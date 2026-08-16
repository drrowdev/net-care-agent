from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
GUIDANCE = (
    "NET/Care records what you enter but does not verify treatment details or advise "
    "starting, stopping, or changing treatment. Confirm treatment decisions with the "
    "treating team."
)
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _treatment_source() -> str:
    start = APP_JS.index("const TREATMENT_SAFETY_GUIDANCE")
    end = APP_JS.index("// ── Init", start)
    return APP_JS[start:end]


def _source(character: str, text: str = "Exact source treatment wording") -> dict:
    ref = f"txref_{character * 64}"
    return {
        "ref": ref,
        "token": f"source-token-{character}",
        "observed_text": text,
        "record_value": {"exact": "", "nullable": None},
        "operation": "added",
        "review_state": "accepted",
        "receipt_state": "applied",
        "provenance": {
            "status": "source_verified",
            "label": "Exact source",
            "source_url": (f"/api/patient/treatment-reconciliation/source-facts/{ref}/source"),
            "evidence_url": (f"/api/patient/treatment-reconciliation/source-facts/{ref}/evidence"),
        },
    }


def _source_document(character: str, **overrides: object) -> dict:
    return {
        "ref": f"txref_{character * 64}",
        "filename": f"visit-summary-{character}.pdf",
        "document_type": "doctor_note",
        "document_date": "2026-08-02",
        **overrides,
    }


def _lifecycle(status: str, qualifier: str | None = None, *, restart: bool = False) -> dict:
    transitions = {
        "current": [{"status": "past", "terminal_qualifiers": ["ended", "other"]}],
        "planned": [
            {"status": "current", "terminal_qualifiers": []},
            {
                "status": "past",
                "terminal_qualifiers": ["not_started", "cancelled", "other"],
            },
        ],
        "past": [],
    }[status]
    if status != "past":
        restart_authority = {"eligible": False, "reason": "course_not_terminal"}
    elif qualifier in {"not_started", "cancelled"}:
        restart_authority = {
            "eligible": False,
            "reason": "terminal_qualifier_not_restartable",
        }
    elif restart:
        restart_authority = {"eligible": True, "reason": "eligible_prior_current"}
    else:
        restart_authority = {
            "eligible": False,
            "reason": "no_prior_current_authority",
        }
    return {"allowed_transitions": transitions, "restart": restart_authority}


def _course(
    character: str,
    text: str,
    *,
    status: str = "current",
    qualifier: str | None = None,
    detail: str | None = None,
    previous: str | None = None,
    restart: bool = False,
    component_ids: list[str] | None = None,
) -> dict:
    return {
        "id": f"txc_{character * 32}",
        "status": status,
        "treatment_text": text,
        "treatment_type_text": "",
        "dose_text": None,
        "route_text": "  exact route  ",
        "frequency_text": None,
        "cycle_text": "",
        "schedule_text": "Every four weeks",
        "formulation_text": None,
        "indication_text": None,
        "notes": None,
        "legacy_component_ids": component_ids or [],
        "start_date": "2026",
        "start_date_precision": "year",
        "start_date_kind": "caregiver_entered",
        "stop_date": None,
        "stop_date_precision": "unknown",
        "stop_date_kind": "unknown",
        "planned_date": None,
        "planned_date_precision": "unknown",
        "planned_date_kind": "unknown",
        "terminal_qualifier": qualifier,
        "terminal_detail": detail,
        "previous_course_id": previous,
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
        "token": f"course-token-{character}",
        "lifecycle": _lifecycle(status, qualifier, restart=restart),
        "provenance": {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        },
    }


def _legacy() -> dict:
    return {
        "id": "txlegacy_example",
        "token": "legacy-token",
        "raw_text": "same earlier wording",
        "source_order": 0,
        "components": [
            {
                "id": "legacy-component-one",
                "text": "same earlier wording",
                "component_order": 0,
            }
        ],
        "generated_classification": [
            {
                "id": "generated-one",
                "text": "Generated compatibility text",
                "label": None,
                "category": None,
                "date": None,
                "source_treatment_ids": ["legacy-component-one"],
            }
        ],
        "authority_label": "Legacy/generated · not caregiver lifecycle authority",
    }


def _unlinked(index: int) -> dict:
    return {
        "id": f"txunlinked_{index:024x}",
        "token": f"unlinked-token-{index}",
        "text": f"Generated unlinked text {index % 5}",
        "label": None if index == 0 else f"Generated unlinked label {index % 5}",
        "category": None if index == 0 else "active",
        "date": None if index == 0 else f"20{index:02d}",
        "authority_label": (
            "Machine-generated compatibility context · source linkage unavailable · "
            "not a treatment record"
        ),
    }


def _confirmation() -> dict:
    return {
        "outcome": "confirmed_as_recorded",
        "note": "Exact caregiver outcome note",
        "clinician_text": "Attributed treating-team wording",
        "context_text": None,
        "date": "2026-08",
        "date_precision": "month",
        "date_kind": "caregiver_entered",
        "recorded_at": "2026-08-12T10:00:00",
        "provenance_label": "Caregiver-entered · attributed to clinician · unverified",
    }


def _discrepancy(
    character: str,
    source_a: dict,
    *,
    source_b: dict | None = None,
    course_b: dict | None = None,
    status: str = "open",
    legacy_incomplete: bool = False,
    follow_up: dict | None = None,
) -> dict:
    source_a_snapshot = copy.deepcopy(source_a)
    source_a_snapshot["observed_text"] = f"Immutable source A {character}"
    source_a_snapshot["token"] = f"snapshot-source-a-{character}"
    citations = {
        "source_a": {
            "snapshot": source_a_snapshot,
            "current": copy.deepcopy(source_a),
        },
        "source_b": None,
        "course_b": None,
    }
    comparison_source_fact = None
    course_snapshot = None
    course_id = None
    if source_b is not None:
        source_b_snapshot = copy.deepcopy(source_b)
        source_b_snapshot["observed_text"] = f"Immutable source B {character}"
        source_b_snapshot["token"] = f"snapshot-source-b-{character}"
        citations["source_b"] = {
            "snapshot": source_b_snapshot,
            "current": copy.deepcopy(source_b),
        }
        comparison_source_fact = copy.deepcopy(source_b_snapshot)
        citation_kind = "source_vs_source"
    elif course_b is not None:
        course_snapshot = copy.deepcopy(course_b)
        course_snapshot["treatment_text"] = f"Immutable caregiver course {character}"
        course_snapshot["token"] = f"snapshot-course-{character}"
        citations["course_b"] = {
            "snapshot": copy.deepcopy(course_snapshot),
            "current": copy.deepcopy(course_b),
        }
        course_id = course_b["id"]
        citation_kind = "source_vs_course"
    else:
        citation_kind = "legacy_incomplete"
    complete = not legacy_incomplete and (source_b is not None or course_b is not None)
    resolved = status == "resolved"
    return {
        "id": f"txd_{character * 32}",
        "token": f"discrepancy-token-{character}",
        "status": status,
        "category": "source_wording",
        "comparison_text": f"Neutral exact comparison {character}",
        "citation_kind": citation_kind,
        "citation_authority": {
            "state": "complete" if complete else "legacy_incomplete",
            "reason": None if complete else "missing_second_citation",
        },
        "eligibility": {
            "resolve": complete and not resolved,
            "reopen": complete and resolved,
            "recur": complete and resolved,
        },
        "citations": citations,
        "course_id": course_id,
        "source_fact": copy.deepcopy(source_a_snapshot),
        "comparison_source_fact": comparison_source_fact,
        "course_snapshot": course_snapshot,
        "recurs_from_id": None,
        "confirmations": [_confirmation()] if resolved else [],
        "follow_up": copy.deepcopy(follow_up),
        "provenance": {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        },
        "created_at": "2026-08-10T10:00:00",
        "updated_at": "2026-08-12T10:00:00",
        "resolved_at": "2026-08-12T10:00:00" if resolved else None,
    }


def _sync_dispositions(projection: dict, hidden_row_ids: tuple[str, ...] = ()) -> dict:
    """Attach the disposition sibling collection the projection contract requires.

    Recomputed from the current ``legacy_treatments`` so a fixture that adds or
    drops rows stays internally consistent.
    """
    rows = projection.get("legacy_treatments") or []
    projection["legacy_treatment_dispositions"] = [
        {
            "row_id": row["id"],
            "hidden": row["id"] in hidden_row_ids,
            "token": f"disposition-token-{row['id']}",
        }
        for row in rows
    ]
    projection["legacy_treatment_hidden_count"] = sum(
        1 for item in projection["legacy_treatment_dispositions"] if item["hidden"]
    )
    return projection


def _projection() -> dict:
    courses = [
        _course("a", "Current one", component_ids=["legacy-component-one"]),
        _course("b", "Planned two", status="planned"),
        _course("c", "Current three"),
        _course("d", "Planned four", status="planned"),
        _course("e", "Past five", status="past", qualifier="ended"),
    ]
    sources = [
        _source("1", "Duplicate source wording"),
        _source("2", "Duplicate source wording"),
    ]
    return _sync_dispositions(
        {
            "profile_revision": 5,
            "workflow_revision": 3,
            "projection_token": "treatment-projection-5-3",
            "source_fact_count": len(sources),
            "legacy_treatment_count": 1,
            "unlinked_generated_context_count": 10,
            "course_count": len(courses),
            "discrepancy_count": 0,
            "source_facts": sources,
            "source_fact_documents": [
                _source_document("1"),
                _source_document("2", filename=None, document_date="2026-08"),
            ],
            "legacy_treatments": [_legacy()],
            "unlinked_generated_context": [_unlinked(index) for index in range(10)],
            "courses": courses,
            "discrepancies": [],
            "eligible_actions": [
                {
                    "id": "action-one",
                    "token": "action-token-one",
                    "text": "Ask the treating team to confirm exact wording",
                    "status": "open",
                    "owner": "Caregiver",
                    "due_date": None,
                }
            ],
            "safety_guidance": {
                "kind": "fixed_non_prescriptive",
                "text": GUIDANCE,
            },
        }
    )


def _projection_with_discrepancies() -> dict:
    projection = _projection()
    linked_action = {
        "id": "linked-action",
        "token": "linked-action-token",
        "text": "Exact linked follow-up",
        "status": "open",
        "owner": None,
        "due_date": "2027",
    }
    projection["courses"][-1]["lifecycle"] = _lifecycle(
        "past",
        "ended",
        restart=True,
    )
    projection["discrepancies"] = [
        _discrepancy(
            "a",
            projection["source_facts"][0],
            course_b=projection["courses"][0],
        ),
        _discrepancy(
            "b",
            projection["source_facts"][0],
            source_b=projection["source_facts"][1],
            status="resolved",
            follow_up=linked_action,
        ),
        _discrepancy(
            "c",
            projection["source_facts"][0],
            legacy_incomplete=True,
        ),
    ]
    projection["discrepancy_count"] = len(projection["discrepancies"])
    return projection


def _recorded_only_projection() -> dict:
    projection = _projection()
    recorded = []
    for index in range(31):
        row = _legacy()
        row["id"] = f"txlegacy-recorded-{index:02d}"
        row["token"] = f"legacy-recorded-token-{index:02d}"
        row["raw_text"] = f"Recorded treatment information {index:02d}"
        row["source_order"] = index
        row["components"] = [
            {
                "id": f"recorded-component-{index:02d}",
                "text": f"Recorded treatment information {index:02d}",
                "component_order": 0,
            }
        ]
        row["generated_classification"] = []
        recorded.append(row)
    projection.update(
        {
            "projection_token": "treatment-recorded-only",
            "source_fact_count": 0,
            "legacy_treatment_count": len(recorded),
            "course_count": 0,
            "discrepancy_count": 0,
            "source_facts": [],
            "source_fact_documents": [],
            "legacy_treatments": recorded,
            "courses": [],
            "discrepancies": [],
            "eligible_actions": [],
        }
    )
    return _sync_dispositions(projection)


def _component_linkage_projection() -> dict:
    projection = _projection()

    def recorded_row(name: str, component_ids: list[str]) -> dict:
        row = _legacy()
        row["id"] = f"txlegacy-{name}"
        row["token"] = f"legacy-token-{name}"
        row["raw_text"] = f"{name.title()} recorded treatment"
        row["source_order"] = len(rows)
        row["components"] = [
            {
                "id": component_id,
                "text": f"{name.title()} component {index + 1}",
                "component_order": index,
            }
            for index, component_id in enumerate(component_ids)
        ]
        row["generated_classification"] = []
        return row

    rows: list[dict] = []
    rows.append(recorded_row("none", ["none-1"]))
    rows.append(recorded_row("all", ["all-1", "all-2"]))
    rows.append(recorded_row("partial", ["partial-1", "partial-2"]))
    course = _course(
        "a",
        "Explicit caregiver status",
        component_ids=["all-1", "all-2", "partial-1"],
    )
    projection.update(
        {
            "projection_token": "treatment-component-linkage",
            "legacy_treatment_count": len(rows),
            "unlinked_generated_context_count": 0,
            "course_count": 1,
            "discrepancy_count": 0,
            "legacy_treatments": rows,
            "unlinked_generated_context": [],
            "courses": [course],
            "discrepancies": [],
        }
    )
    return _sync_dispositions(projection)


