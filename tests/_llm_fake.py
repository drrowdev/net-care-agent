"""Shared helpers for tests that need to inject canned LLM responses.

The conftest fake-client mechanism's `_handler` slot is best set on the
actual ``agent.client`` instance — not the ``anthropic.Anthropic`` class
— because ``agent.client`` was instantiated at the first import of
``agent.llm`` and its identity persists across the per-test ``agent``
fixture reload (the fixture only pops ``net_agent``, not the cached
``agent.*`` submodules).
"""

from __future__ import annotations

import types
from contextlib import contextmanager


def llm_text(text: str, stop_reason: str = "end_turn"):
    """Build a fake Anthropic response object containing a single text block."""
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
    )


@contextmanager
def patch_llm(agent_module, handler):
    """Temporarily install ``handler`` on the agent's live LLM client.

    ``handler`` is a callable ``(**kwargs) -> response`` matching the
    Anthropic ``messages.create`` signature.
    """
    client = agent_module.client
    previous = getattr(client, "_handler", None)
    client._handler = handler
    try:
        yield
    finally:
        if previous is None:
            try:
                del client._handler
            except AttributeError:
                pass
        else:
            client._handler = previous
