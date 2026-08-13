# Changelog

All notable changes to the NET/Care Research Agent are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow strict semantic versioning — versions are
incremented when something user-visible or operationally meaningful changes.

## [Unreleased]

### Changed
- **Caregiver-first Today hierarchy.** Today now leads with access/freshness and
  the expanded latest assessment, key concern, and recommended next steps before
  bounded recorded update times/active-alert count, treatment status, symptoms,
  follow-ups, appointment preparation, and lower-priority tracked research.
  Assessment freshness uses plain Up to date / New information / Couldn't check
  language without exposing revision integers, consequential rationale is
  touch-accessible, and a guarded deferred research load fixes the cold-start
  empty card without delaying primary content or creating unread state.
- **Plain record-source language with internal identity suppression.** Biomarker,
  imaging, symptom, treatment, receipt, follow-up, alert, research, and
  appointment/recap surfaces now explain whether information came from a linked
  document/exact wording, was entered or corrected by the caregiver, or was
  recorded from the clinician. Routine UI no longer prints opaque record,
  evidence, source-row/document, generation, decision, follow-up, token, hash,
  path, or revision identities. Exact source links remain authenticated; receipt
  source actions open human-readable text instead of metadata JSON. These labels
  describe traceability and never claim clinical authenticity.
- **First-class recorded treatment Overview.** Patient Treatments now opens on
  explicitly reviewed current/planned courses, every existing patient treatment
  row under Status not recorded, then finished/past courses. Today no longer
  appears empty when recorded rows exist. Every row, duplicate, order, component,
  and count remains unchanged; no migration, lifecycle inference, promotion,
  prefill, merge, deduplication, or model-context change was added. Automatic
  compatibility notes are collapsed, secondary, and explicitly not treatment
  facts.
- **Truthful Activity artifact states.** PHI-safe job metadata now records
  available, expired, not-retained, unavailable, none, or legacy-unknown output
  state and publishes report/result kind plus current/stale/unknown freshness
  without storage paths. Retention persists its reason before clearing the
  reference; missing/corrupt output is distinct from expiry. Activity uses plain
  task/status names, makes document import receipts first-class, renders
  structured results without raw JSON, removes unreachable PHI-preview branches,
  and no longer falls through to “No report generated.”
- **Appointments navigation and responsive accessibility.** The visible Questions
  destination is now Appointments while its internal `questions` route, APIs,
  deep links, first Questions tab, CAS/replay, recap, and export authority remain
  unchanged. Follow-up tabpanel labels now track selection; duplicate hidden live
  announcements are disabled; secondary text meets 4.5:1 contrast; caregiver
  type is at least 11px; the obsolete mobile stylesheet is removed; the 721–768px
  shell gap is closed; and wide clinical tables retain labelled keyboard-focusable
  local scrolling at phone width.

### Fixed
- **Hosted stable-principal authorization.** Easy Auth allowlist checks now
  prefer a unique canonical object-identifier claim, then `oid`, then
  name-identifier/`sub` fallbacks, before provider convenience identity values.
  Identical duplicates remain valid, malformed or conflicting selected-tier
  claims fail as unauthenticated, and a valid nonmatching stable identifier
  remains forbidden. This prevents an email-valued convenience header from
  overriding the configured stable object-ID allowlist without changing hosted
  Easy Auth, local bypass, health/liveness exemptions, exact allowlist matching,
  or same-origin mutation protection.
- **Focused caregiver workspace polish.** A stale Today assessment now exposes
  exactly one guarded **Refresh assessment** action in its freshness banner;
  duplicate heading and hidden-summary controls are removed while stale
  conclusions remain fail-closed. Every Recent updates row action now uses the
  shared secondary-button styling with phone-sized targets and consistent
  responsive alignment. Repetitive generic symptom, treatment, research, and
  global capability strips are removed from routine presentation while
  actionable stale/auth/error/conflict notices, provenance, source uncertainty,
  generated-context labels, and confirmations remain intact.
- **Post-review caregiver workspace blockers.** Stale corrupt or explicitly
  unavailable reports now remain unavailable in both Activity list and detail
  and are never hydrated or claimed as retained audit
  content. Recorded treatment rows use only explicit component associations to
  distinguish unlinked, fully linked, and partly linked status review without
  hiding rows or inheriting lifecycle. Polling Recent updates is no longer a live
  region, and repeated Recent updates or Active alerts polling failures reuse
  one alert node instead of re-announcing unchanged failure copy. Polling an
  open stale-unavailable Activity item preserves its unavailable state and retry
  action. Activity result links now
  close/deactivate the report dialog before opening Today or Appointments and
  place focus on the target heading/dialog at desktop and phone widths, including
  when workflow mutation locks prevent an appointment dialog from opening.
  Unchanged stale Activity polling now uses a semantic render key, preserving
  action/alert node identity and keyboard focus inside the modal; stale result
  copy says retained/hidden only when the artifact is actually available.

- **Authorization-eviction recovery messaging.** A `401` or `403` now records the
  authorization failure before request epochs invalidate late handlers, so the
  global sign-in/access banner remains visible while every patient-derived
  surface is still cleared fail-closed. The banner and symptom, treatment,
  research, biomarker, and imaging empty states explicitly distinguish cleared
  browser-held data from stored patient records, which were not deleted, and
  expose separate manual **Reload to sign in**, **Sign out and switch account**,
  and **Retry** controls. Denied access uses the supported same-origin Easy Auth
  logout endpoint with an encoded return to `/`; no automatic reload loop is
  introduced before strict current-revision projections repopulate.

### Added
- **Shared Today/Research shortlist and disposition workflow.** One atomically
  validated `research-workspace` projection now drives a bounded Today summary
  with exact totals/omissions and a complete Research view preserving every
  occurrence, duplicate, consideration, event, and history item in server order.
  External facts, machine-generated compatibility context, discovery provenance,
  immutable snapshots, section-specific current state, and caregiver workflow
  remain separate. Exact server eligibility controls shortlist, attributed
  unverified events, neutral close/resume, and atomic follow-up link/create/unlink.
  Strict canonical links, passive latest-batch membership without unread state,
  CAS/replay ownership, provisional full-reload completion, submission-versus-
  refresh retry, endpoint-specific stale retention, PHI clearing, keyboard/focus
  behavior, and 1280/360 overflow safety replace status-derived caches and legacy
  trial/paper dialogs without changing backend compatibility APIs.
- **Backend research shortlist and disposition authority.** Schema v14 preserves
  every existing trial/paper row while assigning stable exact-occurrence
  identities where missing. An authenticated no-store bounded workspace and
  replay/CAS-safe workflow APIs add explicit shortlist capture, immutable
  allowlisted external/generated/discovery snapshots, neutral open/closed
  history, caregiver/clinician/trial-site attributed unverified events, canonical
  PubMed/ClinicalTrials.gov links, and atomic exclusive caregiver-action linkage.
  All mutations are workflow-only; source refresh/removal, exact latest-batch
  membership, existing discovery behavior, and model prompts remain isolated.
- **Shared Today/Patient treatment reconciliation workflow.** Today shows a
  bounded first set of current/planned caregiver records in server order with
  exact totals and omissions; Patient provides complete separate Treatment
  records, Differences to review, Document mentions, and Earlier app records
  panels. One validated projection and mutation owner preserve raw/date/null/
  empty fidelity, render lifecycle/restart/discrepancy/outcome/recurrence/
  follow-up controls only from server authority, keep immutable citation
  snapshots distinct from current sides, and never promote legacy or generated
  compatibility context into treatment authority. Canonical opaque links,
  exact replay/CAS, conflict draft stripping, provisional full-reload success,
  treatment-only hard clearing, central PHI eviction, owned race epochs,
  responsive overflow, keyboard tabs, focus safety, and 44-pixel controls cover
  desktop and phone. `/api/status` treatment UI behavior is retired while
  backend compatibility remains.
