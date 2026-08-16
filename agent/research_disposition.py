"""Stable research occurrence identity and durable caregiver workflow projection."""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import re
import uuid
from typing import Any

from pydantic import ValidationError

from .date_input import parse_partial_date
from .follow_through import action_owner_refs, semantic_token
from .schema import (
    CaregiverAction,
    LiteratureWatched,
    ResearchConsideration,
    TrialTracked,
    derive_date_precision,
)

RESEARCH_SAFETY_GUIDANCE = (
    "NET/Care records the research you choose to follow. It does not decide whether "
    "research is relevant, whether someone is eligible for or enrolled in a study, or "
    "whether a treatment is suitable. Confirm clinical questions with the treating team "
    "and trial details with the study site."
)
CAREGIVER_ATTRIBUTION = "Caregiver-entered · unverified"
CLINICIAN_ATTRIBUTION = "Caregiver-entered · attributed to clinician · unverified"
TRIAL_SITE_ATTRIBUTION = "Caregiver-entered · attributed to trial site · unverified"

RESEARCH_ITEM_TYPES = {"trial", "paper"}
RESEARCH_CONSIDERATION_STATUSES = {"open", "closed"}
SHARED_EVENT_TYPES = {
    "caregiver_note",
    "next_step_recorded",
    "treating_team_communication",
}
TRIAL_EVENT_TYPES = SHARED_EVENT_TYPES | {"trial_site_communication"}

MAX_RESEARCH_ITEMS = 2_000
MAX_RESEARCH_CONSIDERATIONS = 1_000
MAX_RESEARCH_EVENTS = 5_000
MAX_RESEARCH_ACTIONS = 1_000
MAX_RESEARCH_AUTHORITY_BYTES = 50_000_000
MAX_RESEARCH_PUBLIC_BYTES = 20_000_000
MAX_RESEARCH_SNAPSHOT_BYTES = 1_500_000
MAX_RESEARCH_TEXT = 100_000

_NCT_RE = re.compile(r"^NCT\d{8}$")
_PMID_RE = re.compile(r"^[1-9]\d{0,8}$")
_RECORD_ID_RE = re.compile(r"^research_(?:trial|paper)_[A-Za-z0-9_-]{16,128}$")

_TRIAL_EXTERNAL_FIELDS = (
    "nct_id",
    "title",
    "status",
    "phase",
    "phases",
    "countries",
    "brief_summary",
    "eligibility_excerpt",
    "registry_last_update",
)
_PAPER_EXTERNAL_FIELDS = ("pmid", "title", "authors", "journal", "date")
_TRIAL_GENERATED_FIELDS = ("eligibility_notes",)
_PAPER_GENERATED_FIELDS = ("relevance_notes",)
_TRIAL_DISCOVERY_FIELDS = ("date_added",)
_PAPER_DISCOVERY_FIELDS = ("query", "date_added")


class ResearchProjectionError(ValueError):
    """Bounded public-safe failure for research authority."""

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
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research data cannot be projected safely.",
        ) from None


def _digest(prefix: str, value: Any, length: int = 32) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()[:length]}"


def new_research_record_id(item_type: str) -> str:
    if item_type not in RESEARCH_ITEM_TYPES:
        raise ValueError("item_type must be trial or paper")
    return f"research_{item_type}_{uuid.uuid4().hex}"


def research_consideration_id(research_record_id: str) -> str:
    return _digest("research_consideration", {"research_record_id": research_record_id})


def new_research_event_id() -> str:
    return f"research_event_{uuid.uuid4().hex}"


def _semantic_legacy_row(row: dict) -> dict:
    return {key: copy.deepcopy(value) for key, value in row.items() if key != "research_record_id"}


def _legacy_identity_base(item_type: str, row: dict) -> str:
    external_id = row.get("nct_id" if item_type == "trial" else "pmid")
    return _canonical(
        {
            "item_type": item_type,
            "source_authority": external_id if isinstance(external_id, str) else None,
            "semantic_row": _semantic_legacy_row(row),
        }
    )


