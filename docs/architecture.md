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
                │     ├─ /api/patient/          │
                │     │  biomarker-series       │
                │     │  imaging-series         │
                │     │  symptom-episodes       │
                │     │  treatment-reconciliation│
                │     │  research-workspace     │
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
traversal-safe roots. Each job has a bounded PHI-free artifact contract:
`kind=report|result|none`, durable state
`available|expired|not_retained|unavailable|none|legacy_unknown`, and derived
freshness `current|stale|unknown`. Age/count pruning persists the reason before
clearing an indexed reference and deleting the file. A missing or unreadable
indexed file is `unavailable`, never mislabeled expired. Legacy jobs without a
durable state remain `legacy_unknown` rather than being rewritten. Public job
responses strip report/result paths and the internal storage marker. New job
errors and job-runner logs use safe codes/types rather than input, model output,
or traceback. Protected lower-level storage/recovery logs may include OS paths.
The Activity detail renderer keys stale content by selected job, stale reason,
and public artifact kind/state/freshness. Unchanged polls do not replace its
modal DOM, so focused actions and alert nodes remain stable. Stale result copy
claims retained/hidden content only for `artifact.state=available`; every other
state says the prior content is not available and keeps its precise state card.

Every successful intake commit also appends one `document_imports[]` audit record
to the profile before orchestration begins. `GET /api/jobs/<id>/receipt` exposes
that feed-job-only receipt while the job remains retained; it shows additions,
old-to-new scalar updates, conflicts/no-ops, and exact evidence state without
putting PHI in the job list. If orchestration or summary generation later fails,
the already-committed receipt remains available with the intake data.

`GET /api/status` keeps its date-sorted five-document compatibility list and
separately projects `latest_document_import` from the complete active document
set by `added_at`. Today uses only that dedicated ingestion-time field for its
Latest document import row, so a newly imported backdated document cannot be
mislabelled or hidden by the compatibility truncation.

`GET /api/patient/biomarker-series` is a separate authenticated/no-store,
read-only projection over all bounded `biomarkers[]`; `/api/status` remains a
50-row recent-summary compatibility response. The projection returns both
revisions and opaque row/observation/series/analyte/projection tokens. Its
private authority envelope binds every persisted row independently, verified
evidence/source-artifact integrity, document exclusion, import/receipt/change
state, and both revisions without returning paths, raw quotes/text, offsets,
history, or job internals.

Analyte grouping and comparability are deliberately separate. Only a tiny
boundary-exact alias allowlist groups CgA/Chromogranin A,
NSE/neuron-specific enolase, and 5-HIAA/5-hydroxyindoleacetic acid. Comparison
requires an explicit identical unit, exact collection/result day, specimen,
assay or method, and parsed reference-range semantics; missing context never
becomes comparable and no unit conversion occurs. Qualified, ranged, and
nonnumeric values remain exact table-ready observations but never receive
numeric comparison. Same-source exact semantic duplicates may collapse only in
the read projection while retaining every row ID, evidence link, duplicate
count, and token authority; rows from different sources never collapse.

Malformed structure, duplicate/missing IDs, unsafe nested/non-finite values,
overflow, or inconsistent verified source authority fail the complete endpoint
with a bounded path-free `422`. Bounded incomplete facts remain visible as
explicitly unclassified/non-comparable rows rather than being silently omitted.
The projection never saves, audits, advances revisions, persists state, or calls
a network/model service, and it is not injected into any LLM context.

`GET /api/patient/imaging-series` is a separate authenticated/no-store
projection over every bounded `imaging[]` row and the sole longitudinal
authority for the shared Patient imaging timeline/comparison UI. Schema v10 preserves
all existing IDs, rows, duplicates, order, wording, evidence, and unknown fields;
it derives only missing IDs from the strongest source/span/full-row authority and
marks pre-v10 dates `legacy_unknown` without rewriting them. New imaging-report
intake no longer substitutes ingestion day when the study date is absent; dates
on other document types are not promoted to study dates, explicit
source-document dates remain separate, and modality wording is copied exactly
only when present verbatim in source text, without category normalization.

The projection returns each persisted row independently—there is no persistent or
presentation collapse—and carries both revisions plus opaque row/projection
tokens. A private authority envelope binds the complete row (including omitted
legacy/extra fields), validated extracted-text source, exact evidence span,
document exclusion, every matching import/receipt/change lifecycle, and both
revisions. Each referenced extracted-text artifact is validated once through a
source cache. Valid partial/unknown/manual/unverified facts remain visible;
missing/duplicate IDs, malformed/non-finite nested authority, source tampering,
receipt inconsistency, and bounded overflow fail the complete response with a
path-free `422`.

The public allowlist contains exact stored date/modality/findings/impression,
explicit date authority, provenance labels, and opaque derived-record URLs only. It
returns no source ID, path, offset, quote, receipt internals, `new_lesions`, or
unknown nested extras. Source/evidence routes map a stable URL-safe reference
back to the preserved row ID, resolve current source/span authority server-side,
and return validated plain text with no client-provided
path or offsets. The projector never saves, audits, advances revisions,
quarantines, calls a model/network service, or enters LLM context. It performs no
lesion matching, measurement parsing/conversion, comparison, change/response
label, trend, treatment-suitability, or clinical interpretation. The current SPA
validates the entire mechanical response and exact opaque link shapes before
atomically accepting it, preserves response order, and keeps authority tokens
only in owned JavaScript state. It does not use `/api/status` or the
`/api/patient/evidence` imaging compatibility array.

The timeline presents every record independently. Exactly two current record
IDs plus an explicit caregiver confirmation are required before the SPA repeats
their raw facts side by side; report-authored comparison language remains
attributed text, never an app judgment. Imaging-specific request,
selection/comparison, PHI, and revision ownership reject late work. Either
revision advancing makes the projection stale/read-only immediately. Only an
ambiguous imaging transport may retain the last accepted snapshot; auth evicts
all client PHI, while malformed or hard imaging responses scrub only imaging
state, hidden DOM, focus, and pending ownership. The table owns any horizontal
overflow and the comparison stacks at phone width.

