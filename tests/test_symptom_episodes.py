from __future__ import annotations

import copy
import importlib
import json
import threading

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
    response = client.get("/api/patient/symptom-episodes")
    assert response.status_code == 200
    return response.get_json()


def _create_request(projection, *, mutation_id="symptom-create-001", **overrides):
    request = {
        "mutation_id": mutation_id,
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "symptom_text": "Intermittent nausea",
        "severity_level": "moderate",
        "severity_detail": "Felt stronger after breakfast",
        "reported_subject": "patient",
        "onset_date": "2026-08",
        "timing_text": "Mostly in the morning",
        "frequency_text": "A few times this week",
        "triggers_text": "After breakfast",
        "notes": "Caregiver-entered wording",
    }
    request.update(overrides)
    return request


def _follow_up_request(
    projection,
    episode,
    *,
    mutation_id="episode-follow-up-001",
    **overrides,
):
    request = {
        "mutation_id": mutation_id,
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "expected_episode_token": episode["token"],
        "follow_up": {
            "text": "Ask the treating team about this symptom",
            "owner": "Caregiver",
            "due_date": "2026-09-01",
        },
    }
    request.update(overrides)
    return request


def _seed_action(agent, profile, *, action_id="act_existing", status="open", **overrides):
    action = {
        "id": action_id,
        "origin_snapshot": {
            "kind": "manual",
            "source_id": None,
            "source_job_id": None,
            "source_profile_revision": None,
            "generation_id": None,
            "text": "Ask the treating team about the symptom",
            "snapshot": {"preserve": "origin"},
        },
        "text": "Ask the treating team about the symptom",
        "owner": "Caregiver",
        "due_date": "2026-09-01",
        "status": status,
        "outcome": None,
        "visit_id": None,
        "decision_id": None,
        "alert_id": None,
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
        "completed_at": None,
        "cancelled_at": None,
        "history": [],
        "unknown_extra": {"preserve": True},
        **overrides,
    }
    profile["caregiver_actions"] = [action]
    return action


def _ingest_observation(agent, profile, *, job_id="symptom-import-001"):
    text = "Clinic note dated 2026-08-02. The patient described exact nausea wording."
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-02",
        "summary": "Symptom observation.",
        "symptoms_reported": [
            {
                "symptom": "exact nausea wording",
                "severity": 2,
                "source_quote": "exact nausea wording",
            }
        ],
    }
    before = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        updated, extracted = agent.run_intake(text, profile)
    agent.build_import_record(before, updated, extracted, job_id=job_id, text=text)
    return updated


def test_projection_keeps_observations_separate_and_uses_exact_fixed_safety_copy(
    agent, empty_profile
):
    empty_profile["symptoms"] = [
        {
            "id": "unsafe observation/id with spaces",
            "date": "2026-07",
            "date_precision": "month",
            "date_kind": "legacy_unknown",
            "source_document_date": "2026-07-18",
            "source_document_date_precision": "day",
            "symptom": "Exact legacy wording",
            "severity": 4,
            "note": "Exact note",
            "related_treatment": None,
            "source": "manual",
            "unknown_extra": {"kept": ["yes"]},
        },
        {
            "id": "safe-observation",
            "date": None,
            "date_precision": "unknown",
            "date_kind": "unknown",
            "source_document_date": None,
            "source_document_date_precision": "unknown",
            "symptom": "Duplicate wording",
            "severity": None,
            "source": "ai",
        },
    ]

    projection = agent.project_symptom_episodes(empty_profile)
    serialized = json.dumps(projection)

    assert projection["episode_count"] == 0
    assert projection["observation_count"] == 2
    assert projection["observations"][0]["symptom"] == "Exact legacy wording"
    assert projection["observations"][0]["id"].startswith("symref_")
    assert projection["observations"][1]["id"] == "safe-observation"
    assert "unsafe observation/id with spaces" not in serialized
    assert "unknown_extra" not in serialized
    assert projection["safety_guidance"]["text"] == (
        "NET/Care records what you enter but does not assess urgency or monitor "
        "symptoms. Contact the treating team about symptoms or concerns. If you "
        "think this may be a medical emergency, contact local emergency services."
    )


