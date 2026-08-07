"""Coach API tests. The two invariants that matter most:

1. Tenancy — foreign goals 404 (never 403; nothing to probe).
2. The gate — no phase advances without accepted proofs, whoever asks.

LLM calls are stubbed: tests assert the server's decisions, not the model's
prose. The stock-fallback path (LLM down → proof still accepted) is a
feature and is tested as such.
"""

from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from . import gates, guidance
from .models import ChangelogEntry, CheckIn, Goal, Phase

User = get_user_model()


def make_user(name: str):
    return User.objects.create_user(
        username=name, email=f"{name}@example.com", password="pw"
    )


class CoachTestCase(APITestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.client.force_authenticate(self.alice)
        # No test reaches the network. Failing by default is deliberate: every
        # path that calls a model has a deterministic floor, and this makes
        # the whole suite exercise it unless a test says otherwise. Tests that
        # want a specific reply patch this again — the inner patch wins.
        patcher = mock.patch(
            "coach.views.llm.complete", side_effect=RuntimeError("no LLM in tests")
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_goal(self, user=None, **kwargs) -> Goal:
        kwargs.setdefault("title", "Tiffin app")
        return Goal.objects.create(user=user or self.alice, **kwargs)

    def accept_proofs(self, goal: Goal, n: int):
        """Bank n accepted proofs in the goal's CURRENT phase — the gate
        attributes by the stamped phase, exactly as the views write it."""
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=i),
                phase=goal.phase,
                am_declaration="talk to a customer",
                pm_proof_text="notes from the talk",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
            )


# --- the LLM seam ------------------------------------------------------------


class LlmSeamTests(SimpleTestCase):
    """Every model call must carry a timeout. Without one, a hung provider
    holds a gunicorn thread until the health check starts failing — that is
    an outage, discovered the hard way on the free instance.

    Deliberately NOT a CoachTestCase: that base patches llm.complete away,
    and these tests exist to exercise the real seam functions."""

    def fake_response(self):
        message = mock.Mock()
        message.content = "ok"
        choice = mock.Mock()
        choice.message = message
        response = mock.Mock()
        response.choices = [choice]
        return response

    def test_complete_is_bounded(self):
        from django.conf import settings as s

        from . import llm

        with mock.patch("coach.llm.litellm.completion", return_value=self.fake_response()) as call:
            llm.complete("system", "user")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)

    def test_complete_with_image_is_bounded(self):
        from django.conf import settings as s

        from . import llm

        with mock.patch("coach.llm.litellm.completion", return_value=self.fake_response()) as call:
            llm.complete_with_image("system", "user", b"\x89PNG", "image/png")
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)

    def test_stream_chat_is_bounded(self):
        from django.conf import settings as s

        from . import llm

        with mock.patch("coach.llm.litellm.completion", return_value=iter([])) as call:
            list(llm.stream_chat("system", []))
        self.assertEqual(call.call_args.kwargs["timeout"], s.LLM_TIMEOUT_S)


# --- auth ------------------------------------------------------------------


class AuthTests(CoachTestCase):
    def test_endpoints_require_auth(self):
        self.client.force_authenticate(None)
        for path in ["/api/coach/state/", "/api/coach/goals/"]:
            response = self.client.get(path) if "state" in path else self.client.post(path)
            self.assertEqual(response.status_code, 401, path)

    def test_chat_requires_auth(self):
        self.client.force_authenticate(None)
        response = self.client.post("/api/coach/chat/", {"content": "hi"})
        self.assertEqual(response.status_code, 401)


# --- goals + one-at-a-time ---------------------------------------------------


class GoalTests(CoachTestCase):
    def test_create_goal(self):
        response = self.client.post("/api/coach/goals/", {"title": "Tiffin app"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["phase"], "IDEA")

    def test_second_active_goal_rejected(self):
        self.make_goal()
        response = self.client.post("/api/coach/goals/", {"title": "Another one"})
        self.assertEqual(response.status_code, 400)

    def test_db_constraint_backs_the_rule(self):
        self.make_goal()
        with self.assertRaises(Exception):
            Goal.objects.create(user=self.alice, title="Sneaky second")

    def test_completed_goal_frees_the_slot(self):
        self.make_goal(status=Goal.Status.COMPLETED)
        response = self.client.post("/api/coach/goals/", {"title": "Next thing"})
        self.assertEqual(response.status_code, 201)


# --- tenancy -----------------------------------------------------------------


class TenancyTests(CoachTestCase):
    def test_foreign_goal_404s_not_403s(self):
        bobs_goal = self.make_goal(user=self.bob)
        response = self.client.post(f"/api/coach/goals/{bobs_goal.pk}/advance/")
        self.assertEqual(response.status_code, 404)

    def test_state_only_shows_own_goal(self):
        self.make_goal(user=self.bob, title="Bob's secret")
        response = self.client.get("/api/coach/state/")
        self.assertIsNone(response.data["goal"])


# --- the gate ----------------------------------------------------------------


class GateTests(CoachTestCase):
    def test_advance_with_zero_proofs_refused(self):
        goal = self.make_goal()
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["advanced"])
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "IDEA")

    def test_advance_with_enough_proofs(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)  # IDEA needs 1
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "VALIDATION")

    def test_proofs_reset_between_phases(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        # The IDEA proof must not count toward VALIDATION's 3.
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 409)

    def test_launch_is_final(self):
        goal = self.make_goal(phase="LAUNCH")
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 409)

    def test_refusal_names_the_next_action(self):
        """A refusal reaches the builder through the dashboard button with no
        LLM in the loop. If it doesn't say what to do tonight, nothing does."""
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 1)
        _, message = gates.try_advance(goal)
        self.assertIn("1/3 accepted proofs", message)
        self.assertIn(guidance.GATE_NUDGE[Phase.VALIDATION], message)

    def test_every_gated_phase_has_a_nudge(self):
        """PROOFS_REQUIRED and GATE_NUDGE have to cover the same phases — a
        phase that can refuse but has no nudge is the silent door again."""
        self.assertEqual(set(gates.PROOFS_REQUIRED), set(guidance.GATE_NUDGE))

    def test_idea_keeps_a_no_audience_example(self):
        """IDEA's second example — a route into a room of strangers, for a
        builder whose users never announce themselves anywhere countable — is
        load-bearing, not padding. One example gets read as the bar, and the
        hostel example alone sets it at "users you can already count", which
        is the reading that makes builders without an audience quit here."""
        examples = guidance.PROOF_EXAMPLES[Phase.IDEA]
        self.assertGreaterEqual(len(examples), 2)


