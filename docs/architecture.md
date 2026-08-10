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
                │     ├─ /api/jobs + receipts    │
                │     ├─ /api/summary + feedback │
                │     ├─ /api/status + research  │
                │     ├─ /api/sources + evidence │
                │     ├─ /api/patient/evidence   │
                │     ├─ /api/feedback           │
                │     ├─ /api/follow-ups         │
                │     ├─ /api/visits + recap     │
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

Every successful intake commit also appends one `document_imports[]` audit record
to the profile before orchestration begins. `GET /api/jobs/<id>/receipt` exposes
that feed-job-only receipt while the job remains retained; it shows additions,
old-to-new scalar updates, conflicts/no-ops, and exact evidence state without
putting PHI in the job list. If orchestration or summary generation later fails,
the already-committed receipt remains available with the intake data.

Receipt correction/removal and whole-document undo are serialized profile
mutations. Each request carries the receipt revision plus a canonical target
fingerprint. The server compares only affected targets, so unrelated later
profile revisions may proceed; a changed affected row/scalar/treatment or a later
document claim returns atomic `409 import_conflict` with a refreshed receipt and
no partial mutation. Undo reverses direct extraction effects only. The immutable
source and append-only before/after history remain, and the document is excluded
from downstream clinical context. Research discovered during orchestration is
listed as derived receipt output but is not deleted.

Feed-derived clinical alerts carry their source document and job dependency.
Correction/removal/undo deactivates those alerts atomically without deleting
their audit record. Full semantic-row CAS catches later alert resolution and
other mutations; schema-added legacy defaults are canonicalized so they do not
create false conflicts. Generated summaries, questions, and feed reports remain
stored, but revision/generation/source invalidation hides stale conclusions from
chat, Today, Questions, and Activity until regenerated.
Digest/deep-sweep reports and chat results also record their source profile
revision; revisionless legacy artifacts are conservatively outdated. Job-list
metadata exposes only the safe revision/stale state, never report bodies.
Every newly generated alert records its source/origin job and generation profile
revision. Feed alerts additionally record source-document dependency. System-
owned dependency updates are mirrored into receipt effective state so they do
not create false CAS conflicts; caregiver changes such as resolving an alert
remain conflicting mutations.
Alert lifetime is explicit: `durable` ingestion/trial-status alerts remain until
resolved, `source` alerts remain until source correction/undo or resolution, and
`profile_snapshot` alerts require their exact generation revision. Digest
trial-poll mutations commit before fallible orchestration/classification so
durable alerts survive downstream failure.
Alert resolution is serialized by stable alert ID, semantic token, and expected
profile revision; index-based resolution returns `410`. Resolution advances the
clinical revision because generated contexts may have consumed the alert. This
invalidates prior chat history, in-flight chat responses, reports/results,
summaries, and generated questions while durable/source-scoped sibling alerts
remain active under their own lifecycle.

The SPA exposes this contract through one semantic Resolve alert dialog in the
existing Patient alert list. Four mutually exclusive modes send either no link,
one stable action ID, a bounded caregiver-authored follow-up, or one stable visit
ID plus an optional eligible decision ID. Blank outcomes are omitted; nonblank
outcomes retain administrative, caregiver-reported-unverified, or
clinician-attributed-unverified provenance without verified styling. Selector
rows are projected only from the current action/visit caches and eligible
statuses.

One client intent owner is acquired before selection, source loading, or
mutation-ID allocation. Every alert/source/convergence response must still match
that owner, patient-data epoch, alert ID/selection epoch/token, and monotonic
profile/workflow authority before it can change state, DOM, drafts, retry, focus,
or cleanup. Ambiguous transport retry reuses the exact immutable request; `409`
redacts the old card/dialog copy and reloads fresh authority while preserving
only eligible caregiver draft fields. Offline transport keeps the last
authoritative alert/link projections visibly stale and read-only. Authorization
or hard failure centrally evicts every visible and hidden alert copy, selector,
form value, cache, draft, retry body, owner, focus/inert reference, and late
response. Successful rendering waits for accepted revisions plus authoritative
status/action/visit convergence and shows only the bounded returned outcome/link
confirmation.

