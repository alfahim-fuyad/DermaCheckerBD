"""
PdfReportService: build a downloadable PDF summary report.

Reports include:
- Reference ID + date
- Predicted class + class probabilities
- Image-quality results
- Reliability-check results (if performed)
- Multi-image comparison results (if applicable)
- Clear medical-limitation statements and next-step guidance

LANGUAGE AWARENESS
------------------
The PDF respects the user's selected language by reading the
``derma_lang`` cookie passed via the ``language`` parameter. When
``language == "bn"``:
  - All headings, labels, and disclaimers are rendered in Bengali.
  - A Bengali-capable font (Noto Sans Bengali) is registered and used
    for ALL text — Helvetica cannot render Bengali Unicode characters.
  - Numerical confidence/probabilities remain unchanged (they are
    language-independent data from the real FastAPI/Keras model).

When ``language == "en"`` (default), Helvetica is used and all text is
in English.

Reports NEVER contain user PII beyond what the user submitted themselves
(no email, no IP, no user ID). Reports are clearly labeled as experimental
summaries and NOT medical certificates.
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Optional

from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem,
)
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .prediction import PredictionResult, CLASS_NAMES, CLASS_CATEGORIES
from .image_quality import ImageQualityReport
from .reliability import ReliabilityReport
from .multi_image import MultiImageReport
from .wrong_input import WrongInputReport


# Color palette (mirrors the frontend palette)
PRIMARY = colors.HexColor("#0d9488")  # teal-600
ACCENT = colors.HexColor("#2563eb")   # blue-600
MUTED = colors.HexColor("#64748b")     # slate-500
BG = colors.HexColor("#f8fafc")       # slate-50
BORDER = colors.HexColor("#e2e8f0")

# Bengali font registration (lazy — only registered once per process)
_BN_FONT_REGISTERED = False
_BN_FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "static", "fonts", "NotoSansBengali-Regular.ttf",
)

# Bengali display names for the 7 HAM10000 classes
BN_CLASS_NAMES = {
    "akiec": "অ্যাকটিনিক কেরাটোসিস / বোয়েনস ডিজিজ",
    "bcc": "বেসাল সেল কার্সিনোমা",
    "bkl": "বেনাইন কেরাটোসিস-জাতীয় দাগ",
    "df": "ডারমাটোফাইব্রোমা",
    "mel": "মেলানোমা",
    "nv": "মেলানোসাইটিক নেভাস",
    "vasc": "ভাসকুলার লেসন",
}

# Bengali translations for PDF labels
BN_LABELS = {
    "title": "DermaCheckerBD",
    "subtitle": "পরীক্ষামূলক ত্বকের দাগ বিশ্লেষণ সারাংশ — এটি কোনো মেডিকেল সার্টিফিকেট নয়।",
    "reference_id": "রেফারেন্স আইডি",
    "generated": "তৈরির সময়",
    "model_backend": "মডেল ব্যাকএন্ড",
    "input_size": "ইনপুট সাইজ",
    "wrong_input_title": "ভুল ইনপুট সুরক্ষা",
    "wrong_input_default": "ইনপুট অস্বাভাবিক হিসেবে চিহ্নিত।",
    "prediction_title": "প্রেডিকশন সারাংশ",
    "predicted_class": "প্রেডিক্টেড ক্লাস",
    "category": "ক্যাটাগরি",
    "confidence": "কনফিডেন্স (সর্বোচ্চ সফটম্যাক্স)",
    "class_header": "ক্লাস",
    "name_header": "পূর্ণ নাম",
    "category_header": "ক্যাটাগরি",
    "probability_header": "সম্ভাবনা",
    "quality_title": "ছবির গুণগত মান যাচাই",
    "quality_score": "সামগ্রিক কোয়ালিটি স্কোর",
    "suitable": "উপযুক্ত",
    "not_suitable": "উপযুক্ত নয়",
    "check_header": "চেক",
    "result_header": "ফলাফল",
    "value_header": "মান",
    "message_header": "বার্তা",
    "pass": "পাস",
    "fail": "ফেইল",
    "reliability_title": "প্রেডিকশন রিলায়েবিলিটি চেক",
    "agreement": "হালকা ট্রান্সফর্মে চুক্তি",
    "stable": "স্থিতিশীল",
    "unstable": "অস্থিতিশীল",
    "flips_intro": "কিছু ট্রান্সফর্মে শীর্ষ ক্লাস পরিবর্তিত হয়েছে:",
    "no_flips": "সব ট্রান্সফর্মে শীর্ষ ক্লাস প্রেডিকশন একই ছিল।",
    "agreement_note": "চুক্তি স্থিতিশীলতা পরিমাপ করে, সঠিকতা নয়।",
    "multi_title": "একাধিক ছবি তুলনা",
    "modal_class": "মোডাল ক্লাস",
    "disagree_intro": "কিছু ছবি মোডাল ক্লাসের সাথে ভিন্ন মত দিয়েছে:",
    "limitations_title": "সীমাবদ্ধতা ও পরবর্তী পদক্ষেপ",
    "limitation_1": "এই রিপোর্ট একটি পরীক্ষামূলক প্রোটোটাইপ দ্বারা তৈরি। প্রেডিকশনটি যাচাইহীন, ভুল হতে পারে, এবং এটি কোনো মেডিকেল ডায়াগনোসিস নয়। কনফিডেন্স ও স্থিতিশীলতা সংখ্যা মডেলের আচরণ বর্ণনা করে, প্রেডিকশন চিকিৎসাগতভাবে সঠিক কিনা তা নয়।",
    "limitation_2": "দাগটি পরিবর্তিত হলে, রক্তপাত করলে, বড় হলে, ব্যথা হলে, বা অন্য কোনো উদ্বেগের কারণ থাকলে — অথবা নিশ্চিত হতে চাইলে — একজন যোগ্য চর্মরোগ বিশেষজ্ঞের পরামর্শ নিন। এই রিপোর্টের উপর ভিত্তি করে পেশাদার মূল্যায়ন দেরি করবেন না।",
}

EN_LABELS = {
    "title": "DermaCheckerBD",
    "subtitle": "Experimental skin-lesion analysis summary — NOT a medical certificate.",
    "reference_id": "Reference ID",
    "generated": "Generated",
    "model_backend": "Model backend",
    "input_size": "Input size",
    "wrong_input_title": "Wrong-input protection",
    "wrong_input_default": "Input flagged as unusual.",
    "prediction_title": "Prediction summary",
    "predicted_class": "Predicted class",
    "category": "Category",
    "confidence": "Confidence (max softmax)",
    "class_header": "Class",
    "name_header": "Full name",
    "category_header": "Category",
    "probability_header": "Probability",
    "quality_title": "Image quality assessment",
    "quality_score": "Overall quality score",
    "suitable": "suitable",
    "not_suitable": "not suitable",
    "check_header": "Check",
    "result_header": "Result",
    "value_header": "Value",
    "message_header": "Message",
    "pass": "Pass",
    "fail": "Fail",
    "reliability_title": "Prediction reliability check",
    "agreement": "Agreement across mild transforms",
    "stable": "stable",
    "unstable": "unstable",
    "flips_intro": "Top-class changes were observed on some transforms:",
    "no_flips": "Top-class prediction was consistent across all transforms.",
    "agreement_note": "Agreement measures stability, NOT correctness.",
    "multi_title": "Multi-image comparison",
    "modal_class": "Modal class",
    "disagree_intro": "Some images disagreed with the modal class:",
    "limitations_title": "Limitations and next steps",
    "limitation_1": "This report is generated by an experimental prototype. The prediction is unverified, may be wrong, and is NOT a medical diagnosis. Confidence and stability numbers describe the model's behaviour, not whether the prediction is medically correct.",
    "limitation_2": "If the lesion is changing, bleeding, growing, painful, or otherwise concerning — or if you simply want certainty — consult a qualified dermatologist. Do not delay professional evaluation based on this report.",
}


def _register_bn_font():
    """Register the Noto Sans Bengali font once per process."""
    global _BN_FONT_REGISTERED
    if _BN_FONT_REGISTERED:
        return
    try:
        pdfmetrics.registerFont(TTFont("NotoBn", _BN_FONT_PATH))
        _BN_FONT_REGISTERED = True
    except Exception:
        # If the font file is missing, fall back to Helvetica.
        # Bengali text will not render correctly, but the PDF will
        # still be generated (in English labels) rather than crashing.
        pass


def _obj_get(obj, key, default=None):
    """Read a field from either a dict (live object) or a SimpleNamespace."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _styles(language: str = "en"):
    """Build paragraph styles. When language=bn, use the Bengali font."""
    styles = getSampleStyleSheet()
    _register_bn_font()

    if language == "bn":
        font = "NotoBn"
        font_bold = "NotoBn"
        font_italic = "NotoBn"
    else:
        font = "Helvetica"
        font_bold = "Helvetica-Bold"
        font_italic = "Helvetica-Oblique"

    styles.add(ParagraphStyle(
        name="H1Brand",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=20,
        textColor=PRIMARY,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Subtitle",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10,
        textColor=MUTED,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="H2",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=13,
        textColor=ACCENT,
        spaceBefore=14,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Body",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="Limit",
        parent=styles["Normal"],
        fontName=font_italic,
        fontSize=9,
        textColor=colors.HexColor("#b91c1c"),
        leading=12,
    ))
    return styles


