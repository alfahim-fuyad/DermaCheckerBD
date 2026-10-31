"""Base classes and exception hierarchy for the multi-provider chat system.

Every provider (Gemini, Groq, OpenRouter) implements the same ``chat()``
interface and raises the same family of exceptions, so the fallback
manager can route failures uniformly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Exception hierarchy
# --------------------------------------------------------------------------- #
class ProviderError(Exception):
    """Base class for every provider failure.

    Every concrete subclass sets ``retryable`` so the fallback manager
    can decide whether to switch providers or surface the error to the
    caller immediately (for example, an auth error is not retryable on
    the same provider).
    """

    #: Whether the fallback manager should immediately try the next
    #: provider when this error is raised.
    retryable: bool = True

    #: Stable machine code written into ``ChatUsageLog.error_type``.
    code: str = "provider_error"

    def __init__(self, message: str = "", *, status_code: Optional[int] = None) -> None:
        super().__init__(message or self.code)
        self.status_code = status_code


class RateLimitError(ProviderError):
    """HTTP 429 — too many requests in the current window."""

    retryable = True
    code = "rate_limit"


class QuotaExhaustedError(ProviderError):
    """Quota / billing exhausted on the provider side.

    For OpenAI-compatible providers this is usually a 429 with a
    ``quota`` / ``insufficient_quota`` marker in the body, or a 402
    Payment Required. For Gemini it is a 429 RESOURCE_EXHAUSTED with a
    billing-tag in the message.
    """

    retryable = True
    code = "quota_exhausted"


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""

    retryable = True
    code = "timeout"


class ProviderServerError(ProviderError):
    """5xx response from the provider (502/503/504/etc.)."""

    retryable = True
    code = "server_error"


class ProviderAuthError(ProviderError):
    """401/403 — invalid or revoked API key.

    Not retryable on the same provider (changing the key is the only
    fix), but the fallback manager may still try the next provider.
    """

    retryable = True
    code = "auth_error"


class ProviderUnavailableError(ProviderError):
    """The provider is not configured (missing API key or dependency)."""

    retryable = False
    code = "not_configured"


# --------------------------------------------------------------------------- #
# Data containers
# --------------------------------------------------------------------------- #
@dataclass
class ChatMessage:
    """A single chat message.

    Mirrors ``apps.common.services.gemini.GeminiMessage`` so the existing
    chatbot view code can be reused without rewriting the history builder.
    """

    role: str  # "user" | "assistant" | "system" | "model"
    content: str

    @classmethod
    def from_gemini(cls, msg) -> "ChatMessage":
        return cls(role=getattr(msg, "role", "user"), content=getattr(msg, "content", ""))


@dataclass
class ProviderResult:
    """A normalized, provider-agnostic success result."""

    text: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> Optional[int]:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


# --------------------------------------------------------------------------- #
# Provider interface
# --------------------------------------------------------------------------- #
class BaseAIProvider:
    """Common interface implemented by every chat provider adapter.

    Subclasses MUST set:
        - ``name``            – short slug used in logs and cooldown keys
        - ``setting_key``     – settings attribute checked by ``is_configured``

    Subclasses MUST implement:
        - ``is_configured()`` – True when this provider can serve requests
        - ``chat()``          – produce a ``ProviderResult`` or raise a
          ``ProviderError`` subclass.
    """

    #: Short slug used in logs, usage records, and cooldown keys.
    name: str = "base"

    #: Display label used in error messages and admin views.
    label: str = "Base Provider"

    #: Default model slug used when the corresponding ``*_MODEL`` env var
    #: is not set. Subclasses override this.
    default_model: str = ""

    #: Per-request timeout (seconds). Read from settings in subclasses.
    timeout: float = 30.0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @classmethod
    def is_configured(cls) -> bool:
        """Return True when this provider has the credentials to serve."""
        raise NotImplementedError

    @classmethod
    def chat(
        cls,
        *,
        system_prompt: str,
        history: List[ChatMessage],
        user_message: str,
        temperature: float = 0.4,
        max_output_tokens: int = 1200,
        language: str = "en",
    ) -> ProviderResult:
        """Generate a chat reply.

        Raises a ``ProviderError`` subclass on any failure.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Helpers shared by subclasses
    # ------------------------------------------------------------------ #
    @classmethod
    def _model(cls) -> str:
        """Return the configured model slug for this provider."""
        return cls.default_model

    @classmethod
    def _timeout(cls) -> float:
        return float(cls.timeout)

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        """Static metadata used by the admin and the usage view."""
        return {
            "name": cls.name,
            "label": cls.label,
            "model": cls._model(),
            "configured": cls.is_configured(),
            "timeout": cls._timeout(),
        }


def classify_http_error(
    status_code: int,
    body_text: str = "",
) -> ProviderError:
    """Map an HTTP failure to the right ``ProviderError`` subclass.

    The body text is inspected because OpenAI-compatible providers
    (Groq, OpenRouter) signal quota exhaustion with a 429 + a ``quota``
    marker in the JSON body, while a plain 429 is a windowed rate limit.
    """
    body_upper = (body_text or "").upper()
    if status_code in (401, 403):
        return ProviderAuthError(
            f"{status_code} from provider", status_code=status_code
        )
    if status_code == 402:
        return QuotaExhaustedError(
            "402 payment required from provider", status_code=status_code
        )
    if status_code == 429:
        quota_markers = (
            "INSUFFICIENT_QUOTA",
            "QUOTA",
            "BILLING",
            "RATE_LIMIT_EXCEEDED",
            "RESOURCE_EXHAUSTED",
        )
        if any(marker in body_upper for marker in quota_markers):
            return QuotaExhaustedError(
                "429 quota exhausted from provider", status_code=status_code
            )
        return RateLimitError(
            "429 rate limit from provider", status_code=status_code
        )
    if status_code in (500, 502, 503, 504):
        return ProviderServerError(
            f"{status_code} server error from provider", status_code=status_code
        )
    if 400 <= status_code < 500:
        # Other 4xx — bad request, malformed payload, content policy.
        # Not retryable on this provider, but the cascade may still try
        # the next provider because the next provider may accept it.
        err = ProviderError(
            f"{status_code} client error from provider", status_code=status_code
        )
        err.retryable = True
        err.code = "client_error"
        return err
    return ProviderError(
        f"{status_code} unexpected status from provider", status_code=status_code
    )
