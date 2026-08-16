"""The goal itself: signing in, one at a time, tenancy, pivoting, retiring, the
title, the brief, the launch date and the phase's stated intent.
"""

from datetime import date, timedelta
from unittest import mock

from .. import (
    gates,
    guidance,
    judging,
    prompts,
    views,
)
from ..models import (
    CheckIn,
    Goal,
    GoalRetirement,
    LaunchCommitment,
    Message,
    Phase,
)
from .base import CoachTestCase, _state_launch

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


# --- daily loop ----------------------------------------------------------------


class PivotTests(CoachTestCase):
    """Same problem, new idea — the commonest real journey event between
    VALIDATION and BUILD, and the one the product used to punish.

    The whole of what is pinned here: a pivot carries KNOWLEDGE and never
    CREDIT. Everything the builder learned travels; not one row of what they
    earned does, and the successor's first proof is owed exactly as if they had
    started from nothing — which, as far as gates.py is concerned, they have.
    """

    def pivot(self, title="Mess-counter board for Block C"):
        parent = self.make_goal(phase=Phase.VALIDATION)
        self.accept_proofs(parent, 2)
        self.client.post(
            f"/api/coach/goals/{parent.id}/retire/",
            {"reason": "Nobody wants a tiffin service. They want to know what's left."},
        )
        created = self.client.post(
            "/api/coach/goals/", {"title": title, "pivoted_from": parent.id}
        ).json()
        return parent, Goal.objects.get(id=created["id"])

    def test_the_successor_starts_at_idea_with_nothing_banked(self):
        """The gate is never seeded. IDEA's one proof is still owed, and
        writing the new problem statement is that decision made concrete."""
        parent, successor = self.pivot()
        self.assertEqual(successor.pivoted_from_id, parent.id)
        self.assertEqual(successor.phase, Phase.IDEA)
        self.assertEqual(gates.accepted_proofs(successor), 0)
        self.assertEqual(gates.accepted_proofs_total(successor), 0)
        advanced, _ = gates.try_advance(successor)
        self.assertFalse(advanced)

    def test_the_parent_closes_as_it_would_have_anyway(self):
        """No new self-declared verdict. A contact-free pivot still reads
        UNTESTED, because calling it a pivot is not evidence of anything."""
        parent, _ = self.pivot()
        retirement = GoalRetirement.objects.get(goal=parent)
        self.assertEqual(retirement.outcome, GoalRetirement.Outcome.ABANDONED)
        self.assertEqual(
            gates.reads_as(parent, retirement.outcome),
            gates.reads_as(parent, GoalRetirement.Outcome.ABANDONED),
        )

    def test_the_coach_inherits_the_facts_and_is_told_they_are_not_counts(self):
        parent, successor = self.pivot()
        text = prompts.build_system_prompt(
            successor,
            gates.gate_status(successor),
            0,
            "nothing yet",
            "ENGLISH",
            predecessor=views._predecessor(successor),
        )
        self.assertIn(parent.title, text)
        # The guard that keeps the block from leaking into the gate.
        self.assertIn("NONE OF IT COUNTS HERE", text)
        self.assertIn("its first proof is still owed", text)

    def test_a_parent_that_banked_nothing_says_nothing(self):
        """Naming a dead idea and then reporting it produced nothing is a
        paragraph about failure with no facts in it, on the first morning of
        the thing that replaced it."""
        parent = self.make_goal()
        self.client.post(f"/api/coach/goals/{parent.id}/retire/", {"reason": "no"})
        created = self.client.post(
            "/api/coach/goals/", {"title": "Second", "pivoted_from": parent.id}
        ).json()
        successor = Goal.objects.get(id=created["id"])
        self.assertEqual(successor.pivoted_from_id, parent.id)
        self.assertIsNone(views._predecessor(successor))

    def test_a_link_to_somebody_elses_goal_is_dropped_not_honoured(self):
        bobs = self.make_goal(user=self.bob)
        created = self.client.post(
            "/api/coach/goals/", {"title": "Mine", "pivoted_from": bobs.id}
        )
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(Goal.objects.get(id=created.json()["id"]).pivoted_from_id)

    def test_a_link_to_a_goal_still_running_is_dropped(self):
        """A pivot is from something CLOSED. Linking a live goal would be one
        builder with two goals, described in a field instead of a row."""
        live = self.make_goal()
        self.client.post(f"/api/coach/goals/{live.id}/retire/", {"reason": "done"})
        second = self.client.post("/api/coach/goals/", {"title": "Second"}).json()
        third = self.client.post(
            "/api/coach/goals/", {"title": "Third", "pivoted_from": second["id"]}
        )
        # Refused for the ordinary reason — one goal at a time — and the link
        # never gets the chance to be the thing that let a second one exist.
        self.assertEqual(third.status_code, 400)

    def test_a_stale_link_does_not_cost_them_the_commit(self):
        """The goal is what they are committing to; the link is a footnote.
        Refusing the whole commit over it would be the app losing their
        sentence to protect the footnote."""
        created = self.client.post(
            "/api/coach/goals/", {"title": "Mine", "pivoted_from": 999999}
        )
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(Goal.objects.get(id=created.json()["id"]).pivoted_from_id)


