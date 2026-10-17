"""Nearby Doctors & Hospitals — Geoapify Places API integration.

The page itself (GET /doctors/) only renders the template with config.
The actual API calls happen server-side via two JSON endpoints:

- POST /doctors/search/  -> takes {latitude, longitude, radius_km,
                              dermatologists_only?} and returns a list
                              of facilities (no API key in response).
- POST /doctors/geocode/  -> takes {query} and returns a list of
                              matching locations (the JS then calls
                              /doctors/search/ with the first match).

The API key is read from settings.GEOAPIFY_API_KEY and is NEVER passed
to the browser. Both endpoints require a CSRF token (sent by the
frontend on every POST) which closes cross-origin abuse vectors.
"""
from __future__ import annotations

import io
import json
import logging
from functools import wraps
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import localdate
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import PatientProfile
from apps.common.services.geoapify import (
    ALLOWED_RADIUS_KM,
    DEFAULT_RADIUS_KM,
    GeoapifyError,
    geocode as geoapify_geocode,
    is_configured as geoapify_is_configured,
    search_nearby as geoapify_search,
)
from apps.common.services.prediction import confidence_to_fraction, PredictionService
from apps.predictor.models import PredictionRecord

from .forms import ReviewUpdateForm

logger = logging.getLogger(__name__)


def medical_queue_access_required(view):
    """Allow doctors with the queue permission and Django staff/admin users."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated or not (
            user.is_staff or user.has_perm("predictor.view_medical_priority_queue")
        ):
            return render(
                request,
                "doctors/access_denied.html",
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapped


@ensure_csrf_cookie
@require_http_methods(["GET"])
def finder_view(request):
    """Render the nearby doctor finder page.

    Injects only non-secret configuration: the radius options, the
    default radius, the max result count, the Geoapify map tiles URL
    (which DOES contain the API key — that is acceptable per Geoapify's
    terms because the tiles endpoint is rate-limited per-domain and
    the key is meant to be used from the browser for tiles).
    """
    api_key = (getattr(settings, "GEOAPIFY_API_KEY", "") or "").strip()
    map_tiles_url = settings.GEOAPIFY_MAP_TILES_URL
    if "{apiKey}" in map_tiles_url:
        map_tiles_url = map_tiles_url.replace("{apiKey}", api_key)

    return render(request, "doctors/finder.html", {
        "search_radius_km": settings.DOCTOR_SEARCH_RADIUS_KM,
        "max_results": settings.DOCTOR_SEARCH_MAX_RESULTS,
        "radius_options": ALLOWED_RADIUS_KM,
        "default_radius": DEFAULT_RADIUS_KM,
        "geoapify_configured": geoapify_is_configured(),
        "map_tiles_url": map_tiles_url,
        "map_attribution": "© OpenStreetMap contributors, © Geoapify",
    })


def _client_language(request) -> str:
    """Pick a 2-letter language code from the derma_lang cookie, falling
    back to the request's Accept-Language header."""
    cookie_lang = request.COOKIES.get("derma_lang", "").strip().lower()
    if cookie_lang in ("bn", "en"):
        return cookie_lang
    accept = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").lower()
    if accept.startswith("bn"):
        return "bn"
    return "en"


@require_POST
def search_view(request):
    """AJAX endpoint: search for healthcare facilities near a point.

    Expects JSON body:
        {"latitude": 23.81, "longitude": 90.41,
         "radius_km": 5, "dermatologists_only": false}

    Returns the Geoapify service's response verbatim on success, or a
    structured error on failure.
    """
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"success": False, "error": "invalid_request",
             "message": "Invalid request body."},
            status=400,
        )

    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return JsonResponse(
            {"success": False, "error": "missing_coordinates",
             "message": "Latitude and longitude are required."},
            status=400,
        )
    radius_km = data.get("radius_km") or settings.DOCTOR_SEARCH_RADIUS_KM
    derm_only = bool(data.get("dermatologists_only"))
    language = _client_language(request)

    try:
        result = geoapify_search(
            latitude=lat,
            longitude=lon,
            radius_km=radius_km,
            dermatologists_only=derm_only,
            language=language,
        )
    except GeoapifyError as exc:
        # Map known error types to HTTP status codes so the frontend
        # can show a tailored message.
        msg = str(exc)
        if "not configured" in msg:
            status_code = 503  # service unavailable
            err_code = "not_configured"
        elif "out of the supported range" in msg or "Invalid" in msg:
            status_code = 400
            err_code = "invalid_input"
        elif "must be one of" in msg:
            # radius_km not in ALLOWED_RADIUS_KM
            status_code = 400
            err_code = "invalid_input"
        elif "took too long" in msg or "busy" in msg:
            status_code = 504  # gateway timeout
            err_code = "timeout"
        else:
            status_code = 502  # bad gateway (upstream issue)
            err_code = "upstream_error"
        return JsonResponse(
            {"success": False, "error": err_code, "message": msg},
            status=status_code,
        )

    return JsonResponse(result)


