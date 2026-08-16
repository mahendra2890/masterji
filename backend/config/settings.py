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
    # Above whitenoise and everything below it, because a request that did not
    # come through our edge should cost this process a string compare and
    # nothing else — no static file read, no session load, no database. Below
    # SecurityMiddleware so an http:// caller still gets the redirect it would
    # have got before, rather than learning about this gate instead.
    "accounts.middleware.EdgeSecretMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Directly above the ceiling below it, because the value it prints is the
    # value that ceiling keys on and the two should not be able to drift.
    # Costs one attribute lookup per request while it is off, which is the
    # default and should be the steady state — see LOG_FORWARDED_HEADERS.
    "accounts.middleware.ForwardedHeaderLogMiddleware",
    # Inside the session/CSRF layers, so it only counts POSTs that actually
    # reached the admin's login view — a request rejected for a missing CSRF
    # token never checked a password and is not a guess.
    "accounts.middleware.AdminLoginThrottleMiddleware",
    # In front of every view rather than on each one, because the hole a
    # read-only rule can develop is an endpoint written later by somebody who
    # did not know about it. Above the budget below so a refused write never
    # opens an LLM budget it is not going to spend.
    "accounts.middleware.ImpersonationReadOnlyMiddleware",
    # Innermost, so the budget starts as close to the view as possible: the
    # seconds this bounds are the ones spent talking to a provider, not the
    # ones Django spends on sessions and CSRF.
    "coach.middleware.LlmBudgetMiddleware",
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
# Response headers a cross-origin reader may see. Only one, and it earns it: the
# record export names its own file, and without this the client cannot read that
# name and would have to keep a second copy of the naming rule — two names for
# one file depending on whether you fetched it from the app or with curl.
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
# Admin login posts to the API's own origin — trust it too.
if RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

# The secret that tells our own edge apart from the open internet, and so the
# thing that makes DRF_NUM_PROXIES above a measurement rather than a guess.
# Vercel's proxy.ts attaches it to everything it forwards; this process refuses
# anything else. accounts.middleware.EdgeSecretMiddleware is the whole of it,
# and its docstring is the argument.
#
# Empty is inert, deliberately: local development, this test suite, and any
# deployment that has not adopted it are all unaffected — and none of them has
# a second door to close either. Once it IS set, it is required; there is no
# middle state where a missing header is waved through.
#
# Set it on Cloud Run and in Vercel's environment TOGETHER — see
# DEPLOY-cloudrun.md §8, which gives the order that has no window in which one
# side has rotated and the other has not.
#
# `.strip()` for the reason DATABASE_URL above removes whitespace: this value
# is pasted into a dashboard by hand at least once, and a trailing newline is
# invisible in every UI that will show it back to you. Both sides of a string
# compare must match byte for byte, so a stray "\n" on either one is a 403 for
# the entire API with nothing anywhere saying why. A secret whose leading or
# trailing whitespace is load-bearing is not a thing anybody wants, so there is
# no cost to this and one very expensive failure avoided. proxy.ts trims its
# side for the same reason.
EDGE_SHARED_SECRET = os.environ.get("EDGE_SHARED_SECRET", "").strip()

