"""
PredictionService: pluggable skin-lesion classifier.

Backends:
- 'keras' (default): the supplied fine-tuned ResNet50 Keras model.
- 'mock': deterministic hash-based probabilities over the 7 HAM10000 classes.
  Used when no real model weights are available. Same input -> same output, so the
  AI Reliability Check can be meaningfully demonstrated.
- 'onnx': load an ONNX model (requires onnxruntime; not bundled).

The model is loaded once per process, on its first prediction, and reused for
every request — never reloaded per request.
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from django.conf import settings

logger = logging.getLogger(__name__)


def confidence_to_fraction(value) -> float:
    """Normalize decimal (0..1) and percentage (0..100) confidence values.

    A string with a percent sign is always treated as a percentage; otherwise
    values greater than 1 are interpreted as percentages. The result is
    clamped to the model-confidence range.
    """
    is_percentage = isinstance(value, str) and value.strip().endswith("%")
    raw = value.strip()[:-1].strip() if is_percentage else value
    confidence = float(raw)
    if not math.isfinite(confidence):
        raise ValueError("Confidence must be a finite number.")
    if is_percentage or abs(confidence) > 1:
        confidence /= 100.0
    return min(1.0, max(0.0, confidence))


# --- Class metadata ---

CLASS_NAMES: Dict[str, str] = settings.HAM10000_CLASS_NAMES
CLASS_CATEGORIES: Dict[str, str] = settings.HAM10000_CLASS_CATEGORY
CLASS_ORDER: List[str] = settings.ML_MODEL_CLASSES  # must match the trained model's output order


@dataclass(frozen=True)
class PredictionResult:
    """Immutable single-image prediction output."""

    predicted_class: str  # short code, e.g. 'mel'
    predicted_name: str   # full medical name
    category: str         # 'benign' | 'malignant' | 'pre malignant'
    confidence: float     # max softmax probability, 0..1
    probabilities: Dict[str, float] = field(default_factory=dict)
    backend: str = "mock"
    image_quality_score: Optional[float] = None  # populated by caller if available
    input_size: int = 224

    def as_dict(self) -> dict:
        return {
            "predicted_class": self.predicted_class,
            "predicted_name": self.predicted_name,
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "backend": self.backend,
            "input_size": self.input_size,
        }


# --- Exceptions ---

class PredictionError(Exception):
    """Raised when the model cannot produce a prediction."""


class ModelNotLoadedError(PredictionError):
    pass


class InvalidImageError(PredictionError):
    pass


# --- Preprocessing ---

def preprocess_image(image: Image.Image, target_size: Optional[int] = None) -> np.ndarray:
    """
    Preprocess a PIL image for the model.

    - Converts to RGB.
    - Resizes to (target_size, target_size) using ML_MODEL_RESAMPLE.
    - Scales pixel values to [0, 1] for the mock backend and shared utilities.
      The Keras backend restores [0, 255] before applying ResNet50 preprocessing.
    - Returns a (target_size, target_size, 3) float32 numpy array.
    """
    if target_size is None:
        target_size = settings.ML_MODEL_INPUT_SIZE

    if image is None:
        raise InvalidImageError("Image is None")
    try:
        image = image.convert("RGB")
    except Exception as e:
        raise InvalidImageError(f"Could not convert image to RGB: {e}") from e

    if image.size[0] < 16 or image.size[1] < 16:
        raise InvalidImageError(
            f"Image dimensions {image.size} too small (minimum 16x16)."
        )

    resampling = {
        "NEAREST": Image.Resampling.NEAREST,
        "BILINEAR": Image.Resampling.BILINEAR,
        "BICUBIC": Image.Resampling.BICUBIC,
        "LANCZOS": Image.Resampling.LANCZOS,
    }
    resample_name = settings.ML_MODEL_RESAMPLE.upper()
    if resample_name not in resampling:
        raise ModelNotLoadedError(
            f"Unsupported ML_MODEL_RESAMPLE={settings.ML_MODEL_RESAMPLE!r}; "
            f"choose one of {', '.join(resampling)}."
        )
    image = image.resize((target_size, target_size), resampling[resample_name])
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return arr


# --- Backend implementations ---

class _MockBackend:
    """
    Deterministic mock backend.

    Hashes the pixel content to produce a stable per-image probability vector,
    so the same image always yields the same prediction. This lets the AI
    Reliability Check feature show meaningful stability behaviour on mildly
    transformed images (some transforms flip the top class, others don't).

    IMPORTANT: This is NOT a real classifier. Do not treat outputs as medical
    truth. The mock exists purely to make the surrounding application testable
    end-to-end while real weights are unavailable.
    """

    backend_name = "mock"

    def predict(self, arr: np.ndarray) -> Dict[str, float]:
        # Build a deterministic hash from a coarse summary of the array.
        # Coarse so that mild transforms change the hash slightly (and therefore
        # may flip a close-call prediction), but the same image is bit-for-bit
        # identical.
        h = hashlib.sha1(arr.tobytes()).digest()
        # Use the first 7 bytes of the hash to seed per-class logit noise.
        seeds = list(h[:7])
        # Build a class-aligned prior that favors 'nv' (most common class in HAM10000)
        # plus image-dependent noise on top.
        base_logits = np.array(
            [-0.4, -0.2, -0.1, -1.2, 0.2, 1.6, -1.0],  # nv is biased high
            dtype=np.float32,
        )
        noise = np.array([(b - 128) / 128.0 for b in seeds], dtype=np.float32) * 1.2
        logits = base_logits + noise
        # Softmax with temperature 0.6 to make confidences more peaked (and
        # therefore sensitive to small input changes — which is what we want
        # for a demo of stability checks).
        t = 0.6
        z = logits / t
        z = z - z.max()
        exp = np.exp(z)
        probs = exp / exp.sum()
        out = {klass: float(p) for klass, p in zip(CLASS_ORDER, probs)}
        return out


class _KerasBackend:
    """CPU inference backend for the supplied fine-tuned ResNet50 Keras model."""
    backend_name = "keras"

    def __init__(self, model_path: str):
        path = Path(model_path)
        if not path.is_file():
            logger.error("Keras prediction model is missing: %s", path)
            raise ModelNotLoadedError(
                "The prediction model is unavailable. Please try again later."
            )

        try:
            import tensorflow as tf
        except Exception as exc:
            logger.exception("TensorFlow could not be imported for prediction.")
            raise ModelNotLoadedError(
                "The prediction service is unavailable. Please try again later."
            ) from exc

        try:
            self.model = tf.keras.models.load_model(str(path), compile=False)
        except Exception as exc:
            logger.exception("Could not load the configured Keras prediction model.")
            raise ModelNotLoadedError(
                "The prediction model could not be loaded. Please try again later."
            ) from exc

        expected_dim = settings.ML_MODEL_INPUT_SIZE
        input_shape = self.model.input_shape
        if isinstance(input_shape, list):
            if len(input_shape) != 1:
                raise ModelNotLoadedError(
                    "The prediction model must have one image input."
                )
            input_shape = input_shape[0]
        input_shape = tuple(input_shape)
        expected_input_shape = (None, expected_dim, expected_dim, 3)
        if len(input_shape) != 4 or any(
            actual is not None and actual != expected
            for actual, expected in zip(input_shape, expected_input_shape)
        ):
            logger.error(
                "Keras model input shape %s does not match expected %s.",
                input_shape,
                expected_input_shape,
            )
            raise ModelNotLoadedError(
                "The prediction model has an incompatible image input shape."
            )

        output_shape = self.model.output_shape
        if isinstance(output_shape, list):
            if len(output_shape) != 1:
                raise ModelNotLoadedError(
                    "The prediction model must have one classification output."
                )
            output_shape = output_shape[0]
        output_shape = tuple(output_shape)
        if len(output_shape) != 2 or output_shape[-1] != len(CLASS_ORDER):
            logger.error(
                "Keras model output shape %s does not match %d classes.",
                output_shape,
                len(CLASS_ORDER),
            )
            raise ModelNotLoadedError(
                "The prediction model does not match the configured classes."
            )

        self.preprocess_input = tf.keras.applications.resnet50.preprocess_input

    def predict(self, arr: np.ndarray) -> Dict[str, float]:
        # preprocess_image returns [0, 1]; Keras ResNet50 preprocess_input
        # expects RGB pixels in [0, 255] and converts them to BGR mean-centered
        # values internally.
        try:
            pixels = np.asarray(arr, dtype=np.float32) * 255.0
            batch = self.preprocess_input(np.expand_dims(pixels, axis=0))
            predictions = self.model(batch, training=False)
            if hasattr(predictions, "numpy"):
                predictions = predictions.numpy()
            predictions = np.asarray(predictions, dtype=np.float32)
        except Exception as exc:
            logger.exception("Keras prediction inference failed.")
            raise PredictionError(
                "The prediction service could not process this image."
            ) from exc

        if predictions.shape != (1, len(CLASS_ORDER)):
            logger.error(
                "Keras model returned output shape %s; expected (1, %d).",
                predictions.shape,
                len(CLASS_ORDER),
            )
            raise PredictionError(
                "The prediction service returned an invalid result."
            )
        probabilities = predictions[0]
        if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
            raise PredictionError(
                "The prediction service returned an invalid result."
            )
        total = float(probabilities.sum())
        if total <= 0:
            raise PredictionError(
                "The prediction service returned an invalid result."
            )
        probabilities = probabilities / total
        return {
            klass: float(probability)
            for klass, probability in zip(CLASS_ORDER, probabilities)
        }


class _ONNXBackend:
    """TODO: implement when user provides an ONNX model."""
    backend_name = "onnx"

    def __init__(self, model_path: str):
        raise NotImplementedError(
            "ONNX backend is stubbed. Install onnxruntime, drop your .onnx at "
            "ML_MODEL_PATH, and implement apps/common/services/prediction.py "
            "_ONNXBackend.predict to wire it in."
        )

    def predict(self, arr: np.ndarray) -> Dict[str, float]:  # pragma: no cover
        raise NotImplementedError


class _NamedBytesIO(io.BytesIO):
    """A BytesIO that exposes ``.name`` and ``.content_type`` so the
    FastAPI client (which uses ``requests`` multipart) can build a sane
    filename and Content-Type header without crashing.

    Plain ``io.BytesIO`` lacks both attributes; ``requests`` would fall
    back to ``filename=None`` and ``application/octet-stream``, which some
    FastAPI servers reject when validating the upload.
    """

    def __init__(self, *args, name: str = "image.jpg",
                 content_type: str = "image/jpeg", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.name = name
        self.content_type = content_type


class _APIBackend:
    """Forwards every prediction request to an external FastAPI service.

    Unlike the keras / mock / onnx backends, this one does NOT call
    :func:`preprocess_image` itself — the FastAPI service is expected to do
    its own preprocessing (RGB conversion, resize to 224x224, normalise).

    The backend accepts either a file-like object (preferred — zero copy)
    via :meth:`predict_file`, or a numpy array (used by the reliability
    check, which produces variants in-memory) via :meth:`predict`. In the
    array path we re-encode to JPEG before forwarding.

    IMPORTANT: this backend returns the FULL parsed API response dict, not
    just the probabilities. The caller (:meth:`PredictionService.predict_pil`
    etc.) uses :meth:`PredictionService._build_api_result` to preserve the
    API's own ``predicted_class``, ``confidence``, and ``backend`` fields
    verbatim — never normalised, recomputed, or fabricated.
    """
    backend_name = "api"

    def __init__(self) -> None:
        # Import lazily so Django check / migrate can run even if
        # `requests` is not yet installed (helpful for first-time setup).
        try:
            import requests  # noqa: F401
        except ImportError as exc:  # pragma: no cover - environment issue
            raise ModelNotLoadedError(
                "ML_MODEL_BACKEND=api requires the `requests` package. "
                "Run: pip install requests"
            ) from exc
        if not getattr(settings, "AI_API_URL", "").strip():
            raise ModelNotLoadedError(
                "ML_MODEL_BACKEND=api but AI_API_URL is not configured."
            )

    def predict_file(self, image_file) -> dict:
        """Forward a raw uploaded file to FastAPI and return the FULL parsed
        API response dict (with ``success``, ``predicted_class``,
        ``confidence``, ``probabilities``, ``backend``, ``input_size``).

        ``image_file`` must be a file-like object supporting ``.read()``;
        optional ``.name`` and ``.content_type`` attributes are forwarded
        to the multipart upload.
        """
        from apps.common.services.ai_api import predict_skin_image
        result = predict_skin_image(image_file)
        # Validate the bare minimum shape. Normalisation of probabilities
        # is intentionally NOT done here — the API response is preserved
        # verbatim so the result page shows exactly what FastAPI returned.
        if "probabilities" not in result or not isinstance(result["probabilities"], dict):
            raise PredictionError(
                "The prediction service returned an incomplete response."
            )
        return result

    def predict(self, arr: np.ndarray) -> dict:
        """Forward a preprocessed (target_size, target_size, 3) float array
        in [0, 1] to FastAPI by re-encoding it as JPEG.

        Used by the reliability check, which generates mild image variants
        in-memory and calls predict_pil on each.
        """
        pixels = (np.asarray(arr, dtype=np.float32) * 255.0).clip(0, 255).astype(np.uint8)
        pil = Image.fromarray(pixels, mode="RGB")
        buf = _NamedBytesIO(name="reliability_variant.jpg", content_type="image/jpeg")
        pil.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        return self.predict_file(buf)


# --- Public service ---

class PredictionService:
    """
    Singleton-ish service used by all prediction-related views.

    The backend is selected by settings.ML_MODEL_BACKEND.
    The backend instance is built lazily once and cached on the class.
    """

    _backend = None
    _backend_name = None
    _backend_error = None
    _backend_lock = threading.Lock()

    @classmethod
    def _resolve_backend(cls):
        if cls._backend is not None:
            return cls._backend
        if cls._backend_error is not None:
            raise ModelNotLoadedError(cls._backend_error)
        with cls._backend_lock:
            if cls._backend is not None:
                return cls._backend
            if cls._backend_error is not None:
                raise ModelNotLoadedError(cls._backend_error)
            backend_choice = settings.ML_MODEL_BACKEND.lower()
            try:
                if backend_choice == "mock":
                    cls._backend = _MockBackend()
                    cls._backend_name = "mock"
                elif backend_choice == "keras":
                    if not settings.ML_MODEL_PATH:
                        raise ModelNotLoadedError(
                            "The prediction model is unavailable. Please try again later."
                        )
                    cls._backend = _KerasBackend(settings.ML_MODEL_PATH)
                    cls._backend_name = "keras"
                elif backend_choice == "onnx":
                    if not settings.ML_MODEL_PATH:
                        raise ModelNotLoadedError(
                            "ML_MODEL_BACKEND=onnx but ML_MODEL_PATH is empty."
                        )
                    cls._backend = _ONNXBackend(settings.ML_MODEL_PATH)
                    cls._backend_name = "onnx"
                elif backend_choice == "api":
                    # Forward predictions to a FastAPI service.
                    # See apps/common/services/ai_api.py for the wire contract.
                    cls._backend = _APIBackend()
                    cls._backend_name = "api"
                else:
                    raise ModelNotLoadedError(
                        f"Unknown ML_MODEL_BACKEND={backend_choice!r}"
                    )
            except ModelNotLoadedError as exc:
                cls._backend_error = str(exc)
                raise
            logger.info("PredictionService using backend=%s", cls._backend_name)
            return cls._backend

    @classmethod
    def reset(cls):
        """Force re-resolution on next call. Used by tests."""
        with cls._backend_lock:
            cls._backend = None
            cls._backend_name = None
            cls._backend_error = None

    @classmethod
    def predict_pil(cls, image: Image.Image) -> PredictionResult:
        """Run a prediction on a PIL image.

        For the ``keras`` / ``mock`` / ``onnx`` backends this preprocesses
        the image locally and calls ``backend.predict(arr)``, then builds
        a result via :meth:`_build_result` (which normalises probabilities).

        For the ``api`` backend the image is re-encoded as JPEG and
        forwarded to FastAPI (which does its own preprocessing). The local
        preprocess step is skipped so the FastAPI server sees the
        original pixels. The result is built via :meth:`_build_api_result`
        which preserves the API's own ``predicted_class``, ``confidence``,
        ``backend``, and ``input_size`` VERBATIM — never normalised or
        recomputed.
        """
        backend = cls._resolve_backend()
        if isinstance(backend, _APIBackend):
            # FastAPI does its own preprocessing — send JPEG bytes directly.
            buf = _NamedBytesIO(name="image.jpg", content_type="image/jpeg")
            try:
                image.convert("RGB").save(buf, format="JPEG", quality=95)
            except Exception as exc:
                raise InvalidImageError(f"Could not encode image for API: {exc}") from exc
            buf.seek(0)
            api_response = backend.predict_file(buf)
            return cls._build_api_result(api_response)
        arr = preprocess_image(image)
        probs = backend.predict(arr)
        return cls._build_result(probs, backend.backend_name)

    @classmethod
    def predict_uploaded(cls, uploaded) -> PredictionResult:
        """Run a prediction on a Django UploadedFile (or any file-like
        object with ``.read()``).

        For the ``api`` backend the file is forwarded as-is to FastAPI —
        no local PIL round-trip, no preprocessing, no re-encoding. This is
        the most efficient path when the real model lives in FastAPI, and
        it guarantees the bytes FastAPI sees are the bytes the user
        uploaded (so the prediction matches what FastAPI's Swagger UI
        returns for the same image).

        For other backends the file is opened as a PIL image and
        :meth:`predict_pil` is called.
        """
        backend = cls._resolve_backend()
        if isinstance(backend, _APIBackend):
            api_response = backend.predict_file(uploaded)
            return cls._build_api_result(api_response)
        # Local backends: open as PIL.
        try:
            data = uploaded.read() if hasattr(uploaded, "read") else bytes(uploaded)
        except Exception as exc:
            raise InvalidImageError(f"Could not read uploaded file: {exc}") from exc
        try:
            image = Image.open(io.BytesIO(data))
        except Exception as exc:
            raise InvalidImageError(f"Could not open image bytes: {exc}") from exc
        return cls.predict_pil(image)

    @classmethod
    def predict_bytes(cls, image_bytes: bytes) -> PredictionResult:
        """Run a prediction on raw image bytes."""
        backend = cls._resolve_backend()
        if isinstance(backend, _APIBackend):
            buf = _NamedBytesIO(
                initial_bytes=image_bytes,
                name="image.jpg",
                content_type="image/jpeg",
            )
            buf.seek(0)
            api_response = backend.predict_file(buf)
            return cls._build_api_result(api_response)
        try:
            image = Image.open(io.BytesIO(image_bytes))
        except Exception as exc:
            raise InvalidImageError(f"Could not open image bytes: {exc}") from exc
        return cls.predict_pil(image)

    @classmethod
    def predict_path(cls, path: str | Path) -> PredictionResult:
        """Run a prediction on an image file path."""
        path = Path(path)
        if not path.exists():
            raise InvalidImageError(f"Image file does not exist: {path}")
        try:
            image = Image.open(path)
        except Exception as e:
            raise InvalidImageError(f"Could not open image {path}: {e}") from e
        return cls.predict_pil(image)

    @staticmethod
    def _build_result(probs: Dict[str, float], backend_name: str) -> PredictionResult:
        """Build a PredictionResult from LOCAL backends (mock / keras / onnx).

        These backends return only the probabilities dict, so we have to
        compute ``predicted_class`` (argmax) and ``confidence`` (max prob)
        ourselves. Probabilities are renormalised in case of float drift
        so they always sum to exactly 1.0.
        """
        # Always normalize to the canonical class order so downstream code can
        # rely on iteration order.
        ordered = {k: float(probs.get(k, 0.0)) for k in CLASS_ORDER}
        # Renormalize in case of float drift.
        total = sum(ordered.values()) or 1.0
        ordered = {k: v / total for k, v in ordered.items()}
        predicted_class = max(ordered, key=ordered.get)
        return PredictionResult(
            predicted_class=predicted_class,
            predicted_name=CLASS_NAMES.get(predicted_class, predicted_class),
            category=CLASS_CATEGORIES.get(predicted_class, "unknown"),
            confidence=ordered[predicted_class],
            probabilities=ordered,
            backend=backend_name,
            input_size=settings.ML_MODEL_INPUT_SIZE,
        )

    @staticmethod
    def _build_api_result(api_response: dict) -> PredictionResult:
        """Build a PredictionResult from a FastAPI /predict response.

        CRITICAL CONTRACT
        -----------------
        The API response fields ``predicted_class``, ``probabilities``,
        ``backend``, and ``input_size`` are preserved. Confidence is normalized
        to the service's canonical 0..1 representation. We do NOT:
        - renormalise the probabilities (the API's softmax output is
          already normal; renormalising can change displayed values due
          to float drift)
        - recompute ``predicted_class`` from ``argmax(probabilities)``
          (the API's own top class is authoritative — it reflects the
          model's actual argmax before any rounding/serialisation)
        - recompute ``confidence`` from the probabilities dict (the API's
          ``confidence`` field is the source of truth)

        We DO run a sanity check: if the API's ``predicted_class`` is not
        the argmax of its ``probabilities`` dict, we log a warning. This
        is a signal that the API itself returned an inconsistent payload
        — we surface the API's ``predicted_class`` as-is (the user asked
        us to flag, not silently alter).
        """
        if not isinstance(api_response, dict):
            raise PredictionError("The prediction service returned an invalid response.")

        # --- Probabilities: preserve verbatim, but ensure canonical order ---
        raw_probs = api_response.get("probabilities") or {}
        if not isinstance(raw_probs, dict):
            raise PredictionError(
                "The prediction service returned an invalid probabilities field."
            )
        # Build an ordered dict over CLASS_ORDER. Missing classes default
        # to 0.0 (defensive — the API should return all 7, but if it
        # omits one we show 0.0 instead of crashing). Unknown class
        # codes (not in CLASS_ORDER) are silently dropped.
        probabilities = {k: float(raw_probs.get(k, 0.0)) for k in CLASS_ORDER}

        # --- predicted_class: trust the API verbatim ---
        predicted_class = str(api_response.get("predicted_class") or "").strip().lower()
        if predicted_class not in CLASS_ORDER:
            # The API returned an unknown class code. We cannot map it to
            # a name or category, so this is a hard error (not a silent
            # fallback) — the user should see "could not process this
            # image" rather than a fabricated prediction.
            raise PredictionError(
                f"The prediction service returned an unknown class: "
                f"{predicted_class!r}. Expected one of {CLASS_ORDER}."
            )

        # --- confidence: preserve the API value while normalizing its unit ---
        confidence_raw = api_response.get("confidence")
        try:
            confidence = confidence_to_fraction(confidence_raw)
        except (TypeError, ValueError):
            # If the API omits confidence, fall back to the probability
            # of the predicted class in the probabilities dict. We log
            # this so it's visible but not silently fabricated.
            logger.warning(
                "API response missing valid 'confidence'; falling back to "
                "probabilities[%s] = %s",
                predicted_class, probabilities.get(predicted_class),
            )
            confidence = confidence_to_fraction(
                probabilities.get(predicted_class, 0.0)
            )

        # --- backend: trust the API verbatim ---
        # The API returns e.g. "keras" (the real backend that ran
        # inference), NOT "api" (our forwarder). This is what we display
        # on the result page so the user knows which model produced the
        # prediction.
        api_backend = str(api_response.get("backend") or "").strip().lower() or "api"

        # --- input_size: trust the API verbatim ---
        try:
            input_size = int(api_response.get("input_size") or settings.ML_MODEL_INPUT_SIZE)
        except (TypeError, ValueError):
            input_size = settings.ML_MODEL_INPUT_SIZE

        # --- Consistency check: flag (do NOT silently fix) mismatches ---
        argmax_class = max(probabilities, key=probabilities.get)
        if argmax_class != predicted_class:
            logger.warning(
                "API consistency warning: predicted_class=%s but "
                "argmax(probabilities)=%s (probabilities=%s, confidence=%s). "
                "Surfacing the API's predicted_class as-is.",
                predicted_class, argmax_class, probabilities, confidence,
            )

        return PredictionResult(
            predicted_class=predicted_class,
            predicted_name=CLASS_NAMES.get(predicted_class, predicted_class),
            category=CLASS_CATEGORIES.get(predicted_class, "unknown"),
            confidence=confidence,
            probabilities=probabilities,
            backend=api_backend,
            input_size=input_size,
        )

    @staticmethod
    def class_metadata() -> list:
        """Return a list of (code, full_name, category) for display."""
        return [
            {
                "code": c,
                "name": CLASS_NAMES.get(c, c),
                "category": CLASS_CATEGORIES.get(c, "unknown"),
            }
            for c in CLASS_ORDER
        ]
