"""Durable caregiver follow-through records, validation, CAS, and audit helpers."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import re
import uuid
from typing import Any

from .schema import now_stamp

ACTION_STATUSES = {"open", "in_progress", "completed", "cancelled"}
VISIT_STATUSES = {"planned", "in_progress", "completed", "cancelled"}
DECISION_STATUSES = {"active", "superseded", "retracted", "needs_confirmation"}
OUTCOME_KINDS = {"administrative", "caregiver_reported", "clinician_attributed"}
ORIGIN_KINDS = {"manual", "executive_summary_action", "alert", "visit_decision"}
_MUTATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_DIRECT_TREATMENT_RE = re.compile(
    r"^\s*(?:start|stop|hold|pause|resume|switch|increase|decrease|administer|take|skip|"
    r"discontinue|withhold)\b",
    re.IGNORECASE,
)
_TOKEN_EXCLUDED_KEYS = {"token", "resolve_token", "source_token", "after_token"}


class FollowThroughError(ValueError):
    """Base error for invalid follow-through mutations."""


class FollowThroughConflict(FollowThroughError):
    """The addressed target or idempotency record changed."""


def _semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_value(item)
            for key, item in value.items()
            if key not in _TOKEN_EXCLUDED_KEYS
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _semantic_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def semantic_token(value: Any) -> str:
    """Return a complete semantic compare-and-swap token."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def new_workflow_id(prefix: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,15}", prefix):
        raise ValueError("Invalid workflow ID prefix")
    return f"{prefix}_{uuid.uuid4().hex}"


def validate_mutation_id(value: object) -> str:
    mutation_id = str(value or "").strip()
    if not _MUTATION_ID_RE.fullmatch(mutation_id):
        raise FollowThroughError(
            "mutation_id must be 8-128 ASCII letters, numbers, or . _ : - characters"
        )
    return mutation_id


