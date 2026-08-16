"""The `suggest_*` seam — Masterji hearing something in conversation and writing
it into the box the builder would otherwise type into twice.
"""

import json
from datetime import date, timedelta
from unittest import mock

from .. import (
    gates,
    guidance,
    judging,
    prompts,
    streaks,
    views,
)
from ..models import (
    METRIC_PHASE,
    CheckIn,
    Goal,
    LaunchCommitment,
    Message,
    Phase,
    PhaseTransition,
)
from .base import CoachTestCase, User, _state_launch


class ProofOfferTests(CoachTestCase):
    """Masterji reading the conversation, spotting that the work is already
    described in it, and writing tonight's proof up himself.

    The complaint underneath: a builder tells him the thing, he coaches at them
    about it, and the evening ends with nothing filed — because turning what
    they said into what the box wants was left to them. The draft is an OFFER;
    nothing is recorded until the builder files it, so the gate still counts
    only what they put their name to.
    """

    DRAFT = (
        "Spoke to Ramesh (mess contractor). 40-50 plates wasted most nights. "
        "Tried a WhatsApp group for counts; it died in a week."
    )
    # Work described AFTER the day's cycle was already filed and accepted.
    SECOND = (
        "Also called Sunita at the girls' hostel mess. Same 9pm crush, and she "
        "counts plates by hand every night."
    )
    # The same evening, as the parts the tool now takes. A prose draft alone no
    # longer clears anything: what is missing is counted off these (bar.read),
    # so a complete offer is one where every part of the phase's bar is filled.
    PARTS = {
        "who": "Ramesh, the mess contractor",
        "quotes": [
            "40-50 plates go to waste most nights",
            "nobody replied by 18:00",
            "I'm not sharing my numbers",
        ],
        "last_action": "Tried a WhatsApp group for counts; it died in a week",
        "commitment": "Asked for an intro to the Block B contractor — he gave it",
    }

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.VALIDATION)
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})

    def chat(self, text=DRAFT, events=None):
        events = events or [
            ("delta", "That's tonight's proof. Yes?"),
            (
                "tool_call",
                {"name": "suggest_proof", "arguments": {"text": text, **self.PARTS}},
            ),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)):
            response = self.client.post("/api/coach/chat/", {"content": "talked to him"})
            b"".join(response.streaming_content)

    def prove(self, reply, text):
        with mock.patch("coach.views.llm.complete", return_value=reply) as called:
            response = self.client.post("/api/coach/checkins/prove/", {"text": text})
        return response, called

    def test_the_draft_lands_on_the_day_it_was_written_for(self):
        self.chat()
        self.assertEqual(CheckIn.objects.get().proof_offer, self.DRAFT)

    def test_the_draft_records_nothing_by_itself(self):
        """An offer the builder never accepted must not become a proof — the
        whole design rests on the filing being theirs."""
        self.chat()
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.pm_proof_text, "")
        self.assertEqual(checkin.proof_status, CheckIn.ProofStatus.NONE)
        self.assertEqual(gates.accepted_proofs(self.goal), 0)

    def test_filing_his_own_draft_needs_no_second_opinion(self):
        """He judged the substance when he offered it. Asking again could only
        produce a disagreement with himself, paid for by the builder."""
        self.chat()
        response, called = self.prove('{"verdict": "push_back", "reaction": "no"}', self.DRAFT)
        self.assertEqual(response.data["checkin"]["proof_status"], "ACCEPTED")
        self.assertEqual(
            response.data["checkin"]["coach_reaction"],
            prompts.STOCK_OFFER_ACCEPT["ENGLISH"],
        )
        called.assert_not_called()

    def test_his_own_draft_is_acknowledged_in_the_builders_language(self):
        """This line is on the happy path, unlike the other stock reactions —
        a Hinglish builder would otherwise be answered in English every time
        they took his draft."""
        self.alice.tone = "HINGLISH"
        self.alice.save(update_fields=["tone"])
        self.chat()
        response, _ = self.prove('{"verdict": "accept", "reaction": "x"}', self.DRAFT)
        self.assertEqual(
            response.data["checkin"]["coach_reaction"],
            prompts.STOCK_OFFER_ACCEPT["HINGLISH"],
        )

    def test_every_tone_has_a_line_for_it(self):
        for tone in User.Tone:
            with self.subTest(tone=tone):
                self.assertIn(tone.value, prompts.STOCK_OFFER_ACCEPT)

    def test_an_edited_draft_is_judged_knowing_he_wrote_it(self):
        self.chat()
        _, called = self.prove(
            '{"verdict": "accept", "reaction": "Counted."}',
            self.DRAFT + " He wouldn't share numbers.",
        )
        system = called.call_args.args[0]
        self.assertIn("YOU WROTE THIS PROOF FOR THEM TONIGHT", system)
        self.assertIn(self.DRAFT, system)

    def test_a_draft_for_a_task_they_have_since_changed_is_dropped(self):
        """Re-declaring rewrites the day's task; evidence written for the old
        one would be a proof of work nobody is doing."""
        self.chat()
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Priya"})
        self.assertEqual(CheckIn.objects.get().proof_offer, "")

    def test_nothing_is_drafted_when_no_task_is_on_the_hook(self):
        """ProveView would refuse the filing anyway, so a draft here is a
        button the builder can't press."""
        CheckIn.objects.all().delete()
        self.chat()
        self.assertFalse(CheckIn.objects.exists())

    def test_a_draft_with_nothing_to_pin_it_to_goes_back_to_the_builder(self):
        """The draft is theirs — it came out of work they described. Dropping
        it to a server log left them watching the reply go by with no sign
        that anything had been written up, or thrown away. They get it back,
        with the one thing that has to happen before it can be filed."""
        CheckIn.objects.all().delete()
        self.chat()
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertIn(self.DRAFT, said)
        self.assertIn(guidance.WHERE_TO_FILE, said)
        self.assertIn(guidance.OFFER_NO_DECLARATION.format(offer=self.DRAFT), said)

    def test_a_finished_day_is_not_told_nothing_was_declared(self):
        """The bug this pair of strings exists to fix, seen in real use: the
        builder filed, got accepted, kept talking, described more work — and
        was told "there's no task declared this morning" while the card beside
        the chat read "Declared: talk to Ramesh" with a green "✓ accepted"
        under it.

        _offer_target answers None here for the opposite reason: not an empty
        day, a finished one. The draft still comes back, because the work
        behind it still happened."""
        self.prove('{"verdict": "accept", "reaction": "Counted."}', "Talked to him.")
        self.chat(text=self.SECOND)
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertIn(self.SECOND, said)
        self.assertIn(guidance.OFFER_DAY_CLOSED.format(offer=self.SECOND), said)
        self.assertNotIn(guidance.OFFER_NO_DECLARATION.format(offer=self.SECOND), said)
        # And the closed cycle is left exactly as the builder earned it: the
        # draft is a sentence in the transcript, not a scribble on a row whose
        # proof is already on the record.
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_offer, "")
        self.assertEqual(checkin.proof_status, CheckIn.ProofStatus.ACCEPTED)

    def test_declaring_the_second_task_gives_the_draft_somewhere_to_go(self):
        """The way out that copy points at, walked. More than one cycle a day
        is supported on purpose (CheckIn's docstring), so "declare another
        task and file this against it" has to be a real instruction and not a
        polite way of dropping the draft."""
        self.prove('{"verdict": "accept", "reaction": "Counted."}', "Talked to him.")
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Sunita"})
        self.chat(text=self.SECOND)
        second = CheckIn.objects.latest("id")
        self.assertEqual(second.am_declaration, "talk to Sunita")
        self.assertEqual(second.proof_offer, self.SECOND)
        self.assertEqual(CheckIn.objects.count(), 2)

    def test_a_draft_that_landed_is_not_also_read_back_in_the_chat(self):
        """It is on the check-in where it can be filed in one tap. Repeating
        it in the transcript would be two copies of the same offer, and only
        one of them does anything."""
        self.chat()
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertEqual(said, "That's tonight's proof. Yes?")

    def test_a_draft_with_no_text_is_not_an_offer(self):
        """Tool arguments arrive as streamed JSON fragments and can land
        malformed; llm._tool_arguments answers {} rather than taking the turn
        down with it, and an empty draft must go nowhere."""
        self.chat(events=[("tool_call", {"name": "suggest_proof", "arguments": {}})])
        self.assertEqual(CheckIn.objects.get().proof_offer, "")

    def test_a_turn_spent_entirely_on_the_draft_still_answers(self):
        """The tool call WAS the turn: he wrote the proof and said nothing
        around it. That saved no reply, so the chat — the one screen the
        builder was watching — showed their message with nothing under it,
        while the work landed on a card they had no reason to open. He says
        where it went, on the wire as well as in the record, because the
        refetch is a second late and they are looking now."""
        events = [
            (
                "tool_call",
                {
                    "name": "suggest_proof",
                    "arguments": {"text": self.DRAFT, **self.PARTS},
                },
            )
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)):
            response = self.client.post("/api/coach/chat/", {"content": "talked to him"})
            body = b"".join(response.streaming_content).decode()
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        # Equality, not a substring: the receipt points at the draft and must
        # never restate it, or the builder gets two copies of one offer and
        # only the one on the check-in files anything when tapped.
        self.assertEqual(said, guidance.OFFER_LANDED)
        events = [json.loads(raw) for raw in body.splitlines() if raw.strip()]
        self.assertEqual(
            [e["text"] for e in events if e["t"] == "delta"], [guidance.OFFER_LANDED]
        )
        self.assertEqual(CheckIn.objects.get().proof_offer, self.DRAFT)

    def test_a_draft_he_spoke_around_gets_no_receipt(self):
        """He already said it in his own words. Appending the stock line would
        answer the builder twice for one turn."""
        self.chat()
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertEqual(said, "That's tonight's proof. Yes?")

    def test_the_draft_rides_the_state_payload(self):
        self.chat()
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.data["today"]["proof_offer"], self.DRAFT)

    def test_the_coach_is_told_to_look_for_it(self):
        system = prompts.build_system_prompt(
            self.goal, gates.gate_status(self.goal), 0, "state", "ENGLISH"
        )
        self.assertIn(prompts.SPOT_PROOF, system)