`GET /api/patient/symptom-episodes` is a separate authenticated/no-store
projection over legacy source observations in `symptoms[]` and
caregiver-maintained lifecycle records in `symptom_episodes[]`. Schema v11
preserves every legacy row, ID, duplicate, exact wording, position, provenance,
and unknown extra field. Missing IDs are deterministic from strongest
source/span/provenance/full-row authority; indistinguishable duplicates receive
a deterministic occurrence multiset without an individual-identity claim.
Migration never promotes an observation into an episode. Pre-v11 observation
dates are `legacy_unknown`; future imported observations remain clinically
undated unless row-level event-date authority is added in a later extraction
contract. The document date is stored separately as source-document authority.

Episodes are explicit caregiver-entered, unverified records with stable server
IDs, current/resolved status, exact symptom wording, an optional neutral
mild/moderate/severe selection plus exact detail, explicit reported subject,
timing/frequency/triggers/notes, and precision-preserving onset/resolution dates.
Create is always current; resolve is the only current-to-resolved transition.
There is no delete, reopen, elapsed-time resolution, or lifecycle cascade to a
linked action; recurrence creates another episode. System audit timestamps are
never clinical dates. Fixed copy always says NET/Care records entries but does
not decide how urgent symptoms are or monitor them, directs concerns to the
treating team, and directs a perceived medical emergency to local emergency
services.

The projection returns every bounded observation and episode plus both
revisions, opaque row/episode/projection tokens, and a minimal list of eligible
open/in-progress caregiver actions. Private tokens bind complete persisted rows,
episode history/lifecycle/link state, full relevant source/document/import/
receipt authority, action authority, and both revisions. Each unique claimed
artifact is integrity-validated once. Public rows contain no source/import IDs,
paths, quotes, offsets, receipt/history data, or unknown extras; source/evidence
routes use derived URL-safe references. Missing/manual/unverified facts remain
visible, while duplicate identity, inconsistent lifecycle/link/source/receipt
authority, malformed or non-finite nested data, and overflow fail the whole read
with bounded `422` and no save, quarantine, audit, model, or network call.

Episode create/edit/resolve mutations require a mutation ID, exact projection
and target authority, and both expected revisions under
`serialized_mutation`. They append episode audit, advance both revisions, and
save once. `PATCH /api/symptom-episodes/<episode_id>/follow-up` has three
mutually exclusive variants: link one exact eligible existing action, unlink
the exact linked action, or create and link one bounded manual action. All three
are workflow-only and preserve the episode's clinical revision and content.
Episode creation separately supports mutually exclusive existing-action or
inline manual-action linkage. Every inline variant validates complete authority
and bounds before generating the action, creates both action and episode audit,
and commits one save; conflict or save failure leaves neither action nor link.
Exact replay returns the immutable original episode/action response. Existing
visit/decision/alert action provenance is untouched, duplicate episode linkage
is rejected, and neither lifecycle cascades. The legacy `/api/symptoms` and
`/api/status` payloads remain backend compatibility surfaces, but the SPA makes
no symptom requests to them; only `symptoms[]` enters model prompts.

`GET /api/patient/treatment-reconciliation` is the complete bounded backend
contract for five deliberately separate authorities: every treatment receipt
occurrence, the legacy raw/component/mapped-classification compatibility view,
pre-v6 generated compatibility rows whose source linkage is unavailable,
caregiver-maintained treatment courses, and caregiver-created discrepancies.
Schema v12 migration adds only empty `treatment_courses[]` and
`treatment_discrepancies[]`; it never promotes or rewrites existing treatment,
component, classification, source, receipt, evidence, duplicate, order, or
unknown-field authority.
Each projected source occurrence is paired with a sibling `source_fact_documents[]`
entry keyed by the same opaque `ref`, carrying only the originating receipt's
`filename`, `document_type`, and `document_date`. It answers "which document, and
when" for a mention. It is deliberately a sibling rather than extra fields on the
source fact, because `_validate_source_fact_snapshot` compares the citation
snapshot field set by exact equality — widening `_SOURCE_FACT_PUBLIC_FIELDS` would
invalidate every stored discrepancy snapshot and fail the whole read closed with
`422`. The pairing is the receipt-to-change parent relationship already present in
the projection, so it involves no matching, correlation, or inference, and it
creates no link between a mention and any caregiver course.
Schema v13 adds one mechanical migration: a pre-extension past course lacking
terminal authority receives `terminal_qualifier=legacy_unspecified`. It changes
no status, date, text, ID, order, discrepancy, source/generated/receipt/action
record, history, replay snapshot, or unknown extra. Current/planned courses
receive no terminal authority, and rerunning migration is a no-op.

Courses store exact caregiver text and explicit current/past/planned workflow
state. Dates preserve only explicitly entered year, year-and-month, or full-date
precision, whether typed in Finnish or ISO. New past creation requires exact
`ended`, `not_started`, `cancelled`,
or `other` authority. `other` requires nonempty bounded exact caregiver detail;
other qualifiers reject detail. Current/planned courses have no terminal
authority. Current may transition to past only as `ended|other`; planned may
transition to current or past as `not_started|cancelled|other`. Past is
terminal. The projection returns exact allowed next transitions and qualifier
values plus a bounded server-owned restart eligibility/reason. Restart creates
a new explicitly populated current/planned course linked by
`previous_course_id`, never reopening the old record, only when private history
proves the terminal course was previously current. Planned-never-started,
cancelled, direct legacy past, and direct new past courses are ineligible unless
the preserved legacy history itself proves prior-current authority. No source
fact, date, action, visit, decision, clock, or model changes lifecycle or fills
terminal authority.

