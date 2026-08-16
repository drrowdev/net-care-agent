"""Daily snapshot backups of the patient profile.

Runs piggy-backed on save_profile. Cheap: only copies once per day, then
prunes anything older than BACKUP_RETENTION_DAYS (default 30).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from . import config
from .io import atomic_write_text, replace_with_retry

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

# ── validated copies ──────────────────────────────────────────────────────────
# Both artefact writers used to be a bare ``shutil.copy2`` straight onto their
# final filename. A copy interrupted part-way — container recycle, restart, disk
# pressure — therefore left a TRUNCATED file at the real path, and because
# ``copy2`` had already been through the data, that file carried a perfectly
# ordinary mtime. Nothing downstream could tell it apart from a good artefact:
# ``/api/health`` judges the daily backup by mtime and calendar day so
# ``backup_out_of_date`` stayed false, and ``daily_backup``'s once-per-day
# existence gate treated the day as done, so the corrupt file was never retried.
# Worst of all it stayed a recovery candidate.
#
# Every copy now lands on a sibling temporary, is validated there, and only then
# replaces the real target with ``os.replace``. The target therefore only ever
# transitions from absent, or from one complete artefact, to another complete
# artefact — a reader can never observe a partial one.

# Copy temporaries are named like ``.profile_20260101.json.1755370000.ab3d9f.tmp``:
# the leading dot and the ``.tmp`` suffix keep them out of every ``profile_*.json``
# glob in the codebase — ``_prune_old``, the snapshot prune, ``newest_file_mtime``
# behind /api/health, and ``recovery.find_recovery_candidates``. A temporary can
# therefore never be pruned as an artefact, aged as one, or restored as one.
#
# The embedded creation time is what ``_purge_stale_temps`` ages them by. Their
# MTIME cannot be used: ``_copy_validated`` stamps the source profile's mtime on
# just before the replace, so a live temporary would briefly look days old and a
# concurrent purge could delete it out from under the copy. The name is fixed at
# creation and nothing rewrites it.
_TEMP_SUFFIX = ".tmp"

# A crash between creating a temporary and replacing the target leaves the
# temporary behind. They are swept on a later run rather than immediately,
# because a temporary that another writer is still filling must not be pulled
# out from under it. An hour is far longer than any copy of a single profile.
TEMP_STALE_SECONDS = 3600


COPY_VALID = "valid"
COPY_INVALID = "invalid"
COPY_UNREADABLE = "unreadable"


def _classify_copy(path: Path) -> str:
    """Say whether *path* is a usable profile artefact, corrupt, or unreadable.

    The third answer is load-bearing rather than pedantry. "Cannot read it" is
    not evidence of corruption, and conflating the two would let a single
    transient Azure Files read error against a perfectly good same-day backup
    convince ``daily_backup`` to overwrite it with a later revision of the
    profile — destroying the earlier state that backup exists to preserve. Only
    proven corruption earns a rewrite; an unreadable file is left alone and
    re-examined on the next save.

    The usable bar is the one ``recovery._validate_candidate`` applies, minus the
    clinical-emptiness test: an empty profile on a fresh install is a legitimate
    thing to back up, and rejecting it here would make the once-per-day gate
    rewrite that day's backup on every single save forever.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("profile_copy_unreadable file=%s error=%s", path.name, exc)
        return COPY_UNREADABLE
    try:
        # Undecodable bytes raise UnicodeDecodeError, itself a ValueError.
        data = json.loads(raw)
    except ValueError:
        return COPY_INVALID
    # Deferred like recovery.py's, to keep this module free of schema imports.
    from .schema import structural_check

    return COPY_VALID if structural_check(data) else COPY_INVALID


def _temp_created_at(tmp: Path) -> float | None:
    """Recover the creation time embedded in a copy temporary's name.

    Returns None for a temporary this module did not name — notably the ones
    ``atomic_write_text`` leaves when writing a ``.sha256`` sidecar, which carry
    no timestamp segment but whose mtime is trustworthy because nothing ever
    back-dates them.
    """
    parts = tmp.name.split(".")
    if len(parts) < 3:
        return None
    try:
        return float(parts[-3])
    except ValueError:
        return None


