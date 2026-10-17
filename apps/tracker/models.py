"""Lesion Follow-up Tracker models."""
from django.conf import settings
from django.db import models


def tracked_image_path(instance, filename):
    return f"tracked/{instance.lesion_id}/{filename}"


class LesionRecord(models.Model):
    """A user-private lesion tracking record. Groups multiple photos over time."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesion_records",
    )
    lesion_id = models.CharField(max_length=32, unique=True, db_index=True)
    label = models.CharField(max_length=128, default="Untitled lesion", help_text="User-friendly label.")
    body_location = models.CharField(max_length=64, blank=True, default="", help_text="Body location (e.g., 'left forearm').")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"Lesion {self.lesion_id} ({self.label})"


class FollowUpPhoto(models.Model):
    """A single dated photograph within a LesionRecord."""

    lesion = models.ForeignKey(LesionRecord, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=tracked_image_path, max_length=255)
    captured_at = models.DateField(db_index=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at", "created_at"]
        indexes = [models.Index(fields=["lesion", "captured_at"])]
