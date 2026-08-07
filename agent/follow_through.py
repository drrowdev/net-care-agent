"""Durable caregiver follow-through records, validation, CAS, and audit helpers."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import re
import uuid
from typing import Any

from pydantic import ValidationError

from .schema import Alert, CaregiverAction, Visit, now_stamp

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
_TOKEN_EXCLUDED_KEYS = {
    "token",
    "resolve_token",
    "source_token",
    "after_token",
    "result_hash",
    "result_snapshot",
}


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
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def semantic_token(value: Any) -> str:
    """Return a complete semantic compare-and-swap token."""
    return hashlib.sha256(canonical_json(_semantic_value(value)).encode("utf-8")).hexdigest()


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
    return [
        {**action, "source_token": semantic_token(action)}
        for action in projected.get("next_actions") or []
        if isinstance(action, dict)
    ]


def find_summary_action(profile: dict, action_id: str, expected_token: object) -> dict:
    from .profile import summary_is_current

    summary = profile.get("executive_summary")
    if not isinstance(summary, dict) or not summary_is_current(profile):
        raise FollowThroughConflict(
            "The generated assessment is no longer current. Regenerate it before accepting an action."
        )
    projected = copy.deepcopy(summary)
    ensure_summary_action_ids(projected)
    action = next(
        (item for item in projected.get("next_actions") or [] if item.get("id") == action_id),
        None,
    )
    if action is None or semantic_token(action) != str(expected_token or ""):
        raise FollowThroughConflict("The generated action changed. Reload before accepting it.")
    return action


def question_source_token(question: dict) -> str:
    return semantic_token(question)


def find_question(profile: dict, question_id: str, expected_token: object) -> dict:
    question = next(
        (
            item
            for item in profile.get("appointment_questions", [])
            if isinstance(item, dict) and item.get("id") == question_id
        ),
        None,
    )
    if question is None or question_source_token(question) != str(expected_token or ""):
        raise FollowThroughConflict("The question changed. Reload before adding it to a visit.")
    if question.get("source") == "ai":
        if question.get("stale"):
            raise FollowThroughConflict("The generated question is outdated.")
        if str(question.get("source_profile_revision")) != str(profile.get("profile_revision")):
            raise FollowThroughConflict(
                "The generated question is from an older clinical revision."
            )
        if question.get("generation_job_id") != profile.get("questions_generation_id"):
            raise FollowThroughConflict("The generated question was superseded.")
    return question


def request_hash(payload: dict) -> str:
    """Hash every accepted request value, including compare-and-swap tokens."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def iter_audit_events(profile: dict):
    for collection in ("caregiver_actions", "visits", "alerts"):
        for record in profile.get(collection, []) or []:
            if not isinstance(record, dict):
                continue
            for event in record.get("history") or []:
                if isinstance(event, dict):
                    yield collection, record, event