def _purge_stale_temps(directory: Path) -> None:
    """Delete abandoned copy temporaries in *directory*. Never raises.

    Only temporaries older than ``TEMP_STALE_SECONDS`` are removed, so a copy
    still in flight is never destroyed. Age comes from the timestamp in the name
    rather than the mtime, because ``_copy_validated`` back-dates a temporary to
    the source profile's mtime just before replacing the target and a live
    temporary must not become eligible for deletion in that window.
    """
    try:
        leftovers = list(directory.glob(f".profile_*{_TEMP_SUFFIX}"))
    except OSError:
        return
    cutoff = time.time() - TEMP_STALE_SECONDS
    for tmp in leftovers:
        try:
            created = _temp_created_at(tmp)
            if created is None:
                created = tmp.stat().st_mtime
            if created < cutoff:
                tmp.unlink()
                log.info("stale_copy_temp_removed file=%s", tmp.name)
        except OSError:
            pass


def _fsync_path(path: Path) -> None:
    """Flush a file's own metadata to disk. Best-effort."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _fsync_dir(directory: Path) -> None:
    """Flush a directory entry so a rename survives a crash. Best-effort."""
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Directory fsync is not supported on every platform/filesystem.
        pass


def _copy_validated(src: Path, target: Path) -> None:
    """Copy *src* onto *target* so a partial copy can never land at *target*.

    Streams the bytes to a sibling temporary, flushes them to disk, checks that
    what arrived is parseable and structurally usable, copies the source's
    metadata across, and only then atomically replaces *target*.

    This is ``shutil.copy2`` taken apart on purpose. Validation has to happen
    between the data copy and the metadata copy, the bytes are fsynced so the
    atomic rename commits durable content rather than just a durable name, and
    the copied mtime is fsynced too so content and timestamp survive a crash
    together. The final artefact carries the source profile's mtime, because
    ``copystat`` runs before the replace and ``os.replace`` is a rename that
    carries the inode's metadata with it — ``/api/health`` depends on that
    filename-to-mtime agreement.

    Raises on any failure, having removed the temporary. Callers treat that as a
    failed copy; no caller is allowed to let it reach a save. Interpreter-level
    interrupts (``KeyboardInterrupt``, ``SystemExit``) still propagate past the
    callers' ``except Exception`` guards, exactly as they always have — the
    never-block-a-save contract has always been about operational failures.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.{int(time.time())}.",
        suffix=_TEMP_SUFFIX,
    )
    tmp = Path(tmp_name)
    try:
        # fdopen first so the descriptor is always adopted and closed.
        with os.fdopen(fd, "wb") as dest, open(src, "rb") as source:
            shutil.copyfileobj(source, dest)
            dest.flush()
            os.fsync(dest.fileno())
        if _classify_copy(tmp) != COPY_VALID:
            raise ValueError(f"copy of {src.name} did not validate")
        shutil.copystat(src, tmp)
        _fsync_path(tmp)
        replace_with_retry(tmp, target)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    _fsync_dir(target.parent)


def _snapshot_dir() -> Path:
    return config.DATA_DIR / "snapshots"


def _write_sidecar_hash(path: Path, content_bytes: bytes) -> None:
    """Write a ``.sha256`` sidecar alongside *path* (best-effort).

    Written atomically. A sidecar write interrupted part-way leaves a truncated
    digest, and ``recovery._validate_candidate`` reads a readable-but-mismatched
    sidecar as proof the snapshot itself is corrupt — permanently rejecting a
    perfectly good recovery candidate over damage to its own checksum.
    """
    sidecar = path.with_suffix(path.suffix + ".sha256")
    try:
        digest = hashlib.sha256(content_bytes).hexdigest()
        atomic_write_text(sidecar, digest + "\n", encoding="ascii")
    except OSError as exc:
        log.warning("sidecar_hash_write_failed path=%s error=%s", path.name, exc)


