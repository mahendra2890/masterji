"""`ChatView`: the stream, the notes kept as it goes, its query count, and what
a paid endpoint will and will not take.
"""

from datetime import date
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle

from .. import (
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
from .base import CoachTestCase

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
            [
                ("delta", "Let's check."),
                ("tool_call", {"name": "propose_phase_advance", "arguments": {}}),
            ]
        )
        self.assertIn('"advanced": false', body)
        goal.refresh_from_db()
        self.assertEqual(goal.phase, "IDEA")

    def test_chat_without_goal_rejected(self):
        response = self.client.post("/api/coach/chat/", {"content": "hello"})
        self.assertEqual(response.status_code, 400)

    def test_a_turn_that_dies_before_the_first_token_still_leaves_a_reply(self):
        """The builder's own message is saved before the stream opens, so a
        turn that saved nothing left them talking to themselves — and the
        client refetches the moment the turn ends, so the bubble they were
        watching went with it. The banner explaining why is a state and is
        gone by morning; read back tomorrow, a conversation that answered
        every message except one is Masterji ignoring them."""
        goal = self.make_goal()

        def boom(*args, **kwargs):
            raise RuntimeError("provider hung up")
            yield  # pragma: no cover — a generator that never gets that far

        with mock.patch("coach.views.llm.stream_chat", side_effect=boom):
            response = self.client.post("/api/coach/chat/", {"content": "you there?"})
            body = b"".join(response.streaming_content).decode()
        self.assertIn('"t": "error"', body)
        # SYSTEM, not COACH: it is a row so it survives the refetch, but it is
        # the app reporting a failure and Masterji never said it.
        self.assertEqual(
            list(goal.messages.values_list("role", flat=True))[-2:], ["USER", "SYSTEM"]
        )
        self.assertEqual(goal.messages.latest("id").content, guidance.STREAM_BROKE)

    def test_a_failure_notice_is_never_shown_to_the_model_as_its_own_words(self):
        """The history sent up maps every non-USER row to "assistant". A notice
        left in there is the model reading its own outage back as something it
        said — on every turn after it, for as long as it stays in the window —
        and the likeliest thing to do with that is say it again."""
        goal = self.make_goal()

        def boom(*args, **kwargs):
            raise RuntimeError("provider hung up")
            yield  # pragma: no cover — a generator that never gets that far

        with mock.patch("coach.views.llm.stream_chat", side_effect=boom):
            b"".join(
                self.client.post(
                    "/api/coach/chat/", {"content": "you there?"}
                ).streaming_content
            )
        self.assertEqual(goal.messages.filter(role=Message.Role.SYSTEM).count(), 1)

        seen = {}

        def capture(system, messages, **kwargs):
            seen["history"] = messages
            yield "delta", "Kaam dikhao."

        with mock.patch("coach.views.llm.stream_chat", side_effect=capture):
            b"".join(
                self.client.post(
                    "/api/coach/chat/", {"content": "still there?"}
                ).streaming_content
            )
        self.assertNotIn(
            guidance.STREAM_BROKE, [m["content"] for m in seen["history"]]
        )
        # The builder's own words are untouched — only the notice is dropped.
        self.assertIn("you there?", [m["content"] for m in seen["history"]])

    def test_an_answer_that_broke_off_partway_is_kept_as_far_as_it_got(self):
        """Half an answer is still his answer. Overwriting it with the failure
        line would throw away the part that did arrive — and the builder
        watched that part stream in, so losing it on refetch is the same
        disappearing act by a longer route."""
        goal = self.make_goal()

        def half(*args, **kwargs):
            yield "delta", "Start with the "
            raise RuntimeError("provider hung up")

        with mock.patch("coach.views.llm.stream_chat", side_effect=half):
            response = self.client.post("/api/coach/chat/", {"content": "which stack?"})
            b"".join(response.streaming_content)
        self.assertEqual(goal.messages.latest("id").content, "Start with the ")


