"""Tests for atomic_write_text + daily backup logic."""

from __future__ import annotations

import datetime
import threading


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
