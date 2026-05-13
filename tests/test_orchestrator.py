"""Tests for agent.orchestrator — the region-filter helper."""

from __future__ import annotations


def test_region_filter_with_configured_regions(agent):
    profile = {"patient": {"regions_of_interest": ["Germany", "Switzerland"]}}
    from agent.orchestrator import _region_filter_instruction

    out = _region_filter_instruction(profile)
    assert "Always run one region-specific search" in out
    assert 'country="Germany"' in out
    assert 'country="Switzerland"' in out


def test_region_filter_with_empty_regions_falls_back_to_conditional_advice(agent):
    from agent.orchestrator import _region_filter_instruction

    out = _region_filter_instruction({"patient": {"regions_of_interest": []}})
    assert "Always run" not in out
    assert "regions of interest" in out


def test_region_filter_missing_patient_block(agent):
    """Defensive — must not crash if patient is missing entirely."""
    from agent.orchestrator import _region_filter_instruction

    out = _region_filter_instruction({})
    assert "regions of interest" in out


def test_region_filter_drops_empty_strings(agent):
    """Empty strings in the list shouldn't produce blank country="" fragments."""
    from agent.orchestrator import _region_filter_instruction

    profile = {"patient": {"regions_of_interest": ["Germany", "", "Switzerland"]}}
    out = _region_filter_instruction(profile)
    assert 'country=""' not in out
    assert 'country="Germany"' in out
    assert 'country="Switzerland"' in out
