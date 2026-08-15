"""Patient profile load/save and human-readable summary."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import backups, config
from .io import atomic_write_text
from .migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from .schema import (
    _COLLECTION_KEYS,
    clinically_empty_profile,
    normalize_profile,
    now_stamp,
    structural_check,
    validate_profile,
)
from .serialize import serialized_mutation

log = logging.getLogger(__name__)
_INITIALIZED_MARKER_NAME = ".profile-initialized"


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
    "workflow_revision": 0,
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
        "current_treatment_records": [],
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
    "document_imports": [],
    "trials_tracked": [],
    "literature_watched": [],
    "alerts": [],
    "symptoms": [],
    "symptom_episodes": [],
    "treatment_courses": [],
    "treatment_discrepancies": [],
    "treatment_row_dispositions": [],
    "clinical_judgments": [],
    "appointment_questions": [],
    "questions_generation_id": None,
    "feedback": [],
    "caregiver_actions": [],
    "visits": [],
    "research_considerations": [],
    "latest_research_update": None,
    "treatments_classification_revision": None,
    "treatments_classification_job_id": None,
}

_NCT_ID_RE = re.compile(r"NCT\d{8}")
_PMID_RE = re.compile(r"\d{1,9}")
_RESEARCH_COLLECTIONS = {
    "trial": ("trials_tracked", "nct_id", _NCT_ID_RE),
    "paper": ("literature_watched", "pmid", _PMID_RE),
}

_IMAGING_CONTEXT_AUTHORITY_FIELDS = {
    "date_precision",
    "date_kind",
    "source_document_date",
    "source_document_date_precision",
}


def imaging_context_rows(profile: dict) -> list[dict]:
    """Keep projection-only authority metadata out of existing LLM contexts."""
    return [
        {key: value for key, value in row.items() if key not in _IMAGING_CONTEXT_AUTHORITY_FIELDS}
        for row in profile.get("imaging", [])
        if isinstance(row, dict)
    ]


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


def _canonical_research_id(value: object, kind: str) -> str | None:
    try:
        pattern = _RESEARCH_COLLECTIONS[kind][2]
    except KeyError as exc:
        raise ValueError(f"Unknown research kind: {kind}") from exc
    candidate = str(value) if value is not None else ""
    return candidate if pattern.fullmatch(candidate) else None


def get_research_ids(profile: dict, kind: str) -> list[str]:
    """Return unique, canonical tracked research IDs in profile order."""
    try:
        collection, id_field, _ = _RESEARCH_COLLECTIONS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown research kind: {kind}") from exc

    values = profile.get(collection)
    if not isinstance(values, list):
        return []

    seen = set()
    ids = []
    for item in values:
        if not isinstance(item, dict):
            continue
        item_id = _canonical_research_id(item.get(id_field), kind)
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    return ids


def record_latest_research_update(
    profile: dict,
    *,
    job_id: str,
    trigger: str,
    previous_trial_ids: set[str],
    previous_paper_ids: set[str],
    record_empty: bool,
) -> dict | None:
    """Record the exact canonical IDs added by one feed or digest run."""
    previous_trials = {
        item_id
        for value in previous_trial_ids
        if (item_id := _canonical_research_id(value, "trial")) is not None
    }
    previous_papers = {
        item_id
        for value in previous_paper_ids
        if (item_id := _canonical_research_id(value, "paper")) is not None
    }
    trial_ids = [
        item_id for item_id in get_research_ids(profile, "trial") if item_id not in previous_trials
    ]
    paper_ids = [
        item_id for item_id in get_research_ids(profile, "paper") if item_id not in previous_papers
    ]
    if not record_empty and not trial_ids and not paper_ids:
        return None

    update = {
        "job_id": job_id,
        "trigger": trigger,
        "completed_at": now_stamp(),
        "trial_ids": trial_ids,
        "paper_ids": paper_ids,
    }
    profile["latest_research_update"] = update
    return update


def public_latest_research_update(profile: dict) -> dict | None:
    """Return a sanitized latest batch containing only still-tracked IDs."""
    stored = profile.get("latest_research_update")
    if not isinstance(stored, dict):
        return None

    current = {
        "trial": set(get_research_ids(profile, "trial")),
        "paper": set(get_research_ids(profile, "paper")),
    }

    def _available_ids(field: str, kind: str) -> list[str]:
        values = stored.get(field)
        if not isinstance(values, list):
            return []
        seen = set()
        available = []
        for value in values:
            item_id = _canonical_research_id(value, kind)
            if item_id is None or item_id not in current[kind] or item_id in seen:
                continue
            seen.add(item_id)
            available.append(item_id)
        return available

    trial_ids = _available_ids("trial_ids", "trial")
    paper_ids = _available_ids("paper_ids", "paper")
    return {
        "job_id": stored.get("job_id"),
        "trigger": stored.get("trigger"),
        "completed_at": stored.get("completed_at"),
        "trial_ids": trial_ids,
        "paper_ids": paper_ids,
        "trial_count": len(trial_ids),
        "paper_count": len(paper_ids),
        "total_count": len(trial_ids) + len(paper_ids),
    }


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


def _maintain_initialized_marker() -> None:
    """Best-effort marker maintenance after an authoritative profile exists."""
    try:
        atomic_write_text(config.DATA_DIR / _INITIALIZED_MARKER_NAME, "initialized\n")
    except Exception as exc:
        # The profile replace is the commit point. This secondary marker must not
        # turn an already-committed mutation into an apparent request failure.
        log.warning(
            "profile_initialized_marker_write_failed after_commit=true error_type=%s",
            type(exc).__name__,
        )


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
        profile = _load_validated(path)
        if not (config.DATA_DIR / _INITIALIZED_MARKER_NAME).exists():
            _maintain_initialized_marker()
        return profile

    # First-run creation — serialize to prevent two simultaneous first requests
    # from both creating (and then one overwriting) a new default profile.
    with serialized_mutation():
        if path.exists():
            # Another process created it between our check and lock acquisition.
            profile = _load_validated(path)
            if not (config.DATA_DIR / _INITIALIZED_MARKER_NAME).exists():
                _maintain_initialized_marker()
            return profile
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
            recovered = normalize_profile(recovered)
            _maintain_initialized_marker()
            return recovered
        initialized_marker = config.DATA_DIR / _INITIALIZED_MARKER_NAME
        if initialized_marker.exists():
            raise CorruptProfileError(
                "Profile is missing from an initialized data directory and no recovery "
                "candidate is available. Operator intervention required."
            )
        profile = json.loads(json.dumps(DEFAULT_PROFILE))  # deep copy
        save_profile(profile)
        return profile


def save_profile(
    profile: dict,
    *,
    clinical_change: bool = True,
    before_write: Callable[[dict], None] | None = None,
) -> None:
    """Persist the profile under the global transaction lock.

    Raises ``ValueError`` if *profile* is structurally invalid (not a dict,
    non-dict ``patient``, non-list collection).  This guard prevents knowingly
    persisting unusable data.  Field-level type issues (e.g. an out-of-range
    ``sstr_score``) are still permitted with a log warning, preserving forward
    compatibility.

    ``clinical_change=False`` is reserved for bookkeeping-only writes. Those
    writes must not invalidate an otherwise current clinical summary.

    The atomic replacement of ``PROFILE_PATH`` is the commit point. Failures
    before or during that replacement propagate. Initialization-marker and
    backup maintenance happen after commit and cannot make a committed save
    appear unsuccessful.
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

        if before_write is not None:
            before_write(profile)

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
        _maintain_initialized_marker()
        # Cheap: only copies once per day, then prunes.
        try:
            backups.daily_backup(config.PROFILE_PATH)
        except Exception as e:  # never let backup failure block a save
            log.warning("daily_backup raised: %s", e)


