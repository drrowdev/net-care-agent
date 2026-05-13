"""Profile load/save round-trip and schema invariants."""

from __future__ import annotations

import json


def test_load_profile_creates_default_when_missing(agent):
    profile = agent.load_profile()
    # Default profile ships a generic NET diagnosis; identifying details
    # (grade, primary site, age, sex, location) are filled in at deploy
    # time on the live profile, not in source code.
    assert "neuroendocrine" in (profile["patient"]["diagnosis"] or "").lower()
    assert profile["biomarkers"] == []
    assert profile["alerts"] == []
    assert agent.PROFILE_PATH.exists()


def test_save_then_load_round_trip(agent, empty_profile):
    empty_profile["alerts"].append(
        {
            "date": "2026-01-01",
            "priority": "high",
            "message": "Test alert",
            "action_required": "Review",
            "resolved": False,
        }
    )
    agent.save_profile(empty_profile)

    loaded = agent.load_profile()
    assert loaded["alerts"][0]["message"] == "Test alert"


def test_save_writes_indented_json(agent, empty_profile):
    agent.save_profile(empty_profile)
    text = agent.PROFILE_PATH.read_text()
    # Indented JSON has at least one newline.
    assert "\n" in text
    # And is valid JSON.
    json.loads(text)


def test_default_profile_has_required_top_level_keys(agent):
    required = {
        "patient",
        "biomarkers",
        "imaging",
        "appointments",
        "documents",
        "trials_tracked",
        "literature_watched",
        "alerts",
    }
    assert required.issubset(agent.DEFAULT_PROFILE.keys())


def test_get_patient_summary_contains_diagnosis(agent, empty_profile):
    summary = agent.get_patient_summary(empty_profile)
    assert "PATIENT PROFILE" in summary
    assert "neuroendocrine" in summary.lower()


def test_get_patient_summary_handles_alerts(agent, empty_profile):
    empty_profile["alerts"] = [
        {
            "date": "2026-01-01",
            "priority": "urgent",
            "message": "Critical finding",
            "resolved": False,
        },
        {"date": "2026-01-02", "priority": "high", "message": "Resolved one", "resolved": True},
    ]
    summary = agent.get_patient_summary(empty_profile)
    assert "Critical finding" in summary
    assert "Resolved one" not in summary  # resolved alerts are filtered
    assert "Active alerts      : 1" in summary
