#!/usr/bin/env python3
"""
NET Care Agent — Web UI backend
Deployed on Azure App Service (swedencentral)
Data persisted to /home/data (Azure Files mount)
"""

import datetime
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

from flask import Flask, jsonify, request, send_from_directory

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
    generated["stale"] = False
    generated.pop("summary_error", None)
    profile["executive_summary"] = generated
    profile["summary_stale"] = False
    return None


# ── background workers ────────────────────────────────────────────────────────
def _run_feed_job(job_id: str, text: str):
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
            profile, extracted = agent.run_intake(text, profile)

            _update_job(
                job_id,
                {
                    "stage": "orchestrating",
                    "document_type": extracted.get("document_type", "unknown"),
                    "summary": extracted.get("summary", ""),
                    "key_findings": extracted.get("key_findings", []),
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
    threading.Thread(target=_run_feed_job, args=(job["id"], text), daemon=True).start()
    return jsonify({"job_id": job["id"]})


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
    # Merge with existing — preserve manual questions, replace AI ones
    existing = profile.get("appointment_questions", [])
    manual = [q for q in existing if q.get("source") == "manual"]
    profile["appointment_questions"] = new_questions + manual
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
    return jsonify(profile.get("clinical_judgments", []))


@app.route("/api/judgments/add", methods=["POST"])
@serialized_profile_mutation
def api_judgments_add():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    profile = agent.load_profile()
    judgment = {
        "id": f"j_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text": text,
        "category": data.get("category", "context"),
        "source": data.get("source", "manual"),
        "date": datetime.date.today().isoformat(),
        "added_at": now_stamp(),
    }
    profile.setdefault("clinical_judgments", []).insert(0, judgment)
    agent.save_profile(profile)
    return jsonify(judgment)


@app.route("/api/judgments/<jid>", methods=["PATCH"])
@serialized_profile_mutation
def api_judgments_edit(jid):
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    category = data.get("category", "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    profile = agent.load_profile()
    for j in profile.get("clinical_judgments", []):
        if j.get("id") == jid:
            j["text"] = text
            if category:
                j["category"] = category
            break
    agent.save_profile(profile)
    return jsonify({"ok": True})


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
        # Optionally store feedback as a clinical judgment
        feedback = (data.get("feedback") or "").strip()
        if feedback:
            action_text = dismissed.get("action", "")
            judgment = {
                "id": f"j_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
                "text": f"Regarding '{action_text[:60]}': {feedback}",
                "category": data.get("category", "context"),
                "source": "feedback",
                "date": datetime.date.today().isoformat(),
                "added_at": now_stamp(),
            }
            profile.setdefault("clinical_judgments", []).insert(0, judgment)
        agent.save_profile(profile, clinical_change=bool(feedback))
    return jsonify({"ok": True})


@app.route("/api/summary")
def api_summary():
    profile = agent.load_profile()
    summary = profile.get("executive_summary")
    if not summary:
        return jsonify({"status": "not_generated"})
    response = dict(summary)
    response["profile_revision"] = profile.get("profile_revision")
    response["summary_revision"] = summary.get("summary_revision")
    response["stale"] = bool(profile.get("summary_stale") or summary.get("stale"))
    response["profile_updated_at"] = profile.get("profile_updated_at")
    response["recent_documents"] = sorted(
        profile.get("documents", []),
        key=lambda item: item.get("added_at") or item.get("date") or "",
        reverse=True,
    )[:5]
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
