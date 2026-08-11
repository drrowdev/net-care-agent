from __future__ import annotations

import copy
import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def _projection(client):
    response = client.get("/api/patient/treatment-reconciliation")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _meta(projection, mutation_id):
    return {
        "mutation_id": mutation_id,
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
    }


def _create_course(client, *, mutation_id="course-create-001", **overrides):
    projection = _projection(client)
    request = {
        **_meta(projection, mutation_id),
        "status": "planned",
        "treatment_text": "  Exact caregiver wording  ",
        "treatment_type_text": "Caregiver-entered type",
        "dose_text": "120 mg",
        "schedule_text": "Every four weeks",
        "planned_date": "2026-10",
        "legacy_component_ids": [],
        **overrides,
    }
    response = client.post("/api/treatment-reconciliation/courses", json=request)
    return response, request


def _ingest_treatment(
    agent,
    profile,
    *,
    job_id="treatment-feed-001",
    treatment_change="Start lanreotide 120mg q4w",
):
    text = f"Clinic note: {treatment_change}."
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-02",
        "summary": "Treatment discussion.",
        "treatment_changes": [treatment_change],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": treatment_change,
            }
        ],
    }
    before = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        updated, extracted = agent.run_intake(text, profile)
    agent.build_import_record(before, updated, extracted, job_id=job_id, text=text)
    return updated


def _ingest_two_treatments(agent, profile, *, job_id="treatment-feed-pair"):
    text = "Clinic note: Start lanreotide 120mg q4w. Continue lanreotide 90mg q4w."
    changes = ["Start lanreotide 120mg q4w", "Continue lanreotide 90mg q4w"]
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-02",
        "summary": "Treatment discussion.",
        "treatment_changes": changes,
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": index,
                "source_quote": value,
            }
            for index, value in enumerate(changes)
        ],
    }
    before = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        updated, extracted = agent.run_intake(text, profile)
    agent.build_import_record(before, updated, extracted, job_id=job_id, text=text)
    return updated


def _create_discrepancy(client, course, *, mutation_id="discrepancy-create-001"):
    projection = _projection(client)
    source = projection["source_facts"][0]
    request = {
        **_meta(projection, mutation_id),
        "category": "dose_or_schedule",
        "comparison_text": "Source and caregiver record use different exact schedules.",
        "source_fact_ref": source["ref"],
        "expected_source_fact_token": source["token"],
        "course_id": course["id"],
        "expected_course_token": next(
            item["token"] for item in projection["courses"] if item["id"] == course["id"]
        ),
    }
    return client.post("/api/treatment-reconciliation/discrepancies", json=request), request


def _create_source_discrepancy(
    client,
    *,
    mutation_id="source-discrepancy-create-001",
    source_indexes=(0, 1),
):
    projection = _projection(client)
    source_a = projection["source_facts"][source_indexes[0]]
    source_b = projection["source_facts"][source_indexes[1]]
    request = {
        **_meta(projection, mutation_id),
        "category": "source_wording",
        "comparison_text": "Two source occurrences contain different exact wording.",
        "source_fact_ref": source_a["ref"],
        "expected_source_fact_token": source_a["token"],
        "comparison_source_fact_ref": source_b["ref"],
        "expected_comparison_source_fact_token": source_b["token"],
    }
    return client.post("/api/treatment-reconciliation/discrepancies", json=request), request


def test_v13_migration_marks_only_missing_past_authority_losslessly_and_idempotently():
    from agent.migrations import apply_migrations

    legacy = {
        "schema_version": 12,
        "patient": {
            "current_treatments": ["same", "same"],
            "current_treatment_records": [{"id": "keep", "unknown": {"x": 1}}],
        },
        "treatments_classified": [{"id": "generated", "text": "same", "extra": True}],
        "document_imports": [{"id": "receipt", "changes": [], "unknown": ["keep"]}],
        "treatment_courses": [
            {
                "id": "past",
                "status": "past",
                "start_date": "2020",
                "stop_date": "2021-02",
                "history": [{"operation": "legacy", "unknown": [1, 2]}],
                "unknown_course": {"keep": True},
            },
            {
                "id": "current",
                "status": "current",
                "history": [],
                "unknown_course": ["keep"],
            },
            {
                "id": "planned",
                "status": "planned",
                "history": [],
                "unknown_course": None,
            },
        ],
        "treatment_discrepancies": [
            {"id": "discrepancy", "source_fact_snapshot": {"unknown": "keep"}}
        ],
        "unknown_top": {"keep": None},
    }
    preserved = copy.deepcopy(legacy)

    result = apply_migrations(legacy)
    first = copy.deepcopy(result)
    second = apply_migrations(result)

    assert result["schema_version"] == 15
    assert result["treatment_courses"][0]["terminal_qualifier"] == "legacy_unspecified"
    assert "terminal_detail" not in result["treatment_courses"][0]
    assert "terminal_qualifier" not in result["treatment_courses"][1]
    assert "terminal_qualifier" not in result["treatment_courses"][2]
    assert second == first
    for key, value in preserved.items():
        if key not in {"schema_version", "treatment_courses"}:
            assert result[key] == value
    migrated_courses = copy.deepcopy(result["treatment_courses"])
    migrated_courses[0].pop("terminal_qualifier")
    assert migrated_courses == preserved["treatment_courses"]


def test_projection_preserves_source_occurrence_and_hides_internal_coordinates(
    agent, empty_profile
):
    profile = _ingest_treatment(agent, empty_profile)

    projection = agent.project_treatment_reconciliation(profile)
    source = projection["source_facts"][0]
    serialized = json.dumps(projection)

    assert source["observed_text"] == "Start lanreotide 120mg q4w"
    assert source["provenance"]["status"] == "source_verified"
    assert source["ref"].startswith("txref_")
    assert projection["source_fact_count"] == 1
    assert "evidence_start" not in serialized
    assert "evidence_end" not in serialized
    assert profile["document_imports"][0]["id"] not in serialized
    assert profile["source_documents"][0]["id"] not in serialized
    assert (
        agent.treatment_source_fact_text(profile, source["ref"], evidence_only=True)
        == "Start lanreotide 120mg q4w"
    )


def test_treatment_safety_copy_is_exact_static_contract(agent, empty_profile):
    expected = (
        "NET/Care records what you enter but does not verify treatment details or advise "
        "starting, stopping, or changing treatment. Confirm treatment decisions with the "
        "treating team."
    )

    projection = agent.project_treatment_reconciliation(empty_profile)

    assert agent.TREATMENT_SAFETY_GUIDANCE == expected
    assert projection["safety_guidance"] == {
        "kind": "fixed_non_prescriptive",
        "text": expected,
    }


def test_legacy_projection_preserves_duplicate_order_and_stable_component_mapping(
    agent, empty_profile
):
    empty_profile["patient"]["current_treatments"] = [
        "lanreotide plus everolimus",
        "lanreotide plus everolimus",
    ]
    agent.sync_treatment_records(empty_profile)
    first_component = empty_profile["patient"]["current_treatment_records"][0]["id"]
    empty_profile["treatments_classified"] = [
        {
            "id": "txclass_lanreotide",
            "text": "lanreotide",
            "label": "Lanreotide",
            "category": "active",
            "date": None,
            "source_treatment_ids": [first_component],
            "unknown_private": {"preserve_in_token_only": True},
        }
    ]

    projection = agent.project_treatment_reconciliation(empty_profile)
    serialized = json.dumps(projection)

    assert [row["source_order"] for row in projection["legacy_treatments"]] == [0, 1]
    assert [row["raw_text"] for row in projection["legacy_treatments"]] == [
        "lanreotide plus everolimus",
        "lanreotide plus everolimus",
    ]
    assert projection["legacy_treatments"][0]["components"][0]["id"] == first_component
    assert projection["legacy_treatments"][0]["generated_classification"][0]["category"] == (
        "active"
    )
    assert "unknown_private" not in serialized


