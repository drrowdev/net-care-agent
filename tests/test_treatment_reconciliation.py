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


def _ingest_treatment(agent, profile, *, job_id="treatment-feed-001"):
    text = "Clinic note: Start lanreotide 120mg q4w."
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-02",
        "summary": "Treatment discussion.",
        "treatment_changes": ["Start lanreotide 120mg q4w"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "Start lanreotide 120mg q4w",
            }
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


def test_v12_migration_adds_only_empty_reconciliation_authority():
    from agent.migrations import apply_migrations

    legacy = {
        "schema_version": 11,
        "patient": {
            "current_treatments": ["same", "same"],
            "current_treatment_records": [{"id": "keep", "unknown": {"x": 1}}],
        },
        "treatments_classified": [{"id": "generated", "text": "same", "extra": True}],
        "document_imports": [{"id": "receipt", "changes": [], "unknown": ["keep"]}],
        "unknown_top": {"keep": None},
    }
    preserved = copy.deepcopy(legacy)

    result = apply_migrations(legacy)

    assert result["schema_version"] == 12
    assert result["treatment_courses"] == []
    assert result["treatment_discrepancies"] == []
    for key, value in preserved.items():
        if key != "schema_version":
            assert result[key] == value


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


def test_course_transition_is_explicit_and_restart_creates_new_episode(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = _create_course(client)[0].get_json()["course"]
    projection = _projection(client)
    transition = client.post(
        f"/api/treatment-reconciliation/courses/{created['id']}/transition",
        json={
            **_meta(projection, "course-to-past-001"),
            "expected_course_token": created["token"],
            "status": "past",
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


def test_past_course_is_terminal_and_dates_are_never_inferred(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = _create_course(client, status="past", planned_date=None)[0].get_json()["course"]
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
