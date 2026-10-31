# DermaCheckerBD — Skin Cancer Prediction Website (Django)

An experimental, research-support prototype for skin-lesion analysis. Built as
a university CSE capstone. **Not a medical device. Predictions are unverified
and may be wrong.**

> ⚠️ **Medical disclaimer**: This prototype does NOT provide a medical diagnosis.
> If you are concerned about a skin lesion — especially one that is changing,
> bleeding, growing, or painful — consult a qualified dermatologist promptly.
> Do not delay professional evaluation based on this tool's output.

---

## What this project is

A Django web application that wraps a skin-lesion classification model with
practical, transparency-oriented features:

| Feature                       | What it does                                                              |
| ----------------------------- | -------------------------------------------------------------------------- |
| **Smart Photo Guide**         | Detects blur, exposure, framing, and skin-plausibility before prediction. |
| **AI Reliability Check**      | Runs predictions across mild image transforms; reports agreement %.      |
| **Multi-Image Disagreement**  | Compares predictions across N photos of the same lesion.                  |
| **Lesion Follow-up Tracker**  | Private per-user lesion records with a timeline + PDF summary.            |
| **Floating Assistant**        | Role-scoped chatbot. **Anonymous visitors get 7 predefined FAQs only** (no Gemini calls). Signed-in users get the full Gemini-powered assistant with their own dashboard summary. Staff get aggregate-only totals. Never diagnoses. |
| **Wrong-Input Protection**    | Flags non-skin / corrupt / out-of-range inputs before predicting.        |
| **Similar Case Explorer**    | Modular stub. Plug in a reference dataset to enable.                      |

The default prediction backend is the supplied fine-tuned HAM10000 ResNet50
Keras model. A deterministic mock backend remains available for tests and demos;
the ONNX backend is an optional integration point.

---

## Tech stack

- **Backend**: Python 3.12, Django 5.1, Django REST Framework
- **Frontend**: HTML5, CSS3, Bootstrap 5, vanilla JavaScript, Lucide icons
- **Database**: SQLite (local) → PostgreSQL via `DATABASE_URL` (production, e.g., Neon)
- **ML**: TensorFlow/Keras ResNet50, OpenCV, Pillow, NumPy
- **PDF**: ReportLab
- **AI assistant**: Google Gemini (`google-genai` SDK) — called server-side only, **only for authenticated users**
- **Static**: WhiteNoise (compressed, manifest-hashed)
- **WSGI**: Gunicorn (single worker, Render-compatible)
- **Deployment**: Render (Render Blueprint in `render.yaml`)

---

## Quick start (local development in VS Code)

```bash
# 1. Clone & cd in
git clone <your-repo-url> dermacheckerbd
cd dermacheckerbd

# 2. Create & activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
# For the bundled local Keras model:
pip install -r requirements-ml.txt
# For an API-only setup, install requirements.txt instead.

# 4. Configure environment
cp .env.example .env
# Windows PowerShell alternative: Copy-Item .env.example .env
# For local PostgreSQL, uncomment LOCAL_DB_* in .env and enter your local
# database password there. Leave them commented to use SQLite.
# Set ML_MODEL_BACKEND=mock for tests / demos that should not load TensorFlow.

# 5. Apply database migrations
python manage.py migrate

# 6. (Optional) Create an admin user
python manage.py createsuperuser

# 7. Run the development server
python manage.py runserver
```

Open <http://127.0.0.1:8000/> in your browser.

---

## Doctor follow-up queue

The doctor panel is available at `/doctors/panel/`. After migrations, an
administrator can create a Django auth group for doctors and grant it the
`Can access and manage the medical follow-up queue` permission. Add doctor
accounts to that group; the panel link then appears for those users. Priority
groups and review statuses are follow-up workflow aids, not diagnoses.

---

## Project layout

