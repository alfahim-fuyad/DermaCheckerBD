"""Calibration metrics: ECE, Brier score, reliability diagram.

These metrics describe how well a model's softmax probabilities align
with observed correctness. They are computed against a labelled
validation set.

This service is intentionally split from `ReliabilityService`:
reliability measures per-image *stability* (does the prediction
change under mild transforms?); calibration measures model-wide
*trustworthiness* (does an 80% confidence mean 80% accuracy on
similar inputs?).

Until a labelled validation set is wired in, the service exposes a
public interface that takes a list of (probabilities, true_label)
tuples and returns the metrics. The view layer uses this to compute
metrics on a held-out validation set the user uploads, or to display
the README's documented metrics when no such set exists.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalibrationReport:
    n_samples: int
    n_bins: int
    ece: float                       # Expected Calibration Error
    mce: float                       # Maximum Calibration Error
    brier_score: float               # Mean squared error vs one-hot truth
    accuracy: float                  # Top-1 accuracy on the set
    avg_confidence: float            # Mean max-softmax
    bins: List[dict] = field(default_factory=list)
    # Each bin: { bin_low, bin_high, count, avg_conf, acc, gap }

    def as_dict(self) -> dict:
        return {
            "n_samples": self.n_samples,
            "n_bins": self.n_bins,
            "ece": round(self.ece, 4),
            "mce": round(self.mce, 4),
            "brier_score": round(self.brier_score, 4),
            "accuracy": round(self.accuracy, 4),
            "avg_confidence": round(self.avg_confidence, 4),
            "bins": [
                {
                    "bin_low": round(b["bin_low"], 2),
                    "bin_high": round(b["bin_high"], 2),
                    "count": b["count"],
                    "avg_conf": round(b["avg_conf"], 4),
                    "acc": round(b["acc"], 4),
                    "gap": round(b["gap"], 4),
                }
                for b in self.bins
            ],
        }


class CalibrationService:
    """Compute ECE, MCE, Brier score, and a reliability diagram.

    All methods are static and pure — pass them labelled validation data
    and they return a CalibrationReport.
    """

    @staticmethod
    def compute(
        probabilities: Sequence[Sequence[float]],
        true_labels: Sequence[int],
        class_order: Sequence[str],
        n_bins: int = 10,
    ) -> CalibrationReport:
        """Compute calibration metrics.

        Args:
            probabilities: list of length-K softmax vectors (K = number of classes).
            true_labels:   list of integer class indices (same length as probabilities).
            class_order:   list of class codes; index in this list = true_labels.
            n_bins:        number of bins for the reliability diagram (default 10).

        Returns:
            CalibrationReport with ECE, MCE, Brier, accuracy, and per-bin stats.
        """
        if not probabilities or not true_labels:
            return CalibrationReport(0, n_bins, 0.0, 0.0, 0.0, 0.0, 0.0)
        if len(probabilities) != len(true_labels):
            raise ValueError(
                f"len(probabilities)={len(probabilities)} != "
                f"len(true_labels)={len(true_labels)}"
            )
        K = len(class_order)
        probs_arr = np.asarray(probabilities, dtype=np.float32)
        if probs_arr.ndim != 2 or probs_arr.shape[1] != K:
            raise ValueError(
                f"Expected probabilities shape (N, {K}), got {probs_arr.shape}"
            )
        labels_arr = np.asarray(true_labels, dtype=np.int64)
        if labels_arr.min() < 0 or labels_arr.max() >= K:
            raise ValueError(
                f"true_labels must be in [0, {K - 1}], got range "
                f"[{labels_arr.min()}, {labels_arr.max()}]"
            )

        # Top-1 confidence and predicted index
        max_idx = probs_arr.argmax(axis=1)
        max_conf = probs_arr.max(axis=1)
        correct = (max_idx == labels_arr).astype(np.float32)

        n = len(probs_arr)
        accuracy = float(correct.mean())
        avg_conf = float(max_conf.mean())

        # ECE / MCE via uniform-width bins on [0, 1]
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        mce = 0.0
        bins_meta: List[dict] = []
        for i in range(n_bins):
            lo = bin_edges[i]
            hi = bin_edges[i + 1]
            # First bin is inclusive on both sides; others half-open [lo, hi)
            if i == 0:
                mask = (max_conf >= lo) & (max_conf <= hi)
            else:
                mask = (max_conf > lo) & (max_conf <= hi)
            count = int(mask.sum())
            if count == 0:
                bins_meta.append({
                    "bin_low": float(lo), "bin_high": float(hi),
                    "count": 0, "avg_conf": 0.0, "acc": 0.0, "gap": 0.0,
                })
                continue
            bin_conf = float(max_conf[mask].mean())
            bin_acc = float(correct[mask].mean())
            gap = abs(bin_conf - bin_acc)
            ece += (count / n) * gap
            mce = max(mce, gap)
            bins_meta.append({
                "bin_low": float(lo), "bin_high": float(hi),
                "count": count,
                "avg_conf": bin_conf, "acc": bin_acc,
                "gap": float(gap),
            })

        # Brier score = mean over samples of sum_k (p_k - y_k)^2
        one_hot = np.zeros_like(probs_arr)
        one_hot[np.arange(n), labels_arr] = 1.0
        brier = float(((probs_arr - one_hot) ** 2).sum(axis=1).mean())

        return CalibrationReport(
            n_samples=n,
            n_bins=n_bins,
            ece=ece,
            mce=mce,
            brier_score=brier,
            accuracy=accuracy,
            avg_confidence=avg_conf,
            bins=bins_meta,
        )

    @staticmethod
    def documented_model_metrics() -> dict:
        """Return the model metrics documented in the project README.

        These come from the supplied ResNet50 model's reported test
        evaluation (not recomputed here). They are surfaced as
        documentation only — the README explicitly notes they have
        not been independently verified and do not establish clinical
        validity. Never present them as guarantees for an individual
        prediction.
        """
        return {
            "source": (
                "Reported by the model's training pipeline; documented "
                "in the project README. Not independently verified and "
                "do not establish clinical validity."
            ),
            "test_accuracy": 0.7349,
            "macro_f1": 0.6167,
            "macro_auc": 0.9577,
            # The following are placeholders pending a held-out
            # labelled validation set. The view explicitly labels
            # them as 'pending' so we never claim a metric we did not
            # measure.
            "ece": None,
            "brier_score": None,
            "note": (
                "ECE and Brier score require a labelled validation set. "
                "They are not estimated from confidence or stability scores "
                "and remain unavailable until labelled validation data is configured."
            ),
        }