Schema v8 separates clinical freshness from durable workflow bookkeeping.
`profile_revision` remains the clinical/effective dependency identity for
summaries, questions, chat, reports, alerts, and treatment classification.
`workflow_revision` advances once for every follow-through transaction.
Administrative owner/due/order/pin/status changes do not stale clinical
artifacts; caregiver-captured answers, decisions, clinical outcomes, and every
alert resolution advance both revisions.

`caregiver_actions[]` stores accepted follow-ups independently of their
generated source. `POST /api/follow-ups` accepts a current summary action only
by opaque stable source ID + semantic token, then snapshots its full
caregiver-visible row and generation identity. `PATCH
/api/follow-ups/<action_id>` uses action ID + full-row token and records owner,
due date, lifecycle, and a typed completion/cancellation outcome. Direct
treatment instructions are rejected in favor of contact/ask/confirm wording.

The Today view exposes these records through one responsive Follow-through
surface with Active, Completed, Cancelled, and All projections. One browser
cache keyed by stable action ID also supplies the appointment workspace's
read-only visit-linked rows. Generated assessment acceptance reads only the
current server-projected source ID/token from data attributes; stale or
revisionless rows are redacted before they can be acted on. Action mutation
intents capture both `phiEpoch` and a separate action-selection epoch so late
action A responses cannot repaint action B.

The client treats `workflow_revision` and `profile_revision` independently.
Workflow-only action responses update the shared action UI without invalidating
clinical artifacts. A changed returned clinical revision enters the existing
authoritative status/summary/questions/tasks/chat/visits refresh path. Exact
transport retries retain one immutable request; `409` responses never auto-retry
and reload the addressed action/source before a new explicit request. Action
loading is event-driven (view entry, relevant visibility restoration,
successful mutation, and explicit retry), never polled. Transient failures keep
only caregiver drafts plus an eligible exact retry intent; authorization/hard
failure centrally evicts every action cache, token, DOM/dialog value, draft,
retry/focus reference, and late response.

`visits[]` is deliberately separate from intake-imported `appointments[]`.
`/api/visits` creates and updates working records; nested question endpoints
snapshot a current generated question or an explicit manual question, then
capture pin/order and an answered/unknown clinician response. Decision endpoints
append immutable caregiver-entered, clinician-attributed statements and change
only explicit lifecycle state. Resulting follow-ups are durable action records
linked by ID. Generated questions never become clinician facts.

`GET /api/visits/<visit_id>/recap` is an authenticated, no-store read
projection, not a generated or persisted artifact. It requires the selected
visit's full semantic token and returns that token, both workflow/profile
revisions, and a recap semantic token over the exact bounded response. One
profile load deterministically joins the visit with its durable follow-ups and
only structured resolved-alert links relevant to that visit. The projection
allowlists visible fields and excludes mutation history, replay snapshots,
source paths/text/quotes, evidence offsets, receipt internals, and model/job
internals. A changed visit token returns `409`; viewing or exporting never saves,
advances a revision, appends history, or marks anything reviewed.

Full recap content is available only for in-progress and completed visits.
Planned visits remain unavailable until started; cancelled visits return a
bounded administrative, non-exportable state. Answer and decision wording is
never summarized: generated question snapshots retain generated provenance,
answers and current decisions retain the caregiver-entered/
clinician-attributed/unverified label, and superseded/retracted decisions are
excluded from current statements. Visit-linked action and alert outcomes retain
their typed provenance, with administrative outcomes explicitly non-clinical.

The Questions view now exposes those contracts through one responsive appointment
working mode rather than another top-level SPA view. `GET /api/visits` includes a
bounded picker projection only for imported appointments whose source/import is
still active and linkable; paths, raw text, source quotes, evidence offsets, and
receipt internals are excluded. Visit creation revalidates the selected source ID
under the mutation lock. Question ranking uses one complete-order visit mutation:
the server verifies the visit token, exact current question ID/token membership,
normalizes all ranks, appends one audit event, advances only
`workflow_revision`, and saves once. A conflict cannot leave a partially reordered
authoritative list.

