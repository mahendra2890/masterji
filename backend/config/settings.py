"""Django settings — env-driven so the same code runs locally (SQLite, DEBUG)
and in a container behind a reverse proxy (Postgres, gunicorn, whitenoise).

Adapted from portfolio-fullstack; style and observability conventions from
Teotia-Sons/transcriber (fail-fast secrets in prod, loguru + OTel at runtime).
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local dev reads backend/.env; in containers real env vars win (dotenv
# never overrides variables that are already set).
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Fail fast in production: a missing secret should crash the boot, not limp
# along with an insecure default. Dev keeps friendly fallbacks.
if DEBUG:
    SECRET_KEY = os.environ.get(
        "DJANGO_SECRET_KEY", "django-insecure-dev-only-do-not-use-in-production"
    )
else:
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Render sets RENDER_EXTERNAL_HOSTNAME to the service's public hostname
# (<service>.onrender.com) — trust it without extra env config.
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "accounts",
    "coach",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

# Remove ALL whitespace from pasted connection strings — stray spaces or
# newlines make psycopg refuse to connect. Only the env value: the SQLite
# fallback path may legitimately contain spaces.
_db_url = os.environ.get("DATABASE_URL")
DATABASES = {
    "default": dj_database_url.parse(
        "".join(_db_url.split()) if _db_url else f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        # Serverless Postgres (Neon) drops idle connections on autosuspend;
        # ping before reuse so the first request after a pause doesn't 500.
        conn_health_checks=True,
    )
}

# Tests must never run against the remote DATABASE_URL: creating and
# migrating a test database on Neon takes minutes. Local SQLite is instant.
if "test" in sys.argv:
    DATABASES["default"] = dj_database_url.parse(
        f"sqlite:///{BASE_DIR / 'db.test.sqlite3'}"
    )

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

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- API / cross-origin ---------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
# The browser sends auth cookies cross-origin (3000 → 8000) only with this on
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
# Admin login posts to the API's own origin — trust it too.
if RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Reads the httpOnly access-token cookie, falls back to the
        # Authorization: Bearer header (curl, tests, other API clients).
        "accounts.authentication.CookieJWTAuthentication",
    ],
}

SIMPLE_JWT = {
    # Short-lived access token: if one leaks, the damage window is minutes.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Each refresh hands out a new refresh token, retiring the old one.
    "ROTATE_REFRESH_TOKENS": True,
}

# --- Auth cookies + Google OAuth -------------------------------------------

AUTH_ACCESS_COOKIE = "access_token"
AUTH_REFRESH_COOKIE = "refresh_token"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Where the OAuth callback sends the browser after login
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# --- LLM (litellm) ----------------------------------------------------------
# Provider optionality is this one string: "openai/gpt-5.4-mini" today,
# "anthropic/claude-sonnet-5" tomorrow. The provider's key rides the env
# vars litellm already understands (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...).

LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-5.4-mini")

# Reading a screenshot needs a vision-capable model, which is not necessarily
# the cheap one that handles chat. Its own setting so the two can diverge
# without a code change — same seam philosophy as LLM_MODEL.
LLM_VISION_MODEL = os.environ.get("LLM_VISION_MODEL", LLM_MODEL)

# Ceiling on any single model call, in seconds. Without one, a hung provider
# call holds a gunicorn thread indefinitely — on the free instance that is how
# the health check starts timing out. Every LLM path here has a deterministic
# fallback, so timing out is always safe: the caller degrades, the thread
# comes back.
LLM_TIMEOUT_S = int(os.environ.get("LLM_TIMEOUT_S", "60"))

# --- Proof screenshots: Cloudflare R2 (S3-compatible) -----------------------
# Entirely optional. With these unset, screenshot proofs are simply off and
# every other path behaves exactly as before — so production keeps working
# until the bucket exists. Chosen over Neon Object Storage (Aug 2026) because
# that is still in beta with unpublished limits; S3 compatibility means
# switching later is an endpoint change, not a rewrite.

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_ENDPOINT = (
    os.environ.get("R2_ENDPOINT")
    or (R2_ACCOUNT_ID and f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com")
    or ""
)

# Bounds on what a builder may upload as proof. Small on purpose: a screenshot
# of a chat, a commit or a dashboard is well under this, and anything larger
# is not the evidence we asked for.
PROOF_IMAGE_MAX_BYTES = 5 * 1024 * 1024
PROOF_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")

# --- Observability (optional; no-op when the endpoint is unset) ------------

OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_API_KEY = os.environ.get("OTEL_EXPORTER_OTLP_API_KEY", "")

# --- Behind a reverse proxy in production -----------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
