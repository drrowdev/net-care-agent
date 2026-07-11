"""Deterministic, PHI-safe evaluation gate for intake extraction.

Exit codes: 0 = gates passed, 2 = metric gate failed, 3 = harness/schema error,
4 = model/runtime error. Real model runs are external and intentionally not CI.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2.0.0"
ARTIFACT_SCHEMA_VERSION = "2.0.0"
EXIT_PASS = 0
EXIT_METRICS = 2
EXIT_HARNESS = 3
EXIT_RUNTIME = 4
ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DIR = ROOT / "eval_cases" / "synthetic"

DOCUMENT_TYPES = {
    "lab_result",
    "imaging_report",
    "doctor_note",
    "research_paper",
    "appointment_summary",
    "pathology_report",
    "other",
}
APPOINTMENT_TYPES = {"call", "appointment", "scan", "review", "infusion", "other"}
SSTR_STATUSES = {"positive", "negative"}
TREATMENT_STATES = {"started", "stopped", "held", "increased", "decreased"}
IMAGING_STATUSES = {
    "new",
    "stable",
    "progressing",
    "responding",
    "positive",
    "negative",
    "indeterminate",
    "mixed",
}
LIST_FIELDS = (
    "biomarkers",
    "treatment_changes",
    "imaging_facts",
    "symptoms",
    "appointments",
    "key_findings",
    "critical_events",
)
SCALAR_FIELDS = ("ki67_update", "sstr_status_update", "sstr_score_update")
FIELDS = (
    "document_type",
    *LIST_FIELDS,
    *SCALAR_FIELDS,
)
EXPECTED_KEYS = {
    *FIELDS,
    "source_quotes",
    "must_not_infer",
}
CASE_KEYS = {"schema_version", "id", "text", "expected", "tags"}
DEFAULT_THRESHOLDS = {
    "max_critical_omissions": 0,
    "max_critical_regressions": 0,
    "min_critical_event_recall": 1.0,
    "min_overall_recall": 0.98,
    "min_overall_precision": 0.98,
    "min_source_support": 0.99,
    "min_date_accuracy": 0.99,
    "min_value_accuracy": 0.99,
    "min_unit_accuracy": 0.99,
    "min_treatment_state_accuracy": 0.99,
    "min_special_scalar_accuracy": 0.99,
    "max_unsupported_additions": 0,
    "max_critical_unsupported_additions": 0,
    "max_must_not_infer_violations": 0,
}

STATE_ALIASES = {
    "started": (
        "start",
        "started",
        "restart",
        "restarted",
        "initiate",
        "initiated",
        "begin",
        "began",
    ),
    "continued": ("continue", "continued", "maintain", "maintained", "ongoing"),
    "stopped": ("stop", "stopped", "discontinue", "discontinued"),
    "held": ("hold", "held", "pause", "paused"),
    "increased": ("increase", "increased", "escalate", "escalated"),
    "decreased": ("decrease", "decreased", "reduce", "reduced"),
    "planned": ("plan", "planned", "scheduled", "consider"),
    "administered": ("administered", "given", "received", "injection"),
}
NEGATION_WORDS = ("no ", "not ", "denies ", "denied ", "without ", "absent")
URGENT_WORDS = ("urgent", "critical", "emergency", "obstruction", "thrombus", "embol", "sepsis")
LABEL_STOPWORDS = {
    "a",
    "an",
    "the",
    "was",
    "were",
    "is",
    "are",
    "in",
    "on",
    "of",
    "to",
    "for",
    "and",
    "with",
    "against",
    "had",
    "has",
}


class ValidationError(ValueError):
    """A malformed case or configuration."""


class RuntimeEvaluationError(RuntimeError):
    """The evaluated model failed to return a usable result."""


def normalize_text(value: Any) -> str:
    """Public, transparent normalization used by all fuzzy text matches."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"[^a-z0-9%µμ./+\-]+", " ", text)
    return " ".join(text.split())


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _item_hash(case_id: str, field: str, index: int) -> str:
    return _hash(f"{case_id}:{field}:{index}")[:16]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _validate_item(case_id: str, field: str, index: int, item: Any) -> None:
    prefix = f"{case_id}.expected.{field}[{index}]"
    _require(isinstance(item, dict), f"{prefix} must be an object")
    required: dict[str, tuple[str, ...]] = {
        "biomarkers": ("marker", "value", "unit", "date", "reference_range", "source_quote"),
        "treatment_changes": ("treatment", "state", "date", "source_quote"),
        "imaging_facts": ("finding", "date", "status", "source_quote"),
        "symptoms": ("symptom", "status", "date", "source_quote"),
        "appointments": ("date", "description", "type", "source_quote"),
        "key_findings": ("finding", "date", "source_quote"),
        "critical_events": ("event", "date", "source_quote"),
        "source_quotes": ("field", "quote"),
    }
    allowed = set(required[field]) | ({"critical"} if field != "source_quotes" else set())
    unknown = set(item) - allowed
    _require(not unknown, f"{prefix} has unknown keys: {sorted(unknown)}")
    for key in required[field]:
        _require(key in item, f"{prefix}.{key} is required")
        _require(
            item[key] is None or isinstance(item[key], str | int | float),
            f"{prefix}.{key} has invalid type",
        )
        if isinstance(item[key], float):
            _require(math.isfinite(item[key]), f"{prefix}.{key} must be finite")
    if "critical" in item:
        _require(isinstance(item["critical"], bool), f"{prefix}.critical must be boolean")
    if field == "symptoms":
        _require(
            item["status"] in {"present", "absent"}, f"{prefix}.status must be present or absent"
        )
    if field == "appointments":
        _require(
            item["type"] in APPOINTMENT_TYPES,
            f"{prefix}.type must be one of {sorted(APPOINTMENT_TYPES)}",
        )
    if field == "treatment_changes":
        _require(
            item["state"] in TREATMENT_STATES,
            f"{prefix}.state must be one of {sorted(TREATMENT_STATES)}",
        )
    if field == "imaging_facts":
        _require(
            item["status"] in IMAGING_STATUSES,
            f"{prefix}.status must be one of {sorted(IMAGING_STATUSES)}",
        )


