import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path


def health_check(request):
    """Simple health check for Railway deployment monitoring."""
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# SPA Serving: In production, serve the React app for all non-API routes.
# Find the frontend index.html at startup.
# ---------------------------------------------------------------------------
_FRONTEND_INDEX = None
if not settings.DEBUG:
    _candidates = [
        os.path.join(settings.BASE_DIR, "static", "frontend", "index.html"),
        os.path.join(str(settings.STATIC_ROOT), "frontend", "index.html"),
    ]
    for _p in _candidates:
        if os.path.exists(_p):
            _FRONTEND_INDEX = _p
            break


def spa_view(request):
    """Serve the React SPA index.html for client-side routing."""
    if _FRONTEND_INDEX:
        with open(_FRONTEND_INDEX) as f:
            return HttpResponse(f.read(), content_type="text/html")
    return JsonResponse(
        {"error": "Frontend not built", "searched": _candidates},
        status=404,
    )


# API and admin routes (always present)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    path("", include("investigations.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# In production with frontend: add SPA catch-all AFTER api routes.
# Also override the root "/" to serve the React app instead of Django template.
if not settings.DEBUG and _FRONTEND_INDEX:
    # Insert root SPA view at the beginning so it takes priority over
    # the Django template views but NOT over api/ routes.
    urlpatterns = [
        path("admin/", admin.site.urls),
        path("api/health/", health_check, name="health_check"),
        # All api/ and legacy Django routes
        path("", include("investigations.urls")),
        # SPA catch-all for any route not matched above
        re_path(r"^(?!api/|admin/|static/|media/).*$", spa_view),
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Override root "/" — replace the Django case_list with React SPA
    urlpatterns.insert(0, path("", spa_view, name="spa_root"))
