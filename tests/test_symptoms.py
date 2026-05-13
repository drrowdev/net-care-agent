"""Tests for the symptoms log added in R2.

Backend invariants:
- Schema accepts Symptom entries with severity 1..5 and tolerates extras.
- DEFAULT_PROFILE ships an empty symptoms list.
- intake.run_intake appends AI-extracted symptoms with source=ai.
- _persist_symptoms dedupes same-day same-name entries so re-feeding
  a document does not double-log a symptom.
- get_patient_summary surfaces recent symptoms so the orchestrator and
  chat agents can act on them.
"""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def test_default_profile_includes_empty_symptoms_list(agent):
    assert agent.DEFAULT_PROFILE.get("symptoms") == []


def test_schema_validates_symptom_entry(agent):
    from agent.schema import validate_profile

    raw = {
        "patient": {"diagnosis": "neuroendocrine tumor"},
        "symptoms": [
            {
                "id": "sym_manual_20260513",
                "date": "2026-05-13",
                "symptom": "nausea",
                "severity": 3,
                "note": "after lanreotide injection",
                "related_treatment": "lanreotide",
                "source": "manual",
            }
        ],
    }
    out = validate_profile(raw)
    assert out.symptoms[0].symptom == "nausea"
    assert out.symptoms[0].severity == 3


def test_schema_rejects_out_of_range_severity(agent):
    import pytest
    from pydantic import ValidationError

    from agent.schema import validate_profile

    with pytest.raises(ValidationError):
        validate_profile({"symptoms": [{"symptom": "x", "severity": 9}]})


def test_run_intake_appends_ai_symptoms(agent, empty_profile):
    payload = {
        "document_type": "doctor_note",
        "date": "2026-05-10",
        "summary": "Patient reports grade-2 diarrhea since starting lanreotide.",
        "key_findings": [],
        "symptoms_reported": [
            {
                "symptom": "diarrhea",
                "severity": 2,
                "note": "since starting lanreotide",
                "related_treatment": "lanreotide",
            }
        ],
        "suggested_workflows": [],
        "workflow_rationale": "",
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake("Note from 2026-05-10 ...", empty_profile)
    syms = profile.get("symptoms", [])
    assert len(syms) == 1
    assert syms[0]["symptom"] == "diarrhea"
    assert syms[0]["severity"] == 2
    assert syms[0]["source"] == "ai"
    assert syms[0]["date"] == "2026-05-10"
    assert syms[0]["related_treatment"] == "lanreotide"


def test_persist_symptoms_dedupes_same_day_same_name(agent, empty_profile):
    """Feeding the same note twice must not double-log the same symptom."""
    from agent.intake import _persist_symptoms

    reported = [{"symptom": "Nausea", "severity": 3}]
    _persist_symptoms(empty_profile, reported, "2026-05-13")
    _persist_symptoms(empty_profile, reported, "2026-05-13")
    # Case-insensitive name match too:
    _persist_symptoms(empty_profile, [{"symptom": "nausea", "severity": 4}], "2026-05-13")
    assert len(empty_profile["symptoms"]) == 1


def test_persist_symptoms_different_day_creates_new_entry(agent, empty_profile):
    from agent.intake import _persist_symptoms

    _persist_symptoms(empty_profile, [{"symptom": "nausea"}], "2026-05-13")
    _persist_symptoms(empty_profile, [{"symptom": "nausea"}], "2026-05-14")
    assert len(empty_profile["symptoms"]) == 2


def test_get_patient_summary_shows_recent_symptoms(agent, empty_profile):
    empty_profile["symptoms"] = [
        {"date": "2026-05-13", "symptom": "nausea", "severity": 3, "source": "manual"},
        {"date": "2026-05-10", "symptom": "fatigue", "severity": 2, "source": "ai"},
    ]
    summary = agent.get_patient_summary(empty_profile)
    assert "Recent symptoms" in summary
    assert "nausea" in summary
    assert "fatigue" in summary
    assert "sev 3/5" in summary
    assert "(ai)" in summary  # ai-source tag on the fatigue line
