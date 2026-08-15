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
    cohorts,
    export,
    gates,
    guidance,
    judging,
    links,
    llm,
    prompts,
    storage,
    streaks,
    throttles,
    weekly,
)
from .models import (
    METRIC_PHASE,
    ChangelogEntry,
    CheckIn,
    Cohort,
    CohortMember,
    Goal,
    GoalRetirement,
    LaunchCommitment,
    Message,
    ModelCall,
    Phase,
    PhaseTransition,
    ProofAttempt,
    Workshop,
    WorkshopMessage,
)
from .serializers import (
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


def _active_goal(user) -> Goal | None:
    return Goal.objects.filter(user=user, status=Goal.Status.ACTIVE).first()


# Turns a workshop gets before the only door left is Commit.
#
# It was fifteen, sized for a room whose whole job was choosing: enough to walk
# a week for problems, park three and run a tiebreak, and not enough to live in.
# The room now also has to drive IDEA's four parts to full, which is a longer
# conversation, so the number was re-derived rather than carried over.
#
# The arithmetic, from the session this change came from — 9 of 15 turns spent,
# one candidate parked, `sketch_parts` still empty:
#
#   9   what selection actually cost that builder (arrive, walk the week,
#       park, tiebreak) — observed, not estimated
# + 4   the four parts, at the one-at-a-time the prompt asks for, floor
# + 2   reserved: the prompt tells the coach to name the exit at two or fewer
#   --
#   15  which is the OLD budget exactly, with zero slack in it
#
# So fifteen does not hold: it covers the observed case and nothing slower, and
# a part that needs a follow-up question — most of them, most of the time —
# comes straight out of the reserve that exists so the room can end honestly.
# Twenty is that floor plus one follow-up per part, and it is still a meter:
# the room is bounded, the cap is on screen from turn zero, and Commit is
# reachable on turn one.
#
# This is the one number in the change that is derived rather than measured,
# and it is cheap to move: this constant plus four builder-visible mirrors
# (Landing.tsx ×2, Tour.tsx ×2). What makes it answerable properly is now
# shipped — `Workshop.sketch_parts` next to `_turns_used` says, per room, how
# many turns four parts actually took. Re-derive it from real rooms rather than
# from this comment.
WORKSHOP_TURNS = 20

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

    The reopened room is smaller on purpose. The room before the goal has to get
    from nothing to a candidate AND describe it well enough to act on (see
    WORKSHOP_TURNS for that arithmetic); deciding whether to keep going on a
    goal that already exists is a shorter conversation, and a long one is the
    drift the meter exists to refuse.
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

    `asks` is the whole bar in bar order, each part with whether it has landed —
    what the screen needs to stand the four questions up from turn zero rather
    than only after something has surfaced. It carries the labels because
    bar.py owns them: `owed` has always been labels rather than keys, and a
    client holding its own copy of IDEA's four questions would be a second
    wording of the bar, drifting from the one the evening is judged against.

    `have`/`need`/`owed` stay exactly as they were. `asks` is the same facts in
    the shape a list renders from, and every one of them is still counted here
    — the screen must never be the place the subtraction happens.
    """
    landed = set(parts)
    return {
        "parts": parts,
        "have": len(parts),
        "need": len(bar.BAR[Phase.IDEA].parts),
        "owed": bar.owed(Phase.IDEA, parts),
        "asks": [
            {"key": part.key, "label": part.label, "have": part.key in landed}
            for part in bar.BAR[Phase.IDEA].parts
        ],
    }


def _workshop_receipt(
    parked: list[str],
    suggested: str,
    sketched: list[str] | None,
    candidates: list[str],
) -> str:
    """What a workshop turn that produced only tool calls says for itself.

    One sentence per tool that fired, in the order the room does them: the pile
    first, then the rehearsal, then the title, which is the order of increasing
    commitment. Joined rather than picked between, because one turn can call
    more than one tool and a receipt that mentions two of the three things that
    changed is a worse answer than no receipt at all.

    Every number in it is the server's own arithmetic over what it stored —
    len() over the pile and bar.owed over the part keys — for the reason the
    forecast is computed in _sketch_payload rather than on the screen: a second
    place the subtraction happens is a second answer waiting to disagree.

    Empty is a real answer: a turn whose only tool call was dropped (a repeat,
    a blank one-liner, a fourth candidate) changed nothing, and the caller must
    not write a row claiming it did. The refusal at the ceiling has its own
    voice already, on the `candidates` event.
    """
    said: list[str] = []
    if parked:
        held = len(candidates)
        template = (
            guidance.PARKED_LANDED_FULL
            if held >= Workshop.MAX_CANDIDATES
            else guidance.PARKED_LANDED
        )
        said.append(
            template.format(
                have=held,
                maximum=Workshop.MAX_CANDIDATES,
                left=max(Workshop.MAX_CANDIDATES - held, 0),
            )
        )
    if sketched:
        owed = bar.owed(Phase.IDEA, sketched)
        need = len(bar.BAR[Phase.IDEA].parts)
        said.append(
            guidance.SKETCH_LANDED.format(
                have=len(sketched), need=need, owed="; ".join(owed)
            )
            if owed
            else guidance.SKETCH_LANDED_FULL.format(need=need)
        )
    if suggested:
        said.append(guidance.GOAL_SUGGESTED_LANDED)
    return "\n\n".join(said)


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


# A proof is on the record but the cycle is not finished with it. Both of
# these keep tonight open, for opposite reasons: PUSHED_BACK because Masterji
# read it and wants more, UNJUDGED because he never read it at all.
UNSETTLED = (CheckIn.ProofStatus.PUSHED_BACK, CheckIn.ProofStatus.UNJUDGED)

# What judging._react_to_proof's verdict means on the row. A verdict this
# doesn't know falls back to PUSHED_BACK at the call site: the model has
# answered something nobody planned for, and the safe reading of an
# unrecognised answer is the one that banks nothing. "accept" is the only word
# that opens the gate, and it has to arrive spelled exactly.
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


# How much of the series travels in the state payload. Thirty because TRACTION
# is the end of the ladder and the series only exists there: a goal that has
# recorded thirty readings has been in the terminal phase for a month, and the
# question the number answers ("is it moving") is answered by the recent stretch.
# Newest kept, oldest dropped — the same rule judging.RECORD_LIMIT follows.
METRIC_SERIES = 30


def _metric_payload(goal: Goal) -> dict | None:
    """The one number they chose to watch, and every reading of it.

    None until they name one, which is the honest state for most of the ladder:
    this is asked for at TRACTION and nowhere else, so there is no default metric
    and no placeholder series — a number the app picked is not one anybody chose
    to watch.

    Every reading carries the name it was recorded under (CheckIn.metric_label),
    so `swaps` is a count of adjacent disagreements rather than an inference from
    timestamps. That is the recorded slip: renaming before anything is counted
    leaves no mark, because nothing slipped, and renaming after three days of
    numbers shows up as the series changing what it is about. Computed over ALL
    the readings, not the window sent — a swap that scrolled off the end of the
    payload still happened.

    A day run twice can hold two readings, and both are here. The record already
    renders a repeated day as two cycles (lib/record.cycleOrdinals), and pinning
    the day to one number would mean deciding which of two things the builder
    actually did is the real one.
    """
    if not goal.metric_name:
        return None
    # Values only, oldest last. `-date` is the model's ordering and the wrong end
    # to truncate from, so the window is taken off the newest and reversed:
    # dropping the oldest readings is dropping history, dropping the newest would
    # be dropping the answer.
    rows = list(
        goal.checkins.exclude(metric_value=None).order_by("-date", "-created_at")
    )
    labels = [row.metric_label for row in reversed(rows)]
    return {
        "name": goal.metric_name,
        "series": [
            {
                "date": row.date.isoformat(),
                "value": row.metric_value,
                # What it was called that day, which is not always what it is
                # called now — that difference IS the trail.
                "label": row.metric_label,
            }
            for row in reversed(rows[:METRIC_SERIES])
        ],
        "held": len(rows),
        # How many times they changed what they were watching, counted where it
        # cost something: between two readings. Never the number of names the
        # field has held.
        "swaps": sum(1 for a, b in zip(labels, labels[1:]) if a != b),
    }


def _predecessor(goal: Goal) -> tuple[str, list[dict]] | None:
    """The goal this one came out of, and what it banked — or nothing.

    Nothing when there is no parent, and nothing when the parent banked no
    accepted proofs: naming a dead idea and then reporting that it produced
    nothing is a paragraph about failure with no facts in it, on the first
    morning of the thing that replaced it.

    Reads the parent's proofs through the same judging._banked the live goal
    uses, so the two lists cannot disagree about what a proof was.
    """
    parent = goal.pivoted_from
    if parent is None:
        return None
    banked = judging._banked(parent)
    return (parent.title, banked) if banked else None


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
        # Once, because the guidance bundle below is keyed to the same count the
        # meter renders. Two reads would be two queries and, worse, two chances
        # for the line under the goal title to be about a rung the meter above it
        # is not showing.
        gate = _gate_payload(goal)
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
                "gate": gate,
                # Null until they name one, and the control reads that: there is
                # no default date and no placeholder day, because a date the app
                # picked is not a commitment anybody made.
                "launch": _launch_payload(goal, today),
                "can_set_launch": Phase(goal.phase) in LAUNCH_PHASES,
                "ponds": [
                    {"value": p.value, "label": p.label}
                    for p in LaunchCommitment.Pond
                ],
                # The one number they chose to watch, and every reading of it.
                # Null until they name one — same rule as the launch date, and for
                # the same reason: there is no default metric, because a number the
                # app picked is not one anybody decided to watch.
                #
                # One source for two readers. The series here is the same list
                # prompts.metric_line reads, so the coach's "deposits: 3 → 5" and
                # the record card cannot come to different numbers about the same
                # days — the property days_in_phase is carried for above.
                "metric": _metric_payload(goal),
                # Off the PHASE, never off the transition into it. TRACTION is the
                # end of the ladder, so a builder who reached it before this
                # shipped has no advance left to hang an invitation on — see
                # METRIC_PHASE.
                "can_set_metric": Phase(goal.phase) is METRIC_PHASE,
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
                # Today's task as Masterji heard it in chat, waiting to fill the
                # declare box. Scoped to the builder's own date here rather than
                # served off the goal, because "still today" is a question only
                # the client's clock can answer and this is the request that
                # carries it — read back tomorrow, yesterday's draft is a task
                # nobody is doing sitting above a fresh morning's empty box.
                #
                # Top-level rather than on `today`, and that is not a detail:
                # the row it would ride on does not exist yet. An offer is what
                # there is INSTEAD of a check-in.
                "declaration_offer": (
                    goal.declaration_offer
                    if goal.declaration_offer_date == today
                    else ""
                ),
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
                # Keyed to the gate's own count, so the line under the goal
                # title is about the rung the meter beside it is showing.
                "guidance": guidance.for_phase(Phase(goal.phase), gate["have"]),
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
            content=guidance.WELCOME.format(title=goal.title),
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
    narrower than it looks. `judging._brief_from_proof` fills it when IDEA's proof is
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
                {"detail": guidance.TITLE_LOCKED}, status=status.HTTP_409_CONFLICT
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
                content=guidance.TITLE_SHARPENED.format(before=before, after=goal.title),
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
        brief = guidance.UNLOCKED_BRIEF.get(Phase(goal.phase), "") if advanced else ""
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


class MetricView(APIView):
    """Name the one number you're watching. TRACTION only.

    launch-checklist.md has said "One metric. Pick the single number that means
    'someone got the value' (payments, completed actions — not visits) and watch
    only that" for as long as the corpus has existed, and until now it was a
    sentence the server had never seen. This is the server seeing it.

    At TRACTION rather than at LAUNCH, which is where the playbook that teaches it
    is wired. LAUNCH has finish arithmetic — Need(n=3, kinds={"action": 1}) — and
    TRACTION is the phase with no PROOFS_REQUIRED entry, so it is the one whose
    last mile has no number in it at all. bar.BAR[TRACTION] already asks for this
    shape once (`returned`, `paid`), which is what makes a series here the phase's
    own bar kept over time rather than a fifth thing to have declared.

    NOTHING HERE REFUSES ANYTHING, and the shape of this view is where that is
    enforced: it writes one CharField on the goal, gates.py does not read it,
    PROOFS_REQUIRED gains no TRACTION entry (giving it one is precisely what
    at_finish_line's comment says must not happen), and a builder who never calls
    this has a phase that works exactly as it did. Same terms as the launch date.

    Re-settable, and the slip is recorded on the readings rather than here — see
    CheckIn.metric_label. Write-once was the alternative and it buys a tidier
    field at the price of a builder living out their last phase under a typo with
    a coach quoting it back, which is the trade PhaseIntentView already made the
    other way.
    """

    permission_classes = [IsAuthenticated]
    # A metric is a noun phrase — "paid deposits", "orders through the form". The
    # cap is what stops it being a sentence: the number has to fit beside a date
    # in the record and inside one line of the coach's state block, and a metric
    # you cannot say in four words is more than one metric.
    MAX_CHARS = 60

    def post(self, request, pk: int):
        goal = get_object_or_404(
            Goal.objects.filter(user=request.user, status=Goal.Status.ACTIVE), pk=pk
        )
        if Phase(goal.phase) is not METRIC_PHASE:
            return Response(
                {
                    "detail": (
                        "One number comes later — once somebody has come back or "
                        "paid, there's something to count."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        name = " ".join(str(request.data.get("name") or "").split())
        if not name:
            return Response(
                {"detail": "Name the number — the one that means somebody got the value."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(name) > self.MAX_CHARS:
            return Response(
                {"detail": "Shorter — a metric is a couple of words, not a sentence."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        goal.metric_name = name
        goal.save(update_fields=["metric_name", "updated_at"])
        logger.info(f"Goal {goal.id} watches {name!r}")
        return Response(_metric_payload(goal), status=status.HTTP_200_OK)


def _reading(raw) -> int | None:
    """One number as this product will accept it, or None.

    Split out of `_record_metric` so the chat's drafted number is filtered by
    exactly the same arithmetic the filed one is, rather than by a second copy
    of it: a draft the server would later drop is a box prefilled with something
    that cannot be banked, which is worse than a box left empty.

    Negative is refused and deliberately not clamped: every metric this phase
    can hold is a count of returns or of rupees, and a reading below zero is a
    typo, never a measurement. Zero is a reading like any other — "nobody came
    back today" is a fact about the day — so the empty answer here is None.
    """
    if raw is None or raw == "":
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return None if value < 0 else value


def _record_metric(goal: Goal, checkin: CheckIn, raw) -> bool:
    """Today's reading of the one number, if there is one to record.

    Returns whether the row changed, so the callers can put the two fields in
    their own update_fields rather than saving the whole row.

    IGNORED rather than refused whenever it cannot be recorded — wrong phase, no
    metric named, not an integer, negative. The daily loop is the one thing in
    this product that must never be held hostage by a corroborating detail: a
    stale client sending a number at LAUNCH, or a builder fat-fingering one into
    the box, must not cost them the declaration or the proof that came with it.
    That is the same call `_client_day` makes about a garbled date and the same
    one the image path makes about a dead bucket — and the response carries the
    serialized row either way, so a value that was not recorded comes back null
    rather than being reported as saved.

    Negative is refused with the rest of them, and deliberately not clamped:
    every metric this phase can hold is a count of returns or of rupees, and a
    reading below zero is a typo, never a measurement.
    """
    if Phase(goal.phase) is not METRIC_PHASE or not goal.metric_name:
        return False
    value = _reading(raw)
    if value is None:
        return False
    checkin.metric_value = value
    # Stamped from the goal at the moment the number is written, and never
    # rewritten afterwards. This is what makes renaming the metric a recorded
    # slip instead of a silent relabelling of every evening already banked.
    checkin.metric_label = goal.metric_name
    return True


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
        transition = judging._current_transition(goal)
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
        # And the draft is spent, the way declaring spends the morning's. What
        # they pressed is on the row now; a draft left beside it is an
        # alternative to a decision already made, and it would come back up the
        # moment they tapped the line to reword it.
        transition.intent_offer = ""
        transition.save(update_fields=["intent", "intent_offer"])
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

        reaction = judging._react_to_retirement(retirement, verdict, request.user.tone)
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
        # With the reaction it belongs to, and for the same reason twice over: a
        # sharpening of wording the builder has since changed is a fix for a
        # complaint nobody is making any more, and this endpoint is exactly how
        # an accepted sharpening arrives — so leaving it would put the offer
        # back on the card underneath the sentence it just became.
        checkin.sharpened = ""
        checkin.proof_ask = ""
        checkin.proof_offer = ""
        checkin.proof_missing = ""
        # And the number that was drafted with it. Cleared here and NOT with
        # metric_value below, which is the distinction this field exists to
        # hold: the recorded reading is a fact about the day that re-wording a
        # task does not un-happen, while the offer is part of a draft that has
        # just been thrown away, and a number left prefilled under a proof box
        # the builder is about to refill is a figure with nothing left on the
        # card explaining where it came from.
        checkin.metric_offer = None
        # The draft's labels go with the draft. They describe evidence for the
        # old task, and a stale subject on a row that later banks a proof would
        # credit tonight's person to work they had nothing to do with.
        checkin.subject = ""
        checkin.proof_parts = []
        fields = [
            "am_declaration",
            "due_hour",
            "declaration_fit",
            "declaration_reaction",
            "sharpened",
            "proof_ask",
            "proof_offer",
            "proof_missing",
            "metric_offer",
            "subject",
            "proof_parts",
            "updated_at",
        ]
        # Today's reading of the one number, when the builder has one this
        # morning. Deliberately NOT cleared alongside the judgement fields above:
        # those describe the task and become wrong the moment the wording changes,
        # and a count of returns or of rupees is a fact about the day that a
        # re-worded task does not un-happen.
        if _record_metric(goal, checkin, request.data.get("metric_value")):
            fields += ["metric_value", "metric_label"]
        checkin.save(update_fields=fields)
        # The morning's draft is spent the moment a task is declared, whether or
        # not this is the draft. Something is now on the hook, and an offer that
        # outlived it would sit above a card that already reads "Declared: …",
        # inviting the builder to replace their own commitment with a sentence
        # the model wrote before they made it.
        if goal.declaration_offer:
            goal.declaration_offer = ""
            goal.declaration_offer_date = None
            goal.save(
                update_fields=[
                    "declaration_offer",
                    "declaration_offer_date",
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
        # Attributed out here rather than inside the helper, which is handed a
        # goal and has never needed the check-in: the call it makes is about
        # this morning's row, and this is the innermost place that knows it.
        with llm.attributing(ModelCall.Source.CHECKIN, checkin.id):
            (
                checkin.declaration_fit,
                checkin.declaration_reaction,
                checkin.sharpened,
                checkin.proof_ask,
            ) = judging._react_to_declaration(
                checkin.goal, checkin.am_declaration, request.user.tone
            )
        checkin.save(
            update_fields=[
                "declaration_fit",
                "declaration_reaction",
                "sharpened",
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
        # The evening's reading of the one number, which is the end of the day the
        # builder actually knows it. Before the judge is called, so it lands in the
        # same save as the proof — and read by nothing in that call: the judge
        # scores the evidence, and a number the builder typed is not evidence.
        _record_metric(goal, checkin, request.data.get("metric_value"))

        # Store it if we can, but never let storage decide whether the work
        # counted: the written proof is the record, the screenshot corroborates
        # it. A dead bucket costs the image, not the day.
        if image_bytes and storage.is_configured():
            key = storage.proof_key(goal.id, checkin.id, content_type)
            if storage.put_image(key, image_bytes, content_type):
                checkin.proof_image_key = key

        verdict, reaction, labels = judging._react_to_proof(
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
        # erase them (judging._labels_from_verdict).
        if labels is not None:
            checkin.subject = labels.subject
            checkin.proof_parts = labels.parts
        checkin.coach_reaction = reaction
        brief = judging._brief_from_proof(goal, checkin)
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


# --- what the two streaming turns share ------------------------------------
#
# ChatView and WorkshopChatView open the same way: take a sentence, refuse it
# if it is empty or enormous, read the transcript back without the app's own
# notes in it, and stream NDJSON out past proxies told not to buffer.
#
# They differ in exactly three places — which model of message, whether there
# is a phase, and which tools go out — and those three stay in the views. No
# base class: a workshop turn and a coaching turn are not one thing, and the
# reopened room being handed no tools at all is the clearest proof of it.
# Something that made them look alike would be worse than the duplication.
#
# What is here is only the part where a fix applied to one and not the other
# is the bug. That is not hypothetical in this tree: guidance.py:206-208 has
# to warn in a comment that a third copy of a string lives somewhere that
# cannot import it, and that copy is the one people forget.


def _line(obj) -> str:
    """One NDJSON event.

    Was `line = lambda obj: json.dumps(obj) + "\\n"  # noqa: E731` written out
    in both `_events` — two places to disagree about the one byte every reader
    on the client splits on.
    """
    return json.dumps(obj) + "\n"


def _turn_content(request) -> tuple[str, Response | None]:
    """The builder's sentence, or the refusal to hand back in its place.

    Returned rather than raised: DRF's ValidationError renders `detail` as a
    list, and both of these are a single line the client shows as written.

    The caller decides where this falls in its own order of checks, because
    the two views genuinely disagree about it — ChatView wants a goal first,
    since without one there is nowhere to put the row; the workshop wants the
    sentence first, since a refused turn should not open a room.
    """
    content = (request.data.get("content") or "").strip()
    if not content:
        return "", Response(
            {"detail": "Say something."}, status=status.HTTP_400_BAD_REQUEST
        )
    if len(content) > settings.CHAT_MAX_CHARS:
        return "", Response(
            {"detail": "That's a lot at once. Say the part you want an answer to."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return content, None


def _history(messages, *, user_role, system_role) -> list[dict]:
    """The transcript as the model reads it, oldest first.

    SYSTEM rows are excluded, not mapped: they are the app talking about a
    turn that failed, and the only role this mapping had for them was
    "assistant" — which handed the model its own outage back as something it
    had said, on every turn after it, for as long as it stayed in the window.
    Excluded in the queryset rather than after the slice, so a run of failures
    can't push real turns out of HISTORY_LIMIT.

    Both roles are arguments because the two message models are two models
    with their own enums. Passing them in costs a line at each call site and
    buys not having to trust that both will go on spelling it "SYSTEM".
    """
    turns = messages.exclude(role=system_role).order_by("-created_at")[:HISTORY_LIMIT]
    return [
        {
            "role": "user" if m.role == user_role else "assistant",
            "content": m.content,
        }
        for m in list(turns)[::-1]
    ]


def _ndjson(events) -> StreamingHttpResponse:
    """The stream itself, with every proxy on the way (Vercel, Render) asked
    not to buffer it. A turn that arrives whole at the end is a turn the
    builder spent watching a spinner."""
    response = StreamingHttpResponse(events, content_type="application/x-ndjson")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


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
        # After the goal, deliberately: without one there is nowhere to put
        # the row, so "set a goal first" is the truer answer to an empty box.
        content, refusal = _turn_content(request)
        if refusal is not None:
            return refusal
        # Kept, where it used to be discarded: it is the row this turn's spend
        # is caused by, and the ledger has no other way back to it.
        turn = Message.objects.create(
            goal=goal, role=Message.Role.USER, phase=goal.phase, content=content
        )

        today = _client_day(request)
        checkin = _latest_checkin(goal, today)
        # The row the running draft lives on, not the day's latest cycle: once
        # a cycle is proved and closed its notes are spent, and reading them
        # back would have him chasing pieces of a proof already on the record.
        target = _offer_target(goal, today)
        # The row that opened the phase they are standing in — read once here
        # and used for both halves of the phase's line: the one they already
        # pressed goes into the system prompt below, and the row itself is what
        # a draft would be written onto. None in IDEA, always, because nothing
        # unlocked it; that absence is what keeps suggest_phase_intent out of
        # the schema in the one window PhaseIntentView would 409 in.
        transition = judging._current_transition(goal)
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
            banked=judging._banked(goal),
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
            # the coach could never tell from the phase hint. That sentence is
            # the same for every builder standing where they stand — since
            # guidance.BEATS it moves with the count, and that is still a rung
            # rather than a person. This one is about the thing they decided on
            # the morning the phase opened.
            intent=transition.intent if transition else "",
            # And the day they said they would launch, if they named one. The
            # only fact in the state block the builder put there themselves.
            launch=_launch_payload(goal, today),
            # And the one number they chose to watch, at the phase where they were
            # asked for one. The second fact in the state block the builder put
            # there themselves, and the second that refuses nothing.
            metric=_metric_payload(goal),
            # What the idea before this one taught them, when this goal is a
            # pivot. Facts, never counts: the gate has been given nothing.
            predecessor=_predecessor(goal),
        )
        history = _history(
            goal.messages,
            user_role=Message.Role.USER,
            system_role=Message.Role.SYSTEM,
        )

        # `target` is the one bound above — read once for the turn. It used to
        # be recomputed here, which cost `_open_checkin` plus `_carried_over`
        # a second time on the hottest authenticated path in the product, for
        # a value that cannot have changed: nothing between the two writes.
        # Both readers take the same object off the same `today`, so the draft
        # and the sentence explaining where it can't go can never disagree
        # about the day.
        day_closed = target is None and _day_closed(goal, today)
        return _ndjson(
            self._events(
                goal,
                system,
                history,
                target,
                day_closed=day_closed,
                # Whether today's task can still be written down, decided here
                # rather than left to the model: the tool is only on the table
                # on a morning with nothing on the hook and nothing already
                # declared, filed and closed. That makes the two failures worth
                # worrying about unreachable rather than forbidden — it cannot
                # overwrite a commitment the builder has already made, and it
                # cannot become a third route into a second cycle, which is
                # "Declare another task" and stays a button they press.
                may_declare=target is None and not day_closed,
                # The row a drafted phase line would land on, and — by being
                # None or not — whether the tool exists this turn at all. Both
                # jobs on one object rather than a flag beside it, because a
                # flag that could disagree with the row is the bug it would be
                # there to prevent.
                intent_target=transition,
                day=today,
                turn_id=turn.id,
            )
        )

    def _events(
        self,
        goal: Goal,
        system: str,
        history: list[dict],
        offer_target: CheckIn | None = None,
        day_closed: bool = False,
        may_declare: bool = False,
        intent_target: PhaseTransition | None = None,
        day: date | None = None,
        turn_id: int | None = None,
    ):
        parts: list[str] = []
        advance_proposed = False
        close_proposed = False
        offered = missing = ""
        declared = ""
        # What they said this phase would produce, as the model heard it. Kept
        # as a local until the turn ends for the reason the two above are — and
        # for one more: whether it is written at all depends on something that
        # has not happened yet when the call arrives. See the gate below.
        named = ""
        # Today's reading as the model heard it said, kept beside the draft it
        # arrived with. None means no number, which is the ordinary case and the
        # one the guard is built around — see _reading, and note that 0 is a
        # reading and does not land here.
        reading: int | None = None
        labels = bar.Labels(subject="", parts=[])
        broke = False
        # Inside the generator rather than around the call that returns it: the
        # stream is consumed after every middleware has returned, so a scope
        # opened in `post` would already have closed by the time the seam books
        # anything. Outermost here so it still holds when the ledger row is
        # written, which happens in llm._attempt's `finally` — after the last
        # chunk, and after a stream that died part-way.
        with (
            llm.attributing(ModelCall.Source.MESSAGE, turn_id),
            tracer.start_as_current_span("coach.turn") as span,
        ):
            span.set_attribute("goal.phase", goal.phase)
            span.set_attribute("llm.model", settings.LLM_MODEL)
            try:
                for kind, payload in llm.stream_chat(
                    system,
                    history,
                    tools=[
                        prompts.PROPOSE_ADVANCE_TOOL,
                        # Only on a morning it could be used — see may_declare.
                        # Handed over conditionally rather than always, because
                        # a tool in the list is a thing the model will find a
                        # reason to call, and every reason it could find on an
                        # afternoon with a task already on the hook is one this
                        # product does not want acted on.
                        *([prompts.SUGGEST_DECLARATION_TOOL] if may_declare else []),
                        # Only where there is a phase line to write — which is
                        # anywhere but IDEA, the phase nothing unlocked. The
                        # same question PhaseIntentView asks before it will
                        # accept one, asked once, here: a tool that is absent
                        # cannot be called in a window the view would 409 in,
                        # and there is no prompt sentence about that window for
                        # a later edit to soften.
                        *(
                            [prompts.SUGGEST_PHASE_INTENT_TOOL]
                            if intent_target is not None
                            else []
                        ),
                        # Opens the retire box on the goal card, and that is the
                        # whole of it — see PROPOSE_GOAL_CLOSE_TOOL, which says
                        # at length why this one has no server half. Nothing
                        # below closes a goal.
                        prompts.PROPOSE_GOAL_CLOSE_TOOL,
                        # Shaped by the phase, because the arguments ARE the
                        # phase's bar — a list per part that has a count on it.
                        # The metric name rides along so the same construction
                        # can decide whether tonight's reading is an argument at
                        # all: at any phase but METRIC_PHASE, or before the
                        # builder has named their number, it simply is not in the
                        # schema. Wrong-phase silence as a schema fact rather
                        # than a sentence in a prompt.
                        prompts.suggest_proof_tool(
                            Phase(goal.phase), goal.metric_name
                        ),
                    ],
                ):
                    if kind == "delta":
                        parts.append(payload)
                        yield _line({"t": "delta", "text": payload})
                    elif kind == "tool_call":
                        name = payload.get("name")
                        if name == "propose_phase_advance":
                            advance_proposed = True
                        elif name == "propose_goal_close":
                            # A flag and nothing else. The close itself is
                            # RetireView, reached from the box this opens, with
                            # a reason and an outcome only the builder has.
                            close_proposed = True
                        elif name == "suggest_declaration" and may_declare:
                            # One string, replaced by a later call in the same
                            # turn the way the proof draft is: a builder who
                            # changed their mind mid-conversation should find
                            # the second answer in the box, not the first.
                            #
                            # The `and may_declare` is belt and braces. The tool
                            # is not in the list above when it is false, so a
                            # call cannot arrive — but this branch is the one
                            # that writes to the goal, and a guard that is only
                            # true because of something forty lines away is a
                            # guard the next edit can move.
                            declared = str(
                                payload.get("arguments", {}).get("task") or ""
                            ).strip()
                        elif (
                            name == "suggest_phase_intent"
                            and intent_target is not None
                        ):
                            # One line, replaced by a later call in the same
                            # turn the way the two drafts above are — a builder
                            # who rewords it mid-conversation should find the
                            # second answer in the box.
                            #
                            # Whitespace-collapsed the way PhaseIntentView does
                            # it and capped at the same MAX_CHARS, read off the
                            # view rather than copied, so the box can never open
                            # holding a line the server would refuse on the way
                            # back in. Trimmed rather than dropped, as
                            # declaration_offer is: an over-long draft is one
                            # the builder can see and cut, and it is their own
                            # sentence either way. The `and intent_target is not None` is belt
                            # and braces for the reason its neighbour's is: the
                            # tool is not in the list above when there is no
                            # row, so a call cannot arrive — but this is the
                            # branch that writes, and a guard true only because
                            # of something forty lines away is a guard the next
                            # edit can move.
                            named = " ".join(
                                str(
                                    payload.get("arguments", {}).get("intent") or ""
                                ).split()
                            )[: PhaseIntentView.MAX_CHARS]
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
                            # The number half of the same draft, reassigned on
                            # every call for the reason the pair above is: a
                            # builder who corrected the figure mid-conversation
                            # should find the correction in the box, and a later
                            # call that mentions no number should not leave the
                            # earlier one sitting there attached to text that no
                            # longer says it.
                            #
                            # Re-checked against the phase and the metric here
                            # even though the argument is absent from the schema
                            # forty lines up. That absence is what makes a call
                            # impossible; this is the line that writes to the
                            # row, and a guard that is only true because of
                            # something forty lines away is a guard the next
                            # edit can move.
                            reading = (
                                _reading(arguments.get("metric_value"))
                                if Phase(goal.phase) is METRIC_PHASE
                                and goal.metric_name
                                else None
                            )
                            # Who it was about and which parts it satisfied,
                            # from the same arguments and by the same
                            # arithmetic. Kept with the draft because the
                            # unedited-draft path never reaches a model again
                            # (judging._react_to_proof accepts it outright), so this is
                            # the only moment the labels for that path exist.
                            labels = bar.labels(goal.phase, arguments)
            except Exception as e:
                logger.error(f"Chat stream failed: {e}")
                broke = True
                yield _line({"t": "error", "detail": guidance.STREAM_BROKE})

            content = "".join(parts)

            # An unlock is enough news for one message, so a phase line drafted
            # in the same breath as an advance is dropped here rather than
            # written.
            #
            # It is also, on the turn that actually advances, a line about the
            # wrong phase: `intent_target` was read before the stream, when the
            # goal was still in the phase it is about to leave, and
            # gates.try_advance runs below. Writing it would put "three
            # hostellers who'd pay" on the row that opened VALIDATION on the
            # evening BUILD opened.
            #
            # Keyed off the PROPOSAL rather than off whether the gate opened,
            # which is the conservative answer and the only one available this
            # early — but it is also the right one for the refusal: a turn that
            # asked for the next phase and was told what is still owed has no
            # room in it for "and what is this one for?" either.
            if advance_proposed:
                named = ""

            # The morning's draft, on the goal because there is no check-in yet
            # — that absence is the whole situation the tool exists for, and
            # opening a row here would be the app declaring on the builder's
            # behalf. Stamped with their own date so tomorrow does not open on
            # yesterday's task (Goal.declaration_offer_date).
            #
            # A row rather than a wire event, for the reason its evening
            # counterpart is: the client refetches state when the turn ends and
            # reads the offer off the payload with everything else, so the draft
            # outlives the turn it was made in and is still in the box tomorrow
            # morning if they close the tab tonight.
            if declared:
                goal.declaration_offer = declared[: settings.DECLARATION_MAX_CHARS]
                goal.declaration_offer_date = day
                goal.save(
                    update_fields=[
                        "declaration_offer",
                        "declaration_offer_date",
                        "updated_at",
                    ]
                )
                span.set_attribute("declaration.offered", True)
                logger.info(f"Declaration drafted for goal {goal.id}")

            # And the phase's line, onto the row that opened the phase. A row
            # rather than a wire event for the same reason the two around it
            # are: the client refetches state when the turn ends, so the draft
            # is still in the box tomorrow if they close the tab tonight.
            #
            # `intent_offer` and not `intent`. Nothing here names the phase —
            # PhaseIntentView remains the only writer of the line the coach
            # quotes back, and it is reached by a press on the card.
            if named and intent_target is not None:
                intent_target.intent_offer = named
                intent_target.save(update_fields=["intent_offer"])
                span.set_attribute("intent.offered", True)
                logger.info(f"Phase line drafted for goal {goal.id}")

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
                    # Tonight's number, on the same terms and in the same save:
                    # an OFFER, never a record. It prefills the box on the
                    # evening form and nothing else reads it — metric_value, the
                    # field the series is drawn from, is still written by
                    # _record_metric alone and still only when the builder files.
                    #
                    # Assigned unconditionally, so a redraft that heard no number
                    # clears one heard earlier. The alternative — only writing it
                    # when there is something to write — leaves a stale reading
                    # prefilled under a draft whose words no longer mention it.
                    offer_target.metric_offer = reading
                    offer_target.save(
                        update_fields=[
                            "proof_offer",
                            "proof_missing",
                            "metric_offer",
                            "subject",
                            "proof_parts",
                            "updated_at",
                        ]
                    )
                    span.set_attribute("proof.offered", True)
                    span.set_attribute("metric.offered", reading is not None)
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
                    template = (
                        guidance.OFFER_DAY_CLOSED
                        if day_closed
                        else guidance.OFFER_NO_DECLARATION
                    )
                    note = template.format(offer=offered)
                    # Streamed as well as saved, the way a gate refusal is: it
                    # belongs to the turn the builder is watching, not to the
                    # refetch a second later.
                    yield _line(
                        {"t": "delta", "text": f"\n\n{note}" if content else note}
                    )
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
                content = guidance.STREAM_BROKE
                notice = True
            elif offered and offer_target is not None and not content:
                receipt = (
                    guidance.NOTES_LANDED.format(missing=missing)
                    if missing
                    else guidance.OFFER_LANDED
                )
                yield _line({"t": "delta", "text": receipt})
                content = receipt
            elif declared and not content:
                # The same receipt one screen earlier. Reached only when the
                # whole turn was this tool call, which is the failure #310 fixed
                # in the workshop: the thing that happened landed on the card
                # beside the conversation, and the conversation showed the
                # builder's own message with nothing under it.
                yield _line({"t": "delta", "text": guidance.DECLARATION_LANDED})
                content = guidance.DECLARATION_LANDED
            elif named and not content:
                # The same receipt again, for the line about the phase. Reached
                # only when the whole turn was this tool call — #270 / #310: a
                # builder who answered "what's this phase for?" and got a blank
                # screen back has been answered by the card, on a pane they may
                # not be looking at.
                #
                # Below the advance_proposed reset above, so a turn whose line
                # was dropped cannot get a receipt for it.
                yield _line({"t": "delta", "text": guidance.PHASE_INTENT_LANDED})
                content = guidance.PHASE_INTENT_LANDED
            if advance_proposed:
                advanced, detail = gates.try_advance(goal)
                span.set_attribute("gate.advanced", advanced)
                yield _line(
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
                yield _line({"t": "close"})
            if content:
                Message.objects.create(
                    goal=goal,
                    role=Message.Role.SYSTEM if notice else Message.Role.COACH,
                    phase=goal.phase,
                    content=content,
                )
            yield _line({"t": "done"})


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
        # Before the room, deliberately: `create=True` below opens one, and an
        # empty box is not a reason to have started a workshop.
        content, refusal = _turn_content(request)
        if refusal is not None:
            return refusal
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
            refusal = guidance.REOPENED_SPENT if reopened else guidance.WORKSHOP_SPENT
            return Response(
                {"detail": refusal.format(turns=total)},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        # Kept for the same reason ChatView keeps its Message: it is the row
        # this turn's spend is caused by.
        turn = WorkshopMessage.objects.create(
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
                banked=judging._banked(goal),
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
        history = _history(
            workshop.messages,
            user_role=WorkshopMessage.Role.USER,
            system_role=WorkshopMessage.Role.SYSTEM,
        )
        return _ndjson(
            self._events(
                workshop, system, history, reopened=reopened, turn_id=turn.id
            )
        )

    def _events(
        self,
        workshop: Workshop,
        system: str,
        history: list[dict],
        reopened: bool = False,
        turn_id: int | None = None,
    ):
        parts: list[str] = []
        candidates = list(workshop.candidates or [])
        parked: list[str] = []
        suggested = ""
        brief: dict | None = None
        refused_park = False
        sketched: list[str] | None = None
        broke = False
        # Inside the generator, outermost — see ChatView._events.
        with (
            llm.attributing(ModelCall.Source.WORKSHOP_MESSAGE, turn_id),
            tracer.start_as_current_span("coach.workshop") as span,
        ):
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
                        yield _line({"t": "delta", "text": payload})
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
                            # Parked already, so this one costs nothing.
                            #
                            # Dropped silently, and that is the difference from
                            # the ceiling underneath it: `refused` paints "three
                            # is the limit — nothing else got parked", a
                            # sentence for the builder watching a suggestion
                            # fail to appear. This suggestion did appear. It is
                            # on screen, in the pile, and telling them to drop
                            # one to make room for it would be the app arguing
                            # with what they can see. Before the ceiling for the
                            # same reason: a full pile that already holds this
                            # sentence turned nothing away either.
                            #
                            # The damage a duplicate does is the slot, not the
                            # repetition: three is the whole mechanism of this
                            # room (collecting made impossible so choosing is
                            # the only move left), and a copy spends one third
                            # of it on nothing, pushing the builder into the
                            # forced choice between two ideas and an echo.
                            #
                            # judging._same_words is judging._already_banked's
                            # flattening, and deliberately the same one: case
                            # and spacing carry no more meaning in a one-liner
                            # than they do in a proof, and one rule for "is
                            # this the same sentence" is one rule to keep
                            # true. Exact after flattening and no looser, for
                            # that function's own reason — near-matching here
                            # would drop a second idea that merely rhymes with
                            # the first, which in this room is deleting the
                            # builder's thinking.
                            if any(
                                judging._same_words(c) == judging._same_words(one_liner)
                                for c in candidates
                            ):
                                logger.info(
                                    f"Workshop {workshop.id} dropped a repeat candidate"
                                )
                                continue
                            # The ceiling, refused here rather than asked for in
                            # the prompt. The prompt already says three is the
                            # limit and flips to a forced choice at it, but a
                            # limit that only exists in a prompt is a limit the
                            # model can talk itself past — the same division of
                            # labour as judging._already_banked.
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
                            drafted = judging._brief_from_workshop(arguments)
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
                yield _line({"t": "error", "detail": guidance.STREAM_BROKE})

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
                yield _line(
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
            notice = False
            if broke and not content:
                content = guidance.STREAM_BROKE
                notice = True
            elif not content:
                # The workshop's half of ChatView's OFFER_LANDED branch, and
                # the divergence #154 predicted between the two streaming
                # turns. All three of this room's tools used to be able to fire
                # with no words around them, and the turn then wrote no row and
                # streamed no delta: the builder's own message with nothing
                # under it, and the meter down one.
                #
                # Saved as the turn's content as well as streamed, so the
                # transcript and the screen agree — the refetch that ends the
                # turn reads rows, and a sentence that lived only on the wire
                # would vanish under the builder as they read it.
                #
                # Kept as a receipt for what happened and not as a stand-in for
                # an answer: it is written by the server out of what the server
                # stored, so a turn that stored nothing says nothing (the
                # helper returns "" and `if content` below skips the row).
                receipt = _workshop_receipt(parked, suggested, sketched, candidates)
                if receipt:
                    yield _line({"t": "delta", "text": receipt})
                    content = receipt
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
            # The stream's end, and nothing else on it. Bare, exactly like
            # ChatView's — the two wires are meant to look alike, and this is
            # the sentinel both of them close with.
            #
            # It used to carry `turns_used` and `turns_left`, which is a
            # sentence worth leaving here because the numbers looked like the
            # careful thing to do. The comment above them promised the meter and
            # the server's refusal threshold would be the same number, and then
            # subtracted from WORKSHOP_TURNS (15) rather than from
            # _turn_budget(workshop) — so a reopened room, whose budget is
            # REOPENED_TURNS (5), reported 14 left out of 5 after one turn. The
            # server would have refused at 4.
            #
            # Nothing ever read it, which is why nobody found it: streamWorkshopChat
            # dispatches `delta`, `candidates` and `error`, and the client takes
            # the meter off the state refetch that ends every turn
            # (_workshop_payload, which computes it against the real budget and
            # says so). A wrong number under a comment asserting the invariant it
            # breaks, in the one place structurally incapable of being noticed.
            #
            # So the fix is not a second copy computed correctly. Two sources for
            # one number is what produced this; the payload is the one the client
            # reads and the one the refusal agrees with, and it stays the only
            # one. The `sketch` event above went the same way and for the same
            # reason — the client reads `w.sketch` off that same payload.
            yield _line({"t": "done"})


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


# --- cohorts: a lens over the record, with no way to write on it -------------
#
# Four views, and between them exactly two writes: a builder creating their own
# membership row, and a builder removing it. Neither takes a user — there is no
# way to spell "somebody else" in either request — and nothing in this section
# writes to a Goal, a CheckIn, a PhaseTransition or any proof field. The board
# itself is GET and defines no other method, so every other verb is a 405 from
# DRF because the handler is absent rather than because a check refused it.
#
# There is no view here for making, renaming or deleting a cohort, and that is
# the design and not an omission: a cohort is created by staff in the admin, so
# the coordinator's whole capability is holding a code. See coach/cohorts.py.


def _cohort_payload(cohort) -> dict:
    """A cohort as a member sees it before opening its board."""
    return {"id": cohort.id, "name": cohort.name, "members": cohort.size}


class CohortsView(APIView):
    """The cohorts this builder has joined, and no sign that any other exists.

    Not a listing of cohorts. There is no endpoint that lists cohorts, by
    design: joining by code is the consent, and a directory is the thing that
    would make a code unnecessary.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"cohorts": [_cohort_payload(c) for c in cohorts.joined(request.user)]}
        )


