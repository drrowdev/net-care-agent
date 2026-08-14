"""Tests for /api/health endpoint and basic Flask wiring."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import time

import pytest


def _stamp(path, days_ago: int, hour: int, minute: int = 0) -> None:
    """Pin a file's mtime to an explicit local wall-clock time *days_ago* days back.

    Tests that care about calendar-day boundaries must not rewind by a number of
    seconds: "24 hours ago" lands on a different local date depending on what
    time the suite happens to run and on DST transitions, which would make the
    assertions pass or fail for the wrong reason.
    """
    day = datetime.date.today() - datetime.timedelta(days=days_ago)
    when = datetime.datetime.combine(day, datetime.time(hour, minute)).timestamp()
    os.utime(path, (when, when))


def _restamp_backup(backups_dir, days_ago: int, hour: int, minute: int = 0):
    """Re-date every backup file, keeping filename and mtime in agreement.

    ``daily_backup`` names the file after the mtime it copies, so a test that
    moves an mtime without renaming the file would build a directory state the
    writer can never produce.
    """
    day = datetime.date.today() - datetime.timedelta(days=days_ago)
    moved = []
    for path in list(backups_dir.glob("profile_*.json")):
        target = path.rename(backups_dir / f"profile_{day.strftime('%Y%m%d')}.json")
        _stamp(target, days_ago, hour, minute)
        moved.append(target)
    return moved


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


def test_old_but_current_backup_does_not_degrade_health(agent, client):
    """An untouched eight-day-old profile with an equally old backup is fine."""
    import agent.config as cfg

    agent.save_profile({"patient": {"diagnosis": "NET"}})

    eight_days = 8 * 24 * 3600
    _stamp(cfg.PROFILE_PATH, 8, 10)
    _restamp_backup(cfg.DATA_DIR / "backups", 8, 10)

    body = client.get("/api/health").get_json()

    assert body["newest_backup_age_seconds"] > eight_days - 24 * 3600
    assert body["profile_age_seconds"] > eight_days - 24 * 3600
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


# ── backup freshness is judged on the daily-backup cadence ────────────────────
#
# ``daily_backup`` writes one file per calendar day; ``save_profile`` runs many
# times a day.  Comparing the two ages directly reported degraded from the
# second save of every day until midnight.  These tests pin the corrected
# behaviour.


def test_repeated_saves_after_todays_backup_stay_healthy(agent, client):
    """The exact production false alarm: today's backup + a later edit.

    ``daily_backup`` correctly refuses to rewrite today's file, so the backup
    keeps the mtime of the day's first save while the profile advances.  That is
    normal, not a fault, and must not degrade.
    """
    import agent.config as cfg

    profile = {"patient": {"diagnosis": "NET"}}
    agent.save_profile(profile)

    for path in (cfg.DATA_DIR / "backups").glob("profile_*.json"):
        _stamp(path, 0, 0, 0)  # today's file, taken by the first save at 00:00

    # A perfectly ordinary later edit on the same day.
    profile["patient"]["stage"] = "IV"
    agent.save_profile(profile)

    body = client.get("/api/health").get_json()

    assert body["profile_status"] == "ok"
    assert body["profile_age_seconds"] < 60
    # The backup is structurally older than the profile: that is the steady
    # state the old check mistook for a fault.
    assert body["newest_backup_age_seconds"] >= body["profile_age_seconds"]
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_idle_days_after_a_late_save_stay_healthy(agent, client):
    """Backup taken at 00:01, last save at 23:59 that same day, then idle days.

    The backup's age grows without bound and it trails the profile by nearly 24
    hours, yet nothing is wrong: both belong to the same calendar day, so that
    day's ``daily_backup`` did its job.  An absolute age threshold would
    false-alarm here, and the old age comparison degraded immediately.
    """
    import agent.config as cfg

    profile = {"patient": {"diagnosis": "NET"}}
    agent.save_profile(profile)

    _restamp_backup(cfg.DATA_DIR / "backups", 3, 0, 1)
    _stamp(cfg.PROFILE_PATH, 3, 23, 59)

    body = client.get("/api/health").get_json()

    assert body["newest_backup_age_seconds"] > 3 * 24 * 3600
    assert body["newest_backup_age_seconds"] - body["profile_age_seconds"] > 23 * 3600
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_backup_missing_for_the_day_the_profile_was_saved_degrades(agent, client):
    """A save whose day produced no backup means the writer is broken."""
    import agent.config as cfg

    profile = {"patient": {"diagnosis": "NET"}}
    agent.save_profile(profile)

    # Re-date the only backup three days back, exactly as a writer that stopped
    # working three days ago would leave the directory, and keep the profile
    # saved today.
    _restamp_backup(cfg.DATA_DIR / "backups", 3, 12)

    body = client.get("/api/health").get_json()

    assert body["profile_age_seconds"] < 60
    assert body["newest_backup_age_seconds"] > 2 * 24 * 3600
    assert body["backup_out_of_date"] is True
    assert body["status"] == "degraded"


def test_recovery_from_an_old_candidate_does_not_leave_health_degraded(agent, client):
    """Restoring an old backup must not report the storage as out of date.

    ``restore_from_candidate`` gives the profile a current mtime, so without a
    backup of the restored state the newest backup would trail it by whole
    calendar days and degrade until the caregiver happened to save something.
    """
    import agent.config as cfg
    from agent import recovery

    agent.save_profile({"patient": {"diagnosis": "NET"}})

    backups_dir = cfg.DATA_DIR / "backups"
    restored = _restamp_backup(backups_dir, 5, 9)[0]

    recovery.restore_from_candidate(recovery.RecoveryCandidate(restored, "daily_backup"))

    body = client.get("/api/health").get_json()

    assert body["profile_status"] == "ok"
    assert body["profile_age_seconds"] < 60
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_backup_one_day_behind_a_save_degrades(agent, client):
    """Yesterday's backup plus a save today means today's backup never landed.

    The tolerance is zero on purpose: a whole day of slack would let a writer
    that broke yesterday and then saw no further saves sit at a lag of exactly
    one forever and never be reported.
    """
    import agent.config as cfg
    from agent import backups

    assert backups.BACKUP_MAX_LAG_DAYS == 0

    agent.save_profile({"patient": {"diagnosis": "NET"}})

    _restamp_backup(cfg.DATA_DIR / "backups", 1, 12)

    body = client.get("/api/health").get_json()

    assert body["backup_out_of_date"] is True
    assert body["status"] == "degraded"


def test_backup_newer_than_profile_after_restore_is_healthy(agent, client):
    """A restore can leave the backup ahead of the profile; that is not a fault."""
    import agent.config as cfg

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    _stamp(cfg.PROFILE_PATH, 2, 12)

    body = client.get("/api/health").get_json()

    assert body["profile_age_seconds"] > 24 * 3600
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_unreadable_backup_timestamp_degrades_without_crashing(agent, client, monkeypatch):
    """A timestamp that is not a representable date must degrade, not 500."""
    from agent import backups

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    monkeypatch.setattr(backups, "backup_lag_days", lambda *_args: None)

    resp = client.get("/api/health")
    body = resp.get_json()

    assert resp.status_code == 200
    assert body["backup_out_of_date"] is True
    assert body["status"] == "degraded"


def test_missing_backup_degrades_health(agent, client):
    """No daily backup at all is still a real fault."""
    import agent.config as cfg

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    shutil.rmtree(cfg.DATA_DIR / "backups")

    body = client.get("/api/health").get_json()

    assert body["profile_status"] == "ok"
    assert body["newest_backup_age_seconds"] is None
    assert body["backup_out_of_date"] is True
    assert body["status"] == "degraded"


def test_backup_signal_suppressed_when_profile_not_ok(agent):
    """``profile_status != "ok"`` still suppresses the storage-freshness signal."""
    import importlib
    import sys

    import agent.config as cfg

    cfg.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.PROFILE_PATH.write_bytes(b"{{not-valid-json}}")

    if "app" in sys.modules:
        del sys.modules["app"]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True

    body = app_mod.app.test_client().get("/api/health").get_json()

    assert body["profile_status"] == "invalid_json"
    assert body["newest_backup_age_seconds"] is None
    assert body["backup_out_of_date"] is False
    assert body["status"] == "error"


# ── snapshot age is informational and must never raise an alarm ───────────────
#
# ``rotating_snapshot`` copies the PRE-write profile with ``shutil.copy2``,
# which preserves the source mtime.  The newest snapshot therefore carries the
# *previous* profile revision's mtime and is older than the profile by
# construction on every save.


def test_stale_snapshot_age_after_idle_week_is_healthy(agent, client):
    """A fresh snapshot inherits an eight-day-old mtime and must not degrade."""
    import agent.config as cfg

    profile = {"patient": {"diagnosis": "NET"}}
    agent.save_profile(profile)

    eight_days = 8 * 24 * 3600
    _restamp_backup(cfg.DATA_DIR / "backups", 8, 10)
    _stamp(cfg.PROFILE_PATH, 8, 10)

    # First edit in eight days.  This writes a brand-new snapshot, but copy2
    # stamps it with the eight-day-old source mtime, and daily_backup writes a
    # fresh backup for today.
    profile["patient"]["stage"] = "IV"
    agent.save_profile(profile)

    body = client.get("/api/health").get_json()

    assert list((cfg.DATA_DIR / "snapshots").glob("profile_*.json"))
    assert body["newest_snapshot_age_seconds"] > eight_days - 24 * 3600
    assert body["profile_age_seconds"] < 60
    assert body["backup_out_of_date"] is False
    assert body["status"] == "ok"


def test_snapshot_older_than_profile_on_every_save_is_healthy(agent, client):
    """Snapshot age exceeding profile age is structural, never a fault."""
    profile = {"patient": {"diagnosis": "NET"}}
    agent.save_profile(profile)
    time.sleep(0.01)
    profile["patient"]["stage"] = "IV"
    agent.save_profile(profile)

    body = client.get("/api/health").get_json()

    assert body["newest_snapshot_age_seconds"] >= body["profile_age_seconds"]
    assert body["status"] == "ok"


# ── deploy gate contract ──────────────────────────────────────────────────────


def test_health_payload_keeps_deploy_gate_contract(agent, client):
    """Scripts/deploy.ps1 reads these exact fields; none may be renamed."""
    agent.save_profile({"patient": {"diagnosis": "NET"}})
    resp = client.get("/api/health")
    body = resp.get_json()

    assert resp.status_code == 200
    for key in ("status", "data_dir_writable", "jobs_healthy", "release_commit"):
        assert key in body
    # deploy.ps1 accepts only these two values and requires both flags truthy.
    assert body["status"] in ("ok", "degraded")
    assert body["data_dir_writable"] is True
    assert body["jobs_healthy"] is True
    # Fields other tooling and the operating manual document.
    for key in (
        "newest_backup_age_seconds",
        "newest_snapshot_age_seconds",
        "profile_age_seconds",
        "backup_out_of_date",
    ):
        assert key in body


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
