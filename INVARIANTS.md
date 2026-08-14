# INVARIANTS — load-bearing rules for the NET/Care Research Agent

**Read this before changing code — especially if you are a smaller/cheaper AI
session.** These are the rules that, if broken, silently corrupt a caregiver's
clinical tool. CI enforces some of them (`tests/test_invariants.py`); the rest
are on you. Nothing here may be routed around. Last verified: 2026-07-11.

## 1. The six non-negotiables
1. **Decision-support only.** Never diagnose, prescribe, or position the tool as
   replacing the oncologist. The oncologist reviews all output.
2. **Clinical judgments override data.** The oncologist's `clinical_judgments`
   are ground truth and override any data-derived conclusion, in EVERY agent that
   sees them (orchestrator, exec_summary, chat, questions). The shared block is
   `agent.judgments.CLINICAL_JUDGMENTS_OVERRIDE` — keep it wired in.
3. **Single JSON profile is the source of truth.** No database, no scheduler, no
   MSAL, no multi-tenancy. These absences are deliberate. `patient_profile.json`
   on the Azure Files mount is everything.
4. **PHI never goes to unprotected sinks** (plaintext logs, Teams, third parties).
   MIP sensitivity labels are respected. The Anthropic key lives in Key Vault.
5. **Machine-parsed output contracts are stable** (see §2). Downstream code does
   `json.loads` on these and the UI renders fixed keys/enums.
6. **Change control.** Every behaviour change updates the matching docs
   (`AGENTS.md` doc-update policy), adds/keeps tests, and passes the
   ruff/gitleaks/sensitive-pattern CI. No exceptions.

## 2. Machine-parsed output contracts (do NOT rename keys or change enums)
- **intake** JSON object keys: `document_type, date, source_document_date,
  summary, biomarkers[],
  imaging_findings, treatment_changes[], ki67_update, sstr_status_update,
  sstr_score_update, symptoms_reported[], appointments[], key_findings[],
  evidence[], suggested_workflows[], workflow_rationale`. Biomarker items:
  `marker, value, unit, date, date_kind, reference_range, flag, specimen, assay,
  method, source_quote`. Observation date/kind and context may be emitted only
  when explicit in the source; source-document date is separate and never
  substitutes for clinical chronology. Qualifiers remain in exact `value`,
  units are never converted, and `flag` is only a printed source flag, never an
  inferred range interpretation. Imaging, symptom,
  and appointment objects also require `source_quote`; `evidence[]` anchors
  scalar updates, treatment changes, and key findings. Appointment items:
  `date, description, type, source_quote`
  (persisted to `profile['appointments']` and merged into the summary timeline).
  Every fed document gets a unique `source_document_id` and immutable source
  artifact. Quotes are normalized only for matching, then stored as the exact
  source slice with offsets and `evidence_status=verified|missing|invalid`;
  unsupported model text is never persisted as a quote.
- **`added_at` (ingestion timestamp).** Every item appended to the counted
  profile collections (`biomarkers, imaging, documents, alerts, symptoms,
  clinical_judgments`) is stamped with `added_at` (wall-clock, seconds) at the
  append site. It remains ingestion provenance for audit and legacy compatibility,
  not unread or review state. The retired `/api/changes` compatibility routes stay
  inert and must not write acknowledgement state. Research freshness is only exact
  `latest_research_update` batch membership; no profile collection is generically
  counted as new, unread, or acknowledged. `trials_tracked` /
  `literature_watched` retain their existing `date_added` provenance.
- **exec_summary** JSON keys: `overall_status` (enum
  `stable|responding|progressing|insufficient_data`), `status_confidence`
  (`high|medium|low`), `status_rationale, key_concern, summary, prrt_status`
  (`eligible|likely_eligible|pending_dotatate|not_eligible|unknown`),
  `prrt_rationale, cga_trend` (`rising|stable|falling|insufficient_data`),
  `cga_trend_detail, next_actions[], timeline[], best_trial, claim_evidence,
  generated_at`. `claim_evidence` and `next_actions[].evidence_ids` may contain
  only opaque IDs from the server-built verified evidence catalog. Unknown IDs
  are invalid, and an empty list means no exact source span. PRRT/trial values
  are screening support for clinician discussion, never definitive eligibility.
- **questions** JSON array items: `text, category`
  (`Treatment|Diagnostics|Symptoms|Trials|Monitoring|Other`), `priority`
  (`urgent|high|medium`), `rationale`. Enums stay English; `text`/`rationale`
  follow `patient.language`.
- **classify** JSON array items: `text, category`
  (`active|planned|completed`), `label, date`.
