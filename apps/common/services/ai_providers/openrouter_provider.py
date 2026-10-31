"""OpenRouter provider — tertiary in the fallback cascade.

OpenRouter is an OpenAI-compatible router that fronts many underlying
models. We use the ``requests`` library directly so no new heavyweight
dependency is added.

Docs: https://openrouter.ai/docs/api-reference/overview
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

from .base import (
    BaseAIProvider,
    ChatMessage,
    ProviderError,
    ProviderResult,
    ProviderUnavailableError,
    ProviderTimeoutError,
    classify_http_error,
)
from .groq_provider import _as_int, _finish_reason, _safe_text

logger = logging.getLogger(__name__)


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter — OpenAI-compatible chat completions."""

    name = "openrouter"
    label = "OpenRouter"
    default_model = "meta-llama/llama-3.1-8b-instruct:free"
    timeout = 45.0

    @classmethod
    def is_configured(cls) -> bool:
        return bool(getattr(settings, "OPENROUTER_API_KEY", "").strip())

    @classmethod
    def _model(cls) -> str:
        return getattr(settings, "OPENROUTER_MODEL", "") or cls.default_model

    @classmethod
    def _timeout(cls) -> float:
        return float(getattr(settings, "OPENROUTER_TIMEOUT", cls.timeout))

    @classmethod
    def _api_key(cls) -> str:
        return getattr(settings, "OPENROUTER_API_KEY", "").strip()

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
        api_key = cls._api_key()
        if not api_key:
            raise ProviderUnavailableError("OPENROUTER_API_KEY not configured")

        messages = GroqProvider_style_build_messages(system_prompt, history, user_message)
        payload: Dict[str, Any] = {
            "model": cls._model(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter recommends these optional identification headers; they
        # are not secrets and help with rate-limit accounting.
        site_url = getattr(settings, "OPENROUTER_SITE_URL", "").strip()
        site_name = getattr(settings, "OPENROUTER_SITE_NAME", "").strip()
        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-Title"] = site_name

        started = time.monotonic()
        try:
            response = requests.post(
                OPENROUTER_CHAT_URL,
                json=payload,
                headers=headers,
                timeout=cls._timeout(),
            )
        except requests.exceptions.Timeout as e:
            raise ProviderTimeoutError(str(e)) from e
        except requests.exceptions.ConnectionError as e:
            raise ProviderTimeoutError(f"connection error: {e}") from e
        except requests.exceptions.RequestException as e:
            raise ProviderError(f"request error: {e}") from e
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code != 200:
            body = _safe_text(response)
            raise classify_http_error(response.status_code, body)

        try:
            data = response.json()
        except ValueError as e:
            raise ProviderError(f"invalid JSON from OpenRouter: {e}") from e

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected OpenRouter response shape: {e}") from e

        text = (text or "").strip()
        if not text:
            raise ProviderError("OpenRouter returned an empty response")

        usage = data.get("usage") or {}
        return ProviderResult(
            text=text,
            provider=cls.name,
            model=str(data.get("model") or cls._model()),
            latency_ms=latency_ms,
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            finish_reason=_finish_reason(data),
            raw={"provider": cls.name, "id": data.get("id")},
        )


def GroqProvider_style_build_messages(
    system_prompt: str,
    history: List[ChatMessage],
    user_message: str,
) -> List[Dict[str, str]]:
    """Shared OpenAI-style message assembler.

    Named explicitly so readers know it intentionally mirrors the Groq
    provider's helper. Kept here to avoid a cross-import cycle and to
    keep the OpenRouter adapter self-contained.
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in history:
        role = "assistant" if m.role in ("model", "assistant") else "user"
        messages.append({"role": role, "content": m.content})
    messages.append({"role": "user", "content": user_message})
    return messages
