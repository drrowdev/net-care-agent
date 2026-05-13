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

configure_logging()
log = __import__("logging").getLogger("netcare.app")

# Read package version for /api/health
try:
    from importlib.metadata import version as _pkg_version
    APP_VERSION = _pkg_version("net-care-agent")
except Exception:
    APP_VERSION = "0.0.0+unknown"

app = Flask(__name__, static_folder="static", template_folder="static")

# ── persistent storage ───────────────────────────────────────────────────────
# Default to /home/data (Azure Files mount on App Service).
# Override with DATA_DIR env var for local development.
# mkdir is deferred to runtime (inside functions) so a missing mount
# at import time does not crash the worker before gunicorn can start.
DATA_DIR  = Path(os.environ.get("DATA_DIR", "/home/data"))
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


# ── background workers ────────────────────────────────────────────────────────
def _run_feed_job(job_id: str, text: str):
    try:
        _update_job(job_id, {"status": "running", "stage": "intake"})
        profile = agent.load_profile()
        profile, extracted = agent.run_intake(text, profile)
        agent.save_profile(profile)

        _update_job(job_id, {
            "stage"        : "orchestrating",
            "document_type": extracted.get("document_type", "unknown"),
            "summary"      : extracted.get("summary", ""),
            "key_findings" : extracted.get("key_findings", []),
        })

        report = agent.run_orchestrator(profile, extracted)
        agent.save_profile(profile)

        # Classify treatments after full processing (lightweight, no summary regeneration)
        _update_job(job_id, {"stage": "classifying"})
        classified_txs = agent.classify_treatments(profile)
        profile = agent.load_profile()
        profile["treatments_classified"] = classified_txs
        agent.save_profile(profile)

        reports_dir = DATA_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rpath = reports_dir / f"report_feed_{stamp}.txt"
        rpath.write_text(report, encoding="utf-8")

        _update_job(job_id, {
            "status"     : "done",
            "stage"      : "done",
            "report"     : report,
            "report_file": str(rpath),
            "finished_at": datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        _update_job(job_id, {
            "status"   : "error",
            "stage"    : "error",
            "error"    : str(e),
            "traceback": traceback.format_exc(),
        })


def _run_digest_job(job_id: str):
    try:
        _update_job(job_id, {"status": "running", "stage": "orchestrating"})
        profile = agent.load_profile()
        extracted = {
            "document_type"      : "scheduled_digest",
            "summary"            : "Manual research digest",
            "key_findings"       : [],
            "suggested_workflows": ["pubmed_search", "trial_search", "biomarker_analysis"],
            "workflow_rationale" : (
                "Comprehensive review: search new NET literature, "
                "check European trials, review biomarker trends."
            ),
        }
        report = agent.run_orchestrator(profile, extracted)
        agent.save_profile(profile)

        # Classify treatments after digest
        _update_job(job_id, {"stage": "classifying"})
        classified_txs = agent.classify_treatments(profile)
        profile = agent.load_profile()
        profile["treatments_classified"] = classified_txs
        agent.save_profile(profile)

        reports_dir = DATA_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rpath = reports_dir / f"report_digest_{stamp}.txt"
        rpath.write_text(report, encoding="utf-8")

        _update_job(job_id, {
            "status"     : "done",
            "stage"      : "done",
            "report"     : report,
            "report_file": str(rpath),
            "finished_at": datetime.datetime.now().isoformat(),
        })

    except Exception as e:
        _update_job(job_id, {
            "status"   : "error",
            "stage"    : "error",
            "error"    : str(e),
            "traceback": traceback.format_exc(),
        })


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
    return response


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
    return jsonify({
        "status": "ok" if healthy else "degraded",
        "version": APP_VERSION,
        "profile_loaded": profile_loaded,
        "data_dir": str(DATA_DIR),
        "data_dir_writable": data_dir_writable,
    }), (200 if healthy else 503)


@app.route("/api/status")
def api_status():
    profile = agent.load_profile()
    alerts = [a for a in profile.get("alerts", []) if not a.get("resolved")]
    bms  = sorted(profile.get("biomarkers", []),
                  key=lambda x: x.get("date", ""), reverse=True)[:50]
    imgs = sorted(profile.get("imaging",    []),
                  key=lambda x: x.get("date", ""), reverse=True)[:3]
    docs = sorted(profile.get("documents",  []),
                  key=lambda x: x.get("date", ""), reverse=True)[:5]
    return jsonify({
        "patient"               : profile.get("patient", {}),
        "alerts"                : alerts,
        "recent_biomarkers"     : bms,
        "recent_imaging"        : imgs,
        "recent_documents"      : docs,
        "treatments_classified" : profile.get("treatments_classified", []),
        "stats": {
            "trials_tracked"    : len(profile.get("trials_tracked", [])),
            "literature_watched": len(profile.get("literature_watched", [])),
            "total_documents"   : len(profile.get("documents", [])),
            "total_biomarkers"  : len(profile.get("biomarkers", [])),
        },
    })


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
        "id"           : _new_id(),
        "type"         : "feed",
        "status"       : "queued",
        "stage"        : "queued",
        "created_at"   : datetime.datetime.now().isoformat(),
        "finished_at"  : None,
        "input_preview": text[:300],
        "document_type": None,
        "summary"      : None,
        "key_findings" : [],
        "report"       : None,
        "error"        : None,
    }
    _add_job(job)
    threading.Thread(target=_run_feed_job, args=(job["id"], text), daemon=True).start()
    return jsonify({"job_id": job["id"]})


@app.route("/api/feed-file", methods=["POST"])
def api_feed_file():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400

    raw_bytes = f.read()
    if f.filename.lower().endswith(".pdf"):
        import io

        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
    else:
        text = raw_bytes.decode("utf-8", errors="replace")

    if not text.strip():
        return jsonify({"error": "File appears to be empty or unreadable"}), 400

    job = {
        "id"           : _new_id(),
        "type"         : "feed",
        "status"       : "queued",
        "stage"        : "queued",
        "created_at"   : datetime.datetime.now().isoformat(),
        "finished_at"  : None,
        "input_preview": f"[File: {f.filename}] " + text[:260],
        "document_type": None,
        "summary"      : None,
        "key_findings" : [],
        "report"       : None,
        "error"        : None,
    }
    _add_job(job)
    threading.Thread(target=_run_feed_job, args=(job["id"], text), daemon=True).start()
    return jsonify({"job_id": job["id"]})


@app.route("/api/digest", methods=["POST"])
def api_digest():
    job = {
        "id"           : _new_id(),
        "type"         : "digest",
        "status"       : "queued",
        "stage"        : "queued",
        "created_at"   : datetime.datetime.now().isoformat(),
        "finished_at"  : None,
        "input_preview": "Research digest — full literature + trial sweep",
        "document_type": "digest",
        "summary"      : None,
        "key_findings" : [],
        "report"       : None,
        "error"        : None,
    }
    _add_job(job)
    threading.Thread(target=_run_digest_job, args=(job["id"],), daemon=True).start()
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
def api_delete_treatment():
    data = request.get_json(force=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    profile = agent.load_profile()
    # Remove from raw treatments list
    profile["patient"]["current_treatments"] = [
        t for t in profile["patient"].get("current_treatments", [])
        if t != text
    ]
    # Remove from classified list
    profile["treatments_classified"] = [
        t for t in profile.get("treatments_classified", [])
        if t.get("text") != text and t.get("label") != text
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/alerts/resolve/<int:idx>", methods=["POST"])
def api_resolve_alert(idx):
    profile = agent.load_profile()
    alerts = profile.get("alerts", [])
    unresolved = [a for a in alerts if not a.get("resolved")]
    if idx < len(unresolved):
        unresolved[idx]["resolved"] = True
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/treatments/update", methods=["POST"])
def api_treatments_update():
    """Update a treatment's category or remove it — syncs both classified and raw lists."""
    data = request.get_json(force=True) or {}
    action   = data.get("action")   # "remove" or "set_category"
    idx      = data.get("idx")
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
            t for t in profile["patient"].get("current_treatments", [])
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
        profile.get("trials_tracked", []),
        key=lambda x: x.get("date_added", ""), reverse=True
    )
    return jsonify(trials)


@app.route("/api/trials/<nct_id>", methods=["DELETE"])
def api_delete_trial(nct_id):
    profile = agent.load_profile()
    profile["trials_tracked"] = [
        t for t in profile.get("trials_tracked", [])
        if t.get("nct_id") != nct_id
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/papers")
def api_papers():
    profile = agent.load_profile()
    papers = sorted(
        profile.get("literature_watched", []),
        key=lambda x: x.get("date_added", ""), reverse=True
    )
    return jsonify(papers)


@app.route("/api/papers/<pmid>", methods=["DELETE"])
def api_delete_paper(pmid):
    profile = agent.load_profile()
    profile["literature_watched"] = [
        p for p in profile.get("literature_watched", [])
        if p.get("pmid") != pmid
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
    appointment_type = data.get("appointment_type", "oncology follow-up")
    profile = agent.load_profile()
    new_questions = agent.generate_questions_for_profile(profile, appointment_type)
    # Merge with existing — preserve manual questions, replace AI ones
    existing = profile.get("appointment_questions", [])
    manual = [q for q in existing if q.get("source") == "manual"]
    profile["appointment_questions"] = new_questions + manual
    agent.save_profile(profile)
    return jsonify(profile["appointment_questions"])


@app.route("/api/questions/add", methods=["POST"])
def api_questions_add():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    profile = agent.load_profile()
    today = datetime.datetime.now().isoformat()
    question = {
        "id"        : f"q_manual_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text"      : text,
        "category"  : data.get("category", "Other"),
        "priority"  : data.get("priority", "medium"),
        "rationale" : "",
        "source"    : "manual",
        "asked"     : False,
        "created_at": today[:10],
    }
    profile.setdefault("appointment_questions", []).insert(0, question)
    agent.save_profile(profile)
    return jsonify(question)


@app.route("/api/questions/<qid>/toggle", methods=["POST"])
def api_questions_toggle(qid):
    profile = agent.load_profile()
    for q in profile.get("appointment_questions", []):
        if q.get("id") == qid:
            q["asked"] = not q.get("asked", False)
            break
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/questions/<qid>", methods=["DELETE"])
def api_questions_delete(qid):
    profile = agent.load_profile()
    profile["appointment_questions"] = [
        q for q in profile.get("appointment_questions", [])
        if q.get("id") != qid
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/judgments")
def api_judgments():
    profile = agent.load_profile()
    return jsonify(profile.get("clinical_judgments", []))


@app.route("/api/judgments/add", methods=["POST"])
def api_judgments_add():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    profile = agent.load_profile()
    judgment = {
        "id"      : f"j_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
        "text"    : text,
        "category": data.get("category", "context"),
        "source"  : data.get("source", "manual"),
        "date"    : datetime.date.today().isoformat(),
    }
    profile.setdefault("clinical_judgments", []).insert(0, judgment)
    agent.save_profile(profile)
    return jsonify(judgment)


@app.route("/api/judgments/<jid>", methods=["PATCH"])
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
def api_judgments_delete(jid):
    profile = agent.load_profile()
    profile["clinical_judgments"] = [
        j for j in profile.get("clinical_judgments", [])
        if j.get("id") != jid
    ]
    agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/summary/dismiss-action/<int:idx>", methods=["POST"])
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
                "id"      : f"j_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
                "text"    : f"Regarding '{action_text[:60]}': {feedback}",
                "category": data.get("category", "context"),
                "source"  : "feedback",
                "date"    : datetime.date.today().isoformat(),
            }
            profile.setdefault("clinical_judgments", []).insert(0, judgment)
        agent.save_profile(profile)
    return jsonify({"ok": True})


@app.route("/api/summary")
def api_summary():
    profile = agent.load_profile()
    summary = profile.get("executive_summary")
    if not summary:
        return jsonify({"status": "not_generated"})
    return jsonify(summary)


@app.route("/api/summary/generate", methods=["POST"])
def api_summary_generate():
    """Generate executive summary and classify treatments on demand."""
    profile = agent.load_profile()
    summary = agent.generate_executive_summary(profile)
    classified_txs = agent.classify_treatments(profile)
    profile["executive_summary"] = summary
    profile["treatments_classified"] = classified_txs
    agent.save_profile(profile)
    return jsonify({"summary": summary, "treatments_classified": classified_txs})


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
