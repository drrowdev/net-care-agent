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
RECAP_MAX_ITEMS = 200
RECAP_CLINICIAN_PROVENANCE = "Caregiver-entered · attributed to clinician · unverified"
RECAP_CAREGIVER_PROVENANCE = "Caregiver-entered · caregiver reported · unverified"
RECAP_ADMIN_PROVENANCE = "Caregiver-entered administrative outcome · not clinical evidence"
RECAP_GENERATED_QUESTION_PROVENANCE = "Generated question snapshot · not clinician-attributed"
RECAP_MANUAL_QUESTION_PROVENANCE = "Manual caregiver question"
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


class RecapIntegrityError(FollowThroughConflict):
    """Persisted recap authority is malformed and cannot be exported."""


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
    """Hash every accepted request value, including compare-and-swap tokens."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def iter_audit_events(profile: dict):
    for collection in (
        "caregiver_actions",
        "visits",
        "alerts",
        "symptom_episodes",
        "treatment_courses",
        "treatment_discrepancies",
    ):
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
    if endpoint == "PATCH /api/visits/<visit_id>/questions/order":
        visit_id = target.removeprefix("visit:").removesuffix(":question_order")
        expected_order = ((event.get("changes") or {}).get("order") or {}).get("after")
        visit = snapshot.get("visit")
        return (
            collection == "visits"
            and record.get("id") == visit_id
            and set(snapshot) == {"visit", "workflow_revision", "profile_revision"}
            and valid_item(visit, Visit, visit_id)
            and isinstance(expected_order, list)
            and all(isinstance(item, str) and item for item in expected_order)
            and len(set(expected_order)) == len(expected_order)
            and isinstance(visit, dict)
            and [
                question.get("id") if isinstance(question, dict) else None
                for question in visit.get("question_snapshots", [])
            ]
            == expected_order
            and [
                question.get("order") if isinstance(question, dict) else None
                for question in visit.get("question_snapshots", [])
            ]
            == list(range(len(expected_order)))
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
    if endpoint in {
        "POST /api/symptom-episodes",
        "PATCH /api/symptom-episodes/<episode_id>",
        "POST /api/symptom-episodes/<episode_id>/resolve",
        "PATCH /api/symptom-episodes/<episode_id>/follow-up",
    }:
        episode = snapshot.get("episode")
        follow_up = snapshot.get("follow_up")
        if endpoint == "POST /api/symptom-episodes":
            expected_id = record.get("id")
        else:
            expected_id = target.removeprefix("symptom_episode:").removesuffix(":follow_up")
        episode_keys = {
            "id",
            "token",
            "status",
            "symptom_text",
            "severity",
            "reported_subject",
            "timing_text",
            "frequency_text",
            "triggers_text",
            "notes",
            "onset",
            "resolution",
            "provenance",
            "follow_up",
            "created_at",
            "updated_at",
        }
        severity = episode.get("severity") if isinstance(episode, dict) else None
        onset = episode.get("onset") if isinstance(episode, dict) else None
        resolution = episode.get("resolution") if isinstance(episode, dict) else None

        def valid_date(value: object) -> bool:
            return (
                isinstance(value, dict)
                and set(value) == {"value", "precision", "kind"}
                and value.get("precision") in {"day", "month", "year", "unknown"}
                and value.get("kind") in {"caregiver_entered", "unknown"}
                and (value.get("value") is None or isinstance(value.get("value"), str))
            )

        valid_episode = (
            collection == "symptom_episodes"
            and record.get("id") == expected_id
            and isinstance(episode, dict)
            and set(episode) == episode_keys
            and episode.get("id") == expected_id
            and isinstance(episode.get("token"), str)
            and bool(episode["token"])
            and episode.get("status") in {"current", "resolved"}
            and isinstance(episode.get("symptom_text"), str)
            and bool(episode["symptom_text"])
            and episode.get("reported_subject") in {"patient", "caregiver", "unspecified"}
            and isinstance(severity, dict)
            and set(severity) == {"level", "detail", "authority"}
            and severity.get("level") in {None, "mild", "moderate", "severe"}
            and (severity.get("detail") is None or isinstance(severity.get("detail"), str))
            and severity.get("authority") == "caregiver_entered_unverified"
            and valid_date(onset)
            and (
                resolution is None
                or (
                    isinstance(resolution, dict)
                    and set(resolution) == {"value", "precision", "kind", "recorded_at"}
                    and valid_date(
                        {
                            "value": resolution.get("value"),
                            "precision": resolution.get("precision"),
                            "kind": resolution.get("kind"),
                        }
                    )
                    and isinstance(resolution.get("recorded_at"), str)
                )
            )
            and episode.get("provenance")
            == {
                "status": "caregiver_entered_unverified",
                "label": "Caregiver-entered · unverified",
            }
            and episode.get("follow_up") == follow_up
        )
        if not valid_episode or set(snapshot) != {
            "episode",
            "follow_up",
            "workflow_revision",
            "profile_revision",
        }:
            return False
        changes = event.get("changes")
        if not isinstance(changes, dict):
            return False
        link_change = changes.get("caregiver_action_id")
        if link_change is not None:
            if (
                not isinstance(link_change, dict)
                or set(link_change) != {"before", "after"}
                or (
                    link_change.get("after") is not None
                    and (not isinstance(link_change.get("after"), str) or not link_change["after"])
                )
            ):
                return False
            linked_id = link_change.get("after")
        else:
            linked_id = follow_up.get("id") if isinstance(follow_up, dict) else None
        if linked_id is None:
            return follow_up is None
        return (
            isinstance(follow_up, dict)
            and follow_up.get("id") == linked_id
            and isinstance(follow_up.get("token"), str)
            and bool(follow_up["token"])
            and isinstance(follow_up.get("text"), str)
            and follow_up.get("status") in ACTION_STATUSES
            and set(follow_up) == {"id", "token", "text", "status", "owner", "due_date"}
        )
    if endpoint in {
        "POST /api/treatment-reconciliation/courses",
        "PATCH /api/treatment-reconciliation/courses/<course_id>",
        "POST /api/treatment-reconciliation/courses/<course_id>/transition",
        "POST /api/treatment-reconciliation/courses/<course_id>/restart",
    }:
        course = snapshot.get("course")
        expected_id = (
            record.get("id")
            if endpoint
            in {
                "POST /api/treatment-reconciliation/courses",
                "POST /api/treatment-reconciliation/courses/<course_id>/restart",
            }
            else target.removeprefix("treatment_course:")
        )
        if not (
            collection == "treatment_courses"
            and isinstance(course, dict)
            and course.get("id") == expected_id
            and isinstance(course.get("token"), str)
            and bool(course["token"])
            and set(snapshot) == {"course", "workflow_revision", "profile_revision"}
        ):
            return False
        from .treatment_reconciliation import treatment_replay_response_is_safe

        return treatment_replay_response_is_safe(
            snapshot,
            expected_id=expected_id,
            discrepancy=False,
        )
    if endpoint in {
        "POST /api/treatment-reconciliation/discrepancies",
        "POST /api/treatment-reconciliation/discrepancies/<id>/resolve",
        "POST /api/treatment-reconciliation/discrepancies/<id>/reopen",
        "PATCH /api/treatment-reconciliation/discrepancies/<id>/follow-up",
    }:
        discrepancy = snapshot.get("discrepancy")
        expected_id = (
            record.get("id")
            if endpoint == "POST /api/treatment-reconciliation/discrepancies"
            else target.removeprefix("treatment_discrepancy:").removesuffix(":follow_up")
        )
        if not (
            collection == "treatment_discrepancies"
            and isinstance(discrepancy, dict)
            and discrepancy.get("id") == expected_id
            and isinstance(discrepancy.get("token"), str)
            and bool(discrepancy["token"])
            and set(snapshot)
            == {
                "discrepancy",
                "course",
                "follow_up",
                "workflow_revision",
                "profile_revision",
            }
        ):
            return False
        from .treatment_reconciliation import treatment_replay_response_is_safe

        return treatment_replay_response_is_safe(
            snapshot,
            expected_id=expected_id,
            discrepancy=True,
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


def _recap_text(value: object, field: str, *, limit: int, optional: bool = False) -> str | None:
    if value in (None, "") and optional:
        return None
    if not isinstance(value, str) or not value:
        raise RecapIntegrityError(f"{field} is unavailable for recap")
    if len(value) > limit:
        raise RecapIntegrityError(f"{field} exceeds the safe recap limit")
    if any((ord(char) < 32 and char not in "\n\t\r") or ord(char) == 127 for char in value):
        raise RecapIntegrityError(f"{field} contains unsupported control characters")
    return value


def _recap_id(value: object, field: str) -> str:
    text = _recap_text(value, field, limit=128)
    assert text is not None
    if "\n" in text or "\r" in text:
        raise RecapIntegrityError(f"{field} must be a single line")
    return text


def _recap_optional_id(value: object, field: str) -> str | None:
    if value in (None, ""):
        return None
    return _recap_id(value, field)


def _recap_records(value: object, field: str) -> list[dict]:
    if not isinstance(value, list):
        raise RecapIntegrityError(f"{field} is unavailable for recap")
    if any(not isinstance(item, dict) for item in value):
        raise RecapIntegrityError(f"{field} contains an invalid recap record")
    return value


def _recap_items(value: object, field: str) -> list[dict]:
    records = _recap_records(value, field)
    if len(records) > RECAP_MAX_ITEMS:
        raise RecapIntegrityError(f"{field} exceeds the safe recap limit")
    return records


def _recap_ids(value: object, field: str) -> set[str]:
    if not isinstance(value, list):
        raise RecapIntegrityError(f"{field} is unavailable for recap")
    if len(value) > RECAP_MAX_ITEMS:
        raise RecapIntegrityError(f"{field} exceeds the safe recap limit")
    ids = [_recap_id(item, f"{field}[]") for item in value]
    if len(ids) != len(set(ids)):
        raise RecapIntegrityError(f"{field} contains duplicate recap links")
    return set(ids)


def _recap_provenance(value: object, field: str) -> dict:
    if not isinstance(value, dict) or not value:
        raise RecapIntegrityError(f"{field} is unavailable for recap")
    if len(value) > 20:
        raise RecapIntegrityError(f"{field} exceeds the safe recap limit")
    provenance = {}
    for key, item in value.items():
        safe_key = _recap_id(key, f"{field}.key")
        provenance[safe_key] = _recap_text(item, f"{field}.{safe_key}", limit=500)
    return provenance


def _recap_authority_entry(
    kind: str,
    record: dict,
    record_id: str,
    lifecycle: str,
    *,
    links: dict | None = None,
    provenance: dict | None = None,
    source: dict | None = None,
) -> dict:
    entry = {
        "kind": kind,
        "id": record_id,
        "authority_token": semantic_token(record),
        "lifecycle": lifecycle,
    }
    if links:
        entry["links"] = links
    if provenance:
        entry["provenance"] = provenance
    if source:
        entry["source"] = source
    return entry


def _recap_action_source(action: dict) -> dict:
    origin = action.get("origin_snapshot")
    if not isinstance(origin, dict):
        raise RecapIntegrityError("follow_up.origin_snapshot is unavailable for recap")
    kind = origin.get("kind")
    if kind not in ORIGIN_KINDS:
        raise RecapIntegrityError("follow_up.origin_snapshot.kind is unavailable for recap")
    source = {
        "kind": kind,
        "source_id": _recap_optional_id(
            origin.get("source_id"), "follow_up.origin_snapshot.source_id"
        ),
        "source_job_id": _recap_optional_id(
            origin.get("source_job_id"), "follow_up.origin_snapshot.source_job_id"
        ),
        "generation_id": _recap_optional_id(
            origin.get("generation_id"), "follow_up.origin_snapshot.generation_id"
        ),
    }
    revision = origin.get("source_profile_revision")
    if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool)):
        raise RecapIntegrityError(
            "follow_up.origin_snapshot.source_profile_revision is unavailable for recap"
        )
    if revision is not None:
        source["source_profile_revision"] = revision
    _recap_text(origin.get("text"), "follow_up.origin_snapshot.text", limit=1000)
    if not isinstance(origin.get("snapshot", {}), dict):
        raise RecapIntegrityError("follow_up.origin_snapshot.snapshot is unavailable for recap")
    return {key: value for key, value in source.items() if value is not None}


def recap_outcome_projection(outcome: object, field: str, *, flat: bool = False) -> dict | None:
    if outcome is None:
        return None
    if not isinstance(outcome, dict):
        raise RecapIntegrityError(f"{field} is unavailable for recap")
    if flat:
        outcome_present = any(
            key in outcome for key in ("outcome_kind", "outcome_text", "provenance")
        )
        if not outcome_present:
            return None
        kind = outcome.get("outcome_kind")
        text = outcome.get("outcome_text")
        recorded_at = outcome.get("resolved_at")
    else:
        if not outcome:
            raise RecapIntegrityError(f"{field} is unavailable for recap")
        kind = outcome.get("kind")
        text = outcome.get("text")
        recorded_at = outcome.get("recorded_at")
    if kind not in OUTCOME_KINDS:
        raise RecapIntegrityError(f"{field}.kind is unavailable for recap")
    if text in (None, ""):
        raise RecapIntegrityError(f"{field}.text is unavailable for recap")
    _recap_provenance(outcome.get("provenance"), f"{field}.provenance")
    if recorded_at in (None, ""):
        raise RecapIntegrityError(f"{field}.recorded_at is unavailable for recap")
    projected = {
        "kind": kind,
        "text": _recap_text(text, f"{field}.text", limit=4000),
        "provenance_label": {
            "clinician_attributed": RECAP_CLINICIAN_PROVENANCE,
            "caregiver_reported": RECAP_CAREGIVER_PROVENANCE,
            "administrative": RECAP_ADMIN_PROVENANCE,
        }[kind],
        "recorded_at": _recap_text(recorded_at, f"{field}.recorded_at", limit=80),
    }
    return projected


def project_visit_recap_with_authority(profile: dict, visit: dict) -> tuple[dict, dict]:
    """Build a bounded recap and its private canonical authority manifest."""
    visit_id = _recap_id(visit.get("id"), "visit.id")
    visit_status = visit.get("status")
    if visit_status not in VISIT_STATUSES:
        raise RecapIntegrityError("visit.status is unavailable for recap")
    visit_links = {
        "source_appointment_id": _recap_optional_id(
            visit.get("source_appointment_id"), "visit.source_appointment_id"
        )
    }
    authority = {
        "visit": _recap_authority_entry(
            "visit",
            visit,
            visit_id,
            visit_status,
            links={key: value for key, value in visit_links.items() if value is not None},
        ),
        "questions": [],
        "decisions": [],
        "follow_ups": [],
        "resolved_alerts": [],
    }
    details = {
        "id": visit_id,
        "title": _recap_text(visit.get("title"), "visit.title", limit=200),
        "date": _recap_text(visit.get("date"), "visit.date", limit=40, optional=True),
        "time": _recap_text(visit.get("time"), "visit.time", limit=40, optional=True),
        "clinician": _recap_text(
            visit.get("clinician"), "visit.clinician", limit=200, optional=True
        ),
        "location": _recap_text(visit.get("location"), "visit.location", limit=300, optional=True),
        "status": visit_status,
    }
    details = {key: value for key, value in details.items() if value is not None}
    if visit_status == "planned":
        return (
            {
                "state": "unavailable",
                "exportable": False,
                "visit": details,
                "sections": {},
            },
            authority,
        )
    if visit_status == "cancelled":
        return (
            {
                "state": "administrative",
                "exportable": False,
                "visit": details,
                "sections": {},
            },
            authority,
        )

    questions = _recap_items(visit.get("question_snapshots", []), "visit.question_snapshots")
    for question in questions:
        order = question.get("order", 0)
        if not isinstance(order, int) or isinstance(order, bool) or not 0 <= order <= 10000:
            raise RecapIntegrityError("question.order is unavailable for recap")
        if not isinstance(question.get("pinned", False), bool):
            raise RecapIntegrityError("question.pinned is unavailable for recap")
        _recap_text(question.get("created_at"), "question.created_at", limit=80)
    questions = sorted(
        questions,
        key=lambda item: (
            not bool(item.get("pinned")),
            item.get("order", 0),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )
    asked = []
    heard = []
    unresolved = []
    question_ids = set()
    for question in questions:
        question_id = _recap_id(question.get("id"), "question.id")
        if question_id in question_ids:
            raise RecapIntegrityError("visit.question_snapshots contains duplicate recap IDs")
        question_ids.add(question_id)
        question_text = _recap_text(question.get("text"), "question.text", limit=1000)
        source_kind = question.get("source_kind")
        if source_kind not in {"manual", "generated"}:
            raise RecapIntegrityError("question.source_kind is unavailable for recap")
        source_label = (
            RECAP_GENERATED_QUESTION_PROVENANCE
            if source_kind == "generated"
            else RECAP_MANUAL_QUESTION_PROVENANCE
        )
        answer = question.get("answer")
        answer_status = "not_recorded"
        answer_provenance = None
        if answer is None:
            unresolved.append(
                {
                    "kind": "not_recorded",
                    "item_id": question_id,
                    "text": question_text,
                    "provenance_label": source_label,
                }
            )
        else:
            if not isinstance(answer, dict) or answer.get("status") not in {
                "answered",
                "unknown",
            }:
                raise RecapIntegrityError("question.answer is unavailable for recap")
            answer_status = answer["status"]
            answer_provenance = _recap_provenance(
                answer.get("provenance"), "question.answer.provenance"
            )
            _recap_text(answer.get("recorded_at"), "question.answer.recorded_at", limit=80)
            asked.append(
                {
                    "id": question_id,
                    "text": question_text,
                    "status": answer_status,
                    "provenance_label": source_label,
                }
            )
            if answer_status == "unknown":
                if answer.get("text") not in (None, ""):
                    raise RecapIntegrityError(
                        "question.answer.text must be empty when the answer is unknown"
                    )
                unresolved.append(
                    {
                        "kind": "unknown",
                        "item_id": question_id,
                        "text": question_text,
                        "provenance_label": RECAP_CLINICIAN_PROVENANCE,
                    }
                )
            else:
                heard.append(
                    {
                        "question_id": question_id,
                        "question": question_text,
                        "text": _recap_text(answer.get("text"), "question.answer.text", limit=4000),
                        "provenance_label": RECAP_CLINICIAN_PROVENANCE,
                    }
                )
        question_links = {
            "source_kind": source_kind,
            "source_question_id": _recap_optional_id(
                question.get("source_question_id"), "question.source_question_id"
            ),
            "source_generation_id": _recap_optional_id(
                question.get("source_generation_id"), "question.source_generation_id"
            ),
        }
        source_revision = question.get("source_profile_revision")
        if source_revision is not None and (
            not isinstance(source_revision, int) or isinstance(source_revision, bool)
        ):
            raise RecapIntegrityError("question.source_profile_revision is unavailable for recap")
        if source_revision is not None:
            question_links["source_profile_revision"] = source_revision
        authority["questions"].append(
            _recap_authority_entry(
                "question",
                question,
                question_id,
                answer_status,
                links={key: value for key, value in question_links.items() if value is not None},
                provenance=answer_provenance,
            )
        )

    all_decisions = _recap_items(visit.get("decisions", []), "visit.decisions")
    decisions = []
    decision_ids = set()
    for decision in all_decisions:
        decision_id = _recap_id(decision.get("id"), "decision.id")
        if decision_id in decision_ids:
            raise RecapIntegrityError("visit.decisions contains duplicate recap IDs")
        decision_ids.add(decision_id)
        decision_status = decision.get("status")
        if decision_status not in DECISION_STATUSES:
            raise RecapIntegrityError("decision.status is unavailable for recap")
        if decision_status in {"superseded", "retracted"}:
            continue
        decision_provenance = _recap_provenance(decision.get("provenance"), "decision.provenance")
        supersedes_id = _recap_optional_id(decision.get("supersedes_id"), "decision.supersedes_id")
        decisions.append(
            {
                "id": decision_id,
                "text": _recap_text(decision.get("text"), "decision.text", limit=4000),
                "status": decision_status,
                "provenance_label": RECAP_CLINICIAN_PROVENANCE,
                "_created_at": _recap_text(
                    decision.get("created_at"), "decision.created_at", limit=80
                ),
            }
        )
        authority["decisions"].append(
            _recap_authority_entry(
                "decision",
                decision,
                decision_id,
                decision_status,
                links={"supersedes_id": supersedes_id} if supersedes_id else None,
                provenance=decision_provenance,
            )
        )
    decisions.sort(key=lambda item: (item.pop("_created_at"), item["id"]))
    authority["decisions"].sort(key=lambda item: item["id"])

    visit_follow_up_ids = _recap_ids(visit.get("follow_up_ids", []), "visit.follow_up_ids")
    actions = _recap_records(profile.get("caregiver_actions", []), "caregiver_actions")
    follow_ups = []
    action_ids = set()
    for action in actions:
        if action.get("visit_id") != visit_id and action.get("id") not in visit_follow_up_ids:
            continue
        action_id = _recap_id(action.get("id"), "follow_up.id")
        if action_id in action_ids:
            raise RecapIntegrityError("visit follow-ups contain duplicate recap IDs")
        action_ids.add(action_id)
        status = action.get("status")
        if status not in ACTION_STATUSES:
            raise RecapIntegrityError("follow_up.status is unavailable for recap")
        links = {
            "visit_id": _recap_optional_id(action.get("visit_id"), "follow_up.visit_id"),
            "decision_id": _recap_optional_id(action.get("decision_id"), "follow_up.decision_id"),
            "alert_id": _recap_optional_id(action.get("alert_id"), "follow_up.alert_id"),
        }
        if links["visit_id"] not in (None, visit_id):
            raise RecapIntegrityError("follow_up contains an invalid recap link shape")
        if links["decision_id"] and links["decision_id"] not in decision_ids:
            raise RecapIntegrityError("follow_up contains an invalid recap link shape")
        source = _recap_action_source(action)
        outcome = recap_outcome_projection(action.get("outcome"), "follow_up.outcome")
        if (status in {"completed", "cancelled"}) != (outcome is not None):
            raise RecapIntegrityError("follow_up outcome does not match its recap lifecycle")
        outcome_provenance = (
            _recap_provenance(action["outcome"].get("provenance"), "follow_up.outcome.provenance")
            if outcome is not None
            else None
        )
        projected = {
            "id": action_id,
            "text": _recap_text(action.get("text"), "follow_up.text", limit=1000),
            "status": status,
            "owner": _recap_text(action.get("owner"), "follow_up.owner", limit=100, optional=True),
            "due_date": _recap_text(
                action.get("due_date"), "follow_up.due_date", limit=40, optional=True
            ),
            "decision_id": links["decision_id"],
            "alert_id": links["alert_id"],
            "outcome": outcome,
            "_created_at": _recap_text(action.get("created_at"), "follow_up.created_at", limit=80),
        }
        follow_ups.append({key: value for key, value in projected.items() if value is not None})
        authority["follow_ups"].append(
            _recap_authority_entry(
                "follow_up",
                action,
                action_id,
                status,
                links={key: value for key, value in links.items() if value is not None},
                provenance=outcome_provenance,
                source=source,
            )
        )
        if len(follow_ups) > RECAP_MAX_ITEMS:
            raise RecapIntegrityError("visit follow-ups exceed the safe recap limit")
    follow_ups.sort(key=lambda item: (item.pop("_created_at"), item["id"]))
    authority["follow_ups"].sort(key=lambda item: item["id"])
    follow_up_ids = {item["id"] for item in follow_ups}

    alerts = _recap_records(profile.get("alerts", []), "alerts")
    related_alerts = []
    alert_ids = set()
    for alert in alerts:
        resolution = alert.get("resolution")
        if not isinstance(resolution, dict):
            continue
        if not (
            resolution.get("visit_id") == visit_id
            or resolution.get("decision_id") in decision_ids
            or resolution.get("follow_up_id") in follow_up_ids
        ):
            continue
        if alert.get("resolved") is not True or resolution.get("status") != "resolved":
            raise RecapIntegrityError("alert resolution lifecycle is unavailable for recap")
        links = {
            "visit_id": _recap_optional_id(resolution.get("visit_id"), "alert.resolution.visit_id"),
            "decision_id": _recap_optional_id(
                resolution.get("decision_id"), "alert.resolution.decision_id"
            ),
            "follow_up_id": _recap_optional_id(
                resolution.get("follow_up_id"), "alert.resolution.follow_up_id"
            ),
        }
        if links["follow_up_id"] and (links["visit_id"] or links["decision_id"]):
            raise RecapIntegrityError("alert resolution contains an invalid recap link shape")
        if links["decision_id"] and not links["visit_id"]:
            raise RecapIntegrityError("alert resolution contains an invalid recap link shape")
        alert_id = _recap_id(alert.get("id"), "alert.id")
        if alert_id in alert_ids:
            raise RecapIntegrityError("related alerts contain duplicate recap IDs")
        alert_ids.add(alert_id)
        outcome = recap_outcome_projection(resolution, "alert.resolution", flat=True)
        outcome_provenance = (
            _recap_provenance(resolution.get("provenance"), "alert.resolution.provenance")
            if outcome is not None
            else None
        )
        projected = {
            "id": alert_id,
            "resolved_at": _recap_text(
                resolution.get("resolved_at"),
                "alert.resolution.resolved_at",
                limit=80,
            ),
            "visit_id": links["visit_id"],
            "decision_id": links["decision_id"],
            "follow_up_id": links["follow_up_id"],
            "outcome": outcome,
        }
        related_alerts.append({key: value for key, value in projected.items() if value is not None})
        authority["resolved_alerts"].append(
            _recap_authority_entry(
                "resolved_alert",
                alert,
                alert_id,
                "resolved",
                links={key: value for key, value in links.items() if value is not None},
                provenance=outcome_provenance,
            )
        )
        if len(related_alerts) > RECAP_MAX_ITEMS:
            raise RecapIntegrityError("related alerts exceed the safe recap limit")
    related_alerts.sort(key=lambda item: (item.get("resolved_at") or "", item["id"]))
    authority["resolved_alerts"].sort(key=lambda item: item["id"])

    sections = {
        "what_was_asked": asked,
        "what_we_heard": heard,
        "decisions": decisions,
        "follow_ups": follow_ups,
        "related_resolved_alerts": related_alerts,
        "unresolved": unresolved,
    }
    recap = {
        "state": "current",
        "exportable": True,
        "visit": details,
        "sections": {key: value for key, value in sections.items() if value},
    }
    return recap, authority


def project_visit_recap(profile: dict, visit: dict) -> dict:
    """Build one bounded, read-only recap from authoritative workflow records."""
    recap, _authority = project_visit_recap_with_authority(profile, visit)
    return recap


def public_alert(alert: dict) -> dict:
    from .profile import alert_token

    result = {
        key: _public_value(alert[key])
        for key in (
            "id",
            "date",
            "priority",
            "message",
            "action_required",
            "resolved",
            "dependency_kind",
            "resolution",
            "added_at",
        )
        if key in alert
    }
    result["resolve_token"] = alert_token(alert)
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
