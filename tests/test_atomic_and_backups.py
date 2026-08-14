"""Tests for atomic_write_text + daily backup logic."""

from __future__ import annotations

import datetime
import json
import threading

import pytest


def _profile_temps(config):
    return list(config.DATA_DIR.glob(f".{config.PROFILE_PATH.name}.*.tmp"))


def _noon_today() -> float:
    return datetime.datetime.combine(datetime.date.today(), datetime.time(12)).timestamp()


def test_atomic_write_replaces_target(tmp_path):
    from agent.io import atomic_write_text

    target = tmp_path / "out.json"
    atomic_write_text(target, '{"v": 1}')
    assert target.read_text() == '{"v": 1}'
    atomic_write_text(target, '{"v": 2}')
    assert target.read_text() == '{"v": 2}'
    # No leftover .tmp file
    assert not (tmp_path / "out.json.tmp").exists()


def test_atomic_write_creates_parent_dirs(tmp_path):
    from agent.io import atomic_write_text

    target = tmp_path / "nested" / "dir" / "file.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"


def test_daily_backup_writes_once_per_day(agent, tmp_path, monkeypatch):
    from agent import backups, config

    # Profile must exist for backups to do anything.
    profile = {"patient": {"current_treatments": []}}
    agent.save_profile(profile)

    today = datetime.date.today().isoformat().replace("-", "")
    expected = config.DATA_DIR / "backups" / f"profile_{today}.json"
    assert expected.exists(), "first save_profile should create today's backup"

    # Calling again the same day should NOT create a new backup file.
    mtime_before = expected.stat().st_mtime
    result = backups.daily_backup()
    assert result is None
    assert expected.stat().st_mtime == mtime_before


def test_daily_backup_names_the_file_after_the_profile_mtime(agent, monkeypatch):
    """The filename must agree with the mtime ``copy2`` preserves on the copy.

    A save landing a hair before midnight whose ``daily_backup`` call ran a tick
    after it used to claim tomorrow's filename while carrying yesterday's mtime,
    which then suppressed the following day's real backup. ``/api/health`` reads
    the mtime and judges freshness by calendar day, so the two must not disagree.
    """
    import os

    from agent import backups, config

    agent.save_profile({"patient": {}})

    backups_dir = config.DATA_DIR / "backups"
    for stale in backups_dir.glob("profile_*.json"):
        stale.unlink()

    # The profile was last written at 23:59:59 yesterday.
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    when = datetime.datetime.combine(yesterday, datetime.time(23, 59, 59)).timestamp()
    os.utime(config.PROFILE_PATH, (when, when))

    written = backups.daily_backup()

    assert written is not None
    assert written.name == f"profile_{yesterday.strftime('%Y%m%d')}.json"
    assert datetime.date.fromtimestamp(written.stat().st_mtime) == yesterday
    assert backups.backup_lag_days(when, written.stat().st_mtime) == 0


@pytest.mark.parametrize(
    ("profile_days_ago", "backup_days_ago", "expected"),
    [(0, 0, 0), (0, 1, 1), (0, 2, 2), (1, 0, -1)],
)
def test_backup_lag_days_counts_whole_calendar_days(profile_days_ago, backup_days_ago, expected):
    from agent import backups

    def at(days_ago: int, hour: int) -> float:
        day = datetime.date.today() - datetime.timedelta(days=days_ago)
        return datetime.datetime.combine(day, datetime.time(hour)).timestamp()

    # Deliberately lopsided clock times: only the calendar day may matter, so a
    # backup taken at 00:01 and a save at 23:59 the same day are lag 0.
    lag = backups.backup_lag_days(at(profile_days_ago, 23), at(backup_days_ago, 0))

    assert lag == expected


def test_backup_lag_days_returns_none_for_unrepresentable_timestamps():
    """A corrupt mtime must surface as unknown, never raise into /api/health."""
    from agent import backups

    assert backups.backup_lag_days(1e300, _noon_today()) is None
    assert backups.backup_lag_days(_noon_today(), float("nan")) is None


def test_daily_backup_prunes_old_files(agent, tmp_path, monkeypatch):
    from agent import backups, config

    agent.save_profile({"patient": {}})

    # Drop a fake very-old backup
    old = config.DATA_DIR / "backups" / "profile_20200101.json"
    old.write_text("{}")

    monkeypatch.setattr(backups, "BACKUP_RETENTION_DAYS", 30)
    backups._prune_old(config.DATA_DIR / "backups", 30)

    assert not old.exists(), "files older than retention should be pruned"


