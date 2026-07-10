"""Tests for agent/migrations.py — schema versioning and idempotent migrations."""

from __future__ import annotations

import copy

# ── helpers ───────────────────────────────────────────────────────────────────


def _unversioned() -> dict:
    """Minimal unversioned profile (no schema_version key)."""
    return {"patient": {"diagnosis": "NET"}, "biomarkers": [{"marker": "CgA"}]}


def _current() -> dict:
    """Profile already at current schema version."""
    from agent.migrations import CURRENT_SCHEMA_VERSION

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "patient": {"diagnosis": "NET"},
        "biomarkers": [],
    }


# ── migration tests ───────────────────────────────────────────────────────────


def test_unversioned_gets_schema_version():
    """Migration 0001 adds schema_version=1 to an unversioned profile."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION


def test_unversioned_migration_records_log_entry():
    """Migration 0001 records a log entry with an applied_at timestamp."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    assert "_migration_log" in result
    log = result["_migration_log"]
    assert isinstance(log, list)
    assert len(log) == 1
    entry = log[0]
    assert entry["id"] == "0001_add_schema_version"
    assert "applied_at" in entry
    # Timestamp must not be "backfilled" for an unversioned profile.
    assert entry["applied_at"] != "backfilled"


def test_already_current_fast_path_no_change():
    """apply_migrations on an already-current profile returns it unchanged."""
    from agent.migrations import apply_migrations

    data = _current()
    original = copy.deepcopy(data)
    result = apply_migrations(data)
    assert result is data  # same object (no copy)
    assert result == original  # no mutation


def test_idempotent_second_apply_no_change():
    """Applying migrations twice produces the same result; log not duplicated."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    once = apply_migrations(data)
    original_log = copy.deepcopy(once["_migration_log"])
    twice = apply_migrations(once)
    assert twice["_migration_log"] == original_log  # unchanged


def test_idempotent_preserves_original_timestamp():
    """A second apply_migrations call preserves the first applied_at timestamp."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    first = apply_migrations(data)
    original_ts = first["_migration_log"][0]["applied_at"]

    second = apply_migrations(first)
    assert second["_migration_log"][0]["applied_at"] == original_ts


def test_unknown_fields_preserved_through_migration():
    """Extra (unknown) fields survive migration unchanged — forward compat."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    data["custom_extension"] = {"flag": 42}
    data["patient"]["my_extra_field"] = "keep_me"

    result = apply_migrations(data)
    assert result["custom_extension"] == {"flag": 42}
    assert result["patient"]["my_extra_field"] == "keep_me"


def test_clinical_values_not_inferred():
    """Migration must not add clinical values that weren't present."""
    from agent.migrations import apply_migrations

    data = {"patient": {}}  # empty patient, unversioned
    result = apply_migrations(data)
    # No clinical fields should be invented.
    patient = result["patient"]
    assert patient.get("diagnosis") is None
    assert patient.get("ki67_percent") is None
    assert patient.get("sstr_status") is None


def test_already_at_version_with_existing_log_unchanged():
    """Profile at current version with a migration log: log is not touched."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "patient": {},
        "_migration_log": [{"id": "0001_add_schema_version", "applied_at": "2026-01-01T00:00:00"}],
    }
    original_log = copy.deepcopy(data["_migration_log"])
    result = apply_migrations(data)
    assert result["_migration_log"] == original_log  # untouched


def test_non_dict_raises_type_error():
    """apply_migrations on non-dict raises TypeError."""
    import pytest

    from agent.migrations import apply_migrations

    with pytest.raises(TypeError, match="expected dict"):
        apply_migrations(["not", "a", "dict"])


def test_null_schema_version_treated_as_unversioned():
    """Explicit schema_version=null is treated as unversioned."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = {"schema_version": None, "patient": {}}
    result = apply_migrations(data)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION


def test_migration_timestamp_is_iso_seconds():
    """Applied-at timestamp uses second-precision ISO format."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    ts = result["_migration_log"][0]["applied_at"]
    import datetime

    parsed = datetime.datetime.fromisoformat(ts)
    assert parsed.microsecond == 0  # seconds precision


def test_forward_schema_version_passes_through_unchanged():
    """A profile with schema_version > CURRENT_SCHEMA_VERSION is returned
    completely unchanged — no backfill, no mutation, no log entries added."""
    import copy

    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    future_version = CURRENT_SCHEMA_VERSION + 5
    data = {
        "schema_version": future_version,
        "patient": {"diagnosis": "NET"},
        "biomarkers": [],
        "future_field": {"x": 1},
    }
    original = copy.deepcopy(data)
    result = apply_migrations(data)
    assert result is data  # same object, no copy
    assert result == original  # no mutation whatsoever
    assert "_migration_log" not in result