- **orchestrator** report Markdown section headers the UI/consumers key on:
  `## Summary, ## Biomarker Assessment, ## New Literature Findings,
  ## Trial Updates, ## Recommended Next Steps` (plus an optional
  `## ⚠ Reference verification` footer).

## 3. Read vs write discipline
- **Every complete load-mutate-save transaction is serialized.** This includes
  `_run_feed_job`, `_run_digest_job`, manual summary generation, and every
  state-changing Flask route and CLI command. Use `agent.serialized_mutation`;
  its re-entrant thread lock plus advisory lock on the shared data mount permit
  nested helpers while preventing web/CLI/deployment-process lost updates.
- **`deep_sweep` NEVER saves.** It deep-copies the profile and returns a report
  artifact only. Do not add a `save_profile` call to `agent/deep_sweep.py`;
  `tests/test_invariants.py` asserts its source contains none.
- **`chat` never mutates.** Read-only Q&A.
- Feedback writes are serialized review-state mutations. `missed`, `incorrect`,
  and `corrected` feedback may mark the current summary stale, but feedback never
  mutates clinical facts or becomes a clinical judgment implicitly.
- `profile_revision` remains the clinical/effective dependency identity.
  `workflow_revision` advances for every durable follow-through mutation.
  Owner/due/order/pin/administrative status changes advance only workflow;
  captured answers/unknowns/decisions/clinical outcomes and alert resolution
  advance both and invalidate revision-bound generated context.
- Accepted generated actions are server-side snapshots selected by stable source
  ID + full semantic token. Durable `caregiver_actions[]` never reads its text or
  provenance back from a later summary. No index/text acceptance route exists.
- Workflow visits are separate from receipt-correctable `appointments[]`.
  Generated questions remain ordered snapshots. Answers and decisions are
  caregiver-entered, clinician-attributed, and unverified; they are never model-
  written, source-verified, silently rewritten, or promoted to hard constraints.
- Visit recap is a deterministic authenticated/no-store read projection, never
  a schema artifact or clinical mutation. It requires stable visit ID + full
  visit-token CAS and returns both revisions plus a recap semantic token.
  In-progress/completed recap wording is copied exactly from bounded allowlisted
  visit/action/resolved-alert fields; generated questions retain generated
  provenance, clinician-attributed captures remain explicitly unverified,
  administrative outcomes remain non-clinical, and retracted/superseded
  decisions are never current statements. Planned and cancelled visits are
  non-exportable. Viewing/copying/downloading/printing never saves, appends
  history, advances revisions, or marks review state.
- Biomarker series is a deterministic authenticated/no-store read projection,
  never a schema artifact, LLM context, or clinical mutation.
  `GET /api/patient/biomarker-series` returns all bounded observations, both
  revisions, and opaque tokens bound to every full persisted row plus evidence/
  source artifact, document exclusion, import/receipt/change authority. It
  exposes no paths, raw source text/quotes, raw offsets, history, or job
  internals; viewing never saves, audits, advances revisions, or calls a network/
  model service. `/api/status` remains recent-summary compatibility only.
- Biomarker persistence never collapses duplicates. Projection may collapse only
  exact semantic duplicates from the same source and must retain every row ID,
  evidence link, duplicate count, and independent token authority. Different
  sources never collapse.
- Biomarker grouping uses only boundary-exact reviewed aliases and never implies
  comparability. Numeric comparison requires explicit identical unit, exact
  collection/result day, specimen, assay or method, and parsed reference-range
  semantics. Unknown context, partial/invalid dates, qualified/ranged/nonnumeric
  values, and unit differences are non-comparable; no conversion or clinical
  trend label is permitted.
- Biomarker report-range comparison uses only finite unqualified numeric values
  and that observation's narrow parsed range. Stored flags retain explicit
  authority (`source_reported|caregiver_corrected|legacy_unknown|unknown`) and
  are never overwritten or validated by the computed comparison.
- Biomarker projection fails as one bounded path-free `422` on structural
  corruption, missing/duplicate IDs, unsafe nested/non-finite values, overflow,
  or inconsistent verified source authority. A bounded scalar fact with missing
  marker/date/unit/context remains visible as explicitly unclassified or
  non-comparable.
- Imaging series is a deterministic authenticated/no-store read projection,
  never an LLM context or clinical mutation.
  `GET /api/patient/imaging-series` returns every bounded persisted imaging row
  independently, both revisions, and opaque tokens bound to the complete hidden
  row plus validated extracted source, exact evidence, document exclusion, and
  import/receipt/change authority. It exposes no source ID, path, offset, quote,
  receipt internals, arbitrary extra fields, or lossy `new_lesions` boolean.
