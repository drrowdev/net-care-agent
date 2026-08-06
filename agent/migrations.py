"""Profile schema migrations.

Deterministic, idempotent migrations from legacy/unversioned profiles to the
current schema version.  Each migration:

- Has a unique string ID and a ``to_version``.
- Records its ID and ``applied_at`` ISO timestamp in ``_migration_log`` the
  first time it runs; on reload, that entry is preserved verbatim (idempotent).
- Only adds structural defaults — it never infers clinical facts or back-fills
  clinical values from context.
- Preserves all unknown (extra) fields (forward-compat).

Usage::

    from agent.migrations import apply_migrations, CURRENT_SCHEMA_VERSION
    data = apply_migrations(data)
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION

Design notes
------------
- ``apply_migrations`` is a pure function (I/O-free); call it outside any lock.
- If ``schema_version`` already equals ``CURRENT_SCHEMA_VERSION`` the function
  returns ``data`` *unchanged* — no mutation, no timestamp touch.
- Timestamps are only written the first time a migration runs.  Subsequent
  ``load_profile`` calls fast-path out and never touch the log.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any

log = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION: int = 5

# Append-only ordered registry of migrations.  Never reorder entries.
_REGISTRY: list[dict[str, Any]] = []


def _migration(migration_id: str, *, to_version: int):
    """Decorator that registers a migration function in ``_REGISTRY``."""

    def decorator(fn):
        _REGISTRY.append({"id": migration_id, "to_version": to_version, "fn": fn})
        return fn

    return decorator


@_migration("0001_add_schema_version", to_version=1)
def _m0001_add_schema_version(data: dict) -> dict:
    """Unversioned → v1: add the top-level ``schema_version`` field.

    Structural defaults (empty collections, empty patient) are deliberately
    omitted here; they are handled by the coercion step in ``load_profile``
    and by Pydantic defaults in ``normalize_profile``.  This migration only
    stamps the version.
    """
    data["schema_version"] = 1
    return data


@_migration("0002_add_document_imports", to_version=2)
def _m0002_add_document_imports(data: dict) -> dict:
    """v1 → v2: add the audit ledger for document reconciliation receipts."""
    if not isinstance(data.get("document_imports"), list):
        data["document_imports"] = []
    data["schema_version"] = 2
    return data


@_migration("0003_add_generated_content_provenance", to_version=3)
def _m0003_add_generated_content_provenance(data: dict) -> dict:
    """v2 → v3: conservatively stale legacy AI questions without generation identity."""
    data.setdefault("questions_generation_id", None)
    for question in data.get("appointment_questions") or []:
        if (
            isinstance(question, dict)
            and question.get("source") == "ai"
            and not question.get("generation_job_id")
        ):
            question["stale"] = True
            question["stale_reason"] = "legacy_missing_generation_provenance"
    data["schema_version"] = 3
    return data


@_migration("0004_add_stable_alert_ids", to_version=4)
def _m0004_add_stable_alert_ids(data: dict) -> dict:
    """v3 → v4: deterministically identify legacy alerts for CAS-safe resolution."""
    for index, alert in enumerate(data.get("alerts") or []):
        if not isinstance(alert, dict) or alert.get("id"):
            continue
        canonical = json.dumps(alert, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(f"{index}:{canonical}".encode()).hexdigest()[:24]
        alert["id"] = f"alert_legacy_{digest}"
    data["schema_version"] = 4
    return data


@_migration("0005_add_dependency_lifecycles", to_version=5)
def _m0005_add_dependency_lifecycles(data: dict) -> dict:
    """v4 → v5: classify alert lifetime and invalidate legacy treatment classification."""
    data.setdefault("treatments_classification_revision", None)
    data.setdefault("treatments_classification_job_id", None)
    for alert in data.get("alerts") or []:
        if not isinstance(alert, dict) or alert.get("dependency_kind"):
            continue
        if alert.get("source") in {"intake_extraction_failure", "trial_status_poll"}:
            alert["dependency_kind"] = "durable"
        elif alert.get("source_document_id"):
            alert["dependency_kind"] = "source"
        elif alert.get("generation_profile_revision") is not None:
            alert["dependency_kind"] = "profile_snapshot"
        else:
            alert["dependency_kind"] = "durable"
        for receipt in data.get("document_imports") or []:
            if not isinstance(receipt, dict):
                continue
            for change in receipt.get("changes") or []:
                if (
                    isinstance(change, dict)
                    and change.get("target", {}).get("collection") == "alerts"
                    and change.get("target", {}).get("record_id") == alert.get("id")
                    and isinstance(change.get("effective_value"), dict)
                ):
                    change["effective_value"]["dependency_kind"] = alert["dependency_kind"]
    data["schema_version"] = 5
    return data


def apply_migrations(data: dict) -> dict:
    """Apply all pending migrations to ``data`` and return it.

    Guarantees
    ----------
    - **Idempotent**: already-applied migrations are skipped; their
      ``_migration_log`` entries (including timestamps) are never overwritten.
    - **Deterministic**: migration order is fixed; no non-deterministic
      behaviour during normal operation.
    - **Fast-path**: if ``data["schema_version"] == CURRENT_SCHEMA_VERSION``
      the function returns ``data`` immediately without any mutation.
    - **Forward-compat**: unknown extra keys are untouched.

    Raises ``TypeError`` if ``data`` is not a dict.
    """
    if not isinstance(data, dict):
        raise TypeError(f"apply_migrations: expected dict, got {type(data).__name__}")

    current_version = data.get("schema_version")
    if current_version is None:
        current_version = 0  # treat missing schema_version as unversioned (v0)

    if current_version == CURRENT_SCHEMA_VERSION:
        # Fast-path: nothing to do, do NOT mutate or touch the log.
        return data

    if isinstance(current_version, int) and current_version > CURRENT_SCHEMA_VERSION:
        # Forward-compat: profile was written by a newer version of this code.
        # Pass through completely unchanged — do NOT backfill, mutate, or touch
        # the migration log.
        return data

    # Ensure _migration_log is present; index applied IDs for O(1) lookup.
    if "_migration_log" not in data or not isinstance(data["_migration_log"], list):
        data["_migration_log"] = []

    applied_ids: set[str] = {
        entry["id"] for entry in data["_migration_log"] if isinstance(entry, dict) and "id" in entry
    }

    for migration in _REGISTRY:
        mid = migration["id"]
        target_version = migration["to_version"]

        if mid in applied_ids:
            # Already applied — preserve original timestamp, skip.
            continue

        if isinstance(current_version, int) and target_version <= current_version:
            # Data was produced by code that already included this migration's
            # changes but predates our migration system.  Record it as backfilled
            # so the log is complete without re-running the function.
            data["_migration_log"].append(
                {
                    "id": mid,
                    "applied_at": "backfilled",
                    "note": "schema_version already at target on first log construction",
                }
            )
            applied_ids.add(mid)
            continue

        log.info("profile_migration apply id=%s to_version=%s", mid, target_version)
        data = migration["fn"](data)

        now = datetime.datetime.now().isoformat(timespec="seconds")
        data["_migration_log"].append({"id": mid, "applied_at": now})
        applied_ids.add(mid)
        current_version = target_version

    return data