def _validate_scalar(source: str, field: str, value: Any) -> None:
    if value is None:
        return
    if field == "sstr_status_update":
        _require(value in SSTR_STATUSES, f"{source}: {field} must be positive, negative, or null")
        return
    _require(
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value),
        f"{source}: {field} must be a finite number or null",
    )
    low, high = (0, 100) if field == "ki67_update" else (0, 4)
    _require(low <= value <= high, f"{source}: {field} must be in range {low}..{high}")


def validate_case(case: Any, *, source: str = "<memory>") -> dict:
    """Validate one golden case loudly and return it unchanged."""
    _require(isinstance(case, dict), f"{source}: case must be an object")
    unknown = set(case) - CASE_KEYS
    _require(not unknown, f"{source}: unknown case keys: {sorted(unknown)}")
    for key in ("schema_version", "id", "text", "expected", "tags"):
        _require(key in case, f"{source}: {key} is required")
    _require(case["schema_version"] == SCHEMA_VERSION, f"{source}: unsupported schema_version")
    _require(bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", case["id"])), f"{source}: invalid id")
    _require(
        isinstance(case["text"], str) and case["text"].strip(), f"{source}: text must be non-empty"
    )
    _require(
        isinstance(case["tags"], list) and all(isinstance(x, str) for x in case["tags"]),
        f"{source}: tags must be strings",
    )
    expected = case["expected"]
    _require(isinstance(expected, dict), f"{source}: expected must be an object")
    missing = EXPECTED_KEYS - set(expected)
    unknown = set(expected) - EXPECTED_KEYS
    _require(not missing, f"{source}: missing expected keys: {sorted(missing)}")
    _require(not unknown, f"{source}: unknown expected keys: {sorted(unknown)}")
    _require(
        expected["document_type"] in DOCUMENT_TYPES,
        f"{source}: document_type must be one of {sorted(DOCUMENT_TYPES)}",
    )
    for field in LIST_FIELDS:
        _require(isinstance(expected[field], list), f"{source}: expected.{field} must be a list")
        for index, item in enumerate(expected[field]):
            _validate_item(case["id"], field, index, item)
            _require(
                normalize_text(item["source_quote"]) in normalize_text(case["text"]),
                f"{source}: expected.{field}[{index}].source_quote is not in text",
            )
            if field == "biomarkers":
                marker = normalize_text(item["marker"]).replace(" ", "")
                _require(
                    marker not in {"ki-67", "ki67", "mib-1", "mib1", "mitoticrate"},
                    f"{source}: {item['marker']} is not a contract biomarker",
                )
    for field in SCALAR_FIELDS:
        _validate_scalar(source, field, expected[field])
    _require(isinstance(expected["source_quotes"], list), f"{source}: source_quotes must be a list")
    for index, item in enumerate(expected["source_quotes"]):
        _validate_item(case["id"], "source_quotes", index, item)
        _require(
            item["field"] in (*LIST_FIELDS, *SCALAR_FIELDS),
            f"{source}: source quote {index} has invalid field",
        )
        _require(
            normalize_text(item["quote"]) in normalize_text(case["text"]),
            f"{source}: source quote {index} is not in text",
        )
    _require(
        isinstance(expected["must_not_infer"], list), f"{source}: must_not_infer must be a list"
    )
    for index, item in enumerate(expected["must_not_infer"]):
        _require(
            isinstance(item, str | dict), f"{source}: must_not_infer[{index}] must be string/object"
        )
        if isinstance(item, dict):
            _require(
                set(item) <= {"statement", "critical"}, f"{source}: invalid must_not_infer keys"
            )
            _require(
                isinstance(item.get("statement"), str) and item["statement"],
                f"{source}: statement required",
            )
            _require(
                isinstance(item.get("critical", False), bool), f"{source}: critical must be boolean"
            )
    return case


def load_cases(directory: str | Path | None = None) -> list[dict]:
    """Load static JSON cases. Private corpora must be outside the repository."""
    path = Path(directory).resolve() if directory else SYNTHETIC_DIR.resolve()
    if path != SYNTHETIC_DIR.resolve() and (path == ROOT or ROOT in path.parents):
        raise ValidationError("private --golden-dir must be outside the repository")
    if not path.is_dir():
        raise ValidationError(f"golden directory does not exist: {path}")
    files = sorted(path.glob("*.json"))
    if not files:
        raise ValidationError(f"no JSON cases found in {path}")
    cases: list[dict] = []
    seen: set[str] = set()
    for file in files:
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"{file}: invalid JSON: {exc}") from exc
        entries = payload if isinstance(payload, list) else [payload]
        for case in entries:
            validate_case(case, source=str(file))
            _require(case["id"] not in seen, f"duplicate case id: {case['id']}")
            seen.add(case["id"])
            cases.append(case)
    return cases


def _as_items(actual: dict, field: str) -> list[Any]:
    aliases = {
        "imaging_facts": ("imaging_facts", "imaging_findings"),
        "symptoms": ("symptoms", "symptoms_reported"),
        "critical_events": ("critical_events", "key_findings"),
    }
    value: Any = None
    for key in aliases.get(field, (field,)):
        if key in actual and actual[key] not in (None, "", []):
            value = actual[key]
            break
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def _actual_text(item: Any) -> str:
    if isinstance(item, dict):
        return normalize_text(
            " ".join(str(v) for k, v in sorted(item.items()) if k not in {"source_quote", "quote"})
        )
    return normalize_text(item)


def _field_label(field: str, item: dict) -> str:
    key = {
        "biomarkers": "marker",
        "treatment_changes": "treatment",
        "imaging_facts": "finding",
        "symptoms": "symptom",
        "appointments": "description",
        "key_findings": "finding",
        "critical_events": "event",
    }[field]
    return normalize_text(item.get(key))


def _label_similarity(field: str, expected: dict, actual: Any) -> float:
    label = _field_label(field, expected)
    if isinstance(actual, dict):
        keys = {
            "biomarkers": ("marker",),
            "treatment_changes": ("treatment", "name", "text"),
            "imaging_facts": ("finding", "findings", "impression"),
            "symptoms": ("symptom",),
            "appointments": ("description",),
            "key_findings": ("finding", "event", "text"),
            "critical_events": ("event", "finding", "text"),
        }[field]
        text = normalize_text(next((actual.get(key) for key in keys if actual.get(key)), ""))
    else:
        text = _actual_text(actual)
    if not label or not text:
        return 0.0
    if label == text:
        return 1.0
    label_tokens = set(label.split()) - LABEL_STOPWORDS
    text_tokens = set(text.split()) - LABEL_STOPWORDS
    overlap = len(label_tokens & text_tokens)
    if not overlap:
        return 0.0
    expected_coverage = overlap / len(label_tokens)
    if field in {"biomarkers", "treatment_changes", "symptoms", "appointments"}:
        return expected_coverage
    # Both sides must be substantially represented. This prevents a fragment
    # such as "embolus" from satisfying a detailed critical finding.
    return min(expected_coverage, overlap / len(text_tokens))