def _run_validator(payloads: list[dict]) -> list[bool]:
    serialized_payloads = json.dumps(payloads)
    script = "\n".join(
        [
            """
const document = { baseURI: 'http://app.test/' };
const window = {
  location: { href: 'http://app.test/', origin: 'http://app.test' },
};
""",
            _treatment_source(),
            "const payloads = JSON.parse("
            + json.dumps(serialized_payloads)
            + ");\n"
            + "console.log(JSON.stringify(payloads.map("
            + "value => treatmentProjectionPayloadIsValid(value))));\n",
        ]
    )
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_real_treatment_validator_is_atomic_exact_and_canonical():
    valid = _projection()
    complete = _projection_with_discrepancies()
    wrong_guidance = copy.deepcopy(valid)
    wrong_guidance["safety_guidance"]["text"] += " "
    unsafe_link = copy.deepcopy(valid)
    unsafe_link["source_facts"][0]["provenance"]["source_url"] += "?x=1"
    encoded_link = copy.deepcopy(valid)
    encoded_link["source_facts"][0]["provenance"]["source_url"] = encoded_link["source_facts"][0][
        "provenance"
    ]["source_url"].replace("/source", "/%73ource")
    duplicate = copy.deepcopy(valid)
    duplicate["courses"][1]["id"] = duplicate["courses"][0]["id"]
    malformed_lifecycle = copy.deepcopy(valid)
    malformed_lifecycle["courses"][0]["lifecycle"]["allowed_transitions"][0][
        "terminal_qualifiers"
    ] = ["legacy_unspecified"]
    wrong_count = copy.deepcopy(valid)
    wrong_count["course_count"] += 1
    wrong_unlinked_count = copy.deepcopy(valid)
    wrong_unlinked_count["unlinked_generated_context_count"] += 1
    wrong_unlinked_authority = copy.deepcopy(valid)
    wrong_unlinked_authority["unlinked_generated_context"][0]["authority_label"] += " "
    duplicate_unlinked_id = copy.deepcopy(valid)
    duplicate_unlinked_id["unlinked_generated_context"][1]["id"] = duplicate_unlinked_id[
        "unlinked_generated_context"
    ][0]["id"]
    cross_component_id = copy.deepcopy(valid)
    cross_component_id["unlinked_generated_context"][0]["id"] = cross_component_id[
        "legacy_treatments"
    ][0]["components"][0]["id"]
    cross_collection_token = copy.deepcopy(valid)
    cross_collection_token["unlinked_generated_context"][0]["token"] = cross_collection_token[
        "legacy_treatments"
    ][0]["token"]
    malformed_unlinked_type = copy.deepcopy(valid)
    malformed_unlinked_type["unlinked_generated_context"][0]["date"] = []
    malformed_unlinked_label = copy.deepcopy(valid)
    malformed_unlinked_label["unlinked_generated_context"][0]["label"] = []
    malformed_unlinked_category = copy.deepcopy(valid)
    malformed_unlinked_category["unlinked_generated_context"][0]["category"] = "unsafe"
    cross_action_id = copy.deepcopy(valid)
    cross_action_id["unlinked_generated_context"][0]["id"] = cross_action_id["eligible_actions"][0][
        "id"
    ]
    oversized_unlinked = copy.deepcopy(valid)
    oversized_unlinked["unlinked_generated_context"][0]["text"] = "x" * 10001
    duplicate_generated = copy.deepcopy(valid)
    second_legacy = copy.deepcopy(duplicate_generated["legacy_treatments"][0])
    second_legacy["id"] = "txlegacy_second"
    second_legacy["token"] = "legacy-token-second"
    second_legacy["source_order"] = 1
    second_legacy["components"][0]["id"] = "legacy-component-two"
    duplicate_generated["legacy_treatments"].append(second_legacy)
    duplicate_generated["legacy_treatment_count"] = 2
    _sync_dispositions(duplicate_generated)
    spanning_generated = copy.deepcopy(duplicate_generated)
    spanning = spanning_generated["legacy_treatments"][0]["generated_classification"][0]
    spanning["source_treatment_ids"] = ["legacy-component-one", "legacy-component-two"]
    spanning_generated["legacy_treatments"][1]["generated_classification"] = [
        copy.deepcopy(spanning)
    ]
    incomplete_spanning = copy.deepcopy(spanning_generated)
    incomplete_spanning["legacy_treatments"][1]["generated_classification"] = []
    duplicate_mapped_in_place = copy.deepcopy(valid)
    duplicate_mapped_in_place["legacy_treatments"][0]["generated_classification"].append(
        copy.deepcopy(
            duplicate_mapped_in_place["legacy_treatments"][0]["generated_classification"][0]
        )
    )
    expanded_spanning = copy.deepcopy(spanning_generated)
    expanded_rows = []
    for index in range(1001):
        row = copy.deepcopy(spanning)
        row["id"] = f"generated-spanning-{index}"
        row["text"] = f"Synthetic mapped context {index}"
        expanded_rows.append(row)
    expanded_spanning["legacy_treatments"][0]["generated_classification"] = copy.deepcopy(
        expanded_rows
    )
    expanded_spanning["legacy_treatments"][1]["generated_classification"] = copy.deepcopy(
        expanded_rows
    )
    malformed_mapped_category = copy.deepcopy(valid)
    malformed_mapped_category["legacy_treatments"][0]["generated_classification"][0]["category"] = (
        "unsafe"
    )
    oversized_mapped_text = copy.deepcopy(valid)
    oversized_mapped_text["legacy_treatments"][0]["generated_classification"][0]["text"] = (
        "x" * 10001
    )
    recurrence_cycle = copy.deepcopy(complete)
    recurrence_cycle["discrepancies"][0]["recurs_from_id"] = recurrence_cycle["discrepancies"][1][
        "id"
    ]
    recurrence_cycle["discrepancies"][1]["recurs_from_id"] = recurrence_cycle["discrepancies"][0][
        "id"
    ]

    assert _run_validator(
        [
            valid,
            complete,
            spanning_generated,
            expanded_spanning,
            incomplete_spanning,
            duplicate_mapped_in_place,
            malformed_mapped_category,
            oversized_mapped_text,
            wrong_guidance,
            unsafe_link,
            encoded_link,
            duplicate,
            malformed_lifecycle,
            wrong_count,
            wrong_unlinked_count,
            wrong_unlinked_authority,
            duplicate_unlinked_id,
            cross_component_id,
            cross_collection_token,
            malformed_unlinked_type,
            malformed_unlinked_label,
            malformed_unlinked_category,
            cross_action_id,
            oversized_unlinked,
            duplicate_generated,
            recurrence_cycle,
        ]
    ) == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def test_treatment_module_has_one_authority_and_no_legacy_or_date_inference():
    source = _treatment_source()
    assert "/api/patient/treatment-reconciliation" in source
    assert "fetch('/api/status" not in source
    assert "/api/treatments/" not in APP_JS
    assert "new Date(" not in source
    assert "Date.parse" not in source
    # Newest-first display ordering is an explicit, approved decision, so a
    # blanket ban on sorting no longer holds. What must still hold is that
    # sorting only ever runs on a copy, never on accepted authority, and that
    # it is confined to the two display helpers.
    assert source.count(".sort(") == 2
    assert source.count("[...courses].sort(") == 1
    assert source.count("[...rows].sort(") == 1
    assert "treatmentProjection.courses.sort(" not in APP_JS
    assert "treatmentProjection.legacy_treatments.sort(" not in APP_JS
    assert ".dedupe" not in source
    assert "treatments_classified" not in source
    assert "treatments_fallback" not in source
    assert "body: intent.bodyText" in source
    assert "mutation_id: newMutationId()" in source
    assert "pendingTreatmentCompletion" in source
    assert "Retry submission" in INDEX_HTML
    assert "Retry refresh" in INDEX_HTML
    assert GUIDANCE not in INDEX_HTML
    assert (
        "Machine-generated compatibility context · source linkage unavailable · "
        "not a treatment record"
    ) in source
    assert "No status recorded" in source
    assert "No caregiver status record refers to this wording." in source
    # Recorded rows are never framed as outstanding caregiver work.
    assert "need timing/status review" not in source
    assert "not yet reviewed" not in source


class _LiveState:
    def __init__(self, projection: dict | None = None) -> None:
        self.projection = copy.deepcopy(projection or _projection())
        self.requests: list[tuple[str, str, dict | None]] = []
        self.raw_mutation_bodies: list[str] = []
        self.counter = 0
        self.treatment_get_status = 200
        self.abort_next_treatment_get = False
        self.next_mutation_status: int | None = None
        self.abort_next_mutation = False
        self.mismatch_after_mutation = False
        self.hold_summary_job = False

    def _advance(self) -> None:
        self.counter += 1
        self.projection["profile_revision"] += 1
        self.projection["workflow_revision"] += 1
        self.projection["projection_token"] = f"projection-live-{self.counter}"

    def mutate(self, method: str, path: str, body: dict) -> dict:
        self._advance()
        if method == "POST" and path == "/api/treatment-reconciliation/courses":
            course = _course(
                str(5 + self.counter),
                body["treatment_text"],
                status=body["status"],
            )
            for field in (
                "treatment_type_text",
                "dose_text",
                "route_text",
                "frequency_text",
                "cycle_text",
                "schedule_text",
                "formulation_text",
                "indication_text",
                "notes",
                "start_date",
                "stop_date",
                "planned_date",
                "legacy_component_ids",
            ):
                course[field] = copy.deepcopy(body[field])
            for prefix in ("start", "stop", "planned"):
                value = course[f"{prefix}_date"]
                course[f"{prefix}_date_precision"] = (
                    "unknown"
                    if value is None
                    else ("year" if len(value) == 4 else "month" if len(value) == 7 else "day")
                )
                course[f"{prefix}_date_kind"] = "unknown" if value is None else "caregiver_entered"
            course["terminal_qualifier"] = body["terminal_qualifier"]
            course["terminal_detail"] = body["terminal_detail"]
            course["lifecycle"] = _lifecycle(course["status"], course["terminal_qualifier"])
            course["token"] = f"course-token-live-{self.counter}"
            self.projection["courses"].append(course)
        else:
            course_id = path.split("/")[4]
            course = next(item for item in self.projection["courses"] if item["id"] == course_id)
            if path.endswith("/transition"):
                course["status"] = body["status"]
                course["terminal_qualifier"] = body["terminal_qualifier"]
                course["terminal_detail"] = body["terminal_detail"]
                course["lifecycle"] = _lifecycle(course["status"], course["terminal_qualifier"])
            else:
                for field in (
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
                    "start_date",
                    "stop_date",
                    "planned_date",
                    "legacy_component_ids",
                ):
                    course[field] = copy.deepcopy(body[field])
            course["token"] = f"course-token-live-{self.counter}"
            course["updated_at"] = f"2026-09-{self.counter + 1:02d}T10:00:00"
        self.projection["course_count"] = len(self.projection["courses"])
        return {
            "course": copy.deepcopy(course),
            "profile_revision": self.projection["profile_revision"],
            "workflow_revision": self.projection["workflow_revision"],
        }


def _standard_payload(path: str, state: _LiveState) -> object:
    revision = state.projection["profile_revision"]
    workflow = state.projection["workflow_revision"]
    payloads = {
        "/api/status": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "patient": {"diagnosis": "Status patient"},
            "stats": {},
            "alerts": [],
        },
        "/api/patient/symptom-episodes": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "projection_token": "symptom-empty",
            "observation_count": 0,
            "episode_count": 0,
            "observations": [],
            "episodes": [],
            "eligible_actions": [],
            "safety_guidance": {
                "kind": "fixed_non_diagnostic",
                "text": (
                    "NET/Care records what you enter but does not assess urgency or monitor "
                    "symptoms. Contact the treating team about symptoms or concerns. If you "
                    "think this may be a medical emergency, contact local emergency services."
                ),
            },
        },
        "/api/patient/biomarker-series": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "projection_token": "biomarker-empty",
            "observation_count": 0,
            "source_row_count": 0,
            "analytes": [],
        },
        "/api/patient/imaging-series": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "source_row_count": 0,
            "projection_token": "imaging-empty",
            "records": [],
        },
        "/api/follow-ups": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "items": [],
        },
        "/api/visits": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "appointments": [],
            "items": [],
        },
        "/api/summary": {
            "status": "current",
            "stale": False,
            "profile_revision": revision,
            "summary_revision": revision,
            "generation_id": "summary-current",
            "generated_at": "2026-08-12",
            "generated_at_timestamp": "2026-08-12T09:00:00",
            "overall_status": "stable",
            "status_confidence": "medium",
            "status_rationale": "The latest recorded information supports a stable assessment.",
            "key_concern": "Confirm the next monitoring plan with the treating team.",
            "summary": "Latest patient status is available for caregiver review.",
            "prrt_status": "unknown",
            "prrt_rationale": "Discuss screening context with the treating team.",
            "cga_trend": "insufficient_data",
            "cga_trend_detail": None,
            "next_actions": [
                {
                    "id": "summary-action-current",
                    "source_token": "summary-action-token",
                    "generation_id": "summary-current",
                    "source_profile_revision": revision,
                    "stale": False,
                    "action": "Ask the treating team to confirm the monitoring plan.",
                    "priority": "high",
                    "rationale": "Keep the next visit focused.",
                    "timeframe": "Before the next visit",
                }
            ],
            "timeline": [],
            "claim_evidence": {"claims": {}, "actions": [[]]},
            "recent_documents": [],
        },
        "/api/jobs": [],
        "/api/questions": [],
        "/api/judgments": [],
        "/api/patient/evidence": {"documents": [], "sources": []},
    }
    return payloads.get(path, {})


def _open_treatment_page(
    playwright,
    width: int,
    height: int,
    projection: dict | None = None,
):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    state = _LiveState(projection)

    def fulfill(route):
        request = route.request
        path = urlsplit(request.url).path
        body = json.loads(request.post_data) if request.post_data else None
        state.requests.append((request.method, path, body))
        if path == "/api/patient/treatment-reconciliation":
            if state.abort_next_treatment_get:
                state.abort_next_treatment_get = False
                route.abort("failed")
                return
            if state.treatment_get_status != 200:
                route.fulfill(
                    status=state.treatment_get_status,
                    content_type="application/json",
                    body=json.dumps({"error": "not exposed"}),
                )
                return
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(state.projection),
            )
            return
        if path == "/api/summary/generate" and request.method == "POST":
            route.fulfill(
                status=202,
                content_type="application/json",
                body=json.dumps({"job_id": "summary-ui-polish"}),
            )
            return
        if path == "/api/jobs/summary-ui-polish":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "id": "summary-ui-polish",
                        "status": "running" if state.hold_summary_job else "done",
                    }
                ),
            )
            return
        if path.startswith("/api/treatment-reconciliation/") and request.method != "GET":
            state.raw_mutation_bodies.append(request.post_data or "")
            if state.abort_next_mutation:
                state.abort_next_mutation = False
                route.abort("failed")
                return
            if state.next_mutation_status is not None:
                status = state.next_mutation_status
                state.next_mutation_status = None
                route.fulfill(
                    status=status,
                    content_type="application/json",
                    body=json.dumps({"error": "not exposed"}),
                )
                return
            result = state.mutate(request.method, path, body or {})
            if state.mismatch_after_mutation and result.get("course"):
                state.projection["courses"][-1]["treatment_text"] = "Mismatched replacement"
                state.mismatch_after_mutation = False
            route.fulfill(
                status=201 if request.method == "POST" else 200,
                content_type="application/json",
                body=json.dumps(result),
            )
            return
        if path.endswith("/source") or path.endswith("/evidence"):
            route.fulfill(status=200, content_type="text/plain", body="Exact source")
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_standard_payload(path, state)),
        )

    page.route("**/api/**", fulfill)
    page.set_content(html)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content=APP_JS)
    page.evaluate("() => { clearTimeout(pollingInterval); pollingInterval = null; }")
    page.wait_for_function("() => ['current', 'empty'].includes(treatmentProjectionState)")
    return browser, context, page, state


