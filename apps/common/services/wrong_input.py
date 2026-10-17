"""
WrongInputService: pluggable out-of-distribution / non-skin detector.

Goals (all conservative — bias toward flagging, not toward predicting):
- Reject non-image files (handled at the form layer).
- Reject corrupt image files (handled here).
- Reject images with extreme dimensions.
- Coarse non-skin-plausibility flag (delegates to ImageQualityService._skin_ratio).
- Allow an extension point for a real OOD detector (e.g., a one-class SVM over
  image embeddings). Not implemented because we don't ship a pretrained detector.

We do NOT claim reliable OOD detection with simple file validation alone.
If we cannot confidently say an image is in-distribution, we surface a clear
warning and recommend professional review.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import numpy as np
from PIL import Image, UnidentifiedImageError

from django.conf import settings

from .image_quality import ImageQualityService

logger = logging.getLogger(__name__)


class WrongInputReport:
    """Plain class (not a frozen dataclass) so we don't fight with kw-only defaults."""

    __slots__ = (
        "is_valid_image", "looks_like_skin", "in_distribution",
        "warning", "details", "suggestions",
    )

    def __init__(
        self,
        is_valid_image: bool = False,
        looks_like_skin: bool = False,
        in_distribution: Optional[bool] = None,
        warning: str = "",
        details: str = "",
        suggestions: list = None,
    ):
        self.is_valid_image = is_valid_image
        self.looks_like_skin = looks_like_skin
        self.in_distribution = in_distribution
        self.warning = warning
        self.details = details
        self.suggestions = list(suggestions or [])

    def as_dict(self) -> dict:
        return {
            "is_valid_image": self.is_valid_image,
            "looks_like_skin": self.looks_like_skin,
            "in_distribution": self.in_distribution,
            "warning": self.warning,
            "details": self.details,
            "suggestions": self.suggestions,
        }


class WrongInputService:
    SKIN_MIN_RATIO = 0.10

    @classmethod
    def validate_pil(cls, image: Image.Image) -> WrongInputReport:
        if image is None:
            return WrongInputReport(
                is_valid_image=False,
                warning="No image provided.",
                details="The uploaded file could not be parsed as an image.",
                suggestions=["Try uploading a JPG or PNG photo of the skin lesion."],
            )
        return cls._assess(image)

    @classmethod
    def validate_bytes(cls, image_bytes: bytes) -> tuple:
        """Return (report, opened_PIL_image_or_None)."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except (UnidentifiedImageError, OSError, Exception) as e:
            return (
                WrongInputReport(
                    is_valid_image=False,
                    warning="File is corrupt or not a valid image.",
                    details=str(e),
                    suggestions=["Re-export the image as JPG or PNG and try again."],
                ),
                None,
            )

        report = cls._assess(image)
        return report, image

    @classmethod
    def _assess(cls, image: Image.Image) -> WrongInputReport:
        try:
            rgb = image.convert("RGB")
        except Exception as e:
            return WrongInputReport(
                is_valid_image=False,
                warning="Could not process image.",
                details=str(e),
            )

        w, h = rgb.size
        min_dim = min(w, h)
        max_dim = max(w, h)
        if min_dim < 32 or max_dim > settings.IMG_MAX_DIMENSION:
            return WrongInputReport(
                is_valid_image=True,
                looks_like_skin=False,
                in_distribution=False,
                warning=f"Image dimensions {w}x{h}px are outside the supported range.",
                details=f"Min supported side: 32px. Max supported side: {settings.IMG_MAX_DIMENSION}px.",
                suggestions=["Re-capture the photo with appropriate framing."],
            )

        # Coarse skin plausibility
        arr = np.asarray(rgb, dtype=np.uint8)
        skin_ratio = ImageQualityService._skin_ratio(arr)
        looks_like_skin = skin_ratio >= cls.SKIN_MIN_RATIO

        # OOD: unknown (no real detector shipped). We communicate this.
        return WrongInputReport(
            is_valid_image=True,
            looks_like_skin=looks_like_skin,
            in_distribution=None,
            warning=(
                "" if looks_like_skin
                else "This photo doesn't look like a typical skin lesion. The model may be unreliable."
            ),
            details=f"Skin-tone pixel ratio: {skin_ratio*100:.1f}%. No automatic out-of-distribution detector is configured.",
            suggestions=(
                [] if looks_like_skin
                else [
                    "Upload a clear, well-lit close-up of a skin lesion.",
                    "Avoid screenshots, diagrams, or photos of non-skin objects.",
                ]
            ),
        )
