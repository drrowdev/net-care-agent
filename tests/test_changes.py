"""Tests for exact latest-batch research additions."""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    import agent.config as cfg

    monkeypatch.setattr(cfg, "PROFILE_PATH", tmp_path / "patient_profile.json")
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    return app_mod


@pytest.fixture
def client(app_module):
    with app_module.app.test_client() as test_client:
        yield test_client


def _seed_profile(tmp_path, **overrides):
    profile = {
        "patient": {"diagnosis": "neuroendocrine tumor"},
        "trials_tracked": [],
        "literature_watched": [],
    }
    profile.update(overrides)
    (tmp_path / "patient_profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return profile


def test_latest_research_update_records_only_net_new_ids(app_module):
    profile = {
        "trials_tracked": [
            {"nct_id": "NCT00000001"},
            {"nct_id": "NCT00000002"},
        ],
        "literature_watched": [
            {"pmid": "10000001"},
            {"pmid": "10000002"},
        ],
    }

    update = app_module.agent.record_latest_research_update(
        profile,
        job_id="digest-1",
        trigger="digest",
        previous_trial_ids={"NCT00000001"},
        previous_paper_ids={"10000001"},
        record_empty=True,
    )

    assert update["trial_ids"] == ["NCT00000002"]
    assert update["paper_ids"] == ["10000002"]
    assert profile["latest_research_update"] == update


def test_empty_feed_discovery_keeps_previous_research_batch(app_module):
    previous = {
        "job_id": "digest-1",
        "trigger": "digest",
        "completed_at": "2026-08-05T10:00:00",
        "trial_ids": ["NCT00000002"],
        "paper_ids": [],
    }
    profile = {
        "trials_tracked": [{"nct_id": "NCT00000002"}],
        "literature_watched": [],
        "latest_research_update": previous,
    }

    update = app_module.agent.record_latest_research_update(
        profile,
        job_id="feed-1",
        trigger="feed",
        previous_trial_ids={"NCT00000002"},
        previous_paper_ids=set(),
        record_empty=False,
    )

    assert update is None
    assert profile["latest_research_update"] == previous


def test_status_filters_latest_batch_to_items_still_tracked(client, tmp_path):
    _seed_profile(
        tmp_path,
        trials_tracked=[
            {"nct_id": "NCT00000001"},
            {"nct_id": "NCT00000002"},
            {"nct_id": "not-an-nct"},
        ],
        literature_watched=[
            {"pmid": "10000002"},
            {"pmid": "not-a-pmid"},
        ],
        latest_research_update={
            "job_id": "digest-1",
            "trigger": "digest",
            "completed_at": "2026-08-05T10:00:00",
            "trial_ids": ["NCT00000002", "NCT00000003", "not-an-nct"],
            "paper_ids": ["10000002", "10000003", "not-a-pmid"],
        },
    )

    response = client.get("/api/status")

    assert response.status_code == 200
    update = response.get_json()["latest_research_update"]
    assert update["trial_ids"] == ["NCT00000002"]
    assert update["paper_ids"] == ["10000002"]
    assert update["trial_count"] == 1
    assert update["paper_count"] == 1
    assert update["total_count"] == 2


def test_digest_records_zero_when_nothing_new_is_found(app_module, monkeypatch, tmp_path):
    _seed_profile(
        tmp_path,
        trials_tracked=[{"nct_id": "NCT00000001"}],
        literature_watched=[{"pmid": "10000001"}],
        latest_research_update={
            "job_id": "digest-old",
            "trigger": "digest",
            "completed_at": "2026-08-04T10:00:00",
            "trial_ids": ["NCT00000001"],
            "paper_ids": ["10000001"],
        },
    )
    monkeypatch.setattr(app_module, "_update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module.agent, "poll_tracked_trials", lambda _profile: {"changed": []})
    monkeypatch.setattr(app_module.agent, "run_orchestrator", lambda *_args: "report")
    monkeypatch.setattr(app_module.agent, "classify_treatments", lambda _profile: [])
    monkeypatch.setattr(app_module, "_refresh_summary", lambda _profile, **_kwargs: None)

    app_module._run_digest_job("digest-new")

    stored = json.loads((tmp_path / "patient_profile.json").read_text(encoding="utf-8"))
    update = stored["latest_research_update"]
    assert update["job_id"] == "digest-new"
    assert update["trial_ids"] == []
    assert update["paper_ids"] == []


def test_cached_review_routes_are_inert_and_do_not_write_profile(client, tmp_path):
    original = _seed_profile(
        tmp_path,
        acknowledged_at="2026-08-05T09:00:00",
        trials_tracked=[{"nct_id": "NCT00000001"}],
    )

    read_response = client.get("/api/changes")
    acknowledge_response = client.post("/api/changes/acknowledge")

    assert read_response.status_code == 200
    assert acknowledge_response.status_code == 200
    assert read_response.get_json()["new"]["total_new"] == 0
    assert acknowledge_response.get_json()["acknowledged_at"] is None
    stored = json.loads((tmp_path / "patient_profile.json").read_text(encoding="utf-8"))
    assert stored == original


@pytest.mark.parametrize(
    ("command", "expected_trigger"),
    [("feed", "feed"), ("digest", "digest")],
)
def test_cli_research_runs_record_the_latest_batch(
    app_module, monkeypatch, tmp_path, command, expected_trigger
):
    from agent import cli

    _seed_profile(
        tmp_path,
        trials_tracked=[{"nct_id": "NCT00000001"}],
        literature_watched=[{"pmid": "10000001"}],
    )

    def add_research(profile, _extracted):
        profile["trials_tracked"].append({"nct_id": "NCT00000002"})
        profile["literature_watched"].append({"pmid": "10000002"})
        return "report"

    monkeypatch.setattr(cli, "run_orchestrator", add_research)
    monkeypatch.setattr(cli, "_print_and_save_report", lambda *_args: None)

    if command == "feed":
        monkeypatch.setattr(
            cli,
            "run_intake",
            lambda _text, profile, **_kwargs: (profile, {"document_type": "note"}),
        )
        cli.cmd_feed(SimpleNamespace(file=None, text="clinical note"))
    else:
        cli.cmd_digest(SimpleNamespace())

    stored = json.loads((tmp_path / "patient_profile.json").read_text(encoding="utf-8"))
    update = stored["latest_research_update"]
    assert update["trigger"] == expected_trigger
    assert update["job_id"].startswith(f"cli-{command}-")
    assert update["trial_ids"] == ["NCT00000002"]
    assert update["paper_ids"] == ["10000002"]


def test_cli_feed_commits_versioned_intake_before_orchestration_failure(agent, monkeypatch):
    from agent import cli

    def intake(_text, profile, **_kwargs):
        profile["documents"].append(
            {
                "id": "doc-row",
                "date": "2026-08-01",
                "summary": "Committed intake",
                "source_document_id": "doc_" + "a" * 32,
            }
        )
        profile["alerts"].append(
            {
                "id": "alert-row",
                "message": "Intake failure alert",
                "resolved": False,
                "source_document_id": "doc_" + "a" * 32,
            }
        )
        return profile, {"source_document_id": "doc_" + "a" * 32}

    monkeypatch.setattr(cli, "run_intake", intake)
    monkeypatch.setattr(
        cli,
        "run_orchestrator",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("research failed")),
    )

    with pytest.raises(RuntimeError, match="research failed"):
        cli.cmd_feed(SimpleNamespace(file=None, text="clinical note"))

    saved = agent.load_profile()
    assert saved["documents"][0]["summary"] == "Committed intake"
    assert saved["alerts"][0]["source_job_id"].startswith("cli-feed-")
    assert saved["alerts"][0]["generation_profile_revision"] == saved["profile_revision"]


def test_successful_cli_feed_finalizes_intake_alert_revision(agent, monkeypatch):
    from agent import cli

    def intake(_text, profile, **_kwargs):
        source_id = "doc_" + "b" * 32
        profile["alerts"].append(
            {
                "id": "alert-row",
                "message": "Intake failure alert",
                "resolved": False,
                "source_document_id": source_id,
            }
        )
        return profile, {"source_document_id": source_id}

    monkeypatch.setattr(cli, "run_intake", intake)
    monkeypatch.setattr(cli, "run_orchestrator", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(
        cli,
        "classify_treatments",
        lambda _profile: [{"text": "lanreotide", "category": "active"}],
    )
    monkeypatch.setattr(cli, "_print_and_save_report", lambda *_args: None)

    cli.cmd_feed(SimpleNamespace(file=None, text="clinical note"))

    saved = agent.load_profile()
    alert = saved["alerts"][0]
    assert alert["generation_profile_revision"] == saved["profile_revision"]
    assert agent.active_alerts(saved)[0]["id"] == alert["id"]
    assert saved["treatments_classification_revision"] == saved["profile_revision"]


def test_cli_classification_failure_keeps_precommitted_raw_treatments(agent, monkeypatch):
    from agent import cli

    def intake(_text, profile, **_kwargs):
        profile["patient"]["current_treatments"].append("everolimus")
        agent.invalidate_treatment_classification(profile)
        return profile, {"source_document_id": "doc_" + "c" * 32}

    monkeypatch.setattr(cli, "run_intake", intake)
    monkeypatch.setattr(cli, "run_orchestrator", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(
        cli,
        "classify_treatments",
        lambda _profile: (_ for _ in ()).throw(RuntimeError("classification failed")),
    )

    with pytest.raises(RuntimeError, match="classification failed"):
        cli.cmd_feed(SimpleNamespace(file=None, text="clinical note"))

    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["everolimus"]
    assert saved["treatments_classification_revision"] is None
    assert [item["text"] for item in agent.current_treatment_records(saved)] == ["everolimus"]


def test_cli_mixed_surgery_treatment_partial_classification_fails_closed(agent, monkeypatch):
    from agent import cli

    def intake(_text, profile, **_kwargs):
        profile["patient"]["current_treatments"].append("hepatectomy and lanreotide")
        agent.invalidate_treatment_classification(profile)
        agent.sync_treatment_records(profile)
        return profile, {"source_document_id": "doc_" + "d" * 32}

    monkeypatch.setattr(cli, "run_intake", intake)
    monkeypatch.setattr(cli, "run_orchestrator", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(
        cli,
        "classify_treatments",
        lambda _profile: (_ for _ in ()).throw(agent.TreatmentClassificationError("partial")),
    )

    with pytest.raises(agent.TreatmentClassificationError):
        cli.cmd_feed(SimpleNamespace(file=None, text="clinical note"))

    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["hepatectomy and lanreotide"]
    assert saved["treatments_classification_revision"] is None


def test_cli_update_profile_binds_successful_classification_to_saved_revision(agent, monkeypatch):
    from agent import cli

    answers = iter(["", "", "", "", "", "capecitabine"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(
        cli,
        "classify_treatments",
        lambda profile: [
            {
                "text": profile["patient"]["current_treatments"][0],
                "label": "Capecitabine",
                "category": "active",
            }
        ],
    )

    cli.cmd_update_profile(SimpleNamespace())

    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["capecitabine"]
    assert saved["treatments_classification_revision"] == saved["profile_revision"]
    assert saved["treatments_classification_job_id"].startswith("cli-update-")