class LaunchDateTests(CoachTestCase):
    """A date the builder named, and the trail of every time they moved it.

    What is pinned: the trail is the whole consequence. Nothing here refuses
    anything — no gate reads the table, a blown date costs no proof and no
    streak — so every test below is either about the arithmetic being honest or
    about the product declining to punish somebody for it.
    """

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.BUILD)
        self.today = date.today()

    def name_date(self, when: date, pond="ROOMS"):
        return self.client.post(
            f"/api/coach/goals/{self.goal.id}/launch/",
            {"date": when.isoformat(), "pond": pond},
        )

    def test_a_move_is_a_second_row_and_the_trail_says_so(self):
        """Never an update. What the record holds is not "26 August" but
        "declared the 24th, moved once, currently the 26th" — the visible slip
        trail IS the commitment device, since nothing else costs anything."""
        first, second = self.today + timedelta(days=7), self.today + timedelta(days=9)
        self.name_date(first)
        response = self.name_date(second)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["date"], second.isoformat())
        self.assertEqual(body["first"], first.isoformat())
        self.assertEqual(body["moves"], 1)
        self.assertEqual(body["days_out"], 9)
        self.assertEqual(self.goal.launch_commitments.count(), 2)

    def test_naming_one_for_the_first_time_is_not_a_slip(self):
        self.name_date(self.today + timedelta(days=5))
        self.assertEqual(_state_launch(self.client)["moves"], 0)

    def test_saying_the_same_thing_twice_does_not_write_a_slip(self):
        """A double tap, or a builder confirming what they already said. A row
        for it would put a move on the record that never happened."""
        when = self.today + timedelta(days=5)
        self.name_date(when)
        self.name_date(when)
        self.assertEqual(self.goal.launch_commitments.count(), 1)
        self.assertEqual(_state_launch(self.client)["moves"], 0)

    def test_a_date_that_has_come_and_gone_refuses_nothing(self):
        """The one that matters. A blown date is the case this feature exists
        for, and the product's answer to it is a negative number and a
        sentence — never a gate, a lost streak or a refused proof."""
        self.name_date(self.today + timedelta(days=1))
        LaunchCommitment.objects.filter(goal=self.goal).update(
            date=self.today - timedelta(days=3)
        )
        self.accept_proofs(self.goal, gates.PROOFS_REQUIRED[Phase.BUILD].n)
        response = self.client.post(f"/api/coach/goals/{self.goal.id}/advance/")
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.LAUNCH)

    def test_the_coach_is_told_the_date_and_told_not_to_wield_it(self):
        text = prompts.launch_line(
            {
                "date": "2026-08-26",
                "pond_label": "The rooms they sit in",
                "days_out": 9,
                "moves": 1,
                "first": "2026-08-24",
            }
        )
        self.assertIn("2026-08-26", text)
        self.assertIn("9 days out", text)
        self.assertIn("moved 1 time", text)
        self.assertIn("The rooms they sit in", text)
        self.assertIn("nothing refuses them if it slips", text)
        # And absent entirely when they never named one — no default date, and
        # no line in the state block about a thing that does not exist.
        self.assertEqual(prompts.launch_line(None), "")

    def test_a_date_needs_something_to_launch(self):
        """Not a fifth thing to have declared on day one."""
        early = self.make_goal(user=self.bob, phase=Phase.IDEA)
        self.client.force_authenticate(self.bob)
        response = self.client.post(
            f"/api/coach/goals/{early.id}/launch/",
            {"date": (self.today + timedelta(days=5)).isoformat(), "pond": "ROOMS"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("once you're building", response.json()["detail"])

    def test_yesterday_and_a_made_up_room_are_both_refused(self):
        self.assertEqual(self.name_date(self.today - timedelta(days=1)).status_code, 400)
        self.assertEqual(
            self.name_date(self.today + timedelta(days=3), pond="SOMEWHERE").status_code,
            400,
        )
        self.assertFalse(self.goal.launch_commitments.exists())

    def test_the_ponds_are_the_playbooks_ladder(self):
        """Named rungs rather than free text: the ladder belongs to
        launch-checklist.md, and a builder inventing a fifth rung is a builder
        avoiding the four."""
        ponds = self.client.get("/api/coach/state/").json()["ponds"]
        self.assertEqual(
            [p["value"] for p in ponds], ["TALKED", "ROOMS", "PUBLIC", "ASK"]
        )

    def test_the_date_is_the_builders_own(self):
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.name_date(self.today + timedelta(days=5)).status_code, 404)


class PhaseIntentTests(CoachTestCase):
    """One line at every unlock: what this phase will produce.

    A phase has a bar and no shape — PHASE_HINT[BUILD] is the same sentence for
    every builder forever — so the coach could tell whether tonight's task was
    on-phase for BUILD in general and never whether it was the thing this
    builder said on Monday. What is pinned here is that the line is the only
    thing that changed: the ladder is the same length, the gate reads nothing,
    and skipping it costs a builder nothing at all.
    """

    def advance(self, goal: Goal) -> Goal:
        need = gates.PROOFS_REQUIRED[Phase(goal.phase)]
        self.accept_proofs(goal, need.n)
        self.client.post(f"/api/coach/goals/{goal.id}/advance/")
        goal.refresh_from_db()
        return goal

    def set_intent(self, goal: Goal, text: str):
        return self.client.post(f"/api/coach/goals/{goal.id}/intent/", {"intent": text})

    def test_the_line_lands_on_the_row_that_opened_this_phase(self):
        goal = self.advance(self.make_goal())
        self.assertEqual(goal.phase, Phase.VALIDATION)
        response = self.set_intent(goal, "  three hostellers  who\n pay today  ")
        self.assertEqual(response.status_code, 200)

        transition = goal.transitions.get(to_phase=Phase.VALIDATION)
        # Collapsed, not stored as typed: it is one line by construction, and a
        # newline in it would arrive in the prompt as a new instruction.
        self.assertEqual(transition.intent, "three hostellers who pay today")

    def test_idea_has_no_unlock_to_describe(self):
        """Nothing opened IDEA, so there was no moment at which to ask. A 409
        rather than a 404: the goal is real and it is the moment that is wrong."""
        goal = self.make_goal()
        response = self.set_intent(goal, "something")
        self.assertEqual(response.status_code, 409)
        self.assertIn("where you started", response.json()["detail"])

    def test_the_coach_is_told_what_they_said_and_that_it_is_not_the_gate(self):
        goal = self.advance(self.make_goal())
        self.set_intent(goal, "three hostellers who pay today")
        text = prompts.build_system_prompt(
            goal,
            gates.gate_status(goal),
            0,
            "nothing yet",
            "ENGLISH",
            intent="three hostellers who pay today",
        )
        self.assertIn("three hostellers who pay today", text)
        # The two things that keep it from becoming a second bar.
        self.assertIn("it is not a promise you hold them to", text)
        self.assertIn("a phase is cleared by proofs whatever this says", text)

    def test_a_phase_with_nothing_said_about_it_says_nothing(self):
        """Absent rather than defaulted. A coach told "what this phase will
        produce: (not set)" has a fact about the app's own form in the block
        whose whole authority is that everything in it is true of the builder."""
        goal = self.advance(self.make_goal())
        self.assertEqual(prompts.intent_block("", Phase.VALIDATION), "")
        text = prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "nothing yet", "ENGLISH"
        )
        self.assertNotIn("WHAT THEY SAID THIS PHASE WOULD PRODUCE", text)

    def test_the_morning_reads_it_as_context_and_not_as_a_test(self):
        """`fit` is advisory and an off-phase task still earns its proof. A
        builder's own sentence must not quietly become a tighter gate on their
        day than the phase itself is."""
        text = prompts.DECLARATION_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            tone_rule="",
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
            phase=Phase.VALIDATION,
            phase_rules=prompts.PHASE_RULES[Phase.VALIDATION],
            proof_hint=guidance.PROOF_HINT[Phase.VALIDATION],
            intent=prompts.declaration_intent("three hostellers who pay today"),
        )
        self.assertIn("three hostellers who pay today", text)
        self.assertIn("context for your reaction, never a second test", text)

    def test_skipping_it_advances_the_phase_exactly_as_before(self):
        """Not a gate, and this is the test that says so: a goal that never
        answers walks the whole ladder."""
        goal = self.make_goal()
        for _ in range(3):
            goal = self.advance(goal)
        self.assertEqual(goal.phase, Phase.LAUNCH)
        self.assertEqual(goal.transitions.count(), 3)
        self.assertEqual([t.intent for t in goal.transitions.all()], ["", "", ""])

    def test_the_next_phase_cannot_overwrite_the_last_ones_answer(self):
        """The whole reason it lives on PhaseTransition. A field on the Goal
        would keep only the newest, and the record would then say the builder
        had always meant whatever they most recently said."""
        goal = self.advance(self.make_goal())
        self.set_intent(goal, "three hostellers who pay today")
        goal = self.advance(goal)
        self.set_intent(goal, "one screen they can actually open")

        by_phase = {t.to_phase: t.intent for t in goal.transitions.all()}
        self.assertEqual(by_phase[Phase.VALIDATION], "three hostellers who pay today")
        self.assertEqual(by_phase[Phase.BUILD], "one screen they can actually open")
        # And the coach reads the one for the phase they are standing in.
        self.assertEqual(judging._phase_intent(goal), "one screen they can actually open")

    def test_it_can_be_fixed_while_the_phase_is_open(self):
        """Write-once buys a tidier record at the cost of a builder living for
        three weeks under a typo, with a coach quoting it back at them."""
        goal = self.advance(self.make_goal())
        self.set_intent(goal, "three hostlers")
        self.set_intent(goal, "three hostellers who pay today")
        self.assertEqual(judging._phase_intent(goal), "three hostellers who pay today")
        self.assertEqual(goal.transitions.count(), 1)

    def test_an_empty_line_and_a_paragraph_are_both_refused(self):
        goal = self.advance(self.make_goal())
        self.assertEqual(self.set_intent(goal, "   ").status_code, 400)
        self.assertEqual(
            self.set_intent(goal, "x" * (views.PhaseIntentView.MAX_CHARS + 1)).status_code,
            400,
        )
        self.assertEqual(judging._phase_intent(goal), "")

    def test_the_phase_is_the_builders_own(self):
        goal = self.advance(self.make_goal())
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.set_intent(goal, "mine now").status_code, 404)


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

    def test_terminal_goal_state_does_not_500(self):
        """The last phase has no next phase — gate_status must not walk off the
        end of PHASE_ORDER. The guard moved up the ladder with the ladder:
        LAUNCH has somewhere to advance to now, and TRACTION is the end."""
        goal = self.make_goal(phase="TRACTION")
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

    def test_arriving_at_launch_does_not_light_the_finish_line(self):
        """The proofs that paid for the BUILD exit are not evidence about
        LAUNCH. A goal cannot reach LAUNCH without banking proof — that is what
        the gate is for — so counting every proof ever banked lit "Claim the
        win" on the first morning of the phase whose own bar had seen nothing,
        offering the exit right before the public post.

        Advanced through the real endpoint: the stamp on a check-in is written
        when the row is created and never rewritten, so proofs earned in BUILD
        stay BUILD's however far the goal travels afterwards.
        """
        goal = self.make_goal(phase="BUILD")
        self.accept_proofs(goal, gates.PROOFS_REQUIRED[Phase.BUILD].n)
        self.assertEqual(
            self.client.post(f"/api/coach/goals/{goal.pk}/advance/").status_code, 200
        )
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "LAUNCH")
        self.assertTrue(gates.accepted_proofs_total(goal))  # the work is on the record
        self.assertFalse(self.client.get("/api/coach/state/").data["at_finish_line"])

    def test_the_finish_line_waits_for_the_phase_after_the_post(self):
        """The button moved up with the ladder. A LAUNCH proof is the post
        going out — the thing TRACTION exists to follow, not the end of the
        arc — so a full LAUNCH shelf still leaves the win button dark, and the
        phase that lights it is the one whose bar is somebody coming back or
        paying. One TRACTION proof is enough; TRACTION has no count to finish.
        """
        goal = self.make_goal(phase="LAUNCH")
        self.accept_proofs(goal, gates.PROOFS_REQUIRED[Phase.LAUNCH].n)
        self.assertFalse(self.client.get("/api/coach/state/").data["at_finish_line"])
        goal.phase = Phase.TRACTION
        goal.save(update_fields=["phase"])
        self.accept_proofs(goal, 1)
        self.assertTrue(self.client.get("/api/coach/state/").data["at_finish_line"])

    def test_a_dark_finish_line_still_closes_as_achieved(self):
        """Prominence, never permission — the half this change must not break.
        A builder who launched before they found the app, or who is simply
        done, keeps the quiet link and the honest reading: reads_as still
        counts every proof ever banked, so the BUILD work behind them is what
        makes it ACHIEVED rather than UNVERIFIED.
        """
        goal = self.make_goal(phase="LAUNCH")
        CheckIn.objects.create(
            goal=goal,
            date=date.today(),
            phase="BUILD",
            am_declaration="ship the form",
            pm_proof_text="link to the live form",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
        )
        self.assertFalse(self.client.get("/api/coach/state/").data["at_finish_line"])
        response = self._retire(goal, reason="It's live and in use", path="complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reads_as"], "ACHIEVED")

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
        self.assertEqual(
            response.data["gate"],
            {"have": 0, "need": 1, "next_phase": "VALIDATION", "owed": [], "banked": 0},
        )
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


