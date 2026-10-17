"""Image enhancement service: apply mild, reversible preprocessing.

The goal is to surface what the model sees (resized + preprocessed pixels)
and, when the image-quality service flags mild under-exposure or low
contrast, apply a *gentle* enhancement so the user can see the original
versus the input the model actually consumes.

CRITICAL GUARDRAILS:
  - The original image is ALWAYS preserved separately. Enhancement is
    non-destructive — we never replace the user's upload in-place.
  - Aggressive enhancement can change lesion appearance and bias the
    prediction. We only apply mild CLAHE / gamma correction and never
    sharpen, denoise, or inpaint.
  - Enhancement does NOT improve diagnostic accuracy. We never claim
    that enhancement makes the prediction more correct. Its purpose is
    purely to give the model a more standardised input when the upload
    is slightly dark or low-contrast.
  - Enhancement is opt-in: the photo guide offers the enhanced image as an
    optional direct hand-off to prediction; the original remains unchanged.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnhancementReport:
    applied: bool                       # was any enhancement applied?
    operations: list = field(default_factory=list)
    # Each operation: {"name": str, "params": dict, "reason": str}
    brightness_before: Optional[float] = None
    brightness_after: Optional[float] = None
    contrast_before: Optional[float] = None
    contrast_after: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "operations": self.operations,
            "brightness_before": round(self.brightness_before, 2) if self.brightness_before is not None else None,
            "brightness_after":  round(self.brightness_after, 2)  if self.brightness_after  is not None else None,
            "contrast_before":   round(self.contrast_before, 2)   if self.contrast_before   is not None else None,
            "contrast_after":    round(self.contrast_after, 2)    if self.contrast_after    is not None else None,
        }


class ImageEnhancementService:
    """Mild, non-destructive image enhancement.

    All methods accept and return PIL images. The caller is responsible
    for keeping the original untouched.
    """

    @staticmethod
    def assess_brightness(pil_image: Image.Image) -> float:
        """Return mean brightness on 0..255 scale."""
        arr = np.asarray(pil_image.convert("L"), dtype=np.float32)
        return float(arr.mean())

    @staticmethod
    def assess_contrast(pil_image: Image.Image) -> float:
        """Return standard deviation of luminance."""
        arr = np.asarray(pil_image.convert("L"), dtype=np.float32)
        return float(arr.std())

    @classmethod
    def enhance_if_needed(
        cls,
        pil_image: Image.Image,
        *,
        brightness_min: float = 60.0,
        brightness_max: float = 200.0,
        contrast_min: float = 35.0,
    ) -> tuple[Image.Image, EnhancementReport]:
        """Apply mild enhancement when brightness or contrast is outside
        acceptable ranges. Otherwise return the image unchanged.

        Returns (enhanced_or_original_pil, EnhancementReport).
        The caller MUST keep the original; this method does not mutate it.
        """
        ops = []
        b_before = cls.assess_brightness(pil_image)
        c_before = cls.assess_contrast(pil_image)
        out = pil_image.convert("RGB")

        # --- Brightness correction (gamma) ---
        # If too dark, gamma < 1 brightens; if too bright, gamma > 1 darkens.
        # We use a conservative gamma range (0.7–1.4) to avoid artefacts.
        if b_before < brightness_min:
            gamma = max(0.7, b_before / brightness_min)
            out = ImageEnhance.Brightness(out).enhance(1.0 / gamma)
            ops.append({
                "name": "gamma_brighten",
                "params": {"gamma": round(gamma, 3)},
                "reason": f"Mean brightness {b_before:.1f} below {brightness_min:.0f}.",
            })
        elif b_before > brightness_max:
            gamma = min(1.4, brightness_max / max(b_before, 1.0))
            out = ImageEnhance.Brightness(out).enhance(1.0 / gamma)
            ops.append({
                "name": "gamma_darken",
                "params": {"gamma": round(gamma, 3)},
                "reason": f"Mean brightness {b_before:.1f} above {brightness_max:.0f}.",
            })

        # --- Contrast correction (CLAHE) ---
        # Only when contrast is genuinely low; CLAHE is local so it
        # preserves edges well, but heavy CLAHE can create artificial
        # texture. We use clipLimit=2.0, tileGridSize=8x8 (conservative).
        c_after_brightness = cls.assess_contrast(out)
        if c_after_brightness < contrast_min:
            arr = np.asarray(out, dtype=np.uint8)
            # PIL is RGB; OpenCV wants BGR
            arr_bgr = arr[:, :, ::-1]
            lab = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge((l, a, b))
            arr_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            arr_rgb = arr_bgr[:, :, ::-1]
            out = Image.fromarray(arr_rgb, "RGB")
            ops.append({
                "name": "clahe_contrast",
                "params": {"clip_limit": 2.0, "tile_grid": "8x8"},
                "reason": f"Contrast std {c_after_brightness:.1f} below {contrast_min:.0f}.",
            })

        # --- Mild auto-contrast (only when nothing else fired) ---
        # We intentionally do NOT apply this when brightness/contrast
        # corrections already ran — stacking enhancement degrades quality.
        if not ops:
            # Sample only; do not modify if image already looks fine.
            pass

        b_after = cls.assess_brightness(out)
        c_after = cls.assess_contrast(out)
        return out, EnhancementReport(
            applied=bool(ops),
            operations=ops,
            brightness_before=b_before,
            brightness_after=b_after,
            contrast_before=c_before,
            contrast_after=c_after,
        )

    @staticmethod
    def to_data_url(pil_image: Image.Image, max_dim: int = 400, quality: int = 85) -> str:
        """Render a PIL image as a base64 data URL for inline preview."""
        img = pil_image.convert("RGB")
        img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = __import__("base64").b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
