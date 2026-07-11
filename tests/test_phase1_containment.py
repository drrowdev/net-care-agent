from __future__ import annotations

import importlib
import inspect
import io
import sys
import threading
import time

import pytest


@pytest.fixture
def app_mod(agent):
    sys.modules.pop("app", None)
    import app

    importlib.reload(app)
    app.app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_mod):
    return app_mod.app.test_client()


def _successful_summary():
    return {
        "overall_status": "stable",
        "status_confidence": "high",
        "status_rationale": "Current evidence is stable.",
        "key_concern": "None",
        "summary": "Fresh summary",
        "prrt_status": "unknown",
        "prrt_rationale": "",
        "cga_trend": "insufficient_data",
        "cga_trend_detail": "",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "generated_at": "2026-07-10",
    }


def _stub_job_pipeline(app_mod, agent, monkeypatch):
    monkeypatch.setattr(app_mod, "_update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        agent,
        "run_intake",
        lambda text, profile: (
            profile,
            {
                "document_type": "note",
                "summary": text,
                "key_findings": [],
            },
        ),
    )
    monkeypatch.setattr(agent, "run_orchestrator", lambda *_args: "report")
    monkeypatch.setattr(agent, "classify_treatments", lambda _profile: [{"text": "SSA"}])
    monkeypatch.setattr(agent, "generate_executive_summary", lambda _profile: _successful_summary())


@pytest.mark.parametrize("job_type", ["feed", "digest"])
def test_feed_and_digest_refresh_summary(app_mod, agent, monkeypatch, job_type):
    _stub_job_pipeline(app_mod, agent, monkeypatch)
    monkeypatch.setattr(agent, "poll_tracked_trials", lambda _profile: {"changed": []})

    if job_type == "feed":
        app_mod._run_feed_job("job", "clinical note")
    else:
        app_mod._run_digest_job("job")

    profile = agent.load_profile()
    assert profile["executive_summary"]["summary"] == "Fresh summary"
    assert profile["executive_summary"]["summary_revision"] == profile["profile_revision"]
    assert profile["summary_stale"] is False
    assert profile["treatments_classified"][0]["text"] == "SSA"


def test_summary_failure_preserves_mutations_and_marks_existing_summary_stale(
    app_mod, agent, monkeypatch
):
    profile = agent.load_profile()
    profile["documents"] = []
    profile["executive_summary"] = {**_successful_summary(), "summary_revision": 1}
    agent.save_profile(profile)

    monkeypatch.setattr(app_mod, "_update_job", lambda *_args, **_kwargs: None)

    def intake(_text, current):
        current["documents"].append(
            {"date": "2020-01-01", "summary": "Back-dated note", "added_at": "2026-07-10T12:00:00"}
        )
        return current, {"document_type": "note", "summary": "note", "key_findings": []}

    monkeypatch.setattr(agent, "run_intake", intake)
    monkeypatch.setattr(agent, "run_orchestrator", lambda *_args: "report")
    monkeypatch.setattr(agent, "classify_treatments", lambda _profile: [])
    monkeypatch.setattr(
        agent,
        "generate_executive_summary",
        lambda _profile: {
            **_successful_summary(),
            "generation_failed": True,
            "summary": "Error: model unavailable",
        },
    )

    app_mod._run_feed_job("job", "text")
    saved = agent.load_profile()
    assert saved["documents"][-1]["summary"] == "Back-dated note"
    assert saved["executive_summary"]["summary"] == "Fresh summary"
    assert saved["executive_summary"]["summary_error"] == "Summary generation failed."
    assert saved["summary_stale"] is True


def test_backdated_mutation_invalidates_prior_summary(agent):
    profile = agent.load_profile()
    profile["executive_summary"] = {
        **_successful_summary(),
        "summary_revision": int(profile.get("profile_revision") or 0) + 1,
    }
    agent.save_profile(profile)
    assert profile["summary_stale"] is False

    profile["documents"].append(
        {"date": "2019-01-01", "summary": "Old clinical note", "added_at": "2026-07-10T12:00:00"}
    )
    agent.save_profile(profile)
    assert profile["summary_stale"] is True
    assert profile["executive_summary"]["summary_revision"] < profile["profile_revision"]