- **Explicit treatment terminal authority.** Schema v13 gives every past
  caregiver course a mechanical `ended`, `not_started`, `cancelled`, `other`, or
  server-only `legacy_unspecified` qualifier. Exact bounded detail is required
  only for `other`; no clinical reason is inferred. Current/planned-to-past
  matrices, projected allowed transitions, and server-owned restart
  eligibility/reasons prevent the UI from guessing lifecycle meaning. Restart
  requires private history proving prior-current authority and is unavailable
  for planned-never-started, cancelled, or direct past records. Migration marks
  only missing legacy past authority, tokens bind terminal/lifecycle inputs,
  discrepancy snapshots remain immutable, and pre-extension replay remains
  exact.
- **Two-sided treatment discrepancy authority.** New discrepancies now cite
  exactly one source occurrence plus either a distinct source occurrence or an
  exact caregiver course, persist immutable snapshots of both sides, declare a
  mechanical citation kind, and bind either side's full current/private
  lifecycle into replay/CAS tokens. Recurrence copies prior citations
  server-side. Existing complete source/course records remain lossless; older
  one-sided records stay visible as explicitly ineligible legacy authority and
  never receive an invented citation. Generated classification and legacy
  compatibility rows remain non-citable. The contract uses the exact fixed
  non-prescriptive treatment safety copy.
- **Treatment reconciliation backend foundation.** Schema v12 adds separate
  caregiver-maintained treatment courses and explicit neutral discrepancies
  without promoting or rewriting legacy raw/component/classified treatment or
  source-receipt authority. A complete authenticated no-store projection keeps
  every receipt occurrence and legacy duplicate separate, binds private
  source/evidence/history/action authority into opaque tokens, serves only
  opaque integrity-validated source/evidence routes, and fails closed on
  corrupt or oversized authority.
- **Replay/CAS-safe treatment workflow APIs.** Explicit course create/edit/
  transition/restart, discrepancy create/resolve/reopen, and mutually exclusive
  durable action link/unlink/manual create-link mutations require both
  revisions and complete target authority, append audit, and commit once.
  Restarts create new linked episodes; treating-team outcomes retain exact
  caregiver wording with fixed unverified clinician attribution; no date,
  source, action, visit, model, or clock causes a lifecycle change. The new
  authority remains excluded from model prompts.
- **Shared Today/Patient symptom episode workflow.** Today now summarizes every
  current caregiver-entered episode and linked follow-up; Patient provides the
  complete current/resolved lifecycle plus a separate read-only source
  observation table. One responsive accessible dialog supports bounded add,
  edit, resolve, existing-action link, atomic manual create-and-link, and unlink
  operations without delete, reopen, lifecycle cascade, date defaulting, or
  clinical inference. The SPA uses only the complete symptom projection,
  validates all authority before rendering, preserves server order and
  duplicates, displays the exact fixed safety statement, and enforces owned
  CAS/replay/reload, endpoint-specific stale retention, PHI clearing, focus
  safety, and 1280/360 overflow boundaries.
- **Atomic follow-up creation for an existing symptom episode.**
  `PATCH /api/symptom-episodes/<episode_id>/follow-up` now accepts a third,
  mutually exclusive bounded manual follow-up variant alongside exact existing
  action link and unlink. It validates full CAS authority before generating the
  action, records action and episode history against their exact IDs, advances
  workflow revision only, saves once, and replays the immutable generated
  action without duplication. Conflict or save failure commits no partial
  state.
- **Durable symptom episode backend foundation.** Schema v11 keeps every legacy
  `symptoms[]` observation separate while adding explicit caregiver-maintained
  current/resolved `symptom_episodes[]`. Migration preserves IDs, duplicates,
  wording, order, provenance, and unknown fields; missing IDs are deterministic,
  legacy dates remain uncertain, and future imported observations no longer
  inherit a document or ingestion date as clinical symptom chronology.
- **Replay/CAS-safe symptom episode APIs.** Authenticated no-store projection,
  opaque source/evidence routes, and serialized create/edit/resolve/link
  mutations bind both revisions plus complete episode/action/source/import
  authority. Episode creation can atomically link one eligible existing action
  or create and link one bounded manual follow-up; replay returns the original
  response, while conflict/save failure leaves neither partial record. Fixed
  non-diagnostic safety copy is returned without model/rules triage. Episodes
  remain excluded from all model prompts.
- **Provenance-safe imaging longitudinal backend contract.** Schema v10
  deterministically backfills missing imaging IDs from source/span and full-row
  authority without rewriting existing IDs, wording, dates, unknown fields, list
  order, or duplicate occurrences. Legacy dates are explicitly uncertain; new
  undated imaging remains undated instead of receiving ingestion day, dates on
  non-imaging documents are not promoted to study dates, modality is retained
  only when present verbatim in source text, and receipt correction/undo keeps
  target CAS and audit behavior.
- **Bounded imaging series projection API.** Authenticated no-store
  `GET /api/patient/imaging-series` returns every imaging row independently with
  both revisions and opaque tokens bound to complete row/source/evidence/
  document/import authority. Opaque row-ID source/evidence routes resolve
  server-side through URL-safe derived references, with no raw reserved-character
  legacy ID, client path, or offsets. Incomplete/unverified rows remain
  visible, while corrupt, duplicate-ID, inconsistent, tampered, or oversized
  authority fails closed with bounded `422`. The contract performs no duplicate
  collapse, lesion matching, measurement comparison, progression/response label,
  trend, treatment judgment, or other clinical inference.
- **Table-first Patient imaging timeline and explicit comparison.** The shared
  desktop/phone Patient view now validates and atomically accepts the complete
  imaging projection, preserves every server-ordered record and duplicate with
  exact date uncertainty/report wording/provenance, and requires exactly two
  current selections plus caregiver confirmation before showing attributed raw
  facts side by side. Opaque authority stays in JavaScript state; strict
  same-origin opaque source/evidence links, revision/request/selection epochs,
  endpoint-specific stale retention, hard imaging-only clearing, full auth PHI
  eviction, focus safety, contained table overflow, and live 1280/360 browser
  tests enforce the non-inference boundary. No image viewer, chart, diff,
  clinical conclusion, copy, download, print, or export was added.
- **Provenance-safe biomarker longitudinal backend contract.** Schema v9
  deterministically backfills missing biomarker IDs without using mutable list
  position when source/span authority exists, preserves cross-source and
  same-source duplicate facts, and records explicit observation/source-document
  date precision, specimen, assay, method, and stored-flag authority. Intake
  preserves qualifiers and only explicit context; receipt correction/undo keeps
  stable IDs and manual-unverified provenance.
- **Bounded biomarker series projection API.** Authenticated no-store
  `GET /api/patient/biomarker-series` returns every bounded observation, both
  revisions, opaque authority tokens, conservative analyte groups, strict
  comparable-series boundaries, observation-specific report-range comparisons,
  and path-free evidence/source links. Same-source exact duplicates collapse
  only for presentation while retaining all row/evidence authority; malformed,
  oversized, or inconsistent verified data fails closed with bounded `422`.
- **Table-first Patient biomarker explorer.** The shared desktop/phone Patient
  view now selects server-provided analytes and renders every raw observation,
  alias, duplicate/source identity, provenance state, evidence link, and neutral
  non-comparability reason from the complete projection. Secondary SVG charts
  show isolated points only for exact server-declared comparable groups—no
  client aliasing, unit conversion, interpolation, aggregation, connecting line,
  trend label, or clinical judgment. Dedicated request/selection epochs,
  AbortController and exact token ownership reject late responses; offline
  ambiguity keeps a visibly stale read-only snapshot, while authorization and
  hard invalidation scrub biomarker state, DOM, focus, and pending responses.

### Fixed
- **Production profile-load compatibility.** Schema v15 restores only a truly
  missing top-level `profile_revision` as integer `0`, preserves invalid existing
  revision authority for fail-closed review, and accepts the exact historical
  clinical-judgment source tag `feedback` without rewriting its provenance or
  content. The bounded treatment API and Patient workspace now preserve every
  well-formed pre-v6 generated compatibility row with unavailable source linkage
  in a distinct exact-count, occurrence-aware, non-citable, read-only collection;
  Today counts but never presents those rows as current/planned courses.
