"""Web jobs must not abort when the ancillary treatment classifier fails closed.

`classify_treatments` raises `TreatmentClassificationError` on purpose when it
cannot certify a lossless raw/model mapping. That refusal is derived context: it
must not stop assessment/feed/digest work, and consumers fall back to the raw
`current_treatments` records.
"""

from __future__ import annotations

import copy
import importlib
import json

import httpx
import pytest

from tests._llm_fake import llm_text, patch_llm

_WARNING = (
    "Treatment classification could not be refreshed; raw treatment records remain available."
)


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def _summary() -> dict:
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
        "generated_at": "2026-08-01",
    }


def _queue_job(app_module, job_id: str, job_type: str) -> None:
    app_module._jobs = [
        {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
            "error": None,
        }
    ]


def _seed(agent) -> tuple[int, list[dict]]:
    """Two raw treatments plus a prior classification the last save staled."""
    profile = agent.load_profile()
    profile["patient"]["current_treatments"] = ["lanreotide", "everolimus"]
    profile["treatments_classified"] = [
        {"id": "txclass_prior", "text": "lanreotide", "label": "Lanreotide", "category": "active"}
    ]
    profile["treatments_classification_revision"] = profile.get("profile_revision")
    profile["treatments_classification_job_id"] = "prior-job"
    revision = profile["treatments_classification_revision"]
    agent.save_profile(profile)
    stored = agent.load_profile()
    assert agent.treatment_classification_is_current(stored) is False
    return revision, copy.deepcopy(stored["treatments_classified"])


def _refusal(agent):
    def _classify(_profile):
        raise agent.TreatmentClassificationError("did not preserve every raw treatment")

    return _classify


def _assert_untouched(agent, saved: dict, seeded: tuple[int, list[dict]]) -> None:
    revision, rows = seeded
    assert saved["treatments_classified"] == rows
    assert saved["treatments_classification_revision"] == revision
    assert saved["treatments_classification_job_id"] == "prior-job"
    assert agent.treatment_classification_is_current(saved) is False


def _assert_raw_fallback(client) -> None:
    status = client.get("/api/status").get_json()
    assert status["treatments_classified"] == []
    assert status["treatments_fallback"] == ["lanreotide", "everolimus"]
    assert status["treatments_classification_current"] is False


def test_summary_classification_failure_still_generates_the_assessment(
    app_client, agent, monkeypatch, caplog
):
    """Before the fix the refusal aborted the job and no summary was produced."""
    app_module, client = app_client
    seeded = _seed(agent)
    _queue_job(app_module, "summary-tce", "summary")
    monkeypatch.setattr(agent, "classify_treatments", _refusal(agent))
    generated: list[int] = []

    def summary(current):
        generated.append(current["profile_revision"])
        return _summary()

    monkeypatch.setattr(agent, "generate_executive_summary", summary)

    with caplog.at_level("WARNING", logger="netcare.app"):
        app_module._run_summary_job("summary-tce")

    saved = agent.load_profile()
    detail = client.get("/api/jobs/summary-tce").get_json()

    assert generated == [saved["profile_revision"]]
    assert saved["executive_summary"]["summary"] == "Fresh summary"
    assert saved["executive_summary"]["summary_revision"] == saved["profile_revision"]
    assert saved["summary_stale"] is False
    assert detail["status"] == "done"
    assert detail["stage"] == "done_with_warnings"
    assert detail.get("error_code") is None
    assert detail["result"]["classification_warning"] == _WARNING
    assert detail["result"]["treatments_classification_current"] is False
    assert detail["result"]["treatments_classified"] == []
    assert detail["result"]["treatments_fallback"] == ["lanreotide", "everolimus"]
    assert [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("classification_skipped")
    ] == ["classification_skipped id=summary-tce type=TreatmentClassificationError cause=none"]
    _assert_untouched(agent, saved, seeded)
    _assert_raw_fallback(client)


def test_summary_classifier_timeout_is_a_warning_not_a_failure(app_client, agent, monkeypatch):
    app_module, client = app_client
    seeded = _seed(agent)
    _queue_job(app_module, "summary-timeout", "summary")

    def timeout(**_kwargs):
        raise httpx.ReadTimeout("upstream timed out")

    monkeypatch.setattr(agent, "generate_executive_summary", lambda _profile: _summary())

    with patch_llm(agent, timeout):
        app_module._run_summary_job("summary-timeout")

    saved = agent.load_profile()
    detail = client.get("/api/jobs/summary-timeout").get_json()

    assert detail["status"] == "done"
    assert detail["stage"] == "done_with_warnings"
    assert saved["executive_summary"]["summary"] == "Fresh summary"
    _assert_untouched(agent, saved, seeded)
    _assert_raw_fallback(client)