- Imaging persistence and projection never collapse duplicates. Existing IDs,
  wording, dates, evidence, order, and unknown fields are preserved; only missing
  IDs receive deterministic source/span/full-row identities. Legacy dates remain
  exact but explicitly `legacy_unknown`; new missing dates remain null/unknown
  and never fall back to ingestion day. A note/visit date is never promoted to
  an imaging study date; modality is retained only when present verbatim in
  source text and is never normalized.
- Imaging projection never matches lesions, parses or converts measurements,
  computes interval change, or labels progression, stability, response,
  new/resolved lesions, trends, treatment suitability, or clinical meaning.
  Partial/unknown/manual/unverified rows remain visible. Structural corruption,
  missing/duplicate IDs, unsafe/non-finite authority, tampering, inconsistency,
  or overflow fails the complete projection with bounded path-free `422`.
- Imaging source/evidence links use only a URL-safe stable reference derived from
  the preserved imaging row ID. Server-side resolution accepts no raw legacy ID,
  client path, source ID, quote, or offset and serves only integrity-validated
  extracted text or its exact stored span.
- Legacy `symptoms[]` observations and caregiver-maintained
  `symptom_episodes[]` are distinct authorities. Migration and reconciliation
  never promote, merge, deduplicate, reorder, resolve, link, or delete an
  episode because of an observation. Existing observation IDs/extras survive;
  missing IDs use deterministic source/span/provenance/full-row authority, with
  occurrence IDs only for an indistinguishable duplicate multiset.
- Imported symptom observations have unknown clinical event dates unless a
  future per-row extraction contract provides explicit event authority.
  Document/note/visit/import/ingestion dates never become onset or resolution;
  source-document date is separate, and pre-v11 dates remain
  `legacy_unknown`.
- Symptom episodes are explicit caregiver-entered and unverified. Severity is
  only `mild|moderate|severe|null` plus optional exact detail—never mapped,
  compared, scored, inferred, or used for triage/action/alert automation.
  Entry actor and explicit reported subject remain separate. Create is current;
  only current-to-resolved is allowed; no delete, reopen, auto-resolution, or
  lifecycle cascade exists, and recurrence is a new ID.
- `GET /api/patient/symptom-episodes` is a deterministic authenticated/no-store
  complete projection of bounded observations, episodes, and eligible action
  links. Both revisions and opaque tokens bind full row, private source/
  evidence/document/import/receipt/history/lifecycle/action authority. Public
  output contains no paths, offsets, quotes, raw source/import IDs, receipt
  internals, history, or unsafe route IDs. Corruption/inconsistency/overflow is
  a whole-read bounded `422`; reads never save, quarantine, audit, mutate,
  advance revisions, or call models/networks.
- Episode create/edit/resolve and every atomic follow-up link variant require
  exact projection, episode/action authority as applicable, both revisions,
  canonical request, target, and scoped mutation ID under
  `serialized_mutation`. Create/edit/resolve advance both revisions; existing
  link, unlink, and existing-episode inline create-link are workflow-only.
  Inline create-link validates before generating the action, appends action and
  episode audit against their exact IDs, and saves once. Exact replay returns
  the immutable response; conflict/save failure commits no action, link,
  history, or revision. Actions retain visit/decision/alert provenance, may
  link to at most one episode, and never cascade lifecycle in either direction.
- Fixed episode safety copy is non-personalized: NET/Care records entries but
  does not assess urgency or monitor symptoms; contact the treating team about
  symptoms/concerns, and contact local emergency services if the caregiver
  thinks it may be a medical emergency. No model/rules triage or treatment
  recommendation is permitted. Episodes never enter chat, orchestrator,
  questions, or executive-summary prompts; legacy `symptoms[]` behavior stays
  compatible.
- Schema v14 gives every trial and paper occurrence a private stable
  `research_record_id` without normalizing, merging, deduplicating, reordering,
  relabeling, scoring, or deleting any legacy row, duplicate, external ID,
  wording, history, stored URL, or unknown extra. Existing nonempty IDs survive
  verbatim even when malformed or duplicated; profile load remains available,
  while the bounded workspace fails closed on ambiguous occurrence authority.
  Missing legacy IDs derive deterministically from item type, strongest source
  authority, the complete semantic row, and an occurrence within an identical
  duplicate multiset. Newly discovered rows receive fresh opaque IDs before
  persistence, and refresh preserves them.
- `latest_research_update` remains exact external NCT/PMID batch membership only.
  Research views, shortlist creation, lifecycle changes, events, and action links
  never mutate it and never create unread, review, acknowledgement, aging, or
  opening state.