def validate_text(value: object, field: str, *, limit: int = 1000) -> str:
    if not isinstance(value, str):
        raise FollowThroughError(f"{field} must be text")
    text = value.strip()
    if not text:
        raise FollowThroughError(f"{field} is required")
    if len(text) > limit:
        raise FollowThroughError(f"{field} must be at most {limit} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise FollowThroughError(f"{field} contains unsupported control characters")
    return text


def validate_optional_text(
    value: object,
    field: str,
    *,
    limit: int,
    single_line: bool = False,
) -> str | None:
    if value in (None, ""):
        return None
    text = validate_text(value, field, limit=limit)
    if single_line and ("\n" in text or "\r" in text):
        raise FollowThroughError(f"{field} must be a single line")
    return text


def validate_owner(value: object) -> str | None:
    return validate_optional_text(value, "owner", limit=100, single_line=True)


def validate_date(value: object, field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise FollowThroughError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise FollowThroughError(f"{field} must be YYYY-MM-DD") from exc
    return parsed.isoformat()


def validate_follow_up_text(value: object) -> str:
    text = validate_text(value, "text", limit=1000)
    if _DIRECT_TREATMENT_RE.search(text):
        raise FollowThroughError(
            "Follow-ups must use contact, ask, discuss, or confirm wording with the treating team"
        )
    return text


def validate_status(value: object, allowed: set[str], field: str = "status") -> str:
    status = str(value or "").strip()
    if status not in allowed:
        raise FollowThroughError(f"Invalid {field}")
    return status


def validate_expected_token(record: dict, expected_token: object) -> None:
    token = str(expected_token or "")
    if not token:
        raise FollowThroughError("expected_token is required")
    if semantic_token(record) != token:
        raise FollowThroughConflict("The record changed. Reload before trying again.")


def summary_action_id(action: dict, summary_revision: object, index: int) -> str:
    canonical = canonical_json({key: value for key, value in action.items() if key != "id"})
    digest = hashlib.sha256(f"{summary_revision}:{index}:{canonical}".encode()).hexdigest()[:24]
    return f"sumact_{digest}"


def ensure_summary_action_ids(summary: dict) -> dict:
    """Assign deterministic IDs to generated summary actions in place."""
    revision = summary.get("summary_revision")
    for index, action in enumerate(summary.get("next_actions") or []):
        if isinstance(action, dict) and not action.get("id"):
            action["id"] = summary_action_id(action, revision, index)
    return summary


def project_summary_actions(summary: dict) -> list[dict]:
    projected = copy.deepcopy(summary)
    ensure_summary_action_ids(projected)
    actions = []
    for action in projected.get("next_actions") or []:
        if not isinstance(action, dict):
            continue
        source = {
            **action,
            "source_profile_revision": projected.get("summary_revision"),
            "generation_id": projected.get("generation_id"),
            "stale": projected.get("stale") is not False,
        }
        source["source_token"] = semantic_token(source)
        actions.append(source)
    return actions


def validate_current_generated_source(
    source: dict,
    expected_token: object,
    *,
    current_profile_revision: object,
    current_generation_id: object,
    generation_field: str,
    changed_message: str,
    stale_message: str,
) -> None:
    """Require an exact, explicitly current generated-source projection."""
    source_id = source.get("id")
    token = str(expected_token or "")
    if (
        not isinstance(source_id, str)
        or not source_id.strip()
        or not token
        or semantic_token(source) != token
    ):
        raise FollowThroughConflict(changed_message)

    generation_id = source.get(generation_field)
    if (
        source.get("stale") is not False
        or not isinstance(current_generation_id, str)
        or not current_generation_id.strip()
        or not isinstance(generation_id, str)
        or not generation_id.strip()
        or generation_id != current_generation_id
        or source.get("source_profile_revision") is None
        or str(source.get("source_profile_revision")) != str(current_profile_revision)
    ):
        raise FollowThroughConflict(stale_message)


def find_summary_action(profile: dict, action_id: str, expected_token: object) -> dict:
    from .profile import summary_is_current

    summary = profile.get("executive_summary")
    if not isinstance(summary, dict) or not summary_is_current(profile):
        raise FollowThroughConflict(
            "The generated assessment is no longer current. Regenerate it before accepting an action."
        )
    projected = project_summary_actions(summary)
    action = next(
        (item for item in projected if item.get("id") == action_id),
        None,
    )
    if action is None:
        raise FollowThroughConflict("The generated action changed. Reload before accepting it.")
    validate_current_generated_source(
        action,
        expected_token,
        current_profile_revision=profile.get("profile_revision"),
        current_generation_id=summary.get("generation_id"),
        generation_field="generation_id",
        changed_message="The generated action changed. Reload before accepting it.",
        stale_message=(
            "The generated assessment is no longer current. Regenerate it before accepting an action."
        ),
    )
    return action


def question_source_token(question: dict) -> str:
    return semantic_token(question)


def project_question(profile: dict, stored: dict) -> dict:
    """Project one question with freshness derived from current server identity."""
    question = copy.deepcopy(stored)
    if question.get("source") == "ai":
        generation_id = question.get("generation_job_id")
        current_generation_id = profile.get("questions_generation_id")
        current_revision = profile.get("profile_revision")
        if (
            question.get("stale") is not False
            or not isinstance(question.get("id"), str)
            or not question["id"].strip()
            or not isinstance(current_generation_id, str)
            or not current_generation_id.strip()
            or not isinstance(generation_id, str)
            or not generation_id.strip()
            or generation_id != current_generation_id
            or question.get("source_profile_revision") is None
            or str(question.get("source_profile_revision")) != str(current_revision)
        ):
            question["stale"] = True
            question["stale_reason"] = (
                question.get("stale_reason") or "missing_or_superseded_generation_provenance"
            )
        else:
            question["stale"] = False
    question["source_token"] = question_source_token(question)
    return question


def find_question(profile: dict, question_id: str, expected_token: object) -> dict:
    question = next(
        (
            item
            for item in profile.get("appointment_questions", [])
            if isinstance(item, dict) and item.get("id") == question_id
        ),
        None,
    )
    if question is None:
        raise FollowThroughConflict("The question changed. Reload before adding it to a visit.")
    projected = project_question(profile, question)
    if question.get("source") == "ai":
        validate_current_generated_source(
            projected,
            expected_token,
            current_profile_revision=profile.get("profile_revision"),
            current_generation_id=profile.get("questions_generation_id"),
            generation_field="generation_job_id",
            changed_message="The question changed. Reload before adding it to a visit.",
            stale_message="The generated question is outdated.",
        )
    elif question_source_token(projected) != str(expected_token or ""):
        raise FollowThroughConflict("The question changed. Reload before adding it to a visit.")
    return question


def request_hash(payload: dict) -> str:
    return semantic_token(payload)


def iter_audit_events(profile: dict):
    for collection in ("caregiver_actions", "visits", "alerts"):
        for record in profile.get(collection, []) or []:
            if not isinstance(record, dict):
                continue
            for event in record.get("history") or []:
                if isinstance(event, dict):
                    yield collection, record, event


def check_idempotency(profile: dict, mutation_id: str, payload: dict) -> tuple[str, dict] | None:
    expected_hash = request_hash(payload)
    for collection, record, event in iter_audit_events(profile):
        if event.get("mutation_id") != mutation_id:
            continue
        if event.get("request_hash") != expected_hash:
            raise FollowThroughConflict("mutation_id was already used for a different request")
        return collection, record
    return None


def append_history(
    record: dict,
    *,
    operation: str,
    mutation_id: str,
    payload: dict,
    before_token: str | None,
    changes: dict | None = None,
) -> dict:
    event = {
        "id": new_workflow_id("evt"),
        "mutation_id": mutation_id,
        "operation": operation,
        "at": now_stamp(),
        "request_hash": request_hash(payload),
        "before_token": before_token,
        "after_token": None,
        "changes": copy.deepcopy(changes or {}),
    }
    record.setdefault("history", []).append(event)
    event["after_token"] = semantic_token(record)
    return event


def increment_workflow_revision(profile: dict) -> int:
    revision = int(profile.get("workflow_revision") or 0) + 1
    profile["workflow_revision"] = revision
    return revision


def invalidate_generated_context(profile: dict, reason: str) -> None:
    profile["summary_stale"] = True
    if isinstance(profile.get("executive_summary"), dict):
        profile["executive_summary"]["stale"] = True
    timestamp = now_stamp()
    for question in profile.get("appointment_questions", []):
        if question.get("source") == "ai" and not question.get("stale"):
            question["stale"] = True
            question["stale_reason"] = reason
            question["stale_at"] = timestamp


def public_action(action: dict) -> dict:
    return {**copy.deepcopy(action), "token": semantic_token(action)}


def public_visit(visit: dict) -> dict:
    result = copy.deepcopy(visit)
    result["token"] = semantic_token(visit)
    for question in result.get("question_snapshots") or []:
        source = next(
            (
                item
                for item in visit.get("question_snapshots") or []
                if item.get("id") == question.get("id")
            ),
            {},
        )
        question["token"] = semantic_token(source)
    for decision in result.get("decisions") or []:
        source = next(
            (item for item in visit.get("decisions") or [] if item.get("id") == decision.get("id")),
            {},
        )
        decision["token"] = semantic_token(source)
    return result


def find_record(records: list[dict], record_id: str, label: str) -> dict:
    record = next((item for item in records if item.get("id") == record_id), None)
    if record is None:
        raise KeyError(f"{label} not found")
    return record


def action_transition_allowed(current: str, target: str) -> bool:
    return target in {
        "open": {"open", "in_progress", "completed", "cancelled"},
        "in_progress": {"in_progress", "open", "completed", "cancelled"},
        "completed": {"completed"},
        "cancelled": {"cancelled"},
    }.get(current, set())


def visit_transition_allowed(current: str, target: str) -> bool:
    return target in {
        "planned": {"planned", "in_progress", "completed", "cancelled"},
        "in_progress": {"in_progress", "planned", "completed", "cancelled"},
        "completed": {"completed"},
        "cancelled": {"cancelled"},
    }.get(current, set())


def clinical_outcome(outcome: dict | None) -> bool:
    return bool(outcome and outcome.get("kind") in {"caregiver_reported", "clinician_attributed"})


def capture_provenance() -> dict:
    return {
        "capture_method": "caregiver_entered",
        "attributed_to": "clinician",
        "source_verification": "unverified",
    }
