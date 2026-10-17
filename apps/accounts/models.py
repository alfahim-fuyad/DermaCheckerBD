from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PatientProfile(models.Model):
    """Demographics owned by one signed-in account."""

    SEX_CHOICES = [
        ("", "Not specified"),
        ("female", "Female"),
        ("male", "Male"),
        ("other", "Other"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )
    phone = models.CharField(max_length=32, blank=True)
    sex = models.CharField(max_length=24, choices=SEX_CHOICES, blank=True, default="")
    age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(130)],
    )
    location = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Patient profile for {self.user.get_username()}"
