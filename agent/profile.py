"""Patient profile load/save and human-readable summary."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from . import backups, config
from .io import atomic_write_text
from .migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from .schema import (
    _COLLECTION_KEYS,
    clinically_empty_profile,
    normalize_profile,
    structural_check,
    validate_profile,
)
from .serialize import serialized_mutation

log = logging.getLogger(__name__)


# ── exceptions ────────────────────────────────────────────────────────────────


class ProfileLoadError(Exception):
    """Base: profile file existed but could not be loaded or recovered."""


class IOProfileError(ProfileLoadError):
    """Transient I/O error reading the profile file.

    The profile has NOT been quarantined.  Retrying the operation may succeed.
    Do not display to the end user; log and surface as a 503.
    """


class CorruptProfileError(ProfileLoadError):
    """Profile is corrupt (invalid JSON or invalid structural shape) AND no
    valid pre-save snapshot or daily backup was found.

    The caregiver cannot use the app until an operator restores from an
    external backup.  See ``docs/operating_manual.md`` §Recovery.
    """


# ── default profile ───────────────────────────────────────────────────────────

DEFAULT_PROFILE: dict = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "profile_revision": 0,
    "profile_updated_at": None,
    "summary_stale": True,
    "patient": {
        "birth_year": None,
        "age": None,
        "sex": None,
        "diagnosis": "neuroendocrine tumor",
        "ki67_percent": None,
        "sstr_status": None,
        "sstr_score": None,
        "current_treatments": [],
        "allergies": [],
        "comorbidities": [],
        "oncologist": None,
        "treating_center": None,
        "location": None,
        "caregiver_relationship": None,
        "language": None,
        "regions_of_interest": [],
    },
    "biomarkers": [],
    "imaging": [],
    "appointments": [],
    "documents": [],
    "source_documents": [],
    "trials_tracked": [],
    "literature_watched": [],
    "alerts": [],
    "symptoms": [],
    "clinical_judgments": [],
    "appointment_questions": [],
    "feedback": [],
}


def _coerce_none_fields(data: dict) -> dict:
    """Coerce ``None`` patient/collections to their empty-structure defaults.

    This runs after ``apply_migrations`` and before ``normalize_profile`` so
    that Pydantic never sees ``None`` where it expects a sub-model or list.
    No clinical values are inferred — only structural scaffolding is added.
    """
    if data.get("patient") is None:
        data["patient"] = {}
    for key in _COLLECTION_KEYS:
        if data.get(key) is None:
            data[key] = []
    return data


def _persist_migration_metadata(path: Path) -> dict:
    """Acquire the mutation lock, re-read authoritative on-disk bytes, and either
    persist migration metadata or return the authoritative data unchanged.

    Called from ``_load_validated`` when the optimistic read saw a legacy
    ``schema_version``.  Under the lock:

    - Re-reads the authoritative bytes.  Raises ``IOProfileError`` on ``OSError``
      so the caller surfaces a 503 rather than silently serving stale in-memory
      migrated data.
    - If the on-disk ``schema_version`` is current or future (written by another
      process under its own lock), returns normalized authoritative data without
      mutating disk.
    - If on-disk is still legacy, applies migrations to the authoritative dict
      (timestamps generated *here*, inside the lock, for determinism), atomically
      persists the updated dict (schema_version + _migration_log merged into all
      preserved clinical/unknown fields), and returns the normalized result.

    Returns the normalized authoritative dict. If the under-lock bytes became
    corrupt, they enter the normal quarantine/recovery path rather than serving
    stale in-memory data.

    Raises ``IOProfileError`` on re-read ``OSError`` — never silently swallows
    transient I/O failures.
    """
    with serialized_mutation():
        try:
            authoritative_bytes = path.read_bytes()
        except OSError as exc:
            raise IOProfileError(
                f"Transient I/O error on migration lock re-read (not quarantined): {exc}"
            ) from exc

        try:
            authoritative = json.loads(authoritative_bytes)
        except json.JSONDecodeError as exc:
            return _quarantine_and_recover(
                path,
                authoritative_bytes,
                f"json_decode_error_during_migration: {exc}",
            )

        if not structural_check(authoritative):
            return _quarantine_and_recover(
                path,
                authoritative_bytes,
                "structural_invalid_during_migration",
            )

        on_disk_version = authoritative.get("schema_version")
        if isinstance(on_disk_version, int) and on_disk_version >= CURRENT_SCHEMA_VERSION:
            # Another process already migrated the file (or it carries a future schema).
            # Do NOT mutate disk; preserve all fields and return the authoritative result.
            authoritative = _coerce_none_fields(authoritative)
            return normalize_profile(authoritative)

        # Still legacy under lock: apply migrations with timestamps generated here.
        authoritative = apply_migrations(authoritative)
        # All clinical/unknown fields are already present in authoritative;
        # apply_migrations adds only schema_version and _migration_log in-place.
        atomic_write_text(path, json.dumps(authoritative, indent=2, default=str))

        authoritative = _coerce_none_fields(authoritative)
        return normalize_profile(authoritative)


def _load_validated(path: Path) -> dict:
    """Read, validate, migrate and normalise the profile at *path*.

    Distinguishes three failure classes:
    - **I/O error** (``OSError``): transient read failure → raises
      ``IOProfileError``; the file is NOT quarantined.
    - **JSON corruption** or **structural invalidity**: raises
      ``CorruptProfileError`` after quarantining and attempting automated
      recovery (newest valid snapshot or daily backup, atomically restored).
    - **No recovery candidate**: raises ``CorruptProfileError`` with an
      operator-facing message; the app cannot serve requests until restored.
    """
    # ── Step 1: read ──────────────────────────────────────────────────────────
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise IOProfileError(
            f"Transient I/O error reading profile (not quarantined): {exc}"
        ) from exc

    # ── Step 2: parse JSON ────────────────────────────────────────────────────
    parse_error: Exception | None = None
    try:
        data = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        parse_error = exc
        data = None

    if parse_error is not None or not structural_check(data) or clinically_empty_profile(data):
        reason = (
            f"json_decode_error: {parse_error}"
            if parse_error is not None
            else "clinically_empty"
            if clinically_empty_profile(data)
            else "structural_invalid"
        )
        with serialized_mutation():
            return _quarantine_and_recover(path, raw_bytes, reason)

    # ── Step 3: migrate under lock if needed; otherwise fast-path ────────────
    original_version = data.get("schema_version")
    needs_migration = original_version is None or (
        isinstance(original_version, int) and original_version < CURRENT_SCHEMA_VERSION
    )

    if needs_migration:
        # Acquire the lock, re-read the authoritative bytes, and apply migrations
        # (with timestamps) inside the lock.  IOProfileError propagates as-is.
        return _persist_migration_metadata(path)

    # Fast path for already current/future profiles.
    data = apply_migrations(data)
    data = _coerce_none_fields(data)
    return normalize_profile(data)


def _quarantine_and_recover(path: Path, raw_bytes: bytes, reason: str) -> dict:
    """Must be called while holding ``serialized_mutation``.

    Re-reads the file first; if another thread/process already recovered it,
    returns the good data without quarantining.  If the under-lock re-read
    raises ``OSError``, raises ``IOProfileError`` immediately — the current
    file is preserved and no quarantine/recovery occurs based on stale bytes.
    Only when the under-lock bytes themselves fail to parse or structurally
    validate does the function proceed with quarantine and recovery.
    """
    # Re-check: a concurrent process may have already restored the profile.
    try:
        re_raw = path.read_bytes()
    except OSError as exc:
        # Transient I/O on the under-lock re-read: do NOT quarantine or
        # overwrite based on stale bytes.  Preserve the current file.
        raise IOProfileError(
            f"Transient I/O error on under-lock re-read (not quarantined): {exc}"
        ) from exc

    try:
        re_data = json.loads(re_raw)
        if structural_check(re_data) and not clinically_empty_profile(re_data):
            re_data = apply_migrations(re_data)
            re_data = _coerce_none_fields(re_data)
            return normalize_profile(re_data)
    except json.JSONDecodeError:
        pass  # Still corrupt; proceed to quarantine and recovery.

    # Import lazily to avoid circular imports at module level.
    from .recovery import NoRecoveryCandidateError, quarantine_profile, recover_profile

    authoritative_reason = "structural_invalid"
    try:
        json.loads(re_raw)
        if clinically_empty_profile(re_data):
            authoritative_reason = "clinically_empty"
    except json.JSONDecodeError as exc:
        authoritative_reason = f"json_decode_error: {exc}"
    quarantine_profile(path, reason=authoritative_reason, raw_bytes=re_raw)

    try:
        recovered_data = recover_profile()
    except NoRecoveryCandidateError as exc:
        raise CorruptProfileError(
            "Profile is corrupt and no valid snapshot or backup is available for "
            "automated recovery.  Operator intervention required — "
            "see docs/operating_manual.md §Recovery."
        ) from exc

    # Apply migrations to the recovered snapshot (it may be unversioned).
    recovered_data = apply_migrations(recovered_data)
    recovered_data = _coerce_none_fields(recovered_data)
    normalized = normalize_profile(recovered_data)

    # Atomically persist the migrated form so disk and the returned dict agree.
    from .io import atomic_write_text as _atomic_write

    _atomic_write(config.PROFILE_PATH, json.dumps(normalized, indent=2, default=str))

    return normalized


def load_profile() -> dict:
    """Load, validate, migrate and return the patient profile.

    Behaviour by file state
    -----------------------
    - **File missing** (first run): creates a default profile under the
      cross-process lock and returns it.  A first-run default is always safe to
      create; no data is lost.
    - **Valid JSON + structurally sound**: applies pending migrations, coerces
      ``None`` scaffolding, runs lenient Pydantic normalisation, returns.
    - **I/O error** (transient): raises ``IOProfileError``; the file is NOT
      quarantined so a retry may succeed.
    - **Corrupt JSON** or **structurally invalid shape**: atomically quarantines
      a forensic copy, then restores the newest valid pre-save snapshot (or
      daily backup).  Returns the recovered data.  Raises ``CorruptProfileError``
      if no valid candidate exists.

    PHI policy: this function never logs patient data.  Quarantine filenames
    contain only a timestamp and a 8-char hash prefix.
    """
    path = config.PROFILE_PATH

    if path.exists():
        return _load_validated(path)

    # First-run creation — serialize to prevent two simultaneous first requests
    # from both creating (and then one overwriting) a new default profile.
    with serialized_mutation():
        if path.exists():
            # Another process created it between our check and lock acquisition.
            return _load_validated(path)
        from .recovery import NoRecoveryCandidateError, find_recovery_candidates, recover_profile

        if find_recovery_candidates():
            try:
                recovered = recover_profile()
            except NoRecoveryCandidateError as exc:
                raise CorruptProfileError(
                    "Profile is missing and no valid recovery candidate is available."
                ) from exc
            recovered = apply_migrations(recovered)
            recovered = _coerce_none_fields(recovered)
            return normalize_profile(recovered)
        initialized_marker = config.DATA_DIR / ".profile-initialized"
        if initialized_marker.exists():
            raise CorruptProfileError(
                "Profile is missing from an initialized data directory and no recovery "
                "candidate is available. Operator intervention required."
            )
        profile = json.loads(json.dumps(DEFAULT_PROFILE))  # deep copy
        save_profile(profile)
        return profile


def save_profile(profile: dict, *, clinical_change: bool = True) -> None:
    """Persist the profile under the global transaction lock.

    Raises ``ValueError`` if *profile* is structurally invalid (not a dict,
    non-dict ``patient``, non-list collection).  This guard prevents knowingly
    persisting unusable data.  Field-level type issues (e.g. an out-of-range
    ``sstr_score``) are still permitted with a log warning, preserving forward
    compatibility.

    ``clinical_change=False`` is reserved for bookkeeping-only writes such as
    acknowledging the unread counter.  Those writes must not invalidate an
    otherwise current clinical summary.
    """
    if not structural_check(profile):
        raise ValueError(
            "save_profile: refusing to persist structurally invalid profile data. "
            "profile must be a dict with a dict 'patient' and list collections."
        )

    with serialized_mutation():
        config.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now().isoformat(timespec="seconds")
        profile["profile_saved_at"] = now
        if clinical_change:
            revision = int(profile.get("profile_revision") or 0) + 1
            profile["profile_revision"] = revision
            profile["profile_updated_at"] = now
            summary = profile.get("executive_summary")
            if isinstance(summary, dict):
                stale = summary.get("summary_revision") != revision
                summary["stale"] = stale
                profile["summary_stale"] = stale
            else:
                profile["summary_stale"] = True

        # Strict validation pass for the log only — we still write the caller's
        # dict verbatim so ad-hoc / in-flight fields aren't dropped.
        try:
            validate_profile(profile)
        except Exception as e:
            log.warning("save_profile: validation issues type=%s", type(e).__name__)

        # P12: pre-write snapshot so any single bad save is recoverable to the
        # immediately-prior state (never blocks the save on failure).
        try:
            backups.rotating_snapshot(config.PROFILE_PATH)
        except Exception as e:
            log.warning("rotating_snapshot raised: %s", e)

        atomic_write_text(
            config.PROFILE_PATH,
            json.dumps(profile, indent=2, default=str),
        )
        atomic_write_text(config.DATA_DIR / ".profile-initialized", "initialized\n")
        # Cheap: only copies once per day, then prunes.
        try:
            backups.daily_backup(config.PROFILE_PATH)
        except Exception as e:  # never let backup failure block a save
            log.warning("daily_backup raised: %s", e)


def get_patient_summary(profile: dict) -> str:
    """Concise text summary of the patient's current state, used as LLM context."""
    p = profile["patient"]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date", ""), reverse=True)[:6]
    docs = sorted(profile.get("documents", []), key=lambda x: x.get("date", ""), reverse=True)[:3]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date", ""), reverse=True)[:2]
    active_alerts = [a for a in profile.get("alerts", []) if not a.get("resolved")]

    lines = [
        "═══ PATIENT PROFILE ═══",
        f"Diagnosis : {p.get('diagnosis') or 'unknown'}",
        f"Age / Sex : {p.get('age') or 'unknown'} / {p.get('sex') or 'unknown'}",
        f"Ki-67     : {p.get('ki67_percent', 'unknown')}%",
        f"SSTR      : {p.get('sstr_status', 'unknown')} (score: {p.get('sstr_score', 'unknown')})",
        f"Treatments: {', '.join(p.get('current_treatments', [])) or 'none documented'}",
        f"Center    : {p.get('treating_center', 'not specified')}",
        "",
        "─── Recent biomarkers ───",
    ]
    if bms:
        for b in bms:
            flag = (
                f" [{b.get('flag', '').upper()}]" if b.get("flag") and b["flag"] != "normal" else ""
            )
            lines.append(
                f"  {b.get('date', '')}  {b.get('marker', '?')} = {b.get('value', '?')} "
                f"{b.get('unit', '')} (ref: {b.get('reference_range', '?')}){flag}"
            )
    else:
        lines.append("  None recorded")

    lines += ["", "─── Recent imaging ───"]
    if imgs:
        for i in imgs:
            lines.append(
                f"  {i.get('date', '')}  {i.get('modality', '?')}: {i.get('impression', '')[:120]}"
            )
    else:
        lines.append("  None recorded")

    lines += ["", "─── Recent documents ───"]
    if docs:
        for d in docs:
            lines.append(
                f"  [{d.get('date', '')}] {d.get('type', '?')}: {d.get('summary', '')[:100]}"
            )
    else:
        lines.append("  None recorded")

    symptoms = sorted(profile.get("symptoms", []), key=lambda x: x.get("date", ""), reverse=True)[
        :5
    ]
    lines += ["", "─── Recent symptoms ───"]
    if symptoms:
        for s in symptoms:
            sev = s.get("severity")
            sev_str = f" [sev {sev}/5]" if sev else ""
            src = s.get("source", "")
            src_str = " (ai)" if src == "ai" else ""
            note = s.get("note", "")
            note_str = f" — {note[:60]}" if note else ""
            lines.append(
                f"  {s.get('date', '')} {s.get('symptom', '?')}{sev_str}{src_str}{note_str}"
            )
    else:
        lines.append("  None recorded")

    lines += [
        "",
        f"Tracked trials     : {len(profile.get('trials_tracked', []))}",
        f"Tracked literature : {len(profile.get('literature_watched', []))} papers",
        f"Active alerts      : {len(active_alerts)}",
    ]
    if active_alerts:
        lines.append("")
        for a in active_alerts:
            lines.append(f"  ⚠  [{a['priority'].upper()}] {a['message']}")

    return "\n".join(lines)


