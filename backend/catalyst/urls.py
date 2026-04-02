import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path


def health_check(request):
    """Simple health check for Railway deployment monitoring."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    path("", include("investigations.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ---------------------------------------------------------------------------
# SPA Catch-All: In production, serve the React app for any non-API route.
# This lets React Router handle client-side routing (e.g. /cases/abc-123).
# In development, Vite dev server handles this instead.
# ---------------------------------------------------------------------------
if not settings.DEBUG:
    # Look for index.html in multiple possible locations
    _possible_paths = [
        os.path.join(settings.STATIC_ROOT, "frontend", "index.html"),
        os.path.join(settings.BASE_DIR, "static", "frontend", "index.html"),
    ]

    def _find_index_html():
        for p in _possible_paths:
            if os.path.exists(p):
                return p
        return None

    def spa_view(request):
        index_path = _find_index_html()
        if index_path:
            with open(index_path) as f:
                html = f.read()
            return HttpResponse(html, content_type="text/html")
        # Debug info to help diagnose path issues
        return JsonResponse(
            {
                "error": "Frontend not built",
                "searched": _possible_paths,
                "static_root": str(settings.STATIC_ROOT),
                "base_dir": str(settings.BASE_DIR),
            },
            status=404,
        )

    urlpatterns += [
        re_path(r"^(?!api/|admin/|static/|media/).*$", spa_view),
    ]
