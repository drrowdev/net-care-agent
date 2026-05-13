"""Tests for atomic_write_text + daily backup logic."""
from __future__ import annotations

import datetime


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
