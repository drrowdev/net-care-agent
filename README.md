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
| Frontend    | Responsive vanilla JS workspace (`static/index.html` + `app.js` + `styles.css`) |
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
SHA-256; polls authenticated asynchronous Kudu to terminal success and then
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
  "schema_version": 15,
  "profile_revision": 42,
  "workflow_revision": 17,
  "profile_updated_at": "2026-07-10T16:51:49",
  "profile_saved_at": "2026-07-10T16:52:03",
  "summary_stale": false,
  "patient": { ... },
  "biomarkers":  [ {id, date, date_precision, date_kind, marker, value, unit, reference_range, flag, flag_authority, specimen, assay, method, source_document_id, evidence_status}, ... ],
  "imaging":     [ {id, date, date_precision, date_kind, source_document_date, modality, findings, impression, source_document_id, evidence_status}, ... ],
  "symptoms":    [ {id, date, date_precision, date_kind, source_document_date, symptom, severity, source_document_id, evidence_status}, ... ],
  "symptom_episodes": [ {id, status, symptom_text, severity_level, severity_detail, reported_subject, onset_date, resolved_date, provenance, caregiver_action_id, history}, ... ],
  "treatments_classified": [ {id, text, label, category, date, source_treatment_ids}, ... ],
  "treatment_courses": [ {id, status, terminal_qualifier, terminal_detail, treatment_text, dose_text, schedule_text, start_date, stop_date, planned_date, previous_course_id, provenance, history}, ... ],
  "treatment_discrepancies": [ {id, status, category, comparison_text, citation_kind, source_fact_ref, comparison_source_fact_ref, course_id, source_fact_snapshot, comparison_source_fact_snapshot, course_snapshot, confirmations, caregiver_action_id, provenance, history}, ... ],
  "documents":   [ {date, type, summary, key_findings, source_document_id, raw_text}, ... ],
  "source_documents": [ {id, ingested_at, source: {path, sha256, length}, text: {...}}, ... ],
  "document_imports": [ {job_id, source_document_id, status, receipt_revision, changes: [...]}, ... ],
  "trials_tracked": [ {research_record_id, nct_id, title, status, ...}, ... ],
  "literature_watched": [ {research_record_id, pmid, title, journal, date}, ... ],
  "research_considerations": [ {id, item_type, research_record_id, source_key, status, snapshot, events, caregiver_action_id, history}, ... ],
  "alerts":      [ {id, priority, action, resolved, resolution, source_document_id, source_dependency_active}, ... ],
  "clinical_judgments": [ {category, text, source: "manual|ai|feedback", scope, status, review_after, valid_until, supersedes}, ... ],
  "questions":   [ {id, text, category, priority, asked, generation_job_id, stale}, ... ],
  "feedback":    [ {target, item_id, assessment, note, outcome, timestamps}, ... ],
  "caregiver_actions": [ {id, origin_snapshot, text, owner, due_date, status, outcome, history}, ... ],
  "visits":      [ {id, status, question_snapshots, decisions, follow_up_ids, history}, ... ],
  "exec_summary": {
    "generation_id": "summary-job-abc123",
    "summary_revision": 42,
    "stale": false,
    ...
  },
  "latest_research_update": {
    "job_id": "abc123", "trigger": "digest", "completed_at": "...",
    "trial_ids": ["NCT..."], "paper_ids": ["PMID..."]
  }
}
```

`schema_version` tracks the profile schema revision. Deterministic, idempotent
migrations run automatically on load (see `agent/migrations.py`), upgrading
legacy profiles to the current version and logging each step in `_migration_log`.
If a corrupt profile is detected, the app automatically recovers the newest valid
pre-save snapshot or daily backup before applying migrations.

Every clinical-content save advances `profile_revision`; generated artifacts
remain bound to that clinical/effective revision. Schema v8 adds
`workflow_revision`, which advances for every durable follow-through mutation.
Owner, due-date, ordering, pinning, and administrative status changes advance
only the workflow revision. Caregiver-captured clinician answers, decisions,
clinical outcomes, and alert resolution advance both revisions and stale
dependent generated context. Caregiver-entered symptom episode create/edit/
resolve mutations also advance both revisions; pure existing-action link/unlink
is workflow-only. Research shortlist, event, lifecycle, and follow-up mutations
are always workflow-only, including caregiver-entered clinician/site-attributed
unverified notes.
Schema v3 also carries generation identity for AI questions. Legacy generated
questions without that identity migrate to explicit stale history rather than
appearing current.
Schema v4 deterministically backfills stable IDs for legacy alerts so resolution
uses ID + semantic token + profile revision instead of list position.
Schema v5 adds explicit alert dependency lifecycles and treatment-classification
revision/job identity. Legacy classifications become stale and fall back to raw
`current_treatments`; alerts migrate to durable/source/profile-snapshot rules.
Schema v6 backfills stable raw treatment component/source IDs. Classified rows
map explicitly to those components so ID/token/revision CAS edits preserve
unaffected parts of composite entries.
Schema v7 sanitizes source-less legacy generated alerts and binds them to the
profile snapshot that was current at migration; only recognized ingestion and
trial-status producers remain durable. Treatment certification also rejects any
unidentified residual therapy content before editable mappings become current.
Schema v8 adds durable caregiver actions and visit working records, deterministic
generated-action snapshot IDs, structured alert outcomes, target-level semantic
CAS, endpoint/operation/target-scoped idempotent mutation audit with immutable
response snapshots, and the independent workflow revision.
Schema v9 deterministically backfills missing biomarker IDs from the strongest
available source/span and canonical row authority, preserves duplicate
occurrences, and adds explicit observation/source-document date precision plus
optional specimen, assay, method, and stored-flag authority. Legacy dates remain
`clinical_unspecified`; migration never invents collection/result context.
Schema v10 provides the equivalent preservation-first authority for imaging:
missing IDs are derived from source/span and full-row authority without collapsing
duplicates, existing IDs and unknown fields remain untouched, and legacy dates are
explicitly `legacy_unknown` because older intake could substitute ingestion day.
New imaging reports use only an explicitly extracted study date; dates on notes
or other document types are not promoted to imaging dates. Missing dates remain
visible `unknown`, explicit source-document dates stay separate, and modality
wording is retained only when it occurs verbatim in source text—never by category
normalization.
Schema v11 keeps imported/legacy symptom observations separate from explicit
caregiver-maintained symptom episodes and adds the bounded episode projection
and replay-safe lifecycle/action-link mutations.
Schema v12 adds a separate treatment reconciliation authority. Migration only
initializes empty `treatment_courses[]` and `treatment_discrepancies[]`; it does
not promote, normalize, merge, deduplicate, reorder, or relabel legacy raw,
component, classified, receipt, source, evidence, or history facts. Courses use
explicit caregiver-maintained current/past/planned workflow state and
precision-preserving dates. Every new discrepancy is an explicit
`source_vs_source` or `source_vs_course` neutral comparison with immutable
snapshots of both cited sides. Existing complete source/course records remain
valid without rewriting; an older one-sided record remains visible as bounded
`legacy_incomplete` authority and cannot be resolved, reopened, or recurred.
Generated classification and legacy raw/component rows remain compatibility
data, not citable source occurrences. The fixed projection copy is: `NET/Care records what you enter but does not verify treatment details or advise starting, stopping, or changing treatment. Confirm treatment decisions with the treating team.` The new state remains excluded from model prompts, and the
shared Today/Patient treatment workspace uses this projection as its sole SPA
authority; `/api/status` treatment fields remain backend compatibility only.
Schema v13 adds explicit terminal authority for past caregiver courses. New past
creation requires `ended`, `not_started`, `cancelled`, or `other`; `other`
requires bounded exact caregiver detail, while every other qualifier rejects
detail. Current and planned courses have neither field. Existing past courses
without this authority migrate mechanically to `legacy_unspecified`, without
changing any status, date, text, history, replay snapshot, source, discrepancy,
order, ID, or unknown field. The projection publishes exact allowed transitions
and a server-derived restart eligibility/reason. Restart remains available only
when private server history proves the terminal course was previously current;
planned-never-started, cancelled, and direct past records are ineligible.
Schema v14 assigns stable exact-occurrence identity to tracked research rows
without collapsing duplicates or changing external NCT/PMID authority. Schema
v15 backfills `profile_revision=0` only when that top-level key is truly absent;
an existing null, invalid, boolean, negative, or integer value is retained
verbatim so bounded projections continue to fail closed when revision authority
is invalid. Clinical judgment source `feedback` is preserved as the historical
tag written by the legacy feedback flow; it is provenance, not a verification
claim.

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
Profile-dependent feed/digest/deep-sweep reports and chat/question/summary
results carry a PHI-free profile revision or generation identity. After the
record changes, authenticated job detail retains only an explicit outdated/audit
state and withholds the prior clinical content.

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
│   ├── research_disposition.py # stable research identity + bounded shortlist API authority
│   ├── io.py             # atomic_write_text helper
│   ├── backups.py        # daily snapshot + 30-day retention
│   ├── logging_config.py # text/JSON log formatter
│   ├── job_runtime.py    # bounded executors, safe artifacts + PDF subprocess
│   ├── pdf_extract_helper.py # child-only pdfplumber entry point
│   ├── judgments.py      # clinical-judgment context formatter
│   ├── intake.py         # extract structured medical data from text
│   ├── biomarker_series.py # bounded provenance-safe longitudinal read projection
│   ├── imaging_series.py # complete non-inferential imaging authority projection
│   ├── symptom_episodes.py # bounded observation + caregiver episode authority
│   ├── treatment_reconciliation.py # bounded source/course/discrepancy authority
│   ├── evidence.py       # validated claim-level source-span catalog/resolution
│   ├── reconciliation.py # per-document receipts + compare-and-swap correction/undo
│   ├── follow_through.py # durable actions/visits, validation, CAS + audit helpers
│   ├── orchestrator.py   # agentic loop driving the tools
│   ├── verify.py         # deterministic PMID/NCT existence verifier (report backstop)
│   ├── trials_poll.py    # deterministic tracked-trial status poller
│   ├── deep_sweep.py     # on-demand ensemble deep-sweep (multi-model, read-only)
│   ├── classify.py       # treatment dedup + active/planned/completed
│   ├── exec_summary.py   # JSON executive summary generator
│   ├── questions.py      # Appointment questions (language via patient.language)
│   ├── chat.py           # /api/chat handler (pure function)
│   ├── cli.py            # `python net_agent.py {feed|digest|status|resolve-alert|update-profile}`
│   └── tools/            # PubMed, ClinicalTrials.gov, biomarker trends + dispatcher
├── static/                 # Responsive caregiver workspace
│   ├── index.html          # Shared shell + symptom/document/chat/appointment dialogs
│   ├── app.js              # API authority, symptom/imaging/biomarker workflows, jobs, chat
│   └── styles.css          # Responsive workflows, dialogs, tables, and phone navigation
├── startup.sh            # gunicorn launcher (Azure App Service)
├── pyproject.toml        # Python deps + tooling config
├── .env.example          # Template for local secrets
├── tests/                # pytest suite (no network or API key needed)
│   ├── test_imaging_timeline_ui.py # actual-function Node + live responsive browser coverage
│   ├── test_symptom_workflow_ui.py # symptom authority + live lifecycle/responsive coverage
│   ├── test_symptom_episodes.py # backend identity/lifecycle/replay/projection contract
│   └── test_treatment_reconciliation.py # treatment authority/lifecycle/replay contract
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
    W->>J: save profile + job-scoped reconciliation receipt
    U->>API: GET /api/jobs/<id>/receipt
    API-->>U: exact additions/changes/conflicts + source spans
    W->>O: run_orchestrator(profile, extracted)
    loop until end_turn or 12 iterations
        O->>T: tool_use (search_pubmed, ...)
        T-->>O: results (filtered by NET relevance)
        O->>J: persist new papers/trials/alerts
    end
    W->>J: record exact net-new trial/paper IDs for this discovery batch
    O-->>W: report artifact (not embedded in job metadata)
    W->>E: generate_executive_summary
    E-->>W: JSON summary
    W->>J: save_profile
    U->>API: GET /api/jobs/<id> → report/result on demand
    U->>API: GET /api/summary → JSON
```