# How many proxies sit between a client and this process — and therefore what
# every anonymous throttle in this file is actually keyed on. Unset by default,
# and that is a decision rather than an omission. Read this before setting it.
#
# UNSET is what the deployment has always run. DRF's `BaseThrottle.get_ident`
# then returns `''.join(xff.split())` — the WHOLE `X-Forwarded-For` header,
# including whatever the client themselves put at the front of it. So an
# anonymous caller who varies that header lands in a fresh bucket every request
# and meets no ceiling at all (#255).
#
# That is not one small public read endpoint. Every scope below that is reached
# without a session goes through this one function:
#
#   * `changelog`   — ChangelogView and SharedRecordView, both AllowAny
#   * `cohort_join` — the code lookup
#   * `login`       — POST /api/auth/token/, guarding the operator's password
#   * and accounts.middleware.AdminLoginThrottleMiddleware, which calls the
#     same `get_ident` by hand for /admin/login/
#
# The last two are the ones that make this worth care. They guard a CREDENTIAL,
# and a credential ceiling that a header can step around is decoration.
#
# WHAT WAS MEASURED, on 15 August 2026, against the live deployment:
#
#   1. Cloud Run REPLACES `X-Forwarded-Proto`. A request to the run.app host
#      carrying `X-Forwarded-Proto: http` was served (404 on a missing path),
#      not answered with the 301 that SECURE_SSL_REDIRECT would have produced
#      had Django seen anything but "https".
#   2. Cloud Run PASSES THROUGH the `X-Forwarded-*` headers it does not manage.
#      `X-Forwarded-Host: evil.example` to the run.app host came back 400 —
#      Django's ALLOWED_HOSTS refusing a host it could only have read from the
#      forged header. Through the Vercel domain the same request was 200, so
#      Vercel normalises that header and Cloud Run does not.
#   3. The forgeability is REAL on the run.app host. Eleven wrong-password
#      POSTs to /api/auth/token/ from one address earned a 429 on the twelfth —
#      and then twelve more from that same, already-refused address, each with
#      a different `X-Forwarded-For`, were all answered 401. The ceiling was
#      walked around with one header.
#   4. Through the primary domain the ceiling does not bind AT ALL. Thirty-two
#      consecutive wrong-password POSTs to
#      https://masterji.mscsoftwares.in/api/auth/token/ — fixed client, no
#      header of our own — never produced a 429. The key is varying on
#      something the client never sent, which is what a per-request Vercel
#      egress address in the joined header would do.
#
# WHY THERE WAS NO NUMBER TO SET. `get_ident` with this set returns
# `xff.split(',')[-n]`, so `n` has to be the count of proxies that append, and
# for as long as the run.app host answered anonymous requests this deployment
# had two counts rather than one:
#
#   * Browsers arrive browser → Vercel → Cloud Run → Django.      (2 append)
#   * The Cloud Run URL was ALSO publicly reachable, so an attacker could
#     choose the shorter chain — and an attacker is the only caller who
#     gets to pick.                                               (1 appends)
#
# Set it to 1 and the direct path was fixed while the Vercel path keyed on
# Vercel's egress address; set it to 2 and the direct path stayed forgeable.
# Too high re-opens the forgery; too low puts every visitor behind the proxy in
# one bucket, where one attacker refuses everybody. A guess was worse than the
# honest gap, which is why this stayed unset through #255.
#
# WHAT CHANGED. EDGE_SHARED_SECRET below closes the second door: with it set,
# accounts.middleware.EdgeSecretMiddleware refuses anything that did not come
# through our own edge, so every request that now reaches a throttled endpoint
# has crossed the same chain (#317). The count is a measurement again.
#
# DEMOTED, 16 August 2026 — read this first. Since #334 the anonymous ceilings
# do NOT key on this number. They key on `accounts.throttling.trusted_ident`,
# which reads the one header Vercel writes and a caller cannot, and that module
# carries the measurement and the argument.
#
# What is left for this setting is the FALLBACK: `trusted_ident` returns DRF's
# own answer when the trusted header is absent, which is local development, the
# test suite, the two exempt direct callers, and any deployment without the
# edge gate. Everything below is still true of that fallback and still worth
# reading — it is simply no longer what stands in front of the password.
#
# Kept rather than deleted for that reason. Removing it would not simplify
# anything; it would just make the fallback silently key on the whole joined
# header again, which is the worst of the options priced below.
#
# THE NUMBER IS 2, AND 2 DOES NOT BUY WHAT IT LOOKS LIKE IT BUYS. Read this
# before trusting any anonymous ceiling in this file. Measured 15 August 2026.
#
# The reading that produced it — LOG_FORWARDED_HEADERS=1, one page load through
# masterji.mscsoftwares.in:
#
#   path=/api/auth/me/  xff='152.59.127.247,13.233.186.70'  ident='152.59...'
#
# Two entries: the browser, then an AWS Mumbai address where Vercel's bom1
# egress sits. `[-2]` is the browser, so 2 looked correct and was pinned.
#
# THAT READING WAS INCOMPLETE, and the correction matters more than the number.
# A browser never sends `X-Forwarded-For`, so the page load above could only
# ever exercise the benign case. Sending one deliberately, same day, same path:
#
#   xff='203.0.113.20,13.233.186.70'  ident='203.0.113.20'   <-- OUR value
#
# STILL TWO ENTRIES. Vercel does not append the client's address when the
# client already supplied the header — it forwards theirs and only Google's
# front end appends. So the `[-2]` slot holds the real browser only for callers
# who did not think to write it, and belongs to anyone who did.
#
# Confirmed end to end rather than inferred, 20 requests each against the live
# login ceiling, one client, back to back:
#
#   fixed header     6/20 got through
#   rotating header  14/20 got through
#
# WHY 2 IS STILL SET, WHICH IS NOT THE SAME AS IT BEING RIGHT. Unset keys on
# the whole joined header, and the second entry — Vercel's egress — VARIES PER
# REQUEST (13.233.186.70 then 3.110.215.22, one second apart, same browser).
# That is the mechanism behind measurement 4 above, which recorded 32 wrong
# passwords producing no 429 and could not say why. So unset binds on nobody at
# all, while 2 binds correctly on every caller who does not forge. 1 is worse
# than both: `[-1]` is that rotating egress address, useless as a key and
# shared by every visitor at once.
#
# 2 is the best of three bad options and none of them is a working credential
# ceiling. NUM_PROXIES cannot express one on this topology, because there is no
# position in this header that Vercel guarantees. That is a property of the
# forwarding behaviour, not a number nobody has found yet.
#
# THE FIX IS NOT A NUMBER. proxy.ts is already a trusted edge — the gate below
# means nothing reaches this process any other way, and it already overwrites a
# client-supplied header rather than appending to it. The same `set` can stamp
# the true client address, which Vercel exposes to it in headers the client
# cannot write, and the throttles can key on that instead. Filed as its own
# issue out of this finding; until it lands, treat every anonymous ceiling here
# as bounding accidents rather than attackers.
#
# ANY OTHER DEPLOYMENT MUST SET THE VARIABLE. 2 describes the
# Vercel → Google front end → Cloud Run chain and nothing else. Render's chain
# is shorter and has never been measured, so if that service is ever
# unsuspended it needs its own reading rather than this default.
#
# AND IF YOU RE-MEASURE: send a forged `X-Forwarded-For` as well as loading a
# page. The benign reading and the adversarial one disagree here, and only one
# of them is about security.
# THE INTERLOCK, and it is the reason the default is conditional rather than a
# plain 2. With the run.app door open, 2 is forgeable by a second route as well
# as the one above: `X-Forwarded-For: a, b` sent straight to that host makes
# `[-2]` the attacker's own `b`, with no Vercel involved at all. Closing the
# door does not make 2 sound — the correction above stands — but it does remove
# the cheaper of the two ways past it.
#
# Written as a condition rather than a comment because the dangerous window is
# real and narrow: this constant ships in a commit, and the secret is set by
# hand in two dashboards afterwards. Anything that made the repository's
# correctness depend on somebody doing those in the right order would be
# trusting a runbook to hold an invariant that costs one line to hold here.
#
# So: no edge secret, no trusted proxy count. A deployment that has not closed
# its second door goes on keying the way it always has, and the moment it does
# close it, the measured count applies with no second deploy. DRF_NUM_PROXIES
# in the environment overrides both, which is how any other chain sets its own.
_num_proxies = os.environ.get("DRF_NUM_PROXIES", "").strip()
DRF_NUM_PROXIES = int(_num_proxies) if _num_proxies else (2 if EDGE_SHARED_SECRET else None)


REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # None until somebody measures it — the block above is the whole argument.
    "NUM_PROXIES": DRF_NUM_PROXIES,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Reads the httpOnly access-token cookie, falls back to the
        # Authorization: Bearer header (curl, tests, other API clients).
        "accounts.authentication.CookieJWTAuthentication",
    ],
    # Ceilings on the three endpoints that spend money, scoped per user, plus
    # one on the only endpoint reachable without an account. Generous multiples
    # of real use: an honest evening is a handful of turns, one proof and one or
    # two readings of the morning's task. Nothing here is a coaching limit — it
    # is the budget that every honest builder's verdict comes out of.
    #
    # No default rate: an endpoint that costs nothing should not be able to
    # refuse anybody by inheriting one, and the ones that need a ceiling say so
    # by name. Declaring is deliberately absent — see DeclareView.
    #
    # `changelog` is the odd one, and it is bounding a different thing: it costs
    # no model call, it is simply the only endpoint here reachable without an
    # account, and a public surface with no ceiling of any kind is one whose
    # size somebody else decides. So it is a brake on hammering, not a fair-use
    # quota, and the number is picked with that asymmetry in mind — a script
    # does thousands a minute and is stopped by anything in this range, while a
    # ceiling set too low costs a real visitor the changelog popup.
    #
    # Per minute rather than per hour because of what it keys on. With no user,
    # ScopedRateThrottle keys by address, and in production that address is
    # whatever the proxy chain leaves in X-Forwarded-For — the same chain this
    # file already trusts for X-Forwarded-Proto and -Host below. If a request
    # ever arrives without one, the bucket is shared by every signed-out
    # visitor at once, which is the case 300 is sized for: one page load is one
    # request, so it would take three hundred landing-page loads inside the same
    # minute, and the refusal then clears in sixty seconds rather than an hour.
    # Signed-in mounts are keyed by user pk and are never in that bucket at all
    # — the app shell is not rationed by what the landing page is doing.
    #
    # Counted in the default cache — see CACHES below for what that means about
    # the exactness of these numbers.
    # `cohort_join` is the third kind again, and narrower than `changelog`: it
    # costs no model call and it does need an account, but it is the one
    # endpoint here that looks a caller-supplied string up in a table. 31^8 is
    # not walkable at any rate, so this is not the security — it is that a
    # lookup surface with no ceiling is one whose size somebody else decides.
    # Sized for a builder mistyping a code off a slide a few times, which is
    # the only honest way to reach it twice.
    #
    # `login` is the fourth kind, and the only one here guarding a CREDENTIAL
    # rather than a budget or a public surface. POST /api/auth/token/ can
    # verify exactly one password in this deployment — the operator's superuser
    # from render.yaml — because every builder account is Google-only and
    # carries set_unusable_password(). Unmetered, it is an offline-speed
    # guessing oracle for the one credential that opens the admin.
    #
    # The number is not sized for honest use, because there is no honest use to
    # size it for: nothing in the app calls this endpoint, and the API clients
    # its docstring names ask for a token once and then hold it for fifteen
    # minutes. Ten an hour is generous for that and useless for guessing. Keyed
    # by address, the same as `changelog` and for the same reason — the caller
    # is unauthenticated by definition here.
    #
    # /admin/login/ needs the same ceiling and cannot have this one: it is
    # Django's own view, DRF's throttling never runs for it, and a scope on it
    # would be silently ignored. That half lives in
    # accounts.middleware.AdminLoginThrottleMiddleware.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/hour",
        "chat": "30/hour",
        "prove": "20/day",
        "judge": "40/day",
        "changelog": "300/min",
        "cohort_join": "20/hour",
        # The push opt-in. Generous because a browser legitimately
        # re-subscribes on visits (the endpoint can be rotated by the push
        # service at any time), and low enough that nothing can farm rows.
        "push": "60/hour",
    },
}

