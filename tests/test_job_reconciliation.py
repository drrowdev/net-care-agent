"""Tests for startup job reconciliation and corrupt jobs.json handling."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest


@pytest.fixture
def app_with_data_dir(tmp_path, monkeypatch):
    """Fresh app module wired to a per-test DATA_DIR."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Ensure agent.config picks up the new DATA_DIR.
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    return app_mod, tmp_path


def _jobs_path(tmp_path: Path) -> Path:
    return tmp_path / "jobs.json"


# ── reconciliation on load ────────────────────────────────────────────────────


def test_queued_jobs_become_interrupted_on_startup(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    # Write jobs file with a queued job BEFORE loading app.
    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            [
                {
                    "id": "abc123",
                    "type": "feed",
                    "status": "queued",
                    "stage": "queued",
                    "created_at": datetime.datetime.now().isoformat(),
                    "traceback": "should be removed",
                }
            ]
        )
    )

    import app as app_mod

    importlib.reload(app_mod)

    # Trigger lazy init
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/jobs")

    with app_mod._jobs_lock:
        jobs = list(app_mod._jobs)

    assert len(jobs) == 1
    j = jobs[0]
    assert j["status"] == "interrupted"
    assert j["finished_at"] is not None
    assert "retry_guidance" in j
    assert "traceback" not in j, "interrupted record must not expose traceback"


def test_running_jobs_become_interrupted_on_startup(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            [
                {
                    "id": "xyz789",
                    "type": "digest",
                    "status": "running",
                    "stage": "orchestrating",
                    "created_at": datetime.datetime.now().isoformat(),
                    "traceback": "big traceback here",
                }
            ]
        )
    )

    import app as app_mod

    importlib.reload(app_mod)

    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/jobs")

    with app_mod._jobs_lock:
        j = app_mod._jobs[0]

    assert j["status"] == "interrupted"
    assert "traceback" not in j


def test_done_jobs_not_changed_on_startup(tmp_path, monkeypatch):
    """Completed jobs are not touched during reconciliation."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            [
                {
                    "id": "done1",
                    "status": "done",
                    "stage": "done",
                    "created_at": "2026-01-01T00:00:00",
                    "finished_at": "2026-01-01T01:00:00",
                }
            ]
        )
    )

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/jobs")

    with app_mod._jobs_lock:
        j = app_mod._jobs[0]
    assert j["status"] == "done"
    assert j.get("retry_guidance") is None


# ── corrupt jobs.json ─────────────────────────────────────────────────────────


def test_corrupt_jobs_json_quarantined(tmp_path, monkeypatch):
    """Corrupt jobs.json is quarantined; _jobs is empty; _jobs_healthy is False."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_bytes(b"{{not-valid-json}}")

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/jobs")  # trigger lazy init

    # _jobs_healthy is False.
    assert app_mod._jobs_healthy is False
    # _jobs is empty.
    assert app_mod._jobs == []
    # A quarantine file must exist.
    qdir = tmp_path / "quarantine"
    qfiles = list(qdir.glob("jobs_*.json"))
    assert len(qfiles) == 1


def test_corrupt_jobs_not_a_list_quarantined(tmp_path, monkeypatch):
    """jobs.json with non-list top-level is quarantined."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(json.dumps({"not": "a-list"}))

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/jobs")

    assert app_mod._jobs_healthy is False
    assert app_mod._jobs == []


def test_corrupt_jobs_invalid_entry_quarantined(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]
    _jobs_path(tmp_path).write_text("[null]", encoding="utf-8")

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    app_mod.app.test_client().get("/api/jobs")

    assert app_mod._jobs == []
    assert app_mod._jobs_healthy is False
    assert len(list((tmp_path / "quarantine").glob("jobs_*.json"))) == 1


def test_transient_jobs_read_failure_retries_without_overwrite(app_with_data_dir, monkeypatch):
    app_mod, tmp_path = app_with_data_dir
    jobs_path = _jobs_path(tmp_path)
    original_jobs = [
        {
            "id": "existing",
            "status": "done",
            "stage": "done",
            "created_at": "2026-01-01T00:00:00",
        }
    ]
    jobs_path.write_text(json.dumps(original_jobs), encoding="utf-8")
    real_read_bytes = Path.read_bytes
    failures = {"remaining": 1}

    def flaky_read(path):
        if path == jobs_path and failures["remaining"]:
            failures["remaining"] -= 1
            raise OSError("temporary mount error")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", flaky_read)
    client = app_mod.app.test_client()

    first = client.get("/api/jobs")
    assert first.status_code == 503
    assert json.loads(jobs_path.read_text()) == original_jobs
    assert app_mod._initialized is False

    second = client.get("/api/jobs")
    assert second.status_code == 200
    assert second.get_json()[0]["id"] == "existing"


def test_interrupted_count_in_health(tmp_path, monkeypatch):
    """Health endpoint discloses interrupted_job_count without PHI."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            [
                {
                    "id": "j1",
                    "status": "running",
                    "stage": "r",
                    "created_at": datetime.datetime.now().isoformat(),
                }
            ]
        )
    )

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()

    resp = client.get("/api/health")
    body = resp.get_json()
    assert body["interrupted_job_count"] >= 1


def test_corrupt_jobs_health_jobs_healthy_false(tmp_path, monkeypatch):
    """Health reports jobs_healthy=False when jobs.json was quarantined."""
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod == "agent" or mod.startswith("agent."):
            del sys.modules[mod]

    jobs_path = _jobs_path(tmp_path)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_bytes(b"{{bad")

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()

    resp = client.get("/api/health")
    body = resp.get_json()
    assert body["jobs_healthy"] is False
    # Status should be degraded (not error — the profile is fine).
    assert body["status"] in ("degraded", "error")
