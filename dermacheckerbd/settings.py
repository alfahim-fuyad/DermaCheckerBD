"""
Django settings for dermacheckerbd (Skin Cancer Prediction Website).

Environment-driven configuration:
- Local dev: SQLite + debug
- Production (Render/Neon): PostgreSQL via DATABASE_URL, secure cookies, WhiteNoise

 NEVER commit real secrets to git. Use .env locally, Render env vars in prod.
"""
from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- Core ---
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-secret-key-change-me-in-production-please-32chars",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "localhost,127.0.0.1,0.0.0.0,.onrender.com,.replit.dev",
).split(",")
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS += [RENDER_EXTERNAL_HOSTNAME]

# Replit serves preview requests through pike.replit.dev origins, often on
# port 5000. Allow those browser origins for Django's CSRF check, plus any
# explicitly configured deployment origins.
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        "https://*.pike.replit.dev:5000",
        "https://*.replit.dev:5000",
    ]
for domain_var in ("REPLIT_DEV_DOMAIN", "REPLIT_DOMAINS"):
    for domain in os.environ.get(domain_var, "").split(","):
        domain = domain.strip()
        if domain:
            origin = domain if "://" in domain else f"https://{domain}"
            CSRF_TRUSTED_ORIGINS.append(origin)
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

# --- Apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd-party
    "rest_framework",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_ratelimit",
    # Local apps
    "apps.common",
    "apps.core",
    "apps.accounts",
    "apps.predictor",
    "apps.photo_guide",
    "apps.reliability",
    "apps.multi_image",
    "apps.tracker",
    "apps.chatbot",
    "apps.similar_cases",
    "apps.education",
    "apps.questionnaire",
    "apps.doctors",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "dermacheckerbd.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.feature_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "dermacheckerbd.wsgi.application"
ASGI_APPLICATION = "dermacheckerbd.asgi.application"

# --- Database ---
# DATABASE_URL wins for hosted databases. A separate LOCAL_DB_* configuration
# supports a native PostgreSQL installation on a developer's own computer
# without changing the Replit preview's SQLite default.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL and not DATABASE_URL.startswith("file:"):
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)}
elif DATABASE_URL.startswith("file:"):
    # Honor an explicitly configured SQLite file URL.
    sqlite_path = DATABASE_URL[len("file:"):]
    sqlite_path = "/" + sqlite_path.lstrip("/") if not sqlite_path.startswith("/") else sqlite_path
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_path,
        }
    }
elif os.environ.get("LOCAL_DB_HOST", "").strip():
    local_db_name = os.environ.get("LOCAL_DB_NAME", "").strip()
    local_db_user = os.environ.get("LOCAL_DB_USER", "").strip()
    if not local_db_name or not local_db_user:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "LOCAL_DB_NAME and LOCAL_DB_USER are required when LOCAL_DB_HOST is set."
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": local_db_name,
            "USER": local_db_user,
            "PASSWORD": os.environ.get("LOCAL_DB_PASSWORD", ""),
            "HOST": os.environ["LOCAL_DB_HOST"].strip(),
            "PORT": os.environ.get("LOCAL_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "sslmode": os.environ.get("LOCAL_DB_SSLMODE", "disable").strip(),
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db" / "db.sqlite3"),
        }
    }

# --- Auth ---
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization ---
LANGUAGE_CODE = "en-us"
LANGUAGES = [
    ("en", "English"),
    ("bn", "বাংলা"),
]
LANGUAGE_COOKIE_NAME = "derma_lang"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static & Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Default primary key field ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (django-ratelimit prefers Redis/Memcached; we use LocMem for dev) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dermacheckerbd-dev",
    }
}

# django-ratelimit system checks: LocMemCache does not support atomic increment.
# For local dev (single worker), this is acceptable. In production, switch CACHES
# to Redis or Memcached. See README for production cache setup.
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]

# --- Crispy ---
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# --- Security (production hardening) ---
if not DEBUG:
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "True").lower() in ("1", "true", "yes")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"

# --- File upload limits ---
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB hard ceiling
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Project-specific feature flags & config ---

# ML model integration
# 'keras' = fine-tuned ResNet50 model supplied with this project
# 'mock' = deterministic mock prediction backend for tests/demos
# 'onnx'  = optional ONNX backend (not bundled)
ML_MODEL_BACKEND = os.environ.get("ML_MODEL_BACKEND", "keras")
MODEL_GDRIVE_URL = os.environ.get("MODEL_GDRIVE_URL", "").strip()
_MODEL_FILENAME = "resnet50_finetuned_1791994962604.keras"
if MODEL_GDRIVE_URL:
    _DEFAULT_MODEL_PATH = (
        Path(os.environ.get("MODEL_CACHE_DIR", "/tmp/dermacheckerbd"))
        / _MODEL_FILENAME
    )
else:
    _DEFAULT_MODEL_PATH = BASE_DIR / "attached_assets" / _MODEL_FILENAME
ML_MODEL_PATH = os.environ.get(
    "ML_MODEL_PATH",
    str(_DEFAULT_MODEL_PATH),
)
ML_MODEL_INPUT_SIZE = int(os.environ.get("ML_MODEL_INPUT_SIZE", "224"))
ML_MODEL_CLASSES = os.environ.get(
    "ML_MODEL_CLASSES",
    "akiec,bcc,bkl,df,mel,nv,vasc",
).split(",")
ML_MODEL_RESAMPLE = os.environ.get("ML_MODEL_RESAMPLE", "BILINEAR")

