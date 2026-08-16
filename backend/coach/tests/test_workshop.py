"""The room before the goal: both rooms, the guards that keep it a vestibule,
what it refines, and what survives the commit.
"""

import json
from datetime import date
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from rest_framework.throttling import ScopedRateThrottle

from .. import (
    bar,
    gates,
    guidance,
    judging,
    prompts,
    throttles,
    views,
)
from ..models import (
    CheckIn,
    Goal,
    Message,
    Phase,
    Workshop,
    WorkshopMessage,
)
from .base import CoachTestCase


class WorkshopTests(CoachTestCase):
    """The room before the goal. What is pinned here is every guard that keeps it
    a vestibule rather than a place to live: the inverted availability, the turn
    cap, the three-candidate ceiling, and the fact that nothing in it can reach
    the gate."""

    URL = "/api/coach/workshop/chat/"

    def say(self, content="I have no idea what to build", stream=None):
        """One turn, with the model stubbed. Default stream is plain words."""
        stream = stream if stream is not None else [("delta", "What did you do Tuesday?")]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(stream)):
            response = self.client.post(self.URL, {"content": content})
            # StreamingHttpResponse does the work while it is consumed, so the
            # rows this view writes do not exist until the body is read.
            body = b"".join(response.streaming_content) if response.streaming else b""
        return response, [json.loads(line) for line in body.splitlines() if line.strip()]

    def workshop(self) -> Workshop:
        return Workshop.objects.get(user=self.alice)

    # --- which room a turn lands in ------------------------------------------

    def test_the_builders_own_state_picks_the_room(self):
        """Neither room is reachable by asking for it. Before the goal the turn
        opens the room that exists because ChatView refuses without one; after
        it, the same endpoint opens that goal's one reopening — the day-four
        version of the same sentence, which used to cost a retirement."""
        response, _ = self.say()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workshop().status, Workshop.Status.OPEN)

        goal = self.make_goal()
        response, _ = self.say("I don't think this is going anywhere")
        self.assertEqual(response.status_code, 200)
        reopened = Workshop.objects.get(goal=goal)
        self.assertEqual(reopened.status, Workshop.Status.REOPENED)
        self.assertEqual(reopened.user, self.alice)

    def test_chat_and_workshop_are_never_both_shut(self):
        """Between the two endpoints there is no state a builder can be in where
        Masterji cannot speak. That was the finding the room answered, and it is
        now true in the stronger direction too: with a goal, both are open."""
        with mock.patch(
            "coach.views.llm.stream_chat", return_value=iter([("delta", "ok")])
        ):
            no_goal = self.client.post(self.URL, {"content": "hi"})
            list(no_goal.streaming_content)
            self.assertEqual(no_goal.status_code, 200)
            self.assertEqual(
                self.client.post("/api/coach/chat/", {"content": "hi"}).status_code, 400
            )

            self.make_goal()
            with_goal_room = self.client.post(self.URL, {"content": "hi"})
            list(with_goal_room.streaming_content)
            self.assertEqual(with_goal_room.status_code, 200)
            with_goal = self.client.post("/api/coach/chat/", {"content": "hi"})
            list(with_goal.streaming_content)
            self.assertEqual(with_goal.status_code, 200)

    def test_a_read_never_opens_a_room(self):
        """A workshop is a turn budget. One exists because a builder started
        talking, never because a dashboard polled."""
        self.client.get("/api/coach/state/")
        self.assertFalse(Workshop.objects.exists())
        self.assertIsNone(self.client.get("/api/coach/state/").json()["workshop"])

    def test_an_empty_turn_is_refused_before_it_costs_anything(self):
        response = self.client.post(self.URL, {"content": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Workshop.objects.exists())

    # --- the turn cap --------------------------------------------------------

    def test_the_cap_is_enforced_in_code_and_names_the_exit(self):
        for i in range(views.WORKSHOP_TURNS):
            response, _ = self.say(f"turn {i}")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(views._turns_used(self.workshop()), views.WORKSHOP_TURNS)

        refused = self.client.post(self.URL, {"content": "one more"})
        self.assertEqual(refused.status_code, 429)
        detail = refused.json()["detail"]
        self.assertIn("workshop done", detail)
        # The count comes from the constant, not from prose: a refusal that
        # spells the number is a second copy of it that goes stale the first
        # time the cap moves.
        self.assertIn(str(views.WORKSHOP_TURNS), detail)
        # A refusal that doesn't name the door is a dead end, which is the
        # failure this whole room was added to fix.
        self.assertIn("commit", detail.lower())
        # And it costs nothing: the refused turn is not a row.
        self.assertEqual(views._turns_used(self.workshop()), views.WORKSHOP_TURNS)

    def test_the_cap_counts_the_builders_turns_only(self):
        """Coach rows are not turns. Counted off USER rows so the meter cannot
        drift from the transcript the builder can see."""
        self.say(stream=[("delta", "a long answer")])
        workshop = self.workshop()
        self.assertEqual(workshop.messages.count(), 2)
        self.assertEqual(views._turns_used(workshop), 1)

    def test_the_turns_left_the_client_shows_is_the_servers_own_count(self):
        """One source for the meter, and it is the one the refusal agrees with.

        This test is named for an invariant it used to check on the wrong copy.
        It read `turns_left` off the `done` event, which subtracted from
        WORKSHOP_TURNS rather than from the room's own budget — correct here by
        coincidence, because this room's budget IS 15, and wrong in the reopened
        room, which nothing drove. The number is now sent once, by
        _workshop_payload, computed against _turn_budget.
        """
        _, events = self.say()
        payload = self.client.get("/api/coach/state/").json()["workshop"]
        self.assertEqual(payload["turns_left"], views.WORKSHOP_TURNS - 1)
        self.assertEqual(payload["turns_total"], views.WORKSHOP_TURNS)
        # And nowhere else. A second copy on the wire is what produced the bug:
        # nothing read it, so nothing could notice it disagreeing.
        self.assertEqual(events[-1], {"t": "done"})
        self.assertNotIn("sketch", [e["t"] for e in events])

    def test_the_reopened_rooms_meter_counts_its_own_budget(self):
        """The case the wire's copy got wrong and no test drove: a five-turn
        room reported fourteen left after one turn, against a server that
        refuses at four."""
        self.make_goal()
        _, events = self.say("I don't think this is going anywhere")
        payload = self.client.get("/api/coach/state/").json()["workshop"]
        self.assertEqual(payload["turns_total"], views.REOPENED_TURNS)
        self.assertEqual(payload["turns_left"], views.REOPENED_TURNS - 1)
        self.assertEqual(events[-1], {"t": "done"})

    def test_both_wires_end_the_same_way(self):
        """The two streams are meant to look alike. `done` is the sentinel each
        of them closes with, and it carries nothing on either — a payload on one
        half of a symmetry is how the two drifted apart in the first place."""
        goal = self.make_goal()
        with mock.patch(
            "coach.views.llm.stream_chat", return_value=iter([("delta", "Kaam dikhao.")])
        ):
            chat = self.client.post("/api/coach/chat/", {"content": "which stack?"})
            body = b"".join(chat.streaming_content).decode()
        chat_events = [json.loads(line) for line in body.splitlines() if line.strip()]
        goal.delete()

        _, room_events = self.say()
        self.assertEqual(chat_events[-1], {"t": "done"})
        self.assertEqual(room_events[-1], chat_events[-1])

    # --- the parking lot -----------------------------------------------------

    def park(self, *one_liners):
        return [
            ("tool_call", {"name": "park_candidate", "arguments": {"one_liner": o}})
            for o in one_liners
        ]

    def test_candidates_are_written_down_as_they_arrive(self):
        _, events = self.say(stream=self.park("hostellers miss dinner"))
        self.assertEqual(self.workshop().candidates, ["hostellers miss dinner"])
        card = [e for e in events if e["t"] == "candidates"][0]
        self.assertEqual(card["candidates"], ["hostellers miss dinner"])

    def test_the_fourth_candidate_is_refused_in_server_code(self):
        """The cap is a len() with no model in the loop — the _already_banked
        division of labour. A limit that lives only in a prompt is a limit the
        model can talk itself past."""
        self.say(stream=self.park("one", "two", "three", "four"))
        self.assertEqual(self.workshop().candidates, ["one", "two", "three"])

    def test_a_refused_park_is_said_out_loud(self):
        """The builder is watching a suggestion not appear, and silence there
        reads as the app dropping their idea."""
        self.say(stream=self.park("one", "two", "three"))
        _, events = self.say(stream=self.park("four"))
        card = [e for e in events if e["t"] == "candidates"][0]
        self.assertTrue(card["refused"])
        self.assertEqual(len(card["candidates"]), 3)

    def test_the_same_one_liner_twice_is_one_candidate(self):
        """A repeat park costs a third of the pile and buys nothing. Refused in
        server code beside the ceiling, and for the same reason: three is the
        mechanism of this room, and a copy spends a slot on an idea the builder
        already has."""
        self.say(stream=self.park("hostellers miss dinner", "hostellers miss dinner"))
        self.assertEqual(self.workshop().candidates, ["hostellers miss dinner"])
        # Across turns too — the pile is read off the row, not off the turn.
        self.say(stream=self.park("hostellers miss dinner"))
        self.assertEqual(self.workshop().candidates, ["hostellers miss dinner"])

    def test_a_repeat_is_the_same_words_not_the_same_string(self):
        """_already_banked's flattening, deliberately reused: case and spacing
        carry no more meaning in a one-liner than they do in a proof."""
        self.say(stream=self.park("Hostellers miss dinner"))
        self.say(stream=self.park("  hostellers   MISS dinner "))
        self.assertEqual(self.workshop().candidates, ["Hostellers miss dinner"])

    def test_two_ideas_that_merely_rhyme_are_two_candidates(self):
        """Exact after flattening and no looser. Near-matching here would drop
        a second idea for resembling the first, which in this room is deleting
        the builder's thinking rather than tidying it."""
        self.say(stream=self.park("hostellers miss dinner", "hostellers miss lunch"))
        self.assertEqual(
            self.workshop().candidates,
            ["hostellers miss dinner", "hostellers miss lunch"],
        )

    def test_a_repeat_park_is_not_reported_as_a_refusal(self):
        """`refused` paints "three is the limit — nothing else got parked",
        which is for a builder watching a suggestion fail to appear. A repeat
        appeared: it is on screen, in the pile."""
        self.say(stream=self.park("one"))
        _, events = self.say(stream=self.park("one"))
        self.assertEqual([e for e in events if e["t"] == "candidates"], [])

    def test_a_repeat_at_a_full_pile_is_still_silent(self):
        """Ordered before the ceiling: a pile of three that already holds this
        sentence turned nothing away, so "drop one to make room" would be the
        app arguing with what the builder can see."""
        self.say(stream=self.park("one", "two", "three"))
        _, events = self.say(stream=self.park("two"))
        self.assertEqual([e for e in events if e["t"] == "candidates"], [])
        self.assertEqual(self.workshop().candidates, ["one", "two", "three"])

    def test_the_prompt_flips_to_a_forced_choice_at_three(self):
        full = prompts.parking_state(["one", "two", "three"], Workshop.MAX_CANDIDATES)
        self.assertIn("FULL", full)
        self.assertIn("Park nothing further", full)
        room = prompts.parking_state(["one"], Workshop.MAX_CANDIDATES)
        self.assertNotIn("FULL", room)
        self.assertIn("one", room)

    def test_a_blank_candidate_is_not_a_candidate(self):
        self.say(stream=self.park("   "))
        self.assertEqual(self.workshop().candidates, [])

    # --- the suggested title -------------------------------------------------

    def test_a_suggested_goal_fills_the_box_and_commits_nothing(self):
        """The GOAL_EXAMPLES bargain: one tap from a suggestion to a database
        constraint is how a builder ends up coached on somebody else's idea."""
        _, events = self.say(
            stream=[
                (
                    "tool_call",
                    {"name": "suggest_goal", "arguments": {"title": "Tiffin for Block C"}},
                )
            ]
        )
        self.assertEqual(self.workshop().suggested_title, "Tiffin for Block C")
        self.assertFalse(Goal.objects.exists())
        card = [e for e in events if e["t"] == "candidates"][0]
        self.assertEqual(card["suggested"], "Tiffin for Block C")
        # And it survives the tab closing, which is the only reason it is stored.
        payload = self.client.get("/api/coach/state/").json()["workshop"]
        self.assertEqual(payload["suggested_title"], "Tiffin for Block C")

    # --- the rehearsal -------------------------------------------------------

    def sketch(self, **parts):
        return [("tool_call", {"name": "sketch_idea_bar", "arguments": parts})]

    def test_the_forecast_is_counted_by_the_server_not_claimed_by_the_model(self):
        """bar.py's transfer, one screen earlier: the model extracts and the
        server counts. What comes back is a len() over the arguments that
        arrived, so there is nowhere in it to round two up to four — and a part
        the model invented is not one of IDEA's, because bar.labels walks the
        bar rather than the payload."""
        self.say(
            stream=self.sketch(
                problem="hostellers miss dinner when labs run late",
                place="the Block C mess queue at 9pm",
                readiness="this idea is basically ready",
            )
        )
        self.assertEqual(self.workshop().sketch_parts, ["problem", "place"])
        # Read off the state payload, which is where the client reads it: the
        # count used to be sent a second time as a `sketch` wire event nobody
        # dispatched, and this assertion was the only thing that ever looked at
        # it.
        card = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        self.assertEqual(card["have"], 2)
        self.assertEqual(card["need"], 4)

    def test_the_rehearsal_holds_keys_and_never_the_values(self):
        """#211's answer, applied to the room one screen before the row it was
        written about. What the builder said is already the transcript; a second
        structured copy of it on the workshop would be a private diary of a
        conversation this table can already show you in full."""
        said = "the Block C mess queue at 9pm"
        self.say(stream=self.sketch(place=said))
        workshop = self.workshop()
        self.assertEqual(workshop.sketch_parts, ["place"])
        self.assertNotIn(said, json.dumps(views._workshop_payload(workshop)))

    def test_a_later_call_replaces_the_earlier_one(self):
        """The tool is told to send the whole of what it has, so a second call
        is a fuller picture and never an addition to the first. It is also how a
        part the builder walked back stops being counted."""
        self.say(stream=self.sketch(problem="p", place="q"))
        self.say(stream=self.sketch(problem="p"))
        self.assertEqual(self.workshop().sketch_parts, ["problem"])

    def test_the_forecast_survives_the_tab_and_says_what_is_still_open(self):
        """Stored for the same reason the parked candidates are: the client
        refetches when a turn ends, and a meter that lived only in the stream
        would reset itself under a builder who was reading it."""
        self.say(stream=self.sketch(problem="hostellers miss dinner"))
        sketch = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        self.assertEqual((sketch["have"], sketch["need"]), (1, 4))
        self.assertEqual(sketch["owed"], bar.owed(Phase.IDEA, ["problem"]))
        self.assertEqual(len(sketch["owed"]), 3)

    def test_four_of_four_still_owes_ideas_proof_after_the_commit(self):
        """The forecast is not a bank and cannot become one. A room that turned
        up all four parts advances nothing, seeds nothing, and dies with the
        commit — IDEA's one proof is still the builder's to file afterwards and
        still judged, against these same four parts."""
        self.say(
            stream=self.sketch(
                problem="p", place="q", why_there="r", first_conversation="s"
            )
        )
        self.assertEqual(len(self.workshop().sketch_parts), 4)
        self.assertEqual(CheckIn.objects.count(), 0)

        created = self.client.post("/api/coach/goals/", {"title": "Tiffin app"}).json()
        goal = Goal.objects.get(id=created["id"])
        self.assertEqual(goal.phase, Phase.IDEA)
        self.assertEqual(gates.accepted_proofs(goal), 0)
        advanced, _ = gates.try_advance(goal)
        self.assertFalse(advanced)
        # And the count went with the room it was drawn in.
        self.assertEqual(self.workshop().status, Workshop.Status.SPENT)

    def test_the_prompt_names_the_parts_that_are_still_open(self):
        """"You have two of four" and "the two still open are these" are
        different facts, and only the second one tells the coach what to ask
        next — the same reason parking_state says which three are parked."""
        empty = prompts.sketch_state([])
        self.assertIn("0 of 4", empty)

        some = prompts.sketch_state(["problem"])
        self.assertIn("1 of 4", some)
        self.assertIn(bar.label_for(Phase.IDEA, "place"), some)

        full = prompts.sketch_state(
            ["problem", "place", "why_there", "first_conversation"]
        )
        self.assertIn("box is right there", full)
        self.assertNotIn("Still open", full)

    # --- the room that reopens -----------------------------------------------

    def reopen(self, content="I don't believe in this any more", stream=None):
        """One turn in the reopened room. Assumes a goal is already active."""
        return self.say(content, stream=stream)

    def test_the_reopening_is_once_per_goal_and_the_database_says_so(self):
        """The meter is what makes this a room rather than a hiding place, and a
        meter you can reset by walking out and back in is not one. So the slot
        is keyed on the goal and a spent reopening still occupies it."""
        goal = self.make_goal()
        self.reopen()
        with self.assertRaises(IntegrityError):
            Workshop.objects.create(
                user=self.alice, goal=goal, status=Workshop.Status.REOPENED
            )

    def test_the_reopened_room_gets_five_turns_not_fifteen(self):
        """A different room, not the first one unlocked. Deciding whether to
        keep going is a shorter conversation than deciding what to build."""
        self.make_goal()
        for i in range(views.REOPENED_TURNS):
            response, _ = self.reopen(f"turn {i}")
            self.assertEqual(response.status_code, 200)

        refused = self.client.post(self.URL, {"content": "one more"})
        self.assertEqual(refused.status_code, 429)
        detail = refused.json()["detail"]
        self.assertIn(str(views.REOPENED_TURNS), detail)
        # The exit out of THIS room is the three doors, not the commit box —
        # there is already a goal, so "put it in the box and commit" would be
        # the wrong sentence entirely.
        self.assertIn("close it today", detail)
        self.assertNotIn("commit", detail.lower())
        payload = self.client.get("/api/coach/state/").json()["workshop"]
        self.assertEqual(payload["turns_total"], views.REOPENED_TURNS)
        self.assertEqual(payload["turns_left"], 0)
        self.assertEqual(payload["status"], Workshop.Status.REOPENED)

    def test_the_reopened_room_is_handed_no_tools_and_honours_none(self):
        """Banks nothing, in code rather than by the schema happening to make it
        unlikely. It has no pile to park into, no title to suggest for a goal
        that exists, and no IDEA bar to rehearse for a phase already committed
        to — so a call that arrives anyway is dropped."""
        self.make_goal()
        with mock.patch(
            "coach.views.llm.stream_chat", return_value=iter([("delta", "ok")])
        ) as streamed:
            self.client.post(self.URL, {"content": "hi"}).streaming_content.__iter__()
            list(self.client.post(self.URL, {"content": "hi"}).streaming_content)
        self.assertEqual(streamed.call_args.kwargs["tools"], [])

        self.reopen(
            stream=self.park("a shinier idea")
            + self.sketch(problem="p")
            + [
                (
                    "tool_call",
                    {"name": "suggest_goal", "arguments": {"title": "something else"}},
                )
            ]
        )
        workshop = Workshop.objects.get(goal__isnull=False)
        self.assertEqual(workshop.candidates, [])
        self.assertEqual(workshop.sketch_parts, [])
        self.assertEqual(workshop.suggested_title, "")

    def test_the_reopened_room_moves_nothing_it_is_asked_about(self):
        """It exists so that reconsidering costs less than burying. Which means
        it must cost nothing else either: no proof, no phase, no count."""
        goal = self.make_goal()
        state = lambda: (  # noqa: E731
            Goal.objects.get(id=goal.id).phase,
            gates.accepted_proofs(goal),
            CheckIn.objects.count(),
            # Not one row in the goal's own transcript either: this room writes
            # WorkshopMessage, and the two logs are separate on purpose.
            Message.objects.count(),
        )
        before = state()
        self.reopen("is this even worth it")
        self.reopen("I think I want to keep going")
        self.assertEqual(state(), before)

    def test_a_new_goal_gets_its_own_room(self):
        """Once per goal, not once per user: the builder who pivots is a builder
        who used the room correctly, and the next idea gets its own."""
        first = self.make_goal()
        self.reopen()
        self.client.post(f"/api/coach/goals/{first.id}/retire/", {"reason": "no"})
        self.say("starting again")
        second = self.client.post("/api/coach/goals/", {"title": "Second"}).json()
        self.reopen()
        self.assertEqual(
            Workshop.objects.filter(goal__isnull=False).count(), 2
        )
        self.assertTrue(Workshop.objects.filter(goal_id=second["id"]).exists())

    def test_the_reopened_prompt_is_the_doubt_rule_without_the_loop(self):
        """The answer to "should I keep going" was already written — it was just
        being given by a coach who had to ask what they were doing tonight in
        the same breath. One source, two readers, the record_block pattern."""
        text = prompts.build_reopened_prompt(
            title="Tiffin for Block C",
            phase=Phase.VALIDATION,
            days_in_phase=9,
            accepted=2,
            banked=[
                {
                    "date": "2026-08-10",
                    "phase": "VALIDATION",
                    "declared": "talk to Priya",
                    "proof": "she pays 40 a meal",
                }
            ],
            turns_used=1,
            turns_total=views.REOPENED_TURNS,
        )
        self.assertIn(prompts.WHEN_THEY_DOUBT_THE_IDEA, text)
        # The goal it is doubting, by name and by how far in they are.
        self.assertIn("Tiffin for Block C", text)
        self.assertIn("VALIDATION", text)
        self.assertIn("day 9", text)
        # And what they already did, so the room is not asking them to weigh it
        # up from memory.
        self.assertIn("she pays 40 a meal", text)
        # None of the loop. This is the whole point: no task, no proof tonight.
        self.assertNotIn("suggest_proof", text)
        self.assertIn("NOTHING IN THIS ROOM MOVES ANYTHING", text)
        self.assertIn(f"{views.REOPENED_TURNS - 1} of {views.REOPENED_TURNS}", text)

    # --- nothing here reaches the gate ---------------------------------------

    def test_no_checkin_or_proof_can_exist_without_a_goal(self):
        """The room banks nothing and advances nothing. Every row a proof needs
        hangs off a Goal, and there isn't one — so there is nothing here for
        gates.py to read, which is what makes the room safe to give away."""
        self.say(stream=self.park("one") + [("delta", "which of these can you ask about?")])
        self.assertEqual(CheckIn.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(WorkshopMessage.objects.count(), 2)

    def test_committing_spends_the_workshop(self):
        """The next room opens when this goal closes — which is what stops the
        vestibule being somewhere to go back to instead of forward."""
        self.say(stream=self.park("hostellers miss dinner"))
        self.client.post("/api/coach/goals/", {"title": "Tiffin app"})
        self.assertEqual(self.workshop().status, Workshop.Status.SPENT)
        self.assertIsNone(views._open_workshop(self.alice))

    def test_a_spent_workshop_does_not_come_back_with_its_turns(self):
        """A commit-retire lap buys a fresh room, and it costs an UNTESTED row on
        the archive the builder sees. What it must not buy is the old
        conversation's remaining turns."""
        for i in range(3):
            self.say(f"turn {i}")
        goal = self.client.post("/api/coach/goals/", {"title": "Tiffin app"}).json()
        self.client.post(f"/api/coach/goals/{goal['id']}/retire/", {"reason": "no"})
        self.say("starting again")
        fresh = Workshop.objects.filter(
            user=self.alice, status=Workshop.Status.OPEN
        ).get()
        self.assertEqual(views._turns_used(fresh), 1)
        self.assertEqual(Workshop.objects.count(), 2)

    def test_one_open_room_per_user(self):
        self.say()
        with self.assertRaises(IntegrityError):
            Workshop.objects.create(user=self.alice)

    def test_the_room_is_the_builders_own(self):
        """Tenancy: bob's turn never lands in alice's room."""
        self.say()
        self.client.force_authenticate(self.bob)
        self.say("mine")
        self.assertEqual(Workshop.objects.filter(user=self.bob).count(), 1)
        self.assertEqual(views._turns_used(self.workshop()), 1)

    # --- the prompt ----------------------------------------------------------

    def test_the_prompt_carries_the_playbook_and_the_counts(self):
        text = prompts.build_workshop_prompt(
            candidates=["one"],
            turns_used=13,
            turns_total=views.WORKSHOP_TURNS,
            maximum=Workshop.MAX_CANDIDATES,
        )
        # The authority is the credited corpus, not the model's pretraining —
        # the reason a choosing-an-idea playbook was written at all (#74).
        self.assertIn(prompts._playbook("choosing-an-idea"), text)
        # Derived, not typed: this asserts the prompt's meter is the server's
        # own subtraction, and a literal here would have to be edited every
        # time the cap moves — which it just did, from 15 to 20.
        self.assertIn(f"{views.WORKSHOP_TURNS - 13} of {views.WORKSHOP_TURNS} left", text)
        self.assertIn('"one"', text)

    def test_the_week_walk_is_conditioned_not_mandated(self):
        """The MODIFY on #78: ANSWER_WHAT_THEY_ASKED exists because the coach
        once opened with a move for a question nobody asked, and two of the
        three workshop openers arrive WITH ideas."""
        text = prompts.build_workshop_prompt(
            candidates=[],
            turns_used=0,
            turns_total=views.WORKSHOP_TURNS,
            maximum=Workshop.MAX_CANDIDATES,
        )
        self.assertIn("WHEN THEY ARRIVE EMPTY-HANDED", text)
        self.assertIn("gets their actual question answered first", text)
        self.assertIn("never your opening move", text)

    def test_the_room_never_asks_for_proof(self):
        text = prompts.build_workshop_prompt(
            candidates=[],
            turns_used=0,
            turns_total=views.WORKSHOP_TURNS,
            maximum=Workshop.MAX_CANDIDATES,
        )
        self.assertIn("Never ask for proof", text)

    def test_the_openers_are_the_four_actual_freezes(self):
        """Four, not a growing list of prompts: no idea at all, too many ideas,
        the fear that the idea is too obvious, and the belief that somebody has
        already settled the question. The count is asserted because the way this
        list goes wrong is by accumulating conversation-starters — the moment it
        is a menu rather than the freezes, tapping one stops meaning anything."""
        payload = self.client.get("/api/coach/state/").json()
        self.assertEqual(payload["workshop_openers"], guidance.WORKSHOP_OPENERS)
        self.assertEqual(len(guidance.WORKSHOP_OPENERS), 4)

    def test_the_competition_opener_has_a_register_waiting_for_it(self):
        """An opener with nothing behind it is a question the room improvises
        an answer to, and this is the one where improvising costs most: the
        honest answer — an existing product is evidence the problem is real,
        and only the people can say whether it is solved for them — is this
        product's own thesis and points straight at VALIDATION.

        Keyed to the opener the way the week-walk is keyed to the first one, so
        the assertion is that both halves shipped, not that a string exists."""
        self.assertIn("Someone's already built this.", guidance.WORKSHOP_OPENERS)
        text = prompts.build_workshop_prompt(
            candidates=[],
            turns_used=0,
            turns_total=views.WORKSHOP_TURNS,
            maximum=Workshop.MAX_CANDIDATES,
        )
        self.assertIn("SOMEBODY HAS ALREADY BUILT IT", text)
        # The distinction the fourth opener exists for: not a restatement of
        # "too obvious", and not answered with reassurance about market size.
        flat = text.replace("\n", " ")
        self.assertIn("the problem is REAL", flat)
        self.assertIn("evidence that it is solved for the people", flat)
        # The redirect that makes this answerable rather than consoling.
        self.assertIn("VALIDATION exists to make them have", flat)

    def test_an_outage_leaves_the_room_standing(self):
        """The turn is spent and said so, the way a broken chat turn is: a model
        that fell over must not also cost the builder the transcript."""
        with mock.patch(
            "coach.views.llm.stream_chat", side_effect=RuntimeError("down")
        ):
            response = self.client.post(self.URL, {"content": "hello"})
            events = [
                json.loads(line)
                for line in b"".join(response.streaming_content).splitlines()
                if line.strip()
            ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0]["t"], "error")
        rows = self.workshop().messages.all()
        self.assertEqual(rows[1].role, WorkshopMessage.Role.SYSTEM)
        self.assertEqual(rows[1].content, guidance.STREAM_BROKE)

    # --- a tool call is not a reason to say nothing --------------------------

    def deltas(self, events):
        return [e["text"] for e in events if e["t"] == "delta"]

    def coach_rows(self):
        return list(
            self.workshop().messages.filter(role=WorkshopMessage.Role.COACH)
        )

    def test_a_park_only_turn_speaks_and_is_recorded(self):
        """One receipt per tool, and all three of them, because the room has
        three tools and a turn that calls one used to stream nothing at all —
        the builder's own message with nothing under it and the meter down one.
        Streamed AND saved, so the refetch that ends the turn does not replace
        the bubble they just watched arrive with silence."""
        _, events = self.say(stream=self.park("hostellers miss dinner"))
        rows = self.coach_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.deltas(events), [rows[0].content])
        # The state of the pile after the turn, computed by the server.
        self.assertIn("1 of 3", rows[0].content)
        self.assertIn("room for 2 more", rows[0].content)

    def test_the_park_receipt_says_when_collecting_is_over(self):
        """At the cap what changed is not the count: the room stops collecting
        and the only move left is choosing. prompts.PARKING_FULL says that to
        the model; this is the builder's half of the same fact."""
        _, events = self.say(stream=self.park("one", "two", "three"))
        rows = self.coach_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.deltas(events), [rows[0].content])
        self.assertIn("the pile is full", rows[0].content)

    def test_a_sketch_only_turn_speaks_and_carries_what_is_still_owed(self):
        """NOTES_LANDED's reason, one room over: a count with nothing owed
        beside it reads as a finished bar, and the arithmetic is bar.owed's
        rather than anything the model asserted."""
        _, events = self.say(
            stream=self.sketch(problem="hostellers miss dinner when labs run late")
        )
        rows = self.coach_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.deltas(events), [rows[0].content])
        self.assertIn("1 of 4", rows[0].content)
        for label in bar.owed(Phase.IDEA, ["problem"]):
            self.assertIn(label, rows[0].content)

    def test_a_suggest_goal_only_turn_speaks_and_commits_nothing(self):
        """The title is in a box the builder can edit; the receipt names the
        box rather than repeating the title, and says whose the commit is."""
        _, events = self.say(
            stream=[
                (
                    "tool_call",
                    {"name": "suggest_goal", "arguments": {"title": "Tiffin for C"}},
                )
            ]
        )
        rows = self.coach_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.deltas(events), [rows[0].content])
        self.assertIn("goal box", rows[0].content)
        self.assertFalse(Goal.objects.exists())

    def test_the_receipt_never_replaces_words_the_coach_wrote(self):
        """A turn that both said something and called a tool keeps its own
        words: the receipt exists for the silence, not as a suffix on every
        tool call."""
        _, events = self.say(
            stream=[("delta", "Park that one.")] + self.park("hostellers miss dinner")
        )
        self.assertEqual(self.deltas(events), ["Park that one."])
        self.assertEqual([r.content for r in self.coach_rows()], ["Park that one."])

    def test_a_turn_that_changed_nothing_still_says_nothing(self):
        """The receipt is written out of what the server stored, so a dropped
        tool call — a repeat, here — has nothing to report. The refusal at the
        ceiling has its own voice on the `candidates` event and does not need a
        second one."""
        self.say(stream=self.park("one"))
        _, events = self.say(stream=self.park("one"))
        self.assertEqual(self.deltas(events), [])
        self.assertEqual(len(self.coach_rows()), 1)

    # --- the room costs money too --------------------------------------------

    def test_the_room_draws_from_the_same_hourly_budget_as_chat(self):
        """A turn in here is the same paid call a chat turn is, and the two
        endpoints are mutually exclusive — so a second scope would have been a
        second budget for the same spending, reachable by retiring a goal."""
        self.assertEqual(views.WorkshopChatView.throttle_scope, "chat")
        self.assertEqual(views.WorkshopChatView.throttle_classes, throttles.THROTTLES)

    def test_the_refusal_is_voiced(self):
        # Patched on the dict the throttle actually consults, and restored after
        # — see PaidEndpointLimitTests.setUp for why override_settings does not
        # reach it. An unrestored assignment here leaked 1/hour into every other
        # test in this class and failed the guard test with a 429.
        self.addCleanup(cache.clear)
        cache.clear()
        rates = mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"chat": "1/hour"}
        )
        rates.start()
        self.addCleanup(rates.stop)
        self.say()
        refused = self.client.post(self.URL, {"content": "again"})
        self.assertEqual(refused.status_code, 429)
        self.assertIn("thinking out loud", refused.json()["detail"])
        # A throttle refuses a REQUEST, never a turn already taken.
        self.assertEqual(views._turns_used(self.workshop()), 1)

    def test_a_wall_of_text_is_not_a_turn(self):
        response = self.client.post(
            self.URL, {"content": "z" * (settings.CHAT_MAX_CHARS + 1)}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Workshop.objects.exists())


