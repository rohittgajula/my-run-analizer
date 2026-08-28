from django.contrib import admin

from .models import Athlete


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "timezone", "garmin_connected", "garmin_last_sync")
    list_filter = ("garmin_connected", "timezone")
    search_fields = ("display_name", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")
