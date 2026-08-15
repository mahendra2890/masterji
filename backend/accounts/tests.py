"""Auth cookie-flow tests.

The invariant: a bad auth cookie — expired, garbage, or a valid token for a
user this database doesn't have — is a dead session, never a 500 and never a
lockout. It must still be possible to refresh, log out and log back in.
"""

import importlib.util
import os
from datetime import UTC, date, datetime, timedelta
from unittest import mock

import jwt
from django.conf import settings
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from coach.models import (
    CheckIn,
    Goal,
    Message,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
)

from . import erasure
from .models import PushSubscription, User


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
        self.assertEqual(response.json()["detail"], "Session expired — sign in again.")

    def test_every_dead_cookie_is_a_401_in_json(self):
        """The bug this class exists to prevent, in the three shapes that
        actually reach production.

        This view reimplements simplejwt's TokenViewBase.post and used to drop
        its TokenError → InvalidToken conversion, so a malformed, expired, or
        wrong-secret cookie raised past DRF and Django answered 500 in
        text/html. lib/auth-client.ts reads any non-JSON reply as "the instance
        is still booting", so the app showed "The server is waking up." and
        retried every three seconds forever, on a screen with no way out — and
        a SECRET_KEY rotation would have done that to every signed-in builder
        at once. The content type is asserted for that reason: a 500 that
        happened to be JSON would have been a bad code, while a 500 in HTML was
        an unrecoverable app.
        """
        user = User.objects.create_user(username="ash", email="ash@example.com")
        expired = RefreshToken.for_user(user)
        expired.set_exp(
            from_time=datetime.now(UTC) - timedelta(days=30),
            lifetime=timedelta(seconds=1),
        )
        elsewhere = jwt.encode(
            {"token_type": "refresh", "exp": 9999999999, "jti": "x", "user_id": user.id},
            "a-key-this-deploy-does-not-use",
            algorithm="HS256",
        )
        for label, raw in [
            ("malformed", "not-a-jwt"),
            ("expired", str(expired)),
            ("signed with a rotated SECRET_KEY", elsewhere),
        ]:
            with self.subTest(cookie=label):
                response = self.refresh_with_cookie(raw)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response["Content-Type"], "application/json")

    def test_a_dead_cookie_is_cleared_on_the_way_out(self):
        """Otherwise the 401 is the same 401 tomorrow: the cookie outlives the
        session it names, so every visit re-runs the failure. Cleared, the next
        request is the plain "No refresh cookie." case and the builder gets a
        landing page with a sign-in button on it."""
        response = self.refresh_with_cookie("not-a-jwt")
        self.assertEqual(response.status_code, 401)
        for name in (settings.AUTH_ACCESS_COOKIE, settings.AUTH_REFRESH_COOKIE):
            with self.subTest(cookie=name):
                self.assertEqual(response.cookies[name].value, "")


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