class RunningNotesTests(CoachTestCase):
    """The draft kept as the conversation goes, and the one thing it is for:
    the builder never says anything twice.

    The failure it answers, from a real evening: the builder named three things
    their customer had said, in one sentence, and got back "that's one usable
    line, not three". They answered "there are three" and were told to write
    them plainly. Five round trips to recover what the first message already
    held — because nothing accumulated anywhere and every turn re-derived the
    evening from a transcript.

    So Masterji writes it down as it arrives, and the notes carry both halves:
    what he has (banked, never asked for again) and what is still owed. Notes
    are a record of what the builder said, never a verdict — the half-finished
    ones buy no proof, and the gate counts exactly what it counted before.
    """

    PART = "Spoke to Ramesh, the mess contractor. 40-50 plates wasted most nights."
    WHOLE = PART + " Tried a WhatsApp group for counts; it died in a week."
    SOME = {"who": "Ramesh, the mess contractor", "quotes": ["40-50 plates wasted"]}
    ALL = {
        "who": "Ramesh, the mess contractor",
        "quotes": [
            "40-50 plates go to waste most nights",
            "nobody replied by 18:00",
            "I'm not sharing my numbers",
        ],
        "last_action": "Tried a WhatsApp group for counts; it died in a week",
        "commitment": "Asked for an intro to the Block B contractor — he gave it",
    }
    # What SOME leaves owed, in the server's words, not the model's — two more
    # quotes counted off a list of one, and the two parts that are empty.
    GAP = (
        "2 more things they said in their own words; "
        "what they last did about this problem; "
        "the commitment you asked for, and whether you got it"
    )

    def setUp(self):
        super().setUp()
        self.goal = self.make_goal(phase=Phase.VALIDATION)
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Ramesh"})

    def draft(self, text=PART, parts=None, said="Got it. What did he last do?"):
        """One chat turn in which Masterji writes down what he has so far.
        An empty `said` is a turn he spent entirely on the tool call."""
        events = [
            (
                "tool_call",
                {
                    "name": "suggest_proof",
                    "arguments": {"text": text, **(self.SOME if parts is None else parts)},
                },
            ),
        ]
        if said:
            events.insert(0, ("delta", said))
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(events)):
            response = self.client.post("/api/coach/chat/", {"content": "talked to him"})
            b"".join(response.streaming_content)

    def system_prompt_now(self):
        """The system prompt the NEXT turn would be built with — captured off
        the real view, so this can't pass while the wiring is broken."""
        seen = []

        def capture(system, *args, **kwargs):
            seen.append(system)
            return iter([])

        with mock.patch("coach.views.llm.stream_chat", side_effect=capture):
            response = self.client.post("/api/coach/chat/", {"content": "and then?"})
            b"".join(response.streaming_content)
        return seen[0]

    # --- what he has, and what he still needs -------------------------------

    def test_a_part_of_tonights_proof_is_written_down_the_moment_it_arrives(self):
        """He used to hold every piece in his head until the bar was fully met,
        which is why nothing survived a turn."""
        self.draft()
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_offer, self.PART)
        self.assertEqual(checkin.proof_missing, self.GAP)

    def test_the_next_turn_reads_the_notes_as_given(self):
        """The whole fix in one assertion: what the conversation already
        produced arrives as state, not as something to re-derive from thirty
        messages and possibly re-derive differently."""
        self.draft()
        system = self.system_prompt_now()
        self.assertIn(self.PART, system)
        self.assertIn(self.GAP, system)
        self.assertIn("none of it may be asked for again", system)

    def test_a_fuller_draft_replaces_the_one_before_it(self):
        """Each call is the whole of what he has. Appending would double every
        fact the builder repeated, and the draft goes on their record."""
        self.draft()
        self.draft(text=self.WHOLE, parts=self.ALL)
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_offer, self.WHOLE)
        self.assertEqual(checkin.proof_missing, "")

    def test_a_finished_draft_clears_the_gap_it_used_to_have(self):
        """`missing` is read as a pair with the text. Left behind from an
        earlier call it would describe a hole in a draft that has since been
        filled — and would go on blocking the one-tap filing below."""
        self.draft()
        self.draft(text=self.WHOLE, parts=self.ALL)
        self.assertEqual(CheckIn.objects.get().proof_missing, "")
        system = self.system_prompt_now()
        self.assertIn("Nothing is missing", system)

    def test_an_evening_with_no_notes_yet_leaves_no_hole_in_the_prompt(self):
        # Not the block's heading — SPOT_PROOF names that heading when it tells
        # him where the notes come back. These two lines only exist inside the
        # block itself, so they are absent exactly when there are no notes.
        system = self.system_prompt_now()
        self.assertNotIn("every word of it is GIVEN", system)
        self.assertNotIn("Still missing before it clears the bar", system)

    def test_notes_are_dropped_when_the_task_they_belong_to_changes(self):
        """Re-declaring rewrites the day's task; a gap measured against the old
        one would have him chasing evidence for work nobody is doing."""
        self.draft()
        self.client.post("/api/coach/checkins/declare/", {"text": "talk to Priya"})
        checkin = CheckIn.objects.get()
        self.assertEqual(checkin.proof_offer, "")
        self.assertEqual(checkin.proof_missing, "")

    def test_the_gap_rides_the_state_payload(self):
        self.draft()
        response = self.client.get("/api/coach/state/")
        self.assertEqual(response.data["today"]["proof_missing"], self.GAP)

    # --- notes are not a pass ------------------------------------------------

    def test_half_finished_notes_do_not_file_themselves(self):
        """The load-bearing one. A COMPLETE draft filed unedited is accepted
        with no model call, because he decided it when he offered it. Running
        notes live in the same field and were never a decision — filing them
        verbatim must still be judged, or the gate decides nothing."""
        self.draft()
        with mock.patch(
            "coach.views.llm.complete",
            return_value='{"verdict": "push_back", "reaction": "Still no commitment."}',
        ) as called:
            response = self.client.post("/api/coach/checkins/prove/", {"text": self.PART})
        called.assert_called_once()
        self.assertEqual(response.data["checkin"]["proof_status"], "PUSHED_BACK")
        self.assertEqual(gates.accepted_proofs(self.goal), 0)

    def test_the_evening_does_not_re_open_what_the_notes_already_hold(self):
        """Same failure as asking twice in chat, one room over: every fact in
        the notes came from the builder and was taken as given at the time."""
        self.draft()
        with mock.patch(
            "coach.views.llm.complete", return_value='{"verdict": "accept", "reaction": "ok"}'
        ) as called:
            self.client.post(
                "/api/coach/checkins/prove/", {"text": self.PART + " He agreed to meet."}
            )
        system = called.call_args.args[0]
        self.assertIn("YOU KEPT RUNNING NOTES", system)
        self.assertIn(self.PART, system)
        self.assertIn(self.GAP, system)

    def test_a_finished_draft_still_goes_straight_through(self):
        """The shortcut the notes must not break: he judged the substance when
        he said nothing was missing."""
        self.draft(text=self.WHOLE, parts=self.ALL)
        with mock.patch("coach.views.llm.complete") as called:
            response = self.client.post("/api/coach/checkins/prove/", {"text": self.WHOLE})
        called.assert_not_called()
        self.assertEqual(response.data["checkin"]["proof_status"], "ACCEPTED")

    # --- the turn the builder is watching ------------------------------------

    def test_notes_with_nothing_to_pin_them_to_are_not_read_back_in_the_chat(self):
        """A FINISHED draft with no declaration is handed back — it is one move
        from being filed. Half-finished notes are a paraphrase of the
        conversation they are already having, and handing those back every turn
        until they declare is noise, not help."""
        CheckIn.objects.all().delete()
        self.draft(said="Who is he, and what did he last do?")
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertEqual(said, "Who is he, and what did he last do?")
        self.assertNotIn(self.PART, said)

    def test_a_turn_spent_entirely_on_the_notes_says_what_is_still_owed(self):
        """The tool call WAS the turn. A receipt that didn't carry the gap
        would read as a finished proof waiting to be filed, and the builder
        would be pushed back for a piece nobody told them was missing."""
        self.draft(said="")
        said = Message.objects.filter(role=Message.Role.COACH).latest("id").content
        self.assertEqual(said, guidance.NOTES_LANDED.format(missing=self.GAP))
        self.assertIn(guidance.WHERE_TO_FILE, said)

    def test_he_is_told_not_to_make_them_say_it_twice(self):
        system = prompts.build_system_prompt(
            self.goal, gates.gate_status(self.goal), 0, "state"
        )
        self.assertIn(prompts.NEVER_TWICE, system)


