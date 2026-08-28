import datetime as dt

from django.db.models import Q
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.athletes.mixins import AthleteScopedMixin

from .models import Activity
from .serializers import ActivityDetailSerializer, ActivityListSerializer


class ActivityPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ActivityList(AthleteScopedMixin, generics.ListAPIView):
    """Filtered and paginated.

    Filters are applied in the database rather than in the client: an athlete with
    three years of history should not download all of it to look at last week.
    """

    serializer_class = ActivityListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ActivityPagination
    # select_related on the one-to-one avoids a query per row for the metrics.
    queryset = Activity.objects.select_related("metrics").order_by("-started_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        if sport := params.get("sport"):
            queryset = queryset.filter(sport=sport)

        if params.get("ran") == "true":
            # Activities containing actual running, which is not the same as
            # activities Garmin labelled "running".
            queryset = queryset.filter(metrics__run_block_count__gt=0)
        elif params.get("ran") == "false":
            queryset = queryset.filter(
                Q(metrics__isnull=True) | Q(metrics__run_block_count=0)
            )

        for param, lookup in (("from", "local_date__gte"), ("to", "local_date__lte")):
            if raw := params.get(param):
                try:
                    queryset = queryset.filter(**{lookup: dt.date.fromisoformat(raw)})
                except ValueError:
                    pass  # a malformed date filters nothing rather than 500ing

        return queryset


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def activity_facets(request):
    """The values worth offering as filters, and how many each would return.

    Computed from the athlete's own data: offering "cycling" to someone who has never
    cycled is a control that only ever returns nothing.
    """
    base = Activity.objects.filter(athlete=request.user.athlete)
    sports = {}
    for sport in base.values_list("sport", flat=True):
        sports[sport] = sports.get(sport, 0) + 1

    return Response({
        "sports": [{"value": k, "count": v} for k, v in sorted(sports.items(), key=lambda x: -x[1])],
        "with_running": base.filter(metrics__run_block_count__gt=0).count(),
        "total": base.count(),
        "earliest": base.order_by("local_date").values_list("local_date", flat=True).first(),
    })


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
