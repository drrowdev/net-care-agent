"""Tests for recovery hardening: quarantine, snapshot validation, restoration.

All tests are no-network and use only temp directories.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    """Isolated DATA_DIR wired into agent.config for each test."""
    import agent.backups as bk
    import agent.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    # backups uses DATA_DIR at call time, but BACKUPS_DIR is a module-level
    # constant — redirect via monkeypatch.
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")
    return tmp_path


@pytest.fixture
def valid_profile_bytes() -> bytes:
    return json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()


def _write_profile(directory: Path, content: bytes | str) -> Path:
    pp = directory / "patient_profile.json"
    if isinstance(content, str):
        pp.write_text(content, encoding="utf-8")
    else:
        pp.write_bytes(content)
    return pp


def _write_snapshot(
    directory: Path, content: bytes, *, name: str = "profile_20260101_120000_000000.json"
) -> Path:
    sdir = directory / "snapshots"
    sdir.mkdir(parents=True, exist_ok=True)
    snap = sdir / name
    snap.write_bytes(content)
    return snap


def _write_backup(directory: Path, content: bytes, *, name: str = "profile_20260101.json") -> Path:
    bdir = directory / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    bkp = bdir / name
    bkp.write_bytes(content)
    return bkp


# ── structural_check ──────────────────────────────────────────────────────────


def test_structural_check_valid_dict():
    from agent.schema import structural_check

    assert structural_check({"patient": {"diagnosis": "NET"}, "biomarkers": []})


def test_structural_check_empty_dict():
    from agent.schema import structural_check

    assert structural_check({})  # all missing keys → coercible


def test_structural_check_none_patient_coercible():
    from agent.schema import structural_check

    assert structural_check({"patient": None})


def test_structural_check_none_collection_coercible():
    from agent.schema import structural_check

    assert structural_check({"biomarkers": None})


def test_structural_check_string_is_invalid():
    from agent.schema import structural_check

    assert not structural_check("not-a-dict")


def test_structural_check_list_is_invalid():
    from agent.schema import structural_check

    assert not structural_check([{"patient": {}}])


def test_structural_check_patient_string_is_invalid():
    from agent.schema import structural_check

    assert not structural_check({"patient": "not-a-dict"})


def test_structural_check_collection_non_list_invalid():
    from agent.schema import structural_check

    assert not structural_check({"biomarkers": "not-a-list"})
    assert not structural_check({"imaging": 42})


def test_structural_check_none_raises_false():
    from agent.schema import structural_check

    assert not structural_check(None)


# ── quarantine_profile ────────────────────────────────────────────────────────


def test_quarantine_writes_forensic_copy(profile_dir, valid_profile_bytes):
    from agent.recovery import quarantine_profile

    pp = _write_profile(profile_dir, valid_profile_bytes)
    qpath = quarantine_profile(pp, reason="test_quarantine", raw_bytes=valid_profile_bytes)
    assert qpath.exists()
    assert qpath.parent.name == "quarantine"
    # Forensic copy preserved the content.
    assert qpath.read_bytes() == valid_profile_bytes


def test_quarantine_does_not_remove_original(profile_dir, valid_profile_bytes):
    """Quarantine is a copy; recovery overwrites the original."""
    from agent.recovery import quarantine_profile

    pp = _write_profile(profile_dir, valid_profile_bytes)
    quarantine_profile(pp, reason="test", raw_bytes=valid_profile_bytes)
    # Original still present (recovery will atomically replace it).
    assert pp.exists()


def test_quarantine_filename_contains_hash_prefix(profile_dir, valid_profile_bytes):
    import hashlib

    from agent.recovery import quarantine_profile

    pp = _write_profile(profile_dir, valid_profile_bytes)
    qpath = quarantine_profile(pp, reason="test", raw_bytes=valid_profile_bytes)
    expected_hash = hashlib.sha256(valid_profile_bytes).hexdigest()[:8]
    assert expected_hash in qpath.name


# ── validate_candidate ────────────────────────────────────────────────────────


def test_validate_candidate_valid(profile_dir, valid_profile_bytes):
    from agent.recovery import _validate_candidate

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    result = _validate_candidate(snap)
    assert result is not None
    assert result["patient"]["diagnosis"] == "NET"


def test_validate_candidate_corrupt_json(profile_dir):
    from agent.recovery import _validate_candidate

    snap = _write_snapshot(profile_dir, b"{{not valid json")
    assert _validate_candidate(snap) is None


def test_validate_candidate_invalid_shape(profile_dir):
    from agent.recovery import _validate_candidate

    snap = _write_snapshot(profile_dir, json.dumps({"patient": "string"}).encode())
    assert _validate_candidate(snap) is None


def test_validate_candidate_missing_file(profile_dir):
    from pathlib import Path

    from agent.recovery import _validate_candidate

    assert _validate_candidate(Path(profile_dir / "nonexistent.json")) is None


def test_validate_candidate_sidecar_hash_valid(profile_dir, valid_profile_bytes):
    """Candidate passes when sidecar hash matches."""
    import hashlib

    from agent.recovery import _validate_candidate

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    digest = hashlib.sha256(valid_profile_bytes).hexdigest()
    snap.with_suffix(snap.suffix + ".sha256").write_text(digest + "\n")
    result = _validate_candidate(snap)
    assert result is not None


def test_validate_candidate_sidecar_hash_mismatch(profile_dir, valid_profile_bytes):
    """Candidate fails when sidecar hash does not match content."""
    from agent.recovery import _validate_candidate

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    snap.with_suffix(snap.suffix + ".sha256").write_text("0" * 64 + "\n")
    result = _validate_candidate(snap)
    assert result is None


# ── find_recovery_candidates ──────────────────────────────────────────────────


def test_find_recovery_candidates_newer_backup_before_older_snapshot(
    profile_dir, valid_profile_bytes
):
    import os

    from agent.recovery import find_recovery_candidates

    snapshot = _write_snapshot(profile_dir, valid_profile_bytes)
    backup = _write_backup(profile_dir, valid_profile_bytes)
    os.utime(snapshot, (100, 100))
    os.utime(backup, (200, 200))
    candidates = find_recovery_candidates()
    assert candidates[0].source == "daily_backup"


def test_find_recovery_candidates_newest_first(profile_dir, valid_profile_bytes):
    from agent.recovery import find_recovery_candidates

    _write_snapshot(profile_dir, valid_profile_bytes, name="profile_20260101_100000_000000.json")
    s2 = _write_snapshot(
        profile_dir, valid_profile_bytes, name="profile_20260102_100000_000000.json"
    )
    candidates = [c for c in find_recovery_candidates() if c.source == "snapshot"]
    # Newest first — lexicographic reverse gives 20260102 before 20260101.
    assert candidates[0].path.name == s2.name


def test_find_recovery_candidates_empty_dirs(profile_dir):
    from agent.recovery import find_recovery_candidates

    candidates = find_recovery_candidates()
    assert candidates == []


# ── recover_profile ───────────────────────────────────────────────────────────


def test_recover_profile_from_snapshot(profile_dir, valid_profile_bytes):
    """recover_profile uses the newest valid snapshot."""
    import agent.config as cfg
    from agent.recovery import recover_profile

    _write_profile(profile_dir, b"corrupt")
    _write_snapshot(profile_dir, valid_profile_bytes)
    data = recover_profile()
    assert data["patient"]["diagnosis"] == "NET"
    # The profile file has been restored.
    restored = json.loads(cfg.PROFILE_PATH.read_bytes())
    assert restored["patient"]["diagnosis"] == "NET"


def test_recover_profile_from_backup_when_no_snapshot(profile_dir, valid_profile_bytes):
    """recover_profile falls back to daily backup when no snapshot is valid."""
    from agent.recovery import recover_profile

    _write_profile(profile_dir, b"corrupt")
    _write_backup(profile_dir, valid_profile_bytes)
    data = recover_profile()
    assert data["patient"]["diagnosis"] == "NET"


def test_recover_profile_skips_invalid_snapshot(profile_dir, valid_profile_bytes):
    """Invalid newest snapshot is skipped; next valid candidate is used."""
    from agent.recovery import recover_profile

    _write_profile(profile_dir, b"corrupt")
    # Newest snapshot is invalid.
    _write_snapshot(
        profile_dir,
        b"{{bad json",
        name="profile_20260202_120000_000000.json",
    )
    # Older snapshot is valid.
    _write_snapshot(
        profile_dir,
        valid_profile_bytes,
        name="profile_20260101_120000_000000.json",
    )
    data = recover_profile()
    assert data["patient"]["diagnosis"] == "NET"


def test_recover_profile_no_candidates_raises(profile_dir):
    """NoRecoveryCandidateError when no valid snapshot or backup exists."""
    from agent.recovery import NoRecoveryCandidateError, recover_profile

    _write_profile(profile_dir, b"corrupt")
    with pytest.raises(NoRecoveryCandidateError):
        recover_profile()


# ── load_profile integration ──────────────────────────────────────────────────


def test_load_profile_corrupt_json_quarantine_and_recover(tmp_path, monkeypatch):
    """load_profile: corrupt JSON → quarantine + recover from snapshot."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()
    _write_profile(tmp_path, b"{{not-valid-json}}")
    _write_snapshot(tmp_path, valid)

    loaded = load_profile()
    assert isinstance(loaded, dict)
    assert isinstance(loaded["patient"], dict)
    assert isinstance(loaded["biomarkers"], list)

    # Quarantine dir must exist with a forensic copy.
    qfiles = list((tmp_path / "quarantine").glob("patient_profile_*.json"))
    assert len(qfiles) == 1


