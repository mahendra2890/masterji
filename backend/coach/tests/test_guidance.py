"""`guidance.py` — how he talks: the registers he needs, the openers, the state
block he is handed, and the voice reaching every room.
"""

from datetime import date, timedelta
from unittest import mock

from django.utils import timezone

from .. import (
    gates,
    guidance,
    prompts,
    streaks,
    views,
)
from ..models import (
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    Phase,
)
from .base import CoachTestCase


class DeclineOnlyWhatWasAskedTests(CoachTestCase):
    """A builder tapped the first opener this product offers them — "Who
    exactly has this problem?" — and was told they were asking about the wrong
    week for stack or features, which they had not mentioned. The phase rule
    deferring tech talk was the one rule in the block written without a
    trigger, so it fired at nobody."""

    def system_for(self, goal=None, **kwargs):
        goal = goal or self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def test_every_phase_is_told_to_answer_what_was_asked(self):
        """One goal walked through the phases, not four goals — a user is only
        ever allowed one open goal at a time."""
        goal = self.make_goal()
        for phase in Phase:
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.assertIn(prompts.ANSWER_WHAT_THEY_ASKED, self.system_for(goal))

    def test_it_holds_in_both_ways_of_talking(self):
        """THINKING_MODE moves him to the builder's side of the table. Refusing
        a question nobody asked is wrong from either side of it."""
        self.assertIn(prompts.ANSWER_WHAT_THEY_ASKED, self.system_for(mode="THINKING"))

    def test_no_phase_defers_a_topic_without_naming_who_raised_it(self):
        """The invariant the incident came from. A deferral is a reply, so the
        rule that carries one has to say what it is replying to — otherwise it
        reads as a standing order and gets spent on a builder who never went
        near the topic."""
        triggers = ("if the builder asks", "when the builder brings")
        for phase, rule in prompts.PHASE_RULES.items():
            with self.subTest(phase=phase):
                if "wait" in rule.lower():
                    self.assertTrue(
                        any(t in rule.lower() for t in triggers),
                        f"{phase} defers something without naming who raised it",
                    )

    def test_every_phase_can_offer_an_opener(self):
        """The other half of the same failure: the product suggests these, so
        a coach that treats one as off-phase drift is arguing with the app the
        builder is sitting in. A phase missing from the dict is a KeyError on
        the guidance payload the moment it unlocks."""
        for phase in Phase:
            with self.subTest(phase=phase):
                self.assertTrue(guidance.OPENERS[phase])


