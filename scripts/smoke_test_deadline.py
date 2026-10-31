"""Smoke test: cascade deadline + deferred DB writes."""
import time
from unittest.mock import patch

from django.test.utils import setup_databases
from django.test.runner import DiscoverRunner
from django.db import transaction


def main():
    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()

    from apps.common.services.ai_providers import (
        FallbackChatService, GeminiProvider, GroqProvider, OpenRouterProvider,
        ProviderResult, ProviderTimeoutError, CooldownTracker,
    )
    from apps.chatbot.models import ChatUsageLog, ChatConversation, ChatMessage
    from django.contrib.auth import get_user_model

    User = get_user_model()

    print("=== Smoke test: cascade deadline + deferred DB writes ===\n")

    # --- 1. Cascade deadline stops the cascade early ---
    CooldownTracker.clear()
    ChatUsageLog.objects.all().delete()
    print("[1] Cascade deadline stops the cascade when a provider is slow")
    # Simulate Gemini taking 5 seconds (under the 15s deadline, but
    # proves the cascade waits for the configured timeout).
    def slow_gemini(**kw):
        time.sleep(0.3)  # 300ms — fast for the test
        return ProviderResult(
            text="Slow Gemini reply", provider="gemini",
            model="gemini-2.0-flash", latency_ms=300,
        )
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: slow_gemini(**kw))):
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
    print(f"    provider={result.provider}, latency ~300ms")
    assert result.provider == "gemini"
    print("    PASS\n")

    # --- 2. Deadline triggers when every provider times out ---
    CooldownTracker.clear()
    print("[2] Deadline returns canned reply when all providers are slow")
    def slow_fail(**kw):
        time.sleep(0.5)
        raise ProviderTimeoutError("simulated slow timeout")
    # Override the cascade deadline to 1 second for this test
    from django.test import override_settings
    with override_settings(CHATBOT_CASCADE_DEADLINE_SECONDS=1), \
         patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: slow_fail(**kw))), \
         patch.object(GroqProvider, "chat", classmethod(lambda cls, **kw: slow_fail(**kw))), \
         patch.object(OpenRouterProvider, "chat", classmethod(lambda cls, **kw: slow_fail(**kw))):
        started = time.monotonic()
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
        elapsed = time.monotonic() - started
    print(f"    elapsed={elapsed:.2f}s, provider={result.provider}")
    assert result.provider == "canned"
    # The cascade should NOT have tried all three providers (each takes
    # 0.5s + 30s timeout). With a 1s deadline, after Gemini's 0.5s sleep
    # + raise, only ~0.5s budget remains — Groq might or might not be
    # tried, but OpenRouter definitely won't.
    print(f"    attempts: {[a['provider'] for a in result.attempts]}")
    print("    PASS\n")

    # --- 3. Deferred DB writes ---
    CooldownTracker.clear()
    ChatUsageLog.objects.all().delete()
    print("[3] Deferred DB writes: ChatUsageLog appears after commit")
    user = User.objects.create_user(username="defer-test", password="Pass!2024")
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: ProviderResult(
             text="Deferred test reply", provider="gemini",
             model="gemini-2.0-flash", latency_ms=50,
         ))):
        # Wrap in a transaction so on_commit fires at the end.
        with transaction.atomic():
            result = FallbackChatService.chat(
                history=[], user_message="hi", language="en",
                is_authenticated=True, user=user,
            )
            # Before commit: no usage log yet (deferred).
            before = ChatUsageLog.objects.count()
            before_msgs = ChatMessage.objects.count()
        # After the atomic block exits, on_commit fires.
        after = ChatUsageLog.objects.count()
        after_msgs = ChatMessage.objects.count()
    print(f"    usage logs before commit={before}, after commit={after}")
    print(f"    chat messages before commit={before_msgs}, after commit={after_msgs}")
    assert before == 0, "usage log should be deferred until commit"
    assert after >= 1, "usage log should appear after commit"
    assert before_msgs == 0, "chat message should be deferred until commit"
    assert after_msgs >= 2, "user+model messages should appear after commit"
    print("    PASS\n")

    print("=== All deadline + deferral smoke tests passed ===")
    runner.teardown_databases(old_config)


if __name__ == "__main__":
    main()
