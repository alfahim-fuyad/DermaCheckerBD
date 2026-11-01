# DermaCheckerBD — Skin-Lesion Analysis Prototype (Django)

An experimental, research-support prototype for skin-lesion analysis.
Built as a university CSE capstone project at East West University (EWU)
by AL Fahim Fuad and his team.

> **Medical disclaimer**: This prototype does **NOT** provide a medical
> diagnosis. If you are concerned about a skin lesion — especially one
> that is changing, bleeding, growing, or painful — consult a qualified
> dermatologist promptly. Do not delay professional evaluation based on
> this tool's output.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Key Features](#key-features)
3. [Technology Stack](#technology-stack)
4. [Project Architecture](#project-architecture)
5. [Installation & Local Setup](#installation--local-setup)
6. [Environment Variables](#environment-variables)
7. [Database Setup & Migrations](#database-setup--migrations)
8. [AI/ML Model & Prediction Workflow](#aiml-model--prediction-workflow)
9. [Multi-Provider Chatbot (Gemini → Groq → OpenRouter)](#multi-provider-chatbot-gemini--groq--openrouter)
10. [API Endpoints](#api-endpoints)
11. [Management Commands](#management-commands)
12. [Deployment (Render)](#deployment-render)
13. [Bengali / English i18n](#bengali--english-i18n)
14. [Testing](#testing)
15. [Troubleshooting](#troubleshooting)
16. [Limitations](#limitations)

---

## Project Overview

DermaCheckerBD is a Django 5 web application that wraps a fine-tuned
ResNet50 skin-lesion classification model (trained on the HAM10000
dataset) with practical, transparency-oriented features:

- **Image quality assessment** before prediction (blur, exposure, framing,
  skin-plausibility).
- **Skin/non-skin validation** gate — rejects non-skin uploads before the
  lesion classifier runs.
- **Seven-class prediction** with confidence scores and category labels
  (benign / malignant / pre-malignant).
- **Reliability check** — measures how stable the prediction is across
  mild image transforms (brightness, contrast, rotation).
- **Multi-image comparison** — upload 2–5 images and compare predictions
  side by side.
- **Lesion follow-up tracker** — authenticated users can track lesions
  over time with photos and notes.
- **Multi-provider AI chatbot** — Gemini (primary) → Groq (secondary) →
  OpenRouter (tertiary) cascade with automatic failover, cooldowns, and
  usage logging.
- **Bengali + English UI** — full bilingual support with a client-side
  i18n layer.
- **Nearby doctors finder** — Geoapify Places API integration for
  finding dermatologists and hospitals.

The prototype is **not** a medical device. Every prediction is unverified
and may be wrong.

---

## Key Features

| Feature | Description |
| --- | --- |
| Smart Photo Guide | Checks blur, exposure, framing, and skin-plausibility before prediction runs. Optional automatic enhancement. |
| Skin Image Prediction | Fine-tuned ResNet50 classifies uploads into 7 HAM10000 classes. Skin/non-skin validation gate rejects non-skin images. |
| Reliability Check | Reports agreement percentage across mild image transforms (brightness, contrast, rotation). High agreement = stable, not necessarily correct. |
| Multi-Image Comparison | Upload 2–5 images and compare predictions side by side. |
| Lesion Tracker | Authenticated users track lesions over time with photos, body location, and notes. PDF summary export. |
| Multi-Provider Chatbot | Gemini → Groq → OpenRouter cascade with cooldowns, usage logging, and conversation persistence. 7 FAQs available to all users; AI replies require login. |
| Skin Health Library | Bengali + English educational articles for each of the 7 classes plus general skin-health topics. |
| Warning Signs Checker | Interactive ABCDE-rule questionnaire for self-assessment. |
| Nearby Doctors | Geoapify Places API search for dermatologists and hospitals by location and radius. |
| Doctor Panel | Staff-only review queue for predictions with follow-up status tracking. |
| PDF Reports | Downloadable prediction reports with image, class, confidence, quality, and reliability data. |
| Bilingual UI | Full Bengali (বাংলা) + English toggle. Server messages are translated client-side via a known-message table. |

---

## Technology Stack

| Layer | Technology |
| --- | --- |
| Backend | Django 5.2, Python 3.12 |
| Database | SQLite (local dev), PostgreSQL via Neon (production) |
| ML / Image | TensorFlow + Keras (ResNet50), Pillow, OpenCV (headless), NumPy |
| PDF | ReportLab + uharfbuzz (Bengali font support) |
| AI Chatbot | Google Gemini (google-genai SDK), Groq + OpenRouter (OpenAI-compatible HTTP via `requests`) |
| Rate Limiting | django-ratelimit (per-IP) |
| Forms | django-crispy-forms + crispy-bootstrap5 |
| Static Files | WhiteNoise (compressed manifest in production) |
| Image Storage | Local filesystem (dev), Cloudinary (production, optional) |
| Doctors Search | Geoapify Places + Geocoding APIs |
| Frontend | Vanilla JS + Bootstrap 5, client-side i18n dictionary |
| Server | Gunicorn (1 worker, 4 threads, `--max-requests 80` recycle) |
| Deployment | Render (free tier compatible) |

---

## Project Architecture

```
DermaCheckerBD-bengali-fixed/
├── manage.py
├── requirements.txt              # Python dependencies
├── runtime.txt                   # Python version for Render
├── Procfile                      # Gunicorn start command
├── render.yaml                   # Render Blueprint
├── .env.example                  # Environment variable template
│
├── dermacheckerbd/               # Django project package
│   ├── settings.py               # Environment-driven configuration
│   ├── urls.py                   # Root URL conf + health check
│   ├── wsgi.py / asgi.py
│   └── storage.py                # Media storage backend resolver
│
├── apps/                         # Django apps (one per feature area)
│   ├── core/                     # Home, About, How-it-works, Privacy
│   ├── accounts/                 # Signup, login, profile, dashboard
│   ├── predictor/                # Upload, result, history, PDF reports
│   ├── photo_guide/              # Smart Photo Guide (quality check)
│   ├── reliability/              # Prediction reliability check + dashboard
│   ├── multi_image/              # Multi-image comparison
│   ├── tracker/                  # Lesion follow-up tracker
│   ├── chatbot/                  # Multi-provider AI chatbot
│   │   ├── models.py             # ChatConversation, ChatMessage, ChatUsageLog
│   │   ├── faqs.py               # 7 predefined FAQs (en + bn)
│   │   ├── views.py              # Message, history, clear, providers, usage, diagnose
│   │   └── management/commands/  # test_chatbot_providers, clear_chat_cooldowns, keep_chatbot_warm
│   ├── education/                # Skin health library (7 class articles)
│   ├── questionnaire/            # ABCDE warning-signs checker
│   ├── doctors/                  # Nearby doctors finder + doctor panel
│   ├── similar_cases/            # Similar case explorer (disabled by default)
│   └── common/                   # Shared services
│       └── services/
│           ├── prediction.py     # PredictionService (keras/mock/onnx/api backends)
│           ├── image_quality.py  # ImageQualityService (blur, exposure, framing, skin ratio)
│           ├── wrong_input.py    # WrongInputService (corrupt/non-skin detection)
│           ├── reliability.py    # ReliabilityService (transform stability)
│           ├── ai_api.py         # FastAPI backend client + NonSkinImageError
│           ├── gemini.py         # GeminiService (delegates to fallback cascade)
│           ├── ai_providers/     # Multi-provider cascade package
│           │   ├── base.py       # BaseAIProvider + exception hierarchy
│           │   ├── cooldown.py   # CooldownTracker (Django cache)
│           │   ├── gemini_provider.py
│           │   ├── groq_provider.py
│           │   ├── openrouter_provider.py
│           │   └── fallback.py   # FallbackChatService orchestrator
│           ├── pdf_report.py     # ReportLab PDF generation
│           ├── geoapify.py       # Places + Geocoding API client
│           └── ...
│
├── templates/                    # Django templates
│   ├── base.html
│   ├── includes/                 # navbar, footer, chatbot widget
│   ├── core/                     # home, about, how_it_works, privacy
│   ├── predictor/                # upload, result, history
│   ├── photo_guide/              # quality_check + partials
│   ├── reliability/              # check, dashboard
│   ├── multi_image/              # compare
│   ├── tracker/                  # index, create, detail, confirm_delete
│   ├── education/                # index, detail, article
│   ├── questionnaire/            # questionnaire
│   ├── doctors/                  # finder, panel, access_denied
│   ├── registration/             # login, signup, profile, dashboard
│   └── 404.html / 500.html
│
├── static/
│   ├── css/                      # Modular per-app CSS
│   ├── js/                       # main.js, chatbot.js, translations.js, etc.
│   ├── fonts/                    # NotoSansBengali for PDF rendering
│   └── images/                   # Logo, class icons, scan demos
│
├── bengali_translations/         # Markdown source for Bengali education articles
├── tests/                        # Django test suite
└── scripts/                      # Dev/utility scripts (smoke tests, mock FastAPI)
```

---

## Installation & Local Setup

### Prerequisites

- Python 3.12+
- `pip` and `venv`
- (Optional) PostgreSQL for production-like local testing
- (Optional) Google Gemini / Groq / OpenRouter API keys for the chatbot

### Steps

```bash
# 1. Clone and enter the project
git clone <your-repo-url> DermaCheckerBD
cd DermaCheckerBD

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the environment template and fill in values
cp .env.example .env
# Edit .env — at minimum set DJANGO_SECRET_KEY and ML_MODEL_BACKEND

# 5. Run database migrations
python manage.py migrate

# 6. (Optional) Create a superuser for the admin
python manage.py ensuresuperuser   # or: python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

### Quick smoke test

```bash
# Verify the ML pipeline works end-to-end with the mock backend
ML_MODEL_BACKEND=mock python manage.py test_chatbot_providers

# Run the full test suite
python manage.py test tests
```

---

## Environment Variables

All configuration is environment-driven via `.env` (local) or the Render
dashboard (production). See `.env.example` for the complete list.

### Core Django

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_DEBUG` | `True` | Debug mode. Set `False` in production. |
| `DJANGO_SECRET_KEY` | (dev key) | Django secret key. **Must** be set when `DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,...` | Comma-separated allowed hosts. |
| `DATABASE_URL` | (empty → SQLite) | PostgreSQL URL for production (`postgres://user:pass@host:port/db`). |
| `CLOUDINARY_URL` | (empty → local) | Cloudinary URL for production image storage. |

### ML Model

| Variable | Default | Purpose |
| --- | --- | --- |
| `ML_MODEL_BACKEND` | `keras` | `keras` / `mock` / `onnx` / `api`. See [AI/ML Model](#aiml-model--prediction-workflow). |
| `ML_MODEL_PATH` | `attached_assets/...` | Path to the `.keras` model file. |
| `ML_MODEL_INPUT_SIZE` | `224` | Input dimension for the model. |
| `ML_MODEL_CLASSES` | `akiec,bcc,bkl,df,mel,nv,vasc` | Comma-separated class codes. |
| `AI_API_URL` | (empty) | FastAPI base URL when `ML_MODEL_BACKEND=api`. |
| `AI_SKIN_API_URL` | (empty) | Skin/non-skin validation API URL. |

### Chatbot (Multi-Provider Cascade)

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | (empty) | Google Gemini API key. Primary provider. |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model slug. |
| `GEMINI_TIMEOUT` | `8` | Per-call timeout (seconds). |
| `GROQ_API_KEY` | (empty) | Groq API key. Secondary provider. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model slug. |
| `GROQ_TIMEOUT` | `8` | Per-call timeout (seconds). |
| `OPENROUTER_API_KEY` | (empty) | OpenRouter API key. Tertiary provider. |
| `OPENROUTER_MODEL` | `openrouter/free` | OpenRouter model slug (auto-router). |
| `OPENROUTER_TIMEOUT` | `12` | Per-call timeout (seconds). |
| `CHATBOT_PROVIDER_ORDER` | `gemini,groq,openrouter` | Cascade order. |
| `CHATBOT_PROVIDER_COOLDOWN_SECONDS` | `30` | Cooldown after a retryable failure. |
| `CHATBOT_CASCADE_DEADLINE_SECONDS` | `15` | Total cascade time budget. |
| `CHATBOT_DEFER_PERSISTENCE` | `True` | Defer usage-log + conversation writes. |
| `CHATBOT_RATE_LIMIT` | `10/m` | Per-IP rate limit for chatbot messages. |

### Geoapify (Nearby Doctors)

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEOAPIFY_API_KEY` | (empty) | Geoapify API key. Leave empty to disable search. |

### Render Free-Tier Optimizations

Set these in the Render dashboard (NOT in `.env`):

```
MALLOC_TRIM_THRESHOLD_=65536     # reduces glibc malloc fragmentation
TF_CPP_MIN_LOG_LEVEL=3           # silences TensorFlow C++ logging
WEB_CONCURRENCY=1                # single gunicorn worker
```

---

## Database Setup & Migrations

### Local (SQLite)

The default `DATABASES` setting uses SQLite at `db/db.sqlite3`. No extra
setup is needed — `python manage.py migrate` creates the file.

### Production (PostgreSQL via Neon)

1. Create a PostgreSQL database on [Neon](https://neon.tech) (free tier).
2. Copy the connection string.
3. Set `DATABASE_URL` in the Render dashboard:
   ```
   DATABASE_URL=postgres://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require
   ```
4. The Procfile runs `python manage.py migrate --noinput` on every deploy.

### Models

| App | Model | Purpose |
| --- | --- | --- |
| `accounts` | `PatientProfile` | Patient contact + demographic details. |
| `predictor` | `PredictionRecord` | One per uploaded image. Stores class, confidence, image, review status. |
| `tracker` | `LesionRecord` | Tracked lesion with body location, label, notes. |
| `tracker` | `FollowUpPhoto` | Photos attached to a lesion record over time. |
| `chatbot` | `ChatConversation` | One per authenticated user. |
| `chatbot` | `ChatMessage` | Individual turns (user/model) within a conversation. |
| `chatbot` | `ChatUsageLog` | One row per provider attempt — for the staff usage view. |

---

## AI/ML Model & Prediction Workflow

### Model

- **Architecture**: Fine-tuned ResNet50 (ImageNet pretrained backbone).
- **Dataset**: HAM10000 (Tschandl et al.).
- **Input**: 224×224 RGB, normalized.
- **Output**: Softmax over 7 classes.

### Seven HAM10000 Classes

| Code | Full Name | Category |
| --- | --- | --- |
| `akiec` | Actinic Keratoses / Bowen's Disease | Pre-malignant |
| `bcc` | Basal Cell Carcinoma | Malignant |
| `bkl` | Benign Keratosis-like Lesions | Benign |
| `df` | Dermatofibroma | Benign |
| `mel` | Melanoma | Malignant |
| `nv` | Melanocytic Nevi | Benign |
| `vasc` | Vascular Lesions | Benign |

### Prediction Backends (`ML_MODEL_BACKEND`)

| Backend | RAM Use | When to Use |
| --- | --- | --- |
| `keras` | ~700 MB+ | Local dev with the bundled `.keras` model file. **Not suitable for Render free tier.** |
| `mock` | ~180 MB | Demos / chatbot-only deployments. Deterministic hash-based predictions. |
| `api` | ~200 MB | **Production.** Forwards to a separate FastAPI service that loads TensorFlow. |
| `onnx` | ~300 MB | Optional ONNX runtime (not bundled). |

### Prediction Workflow

1. User uploads an image on `/predict/` or `/quality/`.
2. **Skin/non-skin validation** — the image is sent to the
   `AI_SKIN_API_URL` endpoint. If classified as non-skin, the upload is
   rejected with a localized message.
3. **Wrong-input protection** — `WrongInputService` checks for corrupt
   files, extreme dimensions, and coarse skin-plausibility.
4. **Image quality assessment** (Smart Photo Guide only) — blur,
   exposure, framing, and skin-ratio are checked before prediction.
5. **Prediction** — `PredictionService.predict_pil()` runs the model and
   returns a `PredictionResult` with class, confidence, and probabilities.
6. **Reliability check** (optional) — the image is transformed (brightness,
   contrast, rotation) and the prediction is re-run. Agreement percentage
   measures stability.
7. **PDF report** — `PdfReportService` generates a downloadable report
   with the image, prediction, quality, and reliability data.

---

## Multi-Provider Chatbot (Gemini → Groq → OpenRouter)

### Access Contract

- **Anonymous users**: 7 predefined FAQs only. No AI provider is ever
  called. The FAQ list lives in `apps/chatbot/faqs.py`.
- **Authenticated users**: Full multi-provider AI cascade for free-text
  questions. Can also click FAQ buttons (7 Q&A available to all users).

### Cascade Flow

```
User message
    │
    ▼
GeminiService.chat (legacy entry point, patched in tests)
    │
    ▼
FallbackChatService.chat
    │
    ├─ 1. Build system prompt (staff / authenticated / public scope)
    ├─ 2. For each provider in CHATBOT_PROVIDER_ORDER:
    │      ├─ Skip if not configured
    │      ├─ Skip if on cooldown
    │      ├─ Call provider.chat()
    │      ├─ On success: log usage, persist conversation, return
    │      └─ On retryable error: set cooldown, try next provider
    └─ 3. If cascade deadline exceeded or all providers failed:
           return localized canned reply
```

### Error Detection

The `classify_http_error()` function maps HTTP status codes to specific
exception types:

| Status | Exception | Cooldown? |
| --- | --- | --- |
| 401 / 403 | `ProviderAuthError` | No (config error) |
| 402 | `QuotaExhaustedError` | Yes |
| 429 + "quota" in body | `QuotaExhaustedError` | Yes |
| 429 (plain) | `RateLimitError` | Yes |
| 400-4xx + "model not found" | `model_not_found` (non-retryable) | No |
| 400-4xx (other) | `client_error` | Yes |
| 500 / 502 / 503 / 504 | `ProviderServerError` | Yes |
| Timeout | `ProviderTimeoutError` | Yes |

### Model Name Deprecations (Late 2026)

AI providers retire model names frequently. The defaults are kept
current, but if you previously set env vars, check for deprecated values:

| Provider | Deprecated Model | Replacement |
| --- | --- | --- |
| Groq | `llama-3.3-70b-versatile` | `openai/gpt-oss-120b` |
| OpenRouter | `meta-llama/llama-3.1-8b-instruct:free` | `openrouter/free` |
| OpenRouter | `deepseek/deepseek-r1:free` | `openrouter/free` |

Run `python manage.py test_chatbot_providers` to verify — it prints a
deprecation warning if it detects retired model names.

### Diagnostic Endpoints

| Endpoint | Method | Access | Purpose |
| --- | --- | --- | --- |
| `/chatbot/message/` | POST | All users | FAQ button clicks (all users); AI cascade (authed only) |
| `/chatbot/history/` | GET | Login required | Persisted server-side conversation |
| `/chatbot/clear/` | POST | Login required | Clear persisted conversation |
| `/chatbot/providers/` | GET | Login required | Provider config + cooldown state |
| `/chatbot/usage/` | GET | Staff only | Recent `ChatUsageLog` rows + success-rate summary |
| `/chatbot/diagnose/` | GET | Staff only | Live-test each provider with a tiny prompt |

---

## API Endpoints

### Core Pages

| URL | View | Purpose |
| --- | --- | --- |
| `/` | `core:home` | Landing page |
| `/about/` | `core:about` | Project information |
| `/how-it-works/` | `core:how_it_works` | Workflow explanation |
| `/privacy/` | `core:privacy` | Privacy policy |

### Auth

| URL | View | Purpose |
| --- | --- | --- |
| `/accounts/signup/` | `account_signup` | New account creation |
| `/accounts/login/` | `login` | Django login |
| `/accounts/logout/` | `logout` | Django logout |
| `/accounts/profile/` | `account_profile` | Edit profile (login required) |
| `/accounts/dashboard/` | `account_dashboard` | User dashboard (login required) |

### Prediction

| URL | View | Purpose |
| --- | --- | --- |
| `/predict/` | `predictor:upload` | Upload image for prediction |
| `/predict/result/<ref>/` | `predictor:result` | View prediction result |
| `/predict/result/<ref>/pdf/` | `predictor:pdf_report` | Download PDF report |
| `/predict/result/<ref>/delete/` | `predictor:delete` | Delete prediction record |
| `/predict/history/` | `predictor:history` | Prediction history (login required) |
| `/predict/history/clear/` | `predictor:clear_history` | Clear history |

### Smart Photo Guide

| URL | View | Purpose |
| --- | --- | --- |
| `/quality/` | `photo_guide:quality_check` | Image quality assessment + transfer to prediction |

### Reliability

| URL | View | Purpose |
| --- | --- | --- |
| `/reliability/` | `reliability:check` | Run reliability check |
| `/reliability/dashboard/` | `reliability:dashboard` | Reliability dashboard |

### Multi-Image Comparison

| URL | View | Purpose |
| --- | --- | --- |
| `/multi/` | `multi_image:compare` | Compare 2–5 images |

### Lesion Tracker

| URL | View | Purpose |
| --- | --- | --- |
| `/tracker/` | `tracker:index` | List tracked lesions |
| `/tracker/new/` | `tracker:create` | Create new lesion record |
| `/tracker/<id>/` | `tracker:detail` | View lesion detail |
| `/tracker/<id>/add-photo/` | `tracker:add_photo` | Add follow-up photo |
| `/tracker/<id>/delete/` | `tracker:delete` | Delete lesion record |
| `/tracker/<id>/summary.pdf` | `tracker:summary_pdf` | Download lesion PDF |

### Education & Questionnaire

| URL | View | Purpose |
| --- | --- | --- |
| `/disease/` | `education:index` | Skin health library |
| `/disease/<code>/` | `education:detail` | Class detail page |
| `/disease/article/<slug>/` | `education:article` | Educational article |
| `/warning-signs/` | `questionnaire:form` | ABCDE warning signs checker |

### Doctors

| URL | View | Purpose |
| --- | --- | --- |
| `/doctors/` | `doctors:finder` | Nearby doctors search |
| `/doctors/search/` | `doctors:search` | Places API search |
| `/doctors/geocode/` | `doctors:geocode` | Geocode a location |
| `/doctors/panel/` | `doctors:panel` | Doctor review panel (staff) |

### Chatbot

See [Multi-Provider Chatbot](#multi-provider-chatbot-gemini--groq--openrouter).

### System

| URL | View | Purpose |
| --- | --- | --- |
| `/healthz/` | `health_check` | Lightweight health check for uptime monitors |
| `/admin/` | admin | Django admin |

---

## Management Commands

```bash
# Chatbot diagnostics
python manage.py test_chatbot_providers          # live-test each AI provider
python manage.py clear_chat_cooldowns [gemini]   # clear provider cooldowns
python manage.py keep_chatbot_warm --url https://your-app.onrender.com/healthz/

# Maintenance
python manage.py ensuresuperuser                 # create admin user
python manage.py prune_old_predictions           # delete old prediction records
python manage.py migrate                         # apply migrations
python manage.py collectstatic --noinput         # collect static files
```

---

## Deployment (Render)

### Option A: Render Dashboard (manual)

1. Create a new Web Service on [Render](https://render.com) connected to
   your Git repository.
2. Set the following:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Start Command**: (from Procfile)
     ```
     python manage.py migrate --noinput && python manage.py ensure_render_superuser && gunicorn dermacheckerbd.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 --graceful-timeout 10 --max-requests 80 --max-requests-jitter 40 --worker-tmp-dir /dev/shm --access-logfile -
     ```
3. Add environment variables (see [Environment Variables](#environment-variables)).
4. Create a Neon PostgreSQL database and set `DATABASE_URL`.

### Option B: Render Blueprint (`render.yaml`)

The repo includes a `render.yaml` Blueprint. Fork the repo, connect it to
Render, and Render will create the service automatically.

### Render Free-Tier RAM Optimization

The Render free tier has **512 MB RAM**. To stay within this limit:

1. **Do NOT use `ML_MODEL_BACKEND=keras`** — TensorFlow alone uses
   ~700 MB. Use `ML_MODEL_BACKEND=api` (forward to a separate FastAPI
   service) or `ML_MODEL_BACKEND=mock` (chatbot-only deployments).
2. Set these env vars in the Render dashboard:
   ```
   MALLOC_TRIM_THRESHOLD_=65536
   TF_CPP_MIN_LOG_LEVEL=3
   WEB_CONCURRENCY=1
   ```
3. The Procfile uses `--max-requests 80` to recycle the gunicorn worker
   periodically, releasing any leaked RAM.

### Preventing Cold Starts (Free Tier)

Render puts free-tier services to sleep after 15 minutes of inactivity.
The first request after sleep takes 30+ seconds. To prevent this:

- **Option A (recommended)**: Use [UptimeRobot](https://uptimerobot.com)
  or [cron-job.org](https://cron-job.org) to ping
  `https://your-app.onrender.com/healthz/` every 10 minutes.
- **Option B**: Add a Render Background Worker with start command:
  ```
  python manage.py keep_chatbot_warm --url https://your-app.onrender.com/healthz/ --interval 600
  ```

---

## Bengali / English i18n

The UI supports full Bengali (বাংলা) and English. A language toggle in
the navbar switches between them. The i18n layer is client-side:

- `static/js/translations.js` — Bengali dictionary keyed by translation
  keys (e.g. `'nav.home'`, `'predict.subtitle'`).
- `static/js/main.js` — applies translations to elements with
  `data-i18n`, `data-i18n-ph`, `data-i18n-title`, `data-i18n-aria`
  attributes. Captures the original English text on first run so it can
  be restored when switching back.
- **Server-rendered messages** (Django messages, upload errors) are
  translated via the `data-i18n-server` attribute. The
  `translateServerMessage()` function maps known English strings to
  translation keys. A new message is added by:
  1. Adding the key + Bengali value to `translations.js`.
  2. Adding the English→key mapping in `translateServerMessage()` in
     `main.js`.

The language preference is stored in a cookie (`derma_lang`).

---

## Testing

```bash
# Full test suite
python manage.py test tests

# Specific test modules
python manage.py test tests.test_chatbot_privacy
python manage.py test tests.test_views
python manage.py test tests.test_services

# Verbose
python manage.py test tests -v2
```

### Smoke Tests (standalone scripts)

```bash
# Test the multi-provider cascade with mocked providers
python scripts/smoke_test_fallback.py

# Test chatbot HTTP endpoints end-to-end
python scripts/smoke_test_chatbot_http.py

# Test cascade deadline + deferred DB writes
python scripts/smoke_test_deadline.py

# Test the ML prediction pipeline with the mock backend
python scripts/smoke_test_services.py
```

---

## Troubleshooting

### Chatbot returns "assistant is temporarily unavailable"

1. Run `python manage.py test_chatbot_providers` to test each provider.
2. Check for **deprecated model names** (the command prints a warning):
   - Groq: `llama-3.3-70b-versatile` → use `openai/gpt-oss-120b`
   - OpenRouter: `meta-llama/llama-3.1-8b-instruct:free` → use `openrouter/free`
3. Verify API keys are set in the Render dashboard.
4. Visit `/chatbot/diagnose/` (staff login required) for a live JSON
   diagnostic of each provider.

### Render "Memory quota exceeded"

- Do NOT use `ML_MODEL_BACKEND=keras`. Use `api` or `mock`.
- Set `MALLOC_TRIM_THRESHOLD_=65536` in the Render dashboard.
- Verify the Procfile uses `--max-requests 80`.

### Chatbot is slow

- Timeouts are tight (8s Gemini, 8s Groq, 12s OpenRouter) with a 15s
  total cascade deadline.
- The cascade deadline ensures the user never waits more than ~15s.
- If a provider is consistently slow, the cooldown (30s) skips it for
  subsequent requests.
- Run `python manage.py clear_chat_cooldowns` to reset all cooldowns.

### Cold starts (Render free tier)

Render sleeps free-tier services after 15 min of inactivity. Use
UptimeRobot to ping `/healthz/` every 10 minutes. See
[Preventing Cold Starts](#preventing-cold-starts-free-tier).

### Image upload rejected as "non-skin"

The skin/non-skin validation API (`AI_SKIN_API_URL`) rejected the image.
This is expected behavior for screenshots, diagrams, or non-skin photos.
Upload a clear photo of a skin lesion. If the API is not configured
(`ML_MODEL_BACKEND=mock` or `keras` without `AI_SKIN_API_URL`), the
validation step is skipped.

---

## Limitations

- **Not a medical device.** Every prediction is unverified and may be
  wrong. Consult a qualified dermatologist for any medical concern.
- **HAM10000 classes only.** The model recognizes 7 lesion types. It
  cannot identify conditions outside this set.
- **Dermoscopic images preferred.** Phone photos work but may produce
  less reliable results. The Smart Photo Guide helps assess quality.
- **No real OOD detector.** The wrong-input service uses a coarse
  skin-tone ratio heuristic. A real out-of-distribution detector is not
  shipped.
- **Free-tier rate limits.** Groq and OpenRouter free tiers have strict
  rate limits (20 RPM, 50-1000 RPD). For higher traffic, use paid models
  or run your own inference server with `ML_MODEL_BACKEND=api`.
- **Conversation persistence is per-user.** Anonymous visitors do not
  get server-side conversation history (they use sessionStorage in the
  browser). Only authenticated users get `ChatConversation` rows.
