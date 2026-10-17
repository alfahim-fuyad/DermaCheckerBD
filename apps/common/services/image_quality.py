"""
ImageQualityService: Smart Photo Guide.

Lightweight, dependency-light image-quality checks BEFORE prediction.

Checks performed:
- Blurriness (Laplacian variance via OpenCV)
- Brightness (mean pixel intensity)
- Overexposure / underexposure (clipped-pixel ratio)
- Resolution (min dimension below threshold)
- Aspect ratio / framing (extreme aspect ratios flagged)
- Lesion plausibility ("is this even a skin photo?") — a coarse colour-distribution
  heuristic. NOT a real OOD detector; see WrongInputService for the
  pluggable extension point.

IMPORTANT: The image-quality score is a heuristic, NOT a medical suitability
certificate. A high score does not mean the photo is medically suitable for
diagnosis. We communicate this clearly in the UI and PDF.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import cv2
from PIL import Image

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityCheck:
    name: str
    label: str
    passed: bool
    value: Optional[float] = None
    message: str = ""
    suggestion: str = ""


@dataclass(frozen=True)
class ImageQualityReport:
    overall_score: float  # 0..100
    suitable: bool
    checks: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    image_size: tuple = (0, 0)

    def as_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "suitable": self.suitable,
            "checks": [
                {
                    "name": c.name,
                    "label": c.label,
                    "passed": c.passed,
                    "value": round(c.value, 2) if c.value is not None else None,
                    "message": c.message,
                    "suggestion": c.suggestion,
                }
                for c in self.checks
            ],
            "suggestions": self.suggestions,
            "image_size": list(self.image_size),
        }


class ImageQualityService:
    """Static methods — no state needed."""

    THRESHOLDS = {
        "blur": settings.IMG_BLUR_THRESHOLD,
        "brightness_min": settings.IMG_BRIGHTNESS_MIN,
        "brightness_max": settings.IMG_BRIGHTNESS_MAX,
        "min_dim": settings.IMG_MIN_DIMENSION,
        "max_dim": settings.IMG_MAX_DIMENSION,
    }

    @classmethod
    def assess_pil(cls, image: Image.Image) -> ImageQualityReport:
        if image is None:
            raise ValueError("Image is None")
        try:
            image = image.convert("RGB")
        except Exception as e:
            raise ValueError(f"Could not convert image to RGB: {e}") from e

        w, h = image.size
        arr = np.asarray(image, dtype=np.uint8)
        arr_bgr = arr[:, :, ::-1]  # PIL is RGB; OpenCV wants BGR
        gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)

        checks = []

        # --- Resolution ---
        min_dim = min(w, h)
        max_dim = max(w, h)
        if min_dim < cls.THRESHOLDS["min_dim"]:
            res_pass = False
            res_msg = f"Too small: {w}x{h}px (need ≥{cls.THRESHOLDS['min_dim']}px on the short side)."
            res_sug = "Move closer or use a higher-resolution camera."
        elif max_dim > cls.THRESHOLDS["max_dim"]:
            res_pass = True  # not a hard fail, just a note
            res_msg = f"Very large: {w}x{h}px. Will be downscaled internally."
            res_sug = ""
        else:
            res_pass = True
            res_msg = f"Adequate: {w}x{h}px."
            res_sug = ""
        checks.append(QualityCheck(
            name="resolution",
            label="Resolution",
            passed=res_pass,
            value=float(min_dim),
            message=res_msg,
            suggestion=res_sug,
        ))

        # --- Blur (Laplacian variance) ---
        blur_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        blur_pass = blur_val >= cls.THRESHOLDS["blur"]
        checks.append(QualityCheck(
            name="blur",
            label="Sharpness",
            passed=blur_pass,
            value=blur_val,
            message=(
                f"Laplacian variance = {blur_val:.1f} (threshold {cls.THRESHOLDS['blur']:.0f}). "
                + ("Sharp enough." if blur_pass else "Image looks blurry.")
            ),
            suggestion="" if blur_pass else "Hold the camera steady, focus on the lesion, and ensure good lighting.",
        ))

        # --- Brightness (mean intensity) ---
        brightness = float(gray.mean())
        brightness_pass = cls.THRESHOLDS["brightness_min"] <= brightness <= cls.THRESHOLDS["brightness_max"]
        checks.append(QualityCheck(
            name="brightness",
            label="Brightness",
            passed=brightness_pass,
            value=brightness,
            message=(
                f"Mean intensity = {brightness:.1f}. "
                + ("OK." if brightness_pass else (
                    "Too dark." if brightness < cls.THRESHOLDS["brightness_min"] else "Too bright."
                ))
            ),
            suggestion="" if brightness_pass else (
                "Increase ambient lighting (avoid direct glare)."
                if brightness < cls.THRESHOLDS["brightness_min"]
                else "Reduce lighting or move away from direct light."
            ),
        ))

        # --- Over/underexposure (clipped pixels) ---
        overexposed = float((gray >= 245).sum() / gray.size)
        underexposed = float((gray <= 10).sum() / gray.size)
        exposure_pass = overexposed < 0.05 and underexposed < 0.05
        checks.append(QualityCheck(
            name="exposure",
            label="Exposure",
            passed=exposure_pass,
            value=max(overexposed, underexposed),
            message=(
                f"Clipped pixels: {overexposed*100:.1f}% highlights, "
                f"{underexposed*100:.1f}% shadows."
                + (" OK." if exposure_pass else " Some detail lost.")
            ),
            suggestion="" if exposure_pass else "Adjust lighting so highlights and shadows keep detail.",
        ))

        # --- Aspect ratio / framing ---
        aspect = max(w, h) / max(min(w, h), 1)
        aspect_pass = aspect <= 2.5
        checks.append(QualityCheck(
            name="aspect",
            label="Framing",
            passed=aspect_pass,
            value=float(aspect),
            message=f"Aspect ratio = {aspect:.2f}. " + ("OK." if aspect_pass else "Unusual cropping."),
            suggestion="" if aspect_pass else "Re-capture with the lesion centered and visible.",
        ))

        # --- Skin plausibility (coarse colour heuristic, NOT an OOD detector) ---
        skin_ratio = cls._skin_ratio(arr)
        skin_pass = skin_ratio >= 0.10
        checks.append(QualityCheck(
            name="skin_plausibility",
            label="Looks like skin?",
            passed=skin_pass,
            value=float(skin_ratio),
            message=(
                f"Skin-tone pixels ≈ {skin_ratio*100:.1f}%. "
                + ("Plausible." if skin_pass else "Doesn't look like a typical skin photo.")
            ),
            suggestion="" if skin_pass else "Capture a close-up of skin on a body part. Do not upload diagrams, screenshots, or unrelated photos.",
        ))

        # --- Overall score ---
        weights = {
            "blur": 0.30,
            "brightness": 0.20,
            "exposure": 0.15,
            "resolution": 0.15,
            "aspect": 0.05,
            "skin_plausibility": 0.15,
        }
        score = 0.0
        for c in checks:
            score += weights.get(c.name, 0.0) * (1.0 if c.passed else 0.0)
        score = round(score * 100, 1)

        suitable = all(c.passed for c in checks if c.name in ("blur", "brightness", "exposure", "resolution", "skin_plausibility"))

        suggestions = [c.suggestion for c in checks if c.suggestion]

        return ImageQualityReport(
            overall_score=score,
            suitable=suitable,
            checks=checks,
            suggestions=suggestions,
            image_size=(w, h),
        )

    @classmethod
    def assess_bytes(cls, image_bytes: bytes) -> ImageQualityReport:
        try:
            image = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise ValueError(f"Could not open image: {e}") from e
        return cls.assess_pil(image)

    @staticmethod
    def _skin_ratio(rgb_arr: np.ndarray) -> float:
        """Coarse skin-tone heuristic. NOT a robust OOD detector."""
        if rgb_arr.size == 0:
            return 0.0
        r = rgb_arr[:, :, 0].astype(int)
        g = rgb_arr[:, :, 1].astype(int)
        b = rgb_arr[:, :, 2].astype(int)
        # Classic RGB skin heuristic
        cond1 = (r > 95) & (g > 40) & (b > 20)
        cond2 = (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)) > 15
        cond3 = np.abs(r - g) > 15
        cond4 = (r > g) & (r > b)
        skin_mask = cond1 & cond2 & cond3 & cond4
        return float(skin_mask.sum() / skin_mask.size)