class ThinkingModeTests(CoachTestCase):
    """A per-user way of talking. Never a way past the door."""

    def system_for(self, **kwargs):
        goal = self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def as_thinker(self):
        self.alice.mode = "THINKING"
        self.alice.save(update_fields=["mode"])

    def test_thinking_mode_puts_him_on_the_builders_side(self):
        self.assertIn(prompts.THINKING_MODE, self.system_for(mode="THINKING"))

    def test_coach_is_the_default_and_carries_none_of_it(self):
        self.assertNotIn(prompts.THINKING_MODE, self.system_for())

    def test_the_phase_rules_survive_the_mode(self):
        """Thinking a tech stack through together in IDEA is still the wrong
        week's work. The mode changes the posture, not the phase."""
        self.assertIn(prompts.PHASE_RULES[Phase.IDEA], self.system_for(mode="THINKING"))

    def test_the_setting_reaches_the_conversation(self):
        self.make_goal()
        self.as_thinker()
        with mock.patch(
            "coach.views.llm.stream_chat", return_value=iter([])
        ) as streamed:
            response = self.client.post("/api/coach/chat/", {"content": "I'm stuck"})
            b"".join(response.streaming_content)  # the prompt is built in the generator
        self.assertIn(prompts.THINKING_MODE, streamed.call_args.args[0])

    def test_thinking_mode_is_not_a_way_past_the_gate(self):
        """The whole risk of a friendlier mode: that friendliness becomes a
        second door. gates.py doesn't read User.mode and this pins it."""
        goal = self.make_goal()
        self.as_thinker()
        response = self.client.post(f"/api/coach/goals/{goal.id}/advance/")
        self.assertEqual(response.status_code, 409)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, Phase.IDEA)

    def test_the_mode_rides_the_state_payload(self):
        self.make_goal()
        self.assertEqual(self.client.get("/api/coach/state/").data["mode"], "COACH")
        self.as_thinker()
        self.assertEqual(self.client.get("/api/coach/state/").data["mode"], "THINKING")

    def test_the_mode_is_the_builders_to_set(self):
        response = self.client.patch(
            "/api/auth/me/", {"mode": "THINKING"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.mode, "THINKING")


class NotAboutTheWorkTests(CoachTestCase):
    """The one message this coach had no register for.

    Its standing instruction for a stuck builder is "name it and assign the
    smallest next real-world action" — right for stuck-on-the-work, and wrong,
    with total confidence, for "I can't keep doing this". Nothing in prompts.py
    or in any playbook drew that line: RESPECT_RULE forbids contempt and never
    says what to do when the message is not about the work at all.

    Which matters more here than it would elsewhere. The builder this product
    is for is nineteen, in a tier-2 college, with a family that has opinions
    about placement season.
    """

    def system_for(self, goal=None, **kwargs):
        goal = goal or self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def test_every_phase_knows_what_to_do_when_it_is_not_about_the_work(self):
        goal = self.make_goal()
        for phase in Phase:
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.assertIn(
                    prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK, self.system_for(goal)
                )

    def test_it_holds_in_both_ways_of_talking(self):
        """THINKING_MODE moves him to the builder's side of the table. Handing
        somebody a task instead of an answer is wrong from either side of it."""
        self.assertIn(
            prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK, self.system_for(mode="THINKING")
        )

    def test_the_turn_costs_them_no_assignment(self):
        """The whole content of the rule. A builder who says they are worn out
        and gets "so what's tonight's task" has been talked over."""
        block = prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK
        self.assertIn("no assignment", block)
        self.assertIn("no declaration demanded", block)

    def test_it_is_only_ever_a_reply(self):
        """Same condition every deferral in PHASE_RULES carries, and for the
        reason ANSWER_WHAT_THEY_ASKED was written: deciding somebody is
        struggling from a gap in their record is inventing it, and being
        handled gently for a crisis you don't have is its own small insult."""
        self.assertIn(
            "Only ever when they raise it", prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK
        )

    def test_a_clause_on_the_way_to_something_else_is_still_raising_it(self):
        """How it actually arrives. "Only when they raise it" read as "only
        when it is the SUBJECT of the message" would walk straight past the
        commonest presentation there is — a line about being done with all
        this, in front of a question about tomorrow's outreach — which is the
        one this rule most needed to catch."""
        block = prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK
        self.assertIn("does not have to be what the message is ABOUT", block)
        self.assertIn("That clause is them raising it", block)

    def test_their_question_is_still_answered(self):
        """The other half of the same case, and the failure mode of fixing
        only the first half: attending to them solemnly while their actual
        question goes unanswered is not care, it is a different way of not
        listening."""
        block = prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK
        self.assertIn("if they asked you something, answer that too", block)
        self.assertIn("may not do is answer only the question", block)

    def test_frustration_with_the_work_is_still_the_work(self):
        """The boundary that keeps the rule from eating the product. A builder
        saying the outreach is going nowhere wants a coach; going soft there is
        RESPECT_RULE's own failure again — a response that costs nothing to
        give gets given where it was never wanted."""
        self.assertIn(
            "Frustration with the WORK is still the work",
            prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK,
        )

    def test_he_stays_a_coach_and_does_not_invent_a_service(self):
        """Past a hard week the honest answer is that this is not what a
        coaching app is for. A model reaching for a helpline number it half
        remembers is the failure mode that answer exists to avoid."""
        block = prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK
        self.assertIn("past what a coaching app is for", block)
        self.assertIn("Never invent a helpline", block)
        self.assertIn("do not diagnose them", block)

    def test_a_hard_night_still_does_not_open_the_gate(self):
        """The risk every softening carries: that kindness becomes a second
        door. gates.py has never read a message, and this pins it from the
        newest rule that could have been mistaken for one."""
        goal = self.make_goal()
        response = self.client.post(f"/api/coach/goals/{goal.id}/advance/")
        self.assertEqual(response.status_code, 409)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, Phase.IDEA)
        self.assertEqual(gates.accepted_proofs(goal), 0)

    def test_the_promise_that_closing_is_free_is_one_the_server_keeps(self):
        """He is told to say closing costs them nothing — no waiting period, no
        minimum, nothing to earn first. That is RetireView's actual behaviour
        and it has to stay that way: a coach making a promise the server has
        quietly stopped keeping is worse than one who never made it."""
        goal = self.make_goal()
        with mock.patch("coach.views.llm.complete", return_value="Closed."):
            response = self.client.post(
                f"/api/coach/goals/{goal.id}/retire/", {"reason": "I'm done for now"}
            )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.status, Goal.Status.ABANDONED)

    def test_the_work_in_the_same_message_is_still_written_down(self):
        """A builder who says "I'm exhausted, but I did talk to Priya" must not
        pay for the first clause with the second. The rule says answer the
        person first and bank the work quietly — it never suspends SPOT_PROOF."""
        system = self.system_for()
        self.assertIn("answer the person first", prompts.WHEN_IT_IS_NOT_ABOUT_THE_WORK)
        self.assertIn(prompts.SPOT_PROOF, system)


