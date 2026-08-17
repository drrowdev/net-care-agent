# Changelog

All notable changes to the NET/Care Research Agent are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow strict semantic versioning — versions are
incremented when something user-visible or operationally meaningful changes.

## [Unreleased]

### Added
- **Dates can now be typed the way they are read.** The record has displayed
  Finnish dates everywhere since v0.10.0, but every date box still only accepted
  `2026-08-14`. Now `14.8.2026`, `04.08.2026`, `4.8.2026` and `14.8.2026.` all
  record 14 August 2026, `8/2026` records that month and `2026` records that
  year — on the symptom onset and resolution dates, treatment start/stop/planned
  and resolution dates, the treatment follow-up due date, the research event
  date, judgment review and valid-until dates, and every date in the document
  receipt correction editor. The ISO forms still work exactly as before; they
  are simply no longer suggested. Reopening a saved date shows it as
  `14.8.2026`, so saving it untouched changes nothing.

  Nothing about storage moved: the same ISO text is kept, at exactly the
  precision entered, and a partial date is never completed. Anything ambiguous
  or impossible is refused rather than guessed at — `14/8/2026` and `8/14/2026`
  (no way to know which number is the day), `14.8.26` (which century?),
  `2026.8.14`, and `31.2.2026`, `13.13.2026` or `29.2.2026` in a non-leap year.
  A refused date stops the entry and says in plain words what may be typed; it
  is never partly saved. One parser does this in Python (`agent/date_input.py`)
  and one in the browser, and `tests/test_finnish_date_input.py` proves case by
  case that the two accept and reject exactly the same set, so a date the
  browser takes can never be turned away by the server.

### Fixed
- **The assessment no longer contradicts itself about PRRT.** The Assessment
  context panel showed the label **PRRT: POTENTIAL FIT** immediately above its
  own explanation that she *is already receiving Series 2 Lu-177-octreotate*,
  with the treating team tracking cumulative renal dose. Both lines came from
  the same generated assessment, and they disagreed on screen.

  The cause was vocabulary, not a stale value or a wrong answer. The assessment
  could only describe PRRT with words about *screening* — a potential fit, a
  possible fit, needs receptor imaging, not supported — and none of them means
  *a course is already running*. Faced with a patient mid-course, the strongest
  screening word was the closest thing it could say, and the panel then printed
  it as speculation about the future.

  The assessment can now say a course is under way, and the panel labels it
  **PRRT: COURSE RECORDED AS IN PROGRESS**. That is the assessment restating
  what the record shows, not NET/Care deciding anything clinical, and it is
  explicitly not a judgment that treatment should continue: a concern about
  continuing — a dose limit, toxicity, a hold — must still be stated in the
  explanation, the key concern and the next steps, so this can never quietly
  swallow a real disagreement. The screening words are unchanged for anyone who
  has not started PRRT. Nothing reads the explanation's wording to decide what
  the label says; that inference boundary is unchanged.

  This applies to assessments generated from now on. An assessment already
  saved keeps the words it was generated with until the next **Refresh
  assessment** or **Regenerate assessment**.
- **"Open Activity" now opens the import it is talking about.** On Today, the
  **Latest document import** row names one import — its time and its summary —
  but its button dropped you at the top of the whole Activity list to find that
  item yourself. It now opens that import's own record directly. The link is the
  intake job stored on the source document when it was imported, so it is a
  lookup, not a guess about which item you meant.

  Activity records are cleared out over time while the documents themselves are
  kept, so an import can outlive its record. When that has happened the list
  opens as before with a plain note saying the activity record is no longer kept
  and that the document and everything imported from it are unchanged — rather
  than an error, and rather than the browser clearing what it holds. Keyboard
  use and focus are unchanged: the button reads the same, and focus follows the
  record that opens and comes back to Activity when it closes.

  **Open Research** and **Review alerts** on the same card are unchanged. They
  already open the whole of what they name — the research workspace and the
  recorded alert list.
- **The assessment timeline no longer shows machine dates, and reads left to
  right again.** The rows under *What changed / upcoming* still read
  `2026-08 (approx late Aug)`, `2026-08/09` and `2026-09/10` after three earlier
  rounds of date work. The renderer was not at fault — it already called the
  Finnish formatter. The fault was upstream: the assessment's own contract
  described that field as *"YYYY-MM or approximate description"* and told the
  model to *"estimate dates where reasonable"*, so it wrote qualifiers and
  alternatives into a **date** field, and the formatter, which only rewrites an
  exact date and deliberately leaves anything else untouched, passed them
  straight through.

  The contract now asks for a bare calendar date at the precision the record
  actually supports and nothing else, and says that timing wording belongs in
  the event sentence. A deterministic check enforces that after generation, so a
  drifting model cannot reintroduce it: `2026-08 (approx late Aug)` is split
  into the date `2026-08` and the wording `(approx late Aug)`, which moves into
  the event where it reads naturally.

  Assessments already stored still contain the old values, so the display side
  now improves them on its own without anything being regenerated. A recognisable
  date is shown in Finnish with the recorded qualifier kept beside it —
  `8/2026 (approx late Aug)`. Two possible months are shown as
  `8/2026 or 9/2026`; **neither is silently chosen**, because picking one would
  be the app inventing clinical timing. Where even that cannot be read honestly —
  `2026-12/01`, which would need January to be assumed to mean 2027 — it says
  *Timing unclear* rather than guessing, and an item with no timing at all says
  *Timing not recorded*, because those are different facts. No stored value is
  ever rewritten.

  Two related faults went with it. `<time datetime="2026-08 (approx late Aug)">`
  was not a valid machine date, so that attribute is now written only when the
  record really states one date. And past/upcoming was decided by comparing text,
  which marked the whole of August as already past on 14 August, and marked a
  qualified August past because a space sorts below a hyphen; a recorded month or
  year is now compared at the precision it was recorded at, so one that still
  contains today is neither past nor upcoming. Today's date is also read in the
  local zone rather than UTC, which was an hour or three wrong near midnight.

  The horizontal timeline he asked for is back. The one removed in the redesign
  was an SVG graph with hover-only tooltips, no keyboard reach at all, a 400px
  floor that overflowed a phone, event labels cut to 19 characters and English
  month names, so it was rebuilt rather than restored: position along the axis is
  still proportional to real elapsed time, but the axis carries no text and is
  hidden from screen readers, and the readable content sits in an ordered list of
  stops beneath it — which is why no label has to be shortened or dropped any
  more. A month-precision date is drawn as a band across the month it names, not
  as a point on an invented day inside it. Under 720px the axis is dropped and
  the stops stack, which reads better on a phone; nothing scrolls sideways at
  360px.

- **The same due date no longer reads two different ways on two screens.** A
  symptom follow-up's due date was corrected in an earlier round on the episode
  card, but the linked-action line and the follow-up picker still printed it as
  stored, so one screen said `1.9.2026` and the next said `2026-09-01`. The same
  was true of five dates in the research record view — *Recorded*, *Due date*,
  *Date added*, *Registry last updated* and a paper's publication date — which
  were printed by a generic value renderer that showed a scalar exactly as
  stored. That renderer now knows which fields hold a date. The linked-action
  line also stopped printing the stored status code instead of its label.

  The guard that was supposed to prevent all of this asserted that a hand-picked
  list of call sites mentioned a formatter, which is precisely why a site nobody
  had listed kept leaking. It now renders the real screens with every dated field
  set to a machine date and fails if one survives into anything he reads,
  whatever route it took — including accessible names — with a second, cheaper
  check that reads every value interpolated into markup and fails on a
  date-bearing field that has no formatter, next to a written reason for each
  deliberate exception.

