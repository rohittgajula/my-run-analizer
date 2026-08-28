from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

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
