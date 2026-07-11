#!/usr/bin/env python3
"""
NET Care Agent — Web UI backend
Deployed on Azure App Service (swedencentral)
Data persisted to /home/data (Azure Files mount)
"""

import atexit
import base64
import datetime
import hashlib
import io
import json
import os
import shutil
import sys
import threading
import time
from functools import wraps
from pathlib import Path

# Load .env for local development. On Azure App Service, env vars come from
# Application Settings and this is a no-op.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import argparse

from flask import Flask, jsonify, request, send_file, send_from_directory

_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--agent-dir", default=".", help="Directory containing net_agent.py")
_ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
_args, _ = _ap.parse_known_args()
sys.path.insert(0, str(Path(_args.agent_dir).resolve()))

try:
    import net_agent as agent
except Exception as exc:
    print(f"ERROR: Could not import net_agent.py — {type(exc).__name__}")
    sys.exit(1)

# Configure logging once Anthropic + dotenv are loaded.
from agent.io import atomic_write_bytes, atomic_write_text  # noqa: E402
from agent.job_runtime import (  # noqa: E402
    BoundedExecutor,
    SaturatedError,
    extract_pdf_subprocess,
    prune_orphan_sources,
    safe_artifact_path,
    write_json_artifact,
)
from agent.logging_config import configure_logging  # noqa: E402
from agent.provenance import resolve_source_artifact, validate_source_artifact  # noqa: E402
from agent.schema import now_stamp  # noqa: E402

configure_logging()
log = __import__("logging").getLogger("netcare.app")

# Read package version for /api/health
try:
    from importlib.metadata import version as _pkg_version

    APP_VERSION = _pkg_version("net-care-agent")
except Exception:
    APP_VERSION = "0.0.0+unknown"
try:
    RELEASE_COMMIT = Path("RELEASE_COMMIT").read_text(encoding="ascii").strip()
except OSError:
    RELEASE_COMMIT = "development"

app = Flask(__name__, static_folder="static", template_folder="static")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Multipart framing adds a small amount beyond the file itself. Keep the exact
# per-file limit below while allowing bounded protocol overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "100"))
MAX_EXTRACTED_TEXT_CHARS = int(os.environ.get("MAX_EXTRACTED_TEXT_CHARS", "1000000"))
PDF_PARSE_TIMEOUT_SECONDS = int(os.environ.get("PDF_PARSE_TIMEOUT_SECONDS", "30"))

# ── persistent storage ───────────────────────────────────────────────────────
# Default to /home/data (Azure Files mount on App Service).
# Override with DATA_DIR env var for local development.
# mkdir is deferred to runtime (inside functions) so a missing mount
# at import time does not crash the worker before gunicorn can start.
DATA_DIR = Path(os.environ.get("DATA_DIR", "/home/data"))
JOBS_PATH = DATA_DIR / "jobs.json"

_jobs: list[dict] = []
_jobs_lock = threading.Lock()
_initialized = False
_jobs_healthy: bool = True  # set False when jobs.json is quarantined on load
_admission_lock = threading.Lock()
_executor_lock = threading.Lock()
_job_executor: BoundedExecutor | None = None
_feed_executor: BoundedExecutor | None = None

_JOB_FIELDS = {
    "id",
    "type",
    "status",
    "stage",
    "created_at",
    "started_at",
    "finished_at",
    "report_file",
    "result_file",
    "source_document_id",
    "retry_guidance",
    "error_code",
    "error",
}
_ACTIVE_STATUSES = {"queued", "running"}
_SAFE_JOB_ERRORS = {
    "job_failed": "The job failed. Please retry.",
    "upstream_timeout": "The AI service timed out. Please retry.",
    "pdf_timeout": "PDF processing timed out.",
    "pdf_invalid": "PDF could not be processed within safety limits.",
    "pdf_text_limit": "PDF could not be processed within safety limits.",
}
_INTERRUPTED_GUIDANCE = (
    "This job was interrupted by a server restart. Re-submit the same request to retry."
)


def _get_executor(feed: bool = False) -> BoundedExecutor:
    global _job_executor, _feed_executor
    with _executor_lock:
        if feed:
            if _feed_executor is None:
                _feed_executor = BoundedExecutor(
                    workers=int(os.environ.get("FEED_WORKERS", "1")),
                    queue_size=int(os.environ.get("FEED_QUEUE_SIZE", "2")),
                    name="feed-job",
                )
            return _feed_executor
        if _job_executor is None:
            _job_executor = BoundedExecutor(
                workers=int(os.environ.get("JOB_WORKERS", "2")),
                queue_size=int(os.environ.get("JOB_QUEUE_SIZE", "6")),
                name="job",
            )
        return _job_executor


def _shutdown_executors() -> None:
    for executor in (_feed_executor, _job_executor):
        if executor is not None:
            executor.shutdown(wait=True)


atexit.register(_shutdown_executors)


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_jobs() -> bool:
    """Load and reconcile jobs from disk on startup.

    Three outcomes:
    - File missing → no-op (_jobs stays []).
    - File readable + valid JSON list → loaded.  Queued/running jobs are
      marked ``interrupted`` (persisted once, no traceback exposed).
    - File corrupt (bad JSON or not a list) → atomically quarantined, _jobs
      reset to [], _jobs_healthy set False so /api/health discloses degradation.

    Never calls _ensure_data_dir() here — may run at import time on some code
    paths, and the Azure Files mount may not be ready yet.

    All global state mutations (_jobs, _jobs_healthy) and the reconciliation
    persistence are performed under _jobs_lock so the assignment, reconciliation,
    and save are a single atomic unit from other threads' perspective.
    _save_jobs does not acquire _jobs_lock, so there is no deadlock risk.
    """
    global _jobs, _jobs_healthy
    if not JOBS_PATH.exists():
        with _jobs_lock:
            _jobs = []
            _jobs_healthy = True
        return True

    try:
        raw = JOBS_PATH.read_bytes()
    except OSError as exc:
        log.warning("jobs_read_failed type=%s", type(exc).__name__)
        with _jobs_lock:
            _jobs_healthy = False
        return False

    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        with _jobs_lock:
            if not _quarantine_jobs(raw_bytes=raw, reason="json_decode_error"):
                _jobs_healthy = False
                return False
            _jobs = []
            _jobs_healthy = False
        return True

    if not isinstance(loaded, list):
        with _jobs_lock:
            if not _quarantine_jobs(raw_bytes=raw, reason="not_a_list"):
                _jobs_healthy = False
                return False
            _jobs = []
            _jobs_healthy = False
        return True

    if not all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("status"), str)
        for item in loaded
    ):
        with _jobs_lock:
            if not _quarantine_jobs(raw_bytes=raw, reason="invalid_job_entry"):
                _jobs_healthy = False
                return False
            _jobs = []
            _jobs_healthy = False
        return True

    with _jobs_lock:
        _jobs = [_clean_job(item) for item in loaded]
        _jobs_healthy = True

        # Reconcile: any job that was queued or running when the process last
        # died is now interrupted.  Persist once, expose retry guidance, no
        # traceback.
        now_str = datetime.datetime.now().isoformat(timespec="seconds")
        needs_save = _jobs != loaded
        for j in _jobs:
            if j.get("status") in ("queued", "running"):
                j["status"] = "interrupted"
                j["finished_at"] = j.get("finished_at") or now_str
                j["stage"] = "interrupted"
                j["error_code"] = "job_interrupted"
                j["error"] = "The job was interrupted by a server restart."
                j["retry_guidance"] = _INTERRUPTED_GUIDANCE
                needs_save = True

        if needs_save:
            try:
                _save_jobs()
            except Exception as exc:
                log.warning("jobs_reconcile_save_failed type=%s", type(exc).__name__)
                _jobs_healthy = False
                return False
    return True


def _quarantine_jobs(*, raw_bytes: bytes, reason: str) -> bool:
    """Move corrupt jobs.json to the quarantine directory (best-effort).

    Logs only the quarantine filename and a hash prefix — no job data or paths.
    """
    from agent import config as agent_config

    qdir = agent_config.DATA_DIR / "quarantine"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    h = hashlib.sha256(raw_bytes).hexdigest()[:8] if raw_bytes else "empty"
    try:
        qdir.mkdir(parents=True, exist_ok=True)
        qpath = qdir / f"jobs_{ts}_{h}.json"
        atomic_write_bytes(qpath, raw_bytes)
        JOBS_PATH.unlink(missing_ok=True)
        log.warning("jobs_quarantined reason=%s file=%s hash_prefix=%s", reason, qpath.name, h)
        return True
    except OSError as exc:
        log.error("jobs_quarantine_failed reason=%s type=%s", reason, type(exc).__name__)
        return False


def _save_jobs():
    _ensure_data_dir()
    atomic_write_text(JOBS_PATH, json.dumps(_jobs, separators=(",", ":"), default=str))


