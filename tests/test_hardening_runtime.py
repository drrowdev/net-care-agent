"""Regression tests for bounded jobs, hosted auth, artifacts, and PDF isolation."""

from __future__ import annotations

import base64
import json
import os
import threading
import time

import pytest


@pytest.fixture
def hardened_app(tmp_path, monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOCAL_AUTH_BYPASS", "1")
    monkeypatch.setenv("LEGACY_SYNC_JOB_RESPONSES", "0")
    for name in list(sys.modules):
        if name == "app" or name == "agent" or name.startswith("agent."):
            del sys.modules[name]
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    yield app_mod
    app_mod._shutdown_executors()


def test_bounded_executor_counts_active_work_as_capacity():
    from agent.job_runtime import BoundedExecutor, SaturatedError

    entered = threading.Event()
    release = threading.Event()
    executor = BoundedExecutor(workers=1, queue_size=0, name="test")
    executor.submit(lambda: (entered.set(), release.wait(2)))
    assert entered.wait(1)
    with pytest.raises(SaturatedError):
        executor.submit(lambda: None)
    release.set()
    executor.shutdown()


def test_executor_survives_unhandled_task_exception():
    from agent.job_runtime import BoundedExecutor

    completed = threading.Event()
    executor = BoundedExecutor(workers=1, queue_size=1, name="survival")
    executor.submit(lambda: (_ for _ in ()).throw(RuntimeError("task failed")))
    executor.submit(completed.set)
    assert completed.wait(1)
    executor.shutdown()


def test_saturation_returns_429_without_creating_job(hardened_app, monkeypatch):
    class Full:
        def submit(self, *_args, **_kwargs):
            from agent.job_runtime import SaturatedError

            raise SaturatedError

    client = hardened_app.app.test_client()
    client.get("/api/health")
    before = list(hardened_app._jobs)
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: Full())

    response = client.post("/api/digest")

    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert hardened_app._jobs == before


def test_submission_does_not_source_prune(hardened_app, monkeypatch):
    class CaptureExecutor:
        def submit(self, func):
            self.func = func

    executor = CaptureExecutor()
    pruned = []
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: executor)
    monkeypatch.setattr(hardened_app, "_prune_retention", lambda: None)
    monkeypatch.setattr(hardened_app, "_prune_sources_safely", lambda: pruned.append(True))

    job, rejection = hardened_app._submit_job("digest", lambda _job_id: None)

    assert rejection is None
    assert job["status"] == "queued"
    assert pruned == []


def test_duplicate_active_digest_is_rejected(hardened_app):
    hardened_app.app.test_client().get("/api/health")
    hardened_app._add_job(
        {
            "id": "active",
            "type": "digest",
            "status": "running",
            "stage": "orchestrating",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    response = hardened_app.app.test_client().post("/api/digest")
    assert response.status_code == 409
    assert response.get_json()["job_id"] == "active"


def _principal(value: dict) -> str:
    return base64.b64encode(json.dumps(value).encode()).decode()


def test_hosted_api_requires_valid_easy_auth(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    client = hardened_app.app.test_client()

    assert client.get("/api/status").status_code == 401
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": "not-base64"}).status_code
        == 401
    )
    valid = _principal({"userId": "allowed-id", "claims": []})
    assert client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL": valid}).status_code == 200


def test_hosted_allowlist_fails_closed(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_INSTANCE_ID", "instance")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_ALLOWED_PRINCIPAL_IDS", "allowed-id")
    client = hardened_app.app.test_client()
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "other-id"}).status_code
        == 403
    )
    assert (
        client.get("/api/status", headers={"X-MS-CLIENT-PRINCIPAL-ID": "allowed-id"}).status_code
        == 200
    )


def test_unhosted_principal_header_does_not_replace_explicit_bypass(hardened_app, monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_AUTH_BYPASS", raising=False)
    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-id"},
    )
    assert response.status_code == 401


