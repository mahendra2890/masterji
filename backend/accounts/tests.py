"""Auth cookie-flow tests.

The invariant: a bad auth cookie — expired, garbage, or a valid token for a
user this database doesn't have — is a dead session, never a 500 and never a
lockout. It must still be possible to refresh, log out and log back in.
"""

import importlib.util
import os
from datetime import UTC, date, datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import resolve, reverse
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from coach.models import (
    CheckIn,
    Goal,
    Message,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
)

from . import erasure, oauth
from .middleware import KEY_PREFIX
from .models import PushSubscription, User
from .views import ThrottledTokenObtainPairView


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


class PasswordLoginCeilingTests(APITestCase):
    """The two surfaces here that take a password, and the ceiling on each.

    Neither can unlock a builder: sign-in is Google and every account carries
    `set_unusable_password()`. What they can unlock is the operator's superuser,
    whose admin session reads every builder's record — so an unmetered guessing
    run against either one is the whole distance to full compromise if that
    password is ever weak or reused.

    What is pinned is that a 429 arrives at all. Before this, eighty rapid wrong
    passwords against `/api/auth/token/` were eighty 401s, and the absence was
    invisible from the outside — which is exactly how it survived this long.
    """

    def setUp(self):
        # Both ceilings count in the default cache, which is process-wide and
        # outlives a test. An uncleared bucket would leak a refusal into the
        # next test, or hide one.
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_superuser(
            username="rootadmin", email="root@example.com", password="c0rrect-horse"
        )

    def _guess(self, password="wrong"):
        return self.client.post(
            reverse("token_obtain_pair"),
            {"username": "rootadmin", "password": password},
            format="json",
        )

    def test_the_token_endpoint_is_the_throttled_view(self):
        """The scope is the whole mechanism, and it is an attribute somebody
        could drop while the endpoint keeps working perfectly."""
        self.assertIs(
            resolve(reverse("token_obtain_pair")).func.cls,
            ThrottledTokenObtainPairView,
        )
        self.assertEqual(ThrottledTokenObtainPairView.throttle_scope, "login")
        self.assertIn(
            "login", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        )

    def test_the_token_endpoint_stops_answering_wrong_passwords(self):
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "3/hour"}):
            self.assertEqual([self._guess().status_code for _ in range(3)], [401] * 3)
            self.assertEqual(self._guess().status_code, 429)

    def test_the_ceiling_counts_the_address_not_the_username(self):
        """Otherwise it is no ceiling at all: a guessing run picks a new
        username per request and walks straight through."""
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "3/hour"}):
            for i in range(3):
                self.client.post(
                    reverse("token_obtain_pair"),
                    {"username": f"nobody{i}", "password": "wrong"},
                    format="json",
                )
            self.assertEqual(self._guess().status_code, 429)

    def test_a_correct_password_still_mints_a_token(self):
        """The ceiling is not a lock. Ten an hour is far above the once-per-
        fifteen-minutes an API client holding its own token actually needs."""
        response = self._guess("c0rrect-horse")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())


