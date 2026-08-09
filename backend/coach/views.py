"""Masterji's API. Tenancy rule: every queryset filters by request.user,
so a foreign id 404s rather than 403s (nothing to probe). The LLM only
colors the conversation — every decision that matters (phase advancement,
proof acceptance defaults) is made in server code.

Chat streams NDJSON lines: {"t":"delta","text":...} while the coach talks,
one optional {"t":"gate",...} if a phase advance was proposed and checked,
then {"t":"done"}.
"""

import json
from datetime import date

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from loguru import logger
from opentelemetry import trace
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import bar, gates, guidance, llm, prompts, storage, streaks
from .models import (
    ChangelogEntry,
    CheckIn,
    Goal,
    GoalRetirement,
    Message,
    Phase,
    ProofAttempt,
)
from .serializers import (
    ChangelogEntrySerializer,
    CheckInSerializer,
    GoalSerializer,
    MessageSerializer,
    PhaseTransitionSerializer,
    RetirementSerializer,
)

tracer = trace.get_tracer(__name__)

HISTORY_LIMIT = 30
# Generous enough that a phase completed weeks ago still has its proofs
# available for the stepper drill-in, not just the current phase's recent few.
CHECKIN_HISTORY = 90

# Named, never pointed at. "Above" was true in no layout the product has:
# on a laptop the check-in is the LEFT column, and on a phone it is behind a
# tab you can't see while you're reading this. Both spellings sent half the
# builders looking in the wrong place on the one screen where they have no
# idea yet which half of the app does what. "Today" is the label on the card
# and on the phone tab, so it survives the breakpoint.
WHERE_TO_FILE = "Today"

