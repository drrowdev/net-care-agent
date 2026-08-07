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


@pytest.mark.parametrize(
    "treatment",
    [
        "CAPTEM",
        "hepatic artery embolization",
        "radiofrequency ablation",
        "liver resection",
        "peptide receptor radionuclide therapy",
        "TACE",
        "Y-90 radioembolization",
        "pasireotide",
        "telotristat",
        "interferon alfa",
    ],
)
def test_common_net_regimens_and_procedures_have_canonical_identity(
    agent, empty_profile, treatment
):
    empty_profile["patient"]["current_treatments"] = [treatment]
    payload = [{"text": treatment, "category": "active", "label": treatment}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["text"] == treatment


@pytest.mark.parametrize(
    "surgery",
    [
        "hepatectomy",
        "partial hepatectomy",
        "pancreatectomy",
        "debulking surgery",
        "metastasectomy",
    ],
)
def test_common_net_surgeries_have_canonical_identity(agent, empty_profile, surgery):
    empty_profile["patient"]["current_treatments"] = [surgery]
    payload = [{"text": surgery, "category": "completed", "label": surgery}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["text"] == surgery


def test_mixed_recognized_and_unknown_compound_fails_closed(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["hepatectomy and lanreotide"]
    incomplete = [{"text": "lanreotide", "category": "active", "label": "lanreotide"}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(incomplete))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


def test_mixed_known_and_custom_treatment_cannot_drop_custom_identity(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide plus TACE"]
    payload = [{"text": "lanreotide", "category": "active", "label": "lanreotide"}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


@pytest.mark.parametrize(
    "raw",
    [
        "Switched from lanreotide to ABC-123",
        "lanreotide replaced by ABC-123",
        "lanreotide versus ABC-123",
        "lanreotide vs ABC-123",
        "lanreotide with irreversible electroporation",
        "lanreotide after experimental tumor procedure",
    ],
)
def test_uncertified_residual_therapy_content_fails_closed(agent, empty_profile, raw):
    empty_profile["patient"]["current_treatments"] = [raw]
    incomplete = [{"text": "lanreotide", "category": "active", "label": "lanreotide"}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(incomplete))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


@pytest.mark.parametrize(
    "raw",
    [
        "Switched from lanreotide",
        "lanreotide stopped",
        "lanreotide currently active",
        "lanreotide depot 120 mg every 4 weeks",
    ],
)
def test_action_status_and_schedule_residuals_remain_certifiable(agent, empty_profile, raw):
    empty_profile["patient"]["current_treatments"] = [raw]
    payload = [{"text": "lanreotide", "category": "active", "label": "lanreotide"}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        assert agent.classify_treatments(empty_profile)[0]["text"] == "lanreotide"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("octreotide LAR 30 mg IM monthly", "octreotide"),
        ("Sandostatin LAR 30mg monthly", "octreotide"),
        ("everolimus 10mg PO daily", "everolimus"),
        ("octreotide 100mcg SC tid", "octreotide"),
        ("lanreotide 120mg SQ q4w", "lanreotide"),
        ("Lu-177 dotatate 7.4 GBq IV", "PRRT"),
    ],
)
def test_standard_route_formulation_frequency_and_radionuclide_qualifiers_certify(
    agent, empty_profile, raw, canonical
):
    empty_profile["patient"]["current_treatments"] = [raw]
    payload = [{"text": canonical, "category": "active", "label": canonical}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        assert agent.classify_treatments(empty_profile)[0]["text"] == canonical


def test_known_transition_components_receive_exclusive_source_mappings(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["Switched from lanreotide to everolimus"]
    payload = [
        {"text": "lanreotide", "category": "completed", "label": "lanreotide"},
        {"text": "everolimus", "category": "active", "label": "everolimus"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        classified = agent.classify_treatments(empty_profile)

    assert [item["text"] for item in classified] == ["lanreotide", "everolimus"]
    assert len({source for item in classified for source in item["source_treatment_ids"]}) == 2
    assert not (
        set(classified[0]["source_treatment_ids"]) & set(classified[1]["source_treatment_ids"])
    )


def test_unknown_drug_suffix_in_composite_cannot_be_dropped(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide plus cabozantinib"]
    incomplete = [{"text": "lanreotide", "category": "active", "label": "lanreotide"}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(incomplete))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)

    complete = [
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
        {"text": "cabozantinib", "category": "planned", "label": "cabozantinib"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(complete))):
        result = agent.classify_treatments(empty_profile)
    assert [item["text"] for item in result] == ["lanreotide", "cabozantinib"]


def test_short_alias_does_not_match_inside_narrative_word(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["surface findings plus cabozantinib"]
    payload = [
        {"text": "RFA", "category": "completed", "label": "RFA"},
        {"text": "cabozantinib", "category": "planned", "label": "cabozantinib"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)


@pytest.mark.parametrize(
    ("raw", "outputs"),
    [
        (
            "CAPTEM (capecitabine and temozolomide)",
            [{"text": "CAPTEM", "category": "active", "label": "CAPTEM"}],
        ),
        (
            "capecitabine / temozolomide",
            [{"text": "CAPTEM", "category": "active", "label": "CAPTEM"}],
        ),
    ],
)
def test_captem_expansions_canonicalize_to_one_regimen(agent, empty_profile, raw, outputs):
    empty_profile["patient"]["current_treatments"] = [raw]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(outputs))):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["text"] == "CAPTEM"


def test_captem_stays_atomic_while_additional_treatment_splits(agent, empty_profile):
    raw = "CAPTEM (capecitabine and temozolomide) plus lanreotide"
    empty_profile["patient"]["current_treatments"] = [raw]
    payload = [
        {"text": "CAPTEM", "category": "active", "label": "CAPTEM"},
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert [item["text"] for item in result] == ["CAPTEM", "lanreotide"]
    records = agent.sync_treatment_records(empty_profile)
    assert [item["text"] for item in records] == ["CAPTEM", "lanreotide"]


@pytest.mark.parametrize("separator", ["+", "&", "/", "and", "plus"])
def test_captem_parenthetical_separator_is_preserved_atomically(agent, separator):
    from agent.classify import split_treatment_components

    raw = f"CAPTEM (capecitabine {separator} temozolomide) plus lanreotide"
    assert split_treatment_components(raw) == ["CAPTEM", "lanreotide"]


@pytest.mark.parametrize(
    "raw",
    [
        "Start everolimus",
        "Stop lanreotide",
        "Hold everolimus",
        "Pause PRRT",
        "Continue octreotide",
        "Restart sunitinib",
        "Reduce everolimus dose now",
        "Everolimus dose reduced to 5 mg daily",
        "Plan to start lanreotide next week",
    ],
)
def test_treatment_action_words_are_not_canonical_identities(agent, empty_profile, raw):
    expected = next(
        name
        for name in ("everolimus", "lanreotide", "prrt", "octreotide", "sunitinib")
        if name in raw.casefold()
    )
    empty_profile["patient"]["current_treatments"] = [raw]
    payload = [{"text": expected, "category": "active", "label": expected}]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        result = agent.classify_treatments(empty_profile)
    assert result[0]["text"] == expected


def test_duplicate_contradictory_rows_for_one_identity_are_rejected(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["lanreotide"]
    payload = [
        {"text": "lanreotide", "category": "active", "label": "lanreotide"},
        {"text": "Somatuline", "category": "completed", "label": "Somatuline"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        with pytest.raises(agent.TreatmentClassificationError):
            agent.classify_treatments(empty_profile)