class DoubtingTheIdeaTests(CoachTestCase):
    """"Is this even the right idea?" — the question the coach answered by
    defending the goal.

    Its neighbour above handles the message that is about the person. This one
    is about the idea, and it had the opposite problem: not an absent register
    but a wrong one. PHASE_RULES[IDEA] gives the coach exactly one doubt-
    adjacent move — "put the problem statement back in front of them" — which
    is right for a builder drifting toward their tech stack and reads, to a
    builder asking whether to keep going at all, as the app protecting its own
    sunk cost. Same tone user-testing disliked, on the turn most likely to end
    in a closed tab.
    """

    def system_for(self, goal=None, **kwargs):
        goal = goal or self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def test_every_phase_can_answer_the_doubt(self):
        """Doubt is not an IDEA-phase event. It arrives hardest in VALIDATION,
        where the builder has heard three people be polite about it, and the
        block has to be in the prompt when it does."""
        goal = self.make_goal()
        for phase in Phase:
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.assertIn(prompts.WHEN_THEY_DOUBT_THE_IDEA, self.system_for(goal))

    def test_it_holds_in_the_mode_built_for_thinking(self):
        """THINKING mode takes its own branch through the format call, and it
        is the likeliest room for this question: a builder who wants to think
        rather than declare is often thinking about whether to continue."""
        self.assertIn(
            prompts.WHEN_THEY_DOUBT_THE_IDEA, self.system_for(mode="THINKING")
        )

    def test_the_turn_does_not_defend_the_goal(self):
        """The whole content of the rule. A builder asking whether to keep
        going who gets today's task back has been argued with, not answered."""
        block = prompts.WHEN_THEY_DOUBT_THE_IDEA
        self.assertIn("do not defend the goal", block)
        self.assertIn("not asking what to do tonight", block)

    def test_it_is_only_ever_a_reply(self):
        """Same condition every deferral carries, for the reason
        ANSWER_WHAT_THEY_ASKED exists: a coach who decides from a quiet week
        that somebody has lost faith in their idea has invented it, and
        raising it unprompted is how you plant the doubt you meant to answer."""
        self.assertIn("Only ever when they raise it", prompts.WHEN_THEY_DOUBT_THE_IDEA)

    def test_the_readiness_test_is_whichever_phase_they_are_in(self):
        """COACH_SYSTEM serves all four phases from one string, so the true
        thing the coach reaches for — the bar in front of them IS the
        readiness test — has to be worded for the phase the builder is
        actually in. Naming IDEA's problem statement would make the sentence
        wrong for three quarters of the builders who read it."""
        block = prompts.WHEN_THEY_DOUBT_THE_IDEA
        self.assertIn("bar in front of them", block)
        self.assertNotIn("problem statement", block)

    def test_the_size_question_gets_the_cut_and_not_the_doors(self):
        """The block's other boundary (#330). Its opening line only separates
        the quit question from "is tonight's task the right task", so a builder
        asking whether their goal was too BIG — a question about a goal they
        were keeping — fell through to the doors and was handed the exit,
        unprompted, on day one. Size gets a cut; the exit is not an answer to
        it."""
        block = prompts.WHEN_THEY_DOUBT_THE_IDEA
        self.assertIn("the answer to size is a cut, never an exit", block)
        self.assertIn("Do not name closing on a size question", block)

    def test_the_size_answer_knows_the_control_and_its_condition(self):
        """The product's own answer to a too-wide goal is the reword control,
        and the coach could not offer what the prompt never mentioned. The
        mention must carry the control's real condition — it is offered until
        the first proof banks (GoalSharpenView refuses after, the card hides
        it) — so the sentence stays true on day thirty, and in the reopened
        room, which shares this block."""
        block = prompts.WHEN_THEY_DOUBT_THE_IDEA
        self.assertIn("reword control", block)
        self.assertIn("while nothing is banked yet", block)


