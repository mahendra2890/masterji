"""LLM access — one thin seam over litellm (transcriber pattern).

Provider optionality is the LLM_MODEL setting: "openai/gpt-5.4-mini" today,
"anthropic/claude-sonnet-5" tomorrow. Keys ride the env vars litellm already
understands (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...). Nothing provider-
specific may leak out of this module.
"""

import base64
import json
from collections.abc import Iterator
from typing import cast

import litellm
from django.conf import settings
from litellm import ModelResponse


def stream_chat(
    system: str, messages: list[dict], tools: list[dict] | None = None
) -> Iterator[tuple[str, str | dict]]:
    """Yield ("delta", text) chunks while the model talks; after the stream,
    ("tool_call", {"name": ..., "arguments": {...}}) once per tool it invoked.

    Arguments arrive as string fragments spread across chunks and keyed by
    index, so they are reassembled here: the seam's job is to hand the view a
    whole call, not a stream of half-parsed JSON.
    """
    response = litellm.completion(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools,
        stream=True,
        num_retries=2,
        timeout=settings.LLM_TIMEOUT_S,
    )
    calls: dict[int, dict] = {}
    for chunk in response:
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield "delta", content
        for call in getattr(delta, "tool_calls", None) or []:
            slot = calls.setdefault(
                getattr(call, "index", 0) or 0, {"name": "", "arguments": ""}
            )
            function = getattr(call, "function", None)
            # Both arrive piecemeal: the name usually lands whole in the first
            # fragment, the arguments never do.
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
    proof is graded. Uses LLM_VISION_MODEL, which defaults to LLM_MODEL.
    """
    b64 = base64.b64encode(image).decode()
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
                            "image_url": {"url": f"data:{content_type};base64,{b64}"},
                        },
                    ],
                },
            ],
            num_retries=2,
            timeout=settings.LLM_TIMEOUT_S,
        ),
    )
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()


def complete(system: str, user_text: str) -> str:
    response = cast(
        ModelResponse,
        litellm.completion(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            num_retries=2,
            timeout=settings.LLM_TIMEOUT_S,
        ),
    )
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()
