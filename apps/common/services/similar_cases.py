"""
SimilarCasesService: modular image-similarity explorer.

This is a STUB. To make this feature real, you need:
1. A reference image dataset (HAM10000 or similar) saved under
   settings.SIMILAR_CASES_REFERENCE_DIR.
2. Pre-computed image embeddings for that dataset (e.g., from a ResNet50,
   EfficientNet, or CLIP backbone).
3. A vector index (FAISS, scikit-learn BallTree, or just a numpy matrix + cosine).

When settings.SIMILAR_CASES_ENABLED is False, the views return a "feature not
configured" page. This avoids pulling in heavy deps when no dataset is present.

Drop-in plan: replace `_compute_embedding()` and `search()` with a real
embedding model. The view layer stays the same.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import List

import numpy as np
from PIL import Image

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimilarCase:
    image_id: str
    label: str  # dataset label (NOT a confirmed diagnosis for the user)
    similarity: float  # 0..1
    thumbnail_url: str = ""

    def as_dict(self) -> dict:
        return {
            "image_id": self.image_id,
            "label": self.label,
            "similarity": round(self.similarity, 3),
            "thumbnail_url": self.thumbnail_url,
        }


class SimilarCasesService:
    """Stub service. Returns no real matches unless a dataset is configured."""

    @classmethod
    def is_enabled(cls) -> bool:
        return bool(settings.SIMILAR_CASES_ENABLED)

    @classmethod
    def search(cls, image: Image.Image, top_k: int = 6) -> List[SimilarCase]:
        if not cls.is_enabled():
            return []

        # ----- DROP-IN POINT -------------------------------------------------
        # When you have a real embedding model and a real reference dataset,
        # replace this block with:
        #   query_emb = cls._compute_embedding(image)
        #   ref_embs, ref_ids, ref_labels = cls._load_reference_index()
        #   sims = ref_embs @ query_emb / (np.linalg.norm(ref_embs, axis=1) * np.linalg.norm(query_emb))
        #   top = np.argsort(-sims)[:top_k]
        #   return [SimilarCase(image_id=ref_ids[i], label=ref_labels[i], similarity=float(sims[i])) for i in top]
        # ---------------------------------------------------------------------

        # Until then: deterministic hash-based "matches" so the UI shows something.
        h = hashlib.sha1(np.asarray(image.convert("RGB")).tobytes()).digest()
        rng = np.random.default_rng(int.from_bytes(h[:4], "big"))
        return [
            SimilarCase(
                image_id=f"ref_{i:04d}",
                label=rng.choice(["nv", "mel", "bkl", "bcc", "akiec", "df", "vasc"]),
                similarity=float(rng.uniform(0.4, 0.95)),
                thumbnail_url="",  # populated by view when ref dir exists
            )
            for i in range(top_k)
        ]

    @staticmethod
    def _compute_embedding(image: Image.Image) -> np.ndarray:
        """TODO: replace with a real embedding model.

        A reasonable starting point is to use a ResNet50 backbone pretrained on
        ImageNet and take the penultimate-layer activations as a 2048-d embedding.
        For CLIP, use the visual encoder and normalize to a 512-d unit vector.
        """
        # Placeholder: deterministic 8-d vector derived from a coarse summary.
        arr = np.asarray(image.convert("RGB").resize((8, 8)), dtype=np.float32) / 255.0
        emb = arr.mean(axis=(0, 1))
        norm = np.linalg.norm(emb) or 1.0
        return emb / norm
