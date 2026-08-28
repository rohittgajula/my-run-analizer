from django.urls import path

from .views import guidance, review, run_analysis, usage

urlpatterns = [
    path("coach/guidance/", guidance, name="coach-guidance"),
    path("coach/weekly/", review, name="coach-weekly"),
    path("coach/usage/", usage, name="coach-usage"),
    path("activities/<int:pk>/analysis/", run_analysis, name="run-analysis"),
]
