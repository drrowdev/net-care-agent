"""Tests for precise ingestion timestamps on profile records."""

from __future__ import annotations

import datetime
import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


# ── ingestion stamping at the append sites ───────────────────────────────────
def test_intake_stamps_added_at_on_extracted_items(agent, empty_profile):
    payload = json.dumps(
        {
            "document_type": "lab_result",
            "date": "2025-01-15",  # deliberately back-dated document
            "summary": "old labs",
            "biomarkers": [{"marker": "CgA", "value": 120, "unit": "ug/L"}],
            "imaging_findings": {"modality": "CT", "findings": "stable", "impression": "no change"},
            "symptoms_reported": [{"symptom": "nausea", "severity": 2}],
        }
    )
    with patch_llm(agent, lambda **_: llm_text(payload)):
        agent.run_intake("some document text", empty_profile)

    bm = empty_profile["biomarkers"][-1]
    doc = empty_profile["documents"][-1]
    img = empty_profile["imaging"][-1]
    sym = empty_profile["symptoms"][-1]

    for item in (bm, doc, img, sym):
        assert item.get("added_at"), f"missing added_at on {item}"
        assert item["added_at"][:10] == datetime.date.today().isoformat()

    # Clinical date stays back-dated; added_at is the (today) ingestion time.
    assert bm["date"] == "2025-01-15"


def test_flag_alert_stamps_added_at(agent, empty_profile):
    from agent.tools import execute_tool

    execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": "renal function trending down",
            "action_required": "review",
        },
        empty_profile,
    )
    assert empty_profile["alerts"][-1]["added_at"]


# ── judgment endpoint stamps added_at ────────────────────────────────────────
@pytest.fixture
def client(agent):
    import app as m

    importlib.reload(m)
    m.app.config["TESTING"] = True
    with m.app.test_client() as c:
        yield c


def test_judgment_add_endpoint_stamps_added_at(client, agent):
    r = client.post(
        "/api/judgments/add",
        json={"text": "Renal function acceptable per oncologist", "category": "context"},
    )
    assert r.status_code == 200
    prof = agent.load_profile()
    assert prof["clinical_judgments"][0].get("added_at")


def test_manual_symptom_endpoint_stamps_added_at(client, agent):
    response = client.post(
        "/api/symptoms",
        json={"symptom": "fatigue", "date": "2020-01-01"},
    )
    assert response.status_code == 200
    assert response.get_json()["added_at"]
    assert agent.load_profile()["symptoms"][0]["added_at"]
