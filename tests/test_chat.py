"""Tests for agent.chat — system-prompt composition.

The chat agent has to surface enough of the patient profile that a
caregiver question like "find that CT report from August" can be
answered against the actual data, not hallucinated. These tests pin
down the prompt-construction invariants.
"""

from __future__ import annotations


def _profile_with_documents(n: int) -> dict:
    return {
        "patient": {
            "age": 42,
            "sex": "male",
            "diagnosis": "neuroendocrine tumor",
            "ki67_percent": 8,
        },
        "biomarkers": [
            {
                "date": f"2026-{(i % 12) + 1:02d}-01",
                "marker": "CgA",
                "value": 100 + i,
                "unit": "ng/mL",
            }
            for i in range(50)
        ],
        "imaging": [
            {"date": f"2025-{(i % 12) + 1:02d}-15", "modality": "CT", "impression": f"Study {i}"}
            for i in range(15)
        ],
        "documents": [
            {
                "date": f"2025-{(i % 12) + 1:02d}-10",
                "type": "imaging_report",
                "summary": f"Imaging report {i}",
                "key_findings": [f"finding-{i}-a", f"finding-{i}-b"],
                "raw_text": "x" * 100,  # raw_text intentionally NOT in prompt
            }
            for i in range(n)
        ],
        "clinical_judgments": [],
        "trials_tracked": [],
        "literature_watched": [],
        "alerts": [],
    }


def test_build_chat_system_includes_all_documents(agent):
    """Every document, however old, must appear in the chat prompt — not just
    the most-recent few. Otherwise "find that report from last August" is
    unanswerable."""
    profile = _profile_with_documents(20)
    prompt = agent.build_chat_system(profile)

    assert "DOCUMENTS (20 entries" in prompt
    # Every summary string must appear
    for i in range(20):
        assert f"Imaging report {i}" in prompt, f"document {i} missing from chat prompt"


def test_build_chat_system_does_not_leak_raw_text(agent):
    """raw_text is intentionally excluded from the chat prompt to keep size
    sane — only summaries + key_findings go in."""
    profile = _profile_with_documents(5)
    prompt = agent.build_chat_system(profile)
    # raw_text is 'xxxxxx...' — none of that should appear
    assert "x" * 50 not in prompt


def test_build_chat_system_includes_full_biomarker_history(agent):
    """Older biomarkers must remain searchable via chat. The previous 30-row
    cap silently dropped older readings from sight."""
    profile = _profile_with_documents(0)
    prompt = agent.build_chat_system(profile)
    assert "BIOMARKERS (50 entries" in prompt


def test_build_chat_system_includes_full_imaging_history(agent):
    profile = _profile_with_documents(0)
    prompt = agent.build_chat_system(profile)
    assert "IMAGING (15 studies" in prompt


def test_build_chat_system_search_hint_present(agent):
    """The system prompt should explicitly point Claude at the full sections
    when asked about specific past content."""
    profile = _profile_with_documents(3)
    prompt = agent.build_chat_system(profile)
    assert "DOCUMENTS / BIOMARKERS / IMAGING sections" in prompt


def test_build_chat_system_includes_patient_context(agent):
    """Identifying context comes from the live profile (not source code)."""
    profile = _profile_with_documents(1)
    prompt = agent.build_chat_system(profile)
    assert "42-year-old male" in prompt
    assert "neuroendocrine tumor" in prompt


def test_build_chat_system_handles_empty_profile(agent, empty_profile):
    """No documents, no biomarkers — prompt must still build cleanly and
    contain the patient header."""
    prompt = agent.build_chat_system(empty_profile)
    assert "PATIENT RECORD" in prompt
    # Empty sections are simply omitted, not labelled "0 entries"
    assert "DOCUMENTS (0" not in prompt