def test_pre_v6_generated_context_is_separate_complete_and_occurrence_stable(agent, empty_profile):
    empty_profile["patient"]["current_treatments"] = [
        f"Synthetic treatment row {index:02d}" for index in range(31)
    ]
    agent.sync_treatment_records(empty_profile)
    component_id = empty_profile["patient"]["current_treatment_records"][0]["id"]
    mapped = {
        "id": "txclass_mapped",
        "text": "Mapped synthetic context",
        "label": "Mapped synthetic label",
        "category": "active",
        "date": None,
        "source_treatment_ids": [component_id],
    }
    unlinked = [
        {
            "text": f"Synthetic unlinked context {index % 5}",
            "label": f"Synthetic unlinked label {index % 5}",
            "category": "active",
            "date": None if index == 0 else f"20{index:02d}",
        }
        for index in range(10)
    ]
    empty_profile["treatments_classified"] = [mapped, *unlinked]

    first = agent.project_treatment_reconciliation(empty_profile)
    second = agent.project_treatment_reconciliation(copy.deepcopy(empty_profile))
    rows = first["unlinked_generated_context"]

    assert first["legacy_treatment_count"] == 31
    assert len(empty_profile["patient"]["current_treatment_records"]) == 31
    assert first["unlinked_generated_context_count"] == 10
    assert rows == second["unlinked_generated_context"]
    assert [row["text"] for row in rows] == [row["text"] for row in unlinked]
    assert len({row["id"] for row in rows}) == 10
    assert len({row["token"] for row in rows}) == 10
    assert rows[0]["text"] == rows[5]["text"]
    assert rows[0]["id"] != rows[5]["id"]
    assert rows[0]["token"] != rows[5]["token"]
    assert first["legacy_treatments"][0]["generated_classification"] == [mapped]
    assert all(
        set(row) == {"id", "token", "text", "label", "category", "date", "authority_label"}
        for row in rows
    )
    assert all(
        row["authority_label"] == agent.TREATMENT_UNLINKED_GENERATED_AUTHORITY_LABEL for row in rows
    )
    collision = copy.deepcopy(empty_profile)
    collision["patient"]["current_treatment_records"][0]["id"] = rows[0]["id"]
    with pytest.raises(agent.TreatmentProjectionError, match="compatibility identity"):
        agent.project_treatment_reconciliation(collision)
    action_collision = copy.deepcopy(empty_profile)
    action_collision["caregiver_actions"] = [
        {
            "id": rows[0]["id"],
            "text": "Ask the treating team a synthetic question",
            "status": "open",
            "owner": None,
            "due_date": None,
            "origin_snapshot": {"kind": "manual"},
            "history": [],
        }
    ]
    with pytest.raises(agent.TreatmentProjectionError, match="public identity"):
        agent.project_treatment_reconciliation(action_collision)


@pytest.mark.parametrize(
    "row",
    [
        {
            "text": "Synthetic",
            "label": "Synthetic",
            "category": "active",
            "date": [],
        },
        {
            "text": "Synthetic",
            "label": "Synthetic",
            "category": "unsafe",
            "date": "2020",
        },
        {
            "text": "Synthetic",
            "label": "Synthetic",
            "category": "active",
            "date": "2020",
            "unknown": "not allowlisted",
        },
    ],
)
def test_malformed_pre_v6_generated_context_still_fails_closed(agent, empty_profile, row):
    empty_profile["treatments_classified"] = [row]

    with pytest.raises(agent.TreatmentProjectionError, match="compatibility authority"):
        agent.project_treatment_reconciliation(empty_profile)


def test_course_create_preserves_exact_text_dates_and_replays(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)

    first, request = _create_course(client)
    replay = client.post("/api/treatment-reconciliation/courses", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert replay.status_code == 200
    first_body = first.get_json()
    replay_body = replay.get_json()
    assert replay_body.pop("idempotent_replay") is True
    assert replay_body == first_body
    assert first_body["course"]["status"] == "planned"
    assert first_body["course"]["treatment_text"] == "  Exact caregiver wording  "
    assert first_body["course"]["planned_date"] == "2026-10"
    assert first_body["course"]["planned_date_precision"] == "month"
    assert first_body["profile_revision"] == 1
    assert first_body["workflow_revision"] == 1
    assert len(saved["treatment_courses"]) == 1
    assert len(saved["treatment_courses"][0]["history"]) == 1


def test_past_create_requires_exact_nonlegacy_terminal_authority_before_allocation(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)
    before = copy.deepcopy(agent.load_profile())
    allocations = 0

    def count_allocation():
        nonlocal allocations
        allocations += 1
        return "txc_" + ("0" * 32)

    monkeypatch.setattr(agent, "new_treatment_course_id", count_allocation)
    invalid = [
        {},
        {"terminal_qualifier": "legacy_unspecified"},
        {"terminal_qualifier": "completed"},
        {"terminal_qualifier": "other"},
        {"terminal_qualifier": "other", "terminal_detail": " "},
        {"terminal_qualifier": "other", "terminal_detail": "x" * 1001},
        {"terminal_qualifier": "ended", "terminal_detail": "contradiction"},
    ]
    for index, authority in enumerate(invalid):
        response = client.post(
            "/api/treatment-reconciliation/courses",
            json={
                **_meta(projection, f"invalid-past-create-{index}"),
                "status": "past",
                "treatment_text": "Exact caregiver wording",
                **authority,
            },
        )
        assert response.status_code == 400
    for status in ("current", "planned"):
        response = client.post(
            "/api/treatment-reconciliation/courses",
            json={
                **_meta(projection, f"invalid-{status}-terminal"),
                "status": status,
                "treatment_text": "Exact caregiver wording",
                "terminal_qualifier": "ended",
            },
        )
        assert response.status_code == 400

    assert allocations == 0
    assert agent.load_profile() == before

    valid = client.post(
        "/api/treatment-reconciliation/courses",
        json={
            **_meta(projection, "valid-other-past-create"),
            "status": "past",
            "treatment_text": "Exact caregiver wording",
            "terminal_qualifier": "other",
            "terminal_detail": "  Exact caregiver terminal detail  ",
        },
    )
    assert valid.status_code == 201
    assert allocations == 1
    assert valid.get_json()["course"]["terminal_detail"] == ("  Exact caregiver terminal detail  ")


@pytest.mark.parametrize(
    ("start_status", "qualifier", "detail", "expected_status"),
    [
        ("current", "ended", None, 200),
        ("current", "other", "  Exact current detail  ", 200),
        ("current", "not_started", None, 400),
        ("current", "cancelled", None, 400),
        ("planned", "not_started", None, 200),
        ("planned", "cancelled", None, 200),
        ("planned", "other", "  Exact planned detail  ", 200),
        ("planned", "ended", None, 400),
    ],
)
def test_transition_matrix_and_other_detail_are_server_authoritative(
    app_client,
    agent,
    empty_profile,
    start_status,
    qualifier,
    detail,
    expected_status,
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = _create_course(
        client,
        status=start_status,
        planned_date=None,
    )[0].get_json()["course"]
    projection = _projection(client)
    before = copy.deepcopy(agent.load_profile())
    response = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/transition",
        json={
            **_meta(projection, f"{start_status}-to-past-{qualifier}"),
            "expected_course_token": created["token"],
            "status": "past",
            "terminal_qualifier": qualifier,
            "terminal_detail": detail,
        },
    )

    assert response.status_code == expected_status
    if expected_status == 200:
        course = response.get_json()["course"]
        assert course["terminal_qualifier"] == qualifier
        assert course["terminal_detail"] == detail
        assert course["start_date"] is None
        assert course["stop_date"] is None
        assert course["planned_date"] is None
        assert response.get_json()["profile_revision"] == 2
        assert response.get_json()["workflow_revision"] == 2
        event = agent.load_profile()["treatment_courses"][0]["history"][-1]
        assert event["changes"]["terminal_qualifier"]["after"] == qualifier
        assert event["changes"]["terminal_detail"]["after"] == detail
    else:
        assert agent.load_profile() == before


def test_course_transition_is_explicit_and_restart_creates_new_episode(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = _create_course(client, status="current", planned_date=None)[0].get_json()["course"]
    projection = _projection(client)
    transition = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/transition",
        json={
            **_meta(projection, "course-to-past-001"),
            "expected_course_token": created["token"],
            "status": "past",
            "terminal_qualifier": "ended",
        },
    )
    assert transition.status_code == 200
    past = transition.get_json()["course"]
    before_restart = copy.deepcopy(agent.load_profile()["treatment_courses"][0])
    projection = _projection(client)
    restart = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/restart",
        json={
            **_meta(projection, "course-restart-001"),
            "expected_course_token": past["token"],
            "status": "current",
            "treatment_text": "Restarted wording",
            "start_date": "2027",
        },
    )
    saved = agent.load_profile()

    assert restart.status_code == 201
    restarted = restart.get_json()["course"]
    assert restarted["id"] != created["id"]
    assert restarted["previous_course_id"] == created["id"]
    assert restarted["start_date_precision"] == "year"
    assert saved["treatment_courses"][0] == before_restart
    assert saved["treatment_courses"][1]["status"] == "current"


