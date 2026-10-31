from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("predictor", "0005_remove_predictionrecord_model_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="predictionrecord",
            name="image_type",
            field=models.CharField(
                choices=[("dermoscopic", "Dermoscopic (HAM10000)"), ("phone", "Phone Image (SkinDisNet)")],
                db_index=True,
                default="dermoscopic",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="model_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="model_version",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="patient_age",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="patient_sex",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="predictionrecord",
            name="lesion_location",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
