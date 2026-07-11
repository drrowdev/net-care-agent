# NET/Care Research Agent

A multi-agent AI system that performs on-demand clinical monitoring for a Grade 2
metastatic neuroendocrine tumor (NET) patient. Operated by the patient's caregiver.

The agent ingests clinical documents, extracts structured medical data, searches
PubMed and ClinicalTrials.gov, synthesises findings into actionable summaries, and
learns from every consultation with the treating oncologist.

> ⚠️ **Decision-support tool only.** Output must be reviewed by a qualified clinician
> before any medical action. Not a medical device.

## Architecture

| Layer       | Implementation                                              |
|-------------|-------------------------------------------------------------|
| LLM         | Anthropic Claude per-role tiering (Opus 4.8 / Sonnet 5; Fable 5 + Opus deep sweep) |
| Backend     | Flask + gunicorn                                            |
| Storage     | JSON file on Azure Files mount (`/home/data`)               |
| Frontend    | Single-page vanilla JS UI (`static/index.html` + `app.js` + `styles.css`) |
| Hosting     | Azure App Service (Linux, swedencentral) behind Easy Auth (Microsoft account) |
| Secrets     | Azure Key Vault + system-assigned managed identity on the webapp |
| External    | PubMed E-utilities, ClinicalTrials.gov API v2               |

## Local development

Requires Python 3.11.

```powershell
# 1. Create venv and install
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Configure secrets
Copy-Item .env.example .env
# edit .env and set ANTHROPIC_API_KEY

# 3. Run (.env.example explicitly sets ALLOW_LOCAL_AUTH_BYPASS=1)
.\Scripts\run_local.ps1
# or:  python app.py --port 8000
```

Open http://localhost:8000. Local APIs are denied by default unless
`ALLOW_LOCAL_AUTH_BYPASS=1` is explicitly set (the local `.env.example` does
this). Hosted deployments ignore that bypass.

## Tests

```powershell
pytest
```

Tests use recorded HTTP fixtures for PubMed and ClinicalTrials.gov, a fake Anthropic
client, and a temporary data directory — no network calls, no API key required.

## Lint & format

```powershell
ruff check agent tests          # CI runs this on every push
ruff format agent tests         # auto-format
pre-commit install              # one-time: install git hooks
```

`ruff` is also wired into `.pre-commit-config.yaml` along with whitespace,
EOL, YAML, TOML, large-file, and private-key checks. Dependabot watches both
pip and GitHub Actions deps weekly.

## Deployment

Azure App Service (Linux). See `startup.sh` for the gunicorn launch command.

Environment variables to set as Application Settings:

