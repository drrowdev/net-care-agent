"""Safe profile recovery helpers.

Use these functions — not raw ``shutil.copy`` or ``Path.rename`` — whenever
recovering a corrupt profile.  All restoration operations use the same
cross-process lock and atomic-sibling-replace semantics as ``save_profile``.

Runbook (automated recovery)
-----------------------------
The normal flow is fully automatic and triggered by ``load_profile`` when it
detects corruption:

1. ``load_profile`` reads the profile and detects JSON corruption or a
   structural invalidity.
2. It acquires ``serialized_mutation`` (cross-process lock) and calls
   ``quarantine_profile`` — which writes a forensic copy to
   ``{DATA_DIR}/quarantine/`` and returns without removing the original.
3. ``recover_profile()`` iterates recovery candidates newest-first
   (pre-save snapshots before daily backups) and calls
   ``restore_from_candidate`` on the first one that passes
   ``_validate_candidate``.
4. ``restore_from_candidate`` atomically replaces the main profile file with
   the valid snapshot content and returns the validated data dict.
5. ``load_profile`` applies pending migrations and returns the recovered data.
6. The next ``save_profile`` call will persist the fully-normalized,
   migration-stamped state.

If no valid candidate is found, ``NoRecoveryCandidateError`` is raised.
The operator must then restore from an external backup — see
``docs/operating_manual.md`` §Recovery.

Operator manual recovery (if automated recovery fails)
-------------------------------------------------------
1. Locate latest backup outside the quarantine dir:
   ``ls -lt {DATA_DIR}/backups/`` — pick the most recent ``profile_YYYYMMDD.json``.
2. Call ``restore_from_candidate(RecoveryCandidate(path, "manual"))``.
3. Restart the web app.  ``load_profile`` will run migrations and normalize.

PHI policy
----------
All log messages from this module use only filenames (never full paths),
hash prefixes (first 8 hex chars), and error codes.  No patient data is
logged, emitted to health responses, or written to quarantine metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import NamedTuple

from . import config
from .io import atomic_write_bytes, atomic_write_text

log = logging.getLogger(__name__)

__all__ = [
    "NoRecoveryCandidateError",
    "RecoveryCandidate",
    "quarantine_profile",
    "find_recovery_candidates",
    "restore_from_candidate",
    "recover_profile",
    "get_recovery_state",
]

_RECOVERY_SIDECAR_NAME = "recovery_state.json"


class NoRecoveryCandidateError(Exception):
    """No valid pre-save snapshot or daily backup is available for recovery.

    Raised by ``recover_profile()`` when every candidate fails validation.
    The operator must restore from an external backup.
    """


class RecoveryCandidate(NamedTuple):
    path: Path
    source: str  # "snapshot" | "daily_backup" | "manual"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def quarantine_profile(path: Path, *, reason: str, raw_bytes: bytes) -> Path:
    """Write a forensic copy of corrupt profile bytes to the quarantine directory.

    This is a *copy* operation — the original file at ``path`` is not removed
    so that ``restore_from_candidate`` can atomically overwrite it.

    Returns the quarantine path.  Never raises — quarantine must not block the
    recovery flow; logs errors and returns a fallback path on I/O failure.

    Must be called while holding ``serialized_mutation``.
    """
    ts = _ts_now()
    h = _sha256_hex(raw_bytes)[:8] if raw_bytes else "empty"

    qdir = path.parent / "quarantine"
    try:
        qdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("quarantine_mkdir_failed reason=%s error=%s", reason, exc)
        return path.parent / f".quarantine_fallback_{ts}"

    existing = next(qdir.glob(f"{path.stem}_*_{h}{path.suffix}"), None)
    if existing is not None:
        log.warning(
            "profile_quarantine_deduplicated reason=%s file=%s hash_prefix=%s",
            reason,
            existing.name,
            h,
        )
        return existing

    qpath = qdir / f"{path.stem}_{ts}_{h}{path.suffix}"
    try:
        atomic_write_bytes(qpath, raw_bytes if raw_bytes else b"")
    except OSError as exc:
        log.error("quarantine_write_failed reason=%s error=%s", reason, exc)
        return qpath

    # Log only filename (no full path), hash prefix, reason — no PHI.
    log.warning(
        "profile_quarantined reason=%s file=%s hash_prefix=%s",
        reason,
        qpath.name,
        h,
    )
    return qpath


def _validate_candidate(path: Path) -> dict | None:
    """Load and structurally validate a snapshot or backup.

    Returns the parsed dict if valid, ``None`` otherwise.  Checks an optional
    ``.sha256`` sidecar file when present.
    """
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("candidate_io_error file=%s error=%s", path.name, exc)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("candidate_json_invalid file=%s error=%s", path.name, exc)
        return None

    # Optional sidecar integrity check.
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists():
        try:
            expected = sidecar.read_text(encoding="ascii").strip()
            actual = _sha256_hex(raw)
            if expected != actual:
                log.warning("candidate_hash_mismatch file=%s", path.name)
                return None
        except OSError:
            pass  # Missing or unreadable sidecar — skip check, not an error.

    # Defer the import to avoid a circular import (schema → ← recovery → profile).
    from .schema import clinically_empty_profile, structural_check

    if not structural_check(data) or clinically_empty_profile(data):
        log.warning("candidate_structural_invalid file=%s", path.name)
        return None

    return data


def find_recovery_candidates() -> list[RecoveryCandidate]:
    """Return all candidate files ordered for recovery preference.

    Candidates are ordered globally by file modification time (newest first).
    Source type is only a stable tie-breaker, so an older snapshot cannot outrank
    a newer daily backup.
    """
    candidates: list[RecoveryCandidate] = []

    sdir = config.DATA_DIR / "snapshots"
    if sdir.exists():
        for p in sorted(sdir.glob("profile_*.json"), reverse=True):
            candidates.append(RecoveryCandidate(p, "snapshot"))

    bdir = config.DATA_DIR / "backups"
    if bdir.exists():
        for p in sorted(bdir.glob("profile_*.json"), reverse=True):
            candidates.append(RecoveryCandidate(p, "daily_backup"))

    def candidate_key(candidate: RecoveryCandidate) -> tuple[float, int, str]:
        try:
            modified = candidate.path.stat().st_mtime
        except OSError:
            modified = 0.0
        source_rank = 1 if candidate.source == "snapshot" else 0
        return (modified, source_rank, candidate.path.name)

    return sorted(candidates, key=candidate_key, reverse=True)


def restore_from_candidate(candidate: RecoveryCandidate) -> dict:
    """Validate and atomically restore ``candidate`` to ``config.PROFILE_PATH``.

    Returns the validated data dict on success.
    Raises ``ValueError`` if the candidate fails validation.

    Acquires ``serialized_mutation`` internally — safe to call directly or from
    within an existing ``serialized_mutation`` block (re-entrant lock).

    On success, writes a best-effort metadata-only recovery state sidecar so
    ``get_recovery_state`` and ``/api/health`` can surface the event without PHI.
    """
    from .serialize import serialized_mutation

    with serialized_mutation():
        data = _validate_candidate(candidate.path)
        if data is None:
            raise ValueError(f"Candidate {candidate.path.name!r} failed validation")

        content = json.dumps(data, indent=2, default=str)
        atomic_write_text(config.PROFILE_PATH, content)

    log.warning(
        "profile_restored source=%s candidate=%s",
        candidate.source,
        candidate.path.name,
    )
    # Record successful recovery — best-effort, no PHI, no paths.
    try:
        _write_recovery_sidecar(
            state="recovered",
            source=candidate.source,
            candidate_hash=_sha256_hex(content.encode())[:8],
        )
    except Exception as exc:
        log.warning("recovery_sidecar_call_failed: %s", exc)
    return data


def recover_profile() -> dict:
    """Find the best valid recovery candidate and restore it.

    Raises ``NoRecoveryCandidateError`` if no valid snapshot or backup is found.
    On exhaustion, writes a ``"failed"`` recovery state sidecar (best-effort).

    Acquires ``serialized_mutation`` internally — safe to call directly or from
    within an existing ``serialized_mutation`` block (re-entrant lock).
    """
    from .serialize import serialized_mutation

    with serialized_mutation():
        candidates = find_recovery_candidates()
        for candidate in candidates:
            try:
                data = restore_from_candidate(candidate)
                return data
            except (ValueError, OSError) as exc:
                log.warning(
                    "candidate_restore_failed candidate=%s error=%s",
                    candidate.path.name,
                    exc,
                )
                continue

        _write_recovery_sidecar(state="failed")
        raise NoRecoveryCandidateError(
            "No valid recovery candidate found in pre-save snapshots or daily backups. "
            "Operator intervention required — see docs/operating_manual.md §Recovery."
        )


# ── recovery state sidecar ─────────────────────────────────────────────────────


def _write_recovery_sidecar(
    *,
    state: str,
    source: str | None = None,
    candidate_hash: str | None = None,
) -> None:
    """Write a metadata-only recovery state sidecar (best-effort, never raises).

    Contains **no PHI, no filesystem paths, no secrets**.  Stored at
    ``{DATA_DIR}/recovery_state.json``.  Fields:

    - ``state``: ``"recovered"`` | ``"failed"``
    - ``source``: candidate category (``"snapshot"`` | ``"daily_backup"`` | ``"manual"``),
      when known
    - ``timestamp``: ISO-8601 wall-clock timestamp of the event
    - ``candidate_hash``: first 8 hex chars of the restored content SHA-256, when known

    Failure to write is logged as a warning and never propagates.
    """
    import datetime

    try:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        payload: dict = {"state": state, "timestamp": ts}
        if source is not None:
            payload["source"] = source
        if candidate_hash is not None:
            payload["candidate_hash"] = candidate_hash
        sidecar = config.DATA_DIR / _RECOVERY_SIDECAR_NAME
        atomic_write_text(sidecar, json.dumps(payload, indent=2))
    except Exception as exc:
        log.warning("recovery_sidecar_write_failed: %s", exc)


def get_recovery_state() -> dict:
    """Return safe recovery metadata from the sidecar.  Never raises.

    Returns a dict with a ``state`` key:

    - ``"recovered"``: a profile was successfully recovered from a snapshot/backup
    - ``"failed"``: recovery was attempted but all candidates were exhausted
    - ``"none"``: no recovery has been attempted (sidecar absent/unreadable)
    - ``"unknown"``: sidecar present but ``state`` field is missing

    The returned dict never contains PHI, filesystem paths, or secrets.
    Optionally includes ``source`` (candidate category) and ``timestamp``.
    """
    try:
        raw = (config.DATA_DIR / _RECOVERY_SIDECAR_NAME).read_bytes()
        data = json.loads(raw)
        if isinstance(data, dict):
            return {
                "state": data.get("state") or "unknown",
                "source": data.get("source"),
                "timestamp": data.get("timestamp"),
            }
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.debug("recovery_sidecar_read_failed: %s", exc)
    return {"state": "none"}


# ── helpers ───────────────────────────────────────────────────────────────────


def _ts_now() -> str:
    """Timestamp string safe for use in filenames."""
    import datetime

    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
