"""Context processor exposing feature flags + chatbot config to all templates."""
from django.conf import settings
from apps.common.services.gemini import GeminiService


def feature_flags(request):
    user = request.user
    chatbot_staff_scope = bool(
        user.is_authenticated
        and (
            user.is_staff
            or user.has_perm("predictor.view_medical_priority_queue")
        )
    )
    if not user.is_authenticated:
        chatbot_role = "public"
        chatbot_scope = "public"
    elif chatbot_staff_scope:
        chatbot_role = "staff"
        chatbot_scope = f"staff-{user.pk}"
    else:
        chatbot_role = "user"
        chatbot_scope = f"user-{user.pk}"

    return {
        "similar_cases_enabled": settings.SIMILAR_CASES_ENABLED,
        "chatbot_configured": GeminiService.is_configured(),
        "chatbot_role": chatbot_role,
        "chatbot_scope": chatbot_scope,
        "ml_backend": settings.ML_MODEL_BACKEND,
        "show_research_banner": settings.DEBUG,
        "ui_language": (
            request.LANGUAGE_CODE[:2]
            if getattr(request, "LANGUAGE_CODE", "en").startswith(("en", "bn"))
            else "en"
        ),
    }
