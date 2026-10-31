"""Fallback orchestration: try providers in configured order, with cooldowns.

The ``FallbackChatService`` is the single entry point the chatbot view
calls. It:

    1. Builds the provider-agnostic system prompt (delegating to the
       existing Gemini prompt builders so the safety contract and
       account/staff scoping remain unchanged).
    2. Walks ``settings.CHATBOT_PROVIDER_ORDER`` (default
       ``["gemini", "groq", "openrouter"]``).
    3. Skips providers that are on cooldown or not configured.
    4. Calls the first available provider. On a retryable error it
       records a cooldown, logs the failure via ``ChatUsageLog``, and
       tries the next provider.
    5. On exhaustion of every provider, returns the existing canned
       failure response so the UI never breaks.

The service also persists conversation turns to ``ChatConversation`` /
``ChatMessage`` for authenticated users, and writes a ``ChatUsageLog``
row for every provider attempt (success or failure).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from django.conf import settings

from .base import (
    BaseAIProvider,
    ChatMessage,
    ProviderError,
    ProviderUnavailableError,
    ProviderResult,
)
from .cooldown import CooldownTracker, CooldownEntry
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .openrouter_provider import OpenRouterProvider

logger = logging.getLogger(__name__)


PROVIDER_REGISTRY: Dict[str, Type[BaseAIProvider]] = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
}


@dataclass
class FallbackResult:
    """Outcome of a fallback cascade run.

    ``text`` is always set — either the winning provider's reply or a
    localized canned message when every provider failed.
    """

    text: str
    provider: str  # "gemini" | "groq" | "openrouter" | "canned"
    model: str = ""
    latency_ms: int = 0
    success: bool = True
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    cooldowns_set: List[CooldownEntry] = field(default_factory=list)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    @property
    def offline(self) -> bool:
        """True when no provider was able to answer (canned reply returned)."""
        return self.provider == "canned"


class FallbackChatService:
    """Cascade through providers, applying cooldowns and writing usage logs."""

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    @classmethod
    def chat(
        cls,
        *,
        history: List[ChatMessage],
        user_message: str,
        context: Optional[dict] = None,
        language: str = "en",
        is_authenticated: bool = False,
        is_staff: bool = False,
        user=None,
    ) -> FallbackResult:
        """Run the cascade and return a ``FallbackResult``.

        ``user`` is the Django user object (or ``None`` for anonymous).
        When provided, every attempt is logged to ``ChatUsageLog`` and
        the winning user/model turns are appended to the user's
        ``ChatConversation``.
        """
        system_prompt = cls._build_system_prompt(
            context=context,
            language=language,
            is_authenticated=is_authenticated,
            is_staff=is_staff,
        )

        order = list(getattr(settings, "CHATBOT_PROVIDER_ORDER", ["gemini", "groq", "openrouter"]))
        if not order:
            order = ["gemini", "groq", "openrouter"]

        attempts: List[Dict[str, Any]] = []
        cooldowns_set: List[CooldownEntry] = []

        for slug in order:
            provider_cls = PROVIDER_REGISTRY.get(slug)
            if provider_cls is None:
                logger.warning("Unknown provider slug in CHATBOT_PROVIDER_ORDER: %s", slug)
                continue

            if not provider_cls.is_configured():
                attempts.append(cls._attempt_record(slug, configured=False))
                continue

            cooldown = CooldownTracker.get(slug)
            if cooldown is not None:
                attempts.append(cls._attempt_record(
                    slug,
                    configured=True,
                    cooldown=cooldown,
                ))
                continue

            try:
                result: ProviderResult = provider_cls.chat(
                    system_prompt=system_prompt,
                    history=history,
                    user_message=user_message,
                    temperature=0.4,
                    max_output_tokens=1200,
                    language=language,
                )
            except ProviderError as e:
                # Cooldown only on retryable errors; auth errors still
                # trigger a cascade but the provider stays available
                # for the next request (a 401 is a config problem the
                # operator should fix, not a transient overload).
                if e.retryable and not isinstance(e, ProviderUnavailableError):
                    cd = CooldownTracker.set(slug, e.code)
                    cooldowns_set.append(cd)
                attempt = cls._attempt_record(
                    slug,
                    configured=True,
                    error_code=e.code,
                    error_message=str(e),
                    status_code=e.status_code,
                    retryable=e.retryable,
                )
                attempts.append(attempt)
                cls._log_usage(
                    user=user,
                    provider=slug,
                    model=provider_cls._model(),
                    success=False,
                    error_code=e.code,
                    error_message=str(e),
                    latency_ms=0,
                )
                logger.info(
                    "Provider %s failed (%s); cascading to next provider.",
                    slug,
                    e.code,
                )
                continue
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("Unexpected error from provider %s: %s", slug, e)
                cd = CooldownTracker.set(slug, "unexpected_error")
                cooldowns_set.append(cd)
                attempts.append(cls._attempt_record(
                    slug,
                    configured=True,
                    error_code="unexpected_error",
                    error_message=str(e),
                    retryable=True,
                ))
                cls._log_usage(
                    user=user,
                    provider=slug,
                    model=provider_cls._model(),
                    success=False,
                    error_code="unexpected_error",
                    error_message=str(e),
                    latency_ms=0,
                )
                continue

            # Success.
            attempt = cls._attempt_record(
                slug,
                configured=True,
                success=True,
                model=result.model,
                latency_ms=result.latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
            attempts.append(attempt)
            cls._log_usage(
                user=user,
                provider=slug,
                model=result.model,
                success=True,
                error_code="",
                error_message="",
                latency_ms=result.latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )
            cls._persist_turn(
                user=user,
                history=history,
                user_message=user_message,
                reply=result.text,
                provider=slug,
                model=result.model,
                is_authenticated=is_authenticated,
            )
            return FallbackResult(
                text=result.text,
                provider=slug,
                model=result.model,
                latency_ms=result.latency_ms,
                success=True,
                attempts=attempts,
                cooldowns_set=cooldowns_set,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
            )

        # Every provider failed or was unavailable — return the canned reply.
        canned = cls._canned_reply(
            user_message=user_message,
            context=context,
            language=language,
            is_authenticated=is_authenticated,
            is_staff=is_staff,
        )
        return FallbackResult(
            text=canned,
            provider="canned",
            success=False,
            attempts=attempts,
            cooldowns_set=cooldowns_set,
        )

    # ------------------------------------------------------------------ #
    # Status / introspection (used by the staff usage view)
    # ------------------------------------------------------------------ #
    @classmethod
    def describe_providers(cls) -> List[Dict[str, Any]]:
        out = []
        for slug in getattr(settings, "CHATBOT_PROVIDER_ORDER", ["gemini", "groq", "openrouter"]):
            provider_cls = PROVIDER_REGISTRY.get(slug)
            if not provider_cls:
                continue
            info = provider_cls.describe()
            cd = CooldownTracker.get(slug)
            info["cooldown"] = {
                "active": cd is not None,
                "remaining_seconds": round(cd.remaining, 1) if cd else 0.0,
                "reason": cd.reason if cd else "",
            } if cd else {"active": False, "remaining_seconds": 0.0, "reason": ""}
            info["order"] = len(out) + 1
            out.append(info)
        return out

    @classmethod
    def is_any_configured(cls) -> bool:
        """True when at least one provider can serve authenticated users."""
        return any(
            PROVIDER_REGISTRY[slug].is_configured()
            for slug in getattr(settings, "CHATBOT_PROVIDER_ORDER", ["gemini", "groq", "openrouter"])
            if slug in PROVIDER_REGISTRY
        )

    # ------------------------------------------------------------------ #
    # System-prompt construction (delegates to existing Gemini prompts)
    # ------------------------------------------------------------------ #
    @classmethod
    def _build_system_prompt(
        cls,
        *,
        context: Optional[dict],
        language: str,
        is_authenticated: bool,
        is_staff: bool,
    ) -> str:
        # Imported lazily so unit tests that override settings still work.
        from apps.common.services.gemini import (
            GEMINI_SYSTEM_PROMPT,
            GEMINI_STAFF_SYSTEM_PROMPT,
            GEMINI_PUBLIC_SYSTEM_PROMPT,
        )

        if is_staff:
            system = GEMINI_STAFF_SYSTEM_PROMPT
        elif is_authenticated:
            system = GEMINI_SYSTEM_PROMPT + """