class CohortBoardView(APIView):
    """One cohort's board: every member's counted work, ranked.

    GET and nothing else. This class deliberately has no `post`, `patch`, `put`
    or `delete` — not a stubbed one that refuses, none — because the feature's
    whole credibility is that no coordinator can bank or unbank anything, and a
    write path that exists and is guarded is one somebody can later mis-guard.

    A non-member gets the same 404 as a cohort that does not exist. The
    difference between "no such cohort" and "not yours" is itself something a
    stranger can walk to learn which cohorts there are.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        cohort = cohorts.mine(request.user, pk)
        if cohort is None:
            return Response(
                {"detail": "No cohort here."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(
            {
                "cohort": _cohort_payload(cohort),
                "board": cohorts.board(cohort, _client_day(request)),
            }
        )


class CohortJoinView(throttles.VoicedThrottleMixin, APIView):
    """Join by code. The one act in this feature that is the builder's consent.

    Idempotent: joining a cohort you are already in returns the membership you
    have. The unique constraint is conditional on the soft-delete predicate, so
    a builder who left and comes back gets a new row rather than a collision.

    Throttled, and not because 31^8 is guessable. It is a lookup keyed on a
    string a stranger supplies, and a surface like that with no ceiling of any
    kind is one whose size somebody else decides — the argument ChangelogView
    already makes for the same reason.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = throttles.THROTTLES
    throttle_scope = "cohort_join"
    throttle_message = "That's a lot of codes at once. Try again in a bit."

    def post(self, request):
        code = Cohort.normalise(request.data.get("code", ""))
        if not code:
            return Response(
                {"detail": "Type the join code your cohort gave you."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cohort = Cohort.objects.filter(join_code=code).first()
        if cohort is None:
            # Same refusal whether the code never existed or has been rotated
            # away. Rotation is how a cohort is closed to new joins, so the two
            # cases are the same event as far as anybody outside is concerned.
            return Response(
                {"detail": "No cohort with that code."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            CohortMember.objects.get_or_create(cohort=cohort, user=request.user)
        except IntegrityError:
            # Two taps racing each other. The constraint did its job and the
            # membership exists, which is what was being asked for.
            pass
        # Re-read through `joined` so the reply carries the member count the
        # board will show, computed the one way it is computed anywhere.
        joined = cohorts.mine(request.user, cohort.id)
        if joined is None:
            # Belt and braces on the race above: `mine` is the same membership
            # scope the board uses, so if it cannot see the row, neither can the
            # page this reply is about to send them to. Saying so is a refusal
            # they can act on; a 201 followed by an empty board is not.
            logger.warning(f"User {request.user.pk} joined cohort {cohort.id}, no row")
            return Response(
                {"detail": "That didn't go through — try the code again."},
                status=status.HTTP_409_CONFLICT,
            )
        logger.info(f"User {request.user.pk} joined cohort {cohort.id}")
        return Response(
            {"cohort": _cohort_payload(joined)}, status=status.HTTP_201_CREATED
        )


class CohortMembershipView(APIView):
    """Leave. DELETE only, and it removes exactly one row.

    The builder's own membership, and nothing else: their goal, their
    check-ins, their proofs and their retirements are untouched, so the day
    after they leave their record is identical. What they agreed to was being
    shown, and taking that back must cost them nothing they earned.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk: int):
        member = CohortMember.objects.filter(
            cohort_id=pk, user=request.user
        ).first()
        if member is None:
            return Response(
                {"detail": "No cohort here."}, status=status.HTTP_404_NOT_FOUND
            )
        member.delete()  # soft, like every delete in this product
        logger.info(f"User {request.user.pk} left cohort {pk}")
        return Response(status=status.HTTP_204_NO_CONTENT)
