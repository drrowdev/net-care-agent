"""Deterministic, provenance-bound imaging longitudinal projection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .provenance import resolve_source_artifact, validate_source_artifact
from .schema import derive_date_precision

MAX_IMAGING_ROWS = 2_000
MAX_UNIQUE_SOURCES = 200
MAX_AUTHORITY_BYTES = 4_000_000
MAX_SOURCE_TEXT_BYTES = 2_000_000
MAX_TOTAL_SOURCE_TEXT_BYTES = 50_000_000

_FIELD_LIMITS = {
    "id": 200,
    "date": 32,
    "source_document_date": 32,
    "modality": 200,
    "findings": 50_000,
    "impression": 50_000,
}
_DATE_KINDS = {"study", "legacy_unknown", "unknown"}
_EVIDENCE_STATUSES = {"verified", "missing", "invalid"}
_MIGRATION_FIELDS = {
    "id",
    "date_precision",
    "date_kind",
    "source_document_date",
    "source_document_date_precision",
}


class ImagingProjectionError(ValueError):
    """A bounded public-safe imaging projection failure."""

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
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging data cannot be projected safely.",
        ) from None


def _digest(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()[:length]}"


def _record_route_ref(row_id: str) -> str:
    return _digest("imref", {"id": row_id}, 64)


def imaging_identity_base(row: dict) -> str:
    """Return the deterministic authority base for a missing imaging row ID."""
    semantic = {key: value for key, value in sorted(row.items()) if key not in _MIGRATION_FIELDS}
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
    else:
        provenance = {"kind": "legacy", "added_at": row.get("added_at")}
    return _canonical({"provenance": provenance, "semantic": semantic})


def derive_imaging_record_id(
    row: dict,
    *,
    occurrence: int = 0,
    used_ids: set[str] | None = None,
) -> str:
    """Derive one stable row ID without claiming identity between exact duplicates."""
    base = imaging_identity_base(row)
    occupied = used_ids or set()
    salt = 0
    while True:
        digest = hashlib.sha256(f"{base}:{occurrence}:{salt}".encode()).hexdigest()[:32]
        candidate = f"fact_imaging_{digest}"
        if candidate not in occupied:
            return candidate
        salt += 1


def _bounded_text(row: dict, field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging data cannot be projected safely.",
        )
    if len(value) > _FIELD_LIMITS[field]:
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging data exceeds the supported projection limits.",
        )
    return value


def _semantic(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic(item)
            for key, item in sorted(value.items())
            if item is not None
            and not (
                key in {"date_precision", "source_document_date_precision"} and item == "unknown"
            )
            and not (key == "date_kind" and item == "unknown")
        }
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def _source_maps(
    profile: dict,
) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, list[dict]]]:
    sources: dict[str, dict] = {}
    for source in profile.get("source_documents", []):
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            continue
        if source_id in sources:
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
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
    for artifact_name in ("source", "text"):
        metadata = source.get(artifact_name)
        if (
            not isinstance(metadata, dict)
            or not isinstance(metadata.get("path"), str)
            or not isinstance(metadata.get("sha256"), str)
            or not isinstance(metadata.get("length"), int)
            or isinstance(metadata.get("length"), bool)
            or metadata["length"] < 0
        ):
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
    return source


def _validated_source_text(source: dict, cache: dict[str, str]) -> str:
    source_id = source.get("id")
    if source_id in cache:
        return cache[source_id]
    text_meta = source.get("text")
    if (
        not isinstance(text_meta, dict)
        or not isinstance(text_meta.get("sha256"), str)
        or not isinstance(text_meta.get("length"), int)
        or isinstance(text_meta.get("length"), bool)
        or text_meta["length"] < 0
    ):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
        )
    if text_meta["length"] > MAX_SOURCE_TEXT_BYTES:
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging source data exceeds the supported projection limits.",
        )
    try:
        path = resolve_source_artifact(source, "text")
        if path.stat().st_size > MAX_SOURCE_TEXT_BYTES:
            raise ImagingProjectionError(
                "imaging_projection_too_large",
                "Imaging source data exceeds the supported projection limits.",
            )
        content = path.read_bytes()
    except ImagingProjectionError:
        raise
    except (OSError, ValueError):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
        ) from None
    if not validate_source_artifact(source, "text", content):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
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
        if not isinstance(receipt.get("changes"), list):
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
        if receipt.get("status") == "undone":
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
        matching = []
        for change in receipt["changes"]:
            if not isinstance(change, dict):
                raise ImagingProjectionError(
                    "imaging_projection_invalid",
                    "Imaging source authority is inconsistent.",
                )
            target = change.get("target")
            if not isinstance(target, dict):
                raise ImagingProjectionError(
                    "imaging_projection_invalid",
                    "Imaging source authority is inconsistent.",
                )
            if target.get("collection") != "imaging" or target.get("record_id") != row["id"]:
                continue
            if change.get("state") in {"removed", "undone"}:
                raise ImagingProjectionError(
                    "imaging_projection_invalid",
                    "Imaging source authority is inconsistent.",
                )
            effective = change.get("effective_value")
            if not isinstance(effective, dict) or _semantic(effective) != _semantic(row):
                raise ImagingProjectionError(
                    "imaging_projection_invalid",
                    "Imaging source authority is inconsistent.",
                )
            matching.append(change)
        authority.append(
            {
                "id": receipt.get("id"),
                "job_id": receipt.get("job_id"),
                "source_document_id": receipt.get("source_document_id"),
                "status": receipt.get("status"),
                "applied_revision": receipt.get("applied_revision"),
                "receipt_revision": receipt.get("receipt_revision"),
                "changes": matching,
            }
        )
    return sorted(authority, key=_canonical)


def _row_projection(
    row: dict,
    sources: dict[str, dict],
    documents: dict[str, list[dict]],
    imports: dict[str, list[dict]],
    verified_text_cache: dict[str, str],
    revisions: dict[str, int],
) -> dict:
    for field in _FIELD_LIMITS:
        _bounded_text(row, field)
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id.strip():
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging identity is missing or invalid.",
        )

    raw_date = row.get("date")
    date_precision = derive_date_precision(raw_date)
    stored_precision = row.get("date_precision")
    if (
        stored_precision not in {"day", "month", "year", "unknown"}
        or stored_precision != date_precision
    ):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging date authority is inconsistent.",
        )
    date_kind = row.get("date_kind")
    if date_kind not in _DATE_KINDS or (date_precision == "unknown" and date_kind != "unknown"):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging date authority is inconsistent.",
        )
    source_document_date = row.get("source_document_date")
    source_document_date_precision = derive_date_precision(source_document_date)
    if row.get("source_document_date_precision") != source_document_date_precision:
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging date authority is inconsistent.",
        )

    new_lesions = row.get("new_lesions")
    if new_lesions is not None and (not isinstance(new_lesions, bool)):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging data cannot be projected safely.",
        )
    source_id = row.get("source_document_id")
    if source_id is not None and not isinstance(source_id, str):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
        )
    if isinstance(source_id, str) and (not source_id or len(source_id) > 200):
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging source data exceeds the supported projection limits.",
        )
    evidence_status = row.get("evidence_status") or "missing"
    if evidence_status not in _EVIDENCE_STATUSES:
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging source authority is inconsistent.",
        )

    source = sources.get(source_id) if source_id else None
    source_authority = _source_metadata_authority(source) if source is not None else None
    source_text = (
        _validated_source_text(source, verified_text_cache) if source is not None else None
    )
    corrected = row.get("provenance_status") == "caregiver_corrected"
    evidence_verified = False
    if evidence_status == "verified":
        if source is None or source_text is None:
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
        start = row.get("evidence_start")
        end = row.get("evidence_end")
        quote = row.get("source_quote")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or end <= start
            or not isinstance(quote, str)
            or start < 0
            or end > len(source_text)
            or source_text[start:end] != quote
        ):
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
        evidence_verified = not corrected

    document_authority = []
    for document in documents.get(source_id, []):
        excluded = document.get("excluded_from_clinical_context", False)
        if not isinstance(excluded, bool):
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging source authority is inconsistent.",
            )
        document_authority.append(
            {"id": document.get("id"), "excluded_from_clinical_context": excluded}
        )
    document_authority.sort(key=_canonical)
    row_authority = {
        "row": row,
        "source": source_authority,
        "documents": document_authority,
        "imports": _receipt_authority(row, source_id, imports),
        "revisions": revisions,
    }
    row_token = _digest("imrow", row_authority, 32)
    record_ref = _record_route_ref(row_id)

    if corrected:
        provenance_status = "caregiver_corrected_unverified"
        provenance_label = "Caregiver-corrected · unverified"
    elif evidence_status == "verified":
        provenance_status = "source_verified"
        provenance_label = "Exact source"
    elif source is not None:
        provenance_status = "source_unverified"
        provenance_label = (
            "Invalid source quote" if evidence_status == "invalid" else "No exact source"
        )
    elif source_id:
        provenance_status = "source_unavailable"
        provenance_label = "Source unavailable · unverified"
    else:
        provenance_status = "unverified"
        provenance_label = "Unverified"

    return {
        "public": {
            "id": row_id,
            "token": row_token,
            "date": {
                "value": raw_date,
                "precision": date_precision,
                "kind": date_kind,
                "source_document_date": source_document_date,
                "source_document_date_precision": source_document_date_precision,
            },
            "modality": row.get("modality"),
            "findings": row.get("findings"),
            "impression": row.get("impression"),
            "provenance": {
                "status": provenance_status,
                "label": provenance_label,
                "source_url": (
                    f"/api/patient/imaging-series/{record_ref}/source"
                    if source is not None
                    else None
                ),
                "evidence_url": (
                    f"/api/patient/imaging-series/{record_ref}/evidence"
                    if evidence_verified
                    else None
                ),
            },
        },
        "authority": row_authority,
    }


def _record_sort_key(record: dict) -> tuple:
    date = record["date"]
    if date["precision"] == "day":
        return (0, date["value"], record["id"])
    if date["precision"] in {"month", "year"}:
        return (1, date["value"], record["id"])
    return (2, str(date["value"] or ""), record["id"])


def _build_projection(profile: dict) -> tuple[dict, dict[str, dict], dict[str, str]]:
    for revision_name in ("profile_revision", "workflow_revision"):
        revision = profile.get(revision_name)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise ImagingProjectionError(
                "imaging_projection_invalid",
                "Imaging projection authority is inconsistent.",
            )
    rows = profile.get("imaging")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging data cannot be projected safely.",
        )
    if len(rows) > MAX_IMAGING_ROWS:
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging data exceeds the supported projection limits.",
        )
    ids = [row.get("id") for row in rows]
    if any(not isinstance(row_id, str) or not row_id.strip() for row_id in ids) or len(
        set(ids)
    ) != len(ids):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging identity is missing or inconsistent.",
        )

    sources, documents, imports = _source_maps(profile)
    referenced_sources = {
        row.get("source_document_id")
        for row in rows
        if isinstance(row.get("source_document_id"), str) and row.get("source_document_id")
    }
    if len(referenced_sources) > MAX_UNIQUE_SOURCES:
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging source data exceeds the supported projection limits.",
        )
    total_text_bytes = sum(
        source.get("text", {}).get("length", MAX_SOURCE_TEXT_BYTES + 1)
        for source_id in referenced_sources
        if (source := sources.get(source_id)) is not None
        and isinstance(source.get("text"), dict)
        and isinstance(source["text"].get("length"), int)
        and not isinstance(source["text"].get("length"), bool)
    )
    if total_text_bytes > MAX_TOTAL_SOURCE_TEXT_BYTES:
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging source data exceeds the supported projection limits.",
        )

    text_cache: dict[str, str] = {}
    revisions = {
        "profile_revision": profile["profile_revision"],
        "workflow_revision": profile["workflow_revision"],
    }
    projected = [
        _row_projection(row, sources, documents, imports, text_cache, revisions) for row in rows
    ]
    if sum(len(_canonical(item["authority"]).encode("utf-8")) for item in projected) > (
        MAX_AUTHORITY_BYTES
    ):
        raise ImagingProjectionError(
            "imaging_projection_too_large",
            "Imaging authority exceeds the supported projection limits.",
        )
    records = sorted((item["public"] for item in projected), key=_record_sort_key)
    manifest = {
        "profile_revision": profile.get("profile_revision"),
        "workflow_revision": profile.get("workflow_revision"),
        "rows": [{"id": record["id"], "token": record["token"]} for record in records],
    }
    projection = {
        "profile_revision": profile.get("profile_revision"),
        "workflow_revision": profile.get("workflow_revision"),
        "source_row_count": len(rows),
        "projection_token": _digest("improj", manifest, 32),
        "records": records,
    }
    rows_by_ref = {_record_route_ref(row["id"]): row for row in rows}
    if len(rows_by_ref) != len(rows):
        raise ImagingProjectionError(
            "imaging_projection_invalid",
            "Imaging identity is inconsistent.",
        )
    return projection, rows_by_ref, text_cache


def project_imaging_series(profile: dict) -> dict:
    """Project every bounded imaging row without mutating the profile."""
    projection, _, _ = _build_projection(profile)
    return projection


def imaging_record_text(profile: dict, record_ref: str, *, evidence_only: bool) -> str:
    """Resolve one opaque imaging row to validated source text or its exact span."""
    projection, rows, text_cache = _build_projection(profile)
    row = rows.get(record_ref)
    row_id = row.get("id") if row is not None else None
    public = next(
        (record for record in projection["records"] if record["id"] == row_id),
        None,
    )
    if public is None or row is None:
        raise ImagingProjectionError("imaging_record_not_found", "Imaging record not found.")
    source_id = row.get("source_document_id")
    text = text_cache.get(source_id)
    if text is None or public["provenance"]["source_url"] is None:
        raise ImagingProjectionError(
            "imaging_source_unavailable",
            "Imaging source is unavailable.",
        )
    if not evidence_only:
        return text
    if public["provenance"]["evidence_url"] is None:
        raise ImagingProjectionError(
            "imaging_evidence_unavailable",
            "Exact imaging evidence is unavailable.",
        )
    return text[row["evidence_start"] : row["evidence_end"]]