- **An interrupted backup can no longer leave a damaged copy that is never
  repaired.** Both protective copies of the record — the pre-write snapshot and
  the once-a-day backup — used to be written straight onto their final filename.
  If one was cut short part-way, by a restart or the machine running out of room,
  what was left behind was **half a file wearing a completely normal timestamp**.
  Nothing could see anything wrong with it: the health page judges the backup by
  its timestamp and calendar day, so it stayed green, and the once-a-day check
  only asked whether a file for today existed, so the damaged one satisfied that
  day permanently and was never written again. The damaged file also stayed on
  the list of things the record could be restored from. The result was a backup
  that looked healthy right up until the moment it was needed.

  Every copy is now written to a temporary file alongside the real one, checked
  there for being complete and readable, and only then swapped into place in a
  single step. A copy that is cut short never becomes the backup. A backup
  already found to be damaged is replaced on the next save rather than trusted
  forever, while a backup that merely could not be read at that moment is left
  untouched — a passing read error is not proof of damage, and overwriting on one
  would throw away the earlier state that backup exists to preserve. A good
  backup for the day is still never rewritten. The checksum file kept beside each
  snapshot is now written the same careful way, so a half-written checksum can no
  longer make the record refuse a perfectly good copy.

  As before, a copy that fails or is refused never stops the record being saved:
  it is recorded in the log and the save goes through regardless.

- **A follow-up due date is now checked in the browser the way the server
  checks it.** The treatment follow-up due field accepted a year or a
  year-and-month in the browser but the server has always required a whole day,
  so a partial entry failed only after pressing save. The field now asks for a
  whole day up front.

### Operations
- **Deploying and rolling back are possible again.** `Scripts/deploy.ps1` builds
  an Authorization header for every Kudu request out of an Azure access token. A
  secret-scrubbing placeholder had been committed over the one line that builds
  it, so the script still fetched the token and still checked it, then discarded
  it and sent a masked value instead. Kudu rejected every such request, so no
  deployment could complete — and because that same line is used by `-Rollback`
  and by the automatic restore that runs when a deployment fails, neither could
  any recovery. Nothing that was already running was affected; the release live
  at the time kept serving normally. The line has been restored byte-for-byte
  from the last known-good commit and is now byte-identical to the one in the
  running release. Nothing else in the deploy script changed, and what gets
  packaged and deployed is unchanged.

  The fault was invisible to review because the same scrubber hides that string
  again whenever the file is displayed, so it had to be found and repaired by
  measuring the line rather than reading it. Two guards now cover it.
  `tests/test_deploy_script.py` evaluates the real `Get-AuthHeaders` against a
  stand-in for the Azure CLI and measures the header it produces, so a header
  that is not the word `Bearer` followed by the token just fetched fails the
  test suite — which is itself one of the gates the deploy script runs before it
  will build a package. `tests/test_redaction_artifacts.py` scans every tracked
  file for committed placeholder text of this kind. Both were confirmed to fail
  against the broken script before the repair. Neither guard prints a token, and
  the deploy script still never echoes one.

- **Leftover `.tmp` files in `snapshots/` and `backups/` are normal and clear
  themselves.** Copies of the record are now staged on a temporary file next to
  the real one, so a crash mid-copy leaves one behind. The next snapshot or
  backup deletes any over an hour old. They are invisible to pruning, to the
  health page and to recovery, and must not be cleaned up by hand — one that is
  still being written would be destroyed. Only the backup for the record's own
  day is re-checked on a save, so a damaged backup from an earlier day is
  rejected rather than repaired; `docs/operating_manual.md` §9 has the check to
  run if you suspect one.