class ClosingIsTheirsTests(CoachTestCase):
    """A builder typed `close` twice and was told "Done. This goal is closed."
    on a goal that was still ACTIVE, at 0/1 proofs, with no GoalRetirement row.

    Its neighbour above is what produced the offer, and correctly: closing IS
    free and the coach should keep saying so. What was missing was the other
    two thirds — a way to do it, and a rule against saying he had. The tests
    here are those two, and the second one is the bug itself pinned: a close
    proposed from the chat turn must leave the record exactly where it was.
    """

    def system_for(self, goal=None, **kwargs):
        goal = goal or self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def test_the_guard_reaches_every_phase(self):
        """One string serves all four, and a builder asks to get out from any
        of them — most often from VALIDATION, where the phase's whole job is
        finding out the answer is no."""
        goal = self.make_goal()
        for phase in Phase:
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.assertIn(prompts.CLOSING_IS_THEIRS, self.system_for(goal))

    def test_it_holds_in_the_mode_built_for_thinking(self):
        """THINKING takes its own branch through the format call, and it is
        the room the reported transcript happened in."""
        self.assertIn(prompts.CLOSING_IS_THEIRS, self.system_for(mode="THINKING"))

    def test_it_forbids_the_sentence_that_was_false(self):
        """The whole content of the rule. Everything else in it is directions."""
        self.assertIn("NEVER say a goal is closed", prompts.CLOSING_IS_THEIRS)

    def test_it_takes_nothing_away_from_the_doors(self):
        """The offer was right and stays. A guard that made the coach hedge on
        whether closing is allowed would trade a false sentence for a cowardly
        one, on the turn where this product's argument is that closing honestly
        is fine."""
        self.assertIn("closing is free", prompts.CLOSING_IS_THEIRS)
        self.assertIn(
            prompts.WHEN_THEY_DOUBT_THE_IDEA, self.system_for()
        )

    def test_the_tool_is_only_ever_a_reply(self):
        """Same condition its neighbour carries, and it matters more here: a
        sentence that raises the doubt can be argued with, and a box that opens
        on the card in place of the two doors cannot."""
        self.assertIn("Only ever when they have asked to get out", prompts.CLOSING_IS_THEIRS)
        self.assertIn(
            "ONLY when the builder has said they want out",
            prompts.PROPOSE_GOAL_CLOSE_TOOL["function"]["description"],
        )

    def test_the_offer_obeys_the_same_condition_as_the_call(self):
        """The gap live use found between the tool and the mouth (#330). The
        call was scoped to a builder who asked out in words; nothing scoped the
        sentence advertising it, so a builder asking about the goal's size was
        told the close box was one plain word away. The offer is the exit
        standing open in a quieter voice, and it follows the same rule."""
        self.assertIn("The OFFER follows the same condition", prompts.CLOSING_IS_THEIRS)
        self.assertIn("never volunteer", prompts.CLOSING_IS_THEIRS)

    def test_the_reopened_room_is_not_told_about_a_tool_it_lacks(self):
        """That room is handed no tools at all, and describing propose_goal_close
        to it would be the first half of this bug again — a model told to reach
        for something that isn't there."""
        room = prompts.build_reopened_prompt(
            "Tiffin app", "VALIDATION", 4, 2, None, 1, 6
        )
        self.assertNotIn("propose_goal_close", room)
        self.assertIn(prompts.WHEN_THEY_DOUBT_THE_IDEA, room)

    def test_the_chat_turn_is_actually_handed_the_tool(self):
        """The half of this that a mocked stream cannot see. Every other test
        here feeds the tool call in by hand, so the tool could be missing from
        the list the model is given and they would all still pass — while in
        production Masterji is back to being told to offer a door with no
        function behind it, which is two thirds of the reported bug."""
        seen = {}

        def capture(system, messages, **kwargs):
            seen["tools"] = kwargs.get("tools") or []
            yield "delta", "ok"

        self.make_goal()
        with mock.patch("coach.views.llm.stream_chat", side_effect=capture):
            b"".join(
                self.client.post(
                    "/api/coach/chat/", {"content": "I want out"}
                ).streaming_content
            )
        names = [t["function"]["name"] for t in seen["tools"]]
        self.assertIn("propose_goal_close", names)

    def test_a_proposed_close_opens_the_box_and_closes_nothing(self):
        """The bug, pinned. propose_goal_close OPENS THE CONTROL — the wire
        event is its entire effect. Both of a close's inputs are the builder's
        (RetireView 400s without a reason; the outcome is a button they press),
        so a turn that closed the goal here would be inventing the record."""
        goal = self.make_goal()
        events = [
            ("delta", "Opened the close box on your card."),
            ("tool_call", {"name": "propose_goal_close", "arguments": {}}),
        ]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)):
            response = self.client.post("/api/coach/chat/", {"content": "close"})
            body = b"".join(response.streaming_content).decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('"t": "close"', body)
        goal.refresh_from_db()
        self.assertEqual(goal.status, Goal.Status.ACTIVE)
        self.assertEqual(GoalRetirement.objects.filter(goal=goal).count(), 0)