Discrepancies are created only by a caregiver request against one opaque source
fact plus exactly one mechanically distinct second authority: another distinct
opaque source occurrence or one exact caregiver course. The public
`citation_kind` is explicitly `source_vs_source` or `source_vs_course`; neutral
source A/B names carry no chronology, preference, correctness, or clinical
meaning. Generated classification and legacy raw/component rows are never
citable. Well-formed pre-v6 rows with exact string `text`, nullable stored
`label`, `category`, and `date`, and no source IDs resolving to a live component
are copied only into
`unlinked_generated_context[]`, with an exact count, deterministic
occurrence-aware ID/token, complete allowlisted row plus revision binding, and
the exact label `Machine-generated compatibility context · source linkage unavailable · not a treatment record`.
They remain in stored order, including duplicates, and never receive inferred
component/source linkage, citations, controls, or currentness/relevance/
verification meaning. Neutral outcomes retain both immutable cited snapshots and the exact
note with the fixed label
`Caregiver-entered · attributed to clinician · unverified`. Only
`caregiver_record_corrected` may include an explicit course patch, atomically in
the same save. Resolution never erases facts or history; reopen is workflow-only
and recurrence creates a new linked discrepancy whose citation kind, references,
and snapshots are copied server-side from the resolved prior record. Clients
cannot substitute a recurrence citation. Older complete source/course records
remain lossless and valid without rewriting. Older one-sided records are
projected as `legacy_incomplete` with reason `missing_second_citation` and
explicit false resolve/reopen/recur eligibility; those operations fail closed
and never invent a second side.

All course/discrepancy mutations require both expected revisions, the complete
projection token, applicable row/source/action tokens, and a scoped mutation
ID. They run under `serialized_mutation`, append request-hash audit, capture a
safe replay response, and save once. Clinical course/discrepancy changes advance
both revisions; reopen and follow-up link/unlink/create-link advance workflow
only. Terminal fields, projected eligibility, and its private history inputs
bind course, discrepancy-current-side, and projection tokens; changing terminal
authority rotates current citation authority without rewriting immutable cited
snapshots. Pre-extension replay snapshots validate and return exactly as stored,
without a fabricated qualifier. An action can link to at most one symptom
episode or treatment discrepancy, and neither lifecycle cascades.

Opaque source/evidence routes resolve receipt/change identity server-side and
validate each referenced artifact once per projection. Public JSON contains no
path, source/import/job/receipt/change ID, quote, or offset. Corrupt,
inconsistent, duplicate-ID, tampered, or oversized authority fails the complete
read with a bounded `422`; incomplete/manual/unverified facts remain visible.

A course's `legacy_component_ids` must resolve against the live component set,
and component identity is re-derived per raw-row occurrence, so a receipt
correction, removal, or undo of an imported treatment value would strand the
link and fail that bounded `422` for the whole projection — an unrecoverable
state, because every treatment mutation needs tokens the projection no longer
issues. The receipt therefore refuses that mutation up front: it projects the
prospective rows in memory, and if any caregiver course would be left linking a
component the edit deletes or re-keys, it returns `409` naming the blocking
course before anything is written. That gate is a delta, not an absolute check:
it compares the live component set with the prospective one and blocks only on a
link that resolves now and would stop resolving. An advisory second check
re-validates the projection after the write and rolls the in-memory profile back
if a previously valid projection became invalid. Neither check weakens the
fail-closed read: authority that was already inconsistent still fails `422`, and
a link that already dangles never blocks a receipt edit — that is load-bearing,
because the in-app repair needs a projection that is already failing closed,
leaving the receipt as the only way back. Links are never dropped implicitly;
only explicit caregiver selection changes linkage.

Each discrepancy exposes immutable snapshots separately from both citations'
current lifecycle state. Discrepancy and projection tokens bind both sides'
complete private source/receipt/import/document/evidence/history authority,
course/action/discrepancy/outcome state, unknown extras, and both revisions, so
either side rotating invalidates current authority without rewriting snapshots.
The exact static safety copy is `NET/Care records what you enter. It does not check whether treatment details are correct or give advice about starting, stopping, or changing treatment. Confirm treatment decisions with the treating team.` It is nonconditional,
non-PHI, and non-prescriptive.
The projector is side-effect-free and the new course/discrepancy/confirmation
state does not enter chat, orchestrator, executive summary, questions, deep
sweep, or other model input.

The SPA treats this endpoint as the sole treatment authority. One accepted
projection, response owner, revision pair, loader, and mutation controller
render a bounded Today summary and the complete Patient workspace; no
`/api/status` treatment row can render, edit, transition, or remove a record.
Today shows current/planned caregiver courses when present; otherwise it shows a
bounded first set of recorded raw rows. A presentation-only linkage check compares
each raw row's component IDs with explicit `course.legacy_component_ids` and
labels the row as unlinked, partly linked, or linked to a caregiver-reviewed
status record. That label is descriptive only: an unlinked row is a legitimate
resting state and is never counted or worded as outstanding caregiver work,
because a recorded statement is wording the record already contains rather than a
task. Patient's default Overview orders
current/planned caregiver courses, every raw row exactly once — in the visible
list, or in the always-disclosed hidden set described below — then past courses.
Inside each of those three groups the SPA sorts newest-first for display only: a
course by the date its own status is about (`planned_date` when planned,
`start_date` when current, `stop_date` falling back to `start_date` when past),
and a raw row by descending `source_order`, the only recency signal a dateless
row carries. A partial date sorts at the start of the period it names, rows with
no usable date hold a fixed last position, and equal keys break on row ID, so the
order is total and identical on every render. No date is parsed from raw wording,
borrowed from a linked course, or taken from generated content. The server
projection order, `source_order`, and every row token are untouched, and nothing
is merged, deduplicated, or promoted. Today's bounded first set uses the
same order, so it shows the most recent entries. Differences and source-document
mentions remain separate. No
status is assigned to raw wording. Stored generated classification remains
compatibility context rather than a treatment fact — it is still projected but
no longer displayed — and a raw component becomes course authority only through
an explicit caregiver association.

### Caregiver workspace visibility for raw rows

`patient.current_treatments[]` accumulates every extracted treatment *statement*,
including stops and administration detail such as an infusion-rate note. Those
can be real clinical context and are never deleted, but the caregiver may decide
one does not belong on his own treatment page. `treatment_row_dispositions[]` is
that decision and nothing more.

Each entry is `{id, source_entry_id, hidden, created_at, updated_at, history[]}`.
It is keyed by `source_entry_id` — the position-independent per-occurrence
identity from `profile.raw_treatment_source_entry_id`, the same value
`sync_treatment_records` already stores on each component — and deliberately
**not** by the public projection row ID, which folds in `source_order` and
re-keys whenever an earlier row is removed. Keying on the public ID would move a
caregiver's choice onto a different statement.