class AccountErasureTests(APITestCase):
    """The way out.

    This product stores a teenager's daily work diary — the nights that were
    not about the work included — and until now had no route for leaving with
    it. What is pinned here is that "delete my account" is true in every sense
    the app can check: the rows stop answering, the identity is gone rather
    than tombstoned, and the session dies with it.
    """

    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice", email="alice@example.com", password="pw"
        )
        self.bob = User.objects.create_user(
            username="bob", email="bob@example.com", password="pw"
        )
        self.client.force_authenticate(self.alice)

    def _a_record(self, user):
        """One row of every shape that hangs off a user, two levels deep."""
        goal = Goal.objects.create(user=user, title="Tiffin app")
        checkin = CheckIn.objects.create(
            goal=goal,
            date=date.today(),
            phase=goal.phase,
            am_declaration="write the problem statement",
            pm_proof_text="wrote it",
        )
        ProofAttempt.objects.create(checkin=checkin, text="first try")
        Message.objects.create(
            goal=goal, role=Message.Role.COACH, phase=goal.phase, content="welcome"
        )
        workshop = Workshop.objects.create(user=user)
        WorkshopMessage.objects.create(
            workshop=workshop, role=WorkshopMessage.Role.USER, content="no idea yet"
        )
        return goal

    def test_a_deleted_account_stops_answering_every_queryset(self):
        """The one test this feature is for. Written against the default
        managers rather than a list of models, because the promise made to the
        builder is about what the product can still see, not about which
        tables somebody remembered."""
        self._a_record(self.alice)
        self._a_record(self.bob)

        response = self.client.delete("/api/auth/me/")
        self.assertEqual(response.status_code, 204)

        for model in (
            Goal,
            CheckIn,
            ProofAttempt,
            Message,
            Workshop,
            WorkshopMessage,
        ):
            with self.subTest(model=model.__name__):
                rows = model.objects.all()
                self.assertEqual(
                    [r for r in rows if self._owner(r) == self.alice.pk], []
                )
                # And nobody else's evening went with it.
                self.assertEqual(len(rows), 1)

    def _owner(self, row) -> int:
        """Whose row this is, however many hops up it lives."""
        for attr in ("user_id",):
            if hasattr(row, attr):
                return getattr(row, attr)
        for attr in ("goal", "workshop", "checkin"):
            parent = getattr(row, attr, None)
            if parent is not None:
                return self._owner(parent)
        raise AssertionError(f"no owner path from {row!r}")

    def test_the_cascade_is_walked_not_listed(self):
        """A hand-written cascade is correct the day it is written and
        silently wrong the first time somebody adds a model — and the failure
        is invisible, because the rows just keep answering. Every soft-delete
        model reachable from the user is reached, two levels down included."""
        goal = self._a_record(self.alice)
        counts = erasure.erase(self.alice)
        reached = {label.split(".")[-1] for label in counts}
        self.assertEqual(
            reached,
            {"Goal", "CheckIn", "ProofAttempt", "Message", "Workshop", "WorkshopMessage"},
        )
        # ProofAttempt hangs off CheckIn, which hangs off Goal — proof the
        # walk descends rather than stopping at the user's own relations.
        self.assertIsNotNone(ProofAttempt.all_objects.get().deleted_at)
        self.assertIsNotNone(Goal.all_objects.get(pk=goal.pk).deleted_at)

    def test_the_identity_is_gone_not_tombstoned(self):
        """Hiding the rows is half of erasure. An account row that still holds
        the email is the other half undone — and because email is unique, it
        would also refuse this person a new account with the same Google
        address for good, which turns deletion into a ban."""
        self.client.delete("/api/auth/me/")
        self.alice.refresh_from_db()
        self.assertNotIn("alice@example.com", self.alice.email)
        self.assertNotEqual(self.alice.username, "alice")
        self.assertFalse(self.alice.is_active)
        self.assertFalse(self.alice.has_usable_password())
        # The address is free, so signing up again works.
        User.objects.create_user(username="alice2", email="alice@example.com")

    def test_the_session_dies_with_the_account(self):
        """`is_active = False` is the kill switch, and it is the built-in one:
        simplejwt refuses an inactive user, so an access token already sitting
        in a browser stops authenticating the moment this commits. There is no
        token blacklist in this deployment and this needs none."""
        token = RefreshToken.for_user(self.alice)
        self.client.force_authenticate(None)
        self.client.cookies[settings.AUTH_ACCESS_COOKIE] = str(token.access_token)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

        self.client.force_authenticate(self.alice)
        self.client.delete("/api/auth/me/")

        self.client.force_authenticate(None)
        self.client.cookies[settings.AUTH_ACCESS_COOKIE] = str(token.access_token)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_deleting_needs_a_session(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.delete("/api/auth/me/").status_code, 401)

    def test_a_push_subscription_does_not_survive_the_account(self):
        """The one row `erase` hard-deletes, and the one `_descend` cannot
        reach — PushSubscription is not a SoftDeleteModel, so the walk goes
        straight past it.

        A tombstone would be the wrong answer even if it could. Every other
        row erasure touches is a record of something the builder did; this one
        is a live capability to send a message to their phone, held by an
        account that has just asked to stop existing. The rule this module
        states about the email applies to it exactly.
        """
        PushSubscription.objects.create(
            user=self.alice,
            endpoint="https://push.example.invalid/alice",
            p256dh="k",
            auth="a",
            timezone_name="Asia/Kolkata",
        )
        # bob's device is somebody else's and must not be caught by this.
        PushSubscription.objects.create(
            user=self.bob,
            endpoint="https://push.example.invalid/bob",
            p256dh="k",
            auth="a",
        )

        counts = erasure.erase(self.alice)

        self.assertEqual(counts["accounts.PushSubscription"], 1)
        self.assertEqual(
            [s.user for s in PushSubscription.objects.all()], [self.bob]
        )

    def test_an_account_with_no_devices_reports_none(self):
        """The count is a log line, and a log line that says "0 push
        subscriptions" on every deletion is noise."""
        self.assertNotIn("accounts.PushSubscription", erasure.erase(self.alice))

    def test_the_spend_ledger_is_reached_by_the_walk(self):
        """coach.ModelCall is a SoftDeleteModel with a user FK, so `_descend`
        finds it through the model graph with nothing written down about it —
        and this test is the only thing that says so.

        Worth pinning precisely because it is free. The graph walk exists so a
        model added later cannot be forgotten, and the failure mode it guards
        against is invisible: the rows simply keep answering queries for an
        account that asked to be gone.

        Soft is also the right depth here, and it is why this ledger does not
        follow PushSubscription's hard delete. A row of it is a record of money
        the operator spent, not a capability held over the builder — and since
        `erase` overwrites the identity (email, username, password) the spend
        survives with the person scrubbed off it, which is exactly what a cost
        ledger should do when somebody leaves.
        """
        from coach.models import ModelCall

        mine = ModelCall.objects.create(
            user=self.alice, kind=ModelCall.Kind.CHAT, model="openai/gpt-5.4-mini",
            prompt_tokens=10, completion_tokens=2, total_tokens=12,
        )
        theirs = ModelCall.objects.create(
            user=self.bob, kind=ModelCall.Kind.CHAT, model="openai/gpt-5.4-mini",
            prompt_tokens=7, completion_tokens=1, total_tokens=8,
        )

        counts = erasure.erase(self.alice)

        self.assertEqual(counts["coach.ModelCall"], 1)
        self.assertEqual([r.id for r in ModelCall.objects.all()], [theirs.id])
        # Soft, not gone: the operator's record of what was spent survives in
        # all_objects, attached to an account whose identity has been erased.
        self.assertIsNotNone(ModelCall.all_objects.get(id=mine.id).deleted_at)