- **Cross-workflow authorization teardown and control targets.** Central PHI
  eviction now aborts and invalidates in-flight document, digest, and deep-sweep
  submissions; clears selected upload bytes, feed errors, focus, and polling; and
  prevents late responses from activating Activity state. Polling also stops
  safely when authority disappears. Alert resolution, visit ordering, and
  research disclosure controls now retain at least 44-pixel targets at desktop
  and phone widths.
- **Authoritative recap export preflight and offline revocation.** Every recap
  Copy, text download, and print now owns one duplicate-locked authenticated
  no-store preflight and performs its browser side effect only when the selected
  visit, full token, recap token, both revisions, request/selection/PHI epochs,
  and exportable lifecycle exactly match the reviewed snapshot. Changed authority
  becomes a new review state requiring a second click; conflicts, stale or
  revisionless responses, network ambiguity, authorization/hard failures, and
  late responses export nothing. The browser offline event now immediately
  revokes recap tokens, text, controls, and Blob URLs, and online state alone
  cannot restore export before a successful authoritative reload.
- **Visit recap identity teardown and export visibility.** Changing the selected
  visit or its full token now removes the prior structured recap, rendered
  sections, export payload/object URL, print state, and export focus before the
  new visit renders or loads, so late responses cannot cross visit identities.
  Copy, download, and print controls are omitted unless a current accepted
  in-progress/completed recap is exportable; planned, cancelled, unavailable,
  stale, authorization-cleared, and other non-exportable states expose none.
- **Structured alert-resolution authority and teardown.** The Patient alert
  dialog now gates open/source/conflict/convergence/mutation responses on one
  pre-selection owner, patient epoch, alert identity/token, and monotonic
  revisions. Conflict reloads redact the old card and hidden copy before
  obtaining fresh authority; offline projections remain visibly stale and
  read-only with an exact unchanged retry; authorization and hard failures scrub
  every visible/hidden alert value, selector, draft, retry, owner, and
  focus/inert reference. Late alert A responses cannot populate alert B, unlock a
  newer intent, or announce success after eviction.
- **Cross-surface revision authority.** Patient-data responses now pass one
  monotonic profile/workflow authority guard before changing caches, revisions,
  drafts, retries, or rendered content. Observing a newer clinical revision
  invalidates every older in-flight patient read, including revisionless legacy
  responses, while equal independent workflow reads remain usable and targeted
  token-authorized results cannot roll global workflow state backward. Chat
  history revisions are monotonic, and stale authorization, catch, and cleanup
  paths cannot repaint or restore older patient projections.
- **Follow-through authorization eviction and offline projections.**
  Authorization loss now also scrubs hidden follow-through dialog copies,
  guidance, forms, intent bodies, focus, and inert state before invalidating
  late responses. Transient offline or aborted refreshes retain the last
  authoritative Today and visit-linked rows as visibly stale read-only
  snapshots, preserve action-scoped drafts in memory, keep accepted assessment
  actions accepted, and re-enable mutations only after fresh tokens reload.
- **Follow-through action intent ownership.** Generated acceptance, manual and
  visit-linked creation, lifecycle, edit, outcome, and filter controls share one
  in-flight mutation owner before selection epochs or mutation IDs can change.
  Duplicate or competing clicks cannot allocate or fetch, saving dialogs remain
  non-dismissible, and only an explicit ambiguous-request retry reuses the exact
  mutation. Authoritative reload completion now revalidates mutation, patient,
  action, and request identity after every await, so nested authorization/hard
  eviction and stale authorization responses cannot announce success, clear a
  draft, restore focus, repaint evicted data, or unlock a newer owner. Targeted
  visit/action responses must also satisfy non-regressive workflow revision
  bounds before changing the shared cache.
- **Late appointment responses and authorization PHI teardown.** Appointment
  mutations now validate their patient-data and visit-selection epochs before
  changing workflow/profile revisions, visit caches, retry state, drafts, or
  rendered content. Late visit A responses cannot repaint visit B or trigger
  success cleanup. Authorization eviction now scrubs appointment titles,
  clinician/location metadata, visit and decision options, statuses, dynamic
  tab content, form values, drafts, retry intents, and dialog references while
  safely resetting focus and inert state. Ordinary offline failures continue to
  preserve the caregiver's in-progress draft for explicit retry.
- **Generated-question revision redaction.** A clinical revision now removes
  generated appointment choices from browser cache and both Questions surfaces
  before the authoritative reload. Offline, stale, revisionless, and late
  responses show only a generic retry state without prior text, metadata,
  priority styling, acceptance tokens, or Add controls, while manual drafts and
  accepted visit snapshots remain intact.
- **Appointment decision controls and phone targets.** Decision actions now match
  the server lifecycle: only active decisions offer immutable successor
  correction, needs-confirmation decisions offer confirm/retract, and terminal
  decisions remain read-only history. At 360px, Move/rank controls retain at
  least 44px targets, visible keyboard focus, wrapping, and no horizontal
  overflow without enlarging their desktop presentation.
- **Mutation replay identity and immutable results.** Layer 2 and alert-resolution
  idempotency is now bound to endpoint, operation, target, and the complete
  accepted request, including CAS/source tokens. Unsupported fields are rejected
  before replay lookup; cross-endpoint, cross-target, or changed-payload reuse
  returns `409`. Exact retries return the original endpoint-shaped item, links,
  tokens, and revisions without another save, audit event, or revision increase,
  even after later edits. Result hashes and owner/link checks fail closed on
  malformed stored snapshots. Legacy alert requests without a mutation ID remain
  compatible through a deterministic ID in a client-inaccessible namespace.
- **Profile-save commit semantics.** Atomic replacement of
  `patient_profile.json` is now the explicit commit point. Failures writing or
  replacing the profile still fail the request without committed workflow
  state, while post-commit `.profile-initialized` maintenance is best-effort,
  path-free in logs, and cannot make a successful mutation appear failed.
  Missing markers are repaired after a valid profile load, and stale markers do
  not block snapshot/backup recovery or permit duplicate initialization.

### Operations
- Profile-load recovery now relies only on deterministic schema v15 migration
  and normal validation/default materialization. Operators must not add empty
  treatment source IDs, map generated rows by wording/order, use `/api/status`
  as a treatment/symptom fallback, or reset an existing null/invalid revision.

### Added
- **Deterministic visit recap and safe export.** The appointment workspace now
  has a fourth shared Recap tab for in-progress and completed visits. One
  authenticated/no-store visit-token CAS projection assembles exact
  provenance-labelled questions/answers, current decisions, visit-linked
  follow-ups, related resolved-alert outcomes, and unresolved items with both
  revisions plus a semantic recap token. Copy, generic UTF-8 text download, and
  print use only that accepted snapshot; newer authority disables export before
  refresh, offline content remains visibly stale/read-only, and auth/hard
  failure scrubs visible and hidden recap data. Planned visits are unavailable
  until started, while cancelled visits show a non-exportable administrative
  state. Viewing or exporting never mutates the profile, invokes a model, or
  creates a recap artifact.
- **Accessible structured Resolve alert dialog.** Active alerts now open one
  responsive desktop/phone dialog with optional provenance-labelled outcome and
  mutually exclusive no-link, existing-follow-up, safe inline-follow-up, or
  current-visit/eligible-decision modes. Existing links submit stable IDs only;
  blank outcomes are omitted; inline text is caregiver-authored treating-team
  follow-through rather than treatment or eligibility advice. Success waits for
  authoritative status/action/visit convergence, removes the old alert copy,
  retains sibling alerts, and renders only the bounded returned confirmation.
- **Today durable follow-through workflow.** Today now has one responsive
  caregiver-action surface with Active, Completed, Cancelled, and All filters,
  safe manual task creation, current generated-action acceptance by opaque
  source ID/token only, owner/due edits, backend-valid lifecycle controls, and
  required typed completion/cancellation outcomes. Generated, manual,
  visit/decision/alert provenance and caregiver-reported or
  clinician-attributed unverified outcomes remain explicit without promoting
  administrative or generated text into clinician facts. Stable-ID/full-token
  CAS, one-intent mutation IDs, exact explicit retry, strict conflict reloads,
  independent workflow/clinical revision handling, action/PHI response epochs,
  complete hard eviction, draft-only offline retention, keyboard dialogs, and
  44px overflow-safe phone controls prevent stale copies and late responses from
  changing the visible action.
