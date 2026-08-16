from __future__ import annotations

import copy
import importlib
import json

import pytest


@pytest.fixture
def app_client(agent):
    app_module = importlib.import_module("app")
    app_module.app.config.update(TESTING=True)
    return app_module, app_module.app.test_client()


def _trial(agent, **overrides):
    return {
        "research_record_id": agent.new_research_record_id("trial"),
        "nct_id": "NCT12345678",
        "title": "Exact registry title",
        "status": "RECRUITING",
        "phase": "PHASE2",
        "phases": ["PHASE2"],
        "countries": ["Sweden"],
        "url": "https://evil.example/redirect?patient=private#fragment",
        "brief_summary": "Exact registry summary",
        "eligibility_excerpt": "Complete exact registry criteria",
        "registry_last_update": "2026-08-01",
        "date_added": "2026-08-02T09:00:00",
        "eligibility_notes": "Machine-generated compatibility context",
        "unknown_private": {"tool_payload": "preserve but do not expose"},
        **overrides,
    }


def _paper(agent, **overrides):
    return {
        "research_record_id": agent.new_research_record_id("paper"),
        "pmid": "12345678",
        "title": "Exact paper title",
        "authors": "A Author; B Author",
        "journal": "Journal",
        "date": "2026",
        "url": "javascript:alert(1)",
        "query": "exact source query",
        "date_added": "2026-08-02T09:00:00",
        "relevance_notes": "Machine-generated compatibility context",
        **overrides,
    }


def _seed_profile(agent, empty_profile):
    trial = _trial(agent)
    paper = _paper(agent)
    empty_profile["trials_tracked"] = [trial]
    empty_profile["literature_watched"] = [paper]
    empty_profile["latest_research_update"] = {
        "job_id": "job_exact",
        "updated_at": "2026-08-02T10:00:00",
        "source": "feed",
        "trial_ids": [trial["nct_id"]],
        "paper_ids": [paper["pmid"]],
    }
    agent.save_profile(empty_profile, clinical_change=False)
    return trial, paper


def _workspace(client):
    response = client.get("/api/patient/research-workspace")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _meta(workspace, mutation_id):
    return {
        "mutation_id": mutation_id,
        "expected_profile_revision": workspace["profile_revision"],
        "expected_workflow_revision": workspace["workflow_revision"],
        "expected_projection_token": workspace["projection_token"],
    }


def _create(client, workspace, item_index=0, mutation_id="research-create-001"):
    item = workspace["items"][item_index]
    return client.post(
        "/api/research-considerations",
        json={
            **_meta(workspace, mutation_id),
            "research_record_id": item["id"],
            "expected_item_token": item["token"],
        },
    )


def test_v14_migration_preserves_rows_and_assigns_reorder_stable_multiset():
    from agent.migrations import apply_migrations

    distinct_a = {"nct_id": "NCT12345678", "title": "A", "unknown": {"x": 1}}
    distinct_b = {"nct_id": "NCT12345678", "title": "B", "unknown": {"x": 2}}
    identical = {"pmid": "12345", "title": "Same", "unknown": ["exact"]}
    source = {
        "schema_version": 13,
        "profile_revision": 8,
        "workflow_revision": 3,
        "trials_tracked": [copy.deepcopy(distinct_a), copy.deepcopy(distinct_b)],
        "literature_watched": [copy.deepcopy(identical), copy.deepcopy(identical)],
        "latest_research_update": {"trial_ids": ["NCT12345678"], "paper_ids": ["12345"]},
        "unknown_top": {"keep": True},
    }
    first = apply_migrations(copy.deepcopy(source))
    reordered = copy.deepcopy(source)
    reordered["trials_tracked"].reverse()
    second = apply_migrations(reordered)

    assert first["schema_version"] == 16
    assert first["profile_revision"] == 8
    assert first["workflow_revision"] == 3
    assert first["research_considerations"] == []
    assert first["unknown_top"] == source["unknown_top"]
    assert [
        {key: value for key, value in row.items() if key != "research_record_id"}
        for row in first["trials_tracked"]
    ] == source["trials_tracked"]
    first_by_title = {row["title"]: row["research_record_id"] for row in first["trials_tracked"]}
    second_by_title = {row["title"]: row["research_record_id"] for row in second["trials_tracked"]}
    assert first_by_title == second_by_title
    assert {row["research_record_id"] for row in first["literature_watched"]} == {
        row["research_record_id"] for row in second["literature_watched"]
    }


