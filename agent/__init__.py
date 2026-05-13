"""NET/Care agent package.

Public symbols are re-exported here so existing callers (`app.py`, tests,
`net_agent.py` shim) can `from agent import …` without knowing the
internal module layout.
"""
from __future__ import annotations

# Agents
from .chat import build_chat_system, handle_chat
from .classify import classify_treatments

# Configuration & paths
from .config import (
    DATA_DIR,
    MODEL,
    MODEL_CHAT,
    MODEL_CLASSIFY,
    MODEL_EXEC_SUMMARY,
    MODEL_INTAKE,
    MODEL_ORCHESTRATOR,
    MODEL_QUESTIONS,
    PROFILE_PATH,
    REPORTS_DIR,
)
from .exec_summary import generate_executive_summary
from .intake import _treatment_similarity, run_intake
from .judgments import get_clinical_judgments_context

# LLM client (used by app.py for the legacy direct-client chat call site)
from .llm import client, strip_code_fences
from .orchestrator import run_orchestrator

# Profile
from .profile import DEFAULT_PROFILE, get_patient_summary, load_profile, save_profile
from .questions import generate_appointment_questions, generate_questions_for_profile

# Tools (registry + dispatcher + relevance + individual tool fns)
from .tools import (
    TOOLS,
    _is_relevant,
    analyze_biomarker_trends,
    execute_tool,
    search_clinical_trials,
    search_pubmed,
)

__all__ = [
    # config
    "DATA_DIR", "PROFILE_PATH", "REPORTS_DIR",
    "MODEL", "MODEL_INTAKE", "MODEL_ORCHESTRATOR",
    "MODEL_EXEC_SUMMARY", "MODEL_QUESTIONS", "MODEL_CLASSIFY", "MODEL_CHAT",
    # llm
    "client", "strip_code_fences",
    # profile
    "DEFAULT_PROFILE", "load_profile", "save_profile", "get_patient_summary",
    # tools
    "TOOLS", "_is_relevant", "execute_tool",
    "search_pubmed", "search_clinical_trials", "analyze_biomarker_trends",
    # judgments
    "get_clinical_judgments_context",
    # agents
    "run_intake", "_treatment_similarity",
    "run_orchestrator",
    "classify_treatments",
    "generate_executive_summary",
    "generate_appointment_questions", "generate_questions_for_profile",
    "build_chat_system", "handle_chat",
]