def _clean_job(job: dict) -> dict:
    clean = {key: value for key, value in job.items() if key in _JOB_FIELDS}
    status = clean.get("status")
    if status == "error":
        code = clean.get("error_code")
        if code not in _SAFE_JOB_ERRORS:
            code = "job_failed"
        clean["error_code"] = code
        clean["error"] = _SAFE_JOB_ERRORS[code]
    elif status == "interrupted":
        clean["error_code"] = "job_interrupted"
        clean["error"] = "The job was interrupted by a server restart."
        clean["retry_guidance"] = _INTERRUPTED_GUIDANCE
    else:
        clean.pop("error_code", None)
        clean.pop("retry_guidance", None)
        clean["error"] = None
    return clean


def _add_job(job: dict):
    with _jobs_lock:
        _jobs.insert(0, _clean_job(job))
        _save_jobs()


def _update_job(job_id: str, updates: dict):
    with _jobs_lock:
        for j in _jobs:
            if j["id"] == job_id:
                j.update({key: value for key, value in updates.items() if key in _JOB_FIELDS})
                cleaned = _clean_job(j)
                j.clear()
                j.update(cleaned)
                break
        _save_jobs()


def _safe_error_code(exc: BaseException) -> tuple[str, str]:
    code = str(exc) if str(exc) in {"pdf_timeout", "pdf_invalid", "pdf_text_limit"} else ""
    if code == "pdf_timeout":
        return code, "PDF processing timed out."
    if code in {"pdf_invalid", "pdf_text_limit"}:
        return code, "PDF could not be processed within safety limits."
    if "timeout" in type(exc).__name__.lower():
        return "upstream_timeout", "The AI service timed out. Please retry."
    return "job_failed", "The job failed. Please retry."


def _fail_job(job_id: str, exc: BaseException) -> None:
    code, message = _safe_error_code(exc)
    log.warning("job_failed id=%s code=%s type=%s", job_id, code, type(exc).__name__)
    _update_job(
        job_id,
        {
            "status": "error",
            "stage": "error",
            "error_code": code,
            "error": message,
            "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
        },
    )


def _submit_job(
    job_type: str,
    target,
    *args,
    feed: bool = False,
    unique_active: bool = False,
    prepare=None,
) -> tuple[dict | None, tuple | None]:
    """Atomically admit bounded work before creating durable job metadata."""
    _prune_retention()
    executor = _get_executor(feed)
    gate = threading.Event()
    cancelled = threading.Event()
    job = {
        "id": _new_id(),
        "type": job_type,
        "status": "queued",
        "stage": "queued",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "error": None,
    }

    def run_after_persist() -> None:
        gate.wait()
        if not cancelled.is_set():
            target(job["id"], *args)

    with _admission_lock:
        if unique_active:
            with _jobs_lock:
                existing = next(
                    (
                        item
                        for item in _jobs
                        if item.get("type") == job_type and item.get("status") in _ACTIVE_STATUSES
                    ),
                    None,
                )
            if existing:
                return None, (
                    jsonify({"error": "An active job of this type already exists.", "job_id": existing["id"]}),
                    409,
                )
        try:
            executor.submit(run_after_persist)
        except SaturatedError:
            response = jsonify({"error": "Job queue is full. Please retry shortly."})
            response.headers["Retry-After"] = os.environ.get("RETRY_AFTER_SECONDS", "10")
            return None, (response, 429)
        try:
            _add_job(job)
            if prepare is not None:
                prepare(job)
        except BaseException:
            cancelled.set()
            try:
                with _jobs_lock:
                    _jobs[:] = [item for item in _jobs if item.get("id") != job["id"]]
                    _save_jobs()
            finally:
                gate.set()
            raise
        gate.set()
    return job, None


def _artifact_ref(path: Path) -> str:
    return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()


def _write_job_result(job_id: str, value: object) -> str:
    path = DATA_DIR / "job_results" / f"{job_id}.json"
    write_json_artifact(path, value)
    return _artifact_ref(path)


def _job_response(job: dict, *, include_artifacts: bool = False) -> dict:
    response = dict(job)
    if not include_artifacts:
        return response
    report_ref = job.get("report_file")
    if report_ref:
        try:
            response["report"] = safe_artifact_path(DATA_DIR, report_ref, {"reports"}).read_text(
                encoding="utf-8"
            )
        except (OSError, ValueError):
            response["artifact_unavailable"] = True
    result_ref = job.get("result_file")
    if result_ref:
        try:
            response["result"] = json.loads(
                safe_artifact_path(DATA_DIR, result_ref, {"job_results"}).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError):
            response["artifact_unavailable"] = True
    return response


def _legacy_sync_result(job_id: str):
    """Compatibility response used only when explicitly enabled."""
    if os.environ.get("LEGACY_SYNC_JOB_RESPONSES", "").lower() not in {"1", "true", "yes"}:
        return None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with _jobs_lock:
            job = next((item for item in _jobs if item.get("id") == job_id), None)
            snapshot = dict(job) if job else None
        if snapshot and snapshot.get("status") == "done":
            return _job_response(snapshot, include_artifacts=True).get("result")
        if snapshot and snapshot.get("status") in {"error", "interrupted"}:
            return {"error": snapshot.get("error") or "The job failed."}
        time.sleep(0.01)
    return {"error": "The job is still running.", "job_id": job_id}