# Where the ceilings above do their counting.
#
# LocMemCache is per process, and start.sh runs gthread workers with more than
# one instance possible above them — so unset, "thirty chat turns an hour" is
# thirty per worker, and a cold start resets it. That is a real limit, not a
# fake one, but it is not the number the product says out loud.
#
# CACHE_URL moves the counters somewhere every process can see, and the numbers
# become exactly what they claim. Unset — local checkouts, the test suite, and
# the deploy as it stands — behaves precisely as it did before this block
# existed. Django's RedisCache takes the URL as its LOCATION, which is why
# `redis` is a dependency: the variable is meant to be a switch somebody flips
# in a dashboard, not a switch that then needs an image rebuilt behind it.
CACHE_URL = os.environ.get("CACHE_URL", "")

CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_URL,
        }
        if CACHE_URL
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

# The other half of the login ceiling: Django's admin login form, which DRF's
# throttling cannot see. Counted in the same cache as everything above, so the
# CACHE_URL caveat applies here word for word.
#
# Failures only, and a correct sign-in clears the counter — so this is a wall in
# front of guessing rather than a quota on signing in, and fumbling a password
# twice before typing it correctly costs nothing. Ten wrong guesses an hour from
# one address, matched to the `login` rate above so both password surfaces
# refuse at the same place.
#
# Once the ten are spent the wall is in front of the view, so the right password
# from that same address waits out the window too. That is the trade, and it is
# the right way round: a staff member locked out for an hour is recoverable, an
# unmetered guessing oracle for the admin credential is not.
# The one-request instrument for DRF_NUM_PROXIES above. Off, and meant to go
# back off: it writes the raw X-Forwarded-For — which is client addresses — to
# the log, so it is a measurement somebody takes deliberately and then stops
# taking. accounts.middleware.ForwardedHeaderLogMiddleware is the whole of it.
LOG_FORWARDED_HEADERS = os.environ.get("LOG_FORWARDED_HEADERS", "0") == "1"

