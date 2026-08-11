"""Bounded projection for source-observed and caregiver-maintained treatments."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any

from .follow_through import semantic_token
from .provenance import resolve_source_artifact, validate_source_artifact
from .schema import derive_date_precision

MAX_SOURCE_FACTS = 2_000
MAX_LEGACY_TREATMENTS = 2_000
MAX_LEGACY_COMPONENTS = 4_000
MAX_CLASSIFIED_TREATMENTS = 2_000
MAX_TREATMENT_COURSES = 1_000
MAX_TREATMENT_DISCREPANCIES = 2_000
MAX_TREATMENT_ACTIONS = 500
MAX_AUTHORITY_BYTES = 6_000_000
MAX_SOURCE_TEXT_BYTES = 2_000_000
MAX_TOTAL_SOURCE_TEXT_BYTES = 50_000_000

TREATMENT_COURSE_STATUSES = {"current", "past", "planned"}
TREATMENT_DISCREPANCY_STATUSES = {"open", "resolved"}
TREATMENT_DISCREPANCY_CITATION_KINDS = {"source_vs_source", "source_vs_course"}
TREATMENT_DISCREPANCY_CATEGORIES = {
    "name_or_type",
    "status",
    "dose_or_schedule",
    "date",
    "source_wording",
    "other",
}
TREATMENT_CONFIRMATION_OUTCOMES = {
    "confirmed_as_recorded",
    "caregiver_record_corrected",
    "source_clarification_needed",
    "no_change_documented",
}
TREATMENT_CONFIRMATION_LABEL = "Caregiver-entered · attributed to clinician · unverified"
TREATMENT_SAFETY_GUIDANCE = (
    "NET/Care records what you enter but does not verify treatment details or advise "
    "starting, stopping, or changing treatment. Confirm treatment decisions with the "
    "treating team."
)

_COURSE_TEXT_LIMITS = {
    "id": 200,
    "treatment_text": 1_000,
    "treatment_type_text": 500,
    "dose_text": 500,
    "route_text": 500,
    "frequency_text": 500,
    "cycle_text": 500,
    "schedule_text": 1_000,
    "formulation_text": 500,
    "indication_text": 1_000,
    "notes": 10_000,
    "start_date": 32,
    "stop_date": 32,
    "planned_date": 32,
    "previous_course_id": 200,
    "created_at": 64,
    "updated_at": 64,
}
_DISCREPANCY_TEXT_LIMITS = {
    "id": 200,
    "comparison_text": 10_000,
    "course_id": 200,
    "source_fact_ref": 80,
    "comparison_source_fact_ref": 80,
    "recurs_from_id": 200,
    "caregiver_action_id": 200,
    "created_at": 64,
    "updated_at": 64,
    "resolved_at": 64,
}
_CONFIRMATION_TEXT_LIMITS = {
    "note": 10_000,
    "clinician_text": 500,
    "context_text": 2_000,
    "date": 32,
    "recorded_at": 64,
}
_DATE_PREFIXES = ("start", "stop", "planned")
_SOURCE_FACT_PUBLIC_FIELDS = {
    "ref",
    "token",
    "observed_text",
    "record_value",
    "operation",
    "review_state",
    "receipt_state",
    "provenance",
}
_COURSE_PUBLIC_FIELDS = {
    "id",
    "status",
    "treatment_text",
    "treatment_type_text",
    "dose_text",
    "route_text",
    "frequency_text",
    "cycle_text",
    "schedule_text",
    "formulation_text",
    "indication_text",
    "notes",
    "legacy_component_ids",
    "start_date",
    "start_date_precision",
    "start_date_kind",
    "stop_date",
    "stop_date_precision",
    "stop_date_kind",
    "planned_date",
    "planned_date_precision",
    "planned_date_kind",
    "previous_course_id",
    "created_at",
    "updated_at",
}
_FORBIDDEN_PUBLIC_KEYS = {
    "path",
    "source_document_id",
    "job_id",
    "receipt_id",
    "change_id",
    "evidence_start",
    "evidence_end",
    "source_quote",
    "raw_text",
    "offset",
    "offsets",
}
_LEGACY_DISCREPANCY_PUBLIC_FIELDS = {
    "id",
    "token",
    "status",
    "category",
    "comparison_text",
    "course_id",
    "source_fact",
    "course_snapshot",
    "recurs_from_id",
    "confirmations",
    "follow_up",
    "provenance",
    "created_at",
    "updated_at",
    "resolved_at",
}
_DISCREPANCY_PUBLIC_FIELDS = _LEGACY_DISCREPANCY_PUBLIC_FIELDS | {
    "citation_kind",
    "citation_authority",
    "eligibility",
    "citations",
    "comparison_source_fact",
}


class TreatmentProjectionError(ValueError):
    """A bounded public-safe treatment projection failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.public_message = message


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment data cannot be projected safely.",
        ) from None


def _digest(prefix: str, value: Any, length: int = 32) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()[:length]}"


def _token_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _token_value(item)
            for key, item in sorted(value.items())
            if key not in {"result_hash", "result_snapshot"}
        }
    if isinstance(value, list):
        return [_token_value(item) for item in value]
    return copy.deepcopy(value)


def new_treatment_course_id() -> str:
    return f"txc_{uuid.uuid4().hex}"


def new_treatment_discrepancy_id() -> str:
    return f"txd_{uuid.uuid4().hex}"


def treatment_course_provenance() -> dict[str, str]:
    return {"capture_method": "caregiver_entered", "source_verification": "unverified"}


def treatment_confirmation_provenance() -> dict[str, str]:
    return {
        "capture_method": "caregiver_entered",
        "attributed_to": "clinician",
        "source_verification": "unverified",
    }


