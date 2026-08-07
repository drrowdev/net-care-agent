from __future__ import annotations

import importlib
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def _save_current_summary(agent, profile, *, revision=5):
    profile["profile_revision"] = revision
    profile["summary_stale"] = False
    profile["executive_summary"] = {
        "generation_id": "summary-current",
        "summary_revision": revision,
        "stale": False,
        "next_actions": [
            {
                "action": "Ask the treating team to confirm the monitoring schedule",
                "priority": "high",
                "timeframe": "At the next visit",
                "evidence_ids": [],
            }
        ],
    }
    agent.save_profile(profile, clinical_change=False)


def _create_visit(client, *, mutation_id="visit-create-001"):
    response = client.post(
        "/api/visits",
        json={"mutation_id": mutation_id, "title": "Oncology follow-up", "date": "2026-09-01"},
    )
    assert response.status_code == 201
    return response.get_json()["item"]


def test_manual_follow_up_is_idempotent_and_workflow_only(app_client, agent, empty_profile):
    _, client = app_client
    empty_profile["profile_revision"] = 7
    agent.save_profile(empty_profile, clinical_change=False)
    request = {
        "mutation_id": "action-create-001",
        "origin_kind": "manual",
        "text": "Contact the treating team to confirm the appointment date",
        "owner": "Caregiver",
        "due_date": "2026-09-01",
    }

    first = client.post("/api/follow-ups", json=request)
    replay = client.post("/api/follow-ups", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert first.get_json()["item"]["id"] == replay.get_json()["item"]["id"]
    assert saved["workflow_revision"] == 1
    assert saved["profile_revision"] == 7
    assert len(saved["caregiver_actions"]) == 1
    assert len(saved["caregiver_actions"][0]["history"]) == 1


def test_generated_action_is_server_snapshotted_and_survives_artifact_change(
    app_client, agent, empty_profile
):
    _, client = app_client
    _save_current_summary(agent, empty_profile)
    source = client.get("/api/summary").get_json()["next_actions"][0]

    response = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-accept-001",
            "origin_kind": "executive_summary_action",
            "source_id": source["id"],
            "expected_source_token": source["source_token"],
        },
    )
    assert response.status_code == 201
    action = response.get_json()["item"]
    assert action["text"] == source["action"]
    assert action["origin_snapshot"]["snapshot"]["priority"] == "high"

    changed = agent.load_profile()
    changed["executive_summary"]["next_actions"] = []
    agent.save_profile(changed, clinical_change=False)

    stored = agent.load_profile()["caregiver_actions"][0]
    assert stored["text"] == source["action"]
    assert stored["origin_snapshot"]["source_id"] == source["id"]


def test_generated_action_rejects_stale_source_without_mutation(app_client, agent, empty_profile):
    _, client = app_client
    _save_current_summary(agent, empty_profile)
    source = client.get("/api/summary").get_json()["next_actions"][0]
    changed = agent.load_profile()
    agent.save_profile(changed)
    before = agent.load_profile()

    response = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-accept-002",
            "origin_kind": "executive_summary_action",
            "source_id": source["id"],
            "expected_source_token": source["source_token"],
        },
    )
    after = agent.load_profile()

    assert response.status_code == 409
    assert after["workflow_revision"] == before["workflow_revision"]
    assert after["caregiver_actions"] == []


def test_migrated_generationless_summary_gets_stale_projection_and_post_is_atomic(
    app_client, agent
):
    _, client = app_client
    from agent.migrations import apply_migrations

    profile = apply_migrations(
        {
            "schema_version": 7,
            "profile_revision": 6,
            "summary_stale": False,
            "patient": {"diagnosis": "NET"},
            "executive_summary": {
                "summary_revision": 6,
                "stale": False,
                "next_actions": [
                    {
                        "action": "Ask the treating team to confirm the monitoring schedule",
                        "priority": "high",
                    }
                ],
            },
        }
    )
    agent.save_profile(profile, clinical_change=False)
    stored = agent.load_profile()
    source = agent.project_summary_actions(stored["executive_summary"])[0]
    before = agent.load_profile()

    projection = client.get("/api/summary")
    response = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "reject-migrated-summary-action",
            "origin_kind": "executive_summary_action",
            "source_id": source["id"],
            "expected_source_token": source["source_token"],
        },
    )

    assert projection.get_json()["stale"] is True
    assert projection.get_json()["content_hidden"] is True
    assert "next_actions" not in projection.get_json()
    assert response.status_code == 409
    assert agent.load_profile() == before