- **Responsive appointment working mode.** Questions now includes visit
  preparation and one focused desktop/phone workspace for current generated or
  manual question snapshots, atomic pin/rank ordering, answered versus explicitly
  unknown clinician-attributed capture, immutable decision successors/lifecycle,
  and visit-linked resulting follow-ups. Imported appointment choices are
  limited to active/linkable bounded projections, stale generated question text
  is withheld, and every caregiver capture is visibly labelled
  caregiver-entered, clinician-attributed, and unverified. Stable target tokens,
  one-intent mutation IDs, profile/workflow revision handling, visit/PHI epochs,
  offline draft preservation, conflict reloads, focus trapping, and narrow-phone
  controls prevent stale or late responses from repainting the active visit.
- **Durable caregiver follow-through backend.** Schema v8 adds independent
  workflow revisioning, accepted/generated action snapshots, visit working
  records with ordered question snapshots, explicit unknowns, caregiver-entered
  clinician-attributed decisions/answers, structured outcomes, and append-only
  mutation audit. Stable target tokens and idempotency keys allow unrelated
  workflow edits while stale targets return `409`; administrative bookkeeping
  no longer stales clinical artifacts, while new clinical capture and alert
  resolution still invalidate every revision-bound generated context. Alert
  resolution can atomically record an outcome/link a follow-up or decision
  without changing sibling alerts. No generic review inbox,
  autonomous treatment instruction, database, or scheduler is introduced.
  Generated summary actions and questions are now acceptable only from an
  explicitly current, fully identified generation with an exact source token;
  generationless or migrated legacy content remains visible as stale provenance
  until regenerated and cannot create workflow records.
- **Scoped document reconciliation and correction.** Every retained feed job now
  opens its own profile-backed receipt showing exact additions, old-to-new
  updates, conflicts/no-ops, immutable source identity/time, and verified,
  missing, or invalid evidence. Caregivers can correct or remove an extracted
  value and can atomically undo that document's direct structured changes.
  Target-level compare-and-swap checks allow unrelated later edits but reject
  changed affected facts with `409`; source bytes/text and append-only audit
  history remain intact. No global review inbox, unread count, or acknowledgement
  was introduced.
  Full-row CAS now detects later alert resolution/clinical row edits, identical
  corrections are byte-for-byte no-ops, and undo audit snapshots preserve
  distinct before/after values.
- **Claim-level and Patient evidence.** Key assessment claims and actions now
  resolve only server-validated evidence-catalog IDs to exact authenticated
  source spans; missing and invented references are labelled explicitly. Patient
  now includes progressive imaging and document/source history with receipt and
  source links, without exposing storage paths.
  Document-only legacy history remains visible even without a source index.
  Source-dependent clinical alerts are retained but deactivated after correction
  or undo.
- **Caregiver safety and accessibility hardening.** Processing status is now
  `Processing`, `Idle`, or `Unavailable`, separate from assessment freshness.
  PRRT is presented as potential fit and trials as items to discuss, not
  definitive eligibility or matching; missing DOTATATE is no longer
  automatically the top action. Dialogs trap focus and inert the background,
  feed tabs support arrow/Home/End keys, mobile controls meet 44px targets,
  badges/secondary text have stronger contrast, empty submissions show inline
  validation, and failed loads leave terminal retry states instead of indefinite
  Connecting/Loading placeholders.
  Stale summaries/actions/PRRT screening, superseded generated questions, and
  corrected feed reports are withheld from current UI/model contexts while their
  audit artifacts remain stored. Receipt mutation controls are dirty-checked,
  disabled while pending, and late responses cannot overwrite another job panel.
  Feed/digest/deep-sweep reports and chat results now carry profile-revision
  dependencies; profile-derived alerts carry job/revision dependencies and
  expire from active contexts after later clinical changes. Receipt system-field
  synchronization preserves correction→undo while caregiver alert resolution
  still conflicts. Screening claim sanitization is polarity-neutral and replaces
  the full assertion rather than retaining definitive inclusion/enrollment text.
  Summary generation now runs after feed/digest clinical state commits and saves
  as derived-only at the same effective revision, preserving active alerts.
  In-tab chat history is profile-revision bound and cleared/rejected on mismatch.
  Alert resolution uses stable schema-v4 IDs plus semantic token/revision CAS,
  stales dependent summaries/questions, and cannot resolve a reordered row.
  Treatment imperatives are replaced wholesale with treating-team confirmation
  wording while factual past treatment history remains unchanged. Submitted-job
  activation also participates in the task-selection epoch protocol.
  Schema v5 adds durable/source/profile-snapshot alert lifecycles and
  treatment-classification revision identity. Durable ingestion/trial alerts
  survive unrelated revisions and document undo; source/snapshot conclusions
  follow their declared dependencies. Classification rejects empty, partial,
  extra, or collapsed-distinct output and every consumer visibly falls back to
  raw treatments whenever classification is stale or fails.
  Stale summary responses now preempt open action-feedback editors; open
  report/result panels revalidate on revision/task polling, clear copy state, and
  show source-correction/profile-change/unverifiable-legacy reasons accurately.
  Successful receipt mutations retain the authoritative receipt through detail
  refresh failure. Status/auth failures clear rendered status-derived PHI and
  client caches instead of leaving prior patient data visible.
  Hard loader/auth failures now evict PHI across reports, receipts, chat,
  feedback, modals, feed text, patient projections, and filters; missing selected
  tasks cannot resurrect cached content. Generated-alert containment covers
  recommendation/need/plan/gerund and embedded-colon treatment directives plus
  candidate/fit/indication/benefit assertions while preserving explicit
  historical passive facts and containing mixed historical/live clauses.
  Schema v6 adds stable treatment source/component mappings and
  ID/token/revision CAS so composite edits preserve siblings. Lossless
  classification recognizes common NET surgical therapies and rejects mixed
  recognized/unknown compounds before mappings can be edited.
  Schema v7 extends that invariant to unidentified residual therapy content,
  including transition narratives, and the mutation endpoint independently
  verifies exclusive component coverage. It also sanitizes source-less legacy
  generated alerts, snapshot-binds them instead of making them durable, and
  safely migrates nullable legacy patient scaffolding. Resolving an alert now
  advances the generated-context revision so chat, reports/results, summaries,
  and questions cannot retain the unresolved-alert context. Authorization
  eviction also clears and hides the assessment freshness/source banner, and
  summary epoch guards prevent auth failures or late responses from repainting
  that patient-derived projection.
- **Today-first responsive caregiver workspace.** Replaced the duplicated
  desktop/mobile surfaces with shared **Today**, **Patient**, **Questions**, and
  **Activity** views while retaining the warm green/amber visual identity.
  Assessment freshness and newer source data are now prominent, recommended
  actions are task cards, and every workflow remains available on phones through
  fixed bottom navigation. Generic unread review and acknowledgement were
  removed; **Today** now shows only the exact net-new trials and research papers
  from the latest discovery batch, with those records labelled **New** in the
  tracked lists. Web and CLI runs share canonical ID tracking, malformed IDs
  are excluded, and returning tabs refresh the latest batch. API failures now
  distinguish sign-in, allowlist, offline, and
  retry states instead of looking like an empty patient record. Activity
  polling stays at three seconds only while work is active, backing off to 30
  seconds when idle and 60 seconds while hidden. Controls use semantic buttons,
  labelled dialogs, visible focus treatment, larger touch targets, and
  consistent English labels. Action dismissal now carries the assessment
  revision and expected action text; stale feedback is disabled in the UI and
  rejected with `409` before it can dismiss a different recommendation.
