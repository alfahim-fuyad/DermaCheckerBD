"""Multi-image comparison views."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image as PILImage

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.common.services.multi_image import MultiImageService
from apps.common.services.prediction import PredictionError
from apps.common.services.wrong_input import WrongInputService

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 6


@require_http_methods(["GET", "POST"])
def compare_view(request):
    report = None
    error = None
    preview_pairs = None  # list of (index, base64_image)

    if request.method == "POST":
        files = request.FILES.getlist("images")
        if not files:
            error = "No files were uploaded."
        elif len(files) < 2:
            error = "Please upload at least 2 images to compare."
        elif len(files) > MAX_IMAGES:
            error = f"Too many files. Max {MAX_IMAGES} images at once."
        else:
            images_with_ids = []
            previews = []
            for i, f in enumerate(files):
                if f.content_type not in ALLOWED_TYPES:
                    error = f"Unsupported file type: {f.content_type!r}."
                    break
                if f.size > MAX_BYTES:
                    error = f"{f.name} is too large. Max 10 MB."
                    break
                raw = f.read()
                wrong, pil = WrongInputService.validate_bytes(raw)
                if not wrong.is_valid_image or not pil:
                    error = f"{f.name}: {wrong.warning}"
                    break
                if wrong.in_distribution is False:
                    error = f"{f.name}: {wrong.warning}"
                    break
                images_with_ids.append((f.name, pil.convert("RGB")))
                # Build a small base64 thumbnail for preview
                buf = io.BytesIO()
                pil.convert("RGB").resize((160, 160)).save(buf, format="JPEG", quality=80)
                import base64
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                previews.append((i, f"data:image/jpeg;base64,{b64}"))
            if not error and len(images_with_ids) >= 2:
                preview_pairs = previews
                try:
                    report = MultiImageService.compare_pil(images_with_ids)
                    if len(report.images) != len(images_with_ids):
                        raise PredictionError("Not all images could be compared.")
                except PredictionError as e:
                    logger.exception("Multi-image comparison could not predict every image.")
                    error = f"Could not compare images: {e}"
                except Exception:
                    logger.exception("Unexpected multi-image comparison failure.")
                    error = "Could not compare images. Please try again later."

    return render(request, "multi_image/compare.html", {
        "report": report,
        "error": error,
        "preview_pairs": preview_pairs,
        "max_images": MAX_IMAGES,
    })
