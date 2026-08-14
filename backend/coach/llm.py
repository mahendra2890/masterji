"""LLM access — one thin seam over litellm (transcriber pattern).

Provider optionality is the LLM_MODEL setting: "openai/gpt-5.4-mini" today,
"anthropic/claude-sonnet-5" tomorrow. Keys ride the env vars litellm already
understands (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...). Nothing provider-
specific may leak out of this module.
"""

import base64
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import cast

import litellm
from django.conf import settings
from django.core.cache import cache
from litellm import ModelResponse
from opentelemetry import trace
from opentelemetry.trace import Span

from . import spend

tracer = trace.get_tracer(__name__)

# What litellm asks for when a retry is affordable. Unchanged from the value
# that was written inline at every call site before the budget existed.
RETRIES = 2

_BREAKER_FAILURES_KEY = "llm:breaker:failures"
_BREAKER_OPEN_KEY = "llm:breaker:open"

# This request's wall-clock deadline for model calls, or None outside a
# request. Set by LlmBudgetMiddleware; see clear_budget for the other end.
_deadline: ContextVar[float | None] = ContextVar("llm_deadline", default=None)

# The request whose turn is paying for the calls on this thread, or None
# outside one. Set by LlmBudgetMiddleware beside the deadline, and a ContextVar
# for the same reason: a chat turn's generator is consumed after every
# middleware has returned, so anything handed in as an argument would have to
# survive a scope that has already closed.
#
# THE REQUEST RATHER THAN A USER ID, and this is the whole of why attribution
# works at all. Authentication here is `CookieJWTAuthentication`, a DRF
# authentication class, so it runs inside the view — not in middleware.
# Django's AuthenticationMiddleware only populates request.user from the
# SESSION, which the API does not use, so at the moment this middleware runs
# request.user is AnonymousUser on every API request, signed in or not.
# Reading the id there would book every row in this ledger to nobody, silently
# and forever, and the feature would ship green having recorded nothing.
#
# So the request is stored and the id is read in _current_actor at the moment
# the row is written — by which time DRF has authenticated and set the user
# back onto the underlying HttpRequest.
_actor_request: ContextVar[object | None] = ContextVar("llm_actor", default=None)


class LlmUnavailable(RuntimeError):
    """Refused here, without asking the provider — either this request's budget
    is spent or the breaker is open.

    A RuntimeError because every caller already treats a raised model call as
    the outage it is: the verdict lands UNJUDGED, the stream yields its error
    line, and the builder's day survives. Nothing needed teaching to catch it.
    """


def begin_budget() -> None:
    """Start this request's wall-clock budget for model calls.

    Called once per request by LlmBudgetMiddleware. Without it there is no
    deadline at all and the seam behaves exactly as it did before budgets
    existed — which is what a management command or a shell should get.
    """
    _deadline.set(time.monotonic() + settings.LLM_REQUEST_BUDGET_S)


def set_actor(request: object | None) -> None:
    """Attribute this thread's model calls to whoever is making this request.

    Called once per request by LlmBudgetMiddleware, before the view has run and
    therefore before DRF has authenticated anyone — which is exactly why this
    takes the request rather than an id. See the comment on _actor_request.
    """
    _actor_request.set(request)


def clear_actor() -> None:
    """Forget whose request this thread was serving.

    The twin of clear_budget, and there for the same case: a long-lived thread
    that is not serving a request must not inherit an actor from one that
    finished hours ago and bill a stranger for the nightly cron.
    """
    _actor_request.set(None)


def _current_actor() -> int | None:
    """The signed-in builder's id, resolved now rather than at request start.

    Never raises and never guesses. An unauthenticated request, a request that
    never reached authentication, and no request at all (the nudge cron, a
    management command, a shell) all answer None — which the ledger's nullable
    column exists to hold, because that spend is the operator's own and still
    counts.
    """
    request = _actor_request.get()
    if request is None:
        return None
    user = getattr(request, "user", None)
    # `is_authenticated` rather than truthiness: AnonymousUser is truthy and
    # has no pk, so the getattr below would answer None anyway — but only by
    # accident, and the accident stops being one the day Django changes it.
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def clear_budget() -> None:
    """Forget this thread's deadline.

    Nothing in the request path calls this — see LlmBudgetMiddleware for why
    the budget deliberately outlives the middleware. It is here so a
    long-lived thread that is NOT serving a request (a shell, a test) cannot
    inherit a deadline that expired hours ago and refuse everything.
    """
    _deadline.set(None)


