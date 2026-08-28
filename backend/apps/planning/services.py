"""Django-facing wrappers over the pure planning modules."""

from __future__ import annotations

import datetime as dt

from apps.activities.models import Activity
from apps.athletes.models import Athlete

from planning.calendar import ModeResult
from planning.calendar import Race as PureRace
from planning.calendar import resolve_mode
from planning.prediction import Prediction, RunSummary, predict

from .models import Race


def races_for(athlete: Athlete) -> list[PureRace]:
    return [
        PureRace(date=r.date, distance_km=r.distance_km, is_target=r.is_target, name=r.name)
        for r in Race.objects.filter(athlete=athlete)
    ]


def mode_for(athlete: Athlete, day: dt.date | None = None) -> ModeResult:
    return resolve_mode(day or athlete.local_today, races_for(athlete))


def run_history(athlete: Athlete) -> list[RunSummary]:
    """Only segmented runs containing actual running.

    A pure walk contributes nothing to a running prediction, and including it would
    drag the run fraction down as though the athlete had tried and failed to run.
    """
    summaries = []
    activities = (
        Activity.objects.filter(athlete=athlete, sport="running")
        .select_related("metrics")
        .order_by("local_date")
    )
    for activity in activities:
        metrics = getattr(activity, "metrics", None)
        if metrics is None or metrics.run_block_count == 0:
            continue
        summaries.append(
            RunSummary(
                date=activity.local_date,
                run_distance_m=metrics.run_distance_m,
                walk_distance_m=metrics.walk_distance_m,
                run_duration_s=metrics.run_duration_s,
                walk_duration_s=metrics.walk_duration_s,
                longest_run_s=metrics.longest_run_s,
                run_pace_s_per_km=metrics.run_pace_s_per_km,
                walk_pace_s_per_km=metrics.walk_pace_s_per_km,
            )
        )
    return summaries


def prediction_for(athlete: Athlete, race: Race) -> Prediction:
    return predict(run_history(athlete), race.date, race.distance_km, athlete.local_today)
