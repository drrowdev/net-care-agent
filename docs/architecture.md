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
                │  gunicorn → Flask (app.py)     │
                │     │                          │
                │     ├─ /api/feed (background)  │
                │     ├─ /api/summary            │
                │     ├─ /api/sources + evidence │
                │     ├─ /api/feedback           │
                │     ├─ /api/chat               │
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
              │   reports/report_*.txt          │
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

## Why this shape

| Decision | Why |
|---|---|
| JSON file, not Postgres | Single patient, single writer; auditable diffs; trivial backup. |
| Vanilla SPA, not React | Caregiver runs the UI on a phone occasionally — zero build pipeline beats lighter frameworks. The SPA is split into `static/index.html` (markup), `static/app.js` (all logic — feed, jobs, summary, timeline, chat), and `static/styles.css`. The main column scrolls as one (exec summary + timeline + activity log share a single scrollbar); document feed is a header-anchored popover, not an inline panel. |
| Flask + gunicorn, not FastAPI/Containers | App Service runs Python natively; no Docker needed; rapid `az webapp deploy` cycle. |
| No MSAL | Single user. App Service Easy Auth (Microsoft personal account) gates all requests to the deployed site. Local dev (`python app.py`) is unauthenticated. |
| Per-agent model env vars | Lets us downgrade exec_summary or chat to Haiku independently for cost without touching code. |

## Failure modes & mitigations

| Risk | Mitigation |
|---|---|
| Corrupt `patient_profile.json` | `load_profile` quarantines a forensic copy, restores newest valid snapshot/daily backup atomically under the cross-process lock.  `CorruptProfileError` if no candidate. |
| Interrupted background job on restart | `_load_jobs` marks queued/running jobs `interrupted` with retry guidance; no traceback exposed.  Corrupt `jobs.json` quarantined; health reports `jobs_healthy=false`. |
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