def test_create_episode_is_explicit_audited_replay_safe_and_revisioned(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    initial = _projection(client)
    request = _create_request(initial)

    first = client.post("/api/symptom-episodes", json=request)
    replay = client.post("/api/symptom-episodes", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert replay.status_code == 200
    first_body = first.get_json()
    replay_body = replay.get_json()
    assert replay_body.pop("idempotent_replay") is True
    assert replay_body == first_body
    assert first_body["profile_revision"] == 1
    assert first_body["workflow_revision"] == 1
    assert first_body["episode"]["status"] == "current"
    assert first_body["episode"]["severity"] == {
        "level": "moderate",
        "detail": "Felt stronger after breakfast",
        "authority": "caregiver_entered_unverified",
    }
    assert first_body["episode"]["onset"] == {
        "value": "2026-08",
        "precision": "month",
        "kind": "caregiver_entered",
    }
    assert saved["symptoms"] == []
    assert len(saved["symptom_episodes"]) == 1
    assert saved["symptom_episodes"][0]["provenance"] == {
        "capture_method": "caregiver_entered",
        "source_verification": "unverified",
    }
    assert len(saved["symptom_episodes"][0]["history"]) == 1


def test_create_rejects_inferred_or_contradictory_episode_authority(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)

    for field, value in (
        ("severity_value", 3),
        ("severity_raw", "three"),
        ("status", "resolved"),
        ("provenance", {"source_verification": "verified"}),
        ("resolved_date", "2026-08-02"),
    ):
        request = _create_request(
            projection,
            mutation_id=f"reject-{field}-authority",
            **{field: value},
        )
        response = client.post("/api/symptom-episodes", json=request)
        assert response.status_code == 400

    relative = _create_request(
        projection,
        mutation_id="reject-relative-date",
        onset_date="last Tuesday",
    )
    invalid_severity = _create_request(
        projection,
        mutation_id="reject-severity-number",
        severity_level=3,
    )
    assert client.post("/api/symptom-episodes", json=relative).status_code == 400
    assert client.post("/api/symptom-episodes", json=invalid_severity).status_code == 400
    assert agent.load_profile()["symptom_episodes"] == []


def test_edit_binds_complete_authority_and_replays_without_another_save(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="edit-create-001"),
    ).get_json()
    projection = _projection(client)
    episode = projection["episodes"][0]
    request = {
        "mutation_id": "edit-episode-001",
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "expected_episode_token": episode["token"],
        "symptom_text": "Exact corrected wording",
        "severity_level": None,
        "onset_date": None,
    }

    first = client.patch(
        f"/api/symptom-episodes/{created['episode']['id']}",
        json=request,
    )
    replay = client.patch(
        f"/api/symptom-episodes/{created['episode']['id']}",
        json=request,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert first.get_json()["episode"]["symptom_text"] == "Exact corrected wording"
    assert first.get_json()["episode"]["severity"]["level"] is None
    assert first.get_json()["episode"]["onset"]["kind"] == "unknown"
    assert first.get_json()["profile_revision"] == projection["profile_revision"] + 1
    saved = agent.load_profile()
    assert len(saved["symptom_episodes"][0]["history"]) == 2

    reused = dict(request)
    reused["symptom_text"] = "Different request with reused mutation ID"
    assert (
        client.patch(
            f"/api/symptom-episodes/{created['episode']['id']}",
            json=reused,
        ).status_code
        == 409
    )

    stale = dict(request)
    stale.update(
        mutation_id="edit-stale-authority",
        symptom_text="Stale update",
    )
    assert (
        client.patch(
            f"/api/symptom-episodes/{created['episode']['id']}",
            json=stale,
        ).status_code
        == 409
    )


def test_replay_rejects_private_or_malformed_snapshot_content(app_client, agent, empty_profile):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)
    request = _create_request(
        projection,
        mutation_id="malformed-replay-snapshot",
    )
    assert client.post("/api/symptom-episodes", json=request).status_code == 201
    saved = agent.load_profile()
    event = saved["symptom_episodes"][0]["history"][0]
    event["result_snapshot"]["episode"]["private_history"] = {"must": "not replay"}
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(saved, clinical_change=False)

    replay = client.post("/api/symptom-episodes", json=request)

    assert replay.status_code == 409
    assert replay.get_json()["code"] == "symptom_conflict"


def test_resolve_is_one_way_with_unknown_date_and_does_not_change_follow_up(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    create = client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="resolve-create-001"),
    ).get_json()
    episode = create["episode"]
    projection = _projection(client)
    request = {
        "mutation_id": "resolve-episode-001",
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "expected_episode_token": episode["token"],
        "resolved_date": None,
    }

    response = client.post(
        f"/api/symptom-episodes/{episode['id']}/resolve",
        json=request,
    )
    replay = client.post(
        f"/api/symptom-episodes/{episode['id']}/resolve",
        json=request,
    )

    assert response.status_code == 200
    assert response.get_json()["episode"]["status"] == "resolved"
    assert response.get_json()["episode"]["resolution"]["value"] is None
    assert response.get_json()["episode"]["resolution"]["kind"] == "unknown"
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    refreshed = _projection(client)
    resolved_episode = refreshed["episodes"][0]
    correction = client.patch(
        f"/api/symptom-episodes/{episode['id']}",
        json={
            "mutation_id": "resolved-correction-001",
            "expected_profile_revision": refreshed["profile_revision"],
            "expected_workflow_revision": refreshed["workflow_revision"],
            "expected_projection_token": refreshed["projection_token"],
            "expected_episode_token": resolved_episode["token"],
            "resolved_date": "2026-08",
            "notes": "Corrected after resolution without reopening",
        },
    )
    assert correction.status_code == 200
    assert correction.get_json()["episode"]["status"] == "resolved"
    assert correction.get_json()["episode"]["resolution"]["precision"] == "month"
    refreshed = _projection(client)
    second = dict(request)
    second.update(
        mutation_id="resolve-episode-002",
        expected_profile_revision=refreshed["profile_revision"],
        expected_workflow_revision=refreshed["workflow_revision"],
        expected_projection_token=refreshed["projection_token"],
        expected_episode_token=refreshed["episodes"][0]["token"],
    )
    assert (
        client.post(
            f"/api/symptom-episodes/{episode['id']}/resolve",
            json=second,
        ).status_code
        == 409
    )