@require_POST
def geocode_view(request):
    """AJAX endpoint: convert an area name to coordinates.

    Expects JSON body: {"query": "Dhaka"}

    Returns a list of Geoapify matches; the frontend picks the first
    match and immediately calls /doctors/search/.
    """
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"success": False, "error": "invalid_request",
             "message": "Invalid request body."},
            status=400,
        )

    query = (data.get("query") or "").strip()
    if not query:
        return JsonResponse(
            {"success": False, "error": "missing_query",
             "message": "Please enter a location to search."},
            status=400,
        )

    try:
        result = geoapify_geocode(query=query)
    except GeoapifyError as exc:
        msg = str(exc)
        if "not configured" in msg:
            status_code = 503
            err_code = "not_configured"
        elif "took too long" in msg or "busy" in msg:
            status_code = 504
            err_code = "timeout"
        else:
            status_code = 502
            err_code = "upstream_error"
        return JsonResponse(
            {"success": False, "error": err_code, "message": msg},
            status=status_code,
        )

    return JsonResponse(result)


PRIORITIES = {
    "p1": {
        "label": "P1 — High",
        "classes": {"mel"},
        "reason": "Prompt dermatologist review",
    },
    "p2": {
        "label": "P2 — Elevated",
        "classes": {"bcc", "akiec"},
        "reason": "Timely professional evaluation",
    },
    "p3": {
        "label": "P3 — Context-dependent",
        "classes": set(),
        "reason": "Review according to clinical context",
    },
}


def _priority_for(record):
    code = (record.predicted_class or "").lower()
    for key in ("p1", "p2"):
        if code in PRIORITIES[key]["classes"]:
            return key, PRIORITIES[key]
    return "p3", PRIORITIES["p3"]


def _medical_queue(request):
    queryset = PredictionRecord.objects.select_related(
        "user", "user__patient_profile"
    )
    search = (request.GET.get("q") or "").strip()
    selected_priority = request.GET.get("priority", "").lower()
    selected_class = request.GET.get("class", "").lower()
    selected_status = request.GET.get("review_status", "").lower()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    sort_by = request.GET.get("sort", "submitted")
    if sort_by not in {"submitted", "review_date"}:
        sort_by = "submitted"

    if search:
        queryset = queryset.filter(
            Q(patient_name__icontains=search)
            | Q(image_name__icontains=search)
            | Q(predicted_class__icontains=search)
            | Q(predicted_name__icontains=search)
            | Q(reference_id__icontains=search)
        )
    if selected_class:
        queryset = queryset.filter(predicted_class=selected_class)
    if selected_status in dict(PredictionRecord.REVIEW_STATUS_CHOICES):
        queryset = queryset.filter(review_status=selected_status)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    if selected_priority == "p1":
        queryset = queryset.filter(predicted_class__iexact="mel")
    elif selected_priority == "p2":
        queryset = queryset.filter(predicted_class__in=["bcc", "akiec"])
    elif selected_priority == "p3":
        queryset = queryset.exclude(
            predicted_class__in=["mel", "bcc", "akiec"]
        )

    records = list(queryset)
    for record in records:
        key, priority = _priority_for(record)
        record.priority_key = key
        record.priority_label = priority["label"]
        record.priority_reason = priority["reason"]
        record.confidence_percent = confidence_to_fraction(record.confidence) * 100
        record.patient_display_name = record.patient_name or ""
        record.patient_phone = ""
        record.patient_sex = ""
        record.patient_age = None
        if record.user_id:
            if not record.patient_display_name:
                record.patient_display_name = record.user.get_full_name().strip()
            try:
                profile = record.user.patient_profile
            except PatientProfile.DoesNotExist:
                profile = None
            if profile:
                record.patient_phone = profile.phone.strip()
                record.patient_sex = profile.get_sex_display()
                record.patient_age = profile.age

    priority_order = {"p1": 1, "p2": 2, "p3": 3}
    if sort_by == "review_date":
        records.sort(key=lambda record: (
            priority_order[record.priority_key],
            record.review_date is None,
            record.review_date or date.max,
            -record.created_at.timestamp(),
        ))
    else:
        records.sort(key=lambda record: (
            priority_order[record.priority_key],
            -record.created_at.timestamp(),
        ))

    filters = {
        "q": search,
        "priority": selected_priority,
        "class": selected_class,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "review_status": selected_status,
        "sort": sort_by,
    }
    return records, filters


@require_http_methods(["GET"])
@medical_queue_access_required
def panel_view(request):
    records, filters = _medical_queue(request)
    counts = {
        key: sum(1 for record in records if record.priority_key == key)
        for key in PRIORITIES
    }
    page_obj = Paginator(records, 50).get_page(request.GET.get("page"))
    priority_cards = [
        {"key": key, **priority, "count": counts[key]}
        for key, priority in PRIORITIES.items()
    ]
    return render(request, "doctors/panel.html", {
        "records": page_obj.object_list,
        "page_obj": page_obj,
        "filters": filters,
        "class_options": PredictionService.class_metadata(),
        "review_statuses": PredictionRecord.REVIEW_STATUS_CHOICES,
        "priorities": PRIORITIES,
        "priority_cards": priority_cards,
        "counts": counts,
        "query_string": request.GET.urlencode(),
    })


