"""Lesion Follow-up Tracker views.

Privacy contract: every view requires login. Records are strictly scoped to the
requesting user. There is no way to view another user's records.
"""
from __future__ import annotations

import io
import logging
import secrets
from pathlib import Path

from PIL import Image as PILImage

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.common.services.wrong_input import WrongInputService
from apps.common.services.pdf_report import PdfReportService
from apps.common.services.prediction import PredictionResult

from .models import LesionRecord, FollowUpPhoto

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024


def _feedback(request, level, english, bangla):
    message = bangla if getattr(request, "LANGUAGE_CODE", "en").startswith("bn") else english
    getattr(messages, level)(request, message)


@login_required
def index_view(request):
    """List the user's lesion records."""
    records = LesionRecord.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "tracker/index.html", {"records": records})


@login_required
@require_http_methods(["GET", "POST"])
def create_view(request):
    """Create a new lesion record (with optional first photo)."""
    if request.method == "POST":
        label = (request.POST.get("label", "") or "").strip() or "Untitled lesion"
        body_location = (request.POST.get("body_location", "") or "").strip()
        notes = (request.POST.get("notes", "") or "").strip()
        captured_at = request.POST.get("captured_at")
        uploaded = request.FILES.get("image")

        record = LesionRecord.objects.create(
            user=request.user,
            lesion_id=secrets.token_hex(6).upper(),
            label=label[:128],
            body_location=body_location[:64],
            notes=notes[:4000],
        )

        if uploaded:
            if uploaded.content_type not in ALLOWED_TYPES:
                _feedback(request, "error", "Unsupported image type.", "এই ছবির ফাইলের ধরন সমর্থিত নয়।")
                return redirect("tracker:detail", lesion_id=record.lesion_id)
            if uploaded.size > MAX_BYTES:
                _feedback(request, "error", "Image too large. Max 10 MB.", "ছবিটি অনেক বড়। সর্বোচ্চ ১০ MB হতে পারে।")
                return redirect("tracker:detail", lesion_id=record.lesion_id)
            raw = uploaded.read()
            wrong, pil = WrongInputService.validate_bytes(raw)
            if not wrong.is_valid_image or not pil:
                messages.error(request, wrong.warning)
                return redirect("tracker:detail", lesion_id=record.lesion_id)
            buf = io.BytesIO()
            pil.convert("RGB").save(buf, format="JPEG", quality=90)
            safe = Path(uploaded.name).stem or "photo"
            FollowUpPhoto.objects.create(
                lesion=record,
                captured_at=captured_at or record.created_at.date(),
                note=(request.POST.get("note", "") or "").strip()[:255],
                image=ContentFile(buf.getvalue(), name=f"{safe}.jpg"),
            )

        _feedback(
            request, "success", f"Created lesion record {record.lesion_id}.",
            f"লেসন রেকর্ড {record.lesion_id} তৈরি হয়েছে।",
        )
        return redirect("tracker:detail", lesion_id=record.lesion_id)

    return render(request, "tracker/create.html")


@login_required
def detail_view(request, lesion_id: str):
    """Show timeline of photos."""
    record = get_object_or_404(LesionRecord, lesion_id=lesion_id, user=request.user)
    photos = record.photos.all().order_by("captured_at", "created_at")
    return render(request, "tracker/detail.html", {"record": record, "photos": photos})


@login_required
@require_http_methods(["POST"])
def add_photo_view(request, lesion_id: str):
    """Add a photo to an existing lesion record."""
    record = get_object_or_404(LesionRecord, lesion_id=lesion_id, user=request.user)
    uploaded = request.FILES.get("image")
    if not uploaded:
        _feedback(request, "error", "No image provided.", "কোনো ছবি দেওয়া হয়নি।")
        return redirect("tracker:detail", lesion_id=lesion_id)
    if uploaded.content_type not in ALLOWED_TYPES:
        _feedback(request, "error", "Unsupported image type.", "এই ছবির ফাইলের ধরন সমর্থিত নয়।")
        return redirect("tracker:detail", lesion_id=lesion_id)
    if uploaded.size > MAX_BYTES:
        _feedback(request, "error", "Image too large. Max 10 MB.", "ছবিটি অনেক বড়। সর্বোচ্চ ১০ MB হতে পারে।")
        return redirect("tracker:detail", lesion_id=lesion_id)

    raw = uploaded.read()
    wrong, pil = WrongInputService.validate_bytes(raw)
    if not wrong.is_valid_image or not pil:
        messages.error(request, wrong.warning)
        return redirect("tracker:detail", lesion_id=lesion_id)

    buf = io.BytesIO()
    pil.convert("RGB").save(buf, format="JPEG", quality=90)
    safe = Path(uploaded.name).stem or "photo"
    FollowUpPhoto.objects.create(
        lesion=record,
        captured_at=request.POST.get("captured_at") or record.created_at.date(),
        note=(request.POST.get("note", "") or "").strip()[:255],
        image=ContentFile(buf.getvalue(), name=f"{safe}.jpg"),
    )
    _feedback(request, "success", "Photo added.", "ছবি যোগ করা হয়েছে।")
    return redirect("tracker:detail", lesion_id=lesion_id)