def test_atomic_inline_follow_up_create_replay_and_save_failure(
    app_client, agent, empty_profile, monkeypatch
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)
    request = _create_request(
        projection,
        mutation_id="inline-follow-up-001",
        follow_up={
            "text": "Contact the treating team about this symptom",
            "owner": "Caregiver",
            "due_date": "2026-09-01",
        },
    )
    first = client.post("/api/symptom-episodes", json=request)
    replay = client.post("/api/symptom-episodes", json=request)
    saved = agent.load_profile()

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert len(saved["caregiver_actions"]) == 1
    assert len(saved["symptom_episodes"]) == 1
    assert (
        saved["symptom_episodes"][0]["caregiver_action_id"] == saved["caregiver_actions"][0]["id"]
    )
    assert saved["caregiver_actions"][0]["origin_snapshot"]["kind"] == "manual"
    assert saved["caregiver_actions"][0]["history"][0]["target"] == (
        f"caregiver_action:{saved['caregiver_actions'][0]['id']}"
    )
    action_update = client.patch(
        f"/api/follow-ups/{saved['caregiver_actions'][0]['id']}",
        json={
            "mutation_id": "episode-action-progress",
            "expected_token": first.get_json()["follow_up"]["token"],
            "status": "in_progress",
        },
    )
    assert action_update.status_code == 200
    assert agent.load_profile()["symptom_episodes"][0]["status"] == "current"
    projection = _projection(client)
    episode = projection["episodes"][0]
    resolved = client.post(
        f"/api/symptom-episodes/{episode['id']}/resolve",
        json={
            "mutation_id": "inline-episode-resolve",
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_episode_token": episode["token"],
            "resolved_date": None,
        },
    )
    assert resolved.status_code == 200
    saved = agent.load_profile()
    assert saved["caregiver_actions"][0]["status"] == "in_progress"

    before = copy.deepcopy(saved)
    fresh_projection = _projection(client)
    failed_request = _create_request(
        fresh_projection,
        mutation_id="inline-follow-up-fail",
        symptom_text="A second symptom",
        follow_up={"text": "Ask the treating team about the second symptom"},
    )

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated symptom save failure")

    monkeypatch.setattr(app_module.agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated symptom save failure"):
        client.post("/api/symptom-episodes", json=failed_request)
    assert agent.load_profile() == before


def test_existing_action_link_preserves_cross_domain_provenance_and_is_unique(
    app_client, agent, empty_profile
):
    _, client = app_client
    action = _seed_action(agent, empty_profile)
    original_action = copy.deepcopy(action)
    agent.save_profile(empty_profile, clinical_change=False)
    projection = _projection(client)
    eligible = projection["eligible_actions"][0]
    request = _create_request(
        projection,
        mutation_id="existing-action-link-001",
        caregiver_action_id=eligible["id"],
        expected_action_token=eligible["token"],
    )

    response = client.post("/api/symptom-episodes", json=request)
    assert response.status_code == 201
    saved = agent.load_profile()
    assert saved["caregiver_actions"][0] == original_action
    assert saved["symptom_episodes"][0]["caregiver_action_id"] == action["id"]

    refreshed = _projection(client)
    duplicate = _create_request(
        refreshed,
        mutation_id="existing-action-link-002",
        symptom_text="Another occurrence",
        caregiver_action_id=action["id"],
        expected_action_token=eligible["token"],
    )
    assert client.post("/api/symptom-episodes", json=duplicate).status_code == 409
    assert len(agent.load_profile()["symptom_episodes"]) == 1


def test_link_and_unlink_are_workflow_only_and_allow_resolved_episode(
    app_client, agent, empty_profile
):
    _, client = app_client
    _seed_action(agent, empty_profile)
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="link-create-001"),
    ).get_json()
    projection = _projection(client)
    current_episode = projection["episodes"][0]
    resolved = client.post(
        f"/api/symptom-episodes/{created['episode']['id']}/resolve",
        json={
            "mutation_id": "link-resolve-001",
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_episode_token": current_episode["token"],
            "resolved_date": "2026-08-31",
        },
    )
    assert resolved.status_code == 200
    projection = _projection(client)
    episode = projection["episodes"][0]
    assert episode["status"] == "resolved"
    action = projection["eligible_actions"][0]
    profile_revision = projection["profile_revision"]
    link_request = {
        "mutation_id": "link-existing-action-001",
        "expected_profile_revision": profile_revision,
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "expected_episode_token": episode["token"],
        "caregiver_action_id": action["id"],
        "expected_action_token": action["token"],
    }
    linked = client.patch(
        f"/api/symptom-episodes/{created['episode']['id']}/follow-up",
        json=link_request,
    )
    assert linked.status_code == 200
    assert linked.get_json()["profile_revision"] == profile_revision
    assert linked.get_json()["workflow_revision"] == projection["workflow_revision"] + 1

    projection = _projection(client)
    episode = projection["episodes"][0]
    linked_action = episode["follow_up"]
    unlink_request = {
        "mutation_id": "unlink-existing-action-001",
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": projection["projection_token"],
        "expected_episode_token": episode["token"],
        "caregiver_action_id": None,
        "expected_action_token": linked_action["token"],
    }
    unlinked = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=unlink_request,
    )
    assert unlinked.status_code == 200
    assert unlinked.get_json()["profile_revision"] == profile_revision
    assert unlinked.get_json()["episode"]["follow_up"] is None


