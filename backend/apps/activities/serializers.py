from rest_framework import serializers

from .models import Activity, ActivityMetrics, Segment


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = [
            "index", "kind", "start_offset_s", "duration_s", "distance_m",
            "avg_pace_s_per_km", "avg_cadence_spm",
            "hr_avg", "hr_max", "hr_recovery_60s", "hr_overshoot_bpm",
        ]


class ActivityMetricsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityMetrics
        exclude = ["id", "activity"]


class ActivityListSerializer(serializers.ModelSerializer):
    metrics = ActivityMetricsSerializer(read_only=True)

    class Meta:
        model = Activity
        fields = [
            "id", "local_date", "sport", "started_at",
            "total_distance_m", "total_timer_s", "total_elapsed_s",
            "avg_hr", "max_hr", "avg_cadence_spm",
            "segmentation_version", "metrics",
        ]


class ActivityDetailSerializer(ActivityListSerializer):
    segments = SegmentSerializer(many=True, read_only=True)

    class Meta(ActivityListSerializer.Meta):
        fields = ActivityListSerializer.Meta.fields + [
            "total_ascent_m", "total_descent_m", "calories", "source", "segments",
        ]
