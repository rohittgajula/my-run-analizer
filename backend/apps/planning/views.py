import dataclasses

from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.athletes.mixins import AthleteScopedMixin

from .models import Race
from .serializers import RaceSerializer
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
