from __future__ import annotations

import importlib
import json
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


def _without_replay_marker(body):
    result = dict(body)
    assert result.pop("idempotent_replay") is True
    return result


def test_request_hash_is_deterministic_and_preserves_cas_tokens():
    from agent.follow_through import request_hash

    first = {
        "mutation_id": "hash-test-001",
        "expected_token": "token-a",
        "nested": {"answer": "same", "source_token": "source-a"},
    }
    reordered = {
        "nested": {"source_token": "source-a", "answer": "same"},
        "expected_token": "token-a",
        "mutation_id": "hash-test-001",
    }

    assert request_hash(first) == request_hash(reordered)
    assert request_hash(first) != request_hash({**first, "expected_token": "token-b"})
    assert request_hash(first) != request_hash(
        {
            **first,
            "nested": {"answer": "same", "source_token": "source-b"},
        }
    )


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


def test_reused_mutation_id_is_scoped_to_endpoint_operation_and_target(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    first_visit = _create_visit(client, mutation_id="scope-visit-001")
    second_visit = _create_visit(client, mutation_id="scope-visit-002")
    decision_request = {
        "mutation_id": "scope-collision-001",
        "expected_visit_token": first_visit["token"],
        "text": "Contact the treating team to confirm the next scan date",
    }

    decision = client.post(
        f"/api/visits/{first_visit['id']}/decisions",
        json=decision_request,
    )
    cross_endpoint = client.post(
        f"/api/visits/{first_visit['id']}/follow-ups",
        json=decision_request,
    )
    visit_patch = {
        "mutation_id": "scope-collision-002",
        "expected_token": second_visit["token"],
        "title": "Updated visit",
    }
    first_target = client.patch(
        f"/api/visits/{first_visit['id']}",
        json=visit_patch,
    )
    cross_target = client.patch(
        f"/api/visits/{second_visit['id']}",
        json=visit_patch,
    )

    assert decision.status_code == 201
    assert cross_endpoint.status_code == 409
    assert cross_endpoint.get_json()["code"] == "workflow_conflict"
    assert "item" not in cross_endpoint.get_json()
    assert first_target.status_code == 409  # first_visit changed when the decision was added
    assert cross_target.status_code == 200
    reuse_other_target = client.patch(
        f"/api/visits/{first_visit['id']}",
        json=visit_patch,
    )
    assert reuse_other_target.status_code == 409
    assert reuse_other_target.get_json()["code"] == "workflow_conflict"


def test_unsupported_or_changed_replay_request_never_replays(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    request = {
        "mutation_id": "strict-replay-001",
        "origin_kind": "manual",
        "text": "Ask the treating team to confirm scan timing",
    }
    first = client.post("/api/follow-ups", json=request)
    unsupported = client.post(
        "/api/follow-ups",
        json={**request, "token": first.get_json()["item"]["token"]},
    )
    changed = client.post(
        "/api/follow-ups",
        json={**request, "text": "Ask the treating team to confirm visit timing"},
    )
    patch_request = {
        "mutation_id": "strict-replay-002",
        "expected_token": first.get_json()["item"]["token"],
        "owner": "Caregiver",
    }
    patched = client.patch(
        f"/api/follow-ups/{first.get_json()['item']['id']}",
        json=patch_request,
    )
    changed_token = client.patch(
        f"/api/follow-ups/{first.get_json()['item']['id']}",
        json={
            **patch_request,
            "expected_token": patched.get_json()["item"]["token"],
        },
    )

    assert first.status_code == 201
    assert unsupported.status_code == 400
    assert unsupported.get_json()["code"] == "invalid_workflow_request"
    assert changed.status_code == 409
    assert patched.status_code == 200
    assert changed_token.status_code == 409


def test_create_replay_returns_original_snapshot_without_saving(
    app_client, agent, empty_profile, monkeypatch
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    original_save = app_module.agent.save_profile
    save_count = 0

    def counting_save(*args, **kwargs):
        nonlocal save_count
        save_count += 1
        return original_save(*args, **kwargs)

    monkeypatch.setattr(app_module.agent, "save_profile", counting_save)
    request = {
        "mutation_id": "snapshot-create-001",
        "origin_kind": "manual",
        "text": "Ask the treating team about monitoring",
    }
    first = client.post("/api/follow-ups", json=request)
    original = first.get_json()
    edited = client.patch(
        f"/api/follow-ups/{original['item']['id']}",
        json={
            "mutation_id": "snapshot-edit-001",
            "expected_token": original["item"]["token"],
            "owner": "Caregiver",
        },
    )
    replay = client.post("/api/follow-ups", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert edited.status_code == 200
    assert replay.status_code == 200
    assert _without_replay_marker(replay.get_json()) == original
    assert "result_hash" not in json.dumps(replay.get_json())
    assert "result_snapshot" not in json.dumps(replay.get_json())
    assert replay.get_json()["item"]["owner"] is None
    assert replay.get_json()["item"]["token"] != edited.get_json()["item"]["token"]
    assert save_count == 2
    assert saved["workflow_revision"] == 2
    assert len(saved["caregiver_actions"][0]["history"]) == 2


@pytest.mark.parametrize("unsafe_snapshot", [{}, {"item": None}])
def test_committed_event_without_safe_result_snapshot_conflicts_deterministically(
    unsafe_snapshot, app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    request = {
        "mutation_id": "legacy-event-001",
        "origin_kind": "manual",
        "text": "Ask the treating team about monitoring",
    }
    created = client.post("/api/follow-ups", json=request)
    profile = agent.load_profile()
    profile["caregiver_actions"][0]["history"][0]["result_snapshot"] = unsafe_snapshot
    agent.save_profile(profile, clinical_change=False)

    replay = client.post("/api/follow-ups", json=request)

    assert created.status_code == 201
    assert replay.status_code == 409
    assert replay.get_json()["code"] == "workflow_conflict"
    assert "safely replayable result" in replay.get_json()["error"]


@pytest.mark.parametrize("corruption", ["skeletal", "wrong_owner"])
def test_replay_rejects_rehashed_malformed_or_mismatched_snapshot(
    corruption, app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    request = {
        "mutation_id": f"corrupt-snapshot-{corruption}",
        "origin_kind": "manual",
        "text": "Ask the treating team about monitoring",
    }
    created = client.post("/api/follow-ups", json=request)
    profile = agent.load_profile()
    action = profile["caregiver_actions"][0]
    event = action["history"][0]
    if corruption == "skeletal":
        event["result_snapshot"] = {
            "item": {"id": action["id"], "token": "synthetic-token"},
            "workflow_revision": 1,
            "profile_revision": 0,
        }
    else:
        event["result_snapshot"]["item"]["id"] = "act_wrong_owner"
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(profile, clinical_change=False)

    replay = client.post("/api/follow-ups", json=request)

    assert created.status_code == 201
    assert replay.status_code == 409
    assert "safely replayable result" in replay.get_json()["error"]


def test_client_cannot_reserve_internal_mutation_namespace(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)

    response = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "_internal-reserved-id",
            "origin_kind": "manual",
            "text": "Ask the treating team about monitoring",
        },
    )

    assert response.status_code == 400
    assert agent.load_profile()["caregiver_actions"] == []


def test_replay_rejects_rehashed_question_snapshot_without_target(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="relation-question-visit")
    added = client.post(
        f"/api/visits/{visit['id']}/questions",
        json={
            "mutation_id": "relation-question-add",
            "expected_visit_token": visit["token"],
            "source_kind": "manual",
            "text": "What is the next step?",
        },
    ).get_json()["visit"]
    question = added["question_snapshots"][0]
    request = {
        "mutation_id": "relation-question-edit",
        "expected_token": question["token"],
        "pinned": True,
    }
    edited = client.patch(
        f"/api/visits/{visit['id']}/questions/{question['id']}",
        json=request,
    )
    profile = agent.load_profile()
    event = profile["visits"][0]["history"][-1]
    event["result_snapshot"]["visit"]["question_snapshots"] = []
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(profile, clinical_change=False)

    replay = client.patch(
        f"/api/visits/{visit['id']}/questions/{question['id']}",
        json=request,
    )

    assert edited.status_code == 200
    assert replay.status_code == 409


def test_replay_rejects_rehashed_visit_follow_up_without_visit_link(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    visit = _create_visit(client, mutation_id="relation-followup-visit")
    request = {
        "mutation_id": "relation-followup-add",
        "expected_visit_token": visit["token"],
        "text": "Ask the treating team about the next step",
    }
    created = client.post(
        f"/api/visits/{visit['id']}/follow-ups",
        json=request,
    )
    profile = agent.load_profile()
    event = profile["visits"][0]["history"][-1]
    event["result_snapshot"]["item"]["visit_id"] = None
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(profile, clinical_change=False)

    replay = client.post(
        f"/api/visits/{visit['id']}/follow-ups",
        json=request,
    )

    assert created.status_code == 201
    assert replay.status_code == 409


def test_replay_rejects_rehashed_alert_snapshot_with_mismatched_resolution(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["alerts"] = [
        {
            "id": "alert-relation",
            "priority": "high",
            "message": "Review needed",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    request = {
        "mutation_id": "relation-alert-resolve",
        "expected_token": status["alerts"][0]["resolve_token"],
        "expected_profile_revision": status["profile_revision"],
    }
    resolved = client.post("/api/alerts/alert-relation/resolve", json=request)
    profile = agent.load_profile()
    event = profile["alerts"][0]["history"][-1]
    event["result_snapshot"]["alert"]["resolution"] = {}
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(profile, clinical_change=False)

    replay = client.post("/api/alerts/alert-relation/resolve", json=request)

    assert resolved.status_code == 200
    assert replay.status_code == 409


def test_every_layer2_visit_mutation_replays_its_original_response(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    create_request = {
        "mutation_id": "symmetry-visit-create",
        "title": "Symmetry visit",
        "date": "2026-10-01",
    }
    created = client.post("/api/visits", json=create_request)
    assert (
        _without_replay_marker(client.post("/api/visits", json=create_request).get_json())
        == created.get_json()
    )
    visit = created.get_json()["item"]

    edit_request = {
        "mutation_id": "symmetry-visit-edit",
        "expected_token": visit["token"],
        "status": "in_progress",
    }
    edited = client.patch(f"/api/visits/{visit['id']}", json=edit_request)
    assert (
        _without_replay_marker(
            client.patch(f"/api/visits/{visit['id']}", json=edit_request).get_json()
        )
        == edited.get_json()
    )
    visit = edited.get_json()["item"]

    question_request = {
        "mutation_id": "symmetry-question-add",
        "expected_visit_token": visit["token"],
        "source_kind": "manual",
        "text": "What is the follow-up schedule?",
    }
    question_added = client.post(
        f"/api/visits/{visit['id']}/questions",
        json=question_request,
    )
    assert (
        _without_replay_marker(
            client.post(
                f"/api/visits/{visit['id']}/questions",
                json=question_request,
            ).get_json()
        )
        == question_added.get_json()
    )
    visit = question_added.get_json()["visit"]
    question = visit["question_snapshots"][0]

    question_patch = {
        "mutation_id": "symmetry-question-edit",
        "expected_token": question["token"],
        "pinned": True,
    }
    question_edited = client.patch(
        f"/api/visits/{visit['id']}/questions/{question['id']}",
        json=question_patch,
    )
    assert (
        _without_replay_marker(
            client.patch(
                f"/api/visits/{visit['id']}/questions/{question['id']}",
                json=question_patch,
            ).get_json()
        )
        == question_edited.get_json()
    )
    visit = question_edited.get_json()["visit"]

    decision_request = {
        "mutation_id": "symmetry-decision-add",
        "expected_visit_token": visit["token"],
        "text": "Continue monitoring until the next scan",
    }
    decision_added = client.post(
        f"/api/visits/{visit['id']}/decisions",
        json=decision_request,
    )
    assert (
        _without_replay_marker(
            client.post(
                f"/api/visits/{visit['id']}/decisions",
                json=decision_request,
            ).get_json()
        )
        == decision_added.get_json()
    )
    visit = decision_added.get_json()["visit"]
    decision = visit["decisions"][0]

    decision_patch = {
        "mutation_id": "symmetry-decision-edit",
        "expected_token": decision["token"],
        "status": "needs_confirmation",
    }
    decision_edited = client.patch(
        f"/api/visits/{visit['id']}/decisions/{decision['id']}",
        json=decision_patch,
    )
    assert (
        _without_replay_marker(
            client.patch(
                f"/api/visits/{visit['id']}/decisions/{decision['id']}",
                json=decision_patch,
            ).get_json()
        )
        == decision_edited.get_json()
    )

    saved = agent.load_profile()
    assert saved["workflow_revision"] == 6
    assert len(saved["visits"][0]["history"]) == 6


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
    assert replay.get_json()["follow_up"] == first.get_json()["follow_up"]
    assert replay.get_json()["follow_up"] is not None
    assert len(saved["caregiver_actions"]) == 1
    target = next(item for item in saved["alerts"] if item["id"] == "alert-target")
    sibling = next(item for item in saved["alerts"] if item["id"] == "alert-sibling")
    assert target["resolved"] is True
    assert agent.alert_token(target) == first.get_json()["alert"]["resolve_token"]
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


def test_alert_linked_follow_up_replay_returns_original_link_snapshot(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 2
    empty_profile["alerts"] = [
        {
            "id": "alert-linked",
            "priority": "high",
            "message": "Linked alert",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    action = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": "alert-linked-action",
            "origin_kind": "manual",
            "text": "Ask the treating team about the linked alert",
        },
    ).get_json()["item"]
    status = client.get("/api/status").get_json()
    alert = status["alerts"][0]
    request = {
        "mutation_id": "alert-linked-resolve",
        "expected_token": alert["resolve_token"],
        "expected_profile_revision": status["profile_revision"],
        "follow_up_id": action["id"],
    }
    resolved = client.post("/api/alerts/alert-linked/resolve", json=request)
    original = resolved.get_json()
    edited = client.patch(
        f"/api/follow-ups/{action['id']}",
        json={
            "mutation_id": "alert-linked-edit",
            "expected_token": action["token"],
            "owner": "Caregiver",
        },
    )
    replay = client.post("/api/alerts/alert-linked/resolve", json=request)

    assert resolved.status_code == 200
    assert edited.status_code == 200
    assert replay.status_code == 200
    assert _without_replay_marker(replay.get_json()) == original
    assert replay.get_json()["follow_up"]["owner"] is None
    assert replay.get_json()["follow_up"]["token"] != edited.get_json()["item"]["token"]


def test_legacy_alert_request_without_mutation_id_replays_safely(app_client, agent, empty_profile):
    _, client = app_client
    empty_profile["profile_revision"] = 6
    empty_profile["alerts"] = [
        {
            "id": "alert-legacy-client",
            "priority": "medium",
            "message": "Legacy client alert",
            "resolved": False,
            "dependency_kind": "durable",
            "source_dependency_active": True,
            "history": [],
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    request = {
        "expected_token": status["alerts"][0]["resolve_token"],
        "expected_profile_revision": status["profile_revision"],
    }
    fallback_id = (
        f"_internal-alert-resolve-"
        f"{agent.semantic_token(['alert-legacy-client', request['expected_token']])[:32]}"
    )
    reservation = client.post(
        "/api/follow-ups",
        json={
            "mutation_id": fallback_id,
            "origin_kind": "manual",
            "text": "Ask the treating team about the alert",
        },
    )

    first = client.post("/api/alerts/alert-legacy-client/resolve", json=request)
    replay = client.post("/api/alerts/alert-legacy-client/resolve", json=request)
    saved = agent.load_profile()

    assert reservation.status_code == 400
    assert first.status_code == 200
    assert replay.status_code == 200
    assert _without_replay_marker(replay.get_json()) == first.get_json()
    assert saved["profile_revision"] == 7
    assert saved["workflow_revision"] == 1
    assert len(saved["alerts"][0]["history"]) == 1


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
