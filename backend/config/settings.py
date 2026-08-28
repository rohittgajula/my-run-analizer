"""Django settings.

Everything environment-dependent comes from the environment. Nothing here holds a
secret, a model name, or a threshold — those live in .env so they can change without
a code change, and so a bad value is a config bug rather than a deploy.
"""

import os
from datetime import timedelta
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
    # Bundled with simplejwt. Without it in INSTALLED_APPS *and* migrated,
    # ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION are silently inert:
    # the settings are accepted, logout appears to work, and nothing is revoked.
    "rest_framework_simplejwt.token_blacklist",
    # Project apps go here as you create them at M1. See docs/ROADMAP.md.
    "apps.athletes",
    "apps.ingest",
    "apps.activities",
    "apps.planning",
    "apps.coaching",
    "apps.journal",
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
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    # AllowAny does not mean unthrottled. These three are the public endpoints, and
    # an unthrottled login on a public host is found by scanners within days.
    "DEFAULT_THROTTLE_RATES": {
        "register": "5/hour",   # per IP
        "login": "10/hour",     # per IP — brute-force ceiling
        "refresh": "60/hour",   # per IP — generous; a 15-min access token refreshes often
        "garmin": "10/hour",    # per user — Garmin rate-limits by IP, see docs/HOSTING.md
        "ai": "30/day",         # per user — this one is money, see docs/COST.md
    },
}

# Access token: 15 minutes, held in JS memory only on the client.
# Refresh token: 7 days, in an httpOnly cookie the client cannot read.
# localStorage was rejected for either — XSS can read it, and a JWT stored there
# cannot be revoked on logout.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    # Without this, rotation issues a new refresh token and leaves the OLD one valid
    # for its full 7 days — a stolen one keeps working alongside the real one.
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

REFRESH_COOKIE_NAME = "refresh_token"
# Scoped so the cookie is not attached to every API call, only the auth endpoints.
REFRESH_COOKIE_PATH = "/api/auth/"

CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o
]
CORS_ALLOW_CREDENTIALS = True

# --- Celery ------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Redis-backed so the Garmin circuit breaker is shared across workers. A per-process
# cache would let each worker discover the rate limit separately, which is how you
# turn one block into several.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# A task that is retried must not double-write, so acks_late is paired with
# idempotent tasks rather than used to paper over non-idempotent ones.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Queue separation matters: a stuck AI call must not block the next Garmin sync, and
# Garmin work is deliberately serialised (see docs/HOSTING.md) while metrics are not.
CELERY_TASK_ROUTES = {
    "ingest.*": {"queue": "garmin"},
    "activities.*": {"queue": "metrics"},
    "coaching.*": {"queue": "ai"},
    "planning.*": {"queue": "planning"},
}

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "sync-every-morning": {
        "task": "ingest.sync_all",
        # Staggered inside the task by athlete id; this is only the window opening.
        "schedule": crontab(hour=5, minute=30),
    },
    "derive-anything-stale": {
        "task": "activities.derive_stale",
        "schedule": crontab(minute="*/20"),
    },
    "analyse-what-is-ready": {
        "task": "coaching.analyse_ready",
        "schedule": crontab(minute="*/30"),
    },
    "weekly-review-sunday-evening": {
        "task": "coaching.weekly_reviews",
        "schedule": crontab(hour=18, minute=0, day_of_week=0),
    },
}

# Queue separation matters from the start: a stuck AI call must not block the next
# Garmin sync. M7 routes tasks onto these.
CELERY_TASK_QUEUES_NAMES = ["garmin", "metrics", "ai", "planning"]

# --- Garmin ------------------------------------------------------------------
# Only the refreshable OAuth token is ever written here. The password is used once
# to obtain it and is never persisted, logged, or echoed back.
GARMIN_TOKEN_DIR = os.environ.get("GARMIN_TOKEN_DIR", "/app/.garmin")

# --- AI ----------------------------------------------------------------------
# One provider is active at a time. Operations name a TIER, never a model ID, so
# switching provider or upgrading a model is an .env edit rather than a code change.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Second provider, added at M6 to prove the abstraction seam is real.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Provider-neutral names: only one provider is live, and operations resolve through
# the tier map below rather than reaching for a vendor-specific setting.
AI_MODELS = {
    "lite": os.environ.get("AI_LITE_MODEL", ""),
    "fast": os.environ.get("AI_FAST_MODEL", ""),
    "coach": os.environ.get("AI_COACH_MODEL", ""),
    "deep": os.environ.get("AI_DEEP_MODEL", ""),
}

# journal_extract is deliberately NOT on `lite`. It reads casual, code-switched
# Hindi/English written straight after a run, and it is where pain gets detected —
# the hardest reading task in the system and the one with safety consequences.
AI_MODEL_TIERS = {
    "journal_extract": "fast",
    "guidance": "coach",
    "run_analysis": "fast",
    "weekly_review": "coach",
    "plan_generation": "coach",
    "monthly_review": "deep",
    "summary": "lite",
}

AI_TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "60"))
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "2"))

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
