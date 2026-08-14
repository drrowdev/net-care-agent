"""Tests for agent.treatment_identity — the deterministic treatment library.

The LLM classification pass was retired. What survives is pure text analysis
that produces stable ``tx_*`` component identity, so these tests pin the
clinical alias/certifiability/splitting surface that the retired classifier
used to exercise indirectly.
"""

from __future__ import annotations

import pytest

from agent.treatment_identity import (
    split_treatment_components,
    treatment_identity_set,
    treatment_text_is_certifiable,
)


def test_module_makes_no_model_calls_and_has_no_profile_dependency():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "agent" / "treatment_identity.py").read_text(
        encoding="utf-8"
    )
    assert "messages.create" not in source
    assert "from .llm import" not in source
    assert "from .profile import" not in source


def test_classify_shim_still_re_exports_the_deterministic_helpers():
    """profile.sync_treatment_records and the frozen v6 migration import here.

    Compared by behaviour, not identity: the ``agent`` fixture reloads modules,
    so a reloaded ``agent.classify`` legitimately holds a different function
    object than the one imported at module scope here.
    """
    from agent import classify

    assert classify.split_treatment_components("lanreotide plus everolimus") == [
        "lanreotide",
        "everolimus",
    ]
    assert classify.treatment_identity_set("Somatuline 120mg") == {"lanreotide"}
    assert classify.treatment_text_is_certifiable("lanreotide 120mg q4w")
    assert classify.__all__ == [
        "split_treatment_components",
        "treatment_identity_set",
        "treatment_text_is_certifiable",
    ]


@pytest.mark.parametrize(
    ("raw", "identity"),
    [
        ("lanreotide, 120 mg monthly", "lanreotide"),
        ("Lutetium-177 dotatate", "prrt"),
        ("Lutetium-177", "prrt"),
        ("Lutetium therapy", "prrt"),
        ("lanreotide depot 120 mg every 4 weeks", "lanreotide"),
        ("Somatuline Autogel 120 mg every 28 days", "lanreotide"),
    ],
)
def test_canonical_identity_accepts_dose_punctuation_and_complete_aliases(raw, identity):
    assert treatment_identity_set(raw) == {identity}
    assert treatment_text_is_certifiable(raw)


@pytest.mark.parametrize(
    ("treatment", "identity"),
    [
        ("CAPTEM", "captem"),
        ("hepatic artery embolization", "hepatic_artery_embolization"),
        ("radiofrequency ablation", "radiofrequency_ablation"),
        ("liver resection", "liver_resection"),
        ("peptide receptor radionuclide therapy", "prrt"),
        ("TACE", "tace"),
        ("Y-90 radioembolization", "y90_radioembolization"),
        ("pasireotide", "pasireotide"),
        ("telotristat", "telotristat"),
        ("interferon alfa", "interferon_alfa"),
    ],
)
def test_common_net_regimens_and_procedures_have_canonical_identity(treatment, identity):
    assert treatment_identity_set(treatment) == {identity}
    assert treatment_text_is_certifiable(treatment)


@pytest.mark.parametrize(
    ("surgery", "identity"),
    [
        ("hepatectomy", "liver_resection"),
        ("partial hepatectomy", "liver_resection"),
        ("pancreatectomy", "pancreatectomy"),
        ("debulking surgery", "cytoreductive_surgery"),
        ("metastasectomy", "metastasectomy"),
    ],
)
def test_common_net_surgeries_have_canonical_identity(surgery, identity):
    assert treatment_identity_set(surgery) == {identity}
    assert treatment_text_is_certifiable(surgery)


@pytest.mark.parametrize(
    "raw",
    [
        "Switched from lanreotide",
        "lanreotide stopped",
        "lanreotide currently active",
        "lanreotide depot 120 mg every 4 weeks",
    ],
)
def test_action_status_and_schedule_residuals_remain_certifiable(raw):
    assert treatment_identity_set(raw) == {"lanreotide"}
    assert treatment_text_is_certifiable(raw)


