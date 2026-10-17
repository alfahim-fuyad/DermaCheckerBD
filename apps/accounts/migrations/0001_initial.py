from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phone", models.CharField(blank=True, max_length=32)),
                (
                    "sex",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "Not specified"),
                            ("female", "Female"),
                            ("male", "Male"),
                            ("other", "Other"),
                            ("prefer_not_to_say", "Prefer not to say"),
                        ],
                        default="",
                        max_length=24,
                    ),
                ),
                (
                    "age",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            MinValueValidator(0),
                            MaxValueValidator(130),
                        ],
                    ),
                ),
                ("location", models.CharField(blank=True, max_length=255)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patient_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