def test_hosted_auth_disabled_fails_closed_and_ignores_fabricated_principal(
    hardened_app, monkeypatch
):
    monkeypatch.setenv("WEBSITE_SITE_NAME", "hosted")
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "false")
    response = hardened_app.app.test_client().get(
        "/api/status",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "spoofed-id"},
    )
    assert response.status_code == 503


def test_cross_origin_mutation_is_denied(hardened_app):
    response = hardened_app.app.test_client().post(
        "/api/digest", headers={"Origin": "https://attacker.example"}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("origin_env", "hostname", "origin"),
    [
        ("https://care.example", "ignored.azurewebsites.net", "https://care.example"),
        (None, "care.azurewebsites.net", "https://care.azurewebsites.net"),
    ],
)
def test_hosted_same_origin_uses_canonical_https_origin(
    hardened_app, monkeypatch, origin_env, hostname, origin
):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSITE_HOSTNAME", hostname)
    if origin_env:
        monkeypatch.setenv("APP_ORIGIN", origin_env)
    else:
        monkeypatch.delenv("APP_ORIGIN", raising=False)
    monkeypatch.setattr(
        hardened_app,
        "_submit_job",
        lambda *_args, **_kwargs: ({"id": "accepted"}, None),
    )
    response = hardened_app.app.test_client().post(
        "/api/digest",
        base_url="http://internal:8000",
        headers={
            "Origin": origin,
            "X-MS-CLIENT-PRINCIPAL-ID": "trusted-id",
        },
    )
    assert response.status_code == 202


def test_hosted_mutation_fails_closed_without_trusted_origin(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.delenv("WEBSITE_HOSTNAME", raising=False)
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "trusted-id"},
    )
    assert response.status_code == 403


