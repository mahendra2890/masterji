"""`bar.py` — the counting on its own, and the same bar reaching the prompt and
the judge.
"""

from unittest import mock

from django.test import SimpleTestCase

from .. import (
    bar,
    gates,
    guidance,
    prompts,
)
from ..models import Phase
from .base import CoachTestCase

# --- how he talks ------------------------------------------------------------


class BarInThePromptTests(CoachTestCase):
    """The chat prompt carried the phase's rules and a proof counter and no
    definition of "enough" anywhere in it — so the only reply it could ever
    assemble was "not yet, give me more". What clears the bar now travels with
    the phase, read from the same module the check-in form and the gate
    refusal read from, so all three answer the same question the same way."""

    def system_for(self, phase=Phase.IDEA, **kwargs):
        goal = self.make_goal(phase=phase)
        return prompts.build_system_prompt(
            goal, gates.gate_status(goal), 0, "no declaration yet", "ENGLISH", **kwargs
        )

    def test_the_prompt_says_what_clears_the_bar(self):
        system = self.system_for()
        self.assertIn(guidance.PROOF_HINT[Phase.IDEA], system)
        for example in guidance.PROOF_EXAMPLES[Phase.IDEA]:
            self.assertIn(example, system)

    def test_the_bar_is_the_one_for_the_phase_they_are_in(self):
        system = self.system_for(Phase.VALIDATION)
        self.assertIn(guidance.PROOF_HINT[Phase.VALIDATION], system)
        self.assertNotIn(guidance.PROOF_HINT[Phase.IDEA], system)

    def test_every_phase_can_state_its_own_bar(self):
        """bar_for reads two dicts keyed by phase. A phase missing from either
        is a KeyError on the builder's first message after they unlock it."""
        for phase in Phase:
            with self.subTest(phase=phase):
                self.assertIn(guidance.PROOF_HINT[phase], prompts.bar_for(phase))


