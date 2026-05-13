"""Tests for the /api/changes delta view (R9).

These exercise the Flask app via Flask's test_client. Mirrors the
pattern used by tests/test_ui_split.py.
"""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    # Point agent.load_profile at this test's temp file.
    import agent.config as cfg

    profile_path = tmp_path / "patient_profile.json"
    monkeypatch.setattr(cfg, "PROFILE_PATH", profile_path)
    # Force a fresh import so the env override takes effect
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def _seed_profile(tmp_path, **overrides):
    """Write a profile JSON to the temp data dir."""
    base = {
        "patient": {"diagnosis": "neuroendocrine tumor"},
        "biomarkers": [],
        "imaging": [],
        "documents": [],
        "trials_tracked": [],
        "literature_watched": [],
        "alerts": [],
        "clinical_judgments": [],
        "symptoms": [],
        "questions": [],
    }
    base.update(overrides)
    (tmp_path / "patient_profile.json").write_text(json.dumps(base))


def test_changes_with_no_ack_returns_all_items_as_new(client, tmp_path):
    _seed_profile(
        tmp_path,
        biomarkers=[{"marker": "CgA", "value": 100, "date": "2026-05-01"}],
        symptoms=[{"id": "s1", "symptom": "nausea", "date": "2026-05-02"}],
    )
    r = client.get("/api/changes")
    assert r.status_code == 200
    body = r.get_json()
    assert body["acknowledged_at"] is None
    assert body["new"]["biomarkers"] == 1
    assert body["new"]["symptoms"] == 1
    assert body["new"]["total_new"] == 2


def test_acknowledge_resets_counts_to_zero(client, tmp_path):
    _seed_profile(
        tmp_path,
        biomarkers=[{"marker": "CgA", "value": 100, "date": "2026-05-01"}],
    )
    # First, confirm we see 1 new biomarker.
    pre = client.get("/api/changes").get_json()
    assert pre["new"]["biomarkers"] == 1
    # Acknowledge.
    r = client.post("/api/changes/acknowledge")
    assert r.status_code == 200
    body = r.get_json()
    assert body["acknowledged_at"] is not None
    assert body["new"]["biomarkers"] == 0
    assert body["new"]["total_new"] == 0


def test_new_item_after_ack_increments_count(client, tmp_path):
    _seed_profile(tmp_path)
    # Ack with no items first.
    client.post("/api/changes/acknowledge")
    pre_ack = client.get("/api/changes").get_json()["acknowledged_at"]
    # Now write a biomarker dated AFTER the ack.
    later = "9999-01-01"  # comfortably after any conceivable ack timestamp
    profile_path = tmp_path / "patient_profile.json"
    p = json.loads(profile_path.read_text())
    p["biomarkers"] = [{"marker": "CgA", "value": 1, "date": later}]
    profile_path.write_text(json.dumps(p))
    # Re-read
    body = client.get("/api/changes").get_json()
    assert body["acknowledged_at"] == pre_ack
    assert body["new"]["biomarkers"] == 1
    assert body["new"]["total_new"] == 1


def test_executive_summary_flagged_when_generated_after_ack(client, tmp_path):
    _seed_profile(tmp_path)
    # Ack first.
    client.post("/api/changes/acknowledge")
    profile_path = tmp_path / "patient_profile.json"
    p = json.loads(profile_path.read_text())
    p["executive_summary"] = {
        "overall_status": "stable",
        "generated_at": "9999-12-31",  # future date guarantees > ack
    }
    profile_path.write_text(json.dumps(p))
    body = client.get("/api/changes").get_json()
    assert body["new"]["executive_summary"] is True
    assert body["new"]["total_new"] == 1


def test_old_items_before_ack_are_not_counted(client, tmp_path):
    _seed_profile(
        tmp_path,
        biomarkers=[
            {"marker": "CgA", "value": 100, "date": "2020-01-01"},  # old
            {"marker": "CgA", "value": 110, "date": "9999-01-01"},  # future
        ],
    )
    client.post("/api/changes/acknowledge")
    body = client.get("/api/changes").get_json()
    # Only the future-dated one is "new"
    assert body["new"]["biomarkers"] == 1