The workspace's fourth internal **Recap** tab loads only on tab/visit entry,
explicit retry, relevant mutation convergence, or visibility restoration while
active. Every response and Copy/Download/Print action must still match the
request epoch, patient-data epoch, visit-selection epoch, selected visit
ID/token, both monotonic revisions, and accepted recap token before changing
DOM/cache or causing an export side effect. Newer authority immediately clears
the export payload and disables actions. Offline failure may retain only a
visibly stale read-only recap; authorization/hard failure scrubs the recap DOM,
structured cache, export text, object URL, focus references, and late responses.
Text download uses a generic UTF-8 `text/plain` filename and print CSS excludes
navigation, controls, dialogs, and stale content. No recap polling or browser
storage is used.

Every new Layer 2 mutation carries a bounded `mutation_id`, appends an immutable
endpoint/operation/target scope plus request-hash/before-token/after-token event,
compares only the addressed semantic target, and saves once under
`serialized_mutation`. The request hash uses deterministic key ordering while
preserving every accepted value, including CAS/source tokens; unsupported fields
are rejected before replay lookup. Each event stores the original endpoint-shaped
response, including returned tokens, linked objects, and revision values. Exact
retries return that snapshot without another save even after later target edits;
mutation-ID reuse across endpoints, operations, targets, or payloads returns
`409`. A canonical result hash and endpoint/owner/link contract reject missing,
malformed, or mismatched snapshots rather than returning a success-shaped row.
Older committed events without those replay guarantees also conflict. Alert
resolution extends the same
audit model with structured outcome and optional visit/decision/follow-up links
while preserving sibling alerts. Legacy alert clients that omit `mutation_id`
retain a deterministic server-derived ID in a client-inaccessible namespace and
can replay only an exact request.
The index route stays retired.

Clinical jobs establish one effective revision: feed/digest commit clinical
mutations and finalized alert dependencies first, then generate/save the summary
as derived bookkeeping at that same revision. Manual summary refresh is also
derived-only. Chat history carries a profile revision; mismatched history is
rejected synchronously with `409` and revalidated in the worker.

Treatment classification carries revision/job identity. Raw treatment mutation
invalidates it before the first save; output must cover every raw treatment
component bidirectionally with no ungrounded extras or collapsed distinct drugs.
When stale/failing, all consumers use the raw `current_treatments` fallback.
Schema v6 stores deterministic raw source/component records and maps every
classified row to component IDs. Manual remove/complete uses treatment ID +
semantic token + expected profile revision; composite siblings survive, and
stale/missing/changed mappings return `409`.
Classification certification strips recognized identities and permits only
known status/action/dose/schedule modifiers in the residual text. Unknown drugs,
procedures, or transition targets fail closed. Transition narratives are split
only when each side has one certified identity, and the edit endpoint rechecks
exclusive component coverage before any destructive mutation.

Schema v7 remediates released legacy alerts: generated source-less rows are
deterministically sanitized and bound to their migration-time profile snapshot,
while only explicitly recognized ingestion-failure and trial-status producers
remain durable. Receipt effective values are synchronized in the same migration.
Nullable legacy patient scaffolding is coerced before treatment-record backfill;
non-null invalid structural types still follow quarantine/recovery.

Executive-summary prompts receive an opaque catalog of verified source-span IDs.
The model may select only those IDs for named claims and actions; Flask resolves
them to authenticated `/api/evidence/<id>` links. Missing selections remain
explicitly `missing`, and invented/unknown IDs are labelled `invalid` rather than
silently attached to a nearby source.

