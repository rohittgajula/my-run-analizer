from django.urls import path

from .views import ActivityDetail, ActivityList, activity_series

urlpatterns = [
    path("activities/", ActivityList.as_view(), name="activity-list"),
    path("activities/<int:pk>/", ActivityDetail.as_view(), name="activity-detail"),
    path("activities/<int:pk>/series/", activity_series, name="activity-series"),
]
