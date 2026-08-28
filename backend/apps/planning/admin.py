from django.contrib import admin

from .models import Race


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "distance_km", "is_target", "athlete")
    list_filter = ("is_target",)