# --- daily loop ----------------------------------------------------------------


class CheckInTests(CoachTestCase):
    def test_declare_then_prove(self):
        self.make_goal()
        response = self.client.post(
            "/api/coach/checkins/declare/", {"text": "call 3 tiffin cooks"}
        )
        self.assertEqual(response.status_code, 200)
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "Theek hai."}',
        ):
            response = self.client.post(
                "/api/coach/checkins/prove/", {"text": "called them, notes attached"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["checkin"]["proof_status"], "ACCEPTED")
        self.assertEqual(response.data["gate"]["have"], 1)
        self.assertEqual(response.data["streak"], 1)

    def test_prove_without_declaration_rejected(self):
        self.make_goal()
        response = self.client.post("/api/coach/checkins/prove/", {"text": "trust me"})
        self.assertEqual(response.status_code, 400)

    def test_llm_failure_still_accepts_proof(self):
        self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "ship the form"})
        with mock.patch("coach.views.llm.complete", side_effect=RuntimeError("down")):
            response = self.client.post(
                "/api/coach/checkins/prove/", {"text": "form is live", "url": "https://x.in"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["checkin"]["proof_status"], "ACCEPTED")

    def test_pushed_back_proof_does_not_count(self):
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "make a plan"})
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "push_back", "reaction": "A plan is not proof."}',
        ):
            response = self.client.post(
                "/api/coach/checkins/prove/", {"text": "wrote a plan"}
            )
        self.assertEqual(response.data["checkin"]["proof_status"], "PUSHED_BACK")
        self.assertEqual(response.data["gate"]["have"], 0)
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 409)


# --- state ---------------------------------------------------------------------


class DeclarationTests(CoachTestCase):
    """Declaring is coached, never refused. The model may object to what the
    builder picked; only gates.py may actually stop them."""

    JUDGEMENT = (
        '{"fit": "off_phase", "reaction": "That is BUILD talk and you have '
        'zero conversations.", "proof_ask": "Send me the three names and what '
        'each one said."}'
    )

    def declare(self, text="ship the landing page"):
        return self.client.post("/api/coach/checkins/declare/", {"text": text})

    def judge(self, pk):
        with mock.patch("coach.views.llm.complete", return_value=self.JUDGEMENT):
            return self.client.post(f"/api/coach/checkins/{pk}/judge/")

    def test_declaring_never_calls_a_model(self):
        """The morning write is the most repeated action in the product. If a
        model call creeps back into it, declaring gets slow again."""
        self.make_goal(phase="VALIDATION")
        with mock.patch("coach.views.llm.complete") as complete:
            response = self.declare()
        self.assertEqual(response.status_code, 200)
        complete.assert_not_called()
        self.assertEqual(response.data["declaration_fit"], "UNJUDGED")

    def test_off_phase_task_is_recorded_not_refused(self):
        goal = self.make_goal(phase="VALIDATION")
        declared = self.declare()
        self.assertEqual(declared.status_code, 200)
        response = self.judge(declared.data["id"])
        self.assertEqual(response.status_code, 200)
        checkin = CheckIn.objects.get(goal=goal)
        self.assertEqual(checkin.am_declaration, "ship the landing page")
        self.assertEqual(checkin.declaration_fit, "OFF_PHASE")

    def test_proof_ask_is_tailored_to_the_declared_task(self):
        self.make_goal(phase="VALIDATION")
        response = self.judge(self.declare().data["id"])
        self.assertEqual(
            response.data["proof_ask"],
            "Send me the three names and what each one said.",
        )

    def test_llm_down_leaves_it_unjudged(self):
        """No tailored ask is honest — a silent ON_PHASE would not be. The
        default patch in setUp already makes every model call fail."""
        goal = self.make_goal(phase="VALIDATION")
        declared = self.declare("talk to 3 shopkeepers")
        response = self.client.post(f"/api/coach/checkins/{declared.data['id']}/judge/")
        self.assertEqual(response.status_code, 200)
        checkin = CheckIn.objects.get(goal=goal)
        self.assertEqual(checkin.declaration_fit, "UNJUDGED")
        self.assertEqual(checkin.proof_ask, "")
        self.assertEqual(checkin.am_declaration, "talk to 3 shopkeepers")

    def test_editing_the_task_clears_a_stale_judgement(self):
        """A verdict on wording the builder has since replaced is worse than
        none — and the tailored ask would be asking for the old task."""
        goal = self.make_goal(phase="VALIDATION")
        self.judge(self.declare().data["id"])
        self.assertEqual(CheckIn.objects.get(goal=goal).declaration_fit, "OFF_PHASE")

        self.declare("talk to 3 shopkeepers instead")
        checkin = CheckIn.objects.get(goal=goal)
        self.assertEqual(checkin.declaration_fit, "UNJUDGED")
        self.assertEqual(checkin.declaration_reaction, "")
        self.assertEqual(checkin.proof_ask, "")

    def test_judging_a_foreign_checkin_404s(self):
        bobs_goal = self.make_goal(user=self.bob, phase="VALIDATION")
        checkin = CheckIn.objects.create(
            goal=bobs_goal,
            date=date.today(),
            phase="VALIDATION",
            am_declaration="bob's task",
        )
        response = self.client.post(f"/api/coach/checkins/{checkin.pk}/judge/")
        self.assertEqual(response.status_code, 404)

    def test_declaring_banks_no_proof(self):
        """Advisory means advisory: the morning judgement must not move the
        gate in either direction."""
        goal = self.make_goal(phase="VALIDATION")
        self.judge(self.declare().data["id"])
        self.assertEqual(gates.accepted_proofs(goal), 0)
        self.assertEqual(
            CheckIn.objects.get(goal=goal).proof_status, CheckIn.ProofStatus.NONE
        )


