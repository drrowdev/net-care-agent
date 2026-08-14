"""Web jobs must never invoke a treatment classifier, and must never rewrite it.

The LLM classification pass was retired. Stored `treatments_classified[]` rows
and their revision/job-id provenance are frozen historical data: the summary,
feed, and digest jobs must leave them byte-identical, and no job may reach the
model for classification.
"""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from tests._llm_fake import llm_text, patch_llm


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def _summary() -> dict:
    return {
        "overall_status": "stable",
        "status_confidence": "high",
        "status_rationale": "Current evidence is stable.",
        "key_concern": "None",
        "summary": "Fresh summary",
        "prrt_status": "unknown",
        "prrt_rationale": "",
        "cga_trend": "insufficient_data",
        "cga_trend_detail": "",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "generated_at": "2026-08-01",
    }


def _queue_job(app_module, job_id: str, job_type: str) -> None:
    app_module._jobs = [
        {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
            "error": None,
        }
    ]


def _seed(agent) -> tuple[object, object, list[dict]]:
    """Raw treatments plus stored generated rows that nothing may refresh."""
    profile = agent.load_profile()
    profile["patient"]["current_treatments"] = ["lanreotide", "everolimus"]
    profile["treatments_classified"] = [
        {"id": "txclass_prior", "text": "lanreotide", "label": "Lanreotide", "category": "active"}
    ]
    profile["treatments_classification_revision"] = profile.get("profile_revision")
    profile["treatments_classification_job_id"] = "prior-job"
    agent.save_profile(profile)
    stored = agent.load_profile()
    return (
        stored.get("treatments_classification_revision"),
        stored.get("treatments_classification_job_id"),
        copy.deepcopy(stored["treatments_classified"]),
    )


def test_no_classifier_symbol_survives_on_the_agent_package(agent):
    assert not hasattr(agent, "classify_treatments")
    assert not hasattr(agent, "TreatmentClassificationError")


def test_app_has_no_classification_job_wiring():
    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert "_classify_treatments_or_warn" not in source
    assert "classification_skipped" not in source
    assert "classify_treatments" not in source
    assert '"classifying"' not in source


def test_summary_job_leaves_stored_classification_byte_identical(app_client, agent):
    app_module, _ = app_client
    revision, job_id, rows = _seed(agent)
    _queue_job(app_module, "summary-frozen", "summary")

    with patch_llm(agent, lambda **_: llm_text(json.dumps(_summary()))):
        app_module._run_summary_job("summary-frozen")

    saved = agent.load_profile()
    assert saved["treatments_classified"] == rows
    assert saved.get("treatments_classification_revision") == revision
    assert saved.get("treatments_classification_job_id") == job_id

    job = app_module._jobs[0]
    assert job["status"] == "done"
    assert job["stage"] == "done"

    result = json.loads(
        (app_module.DATA_DIR / "job_results" / "summary-frozen.json").read_text(encoding="utf-8")
    )
    assert "treatments_classified" not in result
    assert "treatments_fallback" not in result
    assert "treatments_classification_current" not in result
    assert "classification_warning" not in result


def test_status_no_longer_publishes_classification_fields(app_client, agent):
    _, client = app_client
    _seed(agent)

    payload = client.get("/api/status").get_json()

    assert "treatments_classified" not in payload
    assert "treatments_fallback" not in payload
    assert "treatments_classification_current" not in payload


def test_generated_rows_stay_projected_as_reconciliation_authority(app_client, agent):
    """Presentation was removed; the server projection is deliberately unchanged."""
    _, client = app_client
    profile = agent.load_profile()
    profile["patient"]["current_treatments"] = ["lanreotide"]
    agent.sync_treatment_records(profile)
    component_id = profile["patient"]["current_treatment_records"][0]["id"]
    profile["treatments_classified"] = [
        {
            "id": "txclass_mapped",
            "text": "lanreotide",
            "label": "Lanreotide",
            "category": "active",
            "date": None,
            "source_treatment_ids": [component_id],
        },
        {"text": "historical context", "label": None, "category": None, "date": None},
    ]
    agent.save_profile(profile, clinical_change=False)

    projection = client.get("/api/patient/treatment-reconciliation").get_json()

    assert projection["legacy_treatments"][0]["generated_classification"][0]["id"] == (
        "txclass_mapped"
    )
    assert projection["unlinked_generated_context_count"] == 1
    assert projection["unlinked_generated_context"][0]["text"] == "historical context"


def test_treatment_edit_route_is_a_tombstone(app_client, agent):
    _, client = app_client
    _seed(agent)
    before = agent.load_profile()

    response = client.post(
        "/api/treatments/txclass_prior",
        json={"action": "remove", "expected_token": "x", "expected_profile_revision": 1},
    )

    assert response.status_code == 410
    assert agent.load_profile() == before
