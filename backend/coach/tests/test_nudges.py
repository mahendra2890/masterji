"""The evening nudge: who is due, what leaves, the words, the opt-in, and the
one door the hourly workflow knocks on.
"""

import json
from datetime import UTC, date, datetime
from unittest import mock

from django.test import SimpleTestCase, override_settings

from accounts.models import PushSubscription

from .. import (
    nudges,
    prompts,
)
from ..models import (
    CheckIn,
    Goal,
)
from .base import CoachTestCase, make_user

# --- the evening nudge (#87) -------------------------------------------------
#
# What these protect is the one thing in this product that happens with nobody
# watching. Every other decision here is answered into a request a builder
# made and is visible on their screen the same second; a nudge is decided on a
# server, at an hour nobody is looking at, and lands on a lock screen. If the
# selection is wrong the symptom is either silence — which reads as the
# feature not existing — or a notification at three in the morning.
#
# So the selection is tested directly rather than through the endpoint. The
# endpoint is ten lines of token comparison and is tested for exactly that.

# Throwaway. Nothing here signs or encrypts anything: `webpush` is patched out
# in every test below, because what is under test is who gets chosen and what
# is written down afterwards, not pywebpush's crypto. A real keypair would buy
# this suite nothing and put a private key in the repository.
PUSH_ON = dict(
    VAPID_PUBLIC_KEY="test-public-key",
    VAPID_PRIVATE_KEY="test-private-key",
    VAPID_CONTACT="mailto:nobody@example.invalid",
    NUDGE_TOKEN="test-nudge-token",
)


@override_settings(**PUSH_ON)
class NudgeCase(CoachTestCase):
    """Shared ground for the two suites below: a builder, a device, and a
    fixed instant.

    Every `now` here is an explicit UTC instant rather than the wall clock,
    which is the only way to test the thing that actually matters: the server
    runs in UTC and the builder does not. A test that used `timezone.now()`
    would pass in the morning and fail after five, which is the exact class of
    bug this module exists to avoid.
    """

    # 12:00 UTC is 17:30 in Kolkata — the evening has started there, and has
    # not in London (13:00) or New York (08:00).
    EVENING_IN_INDIA = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    def subscribe(self, user=None, zone="Asia/Kolkata", **kwargs) -> PushSubscription:
        user = user or self.alice
        return PushSubscription.objects.create(
            user=user,
            endpoint=kwargs.pop(
                "endpoint", f"https://push.example.invalid/{user.pk}-{zone}"
            ),
            p256dh="k",
            auth="a",
            timezone_name=zone,
            **kwargs,
        )

    def owe(self, goal, day: date, task="ship the tiffin form"):
        """A declared morning with no proof filed — the state `_open_checkin`
        answers to, which is the whole eligibility rule."""
        return CheckIn.objects.create(
            goal=goal, date=day, phase=goal.phase, am_declaration=task
        )