@override_settings(
    # Real settings rather than a patched is_configured(), so these tests
    # exercise the actual configured/unconfigured branch. Only the two calls
    # that would touch the network are mocked.
    R2_ENDPOINT="https://acct.r2.cloudflarestorage.com",
    R2_BUCKET="test-proofs",
    R2_ACCESS_KEY_ID="key",
    R2_SECRET_ACCESS_KEY="secret",
)
class ProofImageTests(CoachTestCase):
    """Screenshots corroborate a proof; they never decide one. Storage being
    absent, misconfigured or broken must cost the image and nothing else."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    def upload(self, content_type="image/png", data=None, name="proof.png"):
        return SimpleUploadedFile(name, data or self.PNG, content_type=content_type)

    def declare_today(self):
        self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "ship the form"})

    def prove(self, **extra):
        return self.client.post("/api/coach/checkins/prove/", {"text": "done", **extra})

    def test_image_is_stored_and_keyed_to_the_goal(self):
        self.declare_today()
        with mock.patch("coach.storage.put_image", return_value=True) as put:
            response = self.prove(image=self.upload())
        self.assertEqual(response.status_code, 200)
        key = CheckIn.objects.get().proof_image_key
        self.assertTrue(key.startswith("proofs/"))
        self.assertEqual(put.call_args.args[0], key)

    def test_a_dead_bucket_costs_the_image_not_the_proof(self):
        """The written proof is the record. If the upload fails the check-in
        still counts — otherwise object storage becomes a gate nobody voted
        for."""
        self.declare_today()
        with mock.patch("coach.storage.put_image", return_value=False):
            response = self.prove(image=self.upload())
        self.assertEqual(response.status_code, 200)
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_image_key, "")
        self.assertEqual(checkin.proof_status, CheckIn.ProofStatus.ACCEPTED)

    @override_settings(R2_ENDPOINT="", R2_BUCKET="")
    def test_unconfigured_storage_still_accepts_the_proof(self):
        self.declare_today()
        response = self.prove(image=self.upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CheckIn.objects.get().proof_image_key, "")
        self.assertFalse(self.client.get("/api/coach/state/").data["uploads_enabled"])

    def test_non_image_is_refused(self):
        self.declare_today()
        response = self.prove(
            image=self.upload(content_type="application/pdf", name="proof.pdf")
        )
        self.assertEqual(response.status_code, 400)

    def test_oversized_image_is_refused(self):
        self.declare_today()
        big = b"0" * (settings.PROOF_IMAGE_MAX_BYTES + 1)
        response = self.prove(image=self.upload(data=big))
        self.assertEqual(response.status_code, 400)

    def test_the_vision_model_grades_when_an_image_is_attached(self):
        self.declare_today()
        with (
            mock.patch("coach.storage.put_image", return_value=True),
            mock.patch(
                "coach.views.llm.complete_with_image",
                return_value='{"verdict": "push_back", "reaction": "That is your own '
                'draft, not a reply from anyone."}',
            ) as vision,
            mock.patch("coach.views.llm.complete") as text_only,
        ):
            self.prove(image=self.upload())
        vision.assert_called_once()
        text_only.assert_not_called()
        self.assertEqual(
            CheckIn.objects.get().proof_status, CheckIn.ProofStatus.PUSHED_BACK
        )

    def test_text_only_proof_does_not_reach_the_vision_model(self):
        """Vision costs more per call than text. No image, no vision."""
        self.declare_today()
        with (
            mock.patch("coach.views.llm.complete_with_image") as vision,
            mock.patch("coach.views.llm.complete", return_value="Noted.") as text_only,
        ):
            self.prove()
        vision.assert_not_called()
        text_only.assert_called_once()

    def test_vision_failure_falls_back_to_accept(self):
        """Same floor as every other model call — the day still counts."""
        self.declare_today()
        with (
            mock.patch("coach.storage.put_image", return_value=True),
            mock.patch(
                "coach.views.llm.complete_with_image",
                side_effect=RuntimeError("vision down"),
            ),
        ):
            response = self.prove(image=self.upload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CheckIn.objects.get().proof_status, CheckIn.ProofStatus.ACCEPTED
        )

    def test_image_url_is_signed_on_read_never_stored(self):
        """The key is what's persisted; the URL is minted per read and expires.
        Note the dashboard signs the same row more than once — it appears both
        as `today` and in `checkins` — which is fine because presigning is
        local HMAC work, not an API call."""
        self.declare_today()
        with mock.patch("coach.storage.put_image", return_value=True):
            self.prove(image=self.upload())
        key = CheckIn.objects.get().proof_image_key
        with mock.patch(
            "coach.storage.view_url", return_value="https://signed"
        ) as signer:
            response = self.client.get("/api/coach/state/")
        self.assertEqual(response.data["today"]["proof_image_url"], "https://signed")
        signer.assert_called_with(key)
        self.assertNotIn(key, str(response.data["today"]))


@override_settings(
    R2_ENDPOINT="https://acct.r2.cloudflarestorage.com",
    R2_BUCKET="test-proofs",
    R2_ACCESS_KEY_ID="key",
    R2_SECRET_ACCESS_KEY="secret",
)
class ProofResubmissionTests(CoachTestCase):
    """A pushed-back proof reopens the cycle; the retry must not erase the
    failed try, and must never inherit its evidence."""

    PUSH_BACK = '{"verdict": "push_back", "reaction": "That is your own ticket, not a user."}'
    ACCEPT = '{"verdict": "accept", "reaction": "Good. Real outreach."}'

    PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    def declare(self):
        self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "share the POC"})

    def submit(self, reply, text, with_image=False):
        payload = {"text": text}
        if with_image:
            payload["image"] = SimpleUploadedFile("shot.png", self.PNG, "image/png")
        with (
            mock.patch("coach.views.llm.complete", return_value=reply),
            mock.patch("coach.views.llm.complete_with_image", return_value=reply),
            mock.patch("coach.storage.put_image", return_value=True),
        ):
            return self.client.post("/api/coach/checkins/prove/", payload)

    def test_the_failed_try_moves_to_the_trail_with_its_image(self):
        self.declare()
        self.submit(self.PUSH_BACK, "made a ticket", with_image=True)
        rejected_key = CheckIn.objects.get().proof_image_key
        self.assertTrue(rejected_key)

        self.submit(self.ACCEPT, "DMed 4 builders, 2 replied")
        checkin = CheckIn.objects.get()
        attempt = checkin.attempts.get()
        self.assertEqual(attempt.text, "made a ticket")
        self.assertEqual(attempt.image_key, rejected_key)
        self.assertEqual(attempt.reaction, "That is your own ticket, not a user.")

    def test_accepted_proof_never_wears_the_rejected_image(self):
        """The bug as found in prod: resubmit without an image after a
        pushed-back image proof, and the old screenshot stayed attributed
        to the accepted proof."""
        self.declare()
        self.submit(self.PUSH_BACK, "made a ticket", with_image=True)
        self.submit(self.ACCEPT, "DMed 4 builders, 2 replied")
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_image_key, "")
        self.assertEqual(checkin.proof_status, CheckIn.ProofStatus.ACCEPTED)
        self.assertEqual(checkin.pm_proof_text, "DMed 4 builders, 2 replied")

    def test_first_accept_leaves_no_trail(self):
        self.declare()
        self.submit(self.ACCEPT, "DMed 4 builders")
        self.assertEqual(CheckIn.objects.get().attempts.count(), 0)

    def test_every_pushed_back_try_stacks(self):
        self.declare()
        self.submit(self.PUSH_BACK, "made a ticket")
        self.submit(self.PUSH_BACK, "made a nicer ticket")
        self.submit(self.ACCEPT, "actually talked to someone")
        texts = list(
            CheckIn.objects.get().attempts.values_list("text", flat=True)
        )
        self.assertEqual(texts, ["made a ticket", "made a nicer ticket"])

    def test_attempts_ride_the_state_payload(self):
        self.declare()
        self.submit(self.PUSH_BACK, "made a ticket", with_image=True)
        self.submit(self.ACCEPT, "talked to someone")
        with mock.patch("coach.storage.view_url", return_value="https://signed"):
            response = self.client.get("/api/coach/state/")
        attempts = response.data["today"]["attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["text"], "made a ticket")
        self.assertEqual(attempts[0]["image_url"], "https://signed")


class StateTests(CoachTestCase):
    def test_no_goal_state(self):
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["goal"])

    def test_state_shape(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.status_code, 200)
        for key in [
            "goal",
            "gate",
            "streak",
            "today",
            "checkins",
            "transitions",
            "messages",
            "phases",
        ]:
            self.assertIn(key, response.data)
        self.assertEqual(response.data["gate"], {"have": 1, "need": 1, "next_phase": "VALIDATION"})
        self.assertEqual(response.data["phases"], ["IDEA", "VALIDATION", "BUILD", "LAUNCH"])

    def test_state_carries_the_phase_guidance(self):
        """The dashboard renders these strings; it must not own a copy of
        them. Served from one place, so what the form promises and what the
        gate enforces cannot drift apart."""
        self.make_goal(phase="VALIDATION")
        response = self.client.get("/api/coach/state/")
        served = response.data["guidance"]
        self.assertEqual(served["phase_hint"], guidance.PHASE_HINT[Phase.VALIDATION])
        self.assertEqual(served["proof_hint"], guidance.PROOF_HINT[Phase.VALIDATION])
        self.assertTrue(served["proof_examples"])

    def test_guidance_covers_every_phase(self):
        """State is fetched for whatever phase the builder is in — a missing
        key is a 500 on the dashboard, not a missing paragraph."""
        for phase in Phase:
            with self.subTest(phase=phase):
                bundle = guidance.for_phase(phase)
                self.assertTrue(bundle["phase_hint"])
                self.assertTrue(bundle["proof_hint"])
                self.assertTrue(bundle["proof_examples"])

    def test_checkin_is_stamped_with_the_phase_it_was_made_in(self):
        """The drill-in attributes proofs by this field, not by date math."""
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "write it"})
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            self.client.post("/api/coach/checkins/prove/", {"text": "written"})
        self.assertEqual(CheckIn.objects.get(goal=goal).phase, "IDEA")

        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        # A later day's check-in belongs to the phase it was declared in.
        tomorrow = date.today() + timedelta(days=1)
        response = self.client.post(
            "/api/coach/checkins/declare/",
            {"text": "talk to cooks", "date": tomorrow.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CheckIn.objects.get(goal=goal, date=tomorrow).phase, "VALIDATION")

    def test_boundary_checkin_stays_with_the_phase_it_earned(self):
        """A client-local date on the far side of the UTC date boundary — the
        case that broke date-based attribution — must still resolve."""
        goal = self.make_goal()
        # Client says it's already tomorrow (IST after midnight); the server,
        # and therefore the transition it earns, is still on the previous UTC day.
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.client.post(
            "/api/coach/checkins/declare/", {"text": "late night push", "date": tomorrow}
        )
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            self.client.post("/api/coach/checkins/prove/", {"text": "done", "date": tomorrow})
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")

        checkin = CheckIn.objects.get(goal=goal, date=tomorrow)
        transition = goal.transitions.get()
        self.assertEqual(checkin.phase, "IDEA")
        # The proof's client date is AHEAD of the transition's UTC date, which
        # is exactly why the display must not compare the two.
        self.assertGreater(str(checkin.date), str(transition.created_at.date()))


class SameDayCyclesTests(CoachTestCase):
    """Real work counts when it happens. A builder who genuinely does more in
    a day may run more declare→prove cycles; the coach argues about pace in
    conversation rather than silently declining to count it."""

    def _cycle(self, task: str, proof: str):
        self.client.post("/api/coach/checkins/declare/", {"text": task})
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            return self.client.post("/api/coach/checkins/prove/", {"text": proof})

    def test_two_phases_in_one_day(self):
        goal = self.make_goal()
        self._cycle("problem statement", "statement + route")
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "VALIDATION")

        # VALIDATION wants 3 conversations — do all three the same afternoon.
        for i in range(3):
            response = self._cycle(f"conversation {i}", f"notes from person {i}")
            self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 200, response.data)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "BUILD")

        # Four cycles, one date, and the streak still counts it as ONE day.
        self.assertEqual(CheckIn.objects.filter(goal=goal).count(), 4)
        self.assertEqual(
            CheckIn.objects.filter(goal=goal).values("date").distinct().count(), 1
        )
        self.assertEqual(self.client.get("/api/coach/state/").data["streak"], 1)

    def test_only_one_cycle_open_at_a_time(self):
        """Declaring twice without proving edits the task on the hook rather
        than stacking a second one — and makes a double-tap idempotent."""
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "first wording"})
        self.client.post("/api/coach/checkins/declare/", {"text": "better wording"})
        self.assertEqual(CheckIn.objects.filter(goal=goal).count(), 1)
        self.assertEqual(
            CheckIn.objects.get(goal=goal).am_declaration, "better wording"
        )

    def test_pushed_back_proof_reopens_the_same_cycle(self):
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "make a plan"})
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "push_back", "reaction": "A plan is not proof."}',
        ):
            self.client.post("/api/coach/checkins/prove/", {"text": "wrote a plan"})
        # Answering the pushback must not require starting a new cycle.
        self._cycle("make a plan", "actually called two cooks")
        self.assertEqual(CheckIn.objects.filter(goal=goal).count(), 1)
        self.assertEqual(
            CheckIn.objects.get(goal=goal).proof_status, CheckIn.ProofStatus.ACCEPTED
        )


class HistoryDoesNotDriftTests(CoachTestCase):
    """Rows record the phase they happened in. Reading it off the goal instead
    made every past row appear to belong to whatever phase the goal reached —
    history rewriting itself in the admin every time you advanced."""

    def test_message_phase_is_frozen_at_write_time(self):
        # Through the API, so the welcome message is written the real way.
        self.client.post("/api/coach/goals/", {"title": "Tiffin app"})
        goal = Goal.objects.get(user=self.alice)
        welcome = goal.messages.get()
        self.assertEqual(welcome.phase, "IDEA")

        self.accept_proofs(goal, 1)
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")

        welcome.refresh_from_db()
        self.assertEqual(welcome.phase, "IDEA")  # not VALIDATION
        # The unlock announcement belongs to the phase it opened.
        self.assertEqual(goal.messages.order_by("-created_at").first().phase, "VALIDATION")

    def test_goal_label_carries_no_mutable_state(self):
        """Goal.__str__ renders next to rows written phases ago, so it must not
        embed the current phase."""
        goal = self.make_goal()
        self.assertEqual(str(goal), "Tiffin app")
        goal.phase = "BUILD"
        self.assertEqual(str(goal), "Tiffin app")


class RetireTests(CoachTestCase):
    """Retiring is always allowed and never silent. The verdict on whether the
    idea was actually tested is the server's, computed from earned proofs."""

    def _retire(self, goal, reason="Talked to 6 students, they won't pay.", path="retire"):
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            return self.client.post(f"/api/coach/goals/{goal.pk}/{path}/", {"reason": reason})

    def test_retiring_frees_the_slot(self):
        goal = self.make_goal()
        response = self._retire(goal)
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "ABANDONED")
        # And the builder can start the next idea immediately — no cooldown.
        self.assertEqual(
            self.client.post("/api/coach/goals/", {"title": "Next idea"}).status_code, 201
        )

    def test_reason_is_required(self):
        goal = self.make_goal()
        self.assertEqual(self._retire(goal, reason="   ").status_code, 400)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "ACTIVE")

    def test_no_minimum_age_or_proof_count(self):
        """The ten-minute mistake and the honest Tuesday-night kill must both
        be allowed; a gate here would be an invisible refusal."""
        goal = self.make_goal()
        self.assertEqual(gates.contact_proofs(goal), 0)
        self.assertEqual(self._retire(goal).status_code, 200)

    def test_untested_when_nobody_was_asked(self):
        goal = self.make_goal()
        self.assertEqual(self._retire(goal).data["reads_as"], "UNTESTED")

    def test_invalidated_when_the_work_was_done(self):
        """Contact with the world that said no is validation working — it must
        read differently from dropping the idea."""
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 2)
        self.assertEqual(self._retire(goal).data["reads_as"], "INVALIDATED")

    def test_desk_work_cannot_forge_the_verdict(self):
        """IDEA proofs are write-ups, not contact. Banking them must not buy an
        'idea disproved' label."""
        goal = self.make_goal(phase="IDEA")
        self.accept_proofs(goal, 3)  # all stamped IDEA
        self.assertEqual(self._retire(goal).data["reads_as"], "UNTESTED")

    def test_retiring_twice_is_a_voiced_conflict_not_a_404(self):
        goal = self.make_goal()
        self._retire(goal)
        again = self._retire(goal)
        self.assertEqual(again.status_code, 409)

    def test_a_past_goal_cannot_be_relabelled_a_win(self):
        """The confirmed abuse vector: history is not a toggle."""
        goal = self.make_goal()
        self._retire(goal)
        response = self._retire(goal, reason="Actually we shipped it", path="complete")
        self.assertEqual(response.status_code, 409)
        goal.refresh_from_db()
        self.assertEqual(goal.status, "ABANDONED")

    def test_foreign_goal_still_404s(self):
        bobs = self.make_goal(user=self.bob)
        self.assertEqual(self._retire(bobs).status_code, 404)

    def test_achieving_a_goal_is_never_blocked_by_phase(self):
        """Goals are the builder's own words — whether "the school site is live"
        is done isn't the server's call. Gating this on LAUNCH would just move
        the dead end it was supposed to remove."""
        goal = self.make_goal(phase="BUILD")
        self.accept_proofs(goal, 1)
        response = self._retire(goal, reason="Site is live, school uses it", path="complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reads_as"], "ACHIEVED")
        goal.refresh_from_db()
        self.assertEqual(goal.status, "COMPLETED")

    def test_any_accepted_proof_counts_as_achieved(self):
        """Work done while still in IDEA is still work. Talking to the principal
        during IDEA must not be reported back as "0 proofs"."""
        goal = self.make_goal(phase="IDEA")
        self.accept_proofs(goal, 1)  # stamped IDEA
        response = self._retire(goal, reason="Site is live", path="complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reads_as"], "ACHIEVED")
        self.assertEqual(response.data["retirement"]["accepted_proofs"], 1)

    def test_achieved_with_nothing_banked_reads_unverified(self):
        """Never blocked, never silently flattering: with nothing accepted at
        all there is simply nothing to point at."""
        goal = self.make_goal(phase="IDEA")
        response = self._retire(goal, reason="Finished it", path="complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reads_as"], "UNVERIFIED")
        goal.refresh_from_db()
        self.assertEqual(goal.status, "COMPLETED")

    def test_completion_still_needs_a_reason(self):
        goal = self.make_goal(phase="LAUNCH")
        self.assertEqual(self._retire(goal, reason="  ", path="complete").status_code, 400)

    def test_launch_goal_state_does_not_500(self):
        """A LAUNCH goal has no next phase — gate_status must not walk off the
        end of PHASE_ORDER."""
        goal = self.make_goal(phase="LAUNCH")
        self.accept_proofs(goal, 1)
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["at_finish_line"])

    def test_finish_line_is_prominence_not_permission(self):
        goal = self.make_goal(phase="BUILD")
        self.accept_proofs(goal, 1)
        self.assertFalse(self.client.get("/api/coach/state/").data["at_finish_line"])
        # ...and yet closing it as achieved works anyway.
        self.assertEqual(
            self._retire(goal, reason="Done and used", path="complete").status_code, 200
        )

    def test_archive_visible_while_a_new_goal_runs(self):
        """The record can't do its work if it only exists between goals."""
        old = self.make_goal(phase="VALIDATION")
        self.accept_proofs(old, 2)
        self._retire(old)
        self.client.post("/api/coach/goals/", {"title": "Next idea"})
        response = self.client.get("/api/coach/state/")
        self.assertIsNotNone(response.data["goal"])
        self.assertEqual(len(response.data["archive"]), 1)
        closed = response.data["archive"][0]
        # Enough to render the full story without another request.
        for key in ["title", "reason", "coach_reaction", "reads_as", "best_streak"]:
            self.assertIn(key, closed)
        self.assertEqual(closed["reads_as"], "INVALIDATED")

    def test_llm_down_still_retires(self):
        goal = self.make_goal()
        with mock.patch("coach.views.llm.complete", side_effect=RuntimeError("down")):
            response = self.client.post(
                f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Dropping it."}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["reaction"])
        goal.refresh_from_db()
        self.assertEqual(goal.status, "ABANDONED")

    def test_retired_goal_is_write_immutable(self):
        goal = self.make_goal()
        self._retire(goal)
        for path, payload in [
            ("checkins/declare/", {"text": "sneak"}),
            ("checkins/prove/", {"text": "sneak"}),
            ("chat/", {"content": "hi"}),
        ]:
            self.assertEqual(
                self.client.post(f"/api/coach/{path}", payload).status_code, 400, path
            )
        self.assertEqual(
            self.client.post(f"/api/coach/goals/{goal.pk}/advance/").status_code, 404
        )

    def test_archive_and_lifetime_survive_the_goal(self):
        """The work outlives the idea — otherwise retiring reads as punishment
        for doing the right thing."""
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 2)
        self._retire(goal)
        response = self.client.get("/api/coach/state/")
        self.assertIsNone(response.data["goal"])
        self.assertEqual(len(response.data["archive"]), 1)
        self.assertEqual(response.data["archive"][0]["reads_as"], "INVALIDATED")
        self.assertEqual(response.data["lifetime_days"], 2)

    def test_new_goal_starts_clean_but_keeps_the_record(self):
        old = self.make_goal(phase="VALIDATION")
        self.accept_proofs(old, 2)
        self._retire(old)
        self.client.post("/api/coach/goals/", {"title": "Next idea"})
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.data["gate"], {"have": 0, "need": 1, "next_phase": "VALIDATION"})
        self.assertEqual(response.data["streak"], 0)  # per-goal: this idea is new
        self.assertEqual(response.data["lifetime_days"], 2)  # per-user: work remembered
        self.assertEqual(len(response.data["archive"]), 1)

    def test_concurrent_goal_creation_is_a_400_not_a_500(self):
        """Retire makes goal creation routine, so the read-then-write race in
        GoalsView stops being theoretical."""
        self.make_goal()
        with mock.patch("coach.views._active_goal", return_value=None):
            response = self.client.post("/api/coach/goals/", {"title": "Race"})
        self.assertEqual(response.status_code, 400)


