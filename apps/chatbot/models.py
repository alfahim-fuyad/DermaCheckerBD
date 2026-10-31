"""Database models for the multi-provider chatbot.

Three models:

    ChatConversation
        One row per authenticated user. Created on first AI reply and
        reused thereafter. Holds the user-side conversation state.

    ChatMessage
        Individual turns within a ``ChatConversation``. ``role`` is
        ``user`` or ``model``. The ``provider`` / ``model`` columns on
        ``model`` turns record which provider answered, so admins can
        audit provider usage per user.

    ChatUsageLog
        One row per *provider attempt* (not per user turn). A single
        user turn can produce multiple ``ChatUsageLog`` rows when the
        cascade falls through providers. Used for the staff usage view
        and for provider health monitoring.

SECURITY / PRIVACY:
- Conversation content is stored only for authenticated users. Anonymous
  users never trigger a provider call, so no ``ChatMessage`` is written
  for them.
- ``ChatUsageLog`` stores ``user_id`` only for authenticated users; for
  anonymous visitors (which by design never reach the provider cascade)
  the column is NULL.
- ChatMessage.content is truncated to a hard cap on write so a malicious
  history payload cannot balloon the database.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ChatConversation(models.Model):
    """A user's running chat conversation with the assistant."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_conversation",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"ChatConversation(user={self.user_id})"


class ChatMessage(models.Model):
    """A single turn (user or model) within a ``ChatConversation``."""

    ROLE_CHOICES = (("user", "User"), ("model", "Model"))

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=8, choices=ROLE_CHOICES)
    content = models.TextField()
    # Filled only for ``model`` turns; empty for user turns.
    provider = models.CharField(max_length=32, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"ChatMessage({self.role}, conv={self.conversation_id})"

    @classmethod
    def trim_to_last(cls, conversation: ChatConversation, keep: int = 40) -> int:
        """Keep only the last ``keep`` messages for ``conversation``.

        Returns the number of deleted rows.
        """
        if keep <= 0:
            return 0
        total = cls.objects.filter(conversation=conversation).count()
        if total <= keep:
            return 0
        cutoff_ids = list(
            cls.objects.filter(conversation=conversation)
            .order_by("-created_at", "-id")
            .values_list("id", flat=True)[:keep]
        )
        deleted, _ = cls.objects.filter(
            conversation=conversation
        ).exclude(id__in=cutoff_ids).delete()
        return deleted


class ChatUsageLog(models.Model):
    """One row per provider attempt — used for the staff usage view."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_usage_logs",
    )
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=128, blank=True, default="")
    success = models.BooleanField(default=False)
    error_code = models.CharField(max_length=32, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    latency_ms = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "success"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        status = "ok" if self.success else "fail"
        return f"ChatUsageLog({self.provider}, {status})"
