"""Add session_key to PredictionRecord for anonymous (signed-out) records.

This lets anonymous visitors see, delete, and re-open their own past
predictions without an account, scoped to their Django session. Existing
records have session_key='' (empty), which is treated as "no session" —
they remain readable only via direct reference_id URL (link-only access).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionrecord",
            name="session_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Session key for anonymous records. Empty when user is set.",
                max_length=64,
            ),
        ),
        migrations.AddIndex(
            model_name="predictionrecord",
            index=models.Index(
                fields=["session_key", "-created_at"],
                name="predictor_p_session_5b1c2a_idx",
            ),
        ),
    ]
