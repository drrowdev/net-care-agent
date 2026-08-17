"""Deterministic, provenance-bound biomarker longitudinal projection."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

from .provenance import resolve_source_artifact, validate_source_artifact
from .schema import derive_date_precision

MAX_BIOMARKER_ROWS = 2_000
MAX_UNIQUE_SOURCES = 200
MAX_AUTHORITY_BYTES = 4_000_000
MAX_SOURCE_TEXT_BYTES = 2_000_000

_FIELD_LIMITS = {
    "id": 200,
    "marker": 120,
    "date": 32,
    "source_document_date": 32,
    "unit": 80,
    "reference_range": 200,
    "specimen": 200,
    "assay": 200,
    "method": 200,
}
_VALUE_TEXT_LIMIT = 400
_DATE_KINDS = {
    "collection",
    "result",
    "clinical_unspecified",
    "source_document",
    "unknown",
}
_EVIDENCE_STATUSES = {"verified", "missing", "invalid"}
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_NUMBER_RE = re.compile(rf"^({_NUMBER})$")
_QUALIFIED_RE = re.compile(rf"^(<=|>=|<|>)\s*({_NUMBER})$")
_RANGE_RE = re.compile(rf"^({_NUMBER})\s*(?:-|–|—|to)\s*({_NUMBER})$", re.IGNORECASE)
_REFERENCE_BOUND_RE = re.compile(rf"^(<=|>=|<|>)\s*({_NUMBER})$")


class BiomarkerProjectionError(ValueError):
    """A bounded public-safe projection failure."""

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
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        ) from None


def _digest(prefix: str, value: Any, length: int = 24) -> str:
    encoded = _canonical(value).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:length]}"


def _normalized_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _normalized_unit(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _marker_key(value: str) -> str:
    normalized = _normalized_text(value)
    alias_key = re.sub(r"[\s_-]+", " ", normalized).strip()
    aliases = {
        "cga": ("chromogranin-a", "Chromogranin A"),
        "s cga": ("chromogranin-a", "Chromogranin A"),
        "p cga": ("chromogranin-a", "Chromogranin A"),
        "chromogranin a": ("chromogranin-a", "Chromogranin A"),
        "nse": ("nse", "NSE"),
        "neuron specific enolase": ("nse", "NSE"),
        "5 hiaa": ("5-hiaa", "5-HIAA"),
        "5 hydroxyindoleacetic acid": ("5-hiaa", "5-HIAA"),
    }
    family = aliases.get(alias_key)
    if family:
        return f"alias:{family[0]}"
    return f"exact:{normalized}"


def _marker_display(marker_key: str, observed: list[str]) -> str:
    fixed = {
        "alias:chromogranin-a": "Chromogranin A",
        "alias:nse": "NSE",
        "alias:5-hiaa": "5-HIAA",
    }
    if marker_key in fixed:
        return fixed[marker_key]
    return (
        min(observed, key=lambda item: (_normalized_text(item), item))
        if observed
        else "Unclassified"
    )


def _decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _numeric_output(number: Decimal) -> int | float:
    if number == number.to_integral_value():
        integer = int(number)
        if -(2**53) + 1 <= integer <= (2**53) - 1:
            return integer
    result = float(number)
    if not math.isfinite(result):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    return result


def _classify_value(value: Any) -> tuple[dict, Decimal | None]:
    if value is None:
        return (
            {
                "raw": None,
                "display": "",
                "kind": "missing",
                "qualifier": None,
                "numeric_value": None,
            },
            None,
        )
    if isinstance(value, bool) or isinstance(value, dict | list):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    if isinstance(value, int | float):
        if not math.isfinite(value):
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker data cannot be projected safely.",
            )
        number = Decimal(str(value))
        return (
            {
                "raw": value,
                "display": str(value),
                "kind": "numeric",
                "qualifier": None,
                "numeric_value": _numeric_output(number),
            },
            number,
        )
    if not isinstance(value, str) or len(value) > _VALUE_TEXT_LIMIT:
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker data exceeds the supported projection limits.",
        )
    stripped = value.strip()
    numeric = _NUMBER_RE.fullmatch(stripped)
    if numeric:
        number = _decimal(numeric.group(1))
        if number is None:
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker data cannot be projected safely.",
            )
        return (
            {
                "raw": value,
                "display": value,
                "kind": "numeric",
                "qualifier": None,
                "numeric_value": _numeric_output(number),
            },
            number,
        )
    qualified = _QUALIFIED_RE.fullmatch(stripped)
    if qualified:
        return (
            {
                "raw": value,
                "display": value,
                "kind": "qualified_numeric",
                "qualifier": qualified.group(1),
                "numeric_value": None,
            },
            None,
        )
    if _RANGE_RE.fullmatch(stripped):
        kind = "range"
        qualifier = "range"
    elif stripped.casefold() in {"positive", "negative"}:
        kind = "categorical"
        qualifier = stripped.casefold()
    else:
        kind = "text"
        qualifier = None
    return (
        {
            "raw": value,
            "display": value,
            "kind": kind,
            "qualifier": qualifier,
            "numeric_value": None,
        },
        None,
    )


def _normalized_decimal(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _parse_reference_range(value: object) -> tuple[dict | None, tuple | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    stripped = unicodedata.normalize("NFKC", value).strip()
    closed = _RANGE_RE.fullmatch(stripped)
    if closed:
        lower = _decimal(closed.group(1))
        upper = _decimal(closed.group(2))
        if lower is None or upper is None or lower > upper:
            return None, None
        public = {
            "kind": "closed",
            "lower": _normalized_decimal(lower),
            "upper": _normalized_decimal(upper),
            "lower_inclusive": True,
            "upper_inclusive": True,
        }
        return public, ("closed", lower, upper, True, True)
    bound = _REFERENCE_BOUND_RE.fullmatch(stripped)
    if not bound:
        return None, None
    number = _decimal(bound.group(2))
    if number is None:
        return None, None
    operator = bound.group(1)
    kind = "upper" if operator.startswith("<") else "lower"
    public = {
        "kind": kind,
        "bound": _normalized_decimal(number),
        "inclusive": "=" in operator,
    }
    return public, (kind, number, "=" in operator)


def _range_comparison(number: Decimal | None, parsed: tuple | None) -> str | None:
    if number is None or parsed is None:
        return None
    if parsed[0] == "closed":
        _, lower, upper, lower_inclusive, upper_inclusive = parsed
        if number < lower or (number == lower and not lower_inclusive):
            return "below"
        if number > upper or (number == upper and not upper_inclusive):
            return "above"
        return "within"
    kind, bound, inclusive = parsed
    if kind == "upper":
        within = number < bound or (inclusive and number == bound)
        return "within" if within else "above"
    within = number > bound or (inclusive and number == bound)
    return "within" if within else "below"


def _bounded_text(row: dict, field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    if len(value) > _FIELD_LIMITS[field]:
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker data exceeds the supported projection limits.",
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
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
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
    def artifact(name: str) -> dict:
        metadata = source.get(name)
        if (
            not isinstance(metadata, dict)
            or not isinstance(metadata.get("sha256"), str)
            or not isinstance(metadata.get("length"), int)
            or isinstance(metadata.get("length"), bool)
            or metadata["length"] < 0
        ):
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        return {
            "sha256": metadata["sha256"],
            "length": metadata["length"],
        }

    return {
        "id": source.get("id"),
        "ingested_at": source.get("ingested_at"),
        "filename": source.get("filename"),
        "media_type": source.get("media_type"),
        "feed_job_id": source.get("feed_job_id"),
        "source": artifact("source"),
        "text": artifact("text"),
    }


def _validated_source_text(source: dict, cache: dict[str, str]) -> str:
    source_id = source.get("id")
    if source_id in cache:
        return cache[source_id]
    text_meta = source.get("text")
    if (
        not isinstance(text_meta, dict)
        or not isinstance(text_meta.get("sha256"), str)
        or not isinstance(text_meta.get("length"), int)
        or text_meta["length"] < 0
        or text_meta["length"] > MAX_SOURCE_TEXT_BYTES
    ):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        )
    try:
        path = resolve_source_artifact(source, "text")
        if path.stat().st_size > MAX_SOURCE_TEXT_BYTES:
            raise BiomarkerProjectionError(
                "biomarker_projection_too_large",
                "Biomarker source data exceeds the supported projection limits.",
            )
        content = path.read_bytes()
    except BiomarkerProjectionError:
        raise
    except (OSError, ValueError):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        ) from None
    if not validate_source_artifact(source, "text", content):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        ) from None
    cache[source_id] = text
    return text


def _receipt_authority(
    row: dict,
    source_id: str | None,
    imports: dict[str, list[dict]],
) -> list[dict]:
    authority: list[dict] = []
    if not source_id:
        return authority
    for receipt in imports.get(source_id, []):
        if not isinstance(receipt.get("changes"), list):
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        if receipt.get("status") == "undone":
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        changes = []
        for change in receipt.get("changes") or []:
            if not isinstance(change, dict):
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker source authority is inconsistent.",
                )
            target = change.get("target") or {}
            if not isinstance(target, dict):
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker source authority is inconsistent.",
                )
            if target.get("collection") != "biomarkers" or target.get("record_id") != row["id"]:
                continue
            state = change.get("state")
            if state in {"removed", "undone"}:
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker source authority is inconsistent.",
                )
            effective = change.get("effective_value")
            if not isinstance(effective, dict) or _semantic(effective) != _semantic(row):
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker source authority is inconsistent.",
                )
            changes.append(
                {
                    "id": change.get("id"),
                    "state": state,
                    "operation": change.get("operation"),
                    "effective_value": effective,
                }
            )
        authority.append(
            {
                "id": receipt.get("id"),
                "status": receipt.get("status"),
                "receipt_revision": receipt.get("receipt_revision"),
                "changes": changes,
            }
        )
    return sorted(authority, key=_canonical)


def _row_projection(
    row: dict,
    sources: dict[str, dict],
    documents: dict[str, list[dict]],
    imports: dict[str, list[dict]],
    verified_text_cache: dict[str, str],
) -> dict:
    for field in _FIELD_LIMITS:
        _bounded_text(row, field)
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id.strip():
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker identity is missing or invalid.",
        )

    marker = row.get("marker")
    if marker is not None and not isinstance(marker, str):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    marker_text = marker or ""
    family_key = _marker_key(marker_text) if marker_text.strip() else f"unclassified:{row_id}"
    value, numeric = _classify_value(row.get("value"))
    reference_public, reference_internal = _parse_reference_range(row.get("reference_range"))

    raw_date = row.get("date")
    date_precision = derive_date_precision(raw_date)
    date_kind = row.get("date_kind")
    if date_kind not in _DATE_KINDS:
        date_kind = "unknown"
    if date_precision == "unknown":
        date_kind = "unknown"
    source_document_date = row.get("source_document_date")
    source_document_date_precision = derive_date_precision(source_document_date)

    source_id = row.get("source_document_id")
    if source_id is not None and not isinstance(source_id, str):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        )
    if isinstance(source_id, str) and (not source_id.strip() or len(source_id) > 200):
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker source data exceeds the supported projection limits.",
        )
    reported_flag = row.get("flag")
    if reported_flag is not None and (
        not isinstance(reported_flag, str) or len(reported_flag) > 40
    ):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    flag_authority = row.get("flag_authority")
    if flag_authority not in {
        "source_reported",
        "caregiver_corrected",
        "legacy_unknown",
        "unknown",
        None,
    }:
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    flag_authority = flag_authority or "unknown"
    source = sources.get(source_id) if source_id else None
    evidence_status = row.get("evidence_status")
    if evidence_status is None:
        evidence_status = "missing"
    if evidence_status not in _EVIDENCE_STATUSES:
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker source authority is inconsistent.",
        )

    evidence = []
    source_status = "not_linked"
    source_authority = None
    if source is not None:
        source_status = "indexed"
        source_authority = _source_metadata_authority(source)
    if evidence_status == "verified":
        if source is None:
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        start = row.get("evidence_start")
        end = row.get("evidence_end")
        quote = row.get("source_quote")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or end <= start
            or not isinstance(quote, str)
        ):
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        text = _validated_source_text(source, verified_text_cache)
        if start < 0 or end > len(text) or text[start:end] != quote:
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        source_status = "verified"
        evidence_id = _digest(
            "bmev",
            {"source_document_id": source_id, "start": start, "end": end, "row_id": row_id},
        )
        evidence.append(
            {
                "id": evidence_id,
                "status": "verified",
                "evidence_url": f"/api/evidence/{source_id}?start={start}&end={end}",
                "source_url": f"/api/sources/{source_id}/text",
            }
        )
    else:
        evidence.append(
            {
                "id": _digest("bmev", {"row_id": row_id, "status": evidence_status}),
                "status": evidence_status,
                "evidence_url": None,
                "source_url": f"/api/sources/{source_id}/text" if source is not None else None,
            }
        )

    receipts = _receipt_authority(row, source_id, imports)
    document_authority = []
    for document in documents.get(source_id, []):
        excluded = document.get("excluded_from_clinical_context", False)
        if not isinstance(excluded, bool):
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker source authority is inconsistent.",
            )
        document_authority.append(
            {
                "id": document.get("id"),
                "excluded_from_clinical_context": excluded,
            }
        )
    document_authority.sort(key=_canonical)
    row_authority = {
        "row": row,
        "source": source_authority,
        "source_status": source_status,
        "documents": document_authority,
        "imports": receipts,
        "source_quote_sha256": (
            hashlib.sha256(row["source_quote"].encode("utf-8")).hexdigest()
            if isinstance(row.get("source_quote"), str)
            else None
        ),
    }
    row_token = _digest("bmrow", row_authority, 32)

    normalized_unit = _normalized_unit(row.get("unit"))
    normalized_specimen = _normalized_text(row.get("specimen"))
    normalized_assay = _normalized_text(row.get("assay"))
    normalized_method = _normalized_text(row.get("method"))
    reasons = []
    if value["kind"] != "numeric":
        reasons.append("Only finite unqualified numeric values are comparable.")
    if not normalized_unit:
        reasons.append("Unit is not explicitly recorded.")
    if date_precision != "day" or date_kind not in {"collection", "result"}:
        reasons.append("An exact collection or result date is not explicitly recorded.")
    if not normalized_specimen:
        reasons.append("Specimen is not explicitly recorded.")
    if not normalized_assay and not normalized_method:
        reasons.append("Assay or method is not explicitly recorded.")
    if reference_public is None:
        reasons.append("Reference-range semantics are not explicitly comparable.")

    candidate_key = None
    if not reasons:
        candidate_key = {
            "family": family_key,
            "unit": normalized_unit,
            "date_kind": date_kind,
            "specimen": normalized_specimen,
            "assay": normalized_assay or None,
            "method": normalized_method or None,
            "reference_range": reference_public,
        }

    if row.get("provenance_status") == "caregiver_corrected":
        provenance_status = "caregiver_corrected_unverified"
        provenance_label = "Caregiver-corrected · unverified"
    elif evidence_status == "verified":
        provenance_status = "source_verified"
        provenance_label = "Exact source"
    elif source_id:
        provenance_status = "source_unverified"
        provenance_label = (
            "Invalid source quote" if evidence_status == "invalid" else "No exact source"
        )
    else:
        provenance_status = "unverified"
        provenance_label = "Unverified"

    public = {
        "row_id": row_id,
        "row_token": row_token,
        "family_key": family_key,
        "marker": marker_text,
        "date": {
            "value": raw_date,
            "precision": date_precision,
            "kind": date_kind,
            "source_document_date": source_document_date,
            "source_document_date_precision": source_document_date_precision,
        },
        "value": value,
        "unit": row.get("unit"),
        "reference_range": row.get("reference_range"),
        "reference_range_semantics": reference_public,
        "reported_flag": reported_flag,
        "reported_flag_authority": flag_authority,
        "report_range_comparison": _range_comparison(numeric, reference_internal),
        "report_range_label": (
            "Compared with the report's reference range"
            if _range_comparison(numeric, reference_internal) is not None
            else None
        ),
        "specimen": row.get("specimen"),
        "assay": row.get("assay"),
        "method": row.get("method"),
        "candidate_key": candidate_key,
        "comparability_notes": reasons,
        "provenance": {
            "status": provenance_status,
            "label": provenance_label,
            "source_document_ids": [source_id] if source_id else [],
            "evidence": evidence,
        },
        "collapse_key": {
            "source_document_id": source_id,
            "unlinked_row_id": None if source_id else row_id,
            "family": family_key,
            "marker": _normalized_text(marker_text),
            "date": {
                "value": raw_date,
                "precision": date_precision,
                "kind": date_kind,
                "source_document_date": source_document_date,
                "source_document_date_precision": source_document_date_precision,
            },
            "value": {"raw": value["raw"], "kind": value["kind"]},
            "unit": normalized_unit,
            "reference_range": reference_public,
            "reported_flag": reported_flag,
            "reported_flag_authority": flag_authority,
            "specimen": normalized_specimen,
            "assay": normalized_assay,
            "method": normalized_method,
            "provenance_status": provenance_status,
            "evidence_status": evidence_status,
        },
    }
    return {"public": public, "authority": row_authority}


def _observation_sort_key(observation: dict) -> tuple:
    date = observation["date"]
    exact = date["precision"] == "day" and date["kind"] in {"collection", "result"}
    if exact:
        return (0, date["value"], observation["id"])
    if date["precision"] in {"month", "year"}:
        return (1, date["value"] or "", observation["id"])
    return (2, str(date["value"] or ""), observation["id"])


_CHART_REQUIREMENTS = (
    (
        "numeric_value",
        "numeric value",
        "Only finite unqualified numeric values are comparable.",
    ),
    ("unit", "unit", "Unit is not explicitly recorded."),
    (
        "exact_date_kind",
        "exact collection or result date",
        "An exact collection or result date is not explicitly recorded.",
    ),
    ("specimen", "specimen", "Specimen is not explicitly recorded."),
    (
        "assay_or_method",
        "assay or method",
        "Assay or method is not explicitly recorded.",
    ),
    (
        "reference_range",
        "parseable reference range",
        "Reference-range semantics are not explicitly comparable.",
    ),
)


def _chart_diagnostics(
    observations: list[dict],
    candidate_groups: dict[str, list[dict]],
) -> dict:
    note_counts = Counter(
        note for observation in observations for note in observation["comparability_notes"]
    )
    requirements = [
        {
            "code": code,
            "label": label,
            "missing_count": note_counts[note],
        }
        for code, label, note in _CHART_REQUIREMENTS
    ]
    comparable_groups = [members for members in candidate_groups.values() if len(members) >= 2]
    unmatched_compatible_count = sum(
        len(members) for members in candidate_groups.values() if len(members) < 2
    )
    return {
        "observation_count": len(observations),
        "comparable_series_count": len(comparable_groups),
        "comparable_observation_count": sum(len(members) for members in comparable_groups),
        "unmatched_compatible_count": unmatched_compatible_count,
        "range_position_count": sum(
            observation["report_range_comparison"] in {"within", "above", "below"}
            for observation in observations
        ),
        "requirements": requirements,
    }


def project_biomarker_series(profile: dict) -> dict:
    """Project every bounded biomarker row without mutating the profile."""
    for revision_name in ("profile_revision", "workflow_revision"):
        revision = profile.get(revision_name)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker projection authority is inconsistent.",
            )
    rows = profile.get("biomarkers")
    if not isinstance(rows, list):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    if len(rows) > MAX_BIOMARKER_ROWS:
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker data exceeds the supported projection limits.",
        )
    if any(not isinstance(row, dict) for row in rows):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker data cannot be projected safely.",
        )
    ids = [row.get("id") for row in rows]
    if any(not isinstance(row_id, str) or not row_id for row_id in ids) or len(set(ids)) != len(
        ids
    ):
        raise BiomarkerProjectionError(
            "biomarker_projection_invalid",
            "Biomarker identity is missing or inconsistent.",
        )

    sources, documents, imports = _source_maps(profile)
    referenced_sources = {
        row.get("source_document_id")
        for row in rows
        if isinstance(row.get("source_document_id"), str) and row.get("source_document_id")
    }
    if len(referenced_sources) > MAX_UNIQUE_SOURCES:
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker source data exceeds the supported projection limits.",
        )

    verified_text_cache: dict[str, str] = {}
    projected_rows = [
        _row_projection(row, sources, documents, imports, verified_text_cache) for row in rows
    ]
    authority_manifest = {
        "profile_revision": profile.get("profile_revision"),
        "workflow_revision": profile.get("workflow_revision"),
        "rows": sorted(
            [
                {"row_id": item["public"]["row_id"], "row_token": item["public"]["row_token"]}
                for item in projected_rows
            ],
            key=lambda item: item["row_id"],
        ),
    }
    if (
        sum(len(_canonical(item["authority"]).encode("utf-8")) for item in projected_rows)
        > MAX_AUTHORITY_BYTES
    ):
        raise BiomarkerProjectionError(
            "biomarker_projection_too_large",
            "Biomarker authority exceeds the supported projection limits.",
        )

    collapsed: dict[str, list[dict]] = {}
    for item in projected_rows:
        key = _canonical(item["public"]["collapse_key"])
        collapsed.setdefault(key, []).append(item["public"])

    observations = []
    for members in collapsed.values():
        members.sort(key=lambda item: item["row_id"])
        representative = members[0]
        row_ids = [item["row_id"] for item in members]
        row_tokens = [item["row_token"] for item in members]
        evidence_by_id = {}
        source_ids = set()
        for member in members:
            source_ids.update(member["provenance"]["source_document_ids"])
            for evidence in member["provenance"]["evidence"]:
                evidence_by_id[evidence["id"]] = evidence
        observation_id = _digest("bmobs", {"source_row_ids": row_ids}, 32)
        observation_token = _digest(
            "bmot",
            {
                "id": observation_id,
                "row_tokens": row_tokens,
                "collapse_key": representative["collapse_key"],
            },
            32,
        )
        observations.append(
            {
                "id": observation_id,
                "token": observation_token,
                "source_row_ids": row_ids,
                "duplicate_count": len(row_ids),
                "family_key": representative["family_key"],
                "marker": representative["marker"],
                "date": representative["date"],
                "value": representative["value"],
                "unit": representative["unit"],
                "reference_range": representative["reference_range"],
                "reference_range_semantics": representative["reference_range_semantics"],
                "reported_flag": representative["reported_flag"],
                "reported_flag_authority": representative["reported_flag_authority"],
                "report_range_comparison": representative["report_range_comparison"],
                "report_range_label": representative["report_range_label"],
                "specimen": representative["specimen"],
                "assay": representative["assay"],
                "method": representative["method"],
                "candidate_key": representative["candidate_key"],
                "comparability_notes": list(representative["comparability_notes"]),
                "provenance": {
                    "status": representative["provenance"]["status"],
                    "label": representative["provenance"]["label"],
                    "source_document_ids": sorted(source_ids),
                    "evidence": [evidence_by_id[key] for key in sorted(evidence_by_id)],
                },
            }
        )

    analyte_groups: dict[str, list[dict]] = {}
    for observation in observations:
        analyte_groups.setdefault(observation["family_key"], []).append(observation)

    analytes = []
    seen_projected_ids = set()
    for family_key, family_observations in analyte_groups.items():
        family_observations.sort(key=_observation_sort_key)
        candidate_groups: dict[str, list[dict]] = {}
        noncomparable = []
        for observation in family_observations:
            if observation["candidate_key"] is None:
                noncomparable.append(observation)
            else:
                candidate_groups.setdefault(_canonical(observation["candidate_key"]), []).append(
                    observation
                )
        chart_diagnostics = _chart_diagnostics(family_observations, candidate_groups)

        series = []
        for candidate, members in sorted(candidate_groups.items()):
            candidate_value = json.loads(candidate)
            comparable = len(members) >= 2
            notes = [] if comparable else ["Fewer than two compatible observations are recorded."]
            series_id = _digest("bmseries", candidate_value, 32)
            if series_id in seen_projected_ids:
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker projection identity is inconsistent.",
                )
            seen_projected_ids.add(series_id)
            series_token = _digest(
                "bmst",
                {
                    "id": series_id,
                    "observation_tokens": [item["token"] for item in members],
                    "comparable": comparable,
                },
                32,
            )
            for member in members:
                member["series_id"] = series_id
                member["comparable"] = comparable
                if notes:
                    member["comparability_notes"] = notes
            series.append(
                {
                    "id": series_id,
                    "token": series_token,
                    "label": "Comparable numeric series"
                    if comparable
                    else "Single compatible value",
                    "unit": members[0]["unit"],
                    "specimen": members[0]["specimen"],
                    "assay": members[0]["assay"],
                    "method": members[0]["method"],
                    "date_kind": members[0]["date"]["kind"],
                    "reference_range_semantics": members[0]["reference_range_semantics"],
                    "comparable": comparable,
                    "comparability_notes": notes,
                    "observation_ids": [item["id"] for item in members],
                }
            )
        for observation in noncomparable:
            series_id = _digest(
                "bmseries",
                {"family": family_key, "observation_id": observation["id"], "isolated": True},
                32,
            )
            if series_id in seen_projected_ids:
                raise BiomarkerProjectionError(
                    "biomarker_projection_invalid",
                    "Biomarker projection identity is inconsistent.",
                )
            seen_projected_ids.add(series_id)
            observation["series_id"] = series_id
            observation["comparable"] = False
            series.append(
                {
                    "id": series_id,
                    "token": _digest(
                        "bmst",
                        {"id": series_id, "observation_token": observation["token"]},
                        32,
                    ),
                    "label": "Not comparable",
                    "unit": observation["unit"],
                    "specimen": observation["specimen"],
                    "assay": observation["assay"],
                    "method": observation["method"],
                    "date_kind": observation["date"]["kind"],
                    "reference_range_semantics": observation["reference_range_semantics"],
                    "comparable": False,
                    "comparability_notes": observation["comparability_notes"],
                    "observation_ids": [observation["id"]],
                }
            )

        observed_aliases = sorted(
            {item["marker"] for item in family_observations if item["marker"]},
            key=lambda value: (_normalized_text(value), value),
        )
        analyte_id = _digest("bmanalyte", {"family": family_key}, 32)
        if analyte_id in seen_projected_ids:
            raise BiomarkerProjectionError(
                "biomarker_projection_invalid",
                "Biomarker projection identity is inconsistent.",
            )
        seen_projected_ids.add(analyte_id)
        analyte_token = _digest(
            "bmat",
            {
                "id": analyte_id,
                "observation_tokens": [item["token"] for item in family_observations],
                "series_tokens": [item["token"] for item in series],
            },
            32,
        )
        for observation in family_observations:
            observation.pop("family_key", None)
            observation.pop("marker", None)
            observation.pop("candidate_key", None)
        analytes.append(
            {
                "id": analyte_id,
                "token": analyte_token,
                "display_name": _marker_display(family_key, observed_aliases),
                "observed_aliases": observed_aliases,
                "observation_count": len(family_observations),
                "source_row_count": sum(
                    observation["duplicate_count"] for observation in family_observations
                ),
                "series_count": len(series),
                "chart_diagnostics": chart_diagnostics,
                "series": sorted(series, key=lambda item: item["id"]),
                "observations": family_observations,
            }
        )

    analytes.sort(key=lambda item: (_normalized_text(item["display_name"]), item["id"]))
    projection_token = _digest(
        "bmprojection",
        {
            **authority_manifest,
            "analyte_tokens": [item["token"] for item in analytes],
        },
        40,
    )
    return {
        "profile_revision": profile.get("profile_revision"),
        "workflow_revision": profile.get("workflow_revision"),
        "projection_token": projection_token,
        "observation_count": len(observations),
        "source_row_count": len(rows),
        "analytes": analytes,
    }


__all__ = [
    "BiomarkerProjectionError",
    "MAX_BIOMARKER_ROWS",
    "project_biomarker_series",
]
