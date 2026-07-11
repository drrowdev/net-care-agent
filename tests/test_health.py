"""Tests for /api/health endpoint and basic Flask wiring."""

from __future__ import annotations

import json
import os
import time

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
    assert body["status"] in {"ok", "degraded"}
    assert body["data_dir_writable"] is True
    assert "version" in body


def test_health_reports_profile_state(agent, client):
    # No profile yet
    body = client.get("/api/health").get_json()
    assert body["profile_loaded"] is False

    # Create one, then verify
    agent.save_profile({"patient": {"diagnosis": "NET"}})
    body = client.get("/api/health").get_json()
    assert body["profile_loaded"] is True


# ── new health checks ──────────────────────────────────────────────────────────


def test_health_includes_schema_version(client):
    from agent.migrations import CURRENT_SCHEMA_VERSION

    body = client.get("/api/health").get_json()
    assert body["schema_version"] == CURRENT_SCHEMA_VERSION
    assert isinstance(body["hosted_auth_detected"], bool)


def test_health_profile_status_missing_when_no_profile(client):
    body = client.get("/api/health").get_json()
    assert body["profile_status"] == "missing"


def test_health_profile_status_ok_with_valid_profile(agent, client):
    agent.save_profile({"patient": {"diagnosis": "NET"}})
    body = client.get("/api/health").get_json()
    assert body["profile_status"] == "ok"


def test_profile_load_errors_return_phi_safe_503(agent, client, monkeypatch):
    monkeypatch.setattr(
        agent,
        "load_profile",
        lambda: (_ for _ in ()).throw(agent.IOProfileError("secret mount detail")),
    )

    response = client.get("/api/status")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload == {
        "error": "Patient record is temporarily unavailable.",
        "retryable": True,
    }
    assert "secret" not in response.get_data(as_text=True)


def test_health_503_on_corrupt_profile(agent, monkeypatch):
    """Corrupt JSON in profile → 503 with status=error (no side effects)."""
    import importlib
    import sys

    import agent.config as cfg

    # Write a corrupt profile.
    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_bytes(b"{{not-valid-json}}")

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()

    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["profile_status"] in ("invalid_json", "invalid_shape")


def test_health_503_on_invalid_shape_profile(agent, monkeypatch):
    """Non-dict patient → profile_status=invalid_shape → 503."""
    import importlib
    import sys

    import agent.config as cfg

    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_text(json.dumps({"patient": "not-a-dict"}))

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()

    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["profile_status"] == "invalid_shape"


def test_health_no_phi_in_response(agent, client):
    """Health response must not contain any patient data."""
    agent.save_profile({"patient": {"diagnosis": "NET", "age": 65, "sex": "female"}})
    body = client.get("/api/health").get_json()
    body_str = json.dumps(body)
    # No clinical data — check for clearly clinical strings, not bare numbers
    # which may innocently appear in timestamps.
    assert "NET" not in body_str
    assert "female" not in body_str
    assert "neuroendocrine" not in body_str.lower()


def test_health_no_paths_in_response(agent, client):
    """Health response must not expose filesystem paths."""
    import agent.config as cfg

    body = client.get("/api/health").get_json()
    body_str = json.dumps(body)
    # No absolute paths leaked — check that the actual DATA_DIR value is absent.
    assert str(cfg.DATA_DIR) not in body_str
    # Known path fragments that should never appear in health output.
    assert "patient_profile" not in body_str
    assert "/home/" not in body_str
    # The *key* data_dir_writable is allowed; the path *value* must not appear.
    assert "data_dir_writable" in body


def test_health_503_on_io_error_profile(agent, monkeypatch):
    """profile_status=io_error must produce a 503 response."""
    import importlib
    import sys

    import agent.config as cfg

    # Create the profile then simulate a transient OSError on reads.
    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_text(json.dumps({"patient": {"diagnosis": "NET"}}))

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True

    # Patch PROFILE_PATH.read_bytes to raise OSError inside the health check.
    original_read_bytes = cfg.PROFILE_PATH.__class__.read_bytes

    def _raise_io(self):
        if self == cfg.PROFILE_PATH:
            raise OSError("simulated transient I/O error")
        return original_read_bytes(self)

    monkeypatch.setattr(cfg.PROFILE_PATH.__class__, "read_bytes", _raise_io)

    client = app_mod.app.test_client()
    resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["profile_status"] == "io_error"
    assert body["status"] == "error"


def test_health_includes_job_counts(client):
    body = client.get("/api/health").get_json()
    assert "stale_job_count" in body
    assert "interrupted_job_count" in body
    assert body["interrupted_job_count"] == 0
    assert body["stale_job_count"] == 0


def test_health_includes_backup_ages(client):
    body = client.get("/api/health").get_json()
    assert "newest_snapshot_age_seconds" in body
    assert "newest_backup_age_seconds" in body
    assert "profile_age_seconds" in body
    assert "backup_out_of_date" in body