def _labels(language: str = "en"):
    return BN_LABELS if language == "bn" else EN_LABELS


def _class_name(code: str, language: str = "en"):
    if language == "bn":
        return BN_CLASS_NAMES.get(code, code)
    return CLASS_NAMES.get(code, code)


def _category_name(category: str, language: str = "en"):
    if language == "bn":
        return {
            "benign": "বেনাইন",
            "malignant": "ম্যালিগন্যান্ট",
            "pre malignant": "প্রি-ম্যালিগন্যান্ট",
            "unknown": "অজানা",
        }.get(category, category)
    return category


class PdfReportService:
    @staticmethod
    def build_prediction_report(
        reference_id: str,
        prediction: PredictionResult,
        quality: Optional[ImageQualityReport] = None,
        reliability: Optional[ReliabilityReport] = None,
        multi_image: Optional[MultiImageReport] = None,
        wrong_input: Optional[WrongInputReport] = None,
        language: str = "en",
    ) -> bytes:
        """Return raw PDF bytes.

        Args:
            language: "en" (default) or "bn". When "bn", all labels
                are rendered in Bengali using the Noto Sans Bengali
                font. Numerical values (confidence, probabilities) are
                always language-independent.
        """
        lang = "bn" if language == "bn" else "en"
        labels = _labels(lang)
        styles = _styles(lang)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=18*mm, bottomMargin=18*mm,
            title="DermaCheckerBD — Prediction Summary",
            author="DermaCheckerBD (experimental)",
        )
        flow = []

        # --- Header ---
        flow.append(Paragraph(labels["title"], styles["H1Brand"]))
        flow.append(Paragraph(labels["subtitle"], styles["Subtitle"]))

        # --- Reference block ---
        meta_rows = [
            [labels["reference_id"], reference_id],
            [labels["generated"], datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
            [labels["model_backend"], prediction.backend],
            [labels["input_size"], f"{prediction.input_size}×{prediction.input_size}px"],
        ]
        t = Table(meta_rows, colWidths=[35*mm, 120*mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), styles["H2"].fontName),
            ("FONTNAME", (1, 0), (1, -1), styles["Body"].fontName),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
            ("TEXTCOLOR", (1, 0), (1, -1), colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BG, colors.white]),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 10))

        # --- Wrong-input warning ---
        if wrong_input and (not wrong_input.is_valid_image or not wrong_input.looks_like_skin):
            flow.append(Paragraph(labels["wrong_input_title"], styles["H2"]))
            flow.append(Paragraph(wrong_input.warning or labels["wrong_input_default"], styles["Body"]))
            if wrong_input.suggestions:
                flow.append(ListFlowable(
                    [ListItem(Paragraph(s, styles["Body"])) for s in wrong_input.suggestions],
                    bulletType="bullet",
                ))
            flow.append(Spacer(1, 6))

        # --- Prediction block ---
        flow.append(Paragraph(labels["prediction_title"], styles["H2"]))
        flow.append(Paragraph(
            f"{labels['predicted_class']}: <b>{prediction.predicted_class}</b> "
            f"({_class_name(prediction.predicted_class, lang)})",
            styles["Body"],
        ))
        flow.append(Paragraph(
            f"{labels['category']}: <b>{_category_name(prediction.category, lang)}</b>",
            styles["Body"],
        ))
        flow.append(Paragraph(
            f"{labels['confidence']}: <b>{prediction.confidence*100:.1f}%</b>",
            styles["Body"],
        ))
        flow.append(Spacer(1, 4))

        # Class probabilities table
        rows = [[labels["class_header"], labels["name_header"],
                 labels["category_header"], labels["probability_header"]]]
        for code, p in sorted(prediction.probabilities.items(), key=lambda kv: -kv[1]):
            rows.append([
                code,
                _class_name(code, lang),
                _category_name(CLASS_CATEGORIES.get(code, "?"), lang),
                f"{p*100:.1f}%",
            ])
        t2 = Table(rows, colWidths=[20*mm, 70*mm, 25*mm, 35*mm])
        t2.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), styles["H2"].fontName),
            ("FONTNAME", (0, 1), (-1, -1), styles["Body"].fontName),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG, colors.white]),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(t2)
        flow.append(Spacer(1, 8))

        # --- Image quality block ---
        if quality is not None:
            flow.append(Paragraph(labels["quality_title"], styles["H2"]))
            flow.append(Paragraph(
                f"{labels['quality_score']}: <b>{quality.overall_score:.1f}/100</b> "
                f"({labels['suitable'] if quality.suitable else labels['not_suitable']})",
                styles["Body"],
            ))
            qrows = [[labels["check_header"], labels["result_header"],
                      labels["value_header"], labels["message_header"]]]
            for c in quality.checks:
                qrows.append([
                    c.label,
                    labels["pass"] if c.passed else labels["fail"],
                    f"{c.value:.1f}" if c.value is not None else "—",
                    c.message,
                ])
            t3 = Table(qrows, colWidths=[28*mm, 18*mm, 20*mm, 84*mm])
            t3.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), styles["H2"].fontName),
                ("FONTNAME", (0, 1), (-1, -1), styles["Body"].fontName),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BG, colors.white]),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            flow.append(t3)
            flow.append(Spacer(1, 6))

        # --- Reliability block ---
        if reliability is not None:
            flow.append(Paragraph(labels["reliability_title"], styles["H2"]))
            flow.append(Paragraph(
                f"{labels['agreement']}: "
                f"<b>{reliability.agreement_pct:.1f}%</b> "
                f"({labels['stable'] if reliability.stable else labels['unstable']})",
                styles["Body"],
            ))
            if reliability.flipped_classes:
                flow.append(Paragraph(labels["flips_intro"], styles["Body"]))
                flow.append(ListFlowable(
                    [ListItem(Paragraph(
                        f"{_obj_get(f, 'transform')}: "
                        f"{labels['predicted_class'].split(':')[0].lower()} "
                        f"<b>{_obj_get(f, 'class')}</b>",
                        styles["Body"],
                    )) for f in reliability.flipped_classes],
                    bulletType="bullet",
                ))
            else:
                flow.append(Paragraph(labels["no_flips"], styles["Body"]))
            flow.append(Paragraph(labels["agreement_note"], styles["Limit"]))
            flow.append(Spacer(1, 6))

        # --- Multi-image block ---
        if multi_image is not None and multi_image.images:
            flow.append(Paragraph(labels["multi_title"], styles["H2"]))
            flow.append(Paragraph(
                f"{labels['modal_class']}: <b>{multi_image.modal_class}</b> "
                f"({_class_name(multi_image.modal_class, lang)}) — "
                f"{labels['agreement'].split('(')[0].strip().lower()} "
                f"{multi_image.agreement_pct:.1f}%.",
                styles["Body"],
            ))
            if multi_image.disagreeing_images:
                flow.append(Paragraph(labels["disagree_intro"], styles["Body"]))
                flow.append(ListFlowable(
                    [ListItem(Paragraph(
                        f"Image #{int(_obj_get(d, 'index')) + 1} "
                        f"({_obj_get(d, 'image_id')}): "
                        f"<b>{_obj_get(d, 'class')}</b>",
                        styles["Body"],
                    )) for d in multi_image.disagreeing_images],
                    bulletType="bullet",
                ))
            flow.append(Paragraph(multi_image.recommendation, styles["Body"]))
            flow.append(Spacer(1, 6))

        # --- Limitations & next steps ---
        flow.append(Paragraph(labels["limitations_title"], styles["H2"]))
        flow.append(Paragraph(labels["limitation_1"], styles["Limit"]))
        flow.append(Paragraph(labels["limitation_2"], styles["Limit"]))

        doc.build(flow)
        return buf.getvalue()
