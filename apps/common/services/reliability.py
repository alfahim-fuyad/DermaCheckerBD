"""
ReliabilityService: AI Reliability Check.

For each uploaded image, we generate several mildly modified variants
(slightly brighter, slightly darker, slightly higher contrast, slightly rotated),
run the prediction on each, and report:
- the original prediction
- the predictions on the variants
- the agreement percentage (fraction of variants whose top-class matches the original)
- a stability flag (agreement < threshold => unstable)

IMPORTANT — what this is NOT:
- It is NOT a calibrated probability of correctness. A 100% agreement score
  does not mean the prediction is right.
- It is NOT an uncertainty score in the Bayesian sense.
- The transforms are deliberately mild so the medical content is preserved.
  We do NOT apply changes that would meaningfully alter the lesion appearance
  (no strong rotations, no colour-jitter that mimics other skin tones, etc.).

The transforms are configurable via settings.RELIABILITY_TRANSFORMS.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from django.conf import settings

from .prediction import PredictionService, PredictionResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VariantResult:
    transform: str
    description: str
    prediction: PredictionResult

    def as_dict(self) -> dict:
        return {
            "transform": self.transform,
            "description": self.description,
            "prediction": self.prediction.as_dict(),
        }


@dataclass(frozen=True)
class ReliabilityReport:
    original: PredictionResult
    variants: List[VariantResult] = field(default_factory=list)
    agreement_pct: float = 0.0  # 0..100
    stable: bool = False
    stability_threshold: float = 75.0
    flipped_classes: list = field(default_factory=list)
    confidence_spread: float = 0.0  # max-min confidence across variants

    def as_dict(self) -> dict:
        return {
            "original": self.original.as_dict(),
            "variants": [v.as_dict() for v in self.variants],
            "agreement_pct": round(self.agreement_pct, 1),
            "stable": self.stable,
            "stability_threshold": self.stability_threshold,
            "flipped_classes": self.flipped_classes,
            "confidence_spread": round(self.confidence_spread, 4),
        }


class ReliabilityService:
    STABILITY_THRESHOLD = 75.0  # variant agreement % must be at least this to be 'stable'

    # Mild transforms. Each returns a new PIL image.
    @staticmethod
    def _t_brightness_up(img: Image.Image) -> Image.Image:
        return ImageEnhance.Brightness(img).enhance(1.15)

    @staticmethod
    def _t_brightness_down(img: Image.Image) -> Image.Image:
        return ImageEnhance.Brightness(img).enhance(0.85)

    @staticmethod
    def _t_contrast_up(img: Image.Image) -> Image.Image:
        return ImageEnhance.Contrast(img).enhance(1.15)

    @staticmethod
    def _t_contrast_down(img: Image.Image) -> Image.Image:
        return ImageEnhance.Contrast(img).enhance(0.85)

    @staticmethod
    def _t_slight_rotation(img: Image.Image) -> Image.Image:
        return img.rotate(5, expand=False, fillcolor=(0, 0, 0))

    @staticmethod
    def _t_mirror(img: Image.Image) -> Image.Image:
        return ImageOps.mirror(img)

    TRANSFORMS = {
        "brightness_up": ("brightness_up", "Brightness +15%", _t_brightness_up.__func__),
        "brightness_down": ("brightness_down", "Brightness -15%", _t_brightness_down.__func__),
        "contrast_up": ("contrast_up", "Contrast +15%", _t_contrast_up.__func__),
        "contrast_down": ("contrast_down", "Contrast -15%", _t_contrast_down.__func__),
        "slight_rotation": ("slight_rotation", "Rotate 5°", _t_slight_rotation.__func__),
        "mirror": ("mirror", "Horizontal mirror", _t_mirror.__func__),
    }

    @classmethod
    def selected_transforms(cls) -> list:
        names = [t.strip() for t in settings.RELIABILITY_TRANSFORMS if t.strip()]
        return [(n, cls.TRANSFORMS[n][1], cls.TRANSFORMS[n][2]) for n in names if n in cls.TRANSFORMS]

    @classmethod
    def assess_pil(cls, image: Image.Image) -> ReliabilityReport:
        image = image.convert("RGB")
        original = PredictionService.predict_pil(image)

        variants: List[VariantResult] = []
        for name, desc, fn in cls.selected_transforms():
            try:
                modified = fn(image)
                pred = PredictionService.predict_pil(modified)
                variants.append(VariantResult(transform=name, description=desc, prediction=pred))
            except Exception as e:
                logger.warning("Reliability transform %s failed: %s", name, e)

        if not variants:
            return ReliabilityReport(
                original=original,
                variants=[],
                agreement_pct=100.0,
                stable=True,
                stability_threshold=cls.STABILITY_THRESHOLD,
                flipped_classes=[],
                confidence_spread=0.0,
            )

        n_match = sum(1 for v in variants if v.prediction.predicted_class == original.predicted_class)
        agreement_pct = 100.0 * n_match / len(variants)

        flipped = [
            {"transform": v.transform, "class": v.prediction.predicted_class}
            for v in variants
            if v.prediction.predicted_class != original.predicted_class
        ]

        confs = [v.prediction.confidence for v in variants] + [original.confidence]
        spread = float(np.max(confs) - np.min(confs)) if confs else 0.0

        return ReliabilityReport(
            original=original,
            variants=variants,
            agreement_pct=agreement_pct,
            stable=agreement_pct >= cls.STABILITY_THRESHOLD,
            stability_threshold=cls.STABILITY_THRESHOLD,
            flipped_classes=flipped,
            confidence_spread=spread,
        )

    @classmethod
    def assess_bytes(cls, image_bytes: bytes) -> ReliabilityReport:
        image = Image.open(io.BytesIO(image_bytes))
        return cls.assess_pil(image)
