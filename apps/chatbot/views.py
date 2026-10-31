"""Multi-provider chatbot views.

SECURITY + ACCESS CONTRACT:
- POST /chatbot/message/  — Open to ALL users (anonymous and authenticated).
    * Anonymous users ONLY ever receive the 7 predefined FAQs (see
      ``apps.chatbot.faqs``). No AI provider is ever called for them.
    * Authenticated users get the full AI-powered chatbot via the
      multi-provider fallback cascade (Gemini -> Groq -> OpenRouter).
    * The 7 FAQ button clicks (``faq_id`` payload field) are available
      to ALL users — anonymous and authenticated — so the 7 Q&A support
      works for everyone.
- GET  /chatbot/history/   — Login required. Returns the persisted
                              server-side conversation for the user.
- POST /chatbot/clear/     — Login required. Clears the persisted
                              conversation.
- GET  /chatbot/providers/ — Login required. Returns provider health and
                              cooldown state (no API keys exposed).
- GET  /chatbot/usage/     — Staff only. Returns recent ChatUsageLog rows.

PAYLOAD CONTRACT (unchanged from the previous single-provider version
plus a new ``provider`` field for authenticated AI replies):
- ``reply``    – the reply text (HTML allowlisted client-side).
- ``offline``  – True when no provider is configured (informational).
- ``scope``    – "public" | "private" | "staff".
- ``authed``   – bool, mirrors request.user.is_authenticated.
- ``faq_id``   – present only for FAQ replies, identifies which FAQ
                 was answered. Empty string when the message was a
                 free-text query that did not match any FAQ.
- ``faqs``     – present only on the welcome / guidance response, the 7 FAQs
                 so the frontend can render the quick-reply buttons without
                 a second round trip.
- ``provider`` – present for authenticated AI replies: which provider
                 answered ("gemini" / "groq" / "openrouter" / "canned").
                 Empty string for FAQ replies.
"""
import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from apps.chatbot.faqs import (
    FAQS, find_faq_id_by_text, get_faq_answer, list_faqs,
)
from apps.chatbot.models import ChatConversation, ChatMessage, ChatUsageLog
from apps.common.services.ai_providers import FallbackChatService
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
        "anon_guidance": (
            "আমি অতিথি ব্যবহারকারীদের জন্য পূর্বনির্ধারিত ৭টি প্রশ্নের উত্তর দিতে পারি। "
            "নিচের বোতামগুলোর যেকোনো একটি ক্লিক করুন, অথবা বিস্তারিত ব্যক্তিগত উত্তরের জন্য "
            "সাইন ইন করুন।"
        ),
    },
    "en": {
        "invalid": "Invalid request body.",
        "empty": "Please type a question.",
        "long": "Your message is too long (max 600 characters).",
        "unavailable": "I'm sorry, I couldn't generate a reply right now. For urgent concerns, please contact a qualified healthcare professional.",
        "signin": "Please sign in to ask about your personal dashboard.",
        "staff_private": "I can't show usernames, private records, or an individual patient's history. I can only provide anonymized, site-wide totals.",
        "anon_guidance": (
            "I can answer 7 predefined questions for guests. Click one of the "
            "buttons below, or sign in for detailed personalized answers."
        ),
    },
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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


def _faq_response(faq_id, language, *, authed_scope="public", authed=False):
    """Build the JSON response for a successful FAQ answer (any user)."""
    answer = get_faq_answer(faq_id, language=language)
    return _json_response({
        "reply": answer or CHATBOT_ERRORS[language]["unavailable"],
        "offline": True,  # FAQ answers are always canned/offline by design
        "scope": authed_scope,
        "authed": authed,
        "faq_id": faq_id,
    })


def _anon_guidance_response(language):
    """Anonymous free-text that did not match a FAQ: explain the limit.

    The response also carries the FAQ list so the frontend can render the
    quick-reply buttons without a second round trip.
    """
    return _json_response({
        "reply": CHATBOT_ERRORS[language]["anon_guidance"],
        "offline": True,
        "scope": "public",
        "authed": False,
        "faq_id": "",
        "faqs": list_faqs(language),
    })