The projection exposes a sibling `legacy_treatment_dispositions[]`, one entry per
raw row as `{row_id, hidden, token}`, plus `legacy_treatment_hidden_count`. This
mirrors the `source_fact_documents[]` pattern: a sibling keyed by the same
reference, bound by the projection token, so no existing snapshot field set
widens and no stored citation snapshot is invalidated. Rows themselves are
projected unchanged whether hidden or not.

`POST /api/treatment-reconciliation/legacy-rows/<row_id>/disposition` sets it,
under the same contract as every other treatment mutation: both expected
revisions, the projection token, a per-row `expected_disposition_token`, a scoped
`mutation_id` under `serialized_mutation`, one appended audit event, one save,
and exact-replay as a no-op. Setting the visibility a row already has is
rejected. It is workflow authority, so it advances `workflow_revision` only and
never invalidates generated clinical context.

Three properties are load-bearing and covered by
`tests/test_treatment_row_dispositions.py`:

- **Nothing is deleted.** The raw row, its components, its wording and its order
  are untouched; only rendering changes.
- **Nothing is hidden from the assistant.** A hidden row still reaches the chat
  prompt and `get_patient_summary` verbatim, so hiding never decides what
  NET/Care knows. The disposition itself never enters any model prompt.
- **Software never decides relevance.** No alias table, keyword list, or model
  judges which therapies matter; only an explicit caregiver mutation changes
  visibility. An unknown or orphaned key resolves to *visible*, so a stale
  disposition can never hide a row the caregiver did not choose to hide — if a
  row's wording is later corrected its key changes and the row reappears.

Because the key is content-addressed per occurrence, two rows holding
**byte-identical** wording are indistinguishable to it: if an earlier duplicate
is later removed, the survivor inherits the first occurrence's visibility, and a
hidden wording that is removed and re-extracted returns visible. Those rows are
also indistinguishable to the caregiver, and no row with *different* wording can
ever inherit another's state, so the failure is bounded to text the caregiver
cannot tell apart.

The UI collapses hidden rows behind a persistent `N hidden by you · show list`
disclosure inside the recorded section, states there that nothing was deleted and
that NET/Care still uses them, and offers **Show this again** on each. Today
reports the visible count and names the hidden count separately.

Before any treatment DOM replacement, the client validates the complete
projection, exact safety/authority bytes, top-level counts/lists, serialized
bounds, cross-collection IDs/tokens, raw shapes, source links,
terminal fields, published lifecycle/restart authority, both discrepancy
citations, outcomes, recurrence graph, and action ownership. It preserves
duplicates, raw strings, and null/empty/missing distinctions, changes only the
display sequence described above, and
keeps tokens, snapshots, refs, drafts, and serialized retry bytes only in owned
JavaScript memory. Strict literal same-origin opaque source/evidence routes are
the only rendered links.

All controls come from current published eligibility. A mutation uses one owner,
a fresh mutation ID, both revisions, projection/target/citation/action tokens,
and one canonical serialized body. A transport-ambiguous submission alone may
be retried with identical bytes. `409` destroys replay and server-derived
selection, preserves only safe caregiver draft fields, and reloads for explicit
review. A valid targeted response is provisional: both surfaces become
read-only until a complete replacement matches returned revisions and semantic
course/discrepancy/outcome/link state; legitimate token rotation is ignored for
that semantic comparison. Mismatch permits refresh only, never resubmission.
Mutation field `400/422` keeps the still-current projection and draft, while a
hard/malformed projection clears treatment PHI. Auth invokes central PHI
eviction. Endpoint-specific epochs and abort ownership reject late effects;
normal refresh does not steal focus, and desktop/phone use contained table
overflow, stacked citation panels, keyboard tabs, visible focus, and 44-pixel
controls.

For symptoms, one responsive client authority model renders current episodes on Today and
the complete current/resolved/source-observation workflow on Patient. It
validates the full projection, safety copy, lifecycle/link graph, tokens, and
strict same-origin opaque source/evidence routes before replacing any state or
DOM. Dedicated load/selection/dialog/mutation epochs and owned abort
controllers reject late or replaced effects. Either revision advancing marks
the retained projection stale/read-only and triggers an independent reload;
unchanged revision pairs do not refetch. Only ambiguous endpoint transport may
retain stale symptom PHI. Authorization invokes central PHI eviction, while
hard symptom failures scrub symptom rows, dialogs, drafts, serialized retry
bodies, focus, and hidden DOM without clearing unrelated Patient surfaces.
Create/edit/resolve/link/create-and-link/unlink use one mutation owner, exact
CAS authority, duplicate-submit suppression, byte-identical explicit replay,
and authoritative projection reload before completion.

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
chat, Today, visible Appointments, and Activity until regenerated.
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

The Today view exposes these records through one responsive Follow-ups
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

The visible Appointments view exposes those contracts through one responsive
appointment working mode rather than another top-level SPA view. The internal
SPA view key and route remain `questions`. `GET /api/visits` includes a
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
active. Copy/Download/Print share one duplicate-click owner. Each explicit export
performs exactly one authenticated, `no-store` recap preflight with the current
full visit token, then requires exact equality with the reviewed recap token,
request/patient/visit epochs, selected visit ID/token, both revisions, and
exportable lifecycle before the clipboard, Blob/link, or print side effect.
A changed valid projection replaces the visible review state but is never exported
by that click; export requires a second explicit action and unchanged preflight.
Conflict, stale/lower/revisionless authority, network ambiguity, and offline state
clear token/text/object-URL authority and retain at most a visibly stale read-only
recap. The browser `offline` event revokes synchronously; coming online cannot
restore export until authoritative recap reload succeeds. Authorization/hard
failure scrubs the recap DOM, structured cache, export text, object URL, focus
references, and late responses. Text download uses a generic UTF-8 `text/plain`
filename and print CSS excludes navigation, controls, dialogs, and stale content.
No recap polling or browser storage is used.

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

