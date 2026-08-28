from django.urls import path

from .views import RaceDetail, RaceList, predictions, today_mode

urlpatterns = [
    path("races/", RaceList.as_view(), name="race-list"),
    path("races/<int:pk>/", RaceDetail.as_view(), name="race-detail"),
    path("plan/today/", today_mode, name="plan-today"),
    path("plan/predictions/", predictions, name="plan-predictions"),
]
