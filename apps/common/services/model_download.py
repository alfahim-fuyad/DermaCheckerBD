"""Download the configured Keras model from a public Google Drive link."""
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def download_model_if_missing():
    """Download the model atomically when a Drive URL is configured.

    The temporary file is created beside the destination so os.replace remains
    atomic. Existing model files are left untouched if a download fails.
    """
    model_path = Path(settings.ML_MODEL_PATH)
    if model_path.is_file():
        return model_path

    drive_url = settings.MODEL_GDRIVE_URL
    if not drive_url:
        return None

    model_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{model_path.name}.",
        suffix=".download",
        dir=model_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        import gdown

        downloaded_path = gdown.download(
            url=drive_url,
            output=str(temporary_path),
            quiet=True,
            fuzzy=True,
        )
        if not downloaded_path or not temporary_path.is_file():
            raise RuntimeError(
                "Google Drive did not return a model file. Check that the link "
                "is public and points directly to the model."
            )
        if temporary_path.stat().st_size == 0:
            raise RuntimeError("Google Drive returned an empty model file.")
        if model_path.suffix.lower() == ".keras" and not zipfile.is_zipfile(
            temporary_path
        ):
            raise RuntimeError(
                "The downloaded file is not a valid .keras archive. "
                "Check that the Drive link points to the model file."
            )

        os.replace(temporary_path, model_path)
        logger.info(
            "Downloaded Keras model to %s (%d bytes).",
            model_path,
            model_path.stat().st_size,
        )
        return model_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
