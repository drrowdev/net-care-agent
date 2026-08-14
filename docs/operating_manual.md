# Operating manual

Day-to-day workflows for the caregiver. All actions happen in the web UI at the
deployed URL or `http://localhost:8000` for local development.

Flask exempts the PHI-free `/api/health` and `/api/live` probes; all other
hosted APIs require App Service Easy Auth; its protected runtime environment
injects `WEBSITE_AUTH_ENABLED`.
Generic hosting variables without that explicit setting fail closed. Anonymous external probing also
requires App Service Easy Auth path exclusions. Local APIs are protected unless
`ALLOW_LOCAL_AUTH_BYPASS=1` is explicitly set in the local environment (as in
`.env.example`). Do not set that bypass in hosted configuration.

## How dates, times and numbers are displayed

Interface copy is English; every date, time and number is displayed in Finnish
convention, regardless of the browser's own locale setting:

| Recorded value | Displayed as |
|---|---|
| `2026-08-14` | `14.8.2026` |
| `2026-08` | `8/2026` |
| `2026` | `2026` |
| `2026-05 to 2026-08` | `5/2026 – 8/2026` |
| `2026-08-14T06:26:00` | `14.8.2026 09:26` |
| `12345` | `12 345` |

Times are always 24-hour, never AM/PM. Partial dates keep the precision that was
recorded — NET/Care never invents a missing day or month to complete a date.
Relative labels such as `5m ago` and `2h ago` stay in English.

Stored timestamps are written by the server as naive ISO strings on a UTC host,
so the interface reads a timestamp without a timezone as UTC and shows it in the
browser's local zone. A value already carrying `Z` or an offset is honoured as
written.

## Interface map

The desktop and phone layouts use the same five views, so every workflow is
available at every screen size:

- **Today** — global access/freshness, the expanded latest assessment/key
  concern/recommendations, bounded recorded update times plus active-alert
  count, treatment status, symptoms logged, follow-ups, appointment preparation,
  then lower-priority tracked research. The freshness banner holds the only
  assessment action at every state: **Refresh assessment** beside **New
  information since this assessment**, **Regenerate assessment** beside **Up to
  date** for a voluntary rerun, and **Generate assessment** when none exists.
  The heading and hidden stale body do not repeat it. Recent-update row actions
  use the same secondary-button treatment
  as the card action at desktop and phone widths. Today creates no unread state.
  Latest document import is selected by ingestion time across all active
  documents, independently of the clinical document date.
- **Patient** — profile snapshot, treatments, complete biomarker history,
  alerts, symptoms, imaging history, and immutable document/source history.
- **Research** — every current trial/paper occurrence and every open/closed
  caregiver consideration in exact server order.
- **Appointments** — appointment questions, visit working mode, and clinical notes
  from the treating team.
- **Activity** — digest/deep-sweep controls, processing status, and reports.

If an API request is unauthorized, forbidden, offline, or otherwise fails, the
page shows an explicit error and retry action instead of replacing the patient
record with empty states. The phone layout keeps these same views in a fixed
bottom navigation bar.
Failed status/evidence loads clear their patient metadata, treatment/results/
alert rows, search caches, and filters so old PHI is not left looking current.
The research endpoint has its own failure boundary: malformed, `422`, or hard
research loads clear only Research/Today research authority, while ambiguous
transport retains the last verified workspace visibly stale and read-only.
Authorization failure additionally clears open reports/receipts, chat turns and
revision, summary feedback, all research rows/snapshots/events/dialog drafts and
retry bytes, and clinical text or selected file bytes still in the feed dialog.
The page identifies `401` as **Sign-in required** and `403` as denied access,
states that browser-held patient data was cleared while stored patient records
were not deleted, and does not imply clinical-authority corruption. For `401`,
choose **Reload to sign in** to use the existing Easy Auth sign-in path. For
`403`, choose **Sign out and switch account**. That manual same-origin link calls
`/.auth/logout` with an encoded redirect back to `/`, clearing the current Easy
Auth session before the caregiver signs in with the permitted account. **Retry**
remains a separate action for access that was restored without an account switch.
The app does not start an automatic redirect or reload loop. Current symptom,
treatment, research, biomarker, and imaging projections return only after their
authenticated revision and strict payload checks succeed.

If the permitted account still cannot regain access, verify privately that
`AUTH_ALLOWED_PRINCIPAL_IDS` contains the unique stable object identifier from
the trusted encoded Easy Auth principal, not a convenience name or email-valued
identifier. Do not copy principal headers or claim payloads into logs, tickets,
or repository files. A malformed principal or conflicting values at the
selected claim tier intentionally returns `401`; a valid but nonmatching stable
identifier returns `403`. Do not weaken the allowlist, enable local bypass in
hosted configuration, or change the same-origin guard as a recovery step.

In-flight document, digest, and deep-sweep submissions are aborted and cannot
activate Activity from a late response; activity polling stops until current
authority starts it again. A missing selected activity is treated the same way.

## Review biomarker history

Open **Patient** → **Biomarkers**. This explorer reads the complete bounded
longitudinal projection directly from
`GET /api/patient/biomarker-series`; it does not use the truncated biomarker
summary in `/api/status`.

1. Choose the server-provided biomarker name from **Choose a biomarker**.
   Recorded aliases appear exactly as stored; the browser does not rename or
   merge tests.
2. Read the table first. It keeps every
   observation, including partial or unknown dates, qualified/ranged/text
   values, missing context, non-comparable facts, and presentation-collapsed
   same-source duplicates. Expand **Source and wording** for plain source
   meaning and authenticated **View exact wording** / **Open source** links.
   Internal observation, source-row, document, and evidence IDs remain hidden.
3. Treat **Comparable point charts** as a secondary view only. Each card is one
   exact series the server declared comparable. Points are not connected and the
   browser performs no conversion, interpolation, smoothing, aggregation,
   direction label, response judgment, or recommendation. If no group contains
   at least two comparable points, the explorer says so and leaves all facts in
   the table.

The status above the table distinguishes loading, current, current-but-empty,
offline stale, corrupt/inconsistent (`422`), and other failures. If connectivity
becomes ambiguous, the last accepted table and charts remain visibly **Stale
snapshot** and read-only until an authoritative reload succeeds. Reconnecting
triggers that reload. Authorization loss or a hard invalidating response removes
biomarker values, chart/table markup, selection and response tokens, focus, and
late responses from the browser. Biomarker data is never stored in browser
storage, and this surface has no copy, download, or print action.

The header reports processing only: **Processing N**, **Idle**, or
**Unavailable**. It never claims the clinical assessment is current. Assessment
freshness appears separately on **Today**, where profile and assessment
revisions are compared.

## Review and compare imaging reports

Open **Patient** → **Imaging**. This text-report explorer reads the complete
bounded projection directly from `GET /api/patient/imaging-series`. It never
uses `/api/status` or the compatibility imaging list in
`/api/patient/evidence`, and it does not retrieve or display medical images.

1. Read the table first. It keeps every returned record independently and in
   the server-supplied order, including exact duplicates, partial or unknown
   dates, legacy date uncertainty, manual/caregiver-corrected facts, missing
   fields, and unverified or unavailable sources.
2. Treat the displayed date context literally. A study date, month/year
   precision, legacy-unconfirmed date, and unknown date are labelled
   separately. The expandable source-document date is explicitly not used for
   study chronology.
3. Expand **Source and wording** for plain source meaning and authenticated
   opaque source/evidence links. Internal record/source IDs, storage paths,
   coordinates, hashes, and evidence offsets are not exposed.