class NudgeEligibilityTests(NudgeCase):
    """Who is due, and who is not."""

    def test_an_owed_proof_after_the_cutoff_is_selected(self):
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        sub = self.subscribe()

        due = nudges.due_now(self.EVENING_IN_INDIA)

        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].user, self.alice)
        # Their date, not the server's. Both happen to be the 14th at this
        # instant; the timezone test below is the one that pulls them apart.
        self.assertEqual(due[0].day, date(2026, 8, 14))
        self.assertEqual(due[0].subscriptions, [sub])

    def test_a_finished_day_is_not_selected(self):
        """The proof is in and it stood. There is nothing owed, so there is
        nothing to say — and a nudge here would be the app asking for work it
        has already been given, which is the complaint this product's own
        prompt file spends the most words on."""
        goal = self.make_goal()
        CheckIn.objects.create(
            goal=goal,
            date=date(2026, 8, 14),
            phase=goal.phase,
            am_declaration="ship the tiffin form",
            pm_proof_text="here it is",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
        )
        self.subscribe()

        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])

    def test_nobody_is_nudged_twice_in_a_day(self):
        """The tick runs hourly, so this same evening is asked about seven
        more times before midnight. The stamp is the only thing between that
        and seven notifications."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        self.subscribe(last_nudged_on=date(2026, 8, 14))

        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])

        # And yesterday's stamp does not ration today.
        PushSubscription.objects.update(last_nudged_on=date(2026, 8, 13))
        self.assertEqual(len(nudges.due_now(self.EVENING_IN_INDIA)), 1)

    def test_before_their_evening_nobody_is_due(self):
        """Two hours earlier in the same timezone: the proof is owed, and it
        is 15:30 where they are. The Today card has not even unfolded the box
        yet (app/Masterji.tsx, EVENING_FROM), so a nudge would point at
        something the app is still hiding."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        self.subscribe()

        early = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)  # 15:30 IST
        self.assertEqual(nudges.due_now(early), [])

    def test_the_evening_is_the_builders_own_and_not_the_servers(self):
        """The reason PushSubscription stores a timezone at all.

        One instant, three builders, three different local times. In UTC terms
        it is lunchtime — a server reading its own clock would nudge nobody,
        or, six hours later, would nudge the builder in Kolkata at 23:30.
        """
        for name, zone in (("kolkata", "Asia/Kolkata"), ("newyork", "America/New_York")):
            user = make_user(name)
            goal = Goal.objects.create(user=user, title=f"{name} idea")
            # Each builder's own local date on this instant. In New York it is
            # still the 14th; the point is that the row is looked up under the
            # date THEY are on.
            local = self.EVENING_IN_INDIA.astimezone(
                PushSubscription(timezone_name=zone).zone()
            ).date()
            self.owe(goal, local)
            self.subscribe(user=user, zone=zone)

        due = nudges.due_now(self.EVENING_IN_INDIA)

        # 17:30 in Kolkata, 08:00 in New York. Only one evening has started.
        self.assertEqual([d.user.username for d in due], ["kolkata"])

    def test_a_day_with_no_declaration_owes_nothing(self):
        """Deliberate, and the boundary of the whole feature. A day nobody
        declared on has no proof owed against it, so there is nothing to hold
        the builder to — and "you didn't start today" is the scolding this
        product refuses. `_open_checkin` non-empty is the bar."""
        self.make_goal()
        self.subscribe()

        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])

    def test_a_pushed_back_proof_still_owes(self):
        """`_open_checkin` says so, and it is right: a pushed-back cycle is
        open, the builder gets to answer it, and that is the evening a nudge
        is worth the most rather than the one where it is a duplicate."""
        goal = self.make_goal()
        CheckIn.objects.create(
            goal=goal,
            date=date(2026, 8, 14),
            phase=goal.phase,
            am_declaration="ship the tiffin form",
            pm_proof_text="a first go",
            proof_status=CheckIn.ProofStatus.PUSHED_BACK,
        )
        self.subscribe()

        self.assertEqual(len(nudges.due_now(self.EVENING_IN_INDIA)), 1)

    def test_a_builder_with_no_active_goal_is_never_due(self):
        """Between ideas. Nothing is owed because there is nothing to owe it
        against, and a subscription that survives the gap is correct — it is
        the next goal's notification permission, already granted."""
        self.subscribe()
        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])

    def test_a_retired_goal_owes_nothing(self):
        goal = self.make_goal(status=Goal.Status.ABANDONED)
        self.owe(goal, date(2026, 8, 14))
        self.subscribe()

        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])

    def test_one_builders_evening_is_not_anothers(self):
        """Tenancy, in the one place in this product where there is no
        `request.user` to filter by. bob owes a proof; alice does not, and
        alice is the one holding the subscription."""
        self.make_goal()  # alice, nothing declared
        bob_goal = self.make_goal(user=self.bob)
        self.owe(bob_goal, date(2026, 8, 14))
        self.subscribe(user=self.alice)

        self.assertEqual(nudges.due_now(self.EVENING_IN_INDIA), [])


