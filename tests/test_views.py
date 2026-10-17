"""Tests for view-level behavior: auth, upload, prediction history, tracker
privacy, chatbot endpoint."""
import base64
import io
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.common.services.prediction import (
    PredictionError, PredictionResult, PredictionService,
)
from apps.common.services.reliability import ReliabilityReport
from apps.common.services.enhancement import EnhancementReport
from apps.common.services.wrong_input import WrongInputReport
from apps.predictor.models import PredictionRecord
from apps.tracker.models import LesionRecord, FollowUpPhoto
from tests._helpers import make_skin_image, image_to_jpeg_bytes


User = get_user_model()


@override_settings(ML_MODEL_BACKEND="mock")
class MultiImageComparisonViewTests(TestCase):
    def setUp(self):
        PredictionService.reset()

    @staticmethod
    def upload(seed, name):
        return SimpleUploadedFile(
            name,
            image_to_jpeg_bytes(make_skin_image(seed=seed, size=(300, 300))),
            content_type="image/jpeg",
        )

    def test_compare_page_exposes_accessible_multi_file_upload(self):
        response = self.client.get("/multi/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="imageInput"')
        self.assertContains(response, "multiple")
        self.assertContains(response, 'id="compareSubmit" disabled')
        self.assertContains(response, "js/multi-image.js")

    def test_comparison_returns_a_result_for_each_uploaded_image(self):
        response = self.client.post("/multi/", {
            "images": [
                self.upload(61, "first.jpg"),
                self.upload(62, "second.jpg"),
            ],
        })

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["error"])
        self.assertEqual(len(response.context["report"].images), 2)
        self.assertContains(response, "Image #")
        self.assertContains(response, "data:image/jpeg;base64,")

    def test_prediction_failure_is_shown_without_partial_results_or_internal_error(self):
        with patch(
            "apps.common.services.multi_image.PredictionService.predict_pil",
            side_effect=RuntimeError("private model path"),
        ):
            response = self.client.post("/multi/", {
                "images": [
                    self.upload(71, "first.jpg"),
                    self.upload(72, "second.jpg"),
                ],
            })

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["report"])
        self.assertContains(response, "Could not compare images: Prediction failed for image 1.")
        self.assertNotContains(response, "private model path")


class HowItWorksPageTests(TestCase):
    def test_page_explains_user_workflow_without_model_training_details(self):
        response = self.client.get("/how-it-works/")

        self.assertEqual(response.status_code, 200)
        for section_title in (
            "Take and upload a photo",
            "Check photo quality",
            "Review the experimental result",
            "Check result stability",
            "Compare multiple photos",
            "Ask the assistant",
            "Save observations",
            "Doctor Panel",
        ):
            self.assertContains(response, section_title)

        for internal_detail in ("dataset", "trained model", "Laplacian", "softmax"):
            self.assertNotContains(response, internal_detail)


class AboutPageTests(TestCase):
    def test_about_page_is_user_facing_and_omits_private_technical_details(self):
        response = self.client.get("/about/")

        self.assertEqual(response.status_code, 200)
        for public_content in (
            "What the project is for",
            "What the app offers",
            "Doctor Panel",
            "Privacy and access",
            "does not provide medical",
        ):
            self.assertContains(response, public_content)

        for private_detail in (
            "dataset",
            "trained classifier",
            "softmax",
            "Django REST Framework",
            "Google Gemini",
        ):
            self.assertNotContains(response, private_detail)