def _prune_retention() -> None:
    """Prune job metadata and report/result artifacts, but never source evidence."""
    now = time.time()
    job_days = max(1, int(os.environ.get("JOB_RETENTION_DAYS", "365")))
    job_count = max(1, int(os.environ.get("JOB_RETENTION_COUNT", "200")))
    removed: list[dict] = []
    with _jobs_lock:
        kept = []
        for index, job in enumerate(_jobs):
            try:
                age = now - datetime.datetime.fromisoformat(job.get("created_at", "")).timestamp()
            except (TypeError, ValueError):
                age = job_days * 86400 + 1
            if job.get("status") not in _ACTIVE_STATUSES and (
                index >= job_count or age > job_days * 86400
            ):
                removed.append(job)
            else:
                kept.append(job)
        if removed:
            _jobs[:] = kept
            _save_jobs()
    for job in removed:
        for field, roots in (("report_file", {"reports"}), ("result_file", {"job_results"})):
            if job.get(field):
                try:
                    safe_artifact_path(DATA_DIR, job[field], roots).unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass

    def prune_artifacts(field: str, root_name: str, age_days: int, max_count: int) -> None:
        root = DATA_DIR / root_name
        refs_to_delete: list[str] = []
        changed = False
        with _jobs_lock:
            referenced = [job for job in _jobs if job.get(field)]
            for index, job in enumerate(referenced):
                try:
                    age = now - datetime.datetime.fromisoformat(
                        job.get("created_at", "")
                    ).timestamp()
                except (TypeError, ValueError):
                    age = age_days * 86400 + 1
                if index >= max_count or age > age_days * 86400:
                    refs_to_delete.append(job.pop(field))
                    changed = True
            if changed:
                _save_jobs()
            indexed = {job.get(field) for job in _jobs if job.get(field)}
        for reference in refs_to_delete:
            try:
                safe_artifact_path(DATA_DIR, reference, {root_name}).unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        if not root.is_dir():
            return
        try:
            files = sorted(
                (path for path in root.iterdir() if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        unindexed = [path for path in files if _artifact_ref(path) not in indexed]
        cutoff = now - age_days * 86400
        for index, path in enumerate(unindexed):
            try:
                if index >= max_count or path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    prune_artifacts(
        "report_file",
        "reports",
        max(1, int(os.environ.get("REPORT_RETENTION_DAYS", "30"))),
        max(1, int(os.environ.get("REPORT_RETENTION_COUNT", "200"))),
    )
    prune_artifacts("result_file", "job_results", job_days, job_count)


def _prune_source_retention() -> None:
    """Prune orphan evidence while the caller holds the profile mutation lock."""
    try:
        profile = json.loads(agent.PROFILE_PATH.read_bytes())
    except (OSError, ValueError, json.JSONDecodeError):
        return
    protected_ids = {
        source.get("id")
        for source in profile.get("source_documents", [])
        if isinstance(source, dict) and source.get("id")
    }
    prune_orphan_sources(
        DATA_DIR,
        protected_ids,
        age_days=int(os.environ.get("SOURCE_ORPHAN_RETENTION_DAYS", "7")),
        max_count=int(os.environ.get("SOURCE_ORPHAN_RETENTION_COUNT", "20")),
    )


def _prune_sources_safely() -> None:
    with agent.serialized_mutation():
        _prune_source_retention()


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def serialized_profile_mutation(func):
    """Serialize a Flask route's complete profile load-mutate-save transaction."""

    @wraps(func)
    def wrapped(*args, **kwargs):
        with agent.serialized_mutation():
            return func(*args, **kwargs)

    return wrapped


def _refresh_summary(profile: dict) -> str | None:
    """Refresh the summary in-place, preserving prior content on LLM failure."""
    generated = agent.generate_executive_summary(profile)
    failure = generated.get("generation_failed") if isinstance(generated, dict) else True
    if failure:
        generated_message = generated.get("summary", "") if isinstance(generated, dict) else ""
        message = (
            "Summary generation was truncated at max_tokens."
            if "max_tokens" in generated_message.lower() or "truncated" in generated_message.lower()
            else "Summary generation failed."
        )
        existing = profile.get("executive_summary")
        if isinstance(existing, dict):
            existing["stale"] = True
            existing["summary_error"] = message
        else:
            generated["stale"] = True
            generated["summary_error"] = message
            profile["executive_summary"] = generated
        profile["summary_stale"] = True
        return message

    generated["summary_revision"] = int(profile.get("profile_revision") or 0) + 1
    generated["generated_at_timestamp"] = now_stamp()
    generated["feedback_ids_considered"] = [
        item.get("id")
        for item in profile.get("feedback", [])
        if item.get("id") and item.get("assessment") in {"corrected", "incorrect", "missed"}
    ]
    generated["judgment_context_hash"] = agent.clinical_judgments_fingerprint(profile)
    generated["stale"] = False
    generated.pop("summary_error", None)
    profile["executive_summary"] = generated
    profile["summary_stale"] = False
    return None


# ── background workers ────────────────────────────────────────────────────────
def _run_feed_job(
    job_id: str,
    text: str | None,
    upload_ref: str | None = None,
    filename: str | None = None,
    media_type: str = "text/plain",
):
    # P6: serialize profile-mutating jobs so a concurrent feed+digest can't
    # silently lose one job's extracted data (last-writer-wins on the JSON file).
    try:
        raw_bytes = None
        upload_dir = None
        if upload_ref == "job-upload":
            upload_ref = f"uploads/{job_id}/input.bin"
        if upload_ref:
            upload_path = safe_artifact_path(DATA_DIR, upload_ref, {"uploads"})
            upload_dir = upload_path.parent
            raw_bytes = upload_path.read_bytes()
            if (filename or "").lower().endswith(".pdf"):
                extracted_path = upload_dir / "extracted.txt"
                text = extract_pdf_subprocess(
                    upload_path,
                    extracted_path,
                    timeout_seconds=PDF_PARSE_TIMEOUT_SECONDS,
                    max_pages=MAX_PDF_PAGES,
                    max_chars=MAX_EXTRACTED_TEXT_CHARS,
                )
            else:
                text = raw_bytes.decode("utf-8", errors="replace")
                if len(text) > MAX_EXTRACTED_TEXT_CHARS:
                    raise RuntimeError("pdf_text_limit")
        if not text or not text.strip():
            raise RuntimeError("pdf_invalid")
        with agent.serialized_mutation(
            lambda: _update_job(
                job_id,
                {"status": "running", "stage": "waiting for current job"},
            )
        ):
            _update_job(job_id, {"status": "running", "stage": "intake"})
            profile = agent.load_profile()
            if raw_bytes is None and filename is None:
                profile, extracted = agent.run_intake(text, profile)
            else:
                profile, extracted = agent.run_intake(
                    text,
                    profile,
                    raw_bytes=raw_bytes,
                    filename=filename,
                    media_type=media_type,
                )
            # Commit intake before research. A later orchestrator/model failure
            # must not lose an already-extracted clinical document.
            try:
                agent.save_profile(profile)
            except BaseException:
                source_id = extracted.get("source_document_id")
                source = next(
                    (
                        item
                        for item in profile.get("source_documents", [])
                        if item.get("id") == source_id
                    ),
                    None,
                )
                if source is not None:
                    agent.remove_source_document(source)
                raise

            _update_job(
                job_id,
                {
                    "stage": "orchestrating",
                    "document_type": extracted.get("document_type", "unknown"),
                    "summary": extracted.get("summary", ""),
                    "key_findings": extracted.get("key_findings", []),
                    "source_document_id": extracted.get("source_document_id"),
                    "ingested_at": extracted.get("ingested_at"),
                },
            )

            report = agent.run_orchestrator(profile, extracted)
            _update_job(job_id, {"stage": "classifying"})
            profile["treatments_classified"] = agent.classify_treatments(profile)
            _update_job(job_id, {"stage": "refreshing summary"})
            summary_error = _refresh_summary(profile)
            agent.save_profile(profile)
            _prune_source_retention()

            reports_dir = DATA_DIR / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rpath = reports_dir / f"report_feed_{stamp}.txt"
            if summary_error:
                report += f"\n\n## Summary refresh warning\n{summary_error}"
            atomic_write_text(rpath, report)

            _update_job(
                job_id,
                {
                    "status": "done",
                    "stage": "done_with_warnings" if summary_error else "done",
                    "report_file": _artifact_ref(rpath),
                    "summary_error": summary_error,
                    "finished_at": datetime.datetime.now().isoformat(),
                },
            )

    except Exception as exc:
        _fail_job(job_id, exc)
    finally:
        if upload_ref == "job-upload":
            upload_ref = f"uploads/{job_id}/input.bin"
        if upload_ref:
            try:
                shutil.rmtree(safe_artifact_path(DATA_DIR, upload_ref, {"uploads"}).parent)
            except (OSError, ValueError):
                pass


def _run_digest_job(job_id: str):
    try:
        with agent.serialized_mutation(
            lambda: _update_job(
                job_id,
                {"status": "running", "stage": "waiting for current job"},
            )
        ):
            _update_job(job_id, {"status": "running", "stage": "orchestrating"})
            profile = agent.load_profile()
            # P5: deterministically poll tracked-trial statuses before the LLM pass so
            # status changes become alerts (and reach the orchestrator) even though the
            # dedup logic would otherwise suppress already-tracked trials.
            try:
                poll = agent.poll_tracked_trials(profile)
                if poll["changed"]:
                    _update_job(job_id, {"stage": f"trial updates: {len(poll['changed'])}"})
            except Exception as exc:
                log.warning("trial_poll_skipped type=%s", type(exc).__name__)
            extracted = {
                "document_type": "scheduled_digest",
                "summary": "Manual research digest",
                "key_findings": [],
                "suggested_workflows": ["pubmed_search", "trial_search", "biomarker_analysis"],
                "workflow_rationale": (
                    "Comprehensive review: search new NET literature, "
                    "check European trials, review biomarker trends."
                ),
            }
            report = agent.run_orchestrator(profile, extracted)
            _update_job(job_id, {"stage": "classifying"})
            profile["treatments_classified"] = agent.classify_treatments(profile)
            _update_job(job_id, {"stage": "refreshing summary"})
            summary_error = _refresh_summary(profile)
            agent.save_profile(profile)

            reports_dir = DATA_DIR / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rpath = reports_dir / f"report_digest_{stamp}.txt"
            if summary_error:
                report += f"\n\n## Summary refresh warning\n{summary_error}"
            atomic_write_text(rpath, report)

            _update_job(
                job_id,
                {
                    "status": "done",
                    "stage": "done_with_warnings" if summary_error else "done",
                    "report_file": _artifact_ref(rpath),
                    "summary_error": summary_error,
                    "finished_at": datetime.datetime.now().isoformat(),
                },
            )

    except Exception as exc:
        _fail_job(job_id, exc)


def _run_deepsweep_job(job_id: str):
    """Ensemble deep-sweep: multi-model exploratory research pass.

    Deliberately READ-ONLY — it never calls save_profile(), so re-surfaced
    papers/trials/alerts do not pollute the tracked lists. Produces a unioned
    report artifact for pre-appointment prep only.
    """
    try:
        _update_job(job_id, {"status": "running", "stage": "deep-sweep"})
        profile = agent.load_profile()
        result = agent.run_deep_sweep(profile)  # non-mutating; profile NOT saved
        report = result["report"]

        reports_dir = DATA_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rpath = reports_dir / f"report_deepsweep_{stamp}.md"
        atomic_write_text(rpath, report)

        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "report_file": _artifact_ref(rpath),
                "cost_total": result.get("cost_total"),
                "finished_at": datetime.datetime.now().isoformat(),
            },
        )

    except Exception as exc:
        _fail_job(job_id, exc)