Feed, digest, deep-sweep, chat, question generation, and manual summary
generation are asynchronous. The SPA polls every 1.5 seconds when awaiting a
specific result and every 3 seconds while work is active. It backs off to
30 seconds when idle and 60 seconds while the page is hidden. Queue
saturation returns `429 Retry-After` before a job is persisted; duplicate
active digest/deep-sweep/summary runs return `409`. A process restart cannot
resume in-process work: queued/running records become `interrupted` and the
caregiver must re-submit. Graceful shutdown is bounded, not a durability
guarantee.

`GET /api/patient/biomarker-series` is the authenticated, no-store, complete
longitudinal contract behind the **Patient → Biomarkers** explorer. The
authoritative table retains every bounded observation, raw display value,
observed alias, same-source duplicate, provenance identity, and neutral
non-comparability reason. Secondary point charts are partitioned by the exact
server-declared comparable series and never connect points, convert units, or
infer a trend. The response carries both revisions plus opaque authority tokens;
offline ambiguity keeps the last accepted snapshot visibly stale and read-only,
while authorization or hard invalidation scrubs it. `/api/status` remains the
recent-summary compatibility payload and is not used by the explorer.

`GET /api/patient/imaging-series` is the sole longitudinal authority behind the
shared **Patient → Imaging** timeline and explicit comparison workflow. It returns every bounded imaging
row as a distinct record with both revisions and opaque row/projection tokens;
exact duplicates are never collapsed. Tokens bind the full stored row, source
integrity, exact evidence, document exclusion, receipt lifecycle, and revisions
without returning source IDs, paths, offsets, quotes, or receipt internals.
partial, unknown, legacy, manual, and unverified facts remain visible. Stable
derived route references keep even reserved-character legacy IDs out of URL
segments. Malformed,
oversized, duplicate-ID, or inconsistent authority fails the complete projection
with bounded `422`. Opaque row-ID source/evidence routes resolve the source and
span server-side. The contract neither exposes the lossy legacy `new_lesions`
boolean nor computes progression, response, lesion identity, size change,
comparability, trends, or clinical meaning. The browser validates and accepts the
complete response atomically, preserves server order and exact report wording,
and requires the caregiver to select exactly two current records and confirm the
pair before showing raw facts side by side. It never uses `/api/status` or the
legacy `/api/patient/evidence` imaging array as fallback authority.