class TheJudgeSeesTheBarTests(CoachTestCase):
    """The bar reached the conversation and the morning, and not the verdict.

    PROOF_REACTION_SYSTEM got a phase NAME, the declared task and the trail —
    and no statement anywhere of what the app had told this builder would count.
    So the one call whose output gates.py counts graded against whatever the
    model already believed the word "VALIDATION" meant, while SUBSTANCE_RULE sat
    inside the same prompt telling it to judge by a bar that was not in it.

    Both directions of that are bugs, and only one of them is visible: the
    evening asks for something the afternoon said would clear it (the goalposts
    moving between two rooms of one product), or the evening banks a proof the
    written bar would not have.
    """

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.VALIDATION)

    def judge_prompt(self, text: str = "Spoke to Ramesh for 20 minutes."):
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "accept", "reaction": "counts"}',
        ) as called:
            self.client.post("/api/coach/checkins/prove/", {"text": text})
        return called.call_args.args[0]

    def test_the_evening_verdict_is_shown_what_clears_the_bar(self):
        system = self.judge_prompt()
        self.assertIn(guidance.PROOF_HINT[Phase.VALIDATION], system)
        for example in guidance.PROOF_EXAMPLES[Phase.VALIDATION]:
            self.assertIn(example, system)

    def test_the_bar_is_the_one_for_the_phase_they_are_in(self):
        system = self.judge_prompt()
        self.assertNotIn(guidance.PROOF_HINT[Phase.IDEA], system)

    def test_the_coach_and_the_judge_are_shown_one_bar(self):
        """Read out of one module by both, for the reason guidance.py's own
        docstring gives: two copies drift, and only one of them is the one
        gates.py enforces."""
        coach = prompts.build_system_prompt(
            self.goal, gates.gate_status(self.goal), 0, "state", "ENGLISH"
        )
        judge = self.judge_prompt()
        hint = guidance.PROOF_HINT[Phase.VALIDATION]
        self.assertIn(hint, coach)
        self.assertIn(hint, judge)

    def test_every_phase_can_state_its_judging_bar(self):
        """Same failure mode as bar_for: a phase missing from either dict is a
        KeyError on the first proof filed after that phase unlocks."""
        for phase in Phase:
            with self.subTest(phase=phase):
                block = prompts.judge_bar_for(phase)
                self.assertIn(guidance.PROOF_HINT[phase], block)
                for example in guidance.PROOF_EXAMPLES[phase]:
                    self.assertIn(example, block)

    def test_tonights_ask_outranks_the_phases_general_bar(self):
        """The tailored ask is about the task they actually declared. A bar
        arriving in this room must not raise it over what they were asked
        for — that is the goalposts moving, wearing a rule."""
        for phase in Phase:
            with self.subTest(phase=phase):
                self.assertIn("Two things outrank this bar", prompts.judge_bar_for(phase))

    def test_the_off_phase_rule_outranks_the_mornings_ask(self):
        """The two overrides used to be stated as a pair — "both go the same
        way" — and on an off-phase day they do not. The morning's ask IS the
        phase's bar in exactly that case, it was stated first, and it was
        stated as binding, so the judge refused work that was really done.

        They are ranked now, and the ranking has to survive in the text: the
        ask is what tonight is judged against, EXCEPT when the task was
        off-phase, where the task wins. A false refusal is the failure this
        file spent its whole history removing, and this is the one collision
        that produced one in the wild."""
        for phase in Phase:
            with self.subTest(phase=phase):
                block = prompts.judge_bar_for(phase)
                self.assertNotIn("both go the same way", block)
                self.assertIn("and above it", block)
                self.assertIn("the ask was written wrong", block)

    def test_an_off_phase_day_is_still_judged_on_its_own_task(self):
        """Declaring is never refused and an off-phase task still earns its
        proof (DeclarationTests). Handing the evening a phase bar is exactly
        how that could have been quietly taken back."""
        for phase in Phase:
            with self.subTest(phase=phase):
                # Without the leading article: the sentence now opens the
                # clause that ranks the two overrides, so it is capitalised,
                # and the property is that the promise is present rather than
                # where in a sentence it happens to sit.
                self.assertIn(
                    "off-phase day still earns its proof",
                    prompts.judge_bar_for(phase),
                )

    def test_the_bar_is_a_floor_and_not_a_checklist(self):
        """False refusals are the failure this file spent its history removing.
        A bar that reads as a form to fill in adds them back."""
        block = prompts.judge_bar_for(Phase.VALIDATION)
        self.assertIn("floor and not the ceiling", block)
        self.assertIn("not a checklist", block)

    def test_the_substance_rule_no_longer_points_at_a_prompt_it_is_not_in(self):
        """It said "the playbooks say what evidence has to CONTAIN" — inside
        the one prompt that carries no playbook. Now the bar it names is
        directly above it."""
        self.assertIn("The bar above says", prompts.SUBSTANCE_RULE)
        self.assertNotIn("The playbooks say", prompts.SUBSTANCE_RULE)


