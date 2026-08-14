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

import copy
import datetime
import hashlib
import json
import logging
from typing import Any

log = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION: int = 15

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
            alert["dependency_kind"] = "profile_snapshot"
            alert["generation_profile_revision"] = int(data.get("profile_revision") or 0)
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


@_migration("0006_add_stable_treatment_records", to_version=6)
def _m0006_add_stable_treatment_records(data: dict) -> dict:
    """v5 → v6: backfill deterministic raw treatment component identities."""
    patient = data.get("patient")
    if patient is None:
        patient = {}
        data["patient"] = patient
    elif not isinstance(patient, dict):
        raise TypeError("migration 0006 requires patient to be a dict or null")
    records = []
    occurrences: dict[str, int] = {}
    for source_order, raw in enumerate(patient.get("current_treatments") or []):
        text = str(raw)
        occurrence = occurrences.get(text, 0)
        occurrences[text] = occurrence + 1
        source_digest = hashlib.sha256(f"{text}:{occurrence}".encode()).hexdigest()[:20]
        source_id = f"txsrc_{source_digest}"
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
    data["treatments_classification_revision"] = None
    data["treatments_classification_job_id"] = None
    data["schema_version"] = 6
    return data


@_migration("0007_harden_legacy_generated_alerts", to_version=7)
def _m0007_harden_legacy_generated_alerts(data: dict) -> dict:
    """v6 → v7: contain legacy generated claims and remove fail-open lifetimes."""
    from .tools import _screening_safe_alert_text

    durable_sources = {"intake_extraction_failure", "trial_status_poll"}
    revision = int(data.get("profile_revision") or 0)
    alerts_by_id = {}
    for alert in data.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        alert["message"] = _screening_safe_alert_text(alert.get("message", ""))
        alert["action_required"] = _screening_safe_alert_text(alert.get("action_required", ""))
        if alert.get("source") in durable_sources:
            alert["dependency_kind"] = "durable"
        elif alert.get("source_document_id"):
            alert["dependency_kind"] = "source"
        elif alert.get("dependency_kind") == "durable":
            alert["dependency_kind"] = "profile_snapshot"
            alert["generation_profile_revision"] = revision
        elif alert.get("dependency_kind") == "profile_snapshot":
            alert.setdefault("generation_profile_revision", revision)
        if alert.get("id"):
            alerts_by_id[alert["id"]] = alert

    for receipt in data.get("document_imports") or []:
        if not isinstance(receipt, dict):
            continue
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                continue
            target = change.get("target") or {}
            if target.get("collection") != "alerts":
                continue
            alert = alerts_by_id.get(target.get("record_id"))
            effective = change.get("effective_value")
            if alert is None or not isinstance(effective, dict):
                continue
            for key in (
                "message",
                "action_required",
                "dependency_kind",
                "generation_profile_revision",
                "source_dependency_active",
            ):
                if key in alert:
                    effective[key] = alert[key]
    data["schema_version"] = 7
    return data


@_migration("0008_add_follow_through_foundation", to_version=8)
def _m0008_add_follow_through_foundation(data: dict) -> dict:
    """v7 -> v8: add durable workflow state without inferring clinical facts."""
    from .follow_through import ensure_summary_action_ids

    data.setdefault("workflow_revision", 0)
    if not isinstance(data.get("caregiver_actions"), list):
        data["caregiver_actions"] = []
    if not isinstance(data.get("visits"), list):
        data["visits"] = []

    summary = data.get("executive_summary")
    if isinstance(summary, dict):
        ensure_summary_action_ids(summary)
        generation_id = summary.get("generation_id")
        summary_revision = summary.get("summary_revision")
        current_revision = data.get("profile_revision")
        complete_current_identity = (
            isinstance(generation_id, str)
            and bool(generation_id.strip())
            and summary_revision is not None
            and str(summary_revision) == str(current_revision)
            and summary.get("stale") is False
            and data.get("summary_stale") is False
        )
        if not complete_current_identity:
            summary["stale"] = True
            summary.setdefault("stale_reason", "legacy_missing_generation_provenance")
            data["summary_stale"] = True

    alerts_by_id = {}
    for alert in data.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        alert.setdefault("history", [])
        if alert.get("resolved") and "resolution" not in alert:
            alert["resolution"] = {
                "status": "resolved",
                "resolved_at": None,
                "outcome_kind": "legacy_unknown",
                "outcome_text": None,
                "provenance": {"capture_method": "legacy_unknown"},
                "follow_up_id": None,
                "visit_id": None,
                "decision_id": None,
            }
        if alert.get("id"):
            alerts_by_id[alert["id"]] = alert

    for receipt in data.get("document_imports") or []:
        if not isinstance(receipt, dict):
            continue
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                continue
            target = change.get("target") or {}
            if target.get("collection") != "alerts":
                continue
            alert = alerts_by_id.get(target.get("record_id"))
            effective = change.get("effective_value")
            if alert is None or not isinstance(effective, dict):
                continue
            effective["history"] = copy.deepcopy(alert["history"])
            if "resolution" in alert:
                effective["resolution"] = copy.deepcopy(alert["resolution"])

    data["schema_version"] = 8
    return data


