#!/usr/bin/env python3
"""
NET Care Agent — Web UI backend
Deployed on Azure App Service (swedencentral)
Data persisted to /home/data (Azure Files mount)
"""

import atexit
import base64
import copy
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
    "profile_revision",
    "generation_id",
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
_MAX_LINKABLE_APPOINTMENTS = 100
_MAX_VISIT_QUESTION_REORDER_ITEMS = 200
_APPOINTMENT_PROJECTION_FIELDS = (
    "id",
    "date",
    "time",
    "with",
    "location",
    "description",
    "type",
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
                    jsonify(
                        {
                            "error": "An active job of this type already exists.",
                            "job_id": existing["id"],
                        }
                    ),
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


def _job_response(
    job: dict,
    *,
    include_artifacts: bool = False,
    profile: dict | None = None,
) -> dict:
    response = dict(job)
    profile_dependent_report = job.get("type") in {"feed", "digest", "deep-sweep"}
    profile_dependent_result = job.get("type") in {"chat", "questions", "summary"}
    report_revision_stale = False
    if profile_dependent_report and job.get("report_file"):
        profile = profile or agent.load_profile()
        report_revision = job.get("profile_revision")
        report_revision_stale = report_revision is None or str(report_revision) != str(
            profile.get("profile_revision")
        )
    result_revision_stale = False
    result_same_revision_invalidated = False
    if profile_dependent_result and job.get("result_file"):
        profile = profile or agent.load_profile()
        result_revision = job.get("profile_revision")
        result_revision_stale = result_revision is None or str(result_revision) != str(
            profile.get("profile_revision")
        )
        if job.get("type") == "summary" and not agent.summary_is_current(profile):
            result_same_revision_invalidated = not result_revision_stale
            result_revision_stale = True
        if job.get("type") == "questions":
            generation_id = job.get("generation_id")
            revision_was_stale = result_revision_stale
            superseded = (
                generation_id is not None
                and generation_id != profile.get("questions_generation_id")
            )
            questions_invalid = generation_id is None or superseded or any(
                item.get("stale")
                for item in profile.get("appointment_questions", [])
                if isinstance(item, dict)
                and item.get("source") == "ai"
                and item.get("generation_job_id") == generation_id
            )
            if questions_invalid:
                result_same_revision_invalidated = not result_revision_stale
                result_revision_stale = True
                if superseded and not revision_was_stale:
                    response["derived_content_stale_reason"] = (
                        "question_generation_superseded"
                    )
    feed_content_stale = False
    if job.get("type") == "feed" and job.get("source_document_id"):
        profile = profile or agent.load_profile()
        receipt = next(
            (
                item
                for item in profile.get("document_imports", [])
                if item.get("job_id") == job.get("id")
            ),
            None,
        )
        feed_content_stale = bool(receipt and receipt.get("status") != "active")
        if feed_content_stale:
            response["derived_content_stale"] = True
            response["derived_content_stale_reason"] = "source_document_corrected_or_undone"
            for field in ("summary", "key_findings", "input_preview"):
                response.pop(field, None)
    if report_revision_stale:
        response["derived_content_stale"] = True
        if not feed_content_stale:
            response["derived_content_stale_reason"] = (
                "freshness_cannot_be_verified"
                if job.get("profile_revision") is None
                else "patient_record_changed_after_generation"
            )
    if result_revision_stale:
        response["derived_content_stale"] = True
        response.setdefault(
            "derived_content_stale_reason",
            (
                "freshness_cannot_be_verified"
                if job.get("profile_revision") is None
                else (
                    "generated_content_invalidated"
                    if result_same_revision_invalidated
                    else "patient_record_changed_after_generation"
                )
            ),
        )
    if not include_artifacts:
        return response
    if job.get("type") == "feed" and job.get("source_document_id"):
        response["receipt_url"] = f"/api/jobs/{job['id']}/receipt"
    report_ref = job.get("report_file")
    if report_ref:
        if feed_content_stale or report_revision_stale:
            response["report_stale"] = True
            response["report_stale_reason"] = (
                "source_document_corrected_or_undone"
                if feed_content_stale
                else (
                    "freshness_cannot_be_verified"
                    if job.get("profile_revision") is None
                    else "patient_record_changed_after_generation"
                )
            )
            response["report_available_for_audit"] = True
        else:
            try:
                response["report"] = safe_artifact_path(
                    DATA_DIR, report_ref, {"reports"}
                ).read_text(encoding="utf-8")
            except (OSError, ValueError):
                response["artifact_unavailable"] = True
    result_ref = job.get("result_file")
    if result_ref:
        try:
            response["result"] = json.loads(
                safe_artifact_path(DATA_DIR, result_ref, {"job_results"}).read_text(
                    encoding="utf-8"
                )
            )
            if job.get("type") in {"questions", "summary", "chat"} and isinstance(
                response["result"], dict
            ):
                profile = agent.load_profile()
                source_revision = response["result"].get(
                    "source_profile_revision",
                    response["result"].get("profile_revision"),
                )
                current_revision = profile.get("profile_revision")
                stale = source_revision is None or str(source_revision) != str(current_revision)
                if job.get("type") == "summary":
                    nested_summary = response["result"].get("summary")
                    stale = (
                        stale
                        or not agent.summary_is_current(profile)
                        or (isinstance(nested_summary, dict) and bool(nested_summary.get("stale")))
                    )
                elif job.get("type") == "questions":
                    generation_id = response["result"].get("generation_id")
                    stale = (
                        stale
                        or generation_id != profile.get("questions_generation_id")
                        or any(
                            item.get("stale")
                            for item in profile.get("appointment_questions", [])
                            if isinstance(item, dict)
                            and item.get("source") == "ai"
                            and item.get("generation_job_id") == generation_id
                        )
                    )
                    stale = stale or any(
                        item.get("stale")
                        for item in response["result"].get("questions", [])
                        if isinstance(item, dict) and item.get("generation_job_id") == generation_id
                    )
                else:
                    stale = stale or source_revision is None
                if stale:
                    stale_reason = response.get(
                        "derived_content_stale_reason",
                        "patient_record_changed_after_generation",
                    )
                    if job.get("type") == "summary":
                        response["result"] = {
                            "stale": True,
                            "stale_reason": stale_reason,
                            "source_profile_revision": source_revision,
                            "current_profile_revision": current_revision,
                        }
                    elif job.get("type") == "questions":
                        response["result"]["stale"] = True
                        response["result"]["stale_reason"] = stale_reason
                        response["result"]["current_profile_revision"] = current_revision
                        response["result"]["questions"] = [
                            {**item, "stale": True, "stale_reason": stale_reason}
                            for item in response["result"].get("questions", [])
                        ]
                    else:
                        response["result"] = {
                            "stale": True,
                            "stale_reason": stale_reason,
                            "source_profile_revision": source_revision,
                            "current_profile_revision": current_revision,
                        }
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
                    age = (
                        now - datetime.datetime.fromisoformat(job.get("created_at", "")).timestamp()
                    )
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


def _workflow_request() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise agent.FollowThroughError("A JSON object is required")
    return data


def _workflow_error(exc: Exception):
    if isinstance(exc, agent.FollowThroughConflict):
        return jsonify({"error": str(exc), "code": "workflow_conflict"}), 409
    if isinstance(exc, KeyError):
        return jsonify({"error": str(exc.args[0]), "code": "not_found"}), 404
    return jsonify({"error": str(exc), "code": "invalid_workflow_request"}), 400


def _save_workflow_mutation(
    profile: dict,
    *,
    clinical_change: bool,
    reason: str,
    event: dict,
    response_factory,
) -> dict:
    agent.increment_workflow_revision(profile)
    if clinical_change:
        agent.invalidate_generated_context(profile, reason)

    def capture_result(_profile: dict) -> None:
        snapshot = copy.deepcopy(response_factory())
        event["result_snapshot"] = snapshot
        event["result_hash"] = agent.request_hash(snapshot)

    agent.save_profile(
        profile,
        clinical_change=clinical_change,
        before_write=capture_result,
    )
    return copy.deepcopy(event["result_snapshot"])


def _reject_unsupported_fields(data: dict, allowed: set[str], message: str) -> None:
    if set(data) - allowed:
        raise agent.FollowThroughError(message)


def _idempotent_result(
    profile: dict,
    mutation_id: str,
    data: dict,
    *,
    endpoint: str,
    operation: str,
    target: str,
) -> dict | None:
    result = agent.check_idempotency(
        profile,
        mutation_id,
        data,
        endpoint=endpoint,
        operation=operation,
        target=target,
    )
    if result is not None:
        result["idempotent_replay"] = True
    return result


def _semantic_import_value(value):
    if isinstance(value, dict):
        return {
            key: _semantic_import_value(item)
            for key, item in sorted(value.items())
            if item is not None
            and not (key == "source_dependency_active" and item is True)
            and not (key == "excluded_from_clinical_context" and item is False)
            and not (key == "history" and item == [])
        }
    if isinstance(value, list):
        return [_semantic_import_value(item) for item in value]
    return value


def _source_record_is_linkable(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    status = str(record.get("status") or "").strip().lower()
    return not (
        record.get("excluded_from_clinical_context") is True
        or record.get("active") is False
        or record.get("source_dependency_active") is False
        or status in {"inactive", "excluded", "removed", "undone", "deleted"}
        or record.get("inactive_reason")
        or record.get("excluded_at")
        or record.get("removed_at")
        or record.get("deleted_at")
    )


def _linkable_appointment_projections(profile: dict) -> list[dict]:
    """Return a bounded, provenance-free projection of current imported appointments."""
    source_documents = {
        item.get("id")
        for item in profile.get("source_documents", []) or []
        if _source_record_is_linkable(item)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
    }
    active_documents = {
        item.get("source_document_id")
        for item in profile.get("documents", []) or []
        if _source_record_is_linkable(item)
        and isinstance(item.get("source_document_id"), str)
        and item["source_document_id"].strip()
    }
    imports_by_source: dict[str, list[dict]] = {}
    for item in profile.get("document_imports", []) or []:
        source_id = item.get("source_document_id") if isinstance(item, dict) else None
        if (
            isinstance(source_id, str)
            and source_id.strip()
            and _source_record_is_linkable(item)
            and item.get("status") in {"active", "corrected", "partially_removed"}
        ):
            imports_by_source.setdefault(source_id, []).append(item)

    projected = []
    seen_ids = set()
    for appointment in profile.get("appointments", []) or []:
        if not isinstance(appointment, dict):
            continue
        appointment_id = appointment.get("id")
        source_id = appointment.get("source_document_id")
        if (
            not isinstance(appointment_id, str)
            or not appointment_id.strip()
            or appointment_id in seen_ids
            or not isinstance(source_id, str)
            or not source_id.strip()
            or source_id not in source_documents
            or source_id not in active_documents
        ):
            continue
        current_value = _semantic_import_value(appointment)
        linked_change = any(
            isinstance(change, dict)
            and change.get("category") == "appointments"
            and change.get("source_document_id") == source_id
            and change.get("state") in {"active", "corrected"}
            and isinstance(change.get("target"), dict)
            and change["target"].get("kind") == "collection"
            and change["target"].get("collection") == "appointments"
            and change["target"].get("record_id") == appointment_id
            and _semantic_import_value(change.get("effective_value")) == current_value
            for import_record in imports_by_source.get(source_id, [])
            for change in import_record.get("changes", []) or []
        )
        if not linked_change:
            continue
        projected.append(
            {
                key: appointment.get(key)
                for key in _APPOINTMENT_PROJECTION_FIELDS
                if key in appointment
            }
        )
        seen_ids.add(appointment_id)
        if len(projected) >= _MAX_LINKABLE_APPOINTMENTS:
            break
    return projected


def _outcome_from_request(value: object) -> dict | None:
    _validate_outcome_request(value)
    text_value = value.get("text")
    if text_value is None or (isinstance(text_value, str) and not text_value.strip()):
        return None
    kind = agent.validate_status(value.get("kind"), agent.OUTCOME_KINDS, "outcome kind")
    text = agent.validate_text(text_value, "outcome.text", limit=2000)
    if kind == "clinician_attributed":
        provenance = agent.capture_provenance()
    elif kind == "caregiver_reported":
        provenance = {
            "capture_method": "caregiver_entered",
            "attributed_to": "patient_or_caregiver",
            "source_verification": "unverified",
        }
    else:
        provenance = {
            "capture_method": "caregiver_entered",
            "attributed_to": "caregiver",
            "source_verification": "not_applicable",
        }
    return {
        "kind": kind,
        "text": text,
        "recorded_at": now_stamp(),
        "provenance": provenance,
    }


def _validate_outcome_request(value: object) -> None:
    if not isinstance(value, dict):
        raise agent.FollowThroughError("outcome must be an object")
    _reject_unsupported_fields(value, {"kind", "text"}, "Unsupported outcome field")


def _required_link_id(data: dict, field: str) -> str | None:
    if field not in data:
        return None
    value = agent.validate_text(data[field], field, limit=100)
    if "\n" in value or "\r" in value:
        raise agent.FollowThroughError(f"{field} must be a single line")
    return value


def _eligible_alert_visit(profile: dict, visit_id: str) -> dict:
    try:
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
    except KeyError as exc:
        raise agent.FollowThroughConflict(
            "The visit is no longer available for alert resolution. Reload visits."
        ) from exc
    if visit.get("status") not in {"planned", "in_progress"}:
        raise agent.FollowThroughConflict(
            "The visit is no longer available for alert resolution. Reload visits."
        )
    return visit


def _eligible_alert_decision(profile: dict, visit: dict, decision_id: str) -> dict:
    decision = next(
        (item for item in visit.get("decisions", []) if item.get("id") == decision_id),
        None,
    )
    if decision is None:
        belongs_to_other_visit = any(
            any(item.get("id") == decision_id for item in candidate.get("decisions", []))
            for candidate in profile.get("visits", [])
            if candidate.get("id") != visit.get("id")
        )
        if belongs_to_other_visit:
            raise agent.FollowThroughError("decision_id does not belong to visit_id")
        raise agent.FollowThroughConflict(
            "The decision is no longer available for alert resolution. Reload visits."
        )
    if decision.get("status") not in {"active", "needs_confirmation"}:
        raise agent.FollowThroughConflict(
            "The decision is no longer available for alert resolution. Reload visits."
        )
    return decision


def _eligible_alert_follow_up(profile: dict, follow_up_id: str) -> dict:
    try:
        follow_up = agent.find_record(
            profile.get("caregiver_actions", []), follow_up_id, "Follow-up"
        )
    except KeyError as exc:
        raise agent.FollowThroughConflict(
            "The follow-up is no longer available for alert resolution. Reload follow-ups."
        ) from exc
    if follow_up.get("status") not in {"open", "in_progress"}:
        raise agent.FollowThroughConflict(
            "The follow-up is no longer available for alert resolution. Reload follow-ups."
        )
    return follow_up


def _new_action(
    profile: dict,
    data: dict,
    *,
    mutation_id: str,
    visit_id: str | None = None,
    decision: dict | None = None,
    alert_id: str | None = None,
    history_mutation_id: str | None = None,
    history_endpoint: str,
    history_target: str | None = None,
) -> dict:
    origin_kind = data.get("origin_kind") or ("visit_decision" if decision else "manual")
    if origin_kind not in {"manual", "executive_summary_action", "alert", "visit_decision"}:
        raise agent.FollowThroughError("Invalid origin_kind")
    if origin_kind == "executive_summary_action":
        source_id = str(data.get("source_id") or "")
        source = agent.find_summary_action(profile, source_id, data.get("expected_source_token"))
        text = agent.validate_follow_up_text(source.get("action") or source.get("text"))
        origin = {
            "kind": origin_kind,
            "source_id": source_id,
            "source_job_id": profile.get("executive_summary", {}).get("job_id"),
            "source_profile_revision": profile.get("executive_summary", {}).get("summary_revision"),
            "generation_id": profile.get("executive_summary", {}).get("generation_id"),
            "text": text,
            "snapshot": copy.deepcopy(source),
        }
    elif origin_kind == "visit_decision":
        if not isinstance(decision, dict):
            raise agent.FollowThroughError("A valid visit decision is required")
        text = agent.validate_follow_up_text(data.get("text"))
        origin = {
            "kind": origin_kind,
            "source_id": decision.get("id"),
            "source_job_id": None,
            "source_profile_revision": profile.get("profile_revision"),
            "generation_id": None,
            "text": decision.get("text"),
            "snapshot": copy.deepcopy(decision),
        }
    elif origin_kind == "alert":
        text = agent.validate_follow_up_text(data.get("text"))
        alert = agent.find_record(profile.get("alerts", []), alert_id or "", "Alert")
        origin = {
            "kind": origin_kind,
            "source_id": alert.get("id"),
            "source_job_id": alert.get("source_job_id"),
            "source_profile_revision": alert.get("generation_profile_revision"),
            "generation_id": None,
            "text": alert.get("action_required") or alert.get("message") or "",
            "snapshot": {
                key: copy.deepcopy(alert.get(key))
                for key in (
                    "id",
                    "priority",
                    "message",
                    "action_required",
                    "source_job_id",
                    "generation_profile_revision",
                    "dependency_kind",
                )
            },
        }
    else:
        text = agent.validate_follow_up_text(data.get("text"))
        origin = {
            "kind": "manual",
            "source_id": None,
            "source_job_id": None,
            "source_profile_revision": None,
            "generation_id": None,
            "text": text,
            "snapshot": {},
        }
    timestamp = now_stamp()
    action = {
        "id": agent.new_workflow_id("act"),
        "origin_snapshot": origin,
        "text": text,
        "owner": agent.validate_owner(data.get("owner")),
        "due_date": agent.validate_date(data.get("due_date"), "due_date"),
        "status": "open",
        "outcome": None,
        "visit_id": visit_id,
        "decision_id": decision.get("id") if isinstance(decision, dict) else None,
        "alert_id": alert_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "cancelled_at": None,
        "history": [],
    }
    agent.append_history(
        action,
        endpoint=history_endpoint,
        operation="created",
        target=history_target or f"caregiver_action:{action['id']}",
        mutation_id=history_mutation_id or mutation_id,
        payload=data,
        before_token=None,
        changes={"status": {"before": None, "after": "open"}},
    )
    profile.setdefault("caregiver_actions", []).append(action)
    return action


def _refresh_summary(profile: dict, *, generation_id: str) -> str | None:
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

    generated["generation_id"] = generation_id
    generated["summary_revision"] = int(profile.get("profile_revision") or 0)
    agent.ensure_summary_action_ids(generated)
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


def _finalize_generated_alert_dependencies(
    profile: dict,
    *,
    job_id: str,
    profile_revision: int,
) -> None:
    for alert in profile.get("alerts", []):
        if alert.get("source_job_id") != job_id:
            continue
        alert["generation_profile_revision"] = profile_revision
        agent.sync_alert_system_state(profile, alert)


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
            profile_before_intake = copy.deepcopy(profile)
            previous_trial_ids = set(agent.get_research_ids(profile, "trial"))
            previous_paper_ids = set(agent.get_research_ids(profile, "paper"))
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
            receipt_source_id = extracted.get("source_document_id")
            has_receipt = bool(
                receipt_source_id
                and any(
                    item.get("id") == receipt_source_id
                    for item in profile.get("source_documents", [])
                    if isinstance(item, dict)
                )
                and any(
                    item.get("source_document_id") == receipt_source_id
                    for item in profile.get("documents", [])
                    if isinstance(item, dict)
                )
            )
            if has_receipt:
                extracted["source_job_id"] = job_id
                agent.build_import_record(
                    profile_before_intake,
                    profile,
                    extracted,
                    job_id=job_id,
                    text=text,
                )
                _finalize_generated_alert_dependencies(
                    profile,
                    job_id=job_id,
                    profile_revision=int(profile.get("profile_revision") or 0) + 1,
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

            extracted["source_job_id"] = job_id
            extracted["generation_profile_revision"] = int(profile.get("profile_revision") or 0) + 1
            report = agent.run_orchestrator(profile, extracted)
            _update_job(job_id, {"stage": "classifying"})
            profile["treatments_classified"] = agent.classify_treatments(profile)
            final_revision = int(profile.get("profile_revision") or 0) + 1
            profile["treatments_classification_revision"] = final_revision
            profile["treatments_classification_job_id"] = job_id
            research_update = agent.record_latest_research_update(
                profile,
                job_id=job_id,
                trigger="feed",
                previous_trial_ids=previous_trial_ids,
                previous_paper_ids=previous_paper_ids,
                record_empty=False,
            )
            if research_update and has_receipt:
                agent.add_derived_research(
                    profile,
                    job_id,
                    trial_ids=research_update.get("trial_ids", []),
                    paper_ids=research_update.get("paper_ids", []),
                )
            _finalize_generated_alert_dependencies(
                profile,
                job_id=job_id,
                profile_revision=final_revision,
            )
            agent.save_profile(profile)
            _update_job(job_id, {"stage": "refreshing summary"})
            summary_error = _refresh_summary(profile, generation_id=job_id)
            agent.save_profile(profile, clinical_change=False)
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
                    "profile_revision": profile.get("profile_revision"),
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
            previous_trial_ids = set(agent.get_research_ids(profile, "trial"))
            previous_paper_ids = set(agent.get_research_ids(profile, "paper"))
            # P5: deterministically poll tracked-trial statuses before the LLM pass so
            # status changes become alerts (and reach the orchestrator) even though the
            # dedup logic would otherwise suppress already-tracked trials.
            try:
                final_revision = int(profile.get("profile_revision") or 0) + 1
                poll = agent.poll_tracked_trials(
                    profile,
                    source_job_id=job_id,
                    generation_profile_revision=final_revision,
                )
                if poll["changed"]:
                    _update_job(job_id, {"stage": f"trial updates: {len(poll['changed'])}"})
                    agent.save_profile(profile)
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
                "source_job_id": job_id,
                "generation_profile_revision": int(profile.get("profile_revision") or 0) + 1,
            }
            report = agent.run_orchestrator(profile, extracted)
            _update_job(job_id, {"stage": "classifying"})
            profile["treatments_classified"] = agent.classify_treatments(profile)
            final_revision = int(profile.get("profile_revision") or 0) + 1
            profile["treatments_classification_revision"] = final_revision
            profile["treatments_classification_job_id"] = job_id
            agent.record_latest_research_update(
                profile,
                job_id=job_id,
                trigger="digest",
                previous_trial_ids=previous_trial_ids,
                previous_paper_ids=previous_paper_ids,
                record_empty=True,
            )
            _finalize_generated_alert_dependencies(
                profile,
                job_id=job_id,
                profile_revision=final_revision,
            )
            agent.save_profile(profile)
            _update_job(job_id, {"stage": "refreshing summary"})
            summary_error = _refresh_summary(profile, generation_id=job_id)
            agent.save_profile(profile, clinical_change=False)

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
                    "profile_revision": profile.get("profile_revision"),
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
        generation_revision = profile.get("profile_revision")
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
                "profile_revision": generation_revision,
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
            generation_revision = profile.get("profile_revision")
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
                    candidate["generation_job_id"] = job_id
                    merged.append(candidate)
                    seen.add(key)
            profile["appointment_questions"] = merged
            profile["questions_generation_id"] = job_id
            agent.save_profile(profile, clinical_change=False)
        result_ref = _write_job_result(
            job_id,
            {
                "questions": merged,
                "source_profile_revision": generation_revision,
                "generation_id": job_id,
            },
        )
        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "result_file": result_ref,
                "profile_revision": generation_revision,
                "generation_id": job_id,
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
            profile["treatments_classification_revision"] = profile.get("profile_revision")
            profile["treatments_classification_job_id"] = job_id
            summary_error = _refresh_summary(profile, generation_id=job_id)
            agent.save_profile(profile, clinical_change=False)
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
                "profile_revision": profile.get("profile_revision"),
                "finished_at": now_stamp(),
            },
        )
    except Exception as exc:
        _fail_job(job_id, exc)


