"""Masterji's API. Tenancy rule: every queryset filters by request.user,
so a foreign id 404s rather than 403s (nothing to probe). The LLM only
colors the conversation — every decision that matters (phase advancement,
proof acceptance defaults) is made in server code.

Chat streams NDJSON lines: {"t":"delta","text":...} while the coach talks,
one optional {"t":"gate",...} if a phase advance was proposed and checked,
then {"t":"done"}.
"""

import json
import secrets
from datetime import date, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from loguru import logger
from opentelemetry import trace
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import (
    bar,
    export,
    gates,
    guidance,
    links,
    llm,
    prompts,
    storage,
    streaks,
    throttles,
    weekly,
)
from .models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    LaunchCommitment,
    Message,
    Phase,
    PhaseTransition,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
)
from .serializers import (
    BRIEF_CHARS,
    ChangelogEntrySerializer,
    CheckInSerializer,
    GoalSerializer,
    MessageSerializer,
    PhaseTransitionSerializer,
    RetirementSerializer,
    WorkshopMessageSerializer,
)

tracer = trace.get_tracer(__name__)

HISTORY_LIMIT = 30
# Generous enough that a phase completed weeks ago still has its proofs
# available for the stepper drill-in, not just the current phase's recent few.
CHECKIN_HISTORY = 90

# How much of the banked record travels in a prompt (prompts.RECORD_BLOCK).
#
# Ten is more proofs than any phase asks for — three is the largest bar — so it
# covers the whole of a long VALIDATION and then some, while keeping the block a
# paragraph rather than a transcript. Newest first, so what falls off the end is
# the oldest, which is also the least likely to be re-asked for tonight.
RECORD_LIMIT = 10
# Each proof trimmed to its opening. Enough to recognise which conversation or
# which artifact it was, which is all either reader needs: the coach has to know
# not to ask again, the judge has to know a repeat when it sees one. The
# untrimmed text stays on the record, which is the thing that has to be whole.
RECORD_CHARS = 400

# Named, never pointed at. "Above" was true in no layout the product has:
# on a laptop the check-in is the LEFT column, and on a phone it is behind a
# tab you can't see while you're reading this. Both spellings sent half the
# builders looking in the wrong place on the one screen where they have no
# idea yet which half of the app does what. "Today" is the label on the card
# and on the phone tab, so it survives the breakpoint.
WHERE_TO_FILE = "Today"

# Ends on the gate, not on "talking to me records nothing on its own", which
# is the first thing a builder ever reads from him and told them their half
# of the deal was worthless before they had said a word. It was also out of
# date: he drafts the evening's proof from the conversation, so the chat is
# where the proof comes FROM even though it is not where it lands. Same order
# as the note under the reply box — what he does with it first, the gate
# second — and the promise waits on a declaration for the same reason
# _offer_target does: with no task to hang notes on, there is nothing to write
# up yet.
#
# The second sentence is the commit screen's reframe arriving a moment later,
# and it is here rather than only there because this is the first thing the
# coach himself says: "this is yours now" is the whole of what the builder had
# to go on, and it reads as a lock rather than as the start of a test. The
# reframe is one sentence and no more — the message's job past that point is the
# phase in front of them, and the record promise (an idea that dies in front of
# real people reads as tested) belongs on the screen where the hesitation
# actually happens, not stacked on top of the week's instructions.
WELCOME = (
    'Goal locked: "{title}". Rule one: one goal at a time, and this is yours '
    "now. What you picked is the problem you test first, not an idea you are "
    "stuck with. You start in IDEA — write a one-paragraph problem statement, then "
    "the route to these people: one place they already are, why you think "
    "they're there, and how you'd get one conversation this week. No names "
    "needed, and you won't message anyone until VALIDATION. Declare today's "
    f"task under {WHERE_TO_FILE} and I'll write tonight's proof out of what "
    "you tell me here — but nothing counts until you file it there."
)

# What the phase a builder just EARNED is for, in the register WELCOME uses.
#
# The asymmetry this exists to close: signing up writes the 107 words above,
# which brief IDEA completely, and earning a phase wrote five — gates.py's
# "Phase unlocked: X → Y." — for the four transitions that are the bigger
# context switch of the two. IDEA is desk work the builder was just briefed on;
# BUILD arrives with a different count, a kind requirement the earlier phases
# never had, and a nine-word PHASE_HINT that is the same for every builder
# forever.
#
# Keyed by the phase moved INTO, so IDEA has no entry and cannot: nobody
# advances into it, and WELCOME already briefs it at the only moment a goal is
# ever there.
#
# Distilled from each phase's playbooks rather than written fresh. The corpus
# already says what each phase is for, and a brief teaching something it does
# not would be a second bar arriving by the back door — one the builder reads
# once, at speed, and never sees again. What each one adds past the playbook is
# the COUNT: it is the half PHASE_HINT has no room for, and without it the
# first thing to name the new bar is a refusal.
PHASE_BRIEF = {
    Phase.VALIDATION: (
        "VALIDATION is three conversations with three different people — the "
        "same willing friend three times is one person, and it is the server "
        "counting, not me. Ask what they did the last time this happened, not "
        "whether they would use your app: people are honest about what they "
        "did and fantasists about what they'll do. Each night is one "
        "conversation — who, three things in their own words, what they last "
        "did about it, and what you asked them to give up."
    ),
    Phase.BUILD: (
        "BUILD wants two nights of evidence, and at least one has to be a real "
        "person touching the thing — two links nobody opened is an artifact, "
        "not this phase. Scope by subtraction: whatever the first ten users "
        "could live without goes on the later list, and the later list is "
        "where features go to be forgotten. If it can't be in front of "
        "somebody within a week, it isn't the small version yet."
    ),
    Phase.LAUNCH: (
        "LAUNCH is three nights in front of strangers, and one of them has to "
        "be somebody acting — posting is not somebody acting. Climb one rung a "
        "day: the people who already talked to you, the rooms they sit in, the "
        "public ponds, then the ask. A no with the reason they gave is "
        "evidence and counts; silence is not."
    ),
    Phase.TRACTION: (
        "TRACTION is the last rung — there is no phase above it, and what it "
        "asks for is one stranger who came back on their own, or who paid. Two "
        "people using it once each is not that. Recruit one at a time, "
        "over-serve the first ten embarrassingly, and watch returns rather "
        "than signups: signups are the number that flatters."
    ),
}

# Said when the builder sharpens the wording of a goal nothing has been banked
# against yet. In the transcript rather than only in the response, because the
# transcript is the memory: a title that changed with nothing said about it makes
# every message above it read as though it had always been about the new wording.
#
# Both wordings are named. WELCOME froze the original at the top of the log
# already, so nothing is being hidden — this is the line that connects the two
# without the builder having to scroll for it.
TITLE_SHARPENED = (
    'Reworded: "{before}" → "{after}". Nothing is banked against this goal yet, '
    "so nothing moved — same goal, sharper sentence. The days and the streak are "
    "where they were."
)

# And the refusal, once the record does point at the wording. Names the condition
# rather than the rule, and leaves the honest door open: the sentence about a goal
# kept out of guilt is the one the coach already uses in the personal register.
TITLE_LOCKED = (
    "There is proof on the record filed against this wording, so it stays as it "
    "is — those evenings were for this goal, and renaming it now would quietly "
    "rewrite what they were for. Keep it, or close it honestly and start the one "
    "you'd choose now."
)

# A draft Masterji wrote out of the conversation with no check-in to pin it
# to. It used to end at a server log: the builder had done the work, said it
# out loud, and watched the reply go by with no sign that any of it had been
# written up or thrown away. The draft is theirs, so it goes back to them —
# in the transcript, where declaring first costs them the declaration and not
# the writing-up as well.
#
# Said ONLY when nothing was declared today. There is a second evening with
# nothing to pin a draft to and it is the opposite situation — see
# OFFER_DAY_CLOSED.
OFFER_NO_DECLARATION = (
    "That reads like tonight's proof — but there's no task declared this "
    "morning, so I have nothing to pin it to. Declare one under "
    f"{WHERE_TO_FILE} and file this:\n\n{{offer}}"
)

# The same handed-back draft on an evening that is already finished: today's
# task was declared, proved and closed, so there is no open cycle — and the
# line above would be a flat contradiction of the card the builder is looking
# at, which reads "Declared: <task>" with a green "✓ accepted" under it. It
# said that in real use: a builder closed out a VALIDATION conversation, kept
# talking, described more work, and was told nothing had been declared this
# morning.
#
# So this one names what actually happened and offers the way on. More than
# one cycle a day is a supported thing, not a loophole (see CheckIn's
# docstring) — "Declare another task" is the button waiting on that card.
OFFER_DAY_CLOSED = (
    "That reads like another proof — but today's cycle is already declared, "
    "filed and closed, so I have nothing open to pin it to. If this is a "
    "second piece of real work, declare another task under "
    f"{WHERE_TO_FILE} and file this against it:\n\n{{offer}}"
)

# Said when Masterji spends a whole turn writing tonight's proof and adding
# nothing to it. The draft itself is deliberately NOT repeated here: it is on
# the check-in, where one tap files it, and two copies of one offer means one
# of them does nothing. This is the receipt for the other copy. Without it the
# turn was silent — the work landed on the Today card and the chat, the screen
# the builder was actually watching, showed their message with no answer under
# it. A tool call is not a reason to say nothing to someone who just spoke.
OFFER_LANDED = (
    "Wrote tonight's proof up from what you just told me — it's under "
    f"{WHERE_TO_FILE}, yours to edit before you file it."
)

# The same receipt for a turn that banked a PART of tonight's proof and said
# nothing around it. It has to carry the gap: notes that don't say what is still
# owed read as a finished proof the builder can go and file, and they'd be
# pushed back for a piece nobody told them was missing.
NOTES_LANDED = (
    "Noted what you've given me so far — it's under "
    f"{WHERE_TO_FILE}. Still need: {{missing}}"
)

# On the wire when the model drops the turn, and in the transcript too when it
# drops it before the first token. Those turns used to save no reply at all,
# and the refetch that ends every turn then replaced the bubble the builder
# was watching with a record of them talking to themselves. The banner
# carrying this is gone by tomorrow morning. The hole in the day isn't.
STREAM_BROKE = "Masterji lost the thread — try again."


def _active_goal(user) -> Goal | None:
    return Goal.objects.filter(user=user, status=Goal.Status.ACTIVE).first()


# Turns a workshop gets before the only door left is Commit.
#
# Fifteen because it is enough to walk a week for problems, park three and run a
# tiebreak, and not enough to live in. The number is the mechanism: a room before
# the goal with no meter on it is the planning-hiding-place this whole product
# refuses, just with better manners. Counted off USER rows, so it cannot drift
# from the transcript the builder can see.
WORKSHOP_TURNS = 15

# And the reopened room's, which is a different room and gets a different one.
# Five because "should I keep going" is a shorter conversation than "what should
# I build" — the goal, the phase and the record all already exist and are handed
# to it as facts. A long version of this conversation is the drift the meter is
# here to refuse, on a day the builder is already looking for a reason to stop.
REOPENED_TURNS = 5


def _open_workshop(user, create: bool = False) -> Workshop | None:
    """The room this builder can be in right now, whichever of the two it is.

    Before the goal: the OPEN room, which exists because ChatView, DeclareView
    and ProveView all refuse with "Set a goal first" — that is why a builder's
    first contact with Masterji used to be the welcome message written after the
    commit that frightened them.

    After it: the REOPENED room for that goal, once. The first room answered "I
    don't have an idea yet" and never answered "I have one and I no longer
    believe in it", which is the same sentence four days later — and the only
    way to get a room for it was to retire the goal, so burying the idea was the
    cheapest route to reconsidering it.

    `create` is off by default so reads never open a room. A workshop is a row
    with a turn budget attached, and one should exist because a builder started
    talking, not because a dashboard polled.
    """
    goal = _active_goal(user)
    if goal is not None:
        return _reopened_workshop(goal, create=create)
    workshop = Workshop.objects.filter(
        user=user, status=Workshop.Status.OPEN
    ).first()
    if workshop is not None or not create:
        return workshop
    try:
        return Workshop.objects.create(user=user)
    except IntegrityError:
        # Same reasoning as GoalsView: the check above is a read, the
        # conditional-unique constraint is the truth, and two near-simultaneous
        # first turns (a double tap, or the client's 401→refresh→replay) must
        # not 500 the one screen a builder has.
        return Workshop.objects.filter(
            user=user, status=Workshop.Status.OPEN
        ).first()


def _reopened_workshop(goal: Goal, create: bool = False) -> Workshop | None:
    """This goal's one reopening, if it has been started.

    Once per goal is a database constraint (one_workshop_per_goal), not a count
    kept here: the meter is what makes this a room rather than a hiding place,
    and a meter a builder can reset by leaving and coming back is not one. A
    spent reopening therefore still occupies the slot and this still returns it
    — the client needs the row to draw the closed door.
    """
    workshop = Workshop.objects.filter(goal=goal).first()
    if workshop is not None or not create:
        return workshop
    try:
        return Workshop.objects.create(
            user=goal.user, goal=goal, status=Workshop.Status.REOPENED
        )
    except IntegrityError:
        return Workshop.objects.filter(goal=goal).first()


def _turn_budget(workshop: Workshop) -> int:
    """How many turns this room gets, which is a fact about which room it is.

    The reopened room is smaller on purpose. Fifteen turns is what it takes to
    get from nothing to a candidate worth committing to; deciding whether to
    keep going on a goal that already exists is a shorter conversation, and a
    long one is the drift the meter exists to refuse.
    """
    return (
        REOPENED_TURNS
        if workshop.status == Workshop.Status.REOPENED
        else WORKSHOP_TURNS
    )


def _turns_used(workshop: Workshop) -> int:
    """Turns spent, as a count of the builder's own rows.

    The cap is server arithmetic over the transcript rather than a counter on
    the row: a stored integer can disagree with the messages the builder is
    looking at, and this cannot.
    """
    return workshop.messages.filter(role=WorkshopMessage.Role.USER).count()


def _sketch_payload(parts: list[str]) -> dict:
    """The pre-commit forecast: how much of IDEA's bar this room has turned up.

    Sent as the count AND the two lists, both computed here, because the screen
    that renders it must never be the place the subtraction happens — the whole
    point of the tool is that the model extracts and the server counts, and a
    client doing its own arithmetic is a second answer waiting to disagree.

    A forecast, not a gate: gates.py has never read a workshop and does not
    start here, and PROOFS_REQUIRED[IDEA] is still one proof filed after the
    commit, against these same four parts.
    """
    return {
        "parts": parts,
        "have": len(parts),
        "need": len(bar.BAR[Phase.IDEA].parts),
        "owed": bar.owed(Phase.IDEA, parts),
    }


