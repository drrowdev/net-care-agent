#!/usr/bin/env python3
"""
NET Care Agent — Web UI backend
Deployed on Azure App Service (swedencentral)
Data persisted to /home/data (Azure Files mount)
"""

import atexit
import base64
import binascii
import copy
import datetime
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import sys
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, NamedTuple

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
from agent.schema import derive_date_precision, now_stamp  # noqa: E402

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
_artifact_validation_cache: dict[tuple[str, str], tuple[int, int, bool]] = {}

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
    "artifact_state",
}
_ACTIVE_STATUSES = {"queued", "running"}
_ARTIFACT_STATES = {
    "available",
    "expired",
    "not_retained",
    "unavailable",
    "none",
    "legacy_unknown",
}
_REPORT_JOB_TYPES = {"feed", "digest", "deep-sweep"}
_RESULT_JOB_TYPES = {"chat", "questions", "summary"}
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
                j["artifact_state"] = "none"
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
    if clean.get("artifact_state") not in _ARTIFACT_STATES:
        clean.pop("artifact_state", None)
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


def _job_artifact_contract(job: dict) -> tuple[str, str | None, set[str]]:
    if job.get("type") in _REPORT_JOB_TYPES:
        return "report", "report_file", {"reports"}
    if job.get("type") in _RESULT_JOB_TYPES:
        return "result", "result_file", {"job_results"}
    return "none", None, set()


def _job_artifact_state(job: dict) -> str:
    kind, field, _ = _job_artifact_contract(job)
    if kind == "none":
        return "none"
    stored = job.get("artifact_state")
    if stored in _ARTIFACT_STATES:
        if stored == "available" and not job.get(field):
            return "unavailable"
        return stored
    if field and job.get(field):
        return "available"
    if job.get("status") in _ACTIVE_STATUSES | {"error", "interrupted"}:
        return "none"
    return "legacy_unknown"


def _job_artifact_reference_unavailable(job: dict) -> bool:
    kind, field, roots = _job_artifact_contract(job)
    state = _job_artifact_state(job)
    if state == "unavailable":
        return True
    if kind == "none" or state != "available" or not field:
        return False
    reference = job.get(field)
    if not reference:
        return True
    try:
        path = safe_artifact_path(DATA_DIR, reference, roots)
        stat = path.stat()
        cache_key = (kind, reference)
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        cached = _artifact_validation_cache.get(cache_key)
        if cached and cached[:2] == fingerprint:
            return not cached[2]
        if kind == "report":
            path.read_text(encoding="utf-8")
        else:
            json.loads(path.read_text(encoding="utf-8"))
        if len(_artifact_validation_cache) >= 512:
            _artifact_validation_cache.clear()
        _artifact_validation_cache[cache_key] = (*fingerprint, True)
        return False
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        if isinstance(reference, str):
            try:
                path = safe_artifact_path(DATA_DIR, reference, roots)
                stat = path.stat()
                _artifact_validation_cache[(kind, reference)] = (
                    stat.st_mtime_ns,
                    stat.st_size,
                    False,
                )
            except (OSError, ValueError):
                pass
        return True


def _public_job_artifact(
    response: dict,
    job: dict,
    *,
    unavailable: bool = False,
) -> None:
    kind, _, _ = _job_artifact_contract(job)
    state = "unavailable" if unavailable else _job_artifact_state(job)
    stale = bool(
        response.get("derived_content_stale")
        or response.get("report_stale")
        or (isinstance(response.get("result"), dict) and response["result"].get("stale"))
    )
    response.pop("report_file", None)
    response.pop("result_file", None)
    response.pop("artifact_state", None)
    response["artifact"] = {
        "kind": kind,
        "state": state,
        "freshness": (
            "stale"
            if stale and state == "available"
            else ("current" if state == "available" else "unknown")
        ),
    }


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
            "artifact_state": "none",
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
        "artifact_state": "none",
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
    artifact_state = _job_artifact_state(job)
    artifact_unavailable = _job_artifact_reference_unavailable(job)
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
            superseded = generation_id is not None and generation_id != profile.get(
                "questions_generation_id"
            )
            questions_invalid = (
                generation_id is None
                or superseded
                or any(
                    item.get("stale")
                    for item in profile.get("appointment_questions", [])
                    if isinstance(item, dict)
                    and item.get("source") == "ai"
                    and item.get("generation_job_id") == generation_id
                )
            )
            if questions_invalid:
                result_same_revision_invalidated = not result_revision_stale
                result_revision_stale = True
                if superseded and not revision_was_stale:
                    response["derived_content_stale_reason"] = "question_generation_superseded"
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
        _public_job_artifact(response, job, unavailable=artifact_unavailable)
        return response
    if job.get("type") == "feed" and job.get("source_document_id"):
        response["receipt_url"] = f"/api/jobs/{job['id']}/receipt"
    report_ref = job.get("report_file")
    if artifact_unavailable:
        response["artifact_unavailable"] = True
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
            response["report_available_for_audit"] = (
                artifact_state == "available" and not artifact_unavailable
            )
            if artifact_unavailable:
                response["artifact_unavailable"] = True
        elif artifact_state == "available" and not artifact_unavailable:
            try:
                response["report"] = safe_artifact_path(
                    DATA_DIR, report_ref, {"reports"}
                ).read_text(encoding="utf-8")
            except (OSError, ValueError):
                response["artifact_unavailable"] = True
                artifact_unavailable = True
        elif artifact_state == "unavailable":
            response["artifact_unavailable"] = True
    result_ref = job.get("result_file")
    if result_ref and artifact_state == "available" and not artifact_unavailable:
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
            artifact_unavailable = True
    elif result_ref and artifact_state == "unavailable":
        response["artifact_unavailable"] = True
    _public_job_artifact(response, job, unavailable=artifact_unavailable)
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
                    job["artifact_state"] = "expired" if age > age_days * 86400 else "not_retained"
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
    research_consideration: dict | None = None,
    history_mutation_id: str | None = None,
    history_endpoint: str,
    history_target: str | None = None,
) -> dict:
    origin_kind = (
        "research_consideration"
        if research_consideration is not None
        else data.get("origin_kind") or ("visit_decision" if decision else "manual")
    )
    if origin_kind not in {
        "manual",
        "executive_summary_action",
        "alert",
        "visit_decision",
        "research_consideration",
    }:
        raise agent.FollowThroughError("Invalid origin_kind")
    if origin_kind == "research_consideration":
        if not isinstance(research_consideration, dict):
            raise agent.FollowThroughError("A valid research consideration is required")
        text = agent.validate_follow_up_text(data.get("text"))
        origin = {
            "kind": origin_kind,
            "source_id": research_consideration.get("id"),
            "source_job_id": None,
            "source_profile_revision": research_consideration.get("source_profile_revision"),
            "generation_id": None,
            "text": text,
            "snapshot": copy.deepcopy(research_consideration.get("snapshot")),
        }
    elif origin_kind == "executive_summary_action":
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


_SYMPTOM_MUTATION_META_FIELDS = {
    "mutation_id",
    "expected_profile_revision",
    "expected_workflow_revision",
    "expected_projection_token",
}
_SYMPTOM_CONTENT_FIELDS = {
    "symptom_text",
    "severity_level",
    "severity_detail",
    "reported_subject",
    "onset_date",
    "timing_text",
    "frequency_text",
    "triggers_text",
    "notes",
}
_SYMPTOM_OPTIONAL_TEXT_LIMITS = {
    "severity_detail": 500,
    "timing_text": 500,
    "frequency_text": 500,
    "triggers_text": 1000,
    "notes": 2000,
}


class _SymptomConflictError(ValueError):
    pass


class _SymptomNotFoundError(ValueError):
    pass


def _symptom_projection(profile: dict) -> dict:
    return agent.project_symptom_episodes(profile)


def _require_symptom_fields(data: dict, allowed: set[str]) -> None:
    unsupported = set(data) - allowed
    if unsupported:
        raise ValueError("Unsupported symptom episode field.")


def _require_symptom_revisions(profile: dict, data: dict) -> None:
    expected_profile = data.get("expected_profile_revision")
    expected_workflow = data.get("expected_workflow_revision")
    if isinstance(expected_profile, bool) or not isinstance(expected_profile, int):
        raise ValueError("expected_profile_revision must be an integer.")
    if isinstance(expected_workflow, bool) or not isinstance(expected_workflow, int):
        raise ValueError("expected_workflow_revision must be an integer.")
    if expected_profile != int(profile.get("profile_revision") or 0):
        raise _SymptomConflictError("The patient profile changed. Refresh and try again.")
    if expected_workflow != int(profile.get("workflow_revision") or 0):
        raise _SymptomConflictError("The workflow changed. Refresh and try again.")


def _require_projection_token(projection: dict, data: dict) -> None:
    token = data.get("expected_projection_token")
    if not isinstance(token, str) or not token:
        raise ValueError("expected_projection_token is required.")
    if not hmac.compare_digest(token, projection["projection_token"]):
        raise _SymptomConflictError("The symptom episode list changed. Refresh and try again.")


def _required_episode_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("symptom_text is required.")
    text = value.strip()
    if not text or len(text) > 500:
        raise ValueError("symptom_text must be between 1 and 500 characters.")
    return text