def rotating_snapshot(profile_path: Path | None = None) -> Path | None:
    """Copy the CURRENT profile file to a rotating snapshot, keeping the last N.

    Call this BEFORE overwriting the profile so the snapshot captures the
    pre-write state. Also writes an optional ``.sha256`` sidecar for integrity
    validation during recovery. Returns the snapshot path, or None if there is
    nothing to snapshot yet. Never raises — snapshotting must not block a save.

    The copy is validated before it lands (see ``_copy_validated``). A snapshot
    cannot be silently skipped the way a daily backup could — every save writes a
    fresh timestamped one — but a truncated snapshot still occupies one of the
    ``PRESAVE_SNAPSHOT_COUNT`` rotating slots and pushes a genuinely recoverable
    revision out of the window. The ``.sha256`` sidecar cannot catch that: it is
    computed FROM the copy, so a truncated copy gets a matching hash of its own
    truncated bytes.
    """
    src = Path(profile_path) if profile_path else config.PROFILE_PATH
    if not src.exists():
        return None
    sdir = _snapshot_dir()
    try:
        sdir.mkdir(parents=True, exist_ok=True)
        _purge_stale_temps(sdir)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = sdir / f"profile_{ts}.json"
        _copy_validated(src, target)
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

    The once-per-day gate additionally re-checks the existing file. It used to be
    a bare ``if not target.exists()``, which meant a truncated backup — the exact
    thing an interrupted copy left behind — permanently satisfied the gate for
    that day and was never retried. Existence is not the question; a usable
    artefact for the day is. Only a backup *proven* corrupt is replaced: a
    backup that merely could not be read is left alone, since overwriting it
    with a later revision on a transient read error would destroy the earlier
    state it exists to preserve.
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
    _purge_stale_temps(bdir)
    target = bdir / f"profile_{today}.json"

    written: Path | None = None
    existing = target.exists()
    corrupt = existing and _classify_copy(target) == COPY_INVALID
    if corrupt:
        log.warning("daily_backup_corrupt_replacing file=%s", target.name)
    if corrupt or not existing:
        try:
            _copy_validated(src, target)
            written = target
            log.info("daily_backup_written", extra={"path": str(target)})
        except Exception as e:
            log.warning("daily_backup_failed: %s", e)
            return None

    _prune_old(bdir, BACKUP_RETENTION_DAYS, keep=target)
    return written


def protected_profile_write(path: Path, content: str, *, snapshot: bool = True) -> None:
    """Commit new profile bytes with the protection an ordinary save receives.

    This is the single choke point for every durable change to the stored
    profile — a caregiver save, a migration write-back on load, the normalised
    write that follows an automated recovery, and an operator restore. Each of
    those replaces the caregiver's live clinical record, so each must leave the
    same two artefacts behind:

    - a **pre-write rotating snapshot**, so the revision being replaced stays
      recoverable, and
    - a **daily backup** for the calendar day the profile now belongs to.

    Wiring these into ``save_profile`` alone was not enough. Migration-on-load
    fires on the first request after any ``CURRENT_SCHEMA_VERSION`` bump and
    rewrites the profile without going through ``save_profile``, which advanced
    the profile's mtime into a new day while that day's ``daily_backup`` never
    ran. The newest backup then trailed the live profile indefinitely — the
    caregiver's current state was genuinely unprotected — until the next
    ordinary save happened to catch up.

    Pass ``snapshot=False`` only when the bytes being replaced are already known
    to be unusable, as in automated recovery from a corrupt profile: they can
    never serve as a recovery candidate, ``quarantine_profile`` has already kept
    them for forensics, and snapshotting them would spend one of the limited
    rotating slots that the next incident depends on.

    The atomic replace is the commit point and is the only step allowed to
    raise. Snapshot and backup failures are logged and swallowed, preserving the
    existing contract exactly: protection is best-effort and must never block or
    fail a write that has to land.
    """
    target = Path(path)
    if snapshot:
        try:
            rotating_snapshot(target)
        except Exception as exc:
            log.warning("rotating_snapshot raised: %s", exc)

    atomic_write_text(target, content)

    try:
        daily_backup(target)
    except Exception as exc:  # never let backup failure fail a committed write
        log.warning("daily_backup raised: %s", exc)


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