```
dermacheckerbd/              # Django project package (settings, urls, wsgi, asgi)
apps/                    # Local apps
  accounts/              # signup, login, profile, dashboard
  core/                  # home, about, how_it_works, privacy
  predictor/             # upload, predict, result, history, PDF report
  photo_guide/           # standalone image-quality checker
  reliability/           # standalone AI Reliability Check page
  multi_image/           # multi-image disagreement
  tracker/               # lesion follow-up tracker
  chatbot/               # floating assistant endpoint + FAQs
    views.py             # message_view: anonymous=FAQ-only, auth=full Gemini
    faqs.py              # 7 predefined multilingual FAQs (no AI calls)
  similar_cases/         # stubbed similar-case explorer
  common/                # shared services (no URLs, no models)
    services/
      prediction.py      # pluggable PredictionService (keras/mock/onnx)
      image_quality.py   # Smart Photo Guide checks
      reliability.py     # reliability check transforms
      multi_image.py     # multi-image disagreement
      gemini.py          # Gemini client wrapper + safe-mode fallback
      pdf_report.py      # ReportLab PDF report builder
      wrong_input.py    # wrong-input protection
      similar_cases.py   # modular stub
templates/               # Django templates (base, includes/, per-app dirs)
  includes/chatbot.html  # floating chatbot panel + anonymous FAQ quick-reply bar
static/                  # CSS, JS, images
  css/
    main.css             # entry point: ordered @imports of the modular files below
    predictor-result.css # prediction-result report page (loaded only by predictor/result.html)
    base/                # shared/global layer
      variables.css      # :root design tokens (colors, fonts, spacing, radius)
      reset.css          # box-sizing, html/body, headings, a, focus, skip-link
      typography.css     # placeholder (text rules kept in reset.css to preserve order)
      global.css         # navbar, footer, buttons, cards, badges, upload-area,
                         # result-banner, conf-bar, stat-block, qcheck, misc utility,
                         # privacy-note, empty-state, mobile tweaks, reduced-motion,
                         # lang-toggle, print styles
    core/core.css        # home page: hero, scan-panel, how-step
    accounts/accounts.css# auth-card + password-toggle (login/signup)
    chatbot/chatbot.css  # floating assistant: FAB, panel, header, messages, FAQ, form
    doctors/doctors.css  # doctors finder map UI + radar overlay + MapLibre popup
    education/education.css # HAM10000 class library cards + detail figures
    predictor/predictor.css # prediction loading overlay (stages, scan line, spinner)
    tracker/tracker.css  # timeline + btn-link-danger (tracker/detail)
    multi_image/multi_image.css    # placeholder (uses shared base/global classes)
    photo_guide/photo_guide.css    # placeholder (uses shared base/global classes)
    questionnaire/questionnaire.css # placeholder (uses shared base/global classes)
    reliability/reliability.css     # placeholder (uses shared base/global classes)
    similar_cases/similar_cases.css # placeholder (uses shared base/global classes)
    dashboard/dashboard.css         # placeholder (uses shared base/global classes)
  js/main.js             # global JS
  js/image-upload.js     # drag-and-drop upload component
  js/chatbot.js          # floating chatbot client (FAQ buttons + alignment)
media/                   # user uploads (gitignored)
  uploads/               # uploaded prediction images
  tracked/               # follow-up tracker photos
  reference/             # reference dataset for Similar Cases (when enabled)
scripts/                 # development scripts (smoke tests, etc.)
tests/                   # Django test suite
  _helpers.py            # in-memory skin-like test image generator
  test_chatbot_privacy.py# FAQ-only anonymous, Gemini prevention, IDOR, auth regression
  test_views.py          # auth, uploads, history, tracker, chatbot endpoint
  ... (see "Running tests" below for the full list)
db/                      # SQLite db + cache (gitignored)
.env / .env.example      # environment configuration
Procfile                 # Render/Heroku-style process file (single worker)
render.yaml              # Render Blueprint
runtime.txt              # Python version pin
requirements.txt
requirements-ml.txt          # optional TensorFlow/Keras inference dependencies
manage.py
```

---

## Configuration (environment variables)