class DeclarationOfferTests(CoachTestCase):
    """Masterji hearing today's task in conversation and writing it down.

    The morning's mirror of ProofOfferTests, and the same bargain: he drafts,
    the builder presses. The complaint underneath is one the server already
    detected and could do nothing about — OFFER_NO_DECLARATION writes a
    finished proof and hands it back with instructions to go and declare the
    missing half by hand, because the tool to write that half did not exist.
    """

    TASK = "Ask three hostel mess regulars what they ate last night."

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.VALIDATION)

    def chat(self, events=None, task=TASK):
        events = events or [
            ("delta", "Right — that's today."),
            ("tool_call", {"name": "suggest_declaration", "arguments": {"task": task}}),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)) as m:
            response = self.client.post("/api/coach/chat/", {"content": "mess queue tonight"})
            b"".join(response.streaming_content)
        return m

    def tools(self, called):
        return [t["function"]["name"] for t in called.call_args.kwargs["tools"]]

    def test_the_draft_lands_on_the_goal_stamped_with_the_builders_day(self):
        """There is no check-in to hang it on — that absence is the whole
        situation this tool exists for."""
        self.chat()
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.declaration_offer, self.TASK)
        self.assertEqual(self.goal.declaration_offer_date, date.today())

    def test_the_draft_declares_nothing(self):
        """The one rule the morning cannot bend: a promise a model inferred
        from rambling is not a promise made. No row, no streak, no gate."""
        self.chat()
        self.assertEqual(CheckIn.objects.count(), 0)
        self.assertEqual(streaks.current_streak(self.goal, date.today()), 0)

    def test_a_turn_that_only_wrote_it_down_still_says_something(self):
        """#270's failure, one screen over: the thing that happened landed on
        the card beside the conversation, and the conversation showed the
        builder's own message with nothing under it."""
        self.chat(events=[("tool_call", {"name": "suggest_declaration", "arguments": {"task": self.TASK}})])
        row = Message.objects.filter(role=Message.Role.COACH).get()
        self.assertEqual(row.content, guidance.DECLARATION_LANDED)

    def test_the_receipt_says_nothing_is_declared_yet(self):
        """The difference between this receipt and OFFER_LANDED. A builder who
        reads it as 'declared' spends the day owing a proof against a task the
        server was never told about."""
        self.assertIn("Nothing is declared until you press it", guidance.DECLARATION_LANDED)

    def test_declaring_spends_the_draft(self):
        self.chat()
        self.client.post("/api/coach/checkins/declare/", {"text": "my own words"})
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.declaration_offer, "")
        self.assertIsNone(self.goal.declaration_offer_date)

    def test_yesterdays_draft_is_not_todays_task(self):
        """An offer is about ONE morning. Read back tomorrow it would sit above
        a fresh day's empty box holding work nobody is doing."""
        self.chat()
        Goal.objects.filter(pk=self.goal.pk).update(
            declaration_offer_date=date.today() - timedelta(days=1)
        )
        state = self.client.get(f"/api/coach/state/?date={date.today()}")
        self.assertEqual(state.data["declaration_offer"], "")

    def test_the_dashboard_is_handed_the_draft(self):
        self.chat()
        state = self.client.get(f"/api/coach/state/?date={date.today()}")
        self.assertEqual(state.data["declaration_offer"], self.TASK)

    def test_the_tool_is_gone_once_a_task_is_on_the_hook(self):
        """Not forbidden in prose — absent. The failure worth preventing is a
        draft overwriting a commitment the builder has already made, and a tool
        in the list is a thing the model will find a reason to call."""
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        self.assertNotIn("suggest_declaration", self.tools(self.chat()))

    def test_the_tool_is_gone_on_a_day_already_proved_and_closed(self):
        """The second cycle is 'Declare another task', a button the builder
        presses. A draft must not become a third route into one."""
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        CheckIn.objects.update(
            pm_proof_text="spoke to him", proof_status=CheckIn.ProofStatus.ACCEPTED
        )
        self.assertNotIn("suggest_declaration", self.tools(self.chat()))

    def test_the_tool_is_there_on_a_morning_with_nothing_declared(self):
        self.assertIn("suggest_declaration", self.tools(self.chat()))

    def test_a_call_that_arrives_anyway_writes_nothing(self):
        """The branch that writes to the goal guards itself. The tool being
        absent is forty lines away from the code that trusts it."""
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        self.chat()
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.declaration_offer, "")


