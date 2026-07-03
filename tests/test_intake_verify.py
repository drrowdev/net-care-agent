"""Tests for the quote-anchored intake verification pass (architecture-review P1)."""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def test_verify_intake_only_merges_source_anchored_candidates(agent):
    from agent import intake

    text = "Bloodwork: CgA 250 ng/mL. Plan: start lanreotide 120mg."

    def handler(**_):
        return llm_text(
            json.dumps(
                [
                    {
                        "field": "biomarkers",
                        "item": {"marker": "CgA", "value": 250, "unit": "ng/mL"},
                        "source_quote": "CgA 250 ng/mL",  # present in text
                    },
                    {
                        "field": "biomarkers",
                        "item": {"marker": "NSE", "value": 99},
                        "source_quote": "NSE 99 fabricated line",  # NOT in text
                    },
                    {
                        "field": "treatment_changes",
                        "item": "start lanreotide 120mg",
                        "source_quote": "start lanreotide 120mg",  # present
                    },
                ]
            )
        )

    extracted: dict = {"biomarkers": [], "treatment_changes": []}
    with patch_llm(agent, handler):
        added = intake._verify_intake(text, extracted)

    markers = [a["item"]["marker"] for a in added if a["field"] == "biomarkers"]
    assert "CgA" in markers
    assert "NSE" not in markers  # unanchored -> discarded (monotonic safety)
    assert "start lanreotide 120mg" in extracted["treatment_changes"]


def test_verify_intake_tolerates_bad_model_output(agent):
    from agent import intake

    with patch_llm(agent, lambda **_: llm_text("not json")):
        added = intake._verify_intake("some text", {"biomarkers": []})
    assert added == []
