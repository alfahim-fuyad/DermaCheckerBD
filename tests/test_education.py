"""Tests for the HAM10000 education library and class example assets."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase


class EducationLibraryTests(TestCase):
    CLASSES = {
        "akiec": ("pre-malignant", "Actinic keratosis / Bowen disease"),
        "bcc": ("malignant", "Basal cell carcinoma"),
        "bkl": ("benign", "Benign keratosis-like lesions"),
        "df": ("benign", "Dermatofibroma"),
        "mel": ("malignant", "Melanoma"),
        "nv": ("benign", "Melanocytic nevus (common mole)"),
        "vasc": ("benign", "Vascular lesions"),
    }

    def test_class_library_shows_each_example_image_name_and_category_color(self):
        response = self.client.get("/disease/")
        self.assertEqual(response.status_code, 200)

        for code, (category, display_name) in self.CLASSES.items():
            with self.subTest(code=code):
                self.assertContains(response, f"images/classes/{code}.png")
                self.assertContains(response, f"education-class-card--{category}")
                self.assertContains(response, display_name)
                self.assertTrue(
                    (Path(settings.BASE_DIR) / "static" / "images" / "classes" / f"{code}.png").is_file()
                )

    def test_class_detail_uses_the_matching_image_and_safety_caption(self):
        response = self.client.get("/disease/mel/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "images/classes/mel.png")
        self.assertContains(response, "education-class-card--malignant")
        self.assertContains(response, "this image cannot confirm a diagnosis")
