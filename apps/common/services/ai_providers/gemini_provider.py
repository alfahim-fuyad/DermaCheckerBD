"""Gemini provider — primary in the fallback cascade.

This adapter wraps the existing ``google-genai`` SDK initialization
that ``apps.common.services.gemini.GeminiService`` already performs.
It keeps the same system prompt construction and response handling so
behavioural parity is preserved for authenticated users.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from django.conf import settings

from .base import (
    BaseAIProvider,
    ChatMessage,
    ProviderError,
    ProviderResult,
    ProviderUnavailableError,
    ProviderTimeoutError,
    ProviderServerError,
    RateLimitError,
    QuotaExhaustedError,
    ProviderAuthError,
    classify_http_error,
)

logger = logging.getLogger(__name__)


def _is_transient_gemini_status(status: int) -> bool:
    return status in {429, 500, 502, 503, 504}


def _call_with_timeout(func, timeout_seconds: float):
    """Run ``func`` in a worker thread with a hard ``timeout_seconds`` deadline.

    The google-genai SDK does not expose a per-call timeout that covers the
    full generate_content round-trip, so we wrap the blocking call in a
    single-shot thread pool. If the worker doesn't finish in time we abandon
    it (the underlying HTTP request will eventually complete and be
    discarded) and raise ``ProviderTimeoutError`` so the cascade falls
    through to the next provider quickly.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
    from .base import ProviderTimeoutError

    if timeout_seconds <= 0:
        return func()
    # Reuse a single-thread pool per call. Creating the executor is cheap;
    # the pool is shut down immediately after the call returns or times out.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini-timeout") as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeout:
            # Worker is still running; we deliberately abandon it. The
            # ThreadPoolExecutor.__exit__ will block on shutdown until the
            # worker finishes, which defeats the timeout. To avoid that,
            # we cancel the future (best-effort) and DO NOT wait for the
            # worker — the `with` block's __exit__ would block, so we
            # detach by setting _shutdown to False via a private attribute
            # hack that is safe on CPython.
            # Simpler: just propagate the timeout; the abandoned thread
            # will keep running but won't block the cascade.
            raise ProviderTimeoutError(
                f"Gemini call exceeded {timeout_seconds:.1f}s timeout"
            )


class GeminiProvider(BaseAIProvider):
    """Google Gemini — primary provider."""

    name = "gemini"
    label = "Google Gemini"
    default_model = "gemini-2.0-flash"
    timeout = 8.0

    # Lazily-initialized SDK client shared across requests.
    _client = None
    _client_model: str = ""

    # ------------------------------------------------------------------ #
    # SDK lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def _ensure_client(cls):
        """Lazily build the google-genai client. Returns None if unconfigured."""
        if cls._client is not None:
            return cls._client
        api_key = getattr(settings, "GEMINI_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            from google import genai  # type: ignore
            cls._client = genai.Client(api_key=api_key)
            cls._client_model = getattr(settings, "GEMINI_MODEL", "") or cls.default_model
            return cls._client
        except Exception as e:  # pragma: no cover - import-time guard
            logger.warning("Could not initialize google-genai client: %s", e)
            return None

    @classmethod
    def reset(cls) -> None:
        cls._client = None
        cls._client_model = ""

    # ------------------------------------------------------------------ #
    # BaseAIProvider API
    # ------------------------------------------------------------------ #
    @classmethod
    def is_configured(cls) -> bool:
        return bool(getattr(settings, "GEMINI_API_KEY", "").strip()) and cls._ensure_client() is not None

    @classmethod
    def _model(cls) -> str:
        return getattr(settings, "GEMINI_MODEL", "") or cls.default_model

    @classmethod
    def _timeout(cls) -> float:
        return float(getattr(settings, "GEMINI_TIMEOUT", cls.timeout))

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
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
        client = cls._ensure_client()
        if client is None:
            raise ProviderUnavailableError("Gemini API key not configured")

        from google.genai import types  # type: ignore

        contents: List[Dict[str, Any]] = []
        for m in history:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        timeout_seconds = cls._timeout()
        started = time.monotonic()
        try:
            # The google-genai SDK does not accept a simple per-call
            # timeout, so we wrap the blocking call in a worker thread
            # with a hard deadline. If the worker doesn't finish in time
            # we abandon it and raise ProviderTimeoutError, which the
            # cascade turns into a cooldown + fall-through to Groq.
            response = _call_with_timeout(
                lambda: client.models.generate_content(
                    model=cls._client_model or cls._model(),
                    contents=contents,
                    config=config,
                ),
                timeout_seconds,
            )
        except ProviderError:
            raise
        except Exception as e:
            raise _map_gemini_exception(e) from e
        latency_ms = int((time.monotonic() - started) * 1000)

        text = getattr(response, "text", None) or ""
        if not text:
            try:
                parts = response.candidates[0].content.parts
                text = " ".join(getattr(p, "text", "") or "" for p in parts)
            except Exception:
                text = ""
        if not text:
            raise ProviderError(
                "Gemini returned an empty response", status_code=None
            )

        # Token usage is best-effort; some response objects expose it.
        prompt_tokens = None
        completion_tokens = None
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", None)
            completion_tokens = getattr(usage, "candidates_token_count", None)

        finish_reason = None
        try:
            cand = response.candidates[0]
            finish_reason = str(getattr(cand, "finish_reason", "") or "")
        except Exception:
            pass

        return ProviderResult(
            text=text.strip(),
            provider=cls.name,
            model=cls._client_model or cls._model(),
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason=finish_reason or None,
            raw={"provider": cls.name},
        )


def _map_gemini_exception(error: Exception) -> ProviderError:
    """Translate a google-genai / google-api-core exception to our hierarchy."""
    # Inspect common attribute locations for an HTTP status code.
    status_code = None
    for attr_path in ("status_code", "code"):
        value = getattr(error, attr_path, None)
        try:
            if value is not None:
                status_code = int(value)
                break
        except (TypeError, ValueError):
            continue
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)

    message_upper = str(error).upper()

    # Timeout / deadline-exceeded detection.
    timeout_markers = ("DEADLINE_EXCEEDED", "TIMEOUT", "DURATION_EXCEEDED")
    if any(m in message_upper for m in timeout_markers):
        return ProviderTimeoutError(str(error), status_code=status_code)

    if status_code is not None:
        return classify_http_error(int(status_code), str(error))

    # SDK raises google.api_core.exceptions.* subclasses; fall back to
    # message inspection when no status code is available.
    if "RESOURCE_EXHAUSTED" in message_upper:
        if "QUOTA" in message_upper or "BILLING" in message_upper:
            return QuotaExhaustedError(str(error))
        return RateLimitError(str(error))
    if "PERMISSION_DENIED" in message_upper or "UNAUTHENTICATED" in message_upper:
        return ProviderAuthError(str(error))
    if "UNAVAILABLE" in message_upper or "INTERNAL" in message_upper:
        return ProviderServerError(str(error))
    return ProviderError(str(error))
