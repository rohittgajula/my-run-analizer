from django.urls import path

from .views import (
    DailyMetricsList, garmin_connect_view, garmin_disconnect_view, garmin_status,
    garmin_sync_view,
)

urlpatterns = [
    path("garmin/status/", garmin_status, name="garmin-status"),
    path("garmin/connect/", garmin_connect_view, name="garmin-connect"),
    path("garmin/disconnect/", garmin_disconnect_view, name="garmin-disconnect"),
    path("garmin/sync/", garmin_sync_view, name="garmin-sync"),
    path("wellness/", DailyMetricsList.as_view(), name="wellness"),
]
