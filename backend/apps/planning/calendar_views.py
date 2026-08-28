"""A month at a glance: what each day was for, what was planned, what happened."""

from __future__ import annotations

import datetime as dt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.activities.models import Activity
from apps.ingest.models import DailyMetrics
from apps.journal.models import JournalEntry

from planning.calendar import resolve_range

from .plan_services import plan_for
from .services import races_for


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def calendar(request):
    """One month. `?month=YYYY-MM`, defaulting to the athlete's current month."""
    athlete = request.user.athlete
    today = athlete.local_today

    raw = request.query_params.get("month")
    try:
        anchor = dt.date.fromisoformat(f"{raw}-01") if raw else today.replace(day=1)
    except ValueError:
        anchor = today.replace(day=1)

    start = anchor
    end = (anchor.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)

    races = races_for(athlete)
    modes = dict(resolve_range(start, end, races))

    # Planned sessions, keyed by date. The plan is regenerated rather than stored, so
    # this always reflects the data as it stands right now.
    plan = plan_for(athlete)
    zones = athlete.zones()
    phase_by_date: dict[dt.date, str] = {}
    planned: dict[dt.date, dict] = {}

    if plan:
        for week in plan.weeks:
            for session in week.sessions:
                if not (start <= session.date <= end) or session.optional:
                    continue
                phase_by_date[session.date] = week.phase
                band = (
                    zones.band(session.target_zone)
                    if zones and session.target_zone else None
                )
                planned[session.date] = {
                    "kind": session.kind,
                    "run_minutes": session.run_minutes,
                    "walk_minutes": session.walk_minutes,
                    "target_run_m": session.target_run_m,
                    "continuous_target_s": session.continuous_target_s,
                    "purpose": session.purpose,
                    "effort": session.effort,
                    "phase": week.phase,
                    # A pace band and a heart-rate band together, because either
                    # alone is easy to game: pace ignores hills and heat, heart rate
                    # lags by half a minute.
                    "pace_s_per_km": round(athlete.easy_pace_min + athlete.easy_pace_max) // 2
                        if session.kind in ("EASY", "LONG", "RUN_WALK") else None,
                    "zone": session.target_zone,
                    "zone_label": band.label if band else None,
                    "zone_low": band.low if band else None,
                    "zone_high": band.high if band else None,
                    "zone_purpose": band.purpose if band else None,
                }

    actual: dict[dt.date, list] = {}
    for activity in (
        Activity.objects.filter(athlete=athlete, local_date__gte=start, local_date__lte=end)
        .select_related("metrics")
    ):
        metrics = getattr(activity, "metrics", None)
        actual.setdefault(activity.local_date, []).append({
            "id": activity.pk,
            "sport": activity.sport,
            "logged_km": round(activity.total_distance_m / 1000, 2),
            "run_m": round(metrics.run_distance_m) if metrics else None,
            "longest_run_s": metrics.longest_run_s if metrics else None,
        })

    readiness = {
        row.metric_date: row.training_readiness
        for row in DailyMetrics.objects.filter(
            athlete=athlete, metric_date__gte=start, metric_date__lte=end
        )
    }
    noted = set(
        JournalEntry.objects.filter(
            athlete=athlete, applies_to_date__gte=start, applies_to_date__lte=end
        ).values_list("applies_to_date", flat=True)
    )

    days = []
    cursor = start
    while cursor <= end:
        result = modes.get(cursor)
        days.append({
            "date": cursor,
            "mode": result.mode if result else "off_season",
            "is_today": cursor == today,
            "race": (
                {"name": result.race.name, "distance_km": result.race.distance_km}
                if result and result.mode == "race" and result.race else None
            ),
            "phase": phase_by_date.get(cursor),
            "planned": planned.get(cursor),
            "activities": actual.get(cursor, []),
            "readiness": readiness.get(cursor),
            "has_note": cursor in noted,
        })
        cursor += dt.timedelta(days=1)

    return Response({
        "month": anchor.strftime("%Y-%m"),
        "start": start,
        "end": end,
        # Monday-first offset, so the client does not have to know the convention.
        "leading_blanks": start.weekday(),
        "days": days,
    })
