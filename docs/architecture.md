# Architecture

NET/Care Research Agent runs as a single Flask web app on Azure App Service
(Linux, swedencentral). All patient state is stored as a single JSON file on
the Azure Files mount at `/home/data/patient_profile.json`. There is one user
(the caregiver) and one patient.

## Component diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (caregiver)                         │
│                       static/index.html (SPA)                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                ┌───────────────▼────────────────┐
                │   Azure App Service (Linux)    │
                │                                │
                │ gunicorn (1 worker) → Flask    │
                │     │                          │
                │     ├─ /api/feed (feed queue)  │
                │     ├─ /api/jobs (polling)     │
                │     ├─ /api/summary            │
                │     ├─ /api/sources + evidence │
                │     ├─ /api/feedback           │
                │     ├─ /api/chat (general q.)  │
                │     ├─ /api/health             │
                │     └─ /api/{trials,papers,…}  │
                │     │                          │
                │     ▼                          │
                │  agent/  (intake → orchestrator│
                │           → exec_summary)      │
                └─────┬─────────────────┬────────┘
                      │                 │
              ┌───────▼──────┐   ┌──────▼─────────┐
              │  Anthropic   │   │  PubMed +      │
              │  Claude API  │   │  CT.gov v2 API │
              └──────────────┘   └────────────────┘
                      │
                      │ writes
              ┌───────▼─────────────────────────┐
              │ Azure Files mount /home/data/   │
              │   patient_profile.json (atomic) │
              │   jobs.json                     │
              │   snapshots/profile_<ts>.json   │
              │   backups/profile_YYYYMMDD.json │
              │   quarantine/                   │
              │   reports/report_*              │
              │   job_results/<job-id>.json     │
              │   source_documents/<id>/        │
              └─────────────────────────────────┘
```

## Agent topology

```
                       ┌──────────────┐
   raw text / PDF ────▶│  Intake      │  classify doc, extract structured
                       │  (Claude)    │  biomarkers/imaging/treatments
                       └──────┬───────┘
                              │ extracted JSON
                              ▼
                       ┌──────────────┐    ┌──────────────────┐
                       │ Orchestrator │◀──▶│ Tools            │
                       │ (Claude with │    │  search_pubmed   │
                       │  tool use)   │    │  search_trials   │
                       └──────┬───────┘    │  biomarker_trend │
                              │            │  flag_alert      │
                              │            │  questions       │
                              │            └──────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
     ┌────────────┐    ┌────────────┐    ┌────────────┐
     │ Classify   │    │ Exec       │    │ Questions  │
     │ treatments │    │ summary    │    │ (i18n)     │
     └────────────┘    └────────────┘    └────────────┘
