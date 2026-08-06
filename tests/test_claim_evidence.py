from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def _profile_with_evidence(agent, empty_profile):
    payload = {
        "document_type": "lab_result",
        "date": "2026-08-01",
        "summary": "CgA result.",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 234,
                "unit": "ng/mL",
                "source_quote": "CgA 234 ng/mL",
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake("CgA 234 ng/mL", empty_profile)
    return profile


def test_summary_evidence_resolves_only_catalogued_exact_spans(agent, empty_profile):
    profile = _profile_with_evidence(agent, empty_profile)
    evidence_id = next(iter(agent.build_evidence_catalog(profile)))
    summary = {
        "claim_evidence": {
            "status_rationale": [evidence_id],
            "key_concern": ["ev_invented"],
            "summary": [],
        },
        "next_actions": [
            {"action": "Discuss the result", "evidence_ids": [evidence_id]},
            {"action": "Unsupported action"},
        ],
    }

    resolved = agent.resolve_summary_evidence(profile, summary)

    assert resolved["claims"]["status_rationale"][0]["evidence_status"] == "verified"
    assert "/api/evidence/" in resolved["claims"]["status_rationale"][0]["evidence_url"]
    assert resolved["claims"]["key_concern"][0]["evidence_status"] == "invalid"
    assert resolved["claims"]["summary"][0]["evidence_status"] == "missing"
    assert resolved["actions"][0][0]["evidence_status"] == "verified"
    assert resolved["actions"][1][0]["evidence_status"] == "missing"


def test_exec_summary_receives_catalog_and_never_requires_invented_evidence(agent, empty_profile):
    profile = _profile_with_evidence(agent, empty_profile)
    evidence_id = next(iter(agent.build_evidence_catalog(profile)))
    captured = {}
    payload = {
        "overall_status": "stable",
        "status_confidence": "medium",
        "status_rationale": "One supported result.",
        "key_concern": "No urgent concern.",
        "summary": "Review with the treating team.",
        "prrt_status": "unknown",
        "prrt_rationale": "Not assessed.",
        "cga_trend": "insufficient_data",
        "cga_trend_detail": "Only one result.",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "claim_evidence": {"status_rationale": [evidence_id]},
    }

    def handler(**kwargs):
        captured["messages"] = kwargs["messages"]
        return llm_text(json.dumps(payload))

    with patch_llm(agent, handler):
        result = agent.generate_executive_summary(profile)

    assert evidence_id in captured["messages"][0]["content"]
    assert result["claim_evidence"]["status_rationale"] == [evidence_id]


def test_prrt_prompt_uses_screening_language_without_automatic_dotatate_priority(agent):
    from agent import exec_summary

    prompt = exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    assert "screening description of potential fit" in prompt
    assert "never automatically make it the top action" in prompt
    assert "this is the most important missing test" not in prompt
    assert "trial to discuss, not a patient match" in prompt


def test_evidence_prompt_cap_keeps_newest_verified_facts(agent, empty_profile):
    empty_profile["biomarkers"] = [
        {
            "id": f"bm-{index}",
            "date": f"2025-{(index // 28) % 12 + 1:02d}-{index % 28 + 1:02d}",
            "added_at": f"{index:03d}",
            "marker": f"Marker {index}",
            "value": index,
            "source_document_id": "doc_" + "a" * 32,
            "source_quote": f"Marker {index}",
            "evidence_status": "verified",
            "evidence_start": index * 10,
            "evidence_end": index * 10 + 8,
        }
        for index in range(101)
    ]

    prompt_rows = json.loads(agent.evidence_catalog_prompt(empty_profile))

    assert len(prompt_rows) == 100
    assert any(row["fact"].startswith("Biomarker Marker 100") for row in prompt_rows)
    assert not any(row["fact"].startswith("Biomarker Marker 0 =") for row in prompt_rows)
