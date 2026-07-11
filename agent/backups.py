"""Daily snapshot backups of the patient profile.

Runs piggy-backed on save_profile. Cheap: only copies once per day, then
prunes anything older than BACKUP_RETENTION_DAYS (default 30).
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import shutil
import time
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

BACKUP_RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
BACKUPS_DIR = config.DATA_DIR / "backups"

# Pre-save rotating snapshots (architecture-review P12): daily backups leave up
# to a 24h data-loss window. A cheap pre-write snapshot on every save keeps the
# last N states so any single bad write/merge is recoverable to the immediately
# prior state, not yesterday's.
PRESAVE_SNAPSHOT_COUNT = int(os.environ.get("PRESAVE_SNAPSHOT_COUNT", "20"))


def _snapshot_dir() -> Path:
    return config.DATA_DIR / "snapshots"


def _write_sidecar_hash(path: Path, content_bytes: bytes) -> None:
    """Write a ``.sha256`` sidecar alongside *path* (best-effort)."""
    sidecar = path.with_suffix(path.suffix + ".sha256")
    try:
        digest = hashlib.sha256(content_bytes).hexdigest()
        sidecar.write_text(digest + "\n", encoding="ascii")
    except OSError as exc:
        log.warning("sidecar_hash_write_failed path=%s error=%s", path.name, exc)


def rotating_snapshot(profile_path: Path | None = None) -> Path | None:
    """Copy the CURRENT profile file to a rotating snapshot, keeping the last N.

    Call this BEFORE overwriting the profile so the snapshot captures the
    pre-write state. Also writes an optional ``.sha256`` sidecar for integrity
    validation during recovery. Returns the snapshot path, or None if there is
    nothing to snapshot yet. Never raises — snapshotting must not block a save.
    """
    src = Path(profile_path) if profile_path else config.PROFILE_PATH
    if not src.exists():
        return None
    sdir = _snapshot_dir()
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = sdir / f"profile_{ts}.json"
        shutil.copy2(src, target)
        # Best-effort sidecar hash for recovery validation.
        try:
            _write_sidecar_hash(target, target.read_bytes())
        except OSError:
            pass
    except Exception as e:
        log.warning("rotating_snapshot_failed: %s", e)
        return None

    # Prune to the most recent N (timestamped names sort chronologically).
    snaps = sorted(sdir.glob("profile_*.json"))
    for old in snaps[:-PRESAVE_SNAPSHOT_COUNT] if len(snaps) > PRESAVE_SNAPSHOT_COUNT else []:
        try:
            old.unlink()
        except OSError:
            pass
        # Also prune the sidecar if it exists.
        sidecar = old.with_suffix(old.suffix + ".sha256")
        try:
            sidecar.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def _backup_dir() -> Path:
    # Re-resolve at call time so test fixtures that rebind DATA_DIR work.
    return config.DATA_DIR / "backups"


def daily_backup(profile_path: Path | None = None) -> Path | None:
    """Snapshot the profile to backups/profile_YYYYMMDD.json once per day.

    Returns the backup path if one was written this call, else None.
    Silently skips if the source profile doesn't exist yet.
    """
    src = Path(profile_path) if profile_path else config.PROFILE_PATH
    if not src.exists():
        return None

    today = datetime.date.today().isoformat().replace("-", "")
    bdir = _backup_dir()
    bdir.mkdir(parents=True, exist_ok=True)
    target = bdir / f"profile_{today}.json"

    written: Path | None = None
    if not target.exists():
        try:
            shutil.copy2(src, target)
            written = target
            log.info("daily_backup_written", extra={"path": str(target)})
        except Exception as e:
            log.warning("daily_backup_failed: %s", e)
            return None

    _prune_old(bdir, BACKUP_RETENTION_DAYS)
    return written


def _prune_old(bdir: Path, retention_days: int) -> None:
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)
    for f in bdir.glob("profile_*.json"):
        stem = f.stem.replace("profile_", "")
        try:
            d = datetime.date(int(stem[0:4]), int(stem[4:6]), int(stem[6:8]))
        except (ValueError, IndexError):
            continue
        if d < cutoff:
            try:
                f.unlink()
                log.info("daily_backup_pruned", extra={"path": str(f)})
            except OSError:
                pass


def newest_file_age_seconds(directory: Path, pattern: str) -> float | None:
    """Return seconds since the newest file matching ``pattern`` was modified.

    Returns ``None`` when the directory does not exist or no matching files are
    found.  Used by ``/api/health`` to report backup freshness without exposing
    filesystem paths.
    """
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    if not files:
        return None
    try:
        mtime = files[0].stat().st_mtime
        return time.time() - mtime
    except OSError:
        return None
