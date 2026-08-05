"""Coach API tests. The two invariants that matter most:

1. Tenancy — foreign goals 404 (never 403; nothing to probe).
2. The gate — no phase advances without accepted proofs, whoever asks.

LLM calls are stubbed: tests assert the server's decisions, not the model's
prose. The stock-fallback path (LLM down → proof still accepted) is a
feature and is tested as such.
"""

from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import CheckIn, Goal

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

    def make_goal(self, user=None, **kwargs) -> Goal:
        kwargs.setdefault("title", "Tiffin app")
        return Goal.objects.create(user=user or self.alice, **kwargs)

    def accept_proofs(self, goal: Goal, n: int):
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date(2026, 8, i + 1),
                am_declaration="talk to a customer",
                pm_proof_text="notes from the talk",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
            )


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
        for key in ["goal", "gate", "streak", "today", "checkins", "messages", "phases"]:
            self.assertIn(key, response.data)
        self.assertEqual(response.data["gate"], {"have": 1, "need": 1, "next_phase": "VALIDATION"})
        self.assertEqual(response.data["phases"], ["IDEA", "VALIDATION", "BUILD", "LAUNCH"])


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
