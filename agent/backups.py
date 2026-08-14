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

# ── /api/health freshness policy ──────────────────────────────────────────────
# This lives next to the code that decides when artifacts get written, so the
# health check judges the daily backup against its real cadence.
#
# ``daily_backup`` runs after EVERY save but writes at most one file per LOCAL
# CALENDAR DAY. So the meaningful question is not "how old is the backup?" but
# "did the day on which the profile was last saved actually produce a backup?".
# Age alone cannot answer that: a profile saved during a busy day and then left
# untouched keeps a backup that grows arbitrarily old with nothing wrong, while
# a backup writer that has been broken since this morning still looks recent.
#
# ``shutil.copy2`` preserves the source mtime, so a backup's mtime is the mtime
# of the exact profile revision it captured, and ``daily_backup`` names the file
# after that same mtime. Comparing the calendar day of the two mtimes therefore
# compares like with like, and the healthy steady state is an exact invariant:
# the newest backup's day always equals the day of the profile's last save, no
# matter how many times the profile was saved that day or how long ago the day
# was. Any positive lag means a save happened on a day whose ``daily_backup``
# produced nothing, which only happens when the writer is broken.
#
# The tolerance is therefore 0: one full day of slack would let a writer that
# failed yesterday and then saw no further saves stay hidden forever, because
# the lag would sit at exactly 1 in perpetuity. It stays env-overridable so an
# operator can buy quiet without a deploy if some unforeseen environment (a host
# timezone change, say) shifts a day boundary under an idle profile.
BACKUP_MAX_LAG_DAYS = int(os.environ.get("BACKUP_MAX_LAG_DAYS", "0"))


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

    The date in the filename comes from the profile's own mtime rather than the
    wall clock, so it always agrees with the mtime ``copy2`` preserves on the
    copy. That closes a midnight race: a save landing at 23:59:59.9 whose
    ``daily_backup`` call ran a tick past midnight used to claim tomorrow's
    filename while carrying yesterday's mtime, which then suppressed the real
    backup for the whole of the following day. ``/api/health`` relies on that
    filename-to-mtime agreement to judge freshness by calendar day.
    """
    src = Path(profile_path) if profile_path else config.PROFILE_PATH
    if not src.exists():
        return None

    try:
        day = datetime.date.fromtimestamp(src.stat().st_mtime)
    except (OSError, OverflowError, ValueError):
        day = datetime.date.today()
    today = day.isoformat().replace("-", "")
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

    _prune_old(bdir, BACKUP_RETENTION_DAYS, keep=target)
    return written


def _prune_old(bdir: Path, retention_days: int, keep: Path | None = None) -> None:
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)
    for f in bdir.glob("profile_*.json"):
        if keep is not None and f == keep:
            # Never delete the backup this call just took: a profile carrying an
            # mtime older than the retention window would otherwise write and
            # immediately delete its own backup on every save.
            continue
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


def newest_file_mtime(directory: Path, pattern: str) -> float | None:
    """Return the mtime of the newest file matching ``pattern``.

    Returns ``None`` when the directory does not exist or no matching files are
    found.  Used by ``/api/health`` to reason about backup freshness without
    exposing filesystem paths.
    """
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    if not files:
        return None
    try:
        return files[0].stat().st_mtime
    except OSError:
        return None


def newest_file_age_seconds(directory: Path, pattern: str) -> float | None:
    """Return seconds since the newest file matching ``pattern`` was modified.

    Returns ``None`` when the directory does not exist or no matching files are
    found.  Used by ``/api/health`` to report backup freshness without exposing
    filesystem paths.
    """
    mtime = newest_file_mtime(directory, pattern)
    if mtime is None:
        return None
    return time.time() - mtime


def backup_lag_days(profile_mtime: float, backup_mtime: float) -> int | None:
    """Whole local calendar days between the backup's day and the profile's day.

    ``0`` means the profile's most recent save happened on the same day the
    newest backup was taken, which is the healthy steady state no matter how
    many times the profile was saved that day or how long ago that day was. A
    negative value means the backup is newer than the profile, which happens
    after a restore and is likewise not a fault.

    Returns ``None`` when either timestamp is not a representable date, so a
    corrupt mtime surfaces as an unknown lag instead of raising inside
    ``/api/health``.
    """
    try:
        profile_day = datetime.date.fromtimestamp(profile_mtime)
        backup_day = datetime.date.fromtimestamp(backup_mtime)
    except (OSError, OverflowError, ValueError):
        return None
    return (profile_day - backup_day).days