def _validate_nested(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 75_000 or depth > 12:
            raise TreatmentProjectionError(
                "treatment_projection_too_large",
                "Treatment authority exceeds the supported projection limits.",
            )
        if isinstance(current, str):
            if len(current) > 100_000:
                raise TreatmentProjectionError(
                    "treatment_projection_too_large",
                    "Treatment authority exceeds the supported projection limits.",
                )
        elif isinstance(current, dict):
            if len(current) > 2_000:
                raise TreatmentProjectionError(
                    "treatment_projection_too_large",
                    "Treatment authority exceeds the supported projection limits.",
                )
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            if len(current) > 10_000:
                raise TreatmentProjectionError(
                    "treatment_projection_too_large",
                    "Treatment authority exceeds the supported projection limits.",
                )
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, float):
            _canonical(current)
        elif current is not None and not isinstance(current, bool | int):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment data cannot be projected safely.",
            )


def _bounded_text(row: dict, field: str, limits: dict[str, int]) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment authority is inconsistent.",
        )
    if len(value) > limits[field]:
        raise TreatmentProjectionError(
            "treatment_projection_too_large",
            "Treatment data exceeds the supported projection limits.",
        )
    return value


def _validate_public_value(
    value: Any,
    *,
    allowed_keys: frozenset[str] = frozenset(),
) -> None:
    _validate_nested(value)
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if any(key in _FORBIDDEN_PUBLIC_KEYS and key not in allowed_keys for key in current):
                raise TreatmentProjectionError(
                    "treatment_projection_invalid",
                    "Treatment snapshot authority is inconsistent.",
                )
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _validate_source_fact_snapshot(snapshot: dict, expected_ref: str) -> None:
    if set(snapshot) != _SOURCE_FACT_PUBLIC_FIELDS:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy source snapshot is inconsistent.",
        )
    provenance = snapshot.get("provenance")
    source_url = f"/api/patient/treatment-reconciliation/source-facts/{expected_ref}/source"
    evidence_url = f"/api/patient/treatment-reconciliation/source-facts/{expected_ref}/evidence"
    if (
        not isinstance(expected_ref, str)
        or not expected_ref
        or snapshot.get("ref") != expected_ref
        or not isinstance(snapshot.get("token"), str)
        or not snapshot["token"]
        or not isinstance(snapshot.get("observed_text"), str)
        or not isinstance(provenance, dict)
        or set(provenance) != {"status", "label", "source_url", "evidence_url"}
        or provenance.get("status") not in {"source_verified", "source_unverified"}
        or provenance.get("label") not in {"Exact source", "No exact source"}
        or provenance.get("source_url") != source_url
        or provenance.get("evidence_url") not in {evidence_url, None}
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy source snapshot is inconsistent.",
        )
    _validate_public_value(snapshot)


def _validate_course_snapshot(snapshot: dict, expected_id: str) -> None:
    for field in _COURSE_TEXT_LIMITS:
        _bounded_text(snapshot, field, _COURSE_TEXT_LIMITS)
    if (
        set(snapshot) != (_COURSE_PUBLIC_FIELDS | {"token", "provenance"})
        or snapshot.get("id") != expected_id
        or not snapshot["id"].startswith("txc_")
        or len(snapshot["id"]) != 36
        or not isinstance(snapshot.get("token"), str)
        or not snapshot["token"]
        or snapshot.get("provenance")
        != {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        }
        or snapshot.get("status") not in TREATMENT_COURSE_STATUSES
        or not isinstance(snapshot.get("treatment_text"), str)
        or not snapshot["treatment_text"]
        or not isinstance(snapshot.get("legacy_component_ids"), list)
        or any(not isinstance(item, str) for item in snapshot["legacy_component_ids"])
        or len(set(snapshot["legacy_component_ids"])) != len(snapshot["legacy_component_ids"])
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy course snapshot is inconsistent.",
        )
    for prefix in _DATE_PREFIXES:
        value = snapshot.get(f"{prefix}_date")
        precision = derive_date_precision(value)
        kind = snapshot.get(f"{prefix}_date_kind")
        if (
            snapshot.get(f"{prefix}_date_precision") != precision
            or kind not in {"caregiver_entered", "unknown"}
            or (value is None and kind != "unknown")
            or (value is not None and kind != "caregiver_entered")
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment discrepancy course snapshot is inconsistent.",
            )
    _validate_public_value(snapshot)


def _effective_citation_kind(discrepancy: dict) -> str | None:
    citation_kind = discrepancy.get("citation_kind")
    if citation_kind is None:
        if discrepancy.get("course_id") is not None:
            return "source_vs_course"
        if discrepancy.get("comparison_source_fact_ref") is None:
            return "legacy_incomplete"
    return citation_kind


def _source_fact_ref(receipt_id: str, change_id: str) -> str:
    return _digest("txref", {"receipt": receipt_id, "change": change_id}, 64)


def _source_maps(profile: dict) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    sources: dict[str, dict] = {}
    source_rows = profile.get("source_documents")
    document_rows = profile.get("documents")
    if (
        not isinstance(source_rows, list)
        or any(not isinstance(item, dict) for item in source_rows)
        or not isinstance(document_rows, list)
        or any(not isinstance(item, dict) for item in document_rows)
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    for source in source_rows:
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id or source_id in sources:
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment source authority is inconsistent.",
            )
        _validate_nested(source)
        sources[source_id] = source
    documents: dict[str, list[dict]] = {}
    for document in document_rows:
        _validate_nested(document)
        source_id = document.get("source_document_id")
        if isinstance(source_id, str):
            documents.setdefault(source_id, []).append(document)
    return sources, documents


