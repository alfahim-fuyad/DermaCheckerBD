"""Management command: test each chatbot AI provider independently.

Sends a tiny "Hello" prompt to each configured provider (Gemini, Groq,
OpenRouter) and prints the result — success or the full error message
including the provider's response body. This is the fastest way to
diagnose "chatbox ans dite onk late kore" issues: run this command and
see exactly which provider is failing and WHY.

Usage:
    python manage.py test_chatbot_providers
    python manage.py test_chatbot_providers --provider gemini
    python manage.py test_chatbot_providers --provider groq --provider openrouter

Typical output when everything is healthy:
    [1/3] gemini (gemini-2.0-flash) ... OK (1.2s, 28 tokens)
    [2/3] groq (llama-3.3-70b-versatile) ... OK (0.4s, 22 tokens)
    [3/3] openrouter (meta-llama/llama-3.1-8b-instruct:free) ... OK (0.8s, 25 tokens)

Typical output when a model name is wrong:
    [1/3] gemini (gemini-3.8-flash) ... FAIL (model_not_found, 3.1s)
          404 model not found from provider: {"error":{"message":"models gemini-3.8-flash is not found...
    [2/3] groq (llama-3.3-70b-versatile) ... OK (0.4s, 22 tokens)
    [3/3] openrouter (meta-llama/llama-3.1-8b-instruct:free) ... OK (0.8s, 25 tokens)
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.services.ai_providers import (
    GeminiProvider, GroqProvider, OpenRouterProvider,
    ChatMessage, ProviderError, ProviderUnavailableError,
    PROVIDER_REGISTRY,
)


PROVIDER_CHOICES = ["gemini", "groq", "openrouter"]


class Command(BaseCommand):
    help = "Test each chatbot AI provider with a tiny 'Hello' prompt and print the result."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            action="append",
            choices=PROVIDER_CHOICES,
            help="Test only the named provider(s). Can be given multiple times.",
        )
        parser.add_argument(
            "--prompt",
            default="Reply with the single word: hello",
            help="Prompt to send to each provider. Default is a tiny hello test.",
        )

    def handle(self, *args, **options):
        selected = options.get("provider") or PROVIDER_CHOICES
        prompt = options["prompt"]
        order = list(getattr(settings, "CHATBOT_PROVIDER_ORDER", PROVIDER_CHOICES))

        # Show configuration first
        self.stdout.write(self.style.SUCCESS("=== Chatbot provider configuration ==="))
        self.stdout.write(f"CHATBOT_PROVIDER_ORDER = {order}")
        self.stdout.write(f"GEMINI_MODEL  = {getattr(settings, 'GEMINI_MODEL', '(unset)')}")
        self.stdout.write(f"GROQ_MODEL    = {getattr(settings, 'GROQ_MODEL', '(unset)')}")
        self.stdout.write(f"OPENROUTER_MODEL = {getattr(settings, 'OPENROUTER_MODEL', '(unset)')}")
        self.stdout.write(f"GEMINI_TIMEOUT    = {getattr(settings, 'GEMINI_TIMEOUT', 8)}s")
        self.stdout.write(f"GROQ_TIMEOUT      = {getattr(settings, 'GROQ_TIMEOUT', 8)}s")
        self.stdout.write(f"OPENROUTER_TIMEOUT = {getattr(settings, 'OPENROUTER_TIMEOUT', 12)}s")
        self.stdout.write("")

        # Check for known-deprecated model names and warn the operator.
        deprecated = {
            "llama-3.3-70b-versatile": (
                "DEPRECATED on Groq free/developer tier as of August 16, 2026. "
                "Use 'openai/gpt-oss-120b' instead. "
                "See: https://console.groq.com/docs/models"
            ),
            "meta-llama/llama-3.1-8b-instruct:free": (
                "RETIRED by OpenRouter in 2026. Use 'openrouter/free' instead. "
                "See: https://openrouter.ai/models"
            ),
            "deepseek/deepseek-r1:free": (
                "RETIRED by OpenRouter in 2026. Use 'openrouter/free' instead."
            ),
            "meta-llama/llama-3.3-70b-instruct:free": (
                "RETIRED by OpenRouter in 2026. Use 'openrouter/free' instead."
            ),
        }
        groq_model = getattr(settings, "GROQ_MODEL", "").strip()
        or_model = getattr(settings, "OPENROUTER_MODEL", "").strip()
        if groq_model in deprecated or or_model in deprecated:
            self.stdout.write(self.style.ERROR("=== DEPRECATED MODEL WARNING ==="))
            for model_name in (groq_model, or_model):
                if model_name in deprecated:
                    self.stdout.write(self.style.ERROR(
                        f"  {model_name}: {deprecated[model_name]}"
                    ))
            self.stdout.write(
                "Set GROQ_MODEL / OPENROUTER_MODEL to a currently-valid model "
                "in your Render environment variables, then redeploy.\n"
            )

        # Check which API keys are set (without revealing them)
        self.stdout.write("=== API key status (showing only first/last 4 chars) ===")
        for slug, attr in [
            ("gemini", "GEMINI_API_KEY"),
            ("groq", "GROQ_API_KEY"),
            ("openrouter", "OPENROUTER_API_KEY"),
        ]:
            key = getattr(settings, attr, "").strip()
            if not key:
                self.stdout.write(f"  {slug:12s}: NOT SET")
            elif len(key) <= 8:
                self.stdout.write(f"  {slug:12s}: {key[:4]}…{key[-4:]} (len={len(key)})")
            else:
                self.stdout.write(f"  {slug:12s}: {key[:4]}…{key[-4:]} (len={len(key)})")
        self.stdout.write("")

        # Test each selected provider
        self.stdout.write(self.style.SUCCESS(f"=== Testing {len(selected)} provider(s) with prompt: {prompt!r} ==="))
        system_prompt = "You are a test assistant. Reply briefly."
        results = []
        for slug in selected:
            provider_cls = PROVIDER_REGISTRY.get(slug)
            if not provider_cls:
                self.stdout.write(self.style.ERROR(f"  {slug}: unknown provider"))
                continue

            configured = provider_cls.is_configured()
            model_name = provider_cls._model()
            label = f"[{slug}] {model_name}"

            if not configured:
                self.stdout.write(self.style.WARNING(
                    f"  {label} ... SKIP (not configured — no API key or SDK unavailable)"
                ))
                results.append((slug, "skip", "not configured"))
                continue

            self.stdout.write(f"  {label} ... ", ending="")
            self.stdout._out.flush()

            started = time.monotonic()
            try:
                result = provider_cls.chat(
                    system_prompt=system_prompt,
                    history=[],
                    user_message=prompt,
                    temperature=0.0,
                    max_output_tokens=50,
                    language="en",
                )
                elapsed = time.monotonic() - started
                self.stdout.write(self.style.SUCCESS(
                    f"OK ({elapsed:.1f}s, {result.total_tokens or '?'} tokens)"
                ))
                self.stdout.write(f"    reply: {result.text[:120]!r}")
                results.append((slug, "ok", result.text[:80]))
            except ProviderUnavailableError as e:
                self.stdout.write(self.style.WARNING(f"SKIP ({e})"))
                results.append((slug, "skip", str(e)))
            except ProviderError as e:
                elapsed = time.monotonic() - started
                self.stdout.write(self.style.ERROR(
                    f"FAIL ({e.code}, {elapsed:.1f}s)"
                ))
                # Print the full error message including the response body.
                self.stdout.write(f"    {str(e)[:400]}")
                results.append((slug, "fail", str(e)[:200]))
            except Exception as e:
                elapsed = time.monotonic() - started
                self.stdout.write(self.style.ERROR(
                    f"FAIL (unexpected, {elapsed:.1f}s): {type(e).__name__}: {e}"
                ))
                results.append((slug, "fail", str(e)[:200]))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Summary ==="))
        ok = sum(1 for _, status, _ in results if status == "ok")
        fail = sum(1 for _, status, _ in results if status == "fail")
        skip = sum(1 for _, status, _ in results if status == "skip")
        self.stdout.write(f"  OK: {ok}  FAIL: {fail}  SKIP: {skip}")

        if fail > 0:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "FAILures detected. Common causes:\n"
                "  1. DEPRECATED model name — the most common cause in late 2026:\n"
                "     - GROQ: 'llama-3.3-70b-versatile' was deprecated Aug 2026.\n"
                "       Use 'openai/gpt-oss-120b' instead.\n"
                "     - OPENROUTER: 'meta-llama/llama-3.1-8b-instruct:free' was retired.\n"
                "       Use 'openrouter/free' instead.\n"
                "     Verify at:\n"
                "       https://console.groq.com/docs/models\n"
                "       https://openrouter.ai/models\n"
                "  2. Invalid API key — check GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY\n"
                "  3. Quota exhausted — check your provider dashboard\n"
                "  4. Network blocked — Render might be blocking outbound HTTPS\n"
            ))
            # Exit with non-zero code so CI / Render detects the failure.
            import sys
            sys.exit(1)
