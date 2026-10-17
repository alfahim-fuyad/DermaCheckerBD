"""Tests for the prediction service (mock backend)."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from django.test import TestCase, override_settings

from apps.common.services.prediction import (
    PredictionService, PredictionResult, PredictionError, InvalidImageError, CLASS_ORDER,
    confidence_to_fraction,
)
from apps.common.services.image_quality import ImageQualityService
from apps.common.services.reliability import ReliabilityService
from apps.common.services.multi_image import MultiImageService
from apps.common.services.wrong_input import WrongInputService
from apps.common.services.gemini import GeminiService

from tests._helpers import make_skin_image


@override_settings(ML_MODEL_BACKEND="mock")
class PredictionServiceTests(TestCase):
    def setUp(self):
        PredictionService.reset()

    def test_class_order_is_ham10000(self):
        self.assertEqual(CLASS_ORDER, ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"])

    def test_predict_pil_returns_result(self):
        img = make_skin_image(seed=1)
        result = PredictionService.predict_pil(img)
        self.assertIsInstance(result, PredictionResult)
        self.assertIn(result.predicted_class, CLASS_ORDER)
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        self.assertEqual(len(result.probabilities), 7)
        # Probabilities should sum to ~1.0
        total = sum(result.probabilities.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_predict_same_input_same_output(self):
        """The mock backend is deterministic — same image = same output."""
        img = make_skin_image(seed=2)
        r1 = PredictionService.predict_pil(img)
        r2 = PredictionService.predict_pil(img)
        self.assertEqual(r1.predicted_class, r2.predicted_class)
        self.assertEqual(r1.confidence, r2.confidence)

    def test_class_metadata_returns_seven_classes(self):
        meta = PredictionService.class_metadata()
        self.assertEqual(len(meta), 7)
        codes = {m["code"] for m in meta}
        self.assertEqual(codes, set(CLASS_ORDER))

    def test_confidence_accepts_decimal_and_percentage_formats(self):
        for raw, expected in (
            (0.42, 0.42),
            ("0.42", 0.42),
            (42, 0.42),
            ("42%", 0.42),
            (100, 1.0),
        ):
            with self.subTest(raw=raw):
                self.assertAlmostEqual(confidence_to_fraction(raw), expected)

    def test_api_prediction_normalizes_percentage_confidence(self):
        probabilities = {code: 0.1 for code in CLASS_ORDER}
        probabilities["nv"] = 0.4
        result = PredictionService._build_api_result({
            "predicted_class": "nv",
            "confidence": "42%",
            "probabilities": probabilities,
        })
        self.assertAlmostEqual(result.confidence, 0.42)


@override_settings(ML_MODEL_BACKEND="keras", ML_MODEL_INPUT_SIZE=224)
class KerasModelIntegrationTests(TestCase):
    def setUp(self):
        PredictionService.reset()

    def tearDown(self):
        PredictionService.reset()

    def test_keras_model_loads_once_and_receives_resnet50_preprocessing(self):
        loaded_model = Mock()
        loaded_model.input_shape = (None, 224, 224, 3)
        loaded_model.output_shape = (None, 7)
        loaded_model.return_value = np.array(
            [[0.01, 0.02, 0.03, 0.04, 0.15, 0.70, 0.05]],
            dtype=np.float32,
        )
        preprocessed_batches = []

        def preprocess_input(batch):
            preprocessed_batches.append(batch.copy())
            return batch

        load_model = Mock(return_value=loaded_model)
        fake_tf = SimpleNamespace(
            keras=SimpleNamespace(
                models=SimpleNamespace(load_model=load_model),
                applications=SimpleNamespace(
                    resnet50=SimpleNamespace(preprocess_input=preprocess_input)
                ),
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "resnet50_finetuned.keras"
            model_path.touch()
            with patch.dict(sys.modules, {"tensorflow": fake_tf}):
                with override_settings(ML_MODEL_PATH=str(model_path)):
                    image = make_skin_image(seed=99)
                    result = PredictionService.predict_pil(image)
                    again = PredictionService.predict_pil(image)

        self.assertEqual(result.backend, "keras")
        self.assertEqual(result.predicted_class, "nv")
        self.assertEqual(set(result.probabilities), set(CLASS_ORDER))
        self.assertAlmostEqual(sum(result.probabilities.values()), 1.0, places=5)
        self.assertEqual(again.probabilities, result.probabilities)
        load_model.assert_called_once_with(str(model_path), compile=False)
        self.assertEqual(len(preprocessed_batches), 2)
        self.assertEqual(preprocessed_batches[0].shape, (1, 224, 224, 3))
        self.assertGreater(float(preprocessed_batches[0].max()), 1.0)
        self.assertLessEqual(float(preprocessed_batches[0].max()), 255.0)


class ModelDownloadTests(TestCase):
    def test_downloads_public_drive_model_to_configured_path(self):
        import zipfile

        from apps.common.services.model_download import download_model_if_missing

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "resnet50_finetuned.keras"
            source_path = Path(temp_dir) / "source.keras"
            with zipfile.ZipFile(source_path, "w") as archive:
                archive.writestr("config.json", "{}")

            def fake_download(*, url, output, quiet, fuzzy):
                Path(output).write_bytes(source_path.read_bytes())
                return output

            fake_gdown = SimpleNamespace(download=fake_download)
            with patch.dict(sys.modules, {"gdown": fake_gdown}):
                with override_settings(
                    ML_MODEL_PATH=str(model_path),
                    MODEL_GDRIVE_URL="https://drive.google.com/file/d/example/view",
                ):
                    result = download_model_if_missing()

            self.assertEqual(result, model_path)
            self.assertEqual(model_path.read_bytes(), source_path.read_bytes())

    def test_existing_model_skips_drive_download(self):
        from apps.common.services.model_download import download_model_if_missing

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "resnet50_finetuned.keras"
            model_path.write_bytes(b"already downloaded")
            fake_gdown = SimpleNamespace(download=Mock())
            with patch.dict(sys.modules, {"gdown": fake_gdown}):
                with override_settings(
                    ML_MODEL_PATH=str(model_path),
                    MODEL_GDRIVE_URL="https://drive.google.com/file/d/example/view",
                ):
                    result = download_model_if_missing()

            self.assertEqual(result, model_path)
            fake_gdown.download.assert_not_called()


class ImageQualityServiceTests(TestCase):
    def test_assess_good_image(self):
        img = make_skin_image(seed=42, size=(400, 400))
        report = ImageQualityService.assess_pil(img)
        self.assertTrue(report.suitable, msg=f"Expected suitable; checks: {[c.as_dict() if hasattr(c,'as_dict') else c for c in report.checks]}")
        self.assertGreater(report.overall_score, 80.0)
        # Skin-plausibility should pass
        skin_check = next(c for c in report.checks if c.name == "skin_plausibility")
        self.assertTrue(skin_check.passed)

    def test_assess_tiny_image_fails_resolution(self):
        img = make_skin_image(seed=1, size=(32, 32))
        report = ImageQualityService.assess_pil(img)
        res_check = next(c for c in report.checks if c.name == "resolution")
        self.assertFalse(res_check.passed)


@override_settings(ML_MODEL_BACKEND="mock")
class ReliabilityServiceTests(TestCase):
    def setUp(self):
        PredictionService.reset()

    def test_assess_returns_report_with_variants(self):
        img = make_skin_image(seed=3)
        report = ReliabilityService.assess_pil(img)
        self.assertGreater(len(report.variants), 0)
        self.assertGreaterEqual(report.agreement_pct, 0.0)
        self.assertLessEqual(report.agreement_pct, 100.0)
        self.assertIsInstance(report.stable, bool)


@override_settings(ML_MODEL_BACKEND="mock")
class MultiImageServiceTests(TestCase):
    def setUp(self):
        PredictionService.reset()

    def test_compare_returns_modal_class(self):
        img1 = make_skin_image(seed=11)
        img2 = make_skin_image(seed=22)
        img3 = make_skin_image(seed=33)
        report = MultiImageService.compare_pil([
            ("a", img1), ("b", img2), ("c", img3)
        ])
        self.assertEqual(len(report.images), 3)
        self.assertIn(report.modal_class, CLASS_ORDER)

    def test_compare_with_zero_images(self):
        report = MultiImageService.compare_pil([])
        self.assertEqual(len(report.images), 0)
        self.assertEqual(report.modal_class, "")

    def test_compare_fails_instead_of_returning_a_partial_report(self):
        first_prediction = PredictionResult(
            predicted_class="nv",
            predicted_name="Melanocytic Nevi",
            category="benign",
            confidence=0.8,
        )
        images = [
            ("first.jpg", make_skin_image(seed=41)),
            ("second.jpg", make_skin_image(seed=42)),
        ]
        with patch(
            "apps.common.services.multi_image.PredictionService.predict_pil",
            side_effect=[first_prediction, RuntimeError("private backend detail")],
        ):
            with self.assertRaises(PredictionError) as raised:
                MultiImageService.compare_pil(images)

        self.assertIn("image 2", str(raised.exception))
        self.assertNotIn("private backend detail", str(raised.exception))


class WrongInputServiceTests(TestCase):
    def test_validate_valid_skin_image(self):
        img = make_skin_image(seed=42, size=(300, 300))
        report = WrongInputService.validate_pil(img)
        self.assertTrue(report.is_valid_image)
        self.assertTrue(report.looks_like_skin)

    def test_validate_corrupt_bytes(self):
        report, pil = WrongInputService.validate_bytes(b"not an image at all")
        self.assertFalse(report.is_valid_image)
        self.assertIsNone(pil)


class GeminiServiceFailureTests(TestCase):
    def setUp(self):
        GeminiService._model = "gemini-test"

    def tearDown(self):
        GeminiService.reset()

    @staticmethod
    def overloaded_error():
        error = RuntimeError("503 UNAVAILABLE: temporarily overloaded")
        error.status_code = 503
        return error

    def test_retries_a_transient_503_once(self):
        client = Mock()
        client.models.generate_content.side_effect = [
            self.overloaded_error(),
            SimpleNamespace(text="Recovered answer"),
        ]

        with (
            patch.object(GeminiService, "_ensure_client", return_value=client),
            patch("apps.common.services.gemini.time.sleep") as sleep,
        ):
            reply = GeminiService.chat(
                history=[],
                user_message="What public features does this app offer?",
            )

        self.assertEqual(reply, "Recovered answer")
        self.assertEqual(client.models.generate_content.call_count, 2)
        sleep.assert_called_once_with(0.75)

    def test_dashboard_questions_keep_personalized_fallback_during_503(self):
        client = Mock()
        client.models.generate_content.side_effect = [
            self.overloaded_error(),
            self.overloaded_error(),
        ]
        dashboard = {
            "total_predictions": 2,
            "tracked_lesions": 1,
            "predictions_last_7_days": 1,
            "predictions_by_class": [
                {"code": "nv", "name": "Melanocytic Nevi", "count": 2},
            ],
        }

        with (
            patch.object(GeminiService, "_ensure_client", return_value=client),
            patch("apps.common.services.gemini.time.sleep"),
        ):
            reply = GeminiService.chat(
                history=[],
                user_message="Summarize my dashboard",
                context=dashboard,
                is_authenticated=True,
            )

        self.assertIn("temporarily unavailable", reply.lower())
        self.assertIn("2 total predictions", reply)
        self.assertNotIn("offline mode", reply.lower())

    def test_staff_aggregate_question_has_offline_site_wide_answer(self):
        context = {
            "total_users": 12,
            "total_predictions": 7,
            "tracked_lesions": 4,
            "predictions_last_7_days": 2,
            "predictions_last_30_days": 5,
            "review_status_counts": {
                "pending": 3,
                "appointment_planned": 2,
                "reviewed": 2,
            },
        }

        with patch.object(GeminiService, "_ensure_client", return_value=None):
            reply = GeminiService.chat(
                history=[],
                user_message="How many users and predictions are there?",
                context=context,
                is_authenticated=True,
                is_staff=True,
            )

        self.assertIn("12 user accounts", reply)
        self.assertIn("7 predictions", reply)
        self.assertIn("aggregate counts only", reply)