@_migration("0009_add_biomarker_projection_authority", to_version=9)
def _m0009_add_biomarker_projection_authority(data: dict) -> dict:
    """v8 -> v9: add deterministic biomarker identity and explicit authority fields."""
    from .schema import derive_date_precision

    biomarkers = data.get("biomarkers") or []
    used_ids = {
        row.get("id")
        for row in biomarkers
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    occurrences: dict[str, int] = {}
    migration_fields = {
        "id",
        "date_precision",
        "source_document_date_precision",
        "flag_authority",
    }
    for row in biomarkers:
        if not isinstance(row, dict):
            continue
        if not row.get("id"):
            semantic = {
                key: value for key, value in sorted(row.items()) if key not in migration_fields
            }
            source_id = row.get("source_document_id")
            start = row.get("evidence_start")
            end = row.get("evidence_end")
            if (
                isinstance(source_id, str)
                and source_id
                and isinstance(start, int)
                and isinstance(end, int)
                and end > start
            ):
                provenance = {
                    "kind": "source_span",
                    "source_document_id": source_id,
                    "evidence_status": row.get("evidence_status"),
                    "evidence_start": start,
                    "evidence_end": end,
                }
            elif isinstance(source_id, str) and source_id:
                provenance = {
                    "kind": "source",
                    "source_document_id": source_id,
                    "evidence_status": row.get("evidence_status"),
                }
            else:
                provenance = {
                    "kind": "legacy",
                    "added_at": row.get("added_at"),
                }
            base = json.dumps(
                {"provenance": provenance, "semantic": semantic},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            )
            occurrence = occurrences.get(base, 0)
            occurrences[base] = occurrence + 1
            salt = 0
            while True:
                digest = hashlib.sha256(f"{base}:{occurrence}:{salt}".encode()).hexdigest()[:32]
                candidate = f"fact_biomarker_legacy_{digest}"
                if candidate not in used_ids:
                    break
                salt += 1
            row["id"] = candidate
            used_ids.add(candidate)

        precision = derive_date_precision(row.get("date"))
        row.setdefault("date_precision", precision)
        row.setdefault(
            "date_kind",
            "clinical_unspecified" if precision != "unknown" else "unknown",
        )
        row.setdefault("source_document_date", None)
        row.setdefault(
            "source_document_date_precision",
            derive_date_precision(row.get("source_document_date")),
        )
        row.setdefault("specimen", None)
        row.setdefault("assay", None)
        row.setdefault("method", None)
        row.setdefault("flag_authority", "legacy_unknown" if row.get("flag") else "unknown")

    biomarkers_by_id = {
        row.get("id"): row
        for row in biomarkers
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    for receipt in data.get("document_imports") or []:
        if not isinstance(receipt, dict):
            continue
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                continue
            target = change.get("target") or {}
            if target.get("collection") != "biomarkers":
                continue
            row = biomarkers_by_id.get(target.get("record_id"))
            effective = change.get("effective_value")
            if row is None or not isinstance(effective, dict):
                continue
            for field in (
                "date_precision",
                "date_kind",
                "source_document_date",
                "source_document_date_precision",
                "specimen",
                "assay",
                "method",
                "flag_authority",
            ):
                effective[field] = copy.deepcopy(row.get(field))

    data["schema_version"] = 9
    return data


@_migration("0010_add_imaging_projection_authority", to_version=10)
def _m0010_add_imaging_projection_authority(data: dict) -> dict:
    """v9 -> v10: add deterministic imaging identity and explicit date authority."""
    from .imaging_series import derive_imaging_record_id, imaging_identity_base
    from .schema import derive_date_precision

    imaging = data.get("imaging") or []
    used_ids = {
        row.get("id")
        for row in imaging
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    occurrences: dict[str, int] = {}
    for row in imaging:
        if not isinstance(row, dict):
            continue
        if not row.get("id"):
            base = imaging_identity_base(row)
            occurrence = occurrences.get(base, 0)
            occurrences[base] = occurrence + 1
            candidate = derive_imaging_record_id(
                row,
                occurrence=occurrence,
                used_ids=used_ids,
            )
            row["id"] = candidate
            used_ids.add(candidate)

        precision = derive_date_precision(row.get("date"))
        row.setdefault("date_precision", precision)
        row.setdefault("date_kind", "legacy_unknown" if precision != "unknown" else "unknown")
        row.setdefault("source_document_date", None)
        row.setdefault(
            "source_document_date_precision",
            derive_date_precision(row.get("source_document_date")),
        )

    id_counts: dict[str, int] = {}
    for row in imaging:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id"):
            id_counts[row["id"]] = id_counts.get(row["id"], 0) + 1
    imaging_by_id = {
        row["id"]: row
        for row in imaging
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and id_counts.get(row["id"]) == 1
    }
    for receipt in data.get("document_imports") or []:
        if not isinstance(receipt, dict):
            continue
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                continue
            target = change.get("target") or {}
            if target.get("collection") != "imaging":
                continue
            row = imaging_by_id.get(target.get("record_id"))
            effective = change.get("effective_value")
            if row is None or not isinstance(effective, dict):
                continue
            for field in (
                "date_precision",
                "date_kind",
                "source_document_date",
                "source_document_date_precision",
            ):
                effective[field] = copy.deepcopy(row.get(field))

    data["schema_version"] = 10
    return data


@_migration("0011_add_symptom_episode_authority", to_version=11)
def _m0011_add_symptom_episode_authority(data: dict) -> dict:
    """v10 -> v11: preserve observations and add separate episode authority."""
    from .schema import derive_date_precision
    from .symptom_episodes import (
        derive_symptom_observation_id,
        symptom_observation_identity_base,
    )

    symptoms = data.get("symptoms") or []
    used_ids = {
        row.get("id")
        for row in symptoms
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    occurrences: dict[str, int] = {}
    for row in symptoms:
        if not isinstance(row, dict):
            continue
        if not row.get("id"):
            base = symptom_observation_identity_base(row)
            occurrence = occurrences.get(base, 0)
            occurrences[base] = occurrence + 1
            row["id"] = derive_symptom_observation_id(
                row,
                occurrence=occurrence,
                used_ids=used_ids,
            )
            used_ids.add(row["id"])

        precision = derive_date_precision(row.get("date"))
        row.setdefault("date_precision", precision)
        row.setdefault("date_kind", "legacy_unknown" if precision != "unknown" else "unknown")
        row.setdefault("source_document_date", None)
        row.setdefault(
            "source_document_date_precision",
            derive_date_precision(row.get("source_document_date")),
        )

    id_counts: dict[str, int] = {}
    for row in symptoms:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id"):
            id_counts[row["id"]] = id_counts.get(row["id"], 0) + 1
    symptoms_by_id = {
        row["id"]: row
        for row in symptoms
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and id_counts.get(row["id"]) == 1
    }
    for receipt in data.get("document_imports") or []:
        if not isinstance(receipt, dict):
            continue
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                continue
            target = change.get("target") or {}
            if target.get("collection") != "symptoms":
                continue
            row = symptoms_by_id.get(target.get("record_id"))
            effective = change.get("effective_value")
            if row is None or not isinstance(effective, dict):
                continue
            for field in (
                "date_precision",
                "date_kind",
                "source_document_date",
                "source_document_date_precision",
            ):
                effective[field] = copy.deepcopy(row.get(field))

    if data.get("symptom_episodes") is None:
        data["symptom_episodes"] = []
    data["schema_version"] = 11
    return data


@_migration("0012_add_treatment_reconciliation_authority", to_version=12)
def _m0012_add_treatment_reconciliation_authority(data: dict) -> dict:
    """v11 -> v12: add empty caregiver treatment authority without inference."""
    if data.get("treatment_courses") is None:
        data["treatment_courses"] = []
    if data.get("treatment_discrepancies") is None:
        data["treatment_discrepancies"] = []
    data["schema_version"] = 12
    return data


@_migration("0013_add_treatment_terminal_authority", to_version=13)
def _m0013_add_treatment_terminal_authority(data: dict) -> dict:
    """v12 -> v13: mark only pre-extension past courses without inference."""
    courses = data.get("treatment_courses")
    if isinstance(courses, list):
        for course in courses:
            if (
                isinstance(course, dict)
                and course.get("status") == "past"
                and "terminal_qualifier" not in course
            ):
                course["terminal_qualifier"] = "legacy_unspecified"
    data["schema_version"] = 13
    return data


@_migration("0014_add_research_disposition_authority", to_version=14)
def _m0014_add_research_disposition_authority(data: dict) -> dict:
    """v13 -> v14: add stable research occurrences without inferring workflow."""
    from .research_disposition import assign_legacy_research_record_ids

    assign_legacy_research_record_ids(data)
    if data.get("research_considerations") is None:
        data["research_considerations"] = []
    data["schema_version"] = 14
    return data


@_migration("0015_add_profile_revision_authority", to_version=15)
def _m0015_add_profile_revision_authority(data: dict) -> dict:
    """v14 -> v15: backfill only a truly missing top-level revision."""
    if "profile_revision" not in data:
        data["profile_revision"] = 0
    data["schema_version"] = 15
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