- **Operational and security hardening.** Gunicorn is deliberately pinned to one
  worker because job state and execution are in-process. Feed work now has an
  independent bounded executor (`FEED_WORKERS=1`, `FEED_QUEUE_SIZE=2`) so uploads
  cannot be starved by the bounded general executor (`JOB_WORKERS=2`,
  `JOB_QUEUE_SIZE=6`); configured workers/queues are clamped to 1–4/0–50. Full
  queues return `429` with `Retry-After` (default 10 seconds), admission happens
  before durable job creation (no ghost job), and duplicate active digest,
  deep-sweep, and summary runs return `409`.
- **Durable asynchronous job contract.** Feed, digest, deep-sweep, chat,
  appointment-question generation, and manual summary generation return `202`
  plus a job ID. The SPA polls job status and obtains reports/results only from
  the individual job endpoint; reports and result payloads are artifacts, not
  embedded in `jobs.json`. Restarted queued/running work is marked
  `interrupted` with re-submit guidance. Shutdown is best-effort (30-second
  Gunicorn graceful limit; worker joins are bounded), not durable execution.
- **Contained PDF extraction.** `pdfplumber` now imports only in
  `agent/pdf_extract_helper.py`, a child interpreter with a 30-second hard
  timeout, 100-page/1,000,000-character defaults, isolated standard streams and
  environment, output validation, and Linux CPU/address-space/file-size/file-
  descriptor limits (`PDF_MAX_MEMORY_MB=384`). Windows retains the hard
  subprocess timeout and output limits but cannot apply Unix `setrlimit`.
- **PHI-safe job/artifact lifecycle.** Newly written jobs use an allowlisted
  metadata schema and generic errors; job-runner logs expose job IDs, safe
  codes/types, and retry guidance rather than document text, prompts, or
  traceback. Legacy retained job records are not rewritten.
  Reports/results are loaded on demand through traversal-safe roots. Job,
  report, and unreferenced-source retention now have age/count settings; source
  directories indexed by the profile remain protected. Retention is
  best-effort pruning, not guaranteed secure deletion, and does not remove
  backup/provider copies.
- **API authorization boundary.** Flask exempts only `/api/health` and
  `/api/live`; every other `/api/*` route requires a valid App Service Easy Auth
  principal when hosted. App Service must also configure those two probe paths
  as anonymous if they need to be externally public.
  `AUTH_ALLOWED_PRINCIPAL_IDS` optionally applies an exact
  comma-separated allowlist. Local API access is denied unless
  `ALLOW_LOCAL_AUTH_BYPASS=1` is explicitly set. State-changing requests also
  require same-origin `Origin` when present. Health exposes PHI-free aggregate
  active/queued/feed counts only.
- **Bounded upstream calls and gated deployment.** Anthropic defaults to
  5-second connect, 120-second read, 10-second write, 5-second pool, and
  150-second HTTPX default timeout plus one SDK retry (clamped to 0–2); retries
  can make wall-clock duration longer.
  PubMed/ClinicalTrials.gov calls use explicit 5-second
  connect and 12/15-second read limits and no application retry. Runtime/dev
  dependencies and the setuptools build requirement are exactly pinned. The
  release includes `.deployment`, enabling Oryx build-on-deploy against those
  pinned requirements. Deployment rejects dirty trees, gates on pytest, ruff,
  and gitleaks, polls the exact asynchronous Kudu deployment, verifies package
  SHA-256, and checks the authenticated SCM application process plus PHI-free
  `/api/health` critical fields and packaged commit. Only then is the package
  promoted to `last-known-good`; arbitrary 401 responses never pass. Rollback
  verifies and redeploys that exact package and repeats both readiness checks.

- **Profile schema versioning and deterministic migrations.**  A new
  `schema_version` field (integer, current value 1) appears at the top level of
  every profile.  `agent/migrations.py` provides append-only, idempotent
  migrations; each migration's `applied_at` timestamp is recorded in
  `_migration_log` and preserved on subsequent loads.  `load_profile` runs
  migrations before returning the profile; loading a current-version profile is a
  fast-path with no mutations.  Migrations only add structural defaults, never
  infer clinical facts.

- **Robust corrupt-profile recovery.**  `load_profile` now distinguishes three
  failure classes: (1) transient I/O error → `IOProfileError`, no quarantine;
  (2) invalid JSON or structurally invalid shape → quarantine forensic copy to
  `{DATA_DIR}/quarantine/`, atomically restore from the newest valid pre-save
  snapshot (with optional `.sha256` sidecar validation) or daily backup;
  (3) no valid candidate → `CorruptProfileError`.  Recovery is under the
  cross-process lock.  No empty patient is ever returned; first-run missing
  profile still creates a default.  `save_profile` now rejects structurally
  invalid data (non-dict, string patient, non-list collection) with `ValueError`.

- **Rotating snapshot sidecar hashes.**  `backups.rotating_snapshot` writes an
  optional `.sha256` sidecar alongside each snapshot; `_validate_candidate`
  checks the sidecar when present.

- **Explicit safe recovery API** (`agent/recovery.py`).  Exports
  `quarantine_profile`, `find_recovery_candidates`, `restore_from_candidate`,
  `recover_profile`, and `NoRecoveryCandidateError`.  Operator runbook in
  `docs/operating_manual.md §9`.

- **Enhanced `/api/health` readiness probe.**  Now reports: `schema_version`,
  `profile_status` (`ok|missing|invalid_json|invalid_shape|io_error`),
  `stale_job_count`, `interrupted_job_count`, `newest_snapshot_age_seconds`,
  `newest_backup_age_seconds`, `jobs_healthy`.  No PHI, paths, or secrets in
  response.  Returns 503 when data dir is not writable or profile is
  corrupt/unreadable. Returns 200 degraded when the newest backup lags the
  current profile, or
  jobs were interrupted.

- **Liveness route `/api/live`.**  Returns `{"alive": true}` 200 unconditionally.
  Use for k8s/Azure liveness checks separate from readiness.

- **Startup job reconciliation.**  `_load_jobs` marks any job with `status`
  `queued` or `running` as `interrupted` (with `finished_at` and `retry_guidance`
  message), persists the change once, and strips the `traceback` field from
  interrupted records.  A corrupt `jobs.json` (invalid JSON or non-list) is
  atomically quarantined; `_jobs_healthy` is set `False`; `/api/health` discloses
  `jobs_healthy: false` without exposing job data.

- **56 new no-network tests** covering migrations (idempotence, unknown field
  preservation, backfill, timestamp immutability), recovery (quarantine, sidecar
  hash validation, snapshot skip, no-candidate error, transient-IO guard),
  health (503 on corrupt, no PHI, liveness, job counts), and job reconciliation.

### Added
- **Evidence provenance and reviewability.** Every feed now receives a unique
  source-document ID and ingestion timestamp; immutable original/extracted
  artifacts are atomically stored with SHA-256 and length metadata. Intake
  requires source quotes, validates them deterministically, stores exact spans
  or explicit missing/invalid status, and exposes traversal-safe authenticated
  no-cache source/evidence endpoints. Summary responses/UI now include confidence,
  rationale, revisions, freshness, generated time, and evidence affordances.
- **Clinical review state.** Judgments now support scope, active/superseded/
  needs-review lifecycle, review/expiry dates, supersession, and update
  timestamps. Structured feedback records target/item, assessment, notes,
  outcomes, and timestamps without silently changing clinical facts. Asked AI
  questions survive regeneration with deterministic deduplication.
- **Deep-sweep verification metadata.** Final synthesized output receives
  deterministic PMID/NCT verification and a footer; stop reasons, token limits,
  and truncation are explicit, with raw reports retained on synthesis failure or
  truncation. Deep-sweep remains read-only.

### Fixed
- **Phase 1 correctness containment.** PDF uploads now preserve binary fidelity;
  all profile transactions serialize across threads and processes and use unique durable atomic-write
  temporaries; feed/digest refresh revision-bound summaries without discarding
  successful ingestion when summary generation fails; stored UI values are
  escaped and responses carry CSP/security headers. ClinicalTrials.gov phase,
  eligibility, polling, and summary selection are corrected; biomarker trends
  now separate incompatible units and disclose comparison caveats; every
  decision-support LLM path receives current oncologist judgments. Manual
  symptoms now receive the required `added_at` stamp. Bookkeeping-only writes no
  longer invalidate a current clinical summary, and research-item ingestion uses
  second-resolution timestamps so same-day additions remain visible as new.
