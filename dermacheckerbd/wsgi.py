"""WSGI config for dermacheckerbd."""
import os
import logging
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dermacheckerbd.settings")
application = get_wsgi_application()

from django.conf import settings

if settings.ML_MODEL_BACKEND.lower() == "keras":
    from apps.common.services.prediction import ModelNotLoadedError, PredictionService

    try:
        from apps.common.services.model_download import download_model_if_missing

        download_model_if_missing()
        PredictionService._resolve_backend()
    except ModelNotLoadedError as exc:
        logging.getLogger(__name__).error(
            "Prediction model unavailable at startup (%s). The website will stay "
            "available, but image predictions will remain unavailable until the "
            "model file and ML_MODEL_PATH are configured.",
            exc,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Prediction model setup failed at startup. The website will stay "
            "available, but image predictions will remain unavailable until the "
            "model download and ML_MODEL_PATH are configured."
        )
