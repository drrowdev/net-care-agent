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


def _stamp(path, days_ago: int, hour: int, minute: int = 0) -> None:
    """Pin a file's mtime to an explicit local wall-clock time *days_ago* days back."""
    import os

    day = datetime.date.today() - datetime.timedelta(days=days_ago)
    when = datetime.datetime.combine(day, datetime.time(hour, minute)).timestamp()
    os.utime(path, (when, when))


def _backup_names(config) -> set[str]:
    return {p.name for p in (config.DATA_DIR / "backups").glob("profile_*.json")}


def _snapshot_paths(config) -> set:
    return set((config.DATA_DIR / "snapshots").glob("profile_*.json"))


def _today_backup_name() -> str:
    return f"profile_{datetime.date.today().strftime('%Y%m%d')}.json"


def _age_profile_to_previous_schema(config, days_ago: int = 1) -> None:
    """Leave the data dir exactly as a container restart after a schema bump finds it.

    The stored profile carries the previous release's ``schema_version`` and was
    last saved on an earlier day, so its backup and snapshot both belong to that
    earlier day. The next ``load_profile`` must migrate, which durably rewrites
    the profile.
    """
    from agent.migrations import CURRENT_SCHEMA_VERSION

    stored = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    stored["schema_version"] = CURRENT_SCHEMA_VERSION - 1
    config.PROFILE_PATH.write_text(json.dumps(stored, indent=2), encoding="utf-8")

    day = datetime.date.today() - datetime.timedelta(days=days_ago)
    for path in (config.DATA_DIR / "backups").glob("profile_*.json"):
        renamed = path.rename(
            config.DATA_DIR / "backups" / f"profile_{day.strftime('%Y%m%d')}.json"
        )
        _stamp(renamed, days_ago, 4, 26)
    for path in _snapshot_paths(config):
        _stamp(path, days_ago, 4, 26)
    _stamp(config.PROFILE_PATH, days_ago, 4, 26)


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


# ── every durable profile write must be protected ─────────────────────────────
#
# ``daily_backup`` and ``rotating_snapshot`` used to be wired into
# ``save_profile`` alone, so a write that reached the profile file by any other
# route left the caregiver's current state with no same-day backup and no
# snapshot of the revision it replaced. Migration-on-load is exactly such a
# route and it fires on the first request after every schema bump.


def test_migration_on_load_produces_the_days_backup_and_a_snapshot(agent):
    """The production failure: a deploy migrates the profile and protects nothing.

    ``_persist_migration_metadata`` rewrites the profile under the mutation lock
    when the stored ``schema_version`` is behind the code. That is a durable
    change to the caregiver's data, so it must leave the same artefacts an
    ordinary save leaves: a backup for the day the profile now carries, and a
    snapshot of the revision it overwrote.
    """
    from agent import config
    from agent.migrations import CURRENT_SCHEMA_VERSION

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    _age_profile_to_previous_schema(config, days_ago=1)

    snapshots_before = _snapshot_paths(config)
    assert _today_backup_name() not in _backup_names(config)

    migrated = agent.load_profile()

    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))["schema_version"] == (
        CURRENT_SCHEMA_VERSION
    )
    assert _today_backup_name() in _backup_names(
        config
    ), "the migration write left today's profile with no backup for today"

    new_snapshots = _snapshot_paths(config) - snapshots_before
    assert len(new_snapshots) == 1, "the migration write took no snapshot of the prior revision"
    # ``copy2`` preserves the source mtime, so the snapshot carries the mtime of
    # the pre-migration revision it captured, not the time the copy was made.
    snapshot = new_snapshots.pop()
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    assert datetime.date.fromtimestamp(snapshot.stat().st_mtime) == yesterday


def test_migration_on_load_keeps_an_existing_backup_for_the_day(agent):
    """The once-per-day gate still must not rewrite a good same-day backup."""
    from agent import config

    agent.save_profile({"patient": {"diagnosis": "NET"}})

    today_backup = config.DATA_DIR / "backups" / _today_backup_name()
    assert today_backup.exists()
    original = today_backup.read_bytes()
    mtime_before = today_backup.stat().st_mtime

    from agent.migrations import CURRENT_SCHEMA_VERSION

    stored = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    stored["schema_version"] = CURRENT_SCHEMA_VERSION - 1
    config.PROFILE_PATH.write_text(json.dumps(stored, indent=2), encoding="utf-8")

    agent.load_profile()

    assert today_backup.stat().st_mtime == mtime_before
    assert today_backup.read_bytes() == original