@require_http_methods(["POST"])
@medical_queue_access_required
def review_update_view(request, reference_id):
    record = get_object_or_404(PredictionRecord, reference_id=reference_id)
    form = ReviewUpdateForm(request.POST, instance=record)
    if form.is_valid():
        updated = form.save(commit=False)
        if updated.review_status == "reviewed" and not updated.review_date:
            updated.review_date = localdate()
        updated.save()
        messages.success(request, f"Follow-up status updated for {record.patient_name or 'patient'}.")
    else:
        messages.error(request, "Please select a valid follow-up status and date.")

    return_to = request.POST.get("return_to", "")
    if not url_has_allowed_host_and_scheme(
        return_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return_to = reverse("doctors:panel")
    return redirect(return_to)


@require_http_methods(["GET", "POST"])
@medical_queue_access_required
def delete_record_view(request, reference_id):
    record = get_object_or_404(PredictionRecord, reference_id=reference_id)
    if request.method == "POST":
        if record.image:
            record.image.delete(save=False)
        record.delete()
        messages.success(request, "The case and its saved image were deleted.")
        return redirect("doctors:panel")

    return render(request, "doctors/confirm_delete.html", {"record": record})


@require_http_methods(["GET"])
@medical_queue_access_required
def serial_report_view(request):
    records, _ = _medical_queue(request)
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.35 * inch,
        leftMargin=0.35 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title="Medical Serial Report",
    )
    styles = getSampleStyleSheet()
    bengali_font_path = settings.BASE_DIR / "static" / "fonts" / "NotoSansBengali-Regular.ttf"
    if "NotoSansBengali" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(
            "NotoSansBengali",
            str(bengali_font_path),
            shapable=True,
        ))
    title_style = ParagraphStyle(
        "SerialReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    note_style = ParagraphStyle(
        "SerialReportDisclaimer",
        parent=styles["BodyText"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#53636a"),
        spaceAfter=12,
    )
    header_style = ParagraphStyle(
        "SerialReportHeader",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8.5,
        alignment=TA_CENTER,
        spaceAfter=0,
    )
    cell_style = ParagraphStyle(
        "SerialReportCell",
        parent=styles["BodyText"],
        fontName="NotoSansBengali",
        fontSize=7,
        leading=8.5,
        spaceAfter=0,
        shaping=True,
    )
    centered_cell_style = ParagraphStyle(
        "SerialReportCenteredCell",
        parent=cell_style,
        alignment=TA_CENTER,
    )
    link_style = ParagraphStyle(
        "SerialReportLink",
        parent=cell_style,
        textColor=colors.HexColor("#087e76"),
    )
    centered_link_style = ParagraphStyle(
        "SerialReportCenteredLink",
        parent=link_style,
        alignment=TA_CENTER,
    )
    headers = [
        "Serial", "Patient name", "Phone", "Image Label", "Sex / age", "Class",
        "Confidence", "Submitted", "Priority reason", "Report",
    ]
    rows = [[Paragraph(escape(label), header_style) for label in headers]]
    for serial, record in enumerate(records, start=1):
        report_url = request.build_absolute_uri(
            reverse("predictor:result", args=[record.reference_id])
        )
        patient = escape(record.patient_display_name or "—")
        phone = escape(record.patient_phone or "—")
        image_label = escape(record.image_name or "—")
        sex_age = " / ".join(
            str(value) for value in (record.patient_sex, record.patient_age)
            if value not in (None, "")
        ) or "—"
        rows.append([
            Paragraph(str(serial), centered_cell_style),
            Paragraph(patient, cell_style),
            Paragraph(phone, centered_cell_style),
            Paragraph(image_label, cell_style),
            Paragraph(escape(sex_age), centered_cell_style),
            Paragraph(escape(record.predicted_class.upper()), centered_cell_style),
            Paragraph(f"{record.confidence_percent:.1f}%", centered_cell_style),
            Paragraph(record.created_at.strftime("%Y-%m-%d"), centered_cell_style),
            Paragraph(escape(record.priority_reason), cell_style),
            Paragraph(
                f'<link href="{escape(report_url)}">Open report</link>',
                centered_link_style,
            ),
        ])

    title = Paragraph("Medical Serial Report", title_style)
    note = Paragraph(
        "Priority groups are follow-up suggestions, not diagnoses.<br/>"
        "Review status reflects workflow only.",
        note_style,
    )
    table = Table(
        rows,
        colWidths=[0.5*inch, 1.3*inch, 1.15*inch, 1.4*inch, 0.75*inch,
                   0.6*inch, 0.8*inch, 0.95*inch, 2.05*inch, 0.8*inch],
        repeatRows=1,
        hAlign="CENTER",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5f3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#153b3a")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5e1df")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (4, 1), (7, -1), "CENTER"),
        ("ALIGN", (9, 1), (9, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbfa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    document.build([title, note, table])
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="medical_serial_report.pdf"'
    return response