- `research_considerations[]` is explicit caregiver workflow authority separate
  from external facts, machine-generated compatibility context, discovery
  provenance, and latest-batch membership. One deterministic consideration may
  exist for one exact occurrence. Its allowlisted snapshot is immutable; current
  exact-occurrence presence and external/generated/discovery equality are
  projected separately. Refresh, removal, same-external-ID replacement, import
  reconciliation, and delete/re-add never rewrite, delete, close, or rebind the
  saved workflow.
- Research lifecycle is only `open|closed`; close and resume are explicit,
  append-only workflow events and imply no relevance, suitability, eligibility,
  enrollment, availability, obsolescence, or clinical decision. Shared events
  are caregiver note, next step, and treating-team communication; only trials
  permit trial-site communication. Entered year/month/day precision is preserved
  exactly. Attribution is fixed as `Caregiver-entered · unverified`,
  `Caregiver-entered · attributed to clinician · unverified`, or
  `Caregiver-entered · attributed to trial site · unverified`.
- `GET /api/patient/research-workspace` is authenticated, no-store,
  side-effect-free on current schema, complete, and bounded. Tokens bind every
  full private row, consideration/history/event/action, relevant import
  authority, and exact latest batch. Public snapshots contain only allowlisted
  external facts, generated context, discovery provenance, and occurrence/source
  identity. Navigation links are generated only from exact uppercase
  `NCT########` or canonical numeric PMID. Corruption, ambiguity, inconsistency,
  or overflow is one short non-PHI `422`, never partial/truncated output.
- Every research mutation requires both revisions, complete projection and exact
  target tokens, canonical request replay, scoped mutation ID, serialized
  validation before allocation, append-only audit, and one atomic save. Success
  advances only `workflow_revision`, including clinician/site-attributed
  unverified notes. Replay returns the immutable original IDs/revisions and
  creates no second event/action/history/save.
- A caregiver action has at most one durable owner across visit, decision, alert,
  symptom episode, treatment discrepancy, and research consideration. Existing
  persisted links remain readable, but new linking uses the shared symmetric
  owner check. Research inline actions retain immutable
  `research_consideration` origin even after unlink. They never enter model
  context; generic actions are excluded while research-linked and regain prior
  behavior after unlink. Action and consideration lifecycle never cascade.
- Internal research IDs and all shortlist/disposition snapshots, events, notes,
  links, and histories are excluded from chat, orchestrator, questions,
  executive summary, deep sweep, and generic model serialization. Existing
  model-visible source research content stays unchanged. The fixed workspace
  safety copy is: `NET/Care records research you choose to follow but does not
  determine relevance, eligibility, enrollment, or treatment suitability.
  Confirm clinical questions with the treating team and trial details with the
  study site.`
- Treatment receipt occurrences, legacy `patient.current_treatments[]` plus
  raw component/mapped generated classification mappings, pre-v6 unlinked
  generated compatibility context, caregiver-maintained `treatment_courses[]`,
  and caregiver-created `treatment_discrepancies[]` are separate authorities.
  Schema v12 migration initializes only missing/null
  reconciliation collections. Schema v13 marks only pre-extension past courses
  lacking terminal authority as `legacy_unspecified`; both migrations never
  promote, normalize, merge,
  deduplicates, reorders, relabels, or deletes legacy facts, duplicates, IDs,
  mappings, evidence, receipt history, or unknown extras.
- Course current/past/planned status, terminal qualifier, and
  start/stop/planned dates are explicit
  caregiver workflow authority, not inferred clinical truth. Dates retain only
  entered day/month/year precision; document/import/visit/current dates never
  substitute. New past creation requires exact non-legacy
  `ended|not_started|cancelled|other`; `other` requires nonempty bounded exact
  detail and all other qualifiers reject detail. Current/planned have no
  terminal authority. Current may transition to past only as `ended|other`;
  planned may transition to current or past as
  `not_started|cancelled|other`. Past is terminal. Public lifecycle authority
  returns exact allowed transitions plus restart eligibility/reason. Restart
  creates a new current/planned ID only when private server history proves the
  terminal course was previously current; planned-never-started, cancelled, and
  direct past records are ineligible. No date, source, action, visit, decision,
  clock, or model transition or qualifier inference is permitted.
- Treatment names/types, dose, route, frequency, cycle, schedule, formulation,
  indication, and notes remain exact text. Only explicitly selected stable
  legacy component IDs may link; no fuzzy, substring, brand/generic, regimen,
  class, dose-conversion, schedule-normalization, adherence, suitability, or
  clinical comparison logic is part of reconciliation.
