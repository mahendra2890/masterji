"""LLM access — one thin seam over litellm (transcriber pattern).

Provider optionality is the LLM_MODEL setting: "openai/gpt-5.4-mini" today,
"anthropic/claude-sonnet-5" tomorrow. Keys ride the env vars litellm already
understands (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...). Nothing provider-
specific may leak out of this module.
"""

import base64
import contextvars
import json
import time
from collections.abc import Iterator
from typing import cast

import litellm
from django.conf import settings
from django.core.cache import cache
from litellm import ModelResponse
from opentelemetry import trace

# --- The meter ------------------------------------------------------------
# litellm hands back `usage` on every response and nothing was reading it, so
# three questions had no answer: what one builder costs, which prompt is
# expensive, and whether an account is abusive. Throttles cap *requests*, so an
# 8,000-character turn and a 40-character one look identical against them.
#
# Recorded as span EVENTS rather than attributes, and that is the whole design
# decision here. A request can make more than one model call — the evening's
# verdict is two, and a chat turn that pushes back is more — and attributes on
# the one open span would have each call overwrite the last, which is the
# reading most likely to be quietly wrong. Events accumulate.
#
# Free when tracing is off: `get_current_span()` returns a non-recording span
# outside a trace, `is_recording()` is False, and nothing is built. Tests and
# local dev pay nothing, which is the same bargain config/tracing.py makes.
#
# No model, no migration, no leaf — the cheapest useful version, per the issue.


def _record_usage(model: str, usage: object | None) -> None:
    """Put what a single call cost on whichever span the caller already opened
    (coach.turn, coach.workshop, or none at all)."""
    if usage is None:
        return
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.add_event(
        "llm.call",
        {
            "llm.model": model,
            "llm.prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "llm.completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        },
    )


# --- The budget and the breaker -------------------------------------------
# The product already degrades correctly per CALL: ProofStatus.UNJUDGED exists
# so a provider outage costs the gate credit and not the day. What it did not
# do is degrade per SERVICE. One prove holds its thread for a link check plus
# up to two model calls at LLM_TIMEOUT_S with num_retries=2 — roughly 180s of
# worst case — and the box runs `--workers 1 --threads 12`. Twelve of those and
# the process answers nobody, so the graceful path is reached slowly enough
# that the app is unreachable while it works.
#
# Two bounded fixes, neither of which is a queue (a queue is a second service
# on a workspace whose free instance-hours are already the binding constraint,
# DEPLOY.md §6):
#
# 1. A wall-clock budget per request. Set once per request by
#    LlmBudgetMiddleware, spent down by every call in it, so retries cannot
#    stack past it. A call that would start with nothing left does not start.
# 2. A short-lived breaker. After LLM_BREAKER_FAILURES consecutive failures,
#    the next LLM_BREAKER_COOLDOWN_S seconds fail immediately instead of paying
#    the timeout again.
#
# Both raise ProviderUnavailable, which is a subclass of RuntimeError — every
# caller here already catches RuntimeError and falls to its own floor, so the
# fast failure lands in exactly the degraded path the slow one did.
#
# The breaker counts in the Django cache, which #116 made shared: with CACHE_URL
# set, one bad afternoon is noticed once for the whole deployment rather than
# once per process. With it unset the fallback is LocMemCache and the breaker is
# per-process, which is still strictly better than no breaker and is the same
# honest limitation the throttles carry.

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "llm_deadline", default=None
)

_FAILURES_KEY = "llm:consecutive-failures"
_BREAKER_KEY = "llm:breaker-open"


class ProviderUnavailable(RuntimeError):
    """Refused before the network, by the budget or the breaker. A RuntimeError
    on purpose: every caller already has a fallback for one."""


def set_deadline(seconds: float | None) -> None:
    """Start a fresh wall-clock budget for this request. Called by
    LlmBudgetMiddleware, and reset per request rather than lazily — a
    ContextVar lives as long as its thread, and a gthread worker reuses
    threads, so a lazily-initialised deadline would be inherited by the next
    builder's request."""
    _deadline.set(None if seconds is None else time.monotonic() + seconds)


def _remaining() -> float | None:
    """Seconds left in this request's budget, or None if it has none."""
    deadline = _deadline.get()
    return None if deadline is None else deadline - time.monotonic()