class SharpenedDeclarationTests(CoachTestCase):
    """The critique's missing half: Masterji says the task is too vague, and
    now there is something under it to press.

    Not a veto arriving by another door. Declaring is still never refused, the
    suggestion is still an offer, and accepting it goes back through DeclareView
    — so the model never grades wording it handed itself.
    """

    VAGUE = "Figure out an idea"
    JUDGEMENT = (
        '{"fit": "off_phase", "reaction": "That is too vague to count as IDEA '
        'work.", "sharpened": "Write one paragraph naming who has the problem '
        'and where they already are.", "proof_ask": "Send me the paragraph."}'
    )

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.IDEA)

    def declare(self, text=VAGUE):
        return self.client.post("/api/coach/checkins/declare/", {"text": text})

    def judge(self, pk, reply=JUDGEMENT):
        with mock.patch("coach.views.llm.complete", return_value=reply):
            return self.client.post(f"/api/coach/checkins/{pk}/judge/")

    def test_the_critique_arrives_with_a_way_out_of_it(self):
        response = self.judge(self.declare().data["id"])
        self.assertEqual(
            response.data["sharpened"],
            "Write one paragraph naming who has the problem and where they "
            "already are.",
        )

    def test_a_task_that_needed_nothing_is_offered_nothing(self):
        """'An empty reaction is the compliment' extends to this unchanged. A
        sharpening under no complaint is a fix for a problem the builder was
        never told they had."""
        response = self.judge(
            self.declare().data["id"],
            reply='{"fit": "on_phase", "reaction": "", "sharpened": "Talk to '
            'four people instead of three.", "proof_ask": "Names."}',
        )
        self.assertEqual(response.data["sharpened"], "")

    def test_taking_it_rewrites_the_same_day_rather_than_opening_another(self):
        """It is an EDIT of the cycle on the hook. A second cycle is a day with
        two pieces of real work in it, not a change of mind about the first."""
        checkin = self.declare().data["id"]
        self.judge(checkin)
        again = self.declare(text="Write one paragraph naming who has the problem.")
        self.assertEqual(again.data["id"], checkin)
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_the_offer_is_cleared_by_the_declaration_that_accepts_it(self):
        """Otherwise it comes back on the card underneath the sentence it just
        became, offering the builder their own words as an improvement."""
        checkin = self.declare().data["id"]
        self.judge(checkin)
        again = self.declare(text="Write one paragraph naming who has the problem.")
        self.assertEqual(again.data["sharpened"], "")
        self.assertEqual(again.data["declaration_fit"], "UNJUDGED")

    def test_the_suggestion_is_read_back_rather_than_trusted(self):
        """The model would otherwise be writing the task it later grades.
        Re-declaring clears the judgement, so the wording it suggested arrives
        at the judge as a declaration like any other."""
        checkin = self.declare().data["id"]
        self.judge(checkin)
        self.declare(text="Write one paragraph naming who has the problem.")
        row = CheckIn.objects.get(pk=checkin)
        self.assertEqual(row.proof_ask, "")
        self.assertEqual(row.declaration_reaction, "")

    def test_the_floor_is_no_suggestion_rather_than_a_bad_one(self):
        """The suite stubs every model call to raise. An unreachable judge
        leaves the morning exactly as the builder wrote it."""
        response = self.client.post(
            f"/api/coach/checkins/{self.declare().data['id']}/judge/"
        )
        self.assertEqual(response.data["declaration_fit"], "UNJUDGED")
        self.assertEqual(response.data["sharpened"], "")

    def test_the_prompt_asks_for_their_sentence_not_a_better_task(self):
        """The guard that keeps this from being a veto. A sharpening that
        swaps the task is the model deciding what today is for."""
        text = prompts.DECLARATION_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            tone_rule="",
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
            phase=Phase.IDEA,
            phase_rules=prompts.PHASE_RULES[Phase.IDEA],
            proof_hint=guidance.PROOF_HINT[Phase.IDEA],
            intent="",
        )
        rule = text.split("- sharpened is the fix")[1]
        self.assertIn("Never swap their task for a better one", rule)
        self.assertIn("if the reaction is empty, this is empty too", rule)


class MetricOfferTests(CoachTestCase):
    """Masterji hearing today's number said out loud and writing it down.

    The last of the evening's boxes to be typed twice. A builder at TRACTION
    tells him "two people paid today", and then goes and types 2 into the number
    box under Today — a figure the conversation already contains.

    Everything here turns on one distinction: metric_offer is what he heard,
    metric_value is what they filed, and only the second is a reading. The
    load-bearing tests are test_the_draft_records_nothing, which is the rule the
    field exists to keep, and test_a_wrong_drafted_number_cannot_cost_the_proof,
    which is what makes a drafted number safe to prefill at all.
    """

    DRAFT = "Priya came back on her own on Thursday and paid ₹200 for the month."
    PARTS = {
        "returned": "Priya, back on Thursday without being asked",
        "paid": "Priya, ₹200, for the month",
    }

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.TRACTION)
        self.client.post(
            f"/api/coach/goals/{self.goal.id}/metric/", {"name": "paying users"}
        )
        self.client.post("/api/coach/checkins/declare/", {"text": "chase Priya"})

    def chat(self, arguments=None, events=None):
        """One turn in which he drafts tonight's proof, with or without a number."""
        events = events or [
            ("delta", "Then that's tonight's proof."),
            (
                "tool_call",
                {
                    "name": "suggest_proof",
                    "arguments": {
                        "text": self.DRAFT,
                        **self.PARTS,
                        **(arguments or {}),
                    },
                },
            ),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)) as m:
            response = self.client.post("/api/coach/chat/", {"content": "priya paid"})
            b"".join(response.streaming_content)
        return m

    def schema(self, called):
        """The suggest_proof schema this turn was actually offered."""
        tools = called.call_args.kwargs["tools"]
        tool = next(t for t in tools if t["function"]["name"] == "suggest_proof")
        return tool["function"]["parameters"]["properties"]

    def file_it(self, **extra):
        with mock.patch(
            "coach.judging.llm.complete",
            return_value='{"verdict": "accept", "reaction": "good"}',
        ):
            return self.client.post(
                "/api/coach/checkins/prove/", {"text": "priya paid", **extra}
            )

    # --- the window the argument exists in --------------------------------

    def test_the_argument_is_in_the_schema_at_traction(self):
        self.assertIn("metric_value", self.schema(self.chat()))

    def test_it_is_not_in_the_schema_at_any_other_phase(self):
        """Wrong-phase silence as a schema fact rather than a prompt rule: there
        is nothing for the model to disobey and no sentence for a later edit to
        soften. A named metric is passed in at every phase, so what is measured
        here is the phase test and not a missing name."""
        for phase in Phase:
            if phase is METRIC_PHASE:
                continue
            with self.subTest(phase=phase):
                tool = prompts.suggest_proof_tool(phase, "paying users")
                self.assertNotIn(
                    "metric_value", tool["function"]["parameters"]["properties"]
                )

    def test_it_is_absent_until_the_builder_has_named_the_number(self):
        """An unnamed metric has no box on the card to prefill and nothing the
        argument could be called — "the number" with no noun beside it is the app
        inventing the metric, which is the rule the card already follows."""
        goal = self.make_goal(user=self.bob, phase=Phase.TRACTION)
        self.assertEqual(goal.metric_name, "")
        tool = prompts.suggest_proof_tool(Phase.TRACTION, goal.metric_name)
        self.assertNotIn("metric_value", tool["function"]["parameters"]["properties"])

    def test_the_argument_asks_for_it_by_the_builders_own_name(self):
        ask = self.schema(self.chat())["metric_value"]["description"]
        self.assertIn("Today's paying users", ask)

    def test_the_argument_forbids_inventing_one(self):
        """The guard the issue is really about. A model guessing a reading is
        worse than the box staying blank: a wrong sentence is visible to the
        builder as a sentence, and a wrong integer is not visibly a guess."""
        ask = self.schema(self.chat())["metric_value"]["description"]
        self.assertIn("ONLY if they have said it in this conversation", ask)
        self.assertIn("Do not estimate it", ask)
        self.assertIn("leave this out entirely", ask)

    # --- an offer, never a record -----------------------------------------

    def test_the_number_lands_beside_the_draft_it_came_with(self):
        self.chat({"metric_value": 2})
        self.assertEqual(CheckIn.objects.get().metric_offer, 2)

    def test_the_draft_records_nothing(self):
        """No reading exists until the builder files. _record_metric stays the
        only writer of metric_value, and the series is drawn from that field — so
        a number Masterji heard is not a point on anybody's chart."""
        self.chat({"metric_value": 2})
        row = CheckIn.objects.get()
        self.assertIsNone(row.metric_value)
        self.assertEqual(row.metric_label, "")
        payload = self.client.get("/api/coach/state/").json()
        self.assertEqual(payload["metric"]["series"], [])

    def test_the_card_is_handed_the_offer(self):
        self.chat({"metric_value": 2})
        payload = self.client.get("/api/coach/state/").json()
        self.assertEqual(payload["today"]["metric_offer"], 2)
        self.assertIsNone(payload["today"]["metric_value"])

    def test_zero_is_a_number_somebody_counted(self):
        """"Nobody paid today" is a fact about the day and one of the more useful
        points in the series, so it cannot double as "he heard no number"."""
        self.chat({"metric_value": 0})
        self.assertEqual(CheckIn.objects.get().metric_offer, 0)

    def test_no_number_said_leaves_the_box_empty(self):
        """The ordinary evening, and the whole of what the model was told to do
        absent a figure."""
        self.chat()
        self.assertIsNone(CheckIn.objects.get().metric_offer)

    def test_a_redraft_that_heard_no_number_drops_the_earlier_one(self):
        """Each call replaces the last, the number along with the words. A
        reading left prefilled under a draft that no longer mentions it is a
        figure the card can no longer account for."""
        self.chat({"metric_value": 2})
        self.chat()
        self.assertIsNone(CheckIn.objects.get().metric_offer)

    def test_a_correction_in_the_same_conversation_replaces_it(self):
        self.chat({"metric_value": 2})
        self.chat({"metric_value": 3})
        self.assertEqual(CheckIn.objects.get().metric_offer, 3)

    def test_a_number_that_could_not_be_filed_is_never_prefilled(self):
        """The draft is filtered by the same arithmetic the filing is
        (views._reading), so the box never opens holding something the server
        would drop on the way back in."""
        for bad in ("two", -4, "", None):
            with self.subTest(bad=bad):
                CheckIn.objects.update(metric_offer=None)
                self.chat({"metric_value": bad})
                self.assertIsNone(CheckIn.objects.get().metric_offer)

    def test_a_call_from_the_wrong_phase_writes_nothing(self):
        """The argument is not in the schema at BUILD, so this call cannot
        arrive — but the branch that writes to the row is forty lines from the
        one that builds the schema, and a guard held up by distance is a guard
        the next edit can move."""
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.BUILD)
        self.chat({"metric_value": 2})
        self.assertIsNone(CheckIn.objects.get().metric_offer)

    # --- filing, which is unchanged ---------------------------------------

    def test_filing_records_it_through_the_path_it_always_used(self):
        """The chat is a route to the box, not a second way into the record. The
        number rides the prove request exactly as a typed one does, and
        _record_metric stamps the label the same way."""
        self.chat({"metric_value": 2})
        self.file_it(metric_value=2)
        row = CheckIn.objects.get()
        self.assertEqual(row.metric_value, 2)
        self.assertEqual(row.metric_label, "paying users")

    def test_a_wrong_drafted_number_cannot_cost_the_proof(self):
        """_record_metric's IGNORED-not-refused rule, untouched and now load-
        bearing for a second reason: the number in the box may be one nobody
        typed. A drafted figure the builder failed to correct costs them the
        reading and never the evening."""
        self.chat({"metric_value": 2})
        response = self.file_it(metric_value="-4")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["checkin"]["proof_status"], "ACCEPTED")
        self.assertIsNone(CheckIn.objects.get().metric_value)

    def test_editing_the_number_down_files_the_edited_one(self):
        """The box is a box. What he heard is where it opens; what they send is
        the reading."""
        self.chat({"metric_value": 2})
        self.file_it(metric_value=1)
        self.assertEqual(CheckIn.objects.get().metric_value, 1)

    def test_rewording_the_task_drops_the_offer_and_keeps_the_reading(self):
        """The two fields part company here, which is the clearest statement of
        what each one is. The draft is evidence for work the builder has just
        changed their mind about; the reading is a count of paying people that a
        re-worded task does not un-happen."""
        self.client.post(
            "/api/coach/checkins/declare/", {"text": "chase Priya", "metric_value": 5}
        )
        self.chat({"metric_value": 2})
        self.client.post("/api/coach/checkins/declare/", {"text": "chase Sunita"})
        row = CheckIn.objects.get()
        self.assertIsNone(row.metric_offer)
        self.assertEqual(row.metric_value, 5)

    def test_the_typed_box_still_works_with_no_chat_at_all(self):
        """#277's Availability rule: a conversational path is an ADDITIONAL route
        to a write, never the only one. An outage, a throttle or a bad payload
        must never be why a builder cannot file today's number — and the suite
        stubs every model call to raise, so this is that day."""
        response = self.client.post(
            "/api/coach/checkins/prove/", {"text": "priya paid", "metric_value": 7}
        )
        self.assertEqual(response.status_code, 200)
        row = CheckIn.objects.get()
        self.assertEqual(row.metric_value, 7)
        self.assertIsNone(row.metric_offer)