```

The **orchestrator** is the only agentic loop (max 12 iterations of tool use).
All other agents are single-turn, run with adaptive thinking, and return JSON.

The **ensemble deep-sweep** (`agent/deep_sweep.py`, `POST /api/deep-sweep`) is an
on-demand variant of the orchestrator: it runs the same system prompt + tools
across several strong models (default Fable 5 + Opus 4.8) with suppression
relaxed, then a synthesis pass unions their reports. It is **read-only** — it
runs on deep copies and never writes back to the profile — so it is safe to run
repeatedly for pre-appointment prep without polluting the tracked lists.

## Execution and API boundary

`startup.sh` starts one Gunicorn worker (`--workers 1`, `--timeout 300`,
`--graceful-timeout 30`). This is load-bearing: profile mutation locking is
cross-process, but executor admission, queue capacity, and worker threads are
in-process. There are two independent bounded executors:

| Executor | Defaults | Purpose |
|---|---|---|
| Feed | `FEED_WORKERS=1`, `FEED_QUEUE_SIZE=2` | Uploaded/pasted clinical documents |
| General | `JOB_WORKERS=2`, `JOB_QUEUE_SIZE=6` | Digest, deep-sweep, chat, questions, manual summary |

Workers are clamped to 1–4 and queued capacity to 0–50. Admission reserves an
active/queued slot before persisting metadata; saturation returns `429` with
`Retry-After` (10 seconds by default), so rejected work leaves no ghost job.
Digest, deep-sweep, and summary reject a duplicate active run with `409`.

Feed, digest, deep-sweep, chat, questions, and manual summary return `202` and a
job ID. The SPA polls `GET /api/jobs/<id>` for completion and on-demand
report/result expansion. `GET /api/jobs` and `jobs.json` contain only allowlisted
PHI-safe metadata for new records; report/result bodies are separate files below
traversal-safe roots. New job errors and job-runner logs use safe codes/types
rather than input, model output, or traceback. Legacy records are not rewritten,
and protected lower-level storage/recovery logs may include OS error paths.

Queued/running jobs cannot survive restart. Startup marks them `interrupted`
with re-submit guidance. Executor shutdown waits at most five seconds per
thread, sequentially; at maximum configured concurrency those joins can exceed
Gunicorn's 30-second graceful limit, so Gunicorn may terminate first. Neither is
a durability guarantee.

Flask exempts PHI-free `/api/health` and `/api/live`; every other `/api/*` route
requires `WEBSITE_AUTH_ENABLED=true` and a valid Easy Auth principal in hosted mode.
Generic Azure hosting variables without explicit Easy Auth fail closed. Anonymous external probes
also require corresponding App Service Easy Auth path exclusions.
`AUTH_ALLOWED_PRINCIPAL_IDS`, when set, is an exact comma-separated allowlist.
Hosted mode ignores local bypass. Local API use requires explicit
`ALLOW_LOCAL_AUTH_BYPASS=1`; state-changing hosted methods compare `Origin`
only with exact `APP_ORIGIN` or canonical HTTPS `WEBSITE_HOSTNAME`.

## Why this shape

| Decision | Why |
|---|---|
| JSON file, not Postgres | Single patient, single writer; auditable diffs; trivial backup. |
| Vanilla SPA, not React | Caregiver runs the UI on a phone occasionally — zero build pipeline beats lighter frameworks. The SPA is split into `static/index.html` (markup), `static/app.js` (all logic — feed, jobs, summary, timeline, chat), and `static/styles.css`. The main column scrolls as one (exec summary + timeline + activity log share a single scrollbar); document feed is a header-anchored popover, not an inline panel. |
| Flask + gunicorn, not FastAPI/Containers | App Service runs Python natively; no Docker needed; rapid `az webapp deploy` cycle. |
| No MSAL | Single user. App Service Easy Auth gates hosted APIs except health/liveness. Local API bypass is explicit (`ALLOW_LOCAL_AUTH_BYPASS=1`), never implicit. |
| Per-agent model env vars | Lets us downgrade exec_summary or chat to Haiku independently for cost without touching code. |

## Failure modes & mitigations

| Risk | Mitigation |
|---|---|
| Corrupt `patient_profile.json` | `load_profile` quarantines a forensic copy, restores newest valid snapshot/daily backup atomically under the cross-process lock.  `CorruptProfileError` if no candidate. |
| Interrupted background job on restart | `_load_jobs` marks queued/running jobs `interrupted` with retry guidance; no traceback exposed.  Corrupt `jobs.json` quarantined; health reports `jobs_healthy=false`. |
| Queue exhaustion / duplicate expensive work | Separate bounded feed/general executors; `429 Retry-After` before metadata creation; duplicate active digest/deep-sweep/summary returns `409`. |
| Malicious or pathological PDF | `pdfplumber` runs only in `agent/pdf_extract_helper.py`, a child process with a 30-second hard timeout, page/text/output limits, minimal environment and DEVNULL streams; Linux adds CPU, address-space, file-size and FD limits. |
| Slow upstream | Anthropic uses 5 s connect, 120 s read, 10 s write, and 5 s pool operation timeouts with no SDK retries by default (configured retries clamp to 0–2); these are not an outer deadline. PubMed uses 5/12 s and ClinicalTrials.gov 5/15 s connect/read limits with no application retry. |
| Half-written profile.json on crash | `agent.io.atomic_write_text` (tmp + `os.replace`) |
| Accidental data loss | `agent.backups.rotating_snapshot` (last 20 pre-write snapshots) + `agent.backups.daily_backup` (30-day retention) with optional `.sha256` sidecar |
| Anthropic API outage | Each agent has a JSON-decode fallback that returns "insufficient_data" rather than 500 |
| Irrelevant literature pollution | `agent.tools._is_relevant` rule-based filter before persistence |
| Treatment duplicates | `agent.intake._treatment_similarity` synonym dedup (Somatuline = lanreotide) |
| Oncologist disagreement with AI | `clinical_judgments` injected verbatim into orchestrator + exec summary system prompts as hard constraints |
| Unsupported extraction evidence | Intake validates normalized model quotes against immutable source text, then stores the exact source span or explicit `missing`/`invalid` status |
| Source traversal / browser caching | Auth-gated `/api/sources/<id>[/<artifact>]` and `/api/evidence/<id>` resolve only indexed paths below `DATA_DIR`, reject traversal, and return `no-store` |
| Stale clinical judgment | Only active, nonexpired, non-review-due judgments constrain agents; all others are visibly framed as needing clinician review |
| Storage account deletion | `AzureBackupProtectionLock` (CanNotDelete) on the resource group, auto-applied by Azure Backup |
| Azure Files share deletion / corruption | (a) Recovery Services Vault daily backup, 30-day retention; (b) file-share soft-delete, 14 days |
| Single-blob accidental overwrite | Blob versioning enabled on the storage account; blob + container soft-delete, 30 days |
| Plaintext HTTP request leakage | App Service `httpsOnly: true` (auto-redirect to HTTPS); storage min TLS 1.2 |
| Secret leakage / rotation pain | `ANTHROPIC_API_KEY` stored in Azure Key Vault (RBAC); webapp resolves it via system-assigned managed identity + `@Microsoft.KeyVault(SecretUri=…)` reference. Rotation = update vault secret + restart webapp |

## Retention and deployment

Completed job metadata and its indexed report/results default to 365 days/200
records; only unindexed reports use the 30-day/200-file report settings;
unreferenced source directories use 7 days/20 directories (`JOB_RETENTION_*`,
`REPORT_RETENTION_*`, `SOURCE_ORPHAN_RETENTION_*`). Metadata/report pruning runs
at startup and job submission. Source pruning runs only at startup or after jobs
under the serialized profile mutation lock and protects every source ID still
indexed by the profile. It is best-effort, is not secure deletion, and does not purge
snapshots, backups, soft-delete/version history, or provider copies.

The complete production runtime dependency closure and setuptools build
requirement are exactly pinned from local metadata. Direct development
requirements are also exact. The archive includes `.deployment`, which declares
`SCM_DO_BUILD_DURING_DEPLOYMENT=true` for Kudu/Oryx builds.
`Scripts/deploy.ps1` requires a clean working tree plus pytest, ruff, and
gitleaks; builds and verifies a commit/SHA-256-addressed release; polls Kudu for
up to 900 seconds, then the authenticated SCM application process list and
`/api/health` critical fields and exact release commit for up to 300 seconds; and only then
preserves `.deploy/previous-known-good.*` and updates `.deploy/current-verified.*`.
Candidate deployment/readiness failure automatically redeploys and health-checks
the prevalidated current package when one exists, without promoting the candidate.
Rollback verifies the distinct previous package's SHA and embedded commit,
redeploys it, and repeats both readiness checks.
