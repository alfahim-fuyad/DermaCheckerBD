"""
MultiImageService: Multi-Image Disagreement Alert.

Compares predictions across N images of the SAME lesion (user-confirmed).

Does NOT auto-average predictions. The output is a report of:
- per-image predictions and confidences
- agreement % (fraction of images that share the modal class)
- disagreement flag (any non-modal class is treated as disagreement)
- a recommendation to seek professional review when disagreement is significant

We assume the user has confirmed these photos are of the same lesion.
"""
from __future__ import annotations

import io
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import List

from PIL import Image

from .prediction import PredictionError, PredictionService, PredictionResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImagePrediction:
    index: int
    image_id: str  # caller-supplied (e.g., uploaded file name or PK)
    prediction: PredictionResult

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "image_id": self.image_id,
            "prediction": self.prediction.as_dict(),
        }


@dataclass(frozen=True)
class MultiImageReport:
    images: List[ImagePrediction] = field(default_factory=list)
    modal_class: str = ""
    modal_name: str = ""
    agreement_pct: float = 0.0  # 0..100
    disagreeing_images: list = field(default_factory=list)
    significant_disagreement: bool = False
    recommendation: str = ""

    def as_dict(self) -> dict:
        return {
            "images": [i.as_dict() for i in self.images],
            "modal_class": self.modal_class,
            "modal_name": self.modal_name,
            "agreement_pct": round(self.agreement_pct, 1),
            "disagreeing_images": self.disagreeing_images,
            "significant_disagreement": self.significant_disagreement,
            "recommendation": self.recommendation,
        }


class MultiImageService:
    # If the modal class covers less than this fraction of images, we consider
    # the disagreement "significant".
    DISAGREEMENT_THRESHOLD = 0.66

    @classmethod
    def compare_pil(cls, images: List[tuple]) -> MultiImageReport:
        """
        Args:
            images: list of (image_id, PIL.Image) pairs.
        """
        if not images:
            return MultiImageReport()
        per_image: List[ImagePrediction] = []
        for idx, (image_id, pil) in enumerate(images):
            try:
                pil = pil.convert("RGB")
                pred = PredictionService.predict_pil(pil)
                per_image.append(ImagePrediction(index=idx, image_id=image_id, prediction=pred))
            except Exception as e:
                logger.exception("Multi-image prediction failed for index=%s", idx)
                raise PredictionError(
                    f"Prediction failed for image {idx + 1}. Please try again."
                ) from e

        if not per_image:
            return MultiImageReport()

        class_counts = Counter(p.prediction.predicted_class for p in per_image)
        modal_class, modal_count = class_counts.most_common(1)[0]
        agreement_pct = 100.0 * modal_count / len(per_image)
        disagreeing = [
            {"index": p.index, "image_id": p.image_id, "class": p.prediction.predicted_class}
            for p in per_image if p.prediction.predicted_class != modal_class
        ]
        significant = agreement_pct < (cls.DISAGREEMENT_THRESHOLD * 100.0)

        if significant:
            recommendation = (
                "Predictions disagree significantly across photos. We recommend "
                "professional dermatology review and do not rely on this prototype's output."
            )
        elif disagreeing:
            recommendation = (
                "Minor disagreement detected. Treat the modal class as a weak signal only."
            )
        else:
            recommendation = (
                "All images agree on the top class. Agreement does NOT equal diagnostic certainty."
            )

        return MultiImageReport(
            images=per_image,
            modal_class=modal_class,
            modal_name=per_image[0].prediction.predicted_name if per_image else "",
            agreement_pct=agreement_pct,
            disagreeing_images=disagreeing,
            significant_disagreement=significant,
            recommendation=recommendation,
        )