- `ANTHROPIC_API_KEY` (required) — **in production this is a Key Vault reference**
  (`@Microsoft.KeyVault(SecretUri=https://<keyvault-name>.vault.azure.net/secrets/ANTHROPIC-API-KEY/)`),
  resolved via the webapp's system-assigned managed identity. See
  [`AGENTS.md` → Secrets](AGENTS.md#secrets) for the rotation runbook.
- `DATA_DIR` defaults to `/home/data` on Azure (Azure Files mount)
- `ANTHROPIC_MODEL` defaults to `claude-sonnet-5`; per-role overrides
  (`ANTHROPIC_MODEL_INTAKE`, `ANTHROPIC_MODEL_ORCHESTRATOR`, …) — see
  `.env.example`
- `ANTHROPIC_DEEPSWEEP_MODELS` / `ANTHROPIC_DEEPSWEEP_SYNTHESIS` — models used by
  the on-demand ensemble deep-sweep (default `claude-fable-5,claude-opus-4-8`
  synthesised by `claude-opus-4-8`)
- `JOB_WORKERS=2`, `JOB_QUEUE_SIZE=6` — bounded general in-process executor
- `FEED_WORKERS=1`, `FEED_QUEUE_SIZE=2` — independent upload executor; worker
  and queue settings are clamped to 1–4 and 0–50
- `RETRY_AFTER_SECONDS=10` — response hint when either queue is full
- PDF containment: `PDF_PARSE_TIMEOUT_SECONDS=30`, `MAX_PDF_PAGES=100`,
  `MAX_EXTRACTED_TEXT_CHARS=1000000`, `PDF_MAX_MEMORY_MB=384`
- Anthropic: `ANTHROPIC_CONNECT_TIMEOUT_SECONDS=5`,
  `ANTHROPIC_READ_TIMEOUT_SECONDS=120`,
  `ANTHROPIC_OVERALL_TIMEOUT_SECONDS=180`, `ANTHROPIC_MAX_RETRIES=0`
  (retries clamped to 0–2). Connect/read/write/pool phases are bounded by the
  overall monotonic deadline, including streamed response bodies.
- Retention: `JOB_RETENTION_DAYS=365`, `JOB_RETENTION_COUNT=200`,
  `REPORT_RETENTION_DAYS=30`, `REPORT_RETENTION_COUNT=200`,
  `SOURCE_ORPHAN_RETENTION_DAYS=7`, `SOURCE_ORPHAN_RETENTION_COUNT=20`
- Auth: hosted APIs require App Service Easy Auth; the platform injects
  `WEBSITE_AUTH_ENABLED` (do not add that protected setting manually). Generic
  Azure hosting variables never make Easy Auth headers trusted. `APP_ORIGIN` (preferred) or
  `WEBSITE_HOSTNAME` supplies the canonical HTTPS browser origin.
  `AUTH_ALLOWED_PRINCIPAL_IDS` is an optional comma-separated exact principal-ID allowlist. Never set
  `ALLOW_LOCAL_AUTH_BYPASS` in hosted configuration.

`startup.sh` uses exactly one Gunicorn worker, a 300-second worker timeout, and
a 30-second graceful timeout. **One worker is load-bearing:** profile writes are
cross-process locked, but job admission, queues, and execution are in-process.
Do not scale workers/instances until jobs move to a durable distributed queue.

The complete production runtime dependency closure in `requirements.txt` and
the setuptools build requirement are exactly pinned from local installed metadata;
direct development requirements are exact in `pyproject.toml`. `.deployment` is included in the release archive
and declares Oryx build-on-deploy.
`Scripts/deploy.ps1` gates packages on pytest, ruff, and gitleaks; verifies
SHA-256; polls asynchronous Kudu, the authenticated SCM process list, and
the public PHI-free application health endpoint; and
promotes the hash/package to `.deploy/current-verified.*` only after success,
first preserving the former current package as `.deploy/previous-known-good.*`.
The script refuses a dirty working tree so the recorded HEAD identifies the
package. Promotion requires `/api/health` to identify the packaged commit and
report healthy critical storage/job fields; a usable `degraded` response is
accepted for noncritical interrupted history. `-Rollback` fails when no distinct
previous package exists, verifies its hash and embedded commit, redeploys it,
then repeats both readiness checks.

## Profile schema

All patient state lives in a single JSON file at `${DATA_DIR}/patient_profile.json`:

```
{
  "schema_version": 1,
  "profile_revision": 42,
  "profile_updated_at": "2026-07-10T16:51:49",
  "profile_saved_at": "2026-07-10T16:52:03",
  "summary_stale": false,
  "patient": { ... },
  "biomarkers":  [ {date, marker, value, source_document_id, source_quote, evidence_status}, ... ],
  "imaging":     [ {date, modality, findings, impression, source_document_id, source_quote}, ... ],
  "treatments":  [ {name, status, start_date, end_date, ...}, ... ],
  "documents":   [ {date, type, summary, key_findings, source_document_id, raw_text}, ... ],
  "source_documents": [ {id, ingested_at, source: {path, sha256, length}, text: {...}}, ... ],
  "trials":      [ {nct_id, title, status, ...}, ... ],
  "papers":      [ {pmid, title, journal, date}, ... ],
  "alerts":      [ {priority, action, created, resolved}, ... ],
  "judgments":   [ {category, text, scope, status, review_after, valid_until, supersedes}, ... ],
  "questions":   [ {id, text, category, priority, asked}, ... ],
  "feedback":    [ {target, item_id, assessment, note, outcome, timestamps}, ... ],
  "exec_summary": { "summary_revision": 42, "stale": false, ... }
}
```

`schema_version` tracks the profile schema revision. Deterministic, idempotent
migrations run automatically on load (see `agent/migrations.py`), upgrading
legacy profiles to the current version and logging each step in `_migration_log`.
If a corrupt profile is detected, the app automatically recovers the newest valid
pre-save snapshot or daily backup before applying migrations.

Every clinical-content save advances `profile_revision`; bookkeeping-only saves
(for example acknowledging unread items or marking a question asked) update
`profile_saved_at` without invalidating the summary. Summary freshness compares
the clinical revision with `executive_summary.summary_revision`, independent of
clinical dates.

A daily backup is written to `${DATA_DIR}/backups/profile_YYYYMMDD.json`
(retention: 30 days).

Fed source bytes and extracted text are immutable protected artifacts below
`${DATA_DIR}/source_documents/<source_document_id>/`. The profile stores only a
compact SHA-256/length/path index plus a legacy `raw_text` preview; it remains the
structured authority. Hosted source/evidence retrieval requires Easy Auth and
never exposes filesystem paths in API responses.

New job records contain PHI-safe allowlisted metadata and generic errors.
Legacy retained job records are not rewritten. Report and structured
result bodies live in separate artifacts and are read only from
`GET /api/jobs/<id>`; they are not embedded in `jobs.json` or the job-list
response. Retention pruning runs at startup/job admission and is best-effort:
age/count limits do not securely erase backups/provider copies, and source
directories still referenced by the profile are deliberately protected.

## Safety notes

- All Claude calls run with adaptive thinking (Sonnet 5); structured-output
  calls parse the first `text` block (after any `thinking` block) and no
  longer set `temperature` (it must be unset when thinking is enabled).
- Active, nonexpired, non-review-due clinical judgments override AI
  recommendations. Superseded/expired/review-due items remain visible for review.
- Trial and paper relevance is filtered before being persisted.
- Treatment names are fuzzy-matched against synonyms (Somatuline = lanreotide etc.).
- The patient profile is the only source of truth; no conversation state persists.

## Repository layout

```
.
├── README.md             # This file
├── HANDOFF.md            # Single-page primer for new AI assistants — start here
├── CHANGELOG.md          # User-visible changes per version
├── AGENTS.md             # Onboarding + doc-update policy for AI assistants
├── app.py                # Flask app: HTTP endpoints + background jobs + /api/health
├── net_agent.py          # Back-compat shim — re-exports the agent.* package
├── INVARIANTS.md         # Load-bearing rules & output contracts (read before editing)
├── Scripts/              # deploy.ps1 (verified deploy+rollback), eval_harness.py
├── agent/                # Modular agent core
│   ├── config.py         # paths + per-agent ANTHROPIC_MODEL_* env overrides
│   ├── llm.py            # Anthropic client + JSON-fence stripper
│   ├── profile.py        # load/save (atomic) + DEFAULT_PROFILE + summary
│   ├── io.py             # atomic_write_text helper
│   ├── backups.py        # daily snapshot + 30-day retention
│   ├── logging_config.py # text/JSON log formatter
│   ├── job_runtime.py    # bounded executors, safe artifacts + PDF subprocess
│   ├── pdf_extract_helper.py # child-only pdfplumber entry point
│   ├── judgments.py      # clinical-judgment context formatter
│   ├── intake.py         # extract structured medical data from text
│   ├── orchestrator.py   # agentic loop driving the tools
│   ├── verify.py         # deterministic PMID/NCT existence verifier (report backstop)
│   ├── trials_poll.py    # deterministic tracked-trial status poller
│   ├── deep_sweep.py     # on-demand ensemble deep-sweep (multi-model, read-only)
│   ├── classify.py       # treatment dedup + active/planned/completed
│   ├── exec_summary.py   # JSON executive summary generator
│   ├── questions.py      # Appointment questions (language via patient.language)
│   ├── chat.py           # /api/chat handler (pure function)
│   ├── cli.py            # `python net_agent.py {feed|digest|status|update-profile}`
│   └── tools/            # PubMed, ClinicalTrials.gov, biomarker trends + dispatcher
├── static/                 # Single-page UI (Phase 4 split)
│   ├── index.html          # Markup + header (Feed popover, status pill, actions)
│   ├── app.js              # All client logic (feed, jobs, summary, chat, timeline)
│   └── styles.css          # Styles (incl. feed popover + unified main scroll)
├── startup.sh            # gunicorn launcher (Azure App Service)
├── pyproject.toml        # Python deps + tooling config
├── .env.example          # Template for local secrets
├── tests/                # pytest suite (no network or API key needed)
└── docs/                 # Architecture & schema docs
    ├── architecture.md
    ├── operating_manual.md
    └── profile_schema.md
```

## How it works (sequence)

```mermaid
sequenceDiagram
    participant U as Caregiver
    participant API as Flask /api/feed
    participant W as Background worker
    participant I as Intake agent
    participant O as Orchestrator
    participant T as Tools (PubMed / CT.gov / biomarkers / alerts)
    participant E as Exec summary
    participant J as patient_profile.json

    U->>API: POST text or PDF
    API->>W: bounded enqueue; 202 + job_id
    U->>API: poll GET /api/jobs/<id>
    W->>I: run_intake(text, profile)
    I-->>W: structured extract (biomarkers, treatments, ...)
    W->>J: save_profile (atomic + daily backup)
    W->>O: run_orchestrator(profile, extracted)
    loop until end_turn or 12 iterations
        O->>T: tool_use (search_pubmed, ...)
        T-->>O: results (filtered by NET relevance)
        O->>J: persist new papers/trials/alerts
    end
    O-->>W: report artifact (not embedded in job metadata)
    W->>E: generate_executive_summary
    E-->>W: JSON summary
    W->>J: save_profile
    U->>API: GET /api/jobs/<id> → report/result on demand
    U->>API: GET /api/summary → JSON
```

Feed, digest, deep-sweep, chat, question generation, and manual summary
generation are asynchronous. The SPA polls every 1.5 seconds when awaiting a
specific result and every 3 seconds for the activity/status views. Queue
saturation returns `429 Retry-After` before a job is persisted; duplicate
active digest/deep-sweep/summary runs return `409`. A process restart cannot
resume in-process work: queued/running records become `interrupted` and the
caregiver must re-submit. Graceful shutdown is bounded, not a durability
guarantee.

The orchestrator's behaviour is shaped by **clinical_judgments** captured from
oncologist consultations. These act as hard constraints: anything the oncologist
has already addressed is excluded from the recommended actions.

## Operating manual

Day-to-day caregiver workflow lives in [`docs/operating_manual.md`](docs/operating_manual.md).
The most common loops:

| Action | Where | What happens |
|---|---|---|
| Add a clinical document | Header → **📄 Feed** button → popover (paste text or upload file) | Queued on the independent feed executor; PDF parsing is child-only, then intake → orchestrator → exec summary |
| Run a research-only sweep | Header → **↻ Run digest** | Orchestrator runs without new input; new trials/papers added |
| Record an oncologist's judgment | UI → "Judgments" tab → Add | Becomes a hard constraint for future runs |
| Resolve / dismiss an alert | UI → Alert card → Resolve | Marked resolved, persisted in profile |
| Generate appointment questions | UI → "Questions" tab → Generate | Async result is polled, then the question list is rendered |
| Chat with the record | Header → **✦ Ask Claude** | Async result grounded in the full profile; chat remains stateless |
| Open a trial | Exec summary → "Best matched trial" chip | Opens `clinicaltrials.gov/study/<NCT_ID>` in a new tab |

## Keeping docs current

Whenever the UI flow, repo layout, or HTTP/CLI surface changes, update:

- `README.md` — architecture table, repo layout tree, operating-loops table
- `docs/operating_manual.md` — caregiver workflows
- `docs/architecture.md` — component or topology diagrams if endpoints/agents change
- `CHANGELOG.md` — every user-visible change goes under `[Unreleased]`

The full doc-update policy (which doc to touch for which kind of change),
commit conventions, deploy mechanism, and common pitfalls are in
[`AGENTS.md`](AGENTS.md). AI assistants working in this repo should read it
first.