def test_load_profile_invalid_shape_quarantine_and_recover(tmp_path, monkeypatch):
    """load_profile: invalid shape (patient=42) → quarantine + recover."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    invalid = json.dumps({"patient": 42}).encode()
    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()
    _write_profile(tmp_path, invalid)
    _write_snapshot(tmp_path, valid)

    loaded = load_profile()
    assert isinstance(loaded["patient"], dict)
    qfiles = list((tmp_path / "quarantine").glob("*.json"))
    assert len(qfiles) == 1


def test_load_profile_clinically_empty_recovers_existing_data(tmp_path, monkeypatch):
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")
    _write_profile(tmp_path, "{}")
    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()
    _write_backup(tmp_path, valid)

    loaded = load_profile()

    assert loaded["patient"]["diagnosis"] == "NET"


def test_missing_profile_recovers_backup_instead_of_creating_default(tmp_path, monkeypatch):
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")
    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "Recovered NET"}, "biomarkers": []}
    ).encode()
    _write_backup(tmp_path, valid)

    loaded = load_profile()

    assert loaded["patient"]["diagnosis"] == "Recovered NET"


def test_missing_initialized_profile_without_backup_fails_loudly(tmp_path, monkeypatch):
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import CorruptProfileError, load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".profile-initialized").write_text("initialized\n")

    with pytest.raises(CorruptProfileError, match="missing"):
        load_profile()


def test_quarantine_uses_authoritative_under_lock_bytes(profile_dir, valid_profile_bytes):
    from agent.profile import _quarantine_and_recover

    path = _write_profile(profile_dir, b"authoritative corrupt")
    _write_snapshot(profile_dir, valid_profile_bytes)

    _quarantine_and_recover(path, b"stale corrupt", "json_decode_error")

    quarantined = list((profile_dir / "quarantine").glob("patient_profile_*.json"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"authoritative corrupt"


def test_repeated_failed_recovery_deduplicates_quarantine(tmp_path, monkeypatch):
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import CorruptProfileError, load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")
    _write_profile(tmp_path, b"same corrupt bytes")

    for _ in range(2):
        with pytest.raises(CorruptProfileError):
            load_profile()

    quarantined = list((tmp_path / "quarantine").glob("patient_profile_*.json"))
    assert len(quarantined) == 1


def test_load_profile_no_recovery_raises_corrupt_error(tmp_path, monkeypatch):
    """load_profile: corrupt + no candidates → CorruptProfileError."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import CorruptProfileError, load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    _write_profile(tmp_path, b"{{bad")
    with pytest.raises(CorruptProfileError):
        load_profile()


def test_load_profile_transient_io_error_not_quarantined(tmp_path, monkeypatch):
    """Transient I/O error (OSError) raises IOProfileError — no quarantine."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import IOProfileError, load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    # Create a valid profile file but patch read_bytes to raise OSError.
    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()
    _write_profile(tmp_path, valid)

    import agent.profile as prof

    def _raise_io(path):
        raise OSError("simulated transient I/O error")

    monkeypatch.setattr(prof.Path, "read_bytes", _raise_io)

    with pytest.raises(IOProfileError):
        load_profile()

    # No quarantine dir should have been created.
    assert not (tmp_path / "quarantine").exists()


def test_load_profile_valid_profile_not_quarantined(tmp_path, monkeypatch):
    """Valid profile: no quarantine dir created."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    valid = json.dumps(
        {"schema_version": 1, "patient": {"diagnosis": "NET"}, "biomarkers": []}
    ).encode()
    _write_profile(tmp_path, valid)

    loaded = load_profile()
    assert loaded["patient"]["diagnosis"] == "NET"
    assert not (tmp_path / "quarantine").exists()


# ── save_profile structural guard ─────────────────────────────────────────────


def test_save_profile_rejects_non_dict(agent):
    """save_profile refuses non-dict data."""
    with pytest.raises(ValueError, match="structurally invalid"):
        agent.save_profile(["not", "a", "dict"])  # type: ignore[arg-type]


def test_save_profile_rejects_string_patient(agent):
    """save_profile refuses patient=string."""
    with pytest.raises(ValueError, match="structurally invalid"):
        agent.save_profile({"patient": "not-a-dict", "biomarkers": []})


def test_save_profile_rejects_non_list_collection(agent):
    """save_profile refuses biomarkers='string'."""
    with pytest.raises(ValueError, match="structurally invalid"):
        agent.save_profile({"patient": {}, "biomarkers": "not-a-list"})


def test_save_profile_allows_none_patient(agent):
    """save_profile allows None patient (safely coercible — structural guard passes)."""
    # Should NOT raise; structural check returns True for None patient.
    agent.save_profile({"patient": None, "biomarkers": []})


# ── migration integration with load_profile ───────────────────────────────────


def test_load_profile_runs_migrations_on_unversioned(tmp_path, monkeypatch):
    """load_profile applies migration 0001 to an unversioned profile."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    unversioned = json.dumps({"patient": {"diagnosis": "NET"}, "biomarkers": []}).encode()
    _write_profile(tmp_path, unversioned)

    loaded = load_profile()
    assert loaded["schema_version"] == CURRENT_SCHEMA_VERSION
    assert "_migration_log" in loaded
    assert loaded["_migration_log"][0]["id"] == "0001_add_schema_version"


def test_load_profile_current_version_no_migration_log_added(tmp_path, monkeypatch):
    """load_profile on a current-version profile does not add a migration log."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    current = json.dumps(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "patient": {"diagnosis": "NET"},
            "biomarkers": [],
        }
    ).encode()
    _write_profile(tmp_path, current)

    loaded = load_profile()
    # _migration_log not injected when already current.
    assert "_migration_log" not in loaded or loaded.get("_migration_log") == []