def _validated_source_text(source: dict, cache: dict[str, str]) -> str:
    source_id = source.get("id")
    text_meta = source.get("text")
    if (
        not isinstance(source_id, str)
        or not isinstance(text_meta, dict)
        or not isinstance(text_meta.get("sha256"), str)
        or not isinstance(text_meta.get("length"), int)
        or isinstance(text_meta.get("length"), bool)
        or text_meta["length"] < 0
        or text_meta["length"] > MAX_SOURCE_TEXT_BYTES
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    if source_id in cache:
        return cache[source_id]
    try:
        content = resolve_source_artifact(source, "text").read_bytes()
    except (OSError, ValueError, FileNotFoundError):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        ) from None
    if not validate_source_artifact(source, "text", content):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        ) from None
    cache[source_id] = text
    return text


def _source_fact_projection(
    receipt: dict,
    change: dict,
    *,
    sources: dict[str, dict],
    documents: dict[str, list[dict]],
    text_cache: dict[str, str],
    revisions: dict[str, int],
) -> dict:
    receipt_id = receipt.get("id")
    change_id = change.get("id")
    source_id = change.get("source_document_id") or receipt.get("source_document_id")
    if (
        not isinstance(receipt_id, str)
        or not receipt_id
        or not isinstance(change_id, str)
        or not change_id
        or not isinstance(source_id, str)
        or not source_id
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source identity is inconsistent.",
        )
    source = sources.get(source_id)
    if source is None:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    source_text = _validated_source_text(source, text_cache)
    evidence_status = change.get("evidence_status") or "missing"
    if evidence_status not in {"verified", "missing", "invalid"}:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment evidence authority is inconsistent.",
        )
    evidence_text = None
    if evidence_status == "verified":
        start = change.get("evidence_start")
        end = change.get("evidence_end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
            or end > len(source_text)
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment evidence authority is inconsistent.",
            )
        evidence_text = source_text[start:end]
    ref = _source_fact_ref(receipt_id, change_id)
    authority = {
        "receipt": _token_value(receipt),
        "change": _token_value(change),
        "source": _token_value(source),
        "documents": _token_value(documents.get(source_id, [])),
        "validated_source_text": source_text,
        "revisions": revisions,
    }
    observed_text = evidence_text
    if observed_text is None and change.get("operation") == "added":
        observed_text = change.get("after")
    if not isinstance(observed_text, str):
        observed_text = change.get("label")
    if not isinstance(observed_text, str):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source wording is inconsistent.",
        )
    public = {
        "ref": ref,
        "token": _digest("txfact", authority),
        "observed_text": observed_text,
        "record_value": copy.deepcopy(change.get("effective_value")),
        "operation": change.get("operation"),
        "review_state": change.get("state"),
        "receipt_state": receipt.get("status"),
        "provenance": {
            "status": ("source_verified" if evidence_text is not None else "source_unverified"),
            "label": "Exact source" if evidence_text is not None else "No exact source",
            "source_url": (f"/api/patient/treatment-reconciliation/source-facts/{ref}/source"),
            "evidence_url": (
                f"/api/patient/treatment-reconciliation/source-facts/{ref}/evidence"
                if evidence_text is not None
                else None
            ),
        },
    }
    _validate_source_fact_snapshot(public, ref)
    return {
        "public": public,
        "authority": authority,
        "source_id": source_id,
        "source_text": source_text,
        "evidence_text": evidence_text,
    }


def _legacy_projection(profile: dict, revisions: dict[str, int]) -> list[dict]:
    patient = profile.get("patient")
    if not isinstance(patient, dict):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment authority is inconsistent.",
        )
    raw_rows = patient.get("current_treatments")
    components = patient.get("current_treatment_records")
    classified = profile.get("treatments_classified", [])
    if (
        not isinstance(raw_rows, list)
        or any(not isinstance(item, str) for item in raw_rows)
        or not isinstance(components, list)
        or any(not isinstance(item, dict) for item in components)
        or not isinstance(classified, list)
        or any(not isinstance(item, dict) for item in classified)
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment authority is inconsistent.",
        )
    component_ids = [row.get("id") for row in components]
    if any(not isinstance(item, str) or not item for item in component_ids) or len(
        set(component_ids)
    ) != len(component_ids):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment component identity is inconsistent.",
        )
    if any(
        not isinstance(row.get("source_order"), int)
        or isinstance(row.get("source_order"), bool)
        or row["source_order"] < 0
        or row["source_order"] >= len(raw_rows)
        or not isinstance(row.get("component_order"), int)
        or isinstance(row.get("component_order"), bool)
        or row["component_order"] < 0
        or not isinstance(row.get("text"), str)
        for row in components
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment component authority is inconsistent.",
        )
    if any(
        not isinstance(row.get("id"), str)
        or not row["id"]
        or not isinstance(row.get("text"), str)
        or (row.get("label") is not None and not isinstance(row.get("label"), str))
        or (row.get("category") is not None and not isinstance(row.get("category"), str))
        or (row.get("date") is not None and not isinstance(row.get("date"), str))
        or not isinstance(row.get("source_treatment_ids"), list)
        or any(not isinstance(item, str) for item in row.get("source_treatment_ids", []))
        for row in classified
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Generated treatment compatibility authority is inconsistent.",
        )
    result = []
    for source_order, raw_text in enumerate(raw_rows):
        mapped = [row for row in components if row.get("source_order") == source_order]
        mapped.sort(key=lambda row: row.get("component_order", -1))
        mapped_ids = [row["id"] for row in mapped]
        generated = [
            row
            for row in classified
            if isinstance(row.get("source_treatment_ids"), list)
            and any(component_id in mapped_ids for component_id in row["source_treatment_ids"])
        ]
        public_generated = [
            {
                key: copy.deepcopy(row.get(key))
                for key in ("id", "text", "label", "category", "date", "source_treatment_ids")
            }
            for row in generated
        ]
        if any(
            not isinstance(row.get("id"), str)
            or not row["id"]
            or not isinstance(row.get("text"), str)
            or (row.get("label") is not None and not isinstance(row.get("label"), str))
            or (row.get("category") is not None and not isinstance(row.get("category"), str))
            or (row.get("date") is not None and not isinstance(row.get("date"), str))
            or not isinstance(row.get("source_treatment_ids"), list)
            or any(not isinstance(item, str) for item in row.get("source_treatment_ids", []))
            for row in public_generated
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Generated treatment compatibility authority is inconsistent.",
            )
        authority = {
            "raw_text": raw_text,
            "source_order": source_order,
            "components": copy.deepcopy(mapped),
            "classification": copy.deepcopy(generated),
            "classification_revision": profile.get("treatments_classification_revision"),
            "classification_job_id": profile.get("treatments_classification_job_id"),
            "revisions": revisions,
        }
        public_row = {
            "id": _digest("txlegacy", {"order": source_order, "components": mapped_ids}, 24),
            "token": _digest("txlegacyrow", authority),
            "raw_text": raw_text,
            "source_order": source_order,
            "components": [
                {
                    "id": row["id"],
                    "text": row.get("text"),
                    "component_order": row.get("component_order"),
                }
                for row in mapped
            ],
            "generated_classification": public_generated,
            "authority_label": "Legacy/generated · not caregiver lifecycle authority",
        }
        _validate_public_value(public_row, allowed_keys=frozenset({"raw_text"}))
        result.append(public_row)
    return result