def assign_legacy_research_record_ids(profile: dict) -> None:
    """Add only missing occurrence IDs while preserving every existing value."""

    for item_type, collection in (
        ("trial", "trials_tracked"),
        ("paper", "literature_watched"),
    ):
        rows = profile.get(collection)
        if not isinstance(rows, list):
            continue
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("research_record_id"):
                continue
            grouped.setdefault(_legacy_identity_base(item_type, row), []).append(row)
        for base, identical_rows in grouped.items():
            for occurrence, row in enumerate(identical_rows):
                row["research_record_id"] = _digest(
                    f"research_{item_type}",
                    {"base": base, "occurrence": occurrence},
                )


def canonical_external_id(item_type: str, row: dict) -> str | None:
    value = row.get("nct_id" if item_type == "trial" else "pmid")
    if not isinstance(value, str):
        return None
    pattern = _NCT_RE if item_type == "trial" else _PMID_RE
    return value if pattern.fullmatch(value) else None


def research_source_key(item_type: str, row: dict) -> str | None:
    external_id = canonical_external_id(item_type, row)
    if external_id is None:
        return None
    return f"{'ctgov' if item_type == 'trial' else 'pubmed'}:{external_id}"


def canonical_research_url(item_type: str, row: dict) -> str | None:
    external_id = canonical_external_id(item_type, row)
    if external_id is None:
        return None
    if item_type == "trial":
        return f"https://clinicaltrials.gov/study/{external_id}"
    return f"https://pubmed.ncbi.nlm.nih.gov/{external_id}/"


def _copy_allowlisted(row: dict, fields: tuple[str, ...]) -> dict:
    return {field: copy.deepcopy(row[field]) for field in fields if field in row}


def split_research_authority(item_type: str, row: dict) -> dict[str, dict]:
    if item_type == "trial":
        external = _copy_allowlisted(row, _TRIAL_EXTERNAL_FIELDS)
        generated = _copy_allowlisted(row, _TRIAL_GENERATED_FIELDS)
        discovery = _copy_allowlisted(row, _TRIAL_DISCOVERY_FIELDS)
    elif item_type == "paper":
        external = _copy_allowlisted(row, _PAPER_EXTERNAL_FIELDS)
        generated = _copy_allowlisted(row, _PAPER_GENERATED_FIELDS)
        discovery = _copy_allowlisted(row, _PAPER_DISCOVERY_FIELDS)
    else:
        raise ValueError("item_type must be trial or paper")
    return {
        "external_facts": external,
        "generated_context": generated,
        "discovery_provenance": discovery,
    }


def capture_research_snapshot(item_type: str, row: dict) -> dict:
    record_id = row.get("research_record_id")
    source_key = research_source_key(item_type, row)
    if not isinstance(record_id, str) or not _RECORD_ID_RE.fullmatch(record_id):
        raise ResearchProjectionError(
            "research_item_not_actionable",
            "This research occurrence does not have stable authority.",
        )
    if source_key is None:
        raise ResearchProjectionError(
            "research_item_not_actionable",
            "This research occurrence does not have a validated source identifier.",
        )
    split = split_research_authority(item_type, row)
    snapshot = {
        "item_type": item_type,
        "research_record_id": record_id,
        "source_key": source_key,
        **split,
    }
    if len(_canonical(snapshot).encode("utf-8")) > MAX_RESEARCH_SNAPSHOT_BYTES:
        raise ResearchProjectionError(
            "research_snapshot_too_large",
            "This research occurrence exceeds the supported shortlist limits.",
        )
    return snapshot