def _workshop_payload(workshop: Workshop | None) -> dict | None:
    """The room, for the no-goal screen. None means there is no room to show —
    either a goal is active, or nothing has been said yet.

    The transcript goes whole rather than sliced, unlike every other list in
    this file: WORKSHOP_TURNS bounds it at fifteen of the builder's turns and a
    reply each, so the cap is already the limit a slice would be imposing.
    """
    if workshop is None:
        return None
    used = _turns_used(workshop)
    total = _turn_budget(workshop)
    return {
        "id": workshop.id,
        # Which of the two rooms this is. The client draws one differently from
        # the other — the pre-goal room has a pile and a forecast and the
        # reopened one has neither — and asking it to infer that from the
        # presence of candidates would make an empty first room look reopened.
        "status": workshop.status,
        "candidates": list(workshop.candidates or []),
        "max_candidates": Workshop.MAX_CANDIDATES,
        "suggested_title": workshop.suggested_title,
        "sketch": _sketch_payload(list(workshop.sketch_parts or [])),
        "turns_used": used,
        "turns_total": total,
        # Sent computed rather than left to the client, so the meter on screen
        # and the refusal from the server can never disagree about what's left.
        "turns_left": max(total - used, 0),
        "messages": WorkshopMessageSerializer(
            workshop.messages.all(), many=True
        ).data,
    }


# Said when the turns are gone. Names the exit, in the register of every other
# refusal in this file: what they have, and the one door still open.
#
# The count is interpolated, never written out in words. WORKSHOP_TURNS owns the
# number, and a refusal that spells it in prose is a second copy that goes stale
# the first time the cap moves — the same drift the gate's three number-quoting
# surfaces already cost this codebase once.
WORKSHOP_SPENT = (
    "That's the workshop done — {turns} turns, and thinking time is over. "
    "You don't need a better idea; you need one you can test. Pick the one you "
    "could ask somebody about this week, put it in the box, and commit. The "
    "first thing it asks for is one evening at your desk."
)

# The reopened room's version. Same shape and the same rule about the number,
# and a different exit, because the door out of this one is not the commit box:
# it is the three things that were always available, said once more without a
# recommendation attached.
REOPENED_SPENT = (
    "That's this room done — {turns} turns, once per goal. Nothing here changed "
    "your record and nothing was supposed to. You have the same three moves you "
    "walked in with: finish the bar in front of you, sharpen the wording, or "
    "close it today and pick again. Whichever it is, it's yours to make."
)


# A proof is on the record but the cycle is not finished with it. Both of
# these keep tonight open, for opposite reasons: PUSHED_BACK because Masterji
# read it and wants more, UNJUDGED because he never read it at all.
UNSETTLED = (CheckIn.ProofStatus.PUSHED_BACK, CheckIn.ProofStatus.UNJUDGED)

# What _react_to_proof's verdict means on the row. A verdict this doesn't know
# falls back to PUSHED_BACK at the call site: the model has answered something
# nobody planned for, and the safe reading of an unrecognised answer is the one
# that banks nothing. "accept" is the only word that opens the gate, and it has
# to arrive spelled exactly.
VERDICT_STATUS = {
    "accept": CheckIn.ProofStatus.ACCEPTED,
    "push_back": CheckIn.ProofStatus.PUSHED_BACK,
    "unjudged": CheckIn.ProofStatus.UNJUDGED,
}


def _open_checkin(goal: Goal, day: date) -> CheckIn | None:
    """The cycle still awaiting proof on `day`, if any. A pushed-back proof
    reopens the cycle — the builder gets to answer it, not start over — and so
    does one filed while the model was unreachable, which is the same offer
    made for a failure that was ours: file it again and it gets a real reading.
    Neither costs them the day, which streaks.py counts from the declaration
    and the proof without ever looking at a verdict."""
    return (
        CheckIn.objects.filter(goal=goal, date=day)
        .filter(Q(pm_proof_text="") | Q(proof_status__in=UNSETTLED))
        .order_by("-created_at")
        .first()
    )


def _carried_over(goal: Goal, day: date) -> CheckIn | None:
    """Last night's cycle, still open, when the builder is filing in the small
    hours.

    Work finished at 00:30 is the evening's, not tomorrow's: the clock rolled
    over while they were typing. Read against `day` alone it is a proof for a
    morning that never happened — ProveView refused it, the dashboard put an
    empty "Morning. One task" form where the open cycle had been, and
    streaks.py (a date holding a declaration AND a proof) lost the day. The
    product punishing precisely the evening it exists to capture, and the
    first edge a real daily user hits.

    The window is the one _client_day already reads: a client's date runs
    AHEAD of the server's UTC date from local midnight until that client's own
    UTC offset has elapsed. It shuts on its own, and once the two dates agree
    it is daylight — yesterday's unproved cycle stays unproved, because a
    missed day is a missed day.

    Be honest about how long "on its own" is: the window IS the offset, so it
    is 5h30 in IST (the users this is for) but 9h in JST and up to 14h at
    UTC+14, where a proof filed at lunchtime would still land on yesterday and
    repair the streak. Closing it tighter than the offset needs the client's
    local TIME, which it does not send today — #81 scoped the frontend out.
    Builders WEST of UTC get no carry-over at all, because their date never
    runs ahead; that is the behaviour they already had, not a new refusal.

    Reads UTC because USE_TZ is on, which is what makes timezone.now() the
    server's UTC instant rather than its wall clock. NightOwlTests pins that
    setting: with it off the comparison would silently never fire, and every
    test here would still pass.

    It cannot reach further back than one evening whatever the client claims:
    _parse_date already caps `day` at the server's date plus one, and this
    runs only when `day` is past that date, so the look-back lands on the
    server's own today and nowhere else. No proof reaches an older row through
    here (LoopholeTests).

    Only last night's DECLARED cycle, and only while `day` holds nothing of
    its own. Declaring after midnight opens the new day the ordinary way (see
    DeclareView, which reads _open_checkin directly) and that cycle is then
    the one a proof answers — the carry-over never overwrites a declaration.
    """
    if day <= timezone.now().date():
        return None
    if CheckIn.objects.filter(goal=goal, date=day).exists():
        return None
    last_night = _open_checkin(goal, day - timedelta(days=1))
    return last_night if last_night and last_night.am_declaration else None


def _on_the_hook(goal: Goal, day: date) -> CheckIn | None:
    """The cycle a proof filed now answers: the one open on `day`, or last
    night's if the clock has only just rolled over."""
    return _open_checkin(goal, day) or _carried_over(goal, day)


def _latest_checkin(goal: Goal, day: date) -> CheckIn | None:
    """What the dashboard shows for `day`: the cycle on the hook if there is
    one, else the most recently completed one."""
    return _on_the_hook(goal, day) or (
        CheckIn.objects.filter(goal=goal, date=day).order_by("-created_at").first()
    )


def _offer_target(goal: Goal, day: date) -> CheckIn | None:
    """The check-in a drafted proof can be offered against: the cycle declared
    this morning and still owing its proof.

    Without one there is nothing to offer — ProveView would refuse the filing
    anyway ("no declaration this morning — proof of what, exactly?"), and a
    draft the builder cannot act on is worse than none. A pushed-back cycle
    still counts as owing: that is exactly the evening where Masterji writing
    it up himself is worth the most.

    Reads the same cycle ProveView will file against, carry-over included, so
    a draft written at 00:30 lands on the row the dashboard is showing.
    """
    checkin = _on_the_hook(goal, day)
    return checkin if checkin and checkin.am_declaration else None


def _day_closed(goal: Goal, day: date) -> bool:
    """Whether `day` has no cycle open because it already FINISHED one.

    _offer_target answers None for two opposite evenings — nothing declared
    yet, and everything declared already proved — and they need opposite
    things said to them. Told apart here so the copy can be honest about
    which one the builder is in.

    "Closed" means declared and proved and not pushed back: a push-back
    reopens the cycle, so _open_checkin would have found it and this never
    runs. The declaration test only matters for a row that somehow has a
    proof but no task — that is nobody's second cycle, so it reads as the
    empty day it looks like.
    """
    return (
        _open_checkin(goal, day) is None
        and CheckIn.objects.filter(goal=goal, date=day)
        .exclude(am_declaration="")
        .exists()
    )


def _parse_date(value) -> date:
    """The client sends its LOCAL date — the server runs in UTC, so "today"
    is genuinely the browser's to define. But it is still client input: left
    unbounded it lets a builder mint a week of backdated check-ins in one
    sitting and speed-run the phases. Real UTC offsets span UTC-12..UTC+14,
    so anything more than a day from the server's date isn't a timezone,
    it's a claim about another day.
    """
    if not value:
        return timezone.now().date()
    day = date.fromisoformat(value)
    if abs((day - timezone.now().date()).days) > 1:
        raise ValueError("date is not within a day of the server's date")
    return day


def _parse_due_hour(value) -> int | None:
    """The hour the builder says tonight's proof will land, or None.

    On THEIR clock, like `date` above and for the same reason: an evening is
    the builder's own, and the server has no business deciding when one is.
    Nothing here compares it to a real time — no code in this project reads
    the clock against it — so it needs no window the way `_parse_date` does.
    It only has to be an hour.

    Absent, null and the empty string all mean "didn't name one", which is
    the ordinary case: the control that writes this is optional and most
    declarations will leave it alone. Anything else that is not an hour of
    the day is a bug in the caller and gets a 400 rather than a silent None,
    because a builder who named an hour and had it quietly dropped would go
    on believing their word was on the record.
    """
    if value is None or value == "":
        return None
    try:
        hour = int(value)
    except (TypeError, ValueError):
        raise ValueError("due_hour is not a number")
    if not 0 <= hour <= 23:
        raise ValueError("due_hour is not an hour of the day")
    return hour


def _client_day(request) -> date:
    """Which day the daily loop is on, for the endpoints that READ it.

    The writes have taken the client's local date since the beginning (see
    _parse_date) while the reads used the server's UTC date, and the two
    disagree for every builder whose clock is ahead of UTC. In IST a task
    declared at 01:00 was filed under today, then looked for under
    yesterday: the dashboard came back with an empty "Morning. One task"
    form and the task sitting in the record underneath it, so declaring
    read as a button that does nothing.

    Same bounds as the write path, but a bad value falls back to the
    server's date instead of 400ing — a garbled query string must not cost
    the builder their whole dashboard.
    """
    raw = request.query_params.get("date") or (
        request.data.get("date") if hasattr(request.data, "get") else None
    )
    try:
        return _parse_date(raw)
    except ValueError:
        return timezone.now().date()


# Where a launch date can be named. BUILD because that is the phase the
# playbook's own advice is about — "set the launch date before the build feels
# ready", against a phase that dies from drift in week three — and LAUNCH
# because a date that has arrived can still move, and refusing to let it move
# would turn the honest second row into a reason to say nothing.
LAUNCH_PHASES = (Phase.BUILD, Phase.LAUNCH)


def _launch_payload(goal: Goal, today: date) -> dict | None:
    """The date they named, how far off it is, and how often it has moved.

    Every number here is arithmetic over rows: the current date is the newest
    row, the slip count is one less than how many there are, and days_out is a
    subtraction. Nothing about it is a verdict, which is the point — the visible
    trail is the whole consequence, and the product never spends a refusal on it.
    """
    rows = list(goal.launch_commitments.all())
    if not rows:
        return None
    current = rows[-1]
    return {
        "date": current.date.isoformat(),
        "pond": current.pond,
        "pond_label": LaunchCommitment.Pond(current.pond).label,
        "days_out": (current.date - today).days,
        # How many times they moved it, not how many rows there are: naming a
        # date for the first time is not a slip.
        "moves": len(rows) - 1,
        "first": rows[0].date.isoformat(),
    }


def _predecessor(goal: Goal) -> tuple[str, list[dict]] | None:
    """The goal this one came out of, and what it banked — or nothing.

    Nothing when there is no parent, and nothing when the parent banked no
    accepted proofs: naming a dead idea and then reporting that it produced
    nothing is a paragraph about failure with no facts in it, on the first
    morning of the thing that replaced it.

    Reads the parent's proofs through the same _banked the live goal uses, so
    the two lists cannot disagree about what a proof was.
    """
    parent = goal.pivoted_from
    if parent is None:
        return None
    banked = _banked(parent)
    return (parent.title, banked) if banked else None


def _current_transition(goal: Goal) -> PhaseTransition | None:
    """The row that opened the phase the goal is in right now, if there is one.

    None in IDEA, always and correctly: nothing unlocked it, so there was no
    moment at which to ask what it would produce. Filtered on to_phase as well
    as taking the newest, because the two can disagree — a goal is moved back
    only by an operator in the admin, and a phase's line has to belong to the
    phase it names rather than to the last advance that happened.
    """
    return (
        goal.transitions.filter(to_phase=goal.phase).order_by("-created_at").first()
    )


def _phase_intent(goal: Goal) -> str:
    """What the builder said the current phase would produce, or ""."""
    transition = _current_transition(goal)
    return transition.intent if transition else ""


def _today_state(checkin: CheckIn | None) -> str:
    """Where the day has got to, as a fact.

    This is the state block, and state reports — it does not give orders. It
    used to end "demand one before anything else", which COACH_SYSTEM
    contradicts three paragraphs later ("ask for it first — once, and then let
    it go") and THINKING_MODE contradicts outright ("no demanding a declaration
    mid-thought"). A builder who switched to the thinking partner and opened
    with a half-formed idea was met by a prompt telling him both to leave the
    declaration alone and to demand it before anything else. What to do about
    the missing declaration is written in those two places, which know which
    mode is on; this one says only what is so.
    """
    if checkin is None or not checkin.am_declaration:
        return "no task declared yet today."
    if not checkin.pm_proof_text:
        # The hour, when they named one, and only while the proof is still
        # owed — it is a fact about tonight, and once the proof is in it has
        # been overtaken by the thing it was about. Reported as THEIR word
        # ("they said") rather than as a deadline, because it is not one:
        # nothing in this codebase refuses a proof for arriving after it, and
        # a state block that read like a cutoff would be describing a product
        # that does not exist. What it is for is that the coach can hold a
        # builder to something they chose themselves.
        if checkin.due_hour is not None:
            return (
                f'declared "{checkin.am_declaration}" — proof still owed '
                f"tonight; they said it would land by "
                f"{checkin.due_hour:02d}:00."
            )
        return f'declared "{checkin.am_declaration}" — proof still owed tonight.'
    return (
        f'declared "{checkin.am_declaration}", proof submitted '
        f"({checkin.proof_status})."
    )


