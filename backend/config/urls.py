from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("apps.athletes.urls")),
    path("api/", include("apps.ingest.urls")),
    path("api/", include("apps.activities.urls")),
    path("api/", include("apps.planning.urls")),
]