| Variable                   | Default                                          | Notes                                                |
| -------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| `DJANGO_DEBUG`             | `True`                                           | Set `False` in production.                          |
| `DJANGO_SECRET_KEY`        | `dev-insecure-...`                               | Generate a long random string for production.       |
| `DJANGO_ALLOWED_HOSTS`     | `localhost,127.0.0.1,...`                        | Comma-separated. Render domain is auto-added.       |
| `DATABASE_URL`             | unset                                            | Hosted PostgreSQL connection string; SSL is required. |
| `CLOUDINARY_URL`           | unset locally                                    | Required when `DJANGO_DEBUG=False`; use `cloudinary://API_KEY:API_SECRET@CLOUD_NAME`. |
| `LOCAL_DB_HOST`            | unset                                            | Set to `127.0.0.1` to use PostgreSQL installed on your PC. |
| `LOCAL_DB_PORT`            | `5432`                                           | Local PostgreSQL port.                               |
| `LOCAL_DB_NAME`            | unset                                            | Local database name; required when `LOCAL_DB_HOST` is set. |
| `LOCAL_DB_USER`            | unset                                            | Local database user; required when `LOCAL_DB_HOST` is set. |
| `LOCAL_DB_PASSWORD`        | blank                                            | Local database password; keep it in your ignored `.env`. |
| `LOCAL_DB_SSLMODE`         | `disable`                                        | Local connection SSL mode; use `require` only if configured. |
| `ML_MODEL_BACKEND`         | `keras`                                          | `keras` / `mock` / `onnx` / `api`. Render uses `api`. |
| `ML_MODEL_PATH`            | attached `.keras` model                          | Path to the fine-tuned model file; defaults to `/tmp/dermacheckerbd/resnet50_finetuned_1791994962604.keras` when `MODEL_GDRIVE_URL` is set. |
| `MODEL_GDRIVE_URL`         | unset                                            | Optional public Google Drive share link. If the model is missing, it downloads at WSGI startup. |
| `AI_API_URL`               | local URL in development                         | Base URL for the seven-class API; Django sends `POST {AI_API_URL}/predict` with multipart field `file`. Required in production when `ML_MODEL_BACKEND=api`. |
| `AI_SKIN_API_URL`          | unset                                            | Base/tunnel URL or full endpoint for the separate skin/non-skin API. A root URL gets `AI_SKIN_API_PATH` appended; an explicit path is preserved. Required in production when `ML_MODEL_BACKEND=api`. |
| `AI_SKIN_API_PATH`         | `/api/check-skin`                                | POST route appended only when `AI_SKIN_API_URL` is a root URL. |
| `AI_SKIN_API_FILE_FIELD`   | `file`                                           | Multipart field name expected by the skin/non-skin API. |
| `AI_API_TOKEN`             | unset                                            | Optional bearer token for the seven-class API. Store it as a Render environment variable. |
| `AI_SKIN_API_TOKEN`        | `AI_API_TOKEN`                                   | Optional bearer token for the skin/non-skin API; falls back to `AI_API_TOKEN`. |
| `AI_API_TIMEOUT`           | `120` seconds                                    | Per-request timeout for both ML APIs. |
| `ML_MODEL_INPUT_SIZE`      | `224`                                            | Resize dimension used in preprocessing.             |
| `ML_MODEL_CLASSES`         | `akiec,bcc,bkl,df,mel,nv,vasc`                   | Must match the trained model's output order.        |
| `ML_MODEL_RESAMPLE`        | `BILINEAR`                                       | Resize filter; matches the supplied training pipeline. |
| `GEMINI_API_KEY`           | unset                                            | Leave unset to run chatbot in offline mode. **Anonymous visitors never trigger Gemini calls** even when this key is set; the key is only consulted for authenticated users. |
| `GEMINI_MODEL`             | `gemini-2.0-flash`                               | Model name.                                          |
| `GEOAPIFY_API_KEY`         | unset                                            | Optional key for Nearby Doctors and Hospitals.      |
| `DJANGO_SUPERUSER_USERNAME`| unset                                            | Set in Render to create the initial admin account.   |
| `DJANGO_SUPERUSER_PASSWORD`| unset                                            | Set in Render; at least 12 characters.              |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | unset                                          | Optional comma-separated trusted origins. Replit preview origins are allowed automatically in development only. |
| `CHATBOT_RATE_LIMIT`       | `10/m`                                           | django-ratelimit spec (10 messages/minute/IP). Applies to anonymous AND authenticated users. |
| `IMG_BLUR_THRESHOLD`       | `100.0`                                          | Laplacian-variance threshold for blur.              |
| `IMG_BRIGHTNESS_MIN/MAX`   | `40 / 220`                                       | Acceptable mean-intensity range.                    |
| `RELIABILITY_TRANSFORMS`   | `brightness_up,...,slight_rotation`              | Comma-separated transform names.                    |
| `SIMILAR_CASES_ENABLED`    | `False`                                          | Toggle Similar Case Explorer.                       |
| `IMAGE_RETENTION_DAYS`     | `0`                                              | 0 = keep forever.                                   |

