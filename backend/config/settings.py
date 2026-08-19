"""Django settings.

Everything environment-dependent comes from the environment. Nothing here holds a
secret, a model name, or a threshold — those live in .env so they can change without
a code change, and so a bad value is a config bug rather than a deploy.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(int(default))).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    # Project apps go here as you create them at M1. See docs/ROADMAP.md.
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "runanalizer"),
        "USER": os.environ.get("POSTGRES_USER", "runanalizer"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "runanalizer"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT_INTERNAL", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{v}"}
    for v in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

LANGUAGE_CODE = "en-us"

# Deliberately UTC. Every athlete-facing date goes through the athlete's own
# local-today helper instead — Django's localdate() at 00:48 in Kolkata still
# returns yesterday, which silently mis-files a run and its journal entry.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Set from day one. Without it the admin loses its CSS the moment DEBUG=0, and you
# find that out during a deploy rather than now.
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o
]
CORS_ALLOW_CREDENTIALS = True

# --- Celery ------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Queue separation matters from the start: a stuck AI call must not block the next
# Garmin sync. M7 routes tasks onto these.
CELERY_TASK_QUEUES_NAMES = ["garmin", "metrics", "ai", "planning"]

# --- Garmin ------------------------------------------------------------------
# Only the refreshable OAuth token is ever written here. The password is used once
# to obtain it and is never persisted, logged, or echoed back.
GARMIN_TOKEN_DIR = os.environ.get("GARMIN_TOKEN_DIR", "/app/.garmin")

# --- AI ----------------------------------------------------------------------
# Model IDs are never hardcoded anywhere in application code. Operations name a
# TIER; the tier resolves to an ID here. Upgrading a model is an .env edit.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini")

AI_MODELS = {
    "lite": os.environ.get("GEMINI_LITE_MODEL", ""),
    "fast": os.environ.get("GEMINI_FAST_MODEL", ""),
    "coach": os.environ.get("GEMINI_COACH_MODEL", ""),
    "deep": os.environ.get("GEMINI_DEEP_MODEL", ""),
}

AI_MODEL_TIERS = {
    "journal_extract": "lite",
    "run_analysis": "fast",
    "weekly_review": "coach",
    "plan_generation": "coach",
    "monthly_review": "deep",
    "summary": "lite",
}

AI_TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "60"))
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "3"))

# --- Training safety ---------------------------------------------------------
# Thresholds live here, not scattered through the planner. Every one of these is a
# conservative choice open to review, not a universal law.
TRAINING = {
    "MAX_WEEKLY_INCREASE_PCT": float(os.environ.get("MAX_WEEKLY_INCREASE_PCT", "10")),
    "MAX_HARD_SESSIONS_PER_WEEK": int(os.environ.get("MAX_HARD_SESSIONS_PER_WEEK", "2")),
    "MIN_RECOVERY_DAYS_AFTER_HARD": int(os.environ.get("MIN_RECOVERY_DAYS_AFTER_HARD", "2")),
    "MAX_LONG_RUN_PCT_OF_WEEK": float(os.environ.get("MAX_LONG_RUN_PCT_OF_WEEK", "35")),
    "MIN_BUILD_WEEKS": int(os.environ.get("MIN_BUILD_WEEKS", "4")),
    "CUTBACK_EVERY_N_WEEKS": int(os.environ.get("CUTBACK_EVERY_N_WEEKS", "4")),
    "CUTBACK_FACTOR": float(os.environ.get("CUTBACK_FACTOR", "0.7")),
    # Prediction stays silent below this. A point estimate off six runs is fiction.
    "MIN_RUNS_FOR_PREDICTION": int(os.environ.get("MIN_RUNS_FOR_PREDICTION", "8")),
    "MIN_WEEKS_FOR_PREDICTION": int(os.environ.get("MIN_WEEKS_FOR_PREDICTION", "3")),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