@pytest.mark.parametrize(
    ("raw", "identity"),
    [
        ("octreotide LAR 30 mg IM monthly", "octreotide"),
        ("Sandostatin LAR 30mg monthly", "octreotide"),
        ("everolimus 10mg PO daily", "everolimus"),
        ("octreotide 100mcg SC tid", "octreotide"),
        ("lanreotide 120mg SQ q4w", "lanreotide"),
        ("Lu-177 dotatate 7.4 GBq IV", "prrt"),
    ],
)
def test_standard_route_formulation_frequency_and_radionuclide_qualifiers_certify(raw, identity):
    assert treatment_identity_set(raw) == {identity}
    assert treatment_text_is_certifiable(raw)


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
def test_uncertified_residual_therapy_content_is_not_certifiable(raw):
    """Unknown therapy wording must never certify, so it can never be split away."""
    assert not treatment_text_is_certifiable(raw)
    assert split_treatment_components(raw) == [raw]


@pytest.mark.parametrize(
    "raw",
    ["lanreotide monthly", "octreotide monthly", "everolimus oral daily"],
)
def test_schedule_and_route_words_are_not_treatment_identities(raw):
    for noise in ("monthly", "oral daily", "daily"):
        assert treatment_identity_set(noise) == set()
        assert not treatment_text_is_certifiable(noise)
    assert len(treatment_identity_set(raw)) == 1


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
def test_treatment_action_words_are_not_canonical_identities(raw):
    expected = next(
        name
        for name in ("everolimus", "lanreotide", "prrt", "octreotide", "sunitinib")
        if name in raw.casefold()
    )
    assert treatment_identity_set(raw) == {expected}
    assert treatment_text_is_certifiable(raw)


def test_multi_treatment_raw_entry_splits_losslessly():
    assert split_treatment_components("lanreotide plus everolimus") == [
        "lanreotide",
        "everolimus",
    ]


def test_known_transition_components_split_into_both_sides():
    assert split_treatment_components("Switched from lanreotide to everolimus") == [
        "lanreotide",
        "everolimus",
    ]


def test_unknown_drug_suffix_in_composite_is_kept_as_its_own_identity():
    assert treatment_identity_set("lanreotide plus cabozantinib") == {
        "lanreotide",
        "drug:cabozantinib",
    }
    assert split_treatment_components("lanreotide plus cabozantinib") == [
        "lanreotide",
        "cabozantinib",
    ]


def test_short_alias_does_not_match_inside_narrative_word():
    """'rfa' sits inside 'surface'; the alias must be boundary-exact."""
    assert "radiofrequency_ablation" not in treatment_identity_set("surface findings")
    assert not treatment_text_is_certifiable("surface findings plus cabozantinib")


def test_mixed_recognized_and_unknown_compound_does_not_drop_a_component():
    assert split_treatment_components("hepatectomy and lanreotide") == [
        "hepatectomy",
        "lanreotide",
    ]


def test_mixed_known_and_procedure_treatment_keeps_both_identities():
    assert treatment_identity_set("lanreotide plus TACE") == {"lanreotide", "tace"}
    assert split_treatment_components("lanreotide plus TACE") == ["lanreotide", "TACE"]


@pytest.mark.parametrize("separator", ["+", "&", "/", "and", "plus"])
def test_captem_parenthetical_separator_is_preserved_atomically(separator):
    raw = f"CAPTEM (capecitabine {separator} temozolomide) plus lanreotide"
    assert split_treatment_components(raw) == ["CAPTEM", "lanreotide"]


@pytest.mark.parametrize(
    "raw",
    ["CAPTEM (capecitabine and temozolomide)", "capecitabine / temozolomide", "CAPTEM"],
)
def test_captem_expansions_canonicalize_to_one_regimen(raw):
    assert treatment_identity_set(raw) == {"captem"}
    assert split_treatment_components(raw) == [raw]


def test_captem_stays_atomic_while_additional_treatment_splits(agent, empty_profile):
    raw = "CAPTEM (capecitabine and temozolomide) plus lanreotide"
    empty_profile["patient"]["current_treatments"] = [raw]
    records = agent.sync_treatment_records(empty_profile)
    assert [item["text"] for item in records] == ["CAPTEM", "lanreotide"]


def test_sync_treatment_records_gives_transition_components_exclusive_ids(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = ["Switched from lanreotide to everolimus"]
    records = agent.sync_treatment_records(empty_profile)
    assert [item["text"] for item in records] == ["lanreotide", "everolimus"]
    assert len({item["id"] for item in records}) == 2
    assert len({item["source_entry_id"] for item in records}) == 1