Signed-in user access scope:
- The context below contains only this signed-in user's own dashboard summary
  and recent history. You may answer questions about those records.
- Never claim access to another person's information, profile, or history.
"""
        else:
            system = GEMINI_PUBLIC_SYSTEM_PROMPT
        if language == "bn":
            system += (
                "\n\nThe user selected Bengali for the interface. Always answer in "
                "clear, natural Bengali, even if the user's message is in another "
                "language. Keep medical class codes such as mel, nv, and bcc unchanged."
            )
        if context:
            if is_staff:
                context_header = (
                    "\n\nAnonymized, system-wide aggregate statistics generated by "
                    "the server. No individual-level data is available. Use these "
                    "totals only for aggregate questions; do not infer identities "
                    "or individual outcomes:\n"
                )
            else:
                context_header = (
                    "\n\nPrivate dashboard context generated by the server for this "
                    "authenticated user only. It contains only their own aggregate "
                    "counts and recent history, not images, profile details, or "
                    "another user's data. Use it only for this user's questions; "
                    "do not infer a diagnosis or clinical meaning:\n"
                )
            system += context_header + json.dumps(
                context, ensure_ascii=False, separators=(",", ":")
            )
        return system

    # ------------------------------------------------------------------ #
    # Canned reply when every provider is unavailable
    # ------------------------------------------------------------------ #
    @classmethod
    def _canned_reply(
        cls,
        *,
        user_message: str,
        context: Optional[dict],
        language: str,
        is_authenticated: bool,
        is_staff: bool,
    ) -> str:
        # Defer the import to avoid a circular dependency at module load.
        from apps.common.services.gemini import GeminiService

        if is_staff and context and GeminiService._asks_about_staff_dashboard(user_message):
            return GeminiService._staff_canned_reply(
                context, language=language, service_unavailable=True
            )
        if is_authenticated and context and GeminiService._asks_about_dashboard(user_message):
            return GeminiService._dashboard_canned_reply(
                context, language=language, service_unavailable=True
            )
        from apps.common.services.gemini import GEMINI_UNAVAILABLE_RESPONSES
        return GEMINI_UNAVAILABLE_RESPONSES[language]

    # ------------------------------------------------------------------ #
    # Persistence + logging
    # ------------------------------------------------------------------ #
    @staticmethod
    def _attempt_record(
        slug: str,
        *,
        configured: bool,
        success: bool = False,
        model: str = "",
        latency_ms: int = 0,
        error_code: str = "",
        error_message: str = "",
        status_code: Optional[int] = None,
        retryable: bool = False,
        cooldown: Optional[CooldownEntry] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "provider": slug,
            "configured": configured,
            "success": success,
        }
        if model:
            rec["model"] = model
        if latency_ms:
            rec["latency_ms"] = latency_ms
        if error_code:
            rec["error_code"] = error_code
            rec["error_message"] = error_message
            rec["retryable"] = retryable
        if status_code is not None:
            rec["status_code"] = status_code
        if cooldown is not None:
            rec["cooldown"] = {
                "reason": cooldown.reason,
                "remaining_seconds": round(cooldown.remaining, 1),
            }
        if prompt_tokens is not None:
            rec["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            rec["completion_tokens"] = completion_tokens
        return rec

    @staticmethod
    def _log_usage(
        *,
        user,
        provider: str,
        model: str,
        success: bool,
        error_code: str,
        error_message: str,
        latency_ms: int,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
    ) -> None:
        """Best-effort write to ``ChatUsageLog``.

        Wrapped in try/except so a logging failure can never break the
        chat reply path.
        """
        try:
            from apps.chatbot.models import ChatUsageLog
            ChatUsageLog.objects.create(
                user=user if (user is not None and getattr(user, "is_authenticated", False)) else None,
                provider=provider,
                model=model,
                success=success,
                error_code=error_code or "",
                error_message=(error_message or "")[:500],
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception:  # pragma: no cover - logging never breaks chat
            logger.warning("Could not write ChatUsageLog row", exc_info=True)

    @staticmethod
    def _persist_turn(
        *,
        user,
        history: List[ChatMessage],
        user_message: str,
        reply: str,
        provider: str,
        model: str,
        is_authenticated: bool,
    ) -> None:
        """Append the user turn + assistant turn to the user's conversation."""
        if not is_authenticated or user is None:
            return
        try:
            from apps.chatbot.models import ChatConversation, ChatMessage as DBChatMessage
            conversation, _ = ChatConversation.objects.get_or_create(user=user)
            DBChatMessage.objects.bulk_create([
                DBChatMessage(
                    conversation=conversation,
                    role="user",
                    content=user_message[:600],
                    provider="",
                    model="",
                ),
                DBChatMessage(
                    conversation=conversation,
                    role="model",
                    content=reply[:2000],
                    provider=provider,
                    model=model,
                ),
            ])
            # Bound conversation size so it never grows unbounded.
            DBChatMessage.trim_to_last(conversation, keep=40)
            conversation.save(update_fields=["updated_at"])
        except Exception:  # pragma: no cover - persistence never breaks chat
            logger.warning("Could not persist chat turn", exc_info=True)