@pytest.mark.parametrize("width,height", [(1280, 900), (360, 800)])
def test_live_shared_projection_totals_authorities_and_accessibility(width: int, height: int):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, width, height)
        try:
            assert page.locator("#today-treatment-list .treatment-course-card").count() == 3
            totals = page.locator("#today-treatment-totals").inner_text()
            assert "2 current and 2 planned status records" in totals
            assert "1 recorded treatment entry is on file" in totals
            page.locator("#nav-patient").click()
            assert page.locator("#patient-treatment-list .treatment-course-card").count() == 5
            assert (
                "Linked to reviewed status"
                in page.locator("#patient-treatment-list .treatment-recorded-card").inner_text()
            )
            assert [
                " ".join(text.split()) for text in page.locator(".treatment-tab").all_inner_texts()
            ] == [
                "Overview 6",
                "Differences to review 0",
                "Mentions in source documents 2",
            ]
            page.locator("#treatment-tab-sources").click()
            assert page.locator("#treatment-source-table-body tr").count() == 2
            assert (
                page.locator("#treatment-panel-sources")
                .inner_text()
                .count("Duplicate source wording")
                == 2
            )
            # Document identity answers "which document, and when" without
            # linking the mention to any caregiver course.
            document_cells = page.locator("#treatment-source-table-body .treatment-source-document")
            assert document_cells.count() == 2
            first_document = " ".join(document_cells.nth(0).inner_text().split())
            second_document = " ".join(document_cells.nth(1).inner_text().split())
            assert "visit-summary-1.pdf" in first_document
            assert "2.8.2026" in first_document
            # A mention with no filename falls back to the document type, and a
            # month-precision date keeps its recorded precision in Finnish form.
            assert "doctor_note" in second_document
            assert "8/2026" in second_document
            overflow = page.evaluate(
                """() => {
                  const table = [...document.querySelectorAll('.treatment-table-region')]
                    .find(item => item.offsetParent !== null);
                  return {
                    document: document.documentElement.scrollWidth
                      - document.documentElement.clientWidth,
                    tableScrolls: table.scrollWidth > table.clientWidth,
                  };
                }"""
            )
            assert overflow["document"] == 0
            assert overflow["tableScrolls"] is (width == 360)
            # The automatic compatibility notes tab was removed. "End" must land
            # on the last remaining tab, and no generated-context surface may
            # render even though the projection still carries those rows.
            page.locator("#treatment-tab-sources").focus()
            page.keyboard.press("End")
            assert page.evaluate("() => document.activeElement.id") == "treatment-tab-sources"
            page.keyboard.press("Home")
            assert page.evaluate("() => document.activeElement.id") == "treatment-tab-records"
            assert page.locator("#treatment-tab-earlier").count() == 0
            assert page.locator("#treatment-panel-earlier").count() == 0
            assert page.locator(".treatment-generated-disclosure").count() == 0
            assert page.locator(".treatment-unlinked-generated-section").count() == 0
            workspace_text = page.locator("#treatment-workspace").inner_text()
            assert "compatibility notes" not in workspace_text
            assert "NET/Care-generated context - not a treatment fact" not in workspace_text
            assert GUIDANCE not in workspace_text
            treatment_gets = [
                item
                for item in state.requests
                if item[1] == "/api/patient/treatment-reconciliation"
            ]
            assert len(treatment_gets) == 1
            assert not any(path.startswith("/api/treatments") for _, path, _ in state.requests)
            if width == 360:
                heights = page.locator(
                    "#treatment-workspace button, #treatment-workspace summary"
                ).evaluate_all(
                    "items => items.filter(item => item.offsetParent !== null)"
                    ".map(item => item.getBoundingClientRect().height)"
                )
                assert heights
                assert min(heights) >= 44
            page.locator("#patient-treatment-add").click()
            page.keyboard.press("Escape")
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "true"
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (360, 740)])
def test_live_recorded_treatments_are_first_class_without_status_inference(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            width,
            height,
            _recorded_only_projection(),
        )
        try:
            today = page.locator("#treatment-today-card")
            assert "No treatment is recorded as current." in today.inner_text()
            assert "31 recorded treatment entries are on file" in today.inner_text()
            assert page.locator("#today-treatment-list .treatment-recorded-card").count() == 3
            # Recorded rows carry no date, so Today's bounded set shows the
            # three most recently recorded entries.
            assert page.locator(
                "#today-treatment-list .treatment-recorded-card h3"
            ).all_inner_texts() == [
                "Recorded treatment information 30",
                "Recorded treatment information 29",
                "Recorded treatment information 28",
            ]

            page.locator("#nav-patient").click()
            overview = page.locator("#treatment-panel-records")
            assert page.locator("#patient-treatment-list .treatment-recorded-card").count() == 31
            assert "Recorded treatment statements (31)" in overview.inner_text()
            assert "Recorded treatment information 00" in overview.inner_text()
            assert "Recorded treatment information 30" in overview.inner_text()
            assert page.locator(
                "#patient-treatment-list .treatment-recorded-card h3"
            ).all_inner_texts() == [
                f"Recorded treatment information {index:02d}" for index in range(30, -1, -1)
            ]
            normalized = overview.inner_text().lower()
            for forbidden in ("legacy", "earlier app", "archived", "historical", "unverified"):
                assert forbidden not in normalized

            # The unlinked generated context is still carried by the projection
            # (10 rows) but has no UI surface at all after the tab removal.
            assert page.locator("#treatment-tab-earlier").count() == 0
            assert page.locator(".treatment-unlinked-generated-section").count() == 0
            assert page.locator(".treatment-unlinked-generated-card").count() == 0
            writes = [
                request
                for request in state.requests
                if request[0] != "GET" and request[1].startswith("/api/treatment-reconciliation/")
            ]
            assert writes == []
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow == 0
        finally:
            context.close()
            browser.close()


def test_live_recorded_treatment_component_linkage_is_none_all_or_partial():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(
            playwright,
            1280,
            800,
            _component_linkage_projection(),
        )
        try:
            totals = page.locator("#today-treatment-totals").inner_text()
            assert "1 current and 0 planned status record" in totals
            assert "3 recorded treatment entries are on file" in totals
            assert "need timing/status review" not in totals

            page.locator("#nav-patient").click()
            cards = page.locator("#patient-treatment-list .treatment-recorded-card")
            assert cards.count() == 3
            # Recorded rows are listed most recently recorded first, so the
            # last-recorded "partial" row leads and "none" comes last.
            assert "Partly linked to reviewed status" in cards.nth(0).inner_text()
            assert "1 of 2 recorded components are linked" in cards.nth(0).inner_text()
            assert "Linked to reviewed status" in cards.nth(1).inner_text()
            assert "All recorded components are linked" in cards.nth(1).inner_text()
            assert "No status recorded" in cards.nth(2).inner_text()
            assert "No caregiver status record refers to this wording" in cards.nth(2).inner_text()
            assert cards.locator("h3").all_inner_texts() == [
                "Partial recorded treatment",
                "All recorded treatment",
                "None recorded treatment",
            ]
            for card in cards.all():
                assert "Current record" not in card.inner_text()
                assert "Planned record" not in card.inner_text()
                assert "Past record" not in card.inner_text()
        finally:
            context.close()
            browser.close()