def _linked_action_public(action: dict) -> dict:
    return {
        "id": action.get("id"),
        "token": semantic_token(action),
        "text": action.get("text"),
        "status": action.get("status"),
        "owner": action.get("owner"),
        "due_date": action.get("due_date"),
    }


def _validate_course(course: dict, component_ids: set[str], courses_by_id: dict[str, dict]) -> None:
    for field in _COURSE_TEXT_LIMITS:
        _bounded_text(course, field, _COURSE_TEXT_LIMITS)
    if (
        not isinstance(course.get("id"), str)
        or not course["id"].startswith("txc_")
        or len(course["id"]) != 36
        or course.get("status") not in TREATMENT_COURSE_STATUSES
        or not isinstance(course.get("treatment_text"), str)
        or not course["treatment_text"]
        or course.get("provenance") != treatment_course_provenance()
        or not isinstance(course.get("history"), list)
        or any(not isinstance(event, dict) for event in course["history"])
        or not isinstance(course.get("legacy_component_ids"), list)
        or any(item not in component_ids for item in course["legacy_component_ids"])
        or len(set(course["legacy_component_ids"])) != len(course["legacy_component_ids"])
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment course authority is inconsistent.",
        )
    previous = course.get("previous_course_id")
    if previous is not None and (previous == course["id"] or previous not in courses_by_id):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment course lifecycle is inconsistent.",
        )
    for prefix in _DATE_PREFIXES:
        value = course.get(f"{prefix}_date")
        precision = derive_date_precision(value)
        kind = course.get(f"{prefix}_date_kind")
        if course.get(f"{prefix}_date_precision") != precision or kind not in {
            "caregiver_entered",
            "unknown",
        }:
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment course date authority is inconsistent.",
            )
        if (value is None and kind != "unknown") or (
            value is not None and kind != "caregiver_entered"
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment course date authority is inconsistent.",
            )


def _course_public(course: dict, revisions: dict[str, int]) -> dict:
    authority = {"course": _token_value(course), "revisions": revisions}
    result = {key: copy.deepcopy(course.get(key)) for key in _COURSE_PUBLIC_FIELDS}
    result["token"] = _digest("txcourse", authority)
    result["provenance"] = {
        "status": "caregiver_entered_unverified",
        "label": "Caregiver-entered · unverified",
    }
    return result


def _validate_confirmation(value: dict) -> None:
    for field in _CONFIRMATION_TEXT_LIMITS:
        _bounded_text(value, field, _CONFIRMATION_TEXT_LIMITS)
    precision = derive_date_precision(value.get("date"))
    if (
        value.get("outcome") not in TREATMENT_CONFIRMATION_OUTCOMES
        or not isinstance(value.get("note"), str)
        or not value["note"]
        or value.get("date_precision") != precision
        or value.get("date_kind")
        != ("caregiver_entered" if value.get("date") is not None else "unknown")
        or value.get("provenance") != treatment_confirmation_provenance()
        or not isinstance(value.get("recorded_at"), str)
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment confirmation authority is inconsistent.",
        )