def _archive(user) -> list[dict]:
    """Retired goals, newest first — the memory that makes quitting cost
    something. Read-only everywhere; nothing writes to a retired goal."""
    retirements = GoalRetirement.objects.filter(goal__user=user).select_related("goal")
    return RetirementSerializer(retirements, many=True).data


def _banked(goal: Goal, exclude: CheckIn | None = None) -> list[dict]:
    """Accepted proofs on this goal, newest first, as facts for a prompt.

    The counterpart of _archive for the goal that is still alive. `_archive`
    carries goals that ended and `notes_block` carries the evening in progress;
    between them sat every day this goal has already banked, which no prompt
    could see. The coach knew "2/3 accepted toward BUILD" and nothing about what
    the 2 were.

    Whatever phase stamped them, deliberately — the same reason
    gates.accepted_proofs_total exists. A conversation the builder had while
    still in IDEA is a conversation they had, and asking them to repeat it
    because the row carries the wrong label is the exact failure this fixes.

    `exclude` is the row being judged right now: it is not ACCEPTED yet, so it
    cannot match, but a resubmission against a PUSHED_BACK row must not be able
    to read itself back either if that ever changes.
    """
    rows = CheckIn.objects.filter(
        goal=goal, proof_status=CheckIn.ProofStatus.ACCEPTED
    ).order_by("-date", "-created_at")
    if exclude is not None and exclude.pk:
        rows = rows.exclude(pk=exclude.pk)
    return [
        {
            "date": row.date.isoformat(),
            "phase": row.phase or goal.phase,
            "declared": row.am_declaration,
            "proof": row.pm_proof_text[:RECORD_CHARS],
        }
        for row in rows[:RECORD_LIMIT]
    ]


def _same_words(text: str) -> str:
    """Proof text flattened for comparison — case and whitespace carry no
    evidence, so two submissions that differ only there are one submission."""
    return " ".join(text.lower().split())


def _already_banked(goal: Goal, checkin: CheckIn, text: str) -> CheckIn | None:
    """An accepted proof on this goal that is tonight's submission again.

    The deterministic half of the repeat problem, and the reason it needs one at
    all: a day may hold several declare→prove cycles (CheckIn's docstring — real
    work counts when it happens) and each accepted proof banks toward the phase,
    so one conversation filed three times in an evening cleared VALIDATION. The
    model could not have known; nothing it was shown reached past tonight's
    refused tries on this one row.

    Exact after flattening, and no looser. The same words twice is arithmetic and
    belongs in server code; a conversation *retold* is a judgement, and it is the
    model's with prompts.RECORD_FOR_JUDGE in front of it. Guessing at
    near-matches here would refuse genuine second work by similarity, which is a
    gate that fails in the one direction this product cannot afford.
    """
    normalised = _same_words(text)
    if not normalised:
        return None
    # The comparison is normalised text, which no database does portably, so the
    # scan happens here — over three columns rather than whole rows, since a
    # goal's whole accepted history is what has to be looked at.
    for other in (
        CheckIn.objects.filter(goal=goal, proof_status=CheckIn.ProofStatus.ACCEPTED)
        .exclude(pk=checkin.pk)
        .order_by("-date", "-created_at")
        .only("pk", "date", "pm_proof_text")
    ):
        if _same_words(other.pm_proof_text) == normalised:
            return other
    return None


def _gate_payload(goal: Goal) -> dict:
    g = gates.gate_status(goal)
    return {**g, "next_phase": g["next_phase"] and str(g["next_phase"])}


def _read_the_week_back(goal: Goal, user, today: date) -> None:
    """Write last week's digest, at most once, on the first visit of a new week.

    The trigger is the builder's own next visit rather than a clock, because
    there is no clock: `render.yaml` declares one web service and the free plan
    has no cron (see coach/weekly.py). A builder who does not come back gets no
    digest, which is right — there is nobody to read it.

    The claim is one atomic UPDATE, and that is the whole of the concurrency
    story: the dashboard refetches at the end of every turn, so two loads on the
    same Monday morning is ordinary rather than exotic, and both would otherwise
    read "not written yet" and write one each.

    Silent on failure by design — nothing about a weekly summary is worth
    500ing the dashboard for. It writes a Message and touches nothing the gate
    reads.
    """
    covered = weekly.week_start(today) - timedelta(days=weekly.DAYS)
    # Read before writing, on the busiest authenticated endpoint in the product.
    # The UPDATE below is correct on its own — it is what makes the claim atomic
    # — but it is a write statement, and six days out of seven it is guaranteed
    # to match nothing. The row is already in hand.
    if goal.last_digest_week is not None and goal.last_digest_week >= covered:
        return
    # Held before the claim moves it. This is the last week already passed over,
    # which is the floor the search below must not reach past, and the UPDATE is
    # a queryset write that leaves `goal` in hand stale rather than refreshed —
    # so reading it afterwards would work today and break the day somebody adds
    # a refresh_from_db above.
    considered = goal.last_digest_week
    claimed = Goal.objects.filter(
        Q(last_digest_week__isnull=True) | Q(last_digest_week__lt=covered),
        pk=goal.pk,
    ).update(last_digest_week=covered)
    if not claimed:
        return
    # The marker still moves to `covered` above whatever this returns, so the
    # question stays asked once a week. What changes is only which week gets
    # read back when the one just gone is empty: the last week the builder
    # actually worked, named by date so it cannot be taken for the blank one
    # their return landed after.
    week_of, summary = weekly.week_read_back(goal, today, considered)
    if not summary["filed"]:
        # Nothing was declared in that week and nothing within reach behind it,
        # so there is no week to read back. A goal committed on Sunday must not
        # be handed a report card on Monday morning saying it did nothing, and a
        # builder coming back after a month away must not walk into a wall of
        # empty weeks. The marker has moved regardless, so this is asked once a
        # week and not on every load.
        return
    Message.objects.create(
        goal=goal,
        role=Message.Role.SYSTEM,
        kind=Message.Kind.DIGEST,
        phase=goal.phase,
        content=weekly.digest(summary, user.tone, week_of),
    )


class StateView(APIView):
    """Everything the dashboard needs in one payload."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = _active_goal(request.user)
        archive = _archive(request.user)
        lifetime = streaks.lifetime_days(request.user)
        if goal is None:
            # The no-goal screen is also the after-a-retirement screen. It must
            # carry the record forward, or the app forgets the work the moment
            # the idea ends — and the onboarding copy's promise ("he'll
            # remember") becomes a bluff.
            return Response(
                {
                    "goal": None,
                    "archive": archive,
                    "lifetime_days": lifetime,
                    "tone": request.user.tone,
                    "mode": request.user.mode,
                    # The room before the goal, if they have started one. Read
                    # without creating: opening a workshop is something a
                    # builder does by talking, not something a page load does.
                    "workshop": _workshop_payload(_open_workshop(request.user)),
                    "workshop_openers": guidance.WORKSHOP_OPENERS,
                    # Sent whether or not a room exists yet, because the meter
                    # has to be readable BEFORE the first turn is spent: the
                    # cap is the mechanism, and a room that only mentions its
                    # end once you are near it is a trapdoor.
                    "workshop_turns": WORKSHOP_TURNS,
                }
            )
        today = _client_day(request)
        # Before the messages are read, so the digest is in the payload that
        # triggered it rather than appearing on the next refetch.
        _read_the_week_back(goal, request.user, today)
        checkin = _latest_checkin(goal, today)
        messages = list(goal.messages.order_by("-created_at")[:HISTORY_LIMIT])[::-1]
        return Response(
            {
                "goal": GoalSerializer(goal).data,
                # This goal's one reopening, if it has been started. Null until
                # then, and read without creating for the same reason as the
                # room before the goal: a room is a turn budget, and one should
                # exist because a builder started talking, never because a
                # dashboard polled. The door beside "close this goal" is drawn
                # from `workshop_turns` below, which is sent regardless.
                "workshop": _workshop_payload(_open_workshop(request.user)),
                "workshop_turns": REOPENED_TURNS,
                "gate": _gate_payload(goal),
                # Null until they name one, and the control reads that: there is
                # no default date and no placeholder day, because a date the app
                # picked is not a commitment anybody made.
                "launch": _launch_payload(goal, today),
                "can_set_launch": Phase(goal.phase) in LAUNCH_PHASES,
                "ponds": [
                    {"value": p.value, "label": p.label}
                    for p in LaunchCommitment.Pond
                ],
                "streak": streaks.current_streak(goal, today),
                # The run that was, next to the run that is. A builder who
                # missed two days sees a zero, and a zero on its own reads as
                # "none of it happened" at exactly the moment quitting looks
                # reasonable. This was already computed for the retirement
                # record; it just never reached the dashboard.
                "best_streak": streaks.best_streak(goal),
                # The same measurement the coach is handed this turn, sent so
                # the header badge can render it rather than count days itself.
                # Two readers of one number: a builder reading "VALIDATION 12d"
                # and a coach told "In this phase: 12 days" are looking at the
                # same subtraction, which is the only version of this that
                # cannot drift.
                "days_in_phase": streaks.days_in_phase(goal, today),
                "today": CheckInSerializer(checkin).data if checkin else None,
                "checkins": CheckInSerializer(
                    goal.checkins.prefetch_related("attempts")[:CHECKIN_HISTORY],
                    many=True,
                ).data,
                # How many days exist, next to how many travelled. The record
                # card's "Show all N" counted the rows it had been handed, so on
                # a goal past the cap it offered to show all ninety of ninety-five
                # and the other five were gone with no sign they had ever been
                # there. Same honesty as ChangelogView's `total`, and the client
                # uses the difference to go and fetch the rest.
                "checkins_total": goal.checkins.count(),
                "transitions": PhaseTransitionSerializer(
                    goal.transitions.all(), many=True
                ).data,
                "messages": MessageSerializer(messages, many=True).data,
                "phases": [str(p) for p in gates.PHASE_ORDER],
                "guidance": guidance.for_phase(Phase(goal.phase)),
                # The client hides the upload control when storage isn't
                # wired, so an unconfigured deploy offers nothing it can't do.
                "uploads_enabled": storage.is_configured(),
                "at_finish_line": gates.at_finish_line(goal),
                "archive": archive,
                "lifetime_days": lifetime,
                "tone": request.user.tone,
                "mode": request.user.mode,
            }
        )


class GoalHistoryView(APIView):
    """The full record of one of the builder's goals — including closed ones.

    Read-only and deliberately so: retired goals are write-immutable through
    every other endpoint, and a pk-addressable endpoint is exactly where that
    would leak. Scoped to request.user, so a foreign id 404s rather than 403s.

    Kept out of StateView because every retired goal's day-by-day record in
    every dashboard payload is a lot of rows to send for a panel that is
    usually closed.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        goal = get_object_or_404(Goal.objects.filter(user=request.user), pk=pk)
        retirement = GoalRetirement.objects.filter(goal=goal).first()
        return Response(
            {
                "goal": GoalSerializer(goal).data,
                "retirement": RetirementSerializer(retirement).data
                if retirement
                else None,
                # Uncapped, unlike StateView. This endpoint exists precisely
                # because the whole record is too much to send on every page
                # load — it is the one a builder opens when they went looking for
                # something, so applying the dashboard's budget here meant the
                # panel that is supposed to be the product's memory forgot the
                # first weeks of any goal that ran past three months. Bounded in
                # practice by the altitude: this product's stretch is idea to
                # first users, which is months rather than years.
                "checkins": CheckInSerializer(
                    goal.checkins.prefetch_related("attempts").all(),
                    many=True,
                ).data,
                "transitions": PhaseTransitionSerializer(
                    goal.transitions.all(), many=True
                ).data,
                "streak": streaks.best_streak(goal),
            }
        )


class ProofImageView(APIView):
    """One proof image, signed at the moment the browser asks for it.

    The redirect is the whole design. The serializers hand out this app's own
    address for an image (serializers._image_path), a plain <img src> reaches
    it with the session's own first-party cookie, and the signature is minted
    here — once, for an image somebody is actually looking at, instead of
    ninety times for a list that renders none of them.

    A 302 rather than proxying the bytes: R2 serves them, this process does
    not, and a Render web instance streaming screenshots through itself is the
    version of this that trades a latency cliff for a memory one.

    `no-store` because the Location is a credential with a five-minute life.
    Cached, it would be replayed after expiry and read as a broken image; the
    redirect is cheap and correctness is worth the round trip.

    Tenancy is the filter, not a check afterwards — a foreign id 404s here the
    same way it does on every other pk-addressable endpoint in this file.
    """

    permission_classes = [IsAuthenticated]

    # What each kind of row is called in the URL, and how to reach the user
    # who owns it. Both keys are the model's own field name for the image, so
    # nothing here has to remember which is which.
    SOURCES = {
        "checkins": (CheckIn, "goal__user", "proof_image_key"),
        "attempts": (ProofAttempt, "checkin__goal__user", "image_key"),
    }

    def get(self, request, kind: str, pk: int):
        model, owner, field = self.SOURCES[kind]
        row = get_object_or_404(model.objects.filter(**{owner: request.user}), pk=pk)
        key = getattr(row, field)
        # Storage switched off, or a row that never had an image. Not an
        # error: the daily loop predates screenshots and works without them,
        # so this is the same "there is nothing here" the serializer says with
        # an empty string.
        if not key or not storage.is_configured():
            raise Http404
        url = storage.view_url(key)
        if not url:
            # view_url swallows its own failures and returns "" so a dashboard
            # never 500s over a screenshot. Same bargain here.
            raise Http404
        response = HttpResponseRedirect(url)
        response["Cache-Control"] = "no-store"
        return response