def test_pdf_file_endpoint_extracts_and_enqueues_text(app_mod, client, monkeypatch):
    captured = {}
    completed = threading.Event()

    def capture(job_id, *args):
        captured["job_id"] = job_id
        captured["args"] = args
        completed.set()

    monkeypatch.setattr(app_mod, "_run_feed_job", capture)
    response = client.post(
        "/api/feed-file",
        data={"file": (io.BytesIO(b"%PDF-minimal"), "report.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    assert completed.wait(1)
    assert captured["args"][1] == "job-upload"
    assert captured["args"][2] == "report.pdf"


def test_profile_route_waits_for_background_transaction_without_lost_update(
    app_mod, agent, monkeypatch
):
    entered = threading.Event()
    release = threading.Event()
    _stub_job_pipeline(app_mod, agent, monkeypatch)

    def intake(_text, profile):
        profile["documents"].append(
            {"date": "2026-07-10", "summary": "Feed document", "added_at": "2026-07-10T12:00:00"}
        )
        entered.set()
        assert release.wait(3)
        return profile, {"document_type": "note", "summary": "feed", "key_findings": []}

    monkeypatch.setattr(agent, "run_intake", intake)
    feed_thread = threading.Thread(target=app_mod._run_feed_job, args=("job", "text"))
    feed_thread.start()
    assert entered.wait(3)

    response_box = {}

    def add_symptom():
        with app_mod.app.test_client() as route_client:
            response_box["response"] = route_client.post(
                "/api/symptoms",
                json={"symptom": "fatigue", "date": "2020-01-01"},
            )

    route_thread = threading.Thread(target=add_symptom)
    route_thread.start()
    release.set()
    feed_thread.join(5)
    route_thread.join(5)

    assert response_box["response"].status_code == 200
    profile = agent.load_profile()
    assert any(d.get("summary") == "Feed document" for d in profile["documents"])
    assert any(s.get("symptom") == "fatigue" for s in profile["symptoms"])


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "script-src 'self' 'unsafe-inline'" in response.headers["Content-Security-Policy"]
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_csp_inline_script_exception_is_limited_to_legacy_static_handlers(app_mod):
    index = (app_mod.Path(app_mod.app.static_folder) / "index.html").read_text(encoding="utf-8")
    assert "onclick=" in index or "onkeydown=" in index
    assert "TODO: remove script unsafe-inline" in inspect.getsource(app_mod._add_cache_headers)


def test_acknowledging_changes_does_not_stale_current_summary(client, agent):
    profile = agent.load_profile()
    profile["executive_summary"] = {
        **_successful_summary(),
        "summary_revision": int(profile.get("profile_revision") or 0) + 1,
        "stale": False,
    }
    profile["summary_stale"] = False
    agent.save_profile(profile)
    revision = profile["profile_revision"]

    response = client.post("/api/changes/acknowledge")

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["profile_revision"] == revision
    assert saved["summary_stale"] is False
    assert saved["executive_summary"]["stale"] is False


def test_same_day_summary_timestamp_counts_as_new(app_mod):
    profile = {
        "acknowledged_at": "2026-07-10T09:00:00",
        "executive_summary": {
            "generated_at": "2026-07-10",
            "generated_at_timestamp": "2026-07-10T10:00:00",
        },
    }

    counts = app_mod._count_new(profile)

    assert counts["executive_summary"] is True
    assert counts["total_new"] == 1


def test_same_day_research_items_use_timestamp_and_count_as_new(
    app_mod,
    agent,
    empty_profile,
    monkeypatch,
):
    from agent import tools

    monkeypatch.setattr(
        tools,
        "search_pubmed",
        lambda *_args, **_kwargs: {
            "results": [
                {
                    "pmid": "12345678",
                    "title": "Neuroendocrine tumor PRRT evidence",
                    "authors": "A",
                    "journal": "J",
                    "date": "2026",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                }
            ]
        },
    )
    tools.execute_tool("search_pubmed", {"query": "NET PRRT"}, empty_profile)
    added = empty_profile["literature_watched"][0]["date_added"]
    assert "T" in added

    empty_profile["acknowledged_at"] = added[:10] + "T00:00:00"
    assert app_mod._count_new(empty_profile)["papers"] == 1


def test_first_profile_creation_is_serialized(agent):
    from agent import config

    config.PROFILE_PATH.unlink(missing_ok=True)
    profiles = []
    errors = []

    def load():
        try:
            profiles.append(agent.load_profile())
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=load) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert errors == []
    assert len(profiles) == 4
    assert config.PROFILE_PATH.exists()


def test_pdf_page_limit_is_enforced(app_mod, client, monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "extract_pdf_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("pdf_invalid")),
    )

    response = client.post(
        "/api/feed-file",
        data={"file": (io.BytesIO(b"%PDF-minimal"), "report.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    job_id = response.get_json()["job_id"]
    deadline = time.time() + 2
    while time.time() < deadline:
        detail = client.get(f"/api/jobs/{job_id}").get_json()
        if detail["status"] == "error":
            break
        time.sleep(0.01)
    assert detail["error_code"] == "pdf_invalid"


def test_summary_trial_context_prefers_current_and_discloses_omissions(agent):
    from agent.exec_summary import _tracked_trials_context

    trials = [
        {
            "nct_id": f"NCT{i:08d}",
            "status": "COMPLETED",
            "date_added": f"2025-01-{i:02d}",
            "eligibility_excerpt": f"complete criteria {i} " + ("x" * 700),
        }
        for i in range(1, 21)
    ]
    trials.append(
        {
            "nct_id": "NCT99999999",
            "status": "RECRUITING",
            "date_added": "2024-01-01",
            "eligibility_excerpt": "complete recruiting criteria " + ("y" * 700),
        }
    )

    context = _tracked_trials_context({"trials_tracked": trials})

    assert context["tracked_total"] == 21
    assert context["included"] == 20
    assert context["omitted"] == 1
    assert context["trials"][0]["nct_id"] == "NCT99999999"
    assert len(context["trials"][0]["eligibility_excerpt"]) > 700


def test_question_bookkeeping_does_not_invalidate_summary(client, agent):
    profile = agent.load_profile()
    profile["executive_summary"] = {
        **_successful_summary(),
        "summary_revision": int(profile.get("profile_revision") or 0) + 1,
        "stale": False,
    }
    profile["summary_stale"] = False
    agent.save_profile(profile)
    revision = profile["profile_revision"]

    added = client.post(
        "/api/questions/add",
        json={"text": "What should we ask?", "category": "Other"},
    )
    assert added.status_code == 200
    qid = added.get_json()["id"]
    assert client.post(f"/api/questions/{qid}/toggle").status_code == 200
    assert client.delete(f"/api/questions/{qid}").status_code == 200

    saved = agent.load_profile()
    assert saved["profile_revision"] == revision
    assert saved["summary_stale"] is False