class RouteIsGradedPlatformBlindTests(CoachTestCase):
    """The same unnamed "a group where they are" was refused as a channel on
    one platform and credited as progress on another (#330). The playbook's
    anti-example and the coach's own example sentence had turned into the
    grade: the rule was being applied to the platform string, not to whether
    a room was named.
    """

    def system_for(self, goal=None, **kwargs):
        goal = goal or self.make_goal()
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", **kwargs
        )

    def test_the_rule_and_its_test_are_in_ideas_phase_rules(self):
        """One instruction, three teeth: the grade is platform-blind, an
        answer earns nothing by echoing an example the coach gave, and
        platform knowledge is spent the one honest way — saying so when the
        claimed kind of room does not exist where it is claimed to be."""
        rule = prompts.PHASE_RULES[Phase.IDEA]
        self.assertIn("Grade the route platform-blind", rule)
        self.assertIn("echoing an example you gave", rule)
        self.assertIn("does not exist on the platform claimed", rule)

    def test_it_reaches_the_room_where_the_grading_happens(self):
        """PHASE_RULES[IDEA] feeds both the chat turn and the declaration
        reaction, and the misgrading happened in chat — so the sentence has
        to survive composition, not just exist in the dict."""
        self.assertIn("Grade the route platform-blind", self.system_for())

    def test_it_names_no_platform(self):
        """The fix for grading by platform string must not plant new platform
        strings to grade by: the rule stays generic or it becomes the next
        anti-example list. The channel examples already in the rule ('Reddit',
        'LinkedIn') predate it and are the playbook's own."""
        start = prompts.PHASE_RULES[Phase.IDEA].index("Grade the route")
        end = prompts.PHASE_RULES[Phase.IDEA].index("IF THE BUILDER")
        sentence = prompts.PHASE_RULES[Phase.IDEA][start:end]
        for platform in ("Instagram", "Telegram", "WhatsApp", "Reddit", "LinkedIn"):
            self.assertNotIn(platform, sentence)


