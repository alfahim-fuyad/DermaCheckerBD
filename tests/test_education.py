"""Tests for the HAM10000 education library and class example assets.

পরীক্ষাগুলো বাংলা বিষয়বস্তুর জন্য আপডেট করা হয়েছে — Skin Health Library এখন
সম্পূর্ণ বাংলা ভাষায় উপলব্ধ।
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase


class EducationLibraryTests(TestCase):
    # প্রতিটি ক্লাসের (category_slug, bengali_short_name) — Skin Health Library
    # এখন সম্পূর্ণ বাংলা ভাষায় রেন্ডার হয়।
    CLASSES = {
        "akiec": ("pre-malignant", "অ্যাকটিনিক কেরাটোসিস / বোয়েন রোগ (প্রি-ক্যান্সার)"),
        "bcc": ("malignant", "বেসাল সেল কার্সিনোমা (ত্বকের সাধারণ ক্যান্সার)"),
        "bkl": ("benign", "বেনাইন কেরাটোসিস-সদৃশ ক্ষত (নিরীহ ত্বকের দাগ)"),
        "df": ("benign", "ডার্মাটোফাইব্রোমা (নিরীহ ত্বকের নোডিউল)"),
        "mel": ("malignant", "মেলানোমা (গুরুতর ত্বকের ক্যান্সার)"),
        "nv": ("benign", "মেলানোসাইটিক নেভাস (সাধারণ তিল)"),
        "vasc": ("benign", "ভাসকুলার লেসন (রক্তবাহী দাগ)"),
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
        # বাংলা ক্যাপশন: "শুধু উদাহরণ; এই ছবি রোগনির্ণয় নিশ্চিত করতে পারে না।"
        self.assertContains(response, "এই ছবি রোগনির্ণয় নিশ্চিত করতে পারে না")