def _run_chat_job(
    job_id: str,
    user_message: str,
    history: list,
    expected_profile_revision: int,
) -> None:
    try:
        _update_job(job_id, {"status": "running", "stage": "answering", "started_at": now_stamp()})
        profile = agent.load_profile()
        generation_revision = profile.get("profile_revision")
        if str(generation_revision) != str(expected_profile_revision):
            raise RuntimeError("chat_history_stale")
        reply = agent.handle_chat(profile, user_message, history)
        current_revision = agent.load_profile().get("profile_revision")
        if str(current_revision) != str(generation_revision):
            raise RuntimeError("chat_context_stale")
        result_ref = _write_job_result(
            job_id,
            {
                "reply": reply,
                "source_profile_revision": generation_revision,
            },
        )
        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "result_file": result_ref,
                "profile_revision": generation_revision,
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
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _origin_is_same(hosted=hosted):
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
    try:
        profile_age = max(0.0, time.time() - agent.PROFILE_PATH.stat().st_mtime)
    except OSError:
        profile_age = None
    # Age alone is not a failure: an unchanged eight-day-old profile with an
    # eight-day-old backup is protected. Degrade only when the newest backup
    # materially lags the current profile (or is missing).
    backup_out_of_date = profile_status == "ok" and (
        backup_age is None or (profile_age is not None and backup_age > profile_age + 300)
    )

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
        or backup_out_of_date
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
            "profile_age_seconds": profile_age,
            "backup_out_of_date": backup_out_of_date,
            "jobs_healthy": _jobs_healthy,
            "hosted_auth_detected": _easy_auth_enabled(),
            "profile_recovery_state": recovery_state.get("state", "none"),
            "profile_recovery_source": recovery_state.get("source"),
        }
    ), http_status