@pytest.mark.parametrize("episode_status", ["current", "resolved"])
def test_existing_episode_inline_follow_up_is_atomic_replay_safe_and_workflow_only(
    app_client, agent, empty_profile, monkeypatch, episode_status
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/symptom-episodes",
        json=_create_request(
            _projection(client),
            mutation_id=f"inline-patch-create-{episode_status}",
        ),
    ).get_json()
    if episode_status == "resolved":
        projection = _projection(client)
        client.post(
            f"/api/symptom-episodes/{created['episode']['id']}/resolve",
            json={
                "mutation_id": "inline-patch-resolve",
                "expected_profile_revision": projection["profile_revision"],
                "expected_workflow_revision": projection["workflow_revision"],
                "expected_projection_token": projection["projection_token"],
                "expected_episode_token": projection["episodes"][0]["token"],
                "resolved_date": None,
            },
        )

    projection = _projection(client)
    episode = projection["episodes"][0]
    request = _follow_up_request(
        projection,
        episode,
        mutation_id=f"inline-patch-{episode_status}",
    )
    original_save = app_module.agent.save_profile
    save_count = 0

    def counting_save(*args, **kwargs):
        nonlocal save_count
        save_count += 1
        return original_save(*args, **kwargs)

    monkeypatch.setattr(app_module.agent, "save_profile", counting_save)
    first = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=request,
    )
    replay = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=request,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    first_body = first.get_json()
    replay_body = replay.get_json()
    assert replay_body.pop("idempotent_replay") is True
    assert replay_body == first_body
    assert save_count == 1
    assert first_body["profile_revision"] == projection["profile_revision"]
    assert first_body["workflow_revision"] == projection["workflow_revision"] + 1
    assert first_body["episode"]["status"] == episode_status

    saved = agent.load_profile()
    assert len(saved["caregiver_actions"]) == 1
    action = saved["caregiver_actions"][0]
    stored_episode = saved["symptom_episodes"][0]
    assert stored_episode["caregiver_action_id"] == action["id"]
    assert action["origin_snapshot"] == {
        "kind": "manual",
        "source_id": None,
        "source_job_id": None,
        "source_profile_revision": None,
        "generation_id": None,
        "text": request["follow_up"]["text"],
        "snapshot": {},
    }
    assert action["owner"] == "Caregiver"
    assert action["due_date"] == "2026-09-01"
    assert action["status"] == "open"
    assert action["visit_id"] is None
    assert action["decision_id"] is None
    assert action["alert_id"] is None
    assert action["history"][0]["target"] == f"caregiver_action:{action['id']}"
    assert stored_episode["history"][-1]["target"] == f"symptom_episode:{episode['id']}"
    assert stored_episode["history"][-1]["operation"] == "follow_up_created_and_linked"

    refreshed = _projection(client)
    assert refreshed["episodes"][0]["follow_up"] == first_body["follow_up"]
    changed = copy.deepcopy(request)
    changed["follow_up"]["owner"] = "Another caregiver"
    conflict = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=changed,
    )
    assert conflict.status_code == 409
    assert save_count == 1
    assert len(agent.load_profile()["caregiver_actions"]) == 1