def _discrepancy_public(
    discrepancy: dict,
    *,
    source_facts: dict[str, dict],
    courses: dict[str, dict],
    actions: dict[str, dict],
    revisions: dict[str, int],
) -> dict:
    for field in _DISCREPANCY_TEXT_LIMITS:
        _bounded_text(discrepancy, field, _DISCREPANCY_TEXT_LIMITS)
    source = source_facts.get(discrepancy.get("source_fact_ref"))
    comparison_source_ref = discrepancy.get("comparison_source_fact_ref")
    comparison_source = (
        source_facts.get(comparison_source_ref)
        if isinstance(comparison_source_ref, str) and comparison_source_ref
        else None
    )
    course = courses.get(discrepancy.get("course_id")) if discrepancy.get("course_id") else None
    action = (
        actions.get(discrepancy.get("caregiver_action_id"))
        if discrepancy.get("caregiver_action_id")
        else None
    )
    confirmations = discrepancy.get("confirmations")
    citation_kind = _effective_citation_kind(discrepancy)
    if (
        not isinstance(discrepancy.get("id"), str)
        or not discrepancy["id"].startswith("txd_")
        or len(discrepancy["id"]) != 36
        or discrepancy.get("status") not in TREATMENT_DISCREPANCY_STATUSES
        or discrepancy.get("category") not in TREATMENT_DISCREPANCY_CATEGORIES
        or not isinstance(discrepancy.get("comparison_text"), str)
        or not discrepancy["comparison_text"]
        or source is None
        or not isinstance(discrepancy.get("source_fact_snapshot"), dict)
        or (discrepancy.get("caregiver_action_id") is not None and action is None)
        or discrepancy.get("provenance") != treatment_course_provenance()
        or not isinstance(confirmations, list)
        or any(not isinstance(item, dict) for item in confirmations)
        or not isinstance(discrepancy.get("history"), list)
        or any(not isinstance(item, dict) for item in discrepancy["history"])
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy authority is inconsistent.",
        )
    for confirmation in confirmations:
        _validate_confirmation(confirmation)
    snapshot = discrepancy["source_fact_snapshot"]
    _validate_source_fact_snapshot(snapshot, discrepancy["source_fact_ref"])
    comparison_snapshot = discrepancy.get("comparison_source_fact_snapshot")
    course_snapshot = discrepancy.get("course_snapshot")
    if citation_kind == "source_vs_source":
        if (
            not isinstance(comparison_source_ref, str)
            or not comparison_source_ref
            or comparison_source_ref == discrepancy.get("source_fact_ref")
            or comparison_source is None
            or not isinstance(comparison_snapshot, dict)
            or discrepancy.get("course_id") is not None
            or course_snapshot is not None
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment discrepancy citation authority is inconsistent.",
            )
        _validate_source_fact_snapshot(comparison_snapshot, comparison_source_ref)
        authority_state = "complete"
        incomplete_reason = None
    elif citation_kind == "source_vs_course":
        if (
            not isinstance(discrepancy.get("course_id"), str)
            or not discrepancy["course_id"]
            or course is None
            or not isinstance(course_snapshot, dict)
            or comparison_source_ref is not None
            or comparison_snapshot is not None
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment discrepancy citation authority is inconsistent.",
            )
        _validate_course_snapshot(course_snapshot, discrepancy["course_id"])
        authority_state = "complete"
        incomplete_reason = None
    elif citation_kind == "legacy_incomplete":
        if (
            discrepancy.get("course_id") is not None
            or course_snapshot is not None
            or comparison_source_ref is not None
            or comparison_snapshot is not None
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment discrepancy legacy citation authority is inconsistent.",
            )
        authority_state = "legacy_incomplete"
        incomplete_reason = "missing_second_citation"
    else:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy citation authority is inconsistent.",
        )
    recurs_from_id = discrepancy.get("recurs_from_id")
    if recurs_from_id is not None and (not isinstance(recurs_from_id, str) or not recurs_from_id):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy recurrence authority is inconsistent.",
        )
    if (discrepancy["status"] == "open") != (discrepancy.get("resolved_at") is None):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy lifecycle is inconsistent.",
        )
    authority = {
        "discrepancy": _token_value(discrepancy),
        "current_source_fact_a": source["authority"],
        "current_source_fact_b": (
            comparison_source["authority"] if comparison_source is not None else None
        ),
        "current_course_b": _token_value(course),
        "linked_action": _token_value(action),
        "revisions": revisions,
    }
    complete = authority_state == "complete"
    return {
        "id": discrepancy["id"],
        "token": _digest("txdiscrepancy", authority),
        "status": discrepancy["status"],
        "category": discrepancy["category"],
        "comparison_text": discrepancy["comparison_text"],
        "citation_kind": citation_kind,
        "citation_authority": {
            "state": authority_state,
            "reason": incomplete_reason,
        },
        "eligibility": {
            "resolve": complete and discrepancy["status"] == "open",
            "reopen": complete and discrepancy["status"] == "resolved",
            "recur": complete and discrepancy["status"] == "resolved",
        },
        "citations": {
            "source_a": {
                "snapshot": copy.deepcopy(snapshot),
                "current": copy.deepcopy(source["public"]),
            },
            "source_b": (
                {
                    "snapshot": copy.deepcopy(comparison_snapshot),
                    "current": copy.deepcopy(comparison_source["public"]),
                }
                if comparison_source is not None
                else None
            ),
            "course_b": (
                {
                    "snapshot": copy.deepcopy(course_snapshot),
                    "current": _course_public(course, revisions),
                }
                if course is not None
                else None
            ),
        },
        "course_id": discrepancy.get("course_id"),
        "source_fact": copy.deepcopy(snapshot),
        "comparison_source_fact": copy.deepcopy(comparison_snapshot),
        "course_snapshot": copy.deepcopy(course_snapshot),
        "recurs_from_id": discrepancy.get("recurs_from_id"),
        "confirmations": [
            {
                "outcome": item.get("outcome"),
                "note": item.get("note"),
                "clinician_text": item.get("clinician_text"),
                "context_text": item.get("context_text"),
                "date": item.get("date"),
                "date_precision": item.get("date_precision"),
                "date_kind": item.get("date_kind"),
                "recorded_at": item.get("recorded_at"),
                "provenance_label": TREATMENT_CONFIRMATION_LABEL,
            }
            for item in confirmations
        ],
        "follow_up": _linked_action_public(action) if action is not None else None,
        "provenance": {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        },
        "created_at": discrepancy.get("created_at"),
        "updated_at": discrepancy.get("updated_at"),
        "resolved_at": discrepancy.get("resolved_at"),
    }