def _run_questions_job(job_id: str, appointment_type: str) -> None:
    try:
        _update_job(job_id, {"status": "running", "stage": "generating", "started_at": now_stamp()})
        with agent.serialized_mutation():
            profile = agent.load_profile()
            new_questions = agent.generate_questions_for_profile(profile, appointment_type)
            existing = profile.get("appointment_questions", [])
            preserved = [q for q in existing if q.get("source") == "manual" or q.get("asked")]
            used_ids = {q.get("id") for q in preserved if q.get("id")}
            seen = {
                " ".join((q.get("text") or "").split()).casefold()
                for q in preserved
                if (q.get("text") or "").strip()
            }
            merged = list(preserved)
            for question in new_questions:
                key = " ".join((question.get("text") or "").split()).casefold()
                if key and key not in seen:
                    candidate = dict(question)
                    if not candidate.get("id") or candidate["id"] in used_ids:
                        candidate["id"] = f"q_{_new_id()}"
                    used_ids.add(candidate["id"])
                    merged.append(candidate)
                    seen.add(key)
            profile["appointment_questions"] = merged
            agent.save_profile(profile, clinical_change=False)
        result_ref = _write_job_result(job_id, {"questions": merged})
        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "result_file": result_ref,
                "finished_at": now_stamp(),
            },
        )
    except Exception as exc:
        _fail_job(job_id, exc)


def _run_summary_job(job_id: str) -> None:
    try:
        _update_job(job_id, {"status": "running", "stage": "generating", "started_at": now_stamp()})
        with agent.serialized_mutation():
            profile = agent.load_profile()
            classified_txs = agent.classify_treatments(profile)
            profile["treatments_classified"] = classified_txs
            summary_error = _refresh_summary(profile)
            agent.save_profile(profile)
            result = {
                "summary": profile["executive_summary"],
                "treatments_classified": classified_txs,
                "summary_error": summary_error,
                "profile_revision": profile["profile_revision"],
            }
        result_ref = _write_job_result(job_id, result)
        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "result_file": result_ref,
                "finished_at": now_stamp(),
            },
        )
    except Exception as exc:
        _fail_job(job_id, exc)


def _run_chat_job(job_id: str, user_message: str, history: list) -> None:
    try:
        _update_job(job_id, {"status": "running", "stage": "answering", "started_at": now_stamp()})
        profile = agent.load_profile()
        reply = agent.handle_chat(profile, user_message, history)
        result_ref = _write_job_result(job_id, {"reply": reply})
        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "result_file": result_ref,
                "finished_at": now_stamp(),
            },
        )
    except Exception as exc:
        _fail_job(job_id, exc)


# ── API routes ────────────────────────────────────────────────────────────────
@app.after_request
def _add_cache_headers(response):
    """
    Cache hints for static assets.

    - /static/*: short cache (5 min) + revalidate via ETag (Flask sends ETag
      automatically). Long enough to be worthwhile, short enough that a deploy
      of new index.html / app.js / styles.css is picked up promptly without
      manual cache busting.
    - /api/*: never cache.
    """
    path = request.path
    if path.startswith("/static/"):
        # Override Flask's default no-cache on static files. Short cache + ETag
        # gives near-zero overhead repeat-loads while still picking up deploys
        # within 5 minutes (and immediately if the ETag changes mid-window).
        response.headers["Cache-Control"] = "public, max-age=300, must-revalidate"
    elif path.startswith("/api/") or path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        # TODO: remove script unsafe-inline after legacy event attributes in
        # static/index.html are migrated to delegated app.js listeners.
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    return response


@app.errorhandler(413)
def _upload_too_large(_error):
    return jsonify({"error": "File exceeds the 20 MB upload limit"}), 413


@app.errorhandler(agent.ProfileLoadError)
def _profile_unavailable(error):
    log.error("profile_unavailable type=%s", type(error).__name__)
    return jsonify(
        {
            "error": "Patient record is temporarily unavailable.",
            "retryable": isinstance(error, agent.IOProfileError),
        }
    ), 503


@app.before_request
def _lazy_init():
    """Load jobs on the first real request — by then Azure Files is mounted."""
    global _initialized
    if not _initialized:
        loaded = _load_jobs()
        _initialized = loaded
        if loaded:
            _prune_retention()
            _prune_sources_safely()
        if not loaded and request.path not in {"/api/live", "/api/health"}:
            return jsonify(
                {
                    "error": "Job history storage is temporarily unavailable.",
                    "retryable": True,
                }
            ), 503


def _easy_auth_enabled() -> bool:
    return os.environ.get("WEBSITE_AUTH_ENABLED", "").strip().lower() == "true"


def _is_hosted() -> bool:
    return _easy_auth_enabled() or any(
        os.environ.get(name)
        for name in ("WEBSITE_INSTANCE_ID", "WEBSITE_SITE_NAME", "WEBSITE_HOSTNAME")
    )


def _principal_id() -> str | None:
    stable = (request.headers.get("X-MS-CLIENT-PRINCIPAL-ID") or "").strip()
    encoded = (request.headers.get("X-MS-CLIENT-PRINCIPAL") or "").strip()
    if encoded:
        try:
            decoded = base64.b64decode(encoded, validate=True)
            principal = json.loads(decoded)
            if not isinstance(principal, dict):
                return None
            claims = principal.get("claims")
            if claims is not None and not isinstance(claims, list):
                return None
            ids = [
                claim.get("val")
                for claim in (claims or [])
                if isinstance(claim, dict)
                and claim.get("typ", "").lower()
                in {
                    "http://schemas.microsoft.com/identity/claims/objectidentifier",
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier",
                    "oid",
                    "sub",
                }
            ]
            stable = stable or str(principal.get("userId") or next(iter(ids), "")).strip()
            if not stable and not principal.get("userDetails"):
                return None
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return stable or None
        return stable or str(principal.get("userDetails")).strip()
    return stable or None


def _trusted_hosted_origin() -> str | None:
    from urllib.parse import urlsplit

    configured = (os.environ.get("APP_ORIGIN") or "").strip()
    if configured:
        parts = urlsplit(configured)
        if (
            parts.scheme.lower() == "https"
            and parts.netloc
            and not parts.username
            and not parts.password
            and parts.path in {"", "/"}
            and not parts.query
            and not parts.fragment
        ):
            return f"https://{parts.netloc.lower()}"
        return None
    hostname = (os.environ.get("WEBSITE_HOSTNAME") or "").strip().lower()
    if hostname and "/" not in hostname and "@" not in hostname:
        return f"https://{hostname}"
    return None


def _origin_is_same(*, hosted: bool) -> bool:
    from urllib.parse import urlsplit

    origin = request.headers.get("Origin")
    if not origin:
        return not hosted
    expected = _trusted_hosted_origin() if hosted else request.host_url
    if not expected:
        return False
    actual_parts = urlsplit(origin)
    expected_parts = urlsplit(expected)
    return (
        actual_parts.scheme.lower(),
        actual_parts.netloc.lower(),
    ) == (
        expected_parts.scheme.lower(),
        expected_parts.netloc.lower(),
    )


@app.before_request
def _protect_api():
    if not request.path.startswith("/api/") or request.path in {"/api/live", "/api/health"}:
        return None
    local_bypass = os.environ.get("ALLOW_LOCAL_AUTH_BYPASS", "").lower() in {"1", "true", "yes"}
    hosted = _is_hosted()
    if hosted:
        if not _easy_auth_enabled():
            return jsonify({"error": "Hosted authentication is not enabled."}), 503
        principal_id = _principal_id()
        if principal_id is None:
            return jsonify({"error": "Authentication required."}), 401
    elif not local_bypass:
        return jsonify({"error": "Authentication required."}), 401
    else:
        principal_id = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _origin_is_same(
        hosted=hosted
    ):
        return jsonify({"error": "Cross-origin request denied."}), 403
    allowlist = {
        item.strip()
        for item in os.environ.get("AUTH_ALLOWED_PRINCIPAL_IDS", "").split(",")
        if item.strip()
    }
    if hosted and allowlist and principal_id not in allowlist:
        return jsonify({"error": "Access denied."}), 403
    return None


def _source_auth_required(func):
    """Compatibility decorator; global API protection performs authentication."""

    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapped


def _source_by_id(profile: dict, source_id: str) -> dict | None:
    return next(
        (item for item in profile.get("source_documents", []) if item.get("id") == source_id),
        None,
    )


def _public_source_metadata(source: dict) -> dict:
    return {
        "id": source.get("id"),
        "ingested_at": source.get("ingested_at"),
        "filename": source.get("filename"),
        "media_type": source.get("media_type"),
        "artifacts": {
            name: {
                "sha256": (source.get(name) or {}).get("sha256"),
                "length": (source.get(name) or {}).get("length"),
                "url": f"/api/sources/{source.get('id')}/{name}",
            }
            for name in ("source", "text")
        },
    }


