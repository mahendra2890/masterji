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
    # Ceilings on the three endpoints that spend money, scoped per user (they
    # all require auth, so there is no anonymous bucket to fill). Generous
    # multiples of real use: an honest evening is a handful of turns, one proof
    # and one or two readings of the morning's task. Nothing here is a coaching
    # limit — it is the budget that every honest builder's verdict comes out of.
    #
    # No default rate: an endpoint that costs nothing should not be able to
    # refuse anybody by inheriting one, and the three that do cost say so by
    # name. Declaring is deliberately absent — see DeclareView.
    #
    # Counted in the default cache, which is LocMemCache until a shared one is
    # configured: with more than one process serving, the ceiling is per
    # process rather than per user. That is a weaker limit than it reads, not a
    # broken one, and it wants a shared cache before it can be quoted exactly.
    "DEFAULT_THROTTLE_RATES": {
        "chat": "30/hour",
        "prove": "20/day",
        "judge": "40/day",
    },
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

# The model that reaches VERDICTS, as opposed to the one that talks.
#
# Not the same job, and the difference is what it costs to be wrong. A weak turn
# of conversation is a weak turn of conversation; a wrong verdict either banks a
# proof that isn't there or sends a builder who did the work away to rewrite it,
# and the second one is how this product loses people. Two calls decide
# something recorded on the row — the evening's accept / push_back, and the
# morning's on_phase / off_phase plus the tailored proof_ask that the evening is
# then judged against.
#
# It is also where instruction-following is under the most load. Those prompts
# carry the bar, the substance rule, the respect rule, the prior tries, the
# stalemate diagnosis, the banked record and the evidence fence — every failure
# in this product's own bug history (three quotes counted as one, a topic
# refused that nobody raised, a fact asked for twice) is a rule that was in the
# prompt and didn't land.
#
# Defaults to LLM_MODEL, so unset changes nothing and today's deploy behaves
# exactly as it did.
#
# The step to reach for is the NON-MINI SIBLING of whatever LLM_MODEL names —
# "openai/gpt-5.4" against the default above. Same provider, so OPENAI_API_KEY
# is the only key involved and this is one env var and no code. The
# cross-provider example on LLM_MODEL is about provider optionality and reads,
# wrongly, as though upgrading the judge meant switching vendor; it doesn't, and
# that misreading cost a round trip once already.
#
# Whatever it names must be VISION-CAPABLE, because LLM_VISION_MODEL falls back
# to it (see below) and a judge that cannot see would silently break screenshot
# proofs. Cost is ~3x per token on these two calls and nothing else — the chat
# carries the volume and stays on LLM_MODEL — which at the prompt sizes here is
# cents per builder per month.
LLM_JUDGE_MODEL = os.environ.get("LLM_JUDGE_MODEL", LLM_MODEL)

# Reading a screenshot needs a vision-capable model, which is not necessarily
# the cheap one that handles chat. Its own setting so the two can diverge
# without a code change — same seam philosophy as LLM_MODEL.
#
# Defaults to the JUDGE model, not the chat one, because the only thing that
# ever sends an image is the evening's verdict on a proof — vision here is a
# judging path that additionally has to see. Chaining it this way means setting
# LLM_JUDGE_MODEL alone upgrades both halves of the verdict; a screenshot
# silently kept being graded by the cheap model would be the exact trap this
# setting exists to remove. Set it explicitly to override.
LLM_VISION_MODEL = os.environ.get("LLM_VISION_MODEL", LLM_JUDGE_MODEL)

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

# Bounds on the text a builder may send, for the same reason as the image cap
# above and one more: every one of these lands inside a fenced block in a
# prompt, so an unbounded paste is a prompt-stuffing surface as well as a bill.
#
# Sized to the writing each box is actually for, which is why they differ by an
# order of magnitude. A night's proof can honestly be several paragraphs — the
# conversation notes VALIDATION asks for are long — while a declaration is one
# task in one sentence, and a cap that let it run to eight thousand characters
# would be no cap at all on the one field the whole day is judged against.
CHAT_MAX_CHARS = 8000
PROOF_MAX_CHARS = 8000
DECLARATION_MAX_CHARS = 1000

# --- Proof links: does the thing the builder linked actually answer? --------
# Short, and for the same reason LLM_TIMEOUT_S exists: this runs inline in the
# prove path and holds a gunicorn thread while it waits. Two requests at most,
# so the worst case is twice this — still an order of magnitude under the model
# call that follows it, and coach.links degrades to "unchecked" on timeout, so
# spending the thread is always optional.
LINK_CHECK_TIMEOUT_S = float(os.environ.get("LINK_CHECK_TIMEOUT_S", "3"))
# Named rather than anonymous: a builder reading their own access log should be
# able to tell who knocked, and a host that wants to refuse us can.
LINK_CHECK_USER_AGENT = "MasterjiProofCheck/1.0 (+https://github.com/mahendra2890/masterji)"

# --- Observability (optional; no-op when the endpoint is unset) ------------

OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_API_KEY = os.environ.get("OTEL_EXPORTER_OTLP_API_KEY", "")

# --- Behind a reverse proxy in production -----------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