def _expected_label_coverage(field: str, expected: dict, text: str) -> float:
    label_tokens = set(_field_label(field, expected).split()) - LABEL_STOPWORDS
    text_tokens = set(normalize_text(text).split()) - LABEL_STOPWORDS
    return len(label_tokens & text_tokens) / len(label_tokens) if label_tokens else 0.0


def _state_in(text: str, state: str) -> bool:
    state = normalize_text(state)
    aliases = STATE_ALIASES.get(state, (state,))
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalize_text(alias))}(?![a-z0-9])",
            text,
        )
        for alias in aliases
    )


def _status_in(text: str, status: str) -> bool:
    negated = any(word in f"{text} " for word in NEGATION_WORDS)
    return negated if status == "absent" else not negated


def _actual_value(actual: Any, key: str, root: dict) -> Any:
    if isinstance(actual, dict):
        candidate = actual.get(key)
        if key == "date" and candidate is None:
            candidate = actual.get("collection_date")
        if candidate is not None:
            return candidate
    if key == "date":
        return root.get("date")
    return None


def _exact(
    actual: Any,
    key: str,
    expected: Any,
    root: dict | None = None,
    evidence_quote: str | None = None,
) -> bool:
    if expected in (None, ""):
        return True
    if key == "date" and isinstance(actual, dict):
        direct = actual.get("date", actual.get("collection_date"))
        if direct is not None:
            return normalize_text(direct) == normalize_text(expected)
    candidate = _actual_value(actual, key, root or {})
    if normalize_text(candidate) == normalize_text(expected):
        return True
    return bool(
        key == "date"
        and evidence_quote
        and normalize_text(expected) in normalize_text(evidence_quote)
    )


def _evidence_quote(field: str, actual: Any, root: dict, actual_index: int) -> str | None:
    if isinstance(actual, dict):
        direct = actual.get("source_quote", actual.get("quote"))
        if isinstance(direct, str) and direct:
            return direct
    evidence_field = "key_findings" if field == "critical_events" else field
    for candidate in root.get("evidence") or []:
        if not isinstance(candidate, dict) or candidate.get("field") != evidence_field:
            continue
        item_index = candidate.get("item_index")
        if item_index != actual_index:
            continue
        quote = candidate.get("source_quote", candidate.get("quote"))
        if isinstance(quote, str) and quote:
            return quote
    return None


def _quote_supports(
    field: str,
    document: str,
    expected: dict,
    actual: Any,
    root: dict,
    actual_index: int,
) -> bool:
    quote = _evidence_quote(field, actual, root, actual_index)
    normalized_quote = normalize_text(quote)
    if not normalized_quote or normalized_quote not in normalize_text(document):
        return False
    if _expected_label_coverage(field, expected, quote) < 0.5:
        return False
    if field == "biomarkers":
        return all(
            normalize_text(expected[key]) in normalized_quote
            and _exact(actual, key, expected[key], root)
            for key in ("value", "unit")
            if expected.get(key) not in (None, "")
        )
    if field == "treatment_changes":
        return _state_in(normalized_quote, str(expected["state"]))
    if field == "appointments":
        return normalize_text(expected["date"]) in normalized_quote and _exact(
            actual, "date", expected["date"], root
        )
    if field == "symptoms" and expected["status"] == "absent":
        return _status_in(normalized_quote, "absent")
    return True


def _candidate_quality(
    field: str,
    expected: dict,
    actual: Any,
    root: dict,
    actual_index: int,
    document: str,
) -> int:
    similarity = _label_similarity(field, expected, actual)
    if similarity < 0.5:
        return -1
    text = _actual_text(actual)
    if field == "symptoms":
        status_matches = (
            normalize_text(actual.get("status")) == normalize_text(expected["status"])
            if isinstance(actual, dict) and actual.get("status")
            else _status_in(text, expected["status"])
        )
        if not status_matches:
            return -1
    if field == "appointments":
        actual_type = actual.get("type") if isinstance(actual, dict) else None
        if normalize_text(actual_type) != normalize_text(expected["type"]):
            return -1
    quality = 100 + round(similarity * 20)
    for key, weight in (("date", 12), ("value", 20), ("unit", 12)):
        quote = _evidence_quote(field, actual, root, actual_index)
        if expected.get(key) not in (None, "") and _exact(actual, key, expected[key], root, quote):
            quality += weight
    if field == "treatment_changes" and _state_in(text, str(expected["state"])):
        quality += 24
    if _quote_supports(field, document, expected, actual, root, actual_index):
        quality += 8
    return quality


def _maximum_assignment(weights: list[list[int]]) -> list[int]:
    """Return deterministic maximum-weight row assignments; dummy columns mean unmatched."""
    if not weights:
        return []
    row_count = len(weights)
    real_columns = len(weights[0]) if weights[0] else 0
    matrix = [row + [0] * row_count for row in weights]
    column_count = real_columns + row_count
    u = [0] * (row_count + 1)
    v = [0] * (column_count + 1)
    p = [0] * (column_count + 1)
    way = [0] * (column_count + 1)
    for row in range(1, row_count + 1):
        p[0] = row
        column0 = 0
        minimum = [math.inf] * (column_count + 1)
        used = [False] * (column_count + 1)
        while True:
            used[column0] = True
            row0 = p[column0]
            delta = math.inf
            column1 = 0
            for column in range(1, column_count + 1):
                if used[column]:
                    continue
                cost = -matrix[row0 - 1][column - 1] - u[row0] - v[column]
                if cost < minimum[column]:
                    minimum[column] = cost
                    way[column] = column0
                if minimum[column] < delta:
                    delta = minimum[column]
                    column1 = column
            for column in range(column_count + 1):
                if used[column]:
                    u[p[column]] += delta
                    v[column] -= delta
                else:
                    minimum[column] -= delta
            column0 = column1
            if p[column0] == 0:
                break
        while True:
            column1 = way[column0]
            p[column0] = p[column1]
            column0 = column1
            if column0 == 0:
                break
    assignment = [-1] * row_count
    for column in range(1, column_count + 1):
        if p[column]:
            assignment[p[column] - 1] = column - 1
    return assignment