def test_live_hidden_recorded_rows_collapse_without_disappearing():
    """A hidden row leaves the main list but is always disclosed and restorable."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    projection = _component_linkage_projection()
    hidden_id = next(
        row["id"]
        for row in projection["legacy_treatments"]
        if row["raw_text"] == "None recorded treatment"
    )
    _sync_dispositions(projection, (hidden_id,))
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(playwright, 1280, 800, projection)
        try:
            totals = page.locator("#today-treatment-totals").inner_text()
            # The count reflects what is shown, and never conceals the remainder.
            assert "2 recorded treatment entries are on file" in totals
            assert "1 hidden in Patient" in totals

            page.locator("#nav-patient").click()
            visible = page.locator(
                "#patient-treatment-list .treatment-course-list:not(.treatment-hidden-list)"
                " > .treatment-recorded-card"
            )
            assert visible.count() == 2
            assert "None recorded treatment" not in visible.nth(0).inner_text()
            assert "None recorded treatment" not in visible.nth(1).inner_text()

            disclosure = page.locator(".treatment-hidden-disclosure")
            assert disclosure.count() == 1
            assert "1 hidden by you · show" in disclosure.locator("summary").inner_text()
            # The row is present in the DOM behind the disclosure, not removed.
            hidden_cards = disclosure.locator(".treatment-recorded-card")
            assert hidden_cards.count() == 1
            assert "None recorded treatment" in hidden_cards.nth(0).text_content()
            disclosure.locator("summary").click()
            assert "None recorded treatment" in hidden_cards.nth(0).inner_text()
            assert (
                hidden_cards.nth(0)
                .get_by_role("button", name="Show None recorded treatment again")
                .count()
                == 1
            )
            # It must state plainly that nothing was deleted or withheld.
            assert "Nothing was deleted" in disclosure.text_content()
            assert "still uses them when answering your questions" in disclosure.text_content()

            # Today shows only the rows the caregiver kept.
            page.locator("#nav-today").click()
            today = page.locator("#today-treatment-list").inner_text()
            assert "None recorded treatment" not in today
        finally:
            context.close()
            browser.close()


def test_live_row_visibility_transport_failure_does_not_lock_the_workspace():
    """A row action has no reachable retry, so it must never hold the mutation open.

    The in-dialog "Retry submission" control is the only recovery affordance for an
    ambiguous transport failure, and it is unreachable when no dialog is open. If a
    row-level action kept the mutation pending, every treatment control — not just
    this toggle — would stay disabled until a page reload.
    """
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            hide = page.locator("button[data-treatment-visibility-row]").first
            assert hide.is_enabled()
            state.abort_next_mutation = True
            hide.click()

            page.wait_for_function("() => !treatmentMutationPending")
            # No unreachable retry is armed.
            assert page.evaluate("() => pendingTreatmentRetry === null")
            # The authoritative record is reloaded, and the workspace stays usable.
            page.wait_for_function("() => treatmentProjectionState === 'current'")
            assert page.locator("button[data-treatment-visibility-row]").first.is_enabled()
            assert page.locator("#patient-treatment-add").is_enabled()
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (360, 740)])
def test_live_today_first_viewport_prioritizes_latest_assessment(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(playwright, width, height)
        try:
            page.wait_for_selector("#summary-card .summary-concern")
            positions = page.evaluate(
                """() => Object.fromEntries([
                  ['freshness', document.querySelector('#freshness-banner').getBoundingClientRect().top],
                  ['summary', document.querySelector('#summary-card').getBoundingClientRect().top],
                  ['recent', document.querySelector('#recent-updates-card').getBoundingClientRect().top],
                  ['treatment', document.querySelector('#treatment-today-card').getBoundingClientRect().top],
                  ['symptoms', document.querySelector('#symptom-today-card').getBoundingClientRect().top],
                  ['followups', document.querySelector('.follow-through-card').getBoundingClientRect().top],
                  ['appointment', document.querySelector('#today-appointment-card').getBoundingClientRect().top],
                  ['research', document.querySelector('#research-today-card').getBoundingClientRect().top],
                ])"""
            )
            assert list(positions.values()) == sorted(positions.values())
            assert page.locator("#summary-card").get_by_text("What matters now").is_visible()
            assert page.locator("#summary-card .summary-concern").is_visible()
            assert page.locator("#summary-card").get_by_text("Recommended next steps").is_visible()
            action_box = page.locator("#summary-card .action-main").bounding_box()
            assert action_box is not None
            assert action_box["y"] < height
            assert page.locator("#freshness-title").inner_text() == "Up to date"
            regenerate = page.get_by_role("button", name="Regenerate assessment", exact=True)
            assert regenerate.count() == 1
            regenerate_box = regenerate.bounding_box()
            assert regenerate_box is not None
            assert regenerate_box["y"] + regenerate_box["height"] <= height
            assert regenerate_box["height"] >= 44
            assert "revision" not in page.locator("#freshness-banner").inner_text().lower()
            assert "revision" not in page.locator("#summary-card").inner_text().lower()
            assert (
                page.evaluate(
                    "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                == 0
            )

            page.locator('[data-update-view="activity"]').click()
            assert page.evaluate("() => activeView") == "activity"
            page.wait_for_function("() => document.activeElement.id === 'nav-activity'")
            assert page.evaluate("() => document.activeElement.id") == "nav-activity"
            page.locator("#nav-today").click()

            page.evaluate(
                """() => {
                  visitsById = new Map([
                    ['visit-later', {
                      id: 'visit-later', token: 'token-later', title: 'Later visit',
                      status: 'planned', date: '2026-12-01', updated_at: '2026-08-01',
                      question_snapshots: [], decisions: [], follow_up_ids: [],
                    }],
                    ['visit-earlier', {
                      id: 'visit-earlier', token: 'token-earlier', title: 'Earlier visit',
                      status: 'planned', date: '2026-09-01', updated_at: '2026-08-02',
                      question_snapshots: [], decisions: [], follow_up_ids: [],
                    }],
                  ]);
                  renderTodayAppointment();
                }"""
            )
            assert "Earlier visit" in page.locator("#today-appointment-summary").inner_text()
            assert page.evaluate("() => todayAppointmentVisit()?.id") == "visit-earlier"
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (768, 800), (360, 740)])
def test_live_today_polish_keeps_one_guarded_action_and_consistent_update_buttons(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, width, height)
        try:
            removed_copy = (
                "NET/Care records what you enter but does not assess urgency or monitor symptoms.",
                "NET/Care records what you enter but does not verify treatment details",
                "NET/Care records research you choose to follow but does not determine relevance",
                "Decision-support only. Confirm clinical decisions with the treating team.",
            )
            for selector in (
                "#view-today",
                "#view-patient",
                "#view-research",
                "#symptom-dialog",
                "#treatment-dialog",
                "#research-dialog",
            ):
                text = page.locator(selector).text_content() or ""
                assert all(copy not in text for copy in removed_copy)

            actions = page.locator("#recent-updates-list .recent-update-action")
            assert actions.count() == 3
            shared_styles = page.evaluate(
                """() => {
                  const properties = button => {
                    const style = getComputedStyle(button);
                    const box = button.getBoundingClientRect();
                    return {
                      borderRadius: style.borderRadius,
                      fontSize: style.fontSize,
                      fontWeight: style.fontWeight,
                      minHeight: style.minHeight,
                      padding: style.padding,
                      height: box.height,
                    };
                  };
                  const header = document.querySelector(
                    '#recent-updates-card .card-header .button'
                  );
                  return {
                    header: properties(header),
                    rows: [...document.querySelectorAll(
                      '#recent-updates-list .recent-update-action'
                    )].map(properties),
                    overflow: document.documentElement.scrollWidth
                      - document.documentElement.clientWidth,
                  };
                }"""
            )
            for row in shared_styles["rows"]:
                style_keys = (
                    "borderRadius",
                    "fontSize",
                    "fontWeight",
                    "minHeight",
                    "padding",
                )
                assert {key: row[key] for key in style_keys} == {
                    key: shared_styles["header"][key] for key in style_keys
                }
                assert row["height"] >= 44
            assert shared_styles["overflow"] == 0
            for index, expected_view in enumerate(("activity", "research", "patient")):
                page.locator("#nav-today").click()
                action = actions.nth(index)
                assert {"button", "secondary", "recent-update-action"} <= set(
                    (action.get_attribute("class") or "").split()
                )
                action.focus()
                page.keyboard.press("Enter")
                assert page.evaluate("() => activeView") == expected_view

            page.locator("#nav-today").click()

            def generate_posts() -> int:
                return sum(
                    method == "POST" and path == "/api/summary/generate"
                    for method, path, _ in state.requests
                )

            # A current assessment must still expose the one voluntary refresh
            # control, worded so it does not imply new information arrived.
            assert page.locator("#freshness-title").inner_text() == "Up to date"
            regenerate = page.get_by_role("button", name="Regenerate assessment", exact=True)
            assert regenerate.count() == 1
            assert regenerate.is_visible()
            assert regenerate.is_enabled()
            assert (
                page.evaluate(
                    "() => [...document.querySelectorAll('button')].filter("
                    "b => !b.hidden && (b.onclick === generateSummary"
                    " || (b.getAttribute('onclick') || '').includes('generateSummary'))"
                    ").length"
                )
                == 1
            )
            assert page.get_by_role("button", name="Refresh assessment", exact=True).count() == 0
            assert page.get_by_role("button", name="Generate assessment", exact=True).count() == 0
            regenerate.focus()
            assert page.evaluate("() => document.activeElement.id") == "freshness-action"
            assert (
                page.evaluate(
                    "() => document.documentElement.scrollWidth"
                    " - document.documentElement.clientWidth"
                )
                == 0
            )

            current_before = generate_posts()
            page.keyboard.press("Enter")
            page.wait_for_function("() => summaryGenerationPending === false")
            assert generate_posts() - current_before == 1
            assert page.locator("#freshness-title").inner_text() == "Up to date"
            regenerate = page.get_by_role("button", name="Regenerate assessment", exact=True)
            assert regenerate.count() == 1
            assert regenerate.is_enabled()

            duplicate_before = generate_posts()
            page.evaluate("() => { generateSummary(); generateSummary(); }")
            page.wait_for_function("() => summaryGenerationPending === false")
            assert generate_posts() - duplicate_before == 1

            state.hold_summary_job = True
            inflight_before = generate_posts()
            page.get_by_role("button", name="Regenerate assessment", exact=True).click()
            page.wait_for_function("() => summaryGenerationPending === true")
            assert page.locator("#freshness-action").is_disabled()
            assert page.locator("#freshness-action").inner_text() == "Generating assessment…"
            page.evaluate(
                """() => renderFreshness({
                  status: 'current',
                  stale: false,
                  profile_revision: 3,
                  summary_revision: 3,
                  generated_at: '2026-08-12',
                  generated_at_timestamp: '2026-08-12T09:00:00',
                  recent_documents: [],
                })"""
            )
            assert page.locator("#freshness-action").is_disabled()
            assert page.get_by_role("button", name="Regenerate assessment", exact=True).count() == 1
            page.evaluate("() => { generateSummary(); }")
            assert generate_posts() - inflight_before == 1
            state.hold_summary_job = False
            page.wait_for_function("() => summaryGenerationPending === false")
            page.wait_for_function("() => !document.getElementById('freshness-action').disabled")
            assert generate_posts() - inflight_before == 1
            regenerate = page.get_by_role("button", name="Regenerate assessment", exact=True)
            assert regenerate.count() == 1
            assert regenerate.is_enabled()

            page.evaluate(
                """() => renderSummary({
                  status: 'stale',
                  stale: true,
                  content_hidden: true,
                  profile_revision: 9,
                  summary_revision: 8,
                })"""
            )
            refresh = page.get_by_role("button", name="Refresh assessment", exact=True)
            assert refresh.count() == 1
            assert refresh.is_visible()
            assert page.get_by_role("button", name="Regenerate assessment", exact=True).count() == 0
            assert page.locator("#summary-body button").count() == 0
            stale_text = page.locator("#summary-body").inner_text()
            assert "Prior generated assessment is hidden" in stale_text
            assert "using its actions, PRRT screening, or trial suggestion" in stale_text
            assert page.locator("#summary-card .summary-concern").count() == 0

            stale_before = generate_posts()
            refresh.focus()
            page.keyboard.press("Enter")
            page.wait_for_function(
                "() => document.getElementById('freshness-title').textContent === 'Up to date'"
            )
            assert generate_posts() - stale_before == 1
            assert page.get_by_role("button", name="Refresh assessment", exact=True).count() == 0
            assert page.get_by_role("button", name="Generate assessment", exact=True).count() == 0
            regenerate = page.get_by_role("button", name="Regenerate assessment", exact=True)
            assert regenerate.count() == 1
            assert regenerate.is_visible()

            page.evaluate("() => renderSummary({status: 'not_generated'})")
            generate = page.get_by_role("button", name="Generate assessment", exact=True)
            assert generate.count() == 1
            assert generate.is_visible()
            assert page.locator("#summary-body button").count() == 0
            assert page.get_by_role("button", name="Refresh assessment", exact=True).count() == 0
            assert page.get_by_role("button", name="Regenerate assessment", exact=True).count() == 0

            page.evaluate("() => renderFreshness(null, new Error('offline'))")
            assert page.get_by_role("button", name="Retry check", exact=True).count() == 1
            assert page.get_by_role("button", name="Generate assessment", exact=True).count() == 0
            assert page.get_by_role("button", name="Refresh assessment", exact=True).count() == 0
            assert page.get_by_role("button", name="Regenerate assessment", exact=True).count() == 0
            assert (
                page.evaluate(
                    "() => document.documentElement.scrollWidth"
                    " - document.documentElement.clientWidth"
                )
                == 0
            )
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (360, 740)])
def test_live_activity_navigation_closes_report_and_restores_meaningful_focus(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(playwright, width, height)
        try:
            page.locator("#today-appointment-action").click()
            assert page.evaluate("() => activeView") == "questions"
            assert page.evaluate("() => document.activeElement.id") == "appointment-prep-heading"

            page.evaluate(
                """() => {
                  switchView('activity', document.getElementById('nav-activity'));
                  visitsById = new Map([['visit-locked', {
                    id: 'visit-locked', token: 'visit-locked-token',
                    title: 'Locked visit', status: 'planned', date: '2026-09-01',
                    question_snapshots: [], decisions: [], follow_up_ids: [],
                  }]]);
                  followUpMutationPending = true;
                  window.__originalLoadVisits = loadVisits;
                  loadVisits = () => Promise.resolve([]);
                  const report = document.getElementById('report-panel');
                  report.classList.remove('collapsed');
                  report.setAttribute('aria-hidden', 'false');
                  document.getElementById('panel-body').innerHTML =
                    '<button id="activity-open-appointments" onclick="openAppointmentsView(this)">Open Appointments</button>';
                  activateDialog(report, document.getElementById('nav-activity'));
                }"""
            )
            page.locator("#activity-open-appointments").click()
            assert page.locator("#report-panel").get_attribute("aria-hidden") == "true"
            assert page.locator("#report-panel").evaluate(
                "node => node.classList.contains('collapsed')"
            )
            assert page.evaluate("() => activeView") == "questions"
            assert page.evaluate("() => document.activeElement.id") == "appointment-prep-heading"
            assert not page.evaluate("() => appointmentDialogOpen")
            page.evaluate(
                """() => {
                  loadVisits = window.__originalLoadVisits;
                  followUpMutationPending = false;
                  visitsById = new Map();
                }"""
            )

            page.evaluate(
                """() => {
                  switchView('activity', document.getElementById('nav-activity'));
                  const report = document.getElementById('report-panel');
                  report.classList.remove('collapsed');
                  report.setAttribute('aria-hidden', 'false');
                  document.getElementById('panel-body').innerHTML =
                    '<button id="activity-open-today" onclick="openTodayFromActivity(this)">Open Today</button>';
                  activateDialog(report, document.getElementById('nav-activity'));
                }"""
            )
            page.locator("#activity-open-today").click()
            assert page.locator("#report-panel").get_attribute("aria-hidden") == "true"
            assert page.evaluate("() => activeView") == "today"
            assert page.evaluate("() => document.activeElement.id") == "summary-heading"

            failure_deduplicated = page.evaluate(
                """() => {
                  switchView('patient', document.getElementById('nav-patient'));
                  renderStatusFailure();
                  const list = document.getElementById('recent-updates-list');
                  const alerts = document.getElementById('alerts-list');
                  const firstRecent = list.firstElementChild;
                  const firstAlerts = alerts.firstElementChild;
                  renderStatusFailure();
                  return {
                    sameRecentNode: firstRecent === list.firstElementChild,
                    sameAlertsNode: firstAlerts === alerts.firstElementChild,
                    recentFailures: list.querySelectorAll('[data-recent-updates-failure]').length,
                    alertFailures: alerts.querySelectorAll('[data-alerts-load-failure]').length,
                  };
                }"""
            )
            assert failure_deduplicated == {
                "sameRecentNode": True,
                "sameAlertsNode": True,
                "recentFailures": 1,
                "alertFailures": 1,
            }

            stale_corrupt = page.evaluate(
                """() => staleReportMarkup({
                  id: 'stale-corrupt',
                  type: 'digest',
                  status: 'done',
                  report_stale: true,
                  report_stale_reason: 'patient_record_changed_after_generation',
                  artifact: {kind: 'report', state: 'unavailable', freshness: 'unknown'},
                })"""
            )
            assert "retained" not in stale_corrupt.lower()
            assert "prior report is not available here" in stale_corrupt.lower()
            assert "report unavailable" in stale_corrupt.lower()

            polled_stale = page.evaluate(
                """() => {
                  selectedTaskId = 'stale-corrupt';
                  const report = document.getElementById('report-panel');
                  report.classList.remove('collapsed');
                  report.setAttribute('aria-hidden', 'false');
                  revalidateOpenTask([{
                    id: 'stale-corrupt',
                    type: 'digest',
                    status: 'done',
                    derived_content_stale: true,
                    derived_content_stale_reason: 'patient_record_changed_after_generation',
                    artifact: {kind: 'report', state: 'unavailable', freshness: 'unknown'},
                  }]);
                  return document.getElementById('panel-body').innerHTML;
                }"""
            )
            assert "retained" not in polled_stale.lower()
            assert "report unavailable" in polled_stale.lower()
            assert "retry detail load" in polled_stale.lower()
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 800), (360, 740)])
def test_live_unchanged_stale_poll_preserves_action_alert_and_focus(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(playwright, width, height)
        try:
            page.evaluate(
                """() => {
                  switchView('activity', document.getElementById('nav-activity'));
                  const report = document.getElementById('report-panel');
                  report.classList.remove('collapsed');
                  report.setAttribute('aria-hidden', 'false');
                  activateDialog(report, document.getElementById('nav-activity'));
                }"""
            )
            cases = [
                ("report-unavailable", "digest", "report", "unavailable"),
                ("report-not-retained", "digest", "report", "not_retained"),
                ("result-unavailable", "questions", "result", "unavailable"),
                ("result-not-retained", "questions", "result", "not_retained"),
            ]
            for task_id, task_type, kind, state in cases:
                result = page.evaluate(
                    """task => {
                      openTaskRenderKey = null;
                      selectedTaskId = task.id;
                      currentReceipt = null;
                      revalidateOpenTask([task]);
                      const panel = document.getElementById('panel-body');
                      const firstButton = panel.querySelector('.artifact-state-card button');
                      const firstAlert = panel.querySelector('.stale-artifact');
                      firstButton.id = `poll-action-${task.id}`;
                      firstButton.focus();
                      revalidateOpenTask([{...task, artifact: {...task.artifact}}]);
                      return {
                        sameButton: firstButton === panel.querySelector('.artifact-state-card button'),
                        sameAlert: firstAlert === panel.querySelector('.stale-artifact'),
                        focus: document.activeElement.id,
                        focusInsideReport: document.getElementById('report-panel')
                          .contains(document.activeElement),
                        activeDialog: activeDialogSurface?.id || null,
                      };
                    }""",
                    {
                        "id": task_id,
                        "type": task_type,
                        "status": "done",
                        "derived_content_stale": True,
                        "derived_content_stale_reason": ("patient_record_changed_after_generation"),
                        "artifact": {
                            "kind": kind,
                            "state": state,
                            "freshness": "unknown",
                        },
                    },
                )
                assert result == {
                    "sameButton": True,
                    "sameAlert": True,
                    "focus": f"poll-action-{task_id}",
                    "focusInsideReport": True,
                    "activeDialog": "report-panel",
                }

            stale_result_copy = page.evaluate(
                """() => ({
                  available: staleResultMarkup({
                    id: 'result-available',
                    type: 'questions',
                    status: 'done',
                    derived_content_stale: true,
                    derived_content_stale_reason: 'patient_record_changed_after_generation',
                    artifact: {kind: 'result', state: 'available', freshness: 'stale'},
                  }),
                  unavailable: staleResultMarkup({
                    id: 'result-unavailable',
                    type: 'questions',
                    status: 'done',
                    derived_content_stale: true,
                    derived_content_stale_reason: 'patient_record_changed_after_generation',
                    artifact: {kind: 'result', state: 'unavailable', freshness: 'unknown'},
                  }),
                })"""
            )
            assert "retained but hidden" in stale_result_copy["available"].lower()
            assert "not available here" not in stale_result_copy["available"].lower()
            assert "not available here" in stale_result_copy["unavailable"].lower()
            assert "retained" not in stale_result_copy["unavailable"].lower()
            assert "hidden here" not in stale_result_copy["unavailable"].lower()
        finally:
            context.close()
            browser.close()


def test_live_add_and_server_authorized_transition_use_full_reload():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            assert page.locator("#treatment-field-start-date").input_value() == ""
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("  Exact new wording  ")
            # Optional detail is now behind one closed disclosure. Leaving it
            # untouched must record "not provided", not an exact empty string.
            assert page.locator("#treatment-optional-details").get_attribute("open") is None
            page.locator("#treatment-field-start-date").fill("2027")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            page.locator("#nav-patient").click()
            assert "Exact new wording" in page.locator("#patient-treatment-list").inner_text()
            new_card = page.locator("#patient-treatment-list .treatment-course-card").filter(
                has_text="Exact new wording"
            )
            # Wave 1: the recorded-outcome vocabulary no longer uses "terminal",
            # which reads as a prognosis in an oncology app. The stored enum
            # values (not_started, cancelled, other) are unchanged.
            new_card.get_by_role("button", name="Record how it ended").click()
            options = page.locator("#treatment-field-terminal-qualifier option").all_inner_texts()
            assert options == [
                "Choose how it ended",
                "It never started",
                "The plan was cancelled before it started",
                "Something else",
            ]
            page.locator("#treatment-field-terminal-qualifier").select_option("not_started")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            new_card = page.locator("#patient-treatment-list .treatment-course-card").filter(
                has_text="Exact new wording"
            )
            assert "It never started" in new_card.inner_text()
            mutations = [
                item
                for item in state.requests
                if item[1].startswith("/api/treatment-reconciliation/")
            ]
            assert [item[0] for item in mutations] == ["POST", "POST"]
            assert mutations[0][2]["treatment_text"] == "  Exact new wording  "
            assert mutations[0][2]["treatment_type_text"] is None
            assert mutations[0][2]["start_date"] == "2027"
            assert mutations[1][2]["terminal_qualifier"] == "not_started"
            assert all(item[2]["mutation_id"] for item in mutations)
            assert not any(
                method == "POST" and path == "/api/follow-ups" for method, path, _ in state.requests
            )
            assert (
                sum(
                    path == "/api/patient/treatment-reconciliation" for _, path, _ in state.requests
                )
                == 3
            )
        finally:
            context.close()
            browser.close()


def test_live_server_authority_discrepancies_restart_outcomes_and_followups():
    playwright_api = pytest.importorskip("playwright.sync_api")
    projection = _projection_with_discrepancies()
    projection["courses"].append(
        _course(
            "9",
            "Earlier terminal authority",
            status="past",
            qualifier="legacy_unspecified",
        )
    )
    projection["courses"][2]["lifecycle"]["allowed_transitions"] = []
    projection["course_count"] = len(projection["courses"])
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(
            playwright,
            1280,
            900,
            projection,
        )
        try:
            page.locator("#nav-patient").click()
            past = page.locator(".treatment-course-card").filter(has_text="Past five")
            assert past.get_by_role("button", name="Create linked new record").count() == 1
            past.get_by_role("button", name="Create linked new record").click()
            assert page.locator("#treatment-field-status option").all_inner_texts() == [
                "Choose a record status",
                "Current record",
                "Planned record",
            ]
            assert page.locator("#treatment-field-treatment-text").input_value() == ""
            assert page.locator('input[name="treatment-component-choice"]:checked').count() == 0
            dialog_text = page.locator("#treatment-dialog").inner_text()
            assert "You choose this link" in dialog_text
            assert "Linked by you" in dialog_text
            assert "Duplicate source wording" not in dialog_text
            assert "Generated compatibility text" not in dialog_text
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            legacy = page.locator(".treatment-course-card").filter(
                has_text="Earlier terminal authority"
            )
            assert "How it ended was not recorded" in legacy.inner_text()
            assert legacy.get_by_role("button", name="Create linked new record").count() == 0
            no_transition = page.locator(".treatment-course-card").filter(has_text="Current three")
            assert no_transition.get_by_role("button", name="Record how it ended").count() == 0

            page.locator("#treatment-tab-differences").click()
            cards = page.locator(".treatment-discrepancy-card")
            assert cards.count() == 3
            first = cards.nth(0)
            assert (
                "Immutable source A a"
                in first.locator(".treatment-citation-snapshot").first.inner_text()
            )
            assert (
                "Duplicate source wording"
                in first.locator(".treatment-citation-current").first.inner_text()
            )
            assert first.get_by_role("button", name="Record treating-team outcome").count() == 1

            resolved = cards.nth(1)
            assert "You recorded this from the clinician" in resolved.inner_text()
            assert resolved.get_by_role("button", name="Reopen difference").count() == 1
            assert resolved.get_by_role("button", name="Record this difference again").count() == 1
            assert resolved.get_by_role("button", name="Record treating-team outcome").count() == 0

            incomplete = cards.nth(2)
            assert "The second record is missing from what was saved" in incomplete.inner_text()
            assert incomplete.locator(".treatment-card-actions button").count() == 0

            page.locator("#treatment-difference-add").click()
            assert page.locator('input[name="treatment-difference-variant"]:checked').count() == 0
            assert page.locator("#treatment-source-a option").count() == 3
            assert page.locator("#treatment-course-b option").count() == 7
            difference_text = page.locator("#treatment-dialog").inner_text()
            assert "Generated compatibility text" not in difference_text
            assert "same earlier wording" not in difference_text
            page.locator("#treatment-source-a").select_option("0")
            page.get_by_label("Another document mention").check()
            page.locator("#treatment-source-b").select_option("1")
            page.locator("#treatment-field-category").select_option("source_wording")
            page.locator("#treatment-field-comparison").fill("Exact neutral comparison")
            difference_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert difference_body["source_fact_ref"] == projection["source_facts"][0]["ref"]
            assert (
                difference_body["comparison_source_fact_ref"]
                == projection["source_facts"][1]["ref"]
            )
            assert "course_id" not in difference_body
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            first.get_by_role("button", name="Record treating-team outcome").click()
            page.locator("#treatment-field-outcome").select_option("caregiver_record_corrected")
            page.locator("#treatment-field-resolution-note").fill("Exact correction note")
            assert page.locator("#treatment-submit-button").is_disabled()
            page.locator("#treatment-field-treatment-text").fill("Explicit corrected wording")
            assert page.locator("#treatment-submit-button").is_enabled()
            resolve_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert resolve_body["course_patch"] == {"treatment_text": "Explicit corrected wording"}
            assert resolve_body["expected_course_token"] == projection["courses"][0]["token"]
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            resolved.get_by_role("button", name="Reopen difference").click()
            reopen_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert set(reopen_body) == {
                "expected_profile_revision",
                "expected_workflow_revision",
                "expected_projection_token",
                "expected_discrepancy_token",
            }
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            resolved.get_by_role("button", name="Record this difference again").click()
            page.locator("#treatment-field-category").select_option("other")
            page.locator("#treatment-field-comparison").fill("Exact recurrence wording")
            recurrence_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert recurrence_body["recurs_from_id"] == projection["discrepancies"][1]["id"]
            assert "source_fact_ref" not in recurrence_body
            assert "course_id" not in recurrence_body
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            resolved.get_by_role("button", name="Review linked follow-up").click()
            page.locator("#treatment-confirm-unlink").check()
            unlink_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert unlink_body["caregiver_action_id"] is None
            assert unlink_body["expected_action_token"] == "linked-action-token"
            assert "follow_up" not in unlink_body
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            first.get_by_role("button", name="Manage follow-up").click()
            page.get_by_label("Link one currently eligible existing follow-up").check()
            page.locator("#treatment-follow-up-existing").select_option("0")
            existing_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert existing_body["caregiver_action_id"] == "action-one"
            assert existing_body["expected_action_token"] == "action-token-one"
            assert "follow_up" not in existing_body
            page.get_by_label("Create and link one manual follow-up").check()
            page.locator("#treatment-follow-up-text").fill("  Exact inline follow-up  ")
            page.locator("#treatment-follow-up-due").fill("30.4.2027")
            inline_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert inline_body["follow_up"] == {
                "text": "  Exact inline follow-up  ",
                "owner": None,
                "due_date": "2027-04-30",
            }
            assert "caregiver_action_id" not in inline_body
            # A follow-up is due on a day, so a month-only entry is refused here
            # rather than after he presses save.
            page.locator("#treatment-follow-up-due").fill("4/2027")
            assert page.locator("#treatment-submit-button").is_disabled()
            page.locator("#treatment-follow-up-due").fill("2027-99")
            assert page.locator("#treatment-submit-button").is_disabled()

            assert page.evaluate(
                """() => {
                  const discrepancy = JSON.parse(JSON.stringify(treatmentProjection.discrepancies[0]));
                  const rotate = value => {
                    if (Array.isArray(value)) {
                      value.forEach(rotate);
                    } else if (value && typeof value === 'object') {
                      Object.keys(value).forEach(key => {
                        if (key === 'token') value[key] = `rotated-${value[key]}`;
                        else rotate(value[key]);
                      });
                    }
                  };
                  rotate(discrepancy);
                  return treatmentCompletionMatchesProjection({
                    profileRevision: treatmentProjection.profile_revision,
                    workflowRevision: treatmentProjection.workflow_revision,
                    discrepancy,
                    course: null,
                    followUp: null,
                    expectUnlinked: false,
                  });
                }"""
            )
        finally:
            context.close()
            browser.close()


def test_live_request_validation_get_corruption_eviction_and_focus_boundaries():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Safe rejected draft")
            state.next_mutation_status = 422
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            assert page.evaluate("() => treatmentProjectionState") == "current"
            assert page.evaluate("() => treatmentProjection !== null")
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "false"
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Safe rejected draft"
            )
            assert (
                "the treatment record is unchanged"
                in page.locator("#treatment-dialog-status").inner_text()
            )
            page.evaluate("() => closeTreatmentDialog(false, true, false)")

            page.locator("#today-treatment-heading").focus()
            focused = page.evaluate("() => document.activeElement.id")
            page.evaluate(
                "() => loadTreatmentReconciliation({ force: true }).then(() => undefined)"
            )
            assert page.evaluate("() => document.activeElement.id") == focused

            state.treatment_get_status = 422
            page.evaluate(
                "() => loadTreatmentReconciliation({ force: true }).then(() => undefined)"
            )
            assert page.evaluate("() => treatmentProjectionState") == "corrupt"
            assert page.evaluate("() => treatmentProjection === null")
            assert "Current one" not in page.locator("#today-treatment-list").inner_text()
            assert GUIDANCE not in page.locator("#treatment-today-card").inner_text()
            assert GUIDANCE not in page.locator("#treatment-workspace").inner_text()

            state.treatment_get_status = 200
            page.evaluate(
                "() => loadTreatmentReconciliation({ force: true }).then(() => undefined)"
            )
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("current")
            page.locator("#treatment-field-treatment-text").fill("PHI to evict")
            page.evaluate(
                """() => {
                  const error = new Error('auth');
                  error.status = 401;
                  evictClientPhi(error);
                }"""
            )
            assert page.evaluate("() => treatmentProjection === null")
            assert page.locator("#treatment-dialog-body").inner_text() == ""
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert "PHI to evict" not in page.content()
            assert GUIDANCE not in page.locator("#treatment-today-card").inner_text()
            assert not page.evaluate(
                "() => document.getElementById('treatment-dialog').contains(document.activeElement)"
            )
            assert page.evaluate("() => document.activeElement.id") == "nav-patient"
        finally:
            context.close()
            browser.close()


def test_live_workflow_staleness_and_repeated_verification_refresh_ownership():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            initial_gets = sum(
                path == "/api/patient/treatment-reconciliation" for _, path, _ in state.requests
            )
            state.projection["workflow_revision"] += 1
            page.evaluate(
                """revision => {
                  symptomProjection = null;
                  symptomRequestController = null;
                  const request = capturePatientRequest();
                  authorizePatientResponse(request, {
                    profile_revision: treatmentProjection.profile_revision,
                    workflow_revision: revision,
                  });
                }""",
                state.projection["workflow_revision"],
            )
            page.wait_for_function("() => treatmentProjectionState === 'current'")
            assert (
                sum(
                    path == "/api/patient/treatment-reconciliation" for _, path, _ in state.requests
                )
                == initial_gets + 1
            )

            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Verification refresh ownership")
            state.abort_next_treatment_get = True
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => pendingTreatmentCompletion !== null "
                "&& !document.getElementById('treatment-retry-verification').hidden"
            )
            assert page.evaluate("() => treatmentMutationPending")
            assert len(state.raw_mutation_bodies) == 1

            state.abort_next_treatment_get = True
            page.locator("#treatment-retry-verification").click()
            page.wait_for_function(
                "() => !document.getElementById('treatment-retry-verification').hidden"
            )
            assert page.evaluate(
                "() => treatmentMutationPending && pendingTreatmentCompletion !== null"
            )
            assert len(state.raw_mutation_bodies) == 1

            page.locator("#treatment-retry-verification").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            assert page.evaluate("() => pendingTreatmentCompletion === null")
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert len(state.raw_mutation_bodies) == 1
        finally:
            context.close()
            browser.close()


def test_live_submission_retry_conflict_draft_and_refresh_retry_are_separate():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Ambiguous exact bytes")
            state.abort_next_mutation = True
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => pendingTreatmentRetry !== null")
            assert page.locator("#treatment-retry-submit").is_visible()
            assert not page.locator("#today-treatment-retry-refresh").is_visible()
            page.locator("#treatment-retry-submit").click()
            page.wait_for_function("() => !treatmentMutationPending")
            assert len(state.raw_mutation_bodies) == 2
            assert state.raw_mutation_bodies[0] == state.raw_mutation_bodies[1]
            assert page.evaluate("() => pendingTreatmentRetry === null")

            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("current")
            page.locator("#treatment-field-treatment-text").fill("Mismatch request")
            state.mismatch_after_mutation = True
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'stale'"
            )
            assert page.locator("#treatment-retry").is_visible()
            assert not page.locator("#treatment-retry-submit").is_visible()
            assert page.evaluate("() => pendingTreatmentRetry === null")

            page.locator("#treatment-retry-refresh").click()
            page.wait_for_function("() => treatmentProjectionState === 'current'")
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Conflict-safe draft")
            page.locator('input[name="treatment-component-choice"]').first.check()
            state.next_mutation_status = 409
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            draft = page.evaluate(
                """() => ({
                  draft: treatmentDraft,
                  selection: treatmentSelection,
                  retry: pendingTreatmentRetry,
                })"""
            )
            assert draft["draft"]["mode"] == "add"
            assert draft["selection"] is None
            assert draft["retry"] is None
            serialized = json.dumps(draft["draft"])
            assert "token" not in serialized
            assert "txc_" not in serialized
            assert "txref_" not in serialized
            assert "treatment-component-choice" not in serialized

            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Conflict-safe draft"
            )
            assert page.locator('input[name="treatment-component-choice"]:checked').count() == 0
        finally:
            context.close()
            browser.close()


def test_recorded_treatment_rows_expose_status_recording_without_status_inference():
    source = _treatment_source()
    assert "function openTreatmentRecordedStatusDialog(" in source
    assert "prefillTreatmentText" in source
    assert "preselectedComponentIds" in source
    assert "Record status for ${row.raw_text}" in source
    recorded_dialog = source[
        source.index("function openTreatmentRecordedStatusDialog(") : source.index(
            "function openTreatmentCourseDialog("
        )
    ]
    # The in-place affordance may carry wording and component links only. It must
    # never choose clinical status, timing, or a terminal qualifier for the caregiver.
    for forbidden in (
        "status",
        "start_date",
        "stop_date",
        "planned_date",
        "terminal_qualifier",
        "terminal_detail",
    ):
        assert forbidden not in recorded_dialog
    assert "'add'" in recorded_dialog
    # Reuses the one existing creation contract; no second endpoint is introduced.
    assert source.count("url: '/api/treatment-reconciliation/courses'") == 1


@pytest.mark.parametrize("width,height", [(1280, 900), (768, 900), (360, 800)])
def test_live_recorded_row_records_status_prefilled_without_status_inference(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            width,
            height,
            _component_linkage_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            cards = page.locator("#patient-treatment-list .treatment-recorded-card")
            # Rows are listed newest-recorded first, so address this row by its
            # own wording rather than by position.
            unreviewed = cards.filter(has_text="None recorded treatment")
            assert unreviewed.count() == 1
            assert "No status recorded" in unreviewed.inner_text()
            action = unreviewed.get_by_role(
                "button", name="Record status for None recorded treatment"
            )
            assert action.count() == 1
            assert action.is_enabled()
            # Two affordances per recorded row — record a status, or hide the row
            # from this workspace — and the compact Today cards stay read-only.
            assert unreviewed.locator(".treatment-card-actions button").count() == 2
            assert (
                unreviewed.get_by_role(
                    "button", name="Mark None recorded treatment as not useful to me"
                ).count()
                == 1
            )
            assert (
                page.locator("#today-treatment-list .treatment-recorded-card button").count() == 0
            )

            action.click()
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "false"
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "None recorded treatment"
            )
            assert page.locator("#treatment-field-status").input_value() == ""
            for prefix in ("start", "stop", "planned"):
                assert page.locator(f"#treatment-field-{prefix}-date").input_value() == ""
            assert page.locator("#treatment-field-terminal-qualifier").input_value() == ""
            # No status is chosen for the caregiver, so saving stays blocked until they choose.
            assert page.locator("#treatment-submit-button").is_disabled()
            checked = page.evaluate(
                """() => [...document.querySelectorAll(
                  '#treatment-dialog input[name="treatment-component-choice"]:checked'
                )].map(input => treatmentSelection.componentOptions[Number(input.value)].id)"""
            )
            assert checked == ["none-1"]
            assert (
                "You still choose the record status"
                in page.locator("#treatment-dialog").inner_text()
            )

            page.locator("#treatment-field-status").select_option("current")
            assert page.locator("#treatment-submit-button").is_enabled()
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")

            mutations = [
                item
                for item in state.requests
                if item[0] == "POST" and item[1] == "/api/treatment-reconciliation/courses"
            ]
            assert len(mutations) == 1
            body = mutations[0][2]
            assert body["treatment_text"] == "None recorded treatment"
            assert body["status"] == "current"
            assert body["legacy_component_ids"] == ["none-1"]
            assert body["start_date"] is None
            assert body["stop_date"] is None
            assert body["planned_date"] is None
            assert body["terminal_qualifier"] is None
            assert body["expected_projection_token"] == "treatment-component-linkage"
            assert body["expected_profile_revision"] == 5
            assert body["expected_workflow_revision"] == 3
            assert body["mutation_id"]
            assert "expected_course_token" not in body

            page.locator("#nav-patient").click()
            refreshed = page.locator("#patient-treatment-list .treatment-recorded-card").filter(
                has_text="None recorded treatment"
            )
            assert "Linked to reviewed status" in refreshed.inner_text()
            assert "No status recorded" not in refreshed.inner_text()
            assert (
                "None recorded treatment"
                in page.locator("#patient-treatment-list .treatment-course-card")
                .filter(has_text="None recorded treatment")
                .inner_text()
            )
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow == 0
        finally:
            context.close()
            browser.close()


def test_live_recorded_row_status_action_is_keyboard_reachable_and_not_duplicated():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            1280,
            900,
            _component_linkage_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            action = (
                page.locator("#patient-treatment-list .treatment-recorded-card")
                .filter(has_text="None recorded treatment")
                .get_by_role("button", name="Record status for None recorded treatment")
            )
            action.focus()
            assert (
                page.evaluate("() => document.activeElement.dataset.treatmentRecordedRow")
                == "txlegacy-none"
            )
            page.keyboard.press("Enter")
            assert page.evaluate(
                "() => document.getElementById('treatment-dialog').contains(document.activeElement)"
            )
            assert page.evaluate(
                "() => document.getElementById('treatment-dialog').inert === false"
            )
            assert page.evaluate(
                "() => document.getElementById('treatment-workspace').closest('[inert]') !== null"
            )

            # Duplicate rapid activation must not rebuild the dialog or discard caregiver edits.
            epoch = page.evaluate("() => treatmentDialogEpoch")
            page.locator("#treatment-field-treatment-text").fill("Caregiver edited wording")
            page.evaluate(
                """() => openTreatmentRecordedStatusDialog(
                  document.querySelector(
                    '#patient-treatment-list .treatment-recorded-card button'
                  ),
                  'txlegacy-none',
                )"""
            )
            assert page.evaluate("() => treatmentDialogEpoch") == epoch
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Caregiver edited wording"
            )

            page.keyboard.press("Escape")
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert (
                page.evaluate("() => document.activeElement.dataset.treatmentRecordedRow")
                == "txlegacy-none"
            )
            assert page.evaluate(
                "() => document.getElementById('treatment-workspace').closest('[inert]') === null"
            )
            assert not any(
                method != "GET" and path.startswith("/api/treatment-reconciliation/")
                for method, path, _ in state.requests
            )
        finally:
            context.close()
            browser.close()


def test_live_recorded_row_status_conflict_leaves_row_unlinked():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            1280,
            900,
            _component_linkage_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-list .treatment-recorded-card").filter(
                has_text="None recorded treatment"
            ).get_by_role("button", name="Record status for None recorded treatment").click()
            page.locator("#treatment-field-status").select_option("planned")
            state.next_mutation_status = 409
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            assert page.evaluate("() => pendingTreatmentRetry === null")
            assert page.evaluate("() => treatmentDraft.recordedRowId") == "txlegacy-none"
            assert page.evaluate("() => treatmentProjection.courses.length") == 1
            page.locator("#nav-patient").click()
            cards = page.locator("#patient-treatment-list .treatment-recorded-card")
            assert (
                "No status recorded"
                in cards.filter(has_text="None recorded treatment").inner_text()
            )
            assert cards.count() == 3

            # The preserved draft is still live and belongs to that row, so a
            # plain add must not inherit it.
            assert page.evaluate("() => treatmentDraft !== null")
            page.locator("#patient-treatment-add").click()
            assert page.locator("#treatment-field-treatment-text").input_value() == ""
            assert page.locator("#treatment-field-status").input_value() == ""
            assert page.locator('input[name="treatment-component-choice"]:checked').count() == 0
        finally:
            context.close()
            browser.close()


def test_live_recorded_row_reopen_does_not_reassert_removed_component_link():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            1280,
            900,
            _component_linkage_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-list .treatment-recorded-card").filter(
                has_text="None recorded treatment"
            ).get_by_role("button", name="Record status for None recorded treatment").click()
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Caregiver wording X")
            # The caregiver explicitly removes the pre-ticked component link.
            page.locator('input[name="treatment-component-choice"]').first.uncheck()
            state.next_mutation_status = 409
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            assert page.evaluate("() => treatmentDraft.recordedRowId") == "txlegacy-none"

            # Reopening the same row restores the caregiver draft, but the row
            # prefill must never re-assert a link the caregiver removed.
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-list .treatment-recorded-card").filter(
                has_text="None recorded treatment"
            ).get_by_role("button", name="Record status for None recorded treatment").click()
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Caregiver wording X"
            )
            assert page.locator('input[name="treatment-component-choice"]:checked').count() == 0
            assert (
                "Choose the component links again" in page.locator("#treatment-dialog").inner_text()
            )
            # The restored status is the caregiver's own earlier choice, never
            # anything the row prefill supplied.
            assert page.locator("#treatment-field-status").input_value() == "planned"
        finally:
            context.close()
            browser.close()


# ── Caregiver-sized recording dialog ───────────────────────────────────────

_OPTIONAL_FIELDS = (
    "treatment_type_text",
    "dose_text",
    "route_text",
    "frequency_text",
    "cycle_text",
    "schedule_text",
    "formulation_text",
    "indication_text",
    "notes",
)


def _mention_projection() -> dict:
    """Two mentions with distinct wording and no recorded status yet."""
    projection = _projection()
    mentions = [
        _source("1", "Continued Somatuline Autogel (lanreotide) 120 mg every 4 weeks"),
        _source("2", "Everolimus 10 mg daily was stopped"),
    ]
    projection.update(
        {
            "projection_token": "treatment-mentions",
            "source_facts": mentions,
            "source_fact_count": len(mentions),
            "courses": [],
            "course_count": 0,
            "discrepancies": [],
            "discrepancy_count": 0,
            "unlinked_generated_context": [],
            "unlinked_generated_context_count": 0,
        }
    )
    return projection


def test_dialog_drops_the_null_versus_empty_string_control():
    source = _treatment_source()
    # The database distinction was never an invariant and is meaningless to a
    # caregiver, so neither the control nor its wiring may survive.
    assert "Record an exact empty string instead of Null" not in source
    assert "treatment-empty-" not in source
    assert "treatment-empty-toggle" not in CSS
    assert "treatment-empty-" not in INDEX_HTML
    # What replaces it is a stored-value marker, so an untouched empty box
    # round-trips to whatever is already saved instead of rewriting it.
    assert "storedEmptyString" in source
    assert "control?.dataset.storedEmptyString === 'true' ? '' : null" in source


def test_optional_wording_sits_behind_one_closed_disclosure():
    source = _treatment_source()
    assert "treatment-optional-details" in source
    assert "Add more detail (optional)" in source
    # Closed by default: the element is never created with `open` preset, and
    # only content re-opens it.
    assert "optional.open = true" not in source
    assert "details.open = true" in source
    assert "function syncTreatmentOptionalDisclosure(" in source
    # A native disclosure keeps keyboard reachability and expanded state for free.
    assert "treatmentElement('details'" in source
    assert "treatmentElement('summary')" in source


def test_current_and_planned_empty_state_names_the_recording_action():
    source = _treatment_source()
    start = source.index("const routes = ['use Add status record above'];")
    empty_state = source[start : source.index("'Finished or past',", start)]
    assert "Record status on a recorded treatment entry below" in empty_state
    assert "mention in source documents" in empty_state
    assert "use Add status record above" in empty_state
    assert "You choose the status and any dates." in empty_state
    # Only routes that exist right now may be offered: the two row-bound actions
    # are gated on rows actually being on the page.
    assert "if (recordedRows.length) {" in empty_state
    assert "if (treatmentProjection.source_facts.length) {" in empty_state
    # It must not promise that anything happens on its own, and must assert
    # nothing clinical about the patient.
    for forbidden in ("will appear", "automatically", "we ", "once treatment", "is not on"):
        assert forbidden not in empty_state


def test_source_document_mentions_expose_status_recording_without_inference():
    source = _treatment_source()
    assert "function openTreatmentSourceStatusDialog(" in source
    assert "Record status for ${source.observed_text}" in source
    mention_dialog = source[
        source.index("function openTreatmentSourceStatusDialog(") : source.index(
            "function openTreatmentRecordedStatusDialog("
        )
    ]
    # The mention may seed wording only. Source facts carry no temporal data and
    # `operation` is list-membership, so nothing clinical may be read from them.
    for forbidden in (
        "status",
        "start_date",
        "stop_date",
        "planned_date",
        "terminal_qualifier",
        "terminal_detail",
        "legacy_component_ids",
        "operation",
    ):
        assert forbidden not in mention_dialog
    assert "'add'" in mention_dialog
    # Still exactly one creation contract; no second endpoint was invented.
    assert source.count("url: '/api/treatment-reconciliation/courses'") == 1


@pytest.mark.parametrize("width,height", [(1280, 900), (768, 900), (360, 800)])
def test_live_optional_detail_is_collapsed_and_empty_boxes_record_nothing(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, width, height)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()

            # No null-versus-empty control survives anywhere in the dialog.
            assert page.locator("#treatment-dialog .treatment-empty-toggle").count() == 0
            assert page.locator('#treatment-dialog input[id^="treatment-empty-"]').count() == 0
            assert "empty string" not in page.locator("#treatment-dialog").inner_text().lower()

            details = page.locator("#treatment-optional-details")
            assert details.count() == 1
            assert details.get_attribute("open") is None
            assert page.locator("#treatment-optional-count").is_hidden()
            # Status, wording and the three dates stay up front; the nine
            # optional boxes are the only thing behind the disclosure.
            for field in _OPTIONAL_FIELDS:
                control = f"#treatment-field-{field.replace('_', '-')}"
                assert page.locator(control).count() == 1
                assert page.locator(control).is_hidden()
                assert details.locator(control).count() == 1
            for visible in ("status", "treatment-text", "start-date", "stop-date", "planned-date"):
                assert page.locator(f"#treatment-field-{visible}").is_visible()
                assert details.locator(f"#treatment-field-{visible}").count() == 0

            page.locator("#treatment-field-status").select_option("current")
            page.locator("#treatment-field-treatment-text").fill(
                "Continued Somatuline Autogel (lanreotide) 120 mg subcutaneously every 4 weeks"
            )
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")

            body = [
                item
                for item in state.requests
                if item[0] == "POST" and item[1] == "/api/treatment-reconciliation/courses"
            ][0][2]
            # An untouched empty box on a new record means "not provided".
            for field in _OPTIONAL_FIELDS:
                assert body[field] is None, field
            assert body["treatment_text"].startswith("Continued Somatuline Autogel")
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow == 0
        finally:
            context.close()
            browser.close()


def test_live_editing_preserves_a_stored_empty_string_and_reveals_existing_detail():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-list .treatment-course-card").filter(
                has_text="Current one"
            ).get_by_role("button", name="Edit recorded details").click()

            # The saved record already carries route and schedule wording, so
            # nothing may stay hidden behind a closed disclosure.
            details = page.locator("#treatment-optional-details")
            assert details.get_attribute("open") is not None
            assert page.locator("#treatment-optional-count").inner_text() == "2 filled in"
            assert page.locator("#treatment-field-route-text").is_visible()
            assert page.locator("#treatment-field-route-text").input_value() == "  exact route  "

            # treatment_type_text and cycle_text store exact empty strings and
            # render identically to the stored nulls beside them.
            for field in ("treatment-type-text", "cycle-text", "dose-text", "notes"):
                assert page.locator(f"#treatment-field-{field}").input_value() == ""
            marked = page.evaluate(
                """() => Object.fromEntries(
                  [...document.querySelectorAll('#treatment-optional-details input, '
                    + '#treatment-optional-details textarea')]
                    .map(control => [control.name, control.dataset.storedEmptyString === 'true'])
                )"""
            )
            assert marked["treatment_type_text"] is True
            assert marked["cycle_text"] is True
            assert marked["dose_text"] is False
            assert marked["notes"] is False

            # Typing into a stored-empty box and clearing it again returns the
            # box to exactly the state it was rendered in, so the stored empty
            # string must survive rather than silently flipping to null.
            page.locator("#treatment-field-treatment-type-text").fill("typed then removed")
            page.locator("#treatment-field-treatment-type-text").fill("")
            page.locator("#treatment-field-notes").fill("Caregiver note")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")

            patches = [
                item
                for item in state.requests
                if item[0] == "PATCH" and item[1].startswith("/api/treatment-reconciliation/")
            ]
            assert len(patches) == 1
            body = patches[0][2]
            assert body["treatment_type_text"] == ""
            assert body["cycle_text"] == ""
            assert body["dose_text"] is None
            assert body["frequency_text"] is None
            assert body["route_text"] == "  exact route  "
            assert body["schedule_text"] == "Every four weeks"
            assert body["notes"] == "Caregiver note"
            assert body["expected_course_token"]
            assert body["mutation_id"]
        finally:
            context.close()
            browser.close()


def test_live_disclosure_is_keyboard_operable_and_reveals_restored_draft_content():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            summary = page.locator("#treatment-optional-details > summary")
            summary.focus()
            assert page.evaluate("() => document.activeElement.tagName") == "SUMMARY"
            assert "Add more detail" in summary.inner_text()
            page.keyboard.press("Enter")
            assert page.locator("#treatment-optional-details").get_attribute("open") is not None
            assert page.locator("#treatment-field-dose-text").is_visible()
            page.keyboard.press("Enter")
            assert page.locator("#treatment-optional-details").get_attribute("open") is None

            # A draft preserved through a conflict must not be tucked away.
            summary.focus()
            page.keyboard.press("Enter")
            page.locator("#treatment-field-status").select_option("planned")
            page.locator("#treatment-field-treatment-text").fill("Exact caregiver wording")
            page.locator("#treatment-field-dose-text").fill("120 mg")
            state.next_mutation_status = 409
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            assert page.evaluate("() => treatmentProjection.courses.length") == 5

            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            assert page.locator("#treatment-field-dose-text").input_value() == "120 mg"
            assert page.locator("#treatment-optional-details").get_attribute("open") is not None
            assert page.locator("#treatment-optional-count").inner_text() == "1 filled in"
        finally:
            context.close()
            browser.close()


def test_live_collapsed_disclosure_keeps_saying_what_it_holds():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            details = page.locator("#treatment-optional-details")
            count = page.locator("#treatment-optional-count")
            summary = page.locator("#treatment-optional-details > summary")
            assert count.is_hidden()

            # Typing behind an open disclosure updates the summary immediately,
            # so folding it away can never conceal wording that will be sent.
            summary.click()
            page.locator("#treatment-field-dose-text").fill("120 mg")
            assert count.inner_text() == "1 filled in"
            page.locator("#treatment-field-notes").fill("Caregiver note")
            assert count.inner_text() == "2 filled in"
            summary.click()
            assert details.get_attribute("open") is None
            assert count.is_visible()
            assert count.inner_text() == "2 filled in"
            assert page.locator("#treatment-field-dose-text").is_hidden()

            # Emptying the boxes again retires the badge rather than leaving a
            # stale count claiming content that is no longer there.
            summary.click()
            page.locator("#treatment-field-dose-text").fill("")
            assert count.inner_text() == "1 filled in"
            page.locator("#treatment-field-notes").fill("")
            assert count.is_hidden()

            # A collapsed-but-filled disclosure still submits what it holds.
            page.locator("#treatment-field-dose-text").fill("120 mg")
            summary.click()
            assert details.get_attribute("open") is None
            page.locator("#treatment-field-status").select_option("current")
            page.locator("#treatment-field-treatment-text").fill("Exact caregiver wording")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            posts = [
                entry
                for entry in state.requests
                if entry[0] == "POST" and entry[1] == "/api/treatment-reconciliation/courses"
            ]
            assert len(posts) == 1
            assert posts[0][2]["dose_text"] == "120 mg"
            assert posts[0][2]["notes"] is None
        finally:
            context.close()
            browser.close()


def test_live_empty_state_only_offers_routes_that_exist():
    playwright_api = pytest.importorskip("playwright.sync_api")
    bare = _projection()
    bare["courses"] = []
    bare["course_count"] = 0
    bare["discrepancies"] = []
    bare["discrepancy_count"] = 0
    bare["legacy_treatments"] = []
    bare["legacy_treatment_count"] = 0
    _sync_dispositions(bare)
    bare["source_facts"] = []
    bare["source_fact_documents"] = []
    bare["source_fact_count"] = 0
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(playwright, 1280, 900, bare)
        try:
            page.locator("#nav-patient").click()
            empty = " ".join(
                page.locator("#patient-treatment-list .empty-state").first.inner_text().split()
            )
            # Neither row-bound action exists on this page, so neither may be
            # named: sending the caregiver to a surface that reads "No document
            # treatment mentions are recorded." is another dead end.
            assert "use Add status record above" in empty
            assert "recorded treatment entry" not in empty
            assert "mention in source documents" not in empty
            assert "You choose the status and any dates." in empty
        finally:
            context.close()
            browser.close()

        # With rows present, both routes are named again.
        browser, context, page, state = _open_treatment_page(
            playwright, 1280, 900, _mention_projection()
        )
        try:
            page.locator("#nav-patient").click()
            empty = " ".join(
                page.locator("#patient-treatment-list .empty-state").first.inner_text().split()
            )
            assert "use Add status record above" in empty
            assert "Record status on a recorded treatment entry below" in empty
            assert "Record status on a mention in source documents" in empty
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", [(1280, 900), (768, 900), (360, 800)])
def test_live_document_mention_records_status_prefilled_from_observed_text(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            width,
            height,
            _mention_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            # The dead-end empty state now names the action that fills it.
            empty_state = page.locator("#patient-treatment-list .empty-state").first.inner_text()
            assert "Record status on a recorded treatment entry below" in empty_state
            assert "mention in source documents" in empty_state

            page.locator("#treatment-tab-sources").click()
            rows = page.locator("#treatment-source-table-body tr")
            assert rows.count() == 2
            # "was stopped" is clinician wording inside the mention. The import
            # operation stays list-membership, so the row still reads as added.
            stopped = rows.filter(has_text="Everolimus 10 mg daily was stopped")
            assert "Added from the document" in stopped.inner_text()
            assert "Exact wording available" in stopped.inner_text()
            action = stopped.get_by_role(
                "button", name="Record status for Everolimus 10 mg daily was stopped"
            )
            assert action.count() == 1
            assert action.is_enabled()
            action.click()

            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "false"
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Everolimus 10 mg daily was stopped"
            )
            # Nothing clinical is chosen for the caregiver.
            assert page.locator("#treatment-field-status").input_value() == ""
            for prefix in ("start", "stop", "planned"):
                assert page.locator(f"#treatment-field-{prefix}-date").input_value() == ""
            assert page.locator("#treatment-field-terminal-qualifier").input_value() == ""
            assert page.locator('input[name="treatment-component-choice"]:checked').count() == 0
            assert page.locator("#treatment-submit-button").is_disabled()
            note = page.locator("#treatment-dialog .treatment-authority-note").inner_text()
            # The copy may not claim an anchor the record does not carry: nothing
            # in the saved course refers back to the document or the mention.
            assert "not stored as a quotation and is not linked back to that document" in note
            assert "anchored" not in note
            assert "no timing or status is preselected" in note
            # The prefilled wording stays editable.
            assert page.locator("#treatment-field-treatment-text").is_editable()

            page.locator("#treatment-field-status").select_option("past")
            page.locator("#treatment-field-terminal-qualifier").select_option("ended")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")

            mutations = [
                item
                for item in state.requests
                if item[0] == "POST" and item[1] == "/api/treatment-reconciliation/courses"
            ]
            assert len(mutations) == 1
            body = mutations[0][2]
            assert body["treatment_text"] == "Everolimus 10 mg daily was stopped"
            assert body["status"] == "past"
            assert body["terminal_qualifier"] == "ended"
            assert body["legacy_component_ids"] == []
            assert body["start_date"] is None
            assert body["stop_date"] is None
            assert body["planned_date"] is None
            assert all(body[field] is None for field in _OPTIONAL_FIELDS)
            assert body["expected_projection_token"] == "treatment-mentions"
            assert body["expected_profile_revision"] == 5
            assert body["expected_workflow_revision"] == 3
            assert body["mutation_id"]
            assert "expected_course_token" not in body
            assert json.loads(state.raw_mutation_bodies[0]) == body

            page.locator("#nav-patient").click()
            assert (
                "Everolimus 10 mg daily was stopped"
                in page.locator("#patient-treatment-list").inner_text()
            )
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow == 0
        finally:
            context.close()
            browser.close()


def test_live_document_mention_conflict_is_scoped_and_leaves_the_record_untouched():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            1280,
            900,
            _mention_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            page.locator("#treatment-tab-sources").click()
            page.locator("#treatment-source-table-body tr").filter(
                has_text="Everolimus 10 mg daily was stopped"
            ).get_by_role(
                "button", name="Record status for Everolimus 10 mg daily was stopped"
            ).click()
            page.locator("#treatment-field-status").select_option("planned")
            state.next_mutation_status = 409
            page.locator("#treatment-submit-button").click()
            page.wait_for_function(
                "() => !treatmentMutationPending && treatmentProjectionState === 'current'"
            )
            assert page.evaluate("() => pendingTreatmentRetry === null")
            assert page.evaluate("() => treatmentProjection.courses.length") == 0
            assert page.evaluate("() => treatmentDraft.sourceFactRef") == f"txref_{'2' * 64}"

            # The draft belongs to that one mention, so no other creation path
            # may inherit it.
            page.locator("#nav-patient").click()
            page.locator("#patient-treatment-add").click()
            assert page.locator("#treatment-field-treatment-text").input_value() == ""
            assert page.locator("#treatment-field-status").input_value() == ""
            page.keyboard.press("Escape")
            page.locator("#treatment-tab-sources").click()
            other = page.locator("#treatment-source-table-body tr").filter(
                has_text="Continued Somatuline Autogel"
            )
            other.get_by_role(
                "button",
                name="Record status for Continued Somatuline Autogel (lanreotide) 120 mg every 4 weeks",
            ).click()
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Continued Somatuline Autogel (lanreotide) 120 mg every 4 weeks"
            )
            assert page.locator("#treatment-field-status").input_value() == ""
        finally:
            context.close()
            browser.close()


def test_live_document_mention_action_is_keyboard_reachable_and_not_duplicated():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_treatment_page(
            playwright,
            1280,
            900,
            _mention_projection(),
        )
        try:
            page.locator("#nav-patient").click()
            page.locator("#treatment-tab-sources").click()
            ref = f"txref_{'2' * 64}"
            action = page.locator(f'button[data-treatment-source-ref="{ref}"]')
            assert action.count() == 1
            action.focus()
            assert page.evaluate("() => document.activeElement.dataset.treatmentSourceRef") == ref
            page.keyboard.press("Enter")
            assert page.evaluate(
                "() => document.getElementById('treatment-dialog').contains(document.activeElement)"
            )
            assert page.evaluate(
                "() => document.getElementById('treatment-dialog').inert === false"
            )
            assert page.evaluate(
                "() => document.getElementById('treatment-workspace').closest('[inert]') !== null"
            )

            # Duplicate rapid activation must not rebuild the dialog or discard edits.
            epoch = page.evaluate("() => treatmentDialogEpoch")
            page.locator("#treatment-field-treatment-text").fill("Caregiver edited wording")
            page.evaluate(
                """(ref) => openTreatmentSourceStatusDialog(
                  document.querySelector(`button[data-treatment-source-ref="${ref}"]`),
                  ref,
                )""",
                ref,
            )
            assert page.evaluate("() => treatmentDialogEpoch") == epoch
            assert (
                page.locator("#treatment-field-treatment-text").input_value()
                == "Caregiver edited wording"
            )

            page.keyboard.press("Escape")
            assert page.locator("#treatment-dialog-overlay").get_attribute("aria-hidden") == "true"
            # Focus returns to the mention row action only after inert clears.
            assert page.evaluate("() => document.activeElement.dataset.treatmentSourceRef") == ref
            assert page.evaluate(
                "() => document.getElementById('treatment-workspace').closest('[inert]') === null"
            )
            assert not any(
                method != "GET" and path.startswith("/api/treatment-reconciliation/")
                for method, path, _ in state.requests
            )
        finally:
            context.close()
            browser.close()


# ── Newest-first display ordering ──────────────────────────────────────────


def _date_precision(value: str | None) -> str:
    if value is None:
        return "unknown"
    return {4: "year", 7: "month"}.get(len(value), "day")


def _dated_course(
    character: str,
    text: str,
    *,
    status: str,
    start: str | None = None,
    stop: str | None = None,
    planned: str | None = None,
    qualifier: str | None = None,
    component_ids: list[str] | None = None,
) -> dict:
    course = _course(
        character, text, status=status, qualifier=qualifier, component_ids=component_ids
    )
    for prefix, value in (("start", start), ("stop", stop), ("planned", planned)):
        course[f"{prefix}_date"] = value
        course[f"{prefix}_date_precision"] = _date_precision(value)
        course[f"{prefix}_date_kind"] = "unknown" if value is None else "caregiver_entered"
    return course


def _recorded_row(name: str, source_order: int, raw_text: str, generated_date: str | None) -> dict:
    row = _legacy()
    row["id"] = f"txlegacy-{name}"
    row["token"] = f"legacy-token-{name}"
    row["raw_text"] = raw_text
    row["source_order"] = source_order
    row["components"] = [
        {"id": f"component-{name}", "text": raw_text, "component_order": 0},
    ]
    row["generated_classification"] = [
        {
            "id": f"generated-{name}",
            "text": f"Generated compatibility text {name}",
            "label": None,
            "category": None,
            "date": generated_date,
            "source_treatment_ids": [f"component-{name}"],
        }
    ]
    return row


def _ordering_projection() -> dict:
    # Stored order is deliberately not the expected display order, so any
    # renderer that keeps stored order for treatments fails these tests.
    courses = [
        _dated_course("a", "Current no date", status="current"),
        # The planned date, not the misleading start date, places a planned row.
        _dated_course(
            "b", "Planned early", status="planned", planned="2024-02-02", start="2098-01-01"
        ),
        # The start date, not the misleading planned date, places a current row.
        _dated_course(
            "c", "Current mid", status="current", start="2026-03-15", planned="2099-01-01"
        ),
        # The newest-dated course of all is linked to the oldest recorded row,
        # so borrowing a linked course's date would move that row to the top.
        _dated_course(
            "d",
            "Planned late",
            status="planned",
            planned="2027-05-04",
            component_ids=["component-oldest"],
        ),
        _dated_course("e", "Past no date", status="past", qualifier="ended"),
        _dated_course(
            "f",
            "Past stopped",
            status="past",
            stop="2023-08-09",
            start="2010-01-01",
            qualifier="ended",
        ),
        # No stop date was recorded, so the start date places this past row.
        _dated_course(
            "0", "Past fallback start", status="past", start="2024-06-01", qualifier="ended"
        ),
    ]
    # Generated compatibility dates run opposite to the recorded order; they
    # must never be read as treatment timing.
    recorded = [
        _recorded_row("oldest", 0, "Recorded oldest", "2099-01-01"),
        _recorded_row("dup-a", 1, "Recorded duplicate wording", "2098-01-01"),
        _recorded_row("dup-b", 2, "Recorded duplicate wording", "2097-01-01"),
        _recorded_row("newest", 3, "Recorded newest", "2000-01-01"),
    ]
    projection = _projection()
    projection.update(
        {
            "projection_token": "treatment-ordering",
            "legacy_treatment_count": len(recorded),
            "course_count": len(courses),
            "discrepancy_count": 0,
            "legacy_treatments": recorded,
            "courses": courses,
            "discrepancies": [],
        }
    )
    return _sync_dispositions(projection)


def _run_treatment_ordering(body: str):
    script = "\n".join(
        [
            """
