from django.urls import path

from .views import (
    AthleteDetailView, LoginView, LogoutView, MeView, RefreshView, RegisterView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("athlete/", AthleteDetailView.as_view(), name="athlete"),
]
