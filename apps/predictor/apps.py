from django.apps import AppConfig
from django.db import models


class PredictorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.predictor"
    label = "predictor"