def _build_projection(
    profile: dict,
) -> tuple[dict, dict[str, dict], dict[str, str]]:
    for name in ("profile_revision", "workflow_revision"):
        value = profile.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment projection authority is inconsistent.",
            )
    courses_list = profile.get("treatment_courses")
    discrepancies_list = profile.get("treatment_discrepancies")
    actions_list = profile.get("caregiver_actions")
    receipts = profile.get("document_imports")
    for value in (courses_list, discrepancies_list, actions_list, receipts):
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment data cannot be projected safely.",
            )
    if any(not isinstance(receipt.get("changes"), list) for receipt in receipts):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    treatment_changes = [
        (receipt, change)
        for receipt in receipts
        for change in receipt.get("changes", [])
        if isinstance(change, dict) and change.get("category") == "treatments"
    ]
    patient = profile.get("patient")
    if not isinstance(patient, dict):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment authority is inconsistent.",
        )
    raw_rows = patient.get("current_treatments", [])
    if (
        len(treatment_changes) > MAX_SOURCE_FACTS
        or not isinstance(raw_rows, list)
        or len(raw_rows) > MAX_LEGACY_TREATMENTS
        or len(courses_list) > MAX_TREATMENT_COURSES
        or len(discrepancies_list) > MAX_TREATMENT_DISCREPANCIES
        or len(actions_list) > MAX_TREATMENT_ACTIONS
    ):
        raise TreatmentProjectionError(
            "treatment_projection_too_large",
            "Treatment data exceeds the supported projection limits.",
        )
    for rows, label in (
        (courses_list, "course"),
        (discrepancies_list, "discrepancy"),
        (actions_list, "follow-up"),
    ):
        ids = [item.get("id") for item in rows]
        if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                f"Treatment {label} identity is inconsistent.",
            )
    for item in (*courses_list, *discrepancies_list, *actions_list, *receipts):
        _validate_nested(item)
    revisions = {
        "profile_revision": profile["profile_revision"],
        "workflow_revision": profile["workflow_revision"],
    }
    sources, documents = _source_maps(profile)
    referenced_source_ids = {
        change.get("source_document_id") or receipt.get("source_document_id")
        for receipt, change in treatment_changes
    }
    if any(not isinstance(item, str) or not item for item in referenced_source_ids):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source authority is inconsistent.",
        )
    total_source_bytes = 0
    for source_id in referenced_source_ids:
        source = sources.get(source_id)
        text_meta = source.get("text") if isinstance(source, dict) else None
        length = text_meta.get("length") if isinstance(text_meta, dict) else None
        if (
            not isinstance(length, int)
            or isinstance(length, bool)
            or length < 0
            or length > MAX_SOURCE_TEXT_BYTES
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment source authority is inconsistent.",
            )
        total_source_bytes += length
    if total_source_bytes > MAX_TOTAL_SOURCE_TEXT_BYTES:
        raise TreatmentProjectionError(
            "treatment_projection_too_large",
            "Treatment source data exceeds the supported projection limits.",
        )
    text_cache: dict[str, str] = {}
    projected_source = [
        _source_fact_projection(
            receipt,
            change,
            sources=sources,
            documents=documents,
            text_cache=text_cache,
            revisions=revisions,
        )
        for receipt, change in treatment_changes
    ]
    source_facts = {item["public"]["ref"]: item for item in projected_source}
    if len(source_facts) != len(projected_source):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment source identity is inconsistent.",
        )
    components = patient.get("current_treatment_records")
    classified = profile.get("treatments_classified", [])
    if (
        not isinstance(components, list)
        or len(components) > MAX_LEGACY_COMPONENTS
        or not isinstance(classified, list)
        or len(classified) > MAX_CLASSIFIED_TREATMENTS
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Legacy treatment authority is inconsistent.",
        )
    component_ids = {
        item.get("id")
        for item in components
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    courses = {item["id"]: item for item in courses_list}
    for course in courses_list:
        _validate_course(course, component_ids, courses)
    for course in courses_list:
        seen = {course["id"]}
        previous_id = course.get("previous_course_id")
        while previous_id is not None:
            if previous_id in seen:
                raise TreatmentProjectionError(
                    "treatment_projection_invalid",
                    "Treatment course lifecycle is inconsistent.",
                )
            seen.add(previous_id)
            previous_id = courses[previous_id].get("previous_course_id")
    actions = {item["id"]: item for item in actions_list}
    public_courses = [_course_public(course, revisions) for course in courses_list]
    public_discrepancies = [
        _discrepancy_public(
            item,
            source_facts=source_facts,
            courses=courses,
            actions=actions,
            revisions=revisions,
        )
        for item in discrepancies_list
    ]
    discrepancy_ids = set(item["id"] for item in discrepancies_list)
    if any(
        item.get("recurs_from_id") is not None
        and (
            item.get("recurs_from_id") == item["id"]
            or item.get("recurs_from_id") not in discrepancy_ids
        )
        for item in discrepancies_list
    ):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment discrepancy recurrence authority is inconsistent.",
        )
    discrepancies_by_id = {item["id"]: item for item in discrepancies_list}
    for discrepancy in discrepancies_list:
        seen = {discrepancy["id"]}
        prior_id = discrepancy.get("recurs_from_id")
        while prior_id is not None:
            if prior_id in seen:
                raise TreatmentProjectionError(
                    "treatment_projection_invalid",
                    "Treatment discrepancy recurrence authority is inconsistent.",
                )
            seen.add(prior_id)
            prior_id = discrepancies_by_id[prior_id].get("recurs_from_id")
        prior_id = discrepancy.get("recurs_from_id")
        if prior_id is None:
            continue
        prior = discrepancies_by_id[prior_id]
        citation_fields = (
            "source_fact_ref",
            "source_fact_snapshot",
            "comparison_source_fact_ref",
            "comparison_source_fact_snapshot",
            "course_id",
            "course_snapshot",
        )
        if _effective_citation_kind(discrepancy) != _effective_citation_kind(prior) or any(
            _canonical(discrepancy.get(field)) != _canonical(prior.get(field))
            for field in citation_fields
        ):
            raise TreatmentProjectionError(
                "treatment_projection_invalid",
                "Treatment discrepancy recurrence authority is inconsistent.",
            )
    linked_discrepancy_actions = [
        item.get("caregiver_action_id")
        for item in discrepancies_list
        if isinstance(item.get("caregiver_action_id"), str)
    ]
    symptom_action_ids = {
        item.get("caregiver_action_id")
        for item in profile.get("symptom_episodes", [])
        if isinstance(item, dict) and isinstance(item.get("caregiver_action_id"), str)
    }
    if len(linked_discrepancy_actions) != len(set(linked_discrepancy_actions)):
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment follow-up authority is inconsistent.",
        )
    if set(linked_discrepancy_actions) & symptom_action_ids:
        raise TreatmentProjectionError(
            "treatment_projection_invalid",
            "Treatment follow-up authority is inconsistent.",
        )
    eligible_actions = [
        _linked_action_public(action)
        for action in actions_list
        if action.get("status") in {"open", "in_progress"}
        and action.get("id") not in linked_discrepancy_actions
        and action.get("id") not in symptom_action_ids
    ]
    legacy = _legacy_projection(profile, revisions)
    authority_bytes = (
        sum(len(_canonical(item["authority"]).encode("utf-8")) for item in projected_source)
        + sum(
            len(_canonical(item).encode("utf-8"))
            for item in (*courses_list, *discrepancies_list, *actions_list)
        )
        + len(
            _canonical(
                {
                    "raw": raw_rows,
                    "components": components,
                    "classified": classified,
                    "classification_revision": profile.get("treatments_classification_revision"),
                    "classification_job_id": profile.get("treatments_classification_job_id"),
                }
            ).encode("utf-8")
        )
    )
    if authority_bytes > MAX_AUTHORITY_BYTES:
        raise TreatmentProjectionError(
            "treatment_projection_too_large",
            "Treatment authority exceeds the supported projection limits.",
        )
    public_source = [item["public"] for item in projected_source]
    manifest = {
        **revisions,
        "source_facts": [{"ref": item["ref"], "token": item["token"]} for item in public_source],
        "legacy": [{"id": item["id"], "token": item["token"]} for item in legacy],
        "courses": [{"id": item["id"], "token": item["token"]} for item in public_courses],
        "discrepancies": [
            {"id": item["id"], "token": item["token"]} for item in public_discrepancies
        ],
        "eligible_actions": [
            {"id": item["id"], "token": item["token"]} for item in eligible_actions
        ],
        "safety_guidance": TREATMENT_SAFETY_GUIDANCE,
    }
    projection = {
        **revisions,
        "projection_token": _digest("txprojection", manifest),
        "source_fact_count": len(public_source),
        "legacy_treatment_count": len(legacy),
        "course_count": len(public_courses),
        "discrepancy_count": len(public_discrepancies),
        "source_facts": public_source,
        "legacy_treatments": legacy,
        "courses": public_courses,
        "discrepancies": public_discrepancies,
        "eligible_actions": eligible_actions,
        "safety_guidance": {
            "kind": "fixed_non_prescriptive",
            "text": TREATMENT_SAFETY_GUIDANCE,
        },
    }
    if len(_canonical(projection).encode("utf-8")) > MAX_AUTHORITY_BYTES:
        raise TreatmentProjectionError(
            "treatment_projection_too_large",
            "Treatment data exceeds the supported projection limits.",
        )
    return projection, source_facts, text_cache