That fail-closed refusal is bounded to the deterministic identity library itself.
The LLM classification pass that once consumed it was retired: no job calls a
classifier, `treatments_classified[]` is never refreshed, and its
revision/job-id provenance stays frozen at whatever the profile already held.
Stored generated rows are retained verbatim and are still projected by
`GET /api/patient/treatment-reconciliation` as
`legacy_treatments[].generated_classification[]` and
`unlinked_generated_context[]`, where they continue to bind the legacy row and
projection CAS tokens — but they have no UI surface. The "Automatic
compatibility notes" tab was removed, so the workspace shows only caregiver
course authority, recorded raw treatment information, differences, and source
document mentions.

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
snapshot only when it adds research. `GET /api/status` retains compatibility
counts/identifiers, but the SPA does not use them for research display or
workflow state. The shared Today/Research UI uses only per-occurrence
`latest_batch_member` from `GET /api/patient/research-workspace`; no browser
NCT/PMID set, unread state, sort, or acknowledgement exists. The retired
`/api/changes` routes return an inert zero-count payload temporarily so cached
pre-release tabs stop showing the removed review control without writing state.

Schema v14 and `agent/research_disposition.py` add a separate caregiver workflow
authority without changing discovery. Every stored trial/paper occurrence has a
private stable ID; valid external source authority remains exact NCT/PMID, while
generated compatibility notes and discovery provenance are separate structures.
`GET /api/patient/research-workspace` projects every occurrence in profile order,
exact latest-batch membership, immutable allowlisted shortlist snapshots,
section-specific current equality, neutral open/closed history, attributed
caregiver events, eligible follow-ups, both revisions, and opaque full-authority
tokens. Canonical navigation is generated only from validated IDs. Malformed,
ambiguous, inconsistent, or oversized authority fails the whole bounded read
with a short non-PHI `422`.

Research mutation routes create one consideration per exact occurrence, append
events, explicitly close/resume it, and atomically link/create/unlink one existing
`caregiver_action`. Both revisions, the complete projection token, exact target
tokens, canonical request hash, and scoped mutation ID are mandatory. The
serialized transaction validates before allocation, appends audit, saves once,
and increments only `workflow_revision`; replay returns the original immutable
result. Shared action-owner checks cover visits, decisions, alerts, symptom
episodes, treatment discrepancies, and research considerations. Source refresh,
removal, same-external-ID replacement, import reconciliation, action lifecycle,
and latest-batch changes cannot rewrite or close a consideration.

The shortlist/disposition collection, internal occurrence IDs, event text, and
research-linked actions are excluded from all model inputs. Research-created
actions retain immutable origin and remain excluded after unlink; a generic
action is excluded only while linked. This preserves existing discovery queries,
ranking, summaries, and model-visible source research content.

The SPA accepts one atomically validated research projection for both surfaces.
Today renders bounded first sets with exact totals/omissions; Research renders
every occurrence and consideration in server order. External facts, generated
compatibility context, discovery provenance, immutable snapshots, current
section equality, events/history, and caregiver workflow occupy separate DOM
regions. Exact server eligibility alone creates controls. Opaque IDs/tokens,
selected authority, drafts, and retry bytes remain in owned JavaScript memory.
One GET controller and one mutation owner reject late/lower/wrong-owner effects.
Mutation success stays provisional and read-only until a complete replacement
matches returned revisions and expected semantic identities. Only ambiguous
submission retains byte-identical **Retry submission**; accepted submission can
retain only **Retry refresh**. Research transport ambiguity keeps the last
verified workspace stale/read-only, hard research corruption clears only this
surface, and authorization loss uses central full-PHI eviction.

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

### Two gates, not one

A hosted request passes **two independent gates** before any handler runs:

1. **App Service Easy Auth middleware**, outside the Python process. It
   authenticates the account and runs its own CSRF check. A state-changing
   request whose `Referer` is empty is rejected there with HTTP `403`,
   sub-status `60` (`Cross-site request forgery detected ... from referer ''`)
   and never reaches Flask. A `Referrer-Policy: no-referrer` response header
   therefore disables every mutation site-wide, which is exactly how the
   2026-08-13 outage presented. Responses now send `Referrer-Policy:
   same-origin`: the Referer is restored for this site's own requests and is
   still withheld from every other origin.
2. **Flask `_protect_api`**, registered as the first `before_request` handler so
   an unauthenticated, denied, or cross-origin request performs no job-history
   load, retention prune, or source prune. `_lazy_init` runs only afterwards.

### Typed principal decision

The trusted headers are parsed into two strictly separate namespaces.

**ID candidate.** The encoded principal selects identity by fixed claim-type
priority: canonical object-identifier URI, `oid`, canonical name-identifier URI,
then `sub`. The first populated tier must contain one unique nonempty value;
identical duplicates are harmless, while malformed, oversized, or conflicting
selected-tier claims are unauthenticated. `X-MS-CLIENT-PRINCIPAL-ID` is a
provider fallback only when no prioritized claim exists. Static Web Apps
`userId`/`userDetails` fields are a different product's schema and were removed.
IDs are compared exactly and case-sensitively.

**Name candidate.** `X-MS-CLIENT-PRINCIPAL-NAME`, compared with Unicode-safe
`casefold()` after trimming surrounding whitespace. Dots, plus tags, and domains
are never rewritten, so no address is ever treated as equivalent to another.

**Documented compatibility bridge.** This deployment's platform injects the
account's email into `X-MS-CLIENT-PRINCIPAL-ID` and does not guarantee that the
encoded blob or the name header reaches the worker. A bounded `local@domain`
shaped ID-header value is therefore *also* offered as a name candidate
(`provider_id_name_compat`). It is never normalised beyond `casefold()` and
never acquires stable-object-ID semantics. The name header wins when present; if
both sources are email-shaped and differ after `casefold()`, the name path fails
closed rather than widening access.

Base64 decoding accepts standard or URL-safe alphabets with missing padding,
re-padding safely and validating strictly. Mixed alphabets, impossible lengths,
corrupt data, oversized blobs, and excessive claim counts fail closed and never
downgrade to the convenience headers.

### Typed authorization and migration