def test_generated_source_helper_rejects_empty_current_generation(agent):
    source = {
        "id": "q-stale",
        "generation_job_id": None,
        "source_profile_revision": 3,
        "stale": False,
    }

    with pytest.raises(agent.FollowThroughConflict, match="outdated"):
        agent.validate_current_generated_source(
            source,
            agent.semantic_token(source),
            current_profile_revision=3,
            current_generation_id=None,
            generation_field="generation_job_id",
            changed_message="changed",
            stale_message="outdated",
        )


def test_generationless_question_gets_stale_projection_and_post_is_atomic(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 4
    empty_profile["questions_generation_id"] = None
    empty_profile["appointment_questions"] = [
        {
            "id": "q-generationless",
            "text": "What should we monitor?",
            "source": "ai",
            "generation_job_id": None,
            "source_profile_revision": 4,
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="visit-generationless")
    source = client.get("/api/questions").get_json()[0]
    before = agent.load_profile()

    response = client.post(
        f"/api/visits/{visit['id']}/questions",
        json={
            "mutation_id": "visit-question-stale-generationless",
            "expected_visit_token": visit["token"],
            "source_kind": "generated",
            "source_question_id": source["id"],
            "expected_source_token": source["source_token"],
        },
    )

    assert source["stale"] is True
    assert response.status_code == 409
    assert agent.load_profile() == before


def test_manual_visit_question_remains_acceptable(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="visit-manual-question")

    response = client.post(
        f"/api/visits/{visit['id']}/questions",
        json={
            "mutation_id": "visit-question-manual",
            "expected_visit_token": visit["token"],
            "source_kind": "manual",
            "text": "What should we discuss at the next appointment?",
        },
    )

    assert response.status_code == 201
    question = response.get_json()["visit"]["question_snapshots"][0]
    assert question["source_kind"] == "manual"
    assert question["source_generation_id"] is None


def test_follow_up_admin_edit_does_not_stale_clinical_artifacts_but_outcome_does(
    app_client, agent, empty_profile
):
    _, client = app_client
    _save_current_summary(agent, empty_profile)
    empty_profile = agent.load_profile()
    empty_profile["questions_generation_id"] = "questions-1"
    empty_profile["appointment_questions"] = [
        {
            "id": "q1",
            "text": "What should we monitor?",
            "source": "ai",
            "generation_job_id": "questions-1",
            "source_profile_revision": 5,
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-create-003",
            "origin_kind": "manual",
            "text": "Ask the treating team about monitoring",
        },
    ).get_json()["item"]

    admin = client.patch(
        f"/api/follow-ups/{created['id']}",
        json={
            "mutation_id": "action-update-003",
            "expected_token": created["token"],
            "owner": "Caregiver",
        },
    )
    assert admin.status_code == 200
    assert admin.get_json()["profile_revision"] == 5
    assert agent.load_profile()["summary_stale"] is False

    current = admin.get_json()["item"]
    clinical = client.patch(
        f"/api/follow-ups/{current['id']}",
        json={
            "mutation_id": "action-complete-003",
            "expected_token": current["token"],
            "status": "completed",
            "outcome": {
                "kind": "clinician_attributed",
                "text": "The clinician confirmed imaging in three months",
            },
        },
    )
    saved = agent.load_profile()

    assert clinical.status_code == 200
    assert clinical.get_json()["profile_revision"] == 6
    assert saved["workflow_revision"] == 3
    assert saved["summary_stale"] is True
    assert saved["appointment_questions"][0]["stale"] is True
    assert (
        saved["caregiver_actions"][0]["outcome"]["provenance"]["source_verification"]
        == "unverified"
    )


def test_direct_treatment_instruction_is_rejected(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)

    response = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-unsafe-001",
            "origin_kind": "manual",
            "text": "Start treatment tomorrow",
        },
    )

    assert response.status_code == 400
    assert "treating team" in response.get_json()["error"]
    assert agent.load_profile()["caregiver_actions"] == []


