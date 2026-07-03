"""Configuration constants and runtime paths.

Reads from environment variables so production (Azure App Service) and
local dev share the same code path. Defaults match production.
"""

from __future__ import annotations

import os
from pathlib import Path

# Storage
DATA_DIR = Path(os.environ.get("DATA_DIR", "/home/data"))
PROFILE_PATH = DATA_DIR / "patient_profile.json"
REPORTS_DIR = DATA_DIR / "reports"

# Models — single env var per agent so they can be tuned independently.
_DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

MODEL_INTAKE = os.environ.get("ANTHROPIC_MODEL_INTAKE", _DEFAULT_MODEL)
MODEL_ORCHESTRATOR = os.environ.get("ANTHROPIC_MODEL_ORCHESTRATOR", _DEFAULT_MODEL)
MODEL_EXEC_SUMMARY = os.environ.get("ANTHROPIC_MODEL_EXEC_SUMMARY", _DEFAULT_MODEL)
MODEL_QUESTIONS = os.environ.get("ANTHROPIC_MODEL_QUESTIONS", _DEFAULT_MODEL)
MODEL_CLASSIFY = os.environ.get("ANTHROPIC_MODEL_CLASSIFY", _DEFAULT_MODEL)
MODEL_CHAT = os.environ.get("ANTHROPIC_MODEL_CHAT", _DEFAULT_MODEL)

# Back-compat: callers that don't care about per-agent overrides.
MODEL = _DEFAULT_MODEL

# Adaptive thinking (Sonnet 5+): let Claude decide when and how much to think.
# Passed on every messages.create call. IMPORTANT: temperature must be unset
# (or 1) whenever thinking is enabled — never send temperature=0 with this.
THINKING = {"type": "adaptive"}

# Ensemble deep-sweep: on-demand, high-effort research pass that runs several
# strong models with relaxed suppression, then synthesises a unioned report.
# Comma-separated model IDs; the synthesiser merges their reports. This is a
# read-only pre-appointment tool — it never writes findings back to the profile.
DEEPSWEEP_MODELS = [
    m.strip()
    for m in os.environ.get("ANTHROPIC_DEEPSWEEP_MODELS", "claude-fable-5,claude-opus-4-8").split(
        ","
    )
    if m.strip()
]
DEEPSWEEP_SYNTHESIS_MODEL = os.environ.get("ANTHROPIC_DEEPSWEEP_SYNTHESIS", "claude-opus-4-8")
