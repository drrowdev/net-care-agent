"""Tests for agent.llm — small utility surface."""

from __future__ import annotations


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