def _timeout_for_call() -> float:
    """LLM_TIMEOUT_S, or whatever is left of the request's budget if that is
    less. Raises rather than starting a call there is no time to finish."""
    remaining = _remaining()
    if remaining is None:
        return float(settings.LLM_TIMEOUT_S)
    if remaining <= 0:
        raise ProviderUnavailable("request budget spent")
    return min(float(settings.LLM_TIMEOUT_S), remaining)


def _check_breaker() -> None:
    if cache.get(_BREAKER_KEY):
        raise ProviderUnavailable("provider breaker open")


def _note_failure() -> None:
    # Not cache.incr: it raises when the key is absent, and the absent key is
    # the common case (the first failure after a good stretch).
    failures = (cache.get(_FAILURES_KEY) or 0) + 1
    cache.set(_FAILURES_KEY, failures, timeout=settings.LLM_BREAKER_COOLDOWN_S)
    if failures >= settings.LLM_BREAKER_FAILURES:
        cache.set(_BREAKER_KEY, True, timeout=settings.LLM_BREAKER_COOLDOWN_S)


def _note_success() -> None:
    # Consecutive, so one good answer clears the count. A provider having a bad
    # minute should not trip a breaker an hour later.
    cache.delete(_FAILURES_KEY)


def _completion(**kwargs):
    """Every call out of this module goes through here: breaker first (cheapest
    refusal), then the budget, then the provider."""
    _check_breaker()
    kwargs["timeout"] = _timeout_for_call()
    try:
        response = litellm.completion(**kwargs)
    except Exception:
        _note_failure()
        raise
    # A streamed call has not succeeded yet — opening it returns a generator
    # that has not touched the network, and it can still die on the first
    # chunk. stream_chat marks the outcome once it knows one. Calling it here
    # would clear the failure count on every attempt during an outage, so the
    # breaker could never reach its threshold and would never open: the exact
    # failure this module exists to prevent, on the path that carries the
    # volume. (Caught by a test, not by reading.)
    if not kwargs.get("stream"):
        _note_success()
    return response


def stream_chat(
    system: str, messages: list[dict], tools: list[dict] | None = None
) -> Iterator[tuple[str, str | dict]]:
    """Yield ("delta", text) chunks while the model talks; after the stream,
    ("tool_call", {"name": ..., "arguments": {...}}) once per tool it invoked.

    Arguments arrive as string fragments spread across chunks and keyed by
    index, so they are reassembled here: the seam's job is to hand the view a
    whole call, not a stream of half-parsed JSON.
    """
    response = _completion(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools,
        stream=True,
        num_retries=2,
        # The usage totals ride a final chunk that carries no choices. Without
        # this the streamed half of the product — every chat turn — is the half
        # the meter cannot see, which is the expensive half.
        stream_options={"include_usage": True},
    )
    calls: dict[int, dict] = {}
    try:
        for chunk in response:
            # A stream fails while it is being read, not when it is opened, so
            # the breaker has to be told from in here as well as from
            # _completion. Recorded on the last chunk, which has usage and no
            # choices — hence the guard rather than an index straight in.
            _record_usage(settings.LLM_MODEL, getattr(chunk, "usage", None))
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
    except Exception:
        _note_failure()
        raise
    _note_success()
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
    response = cast(
        ModelResponse,
        _completion(
            model=settings.LLM_VISION_MODEL,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{content_type};base64,{b64}"},
                        },
                    ],
                },
            ],
            num_retries=2,
        ),
    )
    _record_usage(settings.LLM_VISION_MODEL, getattr(response, "usage", None))
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()


def complete(system: str, user_text: str, model: str | None = None) -> str:
    """One turn, no stream. `model` overrides LLM_MODEL for callers whose call
    is not a conversation — settings.LLM_JUDGE_MODEL for the two that reach a
    verdict. Still a string chosen from settings, so nothing provider-specific
    crosses this seam."""
    chosen = model or settings.LLM_MODEL
    response = cast(
        ModelResponse,
        _completion(
            model=chosen,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            num_retries=2,
        ),
    )
    _record_usage(chosen, getattr(response, "usage", None))
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()