def _spend(default_timeout: float) -> tuple[float, int]:
    """The timeout and retry count for the next call, given what is left of
    this request's budget.

    Retries are the first thing the budget takes away, because they are what
    turns one slow call into three. A call is only allowed to retry while
    there is room in the budget for the retries to finish.
    """
    deadline = _deadline.get()
    if deadline is None:
        return default_timeout, RETRIES
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LlmUnavailable("this request has spent its model budget")
    retries = RETRIES if remaining > default_timeout * 2 else 0
    return min(default_timeout, remaining), retries


def _breaker_is_open() -> bool:
    return cache.get(_BREAKER_OPEN_KEY) is not None


def _note_failure() -> None:
    failures = (cache.get(_BREAKER_FAILURES_KEY) or 0) + 1
    if failures >= settings.LLM_BREAKER_FAILURES:
        cache.set(_BREAKER_OPEN_KEY, True, settings.LLM_BREAKER_COOLDOWN_S)
        cache.delete(_BREAKER_FAILURES_KEY)
        return
    # The count expires on the same clock as the cooldown, so failures have to
    # be consecutive in TIME as well as in sequence — one bad call this
    # morning must not help trip a breaker this evening.
    cache.set(_BREAKER_FAILURES_KEY, failures, settings.LLM_BREAKER_COOLDOWN_S)


def _note_success() -> None:
    cache.delete(_BREAKER_FAILURES_KEY)


def _usage_attributes(carrier: object) -> dict[str, int]:
    """The three numbers litellm hands back, read defensively.

    `usage` is absent on some providers, absent on a stream that was not asked
    for it, and is sometimes a plain dict rather than an object. Nothing here
    may raise and nothing here may guess: accounting must never be the reason
    a builder's turn fails, and a token count nobody measured is worse than no
    count at all.
    """
    usage = getattr(carrier, "usage", None)
    if usage is None and isinstance(carrier, dict):
        usage = carrier.get("usage")
    if usage is None:
        return {}
    found: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(key)
        # Not `is not None`: a Mock attribute and a provider's stray string
        # both have to fall out here, and only a real integer is a token count.
        if isinstance(value, int) and not isinstance(value, bool):
            found[key] = value
    return found


class _Call:
    """One model call in flight — the span it is measured on, and the usage
    the provider has reported so far.

    The usage is accumulated rather than read at the end because a stream
    reports it on a final chunk of its own: by the time the response object
    is exhausted there is nothing left to ask.
    """

    __slots__ = ("span", "usage")

    def __init__(self, span: Span) -> None:
        self.span = span
        self.usage: dict[str, int] = {}


def _note_usage(call: _Call, carrier: object) -> None:
    found = _usage_attributes(carrier)
    if not found:
        return
    call.usage.update(found)
    for key, value in found.items():
        call.span.set_attribute(f"llm.usage.{key}", value)


@contextmanager
def _attempt(model: str, *, stream: bool, kind: str) -> Iterator[_Call]:
    """One model call: refused if the provider is already failing, counted
    either way, measured on its own span and booked to whoever asked for it.

    A span per call rather than attributes on the caller's span, because a
    single request can make several calls — a declaration and a verdict, a
    chat turn and the judgement under it. Attributes on the parent would be
    last-write-wins, which is a silent undercount of exactly the number this
    exists to produce. The ledger row follows the span for the same reason.
    """
    # Both refusals — this one and the spent budget in _spend — are raised
    # before the try below, which is what stops the breaker feeding itself: a
    # call we declined to make is not evidence about the provider, and if it
    # counted, every refusal would extend the cooldown that caused it.
    #
    # It is also why the ledger cannot be written here: a refused call reached
    # no provider and spent nothing, and a row for it would inflate the total.
    if _breaker_is_open():
        raise LlmUnavailable("the provider is failing; not asking again yet")
    span = tracer.start_span("llm.call")
    span.set_attribute("llm.model", model)
    span.set_attribute("llm.stream", stream)
    call = _Call(span)
    try:
        yield call
    except Exception:
        _note_failure()
        raise
    else:
        _note_success()
    finally:
        # In `finally`, so a call that died part-way still books what the
        # provider had already reported — a stream that failed after its usage
        # chunk really did cost that money, and dropping it would understate
        # the bill in exactly the case worth watching. spend.record never
        # raises, so this cannot turn a model outage into a failed request.
        spend.record(kind=kind, model=model, usage=call.usage, user_id=_current_actor())
        span.end()