def test_save_profile_uses_atomic_write(agent, tmp_path):
    from agent import config

    agent.save_profile({"patient": {"sstr_status": "positive"}})
    # No leftover .tmp sibling
    assert not config.PROFILE_PATH.with_suffix(".json.tmp").exists()
    # Round-trip works
    loaded = agent.load_profile()
    assert loaded["patient"]["sstr_status"] == "positive"


def test_save_profile_temp_write_failure_is_precommit_and_cleans_temp(
    agent, empty_profile, monkeypatch
):
    from agent import config, io

    def fail_profile_fsync(_fd):
        raise OSError("simulated profile temp write failure")

    monkeypatch.setattr(io.os, "fsync", fail_profile_fsync)

    with pytest.raises(OSError, match="temp write failure"):
        agent.save_profile(empty_profile, clinical_change=False)

    assert not config.PROFILE_PATH.exists()
    assert not (config.DATA_DIR / ".profile-initialized").exists()
    assert _profile_temps(config) == []


def test_save_profile_replace_failure_is_precommit_and_cleans_temp(
    agent, empty_profile, monkeypatch
):
    from agent import config, io

    def fail_profile_replace(_source, _destination):
        raise OSError("simulated profile replace failure")

    monkeypatch.setattr(io.os, "replace", fail_profile_replace)

    with pytest.raises(OSError, match="replace failure"):
        agent.save_profile(empty_profile, clinical_change=False)

    assert not config.PROFILE_PATH.exists()
    assert not (config.DATA_DIR / ".profile-initialized").exists()
    assert _profile_temps(config) == []


def test_save_profile_marker_failure_is_nonfatal_and_recoverable(
    agent, empty_profile, monkeypatch, caplog
):
    import agent.profile as profile_module
    from agent import config

    private_error = r"patient-name C:\private\patient_profile.json"
    real_atomic_write = profile_module.atomic_write_text

    def fail_marker(path, content, encoding="utf-8"):
        if path.name == ".profile-initialized":
            raise OSError(private_error)
        return real_atomic_write(path, content, encoding)

    monkeypatch.setattr(profile_module, "atomic_write_text", fail_marker)
    empty_profile["patient"]["diagnosis"] = "Committed NET"

    with caplog.at_level("WARNING"):
        agent.save_profile(empty_profile, clinical_change=False)

    committed = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert committed["patient"]["diagnosis"] == "Committed NET"
    assert not (config.DATA_DIR / ".profile-initialized").exists()
    assert list((config.DATA_DIR / "backups").glob("profile_*.json"))
    assert any(
        "profile_initialized_marker_write_failed" in record.message
        and "after_commit=true" in record.message
        and "error_type=OSError" in record.message
        for record in caplog.records
    )
    assert private_error not in caplog.text

    config.PROFILE_PATH.unlink()
    recovered = agent.load_profile()
    assert recovered["patient"]["diagnosis"] == "Committed NET"
    assert config.PROFILE_PATH.exists()


def test_load_profile_repairs_missing_marker_after_valid_profile(agent, empty_profile):
    from agent import config

    agent.save_profile(empty_profile, clinical_change=False)
    marker = config.DATA_DIR / ".profile-initialized"
    marker.unlink()

    loaded = agent.load_profile()

    assert loaded["profile_revision"] == 0
    assert marker.read_text(encoding="utf-8") == "initialized\n"


def test_atomic_write_uses_unique_sibling_temps(tmp_path, monkeypatch):
    from agent import io

    target = tmp_path / "shared.json"
    real_replace = io.os.replace
    sources = []
    errors = []
    barrier = threading.Barrier(2)
    first_calls = set()
    first_calls_lock = threading.Lock()

    def delayed_replace(source, destination):
        sources.append(source)
        ident = threading.get_ident()
        with first_calls_lock:
            first_for_thread = ident not in first_calls
            first_calls.add(ident)
        if first_for_thread:
            barrier.wait(timeout=3)
        real_replace(source, destination)

    monkeypatch.setattr(io.os, "replace", delayed_replace)

    def write(content):
        try:
            io.atomic_write_text(target, content)
        except BaseException as exc:  # surface thread failures in the test process
            errors.append(exc)

    threads = [
        threading.Thread(target=write, args=('{"writer": 1}',)),
        threading.Thread(target=write, args=('{"writer": 2}',)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(sources) >= 2
    assert sources[0] != sources[1]
    assert all(source.parent == target.parent for source in sources)
    assert not list(tmp_path.glob("*.tmp"))