class TheCoachCanSeeTheCalendarTests(CoachTestCase):
    """The state block held counts and no dates.

    It carries the phase, the gate's arithmetic, the streak and tonight — all
    of it true, none of it saying WHEN. So a builder on day two of VALIDATION
    and one circling it for three weeks were described to the model in the same
    words, and a builder coming back after a silent week was described as though
    they had been here last night. Under a heading that says "trust this over
    anything claimed in chat", the coach could only bluff or contradict them.
    """

    def block(self, goal, **kwargs):
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "nothing yet", **kwargs
        )

    def test_the_state_block_says_how_long_this_phase_has_been_open(self):
        """The fact the tough-love register had no truthful way to state.
        Enforcement is untouched: a phase has no clock, and this only lets the
        coach say out loud what the record already knows."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        self.assertIn("In this phase: 12 days", self.block(goal, days_in_phase=12))

    def test_a_calendar_is_only_ever_stated_when_it_was_computed(self):
        """Every other caller of build_system_prompt — the tests here, and any
        future one without the builder's own date — gets the block it always
        got. A default would have the prompt asserting a calendar nobody
        measured, which is the one thing this block may never do."""
        goal = self.make_goal()
        self.assertNotIn("In this phase:", self.block(goal))
        self.assertNotIn("Last complete day:", self.block(goal))

    def test_the_day_a_phase_opens_is_not_a_negative_number(self):
        """TIME_ZONE is UTC and the loop runs on the builder's own date, so for
        anyone behind UTC the phase can be stamped on a date their calendar has
        not reached — see streaks.days_in_phase. Clamped there rather than worded
        around here."""
        goal = self.make_goal()
        Goal.objects.filter(pk=goal.pk).update(
            phase_entered_at=timezone.now() + timedelta(days=1)
        )
        goal.refresh_from_db()
        self.assertEqual(streaks.days_in_phase(goal, date.today()), 0)
        self.assertIn("In this phase: today", self.block(goal, days_in_phase=0))

    def test_a_broken_streak_says_how_long_it_has_been(self):
        """The returning builder is the most valuable person to get the next
        sentence right for, and the coach had nothing to get it right from."""
        goal = self.make_goal()
        self.assertIn(
            "Last complete day: 6 days ago", self.block(goal, days_since_complete=6)
        )

    def test_a_running_streak_is_told_no_gap(self):
        """The streak line already says a day was complete today or yesterday —
        current_streak counts no further back. Restating it as a gap every turn
        is noise in a block whose whole authority is that everything in it
        matters, and an invitation to remark on an absence that isn't one."""
        goal = self.make_goal()
        self.assertNotIn(
            "Last complete day", self.block(goal, days_in_phase=3, days_since_complete=1)
        )

    def test_a_goal_that_never_completed_a_day_is_given_no_gap(self):
        """A goal committed this morning has no last complete day, and the
        honest rendering of that is silence — "0 days ago" would be false and
        "never" is an accusation on somebody's first afternoon."""
        goal = self.make_goal()
        self.assertNotIn("Last complete day", self.block(goal, days_in_phase=0))

    def test_the_calendar_rule_reaches_every_phase(self):
        """Same reach as the other registers: the gap is a fact about the
        person, and WHEN_IT_IS_NOT_ABOUT_THE_WORK already forbids deciding
        somebody is struggling from one. Handing the model the gap without the
        rule would be the product supplying the evidence for the sentence it
        spent that block banning."""
        goal = self.make_goal()
        for phase in gates.PHASE_ORDER:
            with self.subTest(phase=phase):
                goal.phase = phase
                goal.save(update_fields=["phase"])
                self.assertIn(prompts.THE_CALENDAR, self.block(goal))
        self.assertIn("never a deadline", prompts.THE_CALENDAR)
        self.assertIn("Nothing was lost", prompts.THE_CALENDAR)

    def test_the_dashboard_is_sent_the_same_number_the_coach_is_given(self):
        """One measurement, two readers. The badge in the header renders what
        the server sent — it never counts days itself — so the number a builder
        reads and the number the coach is holding cannot come apart, which is
        the whole failure mode of a fact quoted by hand in two places."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        Goal.objects.filter(pk=goal.pk).update(
            phase_entered_at=timezone.now() - timedelta(days=12)
        )
        response = self.client.get(f"/api/coach/state/?date={date.today()}")
        self.assertEqual(response.data["days_in_phase"], 12)
        goal.refresh_from_db()
        self.assertEqual(
            response.data["days_in_phase"], streaks.days_in_phase(goal, date.today())
        )

    def test_the_chat_turn_carries_both_dates(self):
        """The wiring, without which every assertion above passes against a
        prompt no builder is ever served. ChatView is the only caller that
        knows the builder's own date, which is why it is the only one that
        computes either number."""
        goal = self.make_goal(phase=Phase.VALIDATION)
        today = date.today()
        Goal.objects.filter(pk=goal.pk).update(
            phase_entered_at=timezone.now() - timedelta(days=9)
        )
        CheckIn.objects.create(
            goal=goal,
            date=today - timedelta(days=4),
            phase=goal.phase,
            am_declaration="talk to Ramesh",
            pm_proof_text="notes from the talk",
        )
        seen = {}

        def capture(system, messages, **kwargs):
            seen["system"] = system
            yield "delta", "Kaam dikhao."

        with mock.patch("coach.views.llm.stream_chat", side_effect=capture):
            b"".join(
                self.client.post(
                    "/api/coach/chat/", {"content": "I disappeared, sorry"}
                ).streaming_content
            )
        self.assertIn("In this phase: 9 days", seen["system"])
        self.assertIn("Last complete day: 4 days ago", seen["system"])


class VoiceReachesEveryRoomTests(CoachTestCase):
    """The respect rule is not a chat feature.

    It was in the chat prompt, the morning's and the evening's, and missing
    from the one a builder reads while burying an idea — the moment they are
    likeliest to close the tab for good. RETIREMENT_SYSTEM's own line covers
    flattery and nothing else: nothing in it forbade sarcasm, or implying they
    had wasted anyone's time.
    """

    def test_every_prompt_a_builder_reads_carries_the_respect_rule(self):
        for name in (
            "COACH_SYSTEM",
            "DECLARATION_SYSTEM",
            "PROOF_REACTION_SYSTEM",
            "RETIREMENT_SYSTEM",
        ):
            with self.subTest(prompt=name):
                self.assertIn("{respect_rule}", getattr(prompts, name))

    def test_the_retirement_prompt_is_built_with_it(self):
        """A slot nobody fills is a slot that raises KeyError, so this also
        pins that the caller was updated with the template."""
        goal = self.make_goal()
        with mock.patch(
            "coach.views.llm.complete", return_value="Closed."
        ) as called:
            self.client.post(
                f"/api/coach/goals/{goal.id}/retire/", {"reason": "it died"}
            )
        self.assertIn(prompts.RESPECT_RULE, called.call_args.args[0])

    def test_the_state_block_reports_rather_than_orders(self):
        """_today_state is state. It used to end "demand one before anything
        else", which COACH_SYSTEM contradicts ("ask once, then let it go") and
        THINKING_MODE contradicts outright ("no demanding a declaration
        mid-thought") — so a builder thinking out loud produced a prompt that
        said both."""
        self.assertNotIn("demand", views._today_state(None).lower())

    def test_the_over_engineering_playbook_claims_only_the_phase_it_loads_in(self):
        """It used to say it governed IDEA and VALIDATION, where it is never
        loaded — and loading it there would break the curation rule that a
        playbook applying to every phase applies to none."""
        text = prompts._playbook("over-engineering")
        for phase, names in prompts.PLAYBOOKS_BY_PHASE.items():
            with self.subTest(phase=phase):
                self.assertEqual("over-engineering" in names, phase is Phase.BUILD)
        self.assertNotIn("in IDEA or\nVALIDATION, the answer is no", text)


class OpenersReachEveryPhaseTests(CoachTestCase):
    """The questions that open a phase have to survive arriving in it.

    The client gated them on a virgin chat log, so only IDEA's set could ever
    be seen: every builder who earned VALIDATION got there with a full log, and
    "What do I ask so they don't just say yes?" was written, served, and
    dropped. The gate is now "has this builder said anything in THIS phase",
    which needs the phase the server already stamps on every message.
    """

    def test_messages_carry_the_phase_they_were_said_in(self):
        goal = self.make_goal(phase=Phase.VALIDATION)
        Message.objects.create(
            goal=goal, role=Message.Role.USER, phase=goal.phase, content="hi"
        )
        said = self.client.get("/api/coach/state/").data["messages"][-1]
        self.assertEqual(said["phase"], "VALIDATION")

    def test_the_stamp_is_the_phase_of_the_day_not_of_today(self):
        """Which is the whole reason it can be trusted for this: a reply from
        two phases ago must not silence the questions for the phase the builder
        is in now."""
        goal = self.make_goal(phase=Phase.IDEA)
        Message.objects.create(
            goal=goal, role=Message.Role.USER, phase=goal.phase, content="early"
        )
        goal.phase = Phase.VALIDATION
        goal.save(update_fields=["phase"])
        said = self.client.get("/api/coach/state/").data["messages"][-1]
        self.assertEqual(said["phase"], "IDEA")

    def test_every_phase_still_has_openers_to_offer(self):
        for phase in Phase:
            with self.subTest(phase=phase):
                self.assertTrue(guidance.OPENERS[phase])
