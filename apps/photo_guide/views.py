"""Photo guide views."""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

from PIL import Image as PILImage

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.common.services.enhancement import ImageEnhancementService
from apps.common.services.image_quality import ImageQualityService
from apps.common.services.wrong_input import WrongInputService

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def _pil_to_data_url(
    pil_image: PILImage.Image,
    max_dim: int | None = 480,
    *,
    quality: int = 82,
    max_bytes: int | None = None,
) -> str:
    """Render a PIL image as a data: URL so the template can show a preview
    without persisting any file to media/S3 storage.

    The previous implementation wrote a permanent `uploads/qcheck_*.jpg` to
    `default_storage` for every quality-check POST and never deleted it.
    On Render's ephemeral disk this fills the volume; on S3 it accumulates
    billed storage. Inline data URLs are smaller, ephemeral, and free.
    """
    img = pil_image.convert("RGB")
    if max_dim:
        img.thumbnail((max_dim, max_dim))
    def encode(source, image_quality):
        buf = io.BytesIO()
        source.save(buf, format="JPEG", quality=image_quality, optimize=True)
        return buf.getvalue()

    image_bytes = encode(img, quality)
    for compressed_quality in (quality - 8, 72):
        if not max_bytes or len(image_bytes) <= max_bytes:
            break
        image_bytes = encode(img, max(60, compressed_quality))
    while max_bytes and len(image_bytes) > max_bytes and min(img.size) > 224:
        scale = max(0.5, min(0.9, (max_bytes / len(image_bytes)) ** 0.5 * 0.95))
        img = img.resize(
            (max(224, int(img.width * scale)), max(224, int(img.height * scale))),
            PILImage.Resampling.LANCZOS,
        )
        image_bytes = encode(img, 72)
    if max_bytes and len(image_bytes) > max_bytes:
        raise ValueError("Could not prepare an image smaller than the 10 MB upload limit.")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


@require_http_methods(["GET", "POST"])
def quality_check_view(request):
    """Standalone image-quality checker with optional enhancement preview.

    Does NOT run the prediction. Only checks image quality and, if the
    image is slightly dark or low-contrast, shows a side-by-side preview
    of the original versus a mildly enhanced version.

    The user can optionally hand the enhanced image directly to the existing
    prediction flow. Enhancement does NOT improve diagnostic accuracy, and
    the original upload is preserved.
    """
    report = None
    wrong = None
    error = None
    image_data_url = None
    enhanced_data_url = None
    prediction_data_url = None
    customizer_data_url = None
    enhancement_report = None
    uploaded_name = None
    image_name = None

    if request.method == "POST" and "image" in request.FILES:
        uploaded = request.FILES["image"]
        uploaded_name = uploaded.name
        image_name = (
            (request.POST.get("image_name") or "").strip()
            or Path(uploaded.name).stem
            or "skin-image"
        )[:255]
        if uploaded.content_type not in ALLOWED_TYPES:
            error = f"Unsupported file type {uploaded.content_type!r}."
        elif uploaded.size > MAX_BYTES:
            error = "File too large. Max 10 MB."
        else:
            image_bytes = uploaded.read()
            wrong, pil_image = WrongInputService.validate_bytes(image_bytes)
            if not wrong.is_valid_image or not pil_image:
                # Surface wrong_input.warning even when the image is
                # technically readable but doesn't look like skin
                # (looks_like_skin=False). Previously dropped silently.
                error = wrong.warning
            else:
                try:
                    report = ImageQualityService.assess_pil(pil_image)
                    image_data_url = _pil_to_data_url(pil_image)
                    # Preserve the exact uploaded file for prediction when no
                    # enhancement is selected. Re-encoding every upload as a
                    # JPEG here can change an otherwise valid image before it
                    # reaches the configured prediction backend.
                    prediction_data_url = (
                        f"data:{uploaded.content_type};base64,"
                        f"{base64.b64encode(image_bytes).decode('ascii')}"
                    )
                    # Apply mild enhancement only when needed; show side-by-side
                    enhanced_pil, enhancement_report = (
                        ImageEnhancementService.enhance_if_needed(pil_image)
                    )
                    if enhancement_report.applied:
                        enhanced_data_url = _pil_to_data_url(enhanced_pil)
                        prediction_image = enhanced_pil
                        # Keep automatic enhancement as the default prediction
                        # image when the user does not customize it.
                        prediction_data_url = _pil_to_data_url(
                            prediction_image, max_dim=None, quality=88,
                            max_bytes=MAX_BYTES - 64 * 1024,
                        )
                    else:
                        customizer_data_url = _pil_to_data_url(
                            pil_image, max_dim=None, quality=88,
                            max_bytes=MAX_BYTES - 64 * 1024,
                        )
                except Exception as e:
                    logger.warning("Quality check failed: %s", e)
                    error = f"Could not assess image: {e}"

    return render(request, "photo_guide/quality_check.html", {
        "report": report,
        "wrong_input": wrong,
        "error": error,
        "image_data_url": image_data_url,
        "customizer_data_url": customizer_data_url,
        "enhanced_data_url": enhanced_data_url,
        "prediction_data_url": prediction_data_url,
        "enhancement_report": enhancement_report,
        "uploaded_name": uploaded_name,
        "image_name": image_name,
    })
