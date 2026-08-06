"""Tests for agent.classify — treatment classifier."""

from __future__ import annotations

import json

import pytest

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


def test_llm_failure_leaves_classification_stale_for_raw_fallback(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide", "octreotide"]
    with patch_llm(agent, lambda **_: llm_text("not json at all")):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)
    assert [item["text"] for item in agent.current_treatment_records(empty_profile)] == [
        "lanreotide",
        "octreotide",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        [{"text": "lanreotide", "category": "active", "label": "lanreotide"}],
        [{"text": "everolimus", "category": "unknown", "label": "everolimus"}],
    ],
)
def test_partial_or_invalid_classification_is_rejected(agent, empty_profile, payload):
    empty_profile["patient"]["current_treatments"] = ["lanreotide", "everolimus"]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


def test_synthetic_extra_treatment_is_rejected(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide"]
    payload = [
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
        {"text": "everolimus", "category": "planned", "label": "everolimus"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


def test_collapsed_distinct_treatments_are_rejected(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide", "everolimus"]
    payload = [
        {
            "text": "lanreotide plus everolimus",
            "category": "active",
            "label": "lanreotide + everolimus",
        }
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


def test_multi_treatment_raw_entry_can_be_split_losslessly(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide plus everolimus"]
    payload = [
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
        {"text": "everolimus", "category": "planned", "label": "everolimus"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert [item["text"] for item in result] == ["lanreotide", "everolimus"]


@pytest.mark.parametrize(
    ("raw", "classified"),
    [
        (
            ["lanreotide monthly", "octreotide monthly"],
            [{"text": "monthly", "category": "active", "label": "monthly"}],
        ),
        (
            ["everolimus oral daily"],
            [{"text": "oral daily", "category": "active", "label": "oral daily"}],
        ),
    ],
)
def test_schedule_or_route_only_output_is_not_treatment_identity(
    agent, empty_profile, raw, classified
):
    empty_profile["patient"]["current_treatments"] = raw
    with patch_llm(agent, lambda **_: llm_text(json.dumps(classified))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


@pytest.mark.parametrize(
    ("raw", "output"),
    [
        ("lanreotide, 120 mg monthly", "lanreotide"),
        ("Lutetium-177 dotatate", "PRRT"),
        ("Lutetium-177", "PRRT"),
        ("Lutetium therapy", "PRRT"),
        ("lanreotide depot 120 mg every 4 weeks", "lanreotide"),
        ("Somatuline Autogel 120 mg every 28 days", "lanreotide"),
    ],
)
def test_canonical_identity_accepts_dose_punctuation_and_complete_aliases(
    agent, empty_profile, raw, output
):
    empty_profile["patient"]["current_treatments"] = [raw]
    payload = [{"text": output, "category": "active", "label": output}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["text"] == output


def test_duplicate_contradictory_rows_for_one_identity_are_rejected(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide"]
    payload = [
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
        {"text": "Somatuline", "category": "completed", "label": "Somatuline"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)
