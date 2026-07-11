"""Anthropic client wrapper.

Centralizes client construction so tests can swap it out and so future
retry/logging/rate-limit logic has one place to live.
"""

from __future__ import annotations

import os
import ssl
import time
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from typing import Any

import anthropic
import httpcore
import httpx


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


class _DeadlineByteStream(httpx.SyncByteStream):
    def __init__(
        self,
        stream: httpx.SyncByteStream,
        request: httpx.Request,
        deadline: float,
        clock: Callable[[], float],
        active_deadline: ContextVar[float | None],
    ) -> None:
        self._stream = stream
        self._request = request
        self._deadline = deadline
        self._clock = clock
        self._active_deadline = active_deadline

    def _remaining(self) -> float:
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            self.close()
            raise httpx.TimeoutException(
                "Anthropic request exceeded its overall timeout.",
                request=self._request,
            )
        return remaining

    def __iter__(self) -> Iterator[bytes]:
        iterator = iter(self._stream)
        while True:
            remaining = self._remaining()
            timeouts = self._request.extensions.get("timeout")
            if isinstance(timeouts, dict):
                configured_read = timeouts.get("read")
                timeouts["read"] = (
                    remaining if configured_read is None else min(float(configured_read), remaining)
                )
            try:
                token = self._active_deadline.set(self._deadline)
                try:
                    chunk = next(iterator)
                finally:
                    self._active_deadline.reset(token)
            except StopIteration:
                return
            self._remaining()
            yield chunk

    def close(self) -> None:
        self._stream.close()


class _DeadlineNetworkStream(httpcore.NetworkStream):
    def __init__(
        self,
        stream: httpcore.NetworkStream,
        active_deadline: ContextVar[float | None],
        clock: Callable[[], float],
    ) -> None:
        self._stream = stream
        self._active_deadline = active_deadline
        self._clock = clock

    def _timeout(
        self,
        timeout: float | None,
        exception_type: type[httpcore.TimeoutException],
    ) -> float:
        deadline = self._active_deadline.get()
        if deadline is None:
            return timeout if timeout is not None else float("inf")
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise exception_type("Anthropic request exceeded its overall timeout.")
        return remaining if timeout is None else min(timeout, remaining)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(
            max_bytes,
            self._timeout(timeout, httpcore.ReadTimeout),
        )

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(
            buffer,
            self._timeout(timeout, httpcore.WriteTimeout),
        )

    def close(self) -> None:
        self._stream.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        stream = self._stream.start_tls(
            ssl_context,
            server_hostname,
            self._timeout(timeout, httpcore.ConnectTimeout),
        )
        return _DeadlineNetworkStream(stream, self._active_deadline, self._clock)

    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)


class _DeadlineNetworkBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        backend: httpcore.NetworkBackend,
        active_deadline: ContextVar[float | None],
        clock: Callable[[], float],
    ) -> None:
        self._backend = backend
        self._active_deadline = active_deadline
        self._clock = clock

    def _timeout(self, timeout: float | None) -> float:
        deadline = self._active_deadline.get()
        if deadline is None:
            return timeout if timeout is not None else float("inf")
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise httpcore.ConnectTimeout("Anthropic request exceeded its overall timeout.")
        return remaining if timeout is None else min(timeout, remaining)

    def _wrap(self, stream: httpcore.NetworkStream) -> _DeadlineNetworkStream:
        return _DeadlineNetworkStream(stream, self._active_deadline, self._clock)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        return self._wrap(
            self._backend.connect_tcp(
                host,
                port,
                self._timeout(timeout),
                local_address,
                socket_options,
            )
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        return self._wrap(
            self._backend.connect_unix_socket(
                path,
                self._timeout(timeout),
                socket_options,
            )
        )

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class _DeadlineHTTPTransport(httpx.HTTPTransport):
    def __init__(
        self,
        active_deadline: ContextVar[float | None],
        clock: Callable[[], float],
    ) -> None:
        super().__init__(retries=0)
        self._pool._network_backend = _DeadlineNetworkBackend(
            httpcore.SyncBackend(),
            active_deadline,
            clock,
        )


class OverallTimeoutTransport(httpx.BaseTransport):
    """Apply one monotonic deadline across response headers and body streaming."""

    def __init__(
        self,
        transport: httpx.BaseTransport,
        timeout_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        active_deadline: ContextVar[float | None] | None = None,
    ) -> None:
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._active_deadline = active_deadline or ContextVar(
            "anthropic_active_deadline",
            default=None,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        deadline = self._clock() + self._timeout_seconds
        timeouts = request.extensions.get("timeout")
        if isinstance(timeouts, dict):
            for phase in ("connect", "read", "write", "pool"):
                configured = timeouts.get(phase)
                timeouts[phase] = (
                    self._timeout_seconds
                    if configured is None
                    else min(float(configured), self._timeout_seconds)
                )
        token = self._active_deadline.set(deadline)
        try:
            response = self._transport.handle_request(request)
        finally:
            self._active_deadline.reset(token)
        if self._clock() >= deadline:
            response.close()
            raise httpx.TimeoutException(
                "Anthropic request exceeded its overall timeout.",
                request=request,
            )
        response.stream = _DeadlineByteStream(
            response.stream,
            request,
            deadline,
            self._clock,
            self._active_deadline,
        )
        return response

    def close(self) -> None:
        self._transport.close()


_OVERALL_TIMEOUT = _bounded_float("ANTHROPIC_OVERALL_TIMEOUT_SECONDS", 180.0, 0.1, 290.0)
_CONNECT_TIMEOUT = _bounded_float(
    "ANTHROPIC_CONNECT_TIMEOUT_SECONDS", 5.0, 0.1, min(30.0, _OVERALL_TIMEOUT)
)
_READ_TIMEOUT = _bounded_float(
    "ANTHROPIC_READ_TIMEOUT_SECONDS", 120.0, 0.1, min(240.0, _OVERALL_TIMEOUT)
)
_TIMEOUT = httpx.Timeout(
    connect=_CONNECT_TIMEOUT,
    read=_READ_TIMEOUT,
    write=min(10.0, _OVERALL_TIMEOUT),
    pool=min(5.0, _OVERALL_TIMEOUT),
)
_ACTIVE_DEADLINE: ContextVar[float | None] = ContextVar(
    "anthropic_active_deadline",
    default=None,
)
_TRANSPORT = OverallTimeoutTransport(
    _DeadlineHTTPTransport(_ACTIVE_DEADLINE, time.monotonic),
    _OVERALL_TIMEOUT,
    active_deadline=_ACTIVE_DEADLINE,
)
_HTTP_CLIENT = httpx.Client(transport=_TRANSPORT, timeout=_TIMEOUT)


def _max_retries() -> int:
    try:
        return max(0, min(int(os.environ.get("ANTHROPIC_MAX_RETRIES", "0")), 2))
    except ValueError:
        return 0


# Reads ANTHROPIC_API_KEY from the environment at import time. Tests stub
# anthropic.Anthropic before this module is imported (see tests/conftest.py).
client = anthropic.Anthropic(
    timeout=_TIMEOUT,
    max_retries=_max_retries(),
    http_client=_HTTP_CLIENT,
)


def is_timeout_error(exc: BaseException) -> bool:
    """Return whether an SDK/HTTP exception represents an upstream timeout."""
    return isinstance(exc, httpx.TimeoutException) or "timeout" in type(exc).__name__.lower()


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
