"""Google OAuth 2.0 (authorization-code flow, confidential client).

The browser never sees the client secret or Google's tokens — only the
one-time code passes through it. Unlike the portfolio this flow has no
signup detour: Masterji needs nothing beyond the verified Google identity,
so first-time users are created on the spot and logged straight in.
"""

import secrets
import threading
from urllib.parse import urlencode

import requests as http
from django.conf import settings
from django.core import signing
from django.db import connection
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from loguru import logger
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import set_auth_cookies
from .models import User

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
STATE_SALT = "google-oauth-state"
STATE_MAX_AGE = 600  # seconds a login attempt may take


def _safe_next(value: str | None) -> str:
    """Only same-site relative paths — blocks open-redirect abuse."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def _callback_url(request) -> str:
    return request.build_absolute_uri(reverse("google_callback"))


def _wake_db():
    """SELECT 1 to kick Neon out of autosuspend. Runs in a throwaway
    thread with its own thread-local connection — close it or it leaks."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        pass  # warmup is best-effort; the callback will surface real errors
    finally:
        connection.close()


def _start_db_wakeup():
    threading.Thread(target=_wake_db, name="db-wakeup", daemon=True).start()


def google_login(request):
    """Step 1: send the browser to Google's consent screen."""
    if not settings.GOOGLE_CLIENT_ID:
        return JsonResponse({"detail": "GOOGLE_CLIENT_ID not configured."}, status=503)
    # Wake the database now, without delaying the redirect: Neon resumes
    # (~1s) while the user is busy at Google's account picker, so it's
    # warm when the callback looks up / creates the user.
    _start_db_wakeup()
    # Signed + short-lived: proves the callback originated from a login we
    # started (no server-side session needed), and carries the post-login
    # destination along for the ride.
    state = signing.dumps(
        {"nonce": secrets.token_urlsafe(16), "next": _safe_next(request.GET.get("next"))},
        salt=STATE_SALT,
    )
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")


def _exchange_code(code: str, redirect_uri: str) -> dict:
    """Trade the one-time code (+ client secret) for Google's tokens."""
    res = http.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def _verify_id_token(raw_id_token: str) -> dict:
    """Check Google's signature and audience; returns the claims."""
    return google_id_token.verify_oauth2_token(
        raw_id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
    )


def unique_username(email: str) -> str:
    base = email.split("@")[0][:140] or "user"
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def google_callback(request):
    """Google redirected back; verify identity, create the user if new,
    set auth cookies and send the browser home."""
    try:
        state = signing.loads(
            request.GET.get("state", ""), salt=STATE_SALT, max_age=STATE_MAX_AGE
        )
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired OAuth state.")
    next_path = _safe_next(state.get("next") if isinstance(state, dict) else None)

    if "error" in request.GET:  # user hit "cancel" on the consent screen
        # "/" rather than the old /login/, which no longer exists: the landing
        # page is where sign-in starts now, so it is also where a sign-in that
        # didn't happen belongs. It reads ?error and says so.
        return redirect(f"{settings.FRONTEND_URL}/?error=cancelled")
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("Missing authorization code.")

    tokens = _exchange_code(code, _callback_url(request))
    claims = _verify_id_token(tokens["id_token"])
    if not claims.get("email_verified"):
        return HttpResponseBadRequest("Google account email is not verified.")

    email = claims["email"].lower()
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            username=unique_username(email),
            email=email,
            first_name=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
        )
        user.set_unusable_password()  # social-only account
        user.save(update_fields=["password"])
        logger.info(f"New user via Google login: {user.username}")

    response = redirect(f"{settings.FRONTEND_URL}{next_path}")
    set_auth_cookies(response, RefreshToken.for_user(user))
    return response
