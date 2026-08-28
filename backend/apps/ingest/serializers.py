from rest_framework import serializers

from .models import DailyMetrics


class DailyMetricsSerializer(serializers.ModelSerializer):
    acwr = serializers.FloatField(read_only=True)

    class Meta:
        model = DailyMetrics
        # `raw` is deliberately excluded: it is kept for backfilling, not for the
        # client, and it is large.
        exclude = ["id", "athlete", "raw", "updated_at"]
