"""The numbers this project exists to produce.

Garmin reports a session total. For a beginner doing run/walk, that total describes
two different activities blended together and therefore describes neither: 2.65 km at
8:27/km was really 967 m of running at 8:15/km plus 1.68 km of walking.

Everything here takes segments, never raw samples, because the split is the point.
"""

from __future__ import annotations

from dataclasses import dataclass

from .segmentation import Segment


@dataclass(slots=True)
class RunningTruth:
    total_distance_m: float
    run_distance_m: float
    walk_distance_m: float
    run_fraction: float

    run_duration_s: float
    walk_duration_s: float
    stop_duration_s: float

    run_block_count: int
    longest_run_m: float
    longest_run_s: float

    run_pace_s_per_km: float | None
    walk_pace_s_per_km: float | None
    blended_pace_s_per_km: float | None

    avg_run_cadence_spm: float | None
    avg_run_hr: int | None

    def __str__(self) -> str:
        return (
            f"{self.run_distance_m:.0f} m run in {self.run_block_count} blocks, "
            f"{self.walk_distance_m:.0f} m walked, longest {self.longest_run_s / 60:.1f} min"
        )


def _pace(distance_m: float, duration_s: float) -> float | None:
    # Under 50 m the pace is dominated by GPS noise and reads as nonsense.
    if distance_m < 50 or duration_s <= 0:
        return None
    return duration_s / (distance_m / 1000.0)


def summarise(segments: list[Segment]) -> RunningTruth:
    runs = [s for s in segments if s.kind == "run"]
    walks = [s for s in segments if s.kind == "walk"]
    stops = [s for s in segments if s.kind == "stop"]

    run_distance = sum(s.distance_m for s in runs)
    walk_distance = sum(s.distance_m for s in walks)
    # Stops cover no meaningful ground but still consume elapsed time.
    total_distance = run_distance + walk_distance + sum(s.distance_m for s in stops)

    run_duration = sum(s.duration_s for s in runs)
    walk_duration = sum(s.duration_s for s in walks)

    longest = max(runs, key=lambda s: s.duration_s, default=None)

    # Weighted by the samples behind each block, so a 30-second block does not
    # count as much as a five-minute one.
    cadences = [(s.avg_cadence_spm, s.duration_s) for s in runs if s.avg_cadence_spm]
    heart_rates = [(s.hr_avg, s.duration_s) for s in runs if s.hr_avg]

    def weighted(pairs) -> float | None:
        weight = sum(w for _, w in pairs)
        return sum(v * w for v, w in pairs) / weight if weight else None

    average_hr = weighted(heart_rates)

    return RunningTruth(
        total_distance_m=total_distance,
        run_distance_m=run_distance,
        walk_distance_m=walk_distance,
        run_fraction=run_distance / total_distance if total_distance else 0.0,
        run_duration_s=run_duration,
        walk_duration_s=walk_duration,
        stop_duration_s=sum(s.duration_s for s in stops),
        run_block_count=len(runs),
        longest_run_m=longest.distance_m if longest else 0.0,
        longest_run_s=longest.duration_s if longest else 0.0,
        # Pace over RUN blocks only. This is the athlete's real running pace; the
        # blended figure below is what the watch shows and is slower than either.
        run_pace_s_per_km=_pace(run_distance, run_duration),
        walk_pace_s_per_km=_pace(walk_distance, walk_duration),
        blended_pace_s_per_km=_pace(total_distance, run_duration + walk_duration),
        avg_run_cadence_spm=round(c, 1) if (c := weighted(cadences)) else None,
        avg_run_hr=int(average_hr) if average_hr else None,
    )