def test_existing_episode_inline_follow_up_rejects_ambiguous_or_stale_authority(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    created = client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="inline-reject-create"),
    ).get_json()
    projection = _projection(client)
    episode = projection["episodes"][0]
    valid = _follow_up_request(projection, episode, mutation_id="inline-reject-valid")
    before = agent.load_profile()
    invalid_requests = []

    no_operation = {key: value for key, value in valid.items() if key != "follow_up"}
    invalid_requests.append(no_operation)
    invalid_requests.append(
        {
            **valid,
            "caregiver_action_id": "act_client_supplied",
            "expected_action_token": "client-token",
        }
    )
    invalid_requests.append({**valid, "expected_action_token": "client-token"})
    invalid_requests.append({**valid, "follow_up": None})
    invalid_requests.append({**valid, "follow_up": {}})
    invalid_requests.append({**valid, "follow_up": {"text": "A" * 1001}})
    invalid_requests.append(
        {
            **valid,
            "follow_up": {
                "text": "Ask the treating team about this symptom",
                "owner": "A" * 101,
            },
        }
    )
    invalid_requests.append(
        {
            **valid,
            "follow_up": {
                "text": "Ask the treating team about this symptom",
                "due_date": "next week",
            },
        }
    )
    for forbidden in ("id", "token", "status", "history", "provenance"):
        invalid_requests.append(
            {
                **valid,
                "follow_up": {
                    "text": "Ask the treating team about this symptom",
                    forbidden: "client authority",
                },
            }
        )
    invalid_requests.append({**valid, "status": "open"})
    for required in (
        "expected_profile_revision",
        "expected_workflow_revision",
        "expected_projection_token",
        "expected_episode_token",
    ):
        invalid_requests.append({key: value for key, value in valid.items() if key != required})

    for request in invalid_requests:
        response = client.patch(
            f"/api/symptom-episodes/{created['episode']['id']}/follow-up",
            json=request,
        )
        assert response.status_code == 400
        assert agent.load_profile() == before

    stale_requests = [
        {**valid, "expected_profile_revision": projection["profile_revision"] + 1},
        {**valid, "expected_workflow_revision": projection["workflow_revision"] + 1},
        {**valid, "expected_projection_token": projection["projection_token"] + "stale"},
        {**valid, "expected_episode_token": episode["token"] + "stale"},
    ]
    for request in stale_requests:
        response = client.patch(
            f"/api/symptom-episodes/{created['episode']['id']}/follow-up",
            json=request,
        )
        assert response.status_code == 409
        assert agent.load_profile() == before


def test_existing_episode_inline_follow_up_capacity_and_save_failure_are_atomic(
    app_client, agent, empty_profile, monkeypatch
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="inline-atomic-create"),
    )
    projection = _projection(client)
    episode = projection["episodes"][0]
    request = _follow_up_request(
        projection,
        episode,
        mutation_id="inline-save-failure",
    )
    before = agent.load_profile()

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated inline follow-up save failure")

    monkeypatch.setattr(app_module.agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated inline follow-up save failure"):
        client.patch(
            f"/api/symptom-episodes/{episode['id']}/follow-up",
            json=request,
        )
    assert agent.load_profile() == before

    monkeypatch.undo()
    full = agent.load_profile()
    prototype = _seed_action(agent, full, action_id="act_capacity_000")
    full["caregiver_actions"] = [
        {**copy.deepcopy(prototype), "id": f"act_capacity_{index:03d}"}
        for index in range(agent.MAX_SYMPTOM_ACTIONS)
    ]
    agent.save_profile(full, clinical_change=False)
    projection = _projection(client)
    response = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=_follow_up_request(
            projection,
            projection["episodes"][0],
            mutation_id="inline-capacity-limit",
        ),
    )
    assert response.status_code == 422
    saved = agent.load_profile()
    assert len(saved["caregiver_actions"]) == agent.MAX_SYMPTOM_ACTIONS
    assert saved["symptom_episodes"][0]["caregiver_action_id"] is None


