"""Building the compact athlete state.

This is where the real work of an AI integration happens. The naive version sends
fifty activities and asks for analysis: it is slower, costs roughly twenty times more,
and gives *worse* answers, because the signal drowns.

Everything here is already computed. The model receives derived numbers and interprets
them; it never does arithmetic.
"""

from __future__ import annotations

import datetime as dt

from apps.activities.models import Activity
from apps.athletes.models import Athlete
from apps.ingest.models import DailyMetrics
from apps.planning.plan_services import baseline_for, plan_for, snapshot_for
from apps.planning.services import mode_for


def _pace(seconds: float | None) -> str | None:
    if not seconds:
        return None
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}/km"


def _minutes(seconds: float | None) -> float | None:
    return round(seconds / 60, 1) if seconds else None


def run_summary(activity: Activity) -> dict:
    """One run, as the numbers that matter rather than as a GPS trace."""
    metrics = getattr(activity, "metrics", None)
    if metrics is None:
        return {"date": activity.local_date, "not_segmented": True}

    return {
        "date": activity.local_date,
        "logged_distance_km": round(activity.total_distance_m / 1000, 2),
        "actually_ran_m": round(metrics.run_distance_m),
        "walked_m": round(metrics.walk_distance_m),
        "run_fraction": round(metrics.run_fraction, 2),
        "run_blocks": metrics.run_block_count,
        "longest_unbroken_run_min": _minutes(metrics.longest_run_s),
        "running_pace": _pace(metrics.run_pace_s_per_km),
        "walking_pace": _pace(metrics.walk_pace_s_per_km),
        "pace_shown_by_watch": _pace(metrics.blended_pace_s_per_km),
        "avg_run_hr": metrics.avg_run_hr,
        "avg_run_cadence": round(metrics.avg_run_cadence_spm) if metrics.avg_run_cadence_spm else None,
        "hr_drift_percent": metrics.hr_drift_percent,
    }


