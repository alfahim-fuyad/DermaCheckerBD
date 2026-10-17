"""Database models for the predictor app."""
from django.conf import settings
from django.db import models


def prediction_image_path(instance, filename):
    return f"uploads/{instance.reference_id}_{filename}"


class PredictionRecord(models.Model):
    """A single-image prediction record.

    Stores the user (nullable for anonymous), image, predicted class,
    confidence, full probabilities JSON, and the optional image-quality and
    reliability reports.

    Anonymous records are scoped to the visitor's session via `session_key`
    so the same browser can see and delete their own past predictions
    without an account. If the visitor later signs in, optionally migrate
    their anonymous records to the new account (handled in the upload view).

    Patient name is saved for the report workflow. Contact details remain
    on the user's private PatientProfile, not on each prediction record.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="prediction_records",
        help_text="Owner of this record. Null for anonymous predictions.",
    )
    session_key = models.CharField(
        max_length=64, blank=True, default="",
        db_index=True,
        help_text="Session key for anonymous records. Empty when user is set.",
    )
    reference_id = models.CharField(max_length=32, unique=True, db_index=True)
    image = models.ImageField(upload_to=prediction_image_path, max_length=255)
    image_name = models.CharField(max_length=255, default="")
    patient_name = models.CharField(max_length=150, blank=True, default="")

    predicted_class = models.CharField(max_length=32)
    predicted_name = models.CharField(max_length=128)
    category = models.CharField(max_length=32)
    confidence = models.FloatField()
    probabilities = models.JSONField(default=dict)

    # Quality report snapshot (optional — populated if quality check ran).
    quality_report = models.JSONField(default=dict, blank=True)
    # Reliability report snapshot (optional — populated if reliability check ran).
    reliability_report = models.JSONField(default=dict, blank=True)
    # Wrong-input protection snapshot.
    wrong_input_report = models.JSONField(default=dict, blank=True)

    backend = models.CharField(max_length=32, default="mock")

    REVIEW_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("appointment_planned", "Appointment Planned"),
        ("reviewed", "Reviewed"),
    ]
    review_status = models.CharField(
        max_length=24, choices=REVIEW_STATUS_CHOICES, default="pending", db_index=True
    )
    review_date = models.DateField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(
                fields=["session_key", "-created_at"],
                name="predictor_p_session_5b1c2a_idx",
            ),
            models.Index(fields=["predicted_class"]),
        ]
        permissions = [
            (
                "view_medical_priority_queue",
                "Can access and manage the medical follow-up queue",
            ),
        ]

    def __str__(self):
        return f"Prediction {self.reference_id} ({self.predicted_class})"

    def category_banner_class(self) -> str:
        return {
            "benign": "benign",
            "malignant": "malignant",
            "pre malignant": "pre-malignant",
        }.get(self.category, "unknown")