4. Check exactly two current records, then press **Compare selected records**.
   The two panels repeat only their exact date context, modality/type, findings,
   impression, and provenance. Any comparison, change, progression, or response
   wording is attributed to the stored report; NET/Care does not calculate,
   highlight, or infer a conclusion.

The status distinguishes loading, current, current-but-empty, stale/read-only,
corrupt/inconsistent, and other hard failures. A known patient or workflow
revision change makes the displayed projection stale immediately and reloads
it without blocking other workflow refreshes. Only transport ambiguity from
the imaging endpoint may retain the last accepted projection as a stale,
read-only snapshot; an unrelated request failure or browser online/offline
signal alone does not demote it. Authorization loss clears all browser PHI.
Malformed, `422`, and other hard imaging responses clear the imaging table,
hidden details, selections, comparison, tokens, and focus without clearing
unrelated Patient cards. No imaging data is stored in browser storage, and the
surface has no chart, copy, download, print, or export action.

## 1. Feed a clinical document

When you receive new lab results, an imaging report, or a doctor's note:

1. In the header, click **Add document**. An accessible dialog opens.
2. Either:
   - Stay on the **Paste text** tab and paste into the textarea, or
   - Switch to **Upload file** and drop / pick a `.txt` / `.pdf`. PDF extraction
     runs `pdfplumber` only in a contained child process, never in the web
     worker: 30-second hard timeout, 100-page and 1,000,000-character defaults,
     validated output, and Linux resource limits.
3. Click **Process document** (or select the upload). The dialog auto-closes and
   the **Activity** view opens with the submitted job selected.