def _has_active_judgment_successor(
    judgments: list[dict],
    judgment_id: str,
    *,
    exclude_id: str | None = None,
) -> bool:
    """Return whether an active judgment directly or transitively supersedes an ID."""
    by_id = {item.get("id"): item for item in judgments if item.get("id")}
    for candidate in judgments:
        if candidate.get("id") == exclude_id or (candidate.get("status") or "active") != "active":
            continue
        seen: set[str] = set()
        prior_id = candidate.get("supersedes")
        while prior_id and prior_id not in seen:
            if prior_id == judgment_id:
                return True
            seen.add(prior_id)
            prior = by_id.get(prior_id)
            prior_id = prior.get("supersedes") if prior else None
    return False


@app.route("/api/live")
def api_live():
    """Lightweight liveness probe — just confirms the process is alive.

    Use this for k8s/Azure liveness checks.  Does no I/O and never returns
    503.  Use ``/api/health`` for readiness/degraded state.
    """
    return jsonify({"alive": True}), 200


@app.route("/api/health")
def api_health():
    """Readiness probe — checks storage, profile validity, and job state.

    Response fields (no PHI, paths, or secrets)
    --------------------------------------------
    - ``status``: ``"ok"`` | ``"degraded"`` | ``"error"``
    - ``version``: app package version
    - ``schema_version``: current profile schema version
    - ``data_dir_writable``: bool
    - ``profile_status``: ``"ok"`` | ``"missing"`` | ``"invalid_json"``
      | ``"invalid_shape"`` | ``"io_error"``
    - ``stale_job_count``: jobs queued/running for >1 hour
    - ``interrupted_job_count``: jobs marked interrupted
    - ``newest_snapshot_age_seconds``: float | null
    - ``newest_backup_age_seconds``: float | null
    - ``jobs_healthy``: bool (False when jobs.json is quarantined or unreadable on load)
    - ``profile_recovery_state``: ``"none"`` | ``"recovered"`` | ``"failed"`` | ``"unknown"``
    - ``profile_recovery_source``: ``"snapshot"`` | ``"daily_backup"`` | ``"manual"`` | null

    HTTP status codes
    -----------------
    - 200  status=ok or degraded: app is usable
    - 503  status=error: data dir not writable, or profile is unreadable/invalid
    """
    from agent import backups as agent_backups
    from agent.migrations import CURRENT_SCHEMA_VERSION
    from agent.recovery import get_recovery_state
    from agent.schema import clinically_empty_profile, structural_check

    # ── storage writability ───────────────────────────────────────────────────
    data_dir_writable = False
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".health_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        data_dir_writable = True
    except Exception:
        pass

    # ── profile structural check (no side effects — does NOT quarantine) ──────
    profile_status = "missing"
    try:
        raw_bytes = agent.PROFILE_PATH.read_bytes()
        try:
            pdata = json.loads(raw_bytes)
            if structural_check(pdata) and not clinically_empty_profile(pdata):
                profile_status = "ok"
            elif structural_check(pdata):
                profile_status = "clinically_empty"
            else:
                profile_status = "invalid_shape"
        except json.JSONDecodeError:
            profile_status = "invalid_json"
    except FileNotFoundError:
        profile_status = "missing"
    except OSError:
        profile_status = "io_error"

    # ── job counts ────────────────────────────────────────────────────────────
    stale_threshold = time.time() - 3600  # 1-hour cutoff for "stale" active job
    stale_job_count = 0
    interrupted_job_count = 0
    with _jobs_lock:
        for j in _jobs:
            status = j.get("status")
            if status == "interrupted":
                interrupted_job_count += 1
            elif status in ("queued", "running"):
                created = j.get("created_at", "")
                try:
                    ct = datetime.datetime.fromisoformat(created).timestamp()
                    if ct < stale_threshold:
                        stale_job_count += 1
                except (ValueError, TypeError):
                    stale_job_count += 1

    job_active, job_queued = _get_executor().counts()
    feed_active, feed_queued = _get_executor(feed=True).counts()

    # ── backup / snapshot ages ────────────────────────────────────────────────
    snap_age = agent_backups.newest_file_age_seconds(DATA_DIR / "snapshots", "profile_*.json")
    backup_age = agent_backups.newest_file_age_seconds(DATA_DIR / "backups", "profile_*.json")

    # ── recovery state ────────────────────────────────────────────────────────
    recovery_state = get_recovery_state()

    # ── overall status ────────────────────────────────────────────────────────
    missing_indicates_data_loss = profile_status == "missing" and (
        (DATA_DIR / ".profile-initialized").exists()
        or snap_age is not None
        or backup_age is not None
    )
    error_conditions = (
        not data_dir_writable
        or profile_status in ("invalid_json", "invalid_shape", "clinically_empty", "io_error")
        or missing_indicates_data_loss
    )
    degraded_conditions = (
        not _jobs_healthy
        or profile_status == "missing"
        or interrupted_job_count > 0
        or stale_job_count > 0
        or (
            backup_age is not None and backup_age > 48 * 3600  # >2 days old → conservative degraded
        )
    )

    if error_conditions:
        overall = "error"
        http_status = 503
    elif degraded_conditions:
        overall = "degraded"
        http_status = 200
    else:
        overall = "ok"
        http_status = 200

    return jsonify(
        {
            "status": overall,
            "version": APP_VERSION,
            "release_commit": RELEASE_COMMIT,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "data_dir_writable": data_dir_writable,
            "profile_status": profile_status,
            # backward compat field — callers checking profile_loaded still work
            "profile_loaded": profile_status == "ok",
            "stale_job_count": stale_job_count,
            "interrupted_job_count": interrupted_job_count,
            "active_job_count": job_active + feed_active,
            "queued_job_count": job_queued + feed_queued,
            "feed_active_count": feed_active,
            "feed_queued_count": feed_queued,
            "newest_snapshot_age_seconds": snap_age,
            "newest_backup_age_seconds": backup_age,
            "jobs_healthy": _jobs_healthy,
            "hosted_auth_detected": _easy_auth_enabled(),
            "profile_recovery_state": recovery_state.get("state", "none"),
            "profile_recovery_source": recovery_state.get("source"),
        }
    ), http_status


@app.route("/api/status")
def api_status():
    profile = agent.load_profile()
    alerts = [a for a in profile.get("alerts", []) if not a.get("resolved")]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date", ""), reverse=True)[:50]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date", ""), reverse=True)[:3]
    docs = sorted(profile.get("documents", []), key=lambda x: x.get("date", ""), reverse=True)[:5]
    return jsonify(
        {
            "patient": profile.get("patient", {}),
            "alerts": alerts,
            "recent_biomarkers": bms,
            "recent_imaging": imgs,
            "recent_documents": docs,
            "treatments_classified": profile.get("treatments_classified", []),
            "stats": {
                "trials_tracked": len(profile.get("trials_tracked", [])),
                "literature_watched": len(profile.get("literature_watched", [])),
                "total_documents": len(profile.get("documents", [])),
                "total_biomarkers": len(profile.get("biomarkers", [])),
            },
        }
    )


@app.route("/api/feed", methods=["POST"])
def api_feed():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        f = request.files.get("file")
        if f:
            text = f.read().decode("utf-8", errors="replace")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    job, rejection = _submit_job("feed", _run_feed_job, text, feed=True)
    if rejection:
        return rejection
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/feed-file", methods=["POST"])
def api_feed_file():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400

    raw_bytes = f.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "File exceeds the 20 MB upload limit"}), 413
    filename = Path(f.filename or "upload.bin").name[:255]
    media_type = f.mimetype or "application/octet-stream"

    def persist_upload(job: dict) -> None:
        atomic_write_bytes(DATA_DIR / "uploads" / job["id"] / "input.bin", raw_bytes)

    job, rejection = _submit_job(
        "feed",
        _run_feed_job,
        None,
        "job-upload",
        filename,
        media_type,
        feed=True,
        prepare=persist_upload,
    )
    if rejection:
        return rejection
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/sources/<source_id>")
@_source_auth_required
def api_source_metadata(source_id):
    profile = agent.load_profile()
    source = _source_by_id(profile, source_id)
    if source is None:
        return jsonify({"error": "Source not found"}), 404
    return jsonify(_public_source_metadata(source))