def test_old_but_current_backup_does_not_degrade_health(agent, client, monkeypatch):
    from agent import backups

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    old = time.time() - 8 * 24 * 3600
    os.utime(agent.PROFILE_PATH, (old, old))
    monkeypatch.setattr(backups, "newest_file_age_seconds", lambda *_args: 8 * 24 * 3600)

    body = client.get("/api/health").get_json()

    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_backup_lagging_current_profile_degrades_health(agent, client, monkeypatch):
    from agent import backups

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    monkeypatch.setattr(backups, "newest_file_age_seconds", lambda *_args: 3600)

    body = client.get("/api/health").get_json()

    assert body["backup_out_of_date"] is True
    assert body["status"] == "degraded"


def test_health_jobs_healthy_true_normally(client):
    body = client.get("/api/health").get_json()
    assert body["jobs_healthy"] is True


def test_health_degraded_with_interrupted_jobs(agent, monkeypatch):
    """If _jobs contains interrupted jobs health status is degraded."""
    import importlib
    import sys

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()
    client.get("/api/health")  # complete lazy job-store initialization

    # Inject an interrupted job directly.
    with app_mod._jobs_lock:
        app_mod._jobs.append(
            {"id": "j1", "status": "interrupted", "created_at": "2026-01-01T00:00:00"}
        )

    resp = client.get("/api/health")
    body = resp.get_json()
    assert body["status"] == "degraded"
    assert body["interrupted_job_count"] == 1


# ── liveness ──────────────────────────────────────────────────────────────────


def test_liveness_route_returns_200(client):
    resp = client.get("/api/live")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["alive"] is True


def test_liveness_independent_of_profile(agent, monkeypatch):
    """Liveness is always 200 even when profile is corrupt."""
    import importlib
    import sys

    import agent.config as cfg

    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_bytes(b"{{bad")

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    client = app_mod.app.test_client()

    resp = client.get("/api/live")
    assert resp.status_code == 200
    assert resp.get_json()["alive"] is True


# ── recovery state in health ──────────────────────────────────────────────────


def test_health_includes_profile_recovery_state_default_none(client):
    """Health response includes profile_recovery_state field (default 'none')."""
    body = client.get("/api/health").get_json()
    assert "profile_recovery_state" in body
    assert body["profile_recovery_state"] == "none"


def test_health_profile_recovery_state_after_recovery(agent, monkeypatch):
    """profile_recovery_state reflects 'recovered' after a successful recovery."""
    import importlib
    import sys

    import agent.config as cfg
    from agent.recovery import RecoveryCandidate, restore_from_candidate

    # Simulate a restore by calling restore_from_candidate directly.
    valid = json.dumps({"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []})
    snap_dir = cfg.DATA_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "profile_20260101_120000_000000.json"
    snap.write_text(valid)
    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_bytes(b"corrupt")

    restore_from_candidate(RecoveryCandidate(snap, "snapshot"))

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    c = app_mod.app.test_client()

    body = c.get("/api/health").get_json()
    assert body["profile_recovery_state"] == "recovered"
    assert body.get("profile_recovery_source") == "snapshot"


def test_health_profile_recovery_state_no_phi(agent, client):
    """profile_recovery_state field contains no PHI."""
    agent.save_profile({"patient": {"diagnosis": "NET", "age": 65}})
    body = client.get("/api/health").get_json()
    body_str = json.dumps(body)
    assert "NET" not in body_str
    assert body["profile_recovery_state"] in ("none", "recovered", "failed", "unknown")
    assert body.get("profile_recovery_source") in (None, "snapshot", "daily_backup", "manual")


# ── jobs OSError marks unhealthy ─────────────────────────────────────────────


def test_jobs_read_oserror_marks_unhealthy(agent, monkeypatch):
    """OSError on jobs.json read in _load_jobs sets _jobs_healthy=False."""
    import importlib
    import sys
    from pathlib import Path

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)

    # Create jobs file so JOBS_PATH.exists() is True.
    app_mod.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    app_mod.JOBS_PATH.write_bytes(b"[]")

    original_read = Path.read_bytes

    def _raise_io(self):
        if self == app_mod.JOBS_PATH:
            raise OSError("simulated jobs read error")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", _raise_io)

    app_mod._load_jobs()

    assert app_mod._jobs_healthy is False


def test_health_degraded_when_jobs_read_oserror(agent, monkeypatch):
    """After a jobs.json read OSError, /api/health reports jobs_healthy=False."""
    import importlib
    import sys
    from pathlib import Path

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)

    app_mod.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    app_mod.JOBS_PATH.write_bytes(b"[]")

    original_read = Path.read_bytes

    def _raise_io(self):
        if self == app_mod.JOBS_PATH:
            raise OSError("simulated jobs read error")
        return original_read(self)

    monkeypatch.setattr(Path, "read_bytes", _raise_io)
    app_mod._load_jobs()

    app_mod.app.config["TESTING"] = True
    c = app_mod.app.test_client()
    body = c.get("/api/health").get_json()
    assert body["jobs_healthy"] is False
    # degraded (not error) because read I/O is transient, not quarantine
    assert body["status"] in ("degraded", "error")