# ── quarantine_and_recover: OSError on under-lock re-read ────────────────────


def test_quarantine_and_recover_oserror_on_reread_raises_ioprofile_error(tmp_path, monkeypatch):
    """If the under-lock re-read raises OSError, IOProfileError is raised
    immediately — no quarantine dir created, profile file preserved."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import IOProfileError, load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    # Write a corrupt profile so the first read triggers quarantine-and-recover.
    corrupt = b"{{not-valid-json}}"
    _write_profile(tmp_path, corrupt)

    # First read of file (in _load_validated) succeeds (returns corrupt bytes).
    # Second read (in _quarantine_and_recover, under lock) raises OSError.
    call_count = [0]
    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self):
        if self == cfg.PROFILE_PATH:
            call_count[0] += 1
            if call_count[0] == 1:
                return corrupt  # first read: return corrupt bytes
            raise OSError("simulated I/O error on re-read")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)

    with pytest.raises(IOProfileError, match="re-read"):
        load_profile()

    # No quarantine dir must have been created.
    assert not (tmp_path / "quarantine").exists()
    # Original file must still be present (not removed or overwritten).
    profile_path = tmp_path / "patient_profile.json"
    assert profile_path.exists()
    with open(profile_path, "rb") as fh:
        content = fh.read()
    assert content == corrupt


# ── migration persistence integration ────────────────────────────────────────


def test_migration_persisted_to_disk_on_first_load(tmp_path, monkeypatch):
    """Loading an unversioned profile writes schema_version + _migration_log
    to disk atomically; clinical data is preserved."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    unversioned = json.dumps(
        {"patient": {"diagnosis": "NET"}, "biomarkers": [], "custom_field": 42}
    ).encode()
    _write_profile(tmp_path, unversioned)

    loaded = load_profile()
    assert loaded["schema_version"] == CURRENT_SCHEMA_VERSION

    on_disk = json.loads((tmp_path / "patient_profile.json").read_bytes())
    assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION
    assert "_migration_log" in on_disk
    assert on_disk["_migration_log"][0]["id"] == "0001_add_schema_version"
    # Clinical data preserved, unknown field preserved.
    assert on_disk["patient"]["diagnosis"] == "NET"
    assert on_disk["custom_field"] == 42


