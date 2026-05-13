"""Tests for agent.intake — extraction + treatment deduplication."""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm

# ── synonym dedup (function expects lowercased input — see test_treatment_matching) ──


def test_somatuline_and_lanreotide_merge(agent):
    # Same dose+frequency, only the drug-name token differs after synonym sub.
    sim = agent._treatment_similarity("somatuline 120mg q4w", "lanreotide 120mg q4w")
    assert sim >= 0.7


def test_prrt_synonyms_merge(agent):
    # Both reduce to {"prrt"} after synonym substitution.
    sim = agent._treatment_similarity("lu-177-dotatate", "177lu-octreotate")
    assert sim >= 0.5


def test_unrelated_treatments_low_similarity(agent):
    sim = agent._treatment_similarity("lanreotide", "everolimus")
    assert sim < 0.3


def test_empty_string_yields_zero(agent):
    assert agent._treatment_similarity("", "lanreotide") == 0.0
    assert agent._treatment_similarity("lanreotide", "") == 0.0


# ── run_intake end-to-end with fake LLM ─────────────────────────────────────


def test_run_intake_persists_extracted_biomarker(agent, empty_profile):
    payload = {
        "document_type": "lab_result",
        "date": "2026-04-01",
        "summary": "Routine labs",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 234,
                "unit": "ng/mL",
                "reference_range": "0-100",
                "flag": "high",
            }
        ],
        "key_findings": ["CgA elevated"],
        "suggested_workflows": ["biomarker_analysis"],
        "workflow_rationale": "CgA above reference range",
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, extracted = agent.run_intake("Routine labs\nCgA: 234 ng/mL", empty_profile)
    assert extracted["document_type"] == "lab_result"
    assert any(b.get("marker") == "CgA" for b in profile.get("biomarkers", []))
    assert any(d.get("type") == "lab_result" for d in profile.get("documents", []))