def test_noop_follow_up_patch_does_not_append_audit_or_revision(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-noop-create",
            "origin_kind": "manual",
            "text": "Ask the treating team about timing",
        },
    ).get_json()["item"]

    response = client.patch(
        f"/api/follow-ups/{created['id']}",
        json={
            "mutation_id": "action-noop-update",
            "expected_token": created["token"],
        },
    )
    saved = agent.load_profile()

    assert response.status_code == 400
    assert saved["workflow_revision"] == 1
    assert len(saved["caregiver_actions"][0]["history"]) == 1


def test_visit_question_snapshot_and_answer_revision_semantics(app_client, agent, empty_profile):
    _, client = app_client
    empty_profile["profile_revision"] = 4
    empty_profile["questions_generation_id"] = "questions-current"
    empty_profile["appointment_questions"] = [
        {
            "id": "q-generated",
            "text": "What does the clinician recommend for monitoring?",
            "category": "Monitoring",
            "priority": "high",
            "rationale": "Clarify follow-up",
            "source": "ai",
            "generation_job_id": "questions-current",
            "source_profile_revision": 4,
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client)
    source = client.get("/api/questions").get_json()[0]
    assert source["stale"] is False

    added = client.post(
        f"/api/visits/{visit['id']}/questions",
        json={
            "mutation_id": "visit-question-001",
            "expected_visit_token": visit["token"],
            "source_kind": "generated",
            "source_question_id": source["id"],
            "expected_source_token": source["source_token"],
            "pinned": True,
            "order": 1,
        },
    )
    assert added.status_code == 201
    assert added.get_json()["profile_revision"] == 4
    question = added.get_json()["visit"]["question_snapshots"][0]
    assert question["source_kind"] == "generated"
    assert question["text"] == source["text"]

    answered = client.patch(
        f"/api/visits/{visit['id']}/questions/{question['id']}",
        json={
            "mutation_id": "visit-answer-001",
            "expected_token": question["token"],
            "answer": {"status": "unknown"},
        },
    )
    saved_question = answered.get_json()["visit"]["question_snapshots"][0]

    assert answered.status_code == 200
    assert answered.get_json()["profile_revision"] == 5
    assert saved_question["answer"]["status"] == "unknown"
    assert saved_question["answer"]["text"] is None
    assert saved_question["answer"]["provenance"] == {
        "capture_method": "caregiver_entered",
        "attributed_to": "clinician",
        "source_verification": "unverified",
    }


def test_current_generated_snapshots_survive_later_clinical_revision(
    app_client, agent, empty_profile
):
    _, client = app_client
    _save_current_summary(agent, empty_profile, revision=4)
    profile = agent.load_profile()
    profile["questions_generation_id"] = "questions-current"
    profile["appointment_questions"] = [
        {
            "id": "q-current",
            "text": "What should we monitor?",
            "source": "ai",
            "generation_job_id": "questions-current",
            "source_profile_revision": 4,
            "stale": False,
        }
    ]
    agent.save_profile(profile, clinical_change=False)

    summary_source = client.get("/api/summary").get_json()["next_actions"][0]
    accepted_action = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "durable-summary-action",
            "origin_kind": "executive_summary_action",
            "source_id": summary_source["id"],
            "expected_source_token": summary_source["source_token"],
        },
    )
    assert accepted_action.status_code == 201

    visit = _create_visit(client, mutation_id="durable-visit-create")
    question_source = client.get("/api/questions").get_json()[0]
    accepted_question = client.post(
        f"/api/visits/{visit['id']}/questions",
        json={
            "mutation_id": "durable-question-snapshot",
            "expected_visit_token": visit["token"],
            "source_kind": "generated",
            "source_question_id": question_source["id"],
            "expected_source_token": question_source["source_token"],
        },
    )
    assert accepted_question.status_code == 201

    changed = agent.load_profile()
    agent.save_profile(changed)
    saved = agent.load_profile()

    assert saved["caregiver_actions"][0]["text"] == summary_source["action"]
    assert saved["caregiver_actions"][0]["origin_snapshot"]["generation_id"] == "summary-current"
    assert saved["visits"][0]["question_snapshots"][0]["text"] == question_source["text"]
    assert (
        saved["visits"][0]["question_snapshots"][0]["source_generation_id"] == "questions-current"
    )