def test_existing_malformed_ids_remain_loadable_but_projection_fails(
    agent, empty_profile, app_client
):
    _, client = app_client
    empty_profile["trials_tracked"] = [
        {"research_record_id": "bad", "nct_id": "NCT12345678"},
        {"research_record_id": "bad", "nct_id": "NCT87654321"},
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    loaded = agent.load_profile()
    assert [row["research_record_id"] for row in loaded["trials_tracked"]] == ["bad", "bad"]
    response = client.get("/api/patient/research-workspace")
    assert response.status_code == 422
    assert response.get_json() == {
        "code": "research_projection_invalid",
        "error": "Research occurrence identity is missing or inconsistent.",
    }
    assert agent.load_profile()["trials_tracked"] == loaded["trials_tracked"]


def test_projection_separates_authority_uses_canonical_links_and_exact_safety_copy(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)

    workspace = _workspace(client)
    trial, paper = workspace["items"]
    assert trial["external_url"] == "https://clinicaltrials.gov/study/NCT12345678"
    assert paper["external_url"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert "url" not in trial["external_facts"]
    assert "unknown_private" not in json.dumps(workspace)
    assert (
        agent.load_profile()["trials_tracked"][0]["url"]
        == "https://evil.example/redirect?patient=private#fragment"
    )
    assert trial["generated_context"] == {
        "eligibility_notes": "Machine-generated compatibility context"
    }
    assert trial["latest_batch_member"] is True
    assert paper["latest_batch_member"] is True
    # Reworded copy: wave 3 reworded the three byte-pinned safety paragraphs into plain
    # English. INVARIANTS.md and every pin moved in the same commit; the
    # meaning is unchanged and tests/test_plain_language_copy.py asserts each
    # promise the paragraph makes, not just its bytes.
    assert workspace["safety_guidance"]["text"] == (
        "NET/Care records the research you choose to follow. It does not decide whether "
        "research is relevant, whether someone is eligible for or enrolled in a study, "
        "or whether a treatment is suitable. Confirm clinical questions with the "
        "treating team and trial details with the study site."
    )
    response = client.get("/api/patient/research-workspace")
    assert "no-store" in response.headers["Cache-Control"]


def test_invalid_external_ids_remain_visible_without_links_or_shortlist(
    agent, empty_profile, app_client
):
    _, client = app_client
    empty_profile["trials_tracked"] = [_trial(agent, nct_id="nct12345678")]
    empty_profile["literature_watched"] = [_paper(agent, pmid="001234")]
    agent.save_profile(empty_profile, clinical_change=False)

    workspace = _workspace(client)
    assert all(item["external_url"] is None for item in workspace["items"])
    assert all(item["shortlist"]["eligible"] is False for item in workspace["items"])
    assert {item["shortlist"]["reason"] for item in workspace["items"]} == {
        "missing_or_invalid_source_id"
    }


def test_snapshot_is_immutable_and_current_state_is_section_specific(
    agent, empty_profile, app_client
):
    _, client = app_client
    trial, _ = _seed_profile(agent, empty_profile)
    created = _create(client, _workspace(client))
    assert created.status_code == 201
    original = created.get_json()["consideration"]["snapshot"]

    profile = agent.load_profile()
    profile["trials_tracked"][0]["eligibility_notes"] = "Different generated context only"
    agent.save_profile(profile, clinical_change=True)
    consideration = _workspace(client)["considerations"][0]

    assert consideration["snapshot"] == original
    assert consideration["current_state"] == {
        "occurrence": "present",
        "external_facts": "unchanged",
        "generated_context": "changed",
        "discovery_provenance": "unchanged",
    }
    profile = agent.load_profile()
    profile["trials_tracked"] = [_trial(agent, nct_id=trial["nct_id"], title=trial["title"])]
    agent.save_profile(profile, clinical_change=True)
    missing = _workspace(client)["considerations"][0]
    assert missing["current_state"]["occurrence"] == "missing"
    assert missing["snapshot"] == original


def test_lifecycle_events_attribution_and_latest_batch_are_independent(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    created = _create(client, _workspace(client)).get_json()["consideration"]
    baseline_latest = copy.deepcopy(agent.load_profile()["latest_research_update"])

    workspace = _workspace(client)
    event = client.post(
        f"/api/research-considerations/{created['id']}/events",
        json={
            **_meta(workspace, "research-event-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
            "event_type": "treating_team_communication",
            "note": "Exact caregiver-entered wording",
            "who": "Dr Example",
            "context": "Clinic discussion",
            "occurred_on": "2026-08",
        },
    )
    assert event.status_code == 201
    recorded = event.get_json()["consideration"]["events"][0]
    assert recorded["occurred_on"] == "2026-08"
    assert recorded["occurred_on_precision"] == "month"
    assert recorded["provenance"]["label"] == (
        "Caregiver-entered · attributed to clinician · unverified"
    )

    workspace = _workspace(client)
    closed = client.post(
        f"/api/research-considerations/{created['id']}/close",
        json={
            **_meta(workspace, "research-close-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
        },
    )
    assert closed.status_code == 200
    assert closed.get_json()["consideration"]["status"] == "closed"
    workspace = _workspace(client)
    resumed = client.post(
        f"/api/research-considerations/{created['id']}/resume",
        json={
            **_meta(workspace, "research-resume-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
        },
    )
    assert resumed.status_code == 200
    result = resumed.get_json()["consideration"]
    assert result["status"] == "open"
    assert [entry["operation"] for entry in result["history"]] == [
        "created",
        "event_recorded",
        "closed",
        "resumed",
    ]
    persisted = agent.load_profile()
    assert persisted["latest_research_update"] == baseline_latest
    assert persisted["profile_revision"] == 0
    assert persisted["workflow_revision"] == 4


def test_trial_site_event_is_rejected_for_paper_without_save(agent, empty_profile, app_client):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    created = _create(client, _workspace(client), item_index=1).get_json()["consideration"]
    before = agent.PROFILE_PATH.read_bytes()
    workspace = _workspace(client)
    response = client.post(
        f"/api/research-considerations/{created['id']}/events",
        json={
            **_meta(workspace, "paper-site-event-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
            "event_type": "trial_site_communication",
            "note": "Should not be accepted",
        },
    )
    assert response.status_code == 400
    assert agent.PROFILE_PATH.read_bytes() == before


def test_inline_follow_up_is_atomic_replay_safe_and_permanently_prompt_excluded(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    created = _create(client, _workspace(client)).get_json()["consideration"]
    workspace = _workspace(client)
    request = {
        **_meta(workspace, "research-action-001"),
        "expected_consideration_token": workspace["considerations"][0]["token"],
        "follow_up": {
            "text": "Ask the treating team about this research item",
            "owner": "Caregiver",
            "due_date": "2026-09-01",
        },
    }
    first = client.patch(f"/api/research-considerations/{created['id']}/follow-up", json=request)
    assert first.status_code == 200
    action = agent.load_profile()["caregiver_actions"][0]
    assert action["origin_snapshot"]["kind"] == "research_consideration"
    assert "unknown_private" not in json.dumps(action["origin_snapshot"])

    replay = client.patch(f"/api/research-considerations/{created['id']}/follow-up", json=request)
    assert replay.status_code == 200
    assert replay.get_json()["idempotent_replay"] is True
    assert len(agent.load_profile()["caregiver_actions"]) == 1

    workspace = _workspace(client)
    unlinked = client.patch(
        f"/api/research-considerations/{created['id']}/follow-up",
        json={
            **_meta(workspace, "research-unlink-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
            "caregiver_action_id": None,
            "expected_action_token": workspace["considerations"][0]["follow_up"]["token"],
        },
    )
    assert unlinked.status_code == 200
    profile = agent.load_profile()
    assert _workspace(client)["eligible_actions"] == []
    assert client.get("/api/patient/symptom-episodes").get_json()["eligible_actions"] == []
    assert client.get("/api/patient/treatment-reconciliation").get_json()["eligible_actions"] == []
    profile["caregiver_actions"][0]["outcome"] = {
        "kind": "caregiver_reported",
        "text": "Must never enter model context",
        "recorded_at": "2026-08-03T10:00:00",
    }
    summary = agent.get_patient_summary(profile)
    assert "Must never enter model context" not in summary


def test_cross_linked_research_action_fails_projection_without_rewrite(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    created = _create(client, _workspace(client)).get_json()["consideration"]
    workspace = _workspace(client)
    assert (
        client.patch(
            f"/api/research-considerations/{created['id']}/follow-up",
            json={
                **_meta(workspace, "research-cross-link-001"),
                "expected_consideration_token": workspace["considerations"][0]["token"],
                "follow_up": {"text": "Exact research follow-up"},
            },
        ).status_code
        == 200
    )
    profile = agent.load_profile()
    action_id = profile["caregiver_actions"][0]["id"]
    profile["symptom_episodes"] = [
        {
            "id": "symptom_episode_corrupt",
            "status": "current",
            "symptom_text": "Exact caregiver wording",
            "severity_level": None,
            "severity_detail": None,
            "reported_subject": "patient",
            "onset_date": None,
            "onset_date_precision": "unknown",
            "onset_date_kind": "unknown",
            "timing_text": None,
            "frequency_text": None,
            "impact_text": None,
            "notes": None,
            "resolved_date": None,
            "resolved_date_precision": "unknown",
            "resolved_date_kind": "unknown",
            "provenance": {
                "capture_method": "caregiver_entered",
                "source_verification": "unverified",
            },
            "caregiver_action_id": action_id,
            "created_at": "2026-08-03T10:00:00",
            "updated_at": "2026-08-03T10:00:00",
            "resolved_at": None,
            "history": [],
        }
    ]
    agent.save_profile(profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()
    response = client.get("/api/patient/research-workspace")
    assert response.status_code == 422
    assert response.get_json()["code"] == "research_projection_invalid"
    assert agent.PROFILE_PATH.read_bytes() == before


def test_generic_action_is_excluded_only_while_linked(agent, empty_profile, app_client):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    action = {
        "id": "act_generic",
        "origin_snapshot": {
            "kind": "manual",
            "source_id": None,
            "source_job_id": None,
            "source_profile_revision": None,
            "generation_id": None,
            "text": "Generic follow-up",
            "snapshot": {},
        },
        "text": "Generic follow-up",
        "owner": None,
        "due_date": None,
        "status": "open",
        "outcome": {
            "kind": "caregiver_reported",
            "text": "Temporary context",
            "recorded_at": "2026-08-03T10:00:00",
        },
        "visit_id": None,
        "decision_id": None,
        "alert_id": None,
        "created_at": "2026-08-03T09:00:00",
        "updated_at": "2026-08-03T09:00:00",
        "completed_at": None,
        "cancelled_at": None,
        "history": [],
    }
    profile = agent.load_profile()
    profile["caregiver_actions"] = [action]
    agent.save_profile(profile, clinical_change=False)
    assert "Temporary context" in agent.get_patient_summary(agent.load_profile())

    created = _create(client, _workspace(client)).get_json()["consideration"]
    workspace = _workspace(client)
    eligible = workspace["eligible_actions"][0]
    linked = client.patch(
        f"/api/research-considerations/{created['id']}/follow-up",
        json={
            **_meta(workspace, "generic-link-001"),
            "expected_consideration_token": workspace["considerations"][0]["token"],
            "caregiver_action_id": eligible["id"],
            "expected_action_token": eligible["token"],
        },
    )
    assert linked.status_code == 200
    assert "Temporary context" not in agent.get_patient_summary(agent.load_profile())

    workspace = _workspace(client)
    assert (
        client.patch(
            f"/api/research-considerations/{created['id']}/follow-up",
            json={
                **_meta(workspace, "generic-unlink-001"),
                "expected_consideration_token": workspace["considerations"][0]["token"],
                "caregiver_action_id": None,
                "expected_action_token": workspace["considerations"][0]["follow_up"]["token"],
            },
        ).status_code
        == 200
    )
    assert "Temporary context" in agent.get_patient_summary(agent.load_profile())


def test_visit_owned_action_is_not_eligible_in_any_new_link_projection(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    profile = agent.load_profile()
    profile["caregiver_actions"] = [
        {
            "id": "act_visit_owned",
            "origin_snapshot": {
                "kind": "manual",
                "source_id": None,
                "source_job_id": None,
                "source_profile_revision": None,
                "generation_id": None,
                "text": "Visit-owned",
                "snapshot": {},
            },
            "text": "Visit-owned",
            "status": "open",
            "visit_id": "visit_1",
            "created_at": "2026-08-01T10:00:00",
            "updated_at": "2026-08-01T10:00:00",
            "history": [],
        }
    ]
    agent.save_profile(profile, clinical_change=False)
    assert _workspace(client)["eligible_actions"] == []
    symptom = client.get("/api/patient/symptom-episodes").get_json()
    treatment = client.get("/api/patient/treatment-reconciliation").get_json()
    assert symptom["eligible_actions"] == []
    assert treatment["eligible_actions"] == []


def test_stale_cas_and_different_replay_request_fail_without_mutation(
    agent, empty_profile, app_client
):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    workspace = _workspace(client)
    request = {
        **_meta(workspace, "research-cas-001"),
        "research_record_id": workspace["items"][0]["id"],
        "expected_item_token": workspace["items"][0]["token"],
    }
    assert client.post("/api/research-considerations", json=request).status_code == 201
    before = agent.PROFILE_PATH.read_bytes()
    changed = copy.deepcopy(request)
    changed["research_record_id"] = workspace["items"][1]["id"]
    changed["expected_item_token"] = workspace["items"][1]["token"]
    assert client.post("/api/research-considerations", json=changed).status_code == 409
    assert agent.PROFILE_PATH.read_bytes() == before
    stale = copy.deepcopy(changed)
    stale["mutation_id"] = "research-cas-002"
    assert client.post("/api/research-considerations", json=stale).status_code == 409
    assert agent.PROFILE_PATH.read_bytes() == before


def test_projection_bounds_accept_complete_criteria_limit_and_fail_without_write_above_it(
    agent, empty_profile, app_client
):
    _, client = app_client
    empty_profile["trials_tracked"] = [_trial(agent, eligibility_excerpt="E" * 100_000)]
    agent.save_profile(empty_profile, clinical_change=False)
    workspace = _workspace(client)
    assert _create(client, workspace, mutation_id="research-max-row-001").status_code == 201

    profile = agent.load_profile()
    profile["trials_tracked"][0]["eligibility_excerpt"] = "E" * 100_001
    agent.save_profile(profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()
    response = client.get("/api/patient/research-workspace")
    assert response.status_code == 422
    assert response.get_json()["code"] == "research_projection_too_large"
    assert agent.PROFILE_PATH.read_bytes() == before


def test_internal_identity_and_disposition_do_not_change_model_visible_research(agent):
    from agent.exec_summary import _tracked_trials_context

    legacy_trial = {
        "nct_id": "NCT12345678",
        "title": "Exact registry title",
        "status": "RECRUITING",
        "registry_last_update": "2026-08-01",
        "eligibility_excerpt": "Exact criteria",
    }
    before = copy.deepcopy(agent.DEFAULT_PROFILE)
    before["trials_tracked"] = [copy.deepcopy(legacy_trial)]
    after = copy.deepcopy(before)
    after["trials_tracked"] = [
        {
            "research_record_id": "research_trial_1234567890abcdef",
            **copy.deepcopy(legacy_trial),
        }
    ]
    after["research_considerations"] = [
        {
            "id": "private",
            "events": [{"note": "Never model-visible"}],
        }
    ]
    assert _tracked_trials_context(before) == _tracked_trials_context(after)
    assert agent.get_patient_summary(before) == agent.get_patient_summary(after)


def test_tampered_replay_snapshot_is_rejected_without_save(agent, empty_profile, app_client):
    _, client = app_client
    _seed_profile(agent, empty_profile)
    workspace = _workspace(client)
    request = {
        **_meta(workspace, "research-replay-tamper-001"),
        "research_record_id": workspace["items"][0]["id"],
        "expected_item_token": workspace["items"][0]["token"],
    }
    assert client.post("/api/research-considerations", json=request).status_code == 201
    profile = agent.load_profile()
    event = profile["research_considerations"][0]["history"][0]
    event["result_snapshot"]["consideration"]["snapshot"]["private_manifest"] = {
        "must_not_replay": True
    }
    event["result_hash"] = agent.request_hash(event["result_snapshot"])
    agent.save_profile(profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()

    replay = client.post("/api/research-considerations", json=request)
    assert replay.status_code == 409
    assert agent.PROFILE_PATH.read_bytes() == before


def test_save_failure_commits_no_research_workflow_or_revision(
    agent, empty_profile, app_client, monkeypatch
):
    app_module, client = app_client
    _seed_profile(agent, empty_profile)
    workspace = _workspace(client)
    request = {
        **_meta(workspace, "research-save-failure-001"),
        "research_record_id": workspace["items"][0]["id"],
        "expected_item_token": workspace["items"][0]["token"],
    }
    before = agent.PROFILE_PATH.read_bytes()

    def fail_save(*_args, **_kwargs):
        raise OSError("simulated research save failure")

    monkeypatch.setattr(app_module.agent, "save_profile", fail_save)
    with pytest.raises(OSError, match="simulated research save failure"):
        client.post("/api/research-considerations", json=request)
    assert agent.PROFILE_PATH.read_bytes() == before