class GoalHistoryTests(CoachTestCase):
    """Reading back a closed idea's full record. Read-only by construction —
    a pk-addressable endpoint is exactly where write access would leak."""

    def test_closed_goal_history_is_readable(self):
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 2)
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            self.client.post(f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Dead."})
        response = self.client.get(f"/api/coach/goals/{goal.pk}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["checkins"]), 2)
        self.assertEqual(response.data["retirement"]["reads_as"], "INVALIDATED")
        self.assertEqual(response.data["goal"]["title"], "Tiffin app")

    def test_active_goal_history_also_works(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        response = self.client.get(f"/api/coach/goals/{goal.pk}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["retirement"])

    def test_foreign_goal_history_404s(self):
        bobs = self.make_goal(user=self.bob)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{bobs.pk}/history/").status_code, 404
        )

    def test_history_endpoint_is_read_only(self):
        goal = self.make_goal()
        for method in ("post", "patch", "delete"):
            response = getattr(self.client, method)(
                f"/api/coach/goals/{goal.pk}/history/"
            )
            self.assertEqual(response.status_code, 405, method)

    def test_history_requires_auth(self):
        goal = self.make_goal()
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.get(f"/api/coach/goals/{goal.pk}/history/").status_code, 401
        )

    def test_archive_carries_the_goal_id_for_drilling_in(self):
        goal = self.make_goal()
        with mock.patch("coach.views.llm.complete", return_value="Noted."):
            self.client.post(f"/api/coach/goals/{goal.pk}/retire/", {"reason": "Done."})
        archive = self.client.get("/api/coach/state/").data["archive"]
        self.assertEqual(archive[0]["goal"], goal.pk)


class LoopholeTests(CoachTestCase):
    """Two ways the gate could be walked past, both closed. These protect the
    product's central claim, so they are regression tests, not nice-to-haves."""

    def _prove(self, **extra):
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "ok"}',
        ):
            return self.client.post(
                "/api/coach/checkins/prove/", {"text": "real work", **extra}
            )

    def test_reproving_cannot_recycle_a_spent_proof(self):
        """Double-submitting proof used to re-credit it to the phase it had
        just unlocked — a second advance for one day's work, no API needed."""
        goal = self.make_goal()
        self.client.post("/api/coach/checkins/declare/", {"text": "problem statement"})
        self._prove()
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "VALIDATION")

        self._prove()  # the extra click
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.data["gate"]["have"], 0)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "VALIDATION")

    def test_backdated_checkins_are_refused(self):
        """Minting a week of past check-ins in one sitting would let a builder
        speed-run every phase; a real timezone is never more than a day off."""
        self.make_goal()
        for offset in (-3, -30, 5):
            day = (date.today() + timedelta(days=offset)).isoformat()
            response = self.client.post(
                "/api/coach/checkins/declare/", {"text": "backdated", "date": day}
            )
            self.assertEqual(response.status_code, 400, day)

    def test_real_timezone_offsets_still_accepted(self):
        """±1 day must keep working — that's every real UTC offset."""
        self.make_goal()
        for offset in (-1, 0, 1):
            day = (date.today() + timedelta(days=offset)).isoformat()
            response = self.client.post(
                "/api/coach/checkins/declare/", {"text": "legit", "date": day}
            )
            self.assertEqual(response.status_code, 200, day)

    def test_transitions_reflect_phase_advances(self):
        """The stepper drill-in relies on these boundaries — pin the shape."""
        goal = self.make_goal()
        self.assertEqual(self.client.get("/api/coach/state/").data["transitions"], [])
        self.accept_proofs(goal, 1)
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        response = self.client.get("/api/coach/state/")
        self.assertEqual(len(response.data["transitions"]), 1)
        transition = response.data["transitions"][0]
        self.assertEqual(transition["from_phase"], "IDEA")
        self.assertEqual(transition["to_phase"], "VALIDATION")
        self.assertTrue(transition["created_at"])