def athlete_state(athlete: Athlete) -> dict:
    """Roughly twenty derived fields. State, not history."""
    today = athlete.local_today
    since = today - dt.timedelta(days=28)

    activities = list(
        Activity.objects.filter(athlete=athlete, sport="running", local_date__gte=since)
        .select_related("metrics")
        .order_by("local_date")
    )
    runs = [a for a in activities if getattr(a, "metrics", None) and a.metrics.run_block_count]

    wellness = list(
        DailyMetrics.objects.filter(athlete=athlete, metric_date__gte=since).order_by("-metric_date")
    )

    def avg(values):
        present = [v for v in values if v is not None]
        return round(sum(present) / len(present), 1) if present else None

    mode = mode_for(athlete)
    plan = plan_for(athlete)
    baseline = baseline_for(athlete)

    state = {
        "today": today,
        "training_mode": mode.mode,
        "weeks_to_target_race": mode.weeks_out,
        "goal": (
            f"{mode.race.distance_km:g} km on {mode.race.date}" if mode.race else "no race set"
        ),
        "runs_last_28_days": len(runs),
        "best_recent_week_run_km": round(baseline.run_km_per_week, 1),
        "longest_unbroken_run_min_ever": _minutes(max((r.metrics.longest_run_s for r in runs), default=0)),
        "longest_unbroken_run_min_recent": _minutes(
            max((r.metrics.longest_run_s for r in runs[-4:]), default=0)
        ),
        "typical_running_pace": _pace(baseline.run_pace_s_per_km),
        "typical_walking_pace": _pace(baseline.walk_pace_s_per_km),
        "avg_run_fraction": avg([r.metrics.run_fraction for r in runs]),
        "training_days_per_week": athlete.training_days_per_week,
        # Wellness, because this athlete's limiting factor has been sleep, not legs.
        "avg_sleep_hours_28d": avg([w.sleep_seconds / 3600 if w.sleep_seconds else None for w in wellness]),
        "sleep_hours_last_night": (
            round(wellness[0].sleep_seconds / 3600, 1)
            if wellness and wellness[0].sleep_seconds else None
        ),
        "avg_hrv_28d": avg([w.hrv_overnight_avg for w in wellness]),
        "hrv_last_night": wellness[0].hrv_overnight_avg if wellness else None,
        "training_readiness_today": wellness[0].training_readiness if wellness else None,
        "lowest_readiness_28d": min(
            (w.training_readiness for w in wellness if w.training_readiness is not None), default=None
        ),
        "resting_hr": wellness[0].resting_hr if wellness else None,
    }

    if plan:
        state["plan"] = {
            "weeks": plan.weeks_available,
            "peak_weekly_run_km": plan.peak_run_km,
            "ideal_peak_weekly_run_km": plan.ideal_peak_run_km,
            "projected_longest_unbroken_min": _minutes(plan.peak_continuous_s),
            "minutes_needed_to_run_race_unbroken": _minutes(plan.race_needs_continuous_s),
            "expected_to_run_walk_the_race": not plan.will_run_continuously,
            "limitations": plan.warnings,
        }

    # The trend, as a short list rather than a table. Direction is what the model can
    # usefully read; the numbers behind it are above.
    if len(runs) >= 3:
        blocks = [(_minutes(r.metrics.longest_run_s), str(r.local_date)) for r in runs[-6:]]
        state["recent_longest_blocks_min"] = [
            {"date": date, "minutes": minutes} for minutes, date in blocks
        ]

    snapshot = snapshot_for(athlete)
    state["reported_by_athlete"] = {
        "pain": snapshot.pain_reported,
        "illness": snapshot.illness_reported,
    }

    # What they have said recently, in their own words. The only input here Garmin
    # cannot supply, and usually the one that explains the numbers.
    from apps.journal.models import JournalEntry

    entries = JournalEntry.objects.filter(
        athlete=athlete, applies_to_date__gte=today - dt.timedelta(days=10)
    ).order_by("-applies_to_date")[:6]
    if entries:
        state["recent_notes"] = [
            {
                "date": str(e.applies_to_date),
                "said": (e.extracted or {}).get("notes_summary") or e.text[:160],
                "rpe": e.rpe,
            }
            for e in entries
        ]
    return state


def recent_runs(athlete: Athlete, limit: int = 8) -> list[dict]:
    activities = (
        Activity.objects.filter(athlete=athlete, sport="running")
        .select_related("metrics")
        .order_by("-local_date")[:limit]
    )
    return [run_summary(a) for a in activities if getattr(a, "metrics", None)]


def weekly_rollup(athlete: Athlete, weeks: int = 4) -> list[dict]:
    today = athlete.local_today
    since = today - dt.timedelta(weeks=weeks)
    activities = (
        Activity.objects.filter(athlete=athlete, sport="running", local_date__gte=since)
        .select_related("metrics")
        .order_by("local_date")
    )

    buckets: dict[tuple[int, int], dict] = {}
    for activity in activities:
        metrics = getattr(activity, "metrics", None)
        if metrics is None or not metrics.run_block_count:
            continue
        key = activity.local_date.isocalendar()[:2]
        bucket = buckets.setdefault(
            key, {"week_starting": None, "runs": 0, "run_km": 0.0, "longest_block_min": 0.0}
        )
        bucket["runs"] += 1
        bucket["run_km"] += metrics.run_distance_m / 1000
        bucket["longest_block_min"] = max(
            bucket["longest_block_min"], (metrics.longest_run_s or 0) / 60
        )
        start = activity.local_date - dt.timedelta(days=activity.local_date.weekday())
        bucket["week_starting"] = str(start)

    return [
        {**b, "run_km": round(b["run_km"], 2), "longest_block_min": round(b["longest_block_min"], 1)}
        for _, b in sorted(buckets.items())
    ]
