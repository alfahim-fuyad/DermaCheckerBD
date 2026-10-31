"""Smoke test for the multi-provider AI fallback cascade.

This is NOT a Django test case — it's a standalone script that exercises
the cascade with patched provider classes to prove:

1. The cascade tries Gemini first.
2. On Gemini rate-limit failure, it sets a cooldown and falls through
   to Groq.
3. On Groq failure, it falls through to OpenRouter.
4. When every provider fails, it returns the canned reply.
5. Usage logs are written for every attempt.
6. Cooldowns prevent the cascade from retrying a just-failed provider.

Run it with:
    DJANGO_SETTINGS_MODULE=smoke_test_settings python manage.py shell \
        -c "exec(open('scripts/smoke_test_fallback.py').read())"
"""
from unittest.mock import patch

from django.test.utils import setup_databases
from django.test.runner import DiscoverRunner


def main():
    runner = DiscoverRunner(verbosity=0)
    old_config = runner.setup_databases()

    from apps.common.services.ai_providers import (
        FallbackChatService,
        GeminiProvider,
        GroqProvider,
        OpenRouterProvider,
        RateLimitError,
        ProviderServerError,
        ProviderResult,
        CooldownTracker,
    )
    from apps.chatbot.models import ChatUsageLog
    from apps.common.services.ai_providers.fallback import PROVIDER_REGISTRY

    print("=== Smoke test: multi-provider fallback cascade ===\n")

    # --- Test 1: Gemini succeeds on the first try ---
    CooldownTracker.clear()
    ChatUsageLog.objects.all().delete()
    print("[1] Gemini succeeds on first try")
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(
            GeminiProvider, "chat",
            classmethod(lambda cls, **kw: ProviderResult(
                text="Hello from Gemini", provider="gemini", model="gemini-2.0-flash",
                latency_ms=120,
            )),
         ):
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
    print(f"    provider={result.provider}, text={result.text!r}")
    print(f"    attempts: {len(result.attempts)}")
    print(f"    usage logs: {ChatUsageLog.objects.count()}")
    assert result.provider == "gemini"
    assert result.text == "Hello from Gemini"
    assert ChatUsageLog.objects.filter(provider="gemini", success=True).count() == 1
    print("    PASS\n")

    # --- Test 2: Gemini rate-limited, Groq succeeds ---
    CooldownTracker.clear()
    ChatUsageLog.objects.all().delete()
    print("[2] Gemini 429 -> cascade to Groq")
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(
            GeminiProvider, "chat",
            classmethod(lambda cls, **kw: (_ for _ in ()).throw(
                RateLimitError("429 from Gemini", status_code=429)
            )),
         ), \
         patch.object(
            GroqProvider, "chat",
            classmethod(lambda cls, **kw: ProviderResult(
                text="Hello from Groq", provider="groq", model="llama-3.3-70b-versatile",
                latency_ms=80,
            )),
         ):
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
    print(f"    provider={result.provider}, text={result.text!r}")
    print(f"    attempts: {[a['provider'] + ':' + a.get('error_code', 'ok') for a in result.attempts]}")
    print(f"    cooldowns set: {[c.provider + ':' + c.reason for c in result.cooldowns_set]}")
    print(f"    usage logs: {ChatUsageLog.objects.count()} "
          f"(gemini fail={ChatUsageLog.objects.filter(provider='gemini', success=False).count()}, "
          f"groq ok={ChatUsageLog.objects.filter(provider='groq', success=True).count()})")
    assert result.provider == "groq"
    assert result.text == "Hello from Groq"
    assert CooldownTracker.is_cooled_down("gemini")
    assert ChatUsageLog.objects.filter(provider="gemini", success=False, error_code="rate_limit").count() == 1
    assert ChatUsageLog.objects.filter(provider="groq", success=True).count() == 1
    print("    PASS\n")

    # --- Test 3: Gemini cooled down, Groq succeeds (Gemini skipped) ---
    print("[3] Gemini on cooldown -> skipped, Groq succeeds")
    CooldownTracker.set("gemini", "rate_limit", ttl_seconds=300)
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: (_ for _ in ()).throw(AssertionError("Gemini should have been skipped")))), \
         patch.object(GroqProvider, "chat", classmethod(lambda cls, **kw: ProviderResult(text="Hello from Groq", provider="groq", model="llama", latency_ms=80))):
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
    print(f"    provider={result.provider}, attempts={[a['provider'] + ':cooled_down=' + str(a.get('cooldown', {}).get('active', False)) for a in result.attempts]}")
    assert result.provider == "groq"
    assert any(a["provider"] == "gemini" and a.get("cooldown") for a in result.attempts)
    print("    PASS\n")

    # --- Test 4: All providers fail -> canned reply ---
    CooldownTracker.clear()
    ChatUsageLog.objects.all().delete()
    print("[4] All providers fail -> canned reply")
    with patch.object(GeminiProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GroqProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(OpenRouterProvider, "is_configured", classmethod(lambda cls: True)), \
         patch.object(GeminiProvider, "chat", classmethod(lambda cls, **kw: (_ for _ in ()).throw(ProviderServerError("503 from Gemini", status_code=503)))), \
         patch.object(GroqProvider, "chat", classmethod(lambda cls, **kw: (_ for _ in ()).throw(ProviderServerError("503 from Groq", status_code=503)))), \
         patch.object(OpenRouterProvider, "chat", classmethod(lambda cls, **kw: (_ for _ in ()).throw(ProviderServerError("503 from OpenRouter", status_code=503)))):
        result = FallbackChatService.chat(
            history=[], user_message="hi", language="en",
            is_authenticated=True, user=None,
        )
    print(f"    provider={result.provider}, success={result.success}")
    print(f"    text starts with: {result.text[:60]!r}...")
    print(f"    attempts: {[(a['provider'], a.get('error_code', 'ok')) for a in result.attempts]}")
    assert result.provider == "canned"
    assert result.success is False
    assert ChatUsageLog.objects.filter(success=False).count() == 3
    print(f"    usage logs (all failures): {ChatUsageLog.objects.count()}")
    print("    PASS\n")

    # --- Test 5: Bengali canned reply uses Bengali text ---
    print("[5] Bengali canned reply")
    result = FallbackChatService.chat(
        history=[], user_message="কিছু জানতে চাই", language="bn",
        is_authenticated=True, user=None,
    )
    print(f"    provider={result.provider}, text starts: {result.text[:50]!r}")
    assert result.provider == "canned"
    assert "সহকারীটি" in result.text or "DermaCheckerBD" in result.text
    print("    PASS\n")

    print("=== All smoke tests passed ===")
    runner.teardown_databases(old_config)


if __name__ == "__main__":
    main()