### Render Django admin account

Set `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` in the Render
web service environment. The Render start command runs migrations and
`ensure_render_superuser`, which creates the account once and never changes an
existing account's password. Both values are required for the Render Blueprint
to start. The footer's **Admin** link opens `/admin/`; only staff users can sign
in there. Do not commit the password to the repository.

---

## Prediction model

The default model is `attached_assets/resnet50_finetuned_1791994962604.keras`,
a fine-tuned ResNet50 for the seven HAM10000 diagnosis classes. Keep the model
at that path or set `ML_MODEL_PATH` to its location. It is about 201 MB and
should not be committed to Git.

Inference converts each upload to RGB, resizes it to 224×224 with bilinear
interpolation, converts pixels back to `[0, 255]`, and applies
`tf.keras.applications.resnet50.preprocess_input` before calling the model.
Output order is `akiec,bcc,bkl,df,mel,nv,vasc`. The `.keras` model is loaded
once per application process on the first prediction, then reused.

The model file was provided with reported test metrics of 73.49% accuracy,
61.67% macro F1, and 95.77% macro AUC; those figures have not been independently
verified and do not establish clinical validity. This is an educational/research
prototype, not a medical diagnostic tool. Consult a qualified dermatologist or
healthcare professional for proper evaluation.

Set `ML_MODEL_BACKEND=mock` to use deterministic demo predictions instead.

---

## Floating chatbot — anonymous FAQ-only vs. authenticated full Gemini

The floating chatbot has two distinct paths enforced at the top of
`apps/chatbot/views.py:message_view()`:

### Anonymous (logged-out) visitors — FAQ-only, NO Gemini calls

- The visitor sees **7 predefined FAQ quick-reply buttons** in the chatbot
  panel. Clicking a button sends `{"faq_id": "..."}` and the server returns the
  canned answer for that FAQ (English or Bengali, matching the UI language).
- The visitor can also type a free-text question. The server matches it
  against the 7 FAQs (substring / keyword match). If a FAQ matches, the canned
  answer is returned. If nothing matches, a short guidance message is returned
  along with the FAQ list so the buttons can be re-rendered.
- Personal-data questions ("my dashboard", "my history", …) are redirected to
  a "please sign in" message — **still without calling Gemini**.
- The `GeminiService.chat` function is **never invoked** on the anonymous path,
  even when `GEMINI_API_KEY` is configured. This is enforced both in the view
  and verified by tests (`tests/test_chatbot_privacy.py::AnonymousFaqOnlyTests`).
- Anonymous responses include `"scope": "public"`, `"authed": false`, and either
  `"faq_id": "<id>"` (when a FAQ was answered) or `"faq_id": ""` (guidance /
  sign-in redirect). The guidance response also carries `"faqs": [...]` so the
  frontend can render the buttons.

### Authenticated (logged-in) users — full Gemini-powered chatbot

- All existing chatbot behavior is preserved: Gemini-powered general answers,
  the user's own dashboard summary (reconstructed from the authenticated
  request — never from browser-supplied data), and aggregate-only totals for
  staff / doctors with the medical-queue permission.
- The `faq_id` / `faqs` fields are NOT included on authenticated responses —
  the frontend hides the FAQ bar for logged-in users.
- When `GEMINI_API_KEY` is unset, the authenticated path falls back to the
  canned educational replies (existing behavior).

### The 7 predefined FAQs

The list lives in `apps/chatbot/faqs.py` and is intentionally kept at 7 items
so the button bar stays compact on mobile. Each FAQ has stable ids, English and
Bengali questions, and English and Bengali answers:

| id            | English question                          |
| ------------- | ----------------------------------------- |
| `what_is`     | What is DermaCheckerBD?                   |
| `accuracy`    | How accurate are the predictions?         |
| `photo_guide` | How do I upload a clear photo?            |
| `class_names` | What do the class names (mel, nv, bcc…) mean? |
| `disclaimer`  | Is this a medical diagnosis?              |
| `find_doctor` | How do I find a dermatologist nearby?     |
| `signup`      | How do I sign up or log in?               |

Use `apps.chatbot.faqs.list_faqs(language)` to get the id+question list, and
`get_faq_answer(faq_id, language)` to get a single answer.

### Chatbot UI alignment + responsive layout

