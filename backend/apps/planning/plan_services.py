"""Building a plan and today's session for a real athlete."""

from __future__ import annotations

import datetime as dt

from apps.activities.models import Activity
from apps.athletes.models import Athlete
from apps.ingest.models import DailyMetrics

from planning.generator import Baseline, Plan, PlanConfig, Session, generate_plan
from planning.readiness import Adjustment, WellnessSnapshot, apply, assess

from .services import mode_for, races_for

BASELINE_WEEKS = 4


def config_from_settings() -> PlanConfig:
    from django.conf import settings

    training = settings.TRAINING
    return PlanConfig(
        max_weekly_increase_pct=training["MAX_WEEKLY_INCREASE_PCT"],
        cutback_every_n_weeks=training["CUTBACK_EVERY_N_WEEKS"],
        cutback_factor=training["CUTBACK_FACTOR"],
        max_hard_sessions_per_week=training["MAX_HARD_SESSIONS_PER_WEEK"],
        max_long_run_pct_of_week=training["MAX_LONG_RUN_PCT_OF_WEEK"],
    )


def baseline_for(athlete: Athlete) -> Baseline:
    """From segmented running history, never from a questionnaire.

    The baseline is the BEST recent week, not the four-week mean. Dividing a total by
    four punishes someone who only started three weeks ago: this athlete's 6.8 km of
    running across two weeks averaged to 1.7 km/week, which then capped his whole
    16-week plan at a 3.6 km peak — arithmetically correct and useless as a plan.

    The best week is what he has demonstrably absorbed, which is the honest place to
    ramp from.
    """
    since = athlete.local_today - dt.timedelta(weeks=BASELINE_WEEKS)
    activities = [
        activity
        for activity in Activity.objects.filter(
            athlete=athlete, sport="running", local_date__gte=since
        ).select_related("metrics")
        if getattr(activity, "metrics", None) and activity.metrics.run_block_count > 0
    ]
    metrics = [a.metrics for a in activities]

    by_week: dict[tuple[int, int], float] = {}
    for activity in activities:
        key = activity.local_date.isocalendar()[:2]
        by_week[key] = by_week.get(key, 0.0) + activity.metrics.run_distance_m
    run_km = (max(by_week.values()) / 1000) if by_week else 0.0
    paces = [m.run_pace_s_per_km for m in metrics if m.run_pace_s_per_km]
    walks = [m.walk_pace_s_per_km for m in metrics if m.walk_pace_s_per_km]

    return Baseline(
        # A floor, so a first-time athlete with no history still gets a plan rather
        # than a division by zero. It is a starting point, not a claim about them.
        run_km_per_week=max(run_km, 1.0),
        longest_run_s=max((m.longest_run_s for m in metrics), default=0.0),
        run_pace_s_per_km=sorted(paces)[len(paces) // 2] if paces else 480.0,
        walk_pace_s_per_km=sorted(walks)[len(walks) // 2] if walks else 700.0,
        available_days=athlete.available_days or {},
        long_run_day=athlete.long_run_day,
    )


def plan_for(athlete: Athlete) -> Plan | None:
    """None when there is no target race to build towards."""
    target = next((r for r in races_for(athlete) if r.is_target), None)
    if target is None:
        upcoming = sorted(
            (r for r in races_for(athlete) if r.date >= athlete.local_today),
            key=lambda r: r.date,
        )
        target = upcoming[0] if upcoming else None
    if target is None:
        return None

    return generate_plan(
        plan_start=athlete.local_today,
        race_date=target.date,
        race_km=target.distance_km,
        baseline=baseline_for(athlete),
        config=config_from_settings(),
    )


def snapshot_for(athlete: Athlete, day: dt.date | None = None) -> WellnessSnapshot:
    day = day or athlete.local_today
    rows = list(
        DailyMetrics.objects.filter(athlete=athlete, metric_date__lte=day)
        .order_by("-metric_date")[:29]
    )
    if not rows:
        return WellnessSnapshot()

    today = rows[0] if rows[0].metric_date == day else None
    history = [r.hrv_overnight_avg for r in rows[1:] if r.hrv_overnight_avg]
    resting = [r.resting_hr for r in rows[1:] if r.resting_hr]

    return WellnessSnapshot(
        readiness=today.training_readiness if today else None,
        sleep_hours=(today.sleep_seconds / 3600) if today and today.sleep_seconds else None,
        hrv=today.hrv_overnight_avg if today else None,
        hrv_baseline=history,
        resting_hr=today.resting_hr if today else None,
        resting_hr_baseline=resting,
    )


def today_session(athlete: Athlete) -> tuple[Session | None, Adjustment | None, str]:
    """Today's prescription, after the readiness rules have had their say.

    Returns (session, adjustment, mode). The session is None on days the mode
    prescribes directly — recovery, maintenance, off_season — because the week table
    has no row that is right for those.
    """
    mode = mode_for(athlete)
    if mode.mode != "build":
        return None, None, mode.mode

    plan = plan_for(athlete)
    if plan is None:
        return None, None, mode.mode

    today = athlete.local_today
    planned = next(
        (s for week in plan.weeks for s in week.sessions if s.date == today), None
    )
    if planned is None:
        return None, None, mode.mode

    adjustment = assess(snapshot_for(athlete))
    return apply(planned, adjustment), adjustment, mode.mode