def validate_research_text(
    value: object,
    field: str,
    *,
    limit: int,
    optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    if not value.strip():
        if optional:
            return None
        raise ValueError(f"{field} is required")
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value


def validate_research_date(value: object) -> tuple[str | None, str]:
    if value is None:
        return None, "unknown"
    stored = parse_partial_date(value, optional=True)
    return stored, derive_date_precision(stored)


def allowed_research_event_types(item_type: str) -> list[str]:
    values = TRIAL_EVENT_TYPES if item_type == "trial" else SHARED_EVENT_TYPES
    return sorted(values)


def research_event_provenance(event_type: str) -> dict[str, str]:
    if event_type == "treating_team_communication":
        return {
            "capture_method": "caregiver_entered",
            "attributed_to": "clinician",
            "source_verification": "unverified",
            "label": CLINICIAN_ATTRIBUTION,
        }
    if event_type == "trial_site_communication":
        return {
            "capture_method": "caregiver_entered",
            "attributed_to": "trial_site",
            "source_verification": "unverified",
            "label": TRIAL_SITE_ATTRIBUTION,
        }
    return {
        "capture_method": "caregiver_entered",
        "source_verification": "unverified",
        "label": CAREGIVER_ATTRIBUTION,
    }


def build_research_event(item_type: str, data: dict) -> dict:
    event_type = data.get("event_type")
    if event_type not in allowed_research_event_types(item_type):
        raise ValueError("event_type is not allowed for this research item")
    occurred_on, precision = validate_research_date(data.get("occurred_on"))
    note = validate_research_text(data.get("note"), "note", limit=20_000)
    who = validate_research_text(data.get("who"), "who", limit=500, optional=True)
    context = validate_research_text(data.get("context"), "context", limit=2_000, optional=True)
    return {
        "id": new_research_event_id(),
        "event_type": event_type,
        "note": note,
        "who": who,
        "context": context,
        "occurred_on": occurred_on,
        "occurred_on_precision": precision,
        "provenance": research_event_provenance(event_type),
        "recorded_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def research_origin_action_ids(profile: dict) -> set[str]:
    return {
        action.get("id")
        for action in profile.get("caregiver_actions", [])
        if isinstance(action, dict)
        and isinstance(action.get("id"), str)
        and isinstance(action.get("origin_snapshot"), dict)
        and action["origin_snapshot"].get("kind") == "research_consideration"
    }


def linked_research_action_ids(profile: dict) -> set[str]:
    return {
        item.get("caregiver_action_id")
        for item in profile.get("research_considerations", [])
        if isinstance(item, dict) and isinstance(item.get("caregiver_action_id"), str)
    }


def excluded_research_action_ids_for_model(profile: dict) -> set[str]:
    return research_origin_action_ids(profile) | linked_research_action_ids(profile)


def _validate_nested_authority(value: Any) -> None:
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 200_000 or depth > 16:
            raise ResearchProjectionError(
                "research_projection_too_large",
                "Research authority exceeds the supported projection limits.",
            )
        if isinstance(current, str):
            if len(current) > MAX_RESEARCH_TEXT:
                raise ResearchProjectionError(
                    "research_projection_too_large",
                    "Research authority exceeds the supported projection limits.",
                )
        elif isinstance(current, dict):
            if len(current) > 5_000 or any(
                not isinstance(key, str) or len(key) > 500 for key in current
            ):
                raise ResearchProjectionError(
                    "research_projection_too_large",
                    "Research authority exceeds the supported projection limits.",
                )
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            if len(current) > 20_000:
                raise ResearchProjectionError(
                    "research_projection_too_large",
                    "Research authority exceeds the supported projection limits.",
                )
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, float):
            _canonical(current)
        elif current is not None and not isinstance(current, bool | int):
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research data cannot be projected safely.",
            )


def _public_action(action: dict) -> dict:
    return {
        "id": action["id"],
        "token": semantic_token(action),
        "text": action.get("text"),
        "status": action.get("status"),
        "owner": action.get("owner"),
        "due_date": action.get("due_date"),
    }


def _public_event(event: dict) -> dict:
    return {
        "id": event.get("id"),
        "token": semantic_token(event),
        "event_type": event.get("event_type"),
        "note": event.get("note"),
        "who": event.get("who"),
        "context": event.get("context"),
        "occurred_on": event.get("occurred_on"),
        "occurred_on_precision": event.get("occurred_on_precision"),
        "provenance": copy.deepcopy(event.get("provenance")),
        "recorded_at": event.get("recorded_at"),
    }


def _public_history(history: list[dict]) -> list[dict]:
    return [
        {
            "operation": event.get("operation"),
            "at": event.get("at"),
            "changes": copy.deepcopy(event.get("changes") or {}),
        }
        for event in history
    ]