`GET /api/patient/symptom-episodes` is the sole symptom read authority behind
the shared **Today → Current symptom episodes** summary and complete
**Patient → Symptoms** workflow. Schema v11 keeps
legacy `symptoms[]` observations separate and read-only in this contract; it
never promotes a note/document mention into a current episode or assigns the
document date as symptom onset. Every duplicate and unknown field remains in
the stored observation authority. Caregiver-maintained `symptom_episodes[]`
support explicit current/resolved lifecycle, neutral mild/moderate/severe
caregiver-entered severity plus exact detail, precision-preserving dates,
unverified provenance, replay/CAS-safe mutations, and optional durable
`caregiver_actions[]` linkage. Creation can atomically link one exact eligible
action or create and link one bounded manual action in the same save. The
existing-episode follow-up endpoint also supports mutually exclusive exact
link, exact unlink, or bounded manual-action create-and-link variants; these
link-only workflow changes do not advance the clinical profile revision. Fixed
safety copy states that NET/Care neither assesses urgency nor monitors
symptoms. Episodes are excluded from all model prompts; legacy symptom context
remains unchanged. The browser validates and atomically accepts the complete
projection, preserves every server-ordered row, and never falls back to
`/api/status` or the retired SPA `/api/symptoms` flow. Add, edit, resolve,
existing-action link, manual create-and-link, and unlink use one responsive
dialog model with exact token/revision authority, byte-identical explicit
replay, conflict reload, endpoint-specific stale retention, and PHI-safe hard
clearing.