`AUTH_ALLOWED_PRINCIPAL_IDS` matches only the ID candidate;
`AUTH_ALLOWED_PRINCIPAL_NAMES` matches only the name candidate. A request passes
when **either** configured allowlist matches its own typed candidate, so neither
namespace can authorize the other and an operator can move an entry between the
two settings without an atomic lockout. With **both** empty, behaviour is
unchanged from before: Easy Auth alone is the gate.

Hosted mode ignores local bypass. Local API use requires
explicit `ALLOW_LOCAL_AUTH_BYPASS=1`; state-changing hosted methods compare
`Origin` only with exact `APP_ORIGIN` or canonical HTTPS `WEBSITE_HOSTNAME`, as
defence in depth behind the platform CSRF check.

### PHI-free failure discriminators

Auth failures return fixed enums and never an identifier, claim value, email,
token, or payload:

| Field | Values |
|---|---|
| `reason` | `principal_absent`, `principal_malformed`, `principal_not_allowed`, `cross_origin`, `hosted_auth_unavailable` |
| `principal_source` (where meaningful) | `encoded_claim`, `provider_id_header`, `principal_name_header`, `provider_id_name_compat`, `absent` |

Authorization is evaluated before the origin check, so a denied account always
sees `principal_not_allowed` and an accepted account with a bad request address
always sees `cross_origin`. The browser uses that distinction: `cross_origin`
never evicts patient data and never suggests switching accounts, while
`principal_not_allowed`, `401`, and any unknown or legacy `403` remain
fail-closed evictions.

## Why this shape

| Decision | Why |
|---|---|
| JSON file, not Postgres | Single patient, single writer; auditable diffs; trivial backup. |
| Vanilla SPA, not React | Caregiver runs the UI on a phone occasionally — zero build pipeline beats lighter frameworks. The split SPA uses one responsive Today/Patient/Research/Appointments/Activity shell on every screen size. Today prioritizes freshness and the expanded assessment before stateless recent timestamps, patient-record status, follow-ups, appointments, and research. Internal `questions` routing is unchanged. `static/index.html` owns semantic markup and dialogs, `static/app.js` owns strict API authority plus a separate plain-language presentation layer, and `static/styles.css` provides the desktop rail, locally scrollable authority tables, overflow-safe dialogs, full-height phone sheets, and fixed phone navigation. |
| Flask + gunicorn, not FastAPI/Containers | App Service runs Python natively; no Docker needed; rapid `az webapp deploy` cycle. |
| No MSAL | Single user. App Service Easy Auth gates hosted APIs except health/liveness. Local API bypass is explicit (`ALLOW_LOCAL_AUTH_BYPASS=1`), never implicit. |
| Separate treatment reconciliation authority | Source observations and legacy model classification cannot safely establish longitudinal current/past/planned truth. Explicit caregiver courses and discrepancies preserve source history while stable tokens, replay/CAS, and one-save audit make later shared Patient/Today UI work possible without browser inference. |
| Per-agent model env vars | Lets us downgrade exec_summary or chat to Haiku independently for cost without touching code. |
| `prrt_status` says whether a course is running, not only whether one might suit | The screening vocabulary (`eligible…not_eligible`) had no value for treatment already under way, so the assessment could only reach for the strongest screening token and the chip read `PRRT: POTENTIAL FIT` directly above its own rationale describing a second Lu-177-octreotate series in progress. `course_in_progress` lets the assessment restate the recorded course instead. It is a fact the assessment reports, never a judgment that treatment should continue, and the prompt requires any concern about continuing to appear in `prrt_rationale`, `key_concern` and `next_actions` — so the value cannot mask a clinical disagreement, only a contradiction with itself. The browser renders whichever value the assessment produced and never reads `prrt_rationale` prose to choose, soften, or withhold the chip; that inference boundary is the one an earlier LLM classifier was retired for crossing. Stored assessments generated before this keep their old value until the next regeneration. |
| Today's import shortcut deep-links through stored intake identity | `build_import_record` stamps `feed_job_id` on the source document, so "Latest document import" → **Open Activity** resolves the exact job by lookup rather than by matching dates, filenames, or text. `/api/status` offers the identifier only while that job is still in the live store, because jobs are pruned by count and age while documents are kept; the browser still treats a job that vanished between render and click as an expected retention outcome — panel closed, plain note, focus returned — rather than the authorization eviction a directly clicked missing task triggers. |
| Separate imported appointments and workflow visits | Receipt-correctable source facts remain immutable evidence; caregiver working state can evolve without pretending generated questions or captured statements are source-verified. |
| Clinical + workflow revisions | Administrative follow-through does not invalidate expensive clinical artifacts, while new model-context facts still stale every dependent artifact safely. |
| Server biomarker projection, not browser inference | Complete row/source/import authority is available only at the profile boundary. The Patient explorer renders that projection as a complete table and charts only exact server-declared comparable groups as unconnected points. Dedicated request/selection epochs, AbortController ownership, monotonic revisions, and opaque response-token owners reject late or cross-analyte responses without duplicating clinical rules in JavaScript or reading truncated `/api/status` biomarkers. |
| Server imaging authority before comparison UI | Stable identity, explicit date uncertainty, source/receipt lifecycle, and complete failure semantics must exist before the browser can offer record selection. The first slice exposes exact stored rows only and defers every clinical comparison or visualization decision. |
| Explicit `fi-FI` display formatting, not the browser locale | The caregiver reads this record in Finland, so `14.8.2026`, `8/2026` and the 24-hour `09:26` are the only correct shapes. An implicit locale made the same stored value render differently per browser. `static/app.js` centralises this in `fmtDate` / `fmtTime` / `fmtDateTime` / `fmtNumber`; date-only values are formatted as text so a stored day never shifts across a timezone boundary, and timestamps are parsed through one shared `parseTimestamp` that reads a missing timezone as UTC because the server writes naive stamps on a UTC host. Interface copy, relative labels, and stored/API/prompt values remain untouched English and ISO. |