# --------------------------------------------------------------------------- #
# Main chat endpoint
# --------------------------------------------------------------------------- #
@require_POST
@ratelimit(key="ip", rate=settings.CHATBOT_RATE_LIMIT, block=True)
def message_view(request):
    """Accept a chatbot message and return a safe reply.

    Access contract:
        * Anonymous users: 7 FAQs only — never an AI provider call.
        * Authenticated users: full multi-provider AI cascade for free-text
          questions, OR a FAQ answer if they clicked a FAQ button.

    CSRF is enforced by CsrfViewMiddleware (the frontend sends X-CSRFToken
    on every POST).

    BACKWARD COMPATIBILITY NOTE:
    This view calls ``GeminiService.chat`` (the legacy entry point). In
    production, ``GeminiService.chat`` delegates internally to
    ``FallbackChatService.chat`` which performs the Gemini -> Groq ->
    OpenRouter cascade. Existing tests that patch
    ``apps.chatbot.views.GeminiService.chat`` continue to work because
    the patch replaces the wrapper and bypasses the cascade entirely.
    The winning provider is communicated back to this view via
    ``GeminiService.get_last_fallback_result()`` (thread-local).
    """
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

    authenticated = request.user.is_authenticated

    # ---------- FAQ button click path: available to ALL users ----------
    # When any user (anonymous or authenticated) clicks a FAQ quick-reply
    # button, the frontend sends ``faq_id`` directly. We return the canned
    # FAQ answer without calling any AI provider.
    raw_faq_id = data.get("faq_id")
    if isinstance(raw_faq_id, str) and raw_faq_id:
        faq_id = raw_faq_id.strip()[:32]
        if faq_id in {item["id"] for item in FAQS}:
            if authenticated:
                scope = "staff" if _has_staff_chat_access(request.user) else "private"
                return _faq_response(faq_id, language, authed_scope=scope, authed=True)
            return _faq_response(faq_id, language)
        # Unknown faq_id — surface the FAQ list so the UI can re-render.
        if authenticated:
            return _json_response({
                "reply": CHATBOT_ERRORS[language]["anon_guidance"],
                "offline": not FallbackChatService.is_any_configured(),
                "scope": "staff" if _has_staff_chat_access(request.user) else "private",
                "authed": True,
                "faq_id": "",
                "faqs": list_faqs(language),
            })
        return _anon_guidance_response(language)

    # Free-text message path.
    raw_text = data.get("message")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if not text:
        return _json_response({"reply": CHATBOT_ERRORS[language]["empty"]}, status=400)
    if len(text) > 600:
        return _json_response({"reply": CHATBOT_ERRORS[language]["long"]}, status=400)

    # ---------- Anonymous free-text path: FAQ-only, NO AI call ----------
    if not authenticated:
        # Try to match the typed question to one of the 7 FAQs.
        matched_faq_id = find_faq_id_by_text(text, language=language)
        if matched_faq_id:
            return _faq_response(matched_faq_id, language)

        # Personal-data questions are gently redirected to sign in.
        if _is_personal_data_request(text) or _is_individual_record_request(text):
            return _json_response({
                "reply": CHATBOT_ERRORS[language]["signin"],
                "offline": True,
                "scope": "public",
                "authed": False,
                "faq_id": "",
            })

        # Anything else: explain the FAQ-only limit. Still NO AI call.
        return _anon_guidance_response(language)

    # ---------- Authenticated free-text path: multi-provider AI cascade ----------
    history = _build_history(data.get("history"))
    staff_scope = _has_staff_chat_access(request.user)

    if staff_scope and _is_staff_private_data_request(text):
        return _json_response({
            "reply": CHATBOT_ERRORS[language]["staff_private"],
            "offline": not FallbackChatService.is_any_configured(),
            "scope": "staff",
            "authed": True,
            "provider": "",
        })
    if staff_scope:
        context = _staff_dashboard_context() if _is_staff_aggregate_request(text) else None
    elif _is_personal_data_request(text):
        context = _account_dashboard_context(request.user)
    else:
        context = None

    # Clear any stale thread-local result from a previous request so we
    # never report the wrong provider.
    GeminiService.clear_last_fallback_result()

    try:
        chat_kwargs = {
            "history": history,
            "user_message": text,
            "context": context,
            "language": language,
            "is_authenticated": True,
        }
        # Only send the added staff flag for staff requests. This keeps the
        # call compatible with workers that may still have the previous
        # chat-service signature loaded.
        if staff_scope:
            chat_kwargs["is_staff"] = True
        # GeminiService.chat delegates to FallbackChatService.chat in
        # production (the cascade). The user kwarg is optional and only
        # used for usage logging + conversation persistence.
        chat_kwargs["user"] = request.user
        reply = GeminiService.chat(**chat_kwargs)
    except TypeError as e:
        if staff_scope and "unexpected keyword argument 'is_staff'" in str(e):
            chat_kwargs.pop("is_staff", None)
            reply = GeminiService.chat(**chat_kwargs)
        else:
            logger.warning("GeminiService error: %s", e)
            reply = CHATBOT_ERRORS[language]["unavailable"]
    except Exception as e:
        logger.warning("GeminiService error: %s", e)
        reply = CHATBOT_ERRORS[language]["unavailable"]

    # Read back which provider actually answered (thread-local).
    last_result = GeminiService.get_last_fallback_result()
    provider = last_result.provider if last_result is not None else ""

    return _json_response({
        "reply": reply,
        "offline": not FallbackChatService.is_any_configured(),
        "scope": "staff" if staff_scope else "private",
        "authed": True,
        "provider": provider,
    })