def _pair_items(
    field: str,
    expected: list[dict],
    actual: list[Any],
    root: dict | None = None,
    document: str = "",
    actual_indexes: list[int] | None = None,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    root = root or {}
    actual_indexes = actual_indexes or list(range(len(actual)))
    weights = [
        [
            _candidate_quality(field, exp, item, root, actual_indexes[index], document)
            for index, item in enumerate(actual)
        ]
        for exp in expected
    ]
    assignment = _maximum_assignment(weights)
    pairs = [
        (exp_index, act_index)
        for exp_index, act_index in enumerate(assignment)
        if act_index < len(actual) and weights[exp_index][act_index] >= 0
    ]
    paired_expected = {exp for exp, _ in pairs}
    paired_actual = {act for _, act in pairs}
    return (
        pairs,
        sorted(set(range(len(expected))) - paired_expected),
        sorted(set(range(len(actual))) - paired_actual),
    )


def _contains_prohibited_statement(claim: str, statement: str) -> bool:
    normalized = normalize_text(statement)
    if not normalized:
        return False
    negations = (
        "no ",
        "not ",
        "denies ",
        "denied ",
        "without ",
        "absent",
        "cancelled",
        "canceled",
        "unchanged",
        "stable",
        "consider",
    )
    if normalized in claim:
        start = claim.index(normalized)
        window = claim[max(0, start - 50) : start + len(normalized) + 50]
        return not any(word in window for word in negations)
    statement_tokens = normalized.split()
    actual_tokens = set(claim.split())
    return (
        len(statement_tokens) > 1
        and all(token in actual_tokens for token in statement_tokens)
        and not any(word in claim for word in negations)
    )


def _claim_texts(value: Any, *, parent_key: str = "") -> list[str]:
    if parent_key in {"evidence", "source_quote", "quote", "source_document_id"}:
        return []
    if isinstance(value, dict):
        return [
            claim for key, child in value.items() for claim in _claim_texts(child, parent_key=key)
        ]
    if isinstance(value, list):
        return [claim for child in value for claim in _claim_texts(child)]
    if isinstance(value, str):
        # Keep negation local to its sentence/clause. Normalizing a whole block
        # first would let "No flushing." suppress an unrelated hallucinated
        # statement later in the same field.
        claims = [
            normalize_text(part) for part in re.split(r"[.!?;\n]+", value) if normalize_text(part)
        ]
        return claims
    return []


def _blank_counts() -> dict[str, int]:
    return {"tp": 0, "expected": 0, "actual": 0, "missed": 0, "unsupported": 0}


def _scalar_supported(field: str, expected: Any, actual: dict, document: str) -> bool:
    quote = None
    for candidate in actual.get("evidence") or []:
        if isinstance(candidate, dict) and candidate.get("field") == field:
            quote = candidate.get("source_quote", candidate.get("quote"))
            break
    normalized = normalize_text(quote)
    if not normalized or normalized not in normalize_text(document):
        return False
    identifiers = {
        "ki67_update": ("ki 67", "ki-67", "ki67", "mib 1", "mib-1"),
        "sstr_status_update": ("sstr", "somatostatin receptor", "radiotracer uptake"),
        "sstr_score_update": ("sstr", "krenning", "somatostatin receptor"),
    }[field]
    if not any(normalize_text(identifier) in normalized for identifier in identifiers):
        return False
    if field == "sstr_status_update":
        aliases = {
            "positive": ("positive", "avid", "uptake"),
            "negative": ("negative", "non avid", "no uptake", "without uptake"),
        }[str(expected)]
        return any(normalize_text(alias) in normalized for alias in aliases)
    return normalize_text(expected) in normalized


def _scalar_equal(expected: Any, actual: Any) -> bool:
    if (
        isinstance(expected, int | float)
        and not isinstance(expected, bool)
        and isinstance(actual, int | float)
        and not isinstance(actual, bool)
    ):
        return math.isfinite(actual) and float(expected) == float(actual)
    return normalize_text(expected) == normalize_text(actual)


def score_extraction(
    expected: dict, actual: dict, document_text: str = "", case_id: str = "case"
) -> dict:
    """Score one extraction using deterministic normalized matching only."""
    _require(isinstance(actual, dict), "actual extraction must be an object")
    field_counts = {field: _blank_counts() for field in FIELDS}
    omitted_hashes: list[str] = []
    unsupported_hashes: list[str] = []
    critical_omissions = 0
    critical_unsupported = 0
    critical_event_omissions = 0
    source_supported = 0
    source_total = 0
    exact = Counter()
    pairings: dict[str, list[tuple[int, int]]] = {}
    field_actual: dict[str, tuple[list[Any], list[int]]] = {
        field: (items := _as_items(actual, field), list(range(len(items))))
        for field in LIST_FIELDS
        if field not in {"key_findings", "critical_events"}
    }
    raw_key_items = _as_items(actual, "key_findings")
    if "critical_events" in actual:
        critical_items = _as_items(actual, "critical_events")
        field_actual["key_findings"] = (raw_key_items, list(range(len(raw_key_items))))
        field_actual["critical_events"] = (
            critical_items,
            list(range(len(critical_items))),
        )
    else:
        # Critical events are a safety lens over key findings, not a separate
        # output requirement. Score both against the full set so one complete
        # finding can satisfy overlapping key/critical expectations.
        ordinary_pairs, _, _ = _pair_items(
            "key_findings",
            expected["key_findings"],
            raw_key_items,
            actual,
            document_text,
        )
        critical_pairs, _, _ = _pair_items(
            "critical_events",
            expected["critical_events"],
            raw_key_items,
            actual,
            document_text,
        )
        critical_indexes = {actual_index for _, actual_index in critical_pairs}
        critical_indexes.update(
            index
            for index in range(len(raw_key_items))
            if index not in critical_indexes
            and any(word in _actual_text(raw_key_items[index]) for word in URGENT_WORDS)
        )
        ordinary_matched = {actual_index for _, actual_index in ordinary_pairs}
        ordinary_indexes = ordinary_matched | {
            index for index in range(len(raw_key_items)) if index not in critical_indexes
        }
        ordinary_order = sorted(ordinary_indexes)
        critical_order = sorted(critical_indexes)
        field_actual["key_findings"] = (
            [raw_key_items[index] for index in ordinary_order],
            ordinary_order,
        )
        field_actual["critical_events"] = (
            [raw_key_items[index] for index in critical_order],
            critical_order,
        )

    exp_doc = normalize_text(expected["document_type"])
    act_doc = normalize_text(actual.get("document_type"))
    doc_match = bool(act_doc and act_doc == exp_doc)
    field_counts["document_type"].update(
        tp=int(doc_match),
        expected=1,
        actual=int(bool(act_doc)),
        missed=int(not doc_match),
        unsupported=int(bool(act_doc) and not doc_match),
    )

    for field in LIST_FIELDS:
        exp_items = expected[field]
        act_items, original_indexes = field_actual[field]
        pairs, missed, unsupported = _pair_items(
            field,
            exp_items,
            act_items,
            actual,
            document_text,
            original_indexes,
        )
        pairings[field] = pairs
        field_counts[field].update(
            tp=len(pairs),
            expected=len(exp_items),
            actual=len(act_items),
            missed=len(missed),
            unsupported=len(unsupported),
        )
        for exp_index, act_index in pairs:
            exp_item, act_item = exp_items[exp_index], act_items[act_index]
            original_index = original_indexes[act_index]
            source_total += 1
            source_supported += int(
                _quote_supports(field, document_text, exp_item, act_item, actual, original_index)
            )
            exact["date_total"] += int(exp_item.get("date") not in (None, ""))
            exact["date_correct"] += int(
                _exact(
                    act_item,
                    "date",
                    exp_item.get("date"),
                    actual,
                    _evidence_quote(field, act_item, actual, original_index),
                )
            )
            if field == "biomarkers":
                for key in ("value", "unit"):
                    exact[f"{key}_total"] += int(exp_item.get(key) not in (None, ""))
                    exact[f"{key}_correct"] += int(_exact(act_item, key, exp_item.get(key), actual))
        for index in missed:
            omitted_hashes.append(_item_hash(case_id, field, index))
            if exp_items[index].get("critical", False) or field == "critical_events":
                critical_omissions += 1
            if field == "critical_events":
                critical_event_omissions += 1
        for index in unsupported:
            unsupported_hashes.append(_hash(f"{case_id}:{field}:actual:{index}")[:16])
            text = _actual_text(act_items[index])
            if field == "critical_events" or any(word in text for word in URGENT_WORDS):
                critical_unsupported += 1

    scalar_correct = 0
    scalar_expected = 0
    for field in SCALAR_FIELDS:
        exp_value = expected[field]
        act_value = actual.get(field)
        exp_present = exp_value is not None
        act_present = act_value is not None
        correct = exp_present and act_present and _scalar_equal(exp_value, act_value)
        field_counts[field].update(
            tp=int(correct),
            expected=int(exp_present),
            actual=int(act_present),
            missed=int(exp_present and not correct),
            unsupported=int(act_present and not correct),
        )
        scalar_expected += int(exp_present)
        scalar_correct += int(correct)
        if exp_present and act_present:
            source_total += 1
            source_supported += int(
                correct and _scalar_supported(field, exp_value, actual, document_text)
            )
        if exp_present and not correct:
            omitted_hashes.append(_item_hash(case_id, field, 0))
        if act_present and not correct:
            unsupported_hashes.append(_hash(f"{case_id}:{field}:actual")[:16])

    treatment_items = _as_items(actual, "treatment_changes")
    treatment_pairs = pairings["treatment_changes"]
    treatment_state_correct = sum(
        _state_in(
            _actual_text(treatment_items[act]),
            expected["treatment_changes"][exp]["state"],
        )
        for exp, act in treatment_pairs
    )

    claims = _claim_texts(actual)
    infer_violations = 0
    critical_infer_violations = 0
    violation_hashes: list[str] = []
    for index, prohibition in enumerate(expected["must_not_infer"]):
        statement = prohibition if isinstance(prohibition, str) else prohibition["statement"]
        if any(_contains_prohibited_statement(claim, statement) for claim in claims):
            infer_violations += 1
            critical = isinstance(prohibition, dict) and prohibition.get("critical", False)
            critical_infer_violations += int(critical)
            violation_hashes.append(_item_hash(case_id, "must_not_infer", index))
    critical_unsupported += critical_infer_violations

    total_tp = sum(counts["tp"] for counts in field_counts.values())
    total_expected = sum(counts["expected"] for counts in field_counts.values())
    total_actual = sum(counts["actual"] for counts in field_counts.values())
    critical_expected = sum(
        1
        for field in LIST_FIELDS
        for item in expected[field]
        if item.get("critical", False) or field == "critical_events"
    )
    critical_event_expected = len(expected["critical_events"])
    return {
        "fields": {
            field: {
                **counts,
                "recall": counts["tp"] / counts["expected"] if counts["expected"] else 1.0,
                "precision": counts["tp"] / counts["actual"] if counts["actual"] else 1.0,
            }
            for field, counts in field_counts.items()
        },
        "overall": {
            "tp": total_tp,
            "expected": total_expected,
            "actual": total_actual,
            "recall": total_tp / total_expected if total_expected else 1.0,
            "precision": total_tp / total_actual if total_actual else 1.0,
        },
        "exact": {
            key: {
                "correct": exact[f"{key}_correct"],
                "expected": exact[f"{key}_total"],
                "accuracy": (
                    exact[f"{key}_correct"] / exact[f"{key}_total"]
                    if exact[f"{key}_total"]
                    else 1.0
                ),
            }
            for key in ("date", "value", "unit")
        },
        "treatment_state": {
            "correct": treatment_state_correct,
            "expected": len(expected["treatment_changes"]),
            "accuracy": treatment_state_correct / len(expected["treatment_changes"])
            if expected["treatment_changes"]
            else 1.0,
        },
        "special_scalars": {
            "correct": scalar_correct,
            "expected": scalar_expected,
            "accuracy": scalar_correct / scalar_expected if scalar_expected else 1.0,
        },
        "source_support": {
            "supported": source_supported,
            "total": source_total,
            "rate": source_supported / source_total if source_total else 1.0,
        },
        "critical": {
            "expected": critical_expected,
            "omissions": critical_omissions,
            "recall": (critical_expected - critical_omissions) / critical_expected
            if critical_expected
            else 1.0,
            "unsupported_additions": critical_unsupported,
        },
        "critical_events": {
            "expected": critical_event_expected,
            "omissions": critical_event_omissions,
            "recall": (critical_event_expected - critical_event_omissions) / critical_event_expected
            if critical_event_expected
            else 1.0,
        },
        "unsupported_additions": sum(v["unsupported"] for v in field_counts.values()),
        "must_not_infer_violations": infer_violations,
        "item_hashes": {
            "omitted": sorted(omitted_hashes),
            "unsupported": sorted(unsupported_hashes),
            "violations": sorted(violation_hashes),
        },
    }


def _sum_scores(scores: list[dict]) -> dict:
    fields: dict[str, dict] = {}
    for field in FIELDS:
        counts = {
            key: sum(score["fields"][field][key] for score in scores)
            for key in ("tp", "expected", "actual", "missed", "unsupported")
        }
        fields[field] = {
            **counts,
            "recall": counts["tp"] / counts["expected"] if counts["expected"] else 1.0,
            "precision": counts["tp"] / counts["actual"] if counts["actual"] else 1.0,
        }
    tp = sum(field["tp"] for field in fields.values())
    expected = sum(field["expected"] for field in fields.values())
    actual = sum(field["actual"] for field in fields.values())
    critical_expected = sum(score["critical"]["expected"] for score in scores)
    omissions = sum(score["critical"]["omissions"] for score in scores)
    critical_event_expected = sum(score["critical_events"]["expected"] for score in scores)
    critical_event_omissions = sum(score["critical_events"]["omissions"] for score in scores)
    support_total = sum(score["source_support"]["total"] for score in scores)
    support_ok = sum(score["source_support"]["supported"] for score in scores)
    exact_metrics = {}
    for key in ("date", "value", "unit"):
        total = sum(score["exact"][key]["expected"] for score in scores)
        correct = sum(score["exact"][key]["correct"] for score in scores)
        exact_metrics[f"{key}_accuracy"] = correct / total if total else 1.0
    treatment_total = sum(score["treatment_state"]["expected"] for score in scores)
    treatment_correct = sum(score["treatment_state"]["correct"] for score in scores)
    scalar_total = sum(score["special_scalars"]["expected"] for score in scores)
    scalar_correct = sum(score["special_scalars"]["correct"] for score in scores)
    return {
        "fields": fields,
        "overall_recall": tp / expected if expected else 1.0,
        "overall_precision": tp / actual if actual else 1.0,
        "source_support": support_ok / support_total if support_total else 1.0,
        **exact_metrics,
        "treatment_state_accuracy": (
            treatment_correct / treatment_total if treatment_total else 1.0
        ),
        "special_scalar_accuracy": scalar_correct / scalar_total if scalar_total else 1.0,
        "critical_recall": (critical_expected - omissions) / critical_expected
        if critical_expected
        else 1.0,
        "critical_omissions": omissions,
        "critical_event_recall": (
            (critical_event_expected - critical_event_omissions) / critical_event_expected
            if critical_event_expected
            else 1.0
        ),
        "critical_event_omissions": critical_event_omissions,
        "critical_unsupported_additions": sum(
            score["critical"]["unsupported_additions"] for score in scores
        ),
        "unsupported_additions": sum(score["unsupported_additions"] for score in scores),
        "must_not_infer_violations": sum(score["must_not_infer_violations"] for score in scores),
    }


def _worst_run(run_aggregates: list[dict]) -> dict:
    return {
        "overall_recall": min(run["overall_recall"] for run in run_aggregates),
        "overall_precision": min(run["overall_precision"] for run in run_aggregates),
        "source_support": min(run["source_support"] for run in run_aggregates),
        "date_accuracy": min(run["date_accuracy"] for run in run_aggregates),
        "value_accuracy": min(run["value_accuracy"] for run in run_aggregates),
        "unit_accuracy": min(run["unit_accuracy"] for run in run_aggregates),
        "treatment_state_accuracy": min(run["treatment_state_accuracy"] for run in run_aggregates),
        "special_scalar_accuracy": min(run["special_scalar_accuracy"] for run in run_aggregates),
        "critical_recall": min(run["critical_recall"] for run in run_aggregates),
        "critical_event_recall": min(run["critical_event_recall"] for run in run_aggregates),
        "critical_omissions": max(run["critical_omissions"] for run in run_aggregates),
        "critical_event_omissions": max(run["critical_event_omissions"] for run in run_aggregates),
        "critical_unsupported_additions": max(
            run["critical_unsupported_additions"] for run in run_aggregates
        ),
        "unsupported_additions": max(run["unsupported_additions"] for run in run_aggregates),
        "must_not_infer_violations": max(
            run["must_not_infer_violations"] for run in run_aggregates
        ),
    }


def _baseline_regressions(per_case: list[dict], baseline: dict | None) -> int:
    if not baseline:
        return 0
    previous = {case["id"]: case for case in baseline.get("cases", [])}
    regressions = 0
    for case in per_case:
        old = previous.get(case["id"])
        if old and case["worst"]["critical"]["recall"] < old["worst"]["critical"]["recall"]:
            regressions += 1
    return regressions


def _gate(metrics: dict, thresholds: dict) -> list[str]:
    failures = []
    comparisons = (
        ("critical_omissions", "<=", "max_critical_omissions"),
        ("critical_regressions", "<=", "max_critical_regressions"),
        ("critical_event_recall", ">=", "min_critical_event_recall"),
        ("overall_recall", ">=", "min_overall_recall"),
        ("overall_precision", ">=", "min_overall_precision"),
        ("source_support", ">=", "min_source_support"),
        ("date_accuracy", ">=", "min_date_accuracy"),
        ("value_accuracy", ">=", "min_value_accuracy"),
        ("unit_accuracy", ">=", "min_unit_accuracy"),
        ("treatment_state_accuracy", ">=", "min_treatment_state_accuracy"),
        ("special_scalar_accuracy", ">=", "min_special_scalar_accuracy"),
        ("unsupported_additions", "<=", "max_unsupported_additions"),
        ("critical_unsupported_additions", "<=", "max_critical_unsupported_additions"),
        ("must_not_infer_violations", "<=", "max_must_not_infer_violations"),
    )
    for metric, operator, threshold in comparisons:
        failed = (
            metrics[metric] > thresholds[threshold]
            if operator == "<="
            else metrics[metric] < thresholds[threshold]
        )
        if failed:
            failures.append(
                f"{metric} {metrics[metric]:.6g} not {operator} {thresholds[threshold]:.6g}"
            )
    return failures


def _validate_thresholds(thresholds: dict) -> dict:
    unknown = set(thresholds) - set(DEFAULT_THRESHOLDS)
    _require(not unknown, f"unknown thresholds: {sorted(unknown)}")
    merged = {**DEFAULT_THRESHOLDS, **thresholds}
    for key, value in merged.items():
        _require(
            isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value),
            f"{key} must be finite",
        )
        if key.startswith("min_"):
            _require(0 <= value <= 1, f"{key} must be between 0 and 1")
        else:
            _require(
                isinstance(value, int) and value >= 0,
                f"{key} must be a non-negative integer",
            )
    return merged


