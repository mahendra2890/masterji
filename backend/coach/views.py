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
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import gates, llm, prompts, streaks
from .models import CheckIn, Goal, GoalRetirement, Message
from .serializers import (
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

WELCOME = (
    'Goal locked: "{title}". Rule one: one goal at a time, and this is yours '
    "now. You start in IDEA — write a one-paragraph problem statement and "
    "name 10 real people who have this problem. Declare today's task "
    "above, and bring me proof tonight."
)


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
                }
            )
        today = timezone.now().date()
        checkin = _latest_checkin(goal, today)
        messages = list(goal.messages.order_by("-created_at")[:HISTORY_LIMIT])[::-1]
        return Response(
            {
                "goal": GoalSerializer(goal).data,
                "gate": _gate_payload(goal),
                "streak": streaks.current_streak(goal, today),
                "today": CheckInSerializer(checkin).data if checkin else None,
                "checkins": CheckInSerializer(
                    goal.checkins.all()[:CHECKIN_HISTORY], many=True
                ).data,
                "transitions": PhaseTransitionSerializer(
                    goal.transitions.all(), many=True
                ).data,
                "messages": MessageSerializer(messages, many=True).data,
                "phases": [str(p) for p in gates.PHASE_ORDER],
                "at_finish_line": gates.at_finish_line(goal),
                "archive": archive,
                "lifetime_days": lifetime,
                "tone": request.user.tone,
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
            days_active=(timezone.now().date() - goal.created_at.date()).days + 1,
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
        checkin.save(update_fields=["am_declaration", "updated_at"])
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
        checkin.pm_proof_text = text
        checkin.proof_url = (request.data.get("url") or "").strip()
        # Rows created before the phase field existed (or by an older client)
        # get stamped on their first proof rather than staying unattributed.
        if not checkin.phase:
            checkin.phase = goal.phase

        verdict, reaction = _react_to_proof(goal, checkin, request.user.tone)
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
                "streak": streaks.current_streak(goal, timezone.now().date()),
            }
        )


def _react_to_proof(goal: Goal, checkin: CheckIn, tone: str) -> tuple[str, str]:
    """LLM garnish with a deterministic floor (transcriber's fix_punctuation
    pattern): any failure logs and falls back to accept + stock reaction, so
    the daily loop never breaks because a model call flaked."""
    try:
        system = prompts.PROOF_REACTION_SYSTEM.format(
            tone_rule=prompts.HINGLISH_RULE if tone == "HINGLISH" else "",
            phase=goal.phase,
            declared=checkin.am_declaration,
        )
        user_text = checkin.pm_proof_text
        if checkin.proof_url:
            user_text += f"\nLink: {checkin.proof_url}"
        raw = llm.complete(system, user_text)
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

        today = timezone.now().date()
        checkin = _latest_checkin(goal, today)
        system = prompts.build_system_prompt(
            goal,
            gates.gate_status(goal),
            streaks.current_streak(goal, today),
            _today_state(checkin),
            request.user.tone,
            archive=_archive(request.user),
            lifetime=streaks.lifetime_days(request.user),
        )
        history = [
            {
                "role": "user" if m.role == Message.Role.USER else "assistant",
                "content": m.content,
            }
            for m in list(goal.messages.order_by("-created_at")[:HISTORY_LIMIT])[::-1]
        ]

        response = StreamingHttpResponse(
            self._events(goal, system, history),
            content_type="application/x-ndjson",
        )
        # Ask every proxy on the way (Vercel, Render) not to buffer the stream.
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _events(self, goal: Goal, system: str, history: list[dict]):
        line = lambda obj: json.dumps(obj) + "\n"  # noqa: E731
        parts: list[str] = []
        advance_proposed = False
        with tracer.start_as_current_span("coach.turn") as span:
            span.set_attribute("goal.phase", goal.phase)
            span.set_attribute("llm.model", settings.LLM_MODEL)
            try:
                for kind, payload in llm.stream_chat(
                    system, history, tools=[prompts.PROPOSE_ADVANCE_TOOL]
                ):
                    if kind == "delta":
                        parts.append(payload)
                        yield line({"t": "delta", "text": payload})
                    elif kind == "tool_call" and payload == "propose_phase_advance":
                        advance_proposed = True
            except Exception as e:
                logger.error(f"Chat stream failed: {e}")
                yield line(
                    {"t": "error", "detail": "Masterji lost the thread — try again."}
                )

            content = "".join(parts)
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
