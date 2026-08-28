from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.athletes.mixins import AthleteScopedMixin

from .models import Activity
from .serializers import ActivityDetailSerializer, ActivityListSerializer


class ActivityList(AthleteScopedMixin, generics.ListAPIView):
    serializer_class = ActivityListSerializer
    permission_classes = [IsAuthenticated]
    # select_related on the one-to-one avoids a query per row for the metrics.
    queryset = Activity.objects.select_related("metrics").order_by("-started_at")


class ActivityDetail(AthleteScopedMixin, generics.RetrieveAPIView):
    serializer_class = ActivityDetailSerializer
    permission_classes = [IsAuthenticated]
    queryset = Activity.objects.select_related("metrics").prefetch_related("segments")


# A 28-minute run is ~1,670 samples and a long one is far more. Charts cannot show
# that many points and browsers should not have to parse them, so the series is
# downsampled to roughly this many.
CHART_POINTS = 320


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def activity_series(request, pk: int):
    """Per-second data, downsampled for charting.

    Downsampled by BUCKET AVERAGE rather than by taking every Nth sample: naive
    decimation on a noisy optical-HR trace shows whichever beats happened to land on
    the stride, which looks like signal and is not.
    """
    activity = Activity.objects.filter(athlete=request.user.athlete, pk=pk).first()
    if activity is None:
        return Response({"detail": "Not found."}, status=404)

    rows = list(
        activity.records.order_by("offset_s").values(
            "offset_s", "distance_m", "speed_mps", "cadence_spm", "heart_rate", "altitude_m"
        )
    )
    if not rows:
        return Response({"points": [], "has_hr": False, "has_cadence": False})

    step = max(1, len(rows) // CHART_POINTS)
    points = []
    for start in range(0, len(rows), step):
        bucket = rows[start : start + step]

        def mean(key):
            values = [r[key] for r in bucket if r[key] is not None]
            return round(sum(values) / len(values), 1) if values else None

        speed = mean("speed_mps")
        points.append({
            "t": round(bucket[0]["offset_s"]),
            "km": round((bucket[0]["distance_m"] or 0) / 1000, 3),
            # Pace is what a runner reads; speed is what the device stores. Anything
            # slower than 20 min/km is a stop, and plotting it flattens the whole axis.
            "pace": round(1000 / speed) if speed and 1000 / speed < 1200 else None,
            "hr": mean("heart_rate"),
            "cadence": mean("cadence_spm"),
            "altitude": mean("altitude_m"),
        })

    return Response({
        "points": points,
        "sampled_from": len(rows),
        "has_hr": any(p["hr"] for p in points),
        "has_cadence": any(p["cadence"] for p in points),
        "has_altitude": any(p["altitude"] for p in points),
    })