def _latest_membership(profile: dict, item_type: str) -> set[str]:
    latest = profile.get("latest_research_update")
    field = "trial_ids" if item_type == "trial" else "paper_ids"
    values = latest.get(field) if isinstance(latest, dict) else None
    return {value for value in values or [] if isinstance(value, str)}


def _relevant_import_authority(profile: dict) -> list[dict]:
    result = []
    for receipt in profile.get("document_imports", []):
        if not isinstance(receipt, dict):
            continue
        changes = [
            copy.deepcopy(change)
            for change in receipt.get("changes", [])
            if isinstance(change, dict) and change.get("category") in {"trials", "papers"}
        ]
        if changes:
            result.append(
                {
                    "status": receipt.get("status"),
                    "receipt_revision": receipt.get("receipt_revision"),
                    "changes": changes,
                }
            )
    return result


def _project_item(
    item_type: str,
    row: dict,
    *,
    latest_membership: set[str],
    considerations_by_record: dict[str, dict],
) -> dict:
    record_id = row["research_record_id"]
    source_key = research_source_key(item_type, row)
    split = split_research_authority(item_type, row)
    snapshot_size = None
    if source_key is not None:
        snapshot_size = len(
            _canonical(
                {
                    "item_type": item_type,
                    "research_record_id": record_id,
                    "source_key": source_key,
                    **split,
                }
            ).encode("utf-8")
        )
    consideration = considerations_by_record.get(record_id)
    if consideration is not None:
        shortlist = {"eligible": False, "reason": "already_shortlisted"}
    elif source_key is None:
        shortlist = {"eligible": False, "reason": "missing_or_invalid_source_id"}
    elif snapshot_size is not None and snapshot_size > MAX_RESEARCH_SNAPSHOT_BYTES:
        shortlist = {"eligible": False, "reason": "snapshot_too_large"}
    else:
        shortlist = {"eligible": True, "reason": None}
    external_id = canonical_external_id(item_type, row)
    return {
        "id": record_id,
        "token": semantic_token(row),
        "item_type": item_type,
        "source_identity": {
            "external_id": row.get("nct_id" if item_type == "trial" else "pmid"),
            "source_key": source_key,
            "authority": "validated" if source_key else "missing_or_invalid",
        },
        **split,
        "external_url": canonical_research_url(item_type, row),
        "latest_batch_member": external_id in latest_membership if external_id else False,
        "shortlist": shortlist,
        "consideration_id": consideration.get("id") if consideration else None,
    }


def _project_consideration(
    consideration: dict,
    *,
    items_by_id: dict[str, tuple[str, dict]],
    actions: dict[str, dict],
) -> dict:
    record_id = consideration["research_record_id"]
    current = items_by_id.get(record_id)
    snapshot = consideration["snapshot"]
    current_split = split_research_authority(*current) if current is not None else None
    current_state = {
        "occurrence": "present" if current is not None else "missing",
        "external_facts": (
            "unchanged"
            if current_split is not None
            and _canonical(current_split["external_facts"])
            == _canonical(snapshot["external_facts"])
            else "changed"
            if current_split is not None
            else "unavailable"
        ),
        "generated_context": (
            "unchanged"
            if current_split is not None
            and _canonical(current_split["generated_context"])
            == _canonical(snapshot["generated_context"])
            else "changed"
            if current_split is not None
            else "unavailable"
        ),
        "discovery_provenance": (
            "unchanged"
            if current_split is not None
            and _canonical(current_split["discovery_provenance"])
            == _canonical(snapshot["discovery_provenance"])
            else "changed"
            if current_split is not None
            else "unavailable"
        ),
    }
    action_id = consideration.get("caregiver_action_id")
    action = actions.get(action_id) if isinstance(action_id, str) else None
    status = consideration["status"]
    event_types = allowed_research_event_types(consideration["item_type"])
    follow_up_variants = ["unlink"] if action is not None else ["link_existing", "create_and_link"]
    return {
        "id": consideration["id"],
        "token": semantic_token(consideration),
        "item_type": consideration["item_type"],
        "research_record_id": record_id,
        "source_key": consideration["source_key"],
        "status": status,
        "snapshot": copy.deepcopy(snapshot),
        "current_state": current_state,
        "events": [_public_event(event) for event in consideration["events"]],
        "history": _public_history(consideration["history"]),
        "follow_up": _public_action(action) if action is not None else None,
        "eligibility": {
            "close": {
                "eligible": status == "open",
                "reason": None if status == "open" else "closed",
            },
            "resume": {
                "eligible": status == "closed",
                "reason": None if status == "closed" else "already_open",
            },
            "allowed_event_types": event_types,
            "follow_up_variants": follow_up_variants,
        },
        "created_at": consideration["created_at"],
        "updated_at": consideration["updated_at"],
        "closed_at": consideration.get("closed_at"),
    }