The job runs in the background:
   1. **Intake** parses the text and updates biomarkers / imaging / treatments.
   2. **Orchestrator** runs PubMed + ClinicalTrials.gov searches relevant to the new findings.
   3. **Executive summary** is regenerated.
   4. Treatments are re-classified into active / planned / completed. If that
      classification cannot be certified, the job still finishes and the
      treatment surfaces fall back to the raw records
      (see [§12](#12-asynchronous-jobs-restart-and-graceful-shutdown)).

Every feed receives a unique source ID and ingestion timestamp. The original
bytes plus extracted text are written atomically as immutable protected
artifacts; structured biomarkers, imaging, symptoms, appointments, and findings
link back to exact verified quotes where available. The summary's **Evidence**
links open only authenticated, no-cache source/span endpoints and never reveal a
filesystem path.

As soon as intake commits, the selected feed job shows a **Document
reconciliation** receipt above its research report. This is scoped only to that document—there is no global review inbox or
acknowledgement count. Activity calls it **What this document changed**. The
receipt shows:

- the document filename/type, ingestion time, and human-readable source link;
- each structured addition, old → new scalar update, conflict, and exact
  duplicate/no-op;
- **Exact wording available**, **Document linked - exact wording unavailable**,
  or **No document linked**, without claiming clinical authenticity;
- read-only trials/papers discovered later by orchestration.

The server returns `202` with a job ID. The UI polls active work every three
seconds and loads the
report only from that individual job after completion. If the analysis discovers
research that was not already tracked, the shared research workspace reloads;
**Today** then shows the bounded exact latest-batch summary and **Research**
shows every occurrence in server order. Alerts appear under
**Patient**. The job status moves `queued → running → done` in the activity list;
press **Esc** or click the backdrop to dismiss the document dialog at any time
without submitting. Idle polling backs off to 30 seconds (60 seconds while the
browser tab is hidden).

Feed has its own bounded queue (one active + two queued by default), independent
of other AI work. If full, the API returns `429` with `Retry-After` (10 seconds
by default) and creates no job record; retry after that delay.

### Correct or undo one document

Use the selected feed job's reconciliation receipt when intake extracted a value
incorrectly:

1. Select **Correct value** beside the affected imported fact, edit only the
   offered clinical fields, and save. Or select **Remove imported value** to
   remove that fact from active structured state.
2. To reverse all still-active direct extraction effects, select **Undo document
   changes**. The original source and audit history remain available; research
   findings are not silently deleted.
3. The assessment becomes stale after any correction/removal/undo. Review the
   Patient record, then explicitly refresh the assessment.

Source-dependent alerts are retained but removed from **Active alerts**.
Generated appointment questions move to an **Outdated generated questions**
section, and the prior assessment/feed report is hidden in Today/Activity. This
prevents old actions, PRRT screening, or trial language from being reused while
preserving the audit trail. Regenerate each artifact after confirming the
corrected Patient record.
If correction saves but Activity detail cannot refresh, the authoritative saved
receipt remains visible with **Correction saved successfully** and a retry
button. Open feedback editors and report/result panels are immediately replaced
when stale state is detected; old actions/reports cannot remain copyable.
Digest/deep-sweep reports and chat answers are also labelled outdated and hidden
after any later clinical revision. Alert resolution advances that revision
because those artifacts may have consumed the alert: prior chat turns clear,
in-flight replies are rejected, open reports/results become outdated, and
assessments/generated questions become stale. Durable or source-scoped sibling
alerts remain active under their declared lifecycle. Alerts resolve by stable
identity; if the alert changed while open, the UI reloads it instead of
resolving another row.

Chat history is bound to the patient profile revision. Correction, undo, or any
other clinical revision clears prior in-tab turns with a visible notice. The
server rejects stale history with `409`, so an old answer cannot be resent into a
new-record conversation.

Document intake may still produce legacy raw treatment rows and machine-
generated classifications for compatibility and model context. Those values
remain separate from the caregiver treatment workflow described below: they do
not create a course, seed a form, authorize a status, or become a discrepancy
citation.

Alert lifetime follows its declared dependency. Ingestion-failure and
trial-status alerts are durable until resolved. Feed-source alerts deactivate
when that source is corrected/undone. Digest/profile-snapshot conclusions
deactivate after a later clinical revision. Document undo preserves durable
alerts for explicit resolution.

The server compares only the affected rows/scalars/treatment values. Unrelated
later profile changes do not block the correction. If an affected value changed
or a later document also supports it, the server returns `409` before changing
anything and the receipt shows the conflict. Reload the receipt and review the
newer source; do not retry blindly. Whole-document undo is all-or-nothing—one
conflicting target means no part of the document is rolled back.

Receipt access follows normal feed-job retention. Its audit record remains in
`patient_profile.json` and backups, but legacy imports created before schema v2
do not receive retroactive editable receipts.

## 2. Run a research-only digest

Use this when no new document has arrived but you want a fresh literature/trial sweep
(e.g. once a week):

1. UI → **Activity** → **Run digest**.
2. Orchestrator runs without new input; existing biomarker trends are re-analysed,
   new papers / trials added.
3. The text report is saved to `/home/data/reports/report_digest_*.txt`.

Only one digest may be active; a duplicate request returns `409`. The report is
not embedded in job history—it is loaded on demand when the activity item opens.
At completion, the shared research workspace reloads from
`GET /api/patient/research-workspace`; the browser never merges job-result rows
into display authority. **Today** shows the first three exact current
latest-batch occurrences in server order, with exact trial/paper totals and an
omitted count. **Research** remains complete. A digest that finds only
already-tracked research produces an exact zero-member latest batch.

## 2b. Run an ensemble deep-sweep (pre-appointment deep prep)

Use this before an oncology appointment when you want the most thorough,
insight-hunting pass — not just a routine sweep:

1. UI → **Activity** → **Run deep sweep**, then confirm the prompt.
2. It runs two premium models (default **Fable 5 + Opus 4.8**) with the routine
   "skip what's already tracked" rules relaxed, then a synthesis pass **unions**
   their findings into one briefing with a **Cross-Cutting Insights** and a
   **Where the models diverged** section.
3. Takes a few minutes and costs ~$1–2 (a cost footer is shown on the report).
   The report is saved to `/home/data/reports/report_deepsweep_*.md`.
4. **Read-only:** unlike Feed/Digest, the deep-sweep does **not** add anything to
   your tracked papers / trials / alerts — it is purely a briefing for you to
   take to the oncologist. Everything is decision-support only; your clinician
   reviews it before any action.
5. Final synthesis is deterministically checked for every PMID/NCT reference and
   receives a verification footer plus stop-reason/token metadata. Token or
   iteration limits are explicitly marked. If synthesis fails or truncates, raw
   per-model reports are preserved as the fallback.

Only one deep-sweep may be active; a duplicate returns `409`.

## 3. Record a clinical judgment

After every consultation, capture the oncologist's actual position so future AI runs
respect it as a hard constraint:

1. UI → **Appointments** → **Clinical notes**.
2. Pick the category:
   - `constraint` — rules out a treatment / trial / approach
   - `preference` — what the oncologist favours
   - `outcome` — past response or side effect
   - `context` — clinical background
3. Write the judgment in plain English (e.g. *"Hilar lymph node assessed as non-urgent — re-image in 3 months"*).
4. Click **Add note**. The judgment is persisted; future orchestrator and exec-summary runs will
   read it before proposing actions.

Judgments default to **active**. Editing lets you mark one **needs review** or
**superseded**; API clients may also set `scope`, `review_after`, `valid_until`,
and `supersedes`. Once review is due or validity expires, the note remains
visible but is no longer a hard constraint until a clinician reactivates it.

## 4. Resolve / dismiss an alert

1. UI → **Patient** → **Active alerts**.
2. Click **Resolve alert** on the card. The shared desktop/phone dialog reloads
   the current action, visit, and decision choices before enabling submission.
3. Optionally record what happened. A blank outcome is omitted. A nonblank
   outcome must be one of:
   - **Administrative (not clinical evidence)**
   - **Caregiver-entered · caregiver reported · unverified**
   - **Caregiver-entered · attributed to clinician · unverified**
4. Choose exactly one link mode: no link; one active follow-up; a new caregiver
   follow-up containing only safe contact/ask/discuss/confirm text, owner, and due
   date; or one planned/in-progress visit with an optional active or
   needs-confirmation decision. Existing records are sent by stable ID only.
   These links organize caregiver follow-through; they are not autonomous
   treatment instructions or eligibility findings.
5. Confirm and submit. The alert is marked `resolved=true` but retained for
   audit, with its structured outcome, links, and append-only history attached to
   the stable alert ID. The returned confirmation contains only the bounded saved
   outcome/link projection; the old alert message is removed and sibling alerts
   remain visible.
6. Prior chat turns clear and open generated reports/results become outdated;
   regenerate only after reviewing the remaining active alerts.

The browser acquires one resolution owner before reading the selected alert or
allocating a mutation ID. While loading or saving, competing Resolve controls
and dismissal are locked. A connection loss keeps the last authoritative alert
and link choices visibly stale and read-only, plus the caregiver draft and one
exact unchanged retry. Editing the draft invalidates that retry. A `409` never
auto-retries: the old card/dialog copy and retry are cleared, eligible caregiver
draft text is retained, and fresh alert ID/token/revision and link projections
must reload before a new submission. Authorization loss or a hard load failure
scrubs visible and hidden alert copies, choices, forms, drafts, retries, focus,
and late responses. Alert resolution loading is event-driven; it adds no polling.

## 4a. Track caregiver follow-through

Open **Today** → **Follow-ups**. Desktop and phone use the same action list
and dialogs; there is no separate mobile copy or extra top-level view.

1. Use **Active**, **Completed**, **Cancelled**, and **All** to filter durable
   caregiver tasks. Active combines `open` and `in_progress`. Due dates use calm
   **Due soon** and **Overdue** labels; the card also shows owner, origin,
   linked visit/decision/alert indicators, timestamps, and any recorded outcome.
2. Choose **Add follow-up** for a manual task. Use contact, ask, discuss, or
   confirm wording with the treating team. The browser never silently rewrites a
   treatment directive: it gives safer wording guidance and displays any
   authoritative server rejection.
3. A current generated assessment action offers **Add to follow-through**.
   Acceptance sends only the server-projected stable source ID and semantic
   token, never generated text or a list index. Stale, hidden, revisionless, or
   conflicted actions become a generic unavailable row without cached text,
   token, or action control. Once accepted, the durable generated snapshot
   remains in Follow-ups after later assessment revisions.
4. Use **Edit owner or due date** for administrative changes. Use **Start** on an
   open task or **Move to open** on an in-progress task. Completed and cancelled
   actions are immutable terminal history and do not offer reopen controls.
5. **Complete** or **Cancel** requires an outcome source and text:
   `administrative`, `caregiver_reported`, or `clinician_attributed`.
   Administrative outcomes are explicitly not clinical evidence. The other two
   are labelled **Caregiver-entered · caregiver reported · unverified** or
   **Caregiver-entered · attributed to clinician · unverified**; neither receives
   source-verified styling or becomes a clinician fact.

Each user intent gets one mutation ID and the current full action/source token.
Only an explicit retry after an ambiguous connection loss reuses that exact
unchanged request. A `409` never auto-retries or applies pending browser copies:
the UI reloads the authoritative action (and assessment source when relevant),
keeps only the eligible caregiver-entered draft, and requires a new explicit
submission. Drafts are keyed to their action and intent and live only in the
current SPA memory.

While one follow-through save is in flight, every generated acceptance button,
manual/action mutation control, visit-linked follow-up control, and filter is
disabled, and an open saving dialog cannot be dismissed. A duplicate click does
not create a second mutation ID or request. This is browser-side intent
serialization, not a claim that the server can deduplicate actions created by
another browser. Success is announced only after the targeted response and
authoritative reload satisfy non-regressive workflow revisions and still belong
to the same patient-data, action/visit selection, and mutation owner;
authorization or hard reload eviction silently cancels stale completion cleanup
and focus restoration.

Owner, due-date, and administrative lifecycle changes advance only
`workflow_revision`, so they refresh action UI without clearing chat, reports,
summary, questions, tasks, or status. Caregiver-reported and
clinician-attributed outcomes may also advance `profile_revision`; the browser
uses the returned revision, never the selected outcome kind, to trigger the full
authoritative clinical refresh. Authorization or hard data-load failure clears all action rows, tokens, dialog
copies and forms, drafts, retry bodies, focus state, and late responses. An
ordinary offline or aborted refresh preserves the last authoritative Today and
visit-linked action rows as a visibly stale, read-only snapshot. All action
mutation and generated-action acceptance controls remain disabled until a
successful authoritative reload supplies fresh tokens. Caregiver drafts remain
isolated by action and intent in SPA memory only.

## 5. Generate appointment questions

1. UI → **Appointments** → **Generate visit questions**.
2. Claude reads the current profile + clinical judgments and returns 10–15
   ranked questions in the language configured by `patient.language`
   (defaults to English), grouped by category
   (Treatment / Diagnostics / Symptoms / Trials / Monitoring / Other).
3. You can mark questions as **asked** during or after the appointment.
4. Manual questions can be added with **Add question** at any time.

Generation is asynchronous: the UI polls the job and renders its separate result
artifact. Manual additions remain synchronous profile mutations.

Regeneration preserves already-asked AI questions and all manual questions,
while deduplicating newly generated questions by normalized text.
Each generation has an identity. Superseded or legacy AI questions without
generation provenance remain visible as **Outdated** history and are not
presented as current appointment preparation.

## 5d. Prepare and run an appointment

Open **Appointments** → **Appointment workspace**. Desktop and phone use the same
working record; on a phone it opens as a full-height sheet.

1. Create a visit, or select a current imported appointment to prefill its
   bounded date/time/clinician/location fields. The imported fact remains
   separate and receipt-correctable; the working visit links it by stable ID.
2. Open the visit and edit its title/details. Use **Start visit**, **Complete**,
   or **Cancel visit** for the explicit lifecycle.
3. In **Questions** within the Appointments workspace, add a current generated
   question or type a manual caregiver
   question. Generated acceptance sends only its stable ID/token—the browser
   never copies generated text back as the source. Outdated or revisionless
   generated rows show only a generic unavailable state; their prior text is not
   displayed. When the clinical revision changes, generated choices are removed
   from the browser cache and both question surfaces immediately show a generic
   unavailable/retry state before reloading `/api/questions`; an offline, stale,
   or late response cannot restore the old text, metadata, token, or Add action.
   Manual drafts and already accepted visit snapshots remain visible, with the
   latter retaining their generated-snapshot provenance.
4. Pin questions and use Move/rank controls. On a phone these controls retain
   full-size touch targets and wrap without horizontal scrolling. The complete
   order is saved atomically after the server verifies the visit plus every
   question ID/token; a conflict cannot leave a partially reordered list.
5. During the visit, record either an answered response with text or explicitly
   unknown.    Every captured answer is labelled **You recorded this from the clinician**.
   This attribution does not claim that NET/Care independently verified it.
6. In **Decisions**, record what the clinician said. Decision text is immutable.
   An active decision can be marked **Needs confirmation**, corrected through an
   immutable successor, or retracted. A decision needing confirmation can only be
   confirmed active or retracted; confirm it before creating a correction.
   Superseded and retracted rows are read-only history. Every row carries the same
   caregiver-entered/clinician-attributed/unverified label and is not promoted to
   verified evidence or a hard clinical judgment.
7. In **Follow-ups**, create a resulting caregiver action, optionally linked to
   a decision, using contact/ask/discuss/confirm wording. Visit-linked follow-ups
   are displayed read-only here; general task editing remains outside this
   appointment slice.
8. Open **Recap** during an in-progress visit or after completion. The recap
   deterministically shows **Visit details**, **What was asked**, **What we
   heard**, **Decisions / needs confirmation**, **Follow-ups**, **Related
   resolved alerts**, and **Unresolved / unknown items**, omitting empty
   sections. It preserves the stored wording exactly. Generated question
   snapshots remain labelled generated; captured answers and current decisions
   remain **Caregiver-entered · attributed to clinician · unverified**.
   Administrative action/alert outcomes remain explicitly non-clinical.
9. After reviewing the current recap, use **Copy**, **Download text**, or
   **Print**. Each click performs one authenticated, no-cache recheck using the
   current full visit token and exports only if the returned recap token,
   revisions, visit authority, and exportable lifecycle exactly match the recap
   you reviewed. If anything changed, the app shows the replacement for review
   but performs no clipboard, download, or print action; click export again only
   after reviewing it.
   Export controls appear only when the displayed recap is the accepted current
   in-progress or completed visit.
   Download creates a UTF-8 plain-text file named generically, such as
   `visit-recap-2026-08-10.txt`; the app does not create PDF/Word files, upload,
   email, or share the record. Planned visits cannot be recapped until started.
   Planned visits and cancelled administrative records show no export controls.

Each request has one mutation ID and target token. An explicit retry after an
ambiguous connection failure reuses only that exact unchanged request. A `409`
never retries automatically: the workspace keeps eligible caregiver draft text,
reloads authoritative tokens, and explains that the visit or assessment changed.
Drafts remain only in memory.

The recap is a read projection: opening, copying, downloading, or printing it
does not change either revision, append audit history, or mark any item reviewed.
Only one export can own the controls at a time. If the selected visit, its
If the selected visit or its complete visit token changes, the previous recap
and export payload are removed before the new visit header renders or reload
starts. If its follow-ups, a related alert, or any workflow/clinical authority
changes, export controls disappear immediately and the recap reloads.
A connection failure may leave the previous recap visible as **Offline snapshot
· read-only** only for the same visit identity, but Copy/Download/Print remain
absent and causes no export side effect. The browser going offline revokes export
authority and any prepared download URL synchronously; reconnecting alone does
not restore it. A successful authoritative recap reload/review is required. A
conflict requires the visit and recap to reload; authorization loss or a hard
failure removes the recap and its hidden export payload entirely. Returning to a
visible browser tab refreshes an active recap; there is no recap polling.

Pin/order/visit bookkeeping changes only `workflow_revision`. Captured answers
and clinician-attributed decisions also advance `profile_revision`, clear
revision-bound chat, and revalidate summaries, generated questions, and open
activity detail. Authorization failure clears all appointment PHI, drafts,
dialogs, caches, retry requests, and late responses. A transient offline failure
keeps the current draft for explicit retry.

## 5b. Record review feedback

The **Today** view shows confidence, rationale, freshness, generation time, and
claim-level evidence links. Each key claim and next action links only to exact
authenticated source spans selected from the server's verified catalog;
missing/invalid support is labelled rather than invented. A prominent warning
appears when newer patient data needs assessment and owns the only
**Refresh assessment** action. The prior generated assessment remains hidden and
offers no conclusion or action controls until refresh succeeds. When the
assessment is already up to date, that same banner control stays available as
**Regenerate assessment**, so a rerun can be requested at any time without a
second button anywhere else. Use **Report
something missed or incorrect** to record a prominent `missed` review item. This
only appends structured feedback; it never edits patient facts or silently
creates a clinical judgment. Corrected/incorrect/missed feedback on the current
summary marks it stale for conservative review. `GET/POST /api/feedback`
supports the full assessment set:
`agreed|corrected|acted|helpful|incorrect|missed`.
`PATCH /api/feedback/<id>` records later assessment, note, or outcome updates
with a new `updated_at` timestamp.

Removing a recommended action sends its assessment revision and expected action
text. If a background run updates the assessment while the feedback editor is
open, submission is disabled and the server rejects any stale request with
`409`; close the editor, review the updated action, and reopen it.

## 5a. Record and review symptom episodes

**Today → Current symptom episodes** shows every current caregiver-maintained
episode in server order and its linked follow-up state. Use **Record symptom
episode** there, or open **Patient → Symptoms** for the complete workflow.
Desktop and phone use the same projection, renderer, and dialogs.

In **Patient → Symptoms**:

1. **Current episodes** contains durable caregiver-entered, unverified episodes.
   Use **Edit episode facts** to correct only explicit fields, **Resolve episode**
   for the sole current-to-resolved transition, and **Add follow-up** to link one
   currently eligible action or atomically create and link one manual action.
2. **Resolved episodes** retains completed episodes for review. Resolved facts
   can be corrected where the server permits, but an episode cannot be reopened.
   If the symptom happens again, use **Record episode** to create a new current
   episode.
3. **Source observations** is a separate read-only table of imported and legacy
   mentions. Every row and duplicate remains independent in server order. A
   mention is never promoted, merged, deduplicated, or treated as a current
   episode.

The episode form accepts exact symptom wording; optional
Mild/Moderate/Severe selection and exact detail; reported subject; timing,
frequency, triggers, and notes; and an optional `YYYY`, `YYYY-MM`, or
`YYYY-MM-DD` onset. Resolution date is also optional and starts blank. The
browser does not fill today's date, parse dates into another timezone, compare
chronology, score severity, or infer urgency. Empty, missing, partial, and
unknown server values remain visibly distinct.

Follow-up modes are mutually exclusive. Linking selects one exact eligible
action from the current projection. Manual creation sends one symptom mutation
that creates and links the action atomically; it never creates an action first.
Unlinking changes neither the episode lifecycle nor the action lifecycle.
Existing visit, decision, and alert action provenance is preserved.

Only an uncertain symptom-endpoint transport keeps the last accepted snapshot
visible, marked stale and read-only. Use the explicit unchanged-request retry
after an uncertain mutation; if the save succeeded but the authoritative
reload is uncertain, the retry reloads only and does not resend the mutation.
A conflict reloads the record for explicit review and never auto-submits a
draft. Authorization failure clears all patient information from the browser;
a malformed or hard symptom failure clears the symptom surfaces without
removing unrelated Patient cards.

Routine Today, Patient, and episode-dialog presentation does not repeat a
generic capability or emergency disclaimer. Caregiver-entered/unverified
attribution, stale/read-only notices, conflicts, validation errors, and retry
actions remain visible where they apply. This presentation change does not alter
the strict projection metadata or clinical behavior: the browser does not score
severity, infer urgency, make a treatment recommendation, or promise monitoring.
Legacy observations remain available to the existing model context;
caregiver-maintained episodes remain excluded from all model prompts.

## 5b. Record and reconcile treatment information

**Today → Treatment status** shows explicitly reviewed Current/Planned records
when present. Each recorded raw row is also checked only against explicit
caregiver course-component links: fully linked rows are not counted as unresolved,
partly linked rows remain unresolved, and unlinked rows still need timing/status
review. If no treatment is recorded current, Today says so and shows a bounded
first set with honest unresolved counts. **Review treatment status** opens the
complete **Patient → Treatments** Overview. Today and Patient use the same
accepted projection; neither uses `/api/status` treatment data.

Patient's default Overview combines three kinds of information without inference:

1. Explicit caregiver-maintained **Current and planned** courses.
2. Every row already in the patient treatment record, labelled as unlinked,
   fully linked, or partly linked to an explicit caregiver-reviewed status
   record. Raw wording never inherits the linked course's lifecycle. Each of
   these rows carries exactly one action, **Record status**, which opens the
   same status-record dialog used by **＋ Add status record**. It copies only
   that row's wording into the treatment-wording field and pre-ticks only that
   row's components under *Link recorded treatment components*. It never
   chooses a record status, never fills a start/stop/planned date, and never
   picks a terminal outcome, so the dialog cannot be saved until you choose the
   status yourself. Edit any copied wording freely before saving. Once saved,
   the row shows as linked to the new status record. The compact **Today →
   Treatment status** cards stay read-only.
3. Explicit caregiver-maintained **Finished or past** courses.

Record or edit only explicit wording,
   optional exact fields, partial/unknown dates, and optional earlier-component
   associations. Blank dates stay blank; the browser does not default today,
   parse timezones, match medications, copy document/generated text, or
   infer timing that was never recorded.

Each of the three groups above is listed newest-first. A status record is placed
by the date its own status is about: the planned date for a planned record, the
start date for a current one, and the stop date — or the start date when no stop
date was recorded — for a finished or past one. A date that names only a year or
a month is placed at the start of the period it names, so `2026` sits below
`2026-03-15` but above `2025-12-31`. Records with no usable date always come last
in their group instead of moving around, and two records with the same date keep
the same relative order on every render. Rows already in the patient treatment
record carry no date at all, so they are listed most-recently-recorded first;
NET/Care never reads a date out of the wording, borrows one from a linked status
record, or takes one from generated text. The compact **Today → Treatment
status** card uses the same order, so it shows the most recent entries.

The Overview preserves every row and duplicate. It never promotes,
merges, deduplicates, changes what is stored, or assigns lifecycle. Secondary
panels are:

1. **Differences to review** contains explicit caregiver-recorded comparisons.
   Record A is one document mention. Record B is either a distinct document
   mention or one caregiver course. The browser does not preselect, detect,
   highlight, rank, or decide which side is correct. Immutable A/B snapshots
   remain separate from each side's current state. An older
   `legacy_incomplete` item shows its one real side and an unavailable second
   citation; it is read-only.
2. **Mentions in source documents** contains every source receipt entry, duplicate,
   and exact raw value in server order. These rows are not caregiver lifecycle
   records. Source/evidence links are authenticated opaque routes.

The former **Automatic compatibility notes** tab was removed. The NET/Care-generated
compatibility rows behind it are still stored in the profile and still returned by
the treatment-reconciliation projection, so nothing was deleted — they simply have
no UI surface, because they were machine-generated context rather than treatment
facts and could never set treatment status.

Current lifecycle buttons are exactly those returned by the server. Do not
interpret their presence as treatment advice. A new Past record or a transition
to Past requires a neutral recorded outcome offered by the server. **Did not
start** and **Plan cancelled before starting** do not imply exposure.
**Other recorded outcome** requires exact bounded caregiver detail.
**Earlier record; ending detail not recorded** is display-only legacy authority.
Past is terminal. **Create linked new record** appears only when the server
authorizes restart; it creates a blank new Current or Planned course and leaves
the prior course unchanged.

Treating-team outcomes are always labelled
`Caregiver-entered · attributed to clinician · unverified`. A caregiver-course
correction submits only explicit changed fields atomically with the outcome and
cannot submit a no-op. Reopen keeps prior outcomes. Recurrence uses the server-
owned prior A/B authority without replacement. Follow-up management is one
atomic variant: link one current eligible action, create-and-link one manual
action, or unlink the displayed action. It never performs a preliminary action
create or changes either lifecycle.

Every save is confirmed only after the complete authoritative projection
reloads and matches the returned revisions and public result. If submission
transport is uncertain, **Retry submission** resends the exact same bytes;
editing or closing removes that authority. After any valid mutation response,
only **Retry refresh** can be used. A conflict discards old tokens and
selections, reloads, and requires explicit review; safe caregiver add/difference
wording may be restored, but source, component, action, target, and citation
choices must be selected again. A draft preserved from a row's **Record
status** dialog is offered again only from that same row, and reopening that
row restores the wording but never re-ticks a component link you removed, so
**＋ Add status record** always starts clean. Rejected submitted fields keep
the current projection and draft. A malformed or hard treatment read clears
treatment content; authorization loss clears all patient PHI. Normal refresh
does not move focus.

If the treatment or symptom workspace reports that records could not be
verified safely after an upgrade, do not use `/api/status` as a fallback and do
not edit the profile ad hoc. Confirm the profile loaded through the normal
migration path at schema v15. A genuinely missing top-level
`profile_revision` is restored as `0`; an existing null or invalid revision
remains invalid by design and requires operator review of a valid backup.

Routine Today, Patient, and treatment-dialog presentation does not repeat the
generic non-prescriptive capability strip. Caregiver-entered and
clinician-attributed labels, generated-context-not-a-treatment-fact labels,
source uncertainty, validation errors, conflicts, and retry states remain
visible. The strict response metadata and all treatment authority/inference
rules are unchanged.

## 5c. See newly discovered research

**Today** shows at most the first three exact trial/paper occurrences that the
server marks `latest_batch_member`, in the projection's order. It states the
exact total and omitted count and separately shows at most the first three open
considerations. A routine digest always replaces latest-batch membership,
including with zero results. Document processing replaces it only when that run
adds research, so an unrelated fed document does not erase the prior batch.

Open **Research** for the complete workspace:

1. **Current research** preserves every occurrence, duplicate, and order. Each
   row keeps external registry/bibliographic facts, machine-generated
   compatibility context, discovery provenance, and caregiver workflow separate.
   External navigation is offered only for an exact server canonical
   ClinicalTrials.gov/PubMed URL.
2. Select **Save exact occurrence for consideration** only when the server
   publishes shortlist eligibility. This captures one immutable snapshot; a
   later same-NCT/PMID row with a different occurrence ID is not substituted.
3. **Considerations** keeps the immutable snapshot separate from the exact
   current occurrence and reports occurrence presence plus external/generated/
   discovery equality independently. It does not translate change into clinical
   relevance, availability, suitability, eligibility, or obsolescence.
4. Record only server-allowed caregiver note, next step, treating-team
   communication, or trial-site communication types. Trial-site communication is
   available only for trials. Optional partial dates are stored exactly without
   defaults or browser date interpretation. Attribution remains visibly
   caregiver-entered and unverified.
5. Close or resume only through server eligibility. Closing stops active
   caregiver consideration; it does not mean irrelevant, unavailable, unsuitable,
   ineligible, or rejected, and resume preserves all event/lifecycle history.
6. Link one current eligible action, create one blank manual action and link it
   atomically, or unlink the current action. Research never performs a separate
   action create and never copies generated/source wording into caregiver fields.

This workflow never determines relevance, eligibility, enrollment, availability,
or treatment suitability. Closing is only a caregiver organization choice.
Treating-team and trial-site wording is caregiver-entered, attributed, and
unverified. Source refresh/removal and action completion never change lifecycle.
The immutable capture remains separate from current external facts,
machine-generated compatibility context, and discovery provenance.

The **New research** labels remain only exact server-published per-occurrence
latest-batch membership. Shortlisting, opening, noting, closing, resuming, and
linking do not mark research read, reviewed, acknowledged, old, or new. No
reminders, monitoring, contact automation, or background site communication is
added. Routine Today, Research, and research-dialog presentation omits the
repeated generic capability strip while keeping external/generated attribution,
source uncertainty, caregiver-entered provenance, lifecycle meaning, errors,
conflicts, and confirmations.

## 6. Chat with the record

Header → **✦ Ask Claude**. Free-form conversation grounded in the
**full** patient record:
- Every biomarker reading (no recency cap)
- Every imaging study (no recency cap)
- Every fed document (date + type + summary + key findings — the raw text
  is intentionally not in the chat prompt to keep it sane)
- All tracked trials & papers
- Active alerts and clinical judgments
- The latest executive summary

Use it for either general questions ("how has CgA trended?") or specific
content lookup ("what did the CT report from August say about the hilar
lymph node?"). When you ask about a specific past artefact, the chat
points Claude at the DOCUMENTS / BIOMARKERS / IMAGING sections of its
context so it cites real data instead of hallucinating.

The chat is stateless across page reloads; only the in-tab history is sent
back with each turn. Each answer is an asynchronous general-queue job; the UI
polls and reads the reply from its result artifact.

## 7. Update patient demographics / setup

Use the CLI for one-off setup:

```powershell
python net_agent.py update-profile
```

Prompts for Ki-67, SSTR status / score, treating center, oncologist name, and
a new treatment string. Leave a field blank to keep the current value.

## 8. Local development quick reference

```powershell
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env                       # includes explicit local auth bypass
.\Scripts\run_local.ps1                           # starts Flask on :8000
pytest -q                                         # no network
python Scripts\seed_test_profile.py               # populate a fake profile
```

## 9. Backups, snapshots & automated recovery

### Normal operation

Every `save_profile` call:
1. Writes a pre-save **rotating snapshot** (`/home/data/snapshots/profile_<timestamp>.json`)
   with an optional `.sha256` sidecar.  The last 20 snapshots are kept.
2. Atomically replaces `patient_profile.json`. This replacement is the mutation
   commit point: write or replace failures are reported and the prior profile
   remains authoritative.
3. Best-effort maintains `.profile-initialized`. A marker failure is logged with
   only its error type and does not turn the committed mutation into an API
   failure. Loading a valid profile repairs an absent marker best-effort.
4. Writes a **daily backup** (`/home/data/backups/profile_YYYYMMDD.json`) once per
   calendar day and prunes files older than 30 days.

If the profile is missing, recovery candidates are checked before the marker.
Therefore an absent marker never blocks recovery, and a stale marker never
causes a default profile to overwrite a valid backup. A marker with no profile
and no valid recovery candidate still fails closed for operator intervention.

### Automated recovery on corrupt profile

If `patient_profile.json` has invalid JSON or an unusable structural shape,
`load_profile` automatically:

1. Writes a forensic copy to `/home/data/quarantine/patient_profile_<ts>_<hash8>.json`.
2. Searches all valid pre-save snapshots and daily backups and chooses the
   **globally newest valid candidate** (source type is only a tie-breaker).
3. Atomically restores the best candidate to `patient_profile.json`.
4. Applies any pending migrations and returns the recovered data.

If no valid candidate is found, `load_profile` raises `CorruptProfileError` and
the app returns 503 until the operator intervenes.

### Operator manual restore

If automated recovery fails (no valid snapshots or backups), restore from an
external Azure Backup or Azure Files soft-delete:

```python
# From Python / SSH shell — use the safe API, not raw cp
from pathlib import Path
from agent.recovery import RecoveryCandidate, restore_from_candidate

candidate = RecoveryCandidate(Path("/home/data/backups/profile_20260315.json"), "manual")
data = restore_from_candidate(candidate)  # validates + atomically restores
```

Or from the shell using the validation-checked helper:

```bash
# 1. Check what's in quarantine (forensic copy of the bad file)
ls /home/data/quarantine/

# 2. Find the newest valid backup
ls -lt /home/data/backups/

# 3. Restore via Python (validates before writing)
python -c "
from pathlib import Path
from agent.recovery import RecoveryCandidate, restore_from_candidate
restore_from_candidate(RecoveryCandidate(Path('/home/data/backups/profile_20260315.json'), 'manual'))
print('Restored OK')
"
```

**Never use raw `cp` to restore** — it bypasses the cross-process lock and
structural validation.

A successful restore also writes a daily backup of the restored state, so the
recovered profile is protected immediately and `/api/health` does not report the
storage as out of date (see §10) just because the candidate you restored from
was several days old.

## 10. Health check

`GET /api/health` returns a readiness report.  `GET /api/live` is a
lightweight liveness probe that always returns 200 regardless of profile state.

### `GET /api/health` response fields (no PHI, no paths, no secrets)

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"ok"\|"degraded"\|"error"` | Overall readiness |
| `version` | string | App package version |
| `release_commit` | string | Packaged Git commit (`development` outside release archives) |
| `schema_version` | int | Current profile schema version |
| `data_dir_writable` | bool | Storage is writable |
| `profile_status` | `"ok"\|"missing"\|"invalid_json"\|"invalid_shape"\|"io_error"` | Profile state |
| `profile_loaded` | bool | Alias: profile_status == "ok" |
| `stale_job_count` | int | Jobs queued/running >1 h |
| `interrupted_job_count` | int | Jobs interrupted by restart |
| `active_job_count` | int | Aggregate active jobs across both executors |
| `queued_job_count` | int | Aggregate queued jobs across both executors |
| `feed_active_count` | int | Active feed jobs |
| `feed_queued_count` | int | Queued feed jobs |
| `newest_snapshot_age_seconds` | float\|null | Age of the newest pre-save snapshot. **Informational only — never alarm on it**, see below |
| `newest_backup_age_seconds` | float\|null | Seconds since last daily backup |
| `profile_age_seconds` | float\|null | Seconds since the current profile write |
| `backup_out_of_date` | bool | Daily backup missing, or the profile was last saved more than `BACKUP_MAX_LAG_DAYS` calendar days after the newest backup was taken |
| `jobs_healthy` | bool | False if jobs.json was quarantined |

**How storage freshness is judged.** The two artifacts are written on different
cadences, so they are judged differently.

- **Daily backup.** `daily_backup()` runs after every save but writes
  `backups/profile_YYYYMMDD.json` at most once per local calendar day, while
  the profile is saved many times a day. The backup being older than the
  profile is therefore the normal steady state, not a fault, and raw age says
  nothing useful: a profile left untouched for a week keeps a week-old backup
  that protects it perfectly. Because `shutil.copy2` preserves the source
  mtime, a backup's mtime *is* the mtime of the profile revision it captured,
  so the check compares the **calendar day** of those two mtimes.
  `backup_out_of_date` is true when the backup is missing outright, or when the
  profile's last save falls more than `BACKUP_MAX_LAG_DAYS` (default `0`) whole
  calendar days after the newest backup was taken — meaning a day on which the
  profile was saved produced no backup at all, which only happens when the
  writer is broken. `daily_backup()` names the file after the profile's own
  mtime rather than the wall clock, so filename and mtime always agree and a
  save landing a hair before midnight cannot fake a day of lag; the tolerance is
  therefore zero, because a whole day of slack would let a writer that broke
  yesterday and then saw no further saves sit at a lag of exactly one forever
  and never be reported. Raise `BACKUP_MAX_LAG_DAYS` to buy quiet without a
  deploy if some environment change shifts a day boundary under an idle profile.
- **Snapshots.** `newest_snapshot_age_seconds` is reported for diagnostics but
  is **not** a freshness signal and nothing degrades on it.
  `rotating_snapshot()` copies the *pre-write* profile with `shutil.copy2`, so
  the newest snapshot always carries the **previous** profile revision's mtime
  and is older than the profile by construction on every save. After an idle
  week, a single save writes a brand-new snapshot still stamped a week old.
  Snapshot age measures how old the prior revision is, never whether
  snapshotting works, so any threshold on it would false-alarm. There is
  currently no reliable automatic signal for "snapshots stopped being written";
  check `${DATA_DIR}/snapshots/` directly if you suspect that.

The backup signal is suppressed unless `profile_status == "ok"`, so an
unreadable profile reports its own error rather than a misleading storage
complaint.

**Known gap.** Because backups piggy-back on saves, content written after a
day's first save is not in any daily backup until the next day's first save.
That window is covered by the pre-save snapshots, not by the daily backup, and
is by design rather than a fault — `/api/health` does not report it.

**HTTP status codes:**
- `200 status=ok`: everything normal
- `200 status=degraded`: minor issues (interrupted jobs, daily backup missing or
  not written on a day the profile was saved)
- `503 status=error`: storage not writable, or profile corrupt with no recovery

Configure `/api/health` as the App Service health probe — Azure will recycle
the instance if it returns 503 persistently (e.g. Azure Files mount not writable).
All fields are aggregate operational metadata; no job content, PHI, path, or
secret is returned.

## 10a. Recover from an authorization failure (operator)

Use this when the workspace shows an authorization banner or every action fails
with `403`. Everything below is safe to run without touching patient data.
Substitute your own resource names; never paste real account identifiers,
emails, tokens, or subscription IDs into the repo, an issue, or a PR.

**Step 1 — decide which gate rejected the request.** There are two, and they
fail differently.

| Symptom | Gate | Meaning |
|---|---|---|
| `403`, sub-status `60`, warning `Cross-site request forgery detected ... from referer ''`, request absent from application logs | App Service Easy Auth middleware, before Flask | The browser sent no `Referer` on a state-changing request. Caused by a `Referrer-Policy: no-referrer` response header (or a per-request `referrerPolicy` override). |
| JSON body with `"reason": "principal_not_allowed"` | Flask | The account authenticated, but no configured allowlist matched its typed candidate. |
| JSON body with `"reason": "cross_origin"` | Flask | Same-origin check failed. The workspace keeps patient data and shows a configuration message; it does **not** ask you to switch accounts. |
| JSON body with `"reason": "principal_absent"` or `"principal_malformed"` | Flask | No usable principal reached the worker, or the encoded blob was corrupt/oversized. |
| `503` with `"reason": "hosted_auth_unavailable"` | Flask | `WEBSITE_AUTH_ENABLED` is not `true`. Re-enable Easy Auth; never work around it. |

Read the middleware verdict from the site's diagnostic log stream. The Flask
`reason` and `principal_source` values are fixed enums and contain no
identifier, email, claim value, or token, so they are safe to quote in a ticket.

**Step 2 — confirm the referrer policy.** The app must never emit
`no-referrer`:

```powershell
curl.exe -sS -D - -o NUL https://<app-service>.azurewebsites.net/api/health |
  Select-String -Pattern 'Referrer-Policy'
```

Expect `Referrer-Policy: same-origin`. If it says `no-referrer`, the deployed
package predates this fix — redeploy or roll forward; do not disable Easy Auth.

**Step 3 — confirm which typed allowlist should match.** Check the shape of the
configured settings without printing their values:

```powershell
az webapp config appsettings list -g <resource-group> -n <app-service> `
  --query "[?name=='AUTH_ALLOWED_PRINCIPAL_IDS' || name=='AUTH_ALLOWED_PRINCIPAL_NAMES'].{name:name, entries:length(split(value, ','))}" -o table
```

- `AUTH_ALLOWED_PRINCIPAL_IDS` matches only a stable ID: an object identifier,
  `oid`, name identifier, or `sub` claim, or the `X-MS-CLIENT-PRINCIPAL-ID`
  header when no claim is present. Comparison is exact and case-sensitive.
- `AUTH_ALLOWED_PRINCIPAL_NAMES` matches only the account name/email, trimmed
  and compared with Unicode-safe `casefold()`. Dots, plus tags, and domains are
  never rewritten, so `care.giver@…` and `caregiver@…` are different accounts.

A request is accepted when **either** list matches its own candidate. Leaving
both empty accepts any account Easy Auth authenticated.

**Step 4 — migrate settings without a lockout.** Never change both settings in
one step, and never leave the ID list empty while the name list is still
unverified. Run the sequence in [§14a](#14a-migrate-the-authorization-settings).

**Step 5 — verify recovery.** Sign in in a private browser window, confirm the
workspace loads, and run one state-changing action (for example **Run digest**).
If patient data was evicted, it returns after the authenticated reload; stored
records are never deleted by an authorization failure.

## 11. Running digests

The digest is run on demand via `POST /api/digest` (the "Run digest" button in
the web UI). There is no built-in scheduler — trigger it manually after
uploading new documents, or wire up an external cron (Azure Function timer,
GitHub Actions, etc.) to POST to `/api/digest` if you want automation.

## 12. Asynchronous jobs, restart, and graceful shutdown

Feed, digest, deep-sweep, chat, appointment-question generation, and **Generate
summary** all return `202` plus `job_id`. The UI polls every 1.5 seconds while
waiting for chat/questions/summary and every 3 seconds for activity/status.
`GET /api/jobs` returns metadata only; `GET /api/jobs/<id>` loads the separate
report/result on demand.

The default general executor is two active + six queued
(`JOB_WORKERS=2`, `JOB_QUEUE_SIZE=6`); feed is one + two
(`FEED_WORKERS=1`, `FEED_QUEUE_SIZE=2`). Workers are constrained to 1–4 and
queue settings to 0–50. Queue admission occurs before durable metadata, so a
`429` never leaves a ghost job. Duplicate active digest, deep-sweep, or summary
jobs return `409`.

Jobs run in process and are **not resumable**. A deployment, restart, timeout,
or recycle can interrupt them; startup marks queued/running records
`interrupted` and the operator/caregiver must re-submit. Gunicorn allows 30
seconds for graceful shutdown and executor thread joins are bounded to five
seconds each. Do not assume either limit completes long AI work.

### Finished with warnings

A job that completes its primary work but skips a non-essential derived step
finishes `status=done` with `stage=done_with_warnings`. That is a normal
completion, not an error, and needs no re-submission.

Treatment classification is no longer one of those steps. The LLM classifier was
retired, so no job classifies treatments, nothing is logged as
`classification_skipped`, and no job reports a classification warning.
**Today → Treatment status** and **Patient → Treatments** are driven by
caregiver-reviewed course records and the recorded raw treatment entries, both
of which were always independent of the classifier.

## 13. Retention and PHI artifacts

| Setting | Default | Scope |
|---|---:|---|
| `JOB_RETENTION_DAYS` / `JOB_RETENTION_COUNT` | `365` / `200` | Completed job metadata and indexed report/result artifacts |
| `REPORT_RETENTION_DAYS` / `REPORT_RETENTION_COUNT` | `30` / `200` | Indexed and unindexed narrative report files under `reports/` |
| `SOURCE_ORPHAN_RETENTION_DAYS` / `SOURCE_ORPHAN_RETENTION_COUNT` | `7` / `20` | Source directories not referenced by the profile |

Pruning runs at startup and before new job admission. Active jobs and
profile-referenced sources are protected. This is best-effort housekeeping, not
a secure-erasure guarantee: lowering a setting does not delete protected
clinical sources, snapshots/backups, Azure soft-delete/version history, or
other provider copies. Temporary uploads are removed after feed processing.
If the process dies before the feed `finally` block, an upload directory can
remain; unindexed `job_results/` files are also not swept automatically.
Operators should periodically inspect those protected directories and remove
only entries confirmed to have no active job or job reference. Never expose
their contents in logs or support messages.

New `jobs.json` records store an allowlisted PHI-safe metadata subset, generic
errors, and bounded artifact state. Activity distinguishes available, stale,
expired, not retained, unavailable, no separate artifact, and legacy-unknown
states. Age/count pruning records the reason before clearing the reference;
missing/corrupt content is never called expired or still stored. Feed receipts
remain first-class while their job metadata is retained, even if the narrative
report expired. Reports and structured results are separate atomic artifacts;
individual authenticated job lookups read them through traversal-safe roots and
never expose paths. Job-runner logs avoid input, model output, prompts, and
traceback. Keep all operator logs protected:
lower-level storage/recovery OS errors can include filesystem paths.
Source/evidence endpoints additionally verify SHA-256/length and return
`no-store`.

## 14. Upstream and deployment limits

Anthropic defaults to 5-second connect, 120-second read, 10-second write,
5-second pool operation timeouts, a 180-second monotonic overall deadline, and
no SDK retries (`ANTHROPIC_MAX_RETRIES`, clamped 0–2). The overall deadline
includes streamed response bodies; every phase timeout is clamped to it.
Connect/read values are additionally clamped to 30/240 seconds respectively,
and the overall deadline to 290 seconds, below Gunicorn's 300-second limit.
Configured SDK retries apply a fresh deadline to each HTTP operation. PubMed
requests use 5/12-second connect/read limits; ClinicalTrials.gov search uses
5/15 seconds (verification/polling uses 5/12), with no application-level retry.
Unavailable external tools return sanitized unavailable results.

Production uses exactly one Gunicorn worker (`startup.sh`); this is
load-bearing for in-process queues. The complete production runtime dependency closure and setuptools build
requirement are exactly pinned from verified local metadata. The release archive includes `.deployment`,
which declares Oryx build-on-deploy.
Use only `Scripts/deploy.ps1`: it refuses to package unless pytest, ruff, and
gitleaks pass and the working tree is clean, verifies the release SHA-256,
records the current HEAD, polls asynchronous Kudu (900 seconds default), checks
authenticated terminal Kudu status and `/api/health` critical fields
for the exact packaged commit (300 seconds), and promotes
`.deploy/current-verified.*` only after success, preserving the former current
package as `.deploy/previous-known-good.*`. A usable `degraded` response is
accepted for interrupted-job history, but storage and job metadata must be healthy.
If candidate upload, Kudu completion, or readiness fails, a complete prevalidated
`current-verified` package is automatically redeployed and health-checked before
the candidate failure is returned. A first deployment has no automatic restore.
`-Rollback` requires that distinct previous package, verifies its SHA-256 and
embedded commit, redeploys it, then repeats both checks.

## 14a. Migrate the authorization settings

Only needed once, after the release that adds `AUTH_ALLOWED_PRINCIPAL_NAMES`.
The goal is to move the account **email** out of the stable-ID allowlist, where
it never belonged, and into the name allowlist — with no step where both gates
are mismatched. Substitute your own values; never commit them.

Notation used below (all placeholders):

- `<object-id>` — the caregiver account's stable object identifier (GUID).
- `<account-email>` — the exact account name/email, lower-cased.

**Precondition.** The code containing typed name authorization is already
deployed and verified. Confirm with
`curl.exe -sS https://<app-service>.azurewebsites.net/api/health` that
`release_commit` matches the packaged commit. If it does not, stop: on the old
code `AUTH_ALLOWED_PRINCIPAL_NAMES` is ignored and step 2 would lock the
caregiver out.

**Step 1 — add the name allowlist, keep the ID list untouched (both gates
valid).**

```powershell
az webapp config appsettings set -g <resource-group> -n <app-service> `
  --settings AUTH_ALLOWED_PRINCIPAL_NAMES=<account-email>
```

`AUTH_ALLOWED_PRINCIPAL_IDS` still contains `<object-id>,<account-email>`, so
access survives on the legacy exact-ID path regardless of which headers the
platform sends. Verify sign-in and one state-changing action now.

**Step 2 — remove only the email from the ID allowlist.**

```powershell
az webapp config appsettings set -g <resource-group> -n <app-service> `
  --settings AUTH_ALLOWED_PRINCIPAL_IDS=<object-id>
```

Access now comes from the ID path when the platform sends a claim or GUID
header, and from the name path (`principal_name_header`, or the documented
`provider_id_name_compat` bridge for an email-shaped ID header) otherwise.
Verify sign-in and one state-changing action again.

**Never** run step 2 before step 1, and never issue both changes in one command:
that is the only ordering that can leave zero matching gates.

**Rollback.** Each step is independently reversible and always leaves at least
one valid gate:

- To undo step 2: re-add the email to the ID list
  (`AUTH_ALLOWED_PRINCIPAL_IDS=<object-id>,<account-email>`). Do this first if
  access is failing.
- To undo step 1 afterwards: clear the name list
  (`AUTH_ALLOWED_PRINCIPAL_NAMES=`) only once the ID list again contains every
  value that must be accepted.
- Emergency widening (single-tenant deployment, Easy Auth still enforced): set
  both lists empty to restore Easy-Auth-only access, then re-narrow once the
  correct values are confirmed.

Each `az webapp config appsettings set` restarts the site, so queued or running
jobs become `interrupted` and must be re-submitted. Make these changes when no
digest is running.