- Discrepancies are explicit caregiver-created neutral comparisons with exactly
  two current cited authorities: opaque source occurrence A plus either distinct
  opaque source occurrence B or one exact caregiver course B. Public
  `citation_kind=source_vs_source|source_vs_course` is server-declared; A/B
  carries no chronology, preference, correctness, or clinical meaning.
  Generated classification and legacy raw/component rows are non-citable.
  Pre-v6 generated rows with no modern ID/source mapping must retain the exact
  authority label `Machine-generated compatibility context · source linkage unavailable · not a treatment record`. Their public IDs/tokens are
  deterministic and occurrence-aware, bind the complete allowlisted stored row
  plus both revisions, preserve every duplicate/order, and never infer
  source/component linkage or expose controls.
  Client-authored snapshots, missing/mixed/duplicate/dangling/stale citation
  pairs, and recurrence-side substitution are rejected before ID allocation or
  mutation. Resolution preserves the discrepancy, both immutable cited
  snapshots, source facts, and all prior outcomes. Confirmation notes retain
  exact wording and fixed
  `Caregiver-entered · attributed to clinician · unverified` provenance.
  Bounded outcomes never claim verification, prescription, recommendation, EHR
  authority, safety, error, urgency, interaction, contraindication, duplicate
  therapy, adherence, or causality. Only `caregiver_record_corrected` may carry
  an explicit atomic course patch. Reopen preserves outcomes; recurrence is a
  new linked discrepancy ID with the prior kind/references/snapshots copied only
  by the server. Existing complete source/course records remain valid without
  rewriting. Existing one-sided records remain visible as
  `legacy_incomplete/missing_second_citation`, explicitly ineligible for
  resolve/reopen/recur, and never receive an invented citation.
- `GET /api/patient/treatment-reconciliation` is a deterministic authenticated/
  no-store complete bounded projection. Both revisions and opaque tokens bind
  full raw/classified/component/source/document/import/receipt/evidence/course/
  terminal/lifecycle/discrepancy/history/action authority for both citation
  sides. Source-occurrence document identity (`filename`, `document_type`,
  `document_date`) is projected only as the sibling `source_fact_documents[]`
  keyed by the same opaque `ref`, is bound by the projection token, and never
  widens the source-fact citation snapshot field set. It carries no course
  linkage, correlation, or inference. Immutable
  snapshots and current lifecycle state are separate; changing either side
  rotates current tokens without snapshot rewrite. Public output exposes no paths,
  offsets, quotes, raw source/import/job/receipt/change IDs, or client-
  constructible evidence coordinates. Opaque same-origin routes serve only
  integrity-validated text/span. Invalid, inconsistent, duplicate-ID, tampered,
  or overflowing authority fails the entire read with bounded path-free `422`;
  valid incomplete/manual/unverified facts remain visible.
- Every treatment reconciliation mutation requires both expected revisions,
  complete projection and applicable source/course/discrepancy/action tokens,
  a stable target, full canonical request, and scoped mutation ID under
  `serialized_mutation`. It appends audit and saves once. Exact replay returns
  the immutable original response without another action, event, revision, or
  save; conflicts, invalid terminal authority, stale authority, and save failure
  commit nothing. Pre-extension replay snapshots remain exact and valid without
  inventing client-entered terminal authority. Course/discrepancy clinical
  changes advance both revisions; reopen and follow-up link/unlink/create-link
  advance workflow only. An action links to at most one symptom episode or
  treatment discrepancy and lifecycle never cascades.
- Receipt correction/removal/undo may rotate source-fact/projection tokens and
  legacy compatibility state but never deletes or rewrites courses,
  discrepancies, confirmations, or action links. New reconciliation state is
  excluded from every model prompt. Model-visible treatment context is the
  deterministic component split of raw `patient.current_treatments[]` and
  carries no status, category, or date: caregiver lifecycle status is workflow
  authority and never reaches a prompt.
- Fixed treatment safety copy is exactly `NET/Care records what you enter but does not verify treatment details or advise starting, stopping, or changing treatment. Confirm treatment decisions with the treating team.` It is static,
  nonconditional, non-PHI, and non-prescriptive.
- Every Layer 2 mutation is stable-ID/target-token CAS under
  `serialized_mutation`, appends one request-hash audit event, increments each
  applicable revision once, and saves once. Exact `mutation_id` retries are
  no-ops; payload reuse or changed targets return `409`. No whole-profile
  rollback is permitted.