| Generated timeline dates are a date field, not prose | `timeline[].date` was specified as "YYYY-MM or approximate description", so the model wrote qualifiers and alternatives into it and `fmtDate`, which rewrites only an exact ISO value, passed them to the screen verbatim. The prompt now demands a bare calendar date at the precision the record supports; `agent/exec_summary.py` enforces it deterministically after generation, splitting a trailing qualifier into `event` and clearing a date it cannot verify with `schema.derive_date_precision`. Keys are unchanged. The renderer independently repairs the reading of assessments already stored, because nothing is regenerated to fix display. |
| Two possible months are never narrowed to one | An either/or such as `2026-08/09` is displayed as `8/2026 or 9/2026` and carries no `<time datetime>`, because there is no single instant to claim. A pair the app cannot resolve without assuming a year — `2026-12/01` — is refused and shown as unclear. Choosing a month would be the app inferring clinical timing, which it does nowhere. |
| Past/upcoming decided by comparing date text | A lexicographic `date < today` marked all of August past on 14 August and marked a qualified August past because a space sorts below a hyphen. A recorded date is compared at its own precision, so a month or year still containing today is neither past nor upcoming, and today is read with `localDateIso` rather than a UTC `toISOString`. |
| Horizontal timeline restored at the cost of accessibility | The removed SVG graph was keyboard-unreachable (hover-only tooltips), had a 400px floor that overflowed a phone, truncated labels to 19 characters, and used browser-locale English month names. It is rebuilt instead: a decorative `aria-hidden` axis carries proportional position, an `<ol>` of stops carries the text, month precision draws a band across the named month rather than a point on an invented day, and below the existing 720px breakpoint the axis is dropped and the stops stack. `tests/test_summary_timeline_ui.py` pins zero page overflow and keyboard reach at 1280/768/360. |

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
| Retired LLM treatment classifier leaves orphaned data or UI | Nothing refreshes `treatments_classified[]`, but stored rows and their revision/job-id provenance are retained verbatim, still projected as `generated_classification[]` / `unlinked_generated_context[]`, and still bind the legacy row and projection CAS tokens; only the presentation layer was removed, so no token rotates and no in-flight caregiver edit is invalidated |
| Treatment source correction invalidates a cited comparison | The discrepancy keeps both immutable cited snapshots while its token binds each current source/course side and full private lifecycle authority; correction/removal/undo on either side rotates tokens but never deletes or rewrites courses, discrepancies, confirmations, or links |
| Partial treatment workflow write or duplicate retry | Serialized full-authority validation, both revisions, scoped mutation ID, canonical request hash, append-only audit, one atomic save, and validated immutable replay response |
| Oncologist disagreement with AI | `clinical_judgments` injected verbatim into orchestrator + exec summary system prompts as hard constraints |
| Unsupported extraction evidence | Intake validates normalized model quotes against immutable source text, then stores the exact source span or explicit `missing`/`invalid` status |
| Biomarker aliases merge distinct tests | Boundary-exact allowlist only; grouping never grants comparability, and 5-HIAA specimen contexts remain separate. |
| Biomarker series implies unsupported chronology or conversion | Comparable membership requires exact collection/result day plus explicit compatible unit/specimen/assay-or-method/range semantics; unknown context is isolated and units are never converted. |
| Biomarker projection silently drops corrupt/oversized facts | Complete bounded projection or path-free `422`; valid incomplete scalar facts remain visible and explicitly non-comparable. |
| Biomarker provenance changes behind unchanged display text | Projection token binds every row, source/evidence artifact authority, document/import/receipt state, and both revisions, including presentation-collapsed duplicates. |
| Imaging timeline silently rewrites or infers history | Schema v10 preserves every row/duplicate/value and marks legacy date authority uncertain; new undated rows stay undated, and the all-row projection never collapses or derives clinical change. |
| Imaging source or receipt authority changes behind unchanged wording | Row/projection tokens bind the full hidden row, validated extracted source, exact evidence, document exclusion, receipt lifecycle, and both revisions; inconsistency fails the complete endpoint with bounded `422`. |
| Client constructs an imaging evidence span | Imaging source/evidence routes accept only an opaque stable derived record reference and resolve the preserved row plus current source/span server-side; no projection URL contains a raw legacy ID, source ID, path, quote, or offset. |
| Biomarker browser response races or lost authority | The explorer accepts only the current request/selection/PHI epochs, both monotonic revisions, and exact projection/analyte/series tokens. Network ambiguity retains a labelled read-only snapshot; online recovery reloads authority; auth/hard failure centrally scrubs state, DOM, focus, controllers, and late responses. |
| Stale import correction or undo | Target-level compare-and-swap fingerprints and later-claim checks return atomic `409`; no whole-profile snapshot is restored |
| Receipt edit strands a caregiver course link and darkens the treatment workspace | Correct/remove/undo of an imported treatment value projects the prospective rows first and returns `409` naming the blocking course when a `legacy_component_ids` entry that resolves today would be deleted or re-keyed, before any write; an advisory post-write projection check rolls the in-memory profile back on regression. Nothing is auto-unlinked, and the gate compares before against after, so a link that already dangles stays repairable through the receipt |
| Receipt removal deletes identical raw treatment rows another document contributed | Removal drops exactly one occurrence of the targeted value; occurrence-keyed component identity makes the surviving ID set independent of which physical duplicate is dropped |
| Incorrect import removed from active care context | Direct facts are reversed, the document is marked excluded from clinical prompts, and immutable source/audit history remains visible |
| Invented summary evidence link | Only server-built evidence catalog IDs resolve; unknown IDs are visibly `invalid` and absent IDs are `missing` |
| Stale generated conclusions after correction | Revision-aware summary hiding, question generation IDs, source-dependent alert invalidation, and hidden feed reports retain audit artifacts without presenting them as current |
| Wrong alert resolved after reorder | Stable alert IDs + semantic token + expected revision under the mutation lock; stale/missing targets return `409` |
| Accepted action disappears with an old summary | Server-side source ID/token acceptance snapshots the full generated row into durable `caregiver_actions[]` before the artifact can become stale |
| Administrative task edit stales clinical output | `workflow_revision` advances independently; only explicit clinical capture advances `profile_revision` |
| Caregiver note presented as verified clinician fact | Fixed provenance labels every answer/decision as caregiver-entered, clinician-attributed, and unverified; generated questions remain snapshots |
| Retry duplicates a decision or follow-up | Mutation ID + canonical request hash replay returns the prior target without another save or revision increment |
| Old chat contaminates corrected record | Client clears history on profile revision change; server rejects mismatched `history_revision` with `409` |
| Cached PHI after auth/load failure | Central client eviction clears every patient-bearing cache, panel, dialog, chat turn, receipt/report, filter, and open feedback surface; non-auth receipt refresh is the only fallback exception. Activity result links close/deactivate the report dialog before changing views and then focus the target heading/dialog. |
| Platform CSRF check rejects every mutation (`403.60`) | Responses send `Referrer-Policy: same-origin`, never `no-referrer`, so same-origin state-changing requests carry a `Referer` for the Easy Auth middleware while other origins still receive nothing. A runtime test pins the emitted header and a browser test asserts the wire `Referer`, with `no-referrer` as the failing control. |
| Platform identity shape changes and locks the caregiver out | ID and name candidates are parsed and allow-listed separately (`AUTH_ALLOWED_PRINCIPAL_IDS` / `AUTH_ALLOWED_PRINCIPAL_NAMES`), either one may authorize, and the documented email-shaped ID-header bridge keeps a blob-less, name-header-less platform working. Settings can be migrated one at a time with no lockout window. |
| Denied request performs storage work | `_protect_api` is the first `before_request` handler; job-history load, retention prune, and source prune run only after authorization succeeds. A test pins both the registration order and the absence of side effects. |
| Address-check failure misread as account denial | Auth failures carry fixed PHI-free `reason`/`principal_source` enums; the browser keeps patient data and offers a same-origin recovery for `cross_origin`, and still evicts on `principal_not_allowed`, `401`, or any unknown/legacy `403`. |
| Source traversal / browser caching | Auth-gated `/api/sources/<id>[/<artifact>]` and `/api/evidence/<id>` resolve only indexed paths below `DATA_DIR`, reject traversal, and return `no-store` |
| Stale clinical judgment | Only active, nonexpired, non-review-due judgments constrain agents; all others are visibly framed as needing clinician review |
| Storage account deletion | `AzureBackupProtectionLock` (CanNotDelete) on the resource group, auto-applied by Azure Backup |
| Azure Files share deletion / corruption | (a) Recovery Services Vault daily backup, 30-day retention; (b) file-share soft-delete, 14 days |
| Single-profile accidental overwrite | Cross-process serialized writes, rotating pre-save snapshots, daily Azure Files backup, and file-share soft delete |
| Plaintext HTTP request leakage | App Service `httpsOnly: true` (auto-redirect to HTTPS); storage min TLS 1.2 |
| Secret leakage / rotation pain | `ANTHROPIC_API_KEY` stored in Azure Key Vault (RBAC); webapp resolves it via system-assigned managed identity + `@Microsoft.KeyVault(SecretUri=…)` reference. Rotation = update vault secret + restart webapp |