class PhaseIntentOfferTests(CoachTestCase):
    """Masterji hearing what the new phase is for and writing the line down.

    The strangest of #277's four rows, because the moment it belongs to already
    happens in chat: the gate opens mid-turn, the brief lands in the transcript,
    and the natural next sentence is "what will this phase have produced?" — a
    question the builder then answered in conversation and had to type again
    into a box on the other pane.

    Everything here turns on one distinction: `intent_offer` is what he heard,
    `intent` is what they pressed, and only the second is the line the coach
    quotes back for three weeks. The load-bearing tests are
    test_the_draft_names_nothing, which is the rule the field exists to keep,
    and test_the_ask_is_not_in_the_same_breath_as_the_unlock, which is the
    timing the issue is really about.
    """

    LINE = "Three hostellers who'd pay today"

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.VALIDATION)
        self.transition = PhaseTransition.objects.create(
            goal=self.goal, from_phase=Phase.IDEA, to_phase=Phase.VALIDATION
        )

    def chat(self, events=None, line=LINE):
        events = events or [
            ("delta", "Good — that's the shape of it."),
            (
                "tool_call",
                {"name": "suggest_phase_intent", "arguments": {"intent": line}},
            ),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)) as m:
            response = self.client.post(
                "/api/coach/chat/", {"content": "three people who'd pay"}
            )
            b"".join(response.streaming_content)
        return m

    def tools(self, called):
        return [t["function"]["name"] for t in called.call_args.kwargs["tools"]]

    def row(self) -> PhaseTransition:
        self.transition.refresh_from_db()
        return self.transition

    def set_intent(self, text: str):
        return self.client.post(
            f"/api/coach/goals/{self.goal.id}/intent/", {"intent": text}
        )

    # --- the window the tool exists in ------------------------------------

    def test_the_tool_is_there_once_something_has_unlocked_the_phase(self):
        self.assertIn("suggest_phase_intent", self.tools(self.chat()))

    def test_the_tool_is_absent_with_no_transition_row(self):
        """IDEA, and the whole of the "no ask on the first phase" rule. Nothing
        unlocked it, so there was never a moment at which to ask — and
        PhaseIntentView 409s there. A tool that is absent cannot be called in
        the one window the view refuses; there is no prompt sentence about that
        window for a later edit to soften."""
        self.transition.delete()
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.IDEA)
        self.assertNotIn("suggest_phase_intent", self.tools(self.chat()))

    def test_a_call_with_no_row_to_write_on_writes_nothing(self):
        """The branch that writes guards itself. The tool being absent is forty
        lines away from the code that trusts it, and a turn that arrives here
        anyway must not invent a transition to hang a line on."""
        self.transition.delete()
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.IDEA)
        self.chat()
        self.assertEqual(PhaseTransition.objects.count(), 0)

    def test_the_row_it_lands_on_is_the_one_that_opened_this_phase(self):
        """A line may only ever describe the phase the builder is standing in —
        the same rule PhaseIntentView enforces, and the reason the target is a
        row rather than a field on the goal."""
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.BUILD)
        opened_build = PhaseTransition.objects.create(
            goal=self.goal, from_phase=Phase.VALIDATION, to_phase=Phase.BUILD
        )
        self.chat()
        opened_build.refresh_from_db()
        self.assertEqual(opened_build.intent_offer, self.LINE)
        self.assertEqual(self.row().intent_offer, "")

    # --- an offer, never a record -----------------------------------------

    def test_the_draft_lands_on_the_row_as_an_offer(self):
        self.chat()
        self.assertEqual(self.row().intent_offer, self.LINE)

    def test_the_draft_names_nothing(self):
        """The one rule this cannot bend. The line a coach quotes back for weeks
        has to be one the builder pressed, so `intent` stays empty until they
        do — and every reader of what the phase is for reads `intent`."""
        self.chat()
        self.assertEqual(self.row().intent, "")
        self.assertEqual(judging._phase_intent(self.goal), "")
        self.assertEqual(prompts.intent_block("", Phase.VALIDATION), "")

    def test_the_card_is_handed_the_offer_beside_the_empty_record(self):
        self.chat()
        payload = self.client.get("/api/coach/state/").json()
        transition = payload["transitions"][-1]
        self.assertEqual(transition["intent_offer"], self.LINE)
        self.assertEqual(transition["intent"], "")

    def test_a_later_draft_replaces_the_offer(self):
        """Re-settable while the phase is open, exactly as the view already is.
        A builder who rewords it mid-conversation should find the second answer
        in the box, not the first."""
        self.chat()
        self.chat(line="One hosteller who paid twice")
        self.assertEqual(self.row().intent_offer, "One hosteller who paid twice")

    def test_a_line_too_long_for_the_view_is_trimmed_not_stored_whole(self):
        """The box can never open holding something the server would refuse on
        the way back in — MAX_CHARS is read off the view rather than copied."""
        self.chat(line="x" * (views.PhaseIntentView.MAX_CHARS + 50))
        self.assertEqual(len(self.row().intent_offer), views.PhaseIntentView.MAX_CHARS)
        self.assertEqual(self.set_intent(self.row().intent_offer).status_code, 200)

    def test_the_line_is_collapsed_the_way_the_view_collapses_it(self):
        self.chat(line="  three hostellers  who\n pay today  ")
        self.assertEqual(self.row().intent_offer, "three hostellers who pay today")

    # --- the press, which is unchanged -------------------------------------

    def test_the_press_goes_through_the_view_it_always_did(self):
        """The chat is a route to the box, not a second way into the record.
        PhaseIntentView is still the only writer of `intent`."""
        self.chat()
        response = self.set_intent(self.LINE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.row().intent, self.LINE)
        self.assertEqual(judging._phase_intent(self.goal), self.LINE)

    def test_pressing_spends_the_draft(self):
        """What they pressed is on the row now. A draft left beside it is an
        alternative to a decision already made."""
        self.chat()
        self.set_intent("my own words")
        self.assertEqual(self.row().intent, "my own words")
        self.assertEqual(self.row().intent_offer, "")

    def test_the_typed_box_still_works_with_no_chat_at_all(self):
        """#277's Availability rule: a conversational path is an ADDITIONAL
        route to a write, never the only one. A provider outage, a bad payload
        or a throttle must never be why a builder cannot say what the phase is
        for — and the suite stubs every model call to raise, so this is that
        day."""
        self.assertEqual(self.set_intent(self.LINE).status_code, 200)
        self.assertEqual(self.row().intent, self.LINE)
        self.assertEqual(self.row().intent_offer, "")

    def test_nothing_about_the_gate_reads_either_field(self):
        """Never a fifth thing to have declared. Skipping the whole of this
        leaves the phase working exactly as it did."""
        self.chat()
        before = gates.gate_status(self.goal)
        self.set_intent(self.LINE)
        self.assertEqual(gates.gate_status(self.goal), before)

    # --- the turn it belongs to --------------------------------------------

    def test_the_ask_is_not_in_the_same_breath_as_the_unlock(self):
        """An unlock is enough news for one message. On the turn that advances,
        the row the draft would land on is the one that opened the phase they
        are LEAVING — so a line written here would describe the wrong phase, on
        top of arriving in a turn already carrying the gate's receipt."""
        self.accept_proofs(self.goal, gates.PROOFS_REQUIRED[Phase.VALIDATION].n)
        self.chat(
            events=[
                ("tool_call", {"name": "propose_phase_advance", "arguments": {}}),
                (
                    "tool_call",
                    {
                        "name": "suggest_phase_intent",
                        "arguments": {"intent": self.LINE},
                    },
                ),
            ]
        )
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.BUILD)
        self.assertEqual(self.row().intent_offer, "")
        self.assertEqual(self.row().intent, "")
        self.assertEqual(
            self.goal.transitions.get(to_phase=Phase.BUILD).intent_offer, ""
        )

    def test_a_refused_advance_is_not_a_turn_for_it_either(self):
        """A turn that asked for the next phase and was told what is still owed
        has no room in it for "and what is this one for?"."""
        self.chat(
            events=[
                ("delta", "Let's see where you are."),
                ("tool_call", {"name": "propose_phase_advance", "arguments": {}}),
                (
                    "tool_call",
                    {
                        "name": "suggest_phase_intent",
                        "arguments": {"intent": self.LINE},
                    },
                ),
            ]
        )
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.VALIDATION)
        self.assertEqual(self.row().intent_offer, "")

    def test_the_next_turn_is_the_one_that_can_write_it(self):
        """And the ask lands there. By the turn after the gate event the row for
        the new phase exists, so the tool is on the table and the line goes
        where it belongs."""
        self.accept_proofs(self.goal, gates.PROOFS_REQUIRED[Phase.VALIDATION].n)
        self.chat(
            events=[("tool_call", {"name": "propose_phase_advance", "arguments": {}})]
        )
        self.goal.refresh_from_db()
        self.assertEqual(self.goal.phase, Phase.BUILD)
        self.assertIn("suggest_phase_intent", self.tools(self.chat()))
        self.assertEqual(
            self.goal.transitions.get(to_phase=Phase.BUILD).intent_offer, self.LINE
        )

    # --- not a wordless turn ------------------------------------------------

    def test_a_turn_that_only_wrote_it_down_still_says_something(self):
        """#270 / #310: the draft arrives alongside an answer, never instead of
        one. Without this the thing that happened landed on the card beside the
        conversation, and the conversation showed the builder's own message with
        nothing under it."""
        self.chat(
            events=[
                (
                    "tool_call",
                    {
                        "name": "suggest_phase_intent",
                        "arguments": {"intent": self.LINE},
                    },
                )
            ]
        )
        row = Message.objects.filter(role=Message.Role.COACH).get()
        self.assertEqual(row.content, guidance.PHASE_INTENT_LANDED)

    def test_the_receipt_says_nothing_is_saved_and_does_not_chase_it(self):
        """It is a receipt for something they said, not a second ask. Nothing
        waits on this line, so the sentence hands the choice back."""
        self.assertIn("not saved until you press it", guidance.PHASE_INTENT_LANDED)
        self.assertIn("fine to leave it", guidance.PHASE_INTENT_LANDED)

    def test_a_dropped_line_gets_no_receipt(self):
        """The counterpart of the turn above. A receipt for a draft that was
        never written is the app telling the builder to go and press something
        that is not there."""
        self.accept_proofs(self.goal, gates.PROOFS_REQUIRED[Phase.VALIDATION].n)
        self.chat(
            events=[
                ("tool_call", {"name": "propose_phase_advance", "arguments": {}}),
                (
                    "tool_call",
                    {
                        "name": "suggest_phase_intent",
                        "arguments": {"intent": self.LINE},
                    },
                ),
            ]
        )
        self.assertNotIn(
            guidance.PHASE_INTENT_LANDED,
            [m.content for m in Message.objects.all()],
        )

    # --- what the model is told ---------------------------------------------

    def test_the_tool_says_it_names_nothing(self):
        description = prompts.SUGGEST_PHASE_INTENT_TOOL["function"]["description"]
        self.assertIn("NAMES NOTHING", description)
        self.assertIn("they press the button themselves", description)

    def test_the_tool_forbids_asking_twice_or_withholding_on_it(self):
        """Never a fifth thing to have declared, in the one place the model
        reads. PhaseIntentView's own rule — "there is no version of this
        endpoint that has to be called before anything" — binds the prompt."""
        description = prompts.SUGGEST_PHASE_INTENT_TOOL["function"]["description"]
        self.assertIn("ONCE", description)
        self.assertIn("never in the same message as the unlock", description)
        self.assertIn("Never ask again", description)
        self.assertIn("never withhold", description)