def project_research_workspace(profile: dict) -> dict:
    """Project complete bounded research and caregiver workflow authority."""

    for revision_name in ("profile_revision", "workflow_revision"):
        revision = profile.get(revision_name)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research projection authority is inconsistent.",
            )
    trials = profile.get("trials_tracked")
    papers = profile.get("literature_watched")
    considerations = profile.get("research_considerations")
    actions_list = profile.get("caregiver_actions")
    imports = profile.get("document_imports")
    if any(
        not isinstance(value, list)
        for value in (trials, papers, considerations, actions_list, imports)
    ) or any(
        not isinstance(row, dict)
        for rows in (trials, papers, considerations, actions_list, imports)
        for row in rows
    ):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research data cannot be projected safely.",
        )
    if (
        len(trials) + len(papers) > MAX_RESEARCH_ITEMS
        or len(considerations) > MAX_RESEARCH_CONSIDERATIONS
        or len(actions_list) > MAX_RESEARCH_ACTIONS
    ):
        raise ResearchProjectionError(
            "research_projection_too_large",
            "Research data exceeds the supported projection limits.",
        )
    event_count = sum(
        len(item.get("events", []))
        if isinstance(item.get("events"), list)
        else MAX_RESEARCH_EVENTS + 1
        for item in considerations
    )
    if event_count > MAX_RESEARCH_EVENTS:
        raise ResearchProjectionError(
            "research_projection_too_large",
            "Research event data exceeds the supported projection limits.",
        )
    for value in (*trials, *papers, *considerations, *actions_list, *imports):
        _validate_nested_authority(value)

    rows_with_types = [("trial", row) for row in trials] + [("paper", row) for row in papers]
    for item_type, row in rows_with_types:
        try:
            (TrialTracked if item_type == "trial" else LiteratureWatched).model_validate(row)
        except ValidationError:
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research row authority is inconsistent.",
            ) from None
    record_ids = [row.get("research_record_id") for _, row in rows_with_types]
    if any(
        not isinstance(value, str) or not _RECORD_ID_RE.fullmatch(value) for value in record_ids
    ) or len(set(record_ids)) != len(record_ids):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research occurrence identity is missing or inconsistent.",
        )
    action_ids = [item.get("id") for item in actions_list]
    if any(not isinstance(value, str) or not value for value in action_ids) or len(
        set(action_ids)
    ) != len(action_ids):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research follow-up authority is inconsistent.",
        )
    consideration_ids = [item.get("id") for item in considerations]
    consideration_record_ids = [item.get("research_record_id") for item in considerations]
    if (
        any(not isinstance(value, str) or not value for value in consideration_ids)
        or len(set(consideration_ids)) != len(consideration_ids)
        or any(not isinstance(value, str) or not value for value in consideration_record_ids)
        or len(set(consideration_record_ids)) != len(consideration_record_ids)
    ):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research consideration identity is inconsistent.",
        )

    items_by_id = {
        row["research_record_id"]: (item_type, row) for item_type, row in rows_with_types
    }
    actions = {action["id"]: action for action in actions_list}
    considerations_by_record = {item["research_record_id"]: item for item in considerations}
    for action in actions_list:
        try:
            CaregiverAction.model_validate(action)
        except ValidationError:
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research follow-up authority is inconsistent.",
            ) from None
    for item in considerations:
        events = item.get("events")
        history = item.get("history")
        snapshot = item.get("snapshot")
        try:
            ResearchConsideration.model_validate(item)
        except ValidationError:
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research consideration authority is inconsistent.",
            ) from None
        if (
            item.get("item_type") not in RESEARCH_ITEM_TYPES
            or item.get("status") not in RESEARCH_CONSIDERATION_STATUSES
            or item.get("id") != research_consideration_id(item["research_record_id"])
            or not isinstance(snapshot, dict)
            or snapshot.get("item_type") != item.get("item_type")
            or snapshot.get("research_record_id") != item.get("research_record_id")
            or snapshot.get("source_key") != item.get("source_key")
            or not isinstance(snapshot.get("external_facts"), dict)
            or not isinstance(snapshot.get("generated_context"), dict)
            or not isinstance(snapshot.get("discovery_provenance"), dict)
            or research_source_key(item["item_type"], snapshot["external_facts"])
            != item.get("source_key")
            or isinstance(item.get("source_profile_revision"), bool)
            or not isinstance(item.get("source_profile_revision"), int)
            or item["source_profile_revision"] < 0
            or set(snapshot)
            != {
                "item_type",
                "research_record_id",
                "source_key",
                "external_facts",
                "generated_context",
                "discovery_provenance",
            }
            or not isinstance(events, list)
            or any(not isinstance(event, dict) for event in events)
            or not isinstance(history, list)
            or any(not isinstance(event, dict) for event in history)
            or (
                item.get("caregiver_action_id") is not None
                and item.get("caregiver_action_id") not in actions
            )
            or (
                item["research_record_id"] in items_by_id
                and items_by_id[item["research_record_id"]][0] != item["item_type"]
            )
        ):
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research consideration authority is inconsistent.",
            )
        if len(_canonical(snapshot).encode("utf-8")) > MAX_RESEARCH_SNAPSHOT_BYTES:
            raise ResearchProjectionError(
                "research_projection_too_large",
                "Research snapshot authority exceeds the supported limits.",
            )
        event_ids = [event.get("id") for event in events]
        if (
            any(not isinstance(event_id, str) or not event_id for event_id in event_ids)
            or len(set(event_ids)) != len(event_ids)
            or any(
                event.get("event_type") not in allowed_research_event_types(item["item_type"])
                or event.get("provenance") != research_event_provenance(event.get("event_type"))
                or not isinstance(event.get("note"), str)
                or not event["note"].strip()
                or len(event["note"]) > 20_000
                or (
                    event.get("who") is not None
                    and (
                        not isinstance(event.get("who"), str)
                        or not event["who"].strip()
                        or len(event["who"]) > 500
                    )
                )
                or (
                    event.get("context") is not None
                    and (
                        not isinstance(event.get("context"), str)
                        or not event["context"].strip()
                        or len(event["context"]) > 2_000
                    )
                )
                or derive_date_precision(event.get("occurred_on"))
                != event.get("occurred_on_precision")
                or (
                    event.get("occurred_on") is not None
                    and event.get("occurred_on_precision") == "unknown"
                )
                or not isinstance(event.get("recorded_at"), str)
                or not event["recorded_at"]
                for event in events
            )
        ):
            raise ResearchProjectionError(
                "research_projection_invalid",
                "Research event authority is inconsistent.",
            )

    linked_research_actions = [
        item.get("caregiver_action_id")
        for item in considerations
        if isinstance(item.get("caregiver_action_id"), str)
    ]
    if len(linked_research_actions) != len(set(linked_research_actions)):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research follow-up authority is inconsistent.",
        )
    symptom_actions = {
        item.get("caregiver_action_id")
        for item in profile.get("symptom_episodes", [])
        if isinstance(item, dict) and isinstance(item.get("caregiver_action_id"), str)
    }
    treatment_actions = {
        item.get("caregiver_action_id")
        for item in profile.get("treatment_discrepancies", [])
        if isinstance(item, dict) and isinstance(item.get("caregiver_action_id"), str)
    }
    if set(linked_research_actions) & (symptom_actions | treatment_actions):
        raise ResearchProjectionError(
            "research_projection_invalid",
            "Research follow-up authority is inconsistent.",
        )

    projected_items = [
        _project_item(
            item_type,
            row,
            latest_membership=_latest_membership(profile, item_type),
            considerations_by_record=considerations_by_record,
        )
        for item_type, row in rows_with_types
    ]
    projected_considerations = [
        _project_consideration(item, items_by_id=items_by_id, actions=actions)
        for item in considerations
    ]
    eligible_actions = [
        _public_action(action)
        for action in actions_list
        if action.get("status") in {"open", "in_progress"}
        and not action_owner_refs(profile, action["id"])
    ]
    relevant_imports = _relevant_import_authority(profile)
    authority = {
        "items": rows_with_types,
        "considerations": considerations,
        "actions": actions_list,
        "latest_research_update": profile.get("latest_research_update"),
        "imports": relevant_imports,
    }
    if len(_canonical(authority).encode("utf-8")) > MAX_RESEARCH_AUTHORITY_BYTES:
        raise ResearchProjectionError(
            "research_projection_too_large",
            "Research authority exceeds the supported projection limits.",
        )
    revisions = {
        "profile_revision": profile["profile_revision"],
        "workflow_revision": profile["workflow_revision"],
    }
    manifest = {
        **revisions,
        "items": [{"id": item["id"], "token": item["token"]} for item in projected_items],
        "considerations": [
            {"id": item["id"], "token": item["token"]} for item in projected_considerations
        ],
        "eligible_actions": [
            {"id": item["id"], "token": item["token"]} for item in eligible_actions
        ],
        "latest_token": semantic_token(profile.get("latest_research_update")),
        "import_token": semantic_token(relevant_imports),
        "safety_guidance": RESEARCH_SAFETY_GUIDANCE,
    }
    projection = {
        **revisions,
        "projection_token": _digest("research_projection", manifest),
        "item_count": len(projected_items),
        "consideration_count": len(projected_considerations),
        "items": projected_items,
        "considerations": projected_considerations,
        "eligible_actions": eligible_actions,
        "attribution_labels": {
            "caregiver": CAREGIVER_ATTRIBUTION,
            "clinician": CLINICIAN_ATTRIBUTION,
            "trial_site": TRIAL_SITE_ATTRIBUTION,
        },
        "authority_labels": {
            "external_facts": "External registry or bibliographic facts",
            "generated_context": (
                "Machine-generated compatibility context · not relevance, eligibility, "
                "enrollment, suitability, or recommendation"
            ),
            "discovery_provenance": "Research discovery provenance",
            "caregiver_workflow": "Caregiver-maintained shortlist and disposition workflow",
        },
        "safety_guidance": {
            "kind": "fixed_non_clinical",
            "text": RESEARCH_SAFETY_GUIDANCE,
        },
    }
    if len(_canonical(projection).encode("utf-8")) > MAX_RESEARCH_PUBLIC_BYTES:
        raise ResearchProjectionError(
            "research_projection_too_large",
            "Research data exceeds the supported projection limits.",
        )
    return projection


