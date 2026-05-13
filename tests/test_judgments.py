"""Tests for agent.judgments — clinical-judgment context formatter."""

from __future__ import annotations


def test_empty_profile_returns_empty_string(agent):
    assert agent.get_clinical_judgments_context({}) == ""


def test_profile_with_no_judgments_returns_empty_string(agent):
    assert agent.get_clinical_judgments_context({"clinical_judgments": []}) == ""


def test_single_judgment_appears_with_header(agent):
    profile = {
        "clinical_judgments": [
            {
                "date": "2026-04-01",
                "category": "constraint",
                "text": "Rules out PRRT retreatment for now",
            }
        ]
    }
    out = agent.get_clinical_judgments_context(profile)
    assert "ACCUMULATED CLINICAL JUDGMENTS" in out
    assert "Constraints" in out
    assert "Rules out PRRT retreatment for now" in out
    assert "2026-04-01" in out


def test_categories_appear_in_canonical_order(agent):
    """Order is constraint -> preference -> outcome -> context, regardless of
    insertion order. Agents rely on this to weight constraints highest."""
    profile = {
        "clinical_judgments": [
            {"date": "2026-04-01", "category": "context", "text": "Patient has stable disease"},
            {"date": "2026-04-02", "category": "outcome", "text": "Responded to lanreotide"},
            {"date": "2026-04-03", "category": "preference", "text": "Oncologist prefers PRRT"},
            {"date": "2026-04-04", "category": "constraint", "text": "Hilar LN already addressed"},
        ]
    }
    out = agent.get_clinical_judgments_context(profile)
    i_constraint = out.find("⛔ Constraints")
    i_preference = out.find("★ Oncologist")
    i_outcome = out.find("✓ Treatment/trial")
    i_context = out.find("ℹ Clinical context")
    assert 0 < i_constraint < i_preference < i_outcome < i_context


def test_within_category_sorted_by_date_desc(agent):
    profile = {
        "clinical_judgments": [
            {"date": "2026-01-01", "category": "constraint", "text": "OLD constraint"},
            {"date": "2026-04-01", "category": "constraint", "text": "NEW constraint"},
        ]
    }
    out = agent.get_clinical_judgments_context(profile)
    assert out.find("NEW constraint") < out.find("OLD constraint")


def test_unknown_category_falls_back_to_context(agent):
    profile = {"clinical_judgments": [{"date": "2026-04-01", "text": "No explicit category"}]}
    out = agent.get_clinical_judgments_context(profile)
    assert "No explicit category" in out
    assert "background" in out