def test_summary_fault_outside_the_classifier_wrapping_still_fails_the_job(
    app_client, agent, monkeypatch
):
    """`classify_treatments` wraps its own model call, so drive the real one.

    A fault in the profile reads it performs first is not wrapped, and is the
    production-reachable path that must still fail the job.
    """
    import agent.classify as classify_module

    app_module, client = app_client
    seeded = _seed(agent)
    _queue_job(app_module, "summary-fault", "summary")
    generated: list[str] = []

    def corrupt(_profile):
        raise TypeError("corrupt document collection")

    monkeypatch.setattr(classify_module, "active_documents", corrupt)
    monkeypatch.setattr(
        agent,
        "generate_executive_summary",
        lambda _profile: generated.append("called") or _summary(),
    )

    app_module._run_summary_job("summary-fault")

    detail = client.get("/api/jobs/summary-fault").get_json()

    assert generated == []
    assert detail["status"] == "error"
    assert detail["error_code"] == "job_failed"
    _assert_untouched(agent, agent.load_profile(), seeded)


def test_summary_successful_classification_stays_current_and_done(app_client, agent, monkeypatch):
    app_module, client = app_client
    _seed(agent)
    _queue_job(app_module, "summary-ok", "summary")
    fresh = {
        "id": "txclass_fresh",
        "text": "everolimus",
        "label": "Everolimus",
        "category": "active",
    }
    monkeypatch.setattr(agent, "classify_treatments", lambda _profile: [fresh])
    monkeypatch.setattr(agent, "generate_executive_summary", lambda _profile: _summary())

    app_module._run_summary_job("summary-ok")

    saved = agent.load_profile()
    detail = client.get("/api/jobs/summary-ok").get_json()
    status = client.get("/api/status").get_json()

    assert detail["status"] == "done"
    assert detail["stage"] == "done"
    assert detail["result"]["classification_warning"] is None
    assert detail["result"]["treatments_classified"] == [fresh]
    assert saved["treatments_classification_job_id"] == "summary-ok"
    assert agent.treatment_classification_is_current(saved) is True
    assert [item["text"] for item in status["treatments_classified"]] == ["everolimus"]


@pytest.mark.parametrize("job_type", ["feed", "digest"])
def test_feed_and_digest_classification_failure_finish_with_warnings(
    app_client, agent, monkeypatch, job_type
):
    app_module, client = app_client
    seeded = _seed(agent)
    job_id = f"{job_type}-tce"
    _queue_job(app_module, job_id, job_type)
    monkeypatch.setattr(agent, "classify_treatments", _refusal(agent))
    monkeypatch.setattr(agent, "run_orchestrator", lambda *_args, **_kwargs: "## Summary\nreport")
    monkeypatch.setattr(agent, "poll_tracked_trials", lambda *_args, **_kwargs: {"changed": []})
    monkeypatch.setattr(agent, "generate_executive_summary", lambda _profile: _summary())
    payload = {
        "document_type": "lab_result",
        "date": "2026-08-01",
        "summary": "Lab imported before classification was skipped.",
        "biomarkers": [
            {"marker": "CgA", "value": 234, "unit": "ng/mL", "source_quote": "CgA 234 ng/mL"}
        ],
    }

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        if job_type == "feed":
            app_module._run_feed_job(job_id, "CgA 234 ng/mL")
        else:
            app_module._run_digest_job(job_id)

    saved = agent.load_profile()
    detail = client.get(f"/api/jobs/{job_id}").get_json()

    assert detail["status"] == "done"
    assert detail["stage"] == "done_with_warnings"
    assert detail.get("error_code") is None
    assert f"## Treatment classification warning\n{_WARNING}" in detail["report"]
    # Already-committed work and the refreshed assessment both survive.
    assert saved["executive_summary"]["summary"] == "Fresh summary"
    if job_type == "feed":
        assert saved["biomarkers"][0]["value"] == 234
    _assert_untouched(agent, saved, seeded)
    _assert_raw_fallback(client)