The orchestrator's behaviour is shaped by **clinical_judgments** captured from
oncologist consultations. These act as hard constraints: anything the oncologist
has already addressed is excluded from the recommended actions.

## Operating manual

Day-to-day caregiver workflow lives in [`docs/operating_manual.md`](docs/operating_manual.md).
The most common loops:

| Action | Where | What happens |
|---|---|---|
| Review current priorities | **Today** | Shows assessment freshness, the key concern, and task-oriented next actions before supporting detail |
| Recover an expired sign-in | Any view → **Sign-in required** banner | Browser-held patient data is cleared, but stored patient records are not deleted. Reload to complete Easy Auth sign-in, then press **Retry** if the page remains open; current projections repopulate only after authenticated revision checks succeed |
| Track durable caregiver follow-through | **Today** → **Follow-through** | Create safe caregiver tasks, accept only current generated actions, filter active/completed/cancelled history, edit owner/due date, and record typed completion or cancellation outcomes with explicit provenance; offline snapshots stay visible but read-only, and one mutation owns all related controls until authoritative reload finishes |
| Record or review symptom episodes | **Today** → **Current symptom episodes** or **Patient** → **Symptoms** | Record durable caregiver-entered current episodes; Patient adds explicit fact editing, resolution, resolved review, read-only source observations, and atomic existing/manual follow-up linkage. The exact safety statement remains visible and the app makes no urgency, diagnosis, treatment, chronology, or monitoring inference |
| Reconcile treatment records | **Today** → **Treatment records** or **Patient** → **Treatments** | Today shows only the first three current/planned caregiver records in server order with exact totals and omissions. Patient keeps caregiver courses, differences, document mentions, mapped generated context, and pre-v6 generated context with unavailable source linkage separate; every unlinked row is shown in server order with an exact total and no citation, mutation, lifecycle, or source controls |
| See newly discovered research | **Today** → **Research** | Shows the first three exact latest-batch occurrences in server order with exact totals and omissions. `New research` is passive server membership, never unread/review state |
| Maintain the research shortlist | **Research** → **Current research** / **Considerations** | Review every occurrence and duplicate in server order; keep external facts, machine-generated compatibility context, discovery provenance, immutable snapshots, and current state separate; explicitly save one exact occurrence, record attributed unverified events, close/resume caregiver consideration, and atomically link/create/unlink one follow-up using only current server eligibility |
| Add a clinical document | Header → **Add document** → paste text or upload file | Queued on the independent feed executor; PDF parsing is child-only, then intake → orchestrator → exec summary. Authorization loss aborts the browser submission, clears selected bytes and dialog state, and rejects late activation |
| Reconcile or correct an import | **Activity** → select that feed job | Shows only that document's additions, old → new changes, conflicts, and evidence; correct/remove a value or safely undo the document's direct structured changes |
| Review complete biomarker history | **Patient** → **Biomarkers** | Select an analyte, review every raw observation and source/evidence identity in the authoritative table, and use isolated point charts only where the server declares an exact comparable group |
| Review or compare imaging reports | **Patient** → **Imaging** | Review every authoritative record in server order, including duplicates and uncertain dates; select exactly two current records and confirm the pair to see attributed raw report facts side by side without an app-authored clinical conclusion |
| Review document/source history | **Patient** → **Documents and sources** | Opens immutable source text and retained import receipts without exposing storage paths |
| Run a research-only sweep | **Activity** → **Run digest** | Orchestrator runs without new input; new trials/papers added |
| Record an oncologist's judgment | **Questions** → **Clinical notes** | Becomes a hard constraint for future runs |
| Resolve an alert with its outcome | **Patient** → **Active alerts** → **Resolve alert** | Review the current alert, optionally record an administrative, caregiver-reported, or clinician-attributed unverified outcome, and either create/link a caregiver follow-up or link a current visit and eligible decision; stable ID/token/revision checks, one intent owner, exact ambiguous retry, conflict reload, and stale read-only offline projections prevent the wrong alert or link from being saved |
| Generate appointment questions | **Questions** → **Generate questions** | Async result is polled, then the question list is rendered |
| Prepare, run, and recap an appointment | **Questions** → **Appointment workspace** | Create or link a visit, order current generated/manual question snapshots, capture answered/unknown clinician-attributed responses, manage immutable decision lifecycles, and create visit-linked follow-ups. The fourth **Recap** tab atomically projects exact provenance-labelled wording and related resolved-alert outcomes for an in-progress/completed visit. Each export click first performs one authenticated exact-authority preflight; changed authority requires review and another click. Going offline revokes export until reload, changing visits scrubs the prior recap before rendering, and planned/cancelled visits expose no export controls |
| Chat with the record | Header → **✦ Ask Claude** | Async result grounded in the full profile; chat remains stateless |

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
