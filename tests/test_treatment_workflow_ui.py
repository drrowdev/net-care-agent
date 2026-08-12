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
    return {
        "profile_revision": 5,
        "workflow_revision": 3,
        "projection_token": "treatment-projection-5-3",
        "source_fact_count": len(sources),
        "legacy_treatment_count": 1,
        "unlinked_generated_context_count": 10,
        "course_count": len(courses),
        "discrepancy_count": 0,
        "source_facts": sources,
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
            "legacy_treatments": recorded,
            "courses": [],
            "discrepancies": [],
            "eligible_actions": [],
        }
    )
    return projection


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
    return projection


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
    assert ".sort(" not in source
    assert ".dedupe" not in source
    assert "treatments_classified" not in source
    assert "treatments_fallback" not in source
    assert "body: intent.bodyText" in source
    assert "mutation_id: newMutationId()" in source
    assert "pendingTreatmentCompletion" in source
    assert "Retry submission" in INDEX_HTML
    assert "Retry refresh" in INDEX_HTML
    assert INDEX_HTML.count(GUIDANCE) == 3
    assert (
        "Machine-generated compatibility context · source linkage unavailable · "
        "not a treatment record"
    ) in source
    assert "Status not recorded" in source
    assert "Treatment timing/status not yet reviewed." in source


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
            assert "All 1 recorded treatment entry is linked" in totals
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
                "Automatic compatibility notes 11",
            ]
            page.locator("#treatment-tab-sources").click()
            assert page.locator("#treatment-source-table-body tr").count() == 2
            assert (
                page.locator("#treatment-panel-sources")
                .inner_text()
                .count("Duplicate source wording")
                == 2
            )
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
            page.locator("#treatment-tab-sources").focus()
            page.keyboard.press("End")
            assert page.evaluate("() => document.activeElement.id") == "treatment-tab-earlier"
            page.locator("#treatment-tab-earlier").click()
            earlier = page.locator("#treatment-panel-earlier").inner_text()
            assert "Mapped automatic compatibility notes (1)" in earlier
            assert "Other automatic compatibility notes (10)" in earlier
            page.locator(".treatment-generated-disclosure > summary").click()
            page.locator(".treatment-unlinked-generated-section > summary").click()
            earlier = page.locator("#treatment-panel-earlier").inner_text()
            assert "NET/Care-generated context - not a treatment fact" in earlier
            assert "All 10 notes are retained; none are omitted." in earlier
            assert "Earlier app component" not in earlier
            assert page.locator(".treatment-unlinked-generated-card").count() == 10
            assert (
                page.locator(".treatment-generated-section").inner_text().count("Not recorded") == 3
            )
            assert (
                page.locator(".treatment-unlinked-generated-card")
                .first.inner_text()
                .count("Not recorded")
                == 3
            )
            assert (
                page.locator(
                    ".treatment-unlinked-generated-section a, "
                    ".treatment-unlinked-generated-section button"
                ).count()
                == 0
            )
            assert GUIDANCE in page.locator("#treatment-workspace").inner_text()
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
            assert "31 treatment records need timing/status review" in today.inner_text()
            assert page.locator("#today-treatment-list .treatment-recorded-card").count() == 3

            page.locator("#nav-patient").click()
            overview = page.locator("#treatment-panel-records")
            assert page.locator("#patient-treatment-list .treatment-recorded-card").count() == 31
            assert "Recorded treatment information (31)" in overview.inner_text()
            assert "Recorded treatment information 00" in overview.inner_text()
            assert "Recorded treatment information 30" in overview.inner_text()
            normalized = overview.inner_text().lower()
            for forbidden in ("legacy", "earlier app", "archived", "historical", "unverified"):
                assert forbidden not in normalized

            page.locator("#treatment-tab-earlier").click()
            assert page.locator(".treatment-unlinked-generated-section").count() == 1
            assert not page.locator(".treatment-unlinked-generated-section").evaluate(
                "node => node.open"
            )
            assert page.locator(".treatment-unlinked-generated-card").count() == 10
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
            assert "2 recorded treatment entries need timing/status review" in totals

            page.locator("#nav-patient").click()
            cards = page.locator("#patient-treatment-list .treatment-recorded-card")
            assert cards.count() == 3
            assert "Status not recorded" in cards.nth(0).inner_text()
            assert "Treatment timing/status not yet reviewed" in cards.nth(0).inner_text()
            assert "Linked to reviewed status" in cards.nth(1).inner_text()
            assert "All recorded components are linked" in cards.nth(1).inner_text()
            assert "Partly linked to reviewed status" in cards.nth(2).inner_text()
            assert "1 of 2 recorded components are linked" in cards.nth(2).inner_text()
            assert cards.locator("h3").all_inner_texts() == [
                "None recorded treatment",
                "All recorded treatment",
                "Partial recorded treatment",
            ]
            for card in cards.all():
                assert "Current record" not in card.inner_text()
                assert "Planned record" not in card.inner_text()
                assert "Past record" not in card.inner_text()
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
            page.locator("#treatment-field-treatment-type-text").fill("")
            page.locator("#treatment-empty-treatment-type-text").check()
            page.locator("#treatment-field-start-date").fill("2027")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            page.locator("#nav-patient").click()
            assert "Exact new wording" in page.locator("#patient-treatment-list").inner_text()
            new_card = page.locator("#patient-treatment-list .treatment-course-card").filter(
                has_text="Exact new wording"
            )
            new_card.get_by_role("button", name="Record terminal outcome").click()
            options = page.locator("#treatment-field-terminal-qualifier option").all_inner_texts()
            assert options == [
                "Choose an outcome",
                "Did not start",
                "Plan cancelled before starting",
                "Other recorded outcome",
            ]
            page.locator("#treatment-field-terminal-qualifier").select_option("not_started")
            page.locator("#treatment-submit-button").click()
            page.wait_for_function("() => !treatmentMutationPending")
            new_card = page.locator("#patient-treatment-list .treatment-course-card").filter(
                has_text="Exact new wording"
            )
            assert "Did not start" in new_card.inner_text()
            mutations = [
                item
                for item in state.requests
                if item[1].startswith("/api/treatment-reconciliation/")
            ]
            assert [item[0] for item in mutations] == ["POST", "POST"]
            assert mutations[0][2]["treatment_text"] == "  Exact new wording  "
            assert mutations[0][2]["treatment_type_text"] == ""
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
            assert "Ending detail not recorded" in legacy.inner_text()
            assert legacy.get_by_role("button", name="Create linked new record").count() == 0
            no_transition = page.locator(".treatment-course-card").filter(has_text="Current three")
            assert no_transition.get_by_role("button", name="Record terminal outcome").count() == 0

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
            assert resolved.get_by_role("button", name="Record recurrence").count() == 1
            assert resolved.get_by_role("button", name="Record treating-team outcome").count() == 0

            incomplete = cards.nth(2)
            assert "Second citation unavailable" in incomplete.inner_text()
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

            resolved.get_by_role("button", name="Record recurrence").click()
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
            page.locator("#treatment-follow-up-due").fill("2027-04")
            inline_body = page.evaluate("() => treatmentBodyForDialog().body")
            assert inline_body["follow_up"] == {
                "text": "  Exact inline follow-up  ",
                "owner": None,
                "due_date": "2027-04",
            }
            assert "caregiver_action_id" not in inline_body
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
                "current treatment record remains authoritative"
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
            assert GUIDANCE in page.locator("#treatment-today-card").inner_text()
            assert GUIDANCE in page.locator("#treatment-workspace").inner_text()

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
            assert GUIDANCE in page.locator("#treatment-today-card").inner_text()
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
