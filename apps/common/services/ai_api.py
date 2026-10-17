"""FastAPI prediction client.

When ``settings.ML_MODEL_BACKEND == "api"`` the Django prediction service
forwards every uploaded image to a FastAPI service (running ResNet50 in a
separate process) instead of loading TensorFlow in-process.

Contract with the FastAPI service
---------------------------------
- Endpoint: ``POST {AI_API_URL}/predict``
- Multipart form field: ``file``  (a single image)
- Optional auth: bearer token via ``AI_API_TOKEN``
- Response JSON shape::

    {
      "success": true,
      "predicted_class": "mel",         # one of HAM10000 codes
      "confidence": 0.8723,             # float in [0, 1]
      "probabilities": {                # all 7 HAM10000 classes
        "akiec": 0.0123,
        "bcc":   0.0456,
        "bkl":   0.0789,
        "df":    0.0011,
        "mel":   0.8723,
        "nv":    0.0312,
        "vasc":  0.0006
      }
    }

On failure the service may return ``{"success": false, "error": "..."}`` or
a non-2xx status code; both are translated to :class:`PredictionError`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import requests
from django.conf import settings

from apps.common.services.prediction import PredictionError

logger = logging.getLogger(__name__)


def predict_skin_image(image_file) -> Dict[str, Any]:
    """Forward an uploaded image to the FastAPI prediction service.

    Args:
        image_file: any file-like object with ``.read()``, optionally
            exposing ``.name`` and ``.content_type`` (a Django
            ``UploadedFile`` qualifies, as does a wrapped ``io.BytesIO``).

    Returns:
        The parsed JSON response from FastAPI. Always contains
        ``success=True`` and a ``probabilities`` dict on the happy path.

    Raises:
        PredictionError: on any network failure, non-2xx response, or
            ``success=False`` payload from the FastAPI service.
    """
    url = f"{settings.AI_API_URL.rstrip('/')}/predict"

    # Rewind to start so the same file object can be re-used by other
    # services (quality check, wrong-input check) before/after this call.
    try:
        image_file.seek(0)
    except Exception:
        # Some file-like objects don't support seek; that's fine, the
        # caller is responsible for handing us a fresh-readable object.
        pass

    files = {
        "file": (
            getattr(image_file, "name", "skin_image.jpg") or "skin_image.jpg",
            image_file,
            getattr(image_file, "content_type", "image/jpeg") or "image/jpeg",
        )
    }

    headers: Dict[str, str] = {}
    if getattr(settings, "AI_API_TOKEN", "").strip():
        headers["Authorization"] = f"Bearer {settings.AI_API_TOKEN.strip()}"

    try:
        response = requests.post(
            url,
            files=files,
            headers=headers or None,
            timeout=getattr(settings, "AI_API_TIMEOUT", 120),
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("FastAPI /predict timed out: %s", exc)
        raise PredictionError(
            "The prediction service did not respond in time. Please try again."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("FastAPI /predict connection error: %s", exc)
        raise PredictionError(
            "Could not reach the prediction service. Please try again later."
        ) from exc
    except requests.exceptions.RequestException as exc:
        logger.warning("FastAPI /predict request failed: %s", exc)
        raise PredictionError(
            "The prediction service could not be contacted."
        ) from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        # Try to surface the upstream error message if present.
        try:
            payload = response.json()
            upstream_msg = (payload or {}).get("error") or (payload or {}).get("detail")
        except ValueError:
            upstream_msg = None
        logger.warning("FastAPI /predict returned %s: %s", response.status_code, upstream_msg or exc)
        raise PredictionError(
            upstream_msg or "The prediction service returned an error."
        ) from exc

    try:
        result = response.json()
    except ValueError as exc:
        logger.warning("FastAPI /predict returned non-JSON body: %r", response.text[:200])
        raise PredictionError(
            "The prediction service returned an invalid response."
        ) from exc

    if not result.get("success"):
        upstream_msg = result.get("error") or "Prediction failed on the FastAPI side."
        logger.warning("FastAPI /predict returned success=False: %s", upstream_msg)
        raise PredictionError(upstream_msg)

    # Validate the minimum required fields so the caller can rely on the
    # shape without re-checking.
    if "probabilities" not in result or not isinstance(result["probabilities"], dict):
        logger.warning("FastAPI /predict missing 'probabilities' dict: %r", result)
        raise PredictionError(
            "The prediction service returned an incomplete response."
        )

    return result
