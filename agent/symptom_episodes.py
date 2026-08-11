"""Durable symptom episodes and bounded observation/episode projection."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any

from .follow_through import semantic_token
from .provenance import resolve_source_artifact, validate_source_artifact
from .schema import derive_date_precision

MAX_SYMPTOM_OBSERVATIONS = 2_000
MAX_SYMPTOM_EPISODES = 1_000
MAX_SYMPTOM_ACTIONS = 500
MAX_UNIQUE_SOURCES = 200
MAX_AUTHORITY_BYTES = 4_000_000
MAX_SOURCE_TEXT_BYTES = 2_000_000
MAX_TOTAL_SOURCE_TEXT_BYTES = 50_000_000

SYMPTOM_EPISODE_STATUSES = {"current", "resolved"}
SYMPTOM_SEVERITY_LEVELS = {"mild", "moderate", "severe"}
SYMPTOM_REPORTED_SUBJECTS = {"patient", "caregiver", "unspecified"}
SYMPTOM_OBSERVATION_DATE_KINDS = {"clinical", "legacy_unknown", "unknown"}
SYMPTOM_EPISODE_DATE_KINDS = {"caregiver_entered", "unknown"}
SYMPTOM_SAFETY_GUIDANCE = (
    "NET/Care records what you enter but does not assess urgency or monitor symptoms. "
    "Contact the treating team about symptoms or concerns. If you think this may be a "
    "medical emergency, contact local emergency services."
)

_OBSERVATION_FIELD_LIMITS = {
    "id": 200,
    "date": 32,
    "source_document_date": 32,
    "symptom": 1_000,
    "note": 50_000,
    "related_treatment": 5_000,
}
_EPISODE_FIELD_LIMITS = {
    "id": 200,
    "symptom_text": 1_000,
    "severity_level": 32,
    "severity_detail": 500,
    "reported_subject": 32,
    "timing_text": 2_000,
    "frequency_text": 2_000,
    "triggers_text": 2_000,
    "notes": 10_000,
    "onset_date": 32,
    "resolved_date": 32,
    "caregiver_action_id": 200,
    "created_at": 64,
    "updated_at": 64,
    "resolved_at": 64,
}
_ACTION_FIELD_LIMITS = {
    "id": 200,
    "text": 1_000,
    "owner": 200,
    "due_date": 10,
    "visit_id": 200,
    "decision_id": 200,
    "alert_id": 200,
    "created_at": 64,
    "updated_at": 64,
    "completed_at": 64,
    "cancelled_at": 64,
}
_OBSERVATION_MIGRATION_FIELDS = {
    "id",
    "date_precision",
    "date_kind",
    "source_document_date",
    "source_document_date_precision",
}


class SymptomProjectionError(ValueError):
    """A bounded public-safe symptom projection failure."""

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
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom data cannot be projected safely.",
        ) from None


def _digest(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()[:length]}"


def _observation_route_ref(row_id: str) -> str:
    return _digest("symref", {"id": row_id}, 64)


def _public_observation_id(row_id: str) -> str:
    if (
        len(row_id) <= 200
        and row_id.isascii()
        and row_id[0].isalnum()
        and all(char.isalnum() or char in "._-" for char in row_id)
    ):
        return row_id
    return _observation_route_ref(row_id)


def symptom_observation_identity_base(row: dict) -> str:
    """Return the strongest deterministic identity authority for a legacy row."""
    semantic = {
        key: value for key, value in sorted(row.items()) if key not in _OBSERVATION_MIGRATION_FIELDS
    }
    source_id = row.get("source_document_id")
    start = row.get("evidence_start")
    end = row.get("evidence_end")
    if (
        isinstance(source_id, str)
        and source_id
        and isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
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
    elif row.get("source") or row.get("added_at"):
        provenance = {
            "kind": "recorded",
            "source": row.get("source"),
            "added_at": row.get("added_at"),
        }
    else:
        provenance = {"kind": "legacy"}
    return _canonical({"provenance": provenance, "semantic": semantic})


def derive_symptom_observation_id(
    row: dict,
    *,
    occurrence: int = 0,
    used_ids: set[str] | None = None,
) -> str:
    """Derive a stable ID without claiming equality between duplicate rows."""
    base = symptom_observation_identity_base(row)
    occupied = used_ids or set()
    salt = 0
    while True:
        digest = hashlib.sha256(f"{base}:{occurrence}:{salt}".encode()).hexdigest()[:32]
        candidate = f"fact_symptom_{digest}"
        if candidate not in occupied:
            return candidate
        salt += 1


def new_symptom_episode_id() -> str:
    return f"syme_{uuid.uuid4().hex}"


def symptom_episode_provenance() -> dict[str, str]:
    return {
        "capture_method": "caregiver_entered",
        "source_verification": "unverified",
    }


def _validate_nested_authority(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 50_000 or depth > 12:
            raise SymptomProjectionError(
                "symptom_projection_too_large",
                "Symptom authority exceeds the supported projection limits.",
            )
        if isinstance(current, str):
            if len(current) > 100_000:
                raise SymptomProjectionError(
                    "symptom_projection_too_large",
                    "Symptom authority exceeds the supported projection limits.",
                )
        elif isinstance(current, dict):
            if len(current) > 2_000:
                raise SymptomProjectionError(
                    "symptom_projection_too_large",
                    "Symptom authority exceeds the supported projection limits.",
                )
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            if len(current) > 10_000:
                raise SymptomProjectionError(
                    "symptom_projection_too_large",
                    "Symptom authority exceeds the supported projection limits.",
                )
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, float):
            _canonical(current)
        elif current is not None and not isinstance(current, bool | int):
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom data cannot be projected safely.",
            )


def _bounded_text(row: dict, field: str, limits: dict[str, int]) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom data cannot be projected safely.",
        )
    if len(value) > limits[field]:
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom data exceeds the supported projection limits.",
        )
    return value


def _semantic(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic(item)
            for key, item in sorted(value.items())
            if key not in {"result_hash", "result_snapshot"}
            if item is not None
            and not (
                key in {"date_precision", "source_document_date_precision"} and item == "unknown"
            )
            and not (key == "date_kind" and item == "unknown")
        }
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


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


def _source_maps(
    profile: dict,
) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, list[dict]]]:
    sources: dict[str, dict] = {}
    for source in profile.get("source_documents", []):
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom source authority is inconsistent.",
            )
        if source_id in sources:
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom source authority is inconsistent.",
            )
        sources[source_id] = source
    documents: dict[str, list[dict]] = {}
    for document in profile.get("documents", []):
        if isinstance(document, dict) and isinstance(document.get("source_document_id"), str):
            documents.setdefault(document["source_document_id"], []).append(document)
    imports: dict[str, list[dict]] = {}
    for receipt in profile.get("document_imports", []):
        if isinstance(receipt, dict) and isinstance(receipt.get("source_document_id"), str):
            imports.setdefault(receipt["source_document_id"], []).append(receipt)
    return sources, documents, imports


def _source_metadata_authority(source: dict) -> dict:
    text = source.get("text")
    if (
        not isinstance(source.get("id"), str)
        or not isinstance(text, dict)
        or not isinstance(text.get("sha256"), str)
        or not isinstance(text.get("length"), int)
        or isinstance(text.get("length"), bool)
        or text["length"] < 0
        or text["length"] > MAX_SOURCE_TEXT_BYTES
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        )
    _validate_nested_authority(source)
    return copy.deepcopy(source)


def _validated_source_text(source: dict, cache: dict[str, str]) -> str:
    source_id = source["id"]
    if source_id in cache:
        return cache[source_id]
    try:
        content = resolve_source_artifact(source, "text").read_bytes()
    except (OSError, ValueError, FileNotFoundError):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        ) from None
    if not validate_source_artifact(source, "text", content):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        ) from None
    cache[source_id] = text
    return text


def _receipt_authority(
    row: dict,
    source_id: str | None,
    imports: dict[str, list[dict]],
) -> list[dict]:
    if not source_id:
        return []
    authority = []
    for receipt in imports.get(source_id, []):
        if not isinstance(receipt.get("changes"), list) or receipt.get("status") == "undone":
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom source authority is inconsistent.",
            )
        matching = []
        for change in receipt["changes"]:
            if not isinstance(change, dict) or not isinstance(change.get("target"), dict):
                raise SymptomProjectionError(
                    "symptom_projection_invalid",
                    "Symptom source authority is inconsistent.",
                )
            target = change["target"]
            if target.get("collection") != "symptoms" or target.get("record_id") != row["id"]:
                continue
            if change.get("state") in {"removed", "undone"}:
                raise SymptomProjectionError(
                    "symptom_projection_invalid",
                    "Symptom source authority is inconsistent.",
                )
            effective = change.get("effective_value")
            if not isinstance(effective, dict) or _semantic(effective) != _semantic(row):
                raise SymptomProjectionError(
                    "symptom_projection_invalid",
                    "Symptom source authority is inconsistent.",
                )
            matching.append(change)
        _validate_nested_authority(receipt)
        authority.append(_token_value(receipt))
    return sorted(authority, key=_canonical)


def _observation_projection(
    row: dict,
    sources: dict[str, dict],
    documents: dict[str, list[dict]],
    imports: dict[str, list[dict]],
    text_cache: dict[str, str],
    revisions: dict[str, int],
) -> dict:
    for field in _OBSERVATION_FIELD_LIMITS:
        _bounded_text(row, field, _OBSERVATION_FIELD_LIMITS)
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id.strip():
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom observation identity is missing or invalid.",
        )
    raw_date = row.get("date")
    precision = derive_date_precision(raw_date)
    if row.get("date_precision") != precision:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom date authority is inconsistent.",
        )
    date_kind = row.get("date_kind")
    if date_kind not in SYMPTOM_OBSERVATION_DATE_KINDS or (
        precision == "unknown" and date_kind != "unknown"
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom date authority is inconsistent.",
        )
    source_document_date = row.get("source_document_date")
    source_document_precision = derive_date_precision(source_document_date)
    if row.get("source_document_date_precision") != source_document_precision:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom date authority is inconsistent.",
        )
    severity = row.get("severity")
    if severity is not None and (
        not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom severity authority is inconsistent.",
        )
    source_id = row.get("source_document_id")
    if source_id is not None and not isinstance(source_id, str):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        )
    if isinstance(source_id, str) and (not source_id or len(source_id) > 200):
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom source data exceeds the supported projection limits.",
        )
    evidence_status = row.get("evidence_status") or "missing"
    if evidence_status not in {"verified", "missing", "invalid"}:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom source authority is inconsistent.",
        )

    source = sources.get(source_id) if source_id else None
    source_authority = _source_metadata_authority(source) if source is not None else None
    source_text = _validated_source_text(source, text_cache) if source is not None else None
    corrected = row.get("provenance_status") == "caregiver_corrected"
    evidence_verified = False
    if evidence_status == "verified":
        start = row.get("evidence_start")
        end = row.get("evidence_end")
        quote = row.get("source_quote")
        if (
            source_text is None
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or end <= start
            or not isinstance(quote, str)
            or start < 0
            or end > len(source_text)
            or source_text[start:end] != quote
        ):
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom source authority is inconsistent.",
            )
        evidence_verified = not corrected

    document_authority = []
    for document in documents.get(source_id, []):
        _validate_nested_authority(document)
        excluded = document.get("excluded_from_clinical_context", False)
        if not isinstance(excluded, bool):
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom source authority is inconsistent.",
            )
        document_authority.append(_token_value(document))
    document_authority.sort(key=_canonical)
    authority = {
        "row": row,
        "source": source_authority,
        "documents": document_authority,
        "imports": _receipt_authority(row, source_id, imports),
        "revisions": revisions,
    }
    token = _digest("symobs", authority, 32)
    route_ref = _observation_route_ref(row_id)

    if corrected:
        provenance_status = "caregiver_corrected_unverified"
        provenance_label = "Caregiver-corrected · unverified"
    elif evidence_verified:
        provenance_status = "source_verified"
        provenance_label = "Exact source"
    elif source is not None:
        provenance_status = "source_unverified"
        provenance_label = (
            "Invalid source quote" if evidence_status == "invalid" else "No exact source"
        )
    elif row.get("source") == "manual":
        provenance_status = "legacy_caregiver_entered_unverified"
        provenance_label = "Legacy caregiver entry · unverified"
    elif row.get("source") == "ai":
        provenance_status = "legacy_model_extracted_unverified"
        provenance_label = "Legacy extracted observation · unverified"
    else:
        provenance_status = "legacy_unknown"
        provenance_label = "Legacy observation · unverified"

    return {
        "public": {
            "id": _public_observation_id(row_id),
            "token": token,
            "date": {
                "value": raw_date,
                "precision": precision,
                "kind": date_kind,
                "source_document_date": source_document_date,
                "source_document_date_precision": source_document_precision,
            },
            "symptom": row.get("symptom"),
            "severity": severity,
            "note": row.get("note"),
            "related_treatment": row.get("related_treatment"),
            "provenance": {
                "status": provenance_status,
                "label": provenance_label,
                "source_url": (
                    f"/api/patient/symptom-episodes/observations/{route_ref}/source"
                    if source is not None
                    else None
                ),
                "evidence_url": (
                    f"/api/patient/symptom-episodes/observations/{route_ref}/evidence"
                    if evidence_verified
                    else None
                ),
            },
        },
        "authority": authority,
    }


def _linked_action_public(action: dict) -> dict:
    return {
        "id": action.get("id"),
        "token": semantic_token(action),
        "text": action.get("text"),
        "status": action.get("status"),
        "owner": action.get("owner"),
        "due_date": action.get("due_date"),
    }


def _validate_action(action: dict) -> None:
    for field in _ACTION_FIELD_LIMITS:
        _bounded_text(action, field, _ACTION_FIELD_LIMITS)
    if (
        not isinstance(action.get("id"), str)
        or not action["id"]
        or not isinstance(action.get("text"), str)
        or not action["text"].strip()
        or action.get("status") not in {"open", "in_progress", "completed", "cancelled"}
        or not isinstance(action.get("origin_snapshot"), dict)
        or not isinstance(action.get("history"), list)
        or any(not isinstance(event, dict) for event in action["history"])
        or not isinstance(action.get("created_at"), str)
        or not isinstance(action.get("updated_at"), str)
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom follow-up authority is inconsistent.",
        )


def _episode_projection(
    episode: dict,
    actions: dict[str, dict],
    revisions: dict[str, int],
) -> dict:
    for field in _EPISODE_FIELD_LIMITS:
        _bounded_text(episode, field, _EPISODE_FIELD_LIMITS)
    episode_id = episode.get("id")
    if (
        not isinstance(episode_id, str)
        or len(episode_id) != 37
        or not episode_id.startswith("syme_")
        or any(char not in "0123456789abcdef" for char in episode_id[5:])
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode identity is missing or invalid.",
        )
    if episode.get("status") not in SYMPTOM_EPISODE_STATUSES:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode lifecycle is inconsistent.",
        )
    if not isinstance(episode.get("symptom_text"), str) or not episode["symptom_text"].strip():
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode content is inconsistent.",
        )
    severity_level = episode.get("severity_level")
    if severity_level is not None and severity_level not in SYMPTOM_SEVERITY_LEVELS:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode severity is inconsistent.",
        )
    if episode.get("reported_subject") not in SYMPTOM_REPORTED_SUBJECTS:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode provenance is inconsistent.",
        )
    for prefix in ("onset", "resolved"):
        value = episode.get(f"{prefix}_date")
        precision = derive_date_precision(value)
        if episode.get(f"{prefix}_date_precision") != precision:
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom episode date authority is inconsistent.",
            )
        kind = episode.get(f"{prefix}_date_kind")
        if kind not in SYMPTOM_EPISODE_DATE_KINDS or (precision == "unknown" and kind != "unknown"):
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom episode date authority is inconsistent.",
            )
    expected_provenance = symptom_episode_provenance()
    if episode.get("provenance") != expected_provenance:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode provenance is inconsistent.",
        )
    history = episode.get("history")
    if not isinstance(history, list) or any(not isinstance(event, dict) for event in history):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode audit is inconsistent.",
        )
    if episode["status"] == "current" and any(
        episode.get(field) is not None for field in ("resolved_date", "resolved_at")
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode lifecycle is inconsistent.",
        )
    if episode["status"] == "resolved" and not episode.get("resolved_at"):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom episode lifecycle is inconsistent.",
        )

    action_id = episode.get("caregiver_action_id")
    action = None
    if action_id is not None:
        action = actions.get(action_id)
        if action is None:
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom follow-up authority is inconsistent.",
            )
    authority = {
        "episode": _token_value(episode),
        "linked_action": _token_value(action),
        "revisions": revisions,
    }
    public_action = _linked_action_public(action) if action is not None else None
    return {
        "public": {
            "id": episode_id,
            "token": _digest("symeps", authority, 32),
            "status": episode.get("status"),
            "symptom_text": episode.get("symptom_text"),
            "severity": {
                "level": severity_level,
                "detail": episode.get("severity_detail"),
                "authority": "caregiver_entered_unverified",
            },
            "reported_subject": episode.get("reported_subject"),
            "timing_text": episode.get("timing_text"),
            "frequency_text": episode.get("frequency_text"),
            "triggers_text": episode.get("triggers_text"),
            "notes": episode.get("notes"),
            "onset": {
                "value": episode.get("onset_date"),
                "precision": episode.get("onset_date_precision"),
                "kind": episode.get("onset_date_kind"),
            },
            "resolution": (
                {
                    "value": episode.get("resolved_date"),
                    "precision": episode.get("resolved_date_precision"),
                    "kind": episode.get("resolved_date_kind"),
                    "recorded_at": episode.get("resolved_at"),
                }
                if episode.get("status") == "resolved"
                else None
            ),
            "provenance": {
                "status": "caregiver_entered_unverified",
                "label": "Caregiver-entered · unverified",
            },
            "follow_up": public_action,
            "created_at": episode.get("created_at"),
            "updated_at": episode.get("updated_at"),
        },
        "authority": authority,
    }


def _build_projection(
    profile: dict,
) -> tuple[dict, dict[str, dict], dict[str, str]]:
    for revision_name in ("profile_revision", "workflow_revision"):
        revision = profile.get(revision_name)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                "Symptom projection authority is inconsistent.",
            )
    observations = profile.get("symptoms")
    episodes = profile.get("symptom_episodes")
    actions_list = profile.get("caregiver_actions")
    treatment_discrepancies = profile.get("treatment_discrepancies", [])
    source_documents = profile.get("source_documents")
    documents_list = profile.get("documents")
    imports_list = profile.get("document_imports")
    if (
        not isinstance(observations, list)
        or any(not isinstance(row, dict) for row in observations)
        or not isinstance(episodes, list)
        or any(not isinstance(row, dict) for row in episodes)
        or not isinstance(actions_list, list)
        or any(not isinstance(row, dict) for row in actions_list)
        or not isinstance(treatment_discrepancies, list)
        or any(not isinstance(row, dict) for row in treatment_discrepancies)
        or not isinstance(source_documents, list)
        or any(not isinstance(row, dict) for row in source_documents)
        or not isinstance(documents_list, list)
        or any(not isinstance(row, dict) for row in documents_list)
        or not isinstance(imports_list, list)
        or any(not isinstance(row, dict) for row in imports_list)
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom data cannot be projected safely.",
        )
    if (
        len(observations) > MAX_SYMPTOM_OBSERVATIONS
        or len(episodes) > MAX_SYMPTOM_EPISODES
        or len(actions_list) > MAX_SYMPTOM_ACTIONS
    ):
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom data exceeds the supported projection limits.",
        )
    for rows, label in ((observations, "observation"), (episodes, "episode")):
        ids = [row.get("id") for row in rows]
        if any(not isinstance(row_id, str) or not row_id.strip() for row_id in ids) or len(
            set(ids)
        ) != len(ids):
            raise SymptomProjectionError(
                "symptom_projection_invalid",
                f"Symptom {label} identity is missing or inconsistent.",
            )
    action_ids = [action.get("id") for action in actions_list]
    if any(
        not isinstance(action_id, str) or not action_id.strip() for action_id in action_ids
    ) or len(set(action_ids)) != len(action_ids):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom follow-up authority is inconsistent.",
        )
    actions = {action["id"]: action for action in actions_list}
    for value in (*observations, *episodes, *actions_list):
        _validate_nested_authority(value)
    for action in actions_list:
        _validate_action(action)

    sources, documents, imports = _source_maps(profile)
    referenced_sources = {
        row.get("source_document_id")
        for row in observations
        if isinstance(row.get("source_document_id"), str) and row.get("source_document_id")
    }
    if len(referenced_sources) > MAX_UNIQUE_SOURCES:
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom source data exceeds the supported projection limits.",
        )
    total_source_bytes = sum(
        source.get("text", {}).get("length", MAX_SOURCE_TEXT_BYTES + 1)
        for source_id in referenced_sources
        if (source := sources.get(source_id)) is not None
        and isinstance(source.get("text"), dict)
        and isinstance(source["text"].get("length"), int)
        and not isinstance(source["text"].get("length"), bool)
    )
    if total_source_bytes > MAX_TOTAL_SOURCE_TEXT_BYTES:
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom source data exceeds the supported projection limits.",
        )

    revisions = {
        "profile_revision": profile["profile_revision"],
        "workflow_revision": profile["workflow_revision"],
    }
    text_cache: dict[str, str] = {}
    projected_observations = [
        _observation_projection(row, sources, documents, imports, text_cache, revisions)
        for row in observations
    ]
    projected_episodes = [_episode_projection(episode, actions, revisions) for episode in episodes]
    authority_items = projected_observations + projected_episodes
    authority_bytes = sum(
        len(_canonical(item["authority"]).encode("utf-8")) for item in authority_items
    ) + sum(len(_canonical(_token_value(action)).encode("utf-8")) for action in actions_list)
    if authority_bytes > MAX_AUTHORITY_BYTES:
        raise SymptomProjectionError(
            "symptom_projection_too_large",
            "Symptom authority exceeds the supported projection limits.",
        )

    from .follow_through import action_owner_refs

    linked_action_ids = {
        episode.get("caregiver_action_id")
        for episode in episodes
        if isinstance(episode.get("caregiver_action_id"), str)
    }
    if sum(1 for episode in episodes if isinstance(episode.get("caregiver_action_id"), str)) != len(
        linked_action_ids
    ):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom follow-up authority is inconsistent.",
        )
    treatment_action_ids = {
        discrepancy.get("caregiver_action_id")
        for discrepancy in treatment_discrepancies
        if isinstance(discrepancy.get("caregiver_action_id"), str)
    }
    if linked_action_ids & treatment_action_ids:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom follow-up authority is inconsistent.",
        )
    research_action_ids = {
        consideration.get("caregiver_action_id")
        for consideration in profile.get("research_considerations", [])
        if isinstance(consideration, dict)
        and isinstance(consideration.get("caregiver_action_id"), str)
    }
    if linked_action_ids & research_action_ids:
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom follow-up authority is inconsistent.",
        )
    eligible_actions = [
        _linked_action_public(action)
        for action in actions_list
        if action.get("status") in {"open", "in_progress"}
        and not action_owner_refs(profile, action.get("id"))
    ]
    public_observations = [item["public"] for item in projected_observations]
    public_episodes = [item["public"] for item in projected_episodes]
    manifest = {
        **revisions,
        "observations": [
            {"id": observation["id"], "token": observation["token"]}
            for observation in public_observations
        ],
        "episodes": [
            {"id": episode["id"], "token": episode["token"]} for episode in public_episodes
        ],
        "eligible_actions": [
            {"id": action["id"], "token": action["token"]} for action in eligible_actions
        ],
        "safety_guidance": SYMPTOM_SAFETY_GUIDANCE,
    }
    projection = {
        **revisions,
        "projection_token": _digest("symproj", manifest, 32),
        "observation_count": len(public_observations),
        "episode_count": len(public_episodes),
        "observations": public_observations,
        "episodes": public_episodes,
        "eligible_actions": eligible_actions,
        "safety_guidance": {
            "kind": "fixed_non_diagnostic",
            "text": SYMPTOM_SAFETY_GUIDANCE,
        },
    }
    observations_by_ref = {_observation_route_ref(row["id"]): row for row in observations}
    if len(observations_by_ref) != len(observations):
        raise SymptomProjectionError(
            "symptom_projection_invalid",
            "Symptom observation identity is inconsistent.",
        )
    return projection, observations_by_ref, text_cache


def project_symptom_episodes(profile: dict) -> dict:
    """Project all bounded observations and caregiver episodes without mutation."""
    projection, _, _ = _build_projection(profile)
    return projection


def symptom_observation_text(profile: dict, record_ref: str, *, evidence_only: bool) -> str:
    """Resolve one opaque observation reference to validated source text."""
    projection, observations, text_cache = _build_projection(profile)
    row = observations.get(record_ref)
    row_id = row.get("id") if row is not None else None
    public = (
        next(
            (
                record
                for record in projection["observations"]
                if record["id"] == _public_observation_id(row_id)
            ),
            None,
        )
        if isinstance(row_id, str)
        else None
    )
    if public is None or row is None:
        raise SymptomProjectionError(
            "symptom_observation_not_found",
            "Symptom observation not found.",
        )
    source_id = row.get("source_document_id")
    text = text_cache.get(source_id)
    if text is None or public["provenance"]["source_url"] is None:
        raise SymptomProjectionError(
            "symptom_source_unavailable",
            "Symptom source is unavailable.",
        )
    if not evidence_only:
        return text
    if public["provenance"]["evidence_url"] is None:
        raise SymptomProjectionError(
            "symptom_evidence_unavailable",
            "Exact symptom evidence is unavailable.",
        )
    return text[row["evidence_start"] : row["evidence_end"]]
