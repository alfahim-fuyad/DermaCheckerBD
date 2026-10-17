#!/usr/bin/env python3
"""Generate a small test skin-like image and run a prediction through it
using the mock backend, to verify the full pipeline works."""
import io
import os
import sys

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dermacheckerbd.settings")
sys.path.insert(0, "/home/z/my-project")

import django
django.setup()

import numpy as np
from PIL import Image

from apps.common.services.prediction import PredictionService, CLASS_ORDER
from apps.common.services.image_quality import ImageQualityService
from apps.common.services.reliability import ReliabilityService
from apps.common.services.wrong_input import WrongInputService
from apps.common.services.pdf_report import PdfReportService


def make_test_image():
    """Build a 300x300 RGB image that vaguely resembles skin (warm tones)."""
    rng = np.random.default_rng(seed=42)
    # Skin-tone base: warm beige with noise
    base = np.array([220, 170, 130], dtype=np.uint8)
    arr = np.tile(base, (300, 300, 1)).astype(np.uint8)
    # Add noise
    noise = rng.integers(-20, 20, size=(300, 300, 3), dtype=np.int16)
    arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    # Add a darker lesion blob in the center
    yy, xx = np.mgrid[0:300, 0:300]
    dist = np.sqrt((yy - 150) ** 2 + (xx - 150) ** 2)
    mask = dist < 60
    arr[mask] = [120, 70, 50]  # brown lesion
    # Smear the blob edge
    edge = (dist > 55) & (dist < 65)
    arr[edge] = [180, 120, 90]
    return Image.fromarray(arr, mode="RGB")


def main():
    img = make_test_image()
    print(f"Test image: {img.size}, mode={img.mode}")

    # Save a copy for inspection
    img.save("/home/z/my-project/download/test_image.png")
    print("Saved test image to /home/z/my-project/download/test_image.png")

    # Run wrong-input protection (use validate_bytes to get a tuple, or just use validate_pil)
    wrong = WrongInputService.validate_pil(img)
    print(f"\nWrong-input protection: valid={wrong.is_valid_image}, skin={wrong.looks_like_skin}, in_dist={wrong.in_distribution}")
    if wrong.warning:
        print(f"  Warning: {wrong.warning}")

    # Run image-quality
    quality = ImageQualityService.assess_pil(img)
    print(f"\nImage quality: score={quality.overall_score:.1f}, suitable={quality.suitable}")
    for c in quality.checks:
        status = 'PASS' if c.passed else 'FAIL'
        print(f"  [{status}] {c.label}: {c.message}")

    # Run prediction
    pred = PredictionService.predict_pil(img)
    print(f"\nPrediction: class={pred.predicted_class}, name={pred.predicted_name}")
    print(f"  category={pred.category}, confidence={pred.confidence:.4f}")
    print(f"  backend={pred.backend}")
    print(f"  probabilities:")
    for k, v in sorted(pred.probabilities.items(), key=lambda kv: -kv[1]):
        print(f"    {k}: {v:.4f}")

    # Run reliability
    reliability = ReliabilityService.assess_pil(img)
    print(f"\nReliability: agreement={reliability.agreement_pct:.1f}%, stable={reliability.stable}")
    print(f"  flipped_count={len(reliability.flipped_classes)}")
    for v in reliability.variants:
        same = (v.prediction.predicted_class == reliability.original.predicted_class)
        print(f"  {v.transform:18s} -> {v.prediction.predicted_class:8s} (conf {v.prediction.confidence:.3f}) {'✓' if same else '✗'}")

    # Generate PDF
    pdf_bytes = PdfReportService.build_prediction_report(
        reference_id="TEST0001",
        prediction=pred,
        quality=quality,
        reliability=reliability,
        wrong_input=wrong,
    )
    out_path = "/home/z/my-project/download/test_report.pdf"
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"\nPDF report saved: {out_path} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