- Document receipt correction/removal/undo is a clinical mutation under
  `serialized_mutation`. It uses target-level compare-and-swap fingerprints:
  unrelated profile revisions are allowed, but any changed affected target or
  later document claim returns atomic `409` before mutation.
- Receipt undo never deletes immutable source bytes/text and never restores a
  whole-profile snapshot. It reverses only direct extraction effects, preserves
  append-only before/after history, and excludes the document from active
  clinical prompts. Orchestration research additions are derived output and are
  not silently deleted.
- Compare-and-swap fingerprints cover the complete semantic collection row.
  Later resolution or mutation of an imported alert/fact must return `409`;
  schema-added legacy defaults may be canonicalized only when they do not alter
  clinical meaning.
- Identical corrections are rejected before any mutation, save, audit event, or
  provenance invalidation.
- Stale generated content is audit history, not current context: stale/revision-
  mismatched summaries are omitted from chat and `/api/summary`; question
  generations use persisted generation IDs; corrected feed reports are retained
  but hidden; source-dependent alerts are inactive after correction/undo.
- All profile-dependent artifacts carry dependency identity: report jobs store a
  PHI-free profile revision; chat/question/summary results store source revision
  and generation identity. Missing/mismatched legacy dependencies are stale.
- Every generated alert carries origin job + profile revision; feed alerts also
  carry source-document dependency. System dependency-field synchronization may
  update receipt effective values, but must never mask caregiver mutations such
  as `resolved`.
- Eligibility/qualification/inclusion/enrollment/best-fit alert assertions are
  replaced wholesale by polarity-neutral screening-review language; never infer
  positive or negative fit from string sanitization.
- Treatment-change directives in alerts (`start/stop/hold/pause/resume/switch/
  dose-change/discontinue/withhold/skip/administer/take`) are replaced wholesale
  by treating-team confirmation wording. Factual past-tense treatment history is
  preserved.
- Alert resolution uses stable ID + full semantic token under
  `serialized_mutation`; profile-snapshot alerts also require their generation
  revision. Durable/source alerts may survive unrelated revisions when their
  target is unchanged. Resolution records outcome/links/history, advances both
  revisions, stales dependent context, preserves siblings, and never adds
  reviewed/unread/acknowledged machinery. Index resolution is forbidden.
- Chat history is revision-bound on both client and server. Nonempty mismatched
  history returns `409`; workers revalidate before sending history to the model.
- Clinical mutations commit once at their final effective revision. Summary
  generation/persistence is derived-only and must see alerts tagged to that same
  revision.
- The LLM treatment classifier is retired. Nothing refreshes
  `treatments_classified[]`, so its revision/job identity stay whatever the
  profile already held and `treatment_classification_is_current()` is
  effectively always false. Stored generated rows are retained verbatim, are
  still projected by `/api/patient/treatment-reconciliation` as
  `legacy_treatments[].generated_classification[]` and
  `unlinked_generated_context[]`, and still bind the legacy row and projection
  tokens — but they are no longer surfaced in the UI and no migration deletes
  them.
- Classification identity is canonical treatment identity, never action/status,
  dose, route, schedule, or formulation noise. Stable raw component
  IDs and classified source mappings back ID/token/revision CAS edits; composite
  siblings must survive.
- Alert dependency kinds are explicit: `durable` ignores unrelated revisions and
  survives document undo until resolved; `source` follows source invalidation;
  `profile_snapshot` requires exact generation revision. Producers stamp the
  lifecycle deliberately; future revisions are never generically active.
- Hard status/tasks/summary/evidence or authorization failure centrally evicts
  all client-side patient PHI caches and rendered/dialog content. An authoritative
  receipt may survive only a non-auth post-save detail-refresh failure.
  A server-declared `cross_origin` `403` is the sole exception: it is a request
  address problem, not an authorization problem, so it must not evict PHI or
  offer switch-account recovery, and must instead surface a bounded actionable
  same-origin/configuration message. `401`, `principal_not_allowed`, and any
  unknown, legacy, or unparseable `403` remain fail-closed evictions, and the
  duplicate/stale response guards stay intact.
- Recap render and Copy/Download/Print side effects require one authenticated,
  no-store preflight per explicit action and exact equality with the reviewed
  recap token, selected visit ID/token, exportable lifecycle, both revisions, and
  patient/visit/request epochs. One owner excludes concurrent export clicks.
  Changed authority clears token/text/object URLs and may render only a new review
  state; it is never exported until a second action passes an unchanged preflight.
  Browser offline revokes synchronously, and online alone cannot restore export.
  Network ambiguity may retain only visible stale read-only content. Auth/hard
  eviction also scrubs recap DOM/cache/export text/object URLs/focus references
  and rejects late responses. Recap loading is event-driven and never persists
  text in browser storage, URLs, logs, job metadata, or health output.