# --- sharpening the wording, while nothing points at it ----------------------


class GoalTitleEditTests(CoachTestCase):
    """A mis-phrased goal used to cost retire-and-recreate, which zeroes
    days_active and the streak — so builders pre-polished the title at the
    commit box, which IS the freeze the product is trying to end.

    The lock is a server count, checked in the view: gates.py gains nothing, and
    "nothing is banked yet" is not a judgement call.
    """

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(title="tiffin app")

    def patch(self, goal=None, **data):
        return self.client.patch(
            f"/api/coach/goals/{(goal or self.goal).pk}/", data, format="json"
        )

    def test_the_wording_can_be_sharpened_while_nothing_is_banked(self):
        response = self.patch(title="mess-shut nights on the hostel floor")
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.title, "mess-shut nights on the hostel floor")

    def test_a_banked_proof_locks_the_title(self):
        """Past the first accepted proof the record points at this wording, and
        rewriting it would rewrite what those evenings were for. 409, the same
        answer the gate gives when the record is what refuses."""
        self.accept_proofs(self.goal, 1)
        response = self.patch(title="something else entirely")
        self.assertEqual(response.status_code, 409)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.title, "tiffin app")

    def test_the_lock_counts_every_phase_not_just_this_one(self):
        """accepted_proofs_total, not accepted_proofs: a proof banked in IDEA is
        still a proof that points at this wording after the goal reaches
        VALIDATION, and the phase-scoped count would read zero there and quietly
        unlock the title again."""
        self.accept_proofs(self.goal, 1)
        self.goal.phase = Phase.VALIDATION
        self.goal.save(update_fields=["phase"])
        self.assertEqual(gates.accepted_proofs(self.goal), 0)
        self.assertEqual(self.patch(title="new wording").status_code, 409)

    def test_the_rename_is_on_the_record(self):
        """The transcript is the memory. A title that changed with nothing said
        about it makes every earlier message read as though it were always about
        the new wording."""
        self.patch(title="mess-shut nights")
        message = self.goal.messages.latest("id")
        self.assertEqual(message.role, Message.Role.COACH)
        self.assertIn("mess-shut nights", message.content)

    def test_the_phase_is_not_reachable_from_here(self):
        """The one thing this endpoint must never be: a way past the gate."""
        response = self.patch(title="fine", phase=Phase.LAUNCH, status="RETIRED")
        self.assertEqual(response.status_code, 200)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.IDEA)
        self.assertEqual(self.goal.status, Goal.Status.ACTIVE)

    def test_an_empty_title_is_not_a_sharpening(self):
        self.assertEqual(self.patch(title="   ").status_code, 400)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.title, "tiffin app")

    def test_a_foreign_goal_is_not_found(self):
        self.assertEqual(self.patch(goal=self.make_goal(user=self.bob)).status_code, 404)

    def test_a_closed_goal_keeps_its_wording(self):
        """Retired goals are write-immutable through the API — the record has to
        outlive the idea, and GoalHistoryView is read-only for the same reason."""
        self.goal.status = Goal.Status.ABANDONED
        self.goal.save(update_fields=["status"])
        self.assertEqual(self.patch(title="rewriting history").status_code, 404)