def active_documents(profile: dict) -> list[dict]:
    """Return documents whose extracted clinical content is still active."""
    return [
        item
        for item in profile.get("documents", [])
        if not item.get("excluded_from_clinical_context")
    ]


def active_alerts(profile: dict) -> list[dict]:
    """Return unresolved alerts whose clinical source dependency remains valid."""
    revision = profile.get("profile_revision")
    active = []
    for item in profile.get("alerts", []):
        if item.get("resolved"):
            continue
        kind = item.get("dependency_kind") or "profile_snapshot"
        if kind == "source" and not item.get("source_dependency_active", True):
            continue
        if kind == "profile_snapshot" and str(item.get("generation_profile_revision")) != str(
            revision
        ):
            continue
        active.append(item)
    return active


def invalidate_treatment_classification(profile: dict) -> None:
    """Mark derived treatment categories stale without deleting their audit value."""
    profile["treatments_classification_revision"] = None
    profile["treatments_classification_job_id"] = None


def raw_treatment_source_entry_id(text: str, occurrence: int) -> str:
    """Stable per-occurrence identity for one raw ``current_treatments[]`` row.

    Deliberately position independent. The public projection row ID folds in
    ``source_order``, so it re-keys whenever an earlier row is removed; caregiver
    workflow state must never hang off a positional key or it would silently
    re-attach to a different row.
    """
    digest = hashlib.sha256(f"{text}:{occurrence}".encode()).hexdigest()[:20]
    return f"txsrc_{digest}"