class BarTests(SimpleTestCase):
    """The counting, on its own. This is the module that exists because the
    model got a length wrong.

    A builder gave three things their customer said, in one sentence, and was
    told "that's one usable line, not three" — then asked for all of it again.
    Nothing in the server could have known better, because the only thing that
    had ever read that answer was the model reading its own paragraph back.
    suggest_proof takes the parts now, and everything below is arithmetic: a
    len(), a subtraction, and which arguments came back empty.

    No database, deliberately. If any of this needed a row it would be a
    judgement wearing a count.
    """

    def read(self, phase=Phase.VALIDATION, **arguments):
        arguments.setdefault("text", "draft")
        return bar.read(phase, arguments)

    # --- the length that started it -----------------------------------------

    def test_three_things_in_one_list_are_three_things(self):
        """The regression, stated as plainly as it can be: the count comes off
        the list, and there is no prose left for it to be wrong about."""
        draft = self.read(
            who="Ramesh",
            quotes=["40 plates wasted", "nobody replied by 18:00", "won't share numbers"],
            last_action="tried a WhatsApp group",
            commitment="intro to Block B — got it",
        )
        self.assertEqual(draft.missing, "")

    def test_a_short_list_asks_for_the_difference_not_the_whole_thing_again(self):
        """"Give me three things he said", to a builder who has given two, is
        the sentence that made them retype all three."""
        draft = self.read(who="Ramesh", quotes=["40 plates wasted", "nobody replied"])
        self.assertIn("1 more thing they said in their own words", draft.missing)

    def test_an_empty_list_asks_for_all_of_them(self):
        draft = self.read(who="Ramesh")
        self.assertIn("3 things they said in their own words", draft.missing)

    def test_a_full_list_is_never_named_as_owed(self):
        draft = self.read(quotes=["one", "two", "three"])
        self.assertNotIn("they said in their own words", draft.missing)

    # --- what the model can hand back ---------------------------------------

    def test_a_bare_string_where_a_list_belongs_is_one_entry(self):
        """Model-authored JSON, so the shape is a suggestion. Counting it as
        one is right and counting it as three would be the old bug with extra
        steps."""
        draft = self.read(quotes="40 plates go to waste most nights")
        self.assertIn("2 more things they said in their own words", draft.missing)

    def test_blanks_and_padding_do_not_count(self):
        draft = self.read(quotes=["  40 plates  ", "", "   "])
        self.assertIn("2 more things they said in their own words", draft.missing)

    def test_prose_alone_owes_the_whole_bar(self):
        """A paragraph with no parts is exactly the call the old tool took, and
        it is no longer an offer of anything: the enumeration IS the evidence
        that he counted."""
        draft = self.read()
        self.assertIn("who you spoke to", draft.missing)
        self.assertIn("3 things they said in their own words", draft.missing)

    def test_a_call_with_nothing_in_it_is_not_a_draft_owing_everything(self):
        """views drops an empty draft. Reporting the full bar as missing would
        put an empty note on the check-in with a complaint under it, for a turn
        in which the builder said nothing to bank."""
        draft = bar.read(Phase.VALIDATION, {})
        self.assertEqual(draft, bar.Draft(text="", missing=""))

    def test_parts_without_prose_still_read_back_as_a_draft(self):
        """The deterministic floor: a model that spends its answer on the
        structure must not leave the builder an empty box."""
        draft = bar.read(Phase.VALIDATION, {"who": "Ramesh", "quotes": ["40 wasted"]})
        self.assertIn("Ramesh", draft.text)
        self.assertIn("40 wasted", draft.text)

    def test_the_models_own_wording_wins_when_it_sends_one(self):
        draft = self.read(text="Spoke to Ramesh, the mess contractor.", who="Ramesh")
        self.assertEqual(draft.text, "Spoke to Ramesh, the mess contractor.")

    # --- phases whose bar is an "or" ----------------------------------------

    def test_one_part_clears_a_bar_that_asks_for_either(self):
        """BUILD takes a link OR evidence someone touched it. Demanding both
        would be a bar the playbook never set."""
        draft = bar.read(Phase.BUILD, {"text": "it's up", "link": "https://x.test"})
        self.assertEqual(draft.missing, "")

    def test_an_either_bar_with_nothing_owes_the_whole_choice(self):
        draft = bar.read(Phase.BUILD, {"text": "worked on it"})
        self.assertEqual(draft.missing, bar.BAR[Phase.BUILD].either_label)

    # --- the shape of the table ---------------------------------------------

    def test_every_phase_has_a_bar(self):
        """A phase with no entry would 500 the chat turn for whoever reached
        it, and LAUNCH is where the builders who got furthest are."""
        self.assertEqual(set(bar.BAR), set(Phase))

    def test_every_part_can_be_asked_for_and_named(self):
        for phase, entry in bar.BAR.items():
            for part in entry.parts:
                with self.subTest(phase=phase, part=part.key):
                    self.assertTrue(part.label.strip())
                    self.assertTrue(part.ask.strip())
                    # A list part needs the singular too, or the last one owed
                    # reads "1 more things they said".
                    if part.need > 1:
                        self.assertTrue(part.one_label.strip())
            if not entry.every:
                self.assertTrue(entry.either_label.strip())

    def test_the_tool_asks_for_this_phases_parts_and_nothing_else(self):
        schema = prompts.suggest_proof_tool(Phase.VALIDATION)
        properties = schema["function"]["parameters"]["properties"]
        self.assertEqual(
            set(properties),
            {"text", *(p.key for p in bar.BAR[Phase.VALIDATION].parts)},
        )
        # The count is what makes it a list, and the list is what makes the
        # model enumerate instead of judge.
        self.assertEqual(properties["quotes"]["type"], "array")
        self.assertEqual(properties["who"]["type"], "string")

    def test_the_tool_never_asks_the_model_what_is_missing(self):
        """The whole transfer, in one assertion: there is nowhere left for the
        model to assert its own completeness."""
        for phase in Phase:
            with self.subTest(phase=phase):
                schema = prompts.suggest_proof_tool(phase)
                self.assertNotIn(
                    "missing", schema["function"]["parameters"]["properties"]
                )
