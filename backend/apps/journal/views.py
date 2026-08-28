from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.athletes.mixins import AthleteScopedMixin

from .models import JournalEntry
from .serializers import JournalEntrySerializer
from .services import chat


class AIThrottle(ScopedRateThrottle):
    """Chat is the one endpoint an athlete can spend money on at will."""

    scope = "ai"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([AIThrottle])
def chat_view(request):
    message = (request.data.get("message") or "").strip()
    if not message:
        return Response({"detail": "Say something first."}, status=status.HTTP_400_BAD_REQUEST)
    if len(message) > 4000:
        return Response(
            {"detail": "That is too long — keep it under 4000 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    entry = chat(request.user.athlete, message)
    return Response(JournalEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class JournalList(AthleteScopedMixin, generics.ListAPIView):
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    queryset = JournalEntry.objects.all()

    def get_queryset(self):
        # Oldest first: this reads as a conversation.
        return super().get_queryset().order_by("created_at")[:200]