def project_treatment_reconciliation(profile: dict) -> dict:
    """Project all treatment authorities without mutation or truncation."""
    projection, _, _ = _build_projection(profile)
    return projection


def _safe_public_source(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        _validate_source_fact_snapshot(value, value.get("ref"))
    except TreatmentProjectionError:
        return False
    return True


def _safe_public_course(value: object) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        return False
    try:
        _validate_course_snapshot(value, value["id"])
    except TreatmentProjectionError:
        return False
    return True


def _safe_public_confirmation(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "outcome",
            "note",
            "clinician_text",
            "context_text",
            "date",
            "date_precision",
            "date_kind",
            "recorded_at",
            "provenance_label",
        }
        and value.get("outcome") in TREATMENT_CONFIRMATION_OUTCOMES
        and isinstance(value.get("note"), str)
        and all(
            value.get(field) is None or isinstance(value.get(field), str)
            for field in ("clinician_text", "context_text", "date")
        )
        and value.get("date_precision") in {"day", "month", "year", "unknown"}
        and value.get("date_kind") in {"caregiver_entered", "unknown"}
        and isinstance(value.get("recorded_at"), str)
        and value.get("provenance_label") == TREATMENT_CONFIRMATION_LABEL
    )


def _safe_public_follow_up(value: object) -> bool:
    return value is None or (
        isinstance(value, dict)
        and set(value) == {"id", "token", "text", "status", "owner", "due_date"}
        and isinstance(value.get("id"), str)
        and isinstance(value.get("token"), str)
        and isinstance(value.get("text"), str)
        and value.get("status") in {"open", "in_progress", "completed", "cancelled"}
    )


