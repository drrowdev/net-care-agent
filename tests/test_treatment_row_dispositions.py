"""Caregiver workspace visibility for raw treatment statements.

The caregiver may collapse a recorded treatment statement he does not find
useful (for example an infusion-rate note his clinicians act on but he never
tracks). That choice is presentation only. These tests pin the three properties
that make it safe:

1. Nothing is deleted — the row stays in ``current_treatments[]`` and in the
   projection.
2. Nothing is hidden from the assistant — a hidden row still reaches every model
   prompt verbatim.
3. Software never decides relevance — only an explicit caregiver mutation, under
   compare-and-swap, can change visibility.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


NOISE = "Vamin infusion at half speed to reduce nausea"
REAL = "Started lanreotide 120 mg every 4 weeks"


def _seed(agent, treatments=(REAL, NOISE)):
    profile = agent.load_profile()
    profile["patient"]["current_treatments"] = list(treatments)
    agent.sync_treatment_records(profile)
    agent.save_profile(profile, clinical_change=True)
    return profile


def _projection(client):
    response = client.get("/api/patient/treatment-reconciliation")
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _row_named(projection, needle):
    return next(row for row in projection["legacy_treatments"] if needle in row["raw_text"])


def _disposition_for(projection, row_id):
    return next(
        item for item in projection["legacy_treatment_dispositions"] if item["row_id"] == row_id
    )


def _set_visibility(client, projection, row_id, hidden, mutation_id):
    disposition = _disposition_for(projection, row_id)
    return client.post(
        f"/api/treatment-reconciliation/legacy-rows/{row_id}/disposition",
        json={
            "mutation_id": mutation_id,
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_disposition_token": disposition["token"],
            "hidden": hidden,
        },
    )


def test_source_entry_id_helper_matches_persisted_component_mapping(agent):
    """The disposition key must equal what sync_treatment_records already stores."""
    profile = _seed(agent, (REAL, NOISE, REAL))
    records = profile["patient"]["current_treatment_records"]
    keys = agent.raw_treatment_source_entry_ids(profile["patient"]["current_treatments"])
    for record in records:
        assert record["source_entry_id"] == keys[record["source_order"]]
    # Two identical rows are distinct occurrences, never collapsed onto one key.
    assert keys[0] != keys[2]


def test_new_profile_starts_with_every_row_visible(agent, app_client):
    _seed(agent)
    _, client = app_client
    projection = _projection(client)
    assert projection["legacy_treatment_count"] == 2
    assert projection["legacy_treatment_hidden_count"] == 0
    assert len(projection["legacy_treatment_dispositions"]) == 2
    assert all(not item["hidden"] for item in projection["legacy_treatment_dispositions"])


def test_hiding_a_row_never_deletes_it_or_changes_stored_wording(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise = _row_named(projection, "Vamin")

    response = _set_visibility(client, projection, noise["id"], True, "disp-hide-001")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["disposition"]["hidden"] is True
    assert response.get_json()["legacy_treatment_hidden_count"] == 1

    after = _projection(client)
    assert after["legacy_treatment_count"] == 2
    assert after["legacy_treatment_hidden_count"] == 1
    assert _row_named(after, "Vamin")["raw_text"] == NOISE

    stored = app_module.agent.load_profile()
    assert stored["patient"]["current_treatments"] == [REAL, NOISE]
    assert len(stored["patient"]["current_treatment_records"]) == 2


def test_hidden_row_still_reaches_every_model_prompt(agent, app_client):
    """Hiding is a workspace preference, never a decision about what NET/Care knows."""
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise = _row_named(projection, "Vamin")
    assert (
        _set_visibility(client, projection, noise["id"], True, "disp-hide-002").status_code == 200
    )

    profile = app_module.agent.load_profile()
    chat_prompt = app_module.agent.build_chat_system(profile)
    summary = app_module.agent.get_patient_summary(profile)
    assert NOISE in chat_prompt
    assert NOISE in summary
    assert [item["text"] for item in app_module.agent.current_treatment_records(profile)] == [
        REAL,
        NOISE,
    ]


def test_disposition_state_never_leaks_into_a_model_prompt(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise = _row_named(projection, "Vamin")
    assert (
        _set_visibility(client, projection, noise["id"], True, "disp-hide-003").status_code == 200
    )

    profile = app_module.agent.load_profile()
    stored = profile["treatment_row_dispositions"]
    assert stored and stored[0]["hidden"] is True
    for prompt in (
        app_module.agent.build_chat_system(profile),
        app_module.agent.get_patient_summary(profile),
    ):
        assert "txdisp" not in prompt
        assert stored[0]["source_entry_id"] not in prompt
        assert "not useful in my workspace" not in prompt.casefold()


def test_hidden_state_follows_the_row_when_an_earlier_row_is_removed(agent, app_client):
    """The stored key is position independent, so it cannot re-attach to a neighbour.

    Public projection row IDs fold in ``source_order``. Keying workspace state on
    them would silently move a caregiver's choice onto a different statement the
    moment an earlier row disappeared.
    """
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise = _row_named(projection, "Vamin")
    assert (
        _set_visibility(client, projection, noise["id"], True, "disp-hide-004").status_code == 200
    )

    profile = app_module.agent.load_profile()
    profile["patient"]["current_treatments"] = [NOISE]
    app_module.agent.sync_treatment_records(profile)
    app_module.agent.save_profile(profile, clinical_change=True)

    after = _projection(client)
    assert after["legacy_treatment_count"] == 1
    surviving = _row_named(after, "Vamin")
    assert surviving["id"] != noise["id"]
    assert _disposition_for(after, surviving["id"])["hidden"] is True
    assert after["legacy_treatment_hidden_count"] == 1


def test_correcting_a_hidden_rows_wording_makes_it_visible_again(agent, app_client):
    """Orphaned workspace state must fail towards showing, never towards hiding."""
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise = _row_named(projection, "Vamin")
    assert (
        _set_visibility(client, projection, noise["id"], True, "disp-hide-005").status_code == 200
    )

    profile = app_module.agent.load_profile()
    profile["patient"]["current_treatments"] = [REAL, "Vamin infusion at full speed"]
    app_module.agent.sync_treatment_records(profile)
    app_module.agent.save_profile(profile, clinical_change=True)

    after = _projection(client)
    assert after["legacy_treatment_hidden_count"] == 0
    assert all(not item["hidden"] for item in after["legacy_treatment_dispositions"])


def test_restore_returns_the_row_and_keeps_append_only_history(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    noise_id = _row_named(_projection(client), "Vamin")["id"]
    assert (
        _set_visibility(client, _projection(client), noise_id, True, "disp-hide-006").status_code
        == 200
    )
    assert (
        _set_visibility(client, _projection(client), noise_id, False, "disp-show-006").status_code
        == 200
    )

    assert _projection(client)["legacy_treatment_hidden_count"] == 0
    stored = app_module.agent.load_profile()["treatment_row_dispositions"]
    assert len(stored) == 1
    assert stored[0]["hidden"] is False
    assert [event["operation"] for event in stored[0]["history"]] == ["hidden", "restored"]


def test_stale_disposition_token_conflicts_without_mutating(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    stale = _projection(client)
    noise_id = _row_named(stale, "Vamin")["id"]
    assert _set_visibility(client, stale, noise_id, True, "disp-hide-007").status_code == 200

    replayed_with_stale_authority = _set_visibility(client, stale, noise_id, False, "disp-show-007")
    assert replayed_with_stale_authority.status_code == 409
    assert app_module.agent.load_profile()["treatment_row_dispositions"][0]["hidden"] is True


def test_exact_replay_is_a_no_op(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    noise_id = _row_named(projection, "Vamin")["id"]
    first = _set_visibility(client, projection, noise_id, True, "disp-hide-008")
    assert first.status_code == 200

    replay = _set_visibility(client, projection, noise_id, True, "disp-hide-008")
    assert replay.status_code == 200
    body = replay.get_json()
    assert body.pop("idempotent_replay") is True
    assert body == first.get_json()
    assert len(app_module.agent.load_profile()["treatment_row_dispositions"][0]["history"]) == 1


def test_setting_the_same_visibility_twice_is_rejected(agent, app_client):
    _seed(agent)
    _, client = app_client
    noise_id = _row_named(_projection(client), "Vamin")["id"]
    assert (
        _set_visibility(client, _projection(client), noise_id, True, "disp-hide-009").status_code
        == 200
    )
    repeated = _set_visibility(client, _projection(client), noise_id, True, "disp-hide-009b")
    assert repeated.status_code == 400


def test_unknown_row_is_not_found(agent, app_client):
    _seed(agent)
    _, client = app_client
    projection = _projection(client)
    response = client.post(
        "/api/treatment-reconciliation/legacy-rows/txlegacy_missing/disposition",
        json={
            "mutation_id": "disp-missing-001",
            "expected_profile_revision": projection["profile_revision"],
            "expected_workflow_revision": projection["workflow_revision"],
            "expected_projection_token": projection["projection_token"],
            "expected_disposition_token": "whatever",
            "hidden": True,
        },
    )
    assert response.status_code == 404


def test_visibility_is_workflow_only_and_does_not_stale_clinical_context(agent, app_client):
    _seed(agent)
    app_module, client = app_client
    projection = _projection(client)
    before_profile_revision = projection["profile_revision"]
    noise_id = _row_named(projection, "Vamin")["id"]
    assert _set_visibility(client, projection, noise_id, True, "disp-hide-010").status_code == 200

    after = _projection(client)
    assert after["profile_revision"] == before_profile_revision
    assert after["workflow_revision"] == projection["workflow_revision"] + 1


def test_v16_migration_adds_empty_authority_without_touching_treatments(agent):
    from agent.migrations import apply_migrations

    legacy = {
        "schema_version": 15,
        "patient": {"current_treatments": [REAL, NOISE]},
        "treatment_courses": [],
    }
    migrated = apply_migrations(legacy)
    assert migrated["schema_version"] == 16
    assert migrated["treatment_row_dispositions"] == []
    assert migrated["patient"]["current_treatments"] == [REAL, NOISE]


def test_v16_migration_preserves_existing_dispositions(agent):
    from agent.migrations import apply_migrations

    existing = [{"id": "txdisp_x", "source_entry_id": "txsrc_x", "hidden": True}]
    migrated = apply_migrations(
        {
            "schema_version": 15,
            "patient": {"current_treatments": []},
            "treatment_row_dispositions": existing,
        }
    )
    assert migrated["treatment_row_dispositions"] == existing