# FastAPI prediction endpoint (used when ML_MODEL_BACKEND=api).
# Local dev:  http://127.0.0.1:8000  (FastAPI on port 8000, Django on 8001+)
# Production: set AI_API_URL to your deployed FastAPI service's public URL.
AI_API_URL = os.environ.get(
    "AI_API_URL",
    "http://127.0.0.1:8000",
)
# Optional bearer token if your FastAPI service requires authentication.
AI_API_TOKEN = os.environ.get("AI_API_TOKEN", "").strip()
# Per-request timeout (seconds) for the FastAPI /predict call.
AI_API_TIMEOUT = int(os.environ.get("AI_API_TIMEOUT", "120"))

# HAM10000 class -> full medical name mapping (used for display)
HAM10000_CLASS_NAMES = {
    "akiec": "Actinic Keratoses / Bowen's Disease",
    "bcc": "Basal Cell Carcinoma",
    "bkl": "Benign Keratosis-like Lesions",
    "df": "Dermatofibroma",
    "mel": "Melanoma",
    "nv": "Melanocytic Nevi",
    "vasc": "Vascular Lesions",
}
HAM10000_CLASS_CATEGORY = {
    "akiec": "pre malignant",
    "bcc": "malignant",
    "bkl": "benign",
    "df": "benign",
    "mel": "malignant",
    "nv": "benign",
    "vasc": "benign",
}

# Gemini chatbot
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
CHATBOT_RATE_LIMIT = os.environ.get("CHATBOT_RATE_LIMIT", "10/m")  # 10 msgs/min/user
CHATBOT_SESSION_TTL = int(os.environ.get("CHATBOT_SESSION_TTL", "1800"))  # 30 min

# Image quality thresholds (Smart Photo Guide)
IMG_MIN_DIMENSION = int(os.environ.get("IMG_MIN_DIMENSION", "200"))
IMG_MAX_DIMENSION = int(os.environ.get("IMG_MAX_DIMENSION", "4096"))
IMG_BLUR_THRESHOLD = float(os.environ.get("IMG_BLUR_THRESHOLD", "100.0"))  # Laplacian variance
IMG_BRIGHTNESS_MIN = int(os.environ.get("IMG_BRIGHTNESS_MIN", "40"))
IMG_BRIGHTNESS_MAX = int(os.environ.get("IMG_BRIGHTNESS_MAX", "220"))

# Reliability check transforms (comma-separated names)
RELIABILITY_TRANSFORMS = os.environ.get(
    "RELIABILITY_TRANSFORMS", "brightness_up,brightness_down,contrast_up,contrast_down,slight_rotation"
).split(",")

# Similar Case Explorer (modular; disabled by default)
SIMILAR_CASES_ENABLED = os.environ.get("SIMILAR_CASES_ENABLED", "False").lower() in ("1", "true", "yes")
SIMILAR_CASES_REFERENCE_DIR = os.environ.get(
    "SIMILAR_CASES_REFERENCE_DIR", str(BASE_DIR / "media" / "reference")
)

# Image retention (days). 0 = keep forever.
IMAGE_RETENTION_DAYS = int(os.environ.get("IMAGE_RETENTION_DAYS", "0"))

# ---- Geoapify Places API (Nearby Doctors & Hospitals feature) ----
# Get a key from https://myprojects.geoapify.com/. The key is read
# server-side only; it is NEVER exposed to the browser. Leave empty to
# disable the search endpoints (the page still renders, but every search
# returns a clean "API not configured" message instead of crashing).
GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "").strip()
# Places API base URL. Override only if you have a private mirror.
GEOAPIFY_PLACES_URL = os.environ.get(
    "GEOAPIFY_PLACES_URL",
    "https://api.geoapify.com/v2/places",
)
# Geocoding API base URL (used to convert "Dhaka" -> lat/lon).
GEOAPIFY_GEOCODE_URL = os.environ.get(
    "GEOAPIFY_GEOCODE_URL",
    "https://api.geoapify.com/v1/geocode/search",
)
# Map tiles URL template (MapLibre GL JS vector tiles). The default uses
# Geoapify's OSM-based raster tiles which require the API key as a query
# parameter — that key is rendered into the page ONLY for the map style
# URL and is acceptable per Geoapify's terms because it is rate-limited
# per domain. For full key isolation, host your own tile server.
GEOAPIFY_MAP_TILES_URL = os.environ.get(
    "GEOAPIFY_MAP_TILES_URL",
    "https://maps.geoapify.com/v1/tile/osm-bright/{z}/{x}/{y}.png?apiKey={apiKey}",
)
# Default search radius (km) when the user does not pick one.
DOCTOR_SEARCH_RADIUS_KM = int(os.environ.get("DOCTOR_SEARCH_RADIUS_KM", "5"))
# Maximum results returned per search (Geoapify caps at 500 in one call;
# we use 20 to keep the page light).
DOCTOR_SEARCH_MAX_RESULTS = int(os.environ.get("DOCTOR_SEARCH_MAX_RESULTS", "20"))
# Per-request HTTP timeout (seconds) for both Places and Geocoding.
GEOAPIFY_TIMEOUT = int(os.environ.get("GEOAPIFY_TIMEOUT", "10"))
# Short-lived cache TTL (seconds). Avoids hammering Geoapify when a user
# clicks the same search twice. 300s = 5 minutes.
GEOAPIFY_CACHE_TTL = int(os.environ.get("GEOAPIFY_CACHE_TTL", "300"))

# Logging (privacy-conscious: do not log image content or PII)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
