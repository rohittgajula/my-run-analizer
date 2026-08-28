"""Run / walk / stop segmentation from per-second samples.

This is the file the project exists for. Garmin reports a 2.65 km run; segmentation
is what reveals that 967 m of it was running, in five blocks, and the rest was walked.

**Why cadence and not speed.** GPS speed is noisy enough that a slow jog and a brisk
walk overlap heavily, and it drifts badly under tree cover or between buildings.
Cadence separates them cleanly: walking sits around 100–125 steps/min and running
almost never drops below 140, however slow the runner is.

Bump ALGORITHM_VERSION whenever classification changes. Stored results carry the
version they were computed under, so old activities can be found and reprocessed.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Iterable, Literal

ALGORITHM_VERSION = 1

Kind = Literal["run", "walk", "stop"]

# Sports where a foot cadence means what this module assumes. Cycling cadence is
# pedal revolutions, and strength work has neither cadence nor distance — running
# either through this would produce confident nonsense.
FOOT_SPORTS = frozenset({"running", "walking", "hiking", "trail_running", "treadmill_running"})

# Below this share of samples carrying a cadence reading, refuse to segment rather
# than classify the gaps. A missing cadence is not a cadence of zero.
MIN_CADENCE_COVERAGE = 0.7

# A block shorter than this is sensor jitter rather than a real change of gait.
MIN_SEGMENT_S = 8.0

# Recovery must span at least this long for HRR60 to mean anything.
MIN_RECOVERY_S = 60.0

# A run block shorter than this does not load the athlete enough for the recovery
# that follows to say anything about fitness.
MIN_RUN_FOR_RECOVERY_S = 60.0

STOP_CADENCE = 30.0
STOP_SPEED_MPS = 0.4


@dataclass(slots=True)
class Sample:
    offset_s: float
    distance_m: float | None = None
    speed_mps: float | None = None
    cadence_spm: float | None = None
    heart_rate: int | None = None


@dataclass
class Segment:
    index: int
    kind: Kind
    start_offset_s: float
    duration_s: float
    distance_m: float
    avg_pace_s_per_km: float | None = None
    avg_cadence_spm: float | None = None
    hr_start: int | None = None
    hr_end: int | None = None
    hr_avg: int | None = None
    hr_max: int | None = None
    hr_recovery_60s: int | None = None
    hr_overshoot_bpm: int | None = None
    samples: list[Sample] = field(default_factory=list, repr=False)


class NotSegmentable(Exception):
    """This activity cannot be honestly segmented. The reason is the message."""


def cadence_coverage(samples: list[Sample]) -> float:
    if not samples:
        return 0.0
    return sum(1 for s in samples if s.cadence_spm is not None) / len(samples)


def check_segmentable(sport: str, samples: list[Sample]) -> None:
    """Raise NotSegmentable rather than returning a plausible wrong answer.

    Without this gate a cycling activity segments into 'stop' from end to end, and a
    strength session reports zero running — both of which look like real measurements
    and are not.
    """
    if sport not in FOOT_SPORTS:
        raise NotSegmentable(f"'{sport}' is not a foot sport; cadence does not mean steps here.")
    if len(samples) < 30:
        raise NotSegmentable(f"only {len(samples)} samples; too short to segment.")
    coverage = cadence_coverage(samples)
    if coverage < MIN_CADENCE_COVERAGE:
        raise NotSegmentable(
            f"only {coverage:.0%} of samples carry a cadence reading "
            f"(need {MIN_CADENCE_COVERAGE:.0%}); no cadence sensor on this activity."
        )


def classify(sample: Sample, run_cadence_threshold: float) -> Kind:
    cadence = sample.cadence_spm
    speed = sample.speed_mps or 0.0

    if cadence is not None and cadence >= run_cadence_threshold:
        return "run"
    # A missing cadence is treated as stopped only when speed agrees. Coverage is
    # gated above, so this path is for isolated dropouts, not whole activities.
    if (cadence is not None and cadence < STOP_CADENCE) or speed < STOP_SPEED_MPS:
        return "stop"
    return "walk"


def _median_hr(samples: list[Sample], lo: float, hi: float) -> int | None:
    """Median HR over [lo, hi). Median resists the single-beat spikes optical wrist
    sensors produce, which reading one endpoint sample would not."""
    values = [s.heart_rate for s in samples if s.heart_rate and lo <= s.offset_s < hi]
    return int(statistics.median(values)) if values else None


def _integrate_speed(samples: list[Sample]) -> float:
    """Distance from speed when the device gave no cumulative distance.

    Multiplies by the real time delta rather than assuming 1 Hz — Garmin drops to
    smart recording on long activities, where assuming one sample per second
    understates distance by whatever the true interval was.
    """
    total = 0.0
    for previous, current in zip(samples, samples[1:]):
        dt = current.offset_s - previous.offset_s
        total += (current.speed_mps or 0.0) * max(dt, 0.0)
    return total


def _finalise(segment: Segment) -> Segment:
    samples = segment.samples
    if not samples:
        return segment

    first, last = samples[0], samples[-1]
    segment.duration_s = max(last.offset_s - first.offset_s, 0.0)

    if first.distance_m is not None and last.distance_m is not None:
        segment.distance_m = max(last.distance_m - first.distance_m, 0.0)
    else:
        segment.distance_m = _integrate_speed(samples)

    if segment.duration_s > 0 and segment.distance_m > 1:
        segment.avg_pace_s_per_km = segment.duration_s / (segment.distance_m / 1000.0)

    cadences = [s.cadence_spm for s in samples if s.cadence_spm is not None]
    if cadences:
        segment.avg_cadence_spm = round(statistics.mean(cadences), 1)

    heart_rates = [s.heart_rate for s in samples if s.heart_rate]
    if heart_rates:
        segment.hr_avg = int(statistics.mean(heart_rates))
        segment.hr_max = max(heart_rates)
        start = first.offset_s
        segment.hr_start = _median_hr(samples, start, start + 5) or heart_rates[0]
        segment.hr_end = (
            _median_hr(samples, last.offset_s - 5, last.offset_s + 1) or heart_rates[-1]
        )

    return segment


def _merge_jitter(segments: list[Segment]) -> list[Segment]:
    """Absorb sub-MIN_SEGMENT_S blocks into a neighbour.

    Without this, one dropped cadence reading mid-run splits a five-minute run block
    into three — which would badly understate the athlete's longest continuous run,
    the single most useful progress signal a beginner has.
    """
    if not segments:
        return []

    output: list[Segment] = [segments[0]]
    for segment in segments[1:]:
        span = segment.samples[-1].offset_s - segment.samples[0].offset_s
        if span < MIN_SEGMENT_S:
            output[-1].samples.extend(segment.samples)
        else:
            output.append(segment)

    # A short FIRST block has no predecessor to be absorbed into, so it survives the
    # loop above and must be folded forwards instead.
    if len(output) > 1:
        head = output[0]
        if head.samples[-1].offset_s - head.samples[0].offset_s < MIN_SEGMENT_S:
            output[1].samples = head.samples + output[1].samples
            output.pop(0)

    # Merging can leave two same-kind blocks adjacent; collapse them.
    collapsed: list[Segment] = [output[0]]
    for segment in output[1:]:
        if segment.kind == collapsed[-1].kind:
            collapsed[-1].samples.extend(segment.samples)
        else:
            collapsed.append(segment)
    return collapsed


def _smoothed_peak_hr(samples: list[Sample], lo: float, hi: float) -> int | None:
    """Highest 5-second median HR in the window, so one spurious beat cannot set the peak."""
    windowed = [s for s in samples if s.heart_rate and lo <= s.offset_s <= hi]
    if not windowed:
        return None
    peaks = [
        median
        for s in windowed
        if (median := _median_hr(windowed, s.offset_s - 2, s.offset_s + 3)) is not None
    ]
    return max(peaks) if peaks else None


def _attach_recovery(segments: list[Segment]) -> None:
    """Two distinct heart-rate signals from each qualifying recovery block.

    `hr_recovery_60s` (HRR60) is the standard fitness marker: peak HR minus HR sixty
    seconds later. Measured **from the peak**, not from the moment running stopped —
    cardiac lag means HR usually keeps climbing 15–25 s into recovery, so measuring
    from the block boundary understates the drop on exactly the athletes who need it
    measured. This should climb over months as aerobic fitness improves.

    `hr_overshoot_bpm` is how much further HR rose *after* stopping. A large overshoot
    means the run block outran the athlete's aerobic system. It should fall towards
    zero as base fitness improves, and it is what flags "that block was too fast".
    """
    for index, segment in enumerate(segments):
        if segment.kind not in ("walk", "stop") or index == 0:
            continue
        previous = segments[index - 1]
        if previous.kind != "run" or previous.duration_s < MIN_RUN_FOR_RECOVERY_S:
            continue
        if segment.duration_s < MIN_RECOVERY_S:
            continue

        run_end = previous.samples[-1].offset_s
        # The peak may sit either side of the boundary, so search across both blocks.
        around_boundary = previous.samples + segment.samples
        peak = _smoothed_peak_hr(around_boundary, run_end - 10, run_end + 30)
        hr_at_60 = _median_hr(segment.samples, run_end + 55, run_end + 65)
        hr_at_run_end = _median_hr(previous.samples, run_end - 5, run_end + 1)

        if peak is not None and hr_at_60 is not None:
            segment.hr_recovery_60s = peak - hr_at_60
        if peak is not None and hr_at_run_end is not None:
            segment.hr_overshoot_bpm = max(peak - hr_at_run_end, 0)


def segment_samples(
    samples: Iterable[Sample], run_cadence_threshold: float = 140.0
) -> list[Segment]:
    """Split an ordered sample series into run/walk/stop blocks."""
    ordered = sorted(samples, key=lambda s: s.offset_s)
    if not ordered:
        return []

    raw: list[Segment] = []
    for sample in ordered:
        kind = classify(sample, run_cadence_threshold)
        if raw and raw[-1].kind == kind:
            raw[-1].samples.append(sample)
        else:
            raw.append(
                Segment(
                    index=len(raw), kind=kind, start_offset_s=sample.offset_s,
                    duration_s=0.0, distance_m=0.0, samples=[sample],
                )
            )

    merged = _merge_jitter(raw)
    for index, segment in enumerate(merged):
        segment.index = index
        segment.start_offset_s = segment.samples[0].offset_s
        _finalise(segment)

    _attach_recovery(merged)
    return merged
