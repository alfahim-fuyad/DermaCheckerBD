from django.urls import path
from . import views

app_name = "chatbot"

urlpatterns = [
    # Open to all users. Anonymous users only receive the 7 FAQs;
    # authenticated users get the multi-provider AI cascade.
    path("message/", views.message_view, name="message"),
    # Login-required endpoints for the persisted conversation.
    path("history/", views.history_view, name="history"),
    path("clear/", views.clear_view, name="clear"),
    # Authenticated-only provider health and staff-only usage logs.
    path("providers/", views.providers_view, name="providers"),
    path("usage/", views.usage_view, name="usage"),
]