### Changed
- **The last of the database vocabulary left the screen.** This finishes the
  copy rewrite started two releases ago; every remaining item in the audit is
  now done. A **working visit** is an **appointment** ("No appointment has been
  set up yet"), **follow-through tasks** are **follow-ups**, **Create without
  imported appointment** is **Create a new appointment**, and **Enter a manual
  caregiver question** is **Enter the question you want to ask**. The source
  history no longer says documents have been **fed**.
- **The forensic value panels stopped naming JavaScript types.** In the
  treatment differences and source panels, `Boolean: true` now reads **Yes**,
  `Number: 3` reads **3**, `Show exact array` and `Show exact object` are both
  **Show full details**, and `Show exact text (412 characters)` is **Show full
  wording**. In the research panels, `Show exact object` is **Show full
  details**, `Show exact content` is **Show full wording**, `Empty object` is
  **Recorded as empty**, `Title is null` is **No title recorded** and `External
  identifier is null` is **No source ID recorded**. The deliberate distinction
  between a stored blank and nothing at all is still there.
- **Research details are labelled in words, not schema keys.** The research
  authority panels printed stored field names with their underscores swapped for
  spaces, so `registry_last_update` read as "registry last update" and
  `eligibility_excerpt` as "eligibility excerpt". They now read **Registry last
  updated**, **Who the trial is looking for**, **Trial number**, **PubMed
  number**, **Search that found it** and **Added on**. A field with no written
  label keeps its recorded spelling rather than being re-cased into something
  that only looks like a label.
- **Treatment cards and forms stopped repeating "wording".** *Type wording*,
  *Dose wording*, *Route wording* and their siblings are now **Type**, **Dose**
  and **Route**; *Indication wording* is **Reason for treatment**. *Recorded
  components* is **Parts of this wording**, *Observed wording* is **Wording in
  the document**, *Recorded value* is **Saved from that wording**, and *Record
  treating-team outcome* is **Record what the treating team said**.
- **Appointment answers are written the way you would say them.** *Clinician
  answer explicitly unknown* is **Clinician said the answer is not known**,
  *Clinician-attributed answer* is **Answer you heard from the clinician**, and
  *No clinician-attributed decisions captured* is **No decisions from the
  clinician have been recorded yet**. The attribution line beside them is
  unchanged: it still says you recorded it and that it is unverified.
- **Retry messages say what is being sent.** *Retrying the unchanged request…*
  is **Sending the same details again…**, and *The draft changed. Review the
  latest action and submit it as a new request.* is **The text changed. Review
  the latest follow-up and send it again.** Both still mean exactly what they
  did: a retry re-sends the request already saved, and editing the text cancels
  that retry.
- **Section kickers say what is under them.** *Snapshot* is **At a glance**,
  *Secondary view* is **Charts**, *Needs review* is **Alerts to check**,
  *Session details* is **Appointment details**, *Appointment working mode* is
  **During the appointment**, *Current visit record* is **This visit**,
  *Activity report* is **Report details**, and *Grounded in the patient record*
  is **Uses the patient record**.
- **Offline and load-failure messages stopped mentioning snapshots and
  endpoints.** "The imaging endpoint could not be reached and no prior snapshot
  is available" now reads **Imaging could not be reached and no earlier version
  is available**, and the fourteen "Research … authority is invalid" errors now
  each name what could not be shown, in words.
- **"Eligible" stopped describing the app's filtering.** *Link one current
  eligible action*, *Choose an eligible follow-up* and *Select a currently
  eligible action* are all now about the thing itself: **Link a follow-up you
  already have**, **Choose a follow-up to link**.
- **Five API messages stopped describing the data model.** "This job was
  interrupted by a server restart" is **This task stopped when the server
  restarted**; "The research workspace changed" is **The research list
  changed**; "A caregiver treatment workspace preference changed" is **A
  recorded treatment entry was hidden or restored**. The message about an older
  difference was also wrong as well as opaque — it said the record needed "two
  cited authorities", when the second record may be a treatment record you
  entered rather than a second source. It now says the difference **does not
  have both of its linked records**. The fixed PHI-free reason codes behind all
  of these are unchanged.

### Operations
- **The deployment rollback safety net now actually exists.** `Scripts/deploy.ps1`
  kept its verified release packages in a `.deploy/` directory inside the working
  copy. Deployments here are run from fresh throwaway git worktrees, so that
  directory was empty on every run: `-Rollback` reported that no baseline existed,
  and the automatic restore that is supposed to put the previous release back when
  a deploy fails could not fire either — precisely during an outage. Release state
  now lives in one stable place per machine and per app,
  `%LOCALAPPDATA%\net-care-agent\deploy\apps\<app-service>\` (non-Windows:
  `$XDG_STATE_HOME` or `~/.local/state/net-care-agent/deploy`), so a deploy from
  any worktree sees what earlier deploys verified. Set `-StateRoot` or
  `NET_CARE_DEPLOY_STATE_ROOT` to move it. **Back that directory up — it is the
  only copy of the packages rollback can redeploy.**
- Release packages are now immutable and content-addressed (`<commit>-<sha256>`),
  and one `state.json` names the current and previous release. It is replaced in a
  single atomic move, so current and previous can never disagree and a crash can
  no longer leave a half-promoted pair that `-Rollback` might pick up. Packages are
  re-verified — hash and embedded commit — before anything is sent, on rollback and
  on automatic restore as well as on a normal deploy.
- Before arming the automatic restore, the script compares the release it recorded
  as current against the commit `/api/health` actually reports, so a failed deploy
  cannot "restore" a package production was never running. If health cannot be
  reached it falls back to the recorded current, because the app may simply be
  down.
- One deploy at a time per app per machine, via an exclusive lock taken after the
  local test gates and held for the whole upload and health window; a blocked run
  names the process holding it. Old packages are pruned after a successful deploy
  (`-RetainReleases`, default 10), never touching the current and previous pair.
  An interrupted deploy is journalled and reported by the next run.
- An old in-worktree `.deploy/` is verified and adopted once, only when the durable
  store has no current release, and is never moved or deleted.
- Every existing gate is unchanged and in the same order: clean working tree,
  pytest, ruff, gitleaks, Python `zipfile` build, SHA-256 and embedded
  `RELEASE_COMMIT` verification, Kudu upload with authenticated terminal polling,
  the exact-release `/api/health` check, and promotion only after success. The
  health fields the deploy reads are unchanged. `Scripts/Test-DeployState.ps1`
  checks all of this offline, with no network or Azure access, and `pytest` runs
  it. Documented in `docs/operating_manual.md` §14.

### Safety wording
- **The three byte-pinned safety paragraphs were reworded, and each keeps its
  meaning exactly.** They were deliberately deferred by the two previous waves
  because changing them requires updating `INVARIANTS.md` and their pinning
  tests in the same commit; that is what this release does.
  - Treatment (`INVARIANTS.md:387`) now reads **NET/Care records what you enter.
    It does not check whether treatment details are correct or give advice about
    starting, stopping, or changing treatment. Confirm treatment decisions with
    the treating team.**
  - Research (`INVARIANTS.md:269-276`) now reads **NET/Care records the research
    you choose to follow. It does not decide whether research is relevant,
    whether someone is eligible for or enrolled in a study, or whether a
    treatment is suitable. Confirm clinical questions with the treating team and
    trial details with the study site.** All four things NET/Care does not
    decide are still named, and the copy is still non-personalized.
  - Symptom episodes (`INVARIANTS.md:208-214`) now read **NET/Care records what
    you enter. It does not decide how urgent symptoms are or monitor them.**
    The two sentences that route symptoms to the treating team and possible
    emergencies to emergency services are unchanged, to the byte.
- Two research labels and two treatment labels named in the audit were left
  alone on purpose. `Research discovery provenance`, `Caregiver-maintained
  shortlist and disposition workflow`, `Machine-generated compatibility context
  · source linkage unavailable · not a treatment record` and `Legacy/generated ·
  not caregiver lifecycle authority` are never printed: the browser compares
  them field for field to check the response is the one it expects. Rewording
  them would change a protocol value and show nothing to anyone.
- A guard test now scans real string literals — including multi-line template
  literals and accessible names inside them — plus HTML text and the attributes
  a screen reader speaks, and fails if `array`, `object`, `Boolean:`, `Number:`,
  `fed`, `working visit`, `follow-through task`, `provenance`, `durable`,
  `superseded`, `disposition`, `workspace`, `snapshot`, `endpoint`, `read-only`
  or `immutable` reappears in anything readable.

### Changed
- **"Workspace" is gone from everything you read.** It appeared 59 times, in
  headings, buttons, status messages and screen-reader labels. **Research
  workspace** is now just **Research**, **Appointment workspace** is
  **Appointment prep**, and **Not useful in my workspace** is **Not useful to
  me**. The element ids and function names behind them are unchanged.
- **Offline and out-of-date notices say what is actually happening.**
  `Offline snapshot · read-only` now reads **Offline. Showing the last version
  that loaded**, followed by what to do about it. `Stale · read-only` and
  `Read-only snapshot` both became **Out of date**. Where a view is locked, the
  copy now says so in words — "You cannot make changes yet" — rather than
  "read-only".
- **The app stopped narrating its own consistency machinery.** Roughly forty
  messages mentioning an "authoritative" record, reload or workspace now name
  the thing itself: **Loading research…**, **Try loading again**, **Reload the
  treatment record before saving.** Six "transport is uncertain" messages now
  say **The connection dropped, so it is unclear whether that saved.**
- **"Atomic", "immutable" and "lifecycle" left the interface.** **Save outcome
  atomically** is **Save outcome**; **Atomic follow-up link** is **Linked
  follow-up**; **Create one manual action and link atomically** is **Create a
  follow-up and link it in one step**; **Immutable saved snapshot** is **Saved
  exactly as it was**. A replaced decision now reads **This decision was
  replaced. It stays in the record as history and cannot be changed.**
- **Decision statuses stopped being printed as stored codes.** The badge showed
  `needs confirmation` by stripping the underscore out of the stored value. It
  now reads **Needs confirmation**, **Replaced** or **Withdrawn** from the same
  shared lookup introduced in the previous release. **Correct with successor**
  is now **Correct with a replacement**.
- **The CgA badge no longer shouts.** `↑ CgA RISING`, `→ CgA STABLE` and
  `↓ CgA FALLING` are now **CgA rising**, **CgA stable** and **CgA falling**,
  matching the assessment badge fixed last release.
- **Forensic value views say it in words.** In the treatment differences and
  research detail panels, `Null` now reads **Nothing recorded**,
  `Empty string ("")` reads **Recorded as blank**, and `Missing field` reads
  **Not in the record**. The distinction between a stored blank and nothing at
  all is deliberately preserved — it is the point of those panels.
- **The visit recap exports "Status", not "Lifecycle".** The visit, decision
  and follow-up rows of the plain-text export all use the same word, and the
  follow-up row no longer prints the stored code with its underscores stripped.
- **The status-change note stopped printing stored codes.** It read
  "Server-authorized transition from current to past." It now reads **Changing
  this from a current treatment to a past treatment.**
- **The restart reasons stopped speaking as the server.** "The server permits a
  new record linked to this past record." is now **You can add a new treatment
  record linked to this one.**, and "This status record was not recorded as
  having started." is **This record says the treatment never started.**
- **Column headers and kickers describe what you are looking at.** *Import
  provenance* is **Where this came from**, *Source authority* and *Symptom date
  authority* are **Where this came from** and **Where the date came from**,
  *Chart eligibility* is **Can this be charted?**, *Comparable point charts* is
  **Charts**, *Structured alert outcome* is **What happened**, and *Durable
  caregiver task* is **Follow-up**.
- **Two API messages stopped leaking plumbing.** "mutation_id must be 8-128
  ASCII letters, numbers, or . _ : - characters" is now **The request reference
  is not in a form NET/Care can accept.**, and "Severity must be 1-5 or null"
  is **Severity must be a number from 1 to 5, or left empty**.

### Safety wording

Several safety sentences were reworded and every one keeps its meaning exactly;
each is now pinned by a test naming the invariant it protects.

- The imaging note still says NET/Care **does not draw a clinical conclusion**
  (`INVARIANTS.md:153`).
- Open and closed research states still **say nothing about relevance,
  eligibility, availability, enrolment, or whether a treatment is suitable**
  (`INVARIANTS.md:226-233`).
- The differences card still records that **naming one record first does not
  mean it is the right one** (`INVARIANTS.md:296-297`).
- A captured decision is still **what the clinician decided, as you recorded
  it** — the caregiver's own unverified record, never NET/Care's
  (`INVARIANTS.md:99-100`).
- The hidden-treatment notice still states that nothing was deleted, that the
  rows are still counted, and that NET/Care still uses them
  (`INVARIANTS.md:358-369`).

The three byte-pinned safety paragraphs were left untouched by that wave; they
are reworded in this release, above.

### Changed
- **The app now says how a treatment ended, instead of "terminal outcome".**
  In an app about metastatic cancer, "terminal" read as a statement about the
  patient's prognosis; in the code it only ever meant "end state". The whole
  vocabulary was rewritten as one set: the fieldset legend is now
  **How did this treatment end?**, the field is **How it ended**, the action is
  **Record how it ended**, and the four choices read **It started and then
  stopped**, **It never started**, **The plan was cancelled before it started**
  and **Something else**. Legacy rows show **How it ended was not recorded**.
  Two API messages that surfaced the word `terminal` — and one that printed the
  raw field name `terminal_qualifier` — were rewritten too. Stored values,
  wire field names, element ids and the `treatment_projection_invalid` reason
  code are unchanged; only what you read changed.
- **The assessment badge no longer shouts a verdict.** The status pill on
  **Today → Latest assessment** showed `STABLE` / `RESPONDING` / `PROGRESSING` /
  `DATA PENDING` in capitals. It now reads **Assessment: stable**,
  **Assessment: responding**, **Assessment: progression** and
  **Assessment pending**, which keeps it as the generated assessment's own
  language rather than the app appearing to decide progression itself. All four
  are worded the same way, so the badge does not soften only the adverse status,
  and confidence stays where it already was — reported separately. The raw
  stored status is no longer used as a display fallback.
- **The assistant no longer sounds like it triages.** The empty chat panel said
  "Ask anything about the patient's data, research findings, or treatment
  options" and offered "What are the most urgent actions right now?". It now
  says what it is grounded in, states plainly that it is not medical advice, and
  suggests **What follow-ups are still open?** instead.
- **Stored codes stopped being dressed up as labels.** A helper title-cased raw
  database values, so `caregiver_record_corrected` reached the screen as
  "Caregiver Record Corrected" and `source_clarification_needed` as "Source
  Clarification Needed". Those now read **You corrected the record** and
  **Needs checking with the treating team**. A value that is not in the lookup
  is shown exactly as it was recorded, so a lab's own printed flag is never
  re-cased and never replaced by "Not recorded". The four label helpers that
  previously returned their input unchanged now use explicit lookup tables.
- **Blank values are described in words.** Summary rows showed
  `Empty string ("")` and "Empty string recorded"; they now read **Recorded as
  blank**. The forensic "exact stored value" views in the treatment differences
  and research tabs still distinguish a stored null from a stored empty string
  on purpose and are unchanged.
- **Stale and reload messages stopped narrating the internals.** Twelve variants
  of "X is read-only until the authoritative record reloads" and about thirteen
  of "could not be verified safely" were replaced with one consistent
  vocabulary: **Out of date**, "Refresh X before making changes", and "could not
  be loaded safely". Two success messages that claimed the app had *verified*
  something now say **Treatment changes saved.** and **Saved. Research has been
  refreshed.**, because the app verifies a reload, never treatment or research
  facts.
- **"Record recurrence" became "Record this difference again".** It only ever
  meant that a recorded difference had reappeared.
- **Date fields no longer instruct in `YYYY-MM-DD`.** Twenty placeholders,
  helper sentences and validation messages across the UI and the API showed
  machine notation. They now show real examples. Defensive helper text such as
  "Exact partial date; no date is inferred or defaulted" now reads "Enter as
  much of the date as you know. Nothing is filled in for you." One message also
  stopped leaking the field name `occurred_on` and the word `null`.

### Fixed
- **Timeline chips showed "Event" for the three most common entry types.** The
  timeline on **Today → Latest assessment** renders types produced by the
  executive summary (`appointment`, `scan`, `test`, `milestone`, `trial`,
  `deadline`). `milestone`, `trial` and `deadline` had no label and fell through
  to the generic "Event" — including the red **Deadline** chip, which is the one
  most worth reading. All six now have labels.
- **Nine places printed a stored date raw while the rest of the app showed
  Finnish format.** Biomarker document and observation dates, the biomarker
  chart labels, imaging study and document dates, symptom onset and resolution
  dates, treatment course dates, treatment confirmation dates, difference
  follow-up due dates, research event dates, and the visit recap's visit date
  and follow-up due dates, and the symptom source-document date, all bypassed
  the shared formatter, so a stored `2026-08-14` appeared instead of
  `14.8.2026`. They now route through the same
  helper as everything else. The existing guard test only covered three
  functions, which is how these slipped through; it has been extended and a
  dedicated contract added in `tests/test_plain_language_copy.py`.

### Added
- **You can now hide a recorded treatment statement you don't find useful.**
  Every row under **Patient → Treatments → Recorded treatment statements** gained
  a **Not useful in my workspace** action. Some extracted statements are real
  clinical detail your clinicians act on but that you would never mark as an
  ongoing treatment — an infusion run at half speed to reduce nausea, say. This
  collapses such a row out of your Overview.
  - **Nothing is deleted and nothing is withheld from NET/Care.** The statement
    keeps its exact wording, order and components in the patient record, stays in
    the treatment projection, and still reaches the assistant verbatim — so it
    can still answer "why has he been nauseated?" from it. Hiding changes your
    page, never what NET/Care knows. The preference itself never enters any
    prompt.
  - **It is always disclosed and always reversible.** The recorded section shows
    a permanent **N hidden by you · show** control containing every hidden row,
    each with **Show in my workspace**, and states there that nothing was
    deleted. Today reports the visible count and names the hidden count
    separately.
  - **Software never decides relevance.** No keyword list, alias table or model
    judges which therapies matter; only your explicit action changes visibility.
    The deterministic identity library already in the tree could have filtered
    these rows automatically — it deliberately does not, because it would
    silently hide a real therapy it has never heard of. This is the same
    boundary that retired the LLM treatment classifier.
  - Stored as a new `treatment_row_dispositions[]` collection (schema v16) keyed
    by the position-independent `source_entry_id`, **not** the public projection
    row ID, which folds in `source_order` and re-keys whenever an earlier row is
    removed — keying on it would have moved your choice onto a different
    statement. An unknown or orphaned key resolves to *visible*, so if a hidden
    statement's wording is later corrected it reappears rather than staying
    hidden under stale identity.
  - Served as a sibling `legacy_treatment_dispositions[]` on
    `GET /api/patient/treatment-reconciliation` (the `source_fact_documents[]`
    pattern), so no existing snapshot field set widens and no stored citation
    snapshot is invalidated. Set through
    `POST /api/treatment-reconciliation/legacy-rows/<row_id>/disposition` under
    the same guarded contract as every other treatment mutation: both expected
    revisions, projection and per-row tokens, scoped mutation ID, one audit
    event, one save, exact replay as a no-op. It is workflow-only, so it advances
    `workflow_revision` alone and never marks your assessment stale.

### Changed
- **Recorded treatment rows are no longer presented as unfinished work.** Today
  previously reported "*N treatment records need timing/status review*" for every
  raw row not linked to a caregiver status record, and each card read "*Treatment
  timing/status not yet reviewed*". Those rows are wording the record already
  contains — including stops and administration detail — not a to-do list, and
  leaving one unlinked is a legitimate resting state. Today now reports them
  neutrally ("*3 recorded treatment entries are on file*") and the cards state
  what is linked without implying anything is overdue. Linkage itself, its three
  labels, and every stored `legacy_component_ids` value are unchanged.
- **"Recorded treatment information" is now "Recorded treatment statements".**
  The section says plainly that these are statements — starts, stops, dose or
  schedule changes and administration detail — not a list of current treatments,
  and that no status is assigned to them.
- **Model prompts no longer label these rows "TREATMENTS".** The chat prompt's
  `── TREATMENTS ──` heading became `── RECORDED TREATMENT STATEMENTS ──` with a
  fixed caveat that the list is recorded wording including stops and
  administration detail, carries no status or date, and must not be read as
  ongoing therapy. `get_patient_summary` — which reaches the orchestrator,
  executive summary, deep sweep and question prompts — gained the same
  correction; it had been labelling the same collection "Treatments:" in five
  further prompts. **Membership is unchanged**: chat still lists exactly the
  deterministic component split and the summary still lists exactly the raw
  entries, so `INVARIANTS.md` §3's model-visible treatment context rule holds
  verbatim. Only the labelling changed.
  - `INVARIANTS.md` was corrected to describe both prompt paths. It previously
    described only the chat component split, which was silently inaccurate about
    the four `get_patient_summary` consumers.

### Fixed
- **Correcting an imported treatment value can no longer permanently darken the
  Treatments workspace.** If one of your status records linked the components of
  a raw treatment row, correcting, removing or undoing that row through the
  **document import receipt** left the course pointing at components that no
  longer existed. The complete treatment projection then failed closed with
  `422`, so **Patient → Treatments** and the **Today → Treatment status** cards
  went blank — and could not be repaired from the UI, because every treatment
  mutation needs tokens only that projection issues. This was reachable through
  ordinary use: **Record status** pre-ticks the row's components, so a linked
  course is the normal outcome of the primary workflow.
  - The receipt now refuses the edit instead, with a `409` that **names the
    blocking course** and says what to do next: open that course, clear the
    linked recorded entry, then retry. Nothing is written when it refuses — no
    partial correction, removal or undo — and whole-document undo is checked
    before any of its changes are applied.
  - **Nothing is unlinked for you.** Your explicit selection remains the only
    thing that changes a link, so the fix blocks rather than silently rewriting
    workflow state. Stored legacy facts are untouched.
  - A second, advisory check re-projects after the write and restores the
    in-memory record if a projection that had been valid became invalid. Neither
    check refuses an edit because a link is *already* broken — that would be
    unrecoverable, because clearing the link in the workspace needs the very
    projection that is failing — so a record in that state stays repairable.
  - Documented in `docs/operating_manual.md` §1 (*Blocked: a treatment course
    still links that wording*) with the recovery steps.
- **Removing one imported treatment entry no longer deletes identical rows from
  other documents.** Receipt removal filtered out every raw treatment row equal
  to the target, but identical rows legitimately recur — the record counts
  occurrences precisely because they do. A single receipt entry now drops
  exactly one occurrence.
- **Every change to the stored record is now backed up, not just the ones you
  make.** All patient state lives in one `patient_profile.json`, protected by a
  pre-write snapshot and one backup per calendar day. Both were wired into the
  caregiver save path alone, so a write that reached the file any other way left
  the current record with no same-day backup and no snapshot of the revision it
  replaced. Schema migration on load is exactly such a write, and it runs on the
  first request after any release that raises the schema version — no caregiver
  involved. Production `/api/health` caught the real consequence after the last
  release: the profile was rewritten that morning while the newest backup and
  newest snapshot both still belonged to the previous day, and nothing short of
  an ordinary edit could have closed the gap. All four writers — a save, the
  migration write-back, the normalised write after an automated recovery, and an
  operator restore — now go through one protected write that snapshots, replaces
  atomically, and takes the day's backup. A restore additionally keeps the
  revision it discards, which it previously destroyed outright. The atomic
  replace remains the only step that can fail a write: snapshot and backup
  failures are logged and swallowed exactly as before, so protection can never
  block a save.
- **A dropped connection while hiding a row no longer freezes the treatment
  workspace.** The ambiguous-transport recovery path arms the *Retry submission*
  button inside the Record treatment dialog, which is closed for a row-level
  action — so the retry was unreachable while the mutation stayed open, leaving
  every treatment control (adding records, editing courses, resolving
  differences, not just the toggle) disabled until a page reload. Row-level
  actions now release the mutation and reload the authoritative record instead,
  and say plainly that it is unknown whether the change saved. Dialog
  submissions keep the existing retry behaviour, which preserves the exact
  unchanged request.

### Added
- **Mentions in source documents can now start a status record.** Every row in
  **Patient → Treatments → Mentions in source documents** gained a **Record
  status** action beside the existing *View exact wording* / *Open source*
  links. It opens the same **Record treatment** dialog, sends the same guarded
  `POST /api/treatment-reconciliation/courses` mutation, and carries the same
  expected revisions, projection/source/course tokens, scoped mutation ID and
  `409` conflict semantics as the recorded-row action shipped earlier. No second
  creation path or endpoint exists.
  - The dialog is prefilled with the mention's exact observed wording and
    nothing else. **No status, date, terminal qualifier or component link is
    preselected**, because source facts carry no temporal data and their
    `operation` field is list-membership, not a clinical event — a mention
    reading *"Everolimus 10 mg daily was stopped"* is still recorded with
    `operation: added`. The wording stays editable, and the dialog says so: what
    you save is a caregiver-entered record in your own words. It is not stored
    as a quotation and — like every course — it is not linked back to the
    document; only the wording was copied.
- **The treatment workspace now names the document behind each mention.**
  **Patient → Treatments → Mentions in source documents** gained a **Document**
  column showing the originating document's filename — or its document type when
  no filename was recorded — and the document's own date in Finnish format,
  keeping the recorded precision (`2.8.2026`, `8/2026`, `2026`). Missing values
  read *Date not recorded* / *Not recorded* rather than being guessed or
  substituted. This answers "which document, and when" for a recorded treatment
  mention, which previously required opening the raw source text.
  - The identity is served as a new sibling `source_fact_documents[]` key on
    `GET /api/patient/treatment-reconciliation`, keyed by the same opaque `ref`
    as the mention and bound by the projection token. It is deliberately *not*
    extra fields on `source_facts[]`: the citation snapshot validator compares
    that field set by exact equality, so widening it would invalidate every
    stored discrepancy source snapshot and fail the entire read closed with
    `422`. Existing stored snapshots are untouched and still validate.
  - No inference is involved. The pairing uses the receipt-to-change parent
    relationship already present in the projection — no matching, correlation,
    or staleness logic — and it creates no link between a document mention and
    any caregiver course. Course authorship, `capture_method`, the profile
    schema, and the model-prompt exclusion boundary are all unchanged.

### Changed
- **The Record treatment dialog is caregiver-sized again.** Only the record
  status, the treatment wording and the three dates are shown up front. The nine
  optional wording boxes — type, dose, route, frequency, cycle, schedule,
  formulation, indication and notes — moved behind one closed-by-default **Add
  more detail (optional)** disclosure, because the caregiver's own wording
  ("*Continued Somatuline Autogel (lanreotide) 120 mg subcutaneously every 4
  weeks*") normally already carries them, and the course card renders that
  wording as the heading with these fields as a list beneath it.
  - Nothing is hidden from you. When you edit a record that already has optional
    wording the disclosure opens by itself, and the summary says how many boxes
    are filled in whenever any of them hold something — including while the
    section is folded away, so collapsing it cannot conceal wording that will be
    saved. It also opens when a restored draft has content.

### Fixed
- **Dates the assessment writes into its own sentences now read Finnish.**
  Every dated *field* was localised earlier, but a date the model wrote inside a
  sentence — "*three doses every 8 weeks from 2026-05-07*", "*PET-CT on
  2026-04-22 confirmed progression*" — is just text, so no formatter reached it
  and it stayed ISO next to fields reading `7.5.2026`. The generated narrative
  is now normalised as it is drawn: `2026-05-07` becomes `7.5.2026` and
  `2026-05` becomes `5/2026`, using the same helper as every other date.
  - It covers exactly the generated prose you read: the key concern, the status
    rationale, the narrative summary, the CgA-trend and PRRT-screening context
    lines, each recommended action's text, rationale and timeframe, and each
    timeline entry's event copy. A recommendation you save to follow-through
    keeps the assessment's wording on the follow-up card, in the complete,
    cancel and edit dialogs, and in the alert-resolution picker, so those screens
    cannot disagree about the same sentence. Follow-ups you wrote yourself are
    shown exactly as you typed them. The symptom, research and
    treatment-reconciliation action-linking pickers still show the stored
    wording: those projections deliberately omit the origin, and adding it to
    reach them would no longer be a display-only change.
  - It is transcription, not rewriting. Only the punctuation of an unambiguous
    pattern changes — no word is added, removed, reordered or summarised. A bare
    year (`2026`) and a written-out date (*late August 2026*) are left exactly as
    written, as is any digit run that could be structural: an identifier
    (`doc-2026-05-07-abc`), a filename (`report-2026-05-07.pdf`), a timestamp
    (`2026-05-07T10:30:00`), anything inside a URL, and impossible calendar
    values (`2026-13`, `1234-56`). A hyphenated two-year span (`2011-12`) is also
    left alone: by shape it cannot be told apart from December 2011, and showing
    a span as a single month would change the meaning rather than the
    punctuation.
  - Nothing stored changes and nothing sent to the model changes. The record
    keeps the assessment's words verbatim, so this also corrects assessments
    generated before today. `<time datetime="…">` stays machine-readable
    ISO-8601, and the concurrency token the dismiss-action call sends back still
    carries the stored text character-for-character.
- **Corrected a contradiction in the operating manual.** It stated that
  document-intake treatment rows never "seed a form", while the same document
  described — and the shipped **Record status** action implements — copying a
  recorded row's wording and component links into the status-record dialog. The
  guarantee that actually holds is narrower: those rows never create a course on
  their own, authorize a status, or set treatment timing, and the dialog still
  cannot be saved until the caregiver chooses the status.
- **The empty "Current and planned" list is no longer a dead end.** It now names
  the routes that actually exist right now: **＋ Add status record** always, plus
  **Record status** on a recorded treatment entry or on a mention in source
  documents only when such rows are present — so it never sends you to a surface
  that is itself empty. It repeats that you choose the status and any dates. It
  previously stated only that nothing had been recorded.

### Removed
- **Retired the "No exact wording is linked" chip.** It appeared under
  essentially every line of the Today assessment — every recommendation, the key
  concern, every narrative paragraph. The assessment is generated narrative, so
  most of its claims legitimately have no verbatim source span, which made the
  chip a fixed, uninformative sentence repeated down the whole panel rather than
  a signal.
  - The evidence affordance is now drawn only when it carries information:
    **View exact wording: …** still links a claim that is backed by a verified
    span, and **Linked wording is unavailable** still shows when a linked span
    has genuinely gone missing — a real anomaly, not the routine case. When a
    claim has nothing to show, neither a chip nor its container is emitted.
  - This is presentation only. Which claims count as verified, how spans are
    anchored and validated, and every server-side evidence check are untouched;
    the same `verified` / `missing` / `invalid` statuses are still computed and
    still asserted by their tests.
- **Retired the "Record an exact empty string instead of Null" checkboxes.** All
  nine are gone from the Record treatment dialog. They exposed a storage
  distinction that no invariant, schema rule or server behaviour depends on: the
  server accepts and stores both verbatim. An empty box now simply records
  nothing for that detail.
  - **Records that already store an exact empty string keep it.** Editing such a
    record does not silently flip it to null. The box is marked from the *saved*
    value, so leaving it as rendered — including typing in it and clearing it
    again — round-trips the stored empty string unchanged. Only a box that was
    saved as null and left empty is sent as null.
- **Retired the LLM treatment classifier.** Nothing classifies treatments any
  more. The deterministic identity library it was bundled with survives intact
  in the new `agent/treatment_identity.py` (with `agent/classify.py` kept as a
  re-export shim), because `sync_treatment_records` runs it on every document
  import and the frozen v6 migration replays it. Removing the classifier drops
  one Claude call per assessment refresh, per document import, and per digest.
  - **Chat no longer receives treatment status.** The chat prompt now lists the
    deterministic treatment components with no `active`/`planned`/`completed`
    category and no date. This also fixes a live defect where a stale
    classification made chat render a literal `(None)` after each treatment.
  - **The "Automatic compatibility notes" tab was removed** from
    **Patient → Treatments**, along with its always-visible count badge and both
    collapsed sections. Nothing was deleted: the generated rows behind it remain
    stored in `treatments_classified[]`, are still returned by
    `GET /api/patient/treatment-reconciliation` as
    `legacy_treatments[].generated_classification[]` and
    `unlinked_generated_context[]`, and still bind the legacy row and projection
    CAS tokens. This is a presentation-only removal, so no token rotates and no
    in-flight caregiver edit is invalidated.
  - **Today → Treatment status is unchanged by the classifier removal.** It was
    always driven by caregiver-reviewed courses and raw treatment rows, never by
    the classifier. Its display order does change, separately, under _Changed_
    below.
  - `POST /api/treatments/<treatment_id>` is now a `410` tombstone matching its
    siblings `/api/treatments/update` and `/api/treatments/delete`; it had no
    caller in the UI and operated only on generated classification rows.
  - `/api/status` and the summary job result no longer publish
    `treatments_classified`, `treatments_fallback`, or
    `treatments_classification_current`; the frontend never read them.
  - Removed the `ANTHROPIC_MODEL_CLASSIFY` setting and the
    `classification_skipped` log line / classification job warning stage.

### Changed
- **Treatments are listed newest-first.** **Patient → Treatments** and the
  compact **Today → Treatment status** card no longer show treatments in stored
  order, which read as random and made records hard to find. Each of the three
  Overview groups is now ordered newest-first for display: a status record by
  the date its own status is about (planned date when planned, start date when
  current, stop date — falling back to the start date when no stop date was
  recorded — when finished or past), and a row already in the patient treatment
  record by most recently recorded, because those rows carry no date at all. A
  date naming only a year or a month is placed at the start of the period it
  names, so `2026` sits below `2026-03-15` but above `2025-12-31`; records with
  no usable date hold a fixed last position in their group; and equal keys fall
  back to row identity, so the order is total and never shuffles between
  renders. This is presentation only — every row still appears exactly once,
  duplicates are kept, counts are unchanged, and nothing is merged, hidden,
  promoted, or reordered on the server. No date is parsed out of raw wording,
  borrowed from a linked status record, or taken from generated text: NET/Care
  still never infers treatment timing. Imaging, research, and symptom surfaces
  keep their existing stored/server order.
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
- **`/api/health` no longer reports a permanent false `degraded`.** The backup
  freshness check compared the once-per-day `backups/profile_YYYYMMDD.json`
  against the continuously-updated profile with only a 5-minute grace, so
  `backup_out_of_date` became true at the second save of every day and stayed
  true until midnight. Production had been reporting `degraded` continuously
  with everything else healthy, which masked the real signals the field exists
  to surface. The daily backup is now judged on the cadence it is actually
  written on: because `shutil.copy2` preserves the source mtime, a backup's
  mtime is the mtime of the profile revision it captured, so the check compares
  the **calendar day** of the two mtimes instead of their ages.
  `backup_out_of_date` is true when the backup is missing, or when the profile's
  last save falls more than the new `BACKUP_MAX_LAG_DAYS` (default `0`) whole
  calendar days after the newest backup — meaning a day on which the profile was
  saved produced no backup at all. Raw age is deliberately not used: a profile
  left untouched for a week keeps a week-old backup that protects it perfectly,
  and a backup taken early on a busy day can legitimately age indefinitely once
  saves stop. The previously-correct behaviours are unchanged: a missing backup
  still degrades, an untouched eight-day-old profile with an equally old backup
  still stays `ok`, and the signal is still suppressed unless
  `profile_status == "ok"`. No response key was added, renamed, or removed, and
  the `ok`/`degraded`/`error` vocabulary and HTTP status mapping are untouched,
  so `Scripts/deploy.ps1` is unaffected.
- **`daily_backup()` names its file after the profile's mtime, not the wall
  clock.** A save landing at 23:59:59.9 whose `daily_backup()` call ran a tick
  past midnight claimed tomorrow's filename while carrying yesterday's mtime,
  which then suppressed the following day's real backup for the whole day.
  Filename and mtime now always agree, which is what lets the freshness check
  above run with zero days of tolerance.
- **Recovering the profile now takes a backup of the restored state.**
  `restore_from_candidate()` gives the profile a current mtime while the
  candidate it restored from may be days old, so recovery used to leave
  `/api/health` reporting the storage as out of date until the caregiver
  happened to save something. The restored state is also now protected
  immediately rather than only at the next save. A backup failure is logged and
  never fails the recovery.
- **`newest_snapshot_age_seconds` is documented as informational only.** It
  cannot serve as a freshness alarm: `rotating_snapshot()` copies the pre-write
  profile with `shutil.copy2`, so the newest snapshot always carries the
  *previous* revision's mtime and is older than the profile by construction on
  every save — after an idle week a single save writes a brand-new snapshot
  still stamped a week old. Regression tests now pin that this never degrades,
  so the same class of false alarm cannot be reintroduced for snapshots.
- **Dates, times and numbers now read in Finnish everywhere.** Displayed dates
  used hyphens (`14-08-2026`, `08-2026`) and some surfaces fell back to whatever
  locale the browser happened to have, so the same recorded value could render
  as `Aug 14, 2026, 09:26 AM` on one device and something else on another. Every
  displayed date is now `14.8.2026`, a month-precision date is `8/2026`, a
  year-precision date stays `2026`, a range stays en-dash joined as
  `5/2026 – 8/2026`, times are 24-hour `09:26`, a date with a time is
  `14.8.2026 09:26`, and grouped numbers use the Finnish no-break space.
  Interface copy stays English, including relative labels such as `5m ago`.
  Stored values, API payloads, and the ISO dates given to the models are
  unchanged — this is presentation only.
- **Partial dates are no longer completed with an invented day.** A source
  timestamp list, the clinical-notes list, the import-receipt appointment line,
  and the linked-appointment label showed a month- or year-precision date either
  as a raw `2026-08` or, worse, expanded to a full date the record never
  contained. They now display at the precision that was actually recorded.
- **Recorded times no longer display hours in the past.** The follow-through,
  alert-resolution, research-history and outcome timestamps read the server's
  naive ISO stamps as browser-local time while the rest of the interface
  correctly read them as UTC, so every one of them showed two to three hours
  earlier than when it actually happened. All timestamp surfaces now share one
  parser that reads a missing timezone as UTC, matching how the server writes
  them; a value that already carries `Z` or an offset is honoured as written.
- **The latest-assessment stamp no longer shows a raw ISO timestamp.** Today's
  summary header printed `generated_at_timestamp` verbatim (for example
  `Updated 2026-08-12T09:00:00`). It now renders as `Updated 12.8.2026 12:00`.
- **A current assessment can be refreshed again from Today.** Consolidating the
  three duplicate **Refresh assessment** buttons into the freshness banner left
  the banner action revealed only on the stale path, so once the assessment was
  up to date there was no way to rerun it from Today at all. The banner now
  keeps that single control in the same place when the assessment is current,
  labelled **Regenerate assessment** so it reads as a voluntary rerun rather
  than implying new information arrived. Stale wording, the **Generate
  assessment** and **Retry check** states, the guarded request path, duplicate
  suppression, the disabled/generating state, and error handling are unchanged,
  and no second control was added anywhere. To keep the documented Today
  hierarchy intact at 360px, the up-to-date banner now says only
  `Updated <time>` instead of repeating what **Up to date** already states, and
  the phone banner spacing is slightly tighter, so the first recommended next
  step still lands inside the first phone viewport with a 44px touch target.
- **Keyboard focus is no longer stranded when Research PHI is evicted.**
  `relocateResearchFocus()` tried to focus the sidebar nav item while the
  research dialog still held the rest of the page `inert`, so the focus call was
  silently ignored. Focus only left the PHI note field later, when the browser
  asynchronously blurred the hidden dialog, and it landed on `<body>` instead of
  a real destination — a caregiver navigating by keyboard or screen reader lost
  their place mid-eviction. The helper now blurs the outgoing element before
  focusing its destination, matching the symptom, treatment, imaging, and
  biomarker focus fallbacks, and it runs after the dialog is closed so the nav
  item is focusable. Focus now moves to the active nav item synchronously.
  No PHI-scrubbing behaviour changed.
- **Assessment generation no longer aborts on a treatment-classification
  refusal (production failure).** Manual **Generate/Refresh assessment** ran the
  model successfully and then failed the whole job with
  `job_failed … type=TreatmentClassificationError`, so no executive summary was
  produced. Treatment classification is ancillary derived context that fails
  closed on purpose when it cannot certify a lossless raw/model identity
  mapping; it now warns instead of aborting. The manual summary, feed/import,
  and digest jobs catch that refusal and the narrow classifier timeout, leave
  the stored classification and its revision/job identity untouched so
  stale/current stays truthful, log one fixed PHI-free `classification_skipped`
  line (job ID, exception type, wrapped cause type), and finish `status=done`,
  `stage=done_with_warnings` with the assessment generated and persisted. Every
  consumer keeps using the raw `current_treatments` fallback, and the protected
  result/report artifact carries only the bounded notice `Treatment
  classification could not be refreshed; raw treatment records remain
  available.` Classifier strictness is unchanged, no classification is invented
  or partially promoted, and a fault outside that wrapping still fails the job.
- **Hosted authorization restored end to end (production outage).** Every
  state-changing request was rejected with `403` sub-status `60`
  (`Cross-site request forgery detected ... from referer ''`) by the App Service
  Easy Auth middleware, before the request reached Flask, because the app sent a
  global `Referrer-Policy: no-referrer` that suppressed the `Referer` even on
  same-origin requests. Responses now send `Referrer-Policy: same-origin`, which
  restores the `Referer` for this site only and still sends nothing to any other
  origin; off-site anchors keep `rel="noopener noreferrer"`. A runtime test pins
  the emitted header and a browser test asserts the real wire `Referer`, with
  `no-referrer` as the failing control.
- **Durable typed principal authorization.** Identity is now parsed into two
  namespaces that never cross-match: an exact, case-sensitive ID candidate
  (canonical object-identifier claim, `oid`, name-identifier, `sub`, else the
  `X-MS-CLIENT-PRINCIPAL-ID` provider header) constrained by
  `AUTH_ALLOWED_PRINCIPAL_IDS`, and an account-name candidate
  (`X-MS-CLIENT-PRINCIPAL-NAME`) constrained by the new
  `AUTH_ALLOWED_PRINCIPAL_NAMES` with trimming and Unicode-safe `casefold()`
  matching only — dots, plus tags, and domains are never rewritten. Either list
  may authorize a request, so the account email can be migrated out of the
  stable-ID setting without a lockout window (see the operating manual).
  Because the live platform injects the account email into
  `X-MS-CLIENT-PRINCIPAL-ID` and may send neither the encoded blob nor the name
  header, a bounded `local@domain`-shaped ID-header value is also offered as a
  documented convenience name candidate; it never becomes a stable object ID,
  and conflicting email-shaped name sources fail the name path closed. Leaving
  both lists empty keeps the previous Easy-Auth-only behaviour.
- **Fail-closed principal parsing.** Base64 principals now decode from standard
  or URL-safe alphabets with missing padding while rejecting mixed alphabets,
  impossible lengths, corruption, oversized blobs, over-long values, and
  excessive claim counts — never downgrading to a convenience header. Static Web
  Apps `userId`/`userDetails` fallbacks were removed as a different product's
  schema.
- **Authorization before storage.** `_protect_api` is now the first
  `before_request` handler, so an unauthenticated, denied, or cross-origin
  `/api/*` request performs no job-history load, retention prune, or source
  prune. Health, liveness, and authenticated lazy initialisation are unchanged.
- **Actionable, PHI-free denial reasons.** `401`/`403`/`503` auth responses now
  carry fixed `reason` and `principal_source` enums and never an identifier,
  email, claim value, token, or payload. The workspace uses them: a
  `cross_origin` rejection keeps patient data and shows a bounded same-origin
  recovery instead of clearing PHI and recommending an account switch, while
  `principal_not_allowed`, `401`, and any unknown, legacy, or unparseable `403`
  remain fail-closed evictions with the existing duplicate/stale guards.
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
- **Record status directly from a recorded treatment row.** Every card under
  **Patient → Treatments → Recorded treatment information** now carries one
  action, **Record status**. It opens the existing status-record dialog
  (`POST /api/treatment-reconciliation/courses`) pre-filled with that row's
  treatment wording and that row's components already ticked for linking, so
  the resulting course carries the right `legacy_component_ids` and the row
  immediately shows as linked. Previously these rows were entirely read-only:
  the app told the caregiver a row still needed timing/status review, then
  offered no way to act on it, leaving **＋ Add status record** and manual
  retyping as the only path — which is why an ongoing treatment could sit in
  the record while **Current and planned** stayed empty.
  - **Nothing clinical is pre-filled.** No record status is preselected, no
    start/stop/planned date is inferred, and no terminal outcome is chosen; the
    Save button stays disabled until the caregiver picks a status. Copied
    wording is fully editable before saving.
  - Frontend-only, reusing the one existing creation contract: the same
    expected revisions, projection token, scoped mutation ID, serialized
    mutation, and 409 conflict semantics apply, and no token digest input
    changed. Compact **Today → Treatment status** cards stay read-only. A draft
    preserved from a row's dialog is offered again only from that row, and
    reopening it restores the wording without re-ticking a component link the
    caregiver removed.
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
- **Authorization recovery and settings migration.** `docs/operating_manual.md`
  §10a explains how to tell the App Service Easy Auth middleware CSRF rejection
  (`403.60`, empty `Referer`, request never reaches the app) apart from a Flask
  denial, using only the fixed PHI-free `reason`/`principal_source` enums. §14a
  gives the two-step, never-both-at-once migration that moves the account email
  from `AUTH_ALLOWED_PRINCIPAL_IDS` to `AUTH_ALLOWED_PRINCIPAL_NAMES`, with a
  rollback for each step that always leaves at least one valid gate. Do not
  apply §14a before the release containing typed name authorization is verified
  live, and do not restore `Referrer-Policy: no-referrer` in any layer.
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