- **`save_profile` guards structural validity.** Calling `save_profile` with a
  non-dict, string patient, or non-list collection raises `ValueError`
  immediately.  Field-level type issues (out-of-range values, bad enum literals)
  are still logged as warnings; structural invalidity is rejected outright.
- **Recovery is the only legitimate path to overwrite a corrupt profile.**
  Use `agent.recovery.restore_from_candidate` — never raw `cp` or
  `Path.write_text`.  Recovery validates the candidate, holds the cross-process
  lock, and uses atomic sibling-replace.  `load_profile` calls recovery
  automatically on corrupt JSON or invalid structural shape; manual invocation
  is for operator runbooks only.
- **Quarantine is forensics, not deletion.** `quarantine_profile` copies the
  corrupt bytes to `{DATA_DIR}/quarantine/` but does not remove the original
  (recovery overwrites it atomically).  No patient data is written to quarantine
  metadata — only a filename-safe timestamp and a truncated hash.
- **Transient I/O errors are not quarantined.** If `read_bytes` raises
  `OSError`, `load_profile` raises `IOProfileError` without touching the
  quarantine dir.  The file may be valid; retrying may succeed.

### Judgment lifecycle
- `source=feedback` is the exact historical provenance tag written by the
  legacy feedback flow. Preserve it verbatim; it does not by itself mean
  clinician verification and must not be rewritten to `manual` or `ai`.
- Legacy judgments without `status` are `active`.
- Only `status=active` judgments that are neither expired (`valid_until`) nor
  review-due (`review_after`) are hard constraints.
- `superseded`, `needs_review`, expired, and review-due judgments stay visible as
  historical context explicitly requiring clinician review.

## 4. Single gunicorn worker is load-bearing
Profile mutation protection (`agent/serialize.py`) is cross-process on the
shared data mount, but job admission, executor capacity, the jobs list, and
daemon-thread execution remain in-process and assume **exactly one Gunicorn
worker**. `startup.sh` therefore uses `--workers 1`. Do NOT scale workers or
instances/autoscale without moving execution and admission to a durable
distributed queue and adding distributed coordination.

- Feed has an independent executor (`FEED_WORKERS=1`, `FEED_QUEUE_SIZE=2`);
  general work uses `JOB_WORKERS=2`, `JOB_QUEUE_SIZE=6`. Values are clamped to
  1–4 workers and 0–50 queued items. Capacity means active + queued.
- Saturation must return `429` and `Retry-After` before `_add_job`; failed
  preparation removes metadata before releasing execution. Preserve this
  no-ghost-job ordering.
- Keep `unique_active=True` for digest, deep-sweep, and summary. A duplicate
  active run returns `409`.
- Jobs are not durable work. Restart changes queued/running records to
  `interrupted`; users must re-submit. Gunicorn has a 30-second graceful limit
  and executor shutdown joins are bounded to five seconds per thread.
- New job records are PHI-safe allowlisted metadata with generic errors.
  Reports/results remain separate artifacts and are expanded only by
  `GET /api/jobs/<id>`, never embedded in `jobs.json` or the job list. Existing
  legacy records are not rewritten; do not weaken their retention protection.
  Artifact freshness is computed only in the authenticated job-detail response;
  only the numeric profile revision may be added to `jobs.json`/`GET /api/jobs`;
  no PHI or generated content is added.

## 5. Authentication, containment, and retention
- Responses must never send `Referrer-Policy: no-referrer`, and no markup, meta
  tag, or fetch option may force one. App Service Easy Auth middleware runs its
  own CSRF check before Flask and rejects a state-changing request whose
  `Referer` is empty with `403` sub-status `60`, so `no-referrer` disables every
  mutation site-wide. The emitted policy must keep a same-origin `Referer` and
  must still withhold path and query from other origins; `same-origin` is the
  shipped choice, and off-site anchors keep `rel="noopener noreferrer"`.
- Flask exempts `/api/health` and `/api/live`; all other hosted `/api/*` routes
  require a valid Easy Auth principal. Anonymous external probes additionally
  require App Service Easy Auth path exclusions. `_protect_api` is registered as
  the first `before_request` handler; unauthenticated, denied, or cross-origin
  API requests must perform no job load, retention prune, or source prune.
