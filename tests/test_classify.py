"""Tests for agent.classify — treatment classifier."""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def test_empty_treatments_returns_empty_list(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = []
    assert agent.classify_treatments(empty_profile) == []


def test_classifier_parses_llm_json(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["Somatuline 120mg q3w", "lanreotide"]
    payload = json.dumps(
        [
            {
                "text": "Somatuline (lanreotide) 120mg q3w",
                "category": "active",
                "label": "Somatuline 120mg q3w",
                "date": "2025-01",
            }
        ]
    )
    with patch_llm(agent, lambda **_: llm_text(payload)):
        result = agent.classify_treatments(empty_profile)
    assert len(result) == 1
    assert result[0]["category"] == "active"
    assert "Somatuline" in result[0]["label"]


def test_manual_override_preserved(agent, empty_profile):
    """If the user marked a treatment 'completed' via the UI, a subsequent
    automatic reclassification must not silently revert it."""
    empty_profile["patient"]["current_treatments"] = ["lanreotide"]
    empty_profile["treatments_classified"] = [
        {"text": "lanreotide", "label": "lanreotide", "category": "completed", "date": "2024-12"}
    ]
    payload = json.dumps(
        [{"text": "lanreotide", "category": "active", "label": "lanreotide", "date": "2025-01"}]
    )
    with patch_llm(agent, lambda **_: llm_text(payload)):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["category"] == "completed"


def test_llm_failure_falls_back_to_active(agent, empty_profile):
    """If the LLM returns invalid JSON, every raw treatment becomes 'active'
    (conservative — prefer false-positive over dropping treatments)."""
    empty_profile["patient"]["current_treatments"] = ["lanreotide", "octreotide"]
    with patch_llm(agent, lambda **_: llm_text("not json at all")):
        result = agent.classify_treatments(empty_profile)
    assert len(result) == 2
    assert all(t["category"] == "active" for t in result)