# --------------------------------------------------------------------------- #
# Server-side conversation history (login required)
# --------------------------------------------------------------------------- #
@require_GET
@login_required
def history_view(request):
    """Return the authenticated user's persisted conversation turns."""
    try:
        conversation = ChatConversation.objects.get(user=request.user)
    except ChatConversation.DoesNotExist:
        return _json_response({"messages": [], "truncated": False})
    keep = int(getattr(settings, "CHATBOT_HISTORY_KEEP", 40))
    qs = conversation.messages.order_by("created_at", "id")
    messages = list(qs.values("role", "content", "provider", "model", "created_at"))
    truncated = len(messages) > keep
    for row in messages:
        row["created_at"] = row["created_at"].isoformat()
    return _json_response({
        "messages": messages[-keep:],
        "truncated": truncated,
    })


@require_POST
@login_required
def clear_view(request):
    """Clear the authenticated user's persisted conversation."""
    try:
        conversation = ChatConversation.objects.get(user=request.user)
        conversation.messages.all().delete()
        conversation.save(update_fields=["updated_at"])
    except ChatConversation.DoesNotExist:
        pass
    return _json_response({"cleared": True})


# --------------------------------------------------------------------------- #
# Provider health + usage views
# --------------------------------------------------------------------------- #
@require_GET
@login_required
def providers_view(request):
    """Return provider configuration and cooldown state.

    Available to any authenticated user; only the ``order`` and
    ``configured`` flags are exposed — no API keys.
    """
    providers = FallbackChatService.describe_providers()
    return _json_response({
        "order": [p["name"] for p in providers],
        "providers": providers,
        "any_configured": FallbackChatService.is_any_configured(),
    })


@require_GET
@login_required
def usage_view(request):
    """Return recent ChatUsageLog rows.

    Restricted to staff users (Django staff OR users with the medical
    queue permission). Non-staff get a 403.
    """
    if not _has_staff_chat_access(request.user):
        return _json_response(
            {"detail": "Staff access required."}, status=403,
        )
    try:
        limit = max(1, min(200, int(request.GET.get("limit", "50"))))
    except ValueError:
        limit = 50
    qs = ChatUsageLog.objects.select_related("user").order_by("-created_at")[:limit]
    rows = list(qs.values(
        "id", "provider", "model", "success", "error_code",
        "error_message", "latency_ms", "prompt_tokens",
        "completion_tokens", "created_at",
    ))
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    # Per-provider success-rate summary over the last 100 attempts.
    summary = {}
    for provider in getattr(settings, "CHATBOT_PROVIDER_ORDER", []):
        recent = ChatUsageLog.objects.filter(provider=provider).order_by("-created_at")[:100]
        total = recent.count()
        ok = recent.filter(success=True).count()
        summary[provider] = {
            "recent_attempts": total,
            "recent_successes": ok,
            "success_rate": round(ok / total, 3) if total else None,
        }
    return _json_response({"recent": rows, "summary": summary})