def test_decision_text_is_immutable_and_successor_supersedes_atomically(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="visit-create-002")
    first = client.post(
        f"/api/visits/{visit['id']}/decisions",
        json={
            "mutation_id": "visit-decision-001",
            "expected_visit_token": visit["token"],
            "text": "Continue current monitoring until the next scan",
        },
    )
    assert first.status_code == 201
    visit = first.get_json()["visit"]
    decision = visit["decisions"][0]

    edit = client.patch(
        f"/api/visits/{visit['id']}/decisions/{decision['id']}",
        json={
            "mutation_id": "visit-decision-edit-001",
            "expected_token": decision["token"],
            "text": "Silently replace the statement",
        },
    )
    assert edit.status_code == 400

    successor = client.post(
        f"/api/visits/{visit['id']}/decisions",
        json={
            "mutation_id": "visit-decision-002",
            "expected_visit_token": visit["token"],
            "text": "Reassess monitoring after the next scan",
            "supersedes_id": decision["id"],
        },
    )
    decisions = successor.get_json()["visit"]["decisions"]

    assert successor.status_code == 201
    assert decisions[0]["text"] == "Continue current monitoring until the next scan"
    assert decisions[0]["status"] == "superseded"
    assert decisions[1]["supersedes_id"] == decisions[0]["id"]
    assert decisions[1]["provenance"]["source_verification"] == "unverified"


def test_unrelated_workflow_revision_does_not_conflict_with_target_token(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    first = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-independent-001",
            "origin_kind": "manual",
            "text": "Contact the clinic about the first appointment",
        },
    ).get_json()["item"]
    second = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "action-independent-002",
            "origin_kind": "manual",
            "text": "Ask the treating team about the second appointment",
        },
    ).get_json()["item"]

    update_first = client.patch(
        f"/api/follow-ups/{first['id']}",
        json={
            "mutation_id": "action-independent-003",
            "expected_token": first["token"],
            "owner": "Caregiver",
        },
    )

    assert update_first.status_code == 200
    assert update_first.get_json()["workflow_revision"] == 3
    assert (
        next(
            item for item in agent.load_profile()["caregiver_actions"] if item["id"] == second["id"]
        )["owner"]
        is None
    )