WELCOME = (
    'Goal locked: "{title}". Rule one: one goal at a time, and this is yours '
    "now. You start in IDEA — write a one-paragraph problem statement, then "
    "the route to these people: one place they already are, why you think "
    "they're there, and how you'd get one conversation this week. No names "
    "needed, and you won't message anyone until VALIDATION. Talking to me "
    f"records nothing on its own — declare today's task under {WHERE_TO_FILE}, "
    "and file your proof there tonight."
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


def _open_checkin(goal: Goal, day: date) -> CheckIn | None:
    """The cycle still awaiting proof on `day`, if any. A pushed-back proof
    reopens the cycle — the builder gets to answer it, not start over."""
    return (
        CheckIn.objects.filter(goal=goal, date=day)
        .filter(Q(pm_proof_text="") | Q(proof_status=CheckIn.ProofStatus.PUSHED_BACK))
        .order_by("-created_at")
        .first()
    )


def _latest_checkin(goal: Goal, day: date) -> CheckIn | None:
    """What the dashboard shows for `day`: the open cycle if there is one,
    else the most recently completed one."""
    return _open_checkin(goal, day) or (
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
    """
    checkin = _open_checkin(goal, day)
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


def _days_active(goal: Goal, today: date) -> int:
    """The goal's span, counted on ONE calendar.

    `goal.created_at` is a server UTC timestamp while every check-in date is
    the browser's local date, so subtracting one from the other drops a day
    for anyone whose clock is ahead of UTC — a builder who worked an evening
    and then past midnight IST closed out to "1 day active · best streak 2",
    which is not a thing that can be true. Widening the span to whatever the
    check-ins already claim puts both numbers back on the same calendar
    without trusting the client for anything it can't already write.
    """
    # Materialised once: a lazy values_list would re-run the query for each
    # of the two bounds below.
    dates = list(goal.checkins.values_list("date", flat=True))
    start = min([goal.created_at.date(), *dates])
    end = max([today, *dates])
    return (end - start).days + 1


def _today_state(checkin: CheckIn | None) -> str:
    if checkin is None or not checkin.am_declaration:
        return "NO declaration yet today — demand one before anything else."
    if not checkin.pm_proof_text:
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
                }
            )
        today = _client_day(request)
        checkin = _latest_checkin(goal, today)
        messages = list(goal.messages.order_by("-created_at")[:HISTORY_LIMIT])[::-1]
        return Response(
            {
                "goal": GoalSerializer(goal).data,
                "gate": _gate_payload(goal),
                "streak": streaks.current_streak(goal, today),
                # The run that was, next to the run that is. A builder who
                # missed two days sees a zero, and a zero on its own reads as
                # "none of it happened" at exactly the moment quitting looks
                # reasonable. This was already computed for the retirement
                # record; it just never reached the dashboard.
                "best_streak": streaks.best_streak(goal),
                "today": CheckInSerializer(checkin).data if checkin else None,
                "checkins": CheckInSerializer(
                    goal.checkins.prefetch_related("attempts")[:CHECKIN_HISTORY],
                    many=True,
                ).data,
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
                "checkins": CheckInSerializer(
                    goal.checkins.prefetch_related("attempts")[:CHECKIN_HISTORY],
                    many=True,
                ).data,
                "transitions": PhaseTransitionSerializer(
                    goal.transitions.all(), many=True
                ).data,
                "streak": streaks.best_streak(goal),
            }
        )


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
        try:
            goal = serializer.save(user=request.user)
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
        logger.info(f"Goal {goal.id} created for user {request.user.id}")
        return Response(GoalSerializer(goal).data, status=status.HTTP_201_CREATED)


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
        Message.objects.create(
            goal=goal, role=Message.Role.COACH, phase=goal.phase, content=detail
        )
        if not advanced:
            logger.info(f"Gate refused advance for goal {goal.id}: {detail}")
        return Response(
            {"advanced": advanced, "phase": goal.phase, "detail": detail},
            status=status.HTTP_200_OK if advanced else status.HTTP_409_CONFLICT,
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
        retirement = GoalRetirement.objects.create(
            goal=goal,
            outcome=self.outcome,
            reason=reason,
            phase_reached=goal.phase,
            accepted_proofs=gates.accepted_proofs_total(goal),
            contact_proofs=gates.contact_proofs(goal),
            days_active=_days_active(goal, _client_day(request)),
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
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            outcome=retirement.outcome,
            verdict=verdict,
            phase=retirement.phase_reached,
            accepted_proofs=retirement.accepted_proofs,
            contact_proofs=retirement.contact_proofs,
            days=retirement.days_active,
            best_streak=retirement.best_streak,
        )
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
    """
    try:
        system = prompts.DECLARATION_SYSTEM.format(
            respect_rule=prompts.RESPECT_RULE,
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            phase=goal.phase,
            phase_rules=prompts.PHASE_RULES[Phase(goal.phase)],
            proof_hint=guidance.PROOF_HINT[Phase(goal.phase)],
        )
        raw = llm.complete(system, text)
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
        try:
            day = _parse_date(request.data.get("date"))
        except ValueError:
            return Response(
                {"detail": "Bad date."}, status=status.HTTP_400_BAD_REQUEST
            )
        # Editing the task still on the hook updates it; declaring once the
        # day's last cycle is proved opens a new one (see CheckIn's docstring
        # — real work counts when it happens, not once per calendar day).
        checkin = _open_checkin(goal, day)
        if checkin is None:
            checkin = CheckIn.objects.create(goal=goal, date=day, phase=goal.phase)
        checkin.am_declaration = text
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
        checkin.save(
            update_fields=[
                "am_declaration",
                "declaration_fit",
                "declaration_reaction",
                "proof_ask",
                "proof_offer",
                "proof_missing",
                "updated_at",
            ]
        )
        return Response(CheckInSerializer(checkin).data)


class JudgeDeclarationView(APIView):
    """The half of declaring that needs a model, on its own round-trip.

    Split from DeclareView so the morning write returns instantly. Everything
    here is optional by construction: an UNJUDGED check-in is a complete,
    usable state, so if the client never calls this, or it fails, or the
    builder proves their work before it lands, nothing is broken — the proof
    form falls back to the phase's static ask.
    """

    permission_classes = [IsAuthenticated]

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


class ProveView(APIView):
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
                {"detail": "Proof means something to show."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            day = _parse_date(request.data.get("date"))
        except ValueError:
            return Response(
                {"detail": "Bad date."}, status=status.HTTP_400_BAD_REQUEST
            )
        checkin = _open_checkin(goal, day)
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
        if checkin.pm_proof_text and checkin.proof_status == CheckIn.ProofStatus.PUSHED_BACK:
            ProofAttempt.objects.create(
                checkin=checkin,
                text=checkin.pm_proof_text,
                url=checkin.proof_url,
                image_key=checkin.proof_image_key,
                reaction=checkin.coach_reaction,
            )
            checkin.proof_image_key = ""

        checkin.pm_proof_text = text
        checkin.proof_url = (request.data.get("url") or "").strip()
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

        verdict, reaction = _react_to_proof(
            goal, checkin, request.user.tone, image_bytes, content_type or ""
        )
        checkin.proof_status = (
            CheckIn.ProofStatus.ACCEPTED
            if verdict == "accept"
            else CheckIn.ProofStatus.PUSHED_BACK
        )
        checkin.coach_reaction = reaction
        checkin.save()
        logger.info(f"Proof {checkin.proof_status} for goal {goal.id} on {day}")
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


def _react_to_proof(
    goal: Goal,
    checkin: CheckIn,
    tone: str,
    image: bytes | None = None,
    content_type: str = "",
) -> tuple[str, str]:
    """LLM garnish with a deterministic floor (transcriber's fix_punctuation
    pattern): any failure logs and falls back to accept + stock reaction, so
    the daily loop never breaks because a model call flaked.

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
    """
    offer = checkin.proof_offer.strip()
    missing = checkin.proof_missing.strip()
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
        return "accept", prompts.STOCK_OFFER_ACCEPT.get(
            tone, prompts.STOCK_OFFER_ACCEPT["ENGLISH"]
        )

    # Written archive-before-overwrite by ProveView, so by the time we're here
    # the trail already holds tonight's rejected tries — oldest first (the
    # model's Meta orders by created_at).
    tries = list(checkin.attempts.all())
    try:
        system = prompts.PROOF_REACTION_SYSTEM.format(
            substance_rule=prompts.SUBSTANCE_RULE,
            respect_rule=prompts.RESPECT_RULE,
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            phase=goal.phase,
            declared=checkin.am_declaration,
            asked_for=prompts.PROOF_ASKED_FOR.format(proof_ask=checkin.proof_ask)
            if checkin.proof_ask
            else "",
            prior_try=prompts.prior_tries(tries),
            from_offer=prompts.from_draft(offer, missing),
        )
        if image:
            system += prompts.PROOF_IMAGE_RULE
        user_text = checkin.pm_proof_text
        if checkin.proof_url:
            user_text += f"\nLink: {checkin.proof_url}"
        raw = (
            llm.complete_with_image(system, user_text, image, content_type)
            if image
            else llm.complete(system, user_text)
        )
        payload = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        verdict = payload.get("verdict", "accept")
        if verdict not in ("accept", "push_back"):
            verdict = "accept"
        return verdict, str(payload.get("reaction") or prompts.STOCK_REACTION)
    except Exception as e:
        logger.error(f"Proof reaction failed: {e}")
        return "accept", prompts.STOCK_REACTION


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

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
        Message.objects.create(
            goal=goal, role=Message.Role.USER, phase=goal.phase, content=content
        )

        today = _client_day(request)
        checkin = _latest_checkin(goal, today)
        # The row the running draft lives on, not the day's latest cycle: once
        # a cycle is proved and closed its notes are spent, and reading them
        # back would have him chasing pieces of a proof already on the record.
        target = _offer_target(goal, today)
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
        )
        history = [
            {
                "role": "user" if m.role == Message.Role.USER else "assistant",
                "content": m.content,
            }
            for m in list(goal.messages.order_by("-created_at")[:HISTORY_LIMIT])[::-1]
        ]

        target = _offer_target(goal, today)
        # Both read off the same `today`, so the draft and the sentence
        # explaining where it can't go can never disagree about the day.
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
        offered = missing = ""
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
                        elif name == "suggest_proof":
                            # The model sends the parts; bar.read does the
                            # counting, and what is still owed is arithmetic
                            # over them rather than the model's opinion of its
                            # own paragraph. Assigned as a pair, always both: a
                            # later call in the same turn replaces the draft,
                            # and a gap left over from the earlier one would
                            # describe text that is no longer there.
                            offered, missing = bar.read(
                                goal.phase, payload.get("arguments", {})
                            )
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
                    offer_target.save(
                        update_fields=["proof_offer", "proof_missing", "updated_at"]
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
            if broke and not content:
                content = STREAM_BROKE
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
            if content:
                Message.objects.create(
                    goal=goal,
                    role=Message.Role.COACH,
                    phase=goal.phase,
                    content=content,
                )
            yield line({"t": "done"})


# --- the product's own record ---------------------------------------------


class ChangelogView(APIView):
    """What has changed in Masterji, newest first.

    Public, unlike everything else here: the demo and the sign-in screen
    reach it too, and a changelog kept behind a login is a press release.
    Active rows only — an entry can be written before the change ships.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        entries = ChangelogEntry.objects.filter(is_active=True)
        return Response(
            {"entries": ChangelogEntrySerializer(entries, many=True).data}
        )