def test_second_load_leaves_file_unchanged(tmp_path, monkeypatch):
    """After migration is persisted on first load, the second load does NOT
    rewrite the file — bytes and mtime are identical."""
    import time

    import agent.backups as bk
    import agent.config as cfg
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    unversioned = json.dumps({"patient": {"diagnosis": "NET"}, "biomarkers": []}).encode()
    _write_profile(tmp_path, unversioned)

    # First load — triggers migration + persistence.
    load_profile()
    profile_path = tmp_path / "patient_profile.json"
    bytes_after_first = profile_path.read_bytes()
    mtime_after_first = profile_path.stat().st_mtime

    time.sleep(0.05)  # ensure mtime would differ if a write occurred

    # Second load — must not rewrite the file.
    load_profile()
    bytes_after_second = profile_path.read_bytes()
    mtime_after_second = profile_path.stat().st_mtime

    assert bytes_after_second == bytes_after_first, "File was rewritten on second load"
    assert mtime_after_second == mtime_after_first, "File mtime changed on second load"


def test_recovered_snapshot_persisted_in_migrated_form(tmp_path, monkeypatch):
    """When a corrupt profile is recovered from an unversioned snapshot,
    the restored file on disk is in migrated form (schema_version set)."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    # Corrupt current profile, unversioned snapshot available.
    _write_profile(tmp_path, b"{{corrupt}}")
    unversioned_snap = json.dumps({"patient": {"diagnosis": "NET"}, "biomarkers": []}).encode()
    _write_snapshot(tmp_path, unversioned_snap)

    loaded = load_profile()
    assert loaded["schema_version"] == CURRENT_SCHEMA_VERSION

    on_disk = json.loads((tmp_path / "patient_profile.json").read_bytes())
    assert (
        on_disk["schema_version"] == CURRENT_SCHEMA_VERSION
    ), "Disk still has unversioned snapshot; migrated form was not written"


# ── restore_from_candidate / recover_profile acquire lock ────────────────────


def test_restore_from_candidate_acquires_lock(profile_dir, valid_profile_bytes):
    """restore_from_candidate can be called directly (not only from within a
    serialized_mutation block) — it acquires the lock itself."""
    from agent.recovery import RecoveryCandidate, restore_from_candidate
    from agent.serialize import mutating_lock

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    _write_profile(profile_dir, b"corrupt")

    # Must not raise even without an outer serialized_mutation block.
    data = restore_from_candidate(RecoveryCandidate(snap, "snapshot"))
    assert data["patient"]["diagnosis"] == "NET"
    # Lock must be fully released after the call.
    assert mutating_lock.acquire(blocking=False)
    mutating_lock.release()


def test_recover_profile_acquires_lock(profile_dir, valid_profile_bytes):
    """recover_profile can be called directly without a surrounding lock."""
    from agent.recovery import recover_profile
    from agent.serialize import mutating_lock

    _write_profile(profile_dir, b"corrupt")
    _write_snapshot(profile_dir, valid_profile_bytes)

    data = recover_profile()
    assert isinstance(data, dict)
    # Lock must be fully released.
    assert mutating_lock.acquire(blocking=False)
    mutating_lock.release()


# ── migration concurrency regression ─────────────────────────────────────────


def test_migration_concurrency_no_downgrade_future_version(tmp_path, monkeypatch):
    """Concurrency regression: the outer read sees a legacy (unversioned) profile,
    but the under-lock re-read inside _persist_migration_metadata finds a
    future/current-version profile already written by another process.

    _persist_migration_metadata must:
    - NOT write to disk (no downgrade, no overwrite of the concurrent migration log).
    - Return the authoritative on-disk data, not the stale pre-lock data.
    - load_profile must return that authoritative result.
    """
    import agent.backups as bk
    import agent.config as cfg
    import agent.profile as prof_mod
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    # Outer read: legacy bytes (no schema_version).
    legacy_bytes = json.dumps({"patient": {"diagnosis": "LEGACY"}, "biomarkers": []}).encode()

    # Under-lock re-read: future version written by a concurrent process.
    future_version = CURRENT_SCHEMA_VERSION + 1
    authoritative_data = {
        "schema_version": future_version,
        "patient": {"diagnosis": "AUTHORITATIVE"},
        "biomarkers": [],
        "_migration_log": [{"id": "future_only", "applied_at": "2099-01-01T00:00:00"}],
        "custom_clinical_field": "preserved",
    }
    authoritative_bytes = json.dumps(authoritative_data).encode()

    pp = tmp_path / "patient_profile.json"
    pp.write_bytes(legacy_bytes)

    # First call → legacy bytes; all subsequent (under-lock) → authoritative.
    call_count = [0]
    original_read_bytes = Path.read_bytes

    def _patched(self):
        if self == cfg.PROFILE_PATH:
            call_count[0] += 1
            return legacy_bytes if call_count[0] == 1 else authoritative_bytes
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched)

    # Track any atomic_write_text calls targeting PROFILE_PATH.
    writes_to_profile: list[str] = []
    original_atomic = prof_mod.atomic_write_text

    def _track_write(path, content):
        if Path(path) == cfg.PROFILE_PATH:
            writes_to_profile.append(content)
        return original_atomic(path, content)

    monkeypatch.setattr(prof_mod, "atomic_write_text", _track_write)

    result = load_profile()

    # Must return authoritative data, not stale legacy.
    assert (
        result["patient"]["diagnosis"] == "AUTHORITATIVE"
    ), "load_profile returned stale legacy data instead of authoritative on-disk data"
    # Future schema_version must be preserved — not downgraded.
    assert (
        result.get("schema_version") == future_version
    ), "schema_version was downgraded from future version"
    # Future migration log must be intact — not overwritten.
    assert any(
        e.get("id") == "future_only" for e in result.get("_migration_log", [])
    ), "Future migration log was overwritten"
    # No disk write during migration persistence (future version → no-op on disk).
    assert (
        writes_to_profile == []
    ), f"_persist_migration_metadata wrote to disk for future-version profile: {writes_to_profile}"


def test_migration_concurrency_no_downgrade_current_version(tmp_path, monkeypatch):
    """Same regression: outer read sees legacy, under-lock re-read is already at
    CURRENT_SCHEMA_VERSION (migrated by another process).  Disk must not be
    rewritten and the current-version authoritative data must be returned."""
    import agent.backups as bk
    import agent.config as cfg
    import agent.profile as prof_mod
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    legacy_bytes = json.dumps({"patient": {"diagnosis": "LEGACY"}, "biomarkers": []}).encode()
    current_data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "patient": {"diagnosis": "ALREADY_MIGRATED"},
        "biomarkers": [],
        "_migration_log": [{"id": "0001_add_schema_version", "applied_at": "2026-01-01T00:00:00"}],
    }
    current_bytes = json.dumps(current_data).encode()

    pp = tmp_path / "patient_profile.json"
    pp.write_bytes(legacy_bytes)

    call_count = [0]
    original_read_bytes = Path.read_bytes

    def _patched(self):
        if self == cfg.PROFILE_PATH:
            call_count[0] += 1
            return legacy_bytes if call_count[0] == 1 else current_bytes
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched)

    writes_to_profile: list[str] = []
    original_atomic = prof_mod.atomic_write_text

    def _track_write(path, content):
        if Path(path) == cfg.PROFILE_PATH:
            writes_to_profile.append(content)
        return original_atomic(path, content)

    monkeypatch.setattr(prof_mod, "atomic_write_text", _track_write)

    result = load_profile()

    assert result["patient"]["diagnosis"] == "ALREADY_MIGRATED"
    assert result.get("schema_version") == CURRENT_SCHEMA_VERSION
    # Original log timestamp must be preserved (not overwritten by a new apply).
    log_entry = next(
        (e for e in result.get("_migration_log", []) if e.get("id") == "0001_add_schema_version"),
        None,
    )
    assert log_entry is not None
    assert (
        log_entry.get("applied_at") == "2026-01-01T00:00:00"
    ), "Migration log timestamp was overwritten by a second apply_migrations run"
    assert writes_to_profile == [], "Disk was rewritten for already-current profile"


def test_migration_reread_corruption_enters_recovery(tmp_path, monkeypatch):
    """A file corrupted after the optimistic legacy read is recovered, not served stale."""
    import agent.backups as bk
    import agent.config as cfg
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.profile import load_profile

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    monkeypatch.setattr(bk, "BACKUPS_DIR", tmp_path / "backups")

    legacy = {"patient": {"diagnosis": "STALE"}, "biomarkers": []}
    recovered = {"patient": {"diagnosis": "RECOVERED"}, "biomarkers": []}
    cfg.PROFILE_PATH.write_text(json.dumps(legacy))
    _write_backup(tmp_path, json.dumps(recovered).encode())

    original_read_bytes = Path.read_bytes
    first_profile_read = True

    def _corrupt_after_first_read(self):
        nonlocal first_profile_read
        content = original_read_bytes(self)
        if self == cfg.PROFILE_PATH and first_profile_read:
            first_profile_read = False
            self.write_bytes(b"{{corrupt-after-optimistic-read")
        return content

    monkeypatch.setattr(Path, "read_bytes", _corrupt_after_first_read)

    result = load_profile()

    assert result["patient"]["diagnosis"] == "RECOVERED"
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    assert json.loads(cfg.PROFILE_PATH.read_text())["patient"]["diagnosis"] == "RECOVERED"
    assert list((tmp_path / "quarantine").glob("patient_profile_*.json"))


# ── recovery state sidecar ───────────────────────────────────────────────────


def test_get_recovery_state_returns_none_when_no_sidecar(profile_dir):
    """get_recovery_state returns state='none' when no sidecar exists."""
    from agent.recovery import get_recovery_state

    state = get_recovery_state()
    assert state["state"] == "none"


def test_recovery_sidecar_written_on_successful_restore(profile_dir, valid_profile_bytes):
    """restore_from_candidate writes a 'recovered' sidecar on success."""
    import agent.config as cfg
    from agent.recovery import RecoveryCandidate, get_recovery_state, restore_from_candidate

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    _write_profile(profile_dir, b"corrupt")

    restore_from_candidate(RecoveryCandidate(snap, "snapshot"))

    state = get_recovery_state()
    assert state["state"] == "recovered"
    assert state["source"] == "snapshot"
    assert state.get("timestamp") is not None
    # Sidecar must exist.
    assert (cfg.DATA_DIR / "recovery_state.json").exists()


def test_recovery_sidecar_written_on_failure(profile_dir):
    """recover_profile writes a 'failed' sidecar when no valid candidate exists."""
    from agent.recovery import NoRecoveryCandidateError, get_recovery_state, recover_profile

    _write_profile(profile_dir, b"corrupt")

    with pytest.raises(NoRecoveryCandidateError):
        recover_profile()

    state = get_recovery_state()
    assert state["state"] == "failed"


def test_get_recovery_state_no_phi_or_paths(profile_dir, valid_profile_bytes):
    """Recovery state sidecar and get_recovery_state return no PHI or paths."""
    import agent.config as cfg
    from agent.recovery import RecoveryCandidate, get_recovery_state, restore_from_candidate

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    _write_profile(profile_dir, b"corrupt")
    restore_from_candidate(RecoveryCandidate(snap, "snapshot"))

    sidecar_text = (cfg.DATA_DIR / "recovery_state.json").read_text()
    state = get_recovery_state()
    combined = json.dumps(state) + sidecar_text

    # No clinical content.
    assert "NET" not in combined
    assert "diagnosis" not in combined
    # No filesystem paths.
    assert str(cfg.DATA_DIR) not in combined
    assert "patient_profile" not in combined
    assert "/home/" not in combined


def test_recovery_sidecar_failure_does_not_break_recovery(
    profile_dir, valid_profile_bytes, monkeypatch
):
    """A sidecar write failure must never propagate — recovery succeeds anyway."""
    import agent.recovery as rec_mod
    from agent.recovery import RecoveryCandidate, restore_from_candidate

    def _bad_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rec_mod, "_write_recovery_sidecar", _bad_write)

    snap = _write_snapshot(profile_dir, valid_profile_bytes)
    _write_profile(profile_dir, b"corrupt")

    # Must not raise even though sidecar write fails.
    data = restore_from_candidate(RecoveryCandidate(snap, "snapshot"))
    assert data["patient"]["diagnosis"] == "NET"
