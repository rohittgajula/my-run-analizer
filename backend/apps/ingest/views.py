"""Garmin connect / disconnect / sync endpoints."""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.athletes.mixins import AthleteScopedMixin
from rest_framework import generics

from .garmin import GarminAuthError, GarminRateLimited, check_connection, sync_athlete
from .models import DailyMetrics
from .serializers import DailyMetricsSerializer
from .garmin_connect import MFARequired, connect, disconnect

logger = logging.getLogger(__name__)


class GarminThrottle(ScopedRateThrottle):
    scope = "garmin"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def garmin_status(request):
    """Re-probes rather than trusting the stored flag — a token can look present and
    no longer work, and reporting a stale 'connected' is worse than reporting nothing."""
    return Response(check_connection(request.user.athlete))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([GarminThrottle])
def garmin_connect_view(request):
    email = (request.data.get("email") or "").strip()
    password = request.data.get("password") or ""
    if not email or not password:
        return Response(
            {"detail": "Garmin email and password are both required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # The password is passed straight through and never stored, logged or echoed.
        return Response(connect(request.user.athlete, email, password))
    except MFARequired as exc:
        return Response({"detail": str(exc), "mfa": True}, status=status.HTTP_400_BAD_REQUEST)
    except GarminRateLimited as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except GarminAuthError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        del password


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def garmin_disconnect_view(request):
    return Response(disconnect(request.user.athlete))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([GarminThrottle])
def garmin_sync_view(request):
    try:
        limit = min(int(request.data.get("limit", 20)), 50)
    except (TypeError, ValueError):
        limit = 20

    try:
        return Response(sync_athlete(request.user.athlete, limit=limit).as_dict())
    except GarminRateLimited as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except GarminAuthError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class DailyMetricsList(AthleteScopedMixin, generics.ListAPIView):
    """Wellness history, newest first. `?days=N` limits the window."""

    serializer_class = DailyMetricsSerializer
    permission_classes = [IsAuthenticated]
    queryset = DailyMetrics.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        try:
            days = min(int(self.request.query_params.get("days", 28)), 365)
        except (TypeError, ValueError):
            days = 28
        return queryset[:days]