def run_evaluation(
    cases: list[dict],
    runner: Callable[[str], dict],
    *,
    runs: int = 3,
    thresholds: dict | None = None,
    timestamp: str | None = None,
    git_commit: str = "unknown",
    git_dirty: bool | None = None,
    source_hashes: dict[str, str] | None = None,
    model_ids: list[str] | None = None,
    config: dict | None = None,
    prompt_hash: str = "unknown",
    baseline: dict | None = None,
    anonymize_case_ids: bool = False,
) -> dict:
    """Run and score all cases. Runner receives text and returns extraction JSON."""
    _require(isinstance(runs, int) and runs >= 1, "runs must be >= 1")
    thresholds = _validate_thresholds(thresholds or {})
    validated = [validate_case(case) for case in cases]
    per_case: list[dict] = []
    all_runs: list[list[dict]] = [[] for _ in range(runs)]
    for case in validated:
        scored_runs = []
        for run_index in range(runs):
            try:
                actual = runner(case["text"])
            except Exception as exc:
                raise RuntimeEvaluationError(
                    f"{case['id']} run {run_index + 1}: {type(exc).__name__}"
                ) from exc
            if not isinstance(actual, dict):
                raise RuntimeEvaluationError(
                    f"{case['id']} run {run_index + 1}: runner returned non-object"
                )
            score = score_extraction(case["expected"], actual, case["text"], case["id"])
            scored_runs.append(score)
            all_runs[run_index].append(score)
        worst_index = min(
            range(runs),
            key=lambda index: (
                scored_runs[index]["critical"]["recall"],
                scored_runs[index]["critical_events"]["recall"],
                scored_runs[index]["overall"]["recall"],
                scored_runs[index]["overall"]["precision"],
                scored_runs[index]["source_support"]["rate"],
                scored_runs[index]["special_scalars"]["accuracy"],
                -scored_runs[index]["critical"]["unsupported_additions"],
                -scored_runs[index]["unsupported_additions"],
            ),
        )
        per_case.append(
            {
                "id": _hash(case["id"])[:16] if anonymize_case_ids else case["id"],
                "source_hash": _hash(case["text"]),
                "runs": scored_runs,
                "worst_run": worst_index + 1,
                "worst": scored_runs[worst_index],
            }
        )
    run_aggregates = [_sum_scores(scores) for scores in all_runs]
    aggregate = _sum_scores([score for scores in all_runs for score in scores])
    worst = _worst_run(run_aggregates)
    regressions = _baseline_regressions(per_case, baseline)
    aggregate["critical_regressions"] = regressions
    worst["critical_regressions"] = regressions
    aggregate_failures = _gate(aggregate, thresholds)
    worst_failures = _gate(worst, thresholds)
    return {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "golden_schema_version": SCHEMA_VERSION,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "git": {"head": git_commit, "dirty": git_dirty},
        "evaluated_source_hashes": dict(sorted((source_hashes or {}).items())),
        "model_ids": model_ids or [],
        "config": config or {},
        "prompt_hash": prompt_hash,
        "run_count": runs,
        "case_count": len(validated),
        "cases": per_case,
        "per_run": run_aggregates,
        "aggregate": aggregate,
        "worst": worst,
        "thresholds": thresholds,
        "failures": {"aggregate": aggregate_failures, "worst": worst_failures},
        "pass": not aggregate_failures and not worst_failures,
    }


