"""Reliability app: standalone AI Reliability Check page + calibration dashboard."""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image as PILImage

from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from apps.common.services.calibration import CalibrationService
from apps.common.services.reliability import ReliabilityService
from apps.common.services.wrong_input import WrongInputService
from apps.predictor.models import PredictionRecord

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def _pil_to_data_url(pil_image: PILImage.Image, max_dim: int = 480) -> str:
    """Inline data-URL preview — avoids persisting orphan preview files.

    Previously the reliability view wrote a permanent `uploads/reliab_*.jpg`
    to default_storage on every POST and never deleted it. Inline data URLs
    avoid the storage leak entirely.
    """
    img = pil_image.convert("RGB")
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


@require_http_methods(["GET", "POST"])
def check_view(request):
    report = None
    error = None
    image_data_url = None

    image_bytes = None
    if request.method == "POST":
        uploaded = request.FILES.get("image")
        if uploaded is None:
            error = "Please choose an image before running the reliability check."
        elif uploaded.content_type not in ALLOWED_TYPES:
            error = f"Unsupported file type {uploaded.content_type!r}."
        elif uploaded.size > MAX_BYTES:
            error = "File too large. Max 10 MB."
        else:
            image_bytes = uploaded.read()
    elif request.GET.get("reference_id"):
        record = get_object_or_404(
            PredictionRecord, reference_id=request.GET["reference_id"]
        )
        if record.user is not None and record.user != request.user:
            return HttpResponseForbidden(
                "This prediction record is private to its owner."
            )
        if record.user is None and record.session_key:
            if request.session.session_key != record.session_key:
                return HttpResponseForbidden(
                    "This prediction record belongs to a different session."
                )
        try:
            with record.image.open("rb") as image_file:
                image_bytes = image_file.read(MAX_BYTES + 1)
        except (OSError, ValueError):
            logger.warning("Could not read image for prediction %s", record.reference_id)
            error = "The saved image is not available for a reliability check."
        if image_bytes is not None and len(image_bytes) > MAX_BYTES:
            error = "File too large. Max 10 MB."

    if image_bytes is not None and not error:
        wrong, pil_image = WrongInputService.validate_bytes(image_bytes)
        if not wrong.is_valid_image or not pil_image:
            error = wrong.warning
        else:
            try:
                report = ReliabilityService.assess_pil(pil_image)
                image_data_url = _pil_to_data_url(pil_image)
            except Exception as e:
                logger.warning("Reliability check failed: %s", e)
                error = "Could not run reliability check. Please try again."

    return render(request, "reliability/check.html", {
        "report": report,
        "error": error,
        "image_data_url": image_data_url,
    })


@require_http_methods(["GET"])
def dashboard_view(request):
    """Show documented metrics and scoped, saved per-image stability results.

    ECE and Brier score require a labelled validation set. Until one is
    configured, keep calibration metrics pending and show only actual
    reliability reports saved with this visitor's own prediction records.
    """
    documented = CalibrationService.documented_model_metrics()
    for metric in ("test_accuracy", "macro_f1", "macro_auc"):
        documented[f"{metric}_percent"] = documented[metric] * 100

    if request.user.is_authenticated:
        records = PredictionRecord.objects.filter(user=request.user)
    elif request.session.session_key:
        records = PredictionRecord.objects.filter(
            user__isnull=True, session_key=request.session.session_key
        )
    else:
        records = PredictionRecord.objects.none()

    stability_records = []
    for record in (
        records.exclude(reliability_report={})
        .order_by("-created_at")
        .only("reference_id", "created_at", "reliability_report")[:200]
    ):
        report = record.reliability_report
        if not isinstance(report, dict):
            continue
        try:
            agreement = float(report.get("agreement_pct"))
        except (TypeError, ValueError):
            continue
        if not 0 <= agreement <= 100:
            continue
        stability_records.append({
            "reference_id": record.reference_id,
            "date": record.created_at.strftime("%b %d"),
            "agreement_pct": round(agreement, 1),
            "stable": bool(report.get("stable", agreement >= 75)),
        })

    recent_stability = [
        {
            "label": f"{record['date']} · {record['reference_id'][-6:]}",
            "agreement_pct": record["agreement_pct"],
        }
        for record in reversed(stability_records[:20])
    ]
    average_agreement = (
        round(
            sum(item["agreement_pct"] for item in stability_records)
            / len(stability_records),
            1,
        )
        if stability_records else None
    )

    return render(request, "reliability/dashboard.html", {
        "documented": documented,
        "stability_count": len(stability_records),
        "stability_average": average_agreement,
        "stable_count": sum(item["stable"] for item in stability_records),
        "recent_stability": recent_stability,
    })