class GoalBriefTests(CoachTestCase):
    """What the goal knows about the idea, as opposed to what it is called.

    The issue that asked for this said the brief could be populated "through
    bar.labels(), which already extracts exactly these". It does not: labels()
    returns which parts an answer satisfied and never their values, which
    CheckIn.proof_parts states as a rule — "the keys only, never the values,
    because the values are the proof text and it is already on the row". That is
    the same mistake ProofLabelsTests above documents one field over, so these
    tests pin the shape that is actually available: the accepted IDEA proof's
    own words, with the keys as provenance beside them.
    """

    ACCEPT = (
        '{"verdict": "accept", "reaction": "That is the problem, named.", '
        '"parts": ["problem", "place", "why_there", "first_conversation"], '
        '"subject": ""}'
    )
    PUSH_BACK = '{"verdict": "push_back", "reaction": "Which room, exactly?"}'
    IDEA_TEXT = (
        "Hostellers at Ramaiah eat 20 meals a week they didn't choose. They "
        "keep a WhatsApp group to swap plates, and it dies every month. "
        "They're in the mess queue at 8pm. I'd stand in it on Thursday."
    )

    def prove(self, goal, text, reply):
        self.client.post("/api/coach/checkins/declare/", {"text": "write it up"})
        with mock.patch("coach.views.llm.complete", return_value=reply):
            self.client.post("/api/coach/checkins/prove/", {"text": text})
        goal.refresh_from_db()
        return goal

    def test_the_accepted_idea_proof_becomes_the_goals_body(self):
        """The one write. Before it, `title` was the whole of what this row knew
        about the thing being built."""
        goal = self.prove(self.make_goal(), self.IDEA_TEXT, self.ACCEPT)
        self.assertEqual(goal.brief["text"], self.IDEA_TEXT)
        self.assertEqual(
            goal.brief["parts"], ["problem", "place", "why_there", "first_conversation"]
        )
        self.assertEqual(goal.brief["source"], "PROOF")

    def test_a_brief_the_builder_wrote_is_never_overwritten(self):
        """Their words outrank the filing. A builder who wrote the idea down
        before anything banked — or the workshop that wrote it for them at
        commit — said what the idea is, and the proof arriving later is evidence
        about it, not a replacement for it."""
        goal = self.make_goal()
        goal.brief = {"text": "mine", "parts": [], "source": "BUILDER"}
        goal.save(update_fields=["brief"])
        goal = self.prove(goal, self.IDEA_TEXT, self.ACCEPT)
        self.assertEqual(goal.brief["text"], "mine")
        self.assertEqual(goal.brief["source"], "BUILDER")

    def test_a_refused_proof_is_not_the_idea(self):
        """A pushed-back evening is text the gate declined. Writing it here
        would put refused words into the prompt under a heading that calls them
        what the builder is testing."""
        goal = self.prove(self.make_goal(), self.IDEA_TEXT, self.PUSH_BACK)
        self.assertEqual(goal.brief, {})

    def test_a_later_phase_cannot_rewrite_the_idea(self):
        """VALIDATION's evenings are evidence ABOUT the idea. One of them
        landing in this field would silently replace the problem statement with
        a conversation about it."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        goal = self.prove(
            goal,
            "Spoke to Priya in the mess queue.",
            '{"verdict": "accept", "reaction": "Counted.", '
            '"parts": ["who"], "subject": "Priya"}',
        )
        self.assertEqual(goal.brief, {})

    def test_the_brief_is_the_builders_to_sharpen_until_something_banks(self):
        """The same window as the title (#114), and for the same reason: past
        the first accepted proof the record points at this, and rewriting it
        would rewrite what those evenings were for."""
        goal = self.make_goal()
        # json, not the suite's default multipart: `brief` is an object, and
        # multipart cannot carry a nested one. The client sends JSON here.
        response = self.client.patch(
            f"/api/coach/goals/{goal.id}/",
            {"brief": {"text": "  the  idea  "}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.brief["text"], "the idea")
        self.assertEqual(goal.brief["source"], "BUILDER")

        CheckIn.objects.create(
            goal=goal,
            date=date.today(),
            phase=goal.phase,
            am_declaration="write it up",
            pm_proof_text="notes",
            proof_status=CheckIn.ProofStatus.ACCEPTED,
        )
        locked = self.client.patch(
            f"/api/coach/goals/{goal.id}/",
            {"brief": {"text": "second thoughts"}},
            format="json",
        )
        self.assertEqual(locked.status_code, 409)
        goal.refresh_from_db()
        self.assertEqual(goal.brief["text"], "the idea")

    def test_the_prompt_carries_the_idea_and_only_when_there_is_one(self):
        """The point of copying the text onto the goal at all. `_banked` sends
        the ten newest proofs trimmed to RECORD_CHARS, and the IDEA proof is by
        construction the oldest row a goal has — so the founding statement is
        the first thing to fall out of the record block, on the goal it founded.
        """
        goal = self.make_goal()
        self.assertNotIn("WHAT THE IDEA IS", prompts.idea_block(goal.brief))
        self.assertEqual(prompts.idea_block(goal.brief), "")

        goal = self.prove(goal, self.IDEA_TEXT, self.ACCEPT)
        prompt = prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "nothing yet", "PLAIN"
        )
        self.assertIn("WHAT THE IDEA IS", prompt)
        self.assertIn("stand in it on Thursday", prompt)