- **Header layout** — title and avatar sit on the left (`.chatbot-head-id`),
  the **Clear** and **Close (X)** icon buttons sit horizontally on the right
  inside `.chatbot-head-actions { display: flex; flex-wrap: nowrap; gap: 0.4rem }`.
  This rule is required: each `.chatbot-icon-btn` uses `display: flex` (so it
  is a block-level flex container); without the parent flex rule the two
  buttons stack vertically. Verified side-by-side on desktop (1280×900) and
  mobile (390×844). Styles live in `static/css/chatbot/chatbot.css`.
- **User messages** are right-aligned (`.chatbot-msg.user` → `justify-content: flex-end`;
  `.chatbot-msg.user .chatbot-msg-bubble { text-align: right }`). The JS also
  sets `bubble.style.textAlign = "right"` per bubble for extra robustness.
- **Chatbot replies** are left-aligned (`.chatbot-msg-bot` → `justify-content: flex-start`;
  `.chatbot-msg-bot .chatbot-msg-bubble { text-align: left }`).
- **Responsive mobile**: at `max-width: 480px` the panel becomes full-bleed
  (full width, 88vh height, top-rounded corners only). At `max-width: 360px`
  the bubble `max-width` increases to 92% so longer Bangla questions do not
  wrap awkwardly.
- **FAQ quick-reply buttons** wrap horizontally and use a pill style; on mobile
  they shrink to keep the bar readable.

### CSS architecture (modular per-app files)

Styles are split per Django app so you can edit one feature without searching
a monolithic stylesheet. `static/css/main.css` is now an entry point only —
it contains 11 ordered `@import` statements that pull in the modular files
in the same order the original `main.css` had them, so existing cascade
overrides continue to work unchanged.

- To change chatbot styling, edit `static/css/chatbot/chatbot.css`.
- To change the home hero / scan panel, edit `static/css/core/core.css`.
- To change the prediction-result report, edit `static/css/predictor-result.css`
  (this file is loaded separately by `templates/predictor/result.html` via its
  `extra_head` block; it is NOT `@import`ed by `main.css` to avoid double-load).
- Shared rules used by ≥2 apps live in `static/css/base/global.css`
  (navbar, footer, buttons, cards, badges, `upload-area`, `result-banner`,
  `stat-block`, `qcheck-*`, `medical-disclaimer`, `privacy-note`,
  `empty-state`, mobile tweaks, reduced-motion, print styles).
- Design tokens (colors, fonts, spacing, radius) live in
  `static/css/base/variables.css` as `:root` custom properties.

No Django template was modified to enable the split — the existing
`<link rel="stylesheet" href="{% static 'css/main.css' %}">` tag in
`templates/base.html` transparently pulls in every modular file. Comments
were stripped from all CSS files; only rule bodies, `@import`s,
`@keyframes`, `@media` blocks, and `:root` tokens remain.

---

## Enabling the live Gemini chatbot

1. Get a Gemini API key from <https://aistudio.google.com/app/apikey>.
2. Set `GEMINI_API_KEY=...` in your environment.
3. Restart the server. The floating chatbot will switch from offline canned
   responses to real Gemini calls — **but only for authenticated users**.
   Anonymous visitors continue to receive the 7 FAQs and never trigger a
   Gemini call.

The chatbot's system prompt (see `apps/common/services/gemini.py`) forbids
diagnosing cancer, prescribing medication, or promising a lesion is safe based
on the model output. Image bytes are never sent to Gemini — only text.

### Chatbot access and privacy

The floating assistant sends messages to Django; the browser never calls Gemini
directly. `GEMINI_API_KEY` stays on the server and should be stored in an
environment variable or the hosting platform's secrets manager, never in
frontend code or a committed file.

- **Visitors who are not signed in** can ONLY access the 7 predefined FAQs.
  Gemini is never called for them, so anonymous traffic cannot drive paid API
  usage. Requests for personal information are redirected to "please sign in".
- **Signed-in users** can ask about their own dashboard and recent activity.
  The server builds private context only from the authenticated account;
  browser-supplied dashboard data is not accepted.
- **Django staff and doctors with the medical follow-up queue permission** can
  ask for anonymized site-wide totals and trends, such as user, prediction, and
  tracked-lesion counts or prediction/review-status summaries. The assistant
  does not receive usernames, contact details, individual histories, or
  individual records, and it refuses requests to reveal them.

