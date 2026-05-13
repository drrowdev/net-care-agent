"""Tests for /api/health endpoint and basic Flask wiring."""

from __future__ import annotations

import pytest


@pytest.fixture
def client(agent, monkeypatch):
    # Ensure app picks up the per-test DATA_DIR (set by `agent` fixture).
    import importlib
    import sys

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    return app_mod.app.test_client()


def test_health_returns_200_when_data_dir_writable(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["data_dir_writable"] is True
    assert "version" in body


def test_health_reports_profile_state(agent, client):
    # No profile yet
    body = client.get("/api/health").get_json()
    assert body["profile_loaded"] is False

    # Create one, then verify
    agent.save_profile({"patient": {}})
    body = client.get("/api/health").get_json()
    assert body["profile_loaded"] is True