# --- what a paid endpoint will and won't take --------------------------------


def boom(*args, **kwargs):
    """A stream that dies before its first token. Enough for a test that only
    cares whether the turn was reached at all."""
    raise RuntimeError("provider hung up")
    yield  # pragma: no cover — a generator that never gets that far


class PaidEndpointLimitTests(CoachTestCase):
    """Every chat turn, declaration reading and proof verdict is a paid model
    call, and nothing capped their number or their size.

    Rates are overridden to one per window rather than exercised at their real
    values: the shipped numbers are generous multiples of real use, and a test
    that sent thirty turns would be asserting arithmetic DRF already owns.
    """

    def setUp(self):
        super().setUp()
        self.addCleanup(cache.clear)
        # The rates are patched on the dict the throttle actually consults, NOT
        # with override_settings(REST_FRAMEWORK=...): DRF binds
        # SimpleRateThrottle.THROTTLE_RATES to the dict it read at import, so a
        # settings override reloads api_settings into a new dict the throttle
        # never looks at again — and the test passes at the shipped rate, which
        # is to say it asserts nothing.
        rates = mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES,
            {"chat": "1/hour", "prove": "1/day", "judge": "1/day"},
        )
        rates.start()
        self.addCleanup(rates.stop)
        self.goal = self.make_goal()

    def declare(self, text="write the problem statement"):
        return self.client.post(
            "/api/coach/checkins/declare/", {"text": text, "date": str(date.today())}
        )

    def test_chat_stops_answering_past_its_rate(self):
        with mock.patch("coach.views.llm.stream_chat", side_effect=boom):
            first = self.client.post("/api/coach/chat/", {"content": "you there?"})
            b"".join(first.streaming_content)
            second = self.client.post("/api/coach/chat/", {"content": "and now?"})
        self.assertEqual(second.status_code, 429)
        # Refused in the product's register, not DRF's. A builder who hits this
        # is being told to come back, not shown a rate-limiter's arithmetic.
        self.assertNotIn("throttled", second.json()["detail"].lower())
        # And the turn never happened: a refusal that still wrote the row would
        # leave them talking to themselves, which is what STREAM_BROKE exists
        # to prevent on the other failure path.
        self.assertEqual(self.goal.messages.filter(role=Message.Role.USER).count(), 1)

    def test_prove_stops_filing_past_its_rate(self):
        self.declare()
        first = self.client.post(
            "/api/coach/checkins/prove/",
            {"text": "wrote it up", "date": str(date.today())},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/coach/checkins/prove/",
            {"text": "wrote it up again", "date": str(date.today())},
        )
        self.assertEqual(second.status_code, 429)

    def test_a_throttled_reading_leaves_the_declaration_unjudged(self):
        """The judge is the one throttle whose refusal must cost nothing: an
        UNJUDGED check-in is a complete, usable state the proof form already
        falls back for, so hitting this degrades to the documented outage path
        rather than to a builder who cannot declare."""
        checkin_id = self.declare().json()["id"]
        self.client.post(f"/api/coach/checkins/{checkin_id}/judge/")
        again = self.client.post(f"/api/coach/checkins/{checkin_id}/judge/")
        self.assertEqual(again.status_code, 429)
        self.assertEqual(
            CheckIn.objects.get(pk=checkin_id).declaration_fit,
            CheckIn.DeclarationFit.UNJUDGED,
        )
        # Declaring is not throttled with it: the morning write is free, and a
        # builder who edits their task at nine must not be locked out of it.
        self.assertEqual(self.declare("write it properly").status_code, 200)

    def test_an_essay_is_not_a_task(self):
        response = self.declare("x" * (settings.DECLARATION_MAX_CHARS + 1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_a_wall_of_text_is_not_a_proof(self):
        self.declare()
        response = self.client.post(
            "/api/coach/checkins/prove/",
            {"text": "y" * (settings.PROOF_MAX_CHARS + 1), "date": str(date.today())},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CheckIn.objects.get().proof_status, CheckIn.ProofStatus.NONE)

    def test_a_wall_of_text_is_not_a_turn(self):
        """The judge and the coach both read builder text inside a fenced block.
        An unbounded paste is a prompt-stuffing surface as well as a cost one."""
        response = self.client.post(
            "/api/coach/chat/", {"content": "z" * (settings.CHAT_MAX_CHARS + 1)}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.goal.messages.count(), 0)


class ChatTurnQueryTests(CoachTestCase):
    """The hottest authenticated path, counted rather than argued about."""

    def test_the_offer_target_is_read_once_per_turn(self):
        """`_offer_target` is `_open_checkin` plus `_carried_over` — up to
        three queries — and `ChatView.post` called it twice, with nothing
        written between the two calls that could have changed the answer."""
        self.make_goal()
        with mock.patch(
            "coach.views.llm.stream_chat", return_value=iter([("delta", "ok")])
        ):
            with mock.patch(
                "coach.views._offer_target", wraps=views._offer_target
            ) as spy:
                response = self.client.post("/api/coach/chat/", {"content": "hi"})
                b"".join(response.streaming_content)
        self.assertEqual(spy.call_count, 1)


class OneLanguageTests(CoachTestCase):
    """#268: the app is English everywhere, and says so nowhere twice.

    The defect this removal ends was not "Hinglish is missing". It was that
    `HINGLISH_RULE` reached the workshop's ~9,000-character prompt and drowned
    in the coach's ~32,000-character one, so the header switch changed the
    room before the goal and not the daily chat. Half a language is worse than
    none: a builder who presses a control and reads three English replies
    learns the app is broken, not that it is monolingual.

    These pin the two halves of "removed" that a grep cannot: nothing is left
    in the assembled prompts to select a language with, and the preference is
    no longer settable through the endpoint that used to set it.
    """

    def test_no_prompt_asks_for_a_language(self):
        goal = self.make_goal()
        prompt_texts = [
            prompts.build_system_prompt(
                goal, gates.gate_status(goal), 0, "nothing yet"
            ),
            prompts.build_workshop_prompt(
                candidates=[], turns_used=0, turns_total=views.WORKSHOP_TURNS, maximum=3
            ),
            prompts.build_reopened_prompt(
                title="Tiffin for Block C",
                phase=Phase.VALIDATION,
                days_in_phase=9,
                accepted=2,
                banked=None,
                turns_used=0,
                turns_total=views.REOPENED_TURNS,
            ),
        ]
        for text in prompt_texts:
            self.assertNotIn("Hinglish", text)

    def test_the_preference_cannot_be_set_any_more(self):
        """Not merely absent from the UI. A field the server still accepts is
        a feature with no control, which is the state this issue was about
        with the two sides swapped."""
        response = self.client.patch(
            "/api/auth/me/", {"tone": "HINGLISH"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("tone", response.data)
        self.alice.refresh_from_db()
        self.assertFalse(hasattr(self.alice, "tone"))
