import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

# ---------------------------------------------------------------------------
# Security: SECRET_KEY must be set explicitly. No fallback = crash on startup
# if forgotten. This prevents accidental deployment with a known placeholder.
# See SECURITY.md Rule 4.
# ---------------------------------------------------------------------------
_secret_key = os.getenv("DJANGO_SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "DJANGO_SECRET_KEY environment variable is not set. "
        'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))" '
        "and add it to your .env file."
    )
SECRET_KEY = _secret_key

# ---------------------------------------------------------------------------
# Security: DEBUG defaults to False. You must explicitly set DJANGO_DEBUG=True
# in .env for local development. This prevents accidental debug exposure.
# See SECURITY.md Rule 4 and SEC-003.
# ---------------------------------------------------------------------------
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "investigations",
]

# CORS — allow the frontend origin(s) to call the API directly.
CORS_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
CORS_ALLOW_CREDENTIALS = True

# CSRF — SEC-024: Allow the React SPA to read the csrftoken cookie so it
# can include it as an X-CSRFToken header on write requests.
CSRF_COOKIE_HTTPONLY = False  # JS must be able to read the cookie
CSRF_COOKIE_SAMESITE = "Lax"  # standard protection against cross-site POST

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise must come right after SecurityMiddleware
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # SEC-025: before auth so abusive IPs are blocked early
    "investigations.middleware.RateLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "investigations.middleware.TokenAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# SEC-025: Rate limiting — per-IP request caps.
# Set to "0/minute" to disable a limit.
RATE_LIMIT_READ = os.getenv("RATE_LIMIT_READ", "200/minute")
RATE_LIMIT_WRITE = os.getenv("RATE_LIMIT_WRITE", "30/minute")

ROOT_URLCONF = "catalyst.urls"

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

WSGI_APPLICATION = "catalyst.wsgi.application"
ASGI_APPLICATION = "catalyst.asgi.application"

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------
# Railway (and similar platforms) provide a DATABASE_URL env var.
# If present, use it. Otherwise fall back to individual env vars for local dev.
# ---------------------------------------------------------------------------
_database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
if _database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    _db_password = os.getenv("DB_PASSWORD", "")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "catalyst_db"),
            "USER": os.getenv("POSTGRES_USER", "catalyst_user"),
            "PASSWORD": _db_password,
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5433"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static Files — WhiteNoise serves these in production
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Additional directories for collectstatic to find files.
# The frontend build output goes here so Django can serve the React SPA.
# The ("frontend", path) tuple tells collectstatic to put the files
# under staticfiles/frontend/ so they match the /static/frontend/ URL.
STATICFILES_DIRS = []
_frontend_dist = BASE_DIR / "static" / "frontend"
if _frontend_dist.exists():
    STATICFILES_DIRS.append(("frontend", str(_frontend_dist)))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

IS_TESTING = any(arg.startswith("test") for arg in sys.argv)
UPLOAD_PIPELINE_FORCE_ENABLE = os.getenv("ENABLE_UPLOAD_PIPELINE_LOGS", "False").lower() == "true"

if UPLOAD_PIPELINE_FORCE_ENABLE:
    UPLOAD_PIPELINE_LOG_LEVEL = "INFO"
elif DEBUG or IS_TESTING:
    # Keep local dev and tests quiet by default.
    UPLOAD_PIPELINE_LOG_LEVEL = "WARNING"
else:
    # Production default: emit structured upload decision logs.
    UPLOAD_PIPELINE_LOG_LEVEL = "INFO"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "upload_json": {
            "()": "investigations.logging_utils.JsonKeyValueFormatter",
        },
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "upload_pipeline_console": {
            "class": "logging.StreamHandler",
            "formatter": "upload_json",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "investigations.upload_pipeline": {
            "handlers": ["upload_pipeline_console"],
            "level": UPLOAD_PIPELINE_LOG_LEVEL,
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "investigations": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# API Token Authentication (SEC-001)
# ---------------
