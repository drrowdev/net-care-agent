"""Tests for agent.llm — small utility surface."""

from __future__ import annotations

import types

import httpx
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


def test_overall_timeout_transport_raises_when_stream_crosses_deadline(agent):
    from agent.llm import OverallTimeoutTransport

    class Clock:
        now = 10.0

        def __call__(self):
            return self.now

    clock = Clock()

    class CrossingStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"first"
            clock.now = 12.1
            yield b"late"

    class FakeTransport(httpx.BaseTransport):
        closed = False

        def handle_request(self, request):
            return httpx.Response(200, stream=CrossingStream())

        def close(self):
            self.closed = True

    underlying = FakeTransport()
    transport = OverallTimeoutTransport(underlying, 2.0, clock=clock)
    with httpx.Client(transport=transport) as fake_client:
        with pytest.raises(httpx.TimeoutException, match="overall timeout"):
            fake_client.get("https://anthropic.invalid/")

    assert underlying.closed


def test_overall_timeout_transport_detects_header_phase_crossing_deadline(agent):
    from agent.llm import OverallTimeoutTransport

    class Clock:
        now = 20.0

        def __call__(self):
            return self.now

    clock = Clock()

    class DelayedHeadersTransport(httpx.BaseTransport):
        closed = False

        def handle_request(self, request):
            clock.now = 23.0
            return httpx.Response(200, content=b"too late")

        def close(self):
            self.closed = True

    underlying = DelayedHeadersTransport()
    transport = OverallTimeoutTransport(underlying, 2.0, clock=clock)
    with httpx.Client(transport=transport) as fake_client:
        with pytest.raises(httpx.TimeoutException, match="overall timeout"):
            fake_client.get("https://anthropic.invalid/")

    assert underlying.closed