@login_required
@require_http_methods(["GET", "POST"])
def delete_view(request, lesion_id: str):
    record = get_object_or_404(LesionRecord, lesion_id=lesion_id, user=request.user)
    if request.method == "POST":
        # Image files removed via storage
        for photo in record.photos.all():
            if photo.image:
                photo.image.delete(save=False)
        record.delete()
        _feedback(request, "success", "Lesion record deleted.", "লেসন রেকর্ড মুছে ফেলা হয়েছে।")
        return redirect("tracker:index")
    return render(request, "tracker/confirm_delete.html", {"record": record})


@login_required
@require_http_methods(["POST"])
def delete_photo_view(request, lesion_id: str, photo_id: int):
    record = get_object_or_404(LesionRecord, lesion_id=lesion_id, user=request.user)
    photo = get_object_or_404(FollowUpPhoto, lesion=record, id=photo_id)
    if photo.image:
        photo.image.delete(save=False)
    photo.delete()
    _feedback(request, "success", "Photo removed.", "ছবি সরানো হয়েছে।")
    return redirect("tracker:detail", lesion_id=lesion_id)


@login_required
def summary_pdf_view(request, lesion_id: str):
    """Generate a PDF summary of a lesion tracking record."""
    record = get_object_or_404(LesionRecord, lesion_id=lesion_id, user=request.user)
    photos = record.photos.all().order_by("captured_at", "created_at")

    # Build a minimal PDF (text-only, no images) to avoid heavy PIL image embedding
    # in the reportlab canvas. The PDF service is reused with a stub prediction.
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1Brand", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, textColor=colors.HexColor("#0d9488"), spaceAfter=4))
    styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=14))

    flow = [
        Paragraph("DermaCheckerBD", styles["H1Brand"]),
        Paragraph("Lesion follow-up summary — personal observation aid, NOT a medical certificate.", styles["Subtitle"]),
        Spacer(1, 4),
    ]

    rows = [
        ["Reference", record.lesion_id],
        ["Label", record.label],
        ["Body location", record.body_location or "—"],
        ["Created", record.created_at.strftime("%Y-%m-%d")],
        ["Photos", str(photos.count())],
    ]
    if record.notes:
        rows.append(["Notes", record.notes[:300]])
    t = Table(rows, colWidths=[35*mm, 120*mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 10))

    flow.append(Paragraph("Photo timeline", styles["Heading2"]))
    for p in photos:
        flow.append(Paragraph(
            f"<b>{p.captured_at.strftime('%Y-%m-%d')}</b>"
            + (f" — {p.note}" if p.note else ""),
            styles["Normal"],
        ))
        try:
            img_buf = io.BytesIO()
            pil = PILImage.open(p.image.path)
            pil.thumbnail((300, 300))
            pil.convert("RGB").save(img_buf, format="JPEG", quality=85)
            img_buf.seek(0)
            flow.append(RLImage(img_buf, width=70*mm, height=70*mm))
        except Exception as e:
            logger.warning("Could not embed image %s: %s", p.id, e)
        flow.append(Spacer(1, 8))

    flow.append(Spacer(1, 12))
    flow.append(Paragraph(
        "<i>Lighting, distance, angle, and scale can affect comparisons. "
        "The tracker is a personal observation aid only and must not be used "
        "to infer cancer progression. Consult a dermatologist for any concern.</i>",
        styles["Italic"],
    ))

    doc.build(flow)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="dermacheckerbd_tracker_{record.lesion_id}.pdf"'
    return resp
