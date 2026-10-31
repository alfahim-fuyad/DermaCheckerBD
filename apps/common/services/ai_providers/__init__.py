"""Multi-provider AI fallback system for the DermaCheckerBD chatbot.

This package implements the provider cascade used by the chatbot:

    Gemini (primary)  ->  Groq (secondary)  ->  OpenRouter (tertiary)

Public surface:
    - ``ProviderError`` / ``RateLimitError`` / ``QuotaExhaustedError``
      / ``ProviderTimeoutError`` / ``ProviderServerError``
      Exception hierarchy used by every provider so the fallback
      manager can decide whether to retry, cool down, or surface the
      error to the caller.
    - ``ProviderResult``        – dataclass returned by every provider.
    - ``BaseAIProvider``        – common interface every provider implements.
    - ``CooldownTracker``       – cache-backed per-provider cooldown state.
    - ``GeminiProvider``        – adapter around the existing google-genai SDK.
    - ``GroqProvider``          – OpenAI-compatible HTTP client for Groq.
    - ``OpenRouterProvider``    – OpenAI-compatible HTTP client for OpenRouter.
    - ``FallbackChatService``   – orchestrator that tries providers in order,
                                  applying cooldowns and writing usage logs.

SECURITY CONTRACT
- API keys are read from ``settings`` (env-driven) and NEVER exposed to the
  frontend.
- Frontend never calls any provider directly; it only calls our Django
  endpoint which forwards server-side.
- No image bytes are sent to any provider — only the chat conversation text.
- Conversation history sent from the browser is treated as untrusted input
  and is rebased server-side for authenticated users.
"""
from .base import (  # noqa: F401
    BaseAIProvider,
    ProviderError,
    RateLimitError,
    QuotaExhaustedError,
    ProviderTimeoutError,
    ProviderServerError,
    ProviderAuthError,
    ProviderResult,
    ChatMessage,
)
from .cooldown import CooldownTracker, CooldownEntry  # noqa: F401
from .gemini_provider import GeminiProvider  # noqa: F401
from .groq_provider import GroqProvider  # noqa: F401
from .openrouter_provider import OpenRouterProvider  # noqa: F401
from .fallback import FallbackChatService, FallbackResult  # noqa: F401