class WorkshopSurvivesTheCommitTests(CoachTestCase):
    """What the room worked out, on the goal it produced.

    The complaint this answers is the product's own loudest one, reproduced one
    screen later: fifteen turns establish the problem, who has it and where
    those people are, and IDEA's bar then asks for the problem, one place they
    already are, why the builder thinks so, and how they would get one
    conversation. The same four things, of somebody who has just said them.

    Every guard that keeps this context rather than evidence is pinned here.
    Nothing in it banks, nothing advances, and IDEA's one proof is still owed
    in full — what changes is that the first morning starts from what they
    already said.
    """

    URL = "/api/coach/workshop/chat/"

    ROOM = {
        "problem": "Hostellers miss dinner when labs run late and end up on Maggi",
        "place": "the Block C mess queue at 8pm",
    }

    def turn(self, name, arguments):
        """One workshop turn whose only event is the named tool call."""
        stream = [("tool_call", {"name": name, "arguments": arguments})]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(stream)):
            response = self.client.post(self.URL, {"content": "this one, then"})
            b"".join(response.streaming_content)
        return Workshop.objects.get(user=self.alice)

    def say(self, arguments):
        """The room turning up parts of IDEA's bar. sketch_idea_bar is the one
        collector: it is maintained through the conversation, so it catches a
        room that talks an idea through and never reaches a title."""
        return self.turn("sketch_idea_bar", arguments)

    def commit(self, title="Tiffin for Block C"):
        response = self.client.post("/api/coach/goals/", {"title": title})
        self.assertEqual(response.status_code, 201)
        return Goal.objects.get(user=self.alice, title=title)

    # --- the room's answer, extracted by the model and counted by the server --

    def test_the_room_answers_ideas_bar_and_the_server_composes_it(self):
        """The suggest_proof division of labour, one screen earlier: the model
        extracts the parts, `bar.read` writes the paragraph and `bar.labels`
        says which of the four came back. `parts` is arithmetic over the
        arguments — the model is never asked to grade its own answer."""
        brief = self.say(self.ROOM).brief
        self.assertEqual(brief["parts"], ["problem", "place"])
        self.assertEqual(brief["source"], "WORKSHOP")
        self.assertIn("miss dinner when labs run late", brief["text"])
        self.assertIn("Block C mess queue", brief["text"])
        # And the two the room never reached are absent rather than invented.
        self.assertNotIn("why_there", brief["parts"])
        self.assertNotIn("first_conversation", brief["parts"])

    def test_the_meter_and_the_brief_cannot_describe_different_rooms(self):
        """One tool call writes both, which is why suggest_goal stopped
        carrying these four arguments: two tools built from the same bar entry
        meant the forecast on screen and the brief on the goal could be written
        at different moments, from different calls, and disagree."""
        workshop = self.say(self.ROOM)
        self.assertEqual(workshop.sketch_parts, workshop.brief["parts"])
        self.assertEqual(workshop.sketch_parts, ["problem", "place"])

    def test_the_tiebreak_carries_a_title_and_nothing_else(self):
        """suggest_goal fills the commit box and that is the whole of its job.
        A room that reached a title and never sketched leaves the goal exactly
        as it was before any of this existed."""
        workshop = self.turn("suggest_goal", {"title": "Tiffin for Block C"})
        self.assertEqual(workshop.suggested_title, "Tiffin for Block C")
        self.assertEqual(workshop.brief, {})
        self.assertEqual(workshop.sketch_parts, [])
        self.assertEqual(self.commit().brief, {})

    def test_an_undeclared_text_argument_cannot_become_the_paragraph(self):
        """`bar.read` prefers a `text` argument when given one, and
        suggest_goal's schema does not declare one. Filtering to the four part
        keys is what stops a model-authored aside from arriving in the coach's
        prompt as something the builder is on record as having said."""
        brief = self.say({**self.ROOM, "text": "they will definitely pay for this"})
        self.assertNotIn("definitely pay", brief.brief["text"])

    # --- the commit line -----------------------------------------------------

    def test_the_commit_carries_the_brief_and_the_pile(self):
        """Both halves move onto the goal before the room is spent, because the
        room closes behind them and a goal that reached back through it for the
        idea's own body would be reading from somewhere they have left."""
        self.say(self.ROOM)
        workshop = Workshop.objects.get(user=self.alice)
        workshop.candidates = ["hostellers miss dinner", "lab slot swaps", "cycle repair"]
        workshop.save(update_fields=["candidates"])

        goal = self.commit()
        self.assertEqual(goal.brief["source"], "WORKSHOP")
        self.assertIn("miss dinner when labs run late", goal.brief["text"])
        # Every one-liner the room parked, including the one this goal came
        # from: the commit box is free text, so no server can know which of
        # them became the title, and a wrong exclusion loses exactly the
        # thinking the field exists to keep.
        self.assertEqual(len(goal.considered), 3)
        self.assertIn("lab slot swaps", goal.considered)
        # The room is still spent by the commit it was for.
        self.assertEqual(
            Workshop.objects.get(user=self.alice).status, Workshop.Status.SPENT
        )

    def test_the_pile_is_not_the_builders_to_rewrite_afterwards(self):
        """A record of what they were choosing between, not a list they may
        edit: the workshop is closed, and rewriting its pile would rewrite the
        question this goal was the answer to."""
        self.say(self.ROOM)
        workshop = Workshop.objects.get(user=self.alice)
        workshop.candidates = ["hostellers miss dinner"]
        workshop.save(update_fields=["candidates"])
        goal = self.commit()

        response = self.client.patch(
            f"/api/coach/goals/{goal.id}/", {"considered": ["something else"]}
        )
        self.assertEqual(response.status_code, 200)
        goal.refresh_from_db()
        self.assertEqual(goal.considered, ["hostellers miss dinner"])

    def test_a_brief_typed_at_the_box_outranks_the_rooms(self):
        """They wrote it after everything the room said, so it is the later
        word and not the earlier one."""
        self.say(self.ROOM)
        response = self.client.post(
            "/api/coach/goals/",
            {"title": "Tiffin for Block C", "brief": {"text": "My own words for it."}},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        goal = Goal.objects.get(user=self.alice)
        self.assertEqual(goal.brief["source"], "BUILDER")
        self.assertEqual(goal.brief["text"], "My own words for it.")

    # --- what a sketch is worth once a verdict exists ------------------------

    def test_an_accepted_proof_replaces_the_rooms_sketch_and_not_the_builders(self):
        """The reversal worth stating. A workshop brief is a paragraph the
        coach composed before anything was judged, possibly covering two of the
        four parts; an accepted IDEA proof is the builder's own four-part
        answer and the only one the gate has ever seen. When both exist the
        second is the founding statement and the first was standing in for it.

        A brief the builder typed is the other case and keeps its ground: that
        is also their own words, and the proof does not get to overwrite what
        they said with what they filed."""
        goal = self.make_goal()
        checkin = CheckIn.objects.create(
            goal=goal,
            date=date.today(),
            phase=Phase.IDEA,
            proof_status=CheckIn.ProofStatus.ACCEPTED,
            pm_proof_text="The four-part answer as I filed it.",
            proof_parts=["problem", "place", "why_there", "first_conversation"],
        )

        goal.brief = {"text": "the room's sketch", "parts": ["problem"], "source": "WORKSHOP"}
        replaced = judging._brief_from_proof(goal, checkin)
        self.assertIsNotNone(replaced)
        self.assertEqual(replaced["source"], "PROOF")
        self.assertEqual(replaced["text"], "The four-part answer as I filed it.")

        goal.brief = {"text": "my own words", "parts": [], "source": "BUILDER"}
        self.assertIsNone(judging._brief_from_proof(goal, checkin))

    # --- the first morning ---------------------------------------------------

    def test_the_first_morning_is_told_what_the_room_did_not_cover(self):
        """#163's other half. Naming the gaps is right here and wrong for an
        accepted proof: no gate has passed on this, IDEA's proof is owed in
        full, and the parts the conversation never reached are exactly what
        that evening is for."""
        block = prompts.idea_block(
            {"text": "the sketch", "parts": ["problem", "place"], "source": "WORKSHOP"}
        )
        self.assertIn("never to be asked for again", block)
        self.assertIn("still owed in full", block)
        self.assertIn("why you think they're there", block)
        self.assertIn("how you'd get one conversation this week", block)
        # The two it did cover are not listed as owed.
        self.assertNotIn("one specific place these people already are", block)

        # A room that covered all four says so instead of listing nothing.
        whole = prompts.idea_block(
            {
                "text": "the sketch",
                "parts": ["problem", "place", "why_there", "first_conversation"],
                "source": "WORKSHOP",
            }
        )
        self.assertIn("already covers all four", whole)

        # And a brief the gate wrote is never audited back at the coach.
        proof = prompts.idea_block(
            {"text": "the filed answer", "parts": ["problem"], "source": "PROOF"}
        )
        self.assertNotIn("still owed in full", proof)
        self.assertNotIn("why you think they're there", proof)


class WorkshopRefinesTheIdeaTests(CoachTestCase):
    """The room drives at all four of IDEA's parts instead of stopping at one
    candidate — and still refuses nothing.

    Those two facts are the whole change and they pull against each other, so
    both are pinned here. The prompt is what drives; the screen is what carries
    the opinion about being unfinished (lib/gate.ts, gate.test.ts); the server
    gained no check at all, which is the assertion that must not quietly stop
    being true.
    """

    URL = "/api/coach/workshop/chat/"
    PARTS = {
        "problem": "hostellers miss dinner when labs run late",
        "place": "the Block C mess queue at 21:15",
        "why_there": "I have stood in it every Tuesday this term",
        "first_conversation": "ask the two people behind me what they ate",
    }

    def prompt(self, sketch=None, turns_used=0):
        return prompts.build_workshop_prompt(
            candidates=[],
            turns_used=turns_used,
            turns_total=views.WORKSHOP_TURNS,
            maximum=Workshop.MAX_CANDIDATES,
            sketch=sketch,
        )

    def say(self, content="I have no idea what to build", stream=None):
        stream = stream if stream is not None else [("delta", "What did you do Tuesday?")]
        with mock.patch("coach.views.llm.stream_chat", return_value=iter(stream)):
            response = self.client.post(self.URL, {"content": content})
            b"".join(response.streaming_content)
        return response

    # --- what the room is now for ---------------------------------------------

    def test_the_job_is_choosing_and_then_sharpening(self):
        """The old job statement ended at "out the door... no bar to clear in
        here", which is why a nine-turn session produced no parts at all."""
        text = self.prompt()
        job = text.split("YOUR JOB IN THIS ROOM:")[1].split("\n\n")[0]
        self.assertIn("all four", job.lower())
        self.assertNotIn("there is no bar to clear", job)

    def test_two_of_four_is_no_longer_offered_as_a_good_place_to_commit(self):
        """The sentence that made the count not matter. It said "never hold the
        door shut until all four are full: two of four is a good place to commit
        from", which told the coach to stop asking."""
        text = self.prompt()
        self.assertNotIn("two of four is a good place to commit from", text)
        self.assertIn("ALL FOUR is what you are driving at", text)

    def test_the_room_still_refuses_nothing_and_says_so_twice(self):
        """The half that must survive the reversal. A room with nothing to earn
        in it is the room a stuck builder is in, and the failure mode of gating
        it is that they leave."""
        text = self.prompt()
        self.assertIn("still never a gate", text)
        self.assertIn("you never tell them they are not ready", text)
        # And the specific thing the coach must not invent now that four is the
        # target: a number of parts required before committing.
        self.assertIn("you never say a number of parts is required", text)

    def test_an_empty_sketch_is_no_longer_something_to_keep_quiet_about(self):
        """SKETCH_EMPTY used to end "not a thing to report to them", which is the
        opposite of a room whose agenda is on the screen."""
        text = self.prompt(sketch=[])
        self.assertNotIn("not a thing to report to them", text)
        self.assertIn("the four questions are on their screen already", text)

    # --- the scaffold the screen stands up ------------------------------------

    def test_the_payload_carries_the_four_questions_from_turn_zero(self):
        """The screen shows the agenda before anything has landed, so the
        payload has to describe all four parts on an empty room — not only the
        ones still owed."""
        self.say()
        sketch = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        self.assertEqual(len(sketch["asks"]), 4)
        self.assertEqual(sketch["have"], 0)
        self.assertEqual([a["have"] for a in sketch["asks"]], [False] * 4)

    def test_the_questions_are_bars_own_wording_in_bars_own_order(self):
        """Not a second copy on the client. IDEA's four questions are read here
        first and judged against the same list on the evening they are proved,
        so one wording or they drift."""
        self.say()
        sketch = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        self.assertEqual(
            [a["key"] for a in sketch["asks"]],
            [p.key for p in bar.BAR[Phase.IDEA].parts],
        )
        self.assertEqual(
            [a["label"] for a in sketch["asks"]],
            [p.label for p in bar.BAR[Phase.IDEA].parts],
        )

    def test_parts_flip_as_the_conversation_turns_them_up(self):
        self.say(
            stream=[
                ("delta", "Good — who exactly?"),
                ("tool_call", {"name": "sketch_idea_bar", "arguments": {
                    "problem": self.PARTS["problem"], "place": self.PARTS["place"]}}),
            ]
        )
        sketch = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        landed = {a["key"]: a["have"] for a in sketch["asks"]}
        self.assertEqual(landed["problem"], True)
        self.assertEqual(landed["place"], True)
        self.assertEqual(landed["why_there"], False)
        self.assertEqual(landed["first_conversation"], False)
        self.assertEqual(sketch["have"], 2)

    def test_the_count_and_the_list_can_never_disagree(self):
        """Two shapes of one fact, both computed here. `have` is what the meter
        reads and `asks` is what the list renders, and a screen showing three
        ticks over "2 of 4" is the drift this being server-side prevents."""
        for parts in ([], ["problem"], ["problem", "place", "why_there"], list(self.PARTS)):
            payload = views._sketch_payload(parts)
            self.assertEqual(payload["have"], sum(a["have"] for a in payload["asks"]))
            self.assertEqual(
                payload["need"], len(payload["asks"]), "need is the whole bar"
            )
            self.assertEqual(
                len(payload["owed"]),
                sum(not a["have"] for a in payload["asks"]),
            )

    # --- the thing that must NOT have happened --------------------------------

    def test_committing_at_nought_of_four_is_not_refused(self):
        """The soft gate is a style on the screen. If it ever reaches the server
        this test is what says so — a builder who wants out at 0 of 4 gets the
        same goal as one who filled all four."""
        self.say()
        response = self.client.post(
            "/api/coach/goals/", {"title": "Tiffin app for hostel messes"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Goal.objects.get().title, "Tiffin app for hostel messes")

    def test_committing_at_four_of_four_takes_the_same_route(self):
        self.say(
            stream=[
                ("delta", "That's all four."),
                ("tool_call", {"name": "sketch_idea_bar", "arguments": self.PARTS}),
            ]
        )
        sketch = self.client.get("/api/coach/state/").json()["workshop"]["sketch"]
        self.assertEqual(sketch["have"], 4)
        self.assertEqual(sketch["owed"], [])
        response = self.client.post("/api/coach/goals/", {"title": "Tiffin app"})
        self.assertEqual(response.status_code, 201)

    # --- the budget ------------------------------------------------------------

    def test_the_budget_moved_and_the_room_is_still_metered(self):
        """The number is derived in WORKSHOP_TURNS' own comment and is the one
        judgement call in this change. What must stay true is that it is a
        meter: bounded, and smaller is still smaller."""
        self.assertEqual(views.WORKSHOP_TURNS, 20)
        self.assertLess(views.REOPENED_TURNS, views.WORKSHOP_TURNS)
        payload = self.client.get("/api/coach/state/").json()
        self.assertEqual(payload["workshop_turns"], views.WORKSHOP_TURNS)
