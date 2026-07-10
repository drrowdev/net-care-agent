"""Tests for `added_at` ingestion stamping and the dashboard 'new since
acknowledged' counter (`_count_new`).

The counter must surface an item that was *added* after the last acknowledgement
even when its clinical date is back-dated (e.g. an old document fed today).
Legacy items without `added_at` must keep the previous clinical-date behaviour.
"""

from __future__ import annotations

import datetime
import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


def _date(days: int = 0) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ago(hours: int) -> str:
    return (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat(timespec="seconds")


@pytest.fixture
def app_mod(agent):
    import app as m

    importlib.reload(m)
    return m


# ── _count_new: added_at drives newness, with clinical-date fallback ──────────
def test_backdated_item_counts_as_new_via_added_at(app_mod):
    """A biomarker clinically dated long ago but ADDED just now must count as new."""
    profile = {
        "acknowledged_at": _ago(1),
        "biomarkers": [{"marker": "CgA", "date": _date(-400), "added_at": _now()}],
    }
    counts = app_mod._count_new(profile)
    assert counts["biomarkers"] == 1
    assert counts["total_new"] == 1


def test_new_backdated_document_counts_via_added_at(app_mod):
    """The exact bug we fixed: an old-dated document fed today shows as new."""
    profile = {
        "acknowledged_at": _date(-1),  # acknowledged yesterday
        "documents": [{"date": _date(-10), "added_at": _now()}],
    }
    assert app_mod._count_new(profile)["documents"] == 1


def test_legacy_item_without_added_at_uses_clinical_date(app_mod):
    """No added_at → fall back to clinical date; ack after it → not new (unchanged)."""
    profile = {
        "acknowledged_at": _date(0),
        "biomarkers": [{"marker": "CgA", "date": _date(-30)}],
    }
    assert app_mod._count_new(profile)["biomarkers"] == 0


def test_legacy_item_after_ack_still_counts(app_mod):
    """Legacy item whose clinical date is after ack still counts (fallback intact)."""
    profile = {
        "acknowledged_at": _date(-5),
        "imaging": [{"date": _date(-1)}],
    }
    assert app_mod._count_new(profile)["imaging"] == 1


def test_empty_added_at_falls_back_to_clinical_date(app_mod):
    """An empty added_at string must not suppress the clinical-date fallback."""
    profile = {
        "acknowledged_at": _date(-5),
        "documents": [{"date": _date(-1), "added_at": ""}],
    }
    assert app_mod._count_new(profile)["documents"] == 1


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
