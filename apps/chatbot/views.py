"""Gemini chatbot views.

SECURITY:
- POST /chatbot/message/ accepts JSON {message: "..."} and returns {reply: "..."}.
- CSRF token is required; the frontend sends X-CSRFToken on every request.
- Rate-limited per-IP to prevent abuse.
- No image bytes are accepted here.
- The Gemini API key is used server-side only; it is never exposed to the frontend.
"""
import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.common.services.gemini import GeminiService, GeminiMessage
from apps.common.services.prediction import PredictionService
from apps.predictor.models import PredictionRecord
from apps.tracker.models import LesionRecord

logger = logging.getLogger(__name__)

CHATBOT_ERRORS = {
    "bn": {
        "invalid": "অনুরোধের তথ্য সঠিক নয়।",
        "empty": "একটি প্রশ্ন লিখুন।",
        "long": "বার্তাটি অনেক বড় (সর্বোচ্চ ৬০০ অক্ষর)।",
        "unavailable": "দুঃখিত, এখন উত্তর তৈরি করা যাচ্ছে না। জরুরি সমস্যা হলে যোগ্য চিকিৎসকের পরামর্শ নিন।",
        "signin": "আপনার ব্যক্তিগত ড্যাশবোর্ডের তথ্য জানতে সাইন ইন করুন।",
        "staff_private": "আমি কোনো ব্যবহারকারীর নাম, ব্যক্তিগত রেকর্ড বা নির্দিষ্ট রোগীর ইতিহাস দেখাতে পারি না। আমি শুধু পরিচয়বিহীন সামগ্রিক সংখ্যা জানাতে পারি।",
    },
    "en": {
        "invalid": "Invalid request body.",
        "empty": "Please type a question.",
        "long": "Your message is too long (max 600 characters).",
        "unavailable": "I'm sorry, I couldn't generate a reply right now. For urgent concerns, please contact a qualified healthcare professional.",
        "signin": "Please sign in to ask about your personal dashboard.",
        "staff_private": "I can't show usernames, private records, or an individual patient's history. I can only provide anonymized, site-wide totals.",
    },
}


def _preferred_language(request, data=None):
    requested = data.get("language") if isinstance(data, dict) else None
    if requested in ("bn", "en"):
        return requested
    return "bn" if request.COOKIES.get("derma_lang") == "bn" else "en"


def _json_response(data, status=200):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _account_dashboard_context(user):
    """Build a server-trusted dashboard and recent-history summary for one user."""
    predictions = PredictionRecord.objects.filter(user=user)
    counts = {
        row["predicted_class"]: row["count"]
        for row in predictions.values("predicted_class").annotate(count=Count("id"))
    }
    class_metadata = PredictionService.class_metadata()
    return {
        "total_predictions": predictions.count(),
        "tracked_lesions": LesionRecord.objects.filter(user=user).count(),
        "predictions_last_7_days": predictions.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        "predictions_by_class": [
            {"code": item["code"], "name": item["name"], "count": counts.get(item["code"], 0)}
            for item in class_metadata
            if counts.get(item["code"], 0)
        ],
        "recent_predictions": [
            {
                "date": record.created_at.strftime("%Y-%m-%d"),
                "class": record.predicted_name,
                "code": record.predicted_class,
                "confidence_percent": round((record.confidence or 0.0) * 100, 1),
            }
            for record in predictions.order_by("-created_at")[:5]
        ],
        "recent_lesions": [
            {
                "date": record.created_at.strftime("%Y-%m-%d"),
                "label": record.label or "Unlabeled",
                "body_location": record.body_location or "Unspecified",
                "photo_count": record.photos.count(),
            }
            for record in LesionRecord.objects.filter(user=user).order_by("-created_at")[:5]
        ],
    }