The chatbot is informational only and does not provide a diagnosis. Gemini
receives text conversation only; uploaded images are not sent to the API.

---

## Privacy, IDOR prevention, and ownership checks

Every endpoint that exposes personal data enforces Django authentication and
ownership. Cross-user access (Insecure Direct Object Reference, IDOR) is
blocked at every layer:

| Endpoint                                          | Auth required      | Ownership check                                                                                            |
| ------------------------------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------- |
| `GET /predict/result/<ref>/`                      | Owner or session   | `record.user == request.user` (or same `session_key` for anonymous). Staff with `view_medical_priority_queue` may view. Otherwise 403. |
| `GET /predict/result/<ref>/pdf/`                  | Owner or session   | Same as above. 403 on mismatch.                                                                            |
| `POST /predict/result/<ref>/delete/`              | Owner or session   | Same as above. 403 on mismatch. Record remains.                                                            |
| `GET /predict/history/`                           | Anyone             | Queryset scoped via `_scope_queryset()`: authenticated → own records; anonymous → own `session_key` records. |
| `GET /predict/history/?export=json`               | Anyone             | Same scope; capped at 200 records.                                                                          |
| `GET /tracker/`, `GET /tracker/<id>/`             | `@login_required`  | `LesionRecord.objects.filter(user=request.user)`; `get_object_or_404(..., user=request.user)`. Other users get 404. |
| `POST /tracker/<id>/add-photo/`                   | `@login_required`  | Same.                                                                                                       |
| `POST /tracker/<id>/delete/`                      | `@login_required`  | Same.                                                                                                       |
| `GET /tracker/<id>/summary.pdf`                   | `@login_required`  | Same.                                                                                                       |
| `GET /accounts/profile/`, `GET /accounts/dashboard/` | `@login_required` | All queries scoped to `request.user`.                                                                       |
| `POST /chatbot/message/`                          | Anyone             | Anonymous: FAQ-only, no Gemini. Authenticated: only `request.user`'s own dashboard summary is built; browser-supplied context is ignored. Staff: aggregate-only totals; individual records refused. |
| `GET /doctors/panel/`, `POST /doctors/.../review/` | `medical_queue_access_required` | Restricted to staff / queue-permission holders.                                                             |

Anonymous session-scoped prediction records are isolated by `session_key`; a
different browser session cannot view, delete, or export them. The chatbot
endpoint also ignores any browser-supplied `history` field — even if a
malicious user injects another user's reference id into the conversation
history, the server only builds context from the authenticated request.

---

## Low-RAM / low-CPU contract (Render single-worker compatible)

The deployment stays on Render's free / single-worker plan without any increase
in memory or CPU requirements:

- **Anonymous chatbot path is fully static.** FAQ answers are read from a
  Python list — no Gemini client init, no model load, no DB queries. RAM and
  CPU stay flat regardless of anonymous traffic.
- **Gemini client is lazy + cached.** `GeminiService._client` / `_model` are
  class-level attributes built on first authenticated chatbot call. There is
  no per-request client construction and no background worker.
- **No AI model is loaded into Django memory for the chatbot.** The chatbot
  sends text only; image classification lives behind the separate FastAPI
  `ML_MODEL_BACKEND=api` path on Render.
- **Bounded request sizes.** `DATA_UPLOAD_MAX_MEMORY_SIZE = 10 MB`,
  `FILE_UPLOAD_MAX_MEMORY_SIZE = 10 MB`. Chatbot messages are capped at 600
  characters. History is truncated to the last 10 messages server-side.
- **Efficient DB queries.** Chatbot dashboard summaries use `values() +
  annotate(Count)` instead of fetching full rows. Tracker / history lists use
  indexed `(user, -created_at)` and `(session_key, -created_at)` indexes.
- **No new heavy dependencies.** `requirements.txt` is unchanged; the FAQ
  module uses only the Python standard library + Django.
- **Single worker, no extra processes.** `Procfile` is unchanged:
  `gunicorn dermacheckerbd.wsgi:application --workers 1 --timeout 120`.

---

## Running tests

```bash
# Run the full suite (verbose)
python manage.py test tests -v2

# Run only the new chatbot privacy tests
python manage.py test tests.test_chatbot_privacy -v2

# Run only the existing chatbot endpoint tests
python manage.py test tests.test_views.ChatbotEndpointTests tests.test_views.LanguagePreferenceTests -v2
```