class ProductionTransportSecurityTests(SimpleTestCase):
    """What `if not DEBUG:` in config/settings.py promises, on both sides of
    the gate.

    These settings are read once at import, under an env var, so nothing in the
    running suite exercises them — which is exactly how the deployment ran for
    months with the admin's `sessionid` and `csrftoken` unmarked. The settings
    module is reloaded here under a patched environment instead, so both
    branches are checked rather than assumed.

    The gate matters as much as the settings do. A Secure cookie is one the
    browser will not send back over plain HTTP, so an ungated flag would lock
    local development out of its own admin with nothing to read but a login
    form that keeps reappearing.
    """

    PROD_ENV = {
        "DJANGO_DEBUG": "0",
        "DJANGO_SECRET_KEY": "a-long-enough-key-for-the-deploy-checks-0123456789",
        "DJANGO_ALLOWED_HOSTS": "masterji.mscsoftwares.in",
    }

    def _settings_module(self, env):
        """config/settings.py executed fresh under `env`, into a namespace of
        its own.

        A new module object rather than `importlib.reload`, and the difference
        is the whole reliability of this class: reload re-executes into the
        existing namespace, so the `if not DEBUG:` block's attributes survive
        into the next load and a DEBUG run would inherit production's flags
        from whichever test ran before it. Nothing here touches the real
        `config.settings`, or django.conf's live copy of it.
        """
        import config.settings

        spec = importlib.util.spec_from_file_location(
            "config._settings_under_test", config.settings.__file__
        )
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, env, clear=False):
            spec.loader.exec_module(module)
        return module

    def test_the_admin_cookies_are_secure_in_production(self):
        """`sessionid` and `csrftoken` come from framework defaults, and the
        defaults are insecure. This is the whole of the finding."""
        prod = self._settings_module(self.PROD_ENV)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertGreater(prod.SECURE_HSTS_SECONDS, 0)

    def test_local_development_over_plain_http_is_untouched(self):
        """The other half, and the half that breaks loudly if it is wrong."""
        dev = self._settings_module({"DJANGO_DEBUG": "1"})
        self.assertFalse(getattr(dev, "SESSION_COOKIE_SECURE", False))
        self.assertFalse(getattr(dev, "CSRF_COOKIE_SECURE", False))
        self.assertFalse(getattr(dev, "SECURE_SSL_REDIRECT", False))
        self.assertEqual(getattr(dev, "SECURE_HSTS_SECONDS", 0), 0)

    def test_the_redirect_reads_the_proxy_header(self):
        """SECURE_SSL_REDIRECT without SECURE_PROXY_SSL_HEADER is a redirect
        loop: TLS ends at Render's proxy, so every request looks like plain
        HTTP to the app, and the https URL it sends the browser to arrives
        looking exactly the same."""
        prod = self._settings_module(self.PROD_ENV)
        self.assertEqual(
            prod.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_hsts_is_not_promised_for_subdomains_or_preload(self):
        """Declined deliberately — both widen a commitment no browser lets you
        take back, past what can be checked from inside this repository. Pinned
        so turning either on is a decision somebody makes, not a default that
        arrives with an upgrade."""
        prod = self._settings_module(self.PROD_ENV)
        self.assertFalse(getattr(prod, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False))
        self.assertFalse(getattr(prod, "SECURE_HSTS_PRELOAD", False))

    def _through_security_middleware(self, path, **extra):
        request = RequestFactory().get(path, **extra)
        # Built inside the caller's override: SecurityMiddleware reads every
        # one of these settings in __init__, so an instance made before the
        # override would answer with the suite's own (unhardened) values.
        middleware = SecurityMiddleware(lambda r: HttpResponse("ok"))
        return middleware(request)

    def test_the_health_probe_is_not_redirected(self):
        """Render's health check reaches /api/health/ inside its own network,
        where there is no X-Forwarded-Proto to read — so without the exemption
        every probe is answered with a 301, and a health check that stops
        seeing 200 is a service that stops taking traffic."""
        prod = self._settings_module(self.PROD_ENV)
        with self.settings(
            SECURE_SSL_REDIRECT=prod.SECURE_SSL_REDIRECT,
            SECURE_REDIRECT_EXEMPT=prod.SECURE_REDIRECT_EXEMPT,
            SECURE_PROXY_SSL_HEADER=prod.SECURE_PROXY_SSL_HEADER,
            SECURE_HSTS_SECONDS=prod.SECURE_HSTS_SECONDS,
        ):
            self.assertEqual(self._through_security_middleware("/api/health/").status_code, 200)
            # Everything else over plain HTTP is sent to https once.
            moved = self._through_security_middleware("/admin/login/")
            self.assertEqual(moved.status_code, 301)
            self.assertTrue(moved["Location"].startswith("https://"))
            # And a request the proxy has already terminated TLS for is served,
            # with the HSTS header on it and nothing promised beyond this host.
            served = self._through_security_middleware(
                "/admin/login/", HTTP_X_FORWARDED_PROTO="https"
            )
            self.assertEqual(served.status_code, 200)
            self.assertEqual(
                served["Strict-Transport-Security"],
                f"max-age={prod.SECURE_HSTS_SECONDS}",
            )


class AppAuthCookiesAreUnchangedTests(APITestCase):
    """The app's own JWT cookies were already hardened by hand in
    accounts/cookies.py and are not what the admin finding was about. Pinned
    because the tempting way to "fix" that finding is a global
    SESSION_COOKIE_SECURE-style sweep, and these two are set with explicit
    flags that such a sweep would not reach — so they would keep looking fixed
    while quietly depending on a setting that does not apply to them."""

    def test_the_jwt_cookies_carry_their_own_flags(self):
        user = User.objects.create_user(username="alice", email="alice@example.com")
        with self.settings(DEBUG=True):
            response = self.client.post(
                reverse("dev_login"), {"username": user.username}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        for name in (settings.AUTH_ACCESS_COOKIE, settings.AUTH_REFRESH_COOKIE):
            with self.subTest(cookie=name):
                morsel = response.cookies[name]
                self.assertTrue(morsel["httponly"])
                self.assertEqual(morsel["samesite"], "Lax")
                # The suite runs on the DEBUG settings path, where Secure would
                # keep the cookie off localhost — `secure = not DEBUG` is the
                # rule, and it is the rule this test is protecting.
                self.assertFalse(morsel["secure"])
