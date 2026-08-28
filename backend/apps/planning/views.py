import dataclasses

from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.athletes.mixins import AthleteScopedMixin

from .models import Race
from .serializers import RaceSerializer
from .plan_services import plan_for, today_session
from .services import mode_for, prediction_for


class RaceList(AthleteScopedMixin, generics.ListCreateAPIView):
    serializer_class = RaceSerializer
    permission_classes = [IsAuthenticated]
    queryset = Race.objects.all()

    def perform_create(self, serializer):
        serializer.save(athlete=self.request.user.athlete)


class RaceDetail(AthleteScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RaceSerializer
    permission_classes = [IsAuthenticated]
    queryset = Race.objects.all()


def _session_json(session):
    return {
        "date": session.date,
        "kind": session.kind,
        "run_minutes": session.run_minutes,
        "walk_minutes": session.walk_minutes,
        "total_minutes": round(session.total_minutes, 1),
        "target_run_m": session.target_run_m,
        "purpose": session.purpose,
        "effort": session.effort,
        "optional": session.optional,
        "continuous_target_s": session.continuous_target_s,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def plan_weeks(request):
    """The full projection. Regenerated on read rather than stored.

    A plan is a projection, not a document written once — storing it would let it
    drift from the data it was derived from.
    """
    plan = plan_for(request.user.athlete)
    if plan is None:
        return Response({"detail": "No race to build towards."}, status=404)

    return Response({
        "runway": plan.runway,
        "weeks_available": plan.weeks_available,
        "peak_run_km": plan.peak_run_km,
        "ideal_peak_run_km": plan.ideal_peak_run_km,
        "reached_ideal_peak": plan.reached_ideal_peak,
        "peak_continuous_s": plan.peak_continuous_s,
        "race_needs_continuous_s": plan.race_needs_continuous_s,
        "will_run_continuously": plan.will_run_continuously,
        "warnings": plan.warnings,
        "weeks": [
            {
                "index": week.index,
                "weeks_out": week.weeks_out,
                "phase": week.phase,
                "start_date": week.start_date,
                "planned_run_km": week.planned_run_km,
                "continuous_target_s": week.continuous_target_s,
                "is_cutback": week.is_cutback,
                "sessions": [_session_json(s) for s in week.sessions if not s.optional],
            }
            for week in plan.weeks
        ],
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_session_view(request):
    """Today's prescription after the readiness rules have had their say."""
    session, adjustment, mode = today_session(request.user.athlete)
    return Response({
        "mode": mode,
        "session": _session_json(session) if session else None,
        "adjustment": {
            "severity": adjustment.severity,
            "changed": adjustment.changed,
            "dropped": adjustment.drop_session,
            "reasons": adjustment.reasons,
        } if adjustment else None,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_mode(request):
    """What today is for, and how that was decided."""
    athlete = request.user.athlete
    result = mode_for(athlete)
    race = (
        Race.objects.filter(athlete=athlete, date=result.race.date).first()
        if result.race
        else None
    )
    return Response({
        "date": athlete.local_today,
        "mode": result.mode,
        "weeks_out": result.weeks_out,
        "days_to_race": result.days_to_race,
        "note": result.note,
        "race": RaceSerializer(race).data if race else None,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def predictions(request):
    """A range per upcoming race, or an honest refusal.

    Below the data threshold this returns INSUFFICIENT_DATA and no number at all —
    a point estimate off a handful of runs is fiction, and the UI shows nothing
    rather than something wrong.
    """
    athlete = request.user.athlete
    upcoming = Race.objects.filter(athlete=athlete, date__gte=athlete.local_today)
    return Response([
        {"race": RaceSerializer(race).data, **dataclasses.asdict(prediction_for(athlete, race))}
        for race in upcoming
    ])
