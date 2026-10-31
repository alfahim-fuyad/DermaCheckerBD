"""Per-provider cooldown tracker.

When a provider fails with a retryable error (rate limit, quota, timeout,
or server error), the fallback manager calls ``CooldownTracker.set()``
with a short TTL. While the cooldown is active, that provider is skipped
and the next provider in the cascade is tried.

The tracker uses Django's cache framework so cooldowns survive across
requests within the same worker. In production with a shared cache
backend (Redis/Memcached), cooldowns are shared across all web workers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)


CACHE_KEY_PREFIX = "chatbot:cooldown"


@dataclass
class CooldownEntry:
    """Why and until-when a provider is on cooldown."""

    provider: str
    reason: str  # one of ProviderError.code values
    until: float  # epoch seconds
    set_at: float

    @property
    def remaining(self) -> float:
        import time
        return max(0.0, self.until - time.time())


class CooldownTracker:
    """Tiny wrapper around Django's cache for provider cooldowns."""

    @staticmethod
    def _key(provider: str) -> str:
        return f"{CACHE_KEY_PREFIX}:{provider}"

    @classmethod
    def set(
        cls,
        provider: str,
        reason: str,
        *,
        ttl_seconds: Optional[float] = None,
    ) -> CooldownEntry:
        """Mark ``provider`` as cooled down for ``ttl_seconds`` seconds.

        Defaults to ``settings.CHATBOT_PROVIDER_COOLDOWN_SECONDS``.
        """
        import time

        from django.conf import settings

        if ttl_seconds is None:
            ttl_seconds = float(getattr(settings, "CHATBOT_PROVIDER_COOLDOWN_SECONDS", 60))

        now = time.time()
        until = now + ttl_seconds
        entry = CooldownEntry(
            provider=provider,
            reason=reason,
            until=until,
            set_at=now,
        )
        cache.set(cls._key(provider), entry, timeout=int(max(1, ttl_seconds)))
        logger.info(
            "Provider %s on cooldown for %.1fs (reason=%s)",
            provider,
            ttl_seconds,
            reason,
        )
        return entry

    @classmethod
    def get(cls, provider: str) -> Optional[CooldownEntry]:
        """Return the active cooldown entry, or None if the provider is free."""
        entry = cache.get(cls._key(provider))
        if entry is None:
            return None
        if entry.remaining <= 0:
            # Stale entry — clear it so the next call sees a clean state.
            cache.delete(cls._key(provider))
            return None
        return entry

    @classmethod
    def is_cooled_down(cls, provider: str) -> bool:
        return cls.get(provider) is not None

    @classmethod
    def clear(cls, provider: Optional[str] = None) -> None:
        """Manually clear cooldowns (used by the management command)."""
        if provider:
            cache.delete(cls._key(provider))
            return
        # LocMemCache does not expose iter_keys, so we clear by the known
        # provider list instead.
        from django.conf import settings
        for slug in getattr(settings, "CHATBOT_PROVIDER_ORDER", []):
            cache.delete(cls._key(slug))
