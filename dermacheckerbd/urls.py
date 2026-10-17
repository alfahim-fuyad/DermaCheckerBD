"""dermacheckerbd URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def healthz(request):
    """Lightweight health-check endpoint for Render / uptime monitors."""
    return JsonResponse({"status": "ok"})


# Custom error handlers that render our localized 404/500 templates.
# Django looks up these names in the ROOT_URLCONF module.
handler404 = "dermacheckerbd.urls.custom_404"
handler500 = "dermacheckerbd.urls.custom_500"


def custom_404(request, exception=None):
    """Render the localized 404 page instead of Django's default."""
    from django.shortcuts import render
    return render(request, "404.html", status=404)


def custom_500(request):
    """Render the localized 500 page instead of Django's default."""
    from django.shortcuts import render
    return render(request, "500.html", status=500)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="health_check"),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("predict/", include("apps.predictor.urls")),
    path("quality/", include("apps.photo_guide.urls")),
    path("reliability/", include("apps.reliability.urls")),
    path("multi/", include("apps.multi_image.urls")),
    path("tracker/", include("apps.tracker.urls")),
    path("chatbot/", include("apps.chatbot.urls")),
    path("similar/", include("apps.similar_cases.urls")),
    path("disease/", include("apps.education.urls")),
    path("warning-signs/", include("apps.questionnaire.urls")),
    path("doctors/", include("apps.doctors.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")
