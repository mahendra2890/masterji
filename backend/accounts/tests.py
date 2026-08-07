"""Auth cookie-flow tests.

The invariant: a bad auth cookie — expired, garbage, or a valid token for a
user this database doesn't have — is a dead session, never a 500 and never a
lockout. It must still be possible to refresh, log out and log back in.
"""

from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


class CookieRefreshTests(APITestCase):
    def refresh_with_cookie(self, raw: str):
        self.client.cookies[settings.AUTH_REFRESH_COOKIE] = raw
        return self.client.post(reverse("cookie_refresh"))

    def test_missing_cookie_is_401(self):
        response = self.client.post(reverse("cookie_refresh"))
        self.assertEqual(response.status_code, 401)

    def test_valid_cookie_rotates_tokens(self):
        user = User.objects.create_user(username="alice", email="alice@example.com")
        response = self.refresh_with_cookie(str(RefreshToken.for_user(user)))
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.AUTH_ACCESS_COOKIE, response.cookies)
        self.assertIn(settings.AUTH_REFRESH_COOKIE, response.cookies)

    def test_token_for_unknown_user_is_401_not_500(self):
        # A cryptographically valid token whose user id isn't in this
        # database — another localhost app's cookie signed with the same dev
        # SECRET_KEY, or a deleted account. simplejwt raises User.DoesNotExist
        # while validating; the view must translate that to 401.
        user = User.objects.create_user(username="ghost", email="ghost@example.com")
        raw = str(RefreshToken.for_user(user))
        user.delete()
        response = self.refresh_with_cookie(raw)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unknown session.")


class SessionLifecycleTests(APITestCase):
    """An unusable access cookie must read as signed out, not as a broken
    request. When the auth layer raised instead, it 401'd every view — the
    AllowAny endpoints that exist to recover from a stale session included,
    which left the browser no way back in."""

    def setUp(self):
        self.user = User.objects.create_user(username="dev", email="dev@example.com")

    def _expired_access_cookie(self, refresh: RefreshToken):
        access = refresh.access_token
        access.set_exp(lifetime=-timedelta(minutes=1))  # already expired
        self.client.cookies[settings.AUTH_ACCESS_COOKIE] = str(access)

    def test_an_expired_access_cookie_still_lets_the_session_refresh(self):
        """Every idle tab holds an access cookie older than 15 minutes. If
        that cookie 401s the recovery endpoints, the client's
        401 → refresh → replay path can never succeed, so sessions
        hard-expire every 15 minutes and logout can't even clear itself."""
        refresh = RefreshToken.for_user(self.user)
        self._expired_access_cookie(refresh)
        self.client.cookies[settings.AUTH_REFRESH_COOKIE] = str(refresh)

        self.assertEqual(self.client.post(reverse("cookie_refresh")).status_code, 200)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 200)

    def test_an_expired_access_cookie_reads_as_signed_out_not_broken(self):
        self._expired_access_cookie(RefreshToken.for_user(self.user))
        # Protected views still refuse — from the permission layer.
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_a_cookie_for_an_unknown_user_reads_as_signed_out(self):
        """On localhost, a sibling project's access_token cookie rides along
        (same host, same cookie name, same insecure dev SECRET_KEY) and its
        user id means nothing here. That must not lock the login endpoints."""
        access = RefreshToken.for_user(self.user).access_token
        self.user.delete()
        self.client.cookies[settings.AUTH_ACCESS_COOKIE] = str(access)

        # Reads as anonymous, not as a broken request...
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)
        # ...so the way back in still works.
        with self.settings(DEBUG=True):
            response = self.client.post(
                reverse("dev_login"), {"username": "dev2"}, format="json"
            )
        self.assertEqual(response.status_code, 200)

    def test_a_bad_authorization_header_still_fails_loudly(self):
        # A header is an assertion the client made: a bad one is its bug.
        response = self.client.get(
            reverse("me"), HTTP_AUTHORIZATION="Bearer not-a-token"
        )
        self.assertEqual(response.status_code, 401)