def stream_chat(
    system: str, messages: list[dict], tools: list[dict] | None = None
) -> Iterator[tuple[str, str | dict]]:
    """Yield ("delta", text) chunks while the model talks; after the stream,
    ("tool_call", {"name": ..., "arguments": {...}}) once per tool it invoked.

    Arguments arrive as string fragments spread across chunks and keyed by
    index, so they are reassembled here: the seam's job is to hand the view a
    whole call, not a stream of half-parsed JSON.
    """
    timeout, retries = _spend(settings.LLM_TIMEOUT_S)
    calls: dict[int, dict] = {}
    with _attempt(settings.LLM_MODEL, stream=True, kind=spend.KIND_CHAT) as call:
        response = litellm.completion(
            model=settings.LLM_MODEL,
            messages=[{"role": "system", "content": system}, *messages],
            tools=tools,
            stream=True,
            # The only way a streamed call reports what it cost. litellm
            # implements this in its own wrapper, so it is not a provider
            # feature leaking through the seam.
            stream_options={"include_usage": True},
            num_retries=retries,
            timeout=timeout,
        )
        for chunk in response:
            # The usage arrives on a final chunk of its own, which carries no
            # choices at all — reading one here is what would turn accounting
            # into an IndexError in the middle of a builder's sentence.
            _note_usage(call, chunk)
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield "delta", content
            for call in getattr(delta, "tool_calls", None) or []:
                slot = calls.setdefault(
                    getattr(call, "index", 0) or 0, {"name": "", "arguments": ""}
                )
                function = getattr(call, "function", None)
                # Both arrive piecemeal: the name usually lands whole in the
                # first fragment, the arguments never do.
                slot["name"] = getattr(function, "name", None) or slot["name"]
                slot["arguments"] += getattr(function, "arguments", None) or ""
    for slot in calls.values():
        if slot["name"]:
            yield "tool_call", {
                "name": slot["name"],
                "arguments": _tool_arguments(slot["arguments"]),
            }


def _tool_arguments(raw: str) -> dict:
    """Parsed tool arguments, or {}. A model that streams malformed JSON — or
    valid JSON that isn't an object — costs the caller its arguments and never
    the whole turn: every tool here is a proposal the server re-decides anyway,
    so a call with nothing in it is a proposal that goes nowhere. Callers may
    therefore treat the result as a dict without checking."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def complete_with_image(
    system: str, user_text: str, image: bytes, content_type: str
) -> str:
    """Same contract as complete(), with a screenshot attached.

    The image is inlined as a data URL rather than passed as a link: the
    bucket is private, and handing a model a presigned URL would mean minting
    a publicly-fetchable link to a builder's private work record every time a
    proof is graded. Uses LLM_VISION_MODEL, which defaults to LLM_JUDGE_MODEL —
    the only caller is the evening's verdict, so this is a judging path that
    additionally has to see.
    """
    b64 = base64.b64encode(image).decode()
    timeout, retries = _spend(settings.LLM_TIMEOUT_S)
    with _attempt(
        settings.LLM_VISION_MODEL, stream=False, kind=spend.KIND_VISION
    ) as call:
        response = cast(
            ModelResponse,
            litellm.completion(
                model=settings.LLM_VISION_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content_type};base64,{b64}"
                                },
                            },
                        ],
                    },
                ],
                num_retries=retries,
                timeout=timeout,
            ),
        )
        _note_usage(call, response)
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()


def complete(system: str, user_text: str, model: str | None = None) -> str:
    """One turn, no stream. `model` overrides LLM_MODEL for callers whose call
    is not a conversation — settings.LLM_JUDGE_MODEL for the two that reach a
    verdict. Still a string chosen from settings, so nothing provider-specific
    crosses this seam."""
    chosen = model or settings.LLM_MODEL
    timeout, retries = _spend(settings.LLM_TIMEOUT_S)
    with _attempt(chosen, stream=False, kind=spend.KIND_COMPLETION) as call:
        response = cast(
            ModelResponse,
            litellm.completion(
                model=chosen,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
                num_retries=retries,
                timeout=timeout,
            ),
        )
        _note_usage(call, response)
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()
