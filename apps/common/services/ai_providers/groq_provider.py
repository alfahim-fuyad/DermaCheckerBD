"""Groq provider — secondary in the fallback cascade.

Groq exposes an OpenAI-compatible Chat Completions API. We use the
``requests`` library (already a project dependency) instead of pulling
in the ``openai`` SDK, so the cascade has zero new heavyweight deps.

Docs: https://console.groq.com/docs/api-reference#chat
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

logger = logging.getLogger(__name__)


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(BaseAIProvider):
    """Groq Cloud — OpenAI-compatible chat completions."""

    name = "groq"
    label = "Groq Cloud"
    default_model = "llama-3.3-70b-versatile"
    timeout = 30.0

    @classmethod
    def is_configured(cls) -> bool:
        return bool(getattr(settings, "GROQ_API_KEY", "").strip())

    @classmethod
    def _model(cls) -> str:
        return getattr(settings, "GROQ_MODEL", "") or cls.default_model

    @classmethod
    def _timeout(cls) -> float:
        return float(getattr(settings, "GROQ_TIMEOUT", cls.timeout))

    @classmethod
    def _api_key(cls) -> str:
        return getattr(settings, "GROQ_API_KEY", "").strip()

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
            raise ProviderUnavailableError("GROQ_API_KEY not configured")

        messages = cls._build_messages(system_prompt, history, user_message)
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

        started = time.monotonic()
        try:
            response = requests.post(
                GROQ_CHAT_URL,
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
            raise ProviderError(f"invalid JSON from Groq: {e}") from e

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected Groq response shape: {e}") from e

        text = (text or "").strip()
        if not text:
            raise ProviderError("Groq returned an empty response")

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

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_messages(
        system_prompt: str,
        history: List[ChatMessage],
        user_message: str,
    ) -> List[Dict[str, str]]:
        """Assemble the OpenAI-style ``messages`` array.

        The browser cannot inject a system role into history (the chatbot
        view enforces this), so we prepend our trusted system prompt here.
        """
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for m in history:
            role = "assistant" if m.role in ("model", "assistant") else "user"
            messages.append({"role": role, "content": m.content})
        messages.append({"role": "user", "content": user_message})
        return messages


def _safe_text(response) -> str:
    try:
        return response.text or ""
    except Exception:
        return ""


def _as_int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _finish_reason(data: Dict[str, Any]) -> Optional[str]:
    try:
        return str(data["choices"][0].get("finish_reason") or "") or None
    except (KeyError, IndexError, TypeError):
        return None