ADMIN_LOGIN_MAX_FAILURES = int(os.environ.get("ADMIN_LOGIN_MAX_FAILURES", "10"))
ADMIN_LOGIN_FAILURE_WINDOW_S = int(
    os.environ.get("ADMIN_LOGIN_FAILURE_WINDOW_S", "3600")
)

# How long an operator's read-only view of a builder's account lasts. Nothing
# can end one early — there is no token blacklist in this deployment — so this
# number is the whole of the revocation story, which is why it is half an hour
# and not a working day. accounts/impersonation.py carries the argument.
IMPERSONATION_LIFETIME_S = int(os.environ.get("IMPERSONATION_LIFETIME_S", "1800"))

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

# Ceiling on what ONE REQUEST may spend on model calls, in seconds.
#
# LLM_TIMEOUT_S bounds a single call and nothing bounded their sum: litellm's
# num_retries=2 turns one 60s call into three, and a prove pays a link check
# before any of that. Roughly 180s of held thread, on a box that runs
# --workers 1 --threads 12 — twelve of those and the process answers nobody,
# an outage caused entirely by waiting politely for a provider that is already
# gone.
#
# The first call of a request always gets the full LLM_TIMEOUT_S, so nothing a
# builder does today gets faster or slower. What the budget takes away, it
# takes from what comes after: the retries go first, then the calls. Every
# caller here has a deterministic fallback — UNJUDGED, or the stream's own
# error line — so being refused early is always safe.
LLM_REQUEST_BUDGET_S = float(os.environ.get("LLM_REQUEST_BUDGET_S", "90"))

# The breaker: how many consecutive provider failures before the seam stops
# asking, and for how long it stops.
#
# The product already degrades correctly per call. What it could not do was
# degrade per SERVICE — during a wobble every request paid the full timeout on
# its way to the fallback it was always going to reach, so the graceful path
# arrived too slowly to keep the app up. After LLM_BREAKER_FAILURES in a row
# the seam refuses immediately for LLM_BREAKER_COOLDOWN_S, and then lets the
# next call through to find out whether the provider is back.
#
# Counted in the default cache, so this is shared exactly as far as CACHES is:
# with CACHE_URL set it is one breaker for the deployment, and without it one
# per process — still bounded, still better than paying the timeout every time.
LLM_BREAKER_FAILURES = int(os.environ.get("LLM_BREAKER_FAILURES", "4"))
LLM_BREAKER_COOLDOWN_S = int(os.environ.get("LLM_BREAKER_COOLDOWN_S", "30"))

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

# --- Web push: the evening nudge ------------------------------------------
# All three unset is the default and it means the feature is OFF, everywhere,
# with nothing half-wired: the subscribe endpoint answers 503, the client asks
# for no permission and draws no control, and the hourly tick refuses. That is
# deliberate — a push feature that silently half-works is one that asks a
# builder for notification permission it can never use, and notification
# permission is a thing a browser lets you spend exactly once.
#
# The keypair is VAPID (RFC 8292): it identifies this server to Google's and
# Mozilla's push services, so those services can rate-limit and block a sender.
# The private key is the whole of the authority to push to every subscription
# this app holds; the public key is handed to browsers on purpose. Generating
# them and where each one goes is DEPLOY.md §8. Nothing here has a default,
# because a default keypair is a published private key.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
# The `mailto:` a push service contacts if this sender starts misbehaving.
# Required by the spec, and it is genuinely read by humans at Mozilla — an
# address nobody answers is worth less than no push at all.
VAPID_CONTACT = os.environ.get("VAPID_CONTACT", "")