def test_migration_on_load_survives_a_failing_backup_writer(agent, caplog):
    """Protection is best-effort: it may never fail a write that must land."""
    from agent import backups, config
    from agent.migrations import CURRENT_SCHEMA_VERSION

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    _age_profile_to_previous_schema(config, days_ago=1)

    calls: list[str] = []

    def boom(name):
        def _raise(*_args, **_kwargs):
            calls.append(name)
            raise OSError("simulated Azure Files failure")

        return _raise

    original_backup = backups.daily_backup
    original_snapshot = backups.rotating_snapshot
    backups.daily_backup = boom("daily_backup")
    backups.rotating_snapshot = boom("rotating_snapshot")
    try:
        with caplog.at_level("WARNING"):
            migrated = agent.load_profile()
    finally:
        backups.daily_backup = original_backup
        backups.rotating_snapshot = original_snapshot

    # The migration write must have attempted both artefacts; a bare write would
    # leave this empty and the profile silently unprotected.
    assert calls == ["rotating_snapshot", "daily_backup"]
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    on_disk = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION
    assert on_disk["patient"]["diagnosis"] == "NET"


def test_backup_failure_never_fails_a_save(agent, caplog):
    """A save is committed by the atomic replace; protection runs around it."""
    from agent import backups, config

    calls: list[str] = []

    def boom(name):
        def _raise(*_args, **_kwargs):
            calls.append(name)
            raise OSError("simulated Azure Files failure")

        return _raise

    agent.save_profile({"patient": {"diagnosis": "First"}})

    original_backup = backups.daily_backup
    original_snapshot = backups.rotating_snapshot
    backups.daily_backup = boom("daily_backup")
    backups.rotating_snapshot = boom("rotating_snapshot")
    try:
        with caplog.at_level("WARNING"):
            agent.save_profile({"patient": {"diagnosis": "Committed anyway"}})
    finally:
        backups.daily_backup = original_backup
        backups.rotating_snapshot = original_snapshot

    assert calls == ["rotating_snapshot", "daily_backup"]
    committed = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert committed["patient"]["diagnosis"] == "Committed anyway"


def test_restore_failure_of_protection_never_fails_the_restore(agent, caplog):
    """A restore must commit even when neither artefact can be written."""
    from agent import backups, config, recovery

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    candidate = config.DATA_DIR / "backups" / _today_backup_name()
    agent.save_profile({"patient": {"diagnosis": "NET", "stage": "IV"}})

    calls: list[str] = []

    def boom(name):
        def _raise(*_args, **_kwargs):
            calls.append(name)
            raise OSError("simulated Azure Files failure")

        return _raise

    original_backup = backups.daily_backup
    original_snapshot = backups.rotating_snapshot
    backups.daily_backup = boom("daily_backup")
    backups.rotating_snapshot = boom("rotating_snapshot")
    try:
        with caplog.at_level("WARNING"):
            recovery.restore_from_candidate(recovery.RecoveryCandidate(candidate, "manual"))
    finally:
        backups.daily_backup = original_backup
        backups.rotating_snapshot = original_snapshot

    assert calls == ["rotating_snapshot", "daily_backup"]
    restored = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert restored["patient"].get("stage") is None


def test_automated_recovery_does_not_snapshot_the_corrupt_profile(agent):
    """Corrupt bytes are quarantined, not spent on a limited rotating slot.

    They can never be restored, so keeping them would only push a genuinely
    recoverable revision out of the window that the next incident depends on.
    """
    from agent import config

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    agent.save_profile({"patient": {"diagnosis": "NET", "stage": "IV"}})

    snapshots_before = _snapshot_paths(config)
    config.PROFILE_PATH.write_text("{ this is not json", encoding="utf-8")

    recovered = agent.load_profile()

    assert recovered["patient"]["diagnosis"] == "NET"
    assert list((config.DATA_DIR / "quarantine").glob("*.json")), "corrupt bytes must be kept"

    for path in _snapshot_paths(config) - snapshots_before:
        # Whatever was written after the restore must be a usable candidate.
        json.loads(path.read_text(encoding="utf-8"))


def test_restore_snapshots_the_state_it_replaces(agent):
    """A restore destroys the live profile; the state it replaces must survive.

    Restoring an older candidate over a good profile is a durable change like any
    other. Without a pre-write snapshot the caregiver has no way back to the
    revision the restore discarded.
    """
    from agent import config, recovery

    agent.save_profile({"patient": {"diagnosis": "NET"}})
    candidate = config.DATA_DIR / "backups" / _today_backup_name()
    old = json.loads(candidate.read_text(encoding="utf-8"))

    agent.save_profile({"patient": {"diagnosis": "NET", "stage": "IV"}})
    live = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    snapshots_before = _snapshot_paths(config)

    recovery.restore_from_candidate(recovery.RecoveryCandidate(candidate, "daily_backup"))

    restored = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert restored["patient"].get("stage") is None
    assert old["patient"].get("stage") is None

    new_snapshots = _snapshot_paths(config) - snapshots_before
    assert len(new_snapshots) == 1, "the restore discarded the live profile without a snapshot"
    captured = json.loads(new_snapshots.pop().read_text(encoding="utf-8"))
    assert captured["patient"]["stage"] == "IV"
    assert captured["profile_revision"] == live["profile_revision"]
