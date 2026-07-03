"""Anthropic client wrapper.

Centralizes client construction so tests can swap it out and so future
retry/logging/rate-limit logic has one place to live.
"""

from __future__ import annotations

import anthropic

# Reads ANTHROPIC_API_KEY from the environment at import time. Tests stub
# anthropic.Anthropic before this module is imported (see tests/conftest.py).
client = anthropic.Anthropic()


def strip_code_fences(text: str) -> str:
    """Remove leading/trailing ```json or ``` fences that models sometimes emit."""
    s = text.strip()
    if s.startswith("```json"):
        s = s[len("```json") :].lstrip()
    elif s.startswith("```"):
        s = s[len("```") :].lstrip()
    if s.endswith("```"):
        s = s[: -len("```")].rstrip()
    return s.strip()


def first_text(resp) -> str:
    """Return the text of the first ``text`` content block in a response.

    Adaptive thinking (on by default for Sonnet 5) prepends ``thinking``
    blocks to the response, so the answer is not necessarily ``content[0]``.
    This scans for the first ``text`` block and skips thinking / tool_use
    blocks. Raises ``ValueError`` if the response has no text block (for
    example, a response truncated mid-thinking at ``max_tokens``).
    """
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise ValueError("model response contained no text block")


def render_prompt(template: str, **values: str) -> str:
    """Fill ``[[SENTINEL]]`` placeholders in a prompt template.

    Used instead of ``str.format`` for prompts that embed literal JSON schemas:
    ``format`` would require every ``{``/``}`` in the schema to be doubled, which
    is error-prone. Sentinels like ``[[PATIENT_CONTEXT]]`` sidestep that entirely
    so JSON braces stay literal. Unknown placeholders are left untouched (a render
    test asserts none remain), and a value of ``""`` cleanly removes its line's
    content without leaving a stray token.
    """
    out = template
    for key, val in values.items():
        out = out.replace(f"[[{key}]]", val)
    return out


_CACHE_CONTROL = {"type": "ephemeral"}


def cached_system(text: str) -> list[dict]:
    """Wrap a system prompt as a single cacheable block (prompt caching, P7).

    Marking the stable system prefix ephemeral lets the API reuse it at ~0.1x
    input cost (and lower latency) across the orchestrator's tool-loop iterations
    and a chat session's messages, where the prefix is re-sent unchanged. The
    5-minute TTL comfortably covers a ≤3-minute loop or a chat session. Behaviour
    is unchanged — caching is transparent.
    """
    return [{"type": "text", "text": text, "cache_control": _CACHE_CONTROL}]


def cached_tools(tools: list[dict]) -> list[dict]:
    """Return ``tools`` with a cache breakpoint on the last one.

    A ``cache_control`` on the final tool marks the whole (stable) tool array as
    cacheable, so it too is reused across loop iterations. Returns a shallow copy;
    the shared ``TOOLS`` registry is not mutated.
    """
    if not tools:
        return tools
    out = [dict(t) for t in tools]
    out[-1] = {**out[-1], "cache_control": _CACHE_CONTROL}
    return out
