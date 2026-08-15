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


def test_exec_summary_context_uses_raw_treatments_when_classification_stale(agent, empty_profile):
    empty_profile["profile_revision"] = 5
    empty_profile["patient"]["current_treatments"] = ["raw sunitinib"]
    empty_profile["treatments_classified"] = [{"text": "stale lanreotide", "category": "active"}]
    empty_profile["treatments_classification_revision"] = 4
    captured = {}
    payload = {
        "overall_status": "insufficient_data",
        "status_confidence": "low",
        "status_rationale": "Sparse data.",
        "key_concern": "None established.",
        "summary": "Review current record.",
        "prrt_status": "unknown",
        "prrt_rationale": "Not assessed.",
        "cga_trend": "insufficient_data",
        "cga_trend_detail": "No trend.",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "claim_evidence": {},
    }

    def handler(**kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        return llm_text(json.dumps(payload))

    with patch_llm(agent, handler):
        agent.generate_executive_summary(empty_profile)

    assert "raw sunitinib" in captured["content"]
    assert "stale lanreotide" not in captured["content"]


def test_generated_prose_is_stored_and_prompted_exactly_as_the_model_wrote_it(agent, empty_profile):
    """Finnish dates are a rendering concern and must stay one.

    The interface rewrites ISO dates inside generated sentences on the way to
    the screen. That must never reach back into what is stored or into what is
    sent to the model: the record keeps the model's words verbatim, and the
    prompt asks nothing about date formatting.
    """
    prose = {
        "status_rationale": "PET-CT on 2026-04-22 confirmed progression.",
        "key_concern": "The interval closes 2026-08-26.",
        "summary": "Three doses every 8 weeks from 2026-05-07.",
        "prrt_rationale": "Receptor imaging reviewed 2026-04-22.",
        "cga_trend_detail": "CgA rose between 2026-02-11 and 2026-04-22.",
    }
    payload = {
        "overall_status": "progressing",
        "status_confidence": "medium",
        "prrt_status": "likely_eligible",
        "cga_trend": "rising",
        "next_actions": [
            {
                "priority": "high",
                "action": "Confirm the dose booked for 2026-09-01",
                "timeframe": "before 2026-08-20",
                "rationale": "The interval closes 2026-08-26.",
                "provisional": True,
            }
        ],
        "timeline": [{"date": "2026-09-01", "event": "Third dose due 2026-09-01", "type": "scan"}],
        "best_trial": None,
        "claim_evidence": {},
        **prose,
    }
    captured = {}

    def handler(**kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        captured["system"] = kwargs.get("system")
        return llm_text(json.dumps(payload))

    with patch_llm(agent, handler):
        out = agent.generate_executive_summary(empty_profile)

    for field, text in prose.items():
        assert out[field] == text
    assert out["next_actions"][0]["action"] == "Confirm the dose booked for 2026-09-01"
    assert out["next_actions"][0]["timeframe"] == "before 2026-08-20"
    assert out["next_actions"][0]["rationale"] == "The interval closes 2026-08-26."
    assert out["timeline"][0]["event"] == "Third dose due 2026-09-01"
    assert out["timeline"][0]["date"] == "2026-09-01"
    # Nothing Finnish-shaped was written into the record.
    assert "22.4.2026" not in json.dumps(out)

    prompt = json.dumps(captured, default=str)
    for instruction in ("D.M.YYYY", "Finnish", "dd.mm.yyyy", "day.month.year"):
        assert instruction not in prompt

    from agent import exec_summary

    assert '"generated_at": "YYYY-MM-DD"' in exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
