"""Similar Case Explorer views.

Feature flag: settings.SIMILAR_CASES_ENABLED.
When disabled, the index view returns a clean 'not configured' page so the
UI is consistent and the user is never silently misled.
"""

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.common.services.similar_cases import SimilarCasesService


@require_http_methods(["GET", "POST"])
def explorer_view(request):
    if not settings.SIMILAR_CASES_ENABLED:
        return render(request, "similar_cases/disabled.html")

    results = None
    error = None
    if request.method == "POST" and "image" in request.FILES:
        from PIL import Image
        from apps.common.services.wrong_input import WrongInputService
        from apps.multi_image.views import ALLOWED_TYPES, MAX_BYTES  # reuse constants

        uploaded = request.FILES["image"]
        if uploaded.content_type not in ALLOWED_TYPES:
            error = "Unsupported file type."
        elif uploaded.size > MAX_BYTES:
            error = "File too large. Max 10 MB."
        else:
            wrong, pil = WrongInputService.validate_bytes(uploaded.read())
            if not wrong.is_valid_image or not pil:
                error = wrong.warning
            else:
                try:
                    results = SimilarCasesService.search(pil, top_k=6)
                except Exception as e:
                    error = f"Could not search: {e}"

    return render(request, "similar_cases/explorer.html", {
        "results": results,
        "error": error,
    })