def _optional_episode_text(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null.")
    text = value.strip()
    if not text:
        return None
    if len(text) > _SYMPTOM_OPTIONAL_TEXT_LIMITS[field]:
        raise ValueError(f"{field} is too long.")
    return text


def _episode_date(value: Any, field: str) -> tuple[str | None, str]:
    if value in (None, ""):
        return None, "unknown"
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY, YYYY-MM, or YYYY-MM-DD date.")
    precision = derive_date_precision(value)
    if precision == "unknown":
        raise ValueError(f"{field} must be a valid YYYY, YYYY-MM, or YYYY-MM-DD date.")
    return value, precision


def _episode_content(
    data: dict,
    *,
    existing: dict | None = None,
) -> dict:
    result = dict(existing or {})
    if existing is None or "symptom_text" in data:
        result["symptom_text"] = _required_episode_text(data.get("symptom_text"))
    if existing is None or "severity_level" in data:
        severity = data.get("severity_level")
        if severity not in {None, "mild", "moderate", "severe"}:
            raise ValueError("severity_level must be mild, moderate, severe, or null.")
        result["severity_level"] = severity
    for field in _SYMPTOM_OPTIONAL_TEXT_LIMITS:
        if existing is None or field in data:
            result[field] = _optional_episode_text(data.get(field), field)
    if existing is None or "reported_subject" in data:
        subject = data.get("reported_subject", "unspecified")
        if subject not in {"patient", "caregiver", "unspecified"}:
            raise ValueError("reported_subject must be patient, caregiver, or unspecified.")
        result["reported_subject"] = subject
    if existing is None or "onset_date" in data:
        date_value, precision = _episode_date(data.get("onset_date"), "onset_date")
        result["onset_date"] = date_value
        result["onset_date_precision"] = precision
        result["onset_date_kind"] = "caregiver_entered" if date_value else "unknown"
    return result


def _episode_projection_row(projection: dict, episode_id: str, token: Any) -> dict:
    row = next(
        (item for item in projection["episodes"] if item.get("id") == episode_id),
        None,
    )
    if row is None:
        raise _SymptomNotFoundError("Symptom episode not found.")
    if not isinstance(token, str) or not token:
        raise ValueError("expected_episode_token is required.")
    if not hmac.compare_digest(token, row["token"]):
        raise _SymptomConflictError("The symptom episode changed. Refresh and try again.")
    return row


def _episode_record(profile: dict, episode_id: str) -> dict:
    episode = next(
        (
            item
            for item in profile.get("symptom_episodes", [])
            if isinstance(item, dict) and item.get("id") == episode_id
        ),
        None,
    )
    if episode is None:
        raise _SymptomNotFoundError("Symptom episode not found.")
    return episode


def _action_record(profile: dict, action_id: str) -> dict:
    action = next(
        (
            item
            for item in profile.get("caregiver_actions", [])
            if isinstance(item, dict) and item.get("id") == action_id
        ),
        None,
    )
    if action is None:
        raise _SymptomNotFoundError("Caregiver follow-up not found.")
    return action


def _validate_episode_action_link(
    profile: dict,
    *,
    action_id: Any,
    expected_token: Any,
    episode_id: str | None,
) -> dict:
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("caregiver_action_id is required.")
    action = _action_record(profile, action_id)
    if action.get("status") not in {"open", "in_progress"}:
        raise _SymptomConflictError("The caregiver follow-up is no longer eligible.")
    if not isinstance(expected_token, str) or not expected_token:
        raise ValueError("expected_action_token is required.")
    if not hmac.compare_digest(expected_token, agent.semantic_token(action)):
        raise _SymptomConflictError("The caregiver follow-up changed. Refresh and try again.")
    for episode in profile.get("symptom_episodes", []):
        if not isinstance(episode, dict) or episode.get("id") == episode_id:
            continue
        if episode.get("caregiver_action_id") == action_id:
            raise _SymptomConflictError(
                "The caregiver follow-up is already linked to another symptom episode."
            )
    for discrepancy in profile.get("treatment_discrepancies", []):
        if isinstance(discrepancy, dict) and discrepancy.get("caregiver_action_id") == action_id:
            raise _SymptomConflictError(
                "The caregiver follow-up is already linked to a treatment discrepancy."
            )
    allowed_owner = f"symptom_episode:{episode_id}" if episode_id else None
    other_owners = [
        ref for ref in agent.action_owner_refs(profile, action_id) if ref != allowed_owner
    ]
    if other_owners:
        raise _SymptomConflictError("The caregiver follow-up is already owned by another workflow.")
    return action


def _validate_inline_episode_follow_up(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("follow_up must be an object.")
    if set(value) - {"text", "owner", "due_date"}:
        raise ValueError("Unsupported follow_up field.")
    return {
        "text": agent.validate_follow_up_text(value.get("text")),
        "owner": agent.validate_owner(value.get("owner")),
        "due_date": agent.validate_date(value.get("due_date"), "due_date"),
    }


def _symptom_mutation_response(profile: dict, episode_id: str) -> dict:
    projection = _symptom_projection(profile)
    episode = next(
        (item for item in projection["episodes"] if item.get("id") == episode_id),
        None,
    )
    if episode is None:
        raise RuntimeError("Symptom episode disappeared before response generation.")
    return {
        "episode": episode,
        "follow_up": episode.get("follow_up"),
        "workflow_revision": projection["workflow_revision"],
        "profile_revision": projection["profile_revision"],
    }


def _symptom_mutation_error(exc: Exception):
    if isinstance(exc, agent.SymptomProjectionError):
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    if isinstance(exc, _SymptomNotFoundError):
        return jsonify({"error": str(exc), "code": "not_found"}), 404
    if isinstance(exc, _SymptomConflictError | agent.FollowThroughConflict):
        return jsonify({"error": str(exc), "code": "symptom_conflict"}), 409
    return jsonify({"error": str(exc), "code": "invalid_symptom_request"}), 400


_TREATMENT_META_FIELDS = {
    "mutation_id",
    "expected_profile_revision",
    "expected_workflow_revision",
    "expected_projection_token",
}
_TREATMENT_COURSE_TEXT_FIELDS = {
    "treatment_text",
    "treatment_type_text",
    "dose_text",
    "route_text",
    "frequency_text",
    "cycle_text",
    "schedule_text",
    "formulation_text",
    "indication_text",
    "notes",
}
_TREATMENT_COURSE_DATE_FIELDS = {"start_date", "stop_date", "planned_date"}
_TREATMENT_COURSE_FIELDS = (
    _TREATMENT_COURSE_TEXT_FIELDS | _TREATMENT_COURSE_DATE_FIELDS | {"legacy_component_ids"}
)
_TREATMENT_TEXT_LIMITS = {
    "treatment_text": 1000,
    "treatment_type_text": 500,
    "dose_text": 500,
    "route_text": 500,
    "frequency_text": 500,
    "cycle_text": 500,
    "schedule_text": 1000,
    "formulation_text": 500,
    "indication_text": 1000,
    "notes": 10000,
    "comparison_text": 10000,
    "note": 10000,
    "clinician_text": 500,
    "context_text": 2000,
}
_TREATMENT_TERMINAL_FIELDS = {"terminal_qualifier", "terminal_detail"}


class _TreatmentConflictError(ValueError):
    pass


class _TreatmentNotFoundError(ValueError):
    pass


def _treatment_projection(profile: dict) -> dict:
    return agent.project_treatment_reconciliation(profile)


def _require_treatment_revisions(profile: dict, data: dict) -> None:
    expected_profile = data.get("expected_profile_revision")
    expected_workflow = data.get("expected_workflow_revision")
    if isinstance(expected_profile, bool) or not isinstance(expected_profile, int):
        raise ValueError("expected_profile_revision must be an integer.")
    if isinstance(expected_workflow, bool) or not isinstance(expected_workflow, int):
        raise ValueError("expected_workflow_revision must be an integer.")
    if expected_profile != int(profile.get("profile_revision") or 0):
        raise _TreatmentConflictError("The patient profile changed. Refresh and try again.")
    if expected_workflow != int(profile.get("workflow_revision") or 0):
        raise _TreatmentConflictError("The workflow changed. Refresh and try again.")


def _require_treatment_projection_token(projection: dict, data: dict) -> None:
    token = data.get("expected_projection_token")
    if not isinstance(token, str) or not token:
        raise ValueError("expected_projection_token is required.")
    if not hmac.compare_digest(token, projection["projection_token"]):
        raise _TreatmentConflictError(
            "The treatment reconciliation record changed. Refresh and try again."
        )


def _exact_treatment_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null.")
    if required and not value.strip():
        raise ValueError(f"{field} is required.")
    if len(value) > _TREATMENT_TEXT_LIMITS[field]:
        raise ValueError(f"{field} is too long.")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{field} contains unsupported control characters.")
    return value


def _treatment_date(value: Any, field: str) -> tuple[str | None, str, str]:
    if value is None:
        return None, "unknown", "unknown"
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY, YYYY-MM, or YYYY-MM-DD date or null.")
    precision = derive_date_precision(value)
    if precision == "unknown":
        raise ValueError(f"{field} must be a valid YYYY, YYYY-MM, or YYYY-MM-DD date.")
    return value, precision, "caregiver_entered"


def _course_content(
    data: dict,
    projection: dict,
    *,
    existing: dict | None = None,
) -> dict:
    result = copy.deepcopy(existing or {})
    for field in _TREATMENT_COURSE_TEXT_FIELDS:
        if existing is None or field in data:
            result[field] = _exact_treatment_text(
                data.get(field),
                field,
                required=field == "treatment_text",
            )
    if existing is None or "legacy_component_ids" in data:
        values = data.get("legacy_component_ids", [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value for value in values
        ):
            raise ValueError("legacy_component_ids must be a list of component IDs.")
        if len(values) != len(set(values)):
            raise ValueError("legacy_component_ids cannot contain duplicates.")
        available = {
            component["id"]
            for row in projection["legacy_treatments"]
            for component in row["components"]
        }
        if any(value not in available for value in values):
            raise _TreatmentConflictError(
                "A selected legacy treatment component changed. Refresh and try again."
            )
        result["legacy_component_ids"] = list(values)
    for field in _TREATMENT_COURSE_DATE_FIELDS:
        if existing is None or field in data:
            value, precision, kind = _treatment_date(data.get(field), field)
            result[field] = value
            result[f"{field}_precision"] = precision
            result[f"{field}_kind"] = kind
    return result


def _treatment_row(projection: dict, collection: str, record_id: str, token: Any) -> dict:
    row = next((item for item in projection[collection] if item.get("id") == record_id), None)
    if row is None:
        raise _TreatmentNotFoundError("Treatment reconciliation record not found.")
    if not isinstance(token, str) or not token:
        raise ValueError("Expected record token is required.")
    if not hmac.compare_digest(token, row["token"]):
        raise _TreatmentConflictError(
            "The treatment reconciliation record changed. Refresh and try again."
        )
    return row


def _treatment_source_fact(projection: dict, record_ref: Any, token: Any) -> dict:
    if not isinstance(record_ref, str) or not record_ref:
        raise ValueError("source_fact_ref is required.")
    row = next((item for item in projection["source_facts"] if item["ref"] == record_ref), None)
    if row is None:
        raise _TreatmentNotFoundError("Treatment source fact not found.")
    if not isinstance(token, str) or not token:
        raise ValueError("expected_source_fact_token is required.")
    if not hmac.compare_digest(token, row["token"]):
        raise _TreatmentConflictError("The treatment source fact changed. Refresh and try again.")
    return row


def _require_complete_discrepancy_citations(row: dict) -> None:
    authority = row.get("citation_authority")
    if not isinstance(authority, dict) or authority.get("state") != "complete":
        raise _TreatmentConflictError(
            "This legacy discrepancy does not have two cited authorities and is read-only."
        )


def _course_record(profile: dict, course_id: str) -> dict:
    course = next(
        (
            item
            for item in profile.get("treatment_courses", [])
            if isinstance(item, dict) and item.get("id") == course_id
        ),
        None,
    )
    if course is None:
        raise _TreatmentNotFoundError("Treatment course not found.")
    return course


def _discrepancy_record(profile: dict, discrepancy_id: str) -> dict:
    discrepancy = next(
        (
            item
            for item in profile.get("treatment_discrepancies", [])
            if isinstance(item, dict) and item.get("id") == discrepancy_id
        ),
        None,
    )
    if discrepancy is None:
        raise _TreatmentNotFoundError("Treatment discrepancy not found.")
    return discrepancy


def _raw_row_source_entry_id(profile: dict, row: dict) -> str:
    """Resolve a projected raw row to its position-independent stored identity.

    The public row ID folds in ``source_order``, so it re-keys whenever an earlier
    row is removed. Workspace state is stored against the occurrence identity
    instead, which only changes when that row's own wording changes.
    """
    raw_rows = profile.get("patient", {}).get("current_treatments") or []
    keys = agent.raw_treatment_source_entry_ids(raw_rows)
    order = row.get("source_order")
    if isinstance(order, bool) or not isinstance(order, int) or not 0 <= order < len(keys):
        raise _TreatmentNotFoundError("Recorded treatment entry not found.")
    return keys[order]


def _treatment_row_disposition_response(profile: dict, row_id: str) -> dict:
    projection = _treatment_projection(profile)
    disposition = next(
        (item for item in projection["legacy_treatment_dispositions"] if item["row_id"] == row_id),
        None,
    )
    if disposition is None:
        raise RuntimeError("Recorded treatment entry disappeared before response generation.")
    return {
        "disposition": disposition,
        "legacy_treatment_hidden_count": projection["legacy_treatment_hidden_count"],
        "workflow_revision": projection["workflow_revision"],
        "profile_revision": projection["profile_revision"],
    }


def _treatment_mutation_response(
    profile: dict,
    *,
    course_id: str | None = None,
    discrepancy_id: str | None = None,
) -> dict:
    projection = _treatment_projection(profile)
    if discrepancy_id is None:
        course = next((item for item in projection["courses"] if item["id"] == course_id), None)
        if course is None:
            raise RuntimeError("Treatment course disappeared before response generation.")
        return {
            "course": course,
            "workflow_revision": projection["workflow_revision"],
            "profile_revision": projection["profile_revision"],
        }
    discrepancy = next(
        (item for item in projection["discrepancies"] if item["id"] == discrepancy_id),
        None,
    )
    if discrepancy is None:
        raise RuntimeError("Treatment discrepancy disappeared before response generation.")
    course = next(
        (item for item in projection["courses"] if item["id"] == discrepancy.get("course_id")),
        None,
    )
    return {
        "discrepancy": discrepancy,
        "course": course,
        "follow_up": discrepancy.get("follow_up"),
        "workflow_revision": projection["workflow_revision"],
        "profile_revision": projection["profile_revision"],
    }


def _treatment_mutation_error(exc: Exception):
    if isinstance(exc, agent.TreatmentProjectionError):
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    if isinstance(exc, _TreatmentNotFoundError):
        return jsonify({"error": str(exc), "code": "not_found"}), 404
    if isinstance(exc, _TreatmentConflictError | agent.FollowThroughConflict):
        return jsonify({"error": str(exc), "code": "treatment_conflict"}), 409
    return jsonify({"error": str(exc), "code": "invalid_treatment_request"}), 400


def _treatment_action_link(
    profile: dict,
    *,
    action_id: Any,
    expected_token: Any,
    discrepancy_id: str | None,
) -> dict:
    if not isinstance(action_id, str) or not action_id:
        raise ValueError("caregiver_action_id is required.")
    action = _action_record(profile, action_id)
    if action.get("status") not in {"open", "in_progress"}:
        raise _TreatmentConflictError("The caregiver follow-up is no longer eligible.")
    if not isinstance(expected_token, str) or not expected_token:
        raise ValueError("expected_action_token is required.")
    if not hmac.compare_digest(expected_token, agent.semantic_token(action)):
        raise _TreatmentConflictError("The caregiver follow-up changed. Refresh and try again.")
    for episode in profile.get("symptom_episodes", []):
        if isinstance(episode, dict) and episode.get("caregiver_action_id") == action_id:
            raise _TreatmentConflictError(
                "The caregiver follow-up is already linked to a symptom episode."
            )
    for discrepancy in profile.get("treatment_discrepancies", []):
        if not isinstance(discrepancy, dict) or discrepancy.get("id") == discrepancy_id:
            continue
        if discrepancy.get("caregiver_action_id") == action_id:
            raise _TreatmentConflictError(
                "The caregiver follow-up is already linked to another treatment discrepancy."
            )
    allowed_owner = f"treatment_discrepancy:{discrepancy_id}" if discrepancy_id else None
    other_owners = [
        ref for ref in agent.action_owner_refs(profile, action_id) if ref != allowed_owner
    ]
    if other_owners:
        raise _TreatmentConflictError(
            "The caregiver follow-up is already owned by another workflow."
        )
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
            final_revision = int(profile.get("profile_revision") or 0) + 1
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
                    "stage": ("done_with_warnings" if summary_error else "done"),
                    "report_file": _artifact_ref(rpath),
                    "artifact_state": "available",
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
            final_revision = int(profile.get("profile_revision") or 0) + 1
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
                    "stage": ("done_with_warnings" if summary_error else "done"),
                    "report_file": _artifact_ref(rpath),
                    "artifact_state": "available",
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
                "artifact_state": "available",
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
                "artifact_state": "available",
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
            summary_error = _refresh_summary(profile, generation_id=job_id)
            agent.save_profile(profile, clinical_change=False)
            result = {
                "summary": profile["executive_summary"],
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
                "artifact_state": "available",
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
                "artifact_state": "available",
                "profile_revision": generation_revision,
                "finished_at": now_stamp(),
            },
        )
    except Exception as exc:
        _fail_job(job_id, exc)


# ── API routes ────────────────────────────────────────────────────────────────
# Referrer policies that still emit a Referer on same-origin requests, which the
# App Service Easy Auth middleware requires for its pre-Flask CSRF check.
_EASY_AUTH_COMPATIBLE_REFERRER_POLICIES = frozenset(
    {
        "same-origin",
        "strict-origin-when-cross-origin",
        "origin-when-cross-origin",
        "no-referrer-when-downgrade",
        "unsafe-url",
    }
)
_REFERRER_POLICY = "same-origin"


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
    # `no-referrer` broke every state-changing request in production: App Service
    # Easy Auth middleware runs its own CSRF check before Flask and rejects a
    # same-origin POST that arrives with an empty Referer
    # (HTTP 403, sub-status 60, "Cross-site request forgery detected ... from
    # referer ''"). `same-origin` restores the Referer only for our own origin,
    # where it never leaves this site, and keeps sending nothing at all to every
    # cross-origin destination (Google Fonts, PubMed, ClinicalTrials.gov), so no
    # path, query, or origin leaks off-site. Do not weaken this to `no-referrer`.
    response.headers["Referrer-Policy"] = _REFERRER_POLICY
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


def _easy_auth_enabled() -> bool:
    return os.environ.get("WEBSITE_AUTH_ENABLED", "").strip().lower() == "true"


def _is_hosted() -> bool:
    return _easy_auth_enabled() or any(
        os.environ.get(name)
        for name in ("WEBSITE_INSTANCE_ID", "WEBSITE_SITE_NAME", "WEBSITE_HOSTNAME")
    )


_PRINCIPAL_ID_CLAIM_TYPES = (
    "http://schemas.microsoft.com/identity/claims/objectidentifier",
    "oid",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier",
    "sub",
)

# Bounds that keep a hostile proxy from forcing unbounded parsing work. App
# Service caps a single request header well below these values.
_MAX_PRINCIPAL_HEADER_CHARS = 16384
_MAX_PRINCIPAL_BLOB_BYTES = 12288
_MAX_PRINCIPAL_CLAIMS = 512
_MAX_PRINCIPAL_VALUE_CHARS = 512

# Fixed, PHI-free response discriminators. Values never leave the process.
_PRINCIPAL_SOURCE_ENCODED_CLAIM = "encoded_claim"
_PRINCIPAL_SOURCE_PROVIDER_ID_HEADER = "provider_id_header"
_PRINCIPAL_SOURCE_NAME_HEADER = "principal_name_header"
_PRINCIPAL_SOURCE_PROVIDER_ID_NAME_COMPAT = "provider_id_name_compat"
_PRINCIPAL_SOURCE_ABSENT = "absent"
_PRINCIPAL_SOURCES = frozenset(
    {
        _PRINCIPAL_SOURCE_ENCODED_CLAIM,
        _PRINCIPAL_SOURCE_PROVIDER_ID_HEADER,
        _PRINCIPAL_SOURCE_NAME_HEADER,
        _PRINCIPAL_SOURCE_PROVIDER_ID_NAME_COMPAT,
        _PRINCIPAL_SOURCE_ABSENT,
    }
)
_AUTH_REASON_PRINCIPAL_ABSENT = "principal_absent"
_AUTH_REASON_PRINCIPAL_MALFORMED = "principal_malformed"
_AUTH_REASON_PRINCIPAL_NOT_ALLOWED = "principal_not_allowed"
_AUTH_REASON_CROSS_ORIGIN = "cross_origin"
_AUTH_REASON_HOSTED_AUTH_UNAVAILABLE = "hosted_auth_unavailable"
_AUTH_FAILURE_REASONS = frozenset(
    {
        _AUTH_REASON_PRINCIPAL_ABSENT,
        _AUTH_REASON_PRINCIPAL_MALFORMED,
        _AUTH_REASON_PRINCIPAL_NOT_ALLOWED,
        _AUTH_REASON_CROSS_ORIGIN,
        _AUTH_REASON_HOSTED_AUTH_UNAVAILABLE,
    }
)

# Deliberately narrow: one "@", no whitespace, a dotted domain, bounded labels.
# This only recognises a shape; it never rewrites or widens the compared value.
_EMAIL_LIKE_NAME = re.compile(r"\A[^@\s]{1,64}@[^@\s]{1,252}\.[^@\s.]{2,63}\Z")


class _PrincipalDecision(NamedTuple):
    """Typed identity candidates parsed from trusted Easy Auth headers."""

    principal_id: str | None
    id_source: str | None
    principal_name: str | None
    name_source: str | None
    malformed: bool


def _bounded_header_value(name: str) -> str:
    raw = request.headers.get(name) or ""
    if len(raw) > _MAX_PRINCIPAL_HEADER_CHARS:
        return ""
    value = raw.strip()
    if len(value) > _MAX_PRINCIPAL_VALUE_CHARS or not value.isprintable():
        return ""
    return value


def _is_email_like(value: str) -> bool:
    return bool(_EMAIL_LIKE_NAME.fullmatch(value))


def _decode_principal_blob(encoded: str) -> object | None:
    """Decode a standard or URL-safe base64 principal blob, or return ``None``.

    Missing padding is restored, but corrupt alphabets, impossible lengths,
    mixed alphabets, oversized payloads, and non-JSON bodies all fail closed.
    """
    if len(encoded) > _MAX_PRINCIPAL_HEADER_CHARS or not encoded.isascii():
        return None
    if "=" in encoded:
        if len(encoded) % 4 or "=" in encoded.rstrip("="):
            return None
        candidate = encoded
    else:
        if len(encoded) % 4 == 1:
            return None
        candidate = encoded + "=" * (-len(encoded) % 4)
    urlsafe = "-" in candidate or "_" in candidate
    standard = "+" in candidate or "/" in candidate
    if urlsafe and standard:
        return None
    try:
        decoded = base64.b64decode(
            candidate.encode("ascii"),
            altchars=b"-_" if urlsafe else None,
            validate=True,
        )
    except (ValueError, binascii.Error):
        return None
    if len(decoded) > _MAX_PRINCIPAL_BLOB_BYTES:
        return None
    try:
        return json.loads(decoded)
    except (ValueError, UnicodeDecodeError):
        return None
    except RecursionError:
        # A bounded but deeply nested payload (e.g. thousands of nested arrays
        # inside the size limit) exhausts the parser's stack. `RecursionError`
        # is a `RuntimeError`, not a `ValueError`, so without this it would
        # escape as a Flask 500 instead of the fixed `principal_malformed` 401.
        return None


def _claim_principal_id(principal: object) -> tuple[str | None, bool]:
    """Return ``(selected_id, malformed)`` for the canonical claim tiers."""
    if not isinstance(principal, dict):
        return None, True
    claims = principal.get("claims", [])
    if not isinstance(claims, list) or len(claims) > _MAX_PRINCIPAL_CLAIMS:
        return None, True
    values_by_type: dict[str, set[str]] = {
        claim_type: set() for claim_type in _PRINCIPAL_ID_CLAIM_TYPES
    }
    for claim in claims:
        if not isinstance(claim, dict):
            return None, True
        claim_type = claim.get("typ")
        claim_value = claim.get("val")
        if not isinstance(claim_type, str) or not isinstance(claim_value, str):
            return None, True
        claim_type = claim_type.strip().lower()
        claim_value = claim_value.strip()
        if not claim_type:
            return None, True
        if claim_type in values_by_type:
            if not claim_value or len(claim_value) > _MAX_PRINCIPAL_VALUE_CHARS:
                return None, True
            values_by_type[claim_type].add(claim_value)

    for claim_type in _PRINCIPAL_ID_CLAIM_TYPES:
        values = values_by_type[claim_type]
        if len(values) > 1:
            return None, True
        if values:
            return next(iter(values)), False
    return None, False


def _principal_decision() -> _PrincipalDecision:
    """Parse typed identity candidates from the trusted Easy Auth headers.

    Two namespaces are kept strictly separate:

    * **ID** — the canonical encoded claim (object identifier, ``oid``,
      name identifier, then ``sub``), else the ``X-MS-CLIENT-PRINCIPAL-ID``
      provider header. Compared case-sensitively and exactly.
    * **Name** — ``X-MS-CLIENT-PRINCIPAL-NAME``. Compared with
      ``str.casefold()`` only.

    Live-platform compatibility bridge: the Linux App Service configuration in
    use injects the account's email into ``X-MS-CLIENT-PRINCIPAL-ID`` and does
    not guarantee that ``X-MS-CLIENT-PRINCIPAL`` or
    ``X-MS-CLIENT-PRINCIPAL-NAME`` reaches the worker. An ID-header value that
    matches the bounded ``local@domain`` shape is therefore *also* offered as a
    convenience name candidate. It is never normalised beyond ``casefold()``
    and never gains stable-object-ID semantics. When both a name header and an
    email-shaped ID header exist and are email-shaped but differ after
    ``casefold()``, the name path fails closed rather than widening access.
    """
    header_id = _bounded_header_value("X-MS-CLIENT-PRINCIPAL-ID")
    header_name = _bounded_header_value("X-MS-CLIENT-PRINCIPAL-NAME")
    encoded = (request.headers.get("X-MS-CLIENT-PRINCIPAL") or "").strip()

    principal_id: str | None = None
    id_source: str | None = None
    if encoded:
        principal = _decode_principal_blob(encoded)
        if principal is None:
            return _PrincipalDecision(None, None, None, None, True)
        claim_id, malformed = _claim_principal_id(principal)
        if malformed:
            return _PrincipalDecision(None, None, None, None, True)
        if claim_id is not None:
            principal_id, id_source = claim_id, _PRINCIPAL_SOURCE_ENCODED_CLAIM
    if principal_id is None and header_id:
        principal_id, id_source = header_id, _PRINCIPAL_SOURCE_PROVIDER_ID_HEADER

    principal_name: str | None = None
    name_source: str | None = None
    compat_name = header_id if header_id and _is_email_like(header_id) else ""
    if header_name:
        if (
            compat_name
            and _is_email_like(header_name)
            and header_name.casefold() != compat_name.casefold()
        ):
            principal_name, name_source = None, None
        else:
            principal_name, name_source = header_name, _PRINCIPAL_SOURCE_NAME_HEADER
    elif compat_name:
        principal_name = compat_name
        name_source = _PRINCIPAL_SOURCE_PROVIDER_ID_NAME_COMPAT

    return _PrincipalDecision(principal_id, id_source, principal_name, name_source, False)


def _principal_source_label(decision: _PrincipalDecision) -> str:
    for source in (decision.id_source, decision.name_source):
        if source in _PRINCIPAL_SOURCES:
            return source
    return _PRINCIPAL_SOURCE_ABSENT


def _configured_allowlist(name: str) -> set[str]:
    return {item.strip() for item in os.environ.get(name, "").split(",") if item.strip()}


def _hosted_principal_allowed(decision: _PrincipalDecision) -> bool:
    """Allow when any configured typed allowlist matches its typed candidate.

    Both allowlists empty preserves the pre-existing Easy-Auth-only posture:
    any principal the platform authenticated is accepted. Only one typed match
    is required, so an operator can migrate an entry from
    ``AUTH_ALLOWED_PRINCIPAL_IDS`` to ``AUTH_ALLOWED_PRINCIPAL_NAMES`` without
    an atomic lockout window.
    """
    id_allowlist = _configured_allowlist("AUTH_ALLOWED_PRINCIPAL_IDS")
    # `casefold()` is Unicode caseless matching, not a normalizer: it never
    # rewrites dots, plus tags, or domains. Configure the exact account name.
    name_allowlist = {
        item.casefold() for item in _configured_allowlist("AUTH_ALLOWED_PRINCIPAL_NAMES")
    }
    if not id_allowlist and not name_allowlist:
        return True
    if id_allowlist and decision.principal_id is not None and decision.principal_id in id_allowlist:
        return True
    return bool(
        name_allowlist
        and decision.principal_name is not None
        and decision.principal_name.casefold() in name_allowlist
    )


def _auth_failure(status: int, message: str, *, reason: str, principal_source: str | None = None):
    """Return a PHI-free auth failure body carrying only fixed discriminators."""
    body: dict[str, str] = {
        "error": message,
        "reason": reason if reason in _AUTH_FAILURE_REASONS else _AUTH_REASON_PRINCIPAL_NOT_ALLOWED,
    }
    if principal_source is not None:
        body["principal_source"] = (
            principal_source if principal_source in _PRINCIPAL_SOURCES else _PRINCIPAL_SOURCE_ABSENT
        )
    return jsonify(body), status


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
            return _auth_failure(
                503,
                "Hosted authentication is not enabled.",
                reason=_AUTH_REASON_HOSTED_AUTH_UNAVAILABLE,
            )
        decision = _principal_decision()
        if decision.malformed:
            return _auth_failure(
                401,
                "Authentication required.",
                reason=_AUTH_REASON_PRINCIPAL_MALFORMED,
                principal_source=_PRINCIPAL_SOURCE_ABSENT,
            )
        if decision.principal_id is None and decision.principal_name is None:
            return _auth_failure(
                401,
                "Authentication required.",
                reason=_AUTH_REASON_PRINCIPAL_ABSENT,
                principal_source=_PRINCIPAL_SOURCE_ABSENT,
            )
        if not _hosted_principal_allowed(decision):
            return _auth_failure(
                403,
                "Access denied.",
                reason=_AUTH_REASON_PRINCIPAL_NOT_ALLOWED,
                principal_source=_principal_source_label(decision),
            )
    elif not local_bypass:
        return _auth_failure(
            401,
            "Authentication required.",
            reason=_AUTH_REASON_PRINCIPAL_ABSENT,
            principal_source=_PRINCIPAL_SOURCE_ABSENT,
        )
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _origin_is_same(hosted=hosted):
        return _auth_failure(
            403,
            "Cross-origin request denied.",
            reason=_AUTH_REASON_CROSS_ORIGIN,
        )
    return None


@app.before_request
def _lazy_init():
    """Load jobs on the first authorized request — by then Azure Files is mounted.

    Registered *after* ``_protect_api`` on purpose: Flask runs ``before_request``
    handlers in registration order, so an unauthenticated, denied, or
    cross-origin ``/api/*`` request is rejected before any job history load,
    retention prune, or source prune touches storage.
    """
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
    - ``newest_snapshot_age_seconds``: float | null (informational only — see
      the note in the backup freshness block below; never alarm on it)
    - ``newest_backup_age_seconds``: float | null
    - ``backup_out_of_date``: bool (daily backup missing, or the profile was
      last saved more than ``BACKUP_MAX_LAG_DAYS`` calendar days after the
      newest backup was taken)
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
    snap_mtime = agent_backups.newest_file_mtime(DATA_DIR / "snapshots", "profile_*.json")
    backup_mtime = agent_backups.newest_file_mtime(DATA_DIR / "backups", "profile_*.json")
    now = time.time()
    snap_age = None if snap_mtime is None else now - snap_mtime
    backup_age = None if backup_mtime is None else now - backup_mtime
    try:
        profile_mtime = agent.PROFILE_PATH.stat().st_mtime
        profile_age = max(0.0, now - profile_mtime)
    except OSError:
        profile_mtime = None
        profile_age = None

    # Judge the daily backup against the cadence it is actually written on.
    #
    # ``daily_backup`` writes one file per calendar day while the profile is
    # saved many times a day, so "the backup is older than the profile" is the
    # ordinary steady state, not a fault. The previous check compared the two
    # ages with a 5-minute grace, which was structurally true from the second
    # save of every day until midnight: /api/health reported degraded almost
    # permanently and masked the real signals.
    #
    # Because ``copy2`` preserves mtimes and ``daily_backup`` names the file
    # after the mtime it copies, the backup's mtime is the mtime of the profile
    # revision it captured, so comparing calendar days compares like with like.
    # A lag past the tolerance means the profile was saved on a day that
    # produced no backup at all, which is a genuine failure of the writer. Pure
    # age is deliberately not used: a profile left untouched for a week keeps a
    # week-old backup that protects it perfectly.
    backup_missing = backup_mtime is None
    backup_stale = False
    if backup_mtime is not None and profile_mtime is not None:
        lag_days = agent_backups.backup_lag_days(profile_mtime, backup_mtime)
        # An unreadable timestamp is treated as stale rather than raising.
        backup_stale = lag_days is None or lag_days > agent_backups.BACKUP_MAX_LAG_DAYS
    backup_out_of_date = profile_status == "ok" and (backup_missing or backup_stale)

    # ``newest_snapshot_age_seconds`` is reported but deliberately NOT alarmed
    # on. ``rotating_snapshot`` copies the PRE-write profile with
    # ``shutil.copy2``, which preserves the source mtime, so the newest snapshot
    # always carries the *previous* profile revision's mtime. It is therefore
    # older than the profile by construction on every single save, and after an
    # idle week one save writes a brand-new snapshot still stamped a week old.
    # Snapshot age measures how old the prior revision is, never whether
    # snapshotting works, so any threshold on it would false-alarm exactly the
    # way the backup check did.

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
    alerts = [agent.public_alert(item) for item in agent.active_alerts(profile)]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date") or "", reverse=True)[
        :50
    ]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date") or "", reverse=True)[:3]
    active_documents = agent.active_documents(profile)
    docs = sorted(active_documents, key=lambda x: x.get("date") or "", reverse=True)[:5]
    latest_document_import = max(
        active_documents,
        key=lambda item: item.get("added_at") or "",
        default=None,
    )
    return jsonify(
        {
            "patient": profile.get("patient", {}),
            "profile_revision": profile.get("profile_revision"),
            "alerts": alerts,
            "recent_biomarkers": bms,
            "recent_imaging": imgs,
            "recent_documents": docs,
            "latest_document_import": (
                {
                    key: latest_document_import.get(key)
                    for key in ("added_at", "date", "type", "summary")
                    if key in latest_document_import
                }
                if latest_document_import is not None
                else None
            ),
            "stats": {
                "trials_tracked": len(profile.get("trials_tracked", [])),
                "literature_watched": len(profile.get("literature_watched", [])),
                "total_documents": len(profile.get("documents", [])),
                "total_biomarkers": len(profile.get("biomarkers", [])),
            },
            "latest_research_update": agent.public_latest_research_update(profile),
        }
    )


@app.route("/api/patient/biomarker-series")
def api_biomarker_series():
    """Return the complete bounded longitudinal biomarker read projection."""
    profile = agent.load_profile()
    try:
        projection = agent.project_biomarker_series(profile)
    except agent.BiomarkerProjectionError as exc:
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    return jsonify(projection)


@app.route("/api/patient/imaging-series")
def api_imaging_series():
    """Return the complete bounded longitudinal imaging read projection."""
    profile = agent.load_profile()
    try:
        projection = agent.project_imaging_series(profile)
    except agent.ImagingProjectionError as exc:
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    return jsonify(projection)


def _imaging_record_text_response(record_ref: str, *, evidence_only: bool):
    profile = agent.load_profile()
    try:
        text = agent.imaging_record_text(
            profile,
            record_ref,
            evidence_only=evidence_only,
        )
    except agent.ImagingProjectionError as exc:
        status = (
            404
            if exc.code
            in {
                "imaging_record_not_found",
                "imaging_source_unavailable",
                "imaging_evidence_unavailable",
            }
            else 422
        )
        return jsonify({"error": exc.public_message, "code": exc.code}), status
    return app.response_class(text, mimetype="text/plain")


@app.route("/api/patient/imaging-series/<record_ref>/source")
@_source_auth_required
def api_imaging_series_source(record_ref):
    """Resolve an opaque imaging row ID to validated extracted source text."""
    return _imaging_record_text_response(record_ref, evidence_only=False)


@app.route("/api/patient/imaging-series/<record_ref>/evidence")
@_source_auth_required
def api_imaging_series_evidence(record_ref):
    """Resolve an opaque imaging row ID to its validated exact evidence span."""
    return _imaging_record_text_response(record_ref, evidence_only=True)


@app.route("/api/patient/symptom-episodes")
def api_symptom_episodes():
    """Return the complete bounded symptom observation and episode projection."""
    profile = agent.load_profile()
    try:
        projection = _symptom_projection(profile)
    except agent.SymptomProjectionError as exc:
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    return jsonify(projection)


def _symptom_observation_text_response(record_ref: str, *, evidence_only: bool):
    profile = agent.load_profile()
    try:
        text = agent.symptom_observation_text(
            profile,
            record_ref,
            evidence_only=evidence_only,
        )
    except agent.SymptomProjectionError as exc:
        status = (
            404
            if exc.code
            in {
                "symptom_observation_not_found",
                "symptom_source_unavailable",
                "symptom_evidence_unavailable",
            }
            else 422
        )
        return jsonify({"error": exc.public_message, "code": exc.code}), status
    return app.response_class(text, mimetype="text/plain")


@app.route("/api/patient/symptom-episodes/observations/<record_ref>/source")
@_source_auth_required
def api_symptom_observation_source(record_ref):
    """Resolve an opaque symptom observation reference to validated source text."""
    return _symptom_observation_text_response(record_ref, evidence_only=False)


@app.route("/api/patient/symptom-episodes/observations/<record_ref>/evidence")
@_source_auth_required
def api_symptom_observation_evidence(record_ref):
    """Resolve an opaque symptom observation reference to exact evidence text."""
    return _symptom_observation_text_response(record_ref, evidence_only=True)


@app.route("/api/patient/treatment-reconciliation")
def api_treatment_reconciliation():
    """Return the complete bounded treatment reconciliation projection."""
    profile = agent.load_profile()
    try:
        projection = _treatment_projection(profile)
    except agent.TreatmentProjectionError as exc:
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    return jsonify(projection)


def _treatment_source_fact_text_response(record_ref: str, *, evidence_only: bool):
    profile = agent.load_profile()
    try:
        text = agent.treatment_source_fact_text(
            profile,
            record_ref,
            evidence_only=evidence_only,
        )
    except agent.TreatmentProjectionError as exc:
        status = (
            404
            if exc.code
            in {
                "treatment_source_fact_not_found",
                "treatment_evidence_unavailable",
            }
            else 422
        )
        return jsonify({"error": exc.public_message, "code": exc.code}), status
    return app.response_class(text, mimetype="text/plain")


@app.route("/api/patient/treatment-reconciliation/source-facts/<record_ref>/source")
@_source_auth_required
def api_treatment_source_fact_source(record_ref):
    """Resolve an opaque treatment source-fact reference to validated source text."""
    return _treatment_source_fact_text_response(record_ref, evidence_only=False)


@app.route("/api/patient/treatment-reconciliation/source-facts/<record_ref>/evidence")
@_source_auth_required
def api_treatment_source_fact_evidence(record_ref):
    """Resolve an opaque treatment source-fact reference to exact evidence text."""
    return _treatment_source_fact_text_response(record_ref, evidence_only=True)


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
    if isinstance(exc, agent.TreatmentLinkConflict):
        code = "treatment_course_link_conflict"
    elif isinstance(exc, agent.TreatmentProjectionRegression):
        code = "treatment_projection_regression"
    elif status == 409:
        code = "import_conflict"
    else:
        code = "invalid_receipt_change"
    payload = {
        "error": str(exc),
        "code": code,
    }
    if isinstance(exc, agent.TreatmentLinkConflict):
        payload["blocking_courses"] = exc.courses
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
        recap, authority_manifest = agent.project_visit_recap_with_authority(profile, visit)
        profile_revision = profile.get("profile_revision", 0)
        workflow_revision = profile.get("workflow_revision", 0)
        recap_token = agent.semantic_token(
            {
                "visit_id": visit_id,
                "visit_token": expected_token,
                "profile_revision": profile_revision,
                "workflow_revision": workflow_revision,
                "recap": recap,
                "authority_manifest": authority_manifest,
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
            if not agent.visit_transition_allowed(visit.get("status") or "planned", target_status):
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
def api_treatment_edit(treatment_id):
    return (
        jsonify(
            {
                "error": "Generated-classification treatment edits are no longer supported. Review treatment status in Patient → Treatments."
            }
        ),
        410,
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


# ── research shortlist and disposition ───────────────────────────────────────
_RESEARCH_META_FIELDS = {
    "mutation_id",
    "expected_profile_revision",
    "expected_workflow_revision",
    "expected_projection_token",
}


def _research_error(exc: Exception):
    if isinstance(exc, agent.ResearchProjectionError):
        return jsonify({"error": exc.public_message, "code": exc.code}), 422
    if isinstance(exc, agent.FollowThroughConflict):
        return jsonify({"error": str(exc), "code": "research_conflict"}), 409
    if isinstance(exc, KeyError):
        return jsonify({"error": str(exc.args[0]), "code": "not_found"}), 404
    return jsonify({"error": str(exc), "code": "invalid_research_request"}), 400


def _require_research_fields(data: dict, allowed: set[str]) -> None:
    if set(data) - allowed:
        raise ValueError("Unsupported research workflow field.")


def _require_research_authority(profile: dict, projection: dict, data: dict) -> None:
    expected_profile = data.get("expected_profile_revision")
    expected_workflow = data.get("expected_workflow_revision")
    if isinstance(expected_profile, bool) or not isinstance(expected_profile, int):
        raise ValueError("expected_profile_revision must be an integer.")
    if isinstance(expected_workflow, bool) or not isinstance(expected_workflow, int):
        raise ValueError("expected_workflow_revision must be an integer.")
    if expected_profile != profile.get("profile_revision"):
        raise agent.FollowThroughConflict("The patient profile changed. Refresh and try again.")
    if expected_workflow != profile.get("workflow_revision"):
        raise agent.FollowThroughConflict("The workflow changed. Refresh and try again.")
    expected_projection = data.get("expected_projection_token")
    if not isinstance(expected_projection, str) or not expected_projection:
        raise ValueError("expected_projection_token is required.")
    if not hmac.compare_digest(expected_projection, projection["projection_token"]):
        raise agent.FollowThroughConflict("The research workspace changed. Refresh and try again.")


def _research_row(profile: dict, record_id: str, expected_token: object) -> tuple[str, dict]:
    matches = [
        (item_type, row)
        for item_type, collection in (
            ("trial", "trials_tracked"),
            ("paper", "literature_watched"),
        )
        for row in profile.get(collection, [])
        if isinstance(row, dict) and row.get("research_record_id") == record_id
    ]
    if len(matches) != 1:
        raise KeyError("Research occurrence not found.")
    if not isinstance(expected_token, str) or not expected_token:
        raise ValueError("expected_item_token is required.")
    if not hmac.compare_digest(expected_token, agent.semantic_token(matches[0][1])):
        raise agent.FollowThroughConflict("The research occurrence changed. Refresh and try again.")
    return matches[0]


def _research_consideration(
    profile: dict,
    consideration_id: str,
    expected_token: object,
) -> dict:
    matches = [
        item
        for item in profile.get("research_considerations", [])
        if isinstance(item, dict) and item.get("id") == consideration_id
    ]
    if len(matches) != 1:
        raise KeyError("Research consideration not found.")
    if not isinstance(expected_token, str) or not expected_token:
        raise ValueError("expected_consideration_token is required.")
    if not hmac.compare_digest(expected_token, agent.semantic_token(matches[0])):
        raise agent.FollowThroughConflict(
            "The research consideration changed. Refresh and try again."
        )
    return matches[0]


def _research_mutation_response(profile: dict, consideration_id: str) -> dict:
    projection = agent.project_research_workspace(profile)
    consideration = next(
        item for item in projection["considerations"] if item["id"] == consideration_id
    )
    return {
        "consideration": consideration,
        "workflow_revision": projection["workflow_revision"],
        "profile_revision": projection["profile_revision"],
    }


def _save_research_mutation(profile: dict, event: dict, consideration_id: str) -> dict:
    return _save_workflow_mutation(
        profile,
        clinical_change=False,
        reason="",
        event=event,
        response_factory=lambda: _research_mutation_response(profile, consideration_id),
    )


@app.route("/api/patient/research-workspace")
def api_research_workspace():
    try:
        return jsonify(agent.project_research_workspace(agent.load_profile()))
    except agent.ResearchProjectionError as exc:
        return _research_error(exc)


@app.route("/api/research-considerations", methods=["POST"])
def api_create_research_consideration():
    try:
        data = _workflow_request()
        _require_research_fields(
            data,
            _RESEARCH_META_FIELDS | {"research_record_id", "expected_item_token"},
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        record_id = data.get("research_record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("research_record_id is required.")
        endpoint = "POST /api/research-considerations"
        operation = "created"
        target = f"research_occurrence:{record_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = agent.project_research_workspace(profile)
            _require_research_authority(profile, projection, data)
            item_type, row = _research_row(profile, record_id, data.get("expected_item_token"))
            if any(
                item.get("research_record_id") == record_id
                for item in profile.get("research_considerations", [])
                if isinstance(item, dict)
            ):
                raise agent.FollowThroughConflict(
                    "This research occurrence already has a consideration."
                )
            snapshot = agent.capture_research_snapshot(item_type, row)
            timestamp = now_stamp()
            consideration_id = agent.research_consideration_id(record_id)
            consideration = {
                "id": consideration_id,
                "item_type": item_type,
                "research_record_id": record_id,
                "source_key": snapshot["source_key"],
                "status": "open",
                "snapshot": snapshot,
                "source_profile_revision": profile["profile_revision"],
                "caregiver_action_id": None,
                "events": [],
                "created_at": timestamp,
                "updated_at": timestamp,
                "closed_at": None,
                "history": [],
            }
            profile.setdefault("research_considerations", []).append(consideration)
            event = agent.append_history(
                consideration,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=None,
                changes={"status": {"before": None, "after": "open"}},
            )
            result = _save_research_mutation(profile, event, consideration_id)
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError, KeyError) as exc:
        return _research_error(exc)


def _research_existing_mutation(
    consideration_id: str,
    *,
    endpoint: str,
    operation: str,
    allowed_fields: set[str],
    mutate,
):
    data = _workflow_request()
    _require_research_fields(
        data,
        _RESEARCH_META_FIELDS | {"expected_consideration_token"} | allowed_fields,
    )
    mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
    target = f"research_consideration:{consideration_id}"
    with agent.serialized_mutation():
        profile = agent.load_profile()
        replay = _idempotent_result(
            profile,
            mutation_id,
            data,
            endpoint=endpoint,
            operation=operation,
            target=target,
        )
        if replay is not None:
            return replay
        projection = agent.project_research_workspace(profile)
        _require_research_authority(profile, projection, data)
        consideration = _research_consideration(
            profile,
            consideration_id,
            data.get("expected_consideration_token"),
        )
        before_token = agent.semantic_token(consideration)
        changes = mutate(profile, consideration, data, mutation_id)
        consideration["updated_at"] = now_stamp()
        event = agent.append_history(
            consideration,
            endpoint=endpoint,
            operation=operation,
            target=target,
            mutation_id=mutation_id,
            payload=data,
            before_token=before_token,
            changes=changes,
        )
        return _save_research_mutation(profile, event, consideration_id)


@app.route("/api/research-considerations/<consideration_id>/events", methods=["POST"])
def api_add_research_event(consideration_id):
    def mutate(_profile, consideration, data, _mutation_id):
        event = agent.build_research_event(consideration["item_type"], data)
        consideration.setdefault("events", []).append(event)
        return {"event_id": event["id"], "event_type": event["event_type"]}

    try:
        result = _research_existing_mutation(
            consideration_id,
            endpoint="POST /api/research-considerations/<id>/events",
            operation="event_recorded",
            allowed_fields={"event_type", "note", "who", "context", "occurred_on"},
            mutate=mutate,
        )
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError, KeyError) as exc:
        return _research_error(exc)


def _set_research_status(consideration_id: str, status: str):
    operation = "closed" if status == "closed" else "resumed"

    def mutate(_profile, consideration, _data, _mutation_id):
        current = consideration.get("status")
        expected = "open" if status == "closed" else "closed"
        if current != expected:
            raise agent.FollowThroughConflict(
                "The research consideration is not eligible for this lifecycle change."
            )
        timestamp = now_stamp()
        consideration["status"] = status
        consideration["closed_at"] = timestamp if status == "closed" else None
        return {"status": {"before": current, "after": status}}

    return _research_existing_mutation(
        consideration_id,
        endpoint=f"POST /api/research-considerations/<id>/{'close' if status == 'closed' else 'resume'}",
        operation=operation,
        allowed_fields=set(),
        mutate=mutate,
    )


@app.route("/api/research-considerations/<consideration_id>/close", methods=["POST"])
def api_close_research_consideration(consideration_id):
    try:
        return jsonify(_set_research_status(consideration_id, "closed"))
    except (agent.FollowThroughError, ValueError, TypeError, KeyError) as exc:
        return _research_error(exc)


@app.route("/api/research-considerations/<consideration_id>/resume", methods=["POST"])
def api_resume_research_consideration(consideration_id):
    try:
        return jsonify(_set_research_status(consideration_id, "open"))
    except (agent.FollowThroughError, ValueError, TypeError, KeyError) as exc:
        return _research_error(exc)


@app.route("/api/research-considerations/<consideration_id>/follow-up", methods=["PATCH"])
def api_patch_research_follow_up(consideration_id):
    def mutate(profile, consideration, data, mutation_id):
        has_action_id = "caregiver_action_id" in data
        has_inline = "follow_up" in data
        if has_action_id == has_inline:
            raise ValueError(
                "Use exactly one follow-up operation: caregiver_action_id or follow_up."
            )
        if has_inline and data.get("expected_action_token") is not None:
            raise ValueError("expected_action_token cannot be used with follow_up.")
        current_id = consideration.get("caregiver_action_id")
        new_id = data.get("caregiver_action_id") if has_action_id else None
        if has_inline:
            if current_id is not None:
                raise agent.FollowThroughConflict(
                    "Unlink the current caregiver follow-up before creating another."
                )
            follow_up = data.get("follow_up")
            if not isinstance(follow_up, dict) or set(follow_up) - {
                "text",
                "owner",
                "due_date",
            }:
                raise ValueError("follow_up must contain only text, owner, and due_date.")
            validated = {
                "text": agent.validate_follow_up_text(follow_up.get("text")),
                "owner": agent.validate_owner(follow_up.get("owner")),
                "due_date": agent.validate_date(follow_up.get("due_date"), "due_date"),
            }
            internal_mutation_id = (
                "research-action:" + hashlib.sha256(mutation_id.encode("ascii")).hexdigest()[:32]
            )
            action = _new_action(
                profile,
                validated,
                mutation_id=mutation_id,
                research_consideration=consideration,
                history_mutation_id=internal_mutation_id,
                history_endpoint="PATCH /api/research-considerations/<id>/follow-up",
            )
            new_id = action["id"]
        elif new_id is None:
            if current_id is None:
                raise agent.FollowThroughConflict(
                    "This research consideration has no caregiver follow-up to unlink."
                )
            action = _action_record(profile, current_id)
            expected = data.get("expected_action_token")
            if not isinstance(expected, str) or not hmac.compare_digest(
                expected, agent.semantic_token(action)
            ):
                raise agent.FollowThroughConflict(
                    "The caregiver follow-up changed. Refresh and try again."
                )
        else:
            if current_id is not None:
                raise agent.FollowThroughConflict(
                    "Unlink the current caregiver follow-up before linking another."
                )
            action = _action_record(profile, new_id)
            if action.get("status") not in {"open", "in_progress"}:
                raise agent.FollowThroughConflict("The caregiver follow-up is no longer eligible.")
            expected = data.get("expected_action_token")
            if not isinstance(expected, str) or not hmac.compare_digest(
                expected, agent.semantic_token(action)
            ):
                raise agent.FollowThroughConflict(
                    "The caregiver follow-up changed. Refresh and try again."
                )
            if agent.action_owner_refs(profile, new_id):
                raise agent.FollowThroughConflict(
                    "The caregiver follow-up is already owned by another workflow."
                )
        consideration["caregiver_action_id"] = new_id
        return {"caregiver_action_id": {"before": current_id, "after": new_id}}

    try:
        result = _research_existing_mutation(
            consideration_id,
            endpoint="PATCH /api/research-considerations/<id>/follow-up",
            operation="follow_up_changed",
            allowed_fields={"caregiver_action_id", "expected_action_token", "follow_up"},
            mutate=mutate,
        )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError, KeyError) as exc:
        return _research_error(exc)


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


# ── symptom episodes ─────────────────────────────────────────────────────────
@app.route("/api/symptom-episodes", methods=["POST"])
def api_create_symptom_episode():
    """Create one caregiver-entered episode, optionally with one atomic follow-up."""
    try:
        data = _workflow_request()
    except agent.FollowThroughError as exc:
        return _workflow_error(exc)
    endpoint = "POST /api/symptom-episodes"
    operation = "created"
    target = "symptom_episode:create"
    try:
        _require_symptom_fields(
            data,
            _SYMPTOM_MUTATION_META_FIELDS
            | _SYMPTOM_CONTENT_FIELDS
            | {"caregiver_action_id", "expected_action_token", "follow_up"},
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        existing_action_requested = data.get("caregiver_action_id") is not None
        inline_action_requested = data.get("follow_up") is not None
        if existing_action_requested and inline_action_requested:
            raise ValueError("caregiver_action_id and follow_up are mutually exclusive.")
        if data.get("expected_action_token") is not None and not existing_action_requested:
            raise ValueError("expected_action_token requires caregiver_action_id.")
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id=mutation_id,
                data=data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _symptom_projection(profile)
            _require_symptom_revisions(profile, data)
            _require_projection_token(projection, data)
            content = _episode_content(data)
            linked_action = None
            inline_follow_up = None
            if existing_action_requested:
                linked_action = _validate_episode_action_link(
                    profile,
                    action_id=data.get("caregiver_action_id"),
                    expected_token=data.get("expected_action_token"),
                    episode_id=None,
                )
            elif inline_action_requested:
                inline_follow_up = _validate_inline_episode_follow_up(data.get("follow_up"))
            timestamp = now_stamp()
            episode_id = agent.new_symptom_episode_id()
            episode = {
                "id": episode_id,
                "status": "current",
                **content,
                "resolved_date": None,
                "resolved_date_precision": "unknown",
                "resolved_date_kind": "unknown",
                "provenance": agent.symptom_episode_provenance(),
                "created_at": timestamp,
                "updated_at": timestamp,
                "resolved_at": None,
                "caregiver_action_id": (
                    linked_action.get("id") if linked_action is not None else None
                ),
                "history": [],
            }
            if inline_follow_up is not None:
                internal_mutation_id = (
                    "symact:" + hashlib.sha256(mutation_id.encode("ascii")).hexdigest()[:32]
                )
                linked_action = _new_action(
                    profile,
                    inline_follow_up,
                    mutation_id=mutation_id,
                    history_mutation_id=internal_mutation_id,
                    history_endpoint=endpoint,
                )
                episode["caregiver_action_id"] = linked_action["id"]
            profile.setdefault("symptom_episodes", []).append(episode)
            event = agent.append_history(
                episode,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=None,
                changes={
                    "status": {"before": None, "after": "current"},
                    "caregiver_action_id": {
                        "before": None,
                        "after": episode.get("caregiver_action_id"),
                    },
                },
            )
            result = _save_workflow_mutation(
                profile,
                event=event,
                clinical_change=True,
                reason="A caregiver-entered symptom episode changed.",
                response_factory=lambda: _symptom_mutation_response(profile, episode_id),
            )
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _symptom_mutation_error(exc)


@app.route("/api/symptom-episodes/<episode_id>", methods=["PATCH"])
def api_edit_symptom_episode(episode_id):
    """Correct explicit episode content without changing lifecycle."""
    try:
        data = _workflow_request()
    except agent.FollowThroughError as exc:
        return _workflow_error(exc)
    endpoint = "PATCH /api/symptom-episodes/<episode_id>"
    operation = "edited"
    target = f"symptom_episode:{episode_id}"
    allowed = (
        _SYMPTOM_MUTATION_META_FIELDS
        | _SYMPTOM_CONTENT_FIELDS
        | {"expected_episode_token", "resolved_date"}
    )
    try:
        _require_symptom_fields(data, allowed)
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        changed_fields = set(data) & (_SYMPTOM_CONTENT_FIELDS | {"resolved_date"})
        if not changed_fields:
            raise ValueError("At least one symptom episode field is required.")
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id=mutation_id,
                data=data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _symptom_projection(profile)
            _require_symptom_revisions(profile, data)
            _require_projection_token(projection, data)
            _episode_projection_row(projection, episode_id, data.get("expected_episode_token"))
            episode = _episode_record(profile, episode_id)
            if "resolved_date" in data and episode.get("status") != "resolved":
                raise ValueError("resolved_date can only correct a resolved episode.")
            updated = _episode_content(data, existing=episode)
            if "resolved_date" in data:
                resolved_date, resolved_precision = _episode_date(
                    data.get("resolved_date"), "resolved_date"
                )
                updated["resolved_date"] = resolved_date
                updated["resolved_date_precision"] = resolved_precision
                updated["resolved_date_kind"] = "caregiver_entered" if resolved_date else "unknown"
            mutable_fields = _SYMPTOM_CONTENT_FIELDS | {
                "onset_date_precision",
                "onset_date_kind",
                "resolved_date",
                "resolved_date_precision",
                "resolved_date_kind",
            }
            changes = {
                field: {"before": episode.get(field), "after": updated.get(field)}
                for field in mutable_fields
                if episode.get(field) != updated.get(field)
            }
            if not changes:
                raise ValueError("The symptom episode already has those values.")
            before_token = agent.semantic_token(episode)
            for field in changes:
                episode[field] = copy.deepcopy(updated.get(field))
            episode["updated_at"] = now_stamp()
            event = agent.append_history(
                episode,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes=changes,
            )
            result = _save_workflow_mutation(
                profile,
                event=event,
                clinical_change=True,
                reason="A caregiver-entered symptom episode changed.",
                response_factory=lambda: _symptom_mutation_response(profile, episode_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _symptom_mutation_error(exc)


@app.route("/api/symptom-episodes/<episode_id>/resolve", methods=["POST"])
def api_resolve_symptom_episode(episode_id):
    """Mechanically resolve one current episode without changing its follow-up."""
    try:
        data = _workflow_request()
    except agent.FollowThroughError as exc:
        return _workflow_error(exc)
    endpoint = "POST /api/symptom-episodes/<episode_id>/resolve"
    operation = "resolved"
    target = f"symptom_episode:{episode_id}"
    try:
        _require_symptom_fields(
            data,
            _SYMPTOM_MUTATION_META_FIELDS | {"expected_episode_token", "resolved_date"},
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id=mutation_id,
                data=data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _symptom_projection(profile)
            _require_symptom_revisions(profile, data)
            _require_projection_token(projection, data)
            _episode_projection_row(projection, episode_id, data.get("expected_episode_token"))
            episode = _episode_record(profile, episode_id)
            if episode.get("status") != "current":
                raise _SymptomConflictError("Only a current symptom episode can be resolved.")
            resolved_date, resolved_precision = _episode_date(
                data.get("resolved_date"), "resolved_date"
            )
            before_token = agent.semantic_token(episode)
            timestamp = now_stamp()
            episode["status"] = "resolved"
            episode["resolved_date"] = resolved_date
            episode["resolved_date_precision"] = resolved_precision
            episode["resolved_date_kind"] = "caregiver_entered" if resolved_date else "unknown"
            episode["resolved_at"] = timestamp
            episode["updated_at"] = timestamp
            event = agent.append_history(
                episode,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "status": {"before": "current", "after": "resolved"},
                    "resolved_date": {"before": None, "after": resolved_date},
                },
            )
            result = _save_workflow_mutation(
                profile,
                event=event,
                clinical_change=True,
                reason="A caregiver-entered symptom episode changed.",
                response_factory=lambda: _symptom_mutation_response(profile, episode_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _symptom_mutation_error(exc)


@app.route("/api/symptom-episodes/<episode_id>/follow-up", methods=["PATCH"])
def api_link_symptom_episode_follow_up(episode_id):
    """Atomically create-link, link, or unlink one durable caregiver follow-up."""
    try:
        data = _workflow_request()
    except agent.FollowThroughError as exc:
        return _workflow_error(exc)
    endpoint = "PATCH /api/symptom-episodes/<episode_id>/follow-up"
    target = f"symptom_episode:{episode_id}:follow_up"
    try:
        _require_symptom_fields(
            data,
            _SYMPTOM_MUTATION_META_FIELDS
            | {
                "expected_episode_token",
                "caregiver_action_id",
                "expected_action_token",
                "follow_up",
            },
        )
        has_action_id = "caregiver_action_id" in data
        has_inline_follow_up = "follow_up" in data
        if has_action_id == has_inline_follow_up:
            raise ValueError(
                "Use exactly one follow-up operation: caregiver_action_id or follow_up."
            )
        if has_inline_follow_up and "expected_action_token" in data:
            raise ValueError("expected_action_token cannot be used with follow_up.")
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        if has_inline_follow_up:
            operation = "follow_up_created_and_linked"
            target = f"symptom_episode:{episode_id}"
        else:
            operation = (
                "follow_up_unlinked"
                if data.get("caregiver_action_id") is None
                else "follow_up_linked"
            )
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id=mutation_id,
                data=data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _symptom_projection(profile)
            _require_symptom_revisions(profile, data)
            _require_projection_token(projection, data)
            _episode_projection_row(projection, episode_id, data.get("expected_episode_token"))
            episode = _episode_record(profile, episode_id)
            current_action_id = episode.get("caregiver_action_id")
            new_action_id = data.get("caregiver_action_id") if has_action_id else None
            inline_follow_up = None
            if has_inline_follow_up:
                if current_action_id is not None:
                    raise _SymptomConflictError(
                        "Unlink the current caregiver follow-up before creating another."
                    )
                inline_follow_up = _validate_inline_episode_follow_up(data.get("follow_up"))
                if len(profile.get("caregiver_actions", [])) >= agent.MAX_SYMPTOM_ACTIONS:
                    raise agent.SymptomProjectionError(
                        "symptom_projection_too_large",
                        "Symptom data exceeds the supported projection limits.",
                    )
            elif new_action_id is None:
                if not isinstance(current_action_id, str) or not current_action_id:
                    raise _SymptomConflictError(
                        "The symptom episode has no linked caregiver follow-up."
                    )
                action = _action_record(profile, current_action_id)
                expected_action_token = data.get("expected_action_token")
                if not isinstance(expected_action_token, str) or not expected_action_token:
                    raise ValueError("expected_action_token is required.")
                if not hmac.compare_digest(expected_action_token, agent.semantic_token(action)):
                    raise _SymptomConflictError(
                        "The caregiver follow-up changed. Refresh and try again."
                    )
            else:
                if current_action_id is not None:
                    raise _SymptomConflictError(
                        "Unlink the current caregiver follow-up before linking another."
                    )
                _validate_episode_action_link(
                    profile,
                    action_id=new_action_id,
                    expected_token=data.get("expected_action_token"),
                    episode_id=episode_id,
                )
            if inline_follow_up is not None:
                internal_mutation_id = (
                    "symact:" + hashlib.sha256(mutation_id.encode("ascii")).hexdigest()[:32]
                )
                linked_action = _new_action(
                    profile,
                    inline_follow_up,
                    mutation_id=mutation_id,
                    history_mutation_id=internal_mutation_id,
                    history_endpoint=endpoint,
                )
                new_action_id = linked_action["id"]
            before_token = agent.semantic_token(episode)
            episode["caregiver_action_id"] = new_action_id
            episode["updated_at"] = now_stamp()
            event = agent.append_history(
                episode,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "caregiver_action_id": {
                        "before": current_action_id,
                        "after": new_action_id,
                    }
                },
            )
            result = _save_workflow_mutation(
                profile,
                event=event,
                clinical_change=False,
                reason="A symptom episode follow-up link changed.",
                response_factory=lambda: _symptom_mutation_response(profile, episode_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _symptom_mutation_error(exc)


# ── treatment reconciliation ─────────────────────────────────────────────────
@app.route("/api/treatment-reconciliation/courses", methods=["POST"])
def api_create_treatment_course():
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS
            | _TREATMENT_COURSE_FIELDS
            | _TREATMENT_TERMINAL_FIELDS
            | {"status"},
            "Unsupported treatment course field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        status = data.get("status")
        if status not in agent.TREATMENT_COURSE_STATUSES:
            raise ValueError("status must be current, past, or planned.")
        endpoint = "POST /api/treatment-reconciliation/courses"
        operation = "created"
        target = "treatment_course:create"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            terminal_qualifier, terminal_detail = agent.validate_treatment_terminal_authority(
                status,
                data.get("terminal_qualifier"),
                data.get("terminal_detail"),
            )
            timestamp = now_stamp()
            course = {
                "id": agent.new_treatment_course_id(),
                "status": status,
                **_course_content(data, projection),
                "terminal_qualifier": terminal_qualifier,
                "terminal_detail": terminal_detail,
                "previous_course_id": None,
                "provenance": agent.treatment_course_provenance(),
                "created_at": timestamp,
                "updated_at": timestamp,
                "history": [],
            }
            profile.setdefault("treatment_courses", []).append(course)
            event = agent.append_history(
                course,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=None,
                changes={
                    "status": {"before": None, "after": status},
                    "terminal_qualifier": {
                        "before": None,
                        "after": terminal_qualifier,
                    },
                    "terminal_detail": {
                        "before": None,
                        "after": terminal_detail,
                    },
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-maintained treatment course changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, course_id=course["id"]
                ),
            )
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route("/api/treatment-reconciliation/courses/<course_id>", methods=["PATCH"])
def api_edit_treatment_course(course_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS | _TREATMENT_COURSE_FIELDS | {"expected_course_token"},
            "Unsupported treatment course field.",
        )
        changed_fields = set(data) & _TREATMENT_COURSE_FIELDS
        if not changed_fields:
            raise ValueError("At least one treatment course field is required.")
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        endpoint = "PATCH /api/treatment-reconciliation/courses/<course_id>"
        operation = "edited"
        target = f"treatment_course:{course_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            _treatment_row(projection, "courses", course_id, data.get("expected_course_token"))
            course = _course_record(profile, course_id)
            updated = _course_content(data, projection, existing=course)
            changes = {
                field: {"before": course.get(field), "after": updated.get(field)}
                for field in (
                    _TREATMENT_COURSE_FIELDS
                    | {f"{date}_precision" for date in _TREATMENT_COURSE_DATE_FIELDS}
                    | {f"{date}_kind" for date in _TREATMENT_COURSE_DATE_FIELDS}
                )
                if course.get(field) != updated.get(field)
            }
            if not changes:
                raise ValueError("The treatment course already has those values.")
            before_token = agent.semantic_token(course)
            for field in changes:
                course[field] = copy.deepcopy(updated.get(field))
            course["updated_at"] = now_stamp()
            event = agent.append_history(
                course,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes=changes,
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-maintained treatment course changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(profile, course_id=course_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/courses/<course_id>/transition",
    methods=["POST"],
)
def api_transition_treatment_course(course_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS
            | _TREATMENT_TERMINAL_FIELDS
            | {"expected_course_token", "status"},
            "Unsupported treatment transition field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        new_status = data.get("status")
        endpoint = "POST /api/treatment-reconciliation/courses/<course_id>/transition"
        operation = "transitioned"
        target = f"treatment_course:{course_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            _treatment_row(projection, "courses", course_id, data.get("expected_course_token"))
            course = _course_record(profile, course_id)
            allowed = {
                "planned": {"current", "past"},
                "current": {"past"},
                "past": set(),
            }
            if new_status not in allowed.get(course.get("status"), set()):
                raise _TreatmentConflictError("That treatment course transition is not allowed.")
            before_status = course["status"]
            terminal_qualifier, terminal_detail = agent.validate_treatment_terminal_authority(
                new_status,
                data.get("terminal_qualifier"),
                data.get("terminal_detail"),
                prior_status=before_status,
            )
            before_token = agent.semantic_token(course)
            course["status"] = new_status
            course["terminal_qualifier"] = terminal_qualifier
            course["terminal_detail"] = terminal_detail
            course["updated_at"] = now_stamp()
            event = agent.append_history(
                course,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "status": {"before": before_status, "after": new_status},
                    "terminal_qualifier": {
                        "before": None,
                        "after": terminal_qualifier,
                    },
                    "terminal_detail": {
                        "before": None,
                        "after": terminal_detail,
                    },
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-maintained treatment course changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(profile, course_id=course_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/courses/<course_id>/restart",
    methods=["POST"],
)
def api_restart_treatment_course(course_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS | _TREATMENT_COURSE_FIELDS | {"expected_course_token", "status"},
            "Unsupported treatment restart field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        status = data.get("status")
        if status not in {"current", "planned"}:
            raise ValueError("A restarted course must be current or planned.")
        endpoint = "POST /api/treatment-reconciliation/courses/<course_id>/restart"
        operation = "restarted"
        target = f"treatment_course:{course_id}:restart"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            prior_public = _treatment_row(
                projection, "courses", course_id, data.get("expected_course_token")
            )
            if not prior_public["lifecycle"]["restart"]["eligible"]:
                raise _TreatmentConflictError("That treatment course is not eligible to restart.")
            timestamp = now_stamp()
            course = {
                "id": agent.new_treatment_course_id(),
                "status": status,
                **_course_content(data, projection),
                "terminal_qualifier": None,
                "terminal_detail": None,
                "previous_course_id": course_id,
                "provenance": agent.treatment_course_provenance(),
                "created_at": timestamp,
                "updated_at": timestamp,
                "history": [],
            }
            profile.setdefault("treatment_courses", []).append(course)
            event = agent.append_history(
                course,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=prior_public["token"],
                changes={
                    "status": {"before": None, "after": status},
                    "previous_course_id": {"before": None, "after": course_id},
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-maintained treatment course changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, course_id=course["id"]
                ),
            )
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/legacy-rows/<row_id>/disposition",
    methods=["POST"],
)
def api_set_treatment_row_disposition(row_id):
    """Set the caregiver's workspace visibility for one raw treatment statement.

    Workflow authority only. Nothing is deleted, no stored wording changes, no
    clinical meaning is assigned, and the row keeps reaching every model prompt
    unchanged — so this advances ``workflow_revision`` alone and never
    invalidates generated clinical context.
    """
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS | {"hidden", "expected_disposition_token"},
            "Unsupported treatment row disposition field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        hidden = data.get("hidden")
        if not isinstance(hidden, bool):
            raise ValueError("hidden must be true or false.")
        expected_token = data.get("expected_disposition_token")
        if not isinstance(expected_token, str) or not expected_token:
            raise ValueError("expected_disposition_token is required.")
        endpoint = "POST /api/treatment-reconciliation/legacy-rows/<row_id>/disposition"
        operation = "hidden" if hidden else "restored"
        target = f"treatment_row_disposition:{row_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            row = next(
                (item for item in projection["legacy_treatments"] if item["id"] == row_id),
                None,
            )
            if row is None:
                raise _TreatmentNotFoundError("Recorded treatment entry not found.")
            current = next(
                (
                    item
                    for item in projection["legacy_treatment_dispositions"]
                    if item["row_id"] == row_id
                ),
                None,
            )
            if current is None:
                raise _TreatmentNotFoundError("Recorded treatment entry not found.")
            if not hmac.compare_digest(expected_token, current["token"]):
                raise _TreatmentConflictError(
                    "That recorded treatment entry changed. Refresh and try again."
                )
            if bool(current["hidden"]) == hidden:
                raise ValueError("That recorded treatment entry already has this visibility.")
            source_entry_id = _raw_row_source_entry_id(profile, row)
            timestamp = now_stamp()
            records = profile.setdefault("treatment_row_dispositions", [])
            record = next(
                (
                    item
                    for item in records
                    if isinstance(item, dict) and item.get("source_entry_id") == source_entry_id
                ),
                None,
            )
            before_token = current["token"]
            if record is None:
                record = {
                    "id": agent.new_treatment_row_disposition_id(),
                    "source_entry_id": source_entry_id,
                    "hidden": hidden,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "history": [],
                }
                records.append(record)
            else:
                record["hidden"] = hidden
                record["updated_at"] = timestamp
            event = agent.append_history(
                record,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={"hidden": {"before": not hidden, "after": hidden}},
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=False,
                reason="A caregiver treatment workspace preference changed.",
                event=event,
                response_factory=lambda: _treatment_row_disposition_response(profile, row_id),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route("/api/treatment-reconciliation/discrepancies", methods=["POST"])
def api_create_treatment_discrepancy():
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS
            | {
                "category",
                "comparison_text",
                "source_fact_ref",
                "expected_source_fact_token",
                "comparison_source_fact_ref",
                "expected_comparison_source_fact_token",
                "course_id",
                "expected_course_token",
                "recurs_from_id",
                "expected_recurs_from_token",
            },
            "Unsupported treatment discrepancy field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        category = data.get("category")
        if category not in agent.TREATMENT_DISCREPANCY_CATEGORIES:
            raise ValueError("Invalid treatment discrepancy category.")
        comparison_text = _exact_treatment_text(
            data.get("comparison_text"), "comparison_text", required=True
        )
        endpoint = "POST /api/treatment-reconciliation/discrepancies"
        operation = "created"
        target = "treatment_discrepancy:create"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            recurs_from_id = data.get("recurs_from_id")
            if recurs_from_id is not None:
                citation_fields = {
                    "source_fact_ref",
                    "expected_source_fact_token",
                    "comparison_source_fact_ref",
                    "expected_comparison_source_fact_token",
                    "course_id",
                    "expected_course_token",
                }
                if set(data) & citation_fields:
                    raise ValueError(
                        "Recurring discrepancies preserve cited authorities server-side."
                    )
                prior = _treatment_row(
                    projection,
                    "discrepancies",
                    recurs_from_id,
                    data.get("expected_recurs_from_token"),
                )
                if prior.get("status") != "resolved":
                    raise _TreatmentConflictError(
                        "A recurring discrepancy must link to a resolved discrepancy."
                    )
                _require_complete_discrepancy_citations(prior)
                prior_record = _discrepancy_record(profile, recurs_from_id)
                citation_kind = prior["citation_kind"]
                source_fact_ref = prior_record["source_fact_ref"]
                source_fact_snapshot = copy.deepcopy(prior_record["source_fact_snapshot"])
                comparison_source_fact_ref = prior_record.get("comparison_source_fact_ref")
                comparison_source_fact_snapshot = copy.deepcopy(
                    prior_record.get("comparison_source_fact_snapshot")
                )
                course_id = prior_record.get("course_id")
                course_snapshot = copy.deepcopy(prior_record.get("course_snapshot"))
            elif data.get("expected_recurs_from_token") is not None:
                raise ValueError("expected_recurs_from_token requires recurs_from_id.")
            else:
                source_fact = _treatment_source_fact(
                    projection,
                    data.get("source_fact_ref"),
                    data.get("expected_source_fact_token"),
                )
                source_partner_present = (
                    "comparison_source_fact_ref" in data
                    or "expected_comparison_source_fact_token" in data
                )
                course_partner_present = "course_id" in data or "expected_course_token" in data
                if source_partner_present == course_partner_present:
                    raise ValueError(
                        "Use exactly one second citation: comparison source fact or course."
                    )
                source_fact_ref = source_fact["ref"]
                source_fact_snapshot = copy.deepcopy(source_fact)
                comparison_source_fact_ref = None
                comparison_source_fact_snapshot = None
                course_id = None
                course_snapshot = None
                if source_partner_present:
                    comparison_source_fact = _treatment_source_fact(
                        projection,
                        data.get("comparison_source_fact_ref"),
                        data.get("expected_comparison_source_fact_token"),
                    )
                    if comparison_source_fact["ref"] == source_fact_ref:
                        raise ValueError("Treatment source fact citations must be distinct.")
                    citation_kind = "source_vs_source"
                    comparison_source_fact_ref = comparison_source_fact["ref"]
                    comparison_source_fact_snapshot = copy.deepcopy(comparison_source_fact)
                else:
                    course_id = data.get("course_id")
                    if not isinstance(course_id, str) or not course_id:
                        raise ValueError("course_id must be a treatment course ID.")
                    course_snapshot = _treatment_row(
                        projection,
                        "courses",
                        course_id,
                        data.get("expected_course_token"),
                    )
                    citation_kind = "source_vs_course"
            timestamp = now_stamp()
            discrepancy = {
                "id": agent.new_treatment_discrepancy_id(),
                "status": "open",
                "category": category,
                "comparison_text": comparison_text,
                "citation_kind": citation_kind,
                "course_id": course_id,
                "source_fact_ref": source_fact_ref,
                "source_fact_snapshot": source_fact_snapshot,
                "comparison_source_fact_ref": comparison_source_fact_ref,
                "comparison_source_fact_snapshot": comparison_source_fact_snapshot,
                "course_snapshot": copy.deepcopy(course_snapshot),
                "recurs_from_id": recurs_from_id,
                "confirmations": [],
                "caregiver_action_id": None,
                "provenance": agent.treatment_course_provenance(),
                "created_at": timestamp,
                "updated_at": timestamp,
                "resolved_at": None,
                "history": [],
            }
            profile.setdefault("treatment_discrepancies", []).append(discrepancy)
            event = agent.append_history(
                discrepancy,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=None,
                changes={"status": {"before": None, "after": "open"}},
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-entered treatment discrepancy changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, discrepancy_id=discrepancy["id"]
                ),
            )
        return jsonify(result), 201
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/discrepancies/<discrepancy_id>/resolve",
    methods=["POST"],
)
def api_resolve_treatment_discrepancy(discrepancy_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS
            | {
                "expected_discrepancy_token",
                "outcome",
                "note",
                "clinician_text",
                "context_text",
                "date",
                "course_patch",
                "expected_course_token",
            },
            "Unsupported treatment discrepancy resolution field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        outcome = data.get("outcome")
        if outcome not in agent.TREATMENT_CONFIRMATION_OUTCOMES:
            raise ValueError("Invalid treatment confirmation outcome.")
        note = _exact_treatment_text(data.get("note"), "note", required=True)
        clinician_text = _exact_treatment_text(data.get("clinician_text"), "clinician_text")
        context_text = _exact_treatment_text(data.get("context_text"), "context_text")
        date, date_precision, date_kind = _treatment_date(data.get("date"), "date")
        endpoint = "POST /api/treatment-reconciliation/discrepancies/<id>/resolve"
        operation = "resolved"
        target = f"treatment_discrepancy:{discrepancy_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            public_discrepancy = _treatment_row(
                projection,
                "discrepancies",
                discrepancy_id,
                data.get("expected_discrepancy_token"),
            )
            _require_complete_discrepancy_citations(public_discrepancy)
            discrepancy = _discrepancy_record(profile, discrepancy_id)
            if discrepancy.get("status") != "open":
                raise _TreatmentConflictError("Only an open discrepancy can be resolved.")
            course_patch = data.get("course_patch")
            if outcome == "caregiver_record_corrected":
                if not isinstance(course_patch, dict) or not course_patch:
                    raise ValueError(
                        "course_patch is required when correcting the caregiver record."
                    )
                if set(course_patch) - _TREATMENT_COURSE_FIELDS:
                    raise ValueError("Unsupported treatment course correction field.")
                course_id = discrepancy.get("course_id")
                if not isinstance(course_id, str):
                    raise ValueError(
                        "A linked treatment course is required for caregiver_record_corrected."
                    )
                public_discrepancy = _treatment_row(
                    projection,
                    "courses",
                    course_id,
                    data.get("expected_course_token"),
                )
                course = _course_record(profile, course_id)
                updated = _course_content(course_patch, projection, existing=course)
                course_changes = {
                    field: {"before": course.get(field), "after": updated.get(field)}
                    for field in (
                        _TREATMENT_COURSE_FIELDS
                        | {f"{field}_precision" for field in _TREATMENT_COURSE_DATE_FIELDS}
                        | {f"{field}_kind" for field in _TREATMENT_COURSE_DATE_FIELDS}
                    )
                    if course.get(field) != updated.get(field)
                }
                if not course_changes:
                    raise ValueError("course_patch must change the caregiver record.")
                course_before = agent.semantic_token(course)
                for field in course_changes:
                    course[field] = copy.deepcopy(updated.get(field))
                course["updated_at"] = now_stamp()
                agent.append_history(
                    course,
                    endpoint=endpoint + ":course",
                    operation="corrected_with_discrepancy",
                    target=f"treatment_course:{course_id}",
                    mutation_id=(
                        "txcourse:" + hashlib.sha256(mutation_id.encode("ascii")).hexdigest()[:32]
                    ),
                    payload=course_patch,
                    before_token=course_before,
                    changes=course_changes,
                )
            elif course_patch is not None or data.get("expected_course_token") is not None:
                raise ValueError(
                    "Only caregiver_record_corrected can include a course patch or course token."
                )
            timestamp = now_stamp()
            confirmation = {
                "outcome": outcome,
                "note": note,
                "clinician_text": clinician_text,
                "context_text": context_text,
                "date": date,
                "date_precision": date_precision,
                "date_kind": date_kind,
                "provenance": agent.treatment_confirmation_provenance(),
                "recorded_at": timestamp,
            }
            before_token = agent.semantic_token(discrepancy)
            discrepancy.setdefault("confirmations", []).append(confirmation)
            discrepancy["status"] = "resolved"
            discrepancy["resolved_at"] = timestamp
            discrepancy["updated_at"] = timestamp
            event = agent.append_history(
                discrepancy,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "status": {"before": "open", "after": "resolved"},
                    "confirmation": copy.deepcopy(confirmation),
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=True,
                reason="A caregiver-entered treatment discrepancy changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, discrepancy_id=discrepancy_id
                ),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/discrepancies/<discrepancy_id>/reopen",
    methods=["POST"],
)
def api_reopen_treatment_discrepancy(discrepancy_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS | {"expected_discrepancy_token"},
            "Unsupported treatment discrepancy reopen field.",
        )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        endpoint = "POST /api/treatment-reconciliation/discrepancies/<id>/reopen"
        operation = "reopened"
        target = f"treatment_discrepancy:{discrepancy_id}"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            public_discrepancy = _treatment_row(
                projection,
                "discrepancies",
                discrepancy_id,
                data.get("expected_discrepancy_token"),
            )
            _require_complete_discrepancy_citations(public_discrepancy)
            discrepancy = _discrepancy_record(profile, discrepancy_id)
            if discrepancy.get("status") != "resolved":
                raise _TreatmentConflictError("Only a resolved discrepancy can be reopened.")
            before_token = agent.semantic_token(discrepancy)
            prior_resolved_at = discrepancy.get("resolved_at")
            discrepancy["status"] = "open"
            discrepancy["resolved_at"] = None
            discrepancy["updated_at"] = now_stamp()
            event = agent.append_history(
                discrepancy,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "status": {"before": "resolved", "after": "open"},
                    "resolved_at": {"before": prior_resolved_at, "after": None},
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=False,
                reason="A treatment discrepancy workflow state changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, discrepancy_id=discrepancy_id
                ),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


@app.route(
    "/api/treatment-reconciliation/discrepancies/<discrepancy_id>/follow-up",
    methods=["PATCH"],
)
def api_link_treatment_discrepancy_follow_up(discrepancy_id):
    try:
        data = _workflow_request()
        _reject_unsupported_fields(
            data,
            _TREATMENT_META_FIELDS
            | {
                "expected_discrepancy_token",
                "caregiver_action_id",
                "expected_action_token",
                "follow_up",
            },
            "Unsupported treatment follow-up field.",
        )
        has_action_id = "caregiver_action_id" in data
        has_inline = "follow_up" in data
        if has_action_id == has_inline:
            raise ValueError(
                "Use exactly one follow-up operation: caregiver_action_id or follow_up."
            )
        mutation_id = agent.validate_mutation_id(data.get("mutation_id"))
        if has_inline:
            if "expected_action_token" in data:
                raise ValueError("expected_action_token cannot be used with follow_up.")
            operation = "follow_up_created_and_linked"
        else:
            operation = (
                "follow_up_unlinked"
                if data.get("caregiver_action_id") is None
                else "follow_up_linked"
            )
        endpoint = "PATCH /api/treatment-reconciliation/discrepancies/<id>/follow-up"
        target = f"treatment_discrepancy:{discrepancy_id}:follow_up"
        with agent.serialized_mutation():
            profile = agent.load_profile()
            replay = _idempotent_result(
                profile,
                mutation_id,
                data,
                endpoint=endpoint,
                operation=operation,
                target=target,
            )
            if replay is not None:
                return jsonify(replay)
            projection = _treatment_projection(profile)
            _require_treatment_revisions(profile, data)
            _require_treatment_projection_token(projection, data)
            _treatment_row(
                projection,
                "discrepancies",
                discrepancy_id,
                data.get("expected_discrepancy_token"),
            )
            discrepancy = _discrepancy_record(profile, discrepancy_id)
            current_action_id = discrepancy.get("caregiver_action_id")
            new_action_id = data.get("caregiver_action_id") if has_action_id else None
            inline = None
            if has_inline:
                if current_action_id is not None:
                    raise _TreatmentConflictError(
                        "Unlink the current caregiver follow-up before creating another."
                    )
                inline = _validate_inline_episode_follow_up(data.get("follow_up"))
                if len(profile.get("caregiver_actions", [])) >= agent.MAX_TREATMENT_ACTIONS:
                    raise agent.TreatmentProjectionError(
                        "treatment_projection_too_large",
                        "Treatment data exceeds the supported projection limits.",
                    )
            elif new_action_id is None:
                if current_action_id is None:
                    raise _TreatmentConflictError(
                        "The treatment discrepancy has no linked caregiver follow-up."
                    )
                action = _action_record(profile, current_action_id)
                expected = data.get("expected_action_token")
                if not isinstance(expected, str) or not expected:
                    raise ValueError("expected_action_token is required.")
                if not hmac.compare_digest(expected, agent.semantic_token(action)):
                    raise _TreatmentConflictError(
                        "The caregiver follow-up changed. Refresh and try again."
                    )
            else:
                if current_action_id is not None:
                    raise _TreatmentConflictError(
                        "Unlink the current caregiver follow-up before linking another."
                    )
                _treatment_action_link(
                    profile,
                    action_id=new_action_id,
                    expected_token=data.get("expected_action_token"),
                    discrepancy_id=discrepancy_id,
                )
            if inline is not None:
                linked_action = _new_action(
                    profile,
                    inline,
                    mutation_id=mutation_id,
                    history_mutation_id=(
                        "txaction:" + hashlib.sha256(mutation_id.encode("ascii")).hexdigest()[:32]
                    ),
                    history_endpoint=endpoint,
                )
                new_action_id = linked_action["id"]
            before_token = agent.semantic_token(discrepancy)
            discrepancy["caregiver_action_id"] = new_action_id
            discrepancy["updated_at"] = now_stamp()
            event = agent.append_history(
                discrepancy,
                endpoint=endpoint,
                operation=operation,
                target=target,
                mutation_id=mutation_id,
                payload=data,
                before_token=before_token,
                changes={
                    "caregiver_action_id": {
                        "before": current_action_id,
                        "after": new_action_id,
                    }
                },
            )
            result = _save_workflow_mutation(
                profile,
                clinical_change=False,
                reason="A treatment discrepancy follow-up link changed.",
                event=event,
                response_factory=lambda: _treatment_mutation_response(
                    profile, discrepancy_id=discrepancy_id
                ),
            )
        return jsonify(result)
    except (agent.FollowThroughError, ValueError, TypeError) as exc:
        return _treatment_mutation_error(exc)


# ── symptoms ─────────────────────────────────────────────────────────────────
@app.route("/api/symptoms")
def api_symptoms():
    profile = agent.load_profile()
    if len(profile.get("symptoms", [])) > 2_000:
        return jsonify({"error": "Symptom data exceeds the supported limits."}), 422
    symptoms = sorted(
        profile.get("symptoms", []),
        key=lambda x: x.get("date") or "",
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
    clinical_date = data.get("date") or today
    if derive_date_precision(clinical_date) == "unknown":
        return jsonify({"error": "Date must be YYYY, YYYY-MM, or YYYY-MM-DD"}), 400
    symptom = {
        "id": agent.new_workflow_id("sym"),
        "date": clinical_date,
        "date_precision": derive_date_precision(clinical_date),
        "date_kind": "clinical",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
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
                if derive_date_precision(data["date"]) == "unknown":
                    return jsonify({"error": "Date must be YYYY, YYYY-MM, or YYYY-MM-DD"}), 400
                s["date"] = data["date"]
                s["date_precision"] = derive_date_precision(data["date"])
                s["date_kind"] = "clinical"
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