class GoalExportView(APIView):
    """The same record as GoalHistoryView, rendered server-side as a file.

    Read-only and tenancy-scoped for the same reason its neighbour is: a
    pk-addressable endpoint that hands over a builder's whole diary is exactly
    where a missing filter would matter. A foreign id 404s.

    Rendered here rather than in the client because the file is the product's
    argument about itself and its wording should not depend on which screen the
    builder pressed. What it may and may not contain is `export`'s business —
    notably no image links, which expire.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        goal = get_object_or_404(Goal.objects.filter(user=request.user), pk=pk)
        today = _client_day(request)
        # text/markdown with a filename, so `curl` and the browser's own "save
        # as" both get something usable. The app doesn't navigate to this URL —
        # it fetches through the same client that knows how to refresh an
        # expired session — but a record the builder can only get by pressing a
        # button in one app is a smaller promise than the one being made here.
        response = HttpResponse(
            export.render(goal, today), content_type="text/markdown; charset=utf-8"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{export.filename(goal, today)}"'
        )
        return response


class GoalsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _active_goal(request.user) is not None:
            return Response(
                {"detail": "One goal at a time — that's the whole point."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = GoalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The link back, when this goal is the "same problem, new idea" one.
        # Read here rather than through the serializer because it is not the
        # client's to assert about an arbitrary row: it must be the builder's
        # own goal and it must already be closed. A bad id is dropped rather
        # than 400ing — the goal itself is what the builder is committing to,
        # and refusing the whole commit over a stale link would be the app
        # losing their sentence to protect a footnote.
        parent = None
        raw_parent = request.data.get("pivoted_from")
        if raw_parent:
            parent = (
                Goal.objects.filter(user=request.user, id=raw_parent)
                .exclude(status=Goal.Status.ACTIVE)
                .first()
            )
        try:
            goal = serializer.save(user=request.user, pivoted_from=parent)
        except IntegrityError:
            # The check above is a read; the constraint is the truth. Two
            # near-simultaneous creates (a double tap, or the API client's
            # 401→refresh→replay) would otherwise 500. Retiring makes goal
            # creation routine rather than once-ever, so this matters now.
            return Response(
                {"detail": "One goal at a time — that's the whole point."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        Message.objects.create(
            goal=goal,
            role=Message.Role.COACH,
            phase=goal.phase,
            content=WELCOME.format(title=goal.title),
        )
        # What the room worked out, moved onto the goal before the room is
        # spent. Both halves are copies rather than a foreign key: the workshop
        # is a vestibule that closes behind them, and a goal that had to reach
        # back through it for the idea's own body would be reading from a room
        # the product says they have left.
        #
        # A brief the builder typed at the commit box is never overwritten —
        # they wrote it after everything the room said, so it is the later
        # word, not the earlier one.
        # The same filter that spends it below, rather than _open_workshop:
        # that helper is guarded on there being no active goal, which stopped
        # being true one statement ago. Two readers of one row, and they must
        # not disagree about which room this commit belongs to.
        workshop = Workshop.objects.filter(
            user=request.user, status=Workshop.Status.OPEN
        ).first()
        if workshop is not None:
            carried: list[str] = []
            if workshop.brief and not goal.brief:
                goal.brief = workshop.brief
                carried.append("brief")
            if workshop.candidates:
                goal.considered = list(workshop.candidates)
                carried.append("considered")
            if carried:
                goal.save(update_fields=[*carried, "updated_at"])
                logger.info(f"Goal {goal.id} carried {carried} out of the workshop")
        # The workshop is spent by the commit it was for, whether or not the
        # title came out of it — a builder who thought in there and then typed
        # something else entirely still used the room. The next one opens when
        # this goal closes, which is what stops the vestibule from being
        # somewhere to go back to instead of forward.
        Workshop.objects.filter(
            user=request.user, status=Workshop.Status.OPEN
        ).update(status=Workshop.Status.SPENT)
        logger.info(f"Goal {goal.id} created for user {request.user.id}")
        return Response(GoalSerializer(goal).data, status=status.HTTP_201_CREATED)


class GoalUpdateView(APIView):
    """Sharpening the wording, while nothing on the record points at it.

    The pain this ends: with no update route, a mis-phrased goal cost
    retire-and-recreate, which zeroes days_active and the streak. So builders
    pre-polished the title at the commit box — which is the freeze the product is
    trying to end. "You can sharpen the wording once you're in" is now true.

    The lock is a server count, checked here rather than in gates.py, which gains
    nothing from this file: accepted_proofs_total, so a proof banked in IDEA still
    holds the wording after the goal reaches VALIDATION. Past the first accepted
    proof the record points at this sentence, and rewriting it would rewrite what
    those evenings were for.

    Not a road around the gate, and it cannot become one: the serializer holds
    `phase` and `status` read-only, so the only things a PATCH can reach are the
    title and the brief. Nor can either distort a verdict — proofs are judged
    against the declared task frozen on the check-in row, never against the
    goal's title, and never against its brief.

    The brief rides the same lock for the same reason, and the window is
    narrower than it looks. `_brief_from_proof` fills it when IDEA's proof is
    accepted, which is the same event that makes `accepted_proofs_total` true —
    so a brief written by the server is locked from the moment it exists, and
    what this endpoint can actually edit is a brief written *before* anything
    banked: by the builder here, or by the workshop at commit once #163 lands.
    That is the right shape rather than an accident of ordering — an idea is the
    builder's to sharpen while it is still unproven, and becomes a record the
    moment the gate accepts evidence for it.

    Only a title change writes a transcript row. A brief edited before anything
    is banked is the builder revising an idea nobody has been shown, and
    narrating each pass would fill the log the coach reads with drafts of a
    paragraph he is also sent whole.

    The remaining hole is deliberate: at zero proofs a builder can reword this
    into a different idea entirely. That is the same move retire-and-recreate
    already allowed, now with a transcript trail instead of a lost streak.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk: int):
        goal = get_object_or_404(
            Goal.objects.filter(user=request.user, status=Goal.Status.ACTIVE), pk=pk
        )
        if gates.accepted_proofs_total(goal):
            return Response(
                {"detail": TITLE_LOCKED}, status=status.HTTP_409_CONFLICT
            )
        before = goal.title
        serializer = GoalSerializer(goal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        goal = serializer.save()
        # Only a real change is worth a row. A save that renamed nothing —
        # the same words back, or a PATCH carrying only fields this endpoint
        # ignores — would otherwise put "Reworded: X → X" in the transcript.
        if goal.title != before:
            Message.objects.create(
                goal=goal,
                role=Message.Role.COACH,
                phase=goal.phase,
                content=TITLE_SHARPENED.format(before=before, after=goal.title),
            )
            logger.info(f"Goal {goal.id} reworded before anything was banked")
        return Response(GoalSerializer(goal).data)


class AdvanceView(APIView):
    """The deterministic gate. The demo's money shot lives here."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        goal = get_object_or_404(
            Goal.objects.filter(user=request.user, status=Goal.Status.ACTIVE), pk=pk
        )
        advanced, detail = gates.try_advance(goal)
        # try_advance may have moved the goal on; the announcement of an
        # unlock belongs to the phase it unlocked INTO, which goal.phase now is.
        #
        # So does the brief, and only on an unlock: a refusal says exactly what
        # it says today, because being told what is missing is the coaching and
        # briefing a phase the builder has not earned would talk over it.
        #
        # One row rather than two — an advance is one thing the coach said —
        # and the brief stays OUT of the response `detail`, which the dashboard
        # stamps into gateNote. That note is keyed on the gate it describes and
        # is discarded the moment the phase changes, so a brief sent through it
        # would be written to a card already throwing it away.
        brief = PHASE_BRIEF.get(Phase(goal.phase), "") if advanced else ""
        Message.objects.create(
            goal=goal,
            role=Message.Role.COACH,
            phase=goal.phase,
            content=f"{detail}\n\n{brief}" if brief else detail,
        )
        if not advanced:
            logger.info(f"Gate refused advance for goal {goal.id}: {detail}")
        return Response(
            {"advanced": advanced, "phase": goal.phase, "detail": detail},
            status=status.HTTP_200_OK if advanced else status.HTTP_409_CONFLICT,
        )


class LaunchDateView(APIView):
    """Name the day you will launch, and which room you will launch into.

    Append-only: this never updates a row, it writes another. So the record
    holds the trail rather than the latest answer, and the trail is the entire
    consequence — Beeminder's commitment device with the stake paid in record
    instead of rupees. Nothing here refuses anything: no gate reads
    LaunchCommitment, PROOFS_REQUIRED does not know it exists, and a date that
    comes and goes costs a builder nothing but the second row.

    Not before BUILD. A launch date on a goal with no artifact is a wish, and
    the one thing this must not become is a fifth thing to have declared.
    """

    permission_classes = [IsAuthenticated]
    # Three months. Not a policy about how long a launch may take — it is the
    # far end of "a date", past which the answer stops being a commitment and
    # starts being a way of not making one. The near end is today.
    MAX_DAYS_OUT = 92

    def post(self, request, pk: int):
        goal = get_object_or_404(
            Goal.objects.filter(user=request.user, status=Goal.Status.ACTIVE), pk=pk
        )
        if Phase(goal.phase) not in LAUNCH_PHASES:
            return Response(
                {
                    "detail": (
                        "A date needs something to launch. Name one once you're "
                        "building."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        # NOT _parse_date. That one bounds the value to within a day of the
        # server's date, which is exactly right for a check-in — an unbounded
        # loop date lets a builder mint a week of backdated proofs — and exactly
        # wrong here, where the whole point is a day three weeks out. The bound
        # this one needs is the opposite one: not in the past, and not so far
        # ahead that it is a way of not choosing.
        # The builder's own clock arrives as `today`, NOT as `date`. This is the
        # one endpoint whose body carries two dates, and _client_day reads
        # `date` — so it read the launch date as the builder's today, which made
        # "that day has already been" unreachable: naming yesterday moved
        # "today" to yesterday and the check passed. Found by the test for it.
        try:
            today = _parse_date(request.data.get("today"))
        except ValueError:
            today = timezone.now().date()
        try:
            when = date.fromisoformat(str(request.data.get("date") or ""))
        except ValueError:
            return Response(
                {"detail": "Give a real date — the day you'll put it in front of them."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if when < today:
            return Response(
                {"detail": "That's already been. Pick a day you can still work toward."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (when - today).days > self.MAX_DAYS_OUT:
            return Response(
                {
                    "detail": (
                        "That's far enough away to be a someday. Pick a date "
                        "inside the next three months."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        pond = str(request.data.get("pond") or "").strip().upper()
        if pond not in LaunchCommitment.Pond.values:
            return Response(
                {"detail": "Pick which room you're launching into."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        current = _launch_payload(goal, today)
        # A re-declaration of the same date and pond is not a move, and writing
        # a row for it would put a slip on the record that never happened — a
        # double tap, or a builder confirming what they already said.
        if current and current["date"] == when.isoformat() and current["pond"] == pond:
            return Response(current, status=status.HTTP_200_OK)
        LaunchCommitment.objects.create(goal=goal, date=when, pond=pond)
        logger.info(f"Goal {goal.id} named launch {when} ({pond})")
        return Response(_launch_payload(goal, today), status=status.HTTP_200_OK)


class PhaseIntentView(APIView):
    """One line, on the day a phase opens: what this phase will produce.

    Not a gate, and the shape of this view is where that is enforced. It writes
    to PhaseTransition and nothing else; gates.try_advance has never read that
    table's contents and does not start; skipping it entirely leaves the phase
    working exactly as before, which is why there is no version of this endpoint
    that has to be called before anything.

    Writes to the row that opened the CURRENT phase, so a line can only ever
    describe the phase the builder is standing in. IDEA has no such row — it was
    not unlocked by anything — and 409s rather than 404s, because the goal is
    real and it is the moment that is wrong.

    Re-settable while the phase is open. The alternative was write-once, and
    write-once on a sentence typed in the thirty seconds after an unlock buys a
    tidier record at the cost of a builder living for three weeks under a typo,
    with a coach quoting it back. It cannot be changed once the phase is behind
    them: the next phase gets its own row, and that is the whole reason this
    lives here rather than on the Goal.
    """

    permission_classes = [IsAuthenticated]
    MAX_CHARS = 280

    def post(self, request, pk: int):
        goal = get_object_or_404(
            Goal.objects.filter(user=request.user, status=Goal.Status.ACTIVE), pk=pk
        )
        transition = _current_transition(goal)
        if transition is None:
            return Response(
                {
                    "detail": (
                        "Nothing unlocked this phase yet — this is where you "
                        "started."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        intent = " ".join((request.data.get("intent") or "").split())
        if not intent:
            return Response(
                {"detail": "One line: what will this phase have produced?"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(intent) > self.MAX_CHARS:
            return Response(
                {"detail": "One line, not a plan. Say the thing it produces."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transition.intent = intent
        transition.save(update_fields=["intent"])
        logger.info(f"Goal {goal.id} named what {goal.phase} is for")
        return Response(
            PhaseTransitionSerializer(transition).data, status=status.HTTP_200_OK
        )


class RetireView(APIView):
    """Retiring a goal is always allowed. It is never silent.

    No cooling-off, no minimum age, no minimum proof count — every one of those
    is an invisible refusal, and the builder whose Tuesday conversations killed
    the idea has to be able to start the next thing on Wednesday. What it costs
    is an honest sentence on the record, and Masterji's reaction to it.

    Whether the idea was actually tested is NOT the builder's to declare: it is
    computed from proofs they had to earn (gates.reads_as).
    """

    permission_classes = [IsAuthenticated]
    outcome = GoalRetirement.Outcome.ABANDONED

    def _resolve(self, request, pk: int) -> Goal:
        # Filter by user only, then check status — so a double-tap gets a
        # voiced 409 rather than a bewildering 404. Foreign ids still 404.
        return get_object_or_404(Goal.objects.filter(user=request.user), pk=pk)

    def post(self, request, pk: int):
        goal = self._resolve(request, pk)
        if goal.status != Goal.Status.ACTIVE:
            return Response(
                {"detail": f"That one's already closed ({goal.status.lower()})."},
                status=status.HTTP_409_CONFLICT,
            )
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"detail": "Say what happened. You don't have to be proud of it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._retire(request, goal, reason)

    def _retire(self, request, goal: Goal, reason: str):
        verdict = gates.reads_as(goal, self.outcome)
        # The snapshot and the closing, together or not at all. Half of this is
        # a goal the builder cannot reopen with no last words on the record, or
        # a retirement written against a goal still counted as active — and the
        # one-active-goal constraint means the second shape blocks them from
        # starting anything else. The model call that writes the coach's words
        # is deliberately outside: it can take a minute, and a transaction held
        # open across it would be a worse bug than the one being fixed.
        with transaction.atomic():
            retirement = GoalRetirement.objects.create(
                goal=goal,
                outcome=self.outcome,
                reason=reason,
                phase_reached=goal.phase,
                accepted_proofs=gates.accepted_proofs_total(goal),
                contact_proofs=gates.contact_proofs(goal),
                days_active=streaks.days_active(goal, _client_day(request)),
                best_streak=streaks.best_streak(goal),
            )
            goal.status = (
                Goal.Status.COMPLETED
                if self.outcome == GoalRetirement.Outcome.COMPLETED
                else Goal.Status.ABANDONED
            )
            goal.save(update_fields=["status", "updated_at"])

        reaction = _react_to_retirement(retirement, verdict, request.user.tone)
        retirement.coach_reaction = reaction
        retirement.save(update_fields=["coach_reaction"])
        Message.objects.create(
            goal=goal, role=Message.Role.COACH, phase=goal.phase, content=reaction
        )
        logger.info(f"Goal {goal.id} retired as {goal.status} ({verdict})")
        return Response(
            {
                "retirement": RetirementSerializer(retirement).data,
                "reads_as": verdict,
                "reaction": reaction,
            }
        )


class CompleteView(RetireView):
    """Closing a goal you achieved, from whatever phase you were in.

    Not gated on reaching LAUNCH: goals are the builder's own words, so whether
    "10 paying customers" or "the school website is live" is done is not the
    server's call — and refusing it would just move the dead end that gating
    completion at LAUNCH was meant to remove.

    What the server keeps is the reading: gates.reads_as returns ACHIEVED only
    when there is real-world contact on the record, UNVERIFIED otherwise. So a
    completion is never blocked and never silently flattering.
    """

    outcome = GoalRetirement.Outcome.COMPLETED

    def post(self, request, pk: int):
        goal = self._resolve(request, pk)
        if goal.status != Goal.Status.ACTIVE:
            return Response(
                {"detail": f"That one's already closed ({goal.status.lower()})."},
                status=status.HTTP_409_CONFLICT,
            )
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"detail": "What did you finish, and who saw it?"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._retire(request, goal, reason)


def _react_to_retirement(retirement, verdict: str, tone: str) -> str:
    """LLM garnish over a deterministic floor, same as _react_to_proof: if the
    model is down the goal still retires, with a stock line."""
    try:
        system = prompts.RETIREMENT_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            outcome=retirement.outcome,
            verdict=verdict,
            phase=retirement.phase_reached,
            accepted_proofs=retirement.accepted_proofs,
            contact_proofs=retirement.contact_proofs,
            days=retirement.days_active,
            best_streak=retirement.best_streak,
        )
        # Not the judge model, and that is a decision rather than an oversight:
        # the verdict here was already computed by gates.reads_as before this
        # call, out of proofs the builder had to earn. All the model contributes
        # is the sentence, so it belongs with the conversation, not the verdicts.
        return llm.complete(system, retirement.reason)
    except Exception as e:
        logger.error(f"Retirement reaction failed: {e}")
        stock = (
            prompts.STOCK_SHIPPED
            if retirement.outcome == GoalRetirement.Outcome.COMPLETED
            else prompts.STOCK_RETIRED
        )
        return stock[verdict]


def _react_to_declaration(goal: Goal, text: str, tone: str) -> tuple[str, str, str]:
    """Read this morning's task: does it belong to the phase, and what would
    prove it tonight? Returns (fit, reaction, proof_ask).

    Advisory only, by design. Declaring is never refused — a builder is
    allowed to spend a day off-phase, and the gate at the end of the phase is
    what makes that cost something. Blocking here would hand the model a veto
    it must not have, and turn a coaching moment into an invisible refusal.

    Same deterministic floor as _react_to_proof: any failure logs and leaves
    the check-in UNJUDGED with no tailored ask, so the form falls back to the
    phase's static proof hint rather than showing nothing.

    Fenced like the evening's proof, and for a less obvious reason than that one:
    the `proof_ask` this produces is fed to the evening as "this morning you
    asked them to bring: …", so a declaration carrying an instruction gets to
    write tonight's bar — in a room the builder has already left.
    """
    try:
        system = prompts.DECLARATION_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
            phase=goal.phase,
            phase_rules=prompts.PHASE_RULES[Phase(goal.phase)],
            proof_hint=guidance.PROOF_HINT[Phase(goal.phase)],
            # What this builder said this phase was for, if they said anything.
            # It is what the morning's reading has never had: PHASE_HINT is the
            # same sentence for every builder forever, so "is this the work this
            # phase is for" could only ever be answered about phases in general.
            intent=prompts.declaration_intent(_phase_intent(goal)),
        )
        # The judge model: this call decides declaration_fit and writes the
        # proof_ask the evening is then graded against, so it is a verdict with
        # a second verdict downstream of it, not a turn of conversation.
        raw = llm.complete(
            system,
            prompts.fence_submission(text),
            model=settings.LLM_JUDGE_MODEL,
        )
        payload = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        fit = (
            CheckIn.DeclarationFit.OFF_PHASE
            if payload.get("fit") == "off_phase"
            else CheckIn.DeclarationFit.ON_PHASE
        )
        return (
            fit,
            str(payload.get("reaction") or ""),
            str(payload.get("proof_ask") or ""),
        )
    except Exception as e:
        logger.error(f"Declaration reaction failed: {e}")
        return CheckIn.DeclarationFit.UNJUDGED, "", ""


class DeclareView(APIView):
    """The morning write. Deliberately NOT throttled.

    It calls no model — JudgeDeclarationView is the half that does, and it
    carries the ceiling — so the only budget this could protect is the
    database's. Against that it would cost the one thing the product most wants
    to stay free: a builder sharpening the wording of today's task, which
    rewrites this same row and is encouraged everywhere else in the app. The
    length cap below is the real surface here, because this text is what tonight's
    proof gets judged against and it goes up inside the prompt.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        goal = _active_goal(request.user)
        if goal is None:
            return Response(
                {"detail": "Set a goal first."}, status=status.HTTP_400_BAD_REQUEST
            )
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"detail": "Declare an actual task."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(text) > settings.DECLARATION_MAX_CHARS:
            return Response(
                {"detail": "That's an essay, not a task — one sentence."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            day = _parse_date(request.data.get("date"))
        except ValueError:
            return Response(
                {"detail": "Bad date."}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            due_hour = _parse_due_hour(request.data.get("due_hour"))
        except ValueError:
            return Response(
                {"detail": "An hour of the day, 0 to 23."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Editing the task still on the hook updates it; declaring once the
        # day's last cycle is proved opens a new one (see CheckIn's docstring
        # — real work counts when it happens, not once per calendar day).
        checkin = _open_checkin(goal, day)
        if checkin is None:
            checkin = CheckIn.objects.create(goal=goal, date=day, phase=goal.phase)
        checkin.am_declaration = text
        # Absent clears it, rather than leaving whatever was there. The hour is
        # part of the declaration, not a separate setting with its own
        # endpoint, so re-declaring states the whole of it — and that is the
        # only way a builder who said 21:00 and can no longer make it gets to
        # take the word back. Being held to a promise you have withdrawn is
        # worse than never having made one.
        checkin.due_hour = due_hour
        # Declaring stays a pure write — it is the most repeated action in the
        # product and must not wait on a model. JudgeDeclarationView is the
        # second half. Clearing the judgement fields matters on an EDIT: a
        # verdict on wording the builder has since changed is worse than no
        # verdict, the tailored proof ask would be asking for the old task, and
        # a drafted proof would be evidence for work they are no longer doing.
        checkin.declaration_fit = CheckIn.DeclarationFit.UNJUDGED
        checkin.declaration_reaction = ""
        checkin.proof_ask = ""
        checkin.proof_offer = ""
        checkin.proof_missing = ""
        # The draft's labels go with the draft. They describe evidence for the
        # old task, and a stale subject on a row that later banks a proof would
        # credit tonight's person to work they had nothing to do with.
        checkin.subject = ""
        checkin.proof_parts = []
        checkin.save(
            update_fields=[
                "am_declaration",
                "due_hour",
                "declaration_fit",
                "declaration_reaction",
                "proof_ask",
                "proof_offer",
                "proof_missing",
                "subject",
                "proof_parts",
                "updated_at",
            ]
        )
        return Response(CheckInSerializer(checkin).data)


class JudgeDeclarationView(throttles.VoicedThrottleMixin, APIView):
    """The half of declaring that needs a model, on its own round-trip.

    Split from DeclareView so the morning write returns instantly. Everything
    here is optional by construction: an UNJUDGED check-in is a complete,
    usable state, so if the client never calls this, or it fails, or the
    builder proves their work before it lands, nothing is broken — the proof
    form falls back to the phase's static ask.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "judge"
    # The one throttle whose refusal is meant to cost nothing. The client fires
    # this outside the awaited path and swallows its failures, so a 429 lands
    # exactly where an outage lands: the check-in stays UNJUDGED, which this
    # class's own docstring already calls a complete, usable state.
    throttle_message = "Not read this time — the task is declared and the day is yours."

    def post(self, request, pk: int):
        checkin = get_object_or_404(
            CheckIn.objects.filter(goal__user=request.user), pk=pk
        )
        if not checkin.am_declaration or checkin.pm_proof_text:
            return Response(
                {"detail": "Nothing on the hook to read."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        (
            checkin.declaration_fit,
            checkin.declaration_reaction,
            checkin.proof_ask,
        ) = _react_to_declaration(
            checkin.goal, checkin.am_declaration, request.user.tone
        )
        checkin.save(
            update_fields=[
                "declaration_fit",
                "declaration_reaction",
                "proof_ask",
                "updated_at",
            ]
        )
        logger.info(
            f"Declaration {checkin.declaration_fit} for goal {checkin.goal_id} "
            f"on {checkin.date}"
        )
        return Response(CheckInSerializer(checkin).data)


class ProveView(throttles.VoicedThrottleMixin, APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "prove"
    # Per day rather than per hour, because the honest shape of this endpoint is
    # one proof an evening plus answers to a push-back — and the refusal has to
    # leave tonight's work somewhere to go, so it names the record rather than
    # the clock.
    throttle_message = (
        "That's more filings than a day holds. Whatever you have written down "
        "keeps — bring it back to tonight's box later."
    )

    def post(self, request):
        goal = _active_goal(request.user)
        if goal is None:
            return Response(
                {"detail": "Set a goal first."}, status=status.HTTP_400_BAD_REQUEST
            )
        text = (request.data.get("text") or "").strip()
        if not text:
            return Response(
                {"detail": "Proof means something to show."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(text) > settings.PROOF_MAX_CHARS:
            return Response(
                {"detail": "That's a lot to read. The evidence, not everything around it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            day = _parse_date(request.data.get("date"))
        except ValueError:
            return Response(
                {"detail": "Bad date."}, status=status.HTTP_400_BAD_REQUEST
            )
        checkin = _on_the_hook(goal, day)
        if checkin is None or not checkin.am_declaration:
            return Response(
                {"detail": "No declaration this morning — proof of what, exactly?"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        upload = request.FILES.get("image")
        image_bytes = content_type = None
        if upload is not None:
            content_type = (upload.content_type or "").lower()
            if content_type not in settings.PROOF_IMAGE_TYPES:
                return Response(
                    {"detail": "Screenshots only — PNG, JPEG or WebP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if upload.size > settings.PROOF_IMAGE_MAX_BYTES:
                mb = settings.PROOF_IMAGE_MAX_BYTES // (1024 * 1024)
                return Response(
                    {"detail": f"That image is over {mb}MB. Crop it and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            image_bytes = upload.read()

        # A resubmission is the builder answering a push-back. Move the failed
        # try onto the trail before overwriting: the record is the product,
        # and clearing the image key here is what stops an accepted proof
        # from wearing the screenshot of the try that was rejected.
        #
        # PUSHED_BACK only, and deliberately not UNSETTLED. An UNJUDGED try was
        # never refused — nobody read it — so filing it onto the trail would
        # invent a refusal, and prompts.prior_tries would then hand the model a
        # push-back it never wrote, with an empty reaction under it, as
        # something to judge the next submission against.
        # Built here, where the old values are still on the row, and saved
        # below in the same transaction as the row that replaces them. Written
        # this way round on purpose: creating it here and saving the check-in
        # after the verdict leaves a gap of one model call — up to a minute —
        # in which a failure archives the try and never overwrites it, so the
        # builder's evening reads as still pushed back with the old text under
        # it and the trail carries a duplicate. Wrapping the whole stretch
        # instead would hold a database transaction open across that same
        # model call, twelve threads deep, which is the worse trade.
        archived_try = None
        if checkin.pm_proof_text and checkin.proof_status == CheckIn.ProofStatus.PUSHED_BACK:
            archived_try = ProofAttempt(
                checkin=checkin,
                text=checkin.pm_proof_text,
                url=checkin.proof_url,
                url_alive=checkin.url_alive,
                image_key=checkin.proof_image_key,
                reaction=checkin.coach_reaction,
            )
            checkin.proof_image_key = ""

        checkin.pm_proof_text = text
        checkin.proof_url = (request.data.get("url") or "").strip()
        # Does the link answer? One bounded request, before the judge reads
        # anything, because what comes back is a fact the server owns and the
        # judge is given facts in the system half — the builder's URL itself
        # stays inside the fence where all their own words are.
        #
        # Recomputed on every submission rather than carried: a resubmission is
        # a different link as often as it is different words, and the answer the
        # last try got has already been archived onto its ProofAttempt above.
        checkin.url_alive = links.check(checkin.proof_url) if checkin.proof_url else None
        # Only stamped when there is an answer to stamp. A check that never
        # happened leaves both fields NULL, and the row makes no claim.
        checkin.url_checked_at = (
            timezone.now() if checkin.url_alive is not None else None
        )
        # Rows created before the phase field existed (or by an older client)
        # get stamped on their first proof rather than staying unattributed.
        if not checkin.phase:
            checkin.phase = goal.phase

        # Store it if we can, but never let storage decide whether the work
        # counted: the written proof is the record, the screenshot corroborates
        # it. A dead bucket costs the image, not the day.
        if image_bytes and storage.is_configured():
            key = storage.proof_key(goal.id, checkin.id, content_type)
            if storage.put_image(key, image_bytes, content_type):
                checkin.proof_image_key = key

        verdict, reaction, labels = _react_to_proof(
            goal,
            checkin,
            request.user.tone,
            image_bytes,
            content_type or "",
            pending_try=archived_try,
        )
        checkin.proof_status = VERDICT_STATUS.get(
            verdict, CheckIn.ProofStatus.PUSHED_BACK
        )
        # What the gate will count this evening as, written at the moment the
        # verdict is: who it was about, and which parts of the bar it satisfied.
        # None leaves the row's existing labels alone — the unedited-draft path
        # has better ones already, and a judge that flaked on the labels must not
        # erase them (_labels_from_verdict).
        if labels is not None:
            checkin.subject = labels.subject
            checkin.proof_parts = labels.parts
        checkin.coach_reaction = reaction
        brief = _brief_from_proof(goal, checkin)
        # The refused try reaches the trail exactly when the row that replaces
        # it lands, so the record can never hold one without the other.
        with transaction.atomic():
            if archived_try is not None:
                archived_try.save()
            checkin.save()
            # In the same transaction as the proof it comes from: a goal
            # carrying a brief whose source row never landed would describe an
            # evening that did not happen.
            if brief is not None:
                goal.brief = brief
                goal.save(update_fields=["brief", "updated_at"])
                logger.info(f"Goal {goal.id} gained a brief from checkin {checkin.id}")
        # The row's own date, not the client's: after midnight they differ, and
        # the log should name the evening the proof landed on.
        logger.info(f"Proof {checkin.proof_status} for goal {goal.id} on {checkin.date}")
        return Response(
            {
                "checkin": CheckInSerializer(checkin).data,
                "gate": _gate_payload(goal),
                # `day` is the builder's date, the same one this proof was
                # filed under — the streak counts back from the day they
                # just closed, not from whatever day it is in UTC.
                "streak": streaks.current_streak(goal, day),
            }
        )


def _brief_from_workshop(arguments: dict) -> dict | None:
    """The room's answer to IDEA's bar, from a sketch_idea_bar call.

    The same two functions that will read tonight's real proof do the work
    here, unchanged: `bar.read` composes the parts into one paragraph, and
    `bar.labels` counts which of the four came back. The model extracted; the
    server did the rest, and `parts` is arithmetic over the arguments rather
    than anything the model was asked to assert about itself.

    Both of the things the caller keeps come out of this one call — the keys
    the forecast counts and the prose the commit carries — so the meter on the
    builder's screen and the brief on their goal cannot describe different
    rooms. That is the reason this reads a sketch rather than the tiebreak:
    sketch_idea_bar is maintained through the conversation and catches a room
    that talks an idea through and never reaches a title.

    Only the four declared part keys are passed on. `bar.read` prefers a `text`
    argument when it is given one, and the schema does not declare one — so
    filtering here is what stops an undeclared argument from becoming the
    paragraph the coach is later told the builder said.

    None means nothing of the bar came back, which is every workshop that
    spent its turns on the tiebreak rather than on the body of the idea. That
    is a normal room, not a failure, and it leaves the goal exactly as it was
    before any of this existed.
    """
    given = {
        part.key: arguments.get(part.key) for part in bar.BAR[Phase.IDEA].parts
    }
    labels = bar.labels(Phase.IDEA, given)
    if not labels.parts:
        return None
    text = bar.read(Phase.IDEA, given).text.strip()
    if not text:
        return None
    return {
        # Trimmed to the same width a hand-written brief is held to: this lands
        # in a prompt block that has to stay a paragraph, and unlike an
        # accepted proof there is no row it would then disagree with.
        "text": text[:BRIEF_CHARS],
        "parts": labels.parts,
        "source": "WORKSHOP",
        "written_at": timezone.now().isoformat(),
    }


def _brief_from_proof(goal: Goal, checkin: CheckIn) -> dict | None:
    """The idea's body, written the one time IDEA's proof is accepted.

    None means leave the goal's brief exactly as it is, and there are four ways
    to get it. Three are "this is not that moment" — the verdict was not an
    accept, the evening was earned in some later phase, the row carries no text.
    The fourth is the one worth stating: **a brief the BUILDER wrote is never
    overwritten.** They may have written the idea in their own words before
    anything banked, and the proof arriving later does not get to replace what
    they said with what they filed.

    A brief the WORKSHOP wrote is replaced, and the distinction is the point.
    That one is a paragraph the coach composed out of a conversation, kept
    because it was better than the blank the goal used to carry — a sketch,
    made before anything was judged, and possibly covering two of the four
    parts. This one is the builder's own four-part answer, the only one the
    gate has ever accepted. When both exist the second is the founding
    statement of the idea and the first was standing in for it.

    Why this reads `pm_proof_text` rather than the four parts as fields: it
    cannot read them, and the reason is a rule rather than an omission. Every
    IDEA proof passes through `bar`, but `bar.labels()` returns which parts an
    answer satisfied and never their values — see the comment on
    `CheckIn.proof_parts`, which states the rule outright. The values are
    structured for exactly one turn, inside the suggest_proof arguments, and
    `bar.compose` turns them into prose before the row is written. So the whole
    of the idea, in the builder's own words, is the proof text; `parts` records
    which of the four the gate saw in it.

    The point of copying it onto the goal at all — the text is already on the
    check-in — is that the check-in's copy expires from the coach's view and
    this one does not. `_banked` sends the ten newest accepted proofs, trimmed
    to RECORD_CHARS; the IDEA proof is by construction the oldest row a goal has
    and the only four-part answer the product ever asks for, so it is both the
    first to fall off that list and the most likely to be cut in half while it
    is on it. The founding statement of the idea is the one row that must not
    age out of the prompt, and RECORD_LIMIT's own comment — "what falls off the
    end is the oldest, which is also the least likely to be re-asked for
    tonight" — is right about every row except this one.
    """
    if checkin.proof_status != CheckIn.ProofStatus.ACCEPTED:
        return None
    # The phase the evening was earned in, not the phase the goal is in now: a
    # verdict that advances the goal must still attribute its proof to IDEA.
    if (checkin.phase or goal.phase) != Phase.IDEA:
        return None
    if goal.brief and goal.brief.get("source") != "WORKSHOP":
        return None
    text = (checkin.pm_proof_text or "").strip()
    if not text:
        return None
    return {
        "text": text,
        "parts": list(checkin.proof_parts or []),
        "source": "PROOF",
        "written_at": timezone.now().isoformat(),
    }


def _labels_from_verdict(phase: str, payload: dict) -> bar.Labels | None:
    """The judge's own labels for the evening it just accepted — who it was
    about, and which parts of the bar it satisfied.

    Same division of labour as suggest_proof: the model extracts, the server
    counts. It is the call that already decides accept or push_back, so no new
    authority is handed out here — and what it says is filtered before it lands.
    An invented part key is dropped (bar.known_parts), because a gate that counts
    kinds must count names bar.py chose.

    None means "nothing usable came back", which is deliberately not the same as
    "empty". A verdict that flakes on this must not wipe the labels the draft
    already carried, and must never cost the builder the proof itself: the day
    is accepted either way, and an unlabelled accept simply leaves the kind still
    owed, which try_advance then names.
    """
    known = bar.known_parts(phase)
    parts = [key for key in bar._entries(payload.get("parts")) if key in known]
    subject = bar.normalise_subject(payload.get("subject") or "")
    if not parts and not subject:
        return None
    return bar.Labels(subject=subject, parts=parts)


def _react_to_proof(
    goal: Goal,
    checkin: CheckIn,
    tone: str,
    image: bytes | None = None,
    content_type: str = "",
    pending_try: ProofAttempt | None = None,
) -> tuple[str, str, bar.Labels | None]:
    """LLM garnish with a deterministic floor (transcriber's fix_punctuation
    pattern): any failure logs and falls back to a stock reaction, so the daily
    loop never breaks because a model call flaked.

    That floor is "unjudged", not "accept". The loop surviving an outage is
    right and stays — the day is declared, proved, on the record, and in the
    streak. Banking a gate proof for it was a second, separate decision riding
    on the same word, and it handed the phase gate to whoever caught the model
    on a bad afternoon. Splitting them costs the builder nothing: filing again
    once the model answers gets the same evening a real reading, and until then
    the cycle stays open rather than closing on a verdict nobody gave.

    A screenshot, when there is one, is read by the vision model in this same
    call — one judgement over the text and the image together, because they
    are one claim about one day's work.

    Three things keep the judgement from moving under the builder. A
    resubmission is judged against every try already refused tonight and the
    words that refused each one; a COMPLETE proof Masterji drafted himself,
    filed unedited, is accepted without a model call at all; and his running
    notes go into the prompt so the evening cannot demand a fact the afternoon
    already took as given. The verdict is otherwise entirely the model's —
    nothing here passes work because the builder tried often enough.

    Two things bound what the model is deciding. It sees the proofs this goal has
    already banked, so a proof cannot be banked twice by being retold; and the
    submission arrives inside a fence with the rule that text in there is
    evidence and never instructions, because this is the one call in the product
    whose input the builder writes and whose output is a decision about them.
    """
    offer = checkin.proof_offer.strip()
    missing = checkin.proof_missing.strip()

    # Before anything else, including the draft shortcut below — a draft filed
    # unedited skips the model entirely, so a repeat that went through it would
    # be banked with nothing having read it at all.
    repeat = _already_banked(goal, checkin, checkin.pm_proof_text)
    if repeat is not None:
        logger.info(
            f"Proof on checkin {checkin.id} repeats accepted checkin {repeat.id}"
        )
        line = prompts.STOCK_DUPLICATE.get(tone, prompts.STOCK_DUPLICATE["ENGLISH"])
        # "5 Aug", the same shape the record card shows (Masterji.tsx's
        # formatDate). Built rather than strftime'd because the format that
        # drops the leading zero is a platform extension, not a guarantee.
        return "push_back", line.format(date=f"{repeat.date.day} {repeat.date:%b}"), None

    if offer and not missing and checkin.pm_proof_text.strip() == offer:
        # He read the conversation, decided it cleared the bar, and wrote this
        # out himself. Asking him again could only produce a disagreement with
        # himself, and the builder would be the one who paid for it.
        #
        # `missing` is what makes that true, and why it is checked here. A
        # running draft is written down long before it clears anything, and it
        # is the same field — without this test, notes Masterji himself called
        # incomplete would file straight through untouched. That is not
        # leniency, it is the gate deciding nothing.
        logger.info(f"Proof filed from Masterji's own draft on checkin {checkin.id}")
        # No labels: the row already carries the draft's own, computed from the
        # arguments this very text was composed from (ChatView).
        return (
            "accept",
            prompts.STOCK_OFFER_ACCEPT.get(tone, prompts.STOCK_OFFER_ACCEPT["ENGLISH"]),
            None,
        )

    # Written archive-before-overwrite by ProveView, so by the time we're here
    # the trail already holds tonight's rejected tries — oldest first (the
    # model's Meta orders by created_at).
    tries = list(checkin.attempts.all())
    # The try being replaced right now is handed in rather than read back,
    # because it is not saved yet — it commits with the row that replaces it,
    # so the record can never hold one without the other. Appended last
    # because this list is oldest first and it is tonight's most recent
    # refusal. `prior_tries` only reads `.text` and `.reaction`, so an unsaved
    # instance is the same thing to it as a row.
    if pending_try is not None:
        tries.append(pending_try)
    try:
        system = prompts.PROOF_REACTION_SYSTEM.format(
            # The standard the builder was shown, in the room that decides
            # whether they met it. Read out of guidance.PROOF_HINT, the same
            # module the check-in form, the gate refusal and the chat coach read
            # — so "that clears it" in the afternoon and the verdict at 11pm
            # cannot be answers to two different questions.
            judge_bar=prompts.judge_bar_for(Phase(goal.phase)),
            substance_rule=prompts.SUBSTANCE_RULE,
            respect_rule=prompts.RESPECT_RULE,
            label_rule=prompts.label_rule_for(Phase(goal.phase)),
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            phase=goal.phase,
            declared=checkin.am_declaration,
            asked_for=prompts.PROOF_ASKED_FOR.format(proof_ask=checkin.proof_ask)
            if checkin.proof_ask
            else "",
            prior_try=prompts.prior_tries(tries),
            from_offer=prompts.from_draft(offer, missing),
            banked=prompts.record_block(
                _banked(goal, exclude=checkin), prompts.RECORD_FOR_JUDGE
            ),
            evidence_rule=prompts.EVIDENCE_NOT_INSTRUCTIONS,
        )
        if image:
            system += prompts.PROOF_IMAGE_RULE
        # Empty unless the server actually got an answer from the link.
        system += prompts.url_fact(checkin.url_alive)
        user_text = prompts.fence_submission(
            checkin.pm_proof_text, checkin.proof_url
        )
        raw = (
            # complete_with_image already reads LLM_VISION_MODEL, which chains
            # off the judge model — so both halves of this verdict move together
            # when the judge is upgraded.
            llm.complete_with_image(system, user_text, image, content_type)
            if image
            else llm.complete(system, user_text, model=settings.LLM_JUDGE_MODEL)
        )
        payload = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        verdict = payload.get("verdict", "")
        reaction = str(payload.get("reaction") or "").strip()
        if verdict not in ("accept", "push_back") or not reaction:
            # The model answered, but not the question it was asked. That is
            # the same state of knowledge as it never answering, so it gets the
            # same word — and it used to get "accept", which made a banked
            # proof reachable from any submission that knocked the reply off
            # its JSON: the proof text is the builder's own, and it goes into
            # this very call.
            #
            # A verdict with no words behind it lands here too. There is
            # nothing to say under an accept, and a push-back that cannot name
            # what is missing is the wasted evening PROOF_REACTION_SYSTEM
            # exists to forbid — so an unexplained verdict is treated as no
            # verdict rather than imposed in silence.
            logger.warning(f"Unreadable verdict {verdict!r} on checkin {checkin.id}")
            return "unjudged", _unjudged_reaction(tone), None
        return verdict, reaction, _labels_from_verdict(goal.phase, payload)
    except Exception as e:
        logger.error(f"Proof reaction failed: {e}")
        return "unjudged", _unjudged_reaction(tone), None


def _unjudged_reaction(tone: str) -> str:
    """What he says about an evening he never read. In both tones, like
    STOCK_OFFER_ACCEPT and for the same reason: an outage is not a good moment
    to also stop speaking a builder's language."""
    return prompts.STOCK_UNJUDGED.get(tone, prompts.STOCK_UNJUDGED["ENGLISH"])


class ChatView(throttles.VoicedThrottleMixin, APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "chat"
    throttle_message = (
        "That's a lot of talking for one hour. The work is the part that counts "
        "— go do some of it and come back."
    )

    def post(self, request):
        goal = _active_goal(request.user)
        if goal is None:
            return Response(
                {"detail": "Set a goal first."}, status=status.HTTP_400_BAD_REQUEST
            )
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response(
                {"detail": "Say something."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(content) > settings.CHAT_MAX_CHARS:
            return Response(
                {"detail": "That's a lot at once. Say the part you want an answer to."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        Message.objects.create(
            goal=goal, role=Message.Role.USER, phase=goal.phase, content=content
        )

        today = _client_day(request)
        checkin = _latest_checkin(goal, today)
        # The row the running draft lives on, not the day's latest cycle: once
        # a cycle is proved and closed its notes are spent, and reading them
        # back would have him chasing pieces of a proof already on the record.
        target = _offer_target(goal, today)
        # No marker passed: the digest claims a week once and so must never
        # reach back past its own, but this states a fact every turn and has
        # nothing to claim. Handed the same window either way — see below.
        week_of, week = weekly.week_read_back(goal, today)
        system = prompts.build_system_prompt(
            goal,
            gates.gate_status(goal),
            streaks.current_streak(goal, today),
            _today_state(checkin),
            request.user.tone,
            archive=_archive(request.user),
            lifetime=streaks.lifetime_days(request.user),
            mode=request.user.mode,
            offer=target.proof_offer if target else "",
            missing=target.proof_missing if target else "",
            # Not scoped to the current phase: a builder who already told him
            # who they spoke to should not be asked again because the goal has
            # since moved on. Same call as gates.accepted_proofs_total.
            banked=_banked(goal),
            # The only caller that knows the builder's own date, which is why
            # it is the only one that measures either of these. Both are
            # subtractions over rows this turn already read.
            days_in_phase=streaks.days_in_phase(goal, today),
            days_since_complete=streaks.days_since_complete(goal, today),
            # The same seven days the builder read back on Monday, from the same
            # function — so the coach and the digest cannot come to different
            # numbers about the week they are both describing. That is why the
            # fallback belongs on both: a digest naming the week of 20 Jul beside
            # a prompt drawn on the empty week just gone is exactly the
            # divergence this line was written to prevent, and the builder would
            # find it by replying to the message they just read.
            week=week,
            week_of=week_of,
            # What they said THIS phase would produce, which is the one thing
            # the coach could never tell from PHASE_HINT: that sentence is the
            # same for every builder forever, and this one is about the thing
            # they decided on the morning the phase opened.
            intent=_phase_intent(goal),
            # And the day they said they would launch, if they named one. The
            # only fact in the state block the builder put there themselves.
            launch=_launch_payload(goal, today),
            # What the idea before this one taught them, when this goal is a
            # pivot. Facts, never counts: the gate has been given nothing.
            predecessor=_predecessor(goal),
        )
        # SYSTEM rows are excluded, not mapped: they are the app talking about a
        # turn that failed, and the only role this mapping had for them was
        # "assistant" — which handed the model its own outage back as something
        # it had said, on every turn after it, for as long as it stayed in the
        # window. Excluded in the queryset rather than after the slice, so a run
        # of failures can't push real turns out of HISTORY_LIMIT.
        turns = goal.messages.exclude(role=Message.Role.SYSTEM).order_by(
            "-created_at"
        )[:HISTORY_LIMIT]
        history = [
            {
                "role": "user" if m.role == Message.Role.USER else "assistant",
                "content": m.content,
            }
            for m in list(turns)[::-1]
        ]

        # `target` is the one bound above — read once for the turn. It used to
        # be recomputed here, which cost `_open_checkin` plus `_carried_over`
        # a second time on the hottest authenticated path in the product, for
        # a value that cannot have changed: nothing between the two writes.
        # Both readers take the same object off the same `today`, so the draft
        # and the sentence explaining where it can't go can never disagree
        # about the day.
        response = StreamingHttpResponse(
            self._events(
                goal,
                system,
                history,
                target,
                day_closed=target is None and _day_closed(goal, today),
            ),
            content_type="application/x-ndjson",
        )
        # Ask every proxy on the way (Vercel, Render) not to buffer the stream.
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _events(
        self,
        goal: Goal,
        system: str,
        history: list[dict],
        offer_target: CheckIn | None = None,
        day_closed: bool = False,
    ):
        line = lambda obj: json.dumps(obj) + "\n"  # noqa: E731
        parts: list[str] = []
        advance_proposed = False
        close_proposed = False
        offered = missing = ""
        labels = bar.Labels(subject="", parts=[])
        broke = False
        with tracer.start_as_current_span("coach.turn") as span:
            span.set_attribute("goal.phase", goal.phase)
            span.set_attribute("llm.model", settings.LLM_MODEL)
            try:
                for kind, payload in llm.stream_chat(
                    system,
                    history,
                    tools=[
                        prompts.PROPOSE_ADVANCE_TOOL,
                        # Opens the retire box on the goal card, and that is the
                        # whole of it — see PROPOSE_GOAL_CLOSE_TOOL, which says
                        # at length why this one has no server half. Nothing
                        # below closes a goal.
                        prompts.PROPOSE_GOAL_CLOSE_TOOL,
                        # Shaped by the phase, because the arguments ARE the
                        # phase's bar — a list per part that has a count on it.
                        prompts.suggest_proof_tool(Phase(goal.phase)),
                    ],
                ):
                    if kind == "delta":
                        parts.append(payload)
                        yield line({"t": "delta", "text": payload})
                    elif kind == "tool_call":
                        name = payload.get("name")
                        if name == "propose_phase_advance":
                            advance_proposed = True
                        elif name == "propose_goal_close":
                            # A flag and nothing else. The close itself is
                            # RetireView, reached from the box this opens, with
                            # a reason and an outcome only the builder has.
                            close_proposed = True
                        elif name == "suggest_proof":
                            # The model sends the parts; bar.read does the
                            # counting, and what is still owed is arithmetic
                            # over them rather than the model's opinion of its
                            # own paragraph. Assigned as a pair, always both: a
                            # later call in the same turn replaces the draft,
                            # and a gap left over from the earlier one would
                            # describe text that is no longer there.
                            arguments = payload.get("arguments", {})
                            offered, missing = bar.read(goal.phase, arguments)
                            # Who it was about and which parts it satisfied,
                            # from the same arguments and by the same
                            # arithmetic. Kept with the draft because the
                            # unedited-draft path never reaches a model again
                            # (_react_to_proof accepts it outright), so this is
                            # the only moment the labels for that path exist.
                            labels = bar.labels(goal.phase, arguments)
            except Exception as e:
                logger.error(f"Chat stream failed: {e}")
                broke = True
                yield line({"t": "error", "detail": STREAM_BROKE})

            content = "".join(parts)

            # A drafted proof is a row, not a wire event: the client refetches
            # state the moment the turn ends and reads the offer off the
            # check-in with everything else. One source of truth, and an offer
            # that outlives the turn it was made in — the builder can go and
            # file it tomorrow morning if they close the tab tonight.
            if offered:
                if offer_target is not None:
                    offer_target.proof_offer = offered
                    offer_target.proof_missing = missing
                    # Provisional, exactly as far as the draft is: they describe
                    # THIS draft, and a proof filed with the text edited is
                    # judged, which overwrites them (ProveView). Nothing reads
                    # them until a proof on this row is ACCEPTED.
                    offer_target.subject = labels.subject
                    offer_target.proof_parts = labels.parts
                    offer_target.save(
                        update_fields=[
                            "proof_offer",
                            "proof_missing",
                            "subject",
                            "proof_parts",
                            "updated_at",
                        ]
                    )
                    span.set_attribute("proof.offered", True)
                    logger.info(f"Proof drafted for checkin {offer_target.id}")
                elif not missing:
                    # No OPEN check-in to hang a FINISHED draft on. That is a
                    # reason to hand it back, not to bin it silently: the work
                    # behind it happened, and the builder is the only person who
                    # can turn it into a declaration and a filing. Which
                    # declaration depends on why there's no target — a day nobody
                    # has declared on, or one already proved and closed — and
                    # telling them the wrong one contradicts their own card.
                    span.set_attribute("proof.offered", False)
                    span.set_attribute("proof.day_closed", day_closed)
                    why = "the day already closed" if day_closed else "nothing declared"
                    logger.info(f"Proof offered with {why} on goal {goal.id}")
                    template = OFFER_DAY_CLOSED if day_closed else OFFER_NO_DECLARATION
                    note = template.format(offer=offered)
                    # Streamed as well as saved, the way a gate refusal is: it
                    # belongs to the turn the builder is watching, not to the
                    # refetch a second later.
                    yield line({"t": "delta", "text": f"\n\n{note}" if content else note})
                    content = f"{content}\n\n{note}".strip()
                else:
                    # Running notes with nothing to pin them to, which is not
                    # worth saying out loud. A finished draft handed back is one
                    # move from being filed — declare, paste, done; a partial one
                    # is a paraphrase of the conversation they are already having,
                    # repeated every turn until they declare. His own words in
                    # this turn carry it, and the transcript keeps them.
                    span.set_attribute("proof.offered", False)
                    logger.info(f"Partial draft with nothing owed on goal {goal.id}")

            # Both of these turns produced no words and used to save no row,
            # which is not the same as Masterji having nothing to say — it is
            # the transcript losing the half of the exchange that explains the
            # other half. A turn that got some way in before it fell over
            # needs neither: that answer was already saved as far as it got.
            #
            # `content` is already built above, and handing a draft back may
            # have appended it to it — which is exactly why that case must not
            # also count as wordless. It doesn't: handing back only happens with
            # no target, either wording of it, and the second test here requires
            # a target. Nor does the one below it, partial notes with nothing to
            # pin them to: a turn that banked nothing, said nothing and proposed
            # nothing is a turn with nothing to record.
            #
            # `notice` is whether the row about to be written is the app's note
            # rather than Masterji's answer. Only the wordless failure is: a
            # turn that got some way in before it fell over saved real words,
            # and those are his.
            notice = False
            if broke and not content:
                content = STREAM_BROKE
                notice = True
            elif offered and offer_target is not None and not content:
                receipt = (
                    NOTES_LANDED.format(missing=missing) if missing else OFFER_LANDED
                )
                yield line({"t": "delta", "text": receipt})
                content = receipt
            if advance_proposed:
                advanced, detail = gates.try_advance(goal)
                span.set_attribute("gate.advanced", advanced)
                yield line(
                    {
                        "t": "gate",
                        "advanced": advanced,
                        "phase": goal.phase,
                        "detail": detail,
                    }
                )
                content = f"{content}\n\n{detail}".strip()
                # The gate's answer is the server speaking through him and
                # belongs in the transcript as his. It cannot reach a wordless
                # failure anyway — a proposal arrives as a tool call, so the
                # stream got that far — but the flag is cleared here rather
                # than relied upon not to matter.
                notice = False
            # The close box, opened. No verdict rides along and nothing is
            # written, because nothing happened: the goal is still ACTIVE here
            # and stays that way until the builder writes a reason and presses
            # an exit (PROPOSE_GOAL_CLOSE_TOOL).
            #
            # Deliberately unlike the gate above, which appends its detail to
            # the transcript. That line is the SERVER answering something, and
            # it earns its place. Here the server answered nothing, so a line
            # saying so would be the app narrating an action next to the one
            # sentence the coach was told to say in his own words — the exact
            # register this whole change exists to take away from him. A turn
            # that opens the box and says nothing therefore saves no row; the
            # box is on screen, which is the honest amount of noise for a turn
            # in which the server did not act.
            if close_proposed:
                span.set_attribute("close.proposed", True)
                logger.info(f"Close box proposed on goal {goal.id}")
                yield line({"t": "close"})
            if content:
                Message.objects.create(
                    goal=goal,
                    role=Message.Role.SYSTEM if notice else Message.Role.COACH,
                    phase=goal.phase,
                    content=content,
                )
            yield line({"t": "done"})


class WorkshopChatView(throttles.VoicedThrottleMixin, APIView):
    """Both workshops (models.Workshop): the room before the goal, and the one
    reopened once per goal after it.

    Streams NDJSON like ChatView. It used to be guarded by the inverse of
    ChatView's condition — 400 while a goal IS active — and that guard is gone,
    because the sentence it was refusing turned out to be a real one: "I have an
    idea and I no longer believe in it" is the day-four version of "I don't have
    an idea yet", and the only room for it was the one you got by burying the
    goal. Which room a turn lands in is decided by _open_workshop from the
    builder's own state; neither is reachable by asking for it.

    Everything that made the first room safe to give away is enforced here in
    server code with no model in the loop, and holds for the second: the turn
    cap (a smaller one), the three-candidate ceiling, and the fact that a
    suggested title only ever fills the commit box. The reopened room is handed
    no tools at all. Nothing in this view writes a CheckIn, a proof or a phase —
    gates.py has nothing here to read.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = throttles.THROTTLES
    # Draws from the chat bucket rather than one of its own. Every turn in here
    # is the same paid call a chat turn is, and a second scope would have been a
    # second budget for the same spending.
    #
    # That argument used to rest on the two endpoints refusing each other, which
    # stopped being true when the room learned to reopen: a builder with a goal
    # can now be in both. The shared bucket is what makes that safe rather than
    # something to worry about — the hour's ceiling is on the spending, not on
    # which room it was spent in, so reopening cannot buy a second allowance.
    throttle_scope = "chat"
    throttle_message = (
        "That's a lot of thinking out loud for one hour. Sit with what he's "
        "already said, and come back to it in a bit."
    )

    def post(self, request):
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response(
                {"detail": "Say something."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(content) > settings.CHAT_MAX_CHARS:
            return Response(
                {"detail": "That's a lot at once. Say the part you want an answer to."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        workshop = _open_workshop(request.user, create=True)
        if workshop is None:  # nothing to open, and nothing to say about it
            return Response(
                {"detail": "There's no room open right now."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reopened = workshop.status == Workshop.Status.REOPENED
        total = _turn_budget(workshop)
        # The cap, refused in code and voiced. Checked BEFORE the row is
        # written, so a refused turn costs nothing and the count the builder
        # sees is the count the server used.
        if _turns_used(workshop) >= total:
            logger.info(f"Workshop {workshop.id} spent — turn refused")
            refusal = REOPENED_SPENT if reopened else WORKSHOP_SPENT
            return Response(
                {"detail": refusal.format(turns=total)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        WorkshopMessage.objects.create(
            workshop=workshop, role=WorkshopMessage.Role.USER, content=content
        )
        if reopened:
            goal = workshop.goal
            system = prompts.build_reopened_prompt(
                title=goal.title,
                phase=goal.phase,
                # _client_day rather than the server's, for the same reason
                # every other read of the loop's date uses it: "day 4 of BUILD"
                # is off by one for every builder ahead of UTC otherwise, and
                # this room's whole subject is how long this has been going on.
                days_in_phase=streaks.days_in_phase(goal, _client_day(request)),
                accepted=gates.accepted_proofs_total(goal),
                # The same list the coach next door is handed, from the same
                # function: a builder deciding whether this was worth it should
                # be talking to somebody who can see what they already did.
                banked=_banked(goal),
                turns_used=_turns_used(workshop),
                turns_total=total,
                tone=request.user.tone,
            )
        else:
            system = prompts.build_workshop_prompt(
                candidates=list(workshop.candidates or []),
                turns_used=_turns_used(workshop),
                turns_total=total,
                maximum=Workshop.MAX_CANDIDATES,
                tone=request.user.tone,
                sketch=list(workshop.sketch_parts or []),
            )
        # Same exclusion as ChatView, for the same reason: a SYSTEM row is the
        # app talking about a turn that failed, and feeding it back as
        # "assistant" hands the model its own outage as something it said.
        turns = workshop.messages.exclude(
            role=WorkshopMessage.Role.SYSTEM
        ).order_by("-created_at")[:HISTORY_LIMIT]
        history = [
            {
                "role": "user" if m.role == WorkshopMessage.Role.USER else "assistant",
                "content": m.content,
            }
            for m in list(turns)[::-1]
        ]
        response = StreamingHttpResponse(
            self._events(workshop, system, history, reopened=reopened),
            content_type="application/x-ndjson",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _events(
        self,
        workshop: Workshop,
        system: str,
        history: list[dict],
        reopened: bool = False,
    ):
        line = lambda obj: json.dumps(obj) + "\n"  # noqa: E731
        parts: list[str] = []
        candidates = list(workshop.candidates or [])
        parked: list[str] = []
        suggested = ""
        brief: dict | None = None
        refused_park = False
        sketched: list[str] | None = None
        broke = False
        with tracer.start_as_current_span("coach.workshop") as span:
            span.set_attribute("llm.model", settings.LLM_MODEL)
            try:
                for kind, payload in llm.stream_chat(
                    system,
                    history,
                    # None of the three in the reopened room, and the absence is
                    # the design rather than an omission: there is no pile to
                    # park into, no title to suggest for a goal that exists, and
                    # no IDEA bar to rehearse for a phase already committed to
                    # and possibly long past. A room whose only output is the
                    # conversation is exactly what "banks nothing" means when
                    # you write it down in code.
                    tools=(
                        []
                        if reopened
                        else [
                            prompts.PARK_CANDIDATE_TOOL,
                            prompts.SUGGEST_GOAL_TOOL,
                            prompts.sketch_idea_bar_tool(),
                        ]
                    ),
                ):
                    if kind == "delta":
                        parts.append(payload)
                        yield line({"t": "delta", "text": payload})
                    elif kind == "tool_call":
                        # Sent none, and honours none. The tool list above is
                        # already empty for this room, so this can only fire on
                        # a model inventing a call — and "banks nothing" is a
                        # promise this view keeps in code rather than one the
                        # schema happens to make unlikely. Same division of
                        # labour as the fourth candidate.
                        if reopened:
                            logger.info(
                                f"Workshop {workshop.id} reopened — tool call dropped"
                            )
                            continue
                        name = payload.get("name")
                        arguments = payload.get("arguments", {})
                        if name == "park_candidate":
                            one_liner = str(arguments.get("one_liner") or "").strip()
                            if not one_liner:
                                continue
                            # The ceiling, refused here rather than asked for in
                            # the prompt. The prompt already says three is the
                            # limit and flips to a forced choice at it, but a
                            # limit that only exists in a prompt is a limit the
                            # model can talk itself past — the same division of
                            # labour as _already_banked.
                            if len(candidates) >= Workshop.MAX_CANDIDATES:
                                refused_park = True
                                logger.info(
                                    f"Workshop {workshop.id} refused a 4th candidate"
                                )
                                continue
                            candidates.append(one_liner)
                            parked.append(one_liner)
                        elif name == "suggest_goal":
                            title = str(arguments.get("title") or "").strip()
                            if title:
                                # Last call wins: a later suggestion in the same
                                # turn replaces the earlier one, the way a later
                                # suggest_proof replaces the draft.
                                suggested = title[:200]
                        elif name == "sketch_idea_bar":
                            # The transfer this room borrows from bar.py: the
                            # model extracted, and both of the things kept here
                            # are the server's arithmetic over what it sent.
                            # Anything that is not one of IDEA's four keys is
                            # dropped, so an invented part can neither inflate
                            # the forecast nor reach the goal.
                            #
                            # ONE call writes both, which is the point. The
                            # forecast on screen counts the keys; the brief the
                            # commit carries is those same arguments composed
                            # to prose. They came out of one tool call, so
                            # there is no version of this where the meter and
                            # the goal disagree about what the room found.
                            drafted = _brief_from_workshop(arguments)
                            if drafted is not None:
                                # Last call wins: the tool is told to send the
                                # whole of what it has, so a later call is a
                                # fuller picture and not an addition to the
                                # earlier one.
                                sketched = list(drafted["parts"])
                                brief = drafted
            except Exception as e:
                logger.error(f"Workshop stream failed: {e}")
                broke = True
                yield line({"t": "error", "detail": STREAM_BROKE})

            content = "".join(parts)
            fields: list[str] = []
            if parked:
                fields.append("candidates")
            if suggested:
                fields.append("suggested_title")
            if brief is not None:
                fields.append("brief")
            if sketched is not None:
                fields.append("sketch_parts")
            if fields:
                if parked:
                    workshop.candidates = candidates
                if suggested:
                    workshop.suggested_title = suggested
                if brief is not None:
                    workshop.brief = brief
                if sketched is not None:
                    workshop.sketch_parts = sketched
                workshop.save(update_fields=[*fields, "updated_at"])
                span.set_attribute("workshop.candidates", len(candidates))
                logger.info(
                    f"Workshop {workshop.id} holds {len(candidates)} candidate(s)"
                )
            # Both are rows on the workshop, not just wire events, for the same
            # reason a drafted proof is a row: the client refetches state when
            # the turn ends, and a card that only existed in the stream would
            # vanish under the builder as they reached for it.
            if parked or suggested or refused_park:
                yield line(
                    {
                        "t": "candidates",
                        "candidates": candidates,
                        "suggested": suggested,
                        # Said out loud rather than swallowed: the builder is
                        # watching a suggestion not appear, and silence there
                        # reads as the app dropping their idea.
                        "refused": refused_park,
                    }
                )
            # A row for the same reason the two above are rows: the client
            # refetches when the turn ends, and a meter that only existed in
            # the stream would reset itself under a builder who was reading it.
            if sketched is not None:
                yield line({"t": "sketch", **_sketch_payload(sketched)})
            notice = False
            if broke and not content:
                content = STREAM_BROKE
                notice = True
            if content:
                WorkshopMessage.objects.create(
                    workshop=workshop,
                    role=(
                        WorkshopMessage.Role.SYSTEM
                        if notice
                        else WorkshopMessage.Role.COACH
                    ),
                    content=content,
                )
            # The count the client should show next, computed after this turn's
            # row landed. Sent on `done` so the meter and the server's own
            # refusal threshold are the same number.
            used = _turns_used(workshop)
            yield line(
                {
                    "t": "done",
                    "turns_used": used,
                    "turns_left": max(WORKSHOP_TURNS - used, 0),
                }
            )


# --- the product's own record ---------------------------------------------


def _shared_record(retirement: GoalRetirement) -> dict:
    """A closed goal as facts a stranger may read, and nothing else.

    Every field here was computed by the server from rows the builder had to
    earn — gates.reads_as, the snapshot counts, the phase timeline. That is the
    whole pitch: an E-Cell application or a parent reading "reached BUILD, 5
    accepted proofs, 4 of them from real-world contact, 12 days on the record"
    is reading numbers that came through a gate they can audit in a public
    repo, not a self-report.

    What is deliberately NOT here: the reason they closed it, the goal's brief,
    every proof text, every check-in, the coach's reaction, and the builder's
    name or account. The record is the shape of the work, not a diary, and the
    one thing a builder cannot take back once a link is out is prose.
    """
    goal = retirement.goal
    return {
        "title": goal.title,
        "outcome": retirement.outcome,
        # The verdict, which is the point of the page: INVALIDATED with contact
        # proofs behind it is the only version of "my startup didn't work out"
        # that reads as competence, and it is not the builder's to assert.
        "reads_as": gates.reads_as(goal, retirement.outcome),
        "phase_reached": retirement.phase_reached,
        "accepted_proofs": retirement.accepted_proofs,
        "contact_proofs": retirement.contact_proofs,
        "days_active": retirement.days_active,
        "best_streak": retirement.best_streak,
        "closed_on": retirement.created_at.date().isoformat(),
        "timeline": [
            {
                "to_phase": t.to_phase,
                "on": t.created_at.date().isoformat(),
            }
            for t in goal.transitions.all()
        ],
        "started_on": goal.created_at.date().isoformat(),
    }


class SharedRecordView(throttles.VoicedThrottleMixin, APIView):
    """One closed goal, by its unguessable slug, for anybody holding the link.

    The second public endpoint in this file, and it follows the first one's
    shape (ChangelogView) for the same reason: a surface with no account behind
    it and no ceiling on it is a surface somebody else decides the size of.

    The slug IS the access control, so this deliberately does not 403 or hint:
    a missing, revoked or wrong slug is a 404, identical in every case, because
    the difference between "no such record" and "that one is private" is itself
    something a stranger can walk.
    """

    permission_classes = [AllowAny]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "changelog"

    def get(self, request, slug: str):
        retirement = GoalRetirement.objects.filter(share_slug=slug).first()
        if retirement is None:
            return Response(
                {"detail": "No record here."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(_shared_record(retirement))


class ShareRecordView(APIView):
    """Turn the link on, or take it away. The builder's, and reversible.

    Off by default and off for every row that existed before this — a record
    that became public because the feature shipped is not opt-in.

    Turning it on again after revoking mints a DIFFERENT slug rather than
    restoring the old one. A link handed to somebody and regretted has to be
    able to stop working, and a switch that resurrects the same URL is a switch
    that only ever paused it.
    """

    permission_classes = [IsAuthenticated]
    # 132 bits from token_urlsafe(16), which is 22 characters. Not a UUID: this
    # goes in a URL a builder pastes into a message, and unguessable is the only
    # requirement it has.
    SLUG_BYTES = 16

    def _mine(self, request, pk: int) -> GoalRetirement:
        return get_object_or_404(
            GoalRetirement.objects.filter(goal__user=request.user), pk=pk
        )

    def post(self, request, pk: int):
        retirement = self._mine(request, pk)
        # Minted even when one already exists, which is what makes "off then on"
        # a new link rather than the old one coming back.
        retirement.share_slug = secrets.token_urlsafe(self.SLUG_BYTES)
        retirement.save(update_fields=["share_slug"])
        logger.info(f"Retirement {retirement.id} shared")
        return Response({"share_slug": retirement.share_slug})

    def delete(self, request, pk: int):
        """Revoking is its own verb, and that is not tidiness.

        This was one POST carrying `{"on": true|false}` until a test sent it
        form-encoded and `bool("False")` came back True — the switch turned the
        link ON when asked to take it away. A body that has to be read as a
        boolean is a body somebody can encode wrong; two verbs cannot be.
        """
        retirement = self._mine(request, pk)
        retirement.share_slug = None
        retirement.save(update_fields=["share_slug"])
        logger.info(f"Retirement {retirement.id} unshared")
        return Response({"share_slug": None})


class ChangelogView(throttles.VoicedThrottleMixin, APIView):
    """What has changed in Masterji, newest first.

    Public, unlike everything else here: the demo and the sign-in screen
    reach it too, and a changelog kept behind a login is a press release.
    Active rows only — an entry can be written before the change ships.

    Being the one endpoint with no account behind it is also why it is the one
    endpoint here that is throttled without spending a paisa. The other three
    ceilings exist to bound a model bill; this one exists because a public
    surface with no ceiling of any kind is a surface somebody else decides the
    size of. Signed-in mounts are keyed by user pk like everything else — the
    per-address bucket is the landing page and the tour.

    `?limit=N` serves the newest N. It exists because every screen in the
    product mounts this component to decide whether to show one dot, and the
    whole list had grown to 42KB across 77 entries — served to a first-time
    visitor on the landing page, before they had clicked anything, on a
    connection this product is explicitly built for. The house rule of a row
    per shipped change means that number only goes one way.

    `total` rides along so the client knows whether it is holding all of them
    rather than guessing from `len(entries) == limit`, which is wrong exactly
    when the count lands on the limit. It costs one COUNT on a table of this
    size, which is cheaper than the request it saves.
    """

    permission_classes = [AllowAny]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "changelog"

    def _limit(self, request) -> int | None:
        """The newest N, or None for all of them.

        Raises on anything else. A limit that states an intent the server
        cannot honour — `abc`, `0`, `-3`, `2.5` — used to fall through to the
        whole table, so the reply to a value nobody could mean was the largest
        response this endpoint has. Answering a request that was not made is
        not honesty, it is a silent upgrade, and on the one endpoint with no
        account behind it, it is the wrong direction to fail in.

        An absent `limit`, and an empty one, are not that: `?limit=` is a proxy
        or a typed URL dropping the value rather than asking for a size, and it
        means what leaving it off means.
        """
        raw = request.query_params.get("limit")
        if raw is None or raw == "":
            return None
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            # ParseError rather than a hand-built Response: it is a 400 whose
            # body is `{"detail": ...}`, which is the shape every other refusal
            # in this file answers in.
            raise ParseError("limit must be a positive whole number.")
        return n

    def get(self, request):
        limit = self._limit(request)
        entries = ChangelogEntry.objects.filter(is_active=True)
        total = entries.count()
        if limit is not None:
            entries = entries[:limit]
        return Response(
            {
                "entries": ChangelogEntrySerializer(entries, many=True).data,
                "total": total,
            }
        )
