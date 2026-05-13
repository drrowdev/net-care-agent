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
        s = s[len("```json"):].lstrip()
    elif s.startswith("```"):
        s = s[len("```"):].lstrip()
    if s.endswith("```"):
        s = s[: -len("```")].rstrip()
    return s.strip()