def test_alert_resolution_links_inline_follow_up_atomically_and_replays(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["alerts"] = [
        {
            "id": "alert-target",
            "priority": "high",
            "message": "Monitoring needs review",
            "action_required": "Ask the treating team to confirm follow-up",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        },
        {
            "id": "alert-sibling",
            "priority": "medium",
            "message": "Sibling remains active",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        },
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    alert = next(item for item in status["alerts"] if item["id"] == "alert-target")
    request = {
        "mutation_id": "alert-resolve-001",
        "expected_token": alert["resolve_token"],
        "expected_profile_revision": status["profile_revision"],
        "outcome": {"kind": "administrative", "text": "Called the clinic"},
        "follow_up": {
            "text": "Ask the treating team to confirm the monitoring date",
            "owner": "Caregiver",
        },
    }

    first = client.post("/api/alerts/alert-target/resolve", json=request)
    replay = client.post("/api/alerts/alert-target/resolve", json=request)
    saved = agent.load_profile()

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert len(saved["caregiver_actions"]) == 1
    target = next(item for item in saved["alerts"] if item["id"] == "alert-target")
    sibling = next(item for item in saved["alerts"] if item["id"] == "alert-sibling")
    assert target["resolved"] is True
    assert target["resolution"]["follow_up_id"] == saved["caregiver_actions"][0]["id"]
    assert sibling["resolved"] is False
    assert saved["workflow_revision"] == 1
    assert saved["profile_revision"] == 4


def test_model_context_labels_captured_statements_as_unverified(agent, empty_profile):
    empty_profile["visits"] = [
        {
            "id": "visit",
            "title": "Follow-up",
            "question_snapshots": [
                {
                    "id": "question",
                    "text": "What is the plan?",
                    "answer": {
                        "status": "answered",
                        "text": "Repeat imaging later",
                        "provenance": agent.capture_provenance(),
                    },
                }
            ],
            "decisions": [
                {
                    "id": "decision",
                    "text": "Continue monitoring",
                    "status": "active",
                    "provenance": agent.capture_provenance(),
                }
            ],
        }
    ]

    context = agent.get_patient_summary(empty_profile)

    assert "Caregiver-captured clinician statements (attributed, unverified)" in context
    assert "caregiver-recorded clinician answer" in context
    assert "caregiver-recorded clinician decision" in context


def test_visit_follow_up_snapshots_decision_and_replays(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="visit-create-003")
    decision_response = client.post(
        f"/api/visits/{visit['id']}/decisions",
        json={
            "mutation_id": "visit-decision-003",
            "expected_visit_token": visit["token"],
            "text": "Confirm the next scan date",
        },
    )
    visit = decision_response.get_json()["visit"]
    decision = visit["decisions"][0]
    request = {
        "mutation_id": "visit-followup-003",
        "expected_visit_token": visit["token"],
        "decision_id": decision["id"],
        "text": "Contact the treating team to confirm the next scan date",
    }

    first = client.post(f"/api/visits/{visit['id']}/follow-ups", json=request)
    replay = client.post(f"/api/visits/{visit['id']}/follow-ups", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert len(saved["caregiver_actions"]) == 1
    assert saved["caregiver_actions"][0]["origin_snapshot"]["source_id"] == decision["id"]
    assert saved["visits"][0]["follow_up_ids"] == [saved["caregiver_actions"][0]["id"]]


def test_independent_concurrent_action_updates_do_not_lose_data(app_client, agent, empty_profile):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    actions = []
    for index in range(2):
        actions.append(
            client.post(
                "/api/follow-ups",
                json={
                    "mutation_id": f"concurrent-create-{index}",
                    "origin_kind": "manual",
                    "text": f"Ask the treating team about item {index}",
                },
            ).get_json()["item"]
        )
    barrier = threading.Barrier(2)
    responses = []

    def update(index):
        with app_module.app.test_client() as thread_client:
            barrier.wait()
            responses.append(
                thread_client.patch(
                    f"/api/follow-ups/{actions[index]['id']}",
                    json={
                        "mutation_id": f"concurrent-update-{index}",
                        "expected_token": actions[index]["token"],
                        "owner": f"Owner {index}",
                    },
                )
            )

    threads = [threading.Thread(target=update, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert sorted(response.status_code for response in responses) == [200, 200]
    saved = agent.load_profile()
    assert {item["owner"] for item in saved["caregiver_actions"]} == {
        "Owner 0",
        "Owner 1",
    }
    assert saved["workflow_revision"] == 4


def test_failed_save_leaves_persisted_profile_unchanged(
    app_client, agent, empty_profile, monkeypatch
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    original_save = app_module.agent.save_profile

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(app_module.agent, "save_profile", fail_save)
    with pytest.raises(OSError):
        client.post(
            "/api/follow-ups",
            json={
                "mutation_id": "failed-save-001",
                "origin_kind": "manual",
                "text": "Ask the treating team about timing",
            },
        )
    monkeypatch.setattr(app_module.agent, "save_profile", original_save)

    saved = agent.load_profile()
    assert saved["caregiver_actions"] == []
    assert saved["workflow_revision"] == 0


def test_cli_resolve_alert_uses_stable_id_and_audit(agent, empty_profile):
    from agent.cli import cmd_resolve_alert

    empty_profile["profile_revision"] = 2
    empty_profile["alerts"] = [
        {
            "id": "cli-alert",
            "priority": "high",
            "message": "Call needed",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    cmd_resolve_alert(SimpleNamespace(alert_id="cli-alert", outcome="Clinic contacted"))
    saved = agent.load_profile()

    assert saved["alerts"][0]["resolved"] is True
    assert saved["alerts"][0]["resolution"]["outcome_text"] == "Clinic contacted"
    assert saved["alerts"][0]["history"][0]["operation"] == "resolved"
    assert saved["workflow_revision"] == 1
    assert saved["profile_revision"] == 3
