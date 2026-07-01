"""Tests for agent.llm — small utility surface."""

from __future__ import annotations

import types

import pytest


def test_strip_code_fences_json_label(agent):
    assert agent.strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_bare_triple(agent):
    assert agent.strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_no_fence(agent):
    assert agent.strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_strip_code_fences_only_leading(agent):
    """Trailing fence missing is tolerated."""
    assert agent.strip_code_fences('```json\n{"a": 1}') == '{"a": 1}'


def test_strip_code_fences_only_trailing(agent):
    """Leading fence missing is tolerated."""
    assert agent.strip_code_fences('{"a": 1}\n```') == '{"a": 1}'


def test_strip_code_fences_whitespace_padding(agent):
    assert agent.strip_code_fences('   ```json\n  {"a": 1}\n```   ') == '{"a": 1}'


def test_strip_code_fences_empty(agent):
    assert agent.strip_code_fences("") == ""


def test_first_text_returns_text_block(agent):
    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text="hello")],
        stop_reason="end_turn",
    )
    assert agent.first_text(resp) == "hello"


def test_first_text_skips_leading_thinking_block(agent):
    """Adaptive thinking (Sonnet 5) prepends a thinking block; first_text must
    skip it and return the real answer instead of crashing on `.text`."""
    resp = types.SimpleNamespace(
        content=[
            types.SimpleNamespace(type="thinking", thinking="let me reason…"),
            types.SimpleNamespace(type="text", text='{"ok": true}'),
        ],
        stop_reason="end_turn",
    )
    assert agent.first_text(resp) == '{"ok": true}'


def test_first_text_raises_when_no_text_block(agent):
    """A response truncated mid-thinking carries no text block."""
    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="thinking", thinking="…")],
        stop_reason="max_tokens",
    )
    with pytest.raises(ValueError):
        agent.first_text(resp)
