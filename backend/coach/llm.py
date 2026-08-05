"""LLM access — one thin seam over litellm (transcriber pattern).

Provider optionality is the LLM_MODEL setting: "openai/gpt-5.4-mini" today,
"anthropic/claude-sonnet-5" tomorrow. Keys ride the env vars litellm already
understands (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...). Nothing provider-
specific may leak out of this module.
"""

from collections.abc import Iterator
from typing import cast

import litellm
from django.conf import settings
from litellm import ModelResponse


def stream_chat(
    system: str, messages: list[dict], tools: list[dict] | None = None
) -> Iterator[tuple[str, str]]:
    """Yield ("delta", text) chunks; after the stream, ("tool_call", name)
    once per tool the model invoked."""
    response = litellm.completion(
        model=settings.LLM_MODEL,
        messages=[{"role": "system", "content": system}, *messages],
        tools=tools,
        stream=True,
        num_retries=2,
    )
    tool_names: list[str] = []
    for chunk in response:
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield "delta", content
        for call in getattr(delta, "tool_calls", None) or []:
            name = getattr(getattr(call, "function", None), "name", None)
            if name:
                tool_names.append(name)
    for name in tool_names:
        yield "tool_call", name


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
        ),
    )
    content = response.choices[0].message.content
    assert content is not None
    return content.strip()