- Identity is parsed into two strictly separate typed namespaces that never
  cross-match. The ID candidate comes from trusted encoded claims — canonical
  object-identifier URI, `oid`, canonical name-identifier URI, then `sub`; the
  first populated tier must resolve to one unique nonempty value — else from the
  `X-MS-CLIENT-PRINCIPAL-ID` provider header, and is compared exactly and
  case-sensitively. Malformed, oversized, over-long, or conflicting selected-tier
  claims are unauthenticated and never downgrade to a convenience header.
  Static Web Apps `userId`/`userDetails` fields are a different product's schema
  and are never identity. The name candidate comes from
  `X-MS-CLIENT-PRINCIPAL-NAME` and is compared only after trimming surrounding
  whitespace with Unicode-safe `casefold()`; dots, plus tags, domains, and any
  other equivalence are never rewritten or widened. A bounded `local@domain`
  shaped ID-header value may additionally serve as a documented convenience name
  candidate for platforms that send no blob and no name header, but never gains
  stable-object-ID semantics; when a name header and an email-shaped ID header
  are both email-shaped and differ after `casefold()`, the name path fails
  closed. Base64 decoding accepts standard or URL-safe input with missing
  padding but rejects mixed alphabets, impossible lengths, corruption,
  oversized payloads, and excessive claim counts.
- `AUTH_ALLOWED_PRINCIPAL_IDS` constrains only the ID candidate and
  `AUTH_ALLOWED_PRINCIPAL_NAMES` only the name candidate. A hosted request is
  authorized when at least one configured allowlist matches its own typed
  candidate; matching both is never required, so an entry can be migrated
  between settings without a lockout window. Both allowlists empty preserves the
  historical Easy-Auth-only posture and must not be silently narrowed or
  widened. Hosted mode never honors local bypass.
- Auth failures return fixed PHI-free discriminators only: `reason` in
  `principal_absent|principal_malformed|principal_not_allowed|cross_origin|hosted_auth_unavailable`
  and, where meaningful, `principal_source` in
  `encoded_claim|provider_id_header|principal_name_header|provider_id_name_compat|absent`.
  No identifier, claim value, email, token, header name, or payload is logged or
  returned. Authorization is evaluated before the origin check so a denied
  account is never reported as `cross_origin`.
- Local API access requires explicit `ALLOW_LOCAL_AUTH_BYPASS=1`; do not restore
  implicit unauthenticated local access. State-changing methods reject a
  mismatched `Origin` as defence in depth behind the platform CSRF check.
- `/api/health` is Flask-auth-exempt by design and must remain
  PHI/path/secret-free. Executor fields are aggregate counts only.
- `pdfplumber` stays child-only in `agent/pdf_extract_helper.py`. Preserve the
  subprocess hard timeout, page/text/output limits, minimal environment,
  DEVNULL streams, and Linux resource limits.
- Job errors and job-runner logs must not contain input text, model output,
  traceback, prompts, or PHI. Keep all operational logs access-controlled;
  lower-level storage/recovery `OSError` logs may contain filesystem paths.
- `GET /api/jobs/<id>/receipt` and `/api/patient/evidence` remain authenticated
  and no-store. Public projections may include source IDs and URLs but never
  indexed filesystem paths.
- Retention removes only completed expired/excess jobs and their indexed
  reports/results, unindexed old/excess reports, and unreferenced source
  directories. Profile-referenced sources are protected. Pruning is
  best-effort and does not imply secure deletion or deletion from backups.

## 6. Prompt templating
System prompts that embed JSON schemas use `agent.llm.render_prompt` with
`[[SENTINEL]]` placeholders (NOT `str.format`, which would need brace-doubling).
`tests/test_prompt_rendering.py` fails if any placeholder leaks into a live
prompt. Preserve every injection point when editing a template.

## 7. Deploy
Manual, via `Scripts/deploy.ps1`. It refuses to package unless
pytest/ruff/gitleaks pass, records commit + SHA-256, polls asynchronous Kudu
completion and `/api/health`
critical fields plus the exact packaged commit, then promotes that exact
package to `.deploy/last-known-good.*`. A dirty working tree is rejected so the
recorded commit identifies the package. Rollback
verifies the recorded SHA before redeploying and repeating that check.
Oryx build-on-deploy is required; the release archive includes `.deployment`,
which declares it. Runtime/dev and build dependencies stay exactly pinned. See
`AGENTS.md → Deploy`.

## Provenance and maintenance
- Contract lists here mirror the prompt templates in `agent/*.py`. If you change
  a template's schema, update §2 AND `tests/test_invariants.py` in the same PR.
- Re-verify the read/write discipline: `grep -n save_profile agent/deep_sweep.py`
  (expect no matches) and check `_run_feed_job`/`_run_digest_job` acquire
  `mutating_lock`.
