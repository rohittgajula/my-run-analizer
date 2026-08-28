"""Heart-rate metrics.

Every function returns None rather than a number when the data cannot support one.
Returning 0.0 for missing data is a lie the whole stack then repeats — and heart rate
is the field most often absent, because a strap slips or a wrist sensor drops out.
"""

from __future__ import annotations

import statistics

from .segmentation import Sample

# Below this share of samples carrying HR, any drift figure is an artefact of which
# half happened to have data rather than of the athlete.
MIN_HR_COVERAGE = 0.8


def hr_coverage(samples: list[Sample]) -> float:
    if not samples:
        return 0.0
    return sum(1 for s in samples if s.heart_rate) / len(samples)


def hr_drift_percent(samples: list[Sample]) -> float | None:
    """(2nd-half mean HR − 1st-half mean HR) / 1st-half mean HR × 100.

    Interpret carefully and never alone. High drift can come from heat, humidity,
    hills, dehydration, fatigue, a slipping sensor, or genuinely insufficient aerobic
    conditioning. It is a question to ask, not an answer.
    """
    if hr_coverage(samples) < MIN_HR_COVERAGE:
        return None

    ordered = sorted(samples, key=lambda s: s.offset_s)
    midpoint = (ordered[0].offset_s + ordered[-1].offset_s) / 2

    first = [s.heart_rate for s in ordered if s.heart_rate and s.offset_s < midpoint]
    second = [s.heart_rate for s in ordered if s.heart_rate and s.offset_s >= midpoint]
    if not first or not second:
        return None

    first_mean = statistics.mean(first)
    if first_mean == 0:
        return None
    return round((statistics.mean(second) - first_mean) / first_mean * 100, 1)


def hr_range(samples: list[Sample]) -> tuple[int, int] | None:
    values = [s.heart_rate for s in samples if s.heart_rate]
    return (min(values), max(values)) if values else None
