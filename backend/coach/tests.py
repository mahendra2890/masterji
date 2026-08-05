"""Coach API tests. The two invariants that matter most:

1. Tenancy — foreign goals 404 (never 403; nothing to probe).
2. The gate — no phase advances without accepted proofs, whoever asks.

LLM calls are stubbed: tests assert the server's decisions, not the model's
prose. The stock-fallback path (LLM down → proof still accepted) is a
feature and is tested as such.
"""

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from . import gates
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
        self._cycle("problem statement", "statement + 10 names")
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
