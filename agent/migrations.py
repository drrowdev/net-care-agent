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
import logging
from typing import Any

log = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION: int = 1

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
