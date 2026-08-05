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
from .models import CheckIn, Goal, Message
from .serializers import CheckInSerializer, GoalSerializer, MessageSerializer

tracer = trace.get_tracer(__name__)

HISTORY_LIMIT = 30
CHECKIN_HISTORY = 14

WELCOME = (
    'Goal locked: "{title}". Rule one: one goal at a time, and this is yours '
    "now. You start in IDEA — write a one-paragraph problem statement and "
    "name 10 real people who have this problem. Declare today's task "
    "above, and bring me proof tonight."
)


def _active_goal(user) -> Goal | None:
    return Goal.objects.filter(user=user, status=Goal.Status.ACTIVE).first()


def _parse_date(value) -> date:
    return date.fromisoformat(value) if value else timezone.now().date()


def _today_state(checkin: CheckIn | None) -> str:
    if checkin is None or not checkin.am_declaration:
        return "NO declaration yet today — demand one before anything else."
    if not checkin.pm_proof_text:
        return f'declared "{checkin.am_declaration}" — proof still owed tonight.'
    return (
        f'declared "{checkin.am_declaration}", proof submitted '
        f"({checkin.proof_status})."
    )


def _gate_payload(goal: Goal) -> dict:
    g = gates.gate_status(goal)
    return {**g, "next_phase": g["next_phase"] and str(g["next_phase"])}


class StateView(APIView):
    """Everything the dashboard needs in one payload."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = _active_goal(request.user)
        if goal is None:
            return Response({"goal": None, "tone": request.user.tone})
        today = timezone.now().date()
        checkin = CheckIn.objects.filter(goal=goal, date=today).first()
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
                "messages": MessageSerializer(messages, many=True).data,
                "phases": [str(p) for p in gates.PHASE_ORDER],
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
        goal = serializer.save(user=request.user)
        Message.objects.create(
            goal=goal,
            role=Message.Role.COACH,
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
        Message.objects.create(goal=goal, role=Message.Role.COACH, content=detail)
        if not advanced:
            logger.info(f"Gate refused advance for goal {goal.id}: {detail}")
        return Response(
            {"advanced": advanced, "phase": goal.phase, "detail": detail},
            status=status.HTTP_200_OK if advanced else status.HTTP_409_CONFLICT,
        )


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
        checkin, _ = CheckIn.objects.get_or_create(goal=goal, date=day)
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
        checkin = CheckIn.objects.filter(goal=goal, date=day).first()
        if checkin is None or not checkin.am_declaration:
            return Response(
                {"detail": "No declaration this morning — proof of what, exactly?"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        checkin.pm_proof_text = text
        checkin.proof_url = (request.data.get("url") or "").strip()

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
        Message.objects.create(goal=goal, role=Message.Role.USER, content=content)

        today = timezone.now().date()
        checkin = CheckIn.objects.filter(goal=goal, date=today).first()
        system = prompts.build_system_prompt(
            goal,
            gates.gate_status(goal),
            streaks.current_streak(goal, today),
            _today_state(checkin),
            request.user.tone,
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
                    goal=goal, role=Message.Role.COACH, content=content
                )
            yield line({"t": "done"})
