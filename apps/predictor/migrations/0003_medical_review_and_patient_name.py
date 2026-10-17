from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0002_predictionrecord_session_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionrecord",
            name="patient_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("appointment_planned", "Appointment Planned"),
                    ("reviewed", "Reviewed"),
                ],
                db_index=True,
                default="pending",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="review_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="predictionrecord",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    (
                        "view_medical_priority_queue",
                        "Can access and manage the medical follow-up queue",
                    )
                ],
            },
        ),
    ]