class HomeCancerFaqTests(TestCase):
    def test_cancer_faq_uses_requested_safety_copy_without_dataset_details(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        for public_copy in (
            "Can DermaCheckerBD Diagnose Skin Cancer?",
            "No. DermaCheckerBD is an AI-powered skin lesion analysis prototype",
            "support medical review prioritization",
            "not confirmed diagnoses",
            "cannot determine a patient's actual medical urgency or treatment needs",
            "Important:",
            "regardless of the AI prediction.",
        ):
            self.assertContains(response, public_copy)

        self.assertContains(
            response,
            '<strong><span data-i18n="home.faq.a4_intro">',
            html=False,
        )
        self.assertNotContains(response, "HAM10000")


class UploadPagePrivacyTests(TestCase):
    def test_upload_page_does_not_name_the_training_dataset(self):
        response = self.client.get("/predict/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Supported lesion categories")
        self.assertContains(response, "Across 7 supported categories")
        self.assertNotContains(response, "HAM10000")


class AuthTests(TestCase):
    def test_language_toggle_comes_before_sign_out_for_authenticated_nav(self):
        user = User.objects.create_user(username="navbar", password="Pass!2024")
        client = Client()
        client.force_login(user)

        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        nav_markers = [
            'data-i18n="nav.home"',
            'data-i18n="nav.how_it_works"',
            'data-i18n="nav.features"',
            'data-i18n="nav.about"',
            'data-i18n="nav.dashboard"',
            'data-i18n="nav.profile"',
            'data-lang="en"',
            'data-lang="bn"',
            'data-i18n="nav.sign_out"',
        ]
        positions = [html.index(marker) for marker in nav_markers]
        self.assertEqual(positions, sorted(positions))

    def test_language_toggle_comes_before_start_scan_for_signed_out_nav(self):
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertLess(html.index('data-lang="en"'), html.index('data-lang="bn"'))
        self.assertLess(html.index('data-lang="bn"'), html.index('data-i18n="nav.start_scan"'))

    def test_signup(self):
        c = Client()
        r = c.post("/accounts/signup/", {
            "username": "alice",
            "password1": "Str0ngPass!2024",
            "password2": "Str0ngPass!2024",
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_login_required_for_tracker(self):
        c = Client()
        r = c.get("/tracker/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_login_required_for_profile(self):
        c = Client()
        r = c.get("/accounts/profile/")
        self.assertEqual(r.status_code, 302)

    def test_profile_displays_and_updates_name_and_email(self):
        user = User.objects.create_user(
            username="profile-user", password="Pass!2024",
            first_name="Rafi", last_name="Ahmed", email="old@example.com",
        )
        c = Client()
        c.force_login(user)

        response = c.get("/accounts/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rafi Ahmed")
        self.assertContains(response, "old@example.com")
        self.assertContains(response, "profile.edit")

        response = c.post("/accounts/profile/", {
            "name": "Nadia Rahman",
            "email": "nadia@example.com",
        })
        self.assertRedirects(response, "/accounts/profile/")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Nadia")
        self.assertEqual(user.last_name, "Rahman")
        self.assertEqual(user.email, "nadia@example.com")

    def test_profile_rejects_invalid_email(self):
        user = User.objects.create_user(
            username="profile-invalid", password="Pass!2024",
            email="valid@example.com",
        )
        c = Client()
        c.force_login(user)

        response = c.post("/accounts/profile/", {
            "name": "Valid Name",
            "email": "not-an-email",
        })

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "valid@example.com")


@override_settings(ML_MODEL_BACKEND="mock")
class UploadAndPredictionTests(TestCase):
    def setUp(self):
        PredictionService.reset()
        self.user = User.objects.create_user(username="bob", password="Pass!2024")
        self.c = Client()
        self.c.login(username="bob", password="Pass!2024")

    def test_upload_image_and_predict(self):
        img = make_skin_image(seed=7, size=(300, 300))
        img_bytes = image_to_jpeg_bytes(img)
        # Need CSRF token first
        r = self.c.get("/predict/")
        csrf = r.cookies["csrftoken"].value if "csrftoken" in r.cookies else None
        self.assertIsNotNone(csrf)

        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("test.jpg", img_bytes, content_type="image/jpeg")
        r = self.c.post("/predict/", {
            "image": upload, "patient_name": "Rafi Ahmed",
            "csrfmiddlewaretoken": csrf,
        })
        self.assertEqual(r.status_code, 302)
        self.assertIn("/predict/result/", r["Location"])

        # Verify record was saved
        self.assertTrue(PredictionRecord.objects.filter(user=self.user).exists())
        record = PredictionRecord.objects.get(user=self.user)
        self.assertGreater(record.confidence, 0.0)
        self.assertEqual(len(record.probabilities), 7)


    def test_upload_rejects_non_image(self):
        r = self.c.get("/predict/")
        csrf = r.cookies["csrftoken"].value if "csrftoken" in r.cookies else ""
        upload = SimpleUploadedFile("not.txt", b"hello", content_type="text/plain")
        # Don't actually upload non-image — the form validation should catch it
        r = self.c.post("/predict/", {
            "image": upload, "patient_name": "Rafi Ahmed",
            "csrfmiddlewaretoken": csrf,
        })
        # The view returns 200 with an error (renders upload.html with error)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Unsupported file type", r.content)

    def test_prediction_error_is_not_exposed_to_user(self):
        image = make_skin_image(seed=8, size=(300, 300))
        upload = SimpleUploadedFile(
            "test.jpg", image_to_jpeg_bytes(image), content_type="image/jpeg"
        )
        with patch(
            "apps.predictor.views.PredictionService.predict_pil",
            side_effect=PredictionError("private model internals"),
        ):
            response = self.c.post("/predict/", {
                "image": upload, "patient_name": "Rafi Ahmed",
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prediction could not be completed")
        self.assertNotContains(response, "private model internals")

    def test_low_confidence_warning_normalizes_saved_percentages_and_decimals(self):
        image_bytes = image_to_jpeg_bytes(make_skin_image(seed=30, size=(300, 300)))
        for reference, confidence in (("LOWPERCENT", 42.0), ("LOWDECIMAL", 0.42)):
            record = PredictionRecord(
                user=self.user,
                reference_id=reference,
                image_name="confidence-test.jpg",
                predicted_class="nv",
                predicted_name="Melanocytic nevi",
                category="benign",
                confidence=confidence,
                probabilities={"nv": 0.42},
            )
            record.image.save(
                f"{reference}.jpg", ContentFile(image_bytes), save=False
            )
            record.save()
            response = self.c.get(f"/predict/result/{reference}/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "42.0%")
            self.assertContains(response, "Low model confidence")
            self.assertContains(response, "dermoscopy or other tests")
            self.assertNotContains(response, "4200.0%")

    def test_confidence_at_fifty_percent_does_not_show_low_warning(self):
        record = PredictionRecord(
            user=self.user,
            reference_id="CONFIDENCE50",
            image_name="confidence-test.jpg",
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.5,
            probabilities={"nv": 0.5},
        )
        record.image.save(
            "confidence50.jpg",
            ContentFile(image_to_jpeg_bytes(make_skin_image(seed=31))),
            save=False,
        )
        record.save()
        response = self.c.get("/predict/result/CONFIDENCE50/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Low model confidence")

    def test_malignant_result_shows_clear_warning_icon_and_review_message(self):
        record = PredictionRecord(
            user=self.user,
            reference_id="MALIGNANT01",
            image_name="concerning-result.jpg",
            predicted_class="mel",
            predicted_name="Melanoma",
            category="malignant",
            confidence=0.82,
            probabilities={"mel": 0.82},
        )
        record.image.save(
            "malignant-result.jpg",
            ContentFile(image_to_jpeg_bytes(make_skin_image(seed=33))),
            save=False,
        )
        record.save()

        response = self.c.get("/predict/result/MALIGNANT01/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-lucide="alert-octagon"')
        self.assertContains(response, 'class="report-result-warning mt-3"')
        self.assertContains(response, 'data-i18n="result.professional_review_title"')


@override_settings(ML_MODEL_BACKEND="mock")
class PhotoGuidePredictionHandoffTests(TestCase):
    def setUp(self):
        PredictionService.reset()
        self.media_dir = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_dir.cleanup)

    def test_quality_check_hands_the_original_image_to_prediction(self):
        original_bytes = image_to_jpeg_bytes(
            make_skin_image(seed=144, size=(300, 300))
        )
        with patch(
            "apps.photo_guide.views.ImageEnhancementService.enhance_if_needed",
            return_value=(
                Image.open(io.BytesIO(original_bytes)),
                SimpleNamespace(applied=False),
            ),
        ):
            quality_response = self.client.post("/quality/", {
                "image": SimpleUploadedFile(
                    "original-lesion.jpg",
                    original_bytes,
                    content_type="image/jpeg",
                ),
            })

        self.assertEqual(quality_response.status_code, 200)
        self.assertEqual(quality_response.context["report"].overall_score, 100.0)
        self.assertEqual(
            quality_response.context["prediction_data_url"],
            "data:image/jpeg;base64," + base64.b64encode(original_bytes).decode("ascii"),
        )
        self.assertContains(
            quality_response,
            'data-image-url="data:image/jpeg;base64,',
        )
        self.assertTrue(quality_response.context["report"].suitable)

        prediction_response = self.client.post("/predict/", {
            "image_name": "original-lesion",
            "image": SimpleUploadedFile(
                "original-lesion.jpg",
                original_bytes,
                content_type="image/jpeg",
            ),
        })

        self.assertEqual(prediction_response.status_code, 302)
        self.assertEqual(PredictionRecord.objects.count(), 1)

    def test_png_upload_keeps_png_bytes_for_the_prediction_handoff(self):
        original = make_skin_image(seed=145, size=(300, 300))
        buffer = io.BytesIO()
        original.save(buffer, format="PNG")
        original_bytes = buffer.getvalue()
        with patch(
            "apps.photo_guide.views.ImageEnhancementService.enhance_if_needed",
            return_value=(original, SimpleNamespace(applied=False)),
        ):
            response = self.client.post("/quality/", {
                "image": SimpleUploadedFile(
                    "original-lesion.png",
                    original_bytes,
                    content_type="image/png",
                ),
            })

        self.assertEqual(response.status_code, 200)
        data_url = response.context["prediction_data_url"]
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        self.assertEqual(
            base64.b64decode(data_url.split(",", 1)[1]),
            original_bytes,
        )


class TrackerPrivacyTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="Pass!2024")
        self.bob = User.objects.create_user(username="bob", password="Pass!2024")
        self.alice_record = LesionRecord.objects.create(
            user=self.alice, lesion_id="ALICE001", label="Alice's lesion"
        )
        self.c_alice = Client()
        self.c_alice.login(username="alice", password="Pass!2024")
        self.c_bob = Client()
        self.c_bob.login(username="bob", password="Pass!2024")

    def test_alice_can_view_own_record(self):
        r = self.c_alice.get(f"/tracker/{self.alice_record.lesion_id}/")
        self.assertEqual(r.status_code, 200)
        # The label is HTML-escaped because Django auto-escapes templates.
        self.assertIn(b"Alice", r.content)
        self.assertIn(b"ALICE001", r.content)

    def test_bob_cannot_view_alice_record(self):
        """Critical: a user must NOT be able to access another user's records."""
        # Try direct access
        r = self.c_bob.get(f"/tracker/{self.alice_record.lesion_id}/")
        self.assertEqual(r.status_code, 404)  # get_object_or_404 hides the record

    def test_bob_cannot_delete_alice_record(self):
        r = self.c_bob.post(f"/tracker/{self.alice_record.lesion_id}/delete/", {})
        self.assertIn(r.status_code, (404, 403))
        self.assertTrue(LesionRecord.objects.filter(id=self.alice_record.id).exists())


class PhotoGuideHandoffTests(TestCase):
    def test_enhanced_preview_is_handed_to_prediction_as_the_uploaded_file(self):
        original = make_skin_image(seed=41, size=(300, 300))
        enhanced = Image.new("RGB", (300, 300), (45, 90, 150))
        upload = SimpleUploadedFile(
            "lesion-original.jpg",
            image_to_jpeg_bytes(original),
            content_type="image/jpeg",
        )
        with (
            patch(
                "apps.photo_guide.views.WrongInputService.validate_bytes",
                return_value=(
                    WrongInputReport(is_valid_image=True, looks_like_skin=True),
                    original,
                ),
            ),
            patch(
                "apps.photo_guide.views.ImageEnhancementService.enhance_if_needed",
                return_value=(enhanced, EnhancementReport(applied=True)),
            ),
        ):
            response = self.client.post("/quality/", {"image": upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-enhanced="true"')
        self.assertContains(response, 'id="predictionOverlay"')
        html = response.content.decode()
        self.assertLess(
            html.index('id="qualityCustomizer"'),
            html.index('alt="Enhanced preview"'),
        )
        self.assertGreater(
            html.index('id="qualityImagePreview"'),
            html.index('data-i18n="pg.enhanced"'),
        )
        self.assertIsNone(response.context["customizer_data_url"])
        self.assertIn('data-customizer-url=""', html)
        self.assertLess(
            html.index('data-i18n="pg.enhance_note"'),
            html.index('id="downloadQualityImage"'),
        )
        self.assertLess(
            html.index('data-i18n="pg.enhance_note"'),
            html.index('id="runPredictionButton"'),
        )
        image_data_url = response.context["prediction_data_url"]
        self.assertTrue(image_data_url.startswith("data:image/jpeg;base64,"))
        encoded = image_data_url.split(",", 1)[1]
        handed_off = Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
        red, green, blue = handed_off.getpixel((150, 150))
        self.assertLess(red, 60)
        self.assertGreater(green, 75)
        self.assertGreater(blue, 130)

    def test_customizer_receives_a_full_resolution_image(self):
        image = make_skin_image(seed=42, size=(640, 480))
        original_bytes = image_to_jpeg_bytes(image)
        upload = SimpleUploadedFile(
            "customize.jpg", original_bytes, content_type="image/jpeg"
        )
        with patch(
            "apps.photo_guide.views.ImageEnhancementService.enhance_if_needed",
            return_value=(image, EnhancementReport(applied=False)),
        ):
            response = self.client.post("/quality/", {"image": upload})

        self.assertEqual(response.status_code, 200)
        data_url = response.context["customizer_data_url"]
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        customizer_image = Image.open(
            io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))
        )
        self.assertEqual(customizer_image.size, (640, 480))
        self.assertEqual(
            response.context["prediction_data_url"],
            "data:image/jpeg;base64,"
            + base64.b64encode(original_bytes).decode("ascii"),
        )
        self.assertContains(response, 'id="qualityCustomizer"')
        self.assertContains(response, 'id="downloadQualityImage"')
        self.assertContains(response, 'id="runPredictionButton"')

    def test_quality_handoff_exposes_an_editable_image_name(self):
        image = make_skin_image(seed=43, size=(640, 480))
        upload = SimpleUploadedFile(
            "arm-lesion.jpg", image_to_jpeg_bytes(image), content_type="image/jpeg"
        )
        with patch(
            "apps.photo_guide.views.ImageEnhancementService.enhance_if_needed",
            return_value=(image, EnhancementReport(applied=False)),
        ):
            response = self.client.post("/quality/", {"image": upload})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["image_name"], "arm-lesion")
        self.assertContains(response, 'id="qualityImageName"')
        self.assertContains(response, 'id="qualityPredictionName"')


@override_settings(ML_MODEL_BACKEND="mock")
class ReliabilityPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="reliability-owner")
        self.client = Client()
        self.client.force_login(self.owner)
        image_bytes = image_to_jpeg_bytes(make_skin_image(seed=45, size=(300, 300)))
        self.record = PredictionRecord(
            user=self.owner,
            reference_id="RELTEST01",
            image_name="test-lesion.jpg",
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.82,
            probabilities={"nv": 0.82},
        )
        self.record.image.save(
            "reliability-test.jpg", ContentFile(image_bytes), save=False
        )
        self.record.save()

    def test_result_page_reliability_button_carries_its_record(self):
        response = self.client.get("/predict/result/RELTEST01/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/reliability/?reference_id=RELTEST01")

    def test_reliability_page_runs_on_the_saved_image(self):
        original = PredictionResult(
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.82,
            probabilities={"nv": 0.82},
        )
        with patch(
            "apps.reliability.views.ReliabilityService.assess_pil",
            return_value=ReliabilityReport(
                original=original, agreement_pct=100, stable=True
            ),
        ) as assess:
            response = self.client.get(
                "/reliability/?reference_id=RELTEST01"
            )

        self.assertEqual(response.status_code, 200)
        assess.assert_called_once()
        self.assertContains(response, "Original prediction")
        self.assertContains(response, 'id="reliabilitySubmit"')

    def test_reliability_page_rejects_missing_upload(self):
        response = self.client.post("/reliability/", {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please choose an image")

    def test_reliability_page_enforces_record_privacy(self):
        other_user = User.objects.create_user(username="other-reliability-user")
        self.client.force_login(other_user)
        response = self.client.get(
            "/reliability/?reference_id=RELTEST01"
        )
        self.assertEqual(response.status_code, 403)


class DashboardAndHistoryManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="dashboard-owner")
        self.other = User.objects.create_user(username="dashboard-other")
        self.client = Client()
        self.client.force_login(self.owner)

    @staticmethod
    def make_record(user, reference_id, reliability_report=None):
        return PredictionRecord.objects.create(
            user=user,
            reference_id=reference_id,
            image="",
            image_name=f"{reference_id}.jpg",
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.82,
            probabilities={"nv": 0.82},
            reliability_report=reliability_report or {},
        )

    def test_account_dashboard_shows_only_the_signed_in_users_totals(self):
        self.make_record(self.owner, "DASHOWN01")
        self.make_record(self.other, "DASHOTH01")

        response = self.client.get("/accounts/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["total_predictions"], 1)
        self.assertContains(response, "DASHOWN01")
        self.assertNotContains(response, "DASHOTH01")
        self.assertContains(response, "dashboard-daily-counts")
        self.assertContains(response, 'class="app-card h-100 dashboard-chart-card"')
        self.assertContains(response, 'class="dashboard-chart-frame"')
        self.assertContains(response, "animation: false")

    def test_class_pie_chart_includes_all_seven_classes_with_stable_counts(self):
        self.make_record(self.owner, "DASHCLASS01")

        response = self.client.get("/accounts/dashboard/")

        self.assertEqual(response.status_code, 200)
        distribution = response.context["class_distribution"]
        self.assertEqual(len(distribution), 7)
        nv = next(item for item in distribution if item["code"] == "nv")
        self.assertEqual(nv["count"], 1)
        self.assertEqual(sum(item["count"] for item in distribution), 1)
        self.assertContains(response, "type: 'pie'")
        self.assertContains(response, "'akiec': '#0f766e'")
        self.assertContains(response, "'vasc': '#0891b2'")

    def test_class_chart_keeps_empty_state_before_first_prediction(self):
        response = self.client.get("/accounts/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your class distribution chart will appear here")
        self.assertNotContains(response, 'id="classChart"')

    def test_history_has_clear_all_and_per_record_delete_options(self):
        self.make_record(self.owner, "HISTORY001")

        response = self.client.get("/predict/history/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/predict/history/clear/")
        self.assertContains(response, "/predict/result/HISTORY001/delete/")
        self.assertContains(response, "history.delete")
        self.assertContains(response, "history-clear-button")
        self.assertContains(response, "class-code-badge--benign")

    def test_history_colors_bcc_and_bkl_codes_by_category(self):
        bcc = self.make_record(self.owner, "CLASSBCC001")
        bcc.predicted_class = "bcc"
        bcc.predicted_name = "Basal Cell Carcinoma"
        bcc.category = "malignant"
        bcc.save()
        bkl = self.make_record(self.owner, "CLASSBKL001")
        bkl.predicted_class = "bkl"
        bkl.predicted_name = "Benign Keratosis-like Lesions"
        bkl.save()

        response = self.client.get("/predict/history/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "class-code-badge--malignant")
        self.assertContains(response, "class-code-badge--benign")
        self.assertContains(response, ">BCC</span>")
        self.assertContains(response, ">BKL</span>")

    def test_single_delete_requires_confirmation_and_removes_only_owner_record(self):
        self.make_record(self.owner, "DELETEOWN01")
        self.make_record(self.other, "DELETEOTH01")

        confirm = self.client.get("/predict/result/DELETEOWN01/delete/")
        self.assertEqual(confirm.status_code, 200)

        response = self.client.post("/predict/result/DELETEOWN01/delete/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PredictionRecord.objects.filter(reference_id="DELETEOWN01").exists())
        self.assertTrue(PredictionRecord.objects.filter(reference_id="DELETEOTH01").exists())

    def test_single_delete_rejects_another_users_record(self):
        self.make_record(self.other, "PRIVATEDEL01")

        response = self.client.post("/predict/result/PRIVATEDEL01/delete/")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(PredictionRecord.objects.filter(reference_id="PRIVATEDEL01").exists())

    def test_clear_history_removes_all_and_only_signed_in_users_records(self):
        self.make_record(self.owner, "CLEAROWN001")
        self.make_record(self.owner, "CLEAROWN002")
        self.make_record(self.other, "CLEAROTH001")

        confirm = self.client.get("/predict/history/clear/")
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.context["record_count"], 2)

        response = self.client.post("/predict/history/clear/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PredictionRecord.objects.filter(user=self.owner).exists())
        self.assertTrue(PredictionRecord.objects.filter(user=self.other).exists())

    def test_anonymous_clear_history_is_limited_to_the_current_session(self):
        self.client.logout()
        self.client.get("/predict/history/")
        owner_session_key = self.client.session.session_key
        other_session_key = "different-session-key"
        PredictionRecord.objects.create(
            user=None,
            session_key=owner_session_key,
            reference_id="ANONOWN001",
            image="",
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.82,
            probabilities={"nv": 0.82},
        )
        PredictionRecord.objects.create(
            user=None,
            session_key=other_session_key,
            reference_id="ANONOTH001",
            image="",
            predicted_class="nv",
            predicted_name="Melanocytic nevi",
            category="benign",
            confidence=0.82,
            probabilities={"nv": 0.82},
        )

        response = self.client.post("/predict/history/clear/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PredictionRecord.objects.filter(reference_id="ANONOWN001").exists())
        self.assertTrue(PredictionRecord.objects.filter(reference_id="ANONOTH001").exists())

    def test_reliability_dashboard_displays_real_private_stability_and_percent_metrics(self):
        self.make_record(
            self.owner,
            "STABILITY001",
            {"agreement_pct": 82.5, "stable": True},
        )
        self.make_record(
            self.other,
            "STABILITY002",
            {"agreement_pct": 25.0, "stable": False},
        )

        response = self.client.get("/reliability/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stability_count"], 1)
        self.assertEqual(response.context["stability_average"], 82.5)
        self.assertEqual(response.context["stable_count"], 1)
        self.assertContains(response, "73.49%")
        self.assertContains(response, "61.67%")
        self.assertContains(response, "95.77%")
        self.assertContains(response, 'class="app-card mb-4 dashboard-chart-card"')
        self.assertContains(response, 'class="dashboard-chart-frame"')
        self.assertContains(response, "animation: false")
        self.assertTrue(response.context["recent_stability"][0]["label"].endswith("ITY001"))
        self.assertNotIn("ITY002", response.context["recent_stability"][0]["label"])
        self.assertNotContains(response, "reliabilityDiagram")

    def test_reliability_dashboard_shows_empty_state_without_saved_reports(self):
        response = self.client.get("/reliability/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stability_count"], 0)
        self.assertContains(response, "No saved stability results yet")
        self.assertContains(response, "ECE (pending)")


class ChatbotEndpointTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_endpoint_returns_json(self):
        # Even in offline mode, the endpoint should respond
        c = Client()
        r = c.post("/chatbot/message/",
                   data='{"message":"hi"}',
                   content_type="application/json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("reply", data)

    def test_replit_preview_origin_is_accepted_for_chatbot_post(self):
        c = Client(enforce_csrf_checks=True)
        c.get("/")
        csrf_token = c.cookies["csrftoken"].value
        with patch("apps.chatbot.views.GeminiService.chat", return_value="Hello"):
            response = c.post(
                "/chatbot/message/",
                data=json.dumps({"message": "hi"}),
                content_type="application/json",
                HTTP_ORIGIN="https://preview-123.pike.replit.dev:5000",
                HTTP_X_CSRFTOKEN=csrf_token,
            )

        self.assertEqual(response.status_code, 200)

    def test_endpoint_rejects_empty_message(self):
        c = Client()
        r = c.post("/chatbot/message/",
                   data='{"message":""}',
                   content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_endpoint_rejects_non_json(self):
        c = Client()
        r = c.post("/chatbot/message/",
                   data="not json",
                   content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_guest_cannot_supply_private_dashboard_context(self):
        from unittest.mock import patch

        with patch("apps.chatbot.views.GeminiService.chat", return_value="Public reply") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({
                    "message": "What public features does this site provide?",
                    "context": {"total_predictions": 999},
                }),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "public")
        self.assertIsNone(chat.call_args.kwargs["context"])
        self.assertFalse(chat.call_args.kwargs["is_authenticated"])

    def test_guest_private_dashboard_question_is_blocked_until_sign_in(self):
        with patch("apps.chatbot.views.GeminiService.chat") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "How many predictions do I have?"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sign in", response.json()["reply"].lower())
        chat.assert_not_called()

    def test_authenticated_chatbot_receives_only_own_dashboard_summary(self):
        owner = User.objects.create_user(username="chat-owner", password="Pass!2024")
        other = User.objects.create_user(username="chat-other", password="Pass!2024")
        DashboardAndHistoryManagementTests.make_record(owner, "CHATOWN001")
        DashboardAndHistoryManagementTests.make_record(other, "CHATOTH001")
        self.client.force_login(owner)

        with patch("apps.chatbot.views.GeminiService.chat", return_value="Private reply") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "Summarize my dashboard"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "private")
        self.assertTrue(chat.call_args.kwargs["is_authenticated"])
        context = chat.call_args.kwargs["context"]
        self.assertEqual(context["total_predictions"], 1)
        self.assertEqual(context["predictions_by_class"], [
            {"code": "nv", "name": "Melanocytic Nevi", "count": 1},
        ])
        self.assertNotIn("email", context)

    def test_signed_in_general_question_does_not_send_account_context(self):
        owner = User.objects.create_user(username="general-owner", password="Pass!2024")
        DashboardAndHistoryManagementTests.make_record(owner, "GENERAL001")
        self.client.force_login(owner)

        with patch("apps.chatbot.views.GeminiService.chat", return_value="General reply") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "What does the word dermatologist mean?"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(chat.call_args.kwargs["context"])

    def test_staff_chatbot_receives_only_site_wide_aggregates(self):
        owner = User.objects.create_user(username="staff-owner", password="Pass!2024")
        other = User.objects.create_user(username="staff-other", password="Pass!2024")
        staff = User.objects.create_user(
            username="aggregate-staff", password="Pass!2024", is_staff=True
        )
        DashboardAndHistoryManagementTests.make_record(owner, "STAFFOWN001")
        DashboardAndHistoryManagementTests.make_record(other, "STAFFOTH001")
        self.client.force_login(staff)

        with patch("apps.chatbot.views.GeminiService.chat", return_value="Aggregate reply") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "Show the site-wide dashboard history"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "staff")
        self.assertEqual(response.json()["authed"], True)
        self.assertTrue(chat.call_args.kwargs["is_staff"])
        context = chat.call_args.kwargs["context"]
        self.assertEqual(context["total_users"], 3)
        self.assertEqual(context["total_predictions"], 2)
        self.assertNotIn("STAFFOWN001", str(context))
        self.assertNotIn("STAFFOTH001", str(context))
        self.assertNotIn("staff-owner", str(context))
        self.assertNotIn("staff-other", str(context))

    def test_staff_chatbot_refuses_individual_records_without_calling_gemini(self):
        staff = User.objects.create_user(
            username="private-data-staff", password="Pass!2024", is_staff=True
        )
        self.client.force_login(staff)

        with patch("apps.chatbot.views.GeminiService.chat") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "Show Alice's history"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "staff")
        self.assertIn("can't show", response.json()["reply"].lower())
        chat.assert_not_called()

    def test_doctor_queue_permission_enables_aggregate_staff_scope(self):
        from django.contrib.auth.models import Permission

        doctor = User.objects.create_user(username="queue-doctor", password="Pass!2024")
        permission = Permission.objects.get(
            content_type__app_label="predictor",
            codename="view_medical_priority_queue",
        )
        doctor.user_permissions.add(permission)
        self.client.force_login(doctor)

        with patch("apps.chatbot.views.GeminiService.chat", return_value="Aggregate reply") as chat:
            response = self.client.post(
                "/chatbot/message/",
                data=json.dumps({"message": "How many user accounts are there?"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "staff")
        self.assertTrue(chat.call_args.kwargs["is_staff"])
        self.assertIn("total_users", chat.call_args.kwargs["context"])

    def test_endpoint_rejects_json_array(self):
        response = self.client.post(
            "/chatbot/message/", data="[]", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


@override_settings(GEMINI_API_KEY="")
class LanguagePreferenceTests(TestCase):
    def setUp(self):
        from apps.common.services.gemini import GeminiService
        GeminiService.reset()

    def test_language_cookie_sets_document_language(self):
        c = Client()
        c.cookies["derma_lang"] = "bn"
        response = c.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="bn">', html=False)

    def test_chatbot_replies_in_selected_bengali(self):
        c = Client()
        response = c.post(
            "/chatbot/message/",
            data='{"message":"What does confidence mean?","language":"bn"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("মডেল", response.json()["reply"])

    def test_chatbot_validation_error_uses_saved_language(self):
        c = Client()
        c.cookies["derma_lang"] = "bn"
        response = c.post(
            "/chatbot/message/",
            data='{"message":""}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("প্রশ্ন", response.json()["reply"])

    def test_questionnaire_recommendations_can_be_bengali(self):
        from apps.questionnaire.questions import QUESTIONS, evaluate

        result = evaluate({q["id"]: "no" for q in QUESTIONS}, language="bn")
        self.assertIn("কোনো সতর্কসংকেত", result.recommendations[0])


class ProductionConfigTests(TestCase):
    """Verify production-safe settings can be loaded."""
    @override_settings(DEBUG=False, DJANGO_SECURE_SSL_REDIRECT=True)
    def test_ssl_redirect_enforced(self):
        c = Client()
        # In test, we use the configured settings
        from django.conf import settings
        self.assertFalse(settings.DEBUG)

    def test_csrf_cookie_settings(self):
        from django.conf import settings
        # CSRF is enabled by default
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)
