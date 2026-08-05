from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    """Liveness probe — process only, never the DB. Render's health check
    and the keep-alive pinger both hit this; coupling it to the database
    would drain Neon's compute budget for nothing. The DB wakes on demand
    instead: see accounts.oauth._start_db_wakeup."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/coach/", include("coach.urls")),
]