def test_projection_publishes_exact_lifecycle_and_restart_authority(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    planned = _create_course(client, mutation_id="planned-lifecycle")[0].get_json()["course"]
    assert planned["terminal_qualifier"] is None
    assert planned["terminal_detail"] is None
    assert planned["lifecycle"] == {
        "allowed_transitions": [
            {"status": "current", "terminal_qualifiers": []},
            {
                "status": "past",
                "terminal_qualifiers": ["not_started", "cancelled", "other"],
            },
        ],
        "restart": {"eligible": False, "reason": "course_not_terminal"},
    }
    projection = _projection(client)
    cancelled_response = client.post(
        f"/api/treatment-reconciliation/courses/{planned['id']}/transition",
        json={
            **_meta(projection, "planned-cancelled"),
            "expected_course_token": next(
                item["token"] for item in projection["courses"] if item["id"] == planned["id"]
            ),
            "status": "past",
            "terminal_qualifier": "cancelled",
        },
    )
    cancelled = cancelled_response.get_json()["course"]
    assert cancelled["lifecycle"] == {
        "allowed_transitions": [],
        "restart": {
            "eligible": False,
            "reason": "terminal_qualifier_not_restartable",
        },
    }
    projection = _projection(client)
    rejected_restart = client.post(
        f"/api/treatment-reconciliation/courses/{planned['id']}/restart",
        json={
            **_meta(projection, "cancelled-restart-rejected"),
            "expected_course_token": cancelled["token"],
            "status": "current",
            "treatment_text": "Must not be created",
        },
    )
    assert rejected_restart.status_code == 409

    current = _create_course(
        client,
        mutation_id="current-lifecycle",
        status="current",
        planned_date=None,
    )[0].get_json()["course"]
    assert current["lifecycle"]["allowed_transitions"] == [
        {"status": "past", "terminal_qualifiers": ["ended", "other"]}
    ]
    projection = _projection(client)
    ended = client.post(
        f"/api/treatment-reconciliation/courses/{current['id']}/transition",
        json={
            **_meta(projection, "current-ended"),
            "expected_course_token": current["token"],
            "status": "past",
            "terminal_qualifier": "ended",
        },
    ).get_json()["course"]
    assert ended["lifecycle"] == {
        "allowed_transitions": [],
        "restart": {"eligible": True, "reason": "eligible_prior_current"},
    }

    direct = _create_course(
        client,
        mutation_id="direct-ended",
        status="past",
        terminal_qualifier="ended",
        planned_date=None,
    )[0].get_json()["course"]
    assert direct["lifecycle"]["restart"] == {
        "eligible": False,
        "reason": "no_prior_current_authority",
    }


def test_legacy_unspecified_restart_eligibility_uses_private_prior_current_history(
    agent, empty_profile
):
    from agent.migrations import apply_migrations

    timestamp = "2026-08-10T10:00:00"

    def legacy_course(*, course_id, history):
        return {
            "id": course_id,
            "status": "past",
            "treatment_text": "Exact legacy wording",
            "legacy_component_ids": [],
            "start_date": None,
            "start_date_precision": "unknown",
            "start_date_kind": "unknown",
            "stop_date": None,
            "stop_date_precision": "unknown",
            "stop_date_kind": "unknown",
            "planned_date": None,
            "planned_date_precision": "unknown",
            "planned_date_kind": "unknown",
            "previous_course_id": None,
            "provenance": agent.treatment_course_provenance(),
            "created_at": timestamp,
            "updated_at": timestamp,
            "history": history,
        }

    prior_current = legacy_course(
        course_id=agent.new_treatment_course_id(),
        history=[
            {"changes": {"status": {"before": None, "after": "current"}}},
            {"changes": {"status": {"before": "current", "after": "past"}}},
        ],
    )
    direct_past = legacy_course(
        course_id=agent.new_treatment_course_id(),
        history=[{"changes": {"status": {"before": None, "after": "past"}}}],
    )
    profile = copy.deepcopy(empty_profile)
    profile["schema_version"] = 12
    profile["treatment_courses"] = [prior_current, direct_past]
    migrated = apply_migrations(profile)
    projection = agent.project_treatment_reconciliation(migrated)

    assert [item["terminal_qualifier"] for item in projection["courses"]] == [
        "legacy_unspecified",
        "legacy_unspecified",
    ]
    assert projection["courses"][0]["lifecycle"]["restart"] == {
        "eligible": True,
        "reason": "eligible_prior_current",
    }
    assert projection["courses"][1]["lifecycle"]["restart"] == {
        "eligible": False,
        "reason": "no_prior_current_authority",
    }

    cyclic = copy.deepcopy(migrated)
    cyclic["treatment_courses"][0]["previous_course_id"] = direct_past["id"]
    cyclic["treatment_courses"][1]["previous_course_id"] = prior_current["id"]
    with pytest.raises(agent.TreatmentProjectionError, match="lifecycle"):
        agent.project_treatment_reconciliation(cyclic)


def test_edit_cannot_change_status_or_terminal_authority(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    course = _create_course(client)[0].get_json()["course"]
    projection = _projection(client)
    before = copy.deepcopy(agent.load_profile())

    for index, patch in enumerate(
        (
            {"status": "past"},
            {"terminal_qualifier": "cancelled"},
            {"terminal_detail": "Not editable"},
        )
    ):
        response = client.patch(
            f"/api/treatment-reconciliation/courses/{course['id']}",
            json={
                **_meta(projection, f"immutable-terminal-edit-{index}"),
                "expected_course_token": course["token"],
                **patch,
            },
        )
        assert response.status_code == 400
    assert agent.load_profile() == before


def test_past_course_is_terminal_and_dates_are_never_inferred(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = _create_course(
        client,
        status="past",
        terminal_qualifier="ended",
        planned_date=None,
    )[0].get_json()["course"]
    projection = _projection(client)
    response = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/transition",
        json={
            **_meta(projection, "past-course-transition"),
            "expected_course_token": created["token"],
            "status": "current",
        },
    )

    assert response.status_code == 409
    saved = agent.load_profile()["treatment_courses"][0]
    assert saved["status"] == "past"
    assert saved["start_date"] is None
    assert saved["stop_date"] is None
    assert saved["planned_date"] is None


def test_discrepancy_confirmation_is_neutral_attributed_and_preserved_on_reopen(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client, status="current", planned_date=None)[0].get_json()["course"]
    created_response, _ = _create_discrepancy(client, course)
    assert created_response.status_code == 201
    discrepancy = created_response.get_json()["discrepancy"]
    assert discrepancy["citation_kind"] == "source_vs_course"
    assert discrepancy["citation_authority"] == {"state": "complete", "reason": None}
    assert discrepancy["citations"]["source_a"]["snapshot"] == discrepancy["source_fact"]
    assert discrepancy["citations"]["course_b"]["snapshot"] == discrepancy["course_snapshot"]
    assert discrepancy["citations"]["source_b"] is None
    projection = _projection(client)
    resolved = client.post(
        f"/api/treatment-reconciliation/discrepancies/{discrepancy['id']}/resolve",
        json={
            **_meta(projection, "discrepancy-resolve-001"),
            "expected_discrepancy_token": discrepancy["token"],
            "outcome": "no_change_documented",
            "note": "  Clinician-attributed exact caregiver wording.  ",
            "clinician_text": "Dr Example",
            "context_text": "Visit conversation",
            "date": "2026-09",
        },
    )
    assert resolved.status_code == 200
    resolved_row = resolved.get_json()["discrepancy"]
    confirmation = resolved_row["confirmations"][0]
    assert confirmation["note"] == "  Clinician-attributed exact caregiver wording.  "
    assert confirmation["provenance_label"] == (
        "Caregiver-entered · attributed to clinician · unverified"
    )
    projection = _projection(client)
    reopened = client.post(
        f"/api/treatment-reconciliation/discrepancies/{discrepancy['id']}/reopen",
        json={
            **_meta(projection, "discrepancy-reopen-001"),
            "expected_discrepancy_token": resolved_row["token"],
        },
    )

    assert reopened.status_code == 200
    reopened_row = reopened.get_json()["discrepancy"]
    assert reopened_row["status"] == "open"
    assert reopened_row["confirmations"] == resolved_row["confirmations"]
    assert reopened.get_json()["profile_revision"] == resolved.get_json()["profile_revision"]


def test_source_vs_source_creation_preserves_identical_distinct_occurrences(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile, job_id="duplicate-source-a")
    profile = _ingest_treatment(agent, profile, job_id="duplicate-source-b")
    agent.save_profile(profile, clinical_change=False)

    projection = _projection(client)
    assert len(projection["source_facts"]) == 2
    assert (
        projection["source_facts"][0]["observed_text"]
        == (projection["source_facts"][1]["observed_text"])
    )
    assert projection["source_facts"][0]["ref"] != projection["source_facts"][1]["ref"]

    response, _ = _create_source_discrepancy(client)
    row = response.get_json()["discrepancy"]

    assert response.status_code == 201
    assert row["citation_kind"] == "source_vs_source"
    assert row["course_id"] is None
    assert row["course_snapshot"] is None
    assert row["citations"]["course_b"] is None
    assert (
        row["citations"]["source_a"]["snapshot"]["ref"]
        != (row["citations"]["source_b"]["snapshot"]["ref"])
    )
    assert (
        row["citations"]["source_a"]["current"]["observed_text"]
        == (row["citations"]["source_b"]["current"]["observed_text"])
    )


def test_existing_source_vs_course_record_remains_lossless_without_new_fields(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client)[0].get_json()["course"]
    created = _create_discrepancy(client, course)[0].get_json()["discrepancy"]
    persisted = agent.load_profile()
    record = persisted["treatment_discrepancies"][0]
    record.pop("citation_kind")
    record.pop("comparison_source_fact_ref")
    record.pop("comparison_source_fact_snapshot")
    preserved = copy.deepcopy(record)

    projected = agent.project_treatment_reconciliation(persisted)["discrepancies"][0]

    assert record == preserved
    assert projected["citation_kind"] == "source_vs_course"
    assert projected["citation_authority"] == {"state": "complete", "reason": None}
    assert projected["source_fact"] == created["source_fact"]
    assert projected["course_snapshot"] == created["course_snapshot"]


def test_discrepancy_create_rejects_incomplete_mixed_stale_and_noncitable_authority(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    profile = _ingest_two_treatments(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client)[0].get_json()["course"]
    projection = _projection(client)
    source_a, source_b = projection["source_facts"]
    base = {
        **_meta(projection, "placeholder-mutation"),
        "category": "other",
        "comparison_text": "Neutral exact comparison.",
    }
    source_a_pair = {
        "source_fact_ref": source_a["ref"],
        "expected_source_fact_token": source_a["token"],
    }
    source_b_pair = {
        "comparison_source_fact_ref": source_b["ref"],
        "expected_comparison_source_fact_token": source_b["token"],
    }
    course_pair = {
        "course_id": course["id"],
        "expected_course_token": course["token"],
    }
    legacy = projection["legacy_treatments"][0]
    invalid_requests = [
        {},
        source_a_pair,
        {**source_a_pair, **source_b_pair, **course_pair},
        {
            **source_a_pair,
            "comparison_source_fact_ref": source_a["ref"],
            "expected_comparison_source_fact_token": source_a["token"],
        },
        {
            **source_a_pair,
            "comparison_source_fact_ref": source_b["ref"],
            "expected_comparison_source_fact_token": "stale",
        },
        {
            **source_a_pair,
            "comparison_source_fact_ref": "txref_dangling",
            "expected_comparison_source_fact_token": source_b["token"],
        },
        {
            "source_fact_ref": legacy["id"],
            "expected_source_fact_token": legacy["token"],
            **course_pair,
        },
        {
            "source_fact_ref": "txclass_generated_compatibility_only",
            "expected_source_fact_token": legacy["token"],
            **course_pair,
        },
        {**source_a_pair, **source_b_pair, "source_fact_snapshot": source_a},
    ]
    allocations = 0

    def count_allocation():
        nonlocal allocations
        allocations += 1
        return "txd_" + ("0" * 32)

    monkeypatch.setattr(agent, "new_treatment_discrepancy_id", count_allocation)
    before = copy.deepcopy(agent.load_profile())
    for index, invalid in enumerate(invalid_requests):
        response = client.post(
            "/api/treatment-reconciliation/discrepancies",
            json={
                **base,
                "mutation_id": f"invalid-discrepancy-{index:02d}",
                **invalid,
            },
        )
        assert response.status_code in {400, 404, 409}

    after = agent.load_profile()
    assert allocations == 0
    assert after["treatment_discrepancies"] == before["treatment_discrepancies"]
    assert after["profile_revision"] == before["profile_revision"]
    assert after["workflow_revision"] == before["workflow_revision"]


def test_source_vs_source_tokens_bind_each_current_authority_without_snapshot_rewrite(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile, job_id="source-token-a")
    profile = _ingest_treatment(
        agent,
        profile,
        job_id="source-token-b",
        treatment_change="Start everolimus 10mg daily",
    )
    agent.save_profile(profile, clinical_change=False)
    created, request = _create_source_discrepancy(client)
    created_row = created.get_json()["discrepancy"]
    original_snapshots = copy.deepcopy(created_row["citations"])
    original_token = created_row["token"]

    corrected = agent.load_profile()
    receipt_a = agent.public_receipt(corrected, "source-token-a")
    change_a = next(item for item in receipt_a["changes"] if item["category"] == "treatments")
    agent.correct_change(
        corrected,
        "source-token-a",
        change_a["id"],
        receipt_revision=receipt_a["receipt_revision"],
        target_token=change_a["target_token"],
        replacement="Corrected source A current wording",
    )
    after_a = agent.project_treatment_reconciliation(corrected)["discrepancies"][0]
    assert after_a["token"] != original_token
    assert (
        after_a["citations"]["source_a"]["snapshot"] == original_snapshots["source_a"]["snapshot"]
    )
    assert (
        after_a["citations"]["source_b"]["snapshot"] == original_snapshots["source_b"]["snapshot"]
    )

    receipt_b = agent.public_receipt(corrected, "source-token-b")
    change_b = next(item for item in receipt_b["changes"] if item["category"] == "treatments")
    agent.correct_change(
        corrected,
        "source-token-b",
        change_b["id"],
        receipt_revision=receipt_b["receipt_revision"],
        target_token=change_b["target_token"],
        replacement="Corrected source B current wording",
    )
    after_b = agent.project_treatment_reconciliation(corrected)["discrepancies"][0]
    assert after_b["token"] != after_a["token"]
    assert (
        after_b["citations"]["source_a"]["snapshot"] == original_snapshots["source_a"]["snapshot"]
    )
    assert (
        after_b["citations"]["source_b"]["snapshot"] == original_snapshots["source_b"]["snapshot"]
    )

    agent.save_profile(corrected, clinical_change=True)
    replay = client.post("/api/treatment-reconciliation/discrepancies", json=request)
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert replay.get_json()["discrepancy"] == created_row


def test_terminal_transition_rotates_course_discrepancy_and_projection_tokens_without_snapshot_rewrite(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(
        client,
        status="current",
        planned_date=None,
    )[0].get_json()["course"]
    discrepancy = _create_discrepancy(client, course)[0].get_json()["discrepancy"]
    original_snapshot = copy.deepcopy(discrepancy["course_snapshot"])
    original_course_token = course["token"]
    original_discrepancy_token = discrepancy["token"]
    projection = _projection(client)
    original_projection_token = projection["projection_token"]
    request = {
        **_meta(projection, "terminal-token-rotation"),
        "expected_course_token": next(
            item["token"] for item in projection["courses"] if item["id"] == course["id"]
        ),
        "status": "past",
        "terminal_qualifier": "other",
        "terminal_detail": "  Exact terminal authority  ",
    }

    transitioned_response = client.post(
        f"/api/treatment-reconciliation/courses/{course['id']}/transition",
        json=request,
    )
    transitioned_body = transitioned_response.get_json()
    projected = _projection(client)
    current_discrepancy = projected["discrepancies"][0]

    assert transitioned_response.status_code == 200
    assert transitioned_body["course"]["token"] != original_course_token
    assert projected["projection_token"] != original_projection_token
    assert current_discrepancy["token"] != original_discrepancy_token
    assert current_discrepancy["course_snapshot"] == original_snapshot
    assert current_discrepancy["citations"]["course_b"]["snapshot"] == original_snapshot
    assert current_discrepancy["citations"]["course_b"]["current"]["terminal_qualifier"] == (
        "other"
    )
    assert current_discrepancy["citations"]["course_b"]["current"]["terminal_detail"] == (
        "  Exact terminal authority  "
    )

    _create_course(client, mutation_id="unrelated-after-terminal")
    replay = client.post(
        f"/api/treatment-reconciliation/courses/{course['id']}/transition",
        json=request,
    )
    replay_body = replay.get_json()
    assert replay.status_code == 200
    assert replay_body.pop("idempotent_replay") is True
    assert replay_body == transitioned_body


def test_source_removal_and_undo_rotate_current_state_without_snapshot_rewrite(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile, job_id="source-lifecycle-a")
    profile = _ingest_treatment(
        agent,
        profile,
        job_id="source-lifecycle-b",
        treatment_change="Start everolimus 10mg daily",
    )
    agent.save_profile(profile, clinical_change=False)
    created = _create_source_discrepancy(client)[0].get_json()["discrepancy"]
    snapshots = copy.deepcopy(created["citations"])
    persisted = agent.load_profile()

    removed = copy.deepcopy(persisted)
    receipt = agent.public_receipt(removed, "source-lifecycle-b")
    change = next(item for item in receipt["changes"] if item["category"] == "treatments")
    agent.remove_change(
        removed,
        "source-lifecycle-b",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
    )
    removed_row = agent.project_treatment_reconciliation(removed)["discrepancies"][0]
    removed_side = next(
        removed_row["citations"][key]
        for key in ("source_a", "source_b")
        if "everolimus" in removed_row["citations"][key]["current"]["observed_text"]
    )
    assert removed_side["current"]["review_state"] == "removed"
    assert removed_row["citations"]["source_a"]["snapshot"] == snapshots["source_a"]["snapshot"]
    assert removed_row["citations"]["source_b"]["snapshot"] == snapshots["source_b"]["snapshot"]

    undone = copy.deepcopy(persisted)
    receipt = agent.public_receipt(undone, "source-lifecycle-a")
    agent.undo_import(
        undone,
        "source-lifecycle-a",
        receipt_revision=receipt["receipt_revision"],
        undo_token=receipt["undo_token"],
    )
    undone_row = agent.project_treatment_reconciliation(undone)["discrepancies"][0]
    undone_side = next(
        undone_row["citations"][key]
        for key in ("source_a", "source_b")
        if "lanreotide" in undone_row["citations"][key]["current"]["observed_text"]
    )
    assert undone_side["current"]["receipt_state"] == "undone"
    assert undone_row["citations"]["source_a"]["snapshot"] == snapshots["source_a"]["snapshot"]
    assert undone_row["citations"]["source_b"]["snapshot"] == snapshots["source_b"]["snapshot"]


def test_shared_source_artifact_is_validated_once_for_two_citations(
    agent, empty_profile, monkeypatch
):
    import agent.treatment_reconciliation as reconciliation

    profile = _ingest_two_treatments(agent, empty_profile)
    calls = 0
    original = reconciliation.validate_source_artifact

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(reconciliation, "validate_source_artifact", counted)
    projection = reconciliation.project_treatment_reconciliation(profile)

    assert len(projection["source_facts"]) == 2
    assert calls == 1


def test_source_vs_source_recurrence_reopen_and_replay_preserve_server_owned_citations(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_two_treatments(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    created = _create_source_discrepancy(client)[0].get_json()["discrepancy"]
    projection = _projection(client)
    resolve_request = {
        **_meta(projection, "source-source-resolve"),
        "expected_discrepancy_token": created["token"],
        "outcome": "source_clarification_needed",
        "note": "Treating-team clarification was recorded without changing either citation.",
    }
    resolved_response = client.post(
        f"/api/treatment-reconciliation/discrepancies/{created['id']}/resolve",
        json=resolve_request,
    )
    resolved = resolved_response.get_json()["discrepancy"]
    assert resolved_response.status_code == 200
    assert resolved["confirmations"][0]["outcome"] == "source_clarification_needed"

    projection = _projection(client)
    recurrence_request = {
        **_meta(projection, "source-source-recurrence"),
        "category": "source_wording",
        "comparison_text": "The same two source authorities require another neutral review.",
        "recurs_from_id": resolved["id"],
        "expected_recurs_from_token": resolved["token"],
    }
    recurrence_response = client.post(
        "/api/treatment-reconciliation/discrepancies",
        json=recurrence_request,
    )
    replay = client.post(
        "/api/treatment-reconciliation/discrepancies",
        json=recurrence_request,
    )
    recurrence = recurrence_response.get_json()["discrepancy"]

    assert recurrence_response.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert recurrence["citation_kind"] == "source_vs_source"
    assert recurrence["recurs_from_id"] == created["id"]
    assert (
        recurrence["citations"]["source_a"]["snapshot"]
        == (created["citations"]["source_a"]["snapshot"])
    )
    assert (
        recurrence["citations"]["source_b"]["snapshot"]
        == (created["citations"]["source_b"]["snapshot"])
    )

    projection = _projection(client)
    substituted = client.post(
        "/api/treatment-reconciliation/discrepancies",
        json={
            **_meta(projection, "source-source-recurrence-substitute"),
            "category": "source_wording",
            "comparison_text": "Attempted client substitution.",
            "recurs_from_id": resolved["id"],
            "expected_recurs_from_token": next(
                item["token"]
                for item in projection["discrepancies"]
                if item["id"] == resolved["id"]
            ),
            "source_fact_ref": projection["source_facts"][1]["ref"],
            "expected_source_fact_token": projection["source_facts"][1]["token"],
            "comparison_source_fact_ref": projection["source_facts"][0]["ref"],
            "expected_comparison_source_fact_token": projection["source_facts"][0]["token"],
        },
    )
    assert substituted.status_code == 400

    projection = _projection(client)
    current_resolved = next(
        item for item in projection["discrepancies"] if item["id"] == resolved["id"]
    )
    reopened_response = client.post(
        f"/api/treatment-reconciliation/discrepancies/{resolved['id']}/reopen",
        json={
            **_meta(projection, "source-source-reopen"),
            "expected_discrepancy_token": current_resolved["token"],
        },
    )
    reopened = reopened_response.get_json()["discrepancy"]
    assert reopened_response.status_code == 200
    assert reopened["confirmations"] == resolved["confirmations"]
    assert (
        reopened["citations"]["source_a"]["snapshot"]
        == (current_resolved["citations"]["source_a"]["snapshot"])
    )
    assert (
        reopened["citations"]["source_b"]["snapshot"]
        == (current_resolved["citations"]["source_b"]["snapshot"])
    )


def test_legacy_one_sided_discrepancy_is_visible_incomplete_and_lifecycle_read_only(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client)[0].get_json()["course"]
    created = _create_discrepancy(client, course)[0].get_json()["discrepancy"]

    legacy = agent.load_profile()
    record = legacy["treatment_discrepancies"][0]
    record.pop("citation_kind", None)
    record["course_id"] = None
    record["course_snapshot"] = None
    record.pop("comparison_source_fact_ref", None)
    record.pop("comparison_source_fact_snapshot", None)
    agent.save_profile(legacy, clinical_change=False)
    projection = _projection(client)
    row = projection["discrepancies"][0]

    assert row["citation_kind"] == "legacy_incomplete"
    assert row["citation_authority"] == {
        "state": "legacy_incomplete",
        "reason": "missing_second_citation",
    }
    assert row["eligibility"] == {"resolve": False, "reopen": False, "recur": False}
    assert row["citations"]["source_a"]["snapshot"] == created["source_fact"]
    assert row["citations"]["source_b"] is None
    assert row["citations"]["course_b"] is None

    before = copy.deepcopy(agent.load_profile())
    resolve = client.post(
        f"/api/treatment-reconciliation/discrepancies/{row['id']}/resolve",
        json={
            **_meta(projection, "legacy-incomplete-resolve"),
            "expected_discrepancy_token": row["token"],
            "outcome": "no_change_documented",
            "note": "Must remain read-only.",
        },
    )
    assert resolve.status_code == 409
    assert agent.load_profile() == before

    resolved_legacy = agent.load_profile()
    resolved_record = resolved_legacy["treatment_discrepancies"][0]
    resolved_record["status"] = "resolved"
    resolved_record["resolved_at"] = "2026-08-10T10:00:00"
    resolved_record["updated_at"] = "2026-08-10T10:00:00"
    agent.save_profile(resolved_legacy, clinical_change=False)
    projection = _projection(client)
    row = projection["discrepancies"][0]
    before = copy.deepcopy(agent.load_profile())

    reopen = client.post(
        f"/api/treatment-reconciliation/discrepancies/{row['id']}/reopen",
        json={
            **_meta(projection, "legacy-incomplete-reopen"),
            "expected_discrepancy_token": row["token"],
        },
    )
    recur = client.post(
        "/api/treatment-reconciliation/discrepancies",
        json={
            **_meta(projection, "legacy-incomplete-recur"),
            "category": "other",
            "comparison_text": "Must not invent a citation.",
            "recurs_from_id": row["id"],
            "expected_recurs_from_token": row["token"],
        },
    )

    assert reopen.status_code == 409
    assert recur.status_code == 409
    assert agent.load_profile() == before


def test_discrepancy_projection_fails_whole_response_for_cycles_and_oversized_private_snapshot(
    agent, empty_profile
):
    profile = _ingest_two_treatments(agent, empty_profile)
    projection = agent.project_treatment_reconciliation(profile)
    timestamp = "2026-08-10T10:00:00"

    def record(record_id, source_a, source_b, *, recurs_from_id=None):
        return {
            "id": record_id,
            "status": "open",
            "category": "other",
            "comparison_text": "Neutral comparison.",
            "citation_kind": "source_vs_source",
            "course_id": None,
            "source_fact_ref": source_a["ref"],
            "source_fact_snapshot": copy.deepcopy(source_a),
            "comparison_source_fact_ref": source_b["ref"],
            "comparison_source_fact_snapshot": copy.deepcopy(source_b),
            "course_snapshot": None,
            "recurs_from_id": recurs_from_id,
            "confirmations": [],
            "caregiver_action_id": None,
            "provenance": agent.treatment_course_provenance(),
            "created_at": timestamp,
            "updated_at": timestamp,
            "resolved_at": None,
            "history": [],
        }

    first_id = agent.new_treatment_discrepancy_id()
    second_id = agent.new_treatment_discrepancy_id()
    first = record(
        first_id,
        projection["source_facts"][0],
        projection["source_facts"][1],
        recurs_from_id=second_id,
    )
    second = record(
        second_id,
        projection["source_facts"][1],
        projection["source_facts"][0],
        recurs_from_id=first_id,
    )
    profile["treatment_discrepancies"] = [first, second]
    with pytest.raises(agent.TreatmentProjectionError, match="recurrence"):
        agent.project_treatment_reconciliation(profile)

    first["recurs_from_id"] = None
    second["recurs_from_id"] = first_id
    with pytest.raises(agent.TreatmentProjectionError, match="recurrence"):
        agent.project_treatment_reconciliation(profile)

    for field in (
        "source_fact_ref",
        "source_fact_snapshot",
        "comparison_source_fact_ref",
        "comparison_source_fact_snapshot",
        "course_id",
        "course_snapshot",
    ):
        second[field] = copy.deepcopy(first.get(field))
    first["source_fact_snapshot"]["unknown_private"] = "x" * 100_001
    with pytest.raises(agent.TreatmentProjectionError, match="limits"):
        agent.project_treatment_reconciliation(profile)

    first["source_fact_snapshot"].pop("unknown_private")
    first["source_fact_snapshot"]["path"] = "private/source/path"
    second["source_fact_snapshot"] = copy.deepcopy(first["source_fact_snapshot"])
    with pytest.raises(agent.TreatmentProjectionError, match="snapshot"):
        agent.project_treatment_reconciliation(profile)


def test_treatment_replay_rejects_tampered_private_result_snapshot(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_two_treatments(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    response, request = _create_source_discrepancy(client)
    assert response.status_code == 201

    tampered = agent.load_profile()
    event = tampered["treatment_discrepancies"][0]["history"][0]
    event["result_snapshot"]["discrepancy"]["source_fact"]["path"] = "private/source/path"
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(tampered, clinical_change=False)

    replay = client.post("/api/treatment-reconciliation/discrepancies", json=request)

    assert replay.status_code == 409
    assert replay.get_json()["code"] == "treatment_conflict"
    assert "private/source/path" not in json.dumps(replay.get_json())


@pytest.mark.parametrize(
    "tamper",
    [
        "mismatched_current_ref",
        "contradictory_authority",
        "contradictory_eligibility",
    ],
)
def test_treatment_replay_rejects_contradictory_citation_authority(
    app_client, agent, empty_profile, tamper
):
    _, client = app_client
    profile = _ingest_two_treatments(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    response, request = _create_source_discrepancy(client)
    assert response.status_code == 201

    tampered = agent.load_profile()
    event = tampered["treatment_discrepancies"][0]["history"][0]
    public = event["result_snapshot"]["discrepancy"]
    if tamper == "mismatched_current_ref":
        public["citations"]["source_a"]["current"] = copy.deepcopy(
            public["citations"]["source_b"]["current"]
        )
    elif tamper == "contradictory_authority":
        public["citation_authority"] = {
            "state": "legacy_incomplete",
            "reason": "missing_second_citation",
        }
    else:
        public["eligibility"] = {"resolve": False, "reopen": True, "recur": True}
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(tampered, clinical_change=False)

    replay = client.post("/api/treatment-reconciliation/discrepancies", json=request)

    assert replay.status_code == 409
    assert replay.get_json()["code"] == "treatment_conflict"


def test_record_correction_requires_explicit_atomic_course_patch(app_client, agent, empty_profile):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client, status="current", planned_date=None)[0].get_json()["course"]
    discrepancy = _create_discrepancy(client, course)[0].get_json()["discrepancy"]
    projection = _projection(client)
    response = client.post(
        f"/api/treatment-reconciliation/discrepancies/{discrepancy['id']}/resolve",
        json={
            **_meta(projection, "discrepancy-correct-001"),
            "expected_discrepancy_token": discrepancy["token"],
            "expected_course_token": next(
                item["token"] for item in projection["courses"] if item["id"] == course["id"]
            ),
            "outcome": "caregiver_record_corrected",
            "note": "Caregiver recorded the attributed clarification.",
            "course_patch": {"schedule_text": "Every 28 days exactly as entered"},
        },
    )
    saved = agent.load_profile()

    assert response.status_code == 200
    assert response.get_json()["course"]["schedule_text"] == "Every 28 days exactly as entered"
    assert saved["treatment_discrepancies"][0]["status"] == "resolved"
    assert len(saved["treatment_courses"][0]["history"]) == 2
    assert len(saved["treatment_discrepancies"][0]["history"]) == 2


def test_inline_follow_up_is_atomic_replay_safe_and_has_no_lifecycle_cascade(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client, status="current", planned_date=None)[0].get_json()["course"]
    discrepancy = _create_discrepancy(client, course)[0].get_json()["discrepancy"]
    projection = _projection(client)
    request = {
        **_meta(projection, "discrepancy-follow-up-001"),
        "expected_discrepancy_token": discrepancy["token"],
        "follow_up": {
            "text": "Ask the treating team to confirm the recorded schedule",
            "owner": "Caregiver",
            "due_date": "2026-10-01",
        },
    }
    first = client.patch(
        f"/api/treatment-reconciliation/discrepancies/{discrepancy['id']}/follow-up",
        json=request,
    )
    replay = client.patch(
        f"/api/treatment-reconciliation/discrepancies/{discrepancy['id']}/follow-up",
        json=request,
    )
    saved = agent.load_profile()

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert len(saved["caregiver_actions"]) == 1
    assert saved["treatment_discrepancies"][0]["status"] == "open"
    assert saved["treatment_courses"][0]["status"] == "current"
    symptom_projection = client.get("/api/patient/symptom-episodes").get_json()
    assert symptom_projection["eligible_actions"] == []
    cross_link = client.post(
        "/api/symptom-episodes",
        json={
            "mutation_id": "reject-cross-authority-link",
            "expected_profile_revision": symptom_projection["profile_revision"],
            "expected_workflow_revision": symptom_projection["workflow_revision"],
            "expected_projection_token": symptom_projection["projection_token"],
            "symptom_text": "Separate caregiver symptom",
            "reported_subject": "patient",
            "caregiver_action_id": saved["caregiver_actions"][0]["id"],
            "expected_action_token": first.get_json()["follow_up"]["token"],
        },
    )
    assert cross_link.status_code == 409


def test_receipt_correction_rotates_source_token_without_mutating_reconciliation_records(
    app_client, agent, empty_profile
):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course = _create_course(client, status="current", planned_date=None)[0].get_json()["course"]
    discrepancy = _create_discrepancy(client, course)[0].get_json()["discrepancy"]
    before = agent.load_profile()
    preserved_courses = copy.deepcopy(before["treatment_courses"])
    preserved_discrepancies = copy.deepcopy(before["treatment_discrepancies"])
    old_source_token = _projection(client)["source_facts"][0]["token"]
    receipt = agent.public_receipt(before, "treatment-feed-001")
    treatment_change = next(item for item in receipt["changes"] if item["category"] == "treatments")

    agent.correct_change(
        before,
        "treatment-feed-001",
        treatment_change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=treatment_change["target_token"],
        replacement="Caregiver-corrected legacy compatibility wording",
    )
    projected = agent.project_treatment_reconciliation(before)

    assert projected["source_facts"][0]["token"] != old_source_token
    assert before["treatment_courses"] == preserved_courses
    assert before["treatment_discrepancies"] == preserved_discrepancies
    assert (
        projected["discrepancies"][0]["source_fact"]["token"]
        == (discrepancy["source_fact"]["token"])
    )


def test_projection_fails_closed_for_duplicate_identity_and_inconsistent_dates(
    agent, empty_profile
):
    timestamp = "2026-08-01T10:00:00"
    course = {
        "id": agent.new_treatment_course_id(),
        "status": "current",
        "treatment_text": "Exact text",
        "legacy_component_ids": [],
        "start_date": "2026-08",
        "start_date_precision": "day",
        "start_date_kind": "caregiver_entered",
        "stop_date": None,
        "stop_date_precision": "unknown",
        "stop_date_kind": "unknown",
        "planned_date": None,
        "planned_date_precision": "unknown",
        "planned_date_kind": "unknown",
        "previous_course_id": None,
        "provenance": agent.treatment_course_provenance(),
        "created_at": timestamp,
        "updated_at": timestamp,
        "history": [],
    }
    empty_profile["treatment_courses"] = [course, copy.deepcopy(course)]

    with pytest.raises(agent.TreatmentProjectionError, match="identity"):
        agent.project_treatment_reconciliation(empty_profile)

    empty_profile["treatment_courses"] = [course]
    with pytest.raises(agent.TreatmentProjectionError, match="date"):
        agent.project_treatment_reconciliation(empty_profile)


def test_projection_fails_closed_for_malformed_containers_and_private_current_value(
    agent, empty_profile
):
    malformed = copy.deepcopy(empty_profile)
    malformed["patient"] = None
    with pytest.raises(agent.TreatmentProjectionError, match="Legacy treatment authority"):
        agent.project_treatment_reconciliation(malformed)

    malformed = copy.deepcopy(empty_profile)
    malformed["source_documents"] = [None]
    with pytest.raises(agent.TreatmentProjectionError, match="source authority"):
        agent.project_treatment_reconciliation(malformed)

    malformed = _ingest_treatment(agent, copy.deepcopy(empty_profile))
    malformed["source_documents"][0]["text"] = "not metadata"
    with pytest.raises(agent.TreatmentProjectionError, match="source authority"):
        agent.project_treatment_reconciliation(malformed)

    private = _ingest_treatment(agent, copy.deepcopy(empty_profile))
    treatment_change = next(
        item
        for item in private["document_imports"][0]["changes"]
        if item["category"] == "treatments"
    )
    treatment_change["effective_value"] = {"path": "private/source/path"}
    with pytest.raises(agent.TreatmentProjectionError, match="snapshot"):
        agent.project_treatment_reconciliation(private)

    legacy = copy.deepcopy(empty_profile)
    legacy["patient"]["current_treatments"] = ["one", "two"]
    agent.sync_treatment_records(legacy)
    legacy["patient"]["current_treatment_records"][1]["component_order"] = "invalid"
    with pytest.raises(agent.TreatmentProjectionError, match="component authority"):
        agent.project_treatment_reconciliation(legacy)

    legacy = copy.deepcopy(empty_profile)
    legacy["patient"]["current_treatments"] = ["one"]
    agent.sync_treatment_records(legacy)
    component_id = legacy["patient"]["current_treatment_records"][0]["id"]
    legacy["treatments_classified"] = [
        {
            "id": "generated",
            "text": {"path": "private/source/path"},
            "label": "Compatibility",
            "category": "active",
            "date": None,
            "source_treatment_ids": [component_id],
        }
    ]
    with pytest.raises(agent.TreatmentProjectionError, match="compatibility authority"):
        agent.project_treatment_reconciliation(legacy)


def test_course_snapshot_and_replay_enforce_live_field_contract(app_client, agent, empty_profile):
    _, client = app_client
    profile = _ingest_treatment(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    course_response, course_request = _create_course(client)
    course = course_response.get_json()["course"]
    discrepancy = _create_discrepancy(client, course)[0].get_json()["discrepancy"]

    malformed = agent.load_profile()
    malformed["treatment_discrepancies"][0]["course_snapshot"]["dose_text"] = [
        "not",
        "text",
    ]
    with pytest.raises(agent.TreatmentProjectionError, match="authority"):
        agent.project_treatment_reconciliation(malformed)

    replay_tamper = agent.load_profile()
    course_event = replay_tamper["treatment_courses"][0]["history"][0]
    course_event["result_snapshot"]["course"]["dose_text"] = "x" * 501
    course_event["result_snapshot"]["course"]["planned_date_precision"] = "day"
    course_event["result_hash"] = agent.request_hash(course_event["result_snapshot"])
    agent.save_profile(replay_tamper, clinical_change=False)

    replay = client.post("/api/treatment-reconciliation/courses", json=course_request)

    assert discrepancy["citation_kind"] == "source_vs_course"
    assert replay.status_code == 409
    assert replay.get_json()["code"] == "treatment_conflict"


def test_pre_extension_course_replay_snapshot_remains_exact_and_safe(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created_response, request = _create_course(client)
    created = created_response.get_json()["course"]
    legacy = agent.load_profile()
    event = legacy["treatment_courses"][0]["history"][0]
    legacy_snapshot = event["result_snapshot"]["course"]
    legacy_snapshot.pop("terminal_qualifier")
    legacy_snapshot.pop("terminal_detail")
    legacy_snapshot.pop("lifecycle")
    exact_legacy_snapshot = copy.deepcopy(event["result_snapshot"])
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(legacy, clinical_change=False)

    replay = client.post("/api/treatment-reconciliation/courses", json=request)

    assert created["terminal_qualifier"] is None
    assert replay.status_code == 200
    body = replay.get_json()
    assert body.pop("idempotent_replay") is True
    assert body == exact_legacy_snapshot
    assert "terminal_qualifier" not in body["course"]
    assert "lifecycle" not in body["course"]


def test_terminal_mutations_use_one_save_and_failed_transition_rolls_back(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    original_save = agent.save_profile
    saves = 0

    def counting_save(*args, **kwargs):
        nonlocal saves
        saves += 1
        return original_save(*args, **kwargs)

    monkeypatch.setattr(agent, "save_profile", counting_save)
    created_response, _ = _create_course(
        client,
        status="current",
        planned_date=None,
    )
    created = created_response.get_json()["course"]
    assert created_response.status_code == 201
    assert saves == 1

    projection = _projection(client)
    transitioned = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/transition",
        json={
            **_meta(projection, "counted-terminal-transition"),
            "expected_course_token": created["token"],
            "status": "past",
            "terminal_qualifier": "ended",
        },
    )
    assert transitioned.status_code == 200
    assert saves == 2
    assert transitioned.get_json()["profile_revision"] == 2
    assert transitioned.get_json()["workflow_revision"] == 2

    failed_course = _create_course(
        client,
        mutation_id="failed-transition-course-create",
        status="current",
        planned_date=None,
    )[0].get_json()["course"]
    assert saves == 3
    projection = _projection(client)
    before = copy.deepcopy(agent.load_profile())

    def fail_save(*args, **kwargs):
        raise OSError("simulated terminal transition save failure")

    monkeypatch.setattr(agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated terminal transition save failure"):
        client.post(
            f"/api/treatment-reconciliation/courses/{failed_course['id']}/transition",
            json={
                **_meta(projection, "terminal-transition-save-failure"),
                "expected_course_token": failed_course["token"],
                "status": "past",
                "terminal_qualifier": "ended",
            },
        )
    monkeypatch.setattr(agent, "save_profile", original_save)

    assert agent.load_profile() == before


def test_terminal_overflow_fails_whole_projection_without_side_effects(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    _create_course(
        client,
        status="past",
        terminal_qualifier="other",
        terminal_detail="x" * 1000,
        planned_date=None,
    )
    malformed = agent.load_profile()
    malformed["treatment_courses"][0]["terminal_detail"] = "x" * 1001
    agent.save_profile(malformed, clinical_change=False)
    before = copy.deepcopy(agent.load_profile())

    response = client.get("/api/patient/treatment-reconciliation")

    assert response.status_code == 422
    assert response.get_json()["code"] == "treatment_projection_too_large"
    assert agent.load_profile() == before


@pytest.mark.parametrize(
    ("qualifier", "detail"),
    [
        (["ended"], None),
        ({"value": "ended"}, None),
        ("other", "unsafe\x00detail"),
    ],
)
def test_malformed_terminal_authority_fails_whole_projection_with_bounded_422(
    app_client,
    agent,
    empty_profile,
    qualifier,
    detail,
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    _create_course(
        client,
        status="past",
        terminal_qualifier="ended",
        planned_date=None,
    )
    malformed = agent.load_profile()
    malformed["treatment_courses"][0]["terminal_qualifier"] = qualifier
    malformed["treatment_courses"][0]["terminal_detail"] = detail
    agent.save_profile(malformed, clinical_change=False)
    before = copy.deepcopy(agent.load_profile())

    response = client.get("/api/patient/treatment-reconciliation")

    assert response.status_code == 422
    assert response.get_json() == {
        "error": "Treatment course terminal authority is inconsistent.",
        "code": "treatment_projection_invalid",
    }
    assert agent.load_profile() == before


def test_save_failure_does_not_persist_partial_treatment_course(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)

    def fail_save(*args, **kwargs):
        raise OSError("simulated save failure")

    monkeypatch.setattr(agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated save failure"):
        client.post(
            "/api/treatment-reconciliation/courses",
            json={
                **_meta(projection, "course-save-failure"),
                "status": "current",
                "treatment_text": "Must not persist",
            },
        )
    monkeypatch.undo()

    assert agent.load_profile()["treatment_courses"] == []


def test_save_failure_does_not_persist_partial_two_source_discrepancy(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    profile = _ingest_two_treatments(agent, empty_profile)
    agent.save_profile(profile, clinical_change=False)
    projection = _projection(client)
    source_a, source_b = projection["source_facts"]
    request = {
        **_meta(projection, "source-discrepancy-save-failure"),
        "category": "other",
        "comparison_text": "Must not persist.",
        "source_fact_ref": source_a["ref"],
        "expected_source_fact_token": source_a["token"],
        "comparison_source_fact_ref": source_b["ref"],
        "expected_comparison_source_fact_token": source_b["token"],
    }

    def fail_save(*args, **kwargs):
        raise OSError("simulated discrepancy save failure")

    monkeypatch.setattr(agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated discrepancy save failure"):
        client.post("/api/treatment-reconciliation/discrepancies", json=request)
    monkeypatch.undo()

    saved = agent.load_profile()
    assert saved["treatment_discrepancies"] == []
    assert saved["profile_revision"] == projection["profile_revision"]
    assert saved["workflow_revision"] == projection["workflow_revision"]


def test_reconciliation_state_is_excluded_from_existing_model_contexts(agent, empty_profile):
    course_secret = "COURSE-WORKFLOW-ONLY-UNIQUE"
    discrepancy_secret = "DISCREPANCY-WORKFLOW-ONLY-UNIQUE"
    empty_profile["treatment_courses"] = [{"treatment_text": course_secret}]
    empty_profile["treatment_discrepancies"] = [{"comparison_text": discrepancy_secret}]

    summary = agent.get_patient_summary(empty_profile)
    chat = agent.build_chat_system(empty_profile)

    assert course_secret not in summary
    assert discrepancy_secret not in summary
    assert course_secret not in chat
    assert discrepancy_secret not in chat


def test_terminal_authority_is_excluded_from_status_and_existing_model_contexts(
    app_client, agent, empty_profile
):
    _, client = app_client
    terminal_secret = "TERMINAL-AUTHORITY-WORKFLOW-ONLY-UNIQUE"
    empty_profile["treatment_courses"] = [
        {
            "id": agent.new_treatment_course_id(),
            "status": "past",
            "treatment_text": "Workflow-only course",
            "legacy_component_ids": [],
            "start_date": None,
            "start_date_precision": "unknown",
            "start_date_kind": "unknown",
            "stop_date": None,
            "stop_date_precision": "unknown",
            "stop_date_kind": "unknown",
            "planned_date": None,
            "planned_date_precision": "unknown",
            "planned_date_kind": "unknown",
            "terminal_qualifier": "other",
            "terminal_detail": terminal_secret,
            "previous_course_id": None,
            "provenance": agent.treatment_course_provenance(),
            "created_at": "2026-08-10T10:00:00",
            "updated_at": "2026-08-10T10:00:00",
            "history": [],
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    assert terminal_secret not in agent.get_patient_summary(agent.load_profile())
    assert terminal_secret not in agent.build_chat_system(agent.load_profile())
    assert terminal_secret not in json.dumps(client.get("/api/status").get_json())
