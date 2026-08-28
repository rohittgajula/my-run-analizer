from django.contrib import admin

from .models import DailyMetrics, RawFitFile


@admin.register(RawFitFile)
class RawFitFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "athlete", "status", "size_bytes", "uploaded_at")
    list_filter = ("status",)
    search_fields = ("original_name", "sha256")
    readonly_fields = ("sha256", "size_bytes", "uploaded_at", "parsed_at")


@admin.register(DailyMetrics)
class DailyMetricsAdmin(admin.ModelAdmin):
    list_display = ("metric_date", "athlete", "sleep_score", "hrv_overnight_avg",
                    "training_readiness", "acute_load", "resting_hr", "steps")
    date_hierarchy = "metric_date"
    readonly_fields = ("updated_at",)