The suite is split across these files in `tests/`:

| File                          | What it covers                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| `test_chatbot_privacy.py`     | **NEW.** 40 tests: FAQ module, anonymous FAQ-only access, Gemini-call prevention for anonymous, authenticated full-Gemini preservation, template FAQ button rendering, IDOR prevention across predictor / tracker / chatbot, authenticated regression. |
| `test_views.py`               | Auth, uploads, prediction history, tracker privacy, chatbot endpoint (updated for the new anonymous contract). |
| `test_round2.py`              | History date validation, low-confidence banner, multi-image failures, tracker date validation, predictor access control, reliability low-confidence. |
| `test_services.py`            | Service-layer behavior (prediction, image quality, reliability, multi-image, wrong-input, PDF).         |
| `test_skin_validation.py`    | Skin/non-skin API integration.                                                                          |
| `test_medical_queue.py`       | Doctor follow-up queue access control and review workflow.                                              |
| `test_storage_settings.py`    | Cloudinary storage backend configuration.                                                               |
| `test_geoapify.py`            | Nearby Doctors / Geoapify Places + Geocoding integration.                                               |
| `test_education.py`           | Skin Health Library content + views.                                                                    |

Smoke tests (run them with `python scripts/`):

- `scripts/smoke_test_services.py` — exercises the service layer directly.
- `scripts/http_e2e_test.py` — exercises the full HTTP pipeline against a
  running server (start the server first, then run the script).

### Test status

- **All chatbot-related tests pass** (57 tests across `test_chatbot_privacy.py`
  + `ChatbotEndpointTests` + `LanguagePreferenceTests`).
- The broader `tests/test_round2.py` file contains some pre-existing failures
  that are unrelated to the chatbot fix (predictor access-control status code
  mismatch, low-confidence banner threshold, reliability agreement when all
  transforms fail, malformed date handling). These were present in the project
  before the chatbot fix and are out of scope for "do not change anything else".

---

## Deployment to Render

### VS Code → GitHub → Render → Neon (Blueprint)

1. In Neon, create a PostgreSQL project and copy its **pooled** connection
   string. Keep it private.
2. In VS Code, commit and push this project to the GitHub `main` branch.
3. In Render, choose **New → Blueprint**, connect the GitHub repository, and
   select `render.yaml`. The Blueprint creates the web service; it does not
   create a database on Render.
4. When Render asks for environment values, set these on the web service:
   - `DATABASE_URL` — the Neon pooled connection string.
   - `DJANGO_SECRET_KEY` — a new, long random value (never the development
     placeholder).
   - `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` — your admin
     login; use a strong password of at least 12 characters.
   - `AI_API_URL` — the reachable HTTPS base URL of the seven-class API.
   - `AI_SKIN_API_URL` — the HTTPS tunnel/base URL or full endpoint for the skin/non-skin API. A root URL uses `/api/check-skin`.
   - `AI_SKIN_API_PATH` — defaults to `/api/check-skin`; only change it if the API exposes a different route.
   - `AI_SKIN_API_FILE_FIELD` — the multipart upload field expected by that API (defaults to `file`).
   - `AI_API_TOKEN` — only if the seven-class API requires bearer-token authentication.
   - `AI_SKIN_API_TOKEN` — only if the skin/non-skin API needs a different token; otherwise it falls back to `AI_API_TOKEN`.
   - `GEMINI_API_KEY` — optional; omit it to keep the assistant in offline mode. **Anonymous visitors never trigger Gemini calls** even when this is set; the key is only consulted for authenticated users.
   - `GEOAPIFY_API_KEY` — optional; only needed for Nearby Doctors.
5. Render deploys from `main` automatically after each push. The site health
   endpoint is `/healthz/`; Django admin is at `/admin/`.

The Blueprint sets `ML_MODEL_BACKEND=api`, so this website does not download or
load TensorFlow/model files. `requirements.txt` contains the web/API dependencies
only; `requirements-ml.txt` is for local Keras inference.

This Blueprint uses Render Free. Free web services do not support pre-deploy
commands, so the start command applies migrations and creates the admin before
starting one Gunicorn worker. These operations are safe to repeat on a single
instance. Render Free services can sleep when idle; use a paid plan and a
pre-deploy migration command if you later need always-on service or multiple
instances.