## Retention and deployment

Completed job metadata and structured result artifacts default to 365 days/200
records. Report artifacts, indexed or unindexed, use the separate
30-day/200-file report settings;
unreferenced source directories use 7 days/20 directories (`JOB_RETENTION_*`,
`REPORT_RETENTION_*`, `SOURCE_ORPHAN_RETENTION_*`). Metadata/report pruning runs
at startup and job submission. Source pruning runs only at startup or after jobs
under the serialized profile mutation lock and protects every source ID still
indexed by the profile. It is best-effort, is not secure deletion, and does not purge
snapshots, backups, soft-delete/version history, or provider copies.
Reconciliation audit records are part of `patient_profile.json` and therefore
follow profile backup/recovery rather than report-artifact pruning. A retained
feed job can still expose its receipt after the narrative report expires; source
records referenced by the profile remain separately protected. The job-scoped
receipt endpoint is intentionally available only while its feed job metadata is
retained.

The complete production runtime dependency closure and setuptools build
requirement are exactly pinned from local metadata. Direct development
requirements are also exact. The archive includes `.deployment`, which declares
`SCM_DO_BUILD_DURING_DEPLOYMENT=true` for Kudu/Oryx builds.
`Scripts/deploy.ps1` requires a clean working tree plus pytest, ruff, and
gitleaks; builds and verifies a commit/SHA-256-addressed release; polls Kudu for
up to 900 seconds, then
`/api/health` critical fields and exact release commit for up to 300 seconds; and only then
promotes the release to `current-verified`, keeping the former current release
as `previous-known-good`.
Candidate deployment/readiness failure automatically redeploys and health-checks
the prevalidated current package when one exists, without promoting the candidate.
Rollback verifies the distinct previous package's SHA and embedded commit,
redeploys it, and repeats both readiness checks.

That release state is deliberately **not** stored in the working copy.
Deployments are run from throwaway git worktrees, so a per-worktree store is
empty on every run and both `-Rollback` and the automatic restore silently have
nothing to fall back to. `Scripts/deploy-state.ps1` keeps it in a stable
per-machine, per-app directory instead — `%LOCALAPPDATA%\net-care-agent\deploy\apps\<app>\`
on Windows, `$XDG_STATE_HOME` or `~/.local/state/net-care-agent/deploy`
elsewhere — overridable with `-StateRoot` or `NET_CARE_DEPLOY_STATE_ROOT`.

Releases in that store are immutable and content-addressed as
`<commit>-<sha256>.zip` with sidecar `.sha256`/`.commit` records, and a single
`state.json` manifest names current, previous, and promotion history. The
manifest is written to a temporary file and moved into place in one operation,
so current and previous can never disagree and a crash cannot leave a
half-promoted pair. An exclusive lock file serialises deploys for one app on one
machine; it is taken after the local gates so a long test run does not block
another operator, and is held across the whole remote window. Retention keeps a
bounded number of releases in promotion order and never prunes current or
previous. Before arming the automatic restore, the script compares the recorded
current release against the commit `/api/health` actually reports, so it does not
"restore" a package production was never running; when health is unreachable it
falls back to the recorded current, because the app may simply be down. A legacy
in-worktree `.deploy/` is verified and copied in once, only when the durable
store has no current release, and is never moved or deleted.
`Scripts/Test-DeployState.ps1` exercises all of this against temporary
directories with no network or Azure access, and `pytest` runs it.