Web and CLI research runs share one canonical NCT/PMID diff. Each digest stores
the exact additions in `latest_research_update`; a feed run replaces that
snapshot only when it adds research. `GET /api/status` rejects malformed IDs,
filters the stored IDs against records that still exist, and returns counts plus
identifiers. The SPA refreshes that status on **Today**, after visibility
restoration, and while relevant work is active, then labels the matching tracked
trials and papers **New**. The retired
`/api/changes` routes return an inert zero-count payload temporarily so cached
pre-release tabs stop showing the removed review control without writing state.

Action dismissal posts the assessment revision and expected action text to
`POST /api/summary/dismiss-action/<idx>`. Flask returns `409` without mutating
the profile if either value no longer matches, preventing feedback opened on an
older assessment from dismissing a newly generated recommendation.

Queued/running jobs cannot survive restart. Startup marks them `interrupted`
with re-submit guidance. Executor shutdown waits at most five seconds per
thread, sequentially; at maximum configured concurrency those joins can exceed
Gunicorn's 30-second graceful limit, so Gunicorn may terminate first. Neither is
a durability guarantee.

Flask exempts PHI-free `/api/health` and `/api/live`; every other `/api/*` route
requires platform-enabled Easy Auth (which injects `WEBSITE_AUTH_ENABLED`) and a
valid principal in hosted mode.
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
| Vanilla SPA, not React | Caregiver runs the UI on a phone occasionally — zero build pipeline beats lighter frameworks. The split SPA uses one responsive Today/Patient/Questions/Activity shell on every screen size. `static/index.html` owns semantic markup and dialogs, `static/app.js` owns API state/rendering, receipt reconciliation, appointment and alert-resolution owners/epochs/drafts, focus/inert behavior, and load states, and `static/styles.css` provides the green/amber desktop rail, overflow-safe alert sheet, full-height phone appointment sheet, and fixed phone navigation. |
| Flask + gunicorn, not FastAPI/Containers | App Service runs Python natively; no Docker needed; rapid `az webapp deploy` cycle. |
| No MSAL | Single user. App Service Easy Auth gates hosted APIs except health/liveness. Local API bypass is explicit (`ALLOW_LOCAL_AUTH_BYPASS=1`), never implicit. |
| Per-agent model env vars | Lets us downgrade exec_summary or chat to Haiku independently for cost without touching code. |
| Separate imported appointments and workflow visits | Receipt-correctable source facts remain immutable evidence; caregiver working state can evolve without pretending generated questions or captured statements are source-verified. |
| Clinical + workflow revisions | Administrative follow-through does not invalidate expensive clinical artifacts, while new model-context facts still stale every dependent artifact safely. |

## Failure modes & mitigations

