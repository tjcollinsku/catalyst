import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import TemplateView


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
    # Serve index.html for any route that doesn't match an API endpoint.
    # WhiteNoise serves the JS/CSS assets; this just handles the HTML entry.
    _frontend_index = os.path.join(settings.STATIC_ROOT, "frontend", "index.html")

    class SPAView(TemplateView):
        template_name = None

        def get(self, request, *args, **kwargs):
            try:
                with open(_frontend_index) as f:
                    html = f.read()
                from django.http import HttpResponse

                return HttpResponse(html, content_type="text/html")
            except FileNotFoundError:
                return JsonResponse(
                    {"error": "Frontend not built"},
                    status=404,
                )

    urlpatterns += [
        re_path(r"^(?!api/|admin/|static/|media/).*$", SPAView.as_view()),
    ]