def research_replay_response_is_safe(snapshot: object, expected_id: str) -> bool:
    """Reject replay snapshots with fields outside the bounded public contract."""

    if not isinstance(snapshot, dict) or set(snapshot) != {
        "consideration",
        "workflow_revision",
        "profile_revision",
    }:
        return False
    if any(
        not isinstance(snapshot.get(field), int) or isinstance(snapshot.get(field), bool)
        for field in ("workflow_revision", "profile_revision")
    ):
        return False
    item = snapshot.get("consideration")
    if not isinstance(item, dict) or item.get("id") != expected_id:
        return False
    if set(item) != {
        "id",
        "token",
        "item_type",
        "research_record_id",
        "source_key",
        "status",
        "snapshot",
        "current_state",
        "events",
        "history",
        "follow_up",
        "eligibility",
        "created_at",
        "updated_at",
        "closed_at",
    }:
        return False
    item_type = item.get("item_type")
    saved = item.get("snapshot")
    if (
        item_type not in RESEARCH_ITEM_TYPES
        or item.get("status") not in RESEARCH_CONSIDERATION_STATUSES
        or not isinstance(item.get("token"), str)
        or not item["token"]
        or not isinstance(saved, dict)
        or set(saved)
        != {
            "item_type",
            "research_record_id",
            "source_key",
            "external_facts",
            "generated_context",
            "discovery_provenance",
        }
        or saved.get("item_type") != item_type
        or saved.get("research_record_id") != item.get("research_record_id")
        or saved.get("source_key") != item.get("source_key")
        or not isinstance(saved.get("external_facts"), dict)
        or not isinstance(saved.get("generated_context"), dict)
        or not isinstance(saved.get("discovery_provenance"), dict)
        or set(saved["external_facts"])
        - set(_TRIAL_EXTERNAL_FIELDS if item_type == "trial" else _PAPER_EXTERNAL_FIELDS)
        or set(saved["generated_context"])
        - set(_TRIAL_GENERATED_FIELDS if item_type == "trial" else _PAPER_GENERATED_FIELDS)
        or set(saved["discovery_provenance"])
        - set(_TRIAL_DISCOVERY_FIELDS if item_type == "trial" else _PAPER_DISCOVERY_FIELDS)
        or research_source_key(item_type, saved["external_facts"]) != item.get("source_key")
    ):
        return False
    try:
        model = TrialTracked if item_type == "trial" else LiteratureWatched
        model.model_validate(
            {
                "research_record_id": item.get("research_record_id"),
                **saved["external_facts"],
                **saved["generated_context"],
                **saved["discovery_provenance"],
            }
        )
        if len(_canonical(saved).encode("utf-8")) > MAX_RESEARCH_SNAPSHOT_BYTES:
            return False
    except (ValidationError, ResearchProjectionError):
        return False
    current_state = item.get("current_state")
    if (
        not isinstance(current_state, dict)
        or set(current_state)
        != {
            "occurrence",
            "external_facts",
            "generated_context",
            "discovery_provenance",
        }
        or current_state.get("occurrence") not in {"present", "missing"}
        or any(
            current_state.get(field) not in {"unchanged", "changed", "unavailable"}
            for field in ("external_facts", "generated_context", "discovery_provenance")
        )
    ):
        return False
    events = item.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or set(event)
        != {
            "id",
            "token",
            "event_type",
            "note",
            "who",
            "context",
            "occurred_on",
            "occurred_on_precision",
            "provenance",
            "recorded_at",
        }
        or not isinstance(event.get("id"), str)
        or not isinstance(event.get("token"), str)
        or event.get("event_type") not in allowed_research_event_types(item_type)
        or event.get("provenance") != research_event_provenance(event.get("event_type"))
        or not isinstance(event.get("note"), str)
        or not isinstance(event.get("recorded_at"), str)
        for event in events
    ):
        return False
    history = item.get("history")
    allowed_history_changes = {
        "created": {"status"},
        "event_recorded": {"event_id", "event_type"},
        "closed": {"status"},
        "resumed": {"status"},
        "follow_up_changed": {"caregiver_action_id"},
    }
    if not isinstance(history, list) or any(
        not isinstance(event, dict)
        or set(event) != {"operation", "at", "changes"}
        or event.get("operation") not in allowed_history_changes
        or not isinstance(event.get("at"), str)
        or not isinstance(event.get("changes"), dict)
        or set(event["changes"]) != allowed_history_changes[event["operation"]]
        for event in history
    ):
        return False
    follow_up = item.get("follow_up")
    if follow_up is not None and (
        not isinstance(follow_up, dict)
        or set(follow_up) != {"id", "token", "text", "status", "owner", "due_date"}
        or not isinstance(follow_up.get("id"), str)
        or not isinstance(follow_up.get("token"), str)
    ):
        return False
    eligibility = item.get("eligibility")
    if (
        not isinstance(eligibility, dict)
        or set(eligibility) != {"close", "resume", "allowed_event_types", "follow_up_variants"}
        or not isinstance(eligibility.get("close"), dict)
        or set(eligibility["close"]) != {"eligible", "reason"}
        or not isinstance(eligibility.get("resume"), dict)
        or set(eligibility["resume"]) != {"eligible", "reason"}
        or eligibility.get("allowed_event_types") != allowed_research_event_types(item_type)
        or not isinstance(eligibility.get("follow_up_variants"), list)
    ):
        return False
    try:
        return len(_canonical(snapshot).encode("utf-8")) <= MAX_RESEARCH_PUBLIC_BYTES
    except ResearchProjectionError:
        return False