@override_settings(
    # The admin's login template asks staticfiles for admin/css/base.css, and
    # the manifest storage this project deploys with needs a collectstatic run
    # to answer. Nothing here depends on static files.
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    ADMIN_LOGIN_MAX_FAILURES=3,
)
class AdminLoginCeilingTests(TestCase):
    """`/admin/login/` is Django's own view, so DRF's throttling never runs for
    it and a `throttle_scope` on it would be silently ignored. The ceiling is
    middleware instead — and it counts failures rather than requests, so the
    operator cannot lock themselves out by knowing their own password."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_superuser(
            username="rootadmin", email="root@example.com", password="c0rrect-horse"
        )

    def _login(self, password, **extra):
        return self.client.post(
            reverse("admin:login"),
            {"username": "rootadmin", "password": password, "next": "/admin/"},
            **extra,
        )

    def test_wrong_passwords_stop_being_answered(self):
        # Django re-renders the form on a bad password — a 200 that is a
        # failure, which is why the middleware reads the redirect rather than
        # the status class.
        self.assertEqual([self._login("wrong").status_code for _ in range(3)], [200] * 3)
        refused = self._login("wrong")
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused["Retry-After"], str(settings.ADMIN_LOGIN_FAILURE_WINDOW_S))

    def test_the_right_password_gets_in_and_clears_the_count(self):
        """A staff member who fumbles the password twice and then types it
        correctly must not be one keystroke from a lockout for the rest of the
        hour."""
        self._login("wrong")
        self._login("wrong")
        self.assertEqual(self._login("c0rrect-horse").status_code, 302)

        self.client.logout()
        # Counter cleared: the next wrong guess is answered, not refused.
        self.assertEqual(self._login("wrong").status_code, 200)

    def test_reading_the_form_is_not_a_guess(self):
        """Only POSTs check a password. If GETs counted, opening the login page
        four times would refuse a sign-in nobody had attempted yet."""
        for _ in range(10):
            self.client.get(reverse("admin:login"))
        self.assertEqual(self._login("c0rrect-horse").status_code, 302)

    def test_the_bucket_is_the_forwarded_address(self):
        """In production the client address arrives in X-Forwarded-For from the
        same proxy chain this deployment already trusts for -Proto and -Host.
        Keying on REMOTE_ADDR instead would put every visitor behind the proxy
        in one bucket, which is one attacker locking out the operator."""
        for _ in range(4):
            self._login("wrong", HTTP_X_FORWARDED_FOR="203.0.113.7")
        self.assertEqual(
            self._login("wrong", HTTP_X_FORWARDED_FOR="203.0.113.7").status_code, 429
        )
        # A different address still gets its own three.
        self.assertEqual(
            self._login("wrong", HTTP_X_FORWARDED_FOR="198.51.100.4").status_code, 200
        )

    def test_the_lockout_does_not_extend_itself(self):
        """The window is fixed, not sliding: `cache.add` starts it and is a
        no-op afterwards. A sliding window would let an attacker who keeps
        hammering hold the operator out indefinitely."""
        for _ in range(3):
            self._login("wrong")
        key = f"{KEY_PREFIX}:127.0.0.1"
        self.assertEqual(cache.get(key), 3)
        # Refused requests never reach the view, so they add nothing.
        self._login("wrong")
        self._login("wrong")
        self.assertEqual(cache.get(key), 3)
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


class OAuthStateIsBoundToTheBrowserTests(TestCase):
    """A signed state proves this server minted it. Only a cookie proves the
    browser presenting it is the one that asked for it.

    Without that second half a validly-signed state is accepted from any
    browser — so an attacker can start a login, walk their OWN Google account
    to the consent screen, and then make a victim's browser load the callback
    with the resulting code. The callback would hand that browser auth cookies
    for the ATTACKER'S account, and every declaration and reflection the victim
    then writes lands somewhere the attacker signs into normally (#254).

    These are deliberately about the pairing rather than about Google: the
    state a real `google_login` mints is used throughout, and the only thing
    varied is whether the browser presenting it holds the cookie that came
    with it.
    """

    def setUp(self):
        # google_login answers 503 without a client id. Google itself is never
        # reached: the two calls that would are stubbed in the tests that get
        # that far.
        ctx = self.settings(
            GOOGLE_CLIENT_ID="test-client-id", FRONTEND_URL="https://app.example"
        )
        ctx.enable()
        self.addCleanup(ctx.disable)
        # The Neon warm-up thread has nothing to do with this and everything to
        # do with flakiness: it opens a second connection to the test database
        # from outside the test's transaction.
        waker = mock.patch.object(oauth, "_start_db_wakeup")
        waker.start()
        self.addCleanup(waker.stop)
        # The base case spends no code, the same way the suite's base case
        # refuses to call the model: a refusal that happens AFTER Google has
        # been asked is a different (and worse) thing than one that happens
        # before, and stubbing this to raise is what tells the two apart. The
        # tests that mean to get through re-stub it themselves.
        spend = mock.patch.object(
            oauth,
            "_exchange_code",
            side_effect=AssertionError("the authorization code must not be spent"),
        )
        spend.start()
        self.addCleanup(spend.stop)

    def _start_login(self, next_path="/"):
        """Drive the real first leg; return (state, the cookie it set)."""
        response = self.client.get(reverse("google_login"), {"next": next_path})
        self.assertEqual(response.status_code, 302)
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        return state, response.cookies[oauth.STATE_COOKIE].value

    def _callback(self, state, cookie=None, **params):
        """The callback, from a browser that holds `cookie` — or none at all,
        which is the attacker's position and the cleared-cookies one alike."""
        browser = Client()
        if cookie is not None:
            browser.cookies[oauth.STATE_COOKIE] = cookie
        return browser.get(reverse("google_callback"), {"state": state, **params})

    def test_the_login_hands_the_browser_the_other_half(self):
        """The flags are the defence, not decoration: a readable cookie is one
        any script on this origin can lift, and these are the values
        accounts/cookies.py already uses for the session itself."""
        response = self.client.get(reverse("google_login"))
        morsel = response.cookies[oauth.STATE_COOKIE]
        self.assertTrue(morsel["httponly"])
        self.assertEqual(morsel["samesite"], "Lax")
        self.assertEqual(morsel["path"], oauth.STATE_COOKIE_PATH)
        self.assertEqual(morsel["max-age"], oauth.STATE_MAX_AGE)
        # Django's test runner forces DEBUG off, so this IS the production
        # branch of `secure = not settings.DEBUG`.
        self.assertTrue(morsel["secure"])

    def test_local_development_over_plain_http_still_gets_the_cookie(self):
        """The gate on Secure, and the half that breaks silently if it is
        wrong: a Secure cookie is one the browser never sends back to
        http://localhost, so an ungated flag would make every local sign-in
        fail the binding check with nothing to read."""
        with self.settings(DEBUG=True):
            response = self.client.get(reverse("google_login"))
        self.assertFalse(response.cookies[oauth.STATE_COOKIE]["secure"])

    def test_the_cookie_carries_the_nonce_that_is_inside_the_state(self):
        """The two halves have to be the same value, or the comparison in the
        callback is comparing nothing."""
        state, cookie = self._start_login()
        self.assertTrue(cookie)
        self.assertEqual(signing.loads(state, salt=oauth.STATE_SALT)["nonce"], cookie)

    def test_a_valid_state_from_another_browser_is_refused(self):
        """The finding itself: a real, correctly-signed, unexpired state,
        presented by a browser that never started the login.

        Google is stubbed to succeed — the attacker's code is a real one, and
        the point is that it never gets spent. Before the cookie, this exact
        request answered 302 to https://app.example/goal/ with `access_token`
        and `refresh_token` set for the attacker's account.
        """
        state, _ = self._start_login()
        claims = {"email": "attacker@example.com", "email_verified": True}
        with (
            mock.patch.object(oauth, "_exchange_code", return_value={"id_token": "t"}),
            mock.patch.object(oauth, "_verify_id_token", return_value=claims),
        ):
            response = self._callback(state, code="attackers-code")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://app.example/?error=expired")
        # And, the part that matters: no session was handed out on the way.
        self.assertNotIn(settings.AUTH_ACCESS_COOKIE, response.cookies)
        self.assertNotIn(settings.AUTH_REFRESH_COOKIE, response.cookies)
        # Refused before the code is spent, not after.
        self.assertFalse(User.objects.filter(email="attacker@example.com").exists())

    def test_another_logins_cookie_does_not_open_this_state(self):
        """Two sign-ins in flight at once. Holding *a* state cookie is not the
        same as holding *this* state's cookie."""
        state, _ = self._start_login()
        _, someone_elses = self._start_login()
        response = self._callback(state, someone_elses, code="attackers-code")
        self.assertEqual(response["Location"], "https://app.example/?error=expired")

    def test_a_cleared_cookie_gets_a_retry_not_a_500(self):
        """The honest way to arrive here — cookies cleared mid-flow. What a
        builder sees is the landing page with the sign-in popup open on it
        (components/SignIn.tsx renders `expired`), not a stack trace and not a
        bare 400 with nothing to press."""
        state, _ = self._start_login(next_path="/goal/")
        response = self._callback(state, code="a-real-code")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://app.example/?error=expired")

    def test_an_unreadable_state_lands_in_the_same_place(self):
        """Expired or forged. This used to be a 400 with a sentence in it,
        which is a dead end for the one person who reaches it honestly by
        sitting on Google's account picker for ten minutes."""
        response = self._callback("not-a-state-this-server-signed", "n", code="c")
        self.assertEqual(response["Location"], "https://app.example/?error=expired")

    def test_the_matching_pair_still_signs_in(self):
        """The half that breaks loudly: the browser that started the login
        gets through, and still lands on the ?next it asked for."""
        state, cookie = self._start_login(next_path="/goal/")
        claims = {
            "email": "New.Builder@example.com",
            "email_verified": True,
            "given_name": "New",
            "family_name": "Builder",
        }
        with (
            mock.patch.object(oauth, "_exchange_code", return_value={"id_token": "t"}),
            mock.patch.object(oauth, "_verify_id_token", return_value=claims),
        ):
            response = self._callback(state, cookie, code="a-real-code")
        self.assertEqual(response["Location"], "https://app.example/goal/")
        self.assertIn(settings.AUTH_ACCESS_COOKIE, response.cookies)
        self.assertTrue(User.objects.filter(email="new.builder@example.com").exists())

    def test_the_state_cookie_is_spent_on_the_way_out(self):
        """One shot. A state cookie still sitting in the browser after the
        login it belongs to has ended is a second chance for it, so it is
        cleared on refusal and on success alike."""
        state, cookie = self._start_login()
        cancelled = self._callback(state, cookie, error="access_denied")
        self.assertEqual(cancelled.cookies[oauth.STATE_COOKIE].value, "")

        state, cookie = self._start_login()
        with (
            mock.patch.object(oauth, "_exchange_code", return_value={"id_token": "t"}),
            mock.patch.object(
                oauth,
                "_verify_id_token",
                return_value={"email": "a@example.com", "email_verified": True},
            ),
        ):
            signed_in = self._callback(state, cookie, code="c")
        self.assertEqual(signed_in.cookies[oauth.STATE_COOKIE].value, "")

    def test_a_cancelled_sign_in_still_reads_as_cancelled(self):
        """Pressing cancel on the consent screen comes back with the state and
        the cookie both intact, so the new gate must not swallow the case that
        already had a sentence written for it."""
        state, cookie = self._start_login()
        response = self._callback(state, cookie, error="access_denied")
        self.assertEqual(response["Location"], "https://app.example/?error=cancelled")