class NudgeSendingTests(NudgeCase):
    """What leaves, and what gets written down afterwards.

    `webpush` is patched in every one of these. What is being tested is this
    module's bookkeeping — the stamp, the reaping, the counts — and the push
    service on the other end is somebody else's software.
    """

    def test_the_nudge_goes_out_and_the_evening_is_stamped(self):
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        sub = self.subscribe()

        with mock.patch("coach.nudges.webpush") as sent:
            result = nudges.send_due(self.EVENING_IN_INDIA)

        self.assertEqual(sent.call_count, 1)
        self.assertEqual(result, {"due": 1, "builders": 1, "sent": 1})
        sub.refresh_from_db()
        self.assertEqual(sub.last_nudged_on, date(2026, 8, 14))

        # And the next tick, an hour later, finds nothing.
        with mock.patch("coach.nudges.webpush") as again:
            nudges.send_due(datetime(2026, 8, 14, 13, 0, tzinfo=UTC))
        self.assertEqual(again.call_count, 0)

    def test_two_devices_are_one_nudge_delivered_twice(self):
        """Not two nudges. "One a day" is a promise to a person, so both of a
        builder's devices are stamped together — otherwise adding a laptop
        would silently double what the phone was promised."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        phone = self.subscribe(endpoint="https://push.example.invalid/phone")
        laptop = self.subscribe(endpoint="https://push.example.invalid/laptop")

        with mock.patch("coach.nudges.webpush") as sent:
            result = nudges.send_due(self.EVENING_IN_INDIA)

        self.assertEqual(sent.call_count, 2)
        self.assertEqual(result["builders"], 1)
        for sub in (phone, laptop):
            sub.refresh_from_db()
            self.assertEqual(sub.last_nudged_on, date(2026, 8, 14))

    def test_an_evening_nobody_could_be_reached_on_is_not_stamped(self):
        """A push service having a bad afternoon must not cost the builder
        their nudge. Nothing is written down, so the next tick tries again —
        the retry is the clock, which is why there is no queue here."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        sub = self.subscribe()

        with mock.patch("coach.nudges.webpush", side_effect=RuntimeError("boom")):
            result = nudges.send_due(self.EVENING_IN_INDIA)

        self.assertEqual(result["sent"], 0)
        sub.refresh_from_db()
        self.assertIsNone(sub.last_nudged_on)

    def test_a_subscription_the_push_service_has_retired_is_deleted(self):
        """410 means the browser is gone — uninstalled, site data cleared,
        permission revoked. A row that answers 410 will answer 410 forever."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        self.subscribe()

        gone = nudges.WebPushException("gone")
        gone.response = mock.Mock(status_code=410)
        with mock.patch("coach.nudges.webpush", side_effect=gone):
            nudges.send_due(self.EVENING_IN_INDIA)

        self.assertFalse(PushSubscription.objects.exists())

    def test_a_transient_failure_keeps_the_subscription(self):
        """The opposite of the above, and the reason the codes are checked
        rather than every failure being treated as death: a 500 from a push
        service is their bad minute, not the builder's uninstall."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        self.subscribe()

        flaky = nudges.WebPushException("later")
        flaky.response = mock.Mock(status_code=503)
        with mock.patch("coach.nudges.webpush", side_effect=flaky):
            nudges.send_due(self.EVENING_IN_INDIA)

        self.assertTrue(PushSubscription.objects.exists())

    def test_the_nudge_carries_their_own_words_back(self):
        """The move the copy exists to make. Not "you have an incomplete
        task" — "you said this, this morning"."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14), task="call three tiffin owners")
        self.subscribe()

        with mock.patch("coach.nudges.webpush") as sent:
            nudges.send_due(self.EVENING_IN_INDIA)

        payload = json.loads(sent.call_args.kwargs["data"])
        self.assertEqual(payload["title"], prompts.NUDGE_TITLE)
        self.assertIn("call three tiffin owners", payload["body"])
        self.assertEqual(payload["url"], "/")

    @override_settings(VAPID_PRIVATE_KEY="")
    def test_a_deployment_with_no_keys_sends_nothing(self):
        """Off end to end rather than half-wired, which is the whole reason
        `_configured` reads all three variables. The selection is not even
        run: there is no point choosing who to disappoint."""
        goal = self.make_goal()
        self.owe(goal, date(2026, 8, 14))
        self.subscribe()

        with mock.patch("coach.nudges.webpush") as sent:
            result = nudges.send_due(self.EVENING_IN_INDIA)

        self.assertEqual(sent.call_count, 0)
        self.assertEqual(result["sent"], 0)


class NudgeCopyTests(SimpleTestCase):
    """The words. They land on a lock screen with no app around them, so
    every one of them has to survive being read alone."""

    def test_the_task_is_quoted(self):
        body = prompts.nudge_body("write the problem statement")
        self.assertIn('"write the problem statement"', body)

    def test_a_long_task_is_clipped_and_the_instruction_survives(self):
        """The sentence after the quote is the part that says what to do. A
        task allowed to run on would push it off the end of the notification,
        leaving a builder with their own words and no ask."""
        body = prompts.nudge_body("x" * 400)
        self.assertLess(len(body), 200)
        self.assertIn("…", body)
        self.assertIn("The box is open", body)

    def test_an_empty_task_still_says_something(self):
        self.assertEqual(prompts.nudge_body("  "), prompts.NUDGE_BODY_NO_TASK)

    def test_it_does_not_shout(self):
        """No exclamation mark, no streak, no count of what breaks. The
        register is a coach holding you to your own word, not an app worried
        about its retention numbers."""
        for body in (prompts.nudge_body("a task"), prompts.NUDGE_BODY_NO_TASK):
            self.assertNotIn("!", body)
            self.assertNotIn("streak", body.lower())
            self.assertNotIn("don't forget", body.lower())


@override_settings(**PUSH_ON)
class PushSubscribeTests(CoachTestCase):
    """The builder's opt-in, arriving from a browser."""

    URL = "/api/coach/push/"
    BODY = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
        "keys": {"p256dh": "BPublicKey", "auth": "authsecret"},
        "timezone": "Asia/Kolkata",
    }

    def test_the_config_says_whether_this_deployment_can_push(self):
        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["configured"])
        self.assertEqual(res.data["public_key"], "test-public-key")
        self.assertEqual(res.data["evening_from"], nudges.EVENING_FROM)

    @override_settings(VAPID_PUBLIC_KEY="")
    def test_an_unconfigured_deployment_says_so_rather_than_offering(self):
        """The control draws nothing on this answer. A switch that 503s on
        press would spend the builder's one notification prompt for nothing."""
        self.assertFalse(self.client.get(self.URL).data["configured"])
        self.assertEqual(self.client.post(self.URL, self.BODY, format="json").status_code, 503)

    def test_subscribing_stores_the_three_strings_and_the_zone(self):
        res = self.client.post(self.URL, self.BODY, format="json")

        self.assertEqual(res.status_code, 201)
        sub = PushSubscription.objects.get()
        self.assertEqual(sub.user, self.alice)
        self.assertEqual(sub.endpoint, self.BODY["endpoint"])
        self.assertEqual(sub.p256dh, "BPublicKey")
        self.assertEqual(sub.auth, "authsecret")
        self.assertEqual(sub.timezone_name, "Asia/Kolkata")

    def test_the_same_browser_twice_is_one_row(self):
        """Re-subscribing is normal — a push service may rotate an endpoint
        at any time and the client asks on every visit. Two rows would be two
        buzzes for one device."""
        self.client.post(self.URL, self.BODY, format="json")
        moved = {**self.BODY, "timezone": "Europe/London"}
        res = self.client.post(self.URL, moved, format="json")

        self.assertEqual(res.status_code, 200)
        sub = PushSubscription.objects.get()
        # And the zone is refreshed, which is how a builder who moved starts
        # being nudged in the right evening rather than never.
        self.assertEqual(sub.timezone_name, "Europe/London")

    def test_a_zone_this_server_cannot_resolve_falls_back_to_utc(self):
        """Checked against tzdata rather than a regex. A name that only looks
        right stores fine and then nudges at the wrong hour forever."""
        res = self.client.post(
            self.URL, {**self.BODY, "timezone": "Mars/Olympus"}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(PushSubscription.objects.get().timezone_name, "UTC")

    def test_something_that_is_not_a_subscription_is_refused(self):
        for bad in (
            {**self.BODY, "endpoint": "http://not-https.example.com/x"},
            {**self.BODY, "endpoint": ""},
            {**self.BODY, "keys": {"p256dh": "", "auth": "a"}},
            {**self.BODY, "endpoint": "https://x.invalid/" + "y" * 3000},
        ):
            self.assertEqual(
                self.client.post(self.URL, bad, format="json").status_code, 400, bad
            )
        self.assertFalse(PushSubscription.objects.exists())

    def test_a_shared_browser_moves_the_row_to_whoever_signed_in(self):
        """The endpoint is the BROWSER's identity, not the person's. On a
        shared laptop the row follows the account, and the stamp is cleared
        with it — "already nudged today" was a fact about the builder who
        left."""
        self.client.post(self.URL, self.BODY, format="json")
        PushSubscription.objects.update(last_nudged_on=date(2026, 8, 14))

        self.client.force_authenticate(self.bob)
        self.client.post(self.URL, self.BODY, format="json")

        sub = PushSubscription.objects.get()
        self.assertEqual(sub.user, self.bob)
        self.assertIsNone(sub.last_nudged_on)

    def test_turning_it_off_removes_the_row(self):
        self.client.post(self.URL, self.BODY, format="json")
        res = self.client.delete(
            self.URL, {"endpoint": self.BODY["endpoint"]}, format="json"
        )
        self.assertEqual(res.status_code, 204)
        self.assertFalse(PushSubscription.objects.exists())

    def test_turning_it_off_cannot_reach_somebody_elses_device(self):
        """Tenancy again: knowing an endpoint is not a way to unsubscribe the
        person holding it."""
        self.client.post(self.URL, self.BODY, format="json")

        self.client.force_authenticate(self.bob)
        self.client.delete(self.URL, {"endpoint": self.BODY["endpoint"]}, format="json")

        self.assertEqual(PushSubscription.objects.get().user, self.alice)

    def test_signed_out_cannot_subscribe(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(self.URL, self.BODY, format="json").status_code, (401, 403))


@override_settings(**PUSH_ON)
class NudgeRunEndpointTests(CoachTestCase):
    """The one door the hourly workflow knocks on."""

    URL = "/api/coach/nudges/run/"

    def setUp(self):
        super().setUp()
        # The cron is not a browser. Every test here calls it the way the
        # workflow does — no session — and the one that checks a cookie is
        # ignored says so explicitly.
        self.client.force_authenticate(None)

    def test_the_right_token_runs_the_tick(self):
        with mock.patch("coach.nudges.send_due", return_value={"sent": 0}) as ran:
            res = self.client.post(self.URL, HTTP_X_NUDGE_TOKEN="test-nudge-token")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(ran.call_count, 1)

    def test_a_wrong_token_is_refused(self):
        with mock.patch("coach.nudges.send_due") as ran:
            res = self.client.post(self.URL, HTTP_X_NUDGE_TOKEN="not-it")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(ran.call_count, 0)

    def test_no_token_at_all_is_refused(self):
        with mock.patch("coach.nudges.send_due") as ran:
            res = self.client.post(self.URL)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(ran.call_count, 0)

    @override_settings(NUDGE_TOKEN="")
    def test_an_unset_secret_closes_the_door_rather_than_opening_it(self):
        """The security property of this whole endpoint, and the failure it
        is written against: `compare_digest("", "")` is True, so a view that
        compared before checking would answer an empty header on any
        deployment that had not set the secret yet."""
        for headers in ({}, {"HTTP_X_NUDGE_TOKEN": ""}, {"HTTP_X_NUDGE_TOKEN": "guess"}):
            with mock.patch("coach.nudges.send_due") as ran:
                res = self.client.post(self.URL, **headers)
            self.assertEqual(res.status_code, 503, headers)
            self.assertEqual(ran.call_count, 0)

    def test_a_signed_in_builder_cannot_fire_the_tick(self):
        """`authentication_classes = []`, so this view's answer never depends
        on whatever cookies rode along. A logged-in session is not the
        cron."""
        self.client.force_authenticate(self.alice)
        with mock.patch("coach.nudges.send_due") as ran:
            res = self.client.post(self.URL)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(ran.call_count, 0)


class VapidKeyFormatTests(SimpleTestCase):
    """The format DEPLOY.md §8.1 tells you to paste is the format the library
    actually parses.

    This exists because the obvious instruction is wrong, and wrong in a way
    nothing catches until a builder is waiting for a notification. `vapid
    --gen` is the tool every write-up reaches for; it produces a PEM, a PEM is
    what you would naturally paste into a Render dashboard, and pywebpush
    base64-decodes whatever string it is handed — so the `-----BEGIN` header
    comes back as "Could not deserialize key data", at send time, on the
    server, with nobody watching.

    So the doc says base64url raw, and this pins the doc: generate a keypair
    exactly the way §8.1 does and assert py_vapid both accepts the private
    half and derives the public half back. If a future pywebpush changes what
    it takes, this fails here rather than on somebody's evening.

    No key is committed. One is generated per run and thrown away, which is
    also why this is a SimpleTestCase — nothing here touches the database.
    """

    def generate(self) -> tuple[str, str]:
        """DEPLOY.md §8.1's one-liner, as code."""
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        def b64(raw: bytes) -> str:
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        key = ec.generate_private_key(ec.SECP256R1())
        return (
            b64(key.private_numbers().private_value.to_bytes(32, "big")),
            b64(
                key.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
            ),
        )

    def test_the_lengths_the_doc_states(self):
        """43 and 87. The doc says so, and a builder who pastes something of
        the wrong length should find out from the doc rather than from
        silence."""
        private, public = self.generate()
        self.assertEqual(len(private), 43)
        self.assertEqual(len(public), 87)

    def test_pywebpush_parses_the_private_half_and_agrees_on_the_public_one(self):
        from py_vapid import Vapid

        private, public = self.generate()
        loaded = Vapid.from_string(private)
        # `public_key` off a parsed private key is how the push service will
        # check the signature. If it disagrees with what the browser was
        # handed as applicationServerKey, every push is rejected.
        import base64

        from cryptography.hazmat.primitives import serialization

        derived = base64.urlsafe_b64encode(
            loaded.public_key.public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        ).rstrip(b"=").decode()
        self.assertEqual(derived, public)

    def test_a_pem_is_refused_which_is_why_the_doc_says_not_to(self):
        """The failure §8.1 warns about, pinned so the warning cannot quietly
        stop being true."""
        from py_vapid import Vapid

        # Deliberately not a key — the header is the whole point, and a real
        # one in a test file is a real one in the repository. What breaks
        # `from_string` is the `-----BEGIN` line, which it feeds straight to a
        # base64 decoder; the body never gets read.
        header, footer = "-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----"
        with self.assertRaises(Exception):
            Vapid.from_string(f"{header}\nnot-a-key\n{footer}\n")
