"""Tests for appointment extraction (intake) and the deterministic timeline merge."""

from __future__ import annotations

import datetime
import json

from tests._llm_fake import llm_text, patch_llm


def _future(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


# ── intake: appointment extraction ───────────────────────────────────────────
def test_intake_extracts_appointment(agent, empty_profile):
    appt_date = _future(11)
    payload = json.dumps(
        {
            "document_type": "doctor_note",
            "summary": "routine note",
            "appointments": [
                {"date": appt_date, "description": "Follow-up call re counts", "type": "call"}
            ],
        }
    )
    with patch_llm(agent, lambda **_: llm_text(payload)):
        agent.run_intake("note text", empty_profile)
    appts = empty_profile["appointments"]
    assert len(appts) == 1
    assert appts[0]["date"] == appt_date
    assert "Follow-up call" in appts[0]["description"]


def test_intake_dedups_appointments_on_refeed(agent, empty_profile):
    appt_date = _future(11)
    payload = json.dumps(
        {
            "document_type": "doctor_note",
            "summary": "s",
            "appointments": [{"date": appt_date, "description": "Follow-up call", "type": "call"}],
        }
    )
    with patch_llm(agent, lambda **_: llm_text(payload)):
        agent.run_intake("note", empty_profile)
        agent.run_intake("note", empty_profile)
    assert len(empty_profile["appointments"]) == 1


# ── deterministic timeline merge ─────────────────────────────────────────────
def test_upcoming_appointment_forced_into_timeline(agent, empty_profile):
    from agent import exec_summary

    appt_date = _future(11)
    empty_profile["appointments"] = [
        {"date": appt_date, "description": "14.7 follow-up call", "type": "call"}
    ]
    # LLM returns a timeline that OMITS the near-term call (distant items only).
    summary_json = json.dumps(
        {
            "overall_status": "stable",
            "timeline": [
                {
                    "date": _future(90),
                    "event": "Cycle 3 PRRT",
                    "type": "milestone",
                    "provisional": True,
                }
            ],
        }
    )
    with patch_llm(agent, lambda **_: llm_text(summary_json)):
        out = exec_summary.generate_executive_summary(empty_profile)
    events = [t["event"] for t in out["timeline"]]
    assert any("follow-up call" in e.lower() for e in events)
    # sorted nearest-first: the 11-day call precedes the 90-day cycle
    assert out["timeline"][0]["date"] == appt_date


def test_past_appointments_not_added(agent, empty_profile):
    from agent import exec_summary

    empty_profile["appointments"] = [
        {"date": _future(-30), "description": "old visit", "type": "appointment"}
    ]
    with patch_llm(agent, lambda **_: llm_text('{"overall_status": "stable", "timeline": []}')):
        out = exec_summary.generate_executive_summary(empty_profile)
    assert out["timeline"] == []


def test_merge_deduplicates_against_llm_timeline(agent, empty_profile):
    from agent import exec_summary

    appt_date = _future(11)
    empty_profile["appointments"] = [
        {"date": appt_date, "description": "Follow-up call re blood counts", "type": "call"}
    ]
    # LLM already included the same event — must not duplicate it.
    summary_json = json.dumps(
        {
            "overall_status": "stable",
            "timeline": [
                {
                    "date": appt_date,
                    "event": "Follow-up call re blood counts",
                    "type": "appointment",
                    "provisional": True,
                }
            ],
        }
    )
    with patch_llm(agent, lambda **_: llm_text(summary_json)):
        out = exec_summary.generate_executive_summary(empty_profile)
    calls = [t for t in out["timeline"] if "follow-up call" in t["event"].lower()]
    assert len(calls) == 1
