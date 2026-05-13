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
              │   backups/profile_YYYYMMDD.json │
              │   reports/report_*.txt          │
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
All other agents are single-turn, `temperature=0`, return JSON.

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
| Half-written profile.json on crash | `agent.io.atomic_write_text` (tmp + `os.replace`) |
| Accidental data loss | `agent.backups.daily_backup` snapshot, 30-day retention |
| Anthropic API outage | Each agent has a JSON-decode fallback that returns "insufficient_data" rather than 500 |
| Irrelevant literature pollution | `agent.tools._is_relevant` rule-based filter before persistence |
| Treatment duplicates | `agent.intake._treatment_similarity` synonym dedup (Somatuline = lanreotide) |
| Oncologist disagreement with AI | `clinical_judgments` injected verbatim into orchestrator + exec summary system prompts as hard constraints |
| Storage account deletion | `AzureBackupProtectionLock` (CanNotDelete) on the resource group, auto-applied by Azure Backup |
| Azure Files share deletion / corruption | (a) Recovery Services Vault daily backup, 30-day retention; (b) file-share soft-delete, 14 days |
| Single-blob accidental overwrite | Blob versioning enabled on the storage account; blob + container soft-delete, 30 days |
| Plaintext HTTP request leakage | App Service `httpsOnly: true` (auto-redirect to HTTPS); storage min TLS 1.2 |
| Secret leakage / rotation pain | `ANTHROPIC_API_KEY` stored in Azure Key Vault (RBAC); webapp resolves it via system-assigned managed identity + `@Microsoft.KeyVault(SecretUri=…)` reference. Rotation = update vault secret + restart webapp |