# What the hourly GitHub Actions tick authenticates with (#142). A shared
# secret in a header, not a cookie: the caller is a workflow, not a browser,
# and it has no session to hold.
#
# Unset does NOT mean "unauthenticated" — NudgeRunView refuses when this is
# empty, which is the difference between a feature that is off and a door that
# is open. Compared with hmac.compare_digest at the call site.
NUDGE_TOKEN = os.environ.get("NUDGE_TOKEN", "")
# Held while one push is delivered. The tick sends serially and inline, so the
# ceiling on a whole run is this times the number of live subscriptions — fine
# at this product's size, and the number to revisit before it isn't.
NUDGE_TIMEOUT_S = float(os.environ.get("NUDGE_TIMEOUT_S", "10"))

# --- Observability (optional; no-op when the endpoint is unset) ------------

OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
OTEL_EXPORTER_OTLP_API_KEY = os.environ.get("OTEL_EXPORTER_OTLP_API_KEY", "")

# --- Behind a reverse proxy in production -----------------------------------
#
# Everything in this block is gated on DEBUG, and the gate is the point: local
# development is plain HTTP on localhost, and a cookie marked Secure is a cookie
# the browser never sends back there — so an ungated SESSION_COOKIE_SECURE would
# lock the local admin out of its own login form, silently, with no error to
# read. `manage.py check --deploy` only ever runs against DJANGO_DEBUG=0, which
# is why it could report all of this missing while the app worked.
#
# What is hardened here is the DJANGO ADMIN's cookies — `sessionid` and
# `csrftoken`, which come from framework defaults. The app's own auth cookies
# were never in question: accounts/cookies.py sets `secure = not settings.DEBUG`
# by hand, so `access_token` and `refresh_token` have been Secure + HttpOnly +
# SameSite=Lax in production all along. Nothing below touches them.
#
# The admin login form is proxied onto the primary domain by next.config.ts, so
# a staff member signs in at masterji.mscsoftwares.in — and a staff session is
# read/write over every builder's record. That is what a session cookie readable
# on a downgraded plain-HTTP request would hand over.

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

    # security.W012 / security.W016 — the admin's two cookies, marked so the
    # browser only ever sends them over TLS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # security.W008. Safe behind Render's proxy only because
    # SECURE_PROXY_SSL_HEADER above tells Django to read X-Forwarded-Proto:
    # without it, every request would look like plain HTTP to the app, the
    # redirect would point at a URL the proxy answers the same way, and the
    # browser would follow it round in a loop.
    SECURE_SSL_REDIRECT = True
    # The health probe is the one caller that is not a browser and cannot
    # follow a redirect on the app's behalf. Render hits /api/health/ inside
    # its own network, where there is no X-Forwarded-Proto to read, so without
    # this exemption every probe would be answered with a 301 to https — and a
    # health check that stops seeing 200 is a service that stops taking
    # traffic. Django matches this against the path with the leading slash
    # already stripped.
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]

    # security.W004. An hour, deliberately, and not the year the documentation
    # reaches for. HSTS is the one setting here that cannot be taken back by a
    # deploy: once a browser has seen the header it refuses plain HTTP to this
    # host for the whole max-age, whatever the server later says. An hour is
    # long enough to be a real defence against a downgrade and short enough
    # that a mistake costs an afternoon rather than a year. Raise it — the env
    # var is here so that is a dashboard change, not a deploy — once every host
    # that answers on this domain is HTTPS-only and has been for a while.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))

    # SECURE_HSTS_INCLUDE_SUBDOMAINS and SECURE_HSTS_PRELOAD are deliberately
    # NOT set, which is why security.W005 and security.W021 are silenced below
    # rather than fixed. Both widen the same irreversible commitment past what
    # can be verified from inside this repository: includeSubDomains binds every
    # subdomain of the host serving the header, and preload asks browser vendors
    # to ship the rule baked in, where removal takes months. Turning either on
    # needs somebody who knows what else answers under this domain — which is a
    # DNS question, not a code one.
    SILENCED_SYSTEM_CHECKS = [
        "security.W005",  # HSTS includeSubDomains — declined, see above
        "security.W021",  # HSTS preload — declined, see above
    ]