def test_hosted_mutation_requires_origin_even_with_trusted_hostname(hardened_app, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WEBSITE_HOSTNAME", "care.azurewebsites.net")
    response = hardened_app.app.test_client().post(
        "/api/digest",
        headers={"X-MS-CLIENT-PRINCIPAL-ID": "trusted-id"},
    )
    assert response.status_code == 403


def test_prepare_failure_always_releases_admitted_worker(hardened_app, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    executor = hardened_app.BoundedExecutor(workers=1, queue_size=0, name="admission")
    monkeypatch.setattr(hardened_app, "_get_executor", lambda feed=False: executor)
    monkeypatch.setattr(
        hardened_app,
        "_save_jobs",
        lambda: (_ for _ in ()).throw(OSError("storage unavailable")),
    )

    with pytest.raises(OSError):
        hardened_app._submit_job(
            "digest",
            lambda _job_id: entered.set(),
            prepare=lambda _job: (_ for _ in ()).throw(RuntimeError("prepare failed")),
        )

    deadline = time.time() + 1
    while executor.counts() != (0, 0) and time.time() < deadline:
        time.sleep(0.01)
    assert executor.counts() == (0, 0)
    executor.submit(lambda: (entered.set(), release.wait(1)))
    assert entered.wait(1)
    release.set()
    executor.shutdown()


def test_pdf_subprocess_does_not_use_thread_unsafe_preexec():
    from agent import job_runtime

    source = __import__("inspect").getsource(job_runtime.extract_pdf_subprocess)
    assert "preexec_fn" not in source


def test_failed_job_quarantine_keeps_admission_disabled(hardened_app, monkeypatch):
    hardened_app.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.JOBS_PATH.write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(hardened_app, "_quarantine_jobs", lambda **_kwargs: False)

    assert hardened_app._load_jobs() is False
    assert hardened_app._jobs_healthy is False
    assert hardened_app.JOBS_PATH.read_text(encoding="utf-8") == "{bad"


def test_job_file_contains_only_metadata_and_detail_hydrates(hardened_app):
    report = hardened_app.DATA_DIR / "reports" / "r.txt"
    report.parent.mkdir(parents=True)
    report.write_text("private report", encoding="utf-8")
    hardened_app._add_job(
        {
            "id": "job1",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2026-07-11T08:00:00",
            "report": "must not persist",
            "input_preview": "must not persist",
            "traceback": "must not persist",
            "report_file": "reports/r.txt",
        }
    )
    stored = hardened_app.JOBS_PATH.read_text(encoding="utf-8")
    assert "private report" not in stored
    assert "preview" not in stored
    assert "traceback" not in stored
    detail = hardened_app.app.test_client().get("/api/jobs/job1").get_json()
    assert detail["report"] == "private report"


def test_legacy_job_history_is_sanitized_and_atomically_rewritten(hardened_app):
    hardened_app.JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.JOBS_PATH.write_text(
        json.dumps(
            [
                {
                    "id": "completed",
                    "type": "digest",
                    "status": "done",
                    "stage": "done",
                    "created_at": "2025-01-01T00:00:00",
                    "report": "legacy private report",
                    "input": "legacy private input",
                    "traceback": "legacy private trace",
                    "error": "legacy private error",
                    "error_code": "private_code",
                },
                {
                    "id": "failed",
                    "type": "digest",
                    "status": "error",
                    "stage": "error",
                    "created_at": "2025-01-01T00:00:00",
                    "error": "provider leaked details",
                    "error_code": "provider_internal",
                },
            ]
        ),
        encoding="utf-8",
    )

    assert hardened_app._load_jobs() is True

    stored_text = hardened_app.JOBS_PATH.read_text(encoding="utf-8")
    stored = json.loads(stored_text)
    assert "legacy private" not in stored_text
    assert "provider leaked" not in stored_text
    assert stored[0]["error"] is None
    assert "error_code" not in stored[0]
    assert stored[1]["error_code"] == "job_failed"
    assert stored[1]["error"] == "The job failed. Please retry."


def test_pdf_worker_uses_extractor_and_removes_upload(hardened_app, monkeypatch):
    job_id = "pdfjob"
    upload = hardened_app.DATA_DIR / "uploads" / job_id / "input.bin"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"%PDF fake")
    hardened_app._add_job(
        {
            "id": job_id,
            "type": "feed",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    called = []
    monkeypatch.setattr(
        hardened_app,
        "extract_pdf_subprocess",
        lambda *args, **kwargs: called.append((args, kwargs)) or "safe extracted text",
    )
    monkeypatch.setattr(hardened_app.agent, "load_profile", lambda: {})
    monkeypatch.setattr(
        hardened_app.agent,
        "run_intake",
        lambda text, profile, **kwargs: (
            profile,
            {"document_type": "other", "source_document_id": "doc_test"},
        ),
    )
    monkeypatch.setattr(hardened_app.agent, "save_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(hardened_app.agent, "run_orchestrator", lambda *_args: "report")
    monkeypatch.setattr(hardened_app.agent, "classify_treatments", lambda _profile: [])
    monkeypatch.setattr(hardened_app, "_refresh_summary", lambda _profile: None)
    monkeypatch.setattr(hardened_app, "_prune_retention", lambda: None)

    hardened_app._run_feed_job(job_id, None, "job-upload", "document.pdf", "application/pdf")

    assert called
    assert not upload.parent.exists()
    assert hardened_app._jobs[0]["status"] == "done"


def test_retention_never_prunes_profile_referenced_source(hardened_app, monkeypatch):
    source_root = hardened_app.DATA_DIR / "source_documents"
    protected = source_root / "doc_protected"
    orphan = source_root / "doc_orphan"
    protected.mkdir(parents=True)
    orphan.mkdir()
    old = time.time() - 10 * 86400
    os.utime(protected, (old, old))
    os.utime(orphan, (old, old))
    hardened_app.agent.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.agent.PROFILE_PATH.write_text(
        json.dumps({"patient": {}, "source_documents": [{"id": "doc_protected"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_DAYS", "1")
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_COUNT", "0")

    hardened_app._prune_sources_safely()

    assert protected.exists()
    assert not orphan.exists()


def test_source_pruning_waits_for_ingestion_profile_commit(hardened_app, monkeypatch):
    source = hardened_app.DATA_DIR / "source_documents" / "doc_ingesting"
    source.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(source, (old, old))
    hardened_app.agent.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    hardened_app.agent.PROFILE_PATH.write_text(
        json.dumps({"patient": {}, "source_documents": []}), encoding="utf-8"
    )
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_DAYS", "1")
    monkeypatch.setenv("SOURCE_ORPHAN_RETENTION_COUNT", "0")
    entered = threading.Event()
    finish_ingestion = threading.Event()

    def ingest() -> None:
        with hardened_app.agent.serialized_mutation():
            entered.set()
            assert finish_ingestion.wait(2)
            hardened_app.agent.PROFILE_PATH.write_text(
                json.dumps(
                    {
                        "patient": {},
                        "source_documents": [{"id": "doc_ingesting"}],
                    }
                ),
                encoding="utf-8",
            )

    ingest_thread = threading.Thread(target=ingest)
    prune_thread = threading.Thread(target=hardened_app._prune_sources_safely)
    ingest_thread.start()
    assert entered.wait(1)
    prune_thread.start()
    time.sleep(0.05)
    assert prune_thread.is_alive()
    assert source.exists()
    finish_ingestion.set()
    ingest_thread.join(2)
    prune_thread.join(2)
    assert not ingest_thread.is_alive()
    assert not prune_thread.is_alive()
    assert source.exists()


def test_report_retention_clears_index_before_pruning(hardened_app, monkeypatch):
    report = hardened_app.DATA_DIR / "reports" / "old.txt"
    report.parent.mkdir(parents=True)
    report.write_text("sensitive output", encoding="utf-8")
    hardened_app._add_job(
        {
            "id": "old-report",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2020-01-01T00:00:00",
            "report_file": "reports/old.txt",
        }
    )
    monkeypatch.setenv("REPORT_RETENTION_DAYS", "1")
    monkeypatch.setenv("JOB_RETENTION_DAYS", "36500")

    hardened_app._prune_retention()

    assert not report.exists()
    assert "report_file" not in hardened_app._jobs[0]
    assert "reports/old.txt" not in hardened_app.JOBS_PATH.read_text(encoding="utf-8")


def test_timeout_failure_is_sanitized_in_job_metadata(hardened_app, monkeypatch):
    hardened_app._add_job(
        {
            "id": "timeout-job",
            "type": "chat",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-07-11T08:00:00",
        }
    )
    monkeypatch.setattr(hardened_app.agent, "load_profile", lambda: {})
    monkeypatch.setattr(
        hardened_app.agent,
        "handle_chat",
        lambda *_args: (_ for _ in ()).throw(TimeoutError("private upstream detail")),
    )

    hardened_app._run_chat_job("timeout-job", "question", [])

    job = hardened_app._jobs[0]
    assert job["status"] == "error"
    assert job["error_code"] == "upstream_timeout"
    assert job["error"] == "The AI service timed out. Please retry."
    assert "private upstream detail" not in hardened_app.JOBS_PATH.read_text(encoding="utf-8")


def test_anthropic_defaults_use_bounded_operation_and_overall_timeouts(monkeypatch):
    import importlib

    import agent.llm as llm

    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(llm.anthropic, "Anthropic", fake_client)
    for name in (
        "ANTHROPIC_CONNECT_TIMEOUT_SECONDS",
        "ANTHROPIC_READ_TIMEOUT_SECONDS",
        "ANTHROPIC_OVERALL_TIMEOUT_SECONDS",
        "ANTHROPIC_MAX_RETRIES",
    ):
        monkeypatch.delenv(name, raising=False)
    importlib.reload(llm)

    assert captured["max_retries"] == 0
    assert captured["timeout"].connect == 5.0
    assert captured["timeout"].read == 120.0
    assert captured["timeout"].write == 10.0
    assert captured["timeout"].pool == 5.0
    assert isinstance(captured["http_client"], llm.httpx.Client)
    assert isinstance(captured["http_client"]._transport, llm.OverallTimeoutTransport)
    assert captured["http_client"]._transport._timeout_seconds == 180.0
    assert all(
        timeout <= captured["http_client"]._transport._timeout_seconds
        for timeout in (
            captured["timeout"].connect,
            captured["timeout"].read,
            captured["timeout"].write,
            captured["timeout"].pool,
        )
    )
    captured["http_client"].close()
