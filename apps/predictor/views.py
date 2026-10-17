"""Predictor views: upload, predict, result, history, PDF download."""
from __future__ import annotations

import io
import json
import logging
import math
import secrets
from pathlib import Path

from PIL import Image as PILImage

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.services.prediction import (
    InvalidImageError, ModelNotLoadedError, PredictionError, PredictionService,
    confidence_to_fraction,
)
from apps.common.services.image_quality import ImageQualityService
from apps.common.services.reliability import ReliabilityService
from apps.common.services.wrong_input import WrongInputService
from apps.common.services.pdf_report import PdfReportService
from apps.common.services._hydrate import hydrate

from .forms import ImageUploadForm
from .models import PredictionRecord

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def _new_reference_id() -> str:
    return secrets.token_hex(8).upper()


def _save_pil_image_to_field(record: PredictionRecord, pil_image: PILImage, original_name: str):
    """Save a PIL image to the record.image field as JPEG."""
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=92)
    safe_name = get_valid_filename(original_name.strip())[:100] or "patient"
    record.image.save(
        f"{safe_name}_{record.reference_id}.jpg",
        ContentFile(buf.getvalue()),
        save=False,
    )


def _resolve_session_key(request) -> str:
    """Return the visitor's session key, ensuring the session exists."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key or ""


def _scope_queryset(request):
    """Return a queryset of PredictionRecords visible to this request.

    - Authenticated user → their own records only.
    - Anonymous visitor → records created in this session (via session_key).
      Records with session_key='' (legacy) are link-only.
    """
    if request.user.is_authenticated:
        return PredictionRecord.objects.filter(user=request.user)
    sk = _resolve_session_key(request)
    return PredictionRecord.objects.filter(session_key=sk)


@require_http_methods(["GET", "POST"])
def upload_view(request):
    """Upload + predict + report page. Single endpoint for simplicity."""
    if request.method == "POST":
        return _handle_upload(request)
    form = ImageUploadForm()
    return render(request, "predictor/upload.html", {
        "form": form,
        "classes": PredictionService.class_metadata(),
    })


def _handle_upload(request):
    """Process an upload: validate, quality-check, predict, optionally
    reliability-check, save, and redirect to the result page."""
    form = ImageUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        # Surface the actual form errors instead of a generic message so
        # the user knows what went wrong (file type, file size, missing).
        error_msg = "Please correct the errors below."
        if form.errors:
            try:
                first_field = next(iter(form.errors))
                error_msg = "; ".join(form.errors[first_field])
            except Exception:
                pass
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": error_msg,
        })

    uploaded = request.FILES["image"]
    if uploaded.content_type not in ALLOWED_TYPES:
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": f"Unsupported file type {uploaded.content_type!r}. Use JPG, PNG, or WEBP.",
        })
    if uploaded.size > MAX_BYTES:
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": f"File too large ({uploaded.size//1024} KB). Maximum is 10 MB.",
        })

    # Read bytes once
    image_bytes = uploaded.read()
    uploaded.seek(0)

    # Wrong-input protection (corrupt file / non-skin)
    wrong_report, pil_image = WrongInputService.validate_bytes(image_bytes)
    if not wrong_report.is_valid_image or not pil_image:
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": wrong_report.warning,
            "details": wrong_report.details,
            "suggestions": wrong_report.suggestions,
        })

    # Quality check
    try:
        quality_report = ImageQualityService.assess_pil(pil_image)
    except Exception as e:
        logger.warning("Quality check failed: %s", e)
        quality_report = None

    # Predict
    # When the backend is the FastAPI ``api`` backend, forward the
    # ORIGINAL uploaded file to FastAPI — not a PIL-re-encoded version.
    # This guarantees the prediction matches what FastAPI's own Swagger
    # UI returns for the same image (no JPEG re-compression round-trip).
    # For local backends (mock / keras / onnx), keep using the PIL image
    # we already opened (so quality + reliability checks share the same
    # pixels).
    try:
        from apps.common.services.prediction import _APIBackend, PredictionService as _PS
        backend = _PS._resolve_backend()
        if isinstance(backend, _APIBackend):
            # Rewind the uploaded file so FastAPI sees the full bytes.
            uploaded.seek(0)
            prediction = _PS.predict_uploaded(uploaded)
        else:
            prediction = PredictionService.predict_pil(pil_image)
    except InvalidImageError as e:
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": f"Could not process image: {e}",
        })
    except ModelNotLoadedError as e:
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": f"Model is not loaded. {e}",
        })
    except PredictionError:
        logger.exception("Prediction failed.")
        return render(request, "predictor/upload.html", {
            "form": form, "classes": PredictionService.class_metadata(),
            "error": "Prediction could not be completed. Please try again later.",
        })

    # Reliability check (run automatically; user can ignore if not interested)
    try:
        reliability_report = ReliabilityService.assess_pil(pil_image)
    except Exception as e:
        logger.warning("Reliability check failed: %s", e)
        reliability_report = None

    # Save record — scope by user OR session_key for anonymous visitors
    session_key = "" if request.user.is_authenticated else _resolve_session_key(request)
    # ``patient_name`` is accepted only for compatibility with older clients.
    # New uploads store an image label and leave personal patient details empty.
    legacy_patient_name = (request.POST.get("patient_name") or "").strip()
    image_name = (
        form.cleaned_data["image_name"].strip()
        or legacy_patient_name
        or Path(uploaded.name).stem
        or "skin-image"
    )[:255]
    record = PredictionRecord(
        user=request.user if request.user.is_authenticated else None,
        session_key=session_key,
        reference_id=_new_reference_id(),
        image_name=image_name,
        patient_name=legacy_patient_name,
        predicted_class=prediction.predicted_class,
        predicted_name=prediction.predicted_name,
        category=prediction.category,
        confidence=prediction.confidence,
        probabilities=prediction.probabilities,
        quality_report=quality_report.as_dict() if quality_report else {},
        reliability_report=reliability_report.as_dict() if reliability_report else {},
        wrong_input_report=wrong_report.as_dict(),
        backend=prediction.backend,
    )
    _save_pil_image_to_field(record, pil_image, record.image_name)
    record.save()

    return redirect("predictor:result", reference_id=record.reference_id)


def result_view(request, reference_id: str):
    """Display a saved prediction record with all attached reports."""
    record = get_object_or_404(PredictionRecord, reference_id=reference_id)
    # Privacy: anonymous session-scoped records are visible only from the
    # same session; user-linked records require the owner. Legacy records
    # (session_key='' AND user IS NULL) remain link-only.
    if (
        record.user is not None
        and record.user != request.user
        and not request.user.has_perm("predictor.view_medical_priority_queue")
    ):
        return HttpResponseForbidden("This prediction record is private to its owner.")
    if (
        record.user is None
        and record.session_key
        and not request.user.has_perm("predictor.view_medical_priority_queue")
    ):
        # anonymous + session-scoped → require same session
        if _resolve_session_key(request) != record.session_key:
            return HttpResponseForbidden("This prediction record belongs to a different session.")

    # Hydrate the saved JSON dicts into attribute-access objects so the
    # template can use the same attribute syntax as live objects. This
    # replaces the fragile per-page _QualityDTO class.
    quality = hydrate(record.quality_report) if record.quality_report else None
    reliability = hydrate(record.reliability_report) if record.reliability_report else None
    wrong_input = hydrate(record.wrong_input_report) if record.wrong_input_report else None

    class_names = {
        item["code"]: item["name"]
        for item in PredictionService.class_metadata()
    }
    probability_rows = []
    for code, raw_probability in (record.probabilities or {}).items():
        try:
            probability = float(raw_probability)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(probability):
            continue
        probability = min(1.0, max(0.0, probability))
        probability_rows.append({
            "code": code,
            "name": class_names.get(code, code),
            "probability": probability,
            "percent": probability * 100,
        })
    probability_rows.sort(key=lambda row: row["probability"], reverse=True)

    quality_score_percent = None
    if quality and getattr(quality, "overall_score", None) is not None:
        try:
            score = float(quality.overall_score)
            if math.isfinite(score):
                quality_score_percent = min(100.0, max(0.0, score))
        except (TypeError, ValueError):
            pass

    reliability_original_confidence_percent = None
    reliability_agreement_percent = None
    if reliability:
        original = getattr(reliability, "original", {}) or {}
        original_confidence = (
            original.get("confidence") if isinstance(original, dict)
            else getattr(original, "confidence", None)
        )
        try:
            confidence = float(original_confidence)
            if math.isfinite(confidence):
                reliability_original_confidence_percent = (
                    confidence_to_fraction(confidence) * 100
                )
        except (TypeError, ValueError):
            pass

        try:
            agreement = float(getattr(reliability, "agreement_pct", None))
            if math.isfinite(agreement):
                reliability_agreement_percent = min(100.0, max(0.0, agreement))
        except (TypeError, ValueError):
            pass

    return render(request, "predictor/result.html", {
        "record": record,
        "quality": quality,
        "reliability": reliability,
        "wrong_input": wrong_input,
        "classes": PredictionService.class_metadata(),
        "probability_rows": probability_rows,
        # JSON-encoded chart payload for Chart.js consumption on the client.
        # Each row contains {code, name, probability (0..1), percent (0..100)}.
        "probability_chart_json": json.dumps([
            {
                "code": row["code"],
                "name": row["name"],
                "percent": round(row["percent"], 2),
                "category": next(
                    (c["category"] for c in PredictionService.class_metadata()
                     if c["code"] == row["code"]),
                    "unknown",
                ),
            }
            for row in probability_rows
        ]),
        "confidence_percent": confidence_to_fraction(record.confidence) * 100,
        "quality_score_percent": quality_score_percent,
        "reliability_original_confidence_percent": reliability_original_confidence_percent,
        "reliability_agreement_percent": reliability_agreement_percent,
    })


def history_view(request):
    """Show the visitor's prediction history with search, class filter, date
    filter, and JSON export support.

    Query params:
      - q:        full-text search across image_name + predicted_class/name
      - class:    filter by predicted_class (e.g. ?class=mel)
      - since:    ISO date (YYYY-MM-DD) — only show records on/after that date
      - until:    ISO date (YYYY-MM-DD) — only show records on/before that date
      - export:   if 'json', return a JSON download of all matching records
                  (capped at 200 records) instead of the HTML page.
    """
    qs = _scope_queryset(request).order_by("-created_at")

    q = (request.GET.get("q") or "").strip()
    selected_class = (request.GET.get("class") or "").strip().lower()
    since = (request.GET.get("since") or "").strip()
    until = (request.GET.get("until") or "").strip()

    if q:
        qs = qs.filter(
            Q(image_name__icontains=q)
            | Q(predicted_class__icontains=q)
            | Q(predicted_name__icontains=q)
            | Q(reference_id__icontains=q)
        )
    if selected_class:
        qs = qs.filter(predicted_class=selected_class)
    if since:
        qs = qs.filter(created_at__date__gte=since)
    if until:
        qs = qs.filter(created_at__date__lte=until)

    # Export branch — return JSON download for the matched set (capped)
    if request.GET.get("export") == "json":
        export_qs = qs[:200]
        payload = [
            {
                "reference_id": r.reference_id,
                "predicted_class": r.predicted_class,
                "predicted_name": r.predicted_name,
                "category": r.category,
                "confidence": round(confidence_to_fraction(r.confidence), 4),
                "probabilities": r.probabilities,
                "backend": r.backend,
                "image_name": r.image_name,
                "created_at": r.created_at.isoformat(),
            }
            for r in export_qs
        ]
        resp = JsonResponse({"records": payload, "count": len(payload)})
        resp["Content-Disposition"] = (
            'attachment; filename="dermacheckerbd_history.json"'
        )
        return resp

    records = qs[:50]
    for record in records:
        record.confidence_percent = confidence_to_fraction(record.confidence) * 100
    # Class filter dropdown options
    class_filter_options = PredictionService.class_metadata()

    return render(request, "predictor/history.html", {
        "records": records,
        "class_filter_options": class_filter_options,
        # Replicate current filter state for the form's sticky values
        "filters": {
            "q": q,
            "class": selected_class,
            "since": since,
            "until": until,
        },
        "total_matches": qs.count(),
    })


def pdf_report_view(request, reference_id: str):
    """Generate and return a PDF report for a saved prediction."""
    record = get_object_or_404(PredictionRecord, reference_id=reference_id)
    if (
        record.user is not None
        and record.user != request.user
        and not request.user.has_perm("predictor.view_medical_priority_queue")
    ):
        return HttpResponseForbidden("This prediction record is private to its owner.")
    if (
        record.user is None
        and record.session_key
        and not request.user.has_perm("predictor.view_medical_priority_queue")
    ):
        if _resolve_session_key(request) != record.session_key:
            return HttpResponseForbidden("This prediction record belongs to a different session.")
    from apps.common.services.prediction import PredictionResult

    prediction = PredictionResult(
        predicted_class=record.predicted_class,
        predicted_name=record.predicted_name,
        category=record.category,
        confidence=confidence_to_fraction(record.confidence),
        probabilities=record.probabilities,
        backend=record.backend,
    )
    # Hydrate saved JSON dicts into attribute-access objects for the PDF service.
    quality = hydrate(record.quality_report) if record.quality_report else None
    reliability = hydrate(record.reliability_report) if record.reliability_report else None
    wrong_input = hydrate(record.wrong_input_report) if record.wrong_input_report else None

    # Determine the user's language preference for the PDF.
    # The derma_lang cookie is set client-side by main.js when the user
    # clicks the language toggle. Fall back to the request's Accept-Language
    # header, then to English.
    language = request.COOKIES.get("derma_lang", "").strip().lower()
    if language not in ("en", "bn"):
        accept = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").lower()
        language = "bn" if accept.startswith("bn") else "en"

    pdf_bytes = PdfReportService.build_prediction_report(
        reference_id=record.reference_id,
        prediction=prediction,
        quality=quality,
        reliability=reliability,
        wrong_input=wrong_input,
        language=language,
    )
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="dermacheckerbd_{record.reference_id}.pdf"'
    return resp


@require_http_methods(["GET", "POST"])
def delete_record_view(request, reference_id: str):
    """Delete a saved prediction record (owner or same-session only)."""
    record = get_object_or_404(PredictionRecord, reference_id=reference_id)
    # Authorization
    if record.user is not None and record.user != request.user:
        return HttpResponseForbidden("You can only delete your own records.")
    if record.user is None and record.session_key:
        if _resolve_session_key(request) != record.session_key:
            return HttpResponseForbidden("You can only delete your own records.")
    # Legacy records (no user, no session_key) are link-only and cannot
    # be deleted via this view — preserve original behaviour.
    if record.user is None and not record.session_key:
        return HttpResponseForbidden("This anonymous record cannot be deleted.")

    if request.method == "POST":
        if record.image:
            record.image.delete(save=False)
        record.delete()
        return redirect("predictor:history")
    return render(request, "predictor/confirm_delete.html", {"record": record})


@require_http_methods(["GET", "POST"])
def clear_history_view(request):
    """Confirm and delete all prediction records visible to this visitor."""
    records = _scope_queryset(request)
    if request.method == "POST":
        for record in records.only("id", "image").iterator():
            if record.image:
                record.image.delete(save=False)
        records.delete()
        return redirect("predictor:history")
    return render(request, "predictor/confirm_clear_history.html", {
        "record_count": records.count(),
    })
