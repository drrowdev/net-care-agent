"""Render-safety tests for the re-templatized agent prompts.

The prompt rewrites use ``[[SENTINEL]]`` placeholders filled by
``agent.llm.render_prompt``. These tests pin that every runtime injection point
is filled (no ``[[...]]`` token survives into a live prompt) and that the values
Fable's rewrite risked dropping — the orchestrator's injected judgments and the
questions agent's explicit output language — are preserved.
"""

from __future__ import annotations

import copy
import re


def _profile_with(agent, **patient):
    p = copy.deepcopy(agent.DEFAULT_PROFILE)
    p.setdefault("patient", {}).update(patient)
    p["clinical_judgments"] = [
        {"category": "constraint", "date": "2026-05-11", "text": "START-NET excluded: prior PRRT."}
    ]
    return p


def test_render_prompt_fills_and_leaves_no_tokens(agent):
    out = agent.render_prompt("Hello [[NAME]], re [[TOPIC]].", NAME="X", TOPIC="Y")
    assert out == "Hello X, re Y."


def _assert_no_sentinels(text: str):
    assert not re.search(r"\[\[[A-Z_]+\]\]", text), f"leftover sentinel in: {text[:80]}"


def test_intake_prompt_renders_without_sentinels(agent, empty_profile):
    from agent import intake
    from agent.profile import build_patient_context

    t = agent.render_prompt(
        intake.INTAKE_SYSTEM_TEMPLATE, PATIENT_CONTEXT=build_patient_context(empty_profile)
    )
    _assert_no_sentinels(t)
    assert '"document_type"' in t and '"suggested_workflows"' in t


def test_exec_summary_prompt_renders_without_sentinels(agent, empty_profile):
    from agent import exec_summary
    from agent.profile import build_patient_context, get_caregiver_relationship

    t = agent.render_prompt(
        exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE,
        PATIENT_CONTEXT=build_patient_context(empty_profile),
        CAREGIVER=get_caregiver_relationship(empty_profile),
    )
    _assert_no_sentinels(t)
    assert "OVERRIDE" in t and '"overall_status"' in t and '"best_trial"' in t


def test_orchestrator_prompt_injects_judgments_and_no_sentinels(agent):
    from agent import orchestrator
    from agent.judgments import get_clinical_judgments_context
    from agent.profile import build_patient_context, get_caregiver_relationship, get_patient_summary

    prof = _profile_with(agent)
    t = agent.render_prompt(
        orchestrator.ORCHESTRATOR_SYSTEM_TEMPLATE,
        PATIENT_CONTEXT=build_patient_context(prof),
        CAREGIVER=get_caregiver_relationship(prof),
        PATIENT_SUMMARY=get_patient_summary(prof),
        CLINICAL_JUDGMENTS=get_clinical_judgments_context(prof),
        REGION_FILTER=orchestrator._region_filter_instruction(prof),
    )
    _assert_no_sentinels(t)
    assert "START-NET" in t  # the actual judgment text is injected
    assert "HARD CONSTRAINTS" in t
    assert "## Summary" in t and "## Recommended Next Steps" in t


def test_deep_sweep_system_injects_judgments(agent):
    from agent.deep_sweep import _build_system

    prof = _profile_with(agent)
    t = _build_system(prof)
    _assert_no_sentinels(t)
    assert "START-NET" in t
    assert "EXPLORATORY DEEP-REVIEW MODE" in t


def test_questions_prompt_preserves_explicit_language(agent):
    from agent import questions as q_mod

    prof = _profile_with(agent, language="Finnish", regions_of_interest=["Finland", "Sweden"])
    t = q_mod._build_questions_system_prompt(prof)
    _assert_no_sentinels(t)
    # explicit language injection must survive (Fable's rewrite had generalised it away)
    assert "FINNISH" in t
    assert "Finland or Sweden" in t
    # enums stay exactly
    assert "Treatment|Diagnostics|Symptoms|Trials|Monitoring|Other" in t
    assert "urgent|high|medium" in t


def test_chat_prompt_has_decision_support_and_redflags(agent):
    prof = _profile_with(agent)
    t = agent.build_chat_system(prof)
    _assert_no_sentinels(t)
    assert "decision-support" in t
    assert "RED FLAGS" in t
    assert "HARD CONSTRAINTS" in t  # shared override present when judgments exist
