#!/usr/bin/env python3
"""
NET Care Agent — Web UI backend
Deployed on Azure App Service (swedencentral)
Data persisted to /home/data (Azure Files mount)
"""

import datetime
import io
import json
import os
import sys
import threading
import traceback
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
except Exception as e:
    print(f"ERROR: Could not import net_agent.py — {type(e).__name__}: {e}")
    sys.exit(1)

# Configure logging once Anthropic + dotenv are loaded.
from agent.io import atomic_write_text  # noqa: E402
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

app = Flask(__name__, static_folder="static", template_folder="static")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Multipart framing adds a small amount beyond the file itself. Keep the exact
# per-file limit below while allowing bounded protocol overhead.
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "100"))
MAX_EXTRACTED_TEXT_CHARS = int(os.environ.get("MAX_EXTRACTED_TEXT_CHARS", "1000000"))

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


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_jobs():
    global _jobs
    # Do NOT call _ensure_data_dir() here — this may run at import time
    # and the Azure Files mount may not be ready (causes 230s timeout).
    if JOBS_PATH.exists():
        try:
            _jobs = json.loads(JOBS_PATH.read_text())
        except Exception:
            _jobs = []


def _save_jobs():
    _ensure_data_dir()
    atomic_write_text(JOBS_PATH, json.dumps(_jobs, indent=2, default=str))


def _add_job(job: dict):
    with _jobs_lock:
        _jobs.insert(0, job)
        _jobs[:] = _jobs[:200]
        _save_jobs()