def _safe_result_snapshot(
    endpoint: str,
    target: str,
    snapshot: object,
    *,
    collection: str,
    record: dict,
    event: dict,
) -> bool:
    if not isinstance(snapshot, dict) or "idempotent_replay" in snapshot:
        return False
    if event.get("result_hash") != request_hash(snapshot):
        return False
    if any(
        not isinstance(snapshot.get(field), int) or isinstance(snapshot.get(field), bool)
        for field in ("workflow_revision", "profile_revision")
    ):
        return False

    def valid_item(value: object, model, expected_id: str | None = None) -> bool:
        if not isinstance(value, dict):
            return False
        try:
            model.model_validate(value)
        except ValidationError:
            return False
        return (
            isinstance(value.get("id"), str)
            and bool(value["id"])
            and isinstance(value.get("token"), str)
            and bool(value["token"])
            and (expected_id is None or value["id"] == expected_id)
        )

    def contains_id(value: object, collection_name: str, expected_id: object) -> bool:
        return isinstance(value, dict) and any(
            isinstance(item, dict) and item.get("id") == expected_id
            for item in value.get(collection_name, [])
        )

    if endpoint == "POST /api/follow-ups":
        return (
            collection == "caregiver_actions"
            and set(snapshot) == {"item", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("item"), CaregiverAction, record.get("id"))
        )
    if endpoint == "PATCH /api/follow-ups/<action_id>":
        expected_id = target.removeprefix("caregiver_action:")
        return (
            collection == "caregiver_actions"
            and record.get("id") == expected_id
            and set(snapshot) == {"item", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("item"), CaregiverAction, expected_id)
        )
    if endpoint == "POST /api/visits":
        return (
            collection == "visits"
            and set(snapshot) == {"item", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("item"), Visit, record.get("id"))
        )
    if endpoint == "PATCH /api/visits/<visit_id>":
        expected_id = target.removeprefix("visit:")
        return (
            collection == "visits"
            and record.get("id") == expected_id
            and set(snapshot) == {"item", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("item"), Visit, expected_id)
        )
    if endpoint == "POST /api/visits/<visit_id>/questions":
        visit_id = target.removeprefix("visit:").removesuffix(":questions")
        question_id = (event.get("changes") or {}).get("question_id")
        return (
            collection == "visits"
            and record.get("id") == visit_id
            and set(snapshot) == {"visit", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("visit"), Visit, visit_id)
            and isinstance(question_id, str)
            and contains_id(snapshot.get("visit"), "question_snapshots", question_id)
        )
    if endpoint == "PATCH /api/visits/<visit_id>/questions/<question_id>":
        parts = target.split(":", 2)
        return (
            len(parts) == 3
            and collection == "visits"
            and record.get("id") == parts[1]
            and set(snapshot) == {"visit", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("visit"), Visit, parts[1])
            and contains_id(snapshot.get("visit"), "question_snapshots", parts[2])
        )
    if endpoint == "POST /api/visits/<visit_id>/decisions":
        visit_id = target.removeprefix("visit:").removesuffix(":decisions")
        decision_id = (event.get("changes") or {}).get("decision_id")
        return (
            collection == "visits"
            and record.get("id") == visit_id
            and set(snapshot) == {"visit", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("visit"), Visit, visit_id)
            and isinstance(decision_id, str)
            and contains_id(snapshot.get("visit"), "decisions", decision_id)
        )
    if endpoint == "PATCH /api/visits/<visit_id>/decisions/<decision_id>":
        parts = target.split(":", 2)
        return (
            len(parts) == 3
            and collection == "visits"
            and record.get("id") == parts[1]
            and set(snapshot) == {"visit", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("visit"), Visit, parts[1])
            and contains_id(snapshot.get("visit"), "decisions", parts[2])
        )
    if endpoint == "POST /api/visits/<visit_id>/follow-ups":
        visit_id = target.removeprefix("visit:").removesuffix(":follow-ups")
        follow_up_id = (event.get("changes") or {}).get("follow_up_id")
        return (
            collection == "visits"
            and record.get("id") == visit_id
            and set(snapshot) == {"visit", "item", "workflow_revision", "profile_revision"}
            and valid_item(snapshot.get("visit"), Visit, visit_id)
            and isinstance(follow_up_id, str)
            and valid_item(snapshot.get("item"), CaregiverAction, follow_up_id)
            and snapshot["item"].get("visit_id") == visit_id
            and snapshot["item"].get("decision_id")
            == (event.get("changes") or {}).get("decision_id")
            and follow_up_id in snapshot["visit"].get("follow_up_ids", [])
        )
    if endpoint == "POST /api/alerts/<alert_id>/resolve":
        alert = snapshot.get("alert")
        follow_up = snapshot.get("follow_up")
        expected_resolution = (event.get("changes") or {}).get("resolution")
        follow_up_id = (expected_resolution or {}).get("follow_up_id")
        try:
            Alert.model_validate(alert)
        except ValidationError:
            return False
        return (
            collection == "alerts"
            and record.get("id") == target.removeprefix("alert:")
            and set(snapshot)
            == {"ok", "alert", "follow_up", "workflow_revision", "profile_revision"}
            and snapshot.get("ok") is True
            and isinstance(alert, dict)
            and alert.get("id") == record.get("id")
            and alert.get("resolved") is True
            and isinstance(expected_resolution, dict)
            and alert.get("resolution") == expected_resolution
            and isinstance(alert.get("resolve_token"), str)
            and bool(alert["resolve_token"])
            and (
                (follow_up is None and follow_up_id is None)
                or (
                    isinstance(follow_up_id, str)
                    and valid_item(follow_up, CaregiverAction, follow_up_id)
                )
            )
        )
    return False


def check_idempotency(
    profile: dict,
    mutation_id: str,
    payload: dict,
    *,
    endpoint: str,
    operation: str,
    target: str,
) -> dict | None:
    expected_hash = request_hash(payload)
    for collection, record, event in iter_audit_events(profile):
        if event.get("mutation_id") != mutation_id:
            continue
        identity = (
            event.get("endpoint"),
            event.get("operation"),
            event.get("target"),
            event.get("request_hash"),
        )
        if identity != (endpoint, operation, target, expected_hash):
            raise FollowThroughConflict("mutation_id was already used for a different request")
        snapshot = event.get("result_snapshot")
        if not _safe_result_snapshot(
            endpoint,
            target,
            snapshot,
            collection=collection,
            record=record,
            event=event,
        ):
            raise FollowThroughConflict(
                "mutation_id was already committed without a safely replayable result"
            )
        return copy.deepcopy(snapshot)
    return None


def append_history(
    record: dict,
    *,
    endpoint: str,
    operation: str,
    target: str,
    mutation_id: str,
    payload: dict,
    before_token: str | None,
    changes: dict | None = None,
) -> dict:
    event = {
        "id": new_workflow_id("evt"),
        "mutation_id": mutation_id,
        "endpoint": endpoint,
        "operation": operation,
        "target": target,
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


def _public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_value(item)
            for key, item in value.items()
            if key not in {"result_hash", "result_snapshot"}
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return copy.deepcopy(value)


def public_action(action: dict) -> dict:
    return {**_public_value(action), "token": semantic_token(action)}


def public_visit(visit: dict) -> dict:
    result = _public_value(visit)
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


def public_alert(alert: dict) -> dict:
    from .profile import alert_token

    return {**_public_value(alert), "resolve_token": alert_token(alert)}


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
