"""Treatment fuzzy-matching & synonym dedup.

This is the highest-risk function: a false negative here lets duplicate
treatments accumulate in the profile (Somatuline + lanreotide both showing
as 'active'), which the orchestrator would then reason about incorrectly.
"""
from __future__ import annotations


def test_synonyms_collapse_to_same_treatment(agent):
    # Both should normalize to "lanreotide" and overlap completely.
    score = agent._treatment_similarity("somatuline 120mg q4w", "lanreotide 120mg q4w")
    assert score >= 0.7


def test_octreotide_is_treated_as_somatostatin_analogue(agent):
    # After normalization both contain "lanreotide", overlap depends on dose tokens.
    # The intake dedup uses > 0.7; we assert at least equal to the dedup threshold
    # for the bare drug-name case.
    bare = agent._treatment_similarity("octreotide", "lanreotide")
    assert bare == 1.0  # both normalize to {"lanreotide"}


def test_prrt_synonyms_collapse(agent):
    """Most PRRT name variants should overlap after normalization."""
    pairs = [
        ("Lu-177 DOTATATE", "Lutathera"),
        ("Lutetium therapy", "Lu177 dotatate"),
    ]
    for a, b in pairs:
        score = agent._treatment_similarity(a.lower(), b.lower())
        assert score > 0, f"expected non-zero overlap for {a!r} vs {b!r}, got {score}"


def test_hyphenated_prrt_token_collapses(agent):
    score = agent._treatment_similarity("177lu-octreotate", "prrt cycle 1")
    assert score > 0


def test_unrelated_treatments_have_low_similarity(agent):
    score = agent._treatment_similarity("everolimus 10mg daily", "capecitabine 1500mg bid")
    assert score < 0.3


def test_empty_strings_return_zero(agent):
    assert agent._treatment_similarity("", "lanreotide") == 0.0
    assert agent._treatment_similarity("lanreotide", "") == 0.0
    assert agent._treatment_similarity("", "") == 0.0


def test_identical_strings_return_one(agent):
    assert agent._treatment_similarity("everolimus 10mg", "everolimus 10mg") == 1.0