class LaunchDateOfferTests(CoachTestCase):
    """Masterji hearing the day and the room, and writing them into the box.

    Row 5 of #277's inventory, and the one where the offer / record distance is
    widest. The other three drafts sit beside fields that can be edited; this
    one sits beside `LaunchCommitment`, which is APPEND-ONLY and whose slip
    trail is the entire consequence of having named a date at all. So the
    load-bearing test here is test_a_drafted_date_writes_no_row_ever — a row
    from a tool call would be a move the builder never made, on the one surface
    where moves are the thing being measured.

    Everything else follows from that: `launch_date_offer` is what he heard, a
    LaunchCommitment is what they pressed, and LaunchDateView re-validates the
    lot on the way in because the offer buys no bypass.
    """

    POND = "ROOMS"

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.BUILD)
        self.today = date.today()
        self.when = self.today + timedelta(days=12)

    def chat(self, events=None, when=None, pond=POND):
        when = when if when is not None else self.when
        events = events or [
            ("delta", "Friday it is."),
            (
                "tool_call",
                {
                    "name": "suggest_launch_date",
                    "arguments": {
                        "date": when if isinstance(when, str) else when.isoformat(),
                        "pond": pond,
                    },
                },
            ),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)) as m:
            response = self.client.post(
                "/api/coach/chat/", {"content": "let's say the 12th, to the rooms"}
            )
            b"".join(response.streaming_content)
        return m

    def tools(self, called):
        return [t["function"]["name"] for t in called.call_args.kwargs["tools"]]

    def row(self) -> Goal:
        self.goal.refresh_from_db()
        return self.goal

    def press(self, when=None, pond=POND):
        when = when if when is not None else self.when
        return self.client.post(
            f"/api/coach/goals/{self.goal.id}/launch/",
            {
                "date": when if isinstance(when, str) else when.isoformat(),
                "pond": pond,
            },
        )

    # --- the window the tool exists in --------------------------------------

    def test_the_tool_is_there_in_build(self):
        self.assertIn("suggest_launch_date", self.tools(self.chat()))

    def test_the_tool_is_there_in_launch_too(self):
        """A date that has arrived can still move, and refusing to let it move
        would turn the honest second row into a reason to say nothing."""
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.LAUNCH)
        self.assertIn("suggest_launch_date", self.tools(self.chat()))

    def test_the_tool_is_absent_before_build(self):
        """The view's own refusal, mirrored as a schema fact. A date on a goal
        with no artifact is a wish, and LaunchDateView 409s in IDEA and
        VALIDATION — so the tool is simply not on the table there rather than
        being on it under a prompt rule a later edit could soften."""
        for phase in (Phase.IDEA, Phase.VALIDATION):
            with self.subTest(phase=phase):
                Goal.objects.filter(pk=self.goal.pk).update(phase=phase)
                self.assertNotIn("suggest_launch_date", self.tools(self.chat()))

    def test_the_tool_is_absent_after_launch(self):
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.TRACTION)
        self.assertNotIn("suggest_launch_date", self.tools(self.chat()))

    def test_a_call_outside_the_window_drafts_nothing(self):
        """The branch that writes guards itself. The tool being absent is sixty
        lines away from the code that trusts it, and a turn that arrives here
        anyway must not put a date on a goal the view would refuse one for."""
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.VALIDATION)
        self.chat()
        self.assertIsNone(self.row().launch_date_offer)
        self.assertEqual(self.row().launch_pond_offer, "")
        self.assertEqual(LaunchCommitment.objects.count(), 0)

    # --- an offer, never a record -------------------------------------------

    def test_a_drafted_date_writes_no_row_ever(self):
        """THE guard, and the reason this is not just another prefill.

        LaunchCommitment is append-only and the trail is the whole consequence
        — "declared the 24th, moved once, currently the 26th". A drafted date
        that wrote a row would put a slip on that record which never happened,
        and a second draft would put a second one there. So: draft, redraft,
        redraft again, and the table is still empty.
        """
        self.chat()
        self.chat(when=self.today + timedelta(days=20))
        self.chat(when=self.today + timedelta(days=30), pond="PUBLIC")
        self.assertEqual(LaunchCommitment.objects.count(), 0)
        self.assertIsNone(_state_launch(self.client))

    def test_the_draft_lands_on_the_goal_as_an_offer(self):
        self.chat()
        self.assertEqual(self.row().launch_date_offer, self.when)
        self.assertEqual(self.row().launch_pond_offer, self.POND)

    def test_the_card_is_handed_the_offer_beside_an_empty_record(self):
        self.chat()
        payload = self.client.get("/api/coach/state/").json()
        self.assertEqual(
            payload["launch_offer"],
            {"date": self.when.isoformat(), "pond": self.POND},
        )
        self.assertIsNone(payload["launch"])

    def test_a_later_draft_replaces_the_offer(self):
        """The way declaration_offer is replaced. A builder who moved the day
        mid-conversation should find the second answer in the box."""
        self.chat()
        later = self.today + timedelta(days=20)
        self.chat(when=later, pond="PUBLIC")
        self.assertEqual(self.row().launch_date_offer, later)
        self.assertEqual(self.row().launch_pond_offer, "PUBLIC")

    def test_a_later_draft_the_server_refuses_clears_the_earlier_one(self):
        """Rather than leaving the first day sitting in the box under a
        conversation that has moved on to a day the server will not take."""
        self.chat()
        self.chat(when=self.today - timedelta(days=1))
        self.assertIsNone(self.row().launch_date_offer)
        self.assertEqual(self.row().launch_pond_offer, "")

    def test_the_offer_is_both_halves_or_nothing(self):
        """Half a draft cannot be pressed — the Set button needs a day and a
        room — so a rung that is not on the ladder takes the day down with it
        rather than leaving a control that looks ready and isn't."""
        self.chat(pond="LINKEDIN")
        self.assertIsNone(self.row().launch_date_offer)
        self.assertIsNone(self.client.get("/api/coach/state/").json()["launch_offer"])

    def test_a_day_the_view_would_refuse_is_never_prefilled(self):
        """The bounds the press applies, applied to what the press starts from.
        Dropped rather than clamped: an over-long sentence is a draft a builder
        can cut, but a nearer date the app picked is a default day in a box
        designed to have none."""
        for label, when in (
            ("yesterday", self.today - timedelta(days=1)),
            ("past MAX_DAYS_OUT", self.today + timedelta(days=200)),
            ("not a date at all", "next Friday"),
        ):
            with self.subTest(label):
                Goal.objects.filter(pk=self.goal.pk).update(
                    launch_date_offer=None, launch_pond_offer=""
                )
                self.chat(when=when)
                self.assertIsNone(self.row().launch_date_offer)

    def test_a_draft_whose_day_has_since_been_stops_being_served(self):
        """No `_date` stamp beside this one, unlike the morning's task: a day
        named for Wednesday is exactly as good on Tuesday. What goes stale is
        the day itself, and the box must not open holding one the press would
        turn away."""
        self.chat()
        Goal.objects.filter(pk=self.goal.pk).update(
            launch_date_offer=self.today - timedelta(days=1)
        )
        self.assertIsNone(self.client.get("/api/coach/state/").json()["launch_offer"])

    def test_a_draft_is_not_served_once_the_box_is_gone(self):
        self.chat()
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.TRACTION)
        payload = self.client.get("/api/coach/state/").json()
        self.assertFalse(payload["can_set_launch"])
        self.assertIsNone(payload["launch_offer"])

    # --- the press, unchanged, and still re-validating everything -----------

    def test_the_press_is_what_writes_the_row(self):
        """The chat is a route to the box, not a second way onto the record.
        LaunchDateView is still the only writer of a LaunchCommitment."""
        self.chat()
        response = self.press()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LaunchCommitment.objects.count(), 1)
        self.assertEqual(_state_launch(self.client)["date"], self.when.isoformat())

    def test_pressing_spends_the_draft(self):
        """What they pressed is on the record now. A draft left beside it is an
        alternative to a decision already made — and a stale draft must not
        resurface the next time they open the box to move the day."""
        self.chat()
        self.press()
        self.assertIsNone(self.row().launch_date_offer)
        self.assertEqual(self.row().launch_pond_offer, "")

    def test_the_offer_buys_no_bypass_of_a_past_date(self):
        """An offer sitting on the goal changes nothing about what the view
        will take. The box is an editable control, so what it posts need not be
        what the coach drafted — and the press re-checks all of it."""
        self.chat()
        response = self.press(when=self.today - timedelta(days=2))
        self.assertEqual(response.status_code, 400)
        self.assertIn("already been", response.json()["detail"])
        self.assertEqual(LaunchCommitment.objects.count(), 0)

    def test_the_offer_buys_no_bypass_of_max_days_out(self):
        self.chat()
        response = self.press(
            when=self.today + timedelta(days=views.LaunchDateView.MAX_DAYS_OUT + 1)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(LaunchCommitment.objects.count(), 0)

    def test_the_offer_buys_no_bypass_of_the_ladder(self):
        self.chat()
        response = self.press(pond="LINKEDIN")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(LaunchCommitment.objects.count(), 0)

    def test_the_offer_buys_no_bypass_of_the_phase(self):
        Goal.objects.filter(pk=self.goal.pk).update(
            launch_date_offer=self.when,
            launch_pond_offer=self.POND,
            phase=Phase.IDEA,
        )
        response = self.press()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(LaunchCommitment.objects.count(), 0)

    def test_the_offer_buys_no_bypass_of_the_same_answer_dedupe(self):
        """A second press of a day already on the record is not a move, offer
        or no offer. A row for it would be exactly the invented slip this whole
        change is built to avoid."""
        self.press()
        self.chat()
        response = self.press()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LaunchCommitment.objects.count(), 1)
        self.assertEqual(_state_launch(self.client)["moves"], 0)
        self.assertIsNone(self.row().launch_date_offer)

    def test_a_refused_press_keeps_the_draft(self):
        """The builder's own words are the best starting point for the
        correction. Clearing them would answer "that day has already been" with
        an empty box."""
        self.chat()
        self.press(when=self.today - timedelta(days=2))
        self.assertEqual(self.row().launch_date_offer, self.when)

    def test_the_typed_box_still_works_with_no_chat_at_all(self):
        """#277's Availability rule: a conversational path is an ADDITIONAL
        route to a write, never the only one. A throttle, a provider outage or
        a bad payload must never be why a builder cannot commit to a date — and
        the suite stubs every model call to raise, so this is that day."""
        self.assertEqual(self.press().status_code, 200)
        self.assertEqual(LaunchCommitment.objects.count(), 1)
        self.assertIsNone(self.row().launch_date_offer)

    def test_nothing_about_the_gate_reads_any_of_it(self):
        """PROOFS_REQUIRED and gates.py do not know LaunchCommitment exists,
        and nothing here changes that — for the offer either."""
        before = gates.gate_status(self.goal)
        self.chat()
        self.assertEqual(gates.gate_status(self.row()), before)
        self.press()
        self.assertEqual(gates.gate_status(self.row()), before)

    # --- not a wordless turn ------------------------------------------------

    def test_a_turn_that_only_wrote_it_down_still_says_something(self):
        """#270 / #310: the draft arrives alongside an answer, never instead of
        one. A builder who just said "the 12th, to the rooms" and got a blank
        screen back has been answered by a box on the other pane."""
        self.chat(
            events=[
                (
                    "tool_call",
                    {
                        "name": "suggest_launch_date",
                        "arguments": {
                            "date": self.when.isoformat(),
                            "pond": self.POND,
                        },
                    },
                )
            ]
        )
        row = Message.objects.filter(role=Message.Role.COACH).get()
        self.assertEqual(row.content, guidance.LAUNCH_DATE_LANDED)

    def test_the_receipt_says_nothing_is_committed_yet(self):
        """The receipt that has to be most careful about what it claims: this
        one sits beside an append-only record whose point is that a named date
        is on the trail."""
        self.assertIn("Nothing's committed until you do", guidance.LAUNCH_DATE_LANDED)
        self.assertIn("press Set", guidance.LAUNCH_DATE_LANDED)

    def test_a_dropped_draft_gets_no_receipt(self):
        """A receipt for a draft that was never written is the app telling the
        builder to go and press something that is not in the box."""
        self.chat(
            when=self.today - timedelta(days=1),
            events=[
                (
                    "tool_call",
                    {
                        "name": "suggest_launch_date",
                        "arguments": {
                            "date": (self.today - timedelta(days=1)).isoformat(),
                            "pond": self.POND,
                        },
                    },
                )
            ],
        )
        self.assertNotIn(
            guidance.LAUNCH_DATE_LANDED,
            [m.content for m in Message.objects.all()],
        )

    # --- what the model is told ---------------------------------------------

    def test_the_tool_says_it_commits_nothing(self):
        description = prompts.SUGGEST_LAUNCH_DATE_TOOL["function"]["description"]
        self.assertIn("COMMITS NOTHING", description)
        self.assertIn("they press Set", description)

    def test_the_tool_forbids_choosing_the_date_itself(self):
        """The box has no default day and no placeholder on purpose — a date
        the app chose is not one anybody committed to — and a model that
        suggests a Friday and writes it down in the same breath has handed the
        default back. Coaching toward a date is chat; choosing one is not the
        tool's to do."""
        description = prompts.SUGGEST_LAUNCH_DATE_TOOL["function"]["description"]
        self.assertIn("named a day THEMSELVES", description)
        self.assertIn("never a date you picked for them", description)

    def test_the_ladder_in_the_schema_is_the_playbooks_own(self):
        """Served from LaunchCommitment.Pond rather than typed out again — a
        builder inventing a fifth rung is a builder avoiding the four, and a
        second copy of the four would drift."""
        pond = prompts.SUGGEST_LAUNCH_DATE_TOOL["function"]["parameters"]["properties"][
            "pond"
        ]
        self.assertEqual(pond["enum"], list(LaunchCommitment.Pond.values))