def raw_treatment_source_entry_ids(raw_rows: list) -> list[str]:
    """Per-occurrence identities for every raw treatment row, in stored order.

    Single source of truth shared by ``sync_treatment_records``, the treatment
    projection, and the disposition endpoint so the three can never drift.
    """
    occurrences: dict[str, int] = {}
    keys: list[str] = []
    for raw in raw_rows:
        text = str(raw)
        occurrence = occurrences.get(text, 0)
        occurrences[text] = occurrence + 1
        keys.append(raw_treatment_source_entry_id(text, occurrence))
    return keys


def sync_treatment_records(profile: dict) -> list[dict]:
    """Deterministically map raw/composite treatment strings to stable components."""
    patient = profile.setdefault("patient", {})
    records = []
    occurrences: dict[str, int] = {}
    for source_order, raw in enumerate(patient.get("current_treatments") or []):
        text = str(raw)
        occurrence = occurrences.get(text, 0)
        occurrences[text] = occurrence + 1
        source_id = raw_treatment_source_entry_id(text, occurrence)
        from .treatment_identity import split_treatment_components

        components = split_treatment_components(text)
        for component_order, component in enumerate(components):
            digest = hashlib.sha256(
                f"{source_id}:{component_order}:{component}".encode()
            ).hexdigest()[:20]
            records.append(
                {
                    "id": f"tx_{digest}",
                    "source_entry_id": source_id,
                    "source_order": source_order,
                    "component_order": component_order,
                    "text": component,
                    "source_text": text,
                }
            )
    patient["current_treatment_records"] = records
    return records


def rebuild_raw_treatments(profile: dict) -> list[str]:
    """Rebuild raw entries after component-safe edits without dropping siblings."""
    records = profile.setdefault("patient", {}).get("current_treatment_records") or []
    grouped: dict[str, list[dict]] = {}
    for record in sorted(
        records,
        key=lambda item: (item.get("source_order", 0), item.get("component_order", 0)),
    ):
        grouped.setdefault(record.get("source_entry_id") or record.get("id"), []).append(record)
    raw = [" plus ".join(item.get("text", "") for item in group) for group in grouped.values()]
    profile["patient"]["current_treatments"] = [item for item in raw if item.strip()]
    return profile["patient"]["current_treatments"]


