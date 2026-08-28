from django.contrib import admin

from .models import Activity, ActivityRecord


class ActivityRecordInline(admin.TabularInline):
    model = ActivityRecord
    extra = 0
    # A run is thousands of rows; the inline exists to confirm they landed, not to browse.
    max_num = 0
    fields = ("offset_s", "distance_m", "speed_mps", "cadence_spm", "heart_rate")
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request)[:50]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "local_date", "sport", "distance_km", "record_count",
        "avg_cadence_spm", "segmentation_version", "athlete",
    )
    list_filter = ("sport", "source", "segmentation_version")
    date_hierarchy = "local_date"
    readonly_fields = ("created_at",)
    inlines = [ActivityRecordInline]

    @admin.display(description="km", ordering="total_distance_m")
    def distance_km(self, obj):
        return f"{obj.total_distance_m / 1000:.2f}"

    @admin.display(description="records")
    def record_count(self, obj):
        return obj.records.count()