### Persistent image storage in production

Production requires a `CLOUDINARY_URL` deployment secret and uses Cloudinary
for uploaded images. Set its value to the full URL in this form:
`cloudinary://API_KEY:API_SECRET@CLOUD_NAME`. In Render, enter only the URL as
the secret value—do not include `CLOUDINARY_URL=` or wrap it in quotes.

The URL must use the `cloudinary://` scheme. A missing URL or one with a
different scheme causes Django to stop during startup instead of silently
saving uploads to the ephemeral local filesystem. Local development continues
to use `MEDIA_ROOT` when the URL is unset. Never commit or share the Cloudinary
URL.

---

## Database migrations on Render

The Free-plan Blueprint runs `python manage.py migrate --noinput` before each
web process starts, with one worker/instance. On a paid Render plan, prefer
Render's `preDeployCommand` for migrations so database changes finish before
the new web process starts.

---

## Enabling the Similar Case Explorer

The feature is shipped stubbed (`SIMILAR_CASES_ENABLED=False`). To enable:

1. Place your reference image dataset (e.g., HAM10000) under a directory your
   app can read.
2. Pre-compute image embeddings for that dataset using a ResNet50 / CLIP /
   EfficientNet backbone. Store them as a numpy matrix + a list of
   `(image_id, label)` pairs.
3. Implement `_compute_embedding()` and `search()` in
   `apps/common/services/similar_cases.py`. The view layer is already wired up.
4. Set `SIMILAR_CASES_ENABLED=True` and `SIMILAR_CASES_REFERENCE_DIR=...`.

---

## Research evaluation protocol

The system is designed for measurable experiments. Two features in particular
support research:

1. **AI Reliability Check** — compare stability (agreement %) against
   baselines: max-softmax confidence, predictive entropy, expected calibration
   error. Evaluate whether low-stability predictions correlate with wrong
   predictions, especially for melanoma (`mel`).
2. **Multi-Image Disagreement** — evaluate whether significant disagreement
   across photos of the same lesion is a useful referral signal (i.e., a
   proxy for "this case is uncertain; refer to a dermatologist").

Suggested metrics: **sensitivity, specificity, macro-F1, confusion matrix,
expected calibration error (ECE), and Brier score**. Use patient- or
lesion-level separation where the dataset provides identifiers — prevent
data leakage between training and evaluation splits.

Do not fabricate experimental results. Run the evaluation on real data and
report the numbers honestly, even if they are unfavourable.

---

## Security & privacy summary

- HTTPS enforced in production; HSTS, secure cookies, X-Frame-Options DENY.
- CSRF on every form & state-changing request (including the chatbot endpoint).
- File type + size validation on every upload.
- Rate limiting on the chatbot endpoint (`10/m` per IP by default).
- API keys are read from environment variables — never exposed to the frontend.
- **Anonymous chatbot path never calls Gemini** — only the 7 predefined FAQs
  are returned, so anonymous traffic cannot drive paid API usage or load the
  Gemini client.
- **Authenticated chatbot path** builds context only from the authenticated
  request; browser-supplied context / history is never trusted.
- **Staff chatbot path** receives aggregate-only totals (no usernames, no
  individual records); requests for individual data are refused without calling
  Gemini.
- **Tracker records** are scoped to the requesting user (`get_object_or_404`
  with `user=request.user` filter) — there is no way to enumerate another
  user's records.
- **Prediction records** are scoped by `user` (authenticated) or `session_key`
  (anonymous). Cross-user / cross-session access returns 403. PDF download,
  delete, and JSON export all use the same scope.
- Image bytes are never sent to Gemini.
- `.env` is gitignored; `.env.example` contains placeholder values only.

---

## Acknowledgements

- **HAM10000** dataset: Tschandl, P., Rosendahl, C. & Kittler, H. (2018).
  _Scientific Data_. The class names and categories used in this project
  match the HAM10000 documentation.
- **Google Gemini** for the AI assistant SDK.
- **Bootstrap 5**, **Lucide icons**, **ReportLab**, **OpenCV**, **Pillow**.

---

## License

This project is provided as-is for educational purposes. It is NOT a medical
device. Use of the HAM10000 dataset, the Gemini API, and any other third-party
asset is subject to the respective upstream licenses.
