import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import PatientProfile
from apps.common.services.prediction import PredictionService
from apps.predictor.models import PredictionRecord
from tests._helpers import image_to_jpeg_bytes, make_skin_image
from django.core.files.uploadedfile import SimpleUploadedFile


User = get_user_model()


class PatientProfileDetailsTests(TestCase):
    def test_profile_saves_contact_and_demographic_fields(self):
        user = User.objects.create_user(username="profile-patient", password="Pass!2024")
        client = Client()
        client.force_login(user)

        response = client.post("/accounts/profile/", {
            "name": "Nadia Rahman",
            "email": "nadia@example.com",
            "phone": "+8801712345678",
            "sex": "female",
            "age": "34",
            "location": "Dhaka",
        })

        self.assertRedirects(response, "/accounts/profile/")
        profile = PatientProfile.objects.get(user=user)
        self.assertEqual(profile.phone, "+8801712345678")
        self.assertEqual(profile.sex, "female")
        self.assertEqual(profile.age, 34)
        self.assertEqual(profile.location, "Dhaka")
        self.assertContains(client.get("/accounts/profile/"), "Dhaka")


@override_settings(ML_MODEL_BACKEND="mock")
class PatientNamedUploadTests(TestCase):
    def setUp(self):
        PredictionService.reset()
        self.media_dir = tempfile.TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_dir.cleanup)
        self.user = User.objects.create_user(
            username="named-patient", password="Pass!2024"
        )
        self.client.force_login(self.user)

    def test_patient_name_becomes_saved_image_name_and_history_label(self):
        image = SimpleUploadedFile(
            "original-upload.jpg",
            image_to_jpeg_bytes(make_skin_image(seed=123, size=(300, 300))),
            content_type="image/jpeg",
        )
        response = self.client.post("/predict/", {
            "image": image,
            "patient_name": "Nadia Rahman",
        })

        self.assertEqual(response.status_code, 302)
        record = PredictionRecord.objects.get(user=self.user)
        self.assertEqual(record.patient_name, "Nadia Rahman")
        self.assertEqual(record.image_name, "Nadia Rahman")
        self.assertIn("Nadia_Rahman_", record.image.name)
        self.assertContains(self.client.get("/predict/history/"), "Nadia Rahman")

    def test_image_name_is_saved_without_copying_it_to_patient_name(self):
        image = SimpleUploadedFile(
            "original-upload.jpg",
            image_to_jpeg_bytes(make_skin_image(seed=124, size=(300, 300))),
            content_type="image/jpeg",
        )
        response = self.client.post("/predict/", {
            "image": image,
            "image_name": "Left arm spot",
        })

        self.assertEqual(response.status_code, 302)
        record = PredictionRecord.objects.get(user=self.user)
        self.assertEqual(record.image_name, "Left arm spot")
        self.assertEqual(record.patient_name, "")
        self.assertIn("Left_arm_spot_", record.image.name)


class MedicalPriorityQueueTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(username="doctor", password="Pass!2024")
        self.doctor.user_permissions.add(
            Permission.objects.get(codename="view_medical_priority_queue")
        )
        self.client.force_login(self.doctor)
        PatientProfile.objects.create(
            user=self.doctor,
            sex="female",
            age=46,
            phone="+8801700000000",
            location="Dhaka",
        )
        self.records = {}
        for index, code in enumerate(("mel", "bcc", "akiec", "nv")):
            self.records[code] = PredictionRecord.objects.create(
                user=self.doctor,
                reference_id=f"MEDICAL{index:02d}",
                image_name=f"Patient {code}",
                patient_name=f"Patient {code}",
                predicted_class=code,
                predicted_name=code.upper(),
                category="malignant" if code == "mel" else "benign",
                confidence=0.8,
                probabilities={code: 0.8},
                backend="mock",
                review_status="pending",
            )

    def test_panel_requires_the_medical_queue_permission(self):
        unassigned = User.objects.create_user(
            username="ordinary-user", password="Pass!2024"
        )
        client = Client()
        client.force_login(unassigned)

        denied = client.get("/doctors/panel/")
        self.assertEqual(denied.status_code, 403)
        self.assertContains(
            denied,
            "Only authorized Doctors and Administrators can access and use this panel.",
            status_code=403,
        )
        self.assertContains(client.get("/"), 'href="/doctors/panel/"')

    def test_anonymous_user_sees_panel_link_and_access_message(self):
        client = Client()

        self.assertContains(client.get("/"), "Doctor Panel")
        denied = client.get("/doctors/panel/")
        self.assertEqual(denied.status_code, 403)
        self.assertContains(
            denied,
            "Only authorized Doctors and Administrators can access and use this panel.",
            status_code=403,
        )

    def test_homepage_features_doctor_panel_instead_of_wrong_input_protection(self):
        response = Client().get("/")

        self.assertContains(response, "Doctor Panel")
        self.assertContains(response, "review follow-up cases")
        self.assertContains(response, "Open Doctor Panel")
        self.assertContains(response, 'href="/doctors/panel/"')
        self.assertNotContains(response, "Wrong-Input Protection")

    def test_django_superuser_can_open_doctor_panel(self):
        administrator = User.objects.create_superuser(
            username="site-admin",
            email="admin@example.com",
            password="Pass!2024",
        )
        client = Client()
        client.force_login(administrator)

        self.assertEqual(client.get("/admin/").status_code, 200)
        response = client.get("/doctors/panel/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Doctor Panel")
        self.assertNotContains(response, "Doctor Dashboard")
        self.assertContains(response, 'data-i18n="nav.doctor_panel">Doctor Panel</a>')
        self.assertContains(response, 'href="/doctors/panel/"')
        self.assertNotContains(response, "Staff login")

    def test_queue_groups_high_priority_first_and_exposes_filters(self):
        response = self.client.get("/doctors/panel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [record.predicted_class for record in response.context["records"]],
            ["mel", "akiec", "bcc", "nv"],
        )
        self.assertContains(response, 'class="doctor-review-actions"')
        self.assertContains(response, 'aria-label="Delete case MEDICAL00"')
        self.assertContains(response, 'href="/doctors/panel/delete/MEDICAL00/"')
        self.assertEqual(response.context["records"][0].patient_age, 46)
        self.assertEqual(response.context["records"][0].patient_phone, "+8801700000000")
        self.assertEqual(
            response.context["records"][0].patient_display_name,
            "Patient mel",
        )
        for column in (
            "Serial", "Patient name", "Phone", "Image Label", "Sex / age",
            "Class", "Confidence", "Submitted", "Priority reason", "Report",
        ):
            self.assertContains(response, column)
        self.assertContains(response, "+8801700000000")
        self.assertContains(response, "Patient mel")
        self.assertContains(response, "P1 — High")
        self.assertContains(response, "doctor-submit-button")
        self.assertContains(response, "Review according to clinical context")
        self.assertNotContains(response, "অনুযায়ী")

        filtered = self.client.get(
            "/doctors/panel/?priority=p2&review_status=pending"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(
            [record.predicted_class for record in filtered.context["records"]],
            ["akiec", "bcc"],
        )

    def test_review_status_and_date_can_be_updated_and_report_exported(self):
        record = self.records["mel"]
        record.patient_name = "রহিম উদ্দিন"
        record.save(update_fields=["patient_name"])
        appointment = timezone.localdate() + timedelta(days=10)
        response = self.client.post(
            f"/doctors/panel/review/{record.reference_id}/",
            {
                "review_status": "appointment_planned",
                "review_date": appointment.isoformat(),
                "return_to": "/doctors/panel/?priority=p1",
            },
        )

        self.assertRedirects(
            response, "/doctors/panel/?priority=p1", fetch_redirect_response=False
        )
        record.refresh_from_db()
        self.assertEqual(record.review_status, "appointment_planned")
        self.assertEqual(record.review_date, appointment)

        report = self.client.get("/doctors/panel/serial-report/?priority=p1")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report["Content-Type"], "application/pdf")
        self.assertTrue(report.content.startswith(b"%PDF-"))

