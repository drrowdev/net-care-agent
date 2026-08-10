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
    assert profile["biomarkers"][0]["flag_authority"] == "source_reported"
    assert any(d.get("type") == "lab_result" for d in profile.get("documents", []))


def test_intake_preserves_explicit_biomarker_date_and_context(agent, empty_profile):
    quote = "Plasma CgA by assay X: <5 ng/mL on 2026-04."
    payload = {
        "document_type": "lab_result",
        "date": "2026-04",
        "source_document_date": "2026-05-01",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": "<5",
                "unit": "ng/mL",
                "date": "2026-04",
                "date_kind": "collection",
                "specimen": "Plasma",
                "assay": "assay X",
                "method": None,
                "source_quote": quote,
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    row = profile["biomarkers"][0]
    assert row["value"] == "<5"
    assert row["date"] == "2026-04"
    assert row["date_precision"] == "month"
    assert row["date_kind"] == "collection"
    assert row["source_document_date"] == "2026-05-01"
    assert row["source_document_date_precision"] == "day"
    assert row["specimen"] == "Plasma"
    assert row["assay"] == "assay X"
    assert row["method"] is None


def test_intake_preserves_duplicate_facts_from_different_sources(agent, empty_profile):
    quote = "CgA 42 ng/mL."
    payload = {
        "document_type": "lab_result",
        "date": "2026-04-01",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 42,
                "unit": "ng/mL",
                "source_quote": quote,
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)
        profile, _ = agent.run_intake(quote, profile)

    assert len(profile["biomarkers"]) == 2
    assert len({row["id"] for row in profile["biomarkers"]}) == 2
    assert len({row["source_document_id"] for row in profile["biomarkers"]}) == 2
    assert all(row["date_kind"] == "clinical_unspecified" for row in profile["biomarkers"])


def test_intake_preserves_explicit_imaging_date_authority(agent, empty_profile):
    quote = "MRI liver 2026-03 showed unchanged hepatic lesions."
    payload = {
        "document_type": "imaging_report",
        "date": "2026-03",
        "source_document_date": "2026-04-01",
        "imaging_findings": {
            "modality": "MRI",
            "findings": "unchanged hepatic lesions",
            "impression": "Stored report conclusion",
            "new_lesions": False,
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    row = profile["imaging"][0]
    assert row["date"] == "2026-03"
    assert row["date_precision"] == "month"
    assert row["date_kind"] == "study"
    assert row["source_document_date"] == "2026-04-01"
    assert row["source_document_date_precision"] == "day"
    assert row["modality"] == "MRI"
    assert row["findings"] == "unchanged hepatic lesions"
    assert row["evidence_status"] == "verified"
    assert row["id"].startswith("fact_imaging_")


def test_intake_keeps_exact_modality_wording(agent, empty_profile):
    from agent.intake import INTAKE_SYSTEM_TEMPLATE

    quote = "Contrast-enhanced CT abdomen showed the stored finding."
    payload = {
        "document_type": "imaging_report",
        "date": "2026-03-15",
        "imaging_findings": {
            "modality": "Contrast-enhanced CT abdomen",
            "findings": "the stored finding",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    assert profile["imaging"][0]["modality"] == "Contrast-enhanced CT abdomen"
    assert "exact modality wording" in INTAKE_SYSTEM_TEMPLATE


def test_intake_drops_normalized_modality_not_present_verbatim(agent, empty_profile):
    quote = "68Ga-DOTATATE PET/CT showed the stored finding."
    payload = {
        "document_type": "imaging_report",
        "date": "2026-03-15",
        "imaging_findings": {
            "modality": "PET-CT",
            "findings": "the stored finding",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    assert profile["imaging"][0]["modality"] is None


def test_non_imaging_document_date_is_not_promoted_to_study_date(agent, empty_profile):
    quote = "At the visit, prior CT was described as unchanged."
    payload = {
        "document_type": "doctor_note",
        "date": "2026-03-15",
        "imaging_findings": {
            "modality": "CT",
            "findings": "prior CT was described as unchanged",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    row = profile["imaging"][0]
    assert row["date"] is None
    assert row["date_precision"] == "unknown"
    assert row["date_kind"] == "unknown"


def test_intake_never_substitutes_ingestion_day_for_missing_imaging_date(agent, empty_profile):
    quote = "CT report: indeterminate liver finding."
    payload = {
        "document_type": "imaging_report",
        "date": None,
        "source_document_date": "2026",
        "imaging_findings": {
            "modality": "CT",
            "findings": "indeterminate liver finding",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    row = profile["imaging"][0]
    assert row["date"] is None
    assert row["date_precision"] == "unknown"
    assert row["date_kind"] == "unknown"
    assert row["source_document_date"] == "2026"
    assert row["source_document_date_precision"] == "year"


def test_intake_preserves_unsupported_imaging_date_as_explicitly_unknown(agent, empty_profile):
    quote = "CT report dated Spring 2026: indeterminate liver finding."
    payload = {
        "document_type": "imaging_report",
        "date": "Spring 2026",
        "imaging_findings": {
            "modality": "CT",
            "findings": "indeterminate liver finding",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)

    row = profile["imaging"][0]
    assert row["date"] == "Spring 2026"
    assert row["date_precision"] == "unknown"
    assert row["date_kind"] == "unknown"


def test_intake_keeps_duplicate_imaging_imports_distinct(agent, empty_profile):
    quote = "CT 2026-05-01: exact stored finding."
    payload = {
        "document_type": "imaging_report",
        "date": "2026-05-01",
        "imaging_findings": {
            "modality": "CT",
            "findings": "exact stored finding",
            "source_quote": quote,
        },
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(quote, empty_profile)
        profile, _ = agent.run_intake(quote, profile)

    assert len(profile["imaging"]) == 2
    assert len({row["id"] for row in profile["imaging"]}) == 2
    assert len({row["source_document_id"] for row in profile["imaging"]}) == 2
