from django.urls import path

from .views import (
    RaceDetail, RaceList, plan_weeks, predictions, today_mode, today_session_view,
)

urlpatterns = [
    path("races/", RaceList.as_view(), name="race-list"),
    path("races/<int:pk>/", RaceDetail.as_view(), name="race-detail"),
    path("plan/today/", today_mode, name="plan-today"),
    path("plan/predictions/", predictions, name="plan-predictions"),
    path("plan/weeks/", plan_weeks, name="plan-weeks"),
    path("plan/session/", today_session_view, name="plan-session"),
]
