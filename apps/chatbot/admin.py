"""Admin views for the multi-provider chatbot models.

Registered read-only so staff can audit provider usage and conversation
turns without risking accidental edits.
"""
from django.contrib import admin

from apps.chatbot.models import ChatConversation, ChatMessage, ChatUsageLog


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "provider", "model", "created_at")
    can_delete = False
    max_num = 50

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "messages_count", "created_at", "updated_at")
    search_fields = ("user__username",)
    list_filter = ("created_at", "updated_at")
    inlines = [ChatMessageInline]
    readonly_fields = ("user", "created_at", "updated_at")

    def messages_count(self, obj) -> int:
        return obj.messages.count()
    messages_count.short_description = "Messages"

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(ChatUsageLog)
class ChatUsageLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "provider",
        "model",
        "success",
        "error_code",
        "latency_ms",
        "user",
    )
    list_filter = ("provider", "success", "error_code", "created_at")
    search_fields = ("user__username", "error_message", "provider")
    readonly_fields = (
        "user",
        "provider",
        "model",
        "success",
        "error_code",
        "error_message",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request) -> bool:
        return False