- **Ask Claude replies now render Markdown.** The chat panel previously displayed
  the assistant's Markdown as raw text — headings (`##`), GitHub-style tables,
  `**bold**`, and bullet lists leaked through as literal characters (only newlines
  were converted). Added a small, self-contained, XSS-safe Markdown renderer
  (headings, tables, ordered/unordered lists, bold/italic, inline code, fenced
  code blocks, blockquotes, links, horizontal rules) for assistant messages, plus
  scoped chat styles. User messages stay plain text; HTML is escaped before any
  formatting is applied and `javascript:` links are neutralised.

### Added
- **`added_at` ingestion stamps + accurate "new" counter.** Every item written to
  the counted profile collections (biomarkers, imaging, documents, alerts,
  symptoms, clinical judgments) now carries an `added_at` wall-clock timestamp set
  at the moment it is recorded. The dashboard "Mark all read · N new" counter
  (`_count_new`) keys on `added_at` first, falling back to the clinical date for
  legacy items. Previously the counter compared each item's *clinical* date to the
  acknowledgement watermark, so a back-dated item (e.g. an old document fed today)
  could be silently missed from the "new" count. `trials_tracked` /
  `literature_watched` already used `date_added` and are unaffected.
- **Appointment extraction + guaranteed timeline events.** Intake now extracts
  scheduled/planned events (follow-up calls, appointments, scans, reviews) into a
  structured `appointments[]` field on the profile, and `generate_executive_summary`
  deterministically merges any *upcoming* appointment into the dashboard timeline
  (sorted nearest-first). Previously the timeline was an LLM-only, 6-item,
  re-ranked list, so a near-term event (e.g. a "14.7 follow-up call") could be
  silently dropped in favour of more distant items — now it can't.
- **Deterministic accuracy & robustness guards** (from the architecture review):
  - **Biomarker same-date trend guard** (`analyze_biomarker_trends`): readings
    sharing a date are excluded from slope arithmetic and surfaced as a
    `data_quality_caveats` note instead of producing a spurious trend (fixes the
    observed 8-same-date 5-HIAA "+38%" artefact). Same-date readings are never
    deleted — only flagged for disambiguation.
  - **Loud intake-failure path**: when a document can't be parsed into JSON,
    intake now does one repair retry; if it still fails, the document is stored
    raw AND an **urgent alert** is raised so the caregiver knows its contents are
    invisible to analysis (previously a silent "unstructured" fallback).
  - **Intake biomarker dedup**: exact `(marker, date, value)` triples are no
    longer double-logged when a document is re-fed.
  - **Executive-summary brevity retry**: on a `max_tokens` truncation the summary
    is regenerated once with a concision instruction before falling back to the
    error placeholder.
  - **Deterministic reference verifier** (`agent/verify.py`): every PMID/NCT ID in
    an orchestrator report is existence-checked against PubMed / ClinicalTrials.gov;
    unresolved IDs are flagged inline under "⚠ Reference verification" so a
    fabricated citation can't pass as real. Registry outages mark a reference
    "unavailable", never "unverified".
  - **Trial-status poller** (`agent/trials_poll.py`, `POST /api/trials/poll`, and
    each digest run): the tracked trials are polled by NCT ID; an `overallStatus`
    change writes a `status_history` entry and a high-priority alert — the
    highest-value caregiver event class is now deterministically detected instead
    of depending on the LLM choosing to re-search a suppressed trial.
  - **Mutating-job serialization** (`agent/serialize.py`): document-feed and
    digest jobs now run through one in-process mutating slot, so a concurrent
    feed+digest can no longer silently lose one job's extracted data
    (last-writer-wins on the single JSON profile). Read-only work (deep-sweep,
    chat) bypasses it. A queued job shows "waiting for current job".
  - **Pre-save rotating snapshots** (`agent/backups.py`): every `save_profile`
    first snapshots the prior state (last 20 kept), so a bad write/merge is
    recoverable to the immediately-prior state rather than yesterday's backup.
  - **Prompt caching** (`agent/llm.py` `cached_system`/`cached_tools`): the stable
    system+tools prefix of the orchestrator tool-loop, the deep-sweep, and the
    chat system prompt are marked cacheable (`cache_control: ephemeral`), so
    repeated prefills are reused at ~0.1x input cost with lower latency. Fully
    behaviour-neutral; the 5-minute TTL covers a loop or chat session.
  - **`INVARIANTS.md` + contract-conformance tests** (`tests/test_invariants.py`):
    load-bearing rules and every machine-parsed key/enum are documented and pinned
    so a future edit that renames a contract key or adds a save to the read-only
    deep-sweep fails CI — insurance for the handoff to smaller teams/AI sessions.
  - **Test-gated deploy script** (`scripts/deploy.ps1`): refuses to build/ship the
    zip unless pytest/ruff (+gitleaks) pass, retains the previous zip for a
    one-command `-Rollback`, and health-checks after deploy.
  - **Extraction eval-harness scaffold** (`scripts/eval_harness.py`): scores intake
    recall/precision against a golden set so model/prompt changes become
    measurable; ships a synthetic sample (real PHI cases live on the mount).
  - **Optional quote-anchored intake verification** (`INTAKE_VERIFY`, off by
    default): a second extraction pass that adds only items whose verbatim source
    quote is found in the document (monotonically safe); enable once the eval
    harness shows a recall lift.

### Changed
- **All six agent system prompts rewritten** (Fable 5 audit, tuned for Opus 4.8).
  Highlights: intake JSON schema is no longer interrupted by prose and gains an
  anti-fabrication + date-disambiguation rule; the orchestrator swaps its rigid
  A–E script for decision criteria + interleaved-thinking budget discipline and a
  hard "cite only tool-returned PMIDs/NCTs" rule; exec_summary forbids inventing
  an NCT for `best_trial` and tightens per-field brevity to avoid truncation;
  classify makes date-based reasoning primary; questions anchors every item to a
  profile datum; chat gains explicit decision-support framing and a red-flag rule.
  Output contracts (JSON keys/enums, report section headers) are unchanged.
- **Prompt templating switched to `agent.llm.render_prompt`** (`[[SENTINEL]]`
  placeholders) for the JSON-schema prompts, so literal `{`/`}` no longer need
  escaping. Runtime injection points (patient context, summary, clinical
  judgments, region filter, output language) are preserved; a render-safety test
  suite asserts no placeholder ever leaks into a live prompt.

### Fixed
- **Safety: clinical judgments now override data-derived conclusions in all four
  agents that receive them.** Previously only the orchestrator and exec-summary
  framed the oncologist's `clinical_judgments` as hard constraints; the **chat**
  and **questions** agents included them only as context, so a judgment (e.g.
  "trial X is ruled out") could be under-weighted. A single shared
  `CLINICAL_JUDGMENTS_OVERRIDE` block (in `agent/judgments.py`) is now wired into
  both, instructing the model to treat judgments as ground truth that overrides
  the raw data. Decision-support only; the oncologist still reviews all output.

### Added
- **Ensemble deep-sweep** (`agent/deep_sweep.py`, `POST /api/deep-sweep`, and a
  header **⁂ Deep sweep** button). An on-demand, high-effort pre-appointment
  research pass that runs several strong models (default **Claude Fable 5 +
  Claude Opus 4.8**) with the routine dedup/suppression rules relaxed, then a
  synthesis pass (default Opus 4.8) **unions** their reports — every unique,
  grounded catch from either model is preserved and disagreements are surfaced
  for clinician confirmation. Rationale: an A/B on the live record showed Fable 5
  uniquely spotting cross-trial connections while Opus 4.8 uniquely caught a
  −20% platelet drop; the union beats any single model.
  - **Read-only by design:** each model runs against a deep copy of the profile
    and the job never calls `save_profile`, so re-surfaced papers/trials/alerts
    do not pollute the tracked lists or contaminate future runs. The report is
    saved to `/home/data/reports/report_deepsweep_*.md`.
  - Configurable via `ANTHROPIC_DEEPSWEEP_MODELS` and
    `ANTHROPIC_DEEPSWEEP_SYNTHESIS` app settings. Cost is shown as a footer on
    each report (~$1–2/run at current pricing). Decision-support only.

