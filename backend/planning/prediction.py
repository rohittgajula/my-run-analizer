"""Finish-time prediction, as an honest range.

The source plan pushed this to "later" and warned against fabricated precision. Both
concerns are met the same way: predict a **range that narrows as data accumulates**,
and refuse to predict at all below a data threshold.

Python produces the range. The model explains what it means and what would move it,
never the reverse — a model asked to predict a finish time will produce a confident
number from nothing.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field
from typing import Literal

MIN_RUNS = 8
MIN_SPAN_WEEKS = 3.0

# Beginners improve fast then plateau. An undamped straight line extrapolates a
# first-timer to a marathon, so growth saturates: over a long horizon the total gain
# approaches slope * SATURATION_WEEKS rather than growing without bound.
SATURATION_WEEKS = 8.0

# Above this ratio of projected capacity to race distance, predict a continuous run.
CONTINUOUS_MARGIN = 1.1

# How many recent runs the pace estimate is taken over.
PACE_WINDOW = 5

# Ceiling on pace degradation beyond demonstrated capacity.
MAX_FADE = 1.35

# Riegel's exponent is fitted on trained runners and flatters beginners over longer
# distances, so this uses a harsher one.
RIEGEL_EXPONENT = 1.12

Mode = Literal["CONTINUOUS", "RUN_WALK", "INSUFFICIENT_DATA"]
Confidence = Literal["NONE", "LOW", "MODERATE"]


@dataclass(frozen=True)
class RunSummary:
    """One segmented run. Everything here comes from `analysis`, never from Garmin."""

    date: dt.date
    run_distance_m: float
    walk_distance_m: float
    run_duration_s: float
    walk_duration_s: float
    longest_run_s: float
    run_pace_s_per_km: float | None
    walk_pace_s_per_km: float | None


@dataclass
class Prediction:
    mode: Mode
    observations: int
    span_weeks: float
    confidence: Confidence
    basis: str
    likely_finish_s: float | None = None
    range_s: tuple[float, float] | None = None
    projected_longest_run_s: float | None = None
    projected_run_fraction: float | None = None
    what_would_change_it: list[str] = field(default_factory=list)


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least squares. Returns (slope, intercept)."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return slope, mean_y - slope * mean_x


def _project(values: list[float], weeks: list[float], horizon_weeks: float) -> float:
    """Saturating projection: gain approaches slope × SATURATION_WEEKS, not infinity."""
    slope, intercept = _linear_fit(weeks, values)
    current = slope * weeks[-1] + intercept
    if slope <= 0:
        # Not improving: project flat rather than extrapolating a decline, which
        # over-punishes one bad session in a small sample.
        return max(current, values[-1])
    import math

    damped = slope * SATURATION_WEEKS * (1 - math.exp(-horizon_weeks / SATURATION_WEEKS))
    return current + damped


def _riegel(known_time_s: float, known_km: float, target_km: float) -> float:
    return known_time_s * (target_km / known_km) ** RIEGEL_EXPONENT


def predict(
    runs: list[RunSummary], race_date: dt.date, race_km: float, today: dt.date
) -> Prediction:
    runs = sorted([r for r in runs if r.run_distance_m > 0], key=lambda r: r.date)

    if not runs:
        return Prediction(
            "INSUFFICIENT_DATA", 0, 0.0, "NONE",
            basis="No segmented runs yet.",
            what_would_change_it=[f"{MIN_RUNS} runs spanning {MIN_SPAN_WEEKS:.0f} weeks"],
        )

    span_weeks = (runs[-1].date - runs[0].date).days / 7
    observations = len(runs)

    # The gate is the whole design. A point estimate off six runs is fiction, and
    # the honest empty state is more useful than a confident wrong number.
    if observations < MIN_RUNS or span_weeks < MIN_SPAN_WEEKS:
        missing = []
        if observations < MIN_RUNS:
            missing.append(f"{MIN_RUNS - observations} more run(s)")
        if span_weeks < MIN_SPAN_WEEKS:
            missing.append(f"{MIN_SPAN_WEEKS - span_weeks:.1f} more week(s) of history")
        return Prediction(
            "INSUFFICIENT_DATA", observations, round(span_weeks, 1), "NONE",
            basis=(
                f"{observations} segmented run(s) over {span_weeks:.1f} weeks. "
                f"Needs {MIN_RUNS} over {MIN_SPAN_WEEKS:.0f}."
            ),
            what_would_change_it=missing,
        )

    horizon_weeks = max((race_date - today).days / 7, 0.0)
    weeks = [(r.date - runs[0].date).days / 7 for r in runs]

    projected_longest = _project([r.longest_run_s for r in runs], weeks, horizon_weeks)

    paced = [r for r in runs if r.run_pace_s_per_km]
    if not paced:
        return Prediction(
            "INSUFFICIENT_DATA", observations, round(span_weeks, 1), "NONE",
            basis="No usable running pace in the history.",
            what_would_change_it=["a run long enough to measure a running pace"],
        )

    # Pace is ESTIMATED from recent history, never extrapolated.
    #
    # Extrapolating a pace trend over a 15-week horizon off a handful of runs is
    # unjustifiable in either direction, and here it was actively wrong: this
    # athlete's pace slowed from 8:11 to 10:40/km *deliberately*, because running
    # easier let his longest block go from 4.8 to 13.9 minutes. A trend fit reads
    # that as decline and projects him slower still. Capacity is the thing with a
    # real trend; pace is a level.
    recent = paced[-PACE_WINDOW:]
    run_pace = statistics.median(r.run_pace_s_per_km for r in recent)
    best_pace = min(r.run_pace_s_per_km for r in paced)

    walk_paces = [r.walk_pace_s_per_km for r in runs if r.walk_pace_s_per_km]
    walk_pace = statistics.median(walk_paces) if walk_paces else run_pace * 1.35

    fractions = [
        r.run_distance_m / (r.run_distance_m + r.walk_distance_m)
        for r in runs
        if r.run_distance_m + r.walk_distance_m > 0
    ]
    projected_fraction = min(_project(fractions, weeks, horizon_weeks), 1.0)

    projected_capacity_m = projected_longest / run_pace * 1000
    race_m = race_km * 1000
    what_would_change: list[str] = []

    if projected_capacity_m >= race_m * CONTINUOUS_MARGIN:
        mode: Mode = "CONTINUOUS"
        best = max(runs, key=lambda r: r.longest_run_s)
        best_km = max(best.longest_run_s / (best.run_pace_s_per_km or run_pace), 0.1)
        likely = _riegel(best.longest_run_s, best_km, race_km)
        what_would_change.append("holding this pace as the long runs get longer")
    else:
        mode = "RUN_WALK"
        # Pace degrades beyond the demonstrated longest block — but never past the
        # walking pace. An athlete who would be slower running than walking simply
        # walks, so a "run" slower than that is not a thing that happens.
        overreach = max(race_m / max(projected_capacity_m, 1), 1.0)
        fade = min(1 + (overreach - 1) * 0.15, MAX_FADE)
        effective_run_pace = min(run_pace * fade, walk_pace)
        likely = race_km * (
            projected_fraction * effective_run_pace + (1 - projected_fraction) * walk_pace
        )
        target_block_min = race_km * run_pace / 60 / 2
        what_would_change.append(
            f"a continuous block of about {target_block_min:.0f} min would move this "
            "to a continuous prediction"
        )
        what_would_change.append("run fraction above 0.7 on a 5 km session")

    # Two bounds that must hold whatever the model says. Violating either produced a
    # four-hour 10K on real data, which is slower than walking the whole way.
    slowest_credible = race_km * walk_pace          # you could just walk it
    fastest_credible = race_km * best_pace          # your best pace, held for longer
    likely = min(max(likely, fastest_credible), slowest_credible)

    spread = 0.10 + 0.012 * horizon_weeks + 0.30 / observations
    confidence: Confidence = "MODERATE" if observations >= 15 and span_weeks >= 6 else "LOW"

    return Prediction(
        mode=mode,
        observations=observations,
        span_weeks=round(span_weeks, 1),
        confidence=confidence,
        basis=(
            f"{observations} segmented runs over {span_weeks:.1f} weeks; "
            f"longest block {runs[-1].longest_run_s / 60:.1f} min, "
            f"projected {projected_longest / 60:.1f} min by race day"
        ),
        likely_finish_s=round(likely),
        range_s=(round(likely * (1 - spread)), round(likely * (1 + spread))),
        projected_longest_run_s=round(projected_longest),
        projected_run_fraction=round(projected_fraction, 2),
        what_would_change_it=what_would_change,
    )
