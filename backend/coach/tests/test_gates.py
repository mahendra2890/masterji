"""`gates.py` — PROOFS_REQUIRED, what counts as a person and as a kind, the beat
inside a phase, the two loopholes, and TRACTION's one number.
"""

from datetime import date, timedelta
from unittest import mock

from .. import (
    bar,
    gates,
    guidance,
    prompts,
    views,
)
from ..models import (
    CheckIn,
    Message,
    Phase,
)
from .base import CoachTestCase, make_user

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
        LLM in the loop. If it doesn't say what to do tonight, nothing does.

        The action is the one for the rung they are on (guidance.BEATS), which on
        a phase with beats is never the phase's constant — a builder with one
        person banked is refused for the second, so the second is what the
        refusal has to ask for."""
        goal = self.make_goal(phase="VALIDATION")
        self.accept_proofs(goal, 1)
        _, message = gates.try_advance(goal)
        self.assertIn("1/3 accepted proofs", message)
        self.assertIn(guidance.gate_nudge(Phase.VALIDATION, 1), message)

    def test_a_phase_without_beats_is_refused_in_its_own_constant_words(self):
        """BUILD and LAUNCH escalate through Need.kinds instead, so they have no
        BEATS entry and GATE_NUDGE stays the whole of their nudge. Pinned because
        the fallthrough is what makes beats an addition rather than a rewrite."""
        goal = self.make_goal(phase="BUILD")
        _, message = gates.try_advance(goal)
        self.assertIn(guidance.GATE_NUDGE[Phase.BUILD], message)

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


class IntraPhaseBeatTests(CoachTestCase):
    """The ask moves inside the phase; the gate does not move at all.

    VALIDATION's bar is a count and its coaching was a constant, so evenings one,
    two and three were byte-identical to the server: same PHASE_HINT, same
    PROOF_HINT, same GATE_NUDGE. A builder on their third conversation was
    coached exactly like one who had never spoken to anybody.

    Every test here divides into the two halves of that fix. Either the beat
    follows the banked count, or the gate is untouched by it — and the second
    half is the one worth the most, because a beat that moved the bar would be a
    second gate wearing coaching.
    """

    def bank(self, goal, n, subject="", start=0):
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=start + i),
                phase=goal.phase,
                am_declaration="talk to someone",
                pm_proof_text=f"notes {start + i}",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
                subject=subject,
            )

    def test_the_beat_follows_the_banked_count(self):
        """The issue, in one assertion: three counts, three different asks.

        Both strings that reach a builder move together, because they are two
        halves of one evening — the line under the goal title says what tonight
        is for, and the refusal says what to do about it.
        """
        hints = [guidance.phase_hint(Phase.VALIDATION, n) for n in (0, 1, 2)]
        nudges = [guidance.gate_nudge(Phase.VALIDATION, n) for n in (0, 1, 2)]
        self.assertEqual(len(set(hints)), 3)
        self.assertEqual(len(set(nudges)), 3)
        # And they are the beats the issue asked for, in order: get into a room,
        # then someone who is not the first person, then the commitment.
        self.assertIn("One conversation", hints[0])
        self.assertIn("Someone new", hints[1])
        self.assertIn("costs them", hints[2])
        # The second rung says the counting rule BEFORE a refusal can, which is
        # the half of this issue that is about the refusal that annoys most.
        self.assertIn("counts people rather than evenings", nudges[1])
        # The third reaches for bar.BAR[VALIDATION]'s commitment part, which had
        # been in the bar since it was written with nothing escalating to it.
        self.assertIn("commitment", guidance.beat(Phase.VALIDATION, 2).press)

    def test_the_beat_counts_people_not_evenings(self):
        """Keyed to gates.accepted_proofs, which on this phase is DISTINCT people.

        Two accepted nights about one hostelmate are one person. Keyed on rows
        that builder would be told to go and ask for the commitment while the gate
        is still waiting for a second person to exist.
        """
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 2, subject="priya")
        self.assertEqual(gates.accepted_proofs(goal), 1)
        _, message = gates.try_advance(goal)
        self.assertIn(guidance.gate_nudge(Phase.VALIDATION, 1), message)
        self.assertNotIn(guidance.gate_nudge(Phase.VALIDATION, 2), message)

    def test_the_gate_verdict_is_unchanged_across_the_beats(self):
        """The important one. A beat changes what is asked, never what is refused.

        Pinned as literals rather than against the module, because reading the
        expected sentence out of the code under test would pass just as happily
        if a beat had rewritten it. Every byte here is what this refusal said
        before beats existed.
        """
        expected = {
            0: "Not yet. 0/3 accepted proofs in VALIDATION — 3 more before "
            "BUILD unlocks.",
            1: "Not yet. 1/3 accepted proofs in VALIDATION — 2 more before "
            "BUILD unlocks.",
            2: "Not yet. 2/3 accepted proofs in VALIDATION — 1 more before "
            "BUILD unlocks.",
        }
        goal = self.make_goal(phase=Phase.VALIDATION)
        for have, refusal in expected.items():
            with self.subTest(have=have):
                self.assertEqual(
                    gates.gate_status(goal),
                    {
                        "have": have,
                        "need": 3,
                        "next_phase": Phase.BUILD,
                        "owed": [],
                        "banked": have,
                    },
                )
                advanced, message = gates.try_advance(goal)
                self.assertFalse(advanced)
                # The verdict sentence gates.py itself composes, byte for byte.
                # What follows it is the beat, and that is the only difference
                # between these three messages.
                self.assertTrue(message.startswith(refusal), message)
                self.assertEqual(
                    message,
                    f"{refusal} {guidance.gate_nudge(Phase.VALIDATION, have)}",
                )
                goal.refresh_from_db()
                self.assertEqual(goal.phase, "VALIDATION")
            self.bank(goal, 1, subject=f"person{have}", start=have)
        # And the count met still opens the door, from the same walk.
        self.assertTrue(gates.try_advance(goal)[0])

    def test_the_bar_does_not_move_with_the_beat(self):
        """The judge grades the same evening the same way at every count.

        PROOF_HINT is what prompts.judge_bar_for hands the one model call gates.py
        counts. A version of it that escalated with the count would refuse at 3/3
        what it accepted at 1/3, which is the goalposts moving inside one phase —
        so the beat is kept out of the bar, and out of the served proof hint the
        builder was working to all evening.
        """
        for banked in (0, 1, 2, 3):
            with self.subTest(banked=banked):
                bundle = guidance.for_phase(Phase.VALIDATION, banked)
                self.assertEqual(
                    bundle["proof_hint"], guidance.PROOF_HINT[Phase.VALIDATION]
                )
                self.assertEqual(
                    bundle["proof_examples"], guidance.PROOF_EXAMPLES[Phase.VALIDATION]
                )
        # And the coach carries the same bar at every rung it can be built at.
        goal = self.make_goal(phase=Phase.VALIDATION)
        for have in (0, 1, 2):
            system = prompts.build_system_prompt(
                goal, gates.gate_status(goal), 0, "state", "ENGLISH"
            )
            self.assertIn(prompts.bar_for(Phase.VALIDATION), system)
            self.bank(goal, 1, subject=f"person{have}", start=have)

    def test_the_coach_is_told_which_rung_tonight_is(self):
        """The conversation escalates too, or two thirds of the product doesn't.

        The block is absent for a phase with no beats, which is what makes this
        an addition: BUILD's prompt is byte-for-byte the one it had before.
        """
        goal = self.make_goal(phase=Phase.VALIDATION)
        presses = set()
        for have in (0, 1, 2):
            system = prompts.build_system_prompt(
                goal, gates.gate_status(goal), 0, "state", "ENGLISH"
            )
            press = guidance.beat(Phase.VALIDATION, have).press
            self.assertIn(press, system)
            presses.add(press)
            self.bank(goal, 1, subject=f"person{have}", start=have)
        self.assertEqual(len(presses), 3)
        # The count met, and the block is gone rather than stuck on the last
        # rung: "the third is where this phase produces something" is not a
        # sentence to hand a coach whose builder has had three.
        met = gates.gate_status(goal)
        self.assertEqual(prompts.beat_block(Phase.VALIDATION, met), "")

        build = self.make_goal(user=self.bob, phase=Phase.BUILD)
        self.assertEqual(prompts.beat_block(Phase.BUILD, gates.gate_status(build)), "")

    def test_one_beat_per_rung_and_the_constant_above_the_bar(self):
        """A tuple as long as the phase costs, checked against the gate itself.

        Two failures this catches, and neither is visible by reading either file
        alone: a phase whose Need.n grows past its beats would silently start
        serving the constant on its new last rung, and a fourth beat added to a
        three-proof phase would be dead copy nobody could ever reach. Above the
        count the constant comes back, because "Third conversation" is a false
        sentence said to a builder who has had three.
        """
        for phase, beats in guidance.BEATS.items():
            with self.subTest(phase=phase):
                self.assertEqual(len(beats), gates.PROOFS_REQUIRED[phase].n)
                self.assertIsNone(guidance.beat(phase, len(beats)))
                self.assertEqual(
                    guidance.phase_hint(phase, len(beats)), guidance.PHASE_HINT[phase]
                )
                self.assertEqual(
                    guidance.gate_nudge(phase, len(beats)), guidance.GATE_NUDGE[phase]
                )


class PhaseBriefTests(CoachTestCase):
    """An earned phase says what it is for, and a refused one still doesn't.

    Signing up writes guidance.WELCOME's 107 words. Unlocking a phase wrote five,
    and the phase being unlocked into is the one carrying a bar the builder has
    never met. These pin the two halves that could quietly come apart: that the
    brief rides the unlock, and that it never rides a refusal — where the
    coaching is being told exactly what is missing, and a briefing for a phase
    nobody has earned would talk straight over it.
    """

    def test_earned_phase_is_briefed(self):
        goal = self.make_goal()
        self.accept_proofs(goal, 1)  # IDEA needs 1
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        said = Message.objects.filter(goal=goal)
        # One row, not two: an advance is one thing the coach said.
        self.assertEqual(said.count(), 1)
        self.assertIn("Phase unlocked: IDEA → VALIDATION.", said.first().content)
        self.assertIn(guidance.UNLOCKED_BRIEF[Phase.VALIDATION], said.first().content)

    def test_refused_advance_is_not_briefed(self):
        """Equality rather than a not-in: the refusal is the sentence this
        product is built on, and the assertion should fail if anything at all
        gets appended to it, not only if a brief does."""
        goal = self.make_goal()
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.status_code, 409)
        said = Message.objects.get(goal=goal)
        self.assertEqual(said.content, response.data["detail"])

    def test_the_brief_stays_out_of_the_response(self):
        """The dashboard stamps `detail` into gateNote, which is keyed on the
        gate it describes and discarded the moment the phase changes. A brief
        sent through it would be written to a card already throwing it away —
        and would swap a one-line note for a paragraph on the refusal path's
        own control."""
        goal = self.make_goal()
        self.accept_proofs(goal, 1)
        response = self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        self.assertEqual(response.data["detail"], "Phase unlocked: IDEA → VALIDATION.")

    def test_every_phase_you_can_earn_has_a_brief(self):
        """Keyed by the phase moved INTO, so this is every phase but the first.
        IDEA is excluded rather than missing: nobody advances into it, and
        WELCOME briefs it at the only moment a goal is ever there."""
        self.assertEqual(set(guidance.UNLOCKED_BRIEF), set(gates.PHASE_ORDER[1:]))

    def test_the_terminal_phase_is_briefed_too(self):
        """TRACTION is the one the wiring is most likely to drop: it is the
        only phase with no PROOFS_REQUIRED entry, so it is reached through a
        gate that has nothing above it to look up."""
        goal = self.make_goal(phase="LAUNCH")
        self.accept_proofs(goal, 3)
        self.client.post(f"/api/coach/goals/{goal.pk}/advance/")
        said = Message.objects.filter(goal=goal).first().content
        self.assertIn(guidance.UNLOCKED_BRIEF[Phase.TRACTION], said)


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


class GateCountsPeopleAndKindsTests(CoachTestCase):
    """The gate counting what the phase is actually for.

    Both halves of this move a promise the product already makes in prose into a
    WHERE clause. The README's screenshot caption says "the person already
    counted cannot be counted again" — that was kept by the judge prompt alone,
    and a prompt keeping a gate is the one arrangement this product's whole
    thesis says does not work. BUILD's bar is any-of by design, so two link
    evenings could leave the phase with nobody having touched the thing, which
    is the exact hiding move gates.py's own comment says BUILD exists to catch.

    The rule running the other way is just as load-bearing and has its own tests
    below: a missing label never costs a builder work that was accepted on its
    merits. The label is the model's contribution; the evening is theirs.
    """

    def bank(self, goal, n, subject="", parts=None, start=0):
        """n accepted proofs in the goal's current phase, labelled."""
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=start + i),
                phase=goal.phase,
                am_declaration="talk to someone",
                pm_proof_text=f"notes {start + i}",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
                subject=subject,
                proof_parts=parts or [],
            )

    def test_three_conversations_with_one_person_count_once(self):
        """The heaviest gate in the product, met by one willing hostelmate three
        times. Real work, wrong evidence: VALIDATION exists to establish that
        more than one person has the problem."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 3, subject="priya")
        self.assertEqual(gates.accepted_proofs(goal), 1)
        advanced, message = gates.try_advance(goal)
        self.assertFalse(advanced)
        self.assertIn("1/3", message)

    def test_three_people_open_the_gate(self):
        goal = self.make_goal(phase=Phase.VALIDATION)
        for i, name in enumerate(("priya", "ramesh", "sunita")):
            self.bank(goal, 1, subject=name, start=i)
        self.assertEqual(gates.accepted_proofs(goal), 3)
        self.assertTrue(gates.try_advance(goal)[0])

    def test_the_same_name_written_two_ways_is_one_person(self):
        """Counting keys are normalised on write, so "Priya " and "priya" do not
        buy two proofs. Deliberately crude — see bar.normalise_subject."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.assertEqual(bar.normalise_subject("  Priya  S "), "priya s")
        self.bank(goal, 1, subject=bar.normalise_subject("Priya"))
        self.bank(goal, 1, subject=bar.normalise_subject("priya "), start=1)
        self.assertEqual(gates.accepted_proofs(goal), 1)

    def test_an_unlabelled_proof_counts_as_its_own_person(self):
        """The false-refusal rule, and the reason it is not optional: every proof
        banked before this field existed has a blank subject, and no builder may
        wake up to a gate that moved backwards under them."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 3)
        self.assertEqual(gates.accepted_proofs(goal), 3)
        self.assertTrue(gates.try_advance(goal)[0])

    def test_the_refusal_says_why_three_proofs_read_as_one(self):
        """The number on screen is people and the record is rows, and a refusal
        that names only the first reads as the gate having lost two nights of
        accepted work — the one reading that is not true."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 3, subject="priya")
        advanced, message = gates.try_advance(goal)
        self.assertFalse(advanced)
        self.assertIn("1/3", message)
        self.assertIn("3 accepted proofs", message)
        self.assertIn("1 person", message)
        self.assertIn("2 more", message)
        # The other two branches of this refusal both name the phase being
        # bought. Dropping it here would make the one refusal a builder gets
        # in chat, away from the meter, the only one that doesn't say what
        # the work is for.
        self.assertIn("BUILD", message)

    def test_the_coach_is_told_both_numbers_not_just_the_gate_count(self):
        """THE BUILDER'S STATE says "trust this over anything claimed in chat".
        A builder who filed three proofs about one person will say so, and a
        coach holding "1/3 accepted proofs" as database truth would tell them
        they are wrong about their own record."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 3, subject="priya")
        line = prompts.proof_progress(gates.gate_status(goal))
        self.assertIn("3 accepted proofs", line)
        self.assertIn("1 person", line)

    def test_the_coach_is_told_which_kind_is_still_owed(self):
        """The other half of the same sentence, and the half that was missed.

        Two link-only evenings in BUILD meet the count and do not meet the
        phase, so try_advance refuses that exact goal — while a state block
        reading "2/2 accepted proofs toward LAUNCH" tells the coach, under a
        heading that says to trust it over anything claimed in chat, that the
        gate is open. The coach then reassures a builder who is about to be
        turned away, which is worse than saying nothing.
        """
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 2, parts=["link"])
        line = prompts.proof_progress(gates.gate_status(goal))
        self.assertIn("2/2", line)
        self.assertIn("evidence a real user touched it", line)

    def test_no_phase_can_tell_the_coach_the_gate_is_met_while_refusing_it(self):
        """The invariant, read off PROOFS_REQUIRED rather than off a list of
        phases someone remembered to update.

        Both surfaces were already pinned, separately, and both passed while
        they contradicted each other: that is what a per-surface test cannot
        catch, and it is why this one asserts across them. A future phase that
        gains a kinds floor is covered without anybody thinking of it.
        """
        for phase, need in gates.PROOFS_REQUIRED.items():
            if not need.kinds:
                continue
            with self.subTest(phase=phase):
                goal = self.make_goal(user=make_user(f"owed-{phase}"), phase=phase)
                self.bank(goal, need.n, parts=[])
                owed = gates.kinds_owed(goal)
                self.assertTrue(owed)
                advanced, _ = gates.try_advance(goal)
                self.assertFalse(advanced)
                line = prompts.proof_progress(gates.gate_status(goal))
                for label in owed:
                    self.assertIn(label, line)

    def test_a_rows_phase_states_its_progress_exactly_as_it_always_did(self):
        """The line every other phase gets is unchanged, and that is the point:
        this only speaks where there is a difference to explain."""
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 1, parts=["link"])
        self.assertEqual(
            prompts.proof_progress(gates.gate_status(goal)),
            "1/2 accepted proofs toward LAUNCH",
        )

    def test_the_meter_carries_the_rows_beside_the_people(self):
        """What the dashboard needs to say the same thing without the builder
        having to press a button to hear it."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 3, subject="priya")
        status = gates.gate_status(goal)
        self.assertEqual((status["have"], status["banked"]), (1, 3))

    def test_a_phase_that_counts_rows_reads_them_the_same(self):
        """The dashboard shows the difference, so on a phase that never counts
        people there must not be one to show."""
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 2, parts=["link"])
        status = gates.gate_status(goal)
        self.assertEqual(status["banked"], status["have"])

    def test_unlabelled_proofs_leave_no_gap_to_explain(self):
        """Every row banked before the subject field existed is blank and each
        counts as its own person. The false-refusal rule has a screen half: those
        builders must not be told their nights stopped counting either."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.bank(goal, 2)
        status = gates.gate_status(goal)
        self.assertEqual(status["banked"], status["have"])

    def test_build_needs_one_proof_a_real_user_touched(self):
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 2, parts=["link"])
        self.assertEqual(gates.accepted_proofs(goal), 2)
        advanced, message = gates.try_advance(goal)
        self.assertFalse(advanced)
        # The count is met, so the refusal must not claim proofs are missing —
        # it has to name the kind, or it reads as the gate losing banked work.
        self.assertIn("2/2", message)
        self.assertIn(bar.label_for(Phase.BUILD, "touched"), message)
        self.assertIn(guidance.GATE_NUDGE[Phase.BUILD], message)

    def test_build_opens_once_a_user_has_touched_it(self):
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 1, parts=["link"])
        self.bank(goal, 1, parts=["touched"], start=1)
        self.assertEqual(gates.kinds_owed(goal), [])
        self.assertTrue(gates.try_advance(goal)[0])

    def test_the_meter_never_says_earned_while_a_kind_is_owed(self):
        """The dashboard promises "Earned. X is yours to open." off have >= need.
        Without `owed` in the payload it would promise it here, and the button
        under it would refuse — a lit door that doesn't open, on the product's
        own word."""
        goal = self.make_goal(phase=Phase.BUILD)
        self.bank(goal, 2, parts=["link"])
        status = gates.gate_status(goal)
        self.assertEqual(status["have"], status["need"])
        self.assertEqual(status["owed"], [bar.label_for(Phase.BUILD, "touched")])

    def test_a_phase_that_only_counts_rows_owes_no_kinds(self):
        """IDEA and VALIDATION must keep answering the empty list — the meter
        reads `owed` on every phase, and a stray label there would hold a gate
        shut that nothing asked for. TRACTION answers it as the phase with no
        exit to buy at all."""
        goal = self.make_goal()
        for phase in (Phase.IDEA, Phase.VALIDATION, Phase.TRACTION):
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.bank(goal, 3)
                self.assertEqual(gates.kinds_owed(goal), [])


class TractionTests(CoachTestCase):
    """The phase after the post, and the gate that now stands in front of it.

    LAUNCH was terminal, which ended the ladder at the moment the README's own
    opening statistic says the hard part begins. Giving it somewhere to go
    means LAUNCH finally has an exit to buy, and the exit is priced the way
    BUILD's is: a count, plus one kind of evidence the count cannot fake.
    """

    def bank(self, goal, n, parts=None, start=0):
        """n accepted proofs in the goal's current phase, labelled by kind.

        CoachTestCase.accept_proofs labels rows with whatever the phase
        requires, which is the right default everywhere else and the wrong one
        here: half of these tests are about a shelf full of the WRONG kind.
        """
        for i in range(n):
            CheckIn.objects.create(
                goal=goal,
                date=date.today() - timedelta(days=start + i),
                phase=goal.phase,
                am_declaration="put it in front of someone",
                pm_proof_text=f"notes {start + i}",
                proof_status=CheckIn.ProofStatus.ACCEPTED,
                proof_parts=parts or [],
            )

    def test_three_posts_do_not_buy_traction_on_their_own(self):
        """LAUNCH's own version of the failure BUILD's kinds floor catches: the
        ladder in launch-checklist.md is one rung a day, and three rungs climbed
        is three posts. Posting is not the same as somebody acting, and the
        phase after this one is about people who acted."""
        goal = self.make_goal(phase=Phase.LAUNCH)
        self.bank(goal, 3, parts=["link"])
        advanced, message = gates.try_advance(goal)
        self.assertFalse(advanced)
        # The count is met, so the refusal must name the kind rather than ask
        # for more of the same — the same rule BUILD's refusal already follows.
        self.assertIn("3/3", message)
        self.assertIn(bar.label_for(Phase.LAUNCH, "action"), message)
        self.assertIn(guidance.GATE_NUDGE[Phase.LAUNCH], message)

    def test_a_stranger_acting_opens_traction(self):
        goal = self.make_goal(phase=Phase.LAUNCH)
        self.bank(goal, 2, parts=["link"])
        self.bank(goal, 1, parts=["action"], start=2)
        self.assertEqual(gates.kinds_owed(goal), [])
        self.assertTrue(gates.try_advance(goal)[0])
        goal.refresh_from_db()
        self.assertEqual(goal.phase, Phase.TRACTION)

    def test_traction_is_the_end_of_the_ladder(self):
        """No PROOFS_REQUIRED entry, on purpose: an entry would give gate_status
        a next_phase to look up past the end of PHASE_ORDER. The altitude ends
        at first RETAINED users, and the ladder ends with it."""
        goal = self.make_goal(phase=Phase.TRACTION)
        self.bank(goal, 3, parts=["returned"])
        status = gates.gate_status(goal)
        self.assertIsNone(status["next_phase"])
        advanced, message = gates.try_advance(goal)
        self.assertFalse(advanced)
        self.assertIn("no next phase", message)
        # The line above was the whole of this test, and it stayed green while
        # the sentence read "You're at LAUNCH — there is no next phase": this
        # branch stopped being reachable from LAUNCH the moment TRACTION landed
        # behind it, so the only phase that could reach it was told it was
        # standing somewhere else. A refusal that names a phase has to name the
        # one the builder is in, and asserting a substring of a sentence is not
        # asserting the sentence.
        self.assertIn(Phase.TRACTION, message)
        self.assertNotIn("LAUNCH", message)

    def test_the_final_phase_says_what_is_banked_rather_than_zero(self):
        """`need is None` is a fact about the gate, and the terminal branch
        wrote it as a fact about the record: hardcoded zeros, so the state block
        read "0/0 accepted proofs toward — (final phase)" for a builder who had
        banked the hardest proof the product asks for — under a heading that
        tells the model to trust it over anything claimed in chat.

        `need` stays 0, and that is the half of the placeholder that was right:
        the dashboard hides the whole meter behind `gate.need > 0`, and the end
        of the ladder has no requirement to show a fraction of.
        """
        goal = self.make_goal(phase=Phase.TRACTION)
        self.bank(goal, 2, parts=["returned"])
        status = gates.gate_status(goal)
        self.assertEqual((status["have"], status["banked"]), (2, 2))
        self.assertEqual(status["need"], 0)
        line = prompts.proof_progress(status)
        self.assertIn("2 accepted proofs", line)
        self.assertNotIn("0/0", line)

    def test_the_win_button_cannot_be_lit_while_the_coach_hears_nothing_banked(self):
        """The cross-surface pin, and the one #115's guard cannot make: that test
        reads its phases off PROOFS_REQUIRED, and TRACTION is the phase with no
        entry, so the terminal case is exactly what its loop skips.

        `at_finish_line` counts the same rows `gate_status` does — its own
        docstring says so — so the dashboard could offer "Claim the win" while
        the state block said the record held nothing, and a builder saying "I
        banked it" was contradicted by a coach quoting the database.
        """
        goal = self.make_goal(phase=Phase.TRACTION)
        self.bank(goal, 1, parts=["returned"])
        self.assertTrue(gates.at_finish_line(goal))
        line = prompts.proof_progress(gates.gate_status(goal))
        self.assertIn("1 accepted proof", line)
        self.assertNotIn("0 accepted", line)

    def test_the_coach_is_told_the_whole_ladder(self):
        """The state block is introduced with "trust this over anything claimed
        in chat", and it used to spell the ladder out by hand — so the turn a
        fifth phase shipped, a builder who had reached it would have been told
        by the coach, on the product's own instruction, that their phase is not
        on the ladder. It reads PHASE_ORDER now."""
        goal = self.make_goal(phase=Phase.TRACTION)
        system = prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "nothing yet", "ENGLISH"
        )
        self.assertIn(" → ".join(str(p) for p in gates.PHASE_ORDER), system)
        self.assertIn("TRACTION", system)

    def test_traction_proofs_count_as_real_world_contact(self):
        """reads_as asks one question of CONTACT_PHASES — did real people get a
        vote — and a stranger who came back or paid is the loudest yes in the
        product. Leaving TRACTION out would read a goal that got further than
        any other as UNTESTED."""
        goal = self.make_goal(phase=Phase.TRACTION)
        self.bank(goal, gates.INVALIDATED_AT, parts=["returned"])
        self.assertEqual(gates.reads_as(goal), "INVALIDATED")


class TheOneNumberTests(CoachTestCase):
    """The one number a builder watches at TRACTION, and everything it is not.

    launch-checklist.md has commanded "One metric. Pick the single number that
    means 'someone got the value'... and watch only that" for as long as the
    corpus has existed, and it was a sentence the server had never seen. It is at
    TRACTION rather than at LAUNCH — where the playbook teaching it is wired —
    because LAUNCH has finish arithmetic and TRACTION is the phase with none, so
    TRACTION is the one whose last mile has no number in it at all.

    Every test here is either about the arithmetic being honest or about the
    product declining to count the result. The load-bearing one is
    test_a_series_of_numbers_moves_no_gate: the whole safety of putting a flat
    number at the terminal phase rests on nothing reading it, and the way that
    stops being true is a later change that finds this field useful.
    """

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.TRACTION)

    def name_metric(self, name="paid deposits", goal=None):
        return self.client.post(
            f"/api/coach/goals/{(goal or self.goal).id}/metric/", {"name": name}
        )

    def read(self, value, day=None, text="a stranger came back"):
        """One whole day: declare it, then file the evening with a number on it.

        Both halves, because the number rides the daily loop rather than having an
        endpoint of its own — and the evening is the end of the day a builder
        actually knows the number.
        """
        when = (day or date.today()).isoformat()
        self.client.post(
            "/api/coach/checkins/declare/", {"text": text, "date": when}
        )
        return self.client.post(
            "/api/coach/checkins/prove/",
            {"text": "notes from it", "date": when, "metric_value": value},
        )

    def readings(self, n: int, label="paid deposits"):
        """n days of readings, one per date, oldest last — written straight to the
        rows because the endpoints cannot backdate this far (see _parse_date)."""
        CheckIn.objects.bulk_create(
            CheckIn(
                goal=self.goal,
                date=date.today() - timedelta(days=i),
                phase=self.goal.phase,
                am_declaration=f"day {i}",
                metric_value=i,
                metric_label=label,
            )
            for i in range(n)
        )

    # --- the part that must never move ------------------------------------

    def test_a_series_of_numbers_moves_no_gate(self):
        """A goal with readings and no proofs reads exactly as it does with
        neither. This is the reason a flat number is safe at the phase with no
        finish arithmetic, and it is stated as an equality rather than as a spot
        check so that a later change which teaches gates.py about this field has
        to come through here to do it."""
        bare = gates.gate_status(self.make_goal(user=self.bob, phase=Phase.TRACTION))
        self.name_metric()
        for i, value in enumerate([3, 4, 12]):
            self.read(value, day=date.today() - timedelta(days=i))
        self.assertEqual(gates.gate_status(self.goal), bare)
        self.assertEqual(gates.accepted_proofs(self.goal), 0)
        self.assertEqual(gates.accepted_proofs_total(self.goal), 0)
        # A dozen deposits is not the finish line, and the win button is what
        # would say it was.
        self.assertFalse(gates.at_finish_line(self.goal))
        # And it buys no exit, because there is no exit and there must not be one.
        self.assertFalse(gates.try_advance(self.goal)[0])

    def test_traction_still_has_no_proofs_required_entry(self):
        """at_finish_line's comment explains why that absence has to stay: an
        entry would give gate_status a next_phase to look up past the end of
        PHASE_ORDER and 500 the dashboard for the builders who got furthest.
        Naming a metric is not a reason to give it one."""
        self.name_metric()
        self.read(5)
        self.assertNotIn(Phase.TRACTION, gates.PROOFS_REQUIRED)

    def test_a_number_that_falls_costs_nothing(self):
        """The case this exists for. A metric going backwards is the honest thing
        it is there to show, so it must cost no proof, no streak and no phase."""
        self.name_metric()
        self.read(9, day=date.today() - timedelta(days=1))
        self.read(2)
        self.accept_proofs(self.goal, 1)
        self.assertTrue(gates.at_finish_line(self.goal))
        self.assertEqual(gates.reads_as(self.goal, "COMPLETED"), "ACHIEVED")

    # --- where it can be named --------------------------------------------

    def test_the_last_rung_is_the_only_one(self):
        for phase in (Phase.IDEA, Phase.VALIDATION, Phase.BUILD, Phase.LAUNCH):
            goal = self.make_goal(user=self.bob, phase=phase)
            self.client.force_authenticate(self.bob)
            response = self.name_metric(goal=goal)
            self.assertEqual(response.status_code, 409, phase)
            goal.refresh_from_db()
            self.assertEqual(goal.metric_name, "")
            goal.delete()

    def test_a_builder_already_standing_in_traction_can_name_one(self):
        """The one mechanism from the issue body that does not survive the move
        from LAUNCH unchanged. TRACTION is terminal, so "entering the phase" is
        the last transition the ladder has and a builder who arrived before this
        shipped will never make another one — an invitation that fired on the
        advance would be invisible to exactly the builders who got furthest. So
        the offer is keyed to the PHASE, which a dashboard load can answer on any
        morning, including the first one after a deploy."""
        # No PhaseTransition row at all: this goal has never advanced anywhere.
        self.assertFalse(self.goal.transitions.exists())
        self.assertTrue(self.client.get("/api/coach/state/").json()["can_set_metric"])
        self.assertEqual(self.name_metric().status_code, 200)

    def test_naming_is_offered_nowhere_else(self):
        goal = self.make_goal(user=self.bob, phase=Phase.LAUNCH)
        self.client.force_authenticate(self.bob)
        body = self.client.get("/api/coach/state/").json()
        self.assertFalse(body["can_set_metric"])
        # And no placeholder metric to go with it: there is no default number,
        # because a number the app picked is not one anybody decided to watch.
        self.assertIsNone(body["metric"])
        self.assertEqual(goal.metric_name, "")

    def test_a_sentence_and_an_empty_answer_are_both_refused(self):
        self.assertEqual(self.name_metric("   ").status_code, 400)
        self.assertEqual(self.name_metric("x" * 61).status_code, 400)
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.metric_name, "")

    def test_the_metric_is_the_builders_own(self):
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.name_metric().status_code, 404)

    # --- the recorded slip -------------------------------------------------

    def test_a_rename_does_not_relabel_what_was_already_counted(self):
        """The recorded slip, and the reason the name is stamped on the reading
        instead of read off the goal. Three evenings that counted deposits must
        not become three evenings of signups because the builder changed their
        mind on Friday — that is the record disagreeing with itself in the one
        direction nothing would detect."""
        self.name_metric("paid deposits")
        self.read(3, day=date.today() - timedelta(days=1))
        self.name_metric("signups")
        self.read(40)

        series = _state_metric(self.client)["series"]
        self.assertEqual(
            [(r["value"], r["label"]) for r in series],
            [(3, "paid deposits"), (40, "signups")],
        )
        # Stated on the record, and counted where it cost something: between two
        # readings, never as "how many names the field has held".
        self.assertEqual(_state_metric(self.client)["swaps"], 1)

    def test_a_rename_before_anything_is_counted_leaves_no_mark(self):
        """The other half of the same rule. Renaming with nothing on the record is
        a builder fixing their own wording, not a scoreboard being swapped, and
        recording a slip for it would put something on the record that never
        happened — the same call LaunchDateView makes about a re-declared date."""
        self.name_metric("deposits")
        self.name_metric("paid deposits")
        self.read(3)
        metric = _state_metric(self.client)
        self.assertEqual(metric["swaps"], 0)
        self.assertEqual([r["label"] for r in metric["series"]], ["paid deposits"])

    def test_the_series_runs_oldest_first_and_says_what_it_dropped(self):
        self.name_metric()
        # Written through the ORM rather than the loop: `_parse_date` bounds a
        # check-in to within a day of the server's date — an unbounded loop date
        # lets a builder mint a week of backdated proofs — so a month of readings
        # is not something the endpoints can be asked for.
        self.readings(views.METRIC_SERIES + 3)
        metric = _state_metric(self.client)
        self.assertEqual(len(metric["series"]), views.METRIC_SERIES)
        self.assertEqual(metric["held"], views.METRIC_SERIES + 3)
        # Newest kept, oldest dropped — and reading left to right is reading
        # forward in time, which is the only order a series means anything in.
        dates = [r["date"] for r in metric["series"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[-1], date.today().isoformat())

    # --- what the loop will and won't record -------------------------------

    def test_zero_is_a_reading_and_not_a_missing_one(self):
        """The evening the number did not move is the one the coach most needs.
        A default of 0 would make every untouched row in the product claim it,
        which is why the column is nullable rather than defaulted."""
        self.name_metric()
        self.read(0)
        self.assertEqual([r["value"] for r in _state_metric(self.client)["series"]], [0])

    def test_a_number_never_costs_the_builder_their_day(self):
        """Ignored rather than refused, in every case it cannot be recorded: a
        stale client sending one at LAUNCH, a metric nobody has named yet, a
        typo, a negative. The daily loop is the last thing in this product that
        may be held hostage by a corroborating detail — the same call _client_day
        makes about a garbled date and the image path makes about a dead bucket.
        The response carries the row either way, so nothing is reported as saved
        that was not.
        """
        self.name_metric()
        for value in ("five", -3, ""):
            day = date.today()
            CheckIn.objects.filter(goal=self.goal, date=day).delete()
            body = self.read(value, day=day).json()["checkin"]
            self.assertEqual(body["pm_proof_text"], "notes from it", value)
            self.assertIsNone(body["metric_value"], value)
            self.assertEqual(body["metric_label"], "", value)

    def test_a_number_with_no_metric_named_is_dropped_and_the_proof_lands(self):
        body = self.read(7).json()["checkin"]
        self.assertEqual(body["pm_proof_text"], "notes from it")
        self.assertIsNone(body["metric_value"])
        self.assertIsNone(_state_metric(self.client))

    def test_the_morning_can_carry_it_too(self):
        """DeclareView takes the value as well, which is what makes a reading
        possible on a day whose proof is about something else — without a second
        endpoint that would be a fifth thing to have filed."""
        self.name_metric()
        body = self.client.post(
            "/api/coach/checkins/declare/",
            {"text": "ask the one who came back", "date": date.today().isoformat(),
             "metric_value": 6},
        ).json()
        self.assertEqual(body["metric_value"], 6)
        self.assertEqual(body["metric_label"], "paid deposits")

    def test_rewording_the_task_does_not_erase_the_day_s_number(self):
        """Declaring clears the judgement fields, because a verdict on wording
        the builder has since changed is worse than no verdict. A count of
        returns is not a verdict about the task, and a re-worded task does not
        un-happen it."""
        self.name_metric()
        when = date.today().isoformat()
        self.client.post(
            "/api/coach/checkins/declare/",
            {"text": "first go", "date": when, "metric_value": 4},
        )
        body = self.client.post(
            "/api/coach/checkins/declare/", {"text": "sharper wording", "date": when}
        ).json()
        self.assertEqual(body["am_declaration"], "sharper wording")
        self.assertEqual(body["metric_value"], 4)

    # --- what the coach is handed ------------------------------------------

    def test_the_coach_gets_the_last_two_and_is_told_not_to_wield_them(self):
        text = prompts.metric_line(
            {
                "name": "paid deposits",
                "series": [
                    {"date": "2026-08-11", "value": 1, "label": "paid deposits"},
                    {"date": "2026-08-12", "value": 3, "label": "paid deposits"},
                    {"date": "2026-08-14", "value": 5, "label": "paid deposits"},
                ],
                "held": 3,
                "swaps": 0,
            }
        )
        self.assertIn("paid deposits", text)
        self.assertIn("3 on 2026-08-12 → 5 on 2026-08-14", text)
        self.assertIn("up 2", text)
        # The last TWO, not the series: a prompt block that grows by a line an
        # evening is a transcript pretending to be a fact.
        self.assertNotIn("2026-08-11", text)
        self.assertIn("no gate reads it", text)
        # And absent entirely when they never named one — no default metric, and
        # no line in the state block about a thing that does not exist.
        self.assertEqual(prompts.metric_line(None), "")

    def test_the_coach_is_not_handed_a_subtraction_across_a_rename(self):
        """Two readings under two names are two different measurements. Saying
        "40, up 37" would be the state block — introduced with "trust this over
        anything claimed in chat" — inventing growth out of a swap."""
        text = prompts.metric_line(
            {
                "name": "signups",
                "series": [
                    {"date": "2026-08-12", "value": 3, "label": "paid deposits"},
                    {"date": "2026-08-14", "value": 40, "label": "signups"},
                ],
                "held": 2,
                "swaps": 1,
            }
        )
        self.assertIn("do not subtract", text)
        self.assertNotIn("up 37", text)
        self.assertIn("changed what they watch 1 time", text)

    def test_the_state_block_carries_it_and_the_bar_still_does_not(self):
        self.name_metric()
        self.read(3, day=date.today() - timedelta(days=1))
        self.read(5)
        # The name was written by the endpoint, so the instance this test has been
        # holding since setUp does not know about it.
        self.goal.refresh_from_db()
        system = prompts.build_system_prompt(
            self.goal,
            gates.gate_status(self.goal),
            0,
            "nothing yet",
            "ENGLISH",
            metric=views._metric_payload(self.goal),
        )
        self.assertIn('Watching: "paid deposits"', system)
        self.assertIn("→ 5", system)
        # The number sits in the state list and the bar is untouched underneath
        # it: what clears TRACTION is still a person who came back or a payment,
        # and a number the builder typed is not evidence of either.
        self.assertIn(guidance.PROOF_HINT[Phase.TRACTION], system)

    def test_a_named_metric_with_no_reading_says_so(self):
        """A fact about the builder, not about the app's own form: they chose a
        number and have not read it yet, which is a real state on the first
        morning and must not be reported as a reading of nothing."""
        self.name_metric()
        text = prompts.metric_line(_state_metric(self.client))
        self.assertIn("no reading on the record yet", text)
        self.assertIn("Nothing counts it", text)

    def test_the_playbook_line_is_still_at_launch_and_traction_teaches_returns(self):
        """The call this feature had to make: the sentence the metric comes from
        is wired to LAUNCH while the mechanism lands one rung up. It STAYS at
        LAUNCH — "watch one number" is a launch-week discipline sitting in a list
        with "reply to everyone within the hour" — and moving it into
        coming-back.md would put it inside a document whose thesis is that the
        only number here is a person's name. The coach carries it forward; the
        corpus keeps one copy of each rule."""
        launch = prompts.playbooks_for(Phase.LAUNCH)
        traction = prompts.playbooks_for(Phase.TRACTION)
        self.assertIn("One metric.", launch)
        self.assertNotIn("One metric.", traction)
        # And what TRACTION's own corpus says instead, which is why the server
        # records whatever number they chose and refuses none of them: the
        # judgement about whether it is the RIGHT one lives here, once.
        self.assertIn("Every other number lies to you at this size", traction)


def _state_metric(client) -> dict | None:
    return client.get("/api/coach/state/").json()["metric"]