| Risk | Mitigation |
|---|---|
| Corrupt `patient_profile.json` | `load_profile` quarantines a forensic copy, restores newest valid snapshot/daily backup atomically under the cross-process lock.  `CorruptProfileError` if no candidate. |
| Interrupted background job on restart | `_load_jobs` marks queued/running jobs `interrupted` with retry guidance; no traceback exposed.  Corrupt `jobs.json` quarantined; health reports `jobs_healthy=false`. |
| Queue exhaustion / duplicate expensive work | Separate bounded feed/general executors; `429 Retry-After` before metadata creation; duplicate active digest/deep-sweep/summary returns `409`. |
| Malicious or pathological PDF | `pdfplumber` runs only in `agent/pdf_extract_helper.py`, a child process with a 30-second hard timeout, page/text/output limits, minimal environment and DEVNULL streams; Linux adds CPU, address-space, file-size and FD limits. |
| Slow upstream | Anthropic uses bounded connect/read/write/pool phases plus a 180-second monotonic overall deadline and no SDK retries by default (configured retries clamp to 0–2). PubMed uses 5/12 s and ClinicalTrials.gov 5/15 s connect/read limits with no application retry. |
| Half-written profile.json on crash | `agent.io.atomic_write_text` (tmp + `os.replace`) |
| Accidental data loss | `agent.backups.rotating_snapshot` (last 20 pre-write snapshots) + `agent.backups.daily_backup` (30-day retention) with optional `.sha256` sidecar |
| Anthropic API outage | Each agent has a JSON-decode fallback that returns "insufficient_data" rather than 500 |
| Irrelevant literature pollution | `agent.tools._is_relevant` rule-based filter before persistence |
| Treatment duplicates | `agent.intake._treatment_similarity` synonym dedup (Somatuline = lanreotide) |
| Oncologist disagreement with AI | `clinical_judgments` injected verbatim into orchestrator + exec summary system prompts as hard constraints |
| Unsupported extraction evidence | Intake validates normalized model quotes against immutable source text, then stores the exact source span or explicit `missing`/`invalid` status |
| Stale import correction or undo | Target-level compare-and-swap fingerprints and later-claim checks return atomic `409`; no whole-profile snapshot is restored |
| Incorrect import removed from active care context | Direct facts are reversed, the document is marked excluded from clinical prompts, and immutable source/audit history remains visible |
| Invented summary evidence link | Only server-built evidence catalog IDs resolve; unknown IDs are visibly `invalid` and absent IDs are `missing` |
| Stale generated conclusions after correction | Revision-aware summary hiding, question generation IDs, source-dependent alert invalidation, and hidden feed reports retain audit artifacts without presenting them as current |
| Wrong alert resolved after reorder | Stable alert IDs + semantic token + expected revision under the mutation lock; stale/missing targets return `409` |
| Accepted action disappears with an old summary | Server-side source ID/token acceptance snapshots the full generated row into durable `caregiver_actions[]` before the artifact can become stale |
| Administrative task edit stales clinical output | `workflow_revision` advances independently; only explicit clinical capture advances `profile_revision` |
| Caregiver note presented as verified clinician fact | Fixed provenance labels every answer/decision as caregiver-entered, clinician-attributed, and unverified; generated questions remain snapshots |
| Retry duplicates a decision or follow-up | Mutation ID + canonical request hash replay returns the prior target without another save or revision increment |
| Old chat contaminates corrected record | Client clears history on profile revision change; server rejects mismatched `history_revision` with `409` |
| Cached PHI after auth/load failure | Central client eviction clears every patient-bearing cache, panel, dialog, chat turn, receipt/report, filter, and open feedback surface; non-auth receipt refresh is the only fallback exception |
| Source traversal / browser caching | Auth-gated `/api/sources/<id>[/<artifact>]` and `/api/evidence/<id>` resolve only indexed paths below `DATA_DIR`, reject traversal, and return `no-store` |
| Stale clinical judgment | Only active, nonexpired, non-review-due judgments constrain agents; all others are visibly framed as needing clinician review |
| Storage account deletion | `AzureBackupProtectionLock` (CanNotDelete) on the resource group, auto-applied by Azure Backup |
| Azure Files share deletion / corruption | (a) Recovery Services Vault daily backup, 30-day retention; (b) file-share soft-delete, 14 days |
| Single-profile accidental overwrite | Cross-process serialized writes, rotating pre-save snapshots, daily Azure Files backup, and file-share soft delete |
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
Reconciliation audit records are part of `patient_profile.json` and therefore
follow profile backup/recovery rather than job-artifact pruning. The job-scoped
receipt endpoint is intentionally available only while its feed job is retained.

The complete production runtime dependency closure and setuptools build
requirement are exactly pinned from local metadata. Direct development
requirements are also exact. The archive includes `.deployment`, which declares
`SCM_DO_BUILD_DURING_DEPLOYMENT=true` for Kudu/Oryx builds.
`Scripts/deploy.ps1` requires a clean working tree plus pytest, ruff, and
gitleaks; builds and verifies a commit/SHA-256-addressed release; polls Kudu for
up to 900 seconds, then
`/api/health` critical fields and exact release commit for up to 300 seconds; and only then
preserves `.deploy/previous-known-good.*` and updates `.deploy/current-verified.*`.
Candidate deployment/readiness failure automatically redeploys and health-checks
the prevalidated current package when one exists, without promoting the candidate.
Rollback verifies the distinct previous package's SHA and embedded commit,
redeploys it, and repeats both readiness checks.