@app.route("/api/sources/<source_id>/<artifact>")
@_source_auth_required
def api_source_artifact(source_id, artifact):
    profile = agent.load_profile()
    source = _source_by_id(profile, source_id)
    if source is None:
        return jsonify({"error": "Source not found"}), 404
    try:
        path = resolve_source_artifact(source, artifact)
    except (ValueError, FileNotFoundError):
        return jsonify({"error": "Source artifact unavailable"}), 404
    if not path.is_file():
        return jsonify({"error": "Source artifact unavailable"}), 404
    try:
        content = path.read_bytes()
    except OSError:
        return jsonify({"error": "Source artifact unavailable"}), 404
    if not validate_source_artifact(source, artifact, content):
        return jsonify({"error": "Source artifact integrity check failed"}), 409
    response = send_file(
        io.BytesIO(content),
        as_attachment=artifact == "source",
        download_name=source.get("filename") or f"{source_id}.bin",
        mimetype="text/plain; charset=utf-8" if artifact == "text" else source.get("media_type"),
        conditional=False,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/api/evidence/<source_id>")
@_source_auth_required
def api_evidence(source_id):
    profile = agent.load_profile()
    source = _source_by_id(profile, source_id)
    if source is None:
        return jsonify({"error": "Source not found"}), 404
    try:
        start = int(request.args.get("start", ""))
        end = int(request.args.get("end", ""))
    except ValueError:
        return jsonify({"error": "start and end must be integers"}), 400
    if start < 0 or end <= start or end - start > 10000:
        return jsonify({"error": "Invalid evidence span"}), 400
    try:
        text_path = resolve_source_artifact(source, "text")
        text_bytes = text_path.read_bytes()
        if not validate_source_artifact(source, "text", text_bytes):
            return jsonify({"error": "Evidence source integrity check failed"}), 409
        text = text_bytes.decode("utf-8")
    except (ValueError, FileNotFoundError, OSError, UnicodeError):
        return jsonify({"error": "Evidence source unavailable"}), 404
    if end > len(text):
        return jsonify({"error": "Evidence span is outside the source"}), 416
    return jsonify(
        {
            "source_document_id": source_id,
            "start": start,
            "end": end,
            "quote": text[start:end],
        }
    )


@app.route("/api/digest", methods=["POST"])
def api_digest():
    job, rejection = _submit_job("digest", _run_digest_job, unique_active=True)
    if rejection:
        return rejection
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/deep-sweep", methods=["POST"])
def api_deep_sweep():
    """Enqueue an ensemble deep-sweep (multi-model exploratory research pass).

    Read-only: the job does not write findings back to the profile.
    """
    job, rejection = _submit_job("deep-sweep", _run_deepsweep_job, unique_active=True)
    if rejection:
        return rejection
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/jobs")
def api_jobs():
    with _jobs_lock:
        return jsonify([_job_response(job) for job in _jobs])


@app.route("/api/jobs/<job_id>")
def api_job(job_id):
    with _jobs_lock:
        for j in _jobs:
            if j["id"] == job_id:
                return jsonify(_job_response(j, include_artifacts=True))
    return jsonify({"error": "Not found"}), 404


@app.route("/api/treatments/delete", methods=["POST"])
@serialized_profile_mutation
def api_delete_treatment():
    data = request.get_json(force=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    profile = agent.load_profile()
    # Remove from raw treatments list
    profile["patient"]["current_treatments"] = [
        t for t in profile["patient"].get("current_treatments", []) if t != text
    ]
    # Remove from classified list
    profile["treatments_classified"] = [
        t
        for t in profile.get("treatments_classified", [])
        if t.get("text") != text and t.get("label") != text
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/alerts/resolve/<int:idx>", methods=["POST"])
@serialized_profile_mutation
def api_resolve_alert(idx):
    profile = agent.load_profile()
    alerts = profile.get("alerts", [])
    unresolved = [a for a in alerts if not a.get("resolved")]
    if idx < len(unresolved):
        unresolved[idx]["resolved"] = True
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/treatments/update", methods=["POST"])
@serialized_profile_mutation
def api_treatments_update():
    """Update a treatment's category or remove it — syncs both classified and raw lists."""
    data = request.get_json(force=True) or {}
    action = data.get("action")  # "remove" or "set_category"
    idx = data.get("idx")
    category = data.get("category")

    profile = agent.load_profile()
    txs = profile.get("treatments_classified", [])

    if idx is None or idx >= len(txs):
        return jsonify({"error": "Invalid index"}), 400

    tx = txs[idx]
    tx_text_lower = (tx.get("text") or tx.get("label") or "").lower().strip()

    if action == "remove":
        txs.pop(idx)
        # Also remove from raw current_treatments — match by substring
        profile["patient"]["current_treatments"] = [
            t
            for t in profile["patient"].get("current_treatments", [])
            if tx_text_lower not in t.lower() and t.lower() not in tx_text_lower
        ]

    elif action == "set_category" and category:
        txs[idx]["category"] = category
        # If marking completed, note the change in raw list by appending a completion marker
        if category == "completed":
            raw = profile["patient"].get("current_treatments", [])
            # Replace matching raw entry with a completed-flagged version
            updated_raw = []
            matched = False
            for t in raw:
                if not matched and (tx_text_lower in t.lower() or t.lower() in tx_text_lower):
                    updated_raw.append(f"{t} [completed]")
                    matched = True
                else:
                    updated_raw.append(t)
            profile["patient"]["current_treatments"] = updated_raw
    else:
        return jsonify({"error": "Invalid action"}), 400

    profile["treatments_classified"] = txs
    agent.save_profile(profile)
    return jsonify({"ok": True, "treatments_classified": txs})


@app.route("/api/trials")
def api_trials():
    profile = agent.load_profile()
    trials = sorted(
        profile.get("trials_tracked", []), key=lambda x: x.get("date_added", ""), reverse=True
    )
    return jsonify(trials)


@app.route("/api/trials/poll", methods=["POST"])
@serialized_profile_mutation
def api_trials_poll():
    """On-demand deterministic poll of tracked-trial statuses (P5)."""
    profile = agent.load_profile()
    result = agent.poll_tracked_trials(profile)
    if result.get("changed") or result.get("refreshed"):
        agent.save_profile(profile)
    return jsonify(result)


@app.route("/api/trials/<nct_id>", methods=["DELETE"])
@serialized_profile_mutation
def api_delete_trial(nct_id):
    profile = agent.load_profile()
    profile["trials_tracked"] = [
        t for t in profile.get("trials_tracked", []) if t.get("nct_id") != nct_id
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/papers")
def api_papers():
    profile = agent.load_profile()
    papers = sorted(
        profile.get("literature_watched", []), key=lambda x: x.get("date_added", ""), reverse=True
    )
    return jsonify(papers)


@app.route("/api/papers/<pmid>", methods=["DELETE"])
@serialized_profile_mutation
def api_delete_paper(pmid):
    profile = agent.load_profile()
    profile["literature_watched"] = [
        p for p in profile.get("literature_watched", []) if p.get("pmid") != pmid
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/questions")
def api_questions():
    profile = agent.load_profile()
    questions = profile.get("appointment_questions", [])
    return jsonify(questions)


@app.route("/api/questions/generate", methods=["POST"])
def api_questions_generate():
    data = request.get_json(force=True) or {}
    appointment_type = str(data.get("appointment_type") or "oncology follow-up")[:200]
    job, rejection = _submit_job(
        "questions", _run_questions_job, appointment_type, unique_active=True
    )
    if rejection:
        return rejection
    legacy = _legacy_sync_result(job["id"])
    if legacy is not None:
        if legacy.get("error"):
            return jsonify(legacy), 500
        return jsonify(legacy.get("questions", []))
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/questions/add", methods=["POST"])
@serialized_profile_mutation
def api_questions_add():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    profile = agent.load_profile()
    today = datetime.datetime.now().isoformat()
    question = {
        "id": f"q_manual_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": text,
        "category": data.get("category", "Other"),
        "priority": data.get("priority", "medium"),
        "rationale": "",
        "source": "manual",
        "asked": False,
        "created_at": today[:10],
    }
    profile.setdefault("appointment_questions", []).insert(0, question)
    agent.save_profile(profile, clinical_change=False)
    return jsonify(question)


@app.route("/api/questions/<qid>/toggle", methods=["POST"])
@serialized_profile_mutation
def api_questions_toggle(qid):
    profile = agent.load_profile()
    for q in profile.get("appointment_questions", []):
        if q.get("id") == qid:
            q["asked"] = not q.get("asked", False)
            break
    agent.save_profile(profile, clinical_change=False)
    return jsonify({"ok": True})


@app.route("/api/questions/<qid>", methods=["DELETE"])
@serialized_profile_mutation
def api_questions_delete(qid):
    profile = agent.load_profile()
    profile["appointment_questions"] = [
        q for q in profile.get("appointment_questions", []) if q.get("id") != qid
    ]
    agent.save_profile(profile, clinical_change=False)
    return jsonify({"ok": True})


@app.route("/api/judgments")
def api_judgments():
    profile = agent.load_profile()
    today = datetime.date.today().isoformat()
    judgments = []
    for stored in profile.get("clinical_judgments", []):
        item = dict(stored)
        status = item.get("status") or "active"
        reasons = []
        if item.get("valid_until") and item["valid_until"] < today:
            reasons.append("expired")
        if item.get("review_after") and item["review_after"] <= today:
            reasons.append("review due")
        item["effective_status"] = "needs_review" if reasons else status
        item["review_reason"] = ", ".join(reasons) or None
        judgments.append(item)
    return jsonify(judgments)


@app.route("/api/judgments/add", methods=["POST"])
@serialized_profile_mutation
def api_judgments_add():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    profile = agent.load_profile()
    status = data.get("status") or "active"
    if status not in {"active", "superseded", "needs_review"}:
        return jsonify({"error": "Invalid judgment status"}), 400
    for field in ("review_after", "valid_until"):
        if data.get(field):
            try:
                datetime.date.fromisoformat(data[field])
            except (TypeError, ValueError):
                return jsonify({"error": f"{field} must be YYYY-MM-DD"}), 400
    timestamp = now_stamp()
    judgment = {
        "id": f"j_{_new_id()}",
        "text": text,
        "category": data.get("category", "context"),
        "source": data.get("source", "manual"),
        "date": datetime.date.today().isoformat(),
        "added_at": timestamp,
        "updated_at": timestamp,
        "scope": (data.get("scope") or "").strip() or None,
        "status": status,
        "review_after": data.get("review_after") or None,
        "valid_until": data.get("valid_until") or None,
        "supersedes": data.get("supersedes") or None,
    }
    if judgment["supersedes"]:
        if status != "active":
            return jsonify({"error": "A superseding judgment must be active"}), 400
        prior = next(
            (
                item
                for item in profile.get("clinical_judgments", [])
                if item.get("id") == judgment["supersedes"]
            ),
            None,
        )
        if prior is None:
            return jsonify({"error": "Superseded judgment not found"}), 400
        if _has_active_judgment_successor(
            profile.get("clinical_judgments", []),
            judgment["supersedes"],
        ):
            return jsonify({"error": "Judgment already has an active successor"}), 409
        prior["status"] = "superseded"
        prior["updated_at"] = timestamp
    profile.setdefault("clinical_judgments", []).insert(0, judgment)
    agent.save_profile(profile)
    return jsonify(judgment)


@app.route("/api/judgments/<jid>", methods=["PATCH"])
@serialized_profile_mutation
def api_judgments_edit(jid):
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    category = data.get("category", "").strip()
    if "text" in data and not text:
        return jsonify({"error": "No text"}), 400
    status = data.get("status")
    if status is not None and status not in {"active", "superseded", "needs_review"}:
        return jsonify({"error": "Invalid judgment status"}), 400
    for field in ("review_after", "valid_until"):
        if data.get(field):
            try:
                datetime.date.fromisoformat(data[field])
            except (TypeError, ValueError):
                return jsonify({"error": f"{field} must be YYYY-MM-DD"}), 400
    profile = agent.load_profile()
    for j in profile.get("clinical_judgments", []):
        if j.get("id") == jid:
            supersedes = (data.get("supersedes") or "").strip() if "supersedes" in data else None
            resulting_status = status if status is not None else j.get("status") or "active"
            prior = None
            if supersedes:
                if supersedes == jid or resulting_status != "active":
                    return jsonify({"error": "Invalid judgment supersession"}), 400
                prior = next(
                    (
                        item
                        for item in profile.get("clinical_judgments", [])
                        if item.get("id") == supersedes
                    ),
                    None,
                )
                if prior is None:
                    return jsonify({"error": "Superseded judgment not found"}), 400
                if _has_active_judgment_successor(
                    profile.get("clinical_judgments", []),
                    supersedes,
                    exclude_id=jid,
                ):
                    return jsonify({"error": "Judgment already has an active successor"}), 409
            if resulting_status == "active" and _has_active_judgment_successor(
                profile.get("clinical_judgments", []),
                jid,
            ):
                return jsonify({"error": "Superseded judgment has an active successor"}), 409
            if "text" in data:
                j["text"] = text
            if category:
                j["category"] = category
            for field in ("scope", "review_after", "valid_until", "supersedes"):
                if field in data:
                    j[field] = (data.get(field) or "").strip() or None
            if status is not None:
                j["status"] = status
            j["updated_at"] = now_stamp()
            if prior is not None:
                prior["status"] = "superseded"
                prior["updated_at"] = j["updated_at"]
            agent.save_profile(profile)
            return jsonify(j)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/judgments/<jid>", methods=["DELETE"])
@serialized_profile_mutation
def api_judgments_delete(jid):
    profile = agent.load_profile()
    profile["clinical_judgments"] = [
        j for j in profile.get("clinical_judgments", []) if j.get("id") != jid
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


# ── symptoms ─────────────────────────────────────────────────────────────────
@app.route("/api/symptoms")
def api_symptoms():
    profile = agent.load_profile()
    symptoms = sorted(
        profile.get("symptoms", []),
        key=lambda x: x.get("date", ""),
        reverse=True,
    )
    return jsonify(symptoms)


@app.route("/api/symptoms", methods=["POST"])
@serialized_profile_mutation
def api_symptoms_add():
    data = request.get_json(force=True) or {}
    name = (data.get("symptom") or "").strip()
    if not name:
        return jsonify({"error": "No symptom name"}), 400
    severity = data.get("severity")
    try:
        severity = int(severity) if severity is not None else None
    except (TypeError, ValueError):
        severity = None
    if severity is not None and not (1 <= severity <= 5):
        return jsonify({"error": "Severity must be 1-5"}), 400
    profile = agent.load_profile()
    today = datetime.date.today().isoformat()
    symptom = {
        "id": f"sym_manual_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "date": (data.get("date") or today),
        "symptom": name,
        "severity": severity,
        "note": (data.get("note") or "").strip() or None,
        "related_treatment": (data.get("related_treatment") or "").strip() or None,
        "source": "manual",
        "added_at": now_stamp(),
    }
    profile.setdefault("symptoms", []).insert(0, symptom)
    agent.save_profile(profile)
    return jsonify(symptom)


@app.route("/api/symptoms/<sid>", methods=["PATCH"])
@serialized_profile_mutation
def api_symptoms_edit(sid):
    data = request.get_json(force=True) or {}
    profile = agent.load_profile()
    for s in profile.get("symptoms", []):
        if s.get("id") == sid:
            if "symptom" in data:
                name = (data.get("symptom") or "").strip()
                if not name:
                    return jsonify({"error": "Symptom name cannot be empty"}), 400
                s["symptom"] = name
            if "severity" in data:
                sev = data.get("severity")
                try:
                    sev = int(sev) if sev not in (None, "") else None
                except (TypeError, ValueError):
                    return jsonify({"error": "Severity must be 1-5 or null"}), 400
                if sev is not None and not (1 <= sev <= 5):
                    return jsonify({"error": "Severity must be 1-5"}), 400
                s["severity"] = sev
            if "note" in data:
                s["note"] = (data.get("note") or "").strip() or None
            if "related_treatment" in data:
                s["related_treatment"] = (data.get("related_treatment") or "").strip() or None
            if "date" in data and data["date"]:
                s["date"] = data["date"]
            agent.save_profile(profile)
            return jsonify(s)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/symptoms/<sid>", methods=["DELETE"])
@serialized_profile_mutation
def api_symptoms_delete(sid):
    profile = agent.load_profile()
    profile["symptoms"] = [s for s in profile.get("symptoms", []) if s.get("id") != sid]
    agent.save_profile(profile)
    return jsonify({"ok": True})


# ── changes / "since last login" ─────────────────────────────────────────────
def _is_after(item_date: str, ack: str) -> bool:
    """Return True iff item_date is strictly later than ack.

    Compares as strings — relies on ISO-8601-ish ordering. Both date-only
    (YYYY-MM-DD) and datetime (YYYY-MM-DDTHH:MM:SS) strings sort
    correctly under lexicographic comparison.
    """
    if not item_date:
        return False
    return item_date > ack


def _count_new(profile: dict) -> dict:
    """Compute per-category counts of items dated after acknowledged_at.

    A summary is considered "regenerated since ack" if its
    ``generated_at`` is later than the ack timestamp.
    """
    ack = profile.get("acknowledged_at") or ""
    if not ack:
        # Never acknowledged — every item counts as new.
        ack = ""

    def _count(items, key):
        # Prefer added_at (ingestion time) so a back-dated item fed after the
        # last acknowledgement still surfaces as new; fall back to the clinical
        # date / date_added for legacy items recorded before added_at existed.
        return sum(1 for it in items if _is_after(it.get("added_at") or it.get(key, "") or "", ack))

    summary = profile.get("executive_summary") or {}
    summary_generated = summary.get("generated_at_timestamp") or summary.get("generated_at") or ""
    summary_new = bool(summary_generated and summary_generated > ack)

    counts = {
        "biomarkers": _count(profile.get("biomarkers", []), "date"),
        "imaging": _count(profile.get("imaging", []), "date"),
        "trials": _count(profile.get("trials_tracked", []), "date_added"),
        "papers": _count(profile.get("literature_watched", []), "date_added"),
        "alerts": _count(profile.get("alerts", []), "date"),
        "documents": _count(profile.get("documents", []), "date"),
        "judgments": _count(profile.get("clinical_judgments", []), "date"),
        "symptoms": _count(profile.get("symptoms", []), "date"),
        "executive_summary": summary_new,
    }
    counts["total_new"] = (
        counts["biomarkers"]
        + counts["imaging"]
        + counts["trials"]
        + counts["papers"]
        + counts["alerts"]
        + counts["documents"]
        + counts["judgments"]
        + counts["symptoms"]
        + (1 if counts["executive_summary"] else 0)
    )
    return counts


@app.route("/api/changes")
def api_changes():
    profile = agent.load_profile()
    return jsonify(
        {
            "acknowledged_at": profile.get("acknowledged_at"),
            "new": _count_new(profile),
        }
    )


@app.route("/api/changes/acknowledge", methods=["POST"])
@serialized_profile_mutation
def api_changes_acknowledge():
    profile = agent.load_profile()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    profile["acknowledged_at"] = now
    agent.save_profile(profile, clinical_change=False)
    return jsonify(
        {
            "acknowledged_at": now,
            "new": _count_new(profile),
        }
    )


@app.route("/api/summary/dismiss-action/<int:idx>", methods=["POST"])
@serialized_profile_mutation
def api_dismiss_action(idx):
    data = request.get_json(force=True) or {}
    profile = agent.load_profile()
    summary = profile.get("executive_summary", {})
    actions = summary.get("next_actions", [])
    if 0 <= idx < len(actions):
        dismissed = actions.pop(idx)
        summary["next_actions"] = actions
        profile["executive_summary"] = summary
        # Feedback is review state, never a silent clinical judgment/fact mutation.
        feedback = (data.get("feedback") or "").strip()
        if feedback:
            action_text = dismissed.get("action", "")
            timestamp = now_stamp()
            entry = {
                "id": f"fb_{_new_id()}",
                "target": "summary_action",
                "item_id": action_text[:200] or f"action-{idx}",
                "assessment": "corrected",
                "note": feedback,
                "outcome": "dismissed",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            profile.setdefault("feedback", []).insert(0, entry)
            _invalidate_summary_for_review(profile)
        agent.save_profile(profile, clinical_change=False)
    return jsonify({"ok": True})


def _invalidate_summary_for_review(profile: dict) -> None:
    profile["summary_stale"] = True
    if isinstance(profile.get("executive_summary"), dict):
        profile["executive_summary"]["stale"] = True
        profile["executive_summary"]["review_feedback_pending"] = True


@app.route("/api/feedback")
def api_feedback():
    profile = agent.load_profile()
    return jsonify(profile.get("feedback", []))


@app.route("/api/feedback", methods=["POST"])
@serialized_profile_mutation
def api_feedback_add():
    data = request.get_json(force=True) or {}
    target = (data.get("target") or "").strip()
    item_id = (data.get("item_id") or "").strip()
    assessment = (data.get("assessment") or "").strip()
    allowed = {"agreed", "corrected", "acted", "helpful", "incorrect", "missed"}
    if not target or not item_id:
        return jsonify({"error": "target and item_id are required"}), 400
    if assessment not in allowed:
        return jsonify({"error": "Invalid assessment"}), 400
    timestamp = now_stamp()
    entry = {
        "id": f"fb_{_new_id()}",
        "target": target[:100],
        "item_id": item_id[:200],
        "assessment": assessment,
        "note": (data.get("note") or "").strip()[:4000] or None,
        "outcome": (data.get("outcome") or "").strip()[:2000] or None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    profile = agent.load_profile()
    profile.setdefault("feedback", []).insert(0, entry)
    invalidates = assessment in {"corrected", "incorrect", "missed"} and target.startswith(
        "summary"
    )
    if invalidates:
        _invalidate_summary_for_review(profile)
    agent.save_profile(profile, clinical_change=False)
    return jsonify({"feedback": entry, "summary_invalidated": invalidates}), 201


@app.route("/api/feedback/<feedback_id>", methods=["PATCH"])
@serialized_profile_mutation
def api_feedback_edit(feedback_id):
    data = request.get_json(force=True) or {}
    allowed = {"agreed", "corrected", "acted", "helpful", "incorrect", "missed"}
    if "assessment" in data and data["assessment"] not in allowed:
        return jsonify({"error": "Invalid assessment"}), 400
    profile = agent.load_profile()
    entry = next(
        (item for item in profile.get("feedback", []) if item.get("id") == feedback_id),
        None,
    )
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    for field, limit in (("note", 4000), ("outcome", 2000)):
        if field in data:
            entry[field] = (data.get(field) or "").strip()[:limit] or None
    if "assessment" in data:
        entry["assessment"] = data["assessment"]
    entry["updated_at"] = now_stamp()
    invalidates = entry.get("assessment") in {"corrected", "incorrect", "missed"} and entry.get(
        "target", ""
    ).startswith("summary")
    if invalidates:
        _invalidate_summary_for_review(profile)
    agent.save_profile(profile, clinical_change=False)
    return jsonify({"feedback": entry, "summary_invalidated": invalidates})


@app.route("/api/summary")
def api_summary():
    profile = agent.load_profile()
    summary = profile.get("executive_summary")
    if not summary:
        return jsonify({"status": "not_generated"})
    response = dict(summary)
    response["profile_revision"] = profile.get("profile_revision")
    response["summary_revision"] = summary.get("summary_revision")
    current_judgment_hash = agent.clinical_judgments_fingerprint(profile)
    stored_judgment_hash = summary.get("judgment_context_hash")
    judgment_context_changed = (
        stored_judgment_hash != current_judgment_hash
        if stored_judgment_hash is not None
        else bool(profile.get("clinical_judgments"))
    )
    response["judgment_context_changed"] = judgment_context_changed
    response["stale"] = bool(
        profile.get("summary_stale") or summary.get("stale") or judgment_context_changed
    )
    response["profile_updated_at"] = profile.get("profile_updated_at")
    response["recent_documents"] = sorted(
        profile.get("documents", []),
        key=lambda item: item.get("added_at") or item.get("date") or "",
        reverse=True,
    )[:5]
    evidence_links = []
    seen = set()
    for item in (
        profile.get("biomarkers", [])
        + profile.get("imaging", [])
        + profile.get("symptoms", [])
        + profile.get("appointments", [])
    ):
        source_id = item.get("source_document_id")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        link = {
            "source_document_id": source_id,
            "label": item.get("marker")
            or item.get("modality")
            or item.get("symptom")
            or item.get("description")
            or "Source document",
            "evidence_status": item.get("evidence_status") or "missing",
            "source_url": f"/api/sources/{source_id}/text",
        }
        if (
            item.get("evidence_status") == "verified"
            and item.get("evidence_start") is not None
            and item.get("evidence_end") is not None
        ):
            link["evidence_url"] = (
                f"/api/evidence/{source_id}?start={item['evidence_start']}"
                f"&end={item['evidence_end']}"
            )
        evidence_links.append(link)
        if len(evidence_links) >= 8:
            break
    response["evidence_links"] = evidence_links
    response["source_links"] = [
        {
            "source_document_id": doc.get("source_document_id"),
            "label": doc.get("summary") or doc.get("type") or "Source document",
            "url": f"/api/sources/{doc.get('source_document_id')}",
        }
        for doc in response["recent_documents"]
        if doc.get("source_document_id")
    ]
    considered = set(summary.get("feedback_ids_considered") or [])
    response["feedback_pending"] = sum(
        1
        for item in profile.get("feedback", [])
        if item.get("id") not in considered
        if item.get("assessment") in {"corrected", "incorrect", "missed"}
        and item.get("target", "").startswith("summary")
    )
    return jsonify(response)


@app.route("/api/summary/generate", methods=["POST"])
def api_summary_generate():
    """Queue executive summary generation and treatment classification."""
    job, rejection = _submit_job("summary", _run_summary_job, unique_active=True)
    if rejection:
        return rejection
    legacy = _legacy_sync_result(job["id"])
    if legacy is not None:
        return jsonify(legacy), 500 if legacy.get("error") else 200
    return jsonify({"job_id": job["id"]}), 202


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat endpoint grounded in patient profile data."""
    data = request.get_json(force=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history", [])
    if not user_message:
        return jsonify({"error": "No message"}), 400

    if not isinstance(history, list):
        return jsonify({"error": "Invalid history"}), 400
    history = history[-20:]
    job, rejection = _submit_job("chat", _run_chat_job, user_message[:10000], history)
    if rejection:
        return rejection
    legacy = _legacy_sync_result(job["id"])
    if legacy is not None:
        return jsonify(legacy), 500 if legacy.get("error") else 200
    return jsonify({"job_id": job["id"]}), 202


@app.route("/")
def index():
    response = send_from_directory(app.static_folder, "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=_args.port, debug=False)