def _staff_dashboard_context():
    """Return aggregate-only site metrics; never fetch names or individual records."""
    predictions = PredictionRecord.objects.all()
    status_counts = {
        row["review_status"]: row["count"]
        for row in predictions.values("review_status").annotate(count=Count("id"))
    }
    class_counts = {
        row["predicted_class"]: row["count"]
        for row in predictions.values("predicted_class").annotate(count=Count("id"))
    }
    return {
        "total_users": get_user_model().objects.count(),
        "total_predictions": predictions.count(),
        "tracked_lesions": LesionRecord.objects.count(),
        "predictions_last_7_days": predictions.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        "predictions_last_30_days": predictions.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        "predictions_by_class": [
            {"code": item["code"], "name": item["name"], "count": class_counts.get(item["code"], 0)}
            for item in PredictionService.class_metadata()
            if class_counts.get(item["code"], 0)
        ],
        "review_status_counts": {
            status: status_counts.get(status, 0)
            for status, _label in PredictionRecord.REVIEW_STATUS_CHOICES
        },
    }


def _build_history(raw_history):
    """Bound and normalize browser-supplied conversation history."""
    history = []
    if not isinstance(raw_history, list):
        return history
    for item in raw_history[-10:]:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        # The browser cannot add system/developer roles to a conversation.
        role = "model" if item.get("role") == "model" else "user"
        history.append(GeminiMessage(role=role, content=content[:600]))
    return history


def _is_personal_data_request(text):
    message = re.sub(r"\s+", " ", text.lower())
    phrases = (
        "my dashboard", "my prediction", "my history", "my tracker",
        "my lesion", "how many predictions do i", "how many lesions do i",
        "my recent", "my last", "my total", "how many do i have",
        "my profile", "my account", "my saved", "my record", "my email",
        "my phone", "my personal",
        "আমার ড্যাশবোর্ড", "আমার প্রেডিকশন", "আমার হিস্ট্রি",
        "আমার ট্র্যাকার", "আমার লেসন", "আমার তথ্য", "আমার প্রোফাইল",
        "আমার অ্যাকাউন্ট", "আমার ইমেইল", "আমার ফোন",
    )
    return any(phrase in message for phrase in phrases)


def _is_individual_record_request(text):
    message = re.sub(r"\s+", " ", text.lower())
    phrases = (
        "user history", "patient history", "user record", "patient record",
        "user dashboard", "patient dashboard", "user profile", "patient profile",
        "another user's", "another user’s", "other user's", "other user’s",
        "someone else's", "someone else’s", "history for",
        "history of a user", "history of the user", "history of this user",
        "history of a patient", "history of the patient",
        "records for", "records of a user", "records of the user",
        "records of a patient", "records of the patient",
        "dashboard for", "dashboard of",
        "profile for", "profile of", "prediction for", "predictions for",
        "private record", "private data", "individual history",
        "ব্যবহারকারীর ইতিহাস", "রোগীর ইতিহাস", "ব্যক্তিগত রেকর্ড",
    )
    return (
        any(phrase in message for phrase in phrases)
        or bool(re.search(
            r"\b[\w.-]+(?:'s|’s)\s+(?:history|dashboard|records?|predictions?)\b",
            message,
        ))
        or bool(re.search(
            r"\b(?:history|dashboard|records?|predictions?)\s+(?:for|of)\s+[A-Z][\w.-]*\b",
            text,
        ))
    )


def _is_staff_private_data_request(text):
    message = re.sub(r"\s+", " ", text.lower())
    phrases = (
        "username", "user name", "usernames", "names of users", "user names",
        "list users", "list all users", "show users", "who are the users",
        "patient name", "patient names", "email", "phone number", "phone numbers",
        "specific user", "individual user", "specific patient", "individual patient",
        "patient id", "user id", "record id", "reference id", "lesion id",
        "history for", "records for",
        "dashboard for", "dashboard of", "profile of", "personal data",
        "ব্যবহারকারীর নাম", "রোগীর নাম", "ইমেইল", "ফোন নম্বর",
        "নির্দিষ্ট ব্যবহারকারী", "নির্দিষ্ট রোগী", "ব্যক্তিগত তথ্য",
    )
    return any(phrase in message for phrase in phrases) or _is_individual_record_request(text)