const document = { baseURI: 'http://app.test/' };
const window = {
  location: { href: 'http://app.test/', origin: 'http://app.test' },
};
""",
            _treatment_source(),
            body,
        ]
    )
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _sorted_course_ids(courses: list[dict]) -> list[str]:
    return _run_treatment_ordering(
        "const courses = JSON.parse("
        + json.dumps(json.dumps(courses))
        + ");\n"
        + "console.log(JSON.stringify(treatmentSortedCourses(courses).map(item => item.id)));\n"
    )


def _sorted_recorded_ids(rows: list[dict]) -> list[str]:
    return _run_treatment_ordering(
        "const rows = JSON.parse("
        + json.dumps(json.dumps(rows))
        + ");\n"
        + "console.log(JSON.stringify(treatmentSortedRecordedRows(rows).map(item => item.id)));\n"
    )


def test_courses_order_newest_first_by_the_date_their_own_status_is_about():
    projection = _ordering_projection()
    active = [
        course for course in projection["courses"] if course["status"] in {"current", "planned"}
    ]
    past = [course for course in projection["courses"] if course["status"] == "past"]

    # Planned rows are placed by planned_date, current rows by start_date, and
    # the misleading opposite date on each row must be ignored.
    assert _sorted_course_ids(active) == [
        "txc_" + "d" * 32,  # planned 2027-05-04
        "txc_" + "c" * 32,  # current 2026-03-15
        "txc_" + "b" * 32,  # planned 2024-02-02
        "txc_" + "a" * 32,  # no usable date lands last
    ]
    # Past rows are placed by stop_date, falling back to start_date only when
    # no stop date was recorded.
    assert _sorted_course_ids(past) == [
        "txc_" + "0" * 32,  # start 2024-06-01, no stop date recorded
        "txc_" + "f" * 32,  # stop 2023-08-09
        "txc_" + "e" * 32,  # no usable date lands last
    ]


def test_partial_precision_dates_sort_at_the_start_of_the_period_they_name():
    courses = [
        _dated_course("a", "Exact March day", status="current", start="2026-03-15"),
        _dated_course("b", "March only", status="current", start="2026-03"),
        _dated_course("c", "Year only", status="current", start="2026"),
        _dated_course("d", "Exact February day", status="current", start="2026-02-28"),
        _dated_course("e", "Previous December day", status="current", start="2025-12-31"),
    ]

    # A partial date is ordered at the start of the period it names: month-only
    # 2026-03 sits below every March day but above 2026-02-28, and year-only
    # 2026 sits below every 2026 date but above 2025-12-31.
    assert _sorted_course_ids(courses) == [
        "txc_" + "a" * 32,
        "txc_" + "b" * 32,
        "txc_" + "d" * 32,
        "txc_" + "c" * 32,
        "txc_" + "e" * 32,
    ]


def test_courses_without_a_usable_date_hold_a_fixed_last_position():
    dated = _dated_course("a", "Dated", status="current", start="2026-03-15")
    missing = _dated_course("b", "Missing date", status="current")
    unparsable = _dated_course("c", "Dated", status="current", start="2026-03-15")
    unparsable["start_date"] = "not-a-date"
    unparsable["start_date_precision"] = "unknown"

    for order in ([dated, missing, unparsable], [unparsable, missing, dated]):
        assert _sorted_course_ids(order) == [
            "txc_" + "a" * 32,
            "txc_" + "b" * 32,
            "txc_" + "c" * 32,
        ]


def test_equal_sort_keys_fall_back_to_a_stable_identity_tiebreak():
    first = _dated_course("a", "Same day one", status="current", start="2026-03-15")
    second = _dated_course("b", "Same day two", status="current", start="2026-03-15")
    third = _dated_course("c", "Same day three", status="current", start="2026-03-15")
    expected = ["txc_" + character * 32 for character in "abc"]

    # Identical keys never leave the order to input arrangement.
    assert _sorted_course_ids([third, first, second]) == expected
    assert _sorted_course_ids([first, second, third]) == expected
    assert _sorted_course_ids([second, third, first]) == expected

    undated = [
        _dated_course("d", "No date one", status="current"),
        _dated_course("e", "No date two", status="current"),
    ]
    assert _sorted_course_ids(undated) == _sorted_course_ids(list(reversed(undated)))

    # Recorded rows share the same total, content-determined tiebreak.
    duplicate_order = [
        _recorded_row("zz", 5, "Same recorded order", None),
        _recorded_row("aa", 5, "Same recorded order", None),
    ]
    assert _sorted_recorded_ids(duplicate_order) == ["txlegacy-aa", "txlegacy-zz"]
    assert _sorted_recorded_ids(list(reversed(duplicate_order))) == [
        "txlegacy-aa",
        "txlegacy-zz",
    ]


def test_recorded_rows_order_newest_recorded_first_without_inventing_a_date():
    # The recorded sort key may read nothing except the recorded order.
    start = APP_JS.index("function treatmentRecordedSortValue")
    end = APP_JS.index("function treatmentSortedRecordedRows", start)
    key_source = APP_JS[start:end]
    assert "source_order" in key_source
    for forbidden in (
        "raw_text",
        "components",
        "generated_classification",
        "date",
        "course",
    ):
        assert forbidden not in key_source

    rows = _ordering_projection()["legacy_treatments"]

    # source_order descending is the only recency signal; the generated
    # compatibility dates on these rows run the other way and are ignored.
    assert _sorted_recorded_ids(rows) == [
        "txlegacy-newest",
        "txlegacy-dup-b",
        "txlegacy-dup-a",
        "txlegacy-oldest",
    ]

    # No date is parsed out of raw wording either.
    worded = [
        _recorded_row("first", 0, "Lanreotide from 2099-01-01", None),
        _recorded_row("second", 1, "Everolimus from 2000-01-01", None),
    ]
    assert _sorted_recorded_ids(worded) == ["txlegacy-second", "txlegacy-first"]


def test_recorded_ordering_never_borrows_a_linked_course_date():
    projection = _ordering_projection()
    rows = projection["legacy_treatments"]
    linked = [course for course in projection["courses"] if course["legacy_component_ids"]]
    # The linkage the rule is about must actually exist in the fixture.
    assert [course["treatment_text"] for course in linked] == ["Planned late"]
    assert linked[0]["planned_date"] == "2027-05-04"
    assert linked[0]["legacy_component_ids"] == ["component-oldest"]
    assert rows[0]["id"] == "txlegacy-oldest"
    assert rows[0]["components"][0]["id"] == "component-oldest"

    # The oldest recorded row is the one linked to the newest-dated course.
    # Ordering must still be by recorded order, never by that course's date.
    expected = ["txlegacy-newest", "txlegacy-dup-b", "txlegacy-dup-a", "txlegacy-oldest"]
    assert _sorted_recorded_ids(rows) == expected
    assert _sorted_recorded_ids(list(reversed(rows))) == expected

    # Dropping the linkage entirely must not move a single row.
    unlinked = _ordering_projection()
    for course in unlinked["courses"]:
        course["legacy_component_ids"] = []
    assert _sorted_recorded_ids(unlinked["legacy_treatments"]) == expected


def test_ordering_is_presentation_only_and_keeps_every_row_exactly_once():
    projection = _ordering_projection()
    course_ids = [course["id"] for course in projection["courses"]]
    recorded_ids = [row["id"] for row in projection["legacy_treatments"]]

    assert sorted(_sorted_course_ids(projection["courses"])) == sorted(course_ids)
    assert sorted(_sorted_recorded_ids(projection["legacy_treatments"])) == sorted(recorded_ids)

    duplicates = projection["legacy_treatments"] + [
        _recorded_row("dup-c", 2, "Recorded duplicate wording", None)
    ]
    assert len(_sorted_recorded_ids(duplicates)) == len(duplicates)


@pytest.mark.parametrize("width,height", [(1280, 900), (768, 900), (360, 800)])
def test_live_treatment_workspace_renders_newest_first(width: int, height: int):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_treatment_page(
            playwright,
            width,
            height,
            _ordering_projection(),
        )
        try:
            # Today's compact list shows the newest entries.
            today = page.locator("#today-treatment-list .treatment-course-card")
            assert [item.locator("h3").inner_text() for item in today.all()] == [
                "Planned late",
                "Current mid",
                "Planned early",
            ]

            page.locator("#nav-patient").click()
            sections = page.locator("#patient-treatment-list .treatment-overview-section")
            assert sections.count() == 3
            current_and_planned = sections.nth(0).locator(".treatment-course-card")
            recorded = sections.nth(1).locator(".treatment-recorded-card")
            past = sections.nth(2).locator(".treatment-course-card")

            assert [item.locator("h3").inner_text() for item in current_and_planned.all()] == [
                "Planned late",
                "Current mid",
                "Planned early",
                "Current no date",
            ]
            assert [item.locator("h3").inner_text() for item in recorded.all()] == [
                "Recorded newest",
                "Recorded duplicate wording",
                "Recorded duplicate wording",
                "Recorded oldest",
            ]
            assert [item.locator("h3").inner_text() for item in past.all()] == [
                "Past fallback start",
                "Past stopped",
                "Past no date",
            ]

            # Every row still renders exactly once and the counts are unchanged.
            assert current_and_planned.count() + past.count() == 7
            assert recorded.count() == 4
            assert page.locator("#treatment-count-records").inner_text() == "11"
            assert page.locator("#treatment-count-differences").inner_text() == "0"

            # Reordering is presentation only: the accepted projection, the
            # recorded row identities, and the Record status action are intact.
            assert page.evaluate(
                "() => treatmentProjection.legacy_treatments.map(row => row.source_order)"
            ) == [0, 1, 2, 3]
            assert page.evaluate("() => treatmentProjection.courses.map(course => course.id)") == [
                course["id"] for course in _ordering_projection()["courses"]
            ]
            assert page.evaluate(
                "() => [...document.querySelectorAll("
                "'#patient-treatment-list [data-treatment-recorded-row]')]"
                ".map(node => node.dataset.treatmentRecordedRow)"
            ) == ["txlegacy-newest", "txlegacy-dup-b", "txlegacy-dup-a", "txlegacy-oldest"]
            assert (
                recorded.nth(0)
                .get_by_role("button", name="Record status for Recorded newest")
                .count()
                == 1
            )

            # No treatment timing is invented for rows that carry no date.
            recorded_text = sections.nth(1).inner_text()
            assert "2099" not in recorded_text
            assert "2000-01-01" not in recorded_text
            assert (
                page.evaluate(
                    "() => document.documentElement.scrollWidth"
                    " - document.documentElement.clientWidth"
                )
                == 0
            )
        finally:
            context.close()
            browser.close()