def treatment_edit_token(profile: dict, classified: dict) -> str:
    """CAS token covering one classified row and its mapped raw components."""
    source_ids = set(classified.get("source_treatment_ids") or [])
    records = [
        item
        for item in profile.get("patient", {}).get("current_treatment_records", [])
        if item.get("id") in source_ids
    ]
    canonical = json.dumps(
        {"classified": classified, "records": records},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def treatment_classification_is_current(profile: dict) -> bool:
    """Whether stored generated classification matches the current revision.

    The LLM classifier that refreshed this was retired, so nothing sets the
    revision any more and this is effectively always ``False``. It is kept
    because the stored revision/job-id provenance is still projected as
    treatment-reconciliation authority.
    """
    revision = profile.get("treatments_classification_revision")
    return revision is not None and str(revision) == str(profile.get("profile_revision"))


def current_treatment_records(profile: dict) -> list[dict]:
    """Return deterministic treatment components for model context.

    Component text comes from the deterministic split maintained by
    ``sync_treatment_records``; raw entries are the fallback when no component
    mapping exists yet. No category is inferred and no generated
    classification is read — treatment status is caregiver workflow authority
    and is deliberately not exposed to any model prompt.
    """
    records = profile.get("patient", {}).get("current_treatment_records") or []
    texts = [
        str(record.get("text", "")).strip()
        for record in records
        if isinstance(record, dict) and str(record.get("text", "")).strip()
    ]
    if not texts:
        texts = [
            str(text).strip()
            for text in profile.get("patient", {}).get("current_treatments", [])
            if str(text).strip()
        ]
    return [{"text": text, "label": text} for text in texts]


def alert_token(alert: dict) -> str:
    """Return a semantic compare-and-swap token for one alert."""

    def immutable_value(value):
        if isinstance(value, dict):
            return {
                key: immutable_value(item)
                for key, item in value.items()
                if key not in {"resolve_token", "result_hash", "result_snapshot"}
            }
        if isinstance(value, list):
            return [immutable_value(item) for item in value]
        return value

    canonical = json.dumps(
        immutable_value(alert),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def summary_is_current(profile: dict) -> bool:
    """Return whether generated summary content is safe to reuse as current."""
    summary = profile.get("executive_summary")
    if not isinstance(summary, dict) or not summary:
        return False
    if profile.get("summary_stale") is not False or summary.get("stale") is not False:
        return False
    generation_id = summary.get("generation_id")
    if not isinstance(generation_id, str) or not generation_id.strip():
        return False
    revision = summary.get("summary_revision")
    if revision is None or str(revision) != str(profile.get("profile_revision")):
        return False
    stored_judgment_hash = summary.get("judgment_context_hash")
    if stored_judgment_hash is None and profile.get("clinical_judgments"):
        return False
    if stored_judgment_hash is not None:
        from .judgments import clinical_judgments_fingerprint

        if stored_judgment_hash != clinical_judgments_fingerprint(profile):
            return False
    return True


def get_patient_summary(profile: dict) -> str:
    """Concise text summary of the patient's current state, used as LLM context."""
    p = profile["patient"]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date", ""), reverse=True)[:6]
    docs = sorted(active_documents(profile), key=lambda x: x.get("date", ""), reverse=True)[:3]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date", ""), reverse=True)[:2]
    current_alerts = active_alerts(profile)

    lines = [
        "═══ PATIENT PROFILE ═══",
        f"Diagnosis : {p.get('diagnosis') or 'unknown'}",
        f"Age / Sex : {p.get('age') or 'unknown'} / {p.get('sex') or 'unknown'}",
        f"Ki-67     : {p.get('ki67_percent', 'unknown')}%",
        f"SSTR      : {p.get('sstr_status', 'unknown')} (score: {p.get('sstr_score', 'unknown')})",
        # Recorded statements, not a curated list: starts, stops, dose/schedule
        # changes and administration detail all land in current_treatments[].
        # This reaches the orchestrator, executive summary, deep sweep and
        # question prompts, so the label must not imply any entry is ongoing.
        f"Treatment statements: "
        f"{', '.join(p.get('current_treatments', [])) or 'none documented'}",
        "  (recorded wording, including stops, dose/schedule changes and "
        "administration detail — not a verified list of current treatments)",
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
                f"  {i.get('date', '')}  {i.get('modality', '?')}: "
                f"{(i.get('impression') or i.get('findings') or '')[:120]}"
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

    symptoms = sorted(profile.get("symptoms", []), key=lambda x: x.get("date") or "", reverse=True)[
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
        f"Active alerts      : {len(current_alerts)}",
    ]
    if current_alerts:
        lines.append("")
        for a in current_alerts:
            lines.append(f"  ⚠  [{a['priority'].upper()}] {a['message']}")

    captured = []
    for visit in profile.get("visits", []):
        if not isinstance(visit, dict):
            continue
        for question in visit.get("question_snapshots", []):
            answer = question.get("answer") if isinstance(question, dict) else None
            if not isinstance(answer, dict):
                continue
            captured.append(
                {
                    "kind": "answer",
                    "visit": visit.get("title") or "Visit",
                    "question": question.get("text") or "",
                    "status": answer.get("status"),
                    "text": answer.get("text"),
                }
            )
        for decision in visit.get("decisions", []):
            if isinstance(decision, dict) and decision.get("status") == "active":
                captured.append(
                    {
                        "kind": "decision",
                        "visit": visit.get("title") or "Visit",
                        "text": decision.get("text") or "",
                    }
                )
    from .research_disposition import excluded_research_action_ids_for_model

    excluded_action_ids = excluded_research_action_ids_for_model(profile)
    for action in profile.get("caregiver_actions", []):
        if isinstance(action, dict) and action.get("id") in excluded_action_ids:
            continue
        outcome = action.get("outcome") if isinstance(action, dict) else None
        if not isinstance(outcome, dict) or outcome.get("kind") not in {
            "caregiver_reported",
            "clinician_attributed",
        }:
            continue
        captured.append(
            {
                "kind": "action_outcome",
                "action": action.get("text") or "Follow-up",
                "attribution": outcome.get("kind"),
                "text": outcome.get("text") or "",
            }
        )
    if captured:
        lines += [
            "",
            "─── Caregiver-captured clinician statements (attributed, unverified) ───",
        ]
        for item in captured[-12:]:
            if item["kind"] == "answer":
                answer = "explicitly unknown" if item["status"] == "unknown" else item["text"]
                lines.append(
                    f"  [{item['visit']}] Q: {item['question'][:180]} — "
                    f"caregiver-recorded clinician answer: {str(answer)[:300]}"
                )
            else:
                if item["kind"] == "decision":
                    lines.append(
                        f"  [{item['visit']}] caregiver-recorded clinician decision: "
                        f"{item['text'][:400]}"
                    )
                else:
                    label = (
                        "caregiver-recorded clinician outcome"
                        if item["attribution"] == "clinician_attributed"
                        else "caregiver-reported outcome"
                    )
                    lines.append(f"  [{item['action'][:180]}] {label}: {item['text'][:400]}")

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