@app.route("/api/status")
def api_status():
    profile = agent.load_profile()
    alerts = [
        agent.public_alert(item)
        for item in agent.active_alerts(profile)
    ]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date") or "", reverse=True)[
        :50
    ]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date") or "", reverse=True)[:3]
    docs = sorted(agent.active_documents(profile), key=lambda x: x.get("date") or "", reverse=True)[
        :5
    ]
    classification_current = agent.treatment_classification_is_current(profile)
    return jsonify(
        {
            "patient": profile.get("patient", {}),
            "profile_revision": profile.get("profile_revision"),
            "alerts": alerts,
            "recent_biomarkers": bms,
            "recent_imaging": imgs,
            "recent_documents": docs,
            "treatments_classified": (
                [
                    {**item, "edit_token": agent.treatment_edit_token(profile, item)}
                    for item in profile.get("treatments_classified", [])
                ]
                if classification_current
                else []
            ),
            "treatments_fallback": (
                []
                if classification_current
                else profile.get("patient", {}).get("current_treatments", [])
            ),
            "treatments_classification_current": classification_current,
            "stats": {
                "trials_tracked": len(profile.get("trials_tracked", [])),
                "literature_watched": len(profile.get("literature_watched", [])),
                "total_documents": len(profile.get("documents", [])),
                "total_biomarkers": len(profile.get("biomarkers", [])),
            },
            "latest_research_update": agent.public_latest_research_update(profile),
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
    profile = agent.load_profile()
    with _jobs_lock:
        return jsonify([_job_response(job, profile=profile) for job in _jobs])


@app.route("/api/jobs/<job_id>")
def api_job(job_id):
    profile = agent.load_profile()
    with _jobs_lock:
        for j in _jobs:
            if j["id"] == job_id:
                return jsonify(_job_response(j, include_artifacts=True, profile=profile))
    return jsonify({"error": "Not found"}), 404


def _retained_feed_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return next(
            (
                dict(item)
                for item in _jobs
                if item.get("id") == job_id and item.get("type") == "feed"
            ),
            None,
        )


def _receipt_error_response(profile: dict, job_id: str, exc: Exception):
    status = 409 if isinstance(exc, agent.ImportConflict) else 400
    payload = {
        "error": str(exc),
        "code": "import_conflict" if status == 409 else "invalid_receipt_change",
    }
    if status == 409:
        try:
            payload["receipt"] = agent.public_receipt(profile, job_id)
        except agent.ReconciliationError:
            pass
    return jsonify(payload), status


@app.route("/api/jobs/<job_id>/receipt")
def api_job_receipt(job_id):
    if _retained_feed_job(job_id) is None:
        return jsonify({"error": "Feed job not found"}), 404
    profile = agent.load_profile()
    try:
        return jsonify(agent.public_receipt(profile, job_id))
    except agent.ReconciliationError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/jobs/<job_id>/receipt/changes/<change_id>/correct", methods=["POST"])
@serialized_profile_mutation
def api_correct_import_change(job_id, change_id):
    if _retained_feed_job(job_id) is None:
        return jsonify({"error": "Feed job not found"}), 404
    data = request.get_json(force=True) or {}
    profile = agent.load_profile()
    try:
        agent.correct_change(
            profile,
            job_id,
            change_id,
            receipt_revision=data.get("receipt_revision"),
            target_token=str(data.get("target_token") or ""),
            replacement=data.get("replacement"),
        )
    except agent.ReconciliationError as exc:
        return _receipt_error_response(profile, job_id, exc)
    agent.save_profile(profile)
    return jsonify({"receipt": agent.public_receipt(profile, job_id)})


@app.route("/api/jobs/<job_id>/receipt/changes/<change_id>/remove", methods=["POST"])
@serialized_profile_mutation
def api_remove_import_change(job_id, change_id):
    if _retained_feed_job(job_id) is None:
        return jsonify({"error": "Feed job not found"}), 404
    data = request.get_json(force=True) or {}
    profile = agent.load_profile()
    try:
        agent.remove_change(
            profile,
            job_id,
            change_id,
            receipt_revision=data.get("receipt_revision"),
            target_token=str(data.get("target_token") or ""),
        )
    except agent.ReconciliationError as exc:
        return _receipt_error_response(profile, job_id, exc)
    agent.save_profile(profile)
    return jsonify({"receipt": agent.public_receipt(profile, job_id)})


@app.route("/api/jobs/<job_id>/receipt/undo", methods=["POST"])
@serialized_profile_mutation
def api_undo_import(job_id):
    if _retained_feed_job(job_id) is None:
        return jsonify({"error": "Feed job not found"}), 404
    data = request.get_json(force=True) or {}
    profile = agent.load_profile()
    try:
        agent.undo_import(
            profile,
            job_id,
            receipt_revision=data.get("receipt_revision"),
            undo_token=str(data.get("undo_token") or ""),
        )
    except agent.ReconciliationError as exc:
        return _receipt_error_response(profile, job_id, exc)
    agent.save_profile(profile)
    return jsonify({"receipt": agent.public_receipt(profile, job_id)})


@app.route("/api/patient/evidence")
def api_patient_evidence():
    """Return path-free imaging and document/source history for the Patient view."""
    profile = agent.load_profile()
    imports_by_source = {
        item.get("source_document_id"): item
        for item in profile.get("document_imports", [])
        if item.get("source_document_id")
    }
    indexed_source_ids = {
        item.get("id") for item in profile.get("source_documents", []) if item.get("id")
    }

    def evidence_projection(item: dict) -> dict:
        source_id = item.get("source_document_id")
        projected = {
            key: item.get(key)
            for key in (
                "id",
                "date",
                "modality",
                "findings",
                "impression",
                "new_lesions",
                "type",
                "summary",
                "key_findings",
                "added_at",
                "excluded_from_clinical_context",
                "evidence_status",
            )
            if key in item
        }
        projected["source_document_id"] = source_id
        if source_id in indexed_source_ids:
            projected["source_url"] = f"/api/sources/{source_id}"
        if (
            source_id in indexed_source_ids
            and item.get("evidence_status") == "verified"
            and item.get("evidence_start") is not None
            and item.get("evidence_end") is not None
        ):
            projected["evidence_url"] = (
                f"/api/evidence/{source_id}?start={item['evidence_start']}"
                f"&end={item['evidence_end']}"
            )
        receipt = imports_by_source.get(source_id)
        if receipt and _retained_feed_job(receipt.get("job_id", "")):
            projected["receipt_url"] = f"/api/jobs/{receipt['job_id']}/receipt"
            projected["receipt_job_id"] = receipt["job_id"]
            projected["import_status"] = receipt.get("status")
        return projected

    sources = []
    for source in sorted(
        profile.get("source_documents", []),
        key=lambda item: item.get("ingested_at") or "",
        reverse=True,
    ):
        public = _public_source_metadata(source)
        receipt = imports_by_source.get(source.get("id"))
        if receipt:
            public["document_type"] = receipt.get("document_type")
            public["document_date"] = receipt.get("document_date")
            public["document_summary"] = receipt.get("document_summary")
            public["import_status"] = receipt.get("status")
            if _retained_feed_job(receipt.get("job_id", "")):
                public["receipt_url"] = f"/api/jobs/{receipt['job_id']}/receipt"
                public["receipt_job_id"] = receipt["job_id"]
        sources.append(public)
    return jsonify(
        {
            "imaging": [
                evidence_projection(item)
                for item in sorted(
                    profile.get("imaging", []),
                    key=lambda item: item.get("date") or item.get("added_at") or "",
                    reverse=True,
                )
            ],
            "documents": [
                evidence_projection(item)
                for item in sorted(
                    profile.get("documents", []),
                    key=lambda item: item.get("added_at") or item.get("date") or "",
                    reverse=True,
                )
            ],
            "sources": sources,
        }
    )


@app.route("/api/follow-ups")
def api_follow_ups():
    profile = agent.load_profile()
    return jsonify(
        {
            "items": [agent.public_action(item) for item in profile.get("caregiver_actions", [])],
            "workflow_revision": profile.get("workflow_revision", 0),
            "profile_revision": profile.get("profile_revision", 0),
        }
    )


@app.route("/api/follow-ups", methods=["POST"])
@serialized_profile_mutation
def api_follow_ups_add():
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {
            "mutation_id",
            "origin_kind",
            "source_id",
            "expected_source_token",
            "text",
            "owner",
            "due_date",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported follow-up field")
        endpoint = "POST /api/follow-ups"
        target = "caregiver_actions:new"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="created",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        action = _new_action(
            profile,
            data,
            mutation_id=mutation_id,
            history_endpoint=endpoint,
            history_target=target,
        )
        event = action["history"][-1]
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="caregiver_follow_up_created",
            event=event,
            response_factory=lambda: {
                "item": agent.public_action(action),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return (
            jsonify(result),
            201,
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/follow-ups/<action_id>", methods=["PATCH"])
@serialized_profile_mutation
def api_follow_ups_edit(action_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {"mutation_id", "expected_token", "owner", "due_date", "status", "outcome"}
        _reject_unsupported_fields(data, allowed, "Unsupported follow-up field")
        if "outcome" in data:
            _validate_outcome_request(data["outcome"])
        endpoint = "PATCH /api/follow-ups/<action_id>"
        target = f"caregiver_action:{action_id}"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="updated",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        action = agent.find_record(profile.get("caregiver_actions", []), action_id, "Follow-up")
        agent.validate_expected_token(action, data.get("expected_token"))
        before = copy.deepcopy(action)
        before_token = agent.semantic_token(action)
        if "owner" in data:
            action["owner"] = agent.validate_owner(data.get("owner"))
        if "due_date" in data:
            action["due_date"] = agent.validate_date(data.get("due_date"), "due_date")
        target_status = action.get("status") or "open"
        if "status" in data:
            target_status = agent.validate_status(data.get("status"), agent.ACTION_STATUSES)
            if not agent.action_transition_allowed(action.get("status") or "open", target_status):
                raise agent.FollowThroughConflict(
                    "The follow-up lifecycle transition is not allowed"
                )
            if (action.get("status") or "open") in {"completed", "cancelled"}:
                raise agent.FollowThroughConflict(
                    "Completed or cancelled follow-up outcomes are immutable"
                )
        outcome = None
        if "outcome" in data:
            outcome = _outcome_from_request(data.get("outcome"))
        is_terminal_transition = target_status in {"completed", "cancelled"} and target_status != (
            action.get("status") or "open"
        )
        if is_terminal_transition and outcome is None:
            raise agent.FollowThroughError("A completion or cancellation outcome is required")
        if outcome is not None and not is_terminal_transition:
            raise agent.FollowThroughError(
                "An outcome can only be recorded when completing or cancelling a follow-up"
            )
        timestamp = now_stamp()
        action["status"] = target_status
        if outcome is not None:
            action["outcome"] = outcome
        if is_terminal_transition and target_status == "completed":
            action["completed_at"] = timestamp
        elif is_terminal_transition and target_status == "cancelled":
            action["cancelled_at"] = timestamp
        if agent.semantic_token(before) == agent.semantic_token(action):
            raise agent.FollowThroughError("The follow-up update does not change anything")
        action["updated_at"] = timestamp
        event = agent.append_history(
            action,
            endpoint=endpoint,
            operation="updated",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={
                key: {"before": before.get(key), "after": action.get(key)}
                for key in ("owner", "due_date", "status", "outcome")
                if before.get(key) != action.get(key)
            },
        )
        clinical_change = agent.clinical_outcome(outcome)
        result = _save_workflow_mutation(
            profile,
            clinical_change=clinical_change,
            reason="caregiver_follow_up_clinical_outcome",
            event=event,
            response_factory=lambda: {
                "item": agent.public_action(action),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits")
def api_visits():
    profile = agent.load_profile()
    return jsonify(
        {
            "items": [agent.public_visit(item) for item in profile.get("visits", [])],
            "appointments": _linkable_appointment_projections(profile),
            "workflow_revision": profile.get("workflow_revision", 0),
            "profile_revision": profile.get("profile_revision", 0),
        }
    )


@app.route("/api/visits/<visit_id>/recap")
def api_visit_recap(visit_id):
    try:
        expected_token = request.args.get("expected_visit_token", "")
        if not expected_token:
            raise agent.FollowThroughError("expected_visit_token is required")
        profile = agent.load_profile()
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        if agent.semantic_token(visit) != expected_token:
            raise agent.FollowThroughConflict(
                "The visit changed. Reload it before viewing the recap."
            )
        recap = agent.project_visit_recap(profile, visit)
        profile_revision = profile.get("profile_revision", 0)
        workflow_revision = profile.get("workflow_revision", 0)
        recap_token = agent.semantic_token(
            {
                "visit_token": expected_token,
                "profile_revision": profile_revision,
                "workflow_revision": workflow_revision,
                "recap": recap,
            }
        )
        return jsonify(
            {
                "visit_id": visit_id,
                "visit_token": expected_token,
                "profile_revision": profile_revision,
                "workflow_revision": workflow_revision,
                "recap_token": recap_token,
                "recap": recap,
            }
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits", methods=["POST"])
@serialized_profile_mutation
def api_visits_add():
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {
            "mutation_id",
            "title",
            "date",
            "time",
            "clinician",
            "location",
            "status",
            "source_appointment_id",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported visit field")
        endpoint = "POST /api/visits"
        target = "visits:new"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="created",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        source_id = agent.validate_optional_text(
            data.get("source_appointment_id"),
            "source_appointment_id",
            limit=100,
            single_line=True,
        )
        linkable_appointments = {
            item["id"]: item for item in _linkable_appointment_projections(profile)
        }
        if source_id and source_id not in linkable_appointments:
            raise KeyError("Source appointment not found")
        timestamp = now_stamp()
        status = (
            agent.validate_status(data.get("status"), agent.VISIT_STATUSES)
            if data.get("status")
            else "planned"
        )
        visit = {
            "id": agent.new_workflow_id("visit"),
            "title": agent.validate_text(data.get("title"), "title", limit=200),
            "date": agent.validate_date(data.get("date"), "date"),
            "time": agent.validate_optional_text(
                data.get("time"), "time", limit=40, single_line=True
            ),
            "clinician": agent.validate_optional_text(
                data.get("clinician"), "clinician", limit=200, single_line=True
            ),
            "location": agent.validate_optional_text(
                data.get("location"), "location", limit=300, single_line=True
            ),
            "status": status,
            "source_appointment_id": source_id,
            "question_snapshots": [],
            "decisions": [],
            "follow_up_ids": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": timestamp if status == "completed" else None,
            "cancelled_at": timestamp if status == "cancelled" else None,
            "history": [],
        }
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="created",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=None,
            changes={"status": {"before": None, "after": status}},
        )
        profile.setdefault("visits", []).append(visit)
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="visit_created",
            event=event,
            response_factory=lambda: {
                "item": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return (
            jsonify(result),
            201,
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>", methods=["PATCH"])
@serialized_profile_mutation
def api_visits_edit(visit_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {
            "mutation_id",
            "expected_token",
            "title",
            "date",
            "time",
            "clinician",
            "location",
            "status",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported visit field")
        endpoint = "PATCH /api/visits/<visit_id>"
        target = f"visit:{visit_id}"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="updated",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        agent.validate_expected_token(visit, data.get("expected_token"))
        before = copy.deepcopy(visit)
        before_token = agent.semantic_token(visit)
        if "title" in data:
            visit["title"] = agent.validate_text(data.get("title"), "title", limit=200)
        if "date" in data:
            visit["date"] = agent.validate_date(data.get("date"), "date")
        for field, limit in (("time", 40), ("clinician", 200), ("location", 300)):
            if field in data:
                visit[field] = agent.validate_optional_text(
                    data.get(field), field, limit=limit, single_line=True
                )
        if "status" in data:
            target_status = agent.validate_status(data.get("status"), agent.VISIT_STATUSES)
            if not agent.visit_transition_allowed(
                visit.get("status") or "planned", target_status
            ):
                raise agent.FollowThroughConflict("The visit lifecycle transition is not allowed")
            visit["status"] = target_status
            if target_status != before.get("status"):
                timestamp = now_stamp()
                if target_status == "completed":
                    visit["completed_at"] = timestamp
                elif target_status == "cancelled":
                    visit["cancelled_at"] = timestamp
        if agent.semantic_token(before) == agent.semantic_token(visit):
            raise agent.FollowThroughError("The visit update does not change anything")
        visit["updated_at"] = now_stamp()
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="updated",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={
                key: {"before": before.get(key), "after": visit.get(key)}
                for key in ("title", "date", "time", "clinician", "location", "status")
                if before.get(key) != visit.get(key)
            },
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="visit_updated",
            event=event,
            response_factory=lambda: {
                "item": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/questions", methods=["POST"])
@serialized_profile_mutation
def api_visit_questions_add(visit_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {
            "mutation_id",
            "expected_visit_token",
            "source_kind",
            "source_question_id",
            "expected_source_token",
            "text",
            "category",
            "priority",
            "rationale",
            "pinned",
            "order",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported visit question field")
        endpoint = "POST /api/visits/<visit_id>/questions"
        target = f"visit:{visit_id}:questions"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="question_added",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        agent.validate_expected_token(visit, data.get("expected_visit_token"))
        source_kind = str(data.get("source_kind") or "")
        if source_kind not in {"manual", "generated"}:
            raise agent.FollowThroughError("source_kind must be manual or generated")
        if source_kind == "generated":
            source = agent.find_question(
                profile,
                str(data.get("source_question_id") or ""),
                data.get("expected_source_token"),
            )
            text = source.get("text") or ""
            category = source.get("category")
            priority = source.get("priority")
            rationale = source.get("rationale")
            source_id = source.get("id")
            generation_id = source.get("generation_job_id")
            source_revision = source.get("source_profile_revision")
        else:
            text = agent.validate_text(data.get("text"), "text", limit=1000)
            category = agent.validate_optional_text(
                data.get("category"), "category", limit=100, single_line=True
            )
            priority = agent.validate_optional_text(
                data.get("priority"), "priority", limit=40, single_line=True
            )
            rationale = agent.validate_optional_text(data.get("rationale"), "rationale", limit=1000)
            source_id = None
            generation_id = None
            source_revision = None
        order = data.get("order", len(visit.get("question_snapshots", [])))
        if not isinstance(order, int) or isinstance(order, bool) or not 0 <= order <= 10000:
            raise agent.FollowThroughError("order must be an integer from 0 to 10000")
        pinned = data.get("pinned", False)
        if not isinstance(pinned, bool):
            raise agent.FollowThroughError("pinned must be true or false")
        before_token = agent.semantic_token(visit)
        question = {
            "id": agent.new_workflow_id("vq"),
            "text": text,
            "category": category,
            "priority": priority,
            "rationale": rationale,
            "source_kind": source_kind,
            "source_question_id": source_id,
            "source_generation_id": generation_id,
            "source_profile_revision": source_revision,
            "pinned": pinned,
            "order": order,
            "answer": None,
            "created_at": now_stamp(),
        }
        visit.setdefault("question_snapshots", []).append(question)
        visit["updated_at"] = now_stamp()
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="question_added",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={"question_id": question["id"], "source_kind": source_kind},
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="visit_question_added",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return (
            jsonify(result),
            201,
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/questions/order", methods=["PATCH"])
@serialized_profile_mutation
def api_visit_questions_reorder(visit_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        _reject_unsupported_fields(
            data,
            {"mutation_id", "expected_visit_token", "questions"},
            "Unsupported visit question order field",
        )
        endpoint = "PATCH /api/visits/<visit_id>/questions/order"
        target = f"visit:{visit_id}:question_order"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="questions_reordered",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)

        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        agent.validate_expected_token(visit, data.get("expected_visit_token"))
        requested = data.get("questions")
        if not isinstance(requested, list):
            raise agent.FollowThroughError("questions must be an array")
        if len(requested) > _MAX_VISIT_QUESTION_REORDER_ITEMS:
            raise agent.FollowThroughError(
                f"questions must contain at most {_MAX_VISIT_QUESTION_REORDER_ITEMS} items"
            )

        current_questions = visit.get("question_snapshots", [])
        if not isinstance(current_questions, list):
            raise agent.FollowThroughConflict(
                "The visit questions changed. Reload before reordering."
            )
        if not requested:
            if current_questions:
                raise agent.FollowThroughError(
                    "questions must include every current visit question"
                )
            raise agent.FollowThroughError("The visit question order does not change anything")

        requested_ids = []
        requested_tokens = {}
        for item in requested:
            if not isinstance(item, dict):
                raise agent.FollowThroughError("Each question order item must be an object")
            _reject_unsupported_fields(
                item,
                {"id", "expected_token"},
                "Unsupported question order item field",
            )
            question_id = agent.validate_text(item.get("id"), "question id", limit=100)
            if question_id != item.get("id"):
                raise agent.FollowThroughError("question id must not have surrounding whitespace")
            if question_id in requested_tokens:
                raise agent.FollowThroughError("Question IDs must be unique")
            requested_ids.append(question_id)
            requested_tokens[question_id] = item.get("expected_token")

        current_by_id = {}
        for question in current_questions:
            question_id = question.get("id") if isinstance(question, dict) else None
            if (
                not isinstance(question_id, str)
                or not question_id.strip()
                or question_id in current_by_id
            ):
                raise agent.FollowThroughConflict(
                    "The visit questions changed. Reload before reordering."
                )
            current_by_id[question_id] = question
        if set(requested_ids) != set(current_by_id) or len(requested_ids) != len(current_by_id):
            raise agent.FollowThroughConflict(
                "The visit questions changed. Reload before reordering."
            )
        for question_id in requested_ids:
            agent.validate_expected_token(
                current_by_id[question_id],
                requested_tokens[question_id],
            )

        before_order = [question["id"] for question in current_questions]
        already_normalized = all(
            question.get("order") == index for index, question in enumerate(current_questions)
        )
        if requested_ids == before_order and already_normalized:
            raise agent.FollowThroughError("The visit question order does not change anything")

        before_token = agent.semantic_token(visit)
        ordered_questions = [current_by_id[question_id] for question_id in requested_ids]
        for index, question in enumerate(ordered_questions):
            question["order"] = index
        visit["question_snapshots"] = ordered_questions
        visit["updated_at"] = now_stamp()
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="questions_reordered",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={"order": {"before": before_order, "after": requested_ids}},
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="visit_questions_reordered",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/questions/<question_id>", methods=["PATCH"])
@serialized_profile_mutation
def api_visit_questions_edit(visit_id, question_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {"mutation_id", "expected_token", "pinned", "order", "answer"}
        _reject_unsupported_fields(data, allowed, "Unsupported visit question field")
        if "answer" in data:
            if not isinstance(data["answer"], dict):
                raise agent.FollowThroughError("answer must be an object")
            _reject_unsupported_fields(
                data["answer"],
                {"status", "text"},
                "Answer provenance is server-owned",
            )
        endpoint = "PATCH /api/visits/<visit_id>/questions/<question_id>"
        target = f"visit_question:{visit_id}:{question_id}"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="question_updated",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        question = agent.find_record(
            visit.get("question_snapshots", []), question_id, "Visit question"
        )
        agent.validate_expected_token(question, data.get("expected_token"))
        before = copy.deepcopy(question)
        before_token = agent.semantic_token(question)
        if "pinned" in data:
            if not isinstance(data["pinned"], bool):
                raise agent.FollowThroughError("pinned must be true or false")
            question["pinned"] = data["pinned"]
        if "order" in data:
            if (
                not isinstance(data["order"], int)
                or isinstance(data["order"], bool)
                or not 0 <= data["order"] <= 10000
            ):
                raise agent.FollowThroughError("order must be an integer from 0 to 10000")
            question["order"] = data["order"]
        clinical_change = False
        if "answer" in data:
            answer_data = data.get("answer")
            status = agent.validate_status(
                answer_data.get("status"), {"answered", "unknown"}, "answer status"
            )
            if status == "answered":
                text = agent.validate_text(answer_data.get("text"), "answer.text", limit=4000)
            else:
                if answer_data.get("text") not in (None, ""):
                    raise agent.FollowThroughError("Unknown answers cannot include answer text")
                text = None
            question["answer"] = {
                "status": status,
                "text": text,
                "recorded_at": now_stamp(),
                "provenance": agent.capture_provenance(),
            }
            clinical_change = True
        if agent.semantic_token(before) == agent.semantic_token(question):
            raise agent.FollowThroughError("The visit question update does not change anything")
        visit["updated_at"] = now_stamp()
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="question_updated",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={
                key: {"before": before.get(key), "after": question.get(key)}
                for key in ("pinned", "order", "answer")
                if before.get(key) != question.get(key)
            },
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=clinical_change,
            reason="visit_clinician_answer_captured",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/decisions", methods=["POST"])
@serialized_profile_mutation
def api_visit_decisions_add(visit_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        _reject_unsupported_fields(
            data,
            {"mutation_id", "expected_visit_token", "text", "supersedes_id"},
            "Decision provenance is server-owned",
        )
        endpoint = "POST /api/visits/<visit_id>/decisions"
        target = f"visit:{visit_id}:decisions"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="decision_added",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        agent.validate_expected_token(visit, data.get("expected_visit_token"))
        before_token = agent.semantic_token(visit)
        supersedes_id = agent.validate_optional_text(
            data.get("supersedes_id"),
            "supersedes_id",
            limit=100,
            single_line=True,
        )
        prior = None
        if supersedes_id:
            prior = agent.find_record(
                visit.get("decisions", []), supersedes_id, "Superseded decision"
            )
            if prior.get("status") != "active":
                raise agent.FollowThroughConflict("Only an active decision can be superseded")
        timestamp = now_stamp()
        decision = {
            "id": agent.new_workflow_id("dec"),
            "text": agent.validate_text(data.get("text"), "text", limit=4000),
            "status": "active",
            "provenance": agent.capture_provenance(),
            "supersedes_id": supersedes_id,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        if prior is not None:
            prior["status"] = "superseded"
            prior["updated_at"] = timestamp
        visit.setdefault("decisions", []).append(decision)
        visit["updated_at"] = timestamp
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="decision_added",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={
                "decision_id": decision["id"],
                "supersedes_id": supersedes_id,
            },
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=True,
            reason="visit_clinician_decision_captured",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return (
            jsonify(result),
            201,
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/decisions/<decision_id>", methods=["PATCH"])
@serialized_profile_mutation
def api_visit_decisions_edit(visit_id, decision_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        _reject_unsupported_fields(
            data,
            {"mutation_id", "expected_token", "status"},
            "Decision text is immutable; add a successor instead",
        )
        endpoint = "PATCH /api/visits/<visit_id>/decisions/<decision_id>"
        target = f"visit_decision:{visit_id}:{decision_id}"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="decision_status_changed",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        decision = agent.find_record(visit.get("decisions", []), decision_id, "Decision")
        agent.validate_expected_token(decision, data.get("expected_token"))
        status = agent.validate_status(data.get("status"), agent.DECISION_STATUSES)
        current = decision.get("status") or "active"
        allowed = {
            "active": {"active", "superseded", "retracted", "needs_confirmation"},
            "needs_confirmation": {"needs_confirmation", "active", "superseded", "retracted"},
            "superseded": {"superseded"},
            "retracted": {"retracted"},
        }
        if status not in allowed.get(current, set()):
            raise agent.FollowThroughConflict("The decision lifecycle transition is not allowed")
        if status == current:
            raise agent.FollowThroughError("The decision update does not change anything")
        before_token = agent.semantic_token(decision)
        decision["status"] = status
        decision["updated_at"] = now_stamp()
        visit["updated_at"] = decision["updated_at"]
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="decision_status_changed",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={"decision_id": decision_id, "status": {"before": current, "after": status}},
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=True,
            reason="visit_clinician_decision_lifecycle_changed",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/visits/<visit_id>/follow-ups", methods=["POST"])
@serialized_profile_mutation
def api_visit_follow_ups_add(visit_id):
    try:
        data = _workflow_request()
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        allowed = {
            "mutation_id",
            "expected_visit_token",
            "decision_id",
            "origin_kind",
            "text",
            "owner",
            "due_date",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported visit follow-up field")
        endpoint = "POST /api/visits/<visit_id>/follow-ups"
        target = f"visit:{visit_id}:follow-ups"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="follow_up_created",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        visit = agent.find_record(profile.get("visits", []), visit_id, "Visit")
        agent.validate_expected_token(visit, data.get("expected_visit_token"))
        decision = None
        if data.get("decision_id"):
            decision = agent.find_record(
                visit.get("decisions", []), str(data["decision_id"]), "Decision"
            )
        before_token = agent.semantic_token(visit)
        action = _new_action(
            profile,
            data,
            mutation_id=mutation_id,
            visit_id=visit_id,
            decision=decision,
            history_mutation_id=f"_internal-{agent.semantic_token([mutation_id, 'action'])[:32]}",
            history_endpoint=endpoint,
        )
        visit.setdefault("follow_up_ids", []).append(action["id"])
        visit["updated_at"] = now_stamp()
        event = agent.append_history(
            visit,
            endpoint=endpoint,
            operation="follow_up_created",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={"follow_up_id": action["id"], "decision_id": action.get("decision_id")},
        )
        result = _save_workflow_mutation(
            profile,
            clinical_change=False,
            reason="visit_follow_up_created",
            event=event,
            response_factory=lambda: {
                "visit": agent.public_visit(visit),
                "item": agent.public_action(action),
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return (
            jsonify(result),
            201,
        )
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/treatments/delete", methods=["POST"])
def api_delete_treatment():
    return (
        jsonify(
            {
                "error": "Text-based treatment deletion is no longer supported. Reload and edit by treatment ID."
            }
        ),
        410,
    )


@app.route("/api/alerts/<alert_id>/resolve", methods=["POST"])
@serialized_profile_mutation
def api_resolve_alert(alert_id):
    try:
        data = _workflow_request()
        allowed = {
            "mutation_id",
            "expected_token",
            "expected_profile_revision",
            "outcome",
            "visit_id",
            "decision_id",
            "follow_up_id",
            "follow_up",
        }
        _reject_unsupported_fields(data, allowed, "Unsupported alert resolution field")
        if "outcome" in data:
            _validate_outcome_request(data["outcome"])
        if "follow_up" in data:
            if not isinstance(data["follow_up"], dict):
                raise agent.FollowThroughError("follow_up must be an object")
            _reject_unsupported_fields(
                data["follow_up"],
                {"text", "owner", "due_date"},
                "Unsupported inline follow-up field",
            )
        has_follow_up_id = "follow_up_id" in data
        has_inline_follow_up = "follow_up" in data
        has_visit_link = "visit_id" in data
        if sum((has_follow_up_id, has_inline_follow_up, has_visit_link)) > 1:
            raise agent.FollowThroughError(
                "Use only one alert link mode: an existing follow-up, an inline follow-up, or a visit"
            )
        if "decision_id" in data and not has_visit_link:
            raise agent.FollowThroughError("decision_id requires visit_id")
        expected_token = str(data.get("expected_token") or "")
        expected_revision = data.get("expected_profile_revision")
        if not expected_token or expected_revision is None:
            raise agent.FollowThroughError(
                "expected_token and expected_profile_revision are required"
            )
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision < 0
        ):
            raise agent.FollowThroughError(
                "expected_profile_revision must be a non-negative integer"
            )
        mutation_id = data.get("mutation_id")
        if mutation_id is None:
            mutation_id = (
                f"_internal-alert-resolve-"
                f"{agent.semantic_token([alert_id, expected_token])[:32]}"
            )
        else:
            mutation_id = agent.validate_mutation_id(mutation_id)
        endpoint = "POST /api/alerts/<alert_id>/resolve"
        target = f"alert:{alert_id}"
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation="resolved",
            target=target,
        )
        if replay is not None:
            return jsonify(replay)
        alert = agent.find_record(profile.get("alerts", []), alert_id, "Alert")
        if (
            alert.get("resolved")
            or alert not in agent.active_alerts(profile)
            or agent.alert_token(alert) != expected_token
            or str(expected_revision) != str(profile.get("profile_revision"))
        ):
            raise agent.FollowThroughConflict(
                "The alert changed or is no longer active. Reload alerts before resolving it."
            )
        outcome = _outcome_from_request(data["outcome"]) if "outcome" in data else None
        visit_id = _required_link_id(data, "visit_id")
        decision_id = _required_link_id(data, "decision_id")
        if visit_id:
            visit = _eligible_alert_visit(profile, visit_id)
            if decision_id:
                _eligible_alert_decision(profile, visit, decision_id)
        follow_up_id = _required_link_id(data, "follow_up_id")
        follow_up = None
        if follow_up_id:
            follow_up = _eligible_alert_follow_up(profile, follow_up_id)
        if "follow_up" in data:
            if follow_up_id:
                raise agent.FollowThroughError(
                    "Use either follow_up_id or an inline follow_up, not both"
                )
            follow_up_data = data.get("follow_up")
            follow_up_payload = {
                **follow_up_data,
                "origin_kind": "alert",
                "mutation_id": mutation_id,
            }
            follow_up = _new_action(
                profile,
                follow_up_payload,
                mutation_id=mutation_id,
                alert_id=alert_id,
                history_mutation_id=(
                    f"_internal-{agent.semantic_token([mutation_id, 'alert-action'])[:32]}"
                ),
                history_endpoint=endpoint,
            )
            follow_up_id = follow_up["id"]
        before_token = agent.alert_token(alert)
        timestamp = now_stamp()
        alert["resolved"] = True
        alert["resolution"] = {
            "status": "resolved",
            "resolved_at": timestamp,
            "follow_up_id": follow_up_id,
            "visit_id": visit_id,
            "decision_id": decision_id,
        }
        if outcome is not None:
            alert["resolution"].update(
                {
                    "outcome_kind": outcome["kind"],
                    "outcome_text": outcome["text"],
                    "provenance": outcome["provenance"],
                }
            )
        event = agent.append_history(
            alert,
            endpoint=endpoint,
            operation="resolved",
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes={
                "resolved": {"before": False, "after": True},
                "resolution": alert["resolution"],
            },
        )
        if isinstance(profile.get("executive_summary"), dict):
            profile["executive_summary"]["alert_resolution_pending"] = True
        result = _save_workflow_mutation(
            profile,
            clinical_change=True,
            reason="active_alert_resolved_after_generation",
            event=event,
            response_factory=lambda: {
                "ok": True,
                "alert": agent.public_alert(alert),
                "follow_up": agent.public_action(follow_up) if follow_up else None,
                "workflow_revision": profile["workflow_revision"],
                "profile_revision": profile["profile_revision"],
            },
        )
        return jsonify(result)
    except (agent.FollowThroughError, KeyError) as exc:
        return _workflow_error(exc)


@app.route("/api/alerts/resolve/<int:idx>", methods=["POST"])
def api_resolve_alert_legacy(idx):
    return (
        jsonify(
            {
                "error": "Index-based alert resolution is no longer supported. Reload and resolve by alert ID."
            }
        ),
        410,
    )


@app.route("/api/treatments/update", methods=["POST"])
def api_treatments_update():
    return (
        jsonify(
            {
                "error": "Index-based treatment updates are no longer supported. Reload and edit by treatment ID."
            }
        ),
        410,
    )


@app.route("/api/treatments/<treatment_id>", methods=["POST"])
@serialized_profile_mutation
def api_treatment_edit(treatment_id):
    data = request.get_json(force=True) or {}
    action = data.get("action")
    expected_token = str(data.get("expected_token") or "")
    expected_revision = data.get("expected_profile_revision")
    if action not in {"remove", "complete"} or not expected_token or expected_revision is None:
        return (
            jsonify(
                {
                    "error": "action, expected_token, and expected_profile_revision are required"
                }
            ),
            400,
        )
    profile = agent.load_profile()
    classified = profile.get("treatments_classified", [])
    treatment = next((item for item in classified if item.get("id") == treatment_id), None)
    if (
        not agent.treatment_classification_is_current(profile)
        or str(expected_revision) != str(profile.get("profile_revision"))
        or treatment is None
        or agent.treatment_edit_token(profile, treatment) != expected_token
    ):
        return (
            jsonify(
                {
                    "error": "The treatment changed or classification is outdated. Reload before editing."
                }
            ),
            409,
        )
    source_ids = set(treatment.get("source_treatment_ids") or [])
    records = profile.get("patient", {}).get("current_treatment_records", [])
    if not source_ids or not any(item.get("id") in source_ids for item in records):
        return jsonify({"error": "Mapped raw treatment components are unavailable"}), 409
    overlapping = [
        item
        for item in classified
        if item.get("id") != treatment_id
        and source_ids & set(item.get("source_treatment_ids") or [])
    ]
    if overlapping:
        return (
            jsonify(
                {
                    "error": "Treatment source mapping overlaps another treatment. Refresh classification before editing."
                }
            ),
            409,
        )
    treatment_identities = agent.treatment_identity_set(
        treatment.get("text") or treatment.get("label") or ""
    )
    selected_records = [item for item in records if item.get("id") in source_ids]
    if len(treatment_identities) != 1 or any(
        agent.treatment_identity_set(record.get("text", "")) != treatment_identities
        or not agent.treatment_text_is_certifiable(record.get("text", ""))
        for record in selected_records
    ):
        return (
            jsonify(
                {
                    "error": "Treatment source coverage is not exclusive. Refresh classification before editing."
                }
            ),
            409,
        )
    if action == "remove":
        profile["patient"]["current_treatment_records"] = [
            item for item in records if item.get("id") not in source_ids
        ]
        profile["treatments_classified"] = [
            item for item in classified if item.get("id") != treatment_id
        ]
    else:
        for record in records:
            if record.get("id") in source_ids and "[completed]" not in record.get("text", ""):
                record["text"] = f"{record.get('text', '').strip()} [completed]"
        treatment["category"] = "completed"
    agent.rebuild_raw_treatments(profile)
    profile["treatments_classification_revision"] = (
        int(profile.get("profile_revision") or 0) + 1
    )
    profile["treatments_classification_job_id"] = "manual-treatment-edit"
    agent.save_profile(profile)
    return jsonify(
        {
            "ok": True,
            "treatments_classified": [
                {**item, "edit_token": agent.treatment_edit_token(profile, item)}
                for item in profile.get("treatments_classified", [])
            ],
        }
    )


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
    result = agent.poll_tracked_trials(
        profile,
        source_job_id="manual-trial-poll",
        generation_profile_revision=int(profile.get("profile_revision") or 0) + 1,
    )
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
    questions = []
    for stored in profile.get("appointment_questions", []):
        questions.append(agent.project_question(profile, stored))
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


# Cached pre-release tabs may call these until their short-lived static assets
# revalidate. Keep the routes inert so they hide the removed review UI without
# mutating the profile or surfacing a global load error.
def _empty_legacy_changes() -> dict:
    return {
        "acknowledged_at": None,
        "new": {
            "biomarkers": 0,
            "imaging": 0,
            "trials": 0,
            "papers": 0,
            "alerts": 0,
            "documents": 0,
            "judgments": 0,
            "symptoms": 0,
            "executive_summary": False,
            "total_new": 0,
        },
    }


@app.route("/api/changes")
def api_changes():
    return jsonify(_empty_legacy_changes())


@app.route("/api/changes/acknowledge", methods=["POST"])
def api_changes_acknowledge():
    return jsonify(_empty_legacy_changes())


@app.route("/api/summary/dismiss-action/<int:idx>", methods=["POST"])
@serialized_profile_mutation
def api_dismiss_action(idx):
    data = request.get_json(force=True) or {}
    required_preconditions = {"summary_revision", "expected_action"}
    if not isinstance(data, dict) or not required_preconditions.issubset(data):
        return (
            jsonify(
                {
                    "error": "summary_revision and expected_action are required. Refresh the assessment before dismissing an action."
                }
            ),
            400,
        )
    profile = agent.load_profile()
    summary = profile.get("executive_summary", {})
    if (
        not isinstance(summary, dict)
        or profile.get("summary_stale") is not False
        or summary.get("stale") is not False
    ):
        return (
            jsonify(
                {
                    "error": "The assessment is stale. Refresh it before reviewing or dismissing actions."
                }
            ),
            409,
        )
    actions = summary.get("next_actions", [])
    expected_revision = data["summary_revision"]
    current_revision = summary.get("summary_revision")
    if str(expected_revision or "") != str(current_revision or ""):
        return (
            jsonify(
                {
                    "error": "The assessment changed while this action was open. Review the updated action before dismissing it."
                }
            ),
            409,
        )
    if 0 <= idx < len(actions):
        expected_action = data["expected_action"]
        current_action = actions[idx].get("action", "")
        if str(expected_action) != str(current_action):
            return (
                jsonify(
                    {
                        "error": "This action changed while feedback was open. Review the updated action before dismissing it."
                    }
                ),
                409,
            )
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
    response = copy.deepcopy(summary)
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
    response["stale"] = bool(not agent.summary_is_current(profile) or judgment_context_changed)
    response["profile_updated_at"] = profile.get("profile_updated_at")
    response["recent_documents"] = sorted(
        agent.active_documents(profile),
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
    if response["stale"]:
        for field in (
            "overall_status",
            "status_confidence",
            "status_rationale",
            "key_concern",
            "summary",
            "prrt_status",
            "prrt_rationale",
            "cga_trend",
            "cga_trend_detail",
            "next_actions",
            "timeline",
            "best_trial",
            "claim_evidence",
        ):
            response.pop(field, None)
        response["status"] = "stale"
        response["content_hidden"] = True
    else:
        response["claim_evidence"] = agent.resolve_summary_evidence(profile, response)
        response["next_actions"] = agent.project_summary_actions(summary)
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
    profile = agent.load_profile()
    current_revision = int(profile.get("profile_revision") or 0)
    history_revision = data.get("history_revision")
    if history and str(history_revision) != str(current_revision):
        return (
            jsonify(
                {
                    "error": "The patient record changed. Clear the prior chat history before continuing.",
                    "profile_revision": current_revision,
                }
            ),
            409,
        )
    job, rejection = _submit_job(
        "chat",
        _run_chat_job,
        user_message[:10000],
        history,
        current_revision,
    )
    if rejection:
        return rejection
    legacy = _legacy_sync_result(job["id"])
    if legacy is not None:
        return jsonify(legacy), 500 if legacy.get("error") else 200
    return jsonify({"job_id": job["id"], "profile_revision": current_revision}), 202


@app.route("/")
def index():
    response = send_from_directory(app.static_folder, "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=_args.port, debug=False)
