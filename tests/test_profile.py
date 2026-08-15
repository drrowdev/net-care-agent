"""Profile load/save round-trip and schema invariants."""

from __future__ import annotations

import importlib
import json

import pytest


def _schema14_production_shape(agent) -> dict:
    profile = json.loads(json.dumps(agent.DEFAULT_PROFILE))
    profile["schema_version"] = 14
    profile.pop("profile_revision")
    profile["workflow_revision"] = 6
    profile["patient"]["current_treatments"] = [
        f"Synthetic treatment row {index:02d}" for index in range(31)
    ]
    agent.sync_treatment_records(profile)
    profile["treatments_classified"] = [
        {
            "text": f"Synthetic generated context {index % 5}",
            "label": f"Synthetic generated label {index % 5}",
            "category": "active",
            "date": f"20{index:02d}",
        }
        for index in range(10)
    ]
    profile["clinical_judgments"] = [
        {
            "id": "synthetic-feedback-judgment",
            "date": "2020",
            "category": "context",
            "text": "Synthetic historical feedback provenance",
            "source": "feedback",
        }
    ]
    profile["symptoms"] = [
        {
            "id": "synthetic-legacy-symptom",
            "date": None,
            "date_precision": "unknown",
            "date_kind": "unknown",
            "source_document_date": None,
            "source_document_date_precision": "unknown",
            "symptom": "Synthetic legacy symptom",
            "severity": None,
            "source": "manual",
        }
    ]
    for key in ("source_documents", "feedback", "latest_research_update", "profile_updated_at"):
        profile.pop(key)
    return profile


@pytest.fixture
def app_client(agent):
    app_module = importlib.import_module("app")
    app_module.app.config.update(TESTING=True)
    return app_module, app_module.app.test_client()


def test_load_profile_creates_default_when_missing(agent):
    profile = agent.load_profile()
    # Default profile ships a generic NET diagnosis; identifying details
    # (grade, primary site, age, sex, location) are filled in at deploy
    # time on the live profile, not in source code.
    assert "neuroendocrine" in (profile["patient"]["diagnosis"] or "").lower()
    assert profile["biomarkers"] == []
    assert profile["alerts"] == []
    assert profile["patient"]["current_treatment_records"] == []
    assert agent.PROFILE_PATH.exists()
    assert agent.load_profile()["patient"] == profile["patient"]


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


def test_schema14_profile_load_materializes_revision_and_all_projections(app_client, agent):
    raw = _schema14_production_shape(agent)
    agent.PROFILE_PATH.write_text(json.dumps(raw), encoding="utf-8")

    loaded = agent.load_profile()
    projections = [
        agent.project_biomarker_series(loaded),
        agent.project_imaging_series(loaded),
        agent.project_symptom_episodes(loaded),
        agent.project_treatment_reconciliation(loaded),
        agent.project_research_workspace(loaded),
    ]
    _, client = app_client
    symptom_response = client.get("/api/patient/symptom-episodes")
    treatment_response = client.get("/api/patient/treatment-reconciliation")

    assert loaded["schema_version"] == 16
    assert loaded["profile_revision"] == 0
    assert loaded["workflow_revision"] == 6
    assert loaded["clinical_judgments"][0]["source"] == "feedback"
    assert loaded["source_documents"] == []
    assert loaded["feedback"] == []
    assert loaded["latest_research_update"] is None
    assert loaded["profile_updated_at"] is None
    assert all(projection["profile_revision"] == 0 for projection in projections)
    assert projections[2]["observation_count"] == 1
    assert projections[3]["legacy_treatment_count"] == 31
    assert projections[3]["unlinked_generated_context_count"] == 10
    assert symptom_response.status_code == 200
    assert symptom_response.get_json()["profile_revision"] == 0
    assert treatment_response.status_code == 200
    assert treatment_response.get_json()["profile_revision"] == 0


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
            "dependency_kind": "durable",
        },
        {"date": "2026-01-02", "priority": "high", "message": "Resolved one", "resolved": True},
    ]
    summary = agent.get_patient_summary(empty_profile)
    assert "Critical finding" in summary
    assert "Resolved one" not in summary  # resolved alerts are filtered
    assert "Active alerts      : 1" in summary
