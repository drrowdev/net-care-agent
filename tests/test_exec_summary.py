"""Tests for agent.exec_summary — JSON output generator.

The exec_summary agent must never raise on LLM weirdness — caregiver UX
depends on getting a structured ``insufficient_data`` placeholder rather
than a 500. These tests pin that contract.
"""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def test_malformed_json_falls_back_to_insufficient_data(agent, empty_profile):
    with patch_llm(agent, lambda **_: llm_text("definitely not json")):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "insufficient_data"
    assert out["status_confidence"] == "low"
    assert out["next_actions"] == []
    assert out["best_trial"] is None
    assert "generated_at" in out


def test_max_tokens_stop_reason_falls_back_with_clear_error(agent, empty_profile):
    """If Sonnet truncates, the agent should return the insufficient_data
    shape with a message that mentions max_tokens — so the operator
    knows to bump the limit."""
    with patch_llm(
        agent, lambda **_: llm_text('{"overall_status": "stable"', stop_reason="max_tokens")
    ):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "insufficient_data"
    assert "max_tokens" in out["summary"].lower() or "truncated" in out["summary"].lower()


def test_valid_json_passes_through(agent, empty_profile):
    payload = {
        "overall_status": "stable",
        "status_confidence": "high",
        "status_rationale": "no change since last scan",
        "key_concern": "monitoring",
        "summary": "Stable disease.",
        "prrt_status": "eligible",
        "prrt_rationale": "SSTR+, Ki-67 8%",
        "cga_trend": "stable",
        "cga_trend_detail": "CgA 180 -> 185 over 3 months",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "generated_at": "ignored",
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "stable"
    assert out["status_confidence"] == "high"
    # generated_at must be re-stamped to today (not the dummy 'ignored')
    assert out["generated_at"] != "ignored"
    assert len(out["generated_at"]) == 10  # YYYY-MM-DD