def test_existing_episode_inline_follow_up_serializes_concurrent_intents(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="inline-concurrent-create"),
    )
    projection = _projection(client)
    episode = projection["episodes"][0]
    barrier = threading.Barrier(2)
    responses = []

    def create_follow_up(index):
        with app_module.app.test_client() as thread_client:
            barrier.wait()
            responses.append(
                thread_client.patch(
                    f"/api/symptom-episodes/{episode['id']}/follow-up",
                    json=_follow_up_request(
                        projection,
                        episode,
                        mutation_id=f"inline-concurrent-{index}",
                        follow_up={"text": f"Ask the treating team about symptom intent {index}"},
                    ),
                )
            )

    threads = [threading.Thread(target=create_follow_up, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert sorted(response.status_code for response in responses) == [200, 409]
    saved = agent.load_profile()
    assert len(saved["caregiver_actions"]) == 1
    assert (
        saved["symptom_episodes"][0]["caregiver_action_id"] == (saved["caregiver_actions"][0]["id"])
    )
    assert saved["workflow_revision"] == projection["workflow_revision"] + 1


def test_inline_follow_up_unlink_relink_and_lifecycle_remain_independent(
    app_client, agent, empty_profile
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    client.post(
        "/api/symptom-episodes",
        json=_create_request(_projection(client), mutation_id="inline-compat-create"),
    )
    projection = _projection(client)
    episode = projection["episodes"][0]
    inline_request = _follow_up_request(
        projection,
        episode,
        mutation_id="inline-compat-link",
    )
    linked = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=inline_request,
    )
    assert linked.status_code == 200

    old_projection_token = projection["projection_token"]
    projection = _projection(client)
    episode = projection["episodes"][0]
    action = episode["follow_up"]
    unlink = {
        "mutation_id": "inline-compat-unlink",
        "expected_profile_revision": projection["profile_revision"],
        "expected_workflow_revision": projection["workflow_revision"],
        "expected_projection_token": old_projection_token,
        "expected_episode_token": episode["token"],
        "caregiver_action_id": None,
        "expected_action_token": action["token"],
    }
    assert (
        client.patch(
            f"/api/symptom-episodes/{episode['id']}/follow-up",
            json=unlink,
        ).status_code
        == 409
    )
    unlink["expected_projection_token"] = projection["projection_token"]
    assert (
        client.patch(
            f"/api/symptom-episodes/{episode['id']}/follow-up",
            json=unlink,
        ).status_code
        == 200
    )
    replay_after_unlink = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json=inline_request,
    )
    assert replay_after_unlink.status_code == 200
    replay_body = replay_after_unlink.get_json()
    assert replay_body.pop("idempotent_replay") is True
    assert replay_body == linked.get_json()

    projection = _projection(client)
    episode = projection["episodes"][0]
    eligible = next(item for item in projection["eligible_actions"] if item["id"] == action["id"])
    relink = client.patch(
        f"/api/symptom-episodes/{episode['id']}/follow-up",
        json={
            "mutation_id": "inline-compat-relink",
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_episode_token": episode["token"],
            "caregiver_action_id": eligible["id"],
            "expected_action_token": eligible["token"],
        },
    )
    assert relink.status_code == 200
    action_update = client.patch(
        f"/api/follow-ups/{action['id']}",
        json={
            "mutation_id": "inline-compat-complete",
            "expected_token": relink.get_json()["follow_up"]["token"],
            "status": "completed",
            "outcome": {
                "kind": "administrative",
                "text": "Confirmed the follow-up was completed",
            },
        },
    )
    assert action_update.status_code == 200
    assert agent.load_profile()["symptom_episodes"][0]["status"] == "current"

    projection = _projection(client)
    episode = projection["episodes"][0]
    resolved = client.post(
        f"/api/symptom-episodes/{episode['id']}/resolve",
        json={
            "mutation_id": "inline-compat-resolve",
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_episode_token": episode["token"],
            "resolved_date": None,
        },
    )
    assert resolved.status_code == 200
    saved = agent.load_profile()
    assert saved["caregiver_actions"][0]["status"] == "completed"
    assert saved["symptom_episodes"][0]["caregiver_action_id"] == action["id"]


def test_projection_fails_whole_read_on_duplicate_link_or_private_history_overflow(
    agent, empty_profile
):
    action = _seed_action(agent, empty_profile)
    base_episode = {
        "id": "syme_" + "1" * 32,
        "status": "current",
        "symptom_text": "Nausea",
        "severity_level": None,
        "severity_detail": None,
        "reported_subject": "unspecified",
        "timing_text": None,
        "frequency_text": None,
        "triggers_text": None,
        "notes": None,
        "onset_date": None,
        "onset_date_precision": "unknown",
        "onset_date_kind": "unknown",
        "resolved_date": None,
        "resolved_date_precision": "unknown",
        "resolved_date_kind": "unknown",
        "provenance": agent.symptom_episode_provenance(),
        "caregiver_action_id": action["id"],
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
        "resolved_at": None,
        "history": [],
    }
    empty_profile["symptom_episodes"] = [
        base_episode,
        {**copy.deepcopy(base_episode), "id": "syme_" + "2" * 32},
    ]
    before = copy.deepcopy(empty_profile)

    with pytest.raises(agent.SymptomProjectionError):
        agent.project_symptom_episodes(empty_profile)
    assert empty_profile == before

    empty_profile["symptom_episodes"] = [copy.deepcopy(base_episode)]
    empty_profile["symptom_episodes"][0]["caregiver_action_id"] = None
    nested = {}
    cursor = nested
    for _ in range(14):
        cursor["next"] = {}
        cursor = cursor["next"]
    empty_profile["symptom_episodes"][0]["history"] = [nested]
    with pytest.raises(agent.SymptomProjectionError):
        agent.project_symptom_episodes(empty_profile)

    empty_profile["symptom_episodes"][0]["history"] = []
    empty_profile["caregiver_actions"][0]["owner"] = {"malformed": "nested value"}
    with pytest.raises(agent.SymptomProjectionError):
        agent.project_symptom_episodes(empty_profile)


def test_observation_projection_source_routes_and_reconciliation_isolate_episodes(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    profile = _ingest_observation(agent, empty_profile)
    profile["symptoms"][0]["unknown_extra"] = {"preserve": ["through correction"]}
    symptom_change = next(
        change
        for change in profile["document_imports"][0]["changes"]
        if change.get("target", {}).get("collection") == "symptoms"
    )
    symptom_change["effective_value"]["unknown_extra"] = {"preserve": ["through correction"]}
    profile["symptom_episodes"] = [
        {
            "id": "syme_" + "3" * 32,
            "status": "current",
            "symptom_text": "Caregiver episode remains separate",
            "severity_level": None,
            "severity_detail": None,
            "reported_subject": "unspecified",
            "timing_text": None,
            "frequency_text": None,
            "triggers_text": None,
            "notes": None,
            "onset_date": None,
            "onset_date_precision": "unknown",
            "onset_date_kind": "unknown",
            "resolved_date": None,
            "resolved_date_precision": "unknown",
            "resolved_date_kind": "unknown",
            "provenance": agent.symptom_episode_provenance(),
            "caregiver_action_id": None,
            "created_at": "2026-08-02T10:00:00",
            "updated_at": "2026-08-02T10:00:00",
            "resolved_at": None,
            "history": [],
            "unknown_extra": {"preserve": True},
        }
    ]
    original_episode = copy.deepcopy(profile["symptom_episodes"][0])
    module = importlib.import_module("agent.symptom_episodes")
    original_validate = module.validate_source_artifact
    validations = []

    def counted_validate(source, artifact, content):
        validations.append((source["id"], artifact))
        return original_validate(source, artifact, content)

    monkeypatch.setattr(module, "validate_source_artifact", counted_validate)
    projection = agent.project_symptom_episodes(profile)
    record = projection["observations"][0]
    serialized = json.dumps(projection)

    assert validations == [(profile["source_documents"][0]["id"], "text")]
    assert record["date"]["value"] is None
    assert record["date"]["kind"] == "unknown"
    assert record["date"]["source_document_date"] == "2026-08-02"
    assert record["provenance"]["source_url"].startswith(
        "/api/patient/symptom-episodes/observations/symref_"
    )
    for forbidden in (
        profile["source_documents"][0]["id"],
        "evidence_start",
        "evidence_end",
        "source_quote",
        "document_imports",
        '"path"',
        "?start=",
    ):
        assert forbidden not in serialized

    agent.save_profile(profile, clinical_change=False)
    source = client.get(record["provenance"]["source_url"])
    evidence = client.get(record["provenance"]["evidence_url"])
    assert source.status_code == evidence.status_code == 200
    assert "no-store" in source.headers["Cache-Control"]
    assert evidence.get_data(as_text=True) == "exact nausea wording"

    receipt = agent.public_receipt(profile, "symptom-import-001")
    change = next(item for item in receipt["changes"] if item["category"] == "symptoms")
    agent.correct_change(
        profile,
        "symptom-import-001",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
        replacement={
            "date": "2026-08",
            "date_kind": "clinical",
            "note": "Caregiver correction",
        },
    )
    assert profile["symptom_episodes"][0] == original_episode
    corrected = agent.project_symptom_episodes(profile)
    assert corrected["observations"][0]["date"]["precision"] == "month"
    assert corrected["observations"][0]["provenance"]["status"] == (
        "caregiver_corrected_unverified"
    )
    assert corrected["observations"][0]["provenance"]["evidence_url"] is None
    assert profile["symptoms"][0]["unknown_extra"] == {"preserve": ["through correction"]}

    refreshed = agent.public_receipt(profile, "symptom-import-001")
    agent.undo_import(
        profile,
        "symptom-import-001",
        receipt_revision=refreshed["receipt_revision"],
        undo_token=refreshed["undo_token"],
    )
    assert profile["symptom_episodes"][0] == original_episode
    assert agent.project_symptom_episodes(profile)["observations"] == []


def test_episode_routes_require_hosted_identity_and_are_no_store(
    app_client, agent, empty_profile, monkeypatch
):
    _, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()
    response = client.get("/api/patient/symptom-episodes")
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert agent.PROFILE_PATH.read_bytes() == before

    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    assert client.get("/api/patient/symptom-episodes").status_code == 401
    assert client.get("/api/patient/symptom-episodes/observations/opaque/source").status_code == 401
    assert client.post("/api/symptom-episodes", json={}).status_code == 401


def test_projection_endpoint_returns_bounded_non_phi_422(app_client, empty_profile, monkeypatch):
    app_module, client = app_client
    private_text = "PRIVATE SYMPTOM WORDING MUST NOT LEAK"
    empty_profile["symptoms"] = [
        {
            "id": "duplicate",
            "date": None,
            "date_precision": "unknown",
            "date_kind": "unknown",
            "source_document_date": None,
            "source_document_date_precision": "unknown",
            "symptom": private_text,
        },
        {
            "id": "duplicate",
            "date": None,
            "date_precision": "unknown",
            "date_kind": "unknown",
            "source_document_date": None,
            "source_document_date_precision": "unknown",
            "symptom": private_text,
        },
    ]
    monkeypatch.setattr(app_module.agent, "load_profile", lambda: empty_profile)

    response = client.get("/api/patient/symptom-episodes")

    assert response.status_code == 422
    body = json.dumps(response.get_json())
    assert response.get_json()["code"] == "symptom_projection_invalid"
    assert private_text not in body
    assert len(body) < 300


def test_episode_text_never_enters_legacy_patient_summary(agent, empty_profile):
    empty_profile["symptoms"] = [
        {
            "date": "2026-08-01",
            "symptom": "Legacy observation remains in model context",
            "severity": 2,
            "source": "manual",
        }
    ]
    empty_profile["symptom_episodes"] = [
        {
            "id": "syme_private",
            "status": "current",
            "symptom_text": "EPISODE MUST NOT ENTER MODEL CONTEXT",
        }
    ]

    summary = agent.get_patient_summary(empty_profile)

    assert "Legacy observation remains in model context" in summary
    assert "EPISODE MUST NOT ENTER MODEL CONTEXT" not in summary


def test_episode_text_is_excluded_from_chat_orchestrator_questions_and_summary_prompts(
    agent, empty_profile
):
    marker = "EPISODE_PRIVATE_PROMPT_MARKER"
    empty_profile["symptoms"] = [
        {
            "date": "2026-08-01",
            "symptom": "Legacy symptom prompt wording",
            "severity": 2,
            "source": "manual",
        }
    ]
    empty_profile["symptom_episodes"] = [
        {
            "id": "syme_prompt",
            "status": "current",
            "symptom_text": marker,
            "notes": marker,
        }
    ]
    without_episodes = copy.deepcopy(empty_profile)
    without_episodes["symptom_episodes"] = []
    assert agent.get_patient_summary(empty_profile) == agent.get_patient_summary(without_episodes)
    assert agent.build_chat_system(empty_profile) == agent.build_chat_system(without_episodes)

    captured = []

    def summary_handler(**kwargs):
        captured.append(json.dumps(kwargs, default=str))
        return llm_text(
            json.dumps(
                {
                    "overall_status": "insufficient_data",
                    "timeline": [],
                    "next_actions": [],
                }
            )
        )

    with patch_llm(agent, summary_handler):
        agent.generate_executive_summary(empty_profile)

    def questions_handler(**kwargs):
        captured.append(json.dumps(kwargs, default=str))
        return llm_text("[]")

    with patch_llm(agent, questions_handler):
        agent.generate_questions_for_profile(empty_profile)

    def orchestrator_handler(**kwargs):
        captured.append(json.dumps(kwargs, default=str))
        return llm_text("No research action.")

    with patch_llm(agent, orchestrator_handler):
        agent.run_orchestrator(empty_profile, {})

    assert len(captured) >= 3
    assert all(marker not in prompt for prompt in captured)
    assert all("Legacy symptom prompt wording" in prompt for prompt in captured)