### Changed
- **Anthropic model upgraded** from `claude-sonnet-4-6` → `claude-sonnet-5`
  across all agent roles (intake, orchestrator, exec_summary, questions,
  classify, chat). Sonnet 5 brings a 1M-token context window and up to
  128k output tokens. The code default lives in `agent/config.py`; the
  model actually used in production is controlled by the `ANTHROPIC_MODEL`
  (and optional per-role `ANTHROPIC_MODEL_*`) app settings on the webapp —
  set those to `claude-sonnet-5` to complete the rollout.
- **Adaptive thinking enabled** on every agent call (`thinking={"type":
  "adaptive"}`, Sonnet 5's default). Responses now carry leading `thinking`
  blocks, so parsing uses a new `agent.llm.first_text()` helper that returns
  the first `text` block instead of assuming `content[0]`.
- **Dropped `temperature=0`** from the exec-summary, classify, and
  question-generation calls — temperature must be unset (or 1) when thinking
  is enabled.
- **Raised `max_tokens`** across all agents for thinking headroom
  (exec_summary 8000→16000, orchestrator 4096→12000, others 2–3×).
- **`anthropic` SDK floor raised** to `>=0.115` for native adaptive-thinking
  support.

## [0.8.0] — 2026-05-13

### Added
- `SECURITY.md` describing the GitHub Security Advisory reporting flow,
  scope, and the hardening already in place.
- `.github/pull_request_template.md` with a doc-update checklist (from
  the `AGENTS.md` policy) and a public-repo safety checklist (no PHI,
  no infra names, no personal email).
- **Tests for the eight previously-uncovered agent modules**:
  `chat`, `classify`, `exec_summary`, `intake` (already had treatment-
  matching tests; this adds end-to-end and synonym pinning), `judgments`,
  `llm`, `orchestrator`, `questions`. The suite grows from 61 → 103
  tests, all under 10 s, no network, no API key.
- `tests/_llm_fake.py` shared helper for the in-memory LLM stub. Uses
  a context-manager `patch_llm` that installs a per-call handler on the
  live `agent.client` instance and restores the previous value on exit.
- **Symptoms log.** First-class `symptoms[]` array on the patient
  profile, bridging objective biomarkers and oncologist judgments with
  the caregiver's day-to-day record of how the patient feels.
  - New `Symptom` pydantic model: `id`, `date`, `symptom`,
    `severity` (1–5), `note`, `related_treatment`, `source` (`manual`
    or `ai`). Extras allowed.
  - The intake agent extracts patient-reported symptoms when documents
    mention them (e.g. "patient reports grade-2 diarrhea since starting
    lanreotide") and appends them to the profile with `source="ai"`.
    Same-day same-name entries are deduped to prevent re-feeding a
    document from double-logging.
  - The orchestrator now runs one targeted side-effect-management
    literature search when active treatments correlate with recent
    symptoms.
  - `get_patient_summary` shows the five most-recent symptoms, so every
    downstream agent (orchestrator, exec_summary, chat, questions) sees
    them automatically.
  - The chat prompt includes a SYMPTOMS section listing every recorded
    symptom — Ask Claude can now answer "when did the nausea start?"
    or "is the fatigue getting worse?".
  - REST API: `GET /api/symptoms`, `POST /api/symptoms`,
    `PATCH /api/symptoms/<sid>`, `DELETE /api/symptoms/<sid>`.
  - **Sidebar UI** under *Active alerts*: compact inline add row
    (symptom name + severity 1–5 + optional note), recent-entry list
    with date / color-coded severity dot / AI tag / delete button.
  - `tests/test_symptoms.py` (7 tests): schema validation including
    out-of-range severity, default-profile shape, intake auto-capture
    round-trip, `_persist_symptoms` dedup invariants, patient-summary
    surfacing.
- **"Mark all read" delta indicator (R9).** New
  `acknowledged_at: str | None` field on `PatientProfile`. New
  endpoints `GET /api/changes` and `POST /api/changes/acknowledge`
  return per-category counts of items dated after the acknowledgment
  timestamp (biomarkers, imaging, documents, trials, papers, alerts,
  symptoms, judgments, plus a boolean for whether the executive
  summary has been regenerated since last ack). Header gains a
  *✓ Mark all read · N new* pill which hides at zero and lists the
  per-category breakdown on hover. Polled alongside `/api/status`
  every 3 s.
- `tests/test_changes.py` (5 tests): no-ack returns all-new, ack
  zeroes the counts, items dated after ack re-increment, executive
  summary regenerate-after-ack flagged, items pre-ack not counted.

### Fixed
- `tests/conftest.py::agent` fixture now also pops every `agent.*`
  submodule before re-importing, so tests that imported `agent.X` at
  module top during pytest collection (which races the
  `_stub_anthropic` session fixture) get a fresh fake LLM client. The
  previous behaviour silently let a real Anthropic client persist
  across the stub, causing 401s in tests that rely on canned LLM
  responses.

### Changed
- **Chat now sees the full clinical record, not just recent slices.**
  `build_chat_system` previously capped biomarkers at 30 entries and
  imaging at 10, and never included the documents array. The chat could
  not reliably answer "find that CT report from August" — it would
  either drop the document from context or hallucinate. The prompt
  builder now includes every biomarker, every imaging study, and every
  document (date + type + summary + key_findings; raw_text intentionally
  excluded). For a 100-document profile this adds ~30 KB to the chat
  prompt, well within the model's context window.
- The chat system prompt now explicitly directs Claude to consult the
  DOCUMENTS / BIOMARKERS / IMAGING sections when asked about specific
  past content, and `docs/operating_manual.md §6` is updated to describe
  the broadened search behaviour.
- `docs/profile_schema.md` regenerated to document the new
  `symptoms[]` list.

## [0.7.0] — 2026-05-13

### Changed
- **Patient demographics are now read from the profile, not hard-coded.** Five
  agent modules (`chat`, `orchestrator`, `exec_summary`, `classify`, `questions`)
  previously embedded the patient's age, sex, primary site, location, and the
  caregiver relationship directly in their system prompts. They now compose
  that context at runtime from new optional fields on `patient`
  (`location`, `caregiver_relationship`, `language`, `regions_of_interest`)
  via helpers in `agent/profile.py` (`build_patient_context`,
  `get_caregiver_relationship`, `get_output_language`,
  `get_trial_region_filter`). The repo itself ships no patient-identifying
  details; the deployed profile on Azure Files supplies them at runtime.
- **Question generator is now language-agnostic** — drives the output
  language from `patient.language` (defaults to English). Setting any
  non-English value reproduces the previous localized-output behaviour.
- **Orchestrator trial-search region filter** is driven from
  `patient.regions_of_interest` instead of a hard-coded country list.

### Removed
- `net_care_agent_documentation.docx` (operator-only doc that contained
  patient-identifying details). Operator documentation now lives in a
  private runbook outside the repo; `*.docx` files are gitignored.
- `.vscode/settings.json` (contained the Azure subscription ID and the
  exact App Service deploy target). `.vscode/` is now gitignored.

### Docs
- Owner email, Azure subscription ID, and concrete Azure resource names
  (resource group, App Service site, Key Vault, storage account, Azure
  Files share, Recovery Services Vault) replaced with `<placeholder>`
  tokens across `HANDOFF.md`, `README.md`, `AGENTS.md`, `CHANGELOG.md`,
  and `docs/architecture.md` so the repo is safe to publish.
- `docs/profile_schema.md` regenerated to document the new optional
  `patient.{location, caregiver_relationship, language, regions_of_interest}`
  fields.

### Public-readiness scrub round 2
- **Owner name removed from doc prose.** Operator-name guidance in
  `AGENTS.md`, `HANDOFF.md`, and `CHANGELOG.md` now refers to "the project
  owner's configured author name" instead of naming the owner. The author
  identity is still set in local `git config` (kept in the private
  operator runbook) — switch `user.email` to a `@users.noreply.github.com`
  address before the first public push so the email is never visible in
  `git log`.
- **Test names generalised.** `tests/test_relevance.py` renamed the
  ovarian-NET specific cases to primary-site-agnostic equivalents
  (`test_primary_site_net_is_relevant`,
  `test_generic_non_net_cancer_is_filtered`) so the test suite no longer
  encodes the patient's primary tumor site.
- **UI labels default to English.** `static/app.js` previously held a
  hardcoded Finnish translation table for category/status/stage/type
  labels. Those functions now pass values through unchanged; the file
  documents how to plug in a locale dict driven by `patient.language` if
  multi-language UI is wanted later.
- **Lab-prefix comment generalised** to "Nordic/European lab-name prefixes"
  rather than naming Finnish specifically (the regex itself was always
  generic).
- **Removed `static/index.legacy.html`** (116 KB Phase-4 pre-split
  snapshot). The associated `test_legacy_index_kept_for_rollback` test was
  also removed. Rollback was the only reason to keep this file in-repo;
  git history is the better place for that.

### Known gaps
- Prior commits (everything before the round-1 scrub commit) still
  contain the original patient-identifying strings in system prompts and
  the `net_care_agent_documentation.docx` blob. **Before flipping the
  repo to public, rewrite history** (e.g. `git filter-repo`) or push a
  single squashed snapshot to a fresh public repo and archive this one.



### Changed
- **Anthropic model upgraded** from `claude-sonnet-4-20250514` → `claude-sonnet-4-6`
  for all six agent roles (intake, orchestrator, exec-summary, questions,
  classify, chat). Set via `ANTHROPIC_MODEL` app setting on the webapp;
  `agent/config.py` default and `.env.example` updated to match so a fresh
  clone uses the same model out of the box.

### Fixed
- **`max_tokens` raised** in `exec_summary.py` (2000 → 8000), `intake.py`
  (2000 → 4000), and both `questions.py` paths (1200/2000 → 4000/8000) to
  accommodate Sonnet 4.6's longer JSON responses. Previously the executive
  summary failed with `Unterminated string starting at line 89 column 21`
  because the model response was truncated mid-string. Also added an explicit
  `stop_reason == "max_tokens"` guard in `exec_summary.py` that raises a
  clear `model response truncated at max_tokens` error if it ever recurs.

### Security / Resilience
- **App Service `httpsOnly`** flipped from `false` → `true` (HTTP requests now
  auto-redirect to HTTPS).
- **`ANTHROPIC_API_KEY` moved to Key Vault.** New Key Vault (RBAC-authorized,
  in the project's resource group); webapp uses a system-assigned managed
  identity with the **Key Vault Secrets User** role to resolve the secret
  via an `@Microsoft.KeyVault(SecretUri=…)` reference. Key is no longer
  visible in plain text in `az webapp config appsettings list` output.
  Rotation = update secret in Key Vault + restart webapp.
- **Storage hardened**: blob versioning enabled; blob and container
  soft-delete retention extended from 7 → **30 days** to match the Azure
  Files share backup window (file-share soft-delete remains 14 days,
  Recovery Services Vault daily backups remain 30 days).
- **Documentation** — `HANDOFF.md` added (single-file primer for porting the
  project to another AI assistant); `AGENTS.md` gained a Secrets section with
  the Key Vault rotation runbook; `docs/architecture.md` failure-modes table
  expanded to cover storage, HTTPS, and secret-leakage protections.

### Known gaps (not auto-fixable)
- App Service plan is **Basic (B1)** — does not support deployment slots or
  built-in App Service config backups. Upgrade to Standard (S1) if a staging
  slot or config backups become important.
- GitHub branch protection on `main` is **unverified** (no PAT available
  locally). Should require PR + block force-push + block deletion.

## [0.5.0] — 2026-04-29

### Added
- **Feed-document popover.** "📄 Feed" button in the header opens a floating
  dialog with the existing Paste-text / Upload-file tabs. Click backdrop or
  press **Esc** to dismiss; popover auto-closes after a successful submit so
  the new task is immediately visible in the activity log.
- **Clickable trial chip.** The "Best matched trial" NCT ID in the executive
  summary now links to `clinicaltrials.gov/study/<NCT_ID>` and opens in a new
  tab.
- `CHANGELOG.md` (this file) + `AGENTS.md` (assistant onboarding +
  doc-update policy).

### Changed
- **Unified main-column scroll.** Executive summary, timeline, and activity
  log now share a single scrollbar instead of two nested scroll regions. The
  timeline inside the exec summary is no longer clipped at 55vh.
- **Activity log surface.** Restored to a sensible `min-height: 220px` after
  the feed panel was removed from the inline flow.
- Documentation refresh (`README.md`, `docs/operating_manual.md`,
  `docs/architecture.md`) to match the new feed UX, the 3-file SPA layout
  (`index.html` + `app.js` + `styles.css`), and Easy Auth gating.

### Fixed
- Timeline header labels no longer overlap the today/event markers.
- Repo-local `git config user.name` was overriding the global; corrected
  to the project owner's configured author name and recent commits
  rewritten + force-pushed.

### Operations
- Recovered from a stuck `Compress-Archive`-based deploy that left
  `wwwroot` without the `agent/` package (gunicorn was crashing with
  `ModuleNotFoundError: No module named 'agent'`). Switched to a Python
  `zipfile`-based deploy script + Kudu `/api/zipdeploy`, which rebuilds
  `output.tar.zst` cleanly.

## [0.4.0] — 2026 Phase 6 (#4, #5, removed in #6)

### Added
- **Pydantic profile schema** (#4). All reads/writes of
  `patient_profile.json` go through validated models.

### Removed
- **APScheduler daily digest + ntfy push notifications** (#6, reverting #5).
  The scheduler complicated container restarts and ntfy added an external
  dependency for what is fundamentally a manual, on-demand workflow. Digests
  are now triggered exclusively by the **↻ Run digest** button in the header
  (or `POST /api/digest` from a cron of your choice).

## [0.3.0] — 2026 Phase 4 (#3)

### Changed
- **SPA split** — `static/index.html` was split into:
  - `static/index.html` (markup only)
  - `static/app.js` (all client logic)
  - `static/styles.css` (all styles)
- Static-file cache headers added so JS/CSS revisions invalidate cleanly.

## [0.2.0] — 2026 Phase 2 + 3

### Changed
- **Phase 2:** monolithic `net_agent.py` refactored into the `agent/`
  package (`config`, `llm`, `profile`, `intake`, `orchestrator`,
  `classify`, `exec_summary`, `questions`, `chat`, `cli`, `tools/…`).
  `net_agent.py` is now a back-compat shim.

### Added
- **Phase 3:** backend hygiene — atomic profile writes
  (`agent.io.atomic_write_text`), daily JSON backups with 30-day retention
  (`agent.backups.daily_backup`), `/api/health` endpoint suitable for
  App Service health probes, and a structured (text or JSON) log formatter
  in `agent.logging_config`.

## [0.1.0] — 2026 Phase 0 + 1

### Added
- Initial NET/Care Research Agent: Flask app, agent loop, PubMed +
  ClinicalTrials.gov tools, Anthropic Claude integration, single-page
  vanilla-JS UI.
- **Phase 0:** tooling foundations — `pyproject.toml`, `.env.example`,
  `Scripts/run_local.ps1`, `.editorconfig`.
- **Phase 1:** pytest scaffolding (38 passing, 1 xfail) with recorded
  HTTP fixtures for PubMed and CT.gov, a fake Anthropic client, and a
  temporary data directory — no network calls and no API key required.
- **Phase 5 + 6 lite:** ruff lint config, pre-commit hooks, Dependabot
  for pip + GitHub Actions, initial `docs/` (architecture, operating
  manual, profile schema).