def _git_metadata() -> tuple[str, bool | None]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        return head, dirty
    except (OSError, subprocess.SubprocessError):
        return "unknown", None


def _git_commit() -> str:
    return _git_metadata()[0]


def _file_hashes(paths: list[str]) -> str:
    if not paths:
        return "unknown"
    digest = hashlib.sha256()
    for raw_path in sorted(paths):
        path = Path(raw_path)
        if not path.is_file():
            raise ValidationError(f"prompt source does not exist: {path}")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _evaluated_source_hashes(
    golden_directory: str | Path | None, prompt_files: list[str]
) -> dict[str, str]:
    code_paths = (
        "Scripts/eval_harness.py",
        "agent/__init__.py",
        "agent/config.py",
        "agent/intake.py",
        "agent/llm.py",
        "agent/profile.py",
        "agent/provenance.py",
        "agent/schema.py",
    )
    hashes = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in code_paths}
    for module_name, module in sorted(sys.modules.items()):
        if module_name != "agent" and not module_name.startswith("agent."):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        path = Path(module_file).resolve()
        if path.suffix != ".py" or ROOT not in path.parents:
            continue
        key = path.relative_to(ROOT).as_posix()
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    directory = Path(golden_directory).resolve() if golden_directory else SYNTHETIC_DIR.resolve()
    for index, path in enumerate(sorted(directory.glob("*.json"))):
        key = (
            f"eval_cases/synthetic/{path.name}"
            if directory == SYNTHETIC_DIR.resolve()
            else f"private_golden/{index:04d}"
        )
        hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    for index, raw_path in enumerate(prompt_files):
        path = Path(raw_path)
        if not path.is_file():
            raise ValidationError(f"prompt source does not exist: {path}")
        hashes[f"prompt_file/{index:04d}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(hashes.items()))


def _real_runner() -> tuple[Callable[[str], dict], str, list[str]]:
    sys.path.insert(0, str(ROOT))
    import agent
    from agent import config as agent_config
    from agent.intake import INTAKE_SYSTEM_TEMPLATE
    from agent.llm import render_prompt
    from agent.profile import build_patient_context

    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    effective_prompt = render_prompt(
        INTAKE_SYSTEM_TEMPLATE,
        PATIENT_CONTEXT=build_patient_context(copy.deepcopy(profile)),
    )
    prompt_inputs = {
        "system": effective_prompt,
        "user_template": "Extract structured data:\n\n{document}",
        "verification_enabled": agent_config.INTAKE_VERIFY,
        "verification_prompt_code": (
            inspect.getsource(sys.modules[agent.run_intake.__module__]._verify_intake)
            if agent_config.INTAKE_VERIFY
            else None
        ),
    }

    def run(text: str) -> dict:
        original = {
            "DATA_DIR": agent_config.DATA_DIR,
            "PROFILE_PATH": agent_config.PROFILE_PATH,
            "REPORTS_DIR": agent_config.REPORTS_DIR,
        }
        exported_original = {key: getattr(agent, key) for key in original if hasattr(agent, key)}
        isolated_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="net-care-eval-") as isolated:
            isolated_path = Path(isolated)
            agent_config.DATA_DIR = isolated_path
            agent_config.PROFILE_PATH = isolated_path / "patient_profile.json"
            agent_config.REPORTS_DIR = isolated_path / "reports"
            for key in original:
                if hasattr(agent, key):
                    setattr(agent, key, getattr(agent_config, key))
            try:
                _, extracted = agent.run_intake(text, copy.deepcopy(profile))
            finally:
                for key, value in original.items():
                    setattr(agent_config, key, value)
                for key, value in exported_original.items():
                    setattr(agent, key, value)
        if isolated_path.exists():
            raise RuntimeEvaluationError("isolated evaluation storage was not removed")
        return extracted

    prompt_hash = _hash(json.dumps(prompt_inputs, ensure_ascii=False, sort_keys=True))
    return run, prompt_hash, [agent.MODEL_INTAKE]