def build_patient_context(profile: dict) -> str:
    """Compose a one-line identifying patient description from the live profile.

    System prompts call this instead of embedding identifying details in source
    code. When demographic fields are absent (fresh profile or scrubbed test
    fixture), it returns a generic phrase so the repo can be public without
    leaking PHI.
    """
    p = (profile or {}).get("patient", {}) or {}
    age = p.get("age")
    sex = (p.get("sex") or "").strip()
    if age and sex:
        head = f"a {age}-year-old {sex}"
    elif age:
        head = f"a {age}-year-old patient"
    elif sex:
        head = f"a {sex} patient"
    else:
        head = "a patient"
    diagnosis = (p.get("diagnosis") or "").strip() or "a neuroendocrine tumor"
    parts = [f"{head} with {diagnosis}"]
    location = (p.get("location") or "").strip()
    if location:
        parts.append(f"based in {location}")
    return ", ".join(parts)


def get_caregiver_relationship(profile: dict) -> str:
    """Relationship of the caregiver to the patient (e.g. 'spouse'). Defaults
    to the neutral 'caregiver' when unset so source code ships no relationship
    detail."""
    p = (profile or {}).get("patient", {}) or {}
    return (p.get("caregiver_relationship") or "").strip() or "caregiver"


def get_output_language(profile: dict) -> str:
    """Preferred output language for caregiver-facing artifacts. Defaults to
    English so a fresh deployment ships in a neutral language; override via
    `patient.language` (e.g. 'German', 'Spanish') in the live profile."""
    p = (profile or {}).get("patient", {}) or {}
    return (p.get("language") or "").strip() or "English"


def get_trial_region_filter(profile: dict) -> str | None:
    """Return a CT.gov-style country filter expression derived from
    `patient.regions_of_interest`, or None when no regions are configured."""
    p = (profile or {}).get("patient", {}) or {}
    regions = [r for r in (p.get("regions_of_interest") or []) if r]
    if not regions:
        return None
    return " or ".join(f'country="{r}"' for r in regions)
