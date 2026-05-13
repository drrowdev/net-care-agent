"""Shared pytest fixtures.

Tests must NOT hit the network or require ANTHROPIC_API_KEY. We achieve this by:

1. Setting DATA_DIR to a temp directory at conftest module-load time (BEFORE any
   test file is imported), so that any `from agent.config import …` at a test
   file's top level sees an isolated path. Pytest's collection imports test
   modules before autouse session fixtures run, so doing this in a fixture is
   too late.
2. Stubbing ``anthropic.Anthropic`` with a fake client BEFORE importing net_agent
   (the real client would otherwise try to read ANTHROPIC_API_KEY at import time
   when the module-level ``client = anthropic.Anthropic()`` line runs).
3. Patching ``requests.get`` per-test via the ``responses`` library for any test
   that exercises PubMed or ClinicalTrials.gov.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

import pytest

# ─── Module-load: set up env BEFORE any test file imports agent.config ────────
# (pytest collects test modules before running session fixtures, so an autouse
# fixture is too late if a test file does `from agent.profile import …` at top.)
_CONFTEST_DATA_DIR = Path(
    os.environ.setdefault(
        "DATA_DIR",
        tempfile.mkdtemp(prefix="net-care-data-conftest-"),
    )
)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir() -> Path:
    """Expose the conftest-time DATA_DIR as a session fixture for tests."""
    return _CONFTEST_DATA_DIR


@pytest.fixture(scope="session", autouse=True)
def _stub_anthropic(_isolated_data_dir) -> None:
    """Replace anthropic.Anthropic with a stub that returns canned text.

    Per-test fakes can override behaviour by patching ``net_agent.client``.
    """
    import anthropic

    class _FakeMessages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            handler = self._outer._handler
            if handler is not None:
                return handler(**kwargs)
            # Default: return a single text block with empty JSON object.
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="{}")],
                stop_reason="end_turn",
            )

    class _FakeAnthropic:
        _handler = None  # tests can set this

        def __init__(self, *args, **kwargs):
            self.messages = _FakeMessages(self)

    anthropic.Anthropic = _FakeAnthropic  # type: ignore[assignment]


# ─── Per-test: load net_agent fresh after env is set ─────────────────────────


@pytest.fixture
def agent(_isolated_data_dir, monkeypatch):
    """Import (or re-import) net_agent with a per-test profile path.

    Yields the imported module. Each test starts with no profile file.
    """
    profile_path = _isolated_data_dir / "patient_profile.json"
    if profile_path.exists():
        profile_path.unlink()

    # Force a fresh import so module-level constants pick up DATA_DIR.
    sys.modules.pop("net_agent", None)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import net_agent as ag  # type: ignore  # noqa: E402

    yield ag


@pytest.fixture
def empty_profile(agent) -> dict:
    """Fresh default profile (deep copy)."""
    return json.loads(json.dumps(agent.DEFAULT_PROFILE))


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def load_fixture(fixtures_dir: Path, name: str) -> Any:
    """Read a JSON fixture by filename (without extension)."""
    return json.loads((fixtures_dir / f"{name}.json").read_text())
