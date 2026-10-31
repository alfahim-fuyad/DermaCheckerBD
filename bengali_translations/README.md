# বাংলা অনুবাদ ফাইল সংগ্রহ — Bengali Translation Reference Files

এই ডিরেক্টরিতে DermaCheckerBD-এর Skin Health Library-এর প্রতিটি পেজের জন্য
আলাদা বাংলা অনুবাদ ফাইল রয়েছে। প্রতিটি ফাইলে সংশ্লিষ্ট পেজে প্রদর্শিত
সম্পূর্ণ বাংলা বিষয়বস্তু সংরক্ষিত আছে।

This directory contains a separate Bengali translation reference file for each
page of the Skin Health Library. Each file holds the full Bengali content
displayed on its corresponding page.

## ফাইল তালিকা / File List

### লাইব্রেরি হোমপেজ / Library homepage
- `01_library_homepage.md` — Skin Health Library হোমপেজ

### সাতটি HAM10000 ক্লাস ডিটেইল পেজ / Seven HAM10000 class detail pages
- `02_class_akiec.md` — AKIEC (Actinic Keratoses and Intraepidermal Carcinoma)
- `03_class_bcc.md` — BCC (Basal Cell Carcinoma)
- `04_class_bkl.md` — BKL (Benign Keratosis-like Lesions)
- `05_class_df.md` — DF (Dermatofibroma)
- `06_class_mel.md` — MEL (Melanoma)
- `07_class_nv.md` — NV (Melanocytic Nevus)
- `08_class_vasc.md` — VASC (Vascular Lesions)

### সাধারণ ত্বক স্বাস্থ্য নিবন্ধ / General skin health articles
- `09_article_abcde_rule.md` — ABCDE নিয়ম
- `10_article_sun_protection.md` — সূর্য সুরক্ষা
- `11_article_self_exam.md` — মাসিক ত্বক স্ব-পরীক্ষা
- `12_article_when_to_see_doctor.md` — কখন চর্ম বিশেষজ্ঞকে দেখাবেন

## মূল সোর্স ফাইল / Primary source files

মূল বাংলা বিষয়বস্তু নিচের ফাইলে সংরক্ষিত:
- `apps/education/content.py` — সাতটি HAM10000 ক্লাস ও চারটি নিবন্ধের বাংলা বিষয়বস্তু
- `templates/education/index.html` — হোমপেজ টেমপ্লেট
- `templates/education/detail.html` — ক্লাস ডিটেইল টেমপ্লেট
- `templates/education/article.html` — নিবন্ধ টেমপ্লেট
- `static/js/translations.js` — ক্লায়েন্ট-সাইড i18n অভিধান (UI স্ট্রিং)

## গুরুত্বপূর্ণ নোট / Important Notes

- চিকিৎসা সংক্ষিপ্তরূপ AKIEC, BCC, BKL, DF, MEL, NV, VASC অপরিবর্তিত রাখা হয়েছে।
- প্রাসঙ্গিক ক্ষেত্রে ইংরেজি চিকিৎসা পরিভাষা বন্ধনীতে দেওয়া হয়েছে।
- সমস্ত শিক্ষামূলক ও চিকিৎসাবিষয়ক disclaimer সংরক্ষিত আছে।
- URL, লেআউট, CSS, রঙ, ছবি বা কার্যকারিতা পরিবর্তন করা হয়নি।