def _is_staff_aggregate_request(text):
    message = text.lower()
    phrases = (
        "count", "how many", "total", "overall", "site-wide", "dashboard",
        "users", "accounts", "predictions", "history", "records",
        "প্রতিবেদন", "ড্যাশবোর্ড", "ব্যবহারকারী", "ইউজার",
        "প্রেডিকশন", "হিস্ট্রি", "কতটি", "মোট",
    )
    return any(phrase in message for phrase in phrases)


def _has_staff_chat_access(user):
    """Doctors with the queue permission and Django staff users may see aggregates."""
    return bool(
        user.is_authenticated
        and (
            user.is_staff
            or user.has_perm("predictor.view_medical_priority_queue")
        )
    )


@require_POST
@ratelimit(key="ip", rate=settings.CHATBOT_RATE_LIMIT, block=True)
def message_view(request):
    """Accept a chatbot message and return a safe reply.

    CSRF is enforced by CsrfViewMiddleware (the frontend sends X-CSRFToken
    on every POST). Removing the previous @csrf_exempt closes a cross-origin
    abuse vector that could have driven paid Gemini API calls.
    """
    # Reject clearly malformed JSON bodies early to keep the rate-limit
    # counter clean for legitimate users.
    data = None
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        language = _preferred_language(request)
        return _json_response({"reply": CHATBOT_ERRORS[language]["invalid"]}, status=400)

    if not isinstance(data, dict):
        language = _preferred_language(request)
        return _json_response({"reply": CHATBOT_ERRORS[language]["invalid"]}, status=400)
    language = _preferred_language(request, data)
    raw_text = data.get("message")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not text:
        return _json_response({"reply": CHATBOT_ERRORS[language]["empty"]}, status=400)
    if len(text) > 600:
        return _json_response({"reply": CHATBOT_ERRORS[language]["long"]}, status=400)

    # Conversation history is untrusted browser input. Account data and staff
    # metrics are always reconstructed from the authenticated request below.
    history = _build_history(data.get("history"))

    authenticated = request.user.is_authenticated
    staff_scope = _has_staff_chat_access(request.user)
    if staff_scope and _is_staff_private_data_request(text):
        return _json_response({
            "reply": CHATBOT_ERRORS[language]["staff_private"],
            "offline": not GeminiService.is_configured(),
            "scope": "staff",
            "authed": True,
        })
    if not authenticated and (
        _is_personal_data_request(text) or _is_individual_record_request(text)
    ):
        return _json_response({
            "reply": CHATBOT_ERRORS[language]["signin"],
            "offline": not GeminiService.is_configured(),
            "scope": "public",
            "authed": False,
        })
    if staff_scope:
        context = _staff_dashboard_context() if _is_staff_aggregate_request(text) else None
    elif authenticated and _is_personal_data_request(text):
        context = _account_dashboard_context(request.user)
    else:
        context = None

    try:
        chat_kwargs = {
            "history": history,
            "user_message": text,
            "context": context,
            "language": language,
            "is_authenticated": authenticated,
        }
        # Only send the added staff flag for staff requests. This keeps the
        # public/user call compatible with an already-running worker that may
        # still have the previous chat-service signature loaded.
        if staff_scope:
            chat_kwargs["is_staff"] = True
        reply = GeminiService.chat(
            **chat_kwargs,
        )
    except TypeError as e:
        if staff_scope and "unexpected keyword argument 'is_staff'" in str(e):
            # Older worker compatibility: its context still contains only
            # aggregate counts, never usernames or individual records.
            chat_kwargs.pop("is_staff", None)
            reply = GeminiService.chat(**chat_kwargs)
        else:
            logger.warning("GeminiService error: %s", e)
            reply = CHATBOT_ERRORS[language]["unavailable"]
    except Exception as e:
        logger.warning("GeminiService error: %s", e)
        reply = CHATBOT_ERRORS[language]["unavailable"]

    return _json_response({
        "reply": reply,
        "offline": not GeminiService.is_configured(),
        "scope": "staff" if staff_scope else ("private" if authenticated else "public"),
        "authed": authenticated,
    })
