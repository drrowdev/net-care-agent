"""Validated evidence catalog and claim-level source-link resolution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_CLAIM_KEYS = (
    "status_rationale",
    "key_concern",
    "summary",
    "prrt_rationale",
    "cga_trend_detail",
)


def _catalog_id(source_id: str, start: int, end: int, label: str) -> str:
    raw = f"{source_id}:{start}:{end}:{label}".encode()
    return f"ev_{hashlib.sha256(raw).hexdigest()[:20]}"


def _fact_label(collection: str, item: dict) -> str:
    if collection == "biomarkers":
        return (
            f"Biomarker {item.get('marker') or 'value'} = {item.get('value')} "
            f"{item.get('unit') or ''} on {item.get('date') or 'unknown date'}"
        ).strip()
    if collection == "imaging":
        return (
            f"{item.get('modality') or 'Imaging'} on {item.get('date') or 'unknown date'}: "
            f"{item.get('impression') or item.get('findings') or 'finding'}"
        )[:600]
    if collection == "symptoms":
        return (
            f"Symptom {item.get('symptom') or 'reported'} on "
            f"{item.get('date') or 'unknown date'}"
        )
    return (
        f"Appointment {item.get('description') or item.get('type') or 'event'} on "
        f"{item.get('date') or 'unknown date'}"
    )


def build_evidence_catalog(profile: dict) -> dict[str, dict]:
    """Return only real, verified source spans keyed by opaque stable IDs."""
    catalog: dict[str, dict] = {}
    for collection in ("biomarkers", "imaging", "symptoms", "appointments"):
        for item in profile.get(collection, []):
            source_id = item.get("source_document_id")
            start = item.get("evidence_start")
            end = item.get("evidence_end")
            if (
                item.get("evidence_status") != "verified"
                or not isinstance(source_id, str)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or end <= start
            ):
                continue
            label = _fact_label(collection, item)
            evidence_id = _catalog_id(source_id, start, end, label)
            catalog[evidence_id] = {
                "id": evidence_id,
                "label": label,
                "source_document_id": source_id,
                "evidence_status": "verified",
                "evidence_start": start,
                "evidence_end": end,
                "source_quote": item.get("source_quote"),
                "recorded_at": item.get("added_at") or item.get("date") or "",
            }

    for document in profile.get("documents", []):
        if document.get("excluded_from_clinical_context"):
            continue
        source_id = document.get("source_document_id")
        if not isinstance(source_id, str):
            continue
        for evidence in document.get("evidence", []):
            start = evidence.get("evidence_start")
            end = evidence.get("evidence_end")
            if (
                evidence.get("evidence_status") != "verified"
                or not isinstance(start, int)
                or not isinstance(end, int)
                or end <= start
            ):
                continue
            field = evidence.get("field") or "document finding"
            index = evidence.get("item_index")
            value: Any = None
            if field == "key_findings" and isinstance(index, int):
                findings = document.get("key_findings") or []
                value = findings[index] if index < len(findings) else None
            label = f"{field.replace('_', ' ').title()}: {value or document.get('summary') or 'source span'}"
            evidence_id = _catalog_id(source_id, start, end, label)
            catalog[evidence_id] = {
                "id": evidence_id,
                "label": label[:600],
                "source_document_id": source_id,
                "evidence_status": "verified",
                "evidence_start": start,
                "evidence_end": end,
                "source_quote": evidence.get("source_quote"),
                "recorded_at": document.get("added_at") or document.get("date") or "",
            }
    return catalog


def evidence_catalog_prompt(profile: dict) -> str:
    """Serialize the bounded verified catalog for model selection."""
    rows = []
    catalog = build_evidence_catalog(profile)
    for entry in sorted(
        catalog.values(),
        key=lambda item: item.get("recorded_at") or "",
        reverse=True,
    )[:100]:
        rows.append(
            {
                "evidence_id": entry["id"],
                "fact": entry["label"],
                "exact_source_quote": entry.get("source_quote"),
            }
        )
    return json.dumps(rows, ensure_ascii=False, default=str)


def _resolved_item(catalog: dict[str, dict], evidence_id: object) -> dict:
    if not isinstance(evidence_id, str) or evidence_id not in catalog:
        return {
            "evidence_id": str(evidence_id or ""),
            "label": "Invalid or unavailable evidence reference",
            "evidence_status": "invalid",
        }
    item = catalog[evidence_id]
    return {
        "evidence_id": evidence_id,
        "label": item["label"],
        "evidence_status": "verified",
        "source_document_id": item["source_document_id"],
        "evidence_url": (
            f"/api/evidence/{item['source_document_id']}?start={item['evidence_start']}"
            f"&end={item['evidence_end']}"
        ),
        "source_url": f"/api/sources/{item['source_document_id']}/text",
    }


def _resolve_ids(catalog: dict[str, dict], values: object) -> list[dict]:
    if not isinstance(values, list) or not values:
        return [
            {
                "label": "No exact source span linked",
                "evidence_status": "missing",
            }
        ]
    seen = set()
    resolved = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(_resolved_item(catalog, value))
    return resolved or [{"label": "No exact source span linked", "evidence_status": "missing"}]


def resolve_summary_evidence(profile: dict, summary: dict) -> dict:
    """Resolve model-selected IDs without trusting model paths or offsets."""
    catalog = build_evidence_catalog(profile)
    selected = summary.get("claim_evidence")
    if not isinstance(selected, dict):
        selected = {}
    claims = {key: _resolve_ids(catalog, selected.get(key)) for key in _CLAIM_KEYS}
    actions = []
    for action in summary.get("next_actions", []):
        if not isinstance(action, dict):
            continue
        actions.append(_resolve_ids(catalog, action.get("evidence_ids")))
    return {"claims": claims, "actions": actions}