def _safe_public_discrepancy(value: object, expected_id: str) -> bool:
    if not isinstance(value, dict):
        return False
    public_fields = set(value)
    if (
        public_fields != _LEGACY_DISCREPANCY_PUBLIC_FIELDS
        and public_fields != _DISCREPANCY_PUBLIC_FIELDS
    ):
        return False
    try:
        _validate_public_value(value)
    except TreatmentProjectionError:
        return False
    if (
        value.get("id") != expected_id
        or not isinstance(value.get("token"), str)
        or not value["token"]
        or value.get("status") not in TREATMENT_DISCREPANCY_STATUSES
        or value.get("category") not in TREATMENT_DISCREPANCY_CATEGORIES
        or not isinstance(value.get("comparison_text"), str)
        or not _safe_public_source(value.get("source_fact"))
        or not _safe_public_follow_up(value.get("follow_up"))
        or value.get("provenance")
        != {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        }
        or not isinstance(value.get("confirmations"), list)
        or any(not _safe_public_confirmation(item) for item in value["confirmations"])
        or not isinstance(value.get("created_at"), str)
        or not isinstance(value.get("updated_at"), str)
        or (value.get("resolved_at") is not None and not isinstance(value.get("resolved_at"), str))
        or (value["status"] == "open") != (value.get("resolved_at") is None)
    ):
        return False
    course_snapshot = value.get("course_snapshot")
    if course_snapshot is not None and not _safe_public_course(course_snapshot):
        return False
    if public_fields == _LEGACY_DISCREPANCY_PUBLIC_FIELDS:
        return True
    kind = value.get("citation_kind")
    authority = value.get("citation_authority")
    eligibility = value.get("eligibility")
    citations = value.get("citations")
    if (
        kind not in TREATMENT_DISCREPANCY_CITATION_KINDS | {"legacy_incomplete"}
        or not isinstance(authority, dict)
        or set(authority) != {"state", "reason"}
        or authority.get("state") not in {"complete", "legacy_incomplete"}
        or not isinstance(eligibility, dict)
        or set(eligibility) != {"resolve", "reopen", "recur"}
        or any(not isinstance(item, bool) for item in eligibility.values())
        or not isinstance(citations, dict)
        or set(citations) != {"source_a", "source_b", "course_b"}
    ):
        return False
    source_a = citations["source_a"]
    if (
        not isinstance(source_a, dict)
        or set(source_a) != {"snapshot", "current"}
        or source_a["snapshot"] != value["source_fact"]
        or not _safe_public_source(source_a["snapshot"])
        or not _safe_public_source(source_a["current"])
    ):
        return False
    source_b = citations["source_b"]
    course_b = citations["course_b"]
    if kind == "source_vs_source":
        return (
            authority == {"state": "complete", "reason": None}
            and eligibility
            == {
                "resolve": value["status"] == "open",
                "reopen": value["status"] == "resolved",
                "recur": value["status"] == "resolved",
            }
            and isinstance(source_b, dict)
            and set(source_b) == {"snapshot", "current"}
            and source_b["snapshot"] == value.get("comparison_source_fact")
            and _safe_public_source(source_b["snapshot"])
            and _safe_public_source(source_b["current"])
            and source_a["snapshot"]["ref"] == source_a["current"]["ref"]
            and source_b["snapshot"]["ref"] == source_b["current"]["ref"]
            and source_a["snapshot"]["ref"] != source_b["snapshot"]["ref"]
            and course_b is None
            and value.get("course_id") is None
            and course_snapshot is None
        )
    if kind == "source_vs_course":
        return (
            authority == {"state": "complete", "reason": None}
            and eligibility
            == {
                "resolve": value["status"] == "open",
                "reopen": value["status"] == "resolved",
                "recur": value["status"] == "resolved",
            }
            and source_a["snapshot"]["ref"] == source_a["current"]["ref"]
            and source_b is None
            and value.get("comparison_source_fact") is None
            and isinstance(course_b, dict)
            and set(course_b) == {"snapshot", "current"}
            and course_b["snapshot"] == course_snapshot
            and _safe_public_course(course_b["snapshot"])
            and _safe_public_course(course_b["current"])
            and course_b["snapshot"]["id"] == course_b["current"]["id"]
            and course_b["snapshot"]["id"] == value.get("course_id")
        )
    return (
        authority == {"state": "legacy_incomplete", "reason": "missing_second_citation"}
        and eligibility == {"resolve": False, "reopen": False, "recur": False}
        and source_b is None
        and course_b is None
        and value.get("comparison_source_fact") is None
        and value.get("course_id") is None
        and course_snapshot is None
    )


def treatment_replay_response_is_safe(
    snapshot: object,
    *,
    expected_id: str,
    discrepancy: bool,
) -> bool:
    """Validate immutable treatment replay output without consulting current authority."""
    if not isinstance(snapshot, dict):
        return False
    try:
        _validate_public_value(snapshot)
        if len(_canonical(snapshot).encode("utf-8")) > MAX_AUTHORITY_BYTES:
            return False
    except TreatmentProjectionError:
        return False
    if discrepancy:
        if set(snapshot) != {
            "discrepancy",
            "course",
            "follow_up",
            "workflow_revision",
            "profile_revision",
        } or not _safe_public_discrepancy(snapshot.get("discrepancy"), expected_id):
            return False
        public_discrepancy = snapshot["discrepancy"]
        course = snapshot.get("course")
        public_fields = set(public_discrepancy)
        expected_course_id = public_discrepancy.get("course_id")
        return (
            (course is None or _safe_public_course(course))
            and (
                (course is None and expected_course_id is None)
                or (isinstance(course, dict) and course.get("id") == expected_course_id)
            )
            and (
                public_fields != _DISCREPANCY_PUBLIC_FIELDS
                or public_discrepancy["citations"]["course_b"] is None
                or course == public_discrepancy["citations"]["course_b"]["current"]
            )
            and snapshot.get("follow_up") == public_discrepancy.get("follow_up")
        )
    return (
        set(snapshot) == {"course", "workflow_revision", "profile_revision"}
        and _safe_public_course(snapshot.get("course"))
        and snapshot["course"].get("id") == expected_id
    )


def treatment_source_fact_text(profile: dict, record_ref: str, *, evidence_only: bool) -> str:
    """Resolve one opaque source-fact reference to integrity-validated text."""
    _, source_facts, _ = _build_projection(profile)
    fact = source_facts.get(record_ref)
    if fact is None:
        raise TreatmentProjectionError(
            "treatment_source_fact_not_found",
            "Treatment source fact not found.",
        )
    if evidence_only:
        if fact["evidence_text"] is None:
            raise TreatmentProjectionError(
                "treatment_evidence_unavailable",
                "Exact treatment evidence is unavailable.",
            )
        return fact["evidence_text"]
    return fact["source_text"]
