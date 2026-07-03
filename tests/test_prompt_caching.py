"""Tests for prompt-caching helpers (architecture-review P7)."""

from __future__ import annotations

from agent.llm import cached_system, cached_tools


def test_cached_system_wraps_as_ephemeral_block():
    blocks = cached_system("SYSTEM PROMPT")
    assert isinstance(blocks, list) and len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert blocks[0]["text"] == "SYSTEM PROMPT"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_cached_tools_marks_last_tool_and_does_not_mutate_source():
    tools = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    out = cached_tools(tools)
    assert out[-1]["cache_control"] == {"type": "ephemeral"}
    # earlier tools untouched, source list not mutated
    assert "cache_control" not in out[0]
    assert "cache_control" not in tools[-1]


def test_cached_tools_empty_is_safe():
    assert cached_tools([]) == []
