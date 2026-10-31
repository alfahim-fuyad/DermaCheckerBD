"""Management command: clear chatbot provider cooldowns.

Usage:
    python manage.py clear_chat_cooldowns            # clear all providers
    python manage.py clear_chat_cooldowns gemini      # clear only Gemini
    python manage.py clear_chat_cooldowns gemini groq # clear Gemini + Groq

Useful after a provider outage when you want to immediately retry the
primary provider instead of waiting for the cooldown TTL to expire.
"""
from django.core.management.base import BaseCommand

from apps.common.services.ai_providers import CooldownTracker


class Command(BaseCommand):
    help = "Clear chatbot provider cooldowns so the cascade retries immediately."

    def add_arguments(self, parser):
        parser.add_argument(
            "providers",
            nargs="*",
            help=(
                "Provider slugs to clear (e.g. 'gemini', 'groq', 'openrouter'). "
                "If none are given, all configured providers are cleared."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings

        requested = [p.strip() for p in options.get("providers", []) if p and p.strip()]
        valid_slugs = set(getattr(settings, "CHATBOT_PROVIDER_ORDER", []))
        targets = requested or list(valid_slugs)
        cleared = []
        unknown = []
        for slug in targets:
            if slug not in valid_slugs:
                unknown.append(slug)
                continue
            CooldownTracker.clear(slug)
            cleared.append(slug)
        if cleared:
            self.stdout.write(self.style.SUCCESS(
                f"Cleared cooldowns for: {', '.join(cleared)}"
            ))
        if unknown:
            self.stdout.write(self.style.WARNING(
                f"Unknown provider slugs (ignored): {', '.join(unknown)}. "
                f"Valid slugs: {', '.join(sorted(valid_slugs))}"
            ))
        if not cleared and not unknown:
            self.stdout.write("No cooldowns to clear.")
