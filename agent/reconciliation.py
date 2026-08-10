"""Scoped document-import receipts, correction, and compare-and-swap undo."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
from typing import Any

from .intake import _treatment_similarity
from .provenance import anchor_source_quote
from .schema import derive_date_precision, now_stamp


class ReconciliationError(ValueError):
    """Base error for an invalid receipt mutation."""


class ImportConflict(ReconciliationError):
    """The imported target changed after the receipt was created."""


_EDITABLE_FIELDS = {
    "biomarkers": [
        "date",
        "date_kind",
        "source_document_date",
        "marker",
        "value",
        "unit",
        "reference_range",
        "flag",
        "specimen",
        "assay",
        "method",
    ],
    "imaging": [
        "date",
        "date_kind",
        "source_document_date",
        "modality",
        "findings",
        "impression",
        "new_lesions",
    ],
    "symptoms": ["date", "symptom", "severity", "note", "related_treatment"],
    "appointments": ["date", "description", "type"],
    "documents": ["date", "type", "summary", "key_findings"],
}
_SCALAR_FIELDS = {
    "ki67_update": ("ki67_percent", "Ki-67"),
    "sstr_status_update": ("sstr_status", "SSTR status"),
    "sstr_score_update": ("sstr_score", "SSTR score"),
}
_COLLECTION_LABELS = {
    "biomarkers": "Biomarker",
    "imaging": "Imaging finding",
    "symptoms": "Symptom",
    "appointments": "Appointment",
    "documents": "Document summary",
    "alerts": "Safety alert",
}


def _clone(value: Any) -> Any:
    return copy.deepcopy(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _token(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _change_id(index: int) -> str:
    return f"chg_{index + 1:03d}"


def _row_label(collection: str, row: dict) -> str:
    return str(
        row.get("marker")
        or row.get("modality")
        or row.get("symptom")
        or row.get("description")
        or row.get("summary")
        or row.get("message")
        or _COLLECTION_LABELS.get(collection, "Imported value")
    )[:200]


def _evidence_from_row(row: dict) -> dict:
    if row.get("evidence_status"):
        return {
            "evidence_status": row.get("evidence_status"),
            "evidence_start": row.get("evidence_start"),
            "evidence_end": row.get("evidence_end"),
        }
    evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
    preferred = next(
        (item for item in evidence if item.get("evidence_status") == "verified"),
        evidence[0] if evidence else {},
    )
    return {
        "evidence_status": preferred.get("evidence_status") or "missing",
        "evidence_start": preferred.get("evidence_start"),
        "evidence_end": preferred.get("evidence_end"),
    }


def _document_evidence(document: dict, field: str, index: int | None) -> dict:
    for item in document.get("evidence", []):
        if item.get("field") == field and item.get("item_index") == index:
            return _evidence_from_row(item)
    return {"evidence_status": "missing", "evidence_start": None, "evidence_end": None}


def _new_change(
    changes: list[dict],
    *,
    category: str,
    label: str,
    operation: str,
    target: dict,
    before: Any,
    after: Any,
    source_document_id: str,
    evidence: dict | None = None,
    editable_fields: list[str] | None = None,
) -> None:
    state = (
        "unchanged"
        if operation == "unchanged"
        else "derived"
        if operation == "derived"
        else "active"
    )
    changes.append(
        {
            "id": _change_id(len(changes)),
            "category": category,
            "label": label,
            "operation": operation,
            "target": target,
            "before": _clone(before),
            "after": _clone(after),
            "effective_value": _clone(after),
            "source_document_id": source_document_id,
            **(evidence or {"evidence_status": "missing"}),
            "editable_fields": list(editable_fields or []),
            "state": state,
            "history": [],
        }
    )


def build_import_record(
    before: dict,
    after: dict,
    extracted: dict,
    *,
    job_id: str,
    text: str,
) -> dict:
    """Build and append the direct-intake reconciliation record."""
    source_id = extracted["source_document_id"]
    source = next(item for item in after.get("source_documents", []) if item.get("id") == source_id)
    source["feed_job_id"] = job_id
    document = next(
        item for item in after.get("documents", []) if item.get("source_document_id") == source_id
    )
    changes: list[dict] = []

    for collection in ("documents", "biomarkers", "imaging", "symptoms", "appointments", "alerts"):
        prior_ids = {
            item.get("id")
            for item in before.get(collection, [])
            if isinstance(item, dict) and item.get("id")
        }
        for row in after.get(collection, []):
            if (
                not isinstance(row, dict)
                or row.get("source_document_id") != source_id
                or row.get("id") in prior_ids
            ):
                continue
            if collection == "alerts":
                row["source_job_id"] = job_id
                row["source_dependency_active"] = True
            _new_change(
                changes,
                category=collection,
                label=_row_label(collection, row),
                operation="added",
                target={
                    "kind": "collection",
                    "collection": collection,
                    "record_id": row.get("id"),
                    "path": [],
                },
                before=None,
                after=row,
                source_document_id=source_id,
                evidence=_evidence_from_row(row),
                editable_fields=_EDITABLE_FIELDS.get(collection),
            )

    for extracted_key, (patient_key, label) in _SCALAR_FIELDS.items():
        if extracted.get(extracted_key) is None:
            continue
        old = before.get("patient", {}).get(patient_key)
        new = after.get("patient", {}).get(patient_key)
        if old == new:
            operation = "unchanged"
        elif old not in (None, "", [], {}):
            operation = "conflict"
        else:
            operation = "added"
        _new_change(
            changes,
            category="patient",
            label=label,
            operation=operation,
            target={
                "kind": "scalar",
                "collection": None,
                "record_id": None,
                "path": ["patient", patient_key],
            },
            before=old,
            after=new,
            source_document_id=source_id,
            evidence=_document_evidence(document, extracted_key, None),
            editable_fields=["value"] if operation != "unchanged" else [],
        )

    before_treatments = list(before.get("patient", {}).get("current_treatments", []))
    after_treatments = list(after.get("patient", {}).get("current_treatments", []))
    newly_added = [item for item in after_treatments if item not in before_treatments]
    for index, treatment in enumerate(extracted.get("treatment_changes") or []):
        operation = "added" if treatment in newly_added else "unchanged"
        effective = (
            treatment
            if operation == "added"
            else next(
                (
                    item
                    for item in before_treatments
                    if treatment.casefold() in item.casefold()
                    or item.casefold() in treatment.casefold()
                    or _treatment_similarity(treatment.casefold(), item.casefold()) > 0.7
                ),
                treatment,
            )
        )
        _new_change(
            changes,
            category="treatments",
            label=str(treatment)[:200],
            operation=operation,
            target={"kind": "treatment", "collection": None, "record_id": None, "path": []},
            before=None if operation == "added" else effective,
            after=effective,
            source_document_id=source_id,
            evidence=_document_evidence(document, "treatment_changes", index),
            editable_fields=["value"] if operation == "added" else [],
        )

    for collection, extracted_key, matcher in (
        (
            "symptoms",
            "symptoms_reported",
            lambda existing, candidate: (
                (existing.get("symptom") or "").strip().casefold()
                == (candidate.get("symptom") or "").strip().casefold()
                and existing.get("date") == document.get("date")
            ),
        ),
        (
            "appointments",
            "appointments",
            lambda existing, candidate: (
                (existing.get("date") or "")[:10] == (candidate.get("date") or "")[:10]
                and (existing.get("description") or existing.get("notes") or "").strip().casefold()
                == (candidate.get("description") or candidate.get("notes") or "").strip().casefold()
            ),
        ),
    ):
        for candidate in extracted.get(extracted_key) or []:
            matching = next(
                (
                    item
                    for item in before.get(collection, [])
                    if isinstance(item, dict) and matcher(item, candidate)
                ),
                None,
            )
            if matching is None:
                continue
            evidence = anchor_source_quote(text, candidate.get("source_quote"))
            _new_change(
                changes,
                category=collection,
                label=_row_label(collection, candidate),
                operation="unchanged",
                target={
                    "kind": "collection" if matching.get("id") else "none",
                    "collection": collection if matching.get("id") else None,
                    "record_id": matching.get("id"),
                    "path": [],
                },
                before=matching,
                after=matching,
                source_document_id=source_id,
                evidence=evidence,
            )

    record = {
        "id": f"import_{job_id}",
        "job_id": job_id,
        "source_document_id": source_id,
        "ingested_at": source.get("ingested_at") or now_stamp(),
        "filename": source.get("filename"),
        "media_type": source.get("media_type"),
        "document_type": document.get("type"),
        "document_date": document.get("date"),
        "document_summary": document.get("summary"),
        "applied_revision": int(before.get("profile_revision") or 0) + 1,
        "receipt_revision": 1,
        "status": "active",
        "changes": changes,
    }
    after.setdefault("document_imports", []).insert(0, record)
    return record


def add_derived_research(
    profile: dict,
    job_id: str,
    *,
    trial_ids: list[str],
    paper_ids: list[str],
) -> None:
    """Add read-only research outcomes to an existing receipt."""
    record = find_import(profile, job_id)
    source_id = record["source_document_id"]
    existing = {
        (change.get("category"), str(change.get("after")))
        for change in record.get("changes", [])
        if change.get("operation") == "derived"
    }
    for category, values, label in (
        ("trials", trial_ids, "Trial discovered"),
        ("papers", paper_ids, "Paper discovered"),
    ):
        for value in values:
            if (category, str(value)) in existing:
                continue
            _new_change(
                record["changes"],
                category=category,
                label=f"{label}: {value}",
                operation="derived",
                target={"kind": "none", "collection": None, "record_id": None, "path": []},
                before=None,
                after=value,
                source_document_id=source_id,
            )
    if trial_ids or paper_ids:
        record["receipt_revision"] = int(record.get("receipt_revision") or 0) + 1


def find_import(profile: dict, job_id: str) -> dict:
    record = next(
        (item for item in profile.get("document_imports", []) if item.get("job_id") == job_id),
        None,
    )
    if record is None:
        raise ReconciliationError("Receipt not found")
    return record


def _target_value(profile: dict, change: dict) -> Any:
    target = change.get("target") or {}
    kind = target.get("kind")
    if kind == "collection":
        collection = target.get("collection")
        return next(
            (
                item
                for item in profile.get(collection, [])
                if isinstance(item, dict) and item.get("id") == target.get("record_id")
            ),
            None,
        )
    if kind == "scalar":
        value: Any = profile
        for part in target.get("path") or []:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
    if kind == "treatment":
        expected = change.get("effective_value")
        return next(
            (
                item
                for item in profile.get("patient", {}).get("current_treatments", [])
                if item == expected
            ),
            None,
        )
    return None


def _comparison_value(change: dict, value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return _semantic_value(value)


def _semantic_value(value: Any) -> Any:
    """Canonical clinical value with schema-added null defaults removed."""
    if isinstance(value, dict):
        return {
            key: _semantic_value(item)
            for key, item in sorted(value.items())
            if item is not None
            and not (key == "source_dependency_active" and item is True)
            and not (key == "excluded_from_clinical_context" and item is False)
            and not (key == "history" and item == [])
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    return value


def _same_target(change: dict, current: Any) -> bool:
    effective = change.get("effective_value")
    if not isinstance(current, dict) and not isinstance(effective, dict):
        return current == effective
    return _canonical(_comparison_value(change, current)) == _canonical(
        _comparison_value(change, effective)
    )


def _same_locator(left: dict, right: dict) -> bool:
    ltarget = left.get("target") or {}
    rtarget = right.get("target") or {}
    if ltarget.get("kind") != rtarget.get("kind"):
        return False
    if ltarget.get("kind") == "collection":
        return (
            ltarget.get("collection"),
            ltarget.get("record_id"),
        ) == (
            rtarget.get("collection"),
            rtarget.get("record_id"),
        )
    if ltarget.get("kind") == "scalar":
        return ltarget.get("path") == rtarget.get("path")
    if ltarget.get("kind") == "treatment":
        return left.get("effective_value") == right.get("effective_value")
    return False


def _has_later_claim(profile: dict, record: dict, change: dict) -> bool:
    found = False
    for candidate_record in reversed(profile.get("document_imports", [])):
        if candidate_record.get("job_id") == record.get("job_id"):
            found = True
            continue
        if not found or candidate_record.get("status") == "undone":
            continue
        if any(
            _same_locator(change, candidate) for candidate in candidate_record.get("changes", [])
        ):
            return True
    return False


def _conflict_reason(profile: dict, record: dict, change: dict) -> str | None:
    if change.get("state") not in {"active", "corrected"}:
        return None
    current = _target_value(profile, change)
    if not _same_target(change, current):
        return "The affected patient value changed after this receipt was created."
    if _has_later_claim(profile, record, change):
        return "A later document also supports or changed this patient value."
    return None


def public_receipt(profile: dict, job_id: str) -> dict:
    record = find_import(profile, job_id)
    result = _clone(record)
    active_tokens = []
    for original, change in zip(record.get("changes", []), result.get("changes", []), strict=False):
        current = _target_value(profile, original)
        change["target_token"] = _token(_comparison_value(original, current))
        reason = _conflict_reason(profile, record, original)
        change["conflicted"] = reason is not None
        change["conflict_reason"] = reason
        change["removable"] = not (
            original.get("category") == "alerts"
            and isinstance(original.get("effective_value"), dict)
            and original["effective_value"].get("dependency_kind") == "durable"
        )
        if (
            original.get("state") in {"active", "corrected"}
            and original.get("target", {}).get("kind") != "none"
        ):
            active_tokens.append((original.get("id"), change["target_token"], reason))
        if (
            change.get("evidence_status") == "verified"
            and change.get("evidence_start") is not None
            and change.get("evidence_end") is not None
        ):
            change["evidence_url"] = (
                f"/api/evidence/{record['source_document_id']}?start={change['evidence_start']}"
                f"&end={change['evidence_end']}"
            )
        if original.get("state") == "corrected":
            change["original_evidence_status"] = change.get("evidence_status") or "missing"
            if change.get("evidence_url"):
                change["original_evidence_url"] = change["evidence_url"]
            if isinstance(current, dict):
                change["evidence_status"] = current.get("evidence_status") or "missing"
                if (
                    change["evidence_status"] == "verified"
                    and current.get("evidence_start") is not None
                    and current.get("evidence_end") is not None
                ):
                    change["evidence_url"] = (
                        f"/api/evidence/{record['source_document_id']}"
                        f"?start={current['evidence_start']}&end={current['evidence_end']}"
                    )
                else:
                    change.pop("evidence_url", None)
            else:
                change["evidence_status"] = "missing"
                change.pop("evidence_url", None)
    result["profile_revision"] = profile.get("profile_revision")
    result["source_url"] = f"/api/sources/{record['source_document_id']}"
    result["undo_token"] = _token(
        {
            "receipt_revision": record.get("receipt_revision"),
            "targets": active_tokens,
        }
    )
    result["can_undo"] = bool(active_tokens) and not any(item[2] for item in active_tokens)
    result["counts"] = {
        key: sum(1 for item in result.get("changes", []) if item.get("operation") == key)
        for key in ("added", "updated", "conflict", "unchanged", "derived")
    }
    return result


def _require_preconditions(
    profile: dict,
    record: dict,
    change: dict,
    *,
    receipt_revision: Any,
    target_token: str,
) -> Any:
    if int(receipt_revision or -1) != int(record.get("receipt_revision") or 0):
        raise ImportConflict("The receipt changed. Reload it before editing.")
    reason = _conflict_reason(profile, record, change)
    if reason:
        raise ImportConflict(reason)
    current = _target_value(profile, change)
    if not target_token or target_token != _token(_comparison_value(change, current)):
        raise ImportConflict("The affected patient value changed. Reload the receipt.")
    return current


def _find_change(record: dict, change_id: str) -> dict:
    change = next((item for item in record.get("changes", []) if item.get("id") == change_id), None)
    if change is None:
        raise ReconciliationError("Receipt entry not found")
    if change.get("state") not in {"active", "corrected"}:
        raise ReconciliationError("This receipt entry is no longer editable")
    return change


def _validate_scalar(path: list[str], value: Any) -> Any:
    field = path[-1] if path else ""
    if field == "ki67_percent":
        if (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0 <= value <= 100
        ):
            raise ReconciliationError("Ki-67 must be a number from 0 to 100")
        return value
    if field == "sstr_status":
        if value not in {"positive", "negative", "unknown"}:
            raise ReconciliationError("SSTR status must be positive, negative, or unknown")
        return value
    if field == "sstr_score":
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 4:
            raise ReconciliationError("SSTR score must be an integer from 0 to 4")
        return value
    raise ReconciliationError("This patient field cannot be corrected here")


def _required_text(value: Any, label: str, *, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReconciliationError(f"{label} is required")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise ReconciliationError(f"{label} is too long")
    return cleaned


def _date_text(value: Any, label: str = "Date") -> str:
    cleaned = _required_text(value, label, maximum=10)
    try:
        datetime.date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ReconciliationError(f"{label} must use YYYY-MM-DD") from exc
    return cleaned


def _partial_date_text(value: Any, label: str) -> str | None:
    if value is None or value == "":
        return None
    cleaned = _required_text(value, label, maximum=10)
    if derive_date_precision(cleaned) == "unknown":
        raise ReconciliationError(f"{label} must use YYYY-MM-DD, YYYY-MM, or YYYY")
    return cleaned


def _optional_text(value: Any, label: str, *, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ReconciliationError(f"{label} must be text")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > maximum:
        raise ReconciliationError(f"{label} is too long")
    return cleaned


def _validate_collection_value(collection: str, updated: dict) -> dict:
    if collection == "biomarkers":
        updated["date"] = _partial_date_text(updated.get("date"), "Observation date")
        updated["date_precision"] = derive_date_precision(updated["date"])
        if updated.get("date_kind") not in {
            "collection",
            "result",
            "clinical_unspecified",
            "source_document",
            "unknown",
        }:
            raise ReconciliationError("Choose a valid biomarker date kind")
        if updated["date_precision"] == "unknown":
            updated["date_kind"] = "unknown"
        updated["source_document_date"] = _partial_date_text(
            updated.get("source_document_date"), "Source document date"
        )
        updated["source_document_date_precision"] = derive_date_precision(
            updated["source_document_date"]
        )
        updated["marker"] = _required_text(updated.get("marker"), "Biomarker name", maximum=120)
        value = updated.get("value")
        if value is None or isinstance(value, dict | list | bool):
            raise ReconciliationError("Biomarker value is required")
        if isinstance(value, str) and not value.strip():
            raise ReconciliationError("Biomarker value is required")
        if isinstance(value, float) and not math.isfinite(value):
            raise ReconciliationError("Biomarker value must be finite")
        if updated.get("flag") not in {None, "high", "low", "normal"}:
            raise ReconciliationError("Biomarker flag must be high, low, normal, or empty")
        updated["unit"] = _optional_text(updated.get("unit"), "Unit", maximum=80)
        updated["reference_range"] = _optional_text(
            updated.get("reference_range"), "Reference range", maximum=200
        )
        for field, label in (
            ("specimen", "Specimen"),
            ("assay", "Assay"),
            ("method", "Method"),
        ):
            updated[field] = _optional_text(updated.get(field), label, maximum=200)
    elif collection == "imaging":
        updated["date"] = _partial_date_text(updated.get("date"), "Study date")
        updated["date_precision"] = derive_date_precision(updated["date"])
        if updated.get("date_kind") not in {"study", "legacy_unknown", "unknown"}:
            raise ReconciliationError("Choose a valid imaging date kind")
        if updated["date_precision"] == "unknown":
            updated["date_kind"] = "unknown"
        updated["source_document_date"] = _partial_date_text(
            updated.get("source_document_date"), "Source document date"
        )
        updated["source_document_date_precision"] = derive_date_precision(
            updated["source_document_date"]
        )
        updated["modality"] = _optional_text(
            updated.get("modality"), "Imaging modality", maximum=200
        )
        updated["findings"] = _optional_text(
            updated.get("findings"), "Imaging findings", maximum=50_000
        )
        updated["impression"] = _optional_text(
            updated.get("impression"), "Imaging impression", maximum=50_000
        )
        if (
            not str(updated.get("findings") or "").strip()
            and not str(updated.get("impression") or "").strip()
        ):
            raise ReconciliationError("Imaging findings or impression is required")
        if updated.get("new_lesions") not in {None, True, False}:
            raise ReconciliationError("New lesions must be yes, no, or empty")
    elif collection == "symptoms":
        updated["date"] = _date_text(updated.get("date"))
        updated["symptom"] = _required_text(updated.get("symptom"), "Symptom", maximum=120)
        severity = updated.get("severity")
        if severity is not None and (
            not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5
        ):
            raise ReconciliationError("Symptom severity must be an integer from 1 to 5")
    elif collection == "appointments":
        updated["date"] = _date_text(updated.get("date"))
        updated["description"] = _required_text(
            updated.get("description"), "Appointment description", maximum=500
        )
        updated["type"] = _required_text(updated.get("type"), "Appointment type", maximum=80)
    elif collection == "documents":
        updated["date"] = _date_text(updated.get("date"))
        updated["type"] = _required_text(updated.get("type"), "Document type", maximum=80)
        if updated.get("summary") is not None and not isinstance(updated.get("summary"), str):
            raise ReconciliationError("Document summary must be text")
        findings = updated.get("key_findings")
        if not isinstance(findings, list) or not all(
            isinstance(item, str) and item.strip() for item in findings
        ):
            raise ReconciliationError("Key findings must be a list of non-empty text values")
    else:
        raise ReconciliationError("This record cannot be corrected here")
    return updated


def _set_scalar(profile: dict, path: list[str], value: Any) -> None:
    target = profile
    for part in path[:-1]:
        target = target.setdefault(part, {})
    target[path[-1]] = value


def _update_status(record: dict) -> None:
    states = {
        change.get("state")
        for change in record.get("changes", [])
        if change.get("operation") not in {"unchanged", "derived"}
    }
    if states and states <= {"undone", "removed"}:
        record["status"] = "undone"
    elif "removed" in states:
        record["status"] = "partially_removed"
    elif "corrected" in states:
        record["status"] = "corrected"
    else:
        record["status"] = "active"


def _append_history(change: dict, event: str, before: Any, after: Any) -> None:
    change.setdefault("history", []).append(
        {
            "event": event,
            "at": now_stamp(),
            "before": _clone(before),
            "after": _clone(after),
        }
    )


def _mark_summary_stale(profile: dict) -> None:
    profile["summary_stale"] = True
    summary = profile.get("executive_summary")
    if isinstance(summary, dict):
        summary["stale"] = True
        summary["import_correction_pending"] = True


_ALERT_SYSTEM_FIELDS = {
    "source_document_id",
    "source_job_id",
    "generation_profile_revision",
    "dependency_kind",
    "source_dependency_active",
    "source_invalidated_at",
    "inactive_reason",
}


def sync_alert_system_state(profile: dict, alert: dict) -> None:
    """Mirror system-owned dependency fields without masking caregiver mutations."""
    alert_id = alert.get("id")
    if not alert_id:
        return
    for record in profile.get("document_imports", []):
        change = next(
            (
                item
                for item in record.get("changes", [])
                if item.get("target", {}).get("collection") == "alerts"
                and item.get("target", {}).get("record_id") == alert_id
            ),
            None,
        )
        if not change or not isinstance(change.get("effective_value"), dict):
            continue
        effective = change["effective_value"]
        for field in _ALERT_SYSTEM_FIELDS:
            if field in alert:
                effective[field] = _clone(alert[field])
            else:
                effective.pop(field, None)


def _invalidate_source_dependencies(profile: dict, record: dict) -> None:
    """Retain dependent alerts/questions but stop presenting them as current."""
    timestamp = now_stamp()
    source_id = record.get("source_document_id")
    for alert in profile.get("alerts", []):
        if alert.get("source_document_id") != source_id:
            continue
        if alert.get("dependency_kind") != "source":
            continue
        if alert.get("source_dependency_active", True):
            alert["source_dependency_active"] = False
            alert["source_invalidated_at"] = timestamp
            alert["inactive_reason"] = "source_document_corrected_or_undone"
            sync_alert_system_state(profile, alert)
    for question in profile.get("appointment_questions", []):
        if question.get("source") != "ai" or question.get("stale"):
            continue
        question["stale"] = True
        question["stale_reason"] = "patient_record_changed_after_generation"
        question["stale_at"] = timestamp


def _invalidate_document_evidence(profile: dict, record: dict, change: dict) -> None:
    """Stop a corrected scalar/treatment from citing its original extracted span."""
    target = change.get("target") or {}
    if target.get("kind") == "scalar":
        field = {
            "ki67_percent": "ki67_update",
            "sstr_status": "sstr_status_update",
            "sstr_score": "sstr_score_update",
        }.get((target.get("path") or [""])[-1])
    elif target.get("kind") == "treatment":
        field = "treatment_changes"
    else:
        field = None
    if not field:
        return
    document = next(
        (
            item
            for item in profile.get("documents", [])
            if item.get("source_document_id") == record.get("source_document_id")
        ),
        None,
    )
    if document is None:
        return
    for evidence in document.get("evidence", []):
        if evidence.get("field") == field:
            evidence.update(
                {
                    "source_quote": None,
                    "evidence_status": "missing",
                    "evidence_start": None,
                    "evidence_end": None,
                }
            )
    document_change = next(
        (
            item
            for item in record.get("changes", [])
            if item.get("target", {}).get("collection") == "documents"
            and item.get("target", {}).get("record_id") == document.get("id")
        ),
        None,
    )
    if document_change and document_change.get("state") in {"active", "corrected"}:
        document_change["effective_value"] = _clone(document)


def _exclude_document_context(profile: dict, record: dict) -> None:
    """Keep corrected source history visible without feeding stale extraction prose."""
    document = next(
        (
            item
            for item in profile.get("documents", [])
            if item.get("source_document_id") == record.get("source_document_id")
        ),
        None,
    )
    if document is None:
        return
    document["excluded_from_clinical_context"] = True
    document["exclusion_reason"] = "caregiver_corrected_import"
    document_change = next(
        (
            item
            for item in record.get("changes", [])
            if item.get("target", {}).get("collection") == "documents"
            and item.get("target", {}).get("record_id") == document.get("id")
        ),
        None,
    )
    if document_change and document_change.get("state") in {"active", "corrected"}:
        document_change["effective_value"] = _clone(document)


def correct_change(
    profile: dict,
    job_id: str,
    change_id: str,
    *,
    receipt_revision: Any,
    target_token: str,
    replacement: Any,
) -> None:
    record = find_import(profile, job_id)
    change = _find_change(record, change_id)
    current = _require_preconditions(
        profile,
        record,
        change,
        receipt_revision=receipt_revision,
        target_token=target_token,
    )
    target = change.get("target") or {}
    kind = target.get("kind")
    if kind == "collection":
        allowed = set(change.get("editable_fields") or [])
        if not allowed or not isinstance(replacement, dict):
            raise ReconciliationError("Provide the editable fields to correct")
        unknown = set(replacement) - allowed
        if unknown:
            raise ReconciliationError(
                f"Fields cannot be corrected here: {', '.join(sorted(unknown))}"
            )
        if not replacement:
            raise ReconciliationError("No corrected values were provided")
        updated = _clone(current)
        updated.update(_clone(replacement))
        if (
            target.get("collection") == "imaging"
            and "date" in replacement
            and "date_kind" not in replacement
        ):
            updated["date_kind"] = "unknown"
        updated = _validate_collection_value(target["collection"], updated)
        if target.get("collection") == "biomarkers":
            if "flag" in replacement:
                updated["flag_authority"] = (
                    "caregiver_corrected" if updated.get("flag") is not None else "unknown"
                )
            else:
                updated["flag_authority"] = current.get(
                    "flag_authority",
                    "legacy_unknown" if current.get("flag") else "unknown",
                )
        if _semantic_value(updated) == _semantic_value(current):
            raise ReconciliationError("The corrected value is identical to the current value")
        updated["caregiver_corrected_at"] = now_stamp()
        updated["provenance_status"] = "caregiver_corrected"
        if target.get("collection") == "documents":
            for evidence in updated.get("evidence", []):
                evidence.update(
                    {
                        "source_quote": None,
                        "evidence_status": "missing",
                        "evidence_start": None,
                        "evidence_end": None,
                    }
                )
        else:
            updated.update(
                {
                    "source_quote": None,
                    "evidence_status": "missing",
                    "evidence_start": None,
                    "evidence_end": None,
                }
            )
        collection = target["collection"]
        index = next(
            index
            for index, item in enumerate(profile.get(collection, []))
            if item.get("id") == target.get("record_id")
        )
        profile[collection][index] = updated
    elif kind == "scalar":
        updated = _validate_scalar(target.get("path") or [], replacement)
        if updated == current:
            raise ReconciliationError("The corrected value is identical to the current value")
        _set_scalar(profile, target["path"], updated)
        _invalidate_document_evidence(profile, record, change)
    elif kind == "treatment":
        updated = str(replacement or "").strip()
        if not updated or len(updated) > 500:
            raise ReconciliationError(
                "Corrected treatment text is required (maximum 500 characters)"
            )
        if updated == current:
            raise ReconciliationError("The corrected value is identical to the current value")
        treatments = profile.get("patient", {}).get("current_treatments", [])
        if updated != current and updated in treatments:
            raise ReconciliationError("That treatment is already recorded")
        treatments[treatments.index(current)] = updated
        from .profile import invalidate_treatment_classification, sync_treatment_records

        invalidate_treatment_classification(profile)
        sync_treatment_records(profile)
        _invalidate_document_evidence(profile, record, change)
    else:
        raise ReconciliationError("This receipt entry cannot be corrected")
    _exclude_document_context(profile, record)
    _invalidate_source_dependencies(profile, record)
    _append_history(change, "corrected", current, updated)
    change["effective_value"] = _clone(updated)
    change["state"] = "corrected"
    record["receipt_revision"] = int(record.get("receipt_revision") or 0) + 1
    _update_status(record)
    _mark_summary_stale(profile)


def _remove_effect(profile: dict, change: dict, *, event: str) -> None:
    target = change.get("target") or {}
    kind = target.get("kind")
    current = _target_value(profile, change)
    before = _clone(current)
    if kind == "collection":
        collection = target.get("collection")
        if collection == "documents":
            current["excluded_from_clinical_context"] = True
            after = _clone(current)
        else:
            profile[collection] = [
                item
                for item in profile.get(collection, [])
                if item.get("id") != target.get("record_id")
            ]
            after = None
    elif kind == "scalar":
        after = _clone(change.get("before"))
        _set_scalar(profile, target.get("path") or [], after)
    elif kind == "treatment":
        treatments = profile.get("patient", {}).get("current_treatments", [])
        profile["patient"]["current_treatments"] = [item for item in treatments if item != current]
        from .profile import invalidate_treatment_classification, sync_treatment_records

        invalidate_treatment_classification(profile)
        sync_treatment_records(profile)
        after = None
    else:
        raise ReconciliationError("This receipt entry cannot be removed")
    _append_history(change, event, before, after)


def remove_change(
    profile: dict,
    job_id: str,
    change_id: str,
    *,
    receipt_revision: Any,
    target_token: str,
) -> None:
    record = find_import(profile, job_id)
    change = _find_change(record, change_id)
    if (
        change.get("category") == "alerts"
        and isinstance(change.get("effective_value"), dict)
        and change["effective_value"].get("dependency_kind") == "durable"
    ):
        raise ReconciliationError("Durable alerts must be resolved explicitly")
    _require_preconditions(
        profile,
        record,
        change,
        receipt_revision=receipt_revision,
        target_token=target_token,
    )
    _remove_effect(profile, change, event="removed")
    _exclude_document_context(profile, record)
    _invalidate_source_dependencies(profile, record)
    change["state"] = "removed"
    record["receipt_revision"] = int(record.get("receipt_revision") or 0) + 1
    _update_status(record)
    _mark_summary_stale(profile)


def undo_import(
    profile: dict,
    job_id: str,
    *,
    receipt_revision: Any,
    undo_token: str,
) -> None:
    record = find_import(profile, job_id)
    if int(receipt_revision or -1) != int(record.get("receipt_revision") or 0):
        raise ImportConflict("The receipt changed. Reload it before undoing this document.")
    current_receipt = public_receipt(profile, job_id)
    if not current_receipt.get("can_undo") or undo_token != current_receipt.get("undo_token"):
        raise ImportConflict("One or more affected patient values changed. Reload the receipt.")
    changes = [
        change
        for change in record.get("changes", [])
        if change.get("state") in {"active", "corrected"}
        and change.get("operation") not in {"unchanged", "derived"}
    ]
    for change in changes:
        if (
            change.get("category") == "alerts"
            and isinstance(change.get("effective_value"), dict)
            and change["effective_value"].get("dependency_kind") == "durable"
        ):
            current = _clone(_target_value(profile, change))
            _append_history(change, "undone", current, current)
            change["state"] = "unchanged"
            change["preserved_reason"] = "durable_alert_requires_resolution"
            continue
        _remove_effect(profile, change, event="undone")
        change["state"] = "undone"
    for document in profile.get("documents", []):
        if document.get("source_document_id") == record.get("source_document_id"):
            document["excluded_from_clinical_context"] = True
    _invalidate_source_dependencies(profile, record)
    record["receipt_revision"] = int(record.get("receipt_revision") or 0) + 1
    record["status"] = "undone"
    _mark_summary_stale(profile)
