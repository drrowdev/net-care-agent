"""Back-compat shim. Re-exports the public API from the agent package."""
from __future__ import annotations

from agent import *  # noqa: F401,F403
from agent.cli import main as _main

if __name__ == "__main__":
    _main()