def _update_job(job_id: str, updates: dict):
    with _jobs_lock:
        for j in _jobs:
            if j["id"] == job_id:
                j.update(updates)
                break
        _save_jobs()


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
        message = (
            generated.get("summary", "Summary generation failed")
            if isinstance(generated, dict)
            else "Summary generation failed"
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
    text: str,
    raw_bytes: bytes | None = None,
    filename: str | None = None,
    media_type: str = "text/plain",
):
    # P6: serialize profile-mutating jobs so a concurrent feed+digest can't
    # silently lose one job's extracted data (last-writer-wins on the JSON file).
    try:
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

            reports_dir = DATA_DIR / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rpath = reports_dir / f"report_feed_{stamp}.txt"
            if summary_error:
                report += f"\n\n## Summary refresh warning\n{summary_error}"
            rpath.write_text(report, encoding="utf-8")

            _update_job(
                job_id,
                {
                    "status": "done",
                    "stage": "done_with_warnings" if summary_error else "done",
                    "report": report,
                    "report_file": str(rpath),
                    "summary_error": summary_error,
                    "finished_at": datetime.datetime.now().isoformat(),
                },
            )

    except Exception as e:
        _update_job(
            job_id,
            {
                "status": "error",
                "stage": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )


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
            except Exception as e:
                print(f"trial poll skipped: {e}")
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
            rpath.write_text(report, encoding="utf-8")

            _update_job(
                job_id,
                {
                    "status": "done",
                    "stage": "done_with_warnings" if summary_error else "done",
                    "report": report,
                    "report_file": str(rpath),
                    "summary_error": summary_error,
                    "finished_at": datetime.datetime.now().isoformat(),
                },
            )

    except Exception as e:
        _update_job(
            job_id,
            {
                "status": "error",
                "stage": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )


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
        rpath.write_text(report, encoding="utf-8")

        _update_job(
            job_id,
            {
                "status": "done",
                "stage": "done",
                "report": report,
                "report_file": str(rpath),
                "cost_total": result.get("cost_total"),
                "finished_at": datetime.datetime.now().isoformat(),
            },
        )

    except Exception as e:
        _update_job(
            job_id,
            {
                "status": "error",
                "stage": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )


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


@app.before_request
def _lazy_init():
    """Load jobs on the first real request — by then Azure Files is mounted."""
    global _initialized
    if not _initialized:
        _initialized = True
        _load_jobs()


def _source_auth_required(func):
    """Require Easy Auth identity headers in hosted deployments; allow local dev."""

    @wraps(func)
    def wrapped(*args, **kwargs):
        hosted_auth = os.environ.get("WEBSITE_AUTH_ENABLED", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if hosted_auth and not (
            request.headers.get("X-MS-CLIENT-PRINCIPAL")
            or request.headers.get("X-MS-CLIENT-PRINCIPAL-ID")
        ):
            return jsonify({"error": "Authentication required"}), 401
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


@app.route("/api/health")
def api_health():
    """Liveness/readiness probe — used by Azure App Service health check."""
    data_dir_writable = False
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".health_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        data_dir_writable = True
    except Exception:
        pass

    profile_loaded = False
    try:
        profile_loaded = agent.PROFILE_PATH.exists()
    except Exception:
        pass

    healthy = data_dir_writable
    return jsonify(
        {
            "status": "ok" if healthy else "degraded",
            "version": APP_VERSION,
            "profile_loaded": profile_loaded,
            "data_dir": str(DATA_DIR),
            "data_dir_writable": data_dir_writable,
        }
    ), (200 if healthy else 503)


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

    job = {
        "id": _new_id(),
        "type": "feed",
        "status": "queued",
        "stage": "queued",
        "created_at": datetime.datetime.now().isoformat(),
        "finished_at": None,
        "input_preview": text[:300],
        "document_type": None,
        "summary": None,
        "key_findings": [],
        "report": None,
        "error": None,
    }
    _add_job(job)
    threading.Thread(target=_run_feed_job, args=(job["id"], text), daemon=True).start()
    return jsonify({"job_id": job["id"]})


@app.route("/api/feed-file", methods=["POST"])
def api_feed_file():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400

    raw_bytes = f.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "File exceeds the 20 MB upload limit"}), 413
    try:
        if (f.filename or "").lower().endswith(".pdf"):
            import io

            import pdfplumber

            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                if len(pdf.pages) > MAX_PDF_PAGES:
                    return jsonify(
                        {"error": f"PDF exceeds the {MAX_PDF_PAGES}-page processing limit"}
                    ), 413
                chunks: list[str] = []
                total_chars = 0
                for page in pdf.pages:
                    chunk = page.extract_text() or ""
                    total_chars += len(chunk)
                    if total_chars > MAX_EXTRACTED_TEXT_CHARS:
                        return jsonify(
                            {
                                "error": (
                                    "Extracted text exceeds the "
                                    f"{MAX_EXTRACTED_TEXT_CHARS:,}-character processing limit"
                                )
                            }
                        ), 413
                    chunks.append(chunk)
                text = "\n\n".join(chunks)
        else:
            text = raw_bytes.decode("utf-8", errors="replace")
            if len(text) > MAX_EXTRACTED_TEXT_CHARS:
                return jsonify(
                    {
                        "error": (
                            "Text exceeds the "
                            f"{MAX_EXTRACTED_TEXT_CHARS:,}-character processing limit"
                        )
                    }
                ), 413
    except Exception as exc:
        return jsonify({"error": f"Could not read uploaded file: {exc}"}), 400

    if not text.strip():
        return jsonify({"error": "File appears to be empty or unreadable"}), 400

    job = {
        "id": _new_id(),
        "type": "feed",
        "status": "queued",
        "stage": "queued",
        "created_at": datetime.datetime.now().isoformat(),
        "finished_at": None,
        "input_preview": f"[File: {f.filename}] " + text[:260],
        "document_type": None,
        "summary": None,
        "key_findings": [],
        "report": None,
        "error": None,
    }
    _add_job(job)
    threading.Thread(
        target=_run_feed_job,
        args=(job["id"], text, raw_bytes, f.filename, f.mimetype or "application/octet-stream"),
        daemon=True,
    ).start()
    return jsonify({"job_id": job["id"]})


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
    job = {
        "id": _new_id(),
        "type": "digest",
        "status": "queued",
        "stage": "queued",
        "created_at": datetime.datetime.now().isoformat(),
        "finished_at": None,
        "input_preview": "Research digest — full literature + trial sweep",
        "document_type": "digest",
        "summary": None,
        "key_findings": [],
        "report": None,
        "error": None,
    }
    _add_job(job)
    threading.Thread(target=_run_digest_job, args=(job["id"],), daemon=True).start()
    return jsonify({"job_id": job["id"]})


@app.route("/api/deep-sweep", methods=["POST"])
def api_deep_sweep():
    """Enqueue an ensemble deep-sweep (multi-model exploratory research pass).

    Read-only: the job does not write findings back to the profile.
    """
    job = {
        "id": _new_id(),
        "type": "deep-sweep",
        "status": "queued",
        "stage": "queued",
        "created_at": datetime.datetime.now().isoformat(),
        "finished_at": None,
        "input_preview": "Ensemble deep-sweep — multi-model, unioned findings",
        "document_type": "deep-sweep",
        "summary": None,
        "key_findings": [],
        "report": None,
        "error": None,
    }
    _add_job(job)
    threading.Thread(target=_run_deepsweep_job, args=(job["id"],), daemon=True).start()
    return jsonify({"job_id": job["id"]})


@app.route("/api/jobs")
def api_jobs():
    with _jobs_lock:
        return jsonify(list(_jobs))


@app.route("/api/jobs/<job_id>")
def api_job(job_id):
    with _jobs_lock:
        for j in _jobs:
            if j["id"] == job_id:
                return jsonify(j)
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
@serialized_profile_mutation
def api_questions_generate():
    data = request.get_json(force=True) or {}
    appointment_type = data.get("appointment_type", "oncology follow-up")
    profile = agent.load_profile()
    new_questions = agent.generate_questions_for_profile(profile, appointment_type)
    # Preserve asked history and manual questions; refresh only current unanswered AI items.
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
    return jsonify(profile["appointment_questions"])


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
@serialized_profile_mutation
def api_summary_generate():
    """Generate executive summary and classify treatments on demand."""
    profile = agent.load_profile()
    classified_txs = agent.classify_treatments(profile)
    profile["treatments_classified"] = classified_txs
    summary_error = _refresh_summary(profile)
    agent.save_profile(profile)
    summary = profile["executive_summary"]
    return jsonify(
        {
            "summary": summary,
            "treatments_classified": classified_txs,
            "summary_error": summary_error,
            "profile_revision": profile["profile_revision"],
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat endpoint grounded in patient profile data."""
    data = request.get_json(force=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history", [])
    if not user_message:
        return jsonify({"error": "No message"}), 400

    profile = agent.load_profile()
    try:
        reply = agent.handle_chat(profile, user_message, history)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    response = send_from_directory(app.static_folder, "index.html")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=_args.port, debug=False)