def _runtime_config() -> dict:
    from agent import config as agent_config

    return {
        "model_intake": agent_config.MODEL_INTAKE,
        "thinking": copy.deepcopy(agent_config.THINKING),
        "intake_verify": agent_config.INTAKE_VERIFY,
        "max_tokens": {"intake": 12000, "verification": 6000},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", default=os.environ.get("GOLDEN_DIR"))
    parser.add_argument(
        "--runs", type=int, default=3, help="repeat each case (use --runs 1 for smoke)"
    )
    parser.add_argument("--artifact", type=Path, default=Path("eval_artifact.json"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--prompt-file", action="append", default=[])
    parser.add_argument(
        "--min-overall-recall", type=float, default=DEFAULT_THRESHOLDS["min_overall_recall"]
    )
    parser.add_argument(
        "--min-overall-precision",
        type=float,
        default=DEFAULT_THRESHOLDS["min_overall_precision"],
    )
    parser.add_argument(
        "--min-source-support", type=float, default=DEFAULT_THRESHOLDS["min_source_support"]
    )
    parser.add_argument(
        "--min-critical-event-recall",
        type=float,
        default=DEFAULT_THRESHOLDS["min_critical_event_recall"],
    )
    parser.add_argument(
        "--min-date-accuracy", type=float, default=DEFAULT_THRESHOLDS["min_date_accuracy"]
    )
    parser.add_argument(
        "--min-value-accuracy", type=float, default=DEFAULT_THRESHOLDS["min_value_accuracy"]
    )
    parser.add_argument(
        "--min-unit-accuracy", type=float, default=DEFAULT_THRESHOLDS["min_unit_accuracy"]
    )
    parser.add_argument(
        "--min-treatment-state-accuracy",
        type=float,
        default=DEFAULT_THRESHOLDS["min_treatment_state_accuracy"],
    )
    parser.add_argument(
        "--min-special-scalar-accuracy",
        type=float,
        default=DEFAULT_THRESHOLDS["min_special_scalar_accuracy"],
    )
    parser.add_argument(
        "--max-unsupported-additions",
        type=int,
        default=DEFAULT_THRESHOLDS["max_unsupported_additions"],
    )
    parser.add_argument(
        "--max-critical-omissions", type=int, default=DEFAULT_THRESHOLDS["max_critical_omissions"]
    )
    parser.add_argument(
        "--max-critical-regressions",
        type=int,
        default=DEFAULT_THRESHOLDS["max_critical_regressions"],
    )
    parser.add_argument(
        "--max-critical-unsupported-additions",
        type=int,
        default=DEFAULT_THRESHOLDS["max_critical_unsupported_additions"],
    )
    parser.add_argument(
        "--max-must-not-infer-violations",
        type=int,
        default=DEFAULT_THRESHOLDS["max_must_not_infer_violations"],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = load_cases(args.golden_dir)
        baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
        thresholds = _validate_thresholds({key: getattr(args, key) for key in DEFAULT_THRESHOLDS})
        try:
            runner, detected_prompt_hash, model_ids = _real_runner()
        except Exception as exc:
            raise RuntimeEvaluationError(
                f"runner initialization failed: {type(exc).__name__}"
            ) from exc
        git_commit, git_dirty = _git_metadata()
        source_hashes = _evaluated_source_hashes(args.golden_dir, args.prompt_file)
        runtime_config = {
            **_runtime_config(),
            "golden_set": "synthetic" if not args.golden_dir else "private",
            "additional_prompt_files_hash": _file_hashes(args.prompt_file),
        }
        artifact = run_evaluation(
            cases,
            runner,
            runs=args.runs,
            thresholds=thresholds,
            git_commit=git_commit,
            git_dirty=git_dirty,
            source_hashes=source_hashes,
            model_ids=model_ids,
            config=runtime_config,
            prompt_hash=detected_prompt_hash,
            baseline=baseline,
            anonymize_case_ids=bool(args.golden_dir),
        )
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(
            json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (ValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        return EXIT_HARNESS
    except RuntimeEvaluationError as exc:
        print(f"RUNTIME ERROR: {exc}", file=sys.stderr)
        return EXIT_RUNTIME
    status = "PASS" if artifact["pass"] else "FAIL"
    print(
        f"{status}: {artifact['case_count']} cases x {artifact['run_count']} runs; "
        f"recall={artifact['aggregate']['overall_recall']:.3f}; "
        f"critical_event_recall={artifact['aggregate']['critical_event_recall']:.3f}; "
        f"source_support={artifact['aggregate']['source_support']:.3f}"
    )
    return EXIT_PASS if artifact["pass"] else EXIT_METRICS


if __name__ == "__main__":
    raise SystemExit(main())