class GoalWordingOfferTests(CoachTestCase):
    """Masterji hearing the sharper sentence, and writing it at the reword box.

    Row 7 of #277's inventory, and the last one. Its offer and its record look
    more alike than any of the others' — a string on the goal, one press from a
    string on the goal — so the tests that matter here are the ones keeping them
    apart:

    - test_the_press_is_what_renames_the_goal and its transcript row: the chat
      is a route to the control, and GoalUpdateView is still the only writer.
    - test_a_draft_made_before_the_bank_cannot_outrun_the_record: the sharpest
      edge in the issue. A draft written at zero proofs and pressed after the
      first acceptance meets the 409 like any other rename would.
    - test_the_tool_is_gone_once_a_proof_banks: the moment the record points at
      the sentence the tool leaves the list, on the same count the view checks.
    """

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal()
        self.sharper = "Tiffin app for Pune hostel students who miss home food"

    def chat(self, events=None, title=None):
        title = self.sharper if title is None else title
        events = events or [
            ("delta", "That's the one."),
            (
                "tool_call",
                {"name": "suggest_goal_wording", "arguments": {"title": title}},
            ),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)) as m:
            response = self.client.post(
                "/api/coach/chat/", {"content": "it's really the hostel kids"}
            )
            b"".join(response.streaming_content)
        return m

    def tools(self, called):
        return [t["function"]["name"] for t in called.call_args.kwargs["tools"]]

    def row(self) -> Goal:
        self.goal.refresh_from_db()
        return self.goal

    def press(self, title=None):
        return self.client.patch(
            f"/api/coach/goals/{self.goal.id}/",
            {"title": self.sharper if title is None else title},
        )

    def state_goal(self) -> dict:
        return self.client.get("/api/coach/state/").json()["goal"]

    # --- the window the tool exists in --------------------------------------

    def test_the_tool_is_there_while_nothing_is_banked(self):
        self.assertIn("suggest_goal_wording", self.tools(self.chat()))

    def test_the_tool_is_gone_once_a_proof_banks(self):
        """The view's own lock, mirrored as a schema fact. Past the first
        accepted proof the record points at this sentence, GoalUpdateView 409s,
        and the tool is simply not on the table rather than being on it under a
        prompt rule a later edit could soften."""
        self.accept_proofs(self.goal, 1)
        self.assertNotIn("suggest_goal_wording", self.tools(self.chat()))

    def test_the_lock_is_the_total_and_not_this_phase(self):
        """`accepted_proofs_total`, the same count the view reads: a proof
        banked in IDEA still holds the wording after the goal reaches
        VALIDATION."""
        self.accept_proofs(self.goal, 1)
        Goal.objects.filter(pk=self.goal.pk).update(phase=Phase.VALIDATION)
        self.assertNotIn("suggest_goal_wording", self.tools(self.chat()))

    def test_a_call_past_the_lock_drafts_nothing(self):
        """The branch that writes guards itself. The tool being absent is sixty
        lines from the code that trusts it, and a turn that arrives here anyway
        must not put a draft on a goal the view would refuse a rename for."""
        self.accept_proofs(self.goal, 1)
        self.chat()
        self.assertEqual(self.row().title_offer, "")

    # --- an offer, never a record -------------------------------------------

    def test_a_draft_renames_nothing_ever(self):
        """THE guard. Draft, redraft, redraft again — the title on the record is
        still the one the builder committed to, and no transcript row claims
        otherwise."""
        self.chat()
        self.chat(title="Tiffin for hostellers")
        self.chat(title="Home food for Pune hostellers, delivered")
        self.assertEqual(self.row().title, "Tiffin app")
        self.assertFalse(
            Message.objects.filter(content__startswith="Reworded:").exists()
        )

    def test_the_draft_lands_on_the_goal_as_an_offer(self):
        self.chat()
        self.assertEqual(self.row().title_offer, self.sharper)

    def test_the_card_is_handed_the_offer_beside_the_unchanged_title(self):
        self.chat()
        payload = self.state_goal()
        self.assertEqual(payload["title_offer"], self.sharper)
        self.assertEqual(payload["title"], "Tiffin app")
        self.assertFalse(payload["title_locked"])

    def test_a_later_draft_replaces_the_offer(self):
        self.chat()
        self.chat(title="Home food for Pune hostellers, delivered")
        self.assertEqual(
            self.row().title_offer, "Home food for Pune hostellers, delivered"
        )

    def test_a_draft_the_server_will_not_take_clears_the_earlier_one(self):
        """The tri-state, and why `wording_called` sits beside the draft. An
        empty title is not the same event as a turn that mentioned no wording at
        all, and leaving the first sentence in the box under a conversation that
        has moved past it is the stale draft #342 spent a field to avoid."""
        self.chat()
        self.chat(title="   ")
        self.assertEqual(self.row().title_offer, "")

    def test_the_words_already_on_the_card_are_not_an_offer(self):
        """A draft identical to the title is a "Use this" that changes nothing
        and a Save the view declines to log — an affordance offering the
        sentence already above it, which reads as a rename that did not take."""
        self.chat(title="Tiffin app")
        self.assertEqual(self.row().title_offer, "")

    def test_a_long_draft_is_cut_to_what_the_column_holds(self):
        """Trimmed rather than dropped, as the declaration is: an over-long
        sentence is one the builder can see and cut, and the box must never open
        holding something the column would truncate on the way back in."""
        self.chat(title="x" * 400)
        self.assertEqual(len(self.row().title_offer), 200)

    def test_the_offer_stops_being_served_once_a_proof_banks(self):
        """A draft with nowhere to land. The control is gone at the same count
        and the press 409s, so an offer sent past it would be a suggestion
        beside no way to take it."""
        self.chat()
        self.accept_proofs(self.goal, 1)
        payload = self.state_goal()
        self.assertTrue(payload["title_locked"])
        self.assertEqual(payload["title_offer"], "")

    def test_the_offer_is_not_a_clients_to_assert(self):
        """Read-only on the serializer. A PATCH that could set it would let the
        box fill itself, which is the one thing "the builder still presses"
        rules out."""
        self.client.patch(
            f"/api/coach/goals/{self.goal.id}/", {"title_offer": "mine now"}
        )
        self.assertEqual(self.row().title_offer, "")

    # --- the press, which is still the only writer --------------------------

    def test_the_press_is_what_renames_the_goal(self):
        self.chat()
        response = self.press()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.row().title, self.sharper)

    def test_the_press_still_writes_the_transcript_row(self):
        """The row a real rename earns, written by GoalUpdateView and nowhere
        else — so a rename that came through the chat path is recorded exactly
        like one typed into the box."""
        self.chat()
        self.press()
        row = Message.objects.filter(content__startswith="Reworded:").get()
        self.assertEqual(
            row.content,
            guidance.TITLE_SHARPENED.format(before="Tiffin app", after=self.sharper),
        )

    def test_pressing_spends_the_draft(self):
        """What they pressed is the goal now. A draft left beside it is an
        alternative to a decision already made, and it would come back up the
        next time they tapped reword."""
        self.chat()
        self.press()
        self.assertEqual(self.row().title_offer, "")

    def test_pressing_with_their_own_edit_still_spends_the_draft(self):
        """The box is an editable control, so what it posts need not be what the
        coach drafted — and the offer has been answered either way."""
        self.chat()
        self.press(title="Home food, for hostellers in Pune")
        self.assertEqual(self.row().title, "Home food, for hostellers in Pune")
        self.assertEqual(self.row().title_offer, "")

    def test_a_draft_made_before_the_bank_cannot_outrun_the_record(self):
        """The sharpest edge in #325, and the reason the press re-checks.

        The draft was written when nothing was banked and the control was on
        screen. Then an evening happened. The press meets the same 409 a typed
        rename would, because the lock is read at the press against the record —
        never against when the sentence was drafted.
        """
        self.chat()
        self.assertEqual(self.row().title_offer, self.sharper)
        self.accept_proofs(self.goal, 1)
        response = self.press()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], guidance.TITLE_LOCKED)
        self.assertEqual(self.row().title, "Tiffin app")
        self.assertFalse(
            Message.objects.filter(content__startswith="Reworded:").exists()
        )

    def test_the_offer_buys_no_bypass_of_the_phase_or_the_status(self):
        """Not a road around the gate, and it cannot become one: the serializer
        holds both read-only, so a PATCH may reword a goal and may never advance
        one — offer or no offer."""
        self.chat()
        self.client.patch(
            f"/api/coach/goals/{self.goal.id}/",
            {"title": self.sharper, "phase": Phase.BUILD, "status": "COMPLETED"},
        )
        self.assertEqual(self.row().phase, Phase.IDEA)
        self.assertEqual(self.row().status, Goal.Status.ACTIVE)

    def test_the_typed_route_still_works_with_no_chat_at_all(self):
        """#277's Availability rule: a conversational path is an ADDITIONAL
        route to a write, never the only one. The suite stubs every model call
        to raise, so this is the day the provider is down."""
        self.assertEqual(self.press().status_code, 200)
        self.assertEqual(self.row().title, self.sharper)

    def test_nothing_about_the_gate_reads_any_of_it(self):
        before = gates.gate_status(self.goal)
        self.chat()
        self.assertEqual(gates.gate_status(self.row()), before)
        self.press()
        self.assertEqual(gates.gate_status(self.row()), before)

    # --- not a wordless turn ------------------------------------------------

    def test_a_turn_that_only_wrote_it_down_still_says_something(self):
        """#270 / #310: the draft arrives alongside an answer, never instead of
        one. A builder who just said the sharper sentence out loud and got a
        blank screen back has been answered by a control on the other pane."""
        self.chat(
            events=[
                (
                    "tool_call",
                    {
                        "name": "suggest_goal_wording",
                        "arguments": {"title": self.sharper},
                    },
                )
            ]
        )
        row = Message.objects.filter(role=Message.Role.COACH).get()
        self.assertEqual(row.content, guidance.GOAL_WORDING_LANDED)

    def test_the_receipt_says_nothing_is_renamed_and_names_the_window(self):
        self.assertIn("Nothing's changed until you do", guidance.GOAL_WORDING_LANDED)
        self.assertIn("Save wording", guidance.GOAL_WORDING_LANDED)
        self.assertIn("first proof banks", guidance.GOAL_WORDING_LANDED)

    def test_a_dropped_draft_gets_no_receipt(self):
        """A receipt for a draft that was never written is the app telling the
        builder to go and press something that is not on the card."""
        self.chat(
            events=[
                (
                    "tool_call",
                    {
                        "name": "suggest_goal_wording",
                        "arguments": {"title": "Tiffin app"},
                    },
                )
            ]
        )
        self.assertNotIn(
            guidance.GOAL_WORDING_LANDED,
            [m.content for m in Message.objects.all()],
        )

    # --- what the model is told ---------------------------------------------

    def test_the_tool_says_it_renames_nothing(self):
        description = prompts.SUGGEST_GOAL_WORDING_TOOL["function"]["description"]
        self.assertIn("RENAMES NOTHING", description)
        self.assertIn("they press Save wording", description)

    def test_the_tool_forbids_the_models_own_phrasing(self):
        """The workshop's rule with the constraint already live: one tap from
        "his suggestion" to a database constraint is how a builder ends up
        coached on somebody else's idea."""
        description = prompts.SUGGEST_GOAL_WORDING_TOOL["function"]["description"]
        self.assertIn("said the sharper sentence THEMSELVES", description)
        self.assertIn("never your own preferred phrasing", description)