# --- chat ------------------------------------------------------------------------


class ChatTests(CoachTestCase):
    def _stream(self, events):
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)):
            response = self.client.post("/api/coach/chat/", {"content": "which stack?"})
            body = b"".join(response.streaming_content).decode()
        return response, body

    def test_chat_streams_and_persists(self):
        goal = self.make_goal()
        response, body = self._stream([("delta", "Kaam "), ("delta", "dikhao.")])
        self.assertEqual(response.status_code, 200)
        self.assertIn('"Kaam "', body)
        self.assertIn('"t": "done"', body)
        roles = list(goal.messages.values_list("role", flat=True))
        self.assertEqual(roles[-2:], ["USER", "COACH"])

    def test_chat_tool_call_hits_the_real_gate(self):
        goal = self.make_goal()  # zero proofs
        response, body = self._stream(
            [("delta", "Let's check."), ("tool_call", "propose_phase_advance")]
        )
        self.assertIn('"advanced": false', body)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "IDEA")

    def test_chat_without_goal_rejected(self):
        response = self.client.post("/api/coach/chat/", {"content": "hello"})
        self.assertEqual(response.status_code, 400)


class ChangelogTests(APITestCase):
    """The product's own record. Public, active-only, newest first — and, as
    the one unscoped table here, it must not leak a way to write to it."""

    def setUp(self):
        ChangelogEntry.all_objects.all().delete()  # the seeded history isn't the subject
        self.old = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 5), kind="NEW", title="first build", body="…"
        )
        self.new = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 8), kind="FIXED", title="a fix", body="…"
        )

    def test_readable_without_signing_in(self):
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [e["title"] for e in response.json()["entries"]], ["a fix", "first build"]
        )

    def test_inactive_entries_are_not_served(self):
        self.new.is_active = False
        self.new.save(update_fields=["is_active"])
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual([e["title"] for e in response.json()["entries"]], ["first build"])

    def test_soft_deleted_entries_are_not_served(self):
        self.old.delete()
        response = self.client.get("/api/coach/changelog/")
        self.assertEqual([e["title"] for e in response.json()["entries"]], ["a fix"])

    def test_same_day_entries_lead_with_the_newest_row(self):
        later = ChangelogEntry.objects.create(
            shipped_on=date(2026, 8, 8), kind="CHANGED", title="also today", body="…"
        )
        response = self.client.get("/api/coach/changelog/")
        titles = [e["title"] for e in response.json()["entries"]]
        self.assertEqual(titles[:2], [later.title, self.new.title])

    def test_endpoint_is_read_only(self):
        response = self.client.post(
            "/api/coach/changelog/", {"shipped_on": "2026-08-09", "title": "mine"}
        )
        self.assertEqual(response.status_code, 405)
        self.assertEqual(ChangelogEntry.objects.count(), 2)

    def test_seeded_history_ships_with_the_database(self):
        """The migration's entries are the product's record — a fresh database
        has them without anyone typing into the admin."""
        from django.db.migrations.loader import MigrationLoader

        self.assertIn(
            ("coach", "0011_seed_changelog"), MigrationLoader(None).graph.nodes
        )
