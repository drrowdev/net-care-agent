# Operating manual

Day-to-day workflows for the caregiver. All actions happen in the web UI at the
deployed URL or `http://localhost:8000` for local development.

Flask exempts the PHI-free `/api/health` and `/api/live` probes; all other
hosted APIs require `WEBSITE_AUTH_ENABLED=true` and App Service Easy Auth.
Generic hosting variables without that explicit setting fail closed. Anonymous external probing also
requires App Service Easy Auth path exclusions. Local APIs are protected unless
`ALLOW_LOCAL_AUTH_BYPASS=1` is explicitly set in the local environment (as in
`.env.example`). Do not set that bypass in hosted configuration.

## 1. Feed a clinical document

When you receive new lab results, an imaging report, or a doctor's note:

1. In the header, click **📄 Feed**. A popover opens anchored under the button.
2. Either:
   - Stay on the **Paste text** tab and paste into the textarea, or
   - Switch to **Upload file** and drop / pick a `.txt` / `.pdf`. PDF extraction
     runs `pdfplumber` only in a contained child process, never in the web
     worker: 30-second hard timeout, 100-page and 1,000,000-character defaults,
     validated output, and Linux resource limits.
3. Click **→ Process** (or just hit the upload). The popover auto-closes and the
   job appears in the activity log below the executive summary.

The job runs in the background:
   1. **Intake** parses the text and updates biomarkers / imaging / treatments.
   2. **Orchestrator** runs PubMed + ClinicalTrials.gov searches relevant to the new findings.
   3. **Executive summary** is regenerated.
   4. Treatments are re-classified into active / planned / completed.

Every feed receives a unique source ID and ingestion timestamp. The original
bytes plus extracted text are written atomically as immutable protected
artifacts; structured biomarkers, imaging, symptoms, appointments, and findings
link back to exact verified quotes where available. The summary's **Evidence**
links open only authenticated, no-cache source/span endpoints and never reveal a
filesystem path.

The server returns `202` with a job ID. The UI polls its status and loads the
report only from that individual job after completion. New papers / trials /
alerts appear in their tabs. The job status moves `queued → running → done` in
the activity log; press **Esc** or click the
backdrop to dismiss the Feed popover at any time without submitting.

Feed has its own bounded queue (one active + two queued by default), independent
of other AI work. If full, the API returns `429` with `Retry-After` (10 seconds
by default) and creates no job record; retry after that delay.

## 2. Run a research-only digest

Use this when no new document has arrived but you want a fresh literature/trial sweep
(e.g. once a week):

1. UI → **Generate Digest** button.
2. Orchestrator runs without new input; existing biomarker trends are re-analysed,
   new papers / trials added.
3. The text report is saved to `/home/data/reports/report_digest_*.txt`.

Only one digest may be active; a duplicate request returns `409`. The report is
not embedded in job history—it is loaded on demand when the activity item opens.

## 2b. Run an ensemble deep-sweep (pre-appointment deep prep)

Use this before an oncology appointment when you want the most thorough,
insight-hunting pass — not just a routine sweep:

1. UI → header **⁂ Deep sweep** button, then confirm the prompt.
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

1. UI → **Judgments** tab → **Add Judgment**.
2. Pick the category:
   - `constraint` — rules out a treatment / trial / approach
   - `preference` — what the oncologist favours
   - `outcome` — past response or side effect
   - `context` — clinical background
3. Write the judgment in plain English (e.g. *"Hilar lymph node assessed as non-urgent — re-image in 3 months"*).
4. Save. The judgment is persisted; future orchestrator and exec-summary runs will
   read it before proposing actions.

Judgments default to **active**. Editing lets you mark one **needs review** or
**superseded**; API clients may also set `scope`, `review_after`, `valid_until`,
and `supersedes`. Once review is due or validity expires, the note remains
visible but is no longer a hard constraint until a clinician reactivates it.

## 4. Resolve / dismiss an alert

1. UI → **Alerts** panel.
2. Click **Resolve** on the card.
3. The alert is marked `resolved=true` in the profile but kept for audit.

## 5. Generate appointment questions

1. UI → **Questions** tab → **Generate**.
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

## 5b. Record review feedback

The executive summary shows confidence, rationale, profile/summary revisions,
freshness, generation time, and evidence links. Use **Report something missed or
incorrect** to record a prominent `missed` review item. This only appends
structured feedback; it never edits patient facts or silently creates a clinical
judgment. Corrected/incorrect/missed feedback on the current summary marks it
stale for conservative review. `GET/POST /api/feedback` supports the full
assessment set: `agreed|corrected|acted|helpful|incorrect|missed`.
`PATCH /api/feedback/<id>` records later assessment, note, or outcome updates
with a new `updated_at` timestamp.

## 5a. Log a symptom

In the sidebar (below **Active alerts**) there is a **Symptoms** block.
Use it to record any patient-reported symptom or side effect — nausea
after lanreotide, persistent fatigue, mild diarrhea, etc.

1. Type the symptom name (e.g. *nausea*).
2. Pick a severity 1–5 (1 = mild, 5 = severe).
3. Optionally add a short note.
4. Click **+**. The entry is saved with `source="manual"` and today's date.

When the intake agent processes a doctor's note that mentions a
patient-reported symptom (e.g. *"patient reports grade-2 diarrhea since
starting lanreotide"*) it logs the symptom automatically with
`source="ai"`. AI-captured entries get a small `AI` tag in the list.
Same-day same-name entries are deduped so re-feeding a document does
not double-log.

All downstream agents read the recent-symptoms block in the patient
summary, so a fresh digest will surface side-effect-management
literature if the orchestrator decides the symptoms warrant it.

## 6. Chat with the record

UI → **✦ Ask Claude** in the header. Free-form conversation grounded in the
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
pytest -q                                         # 45 tests, no network
python Scripts\seed_test_profile.py               # populate a fake profile
```

## 9. Backups, snapshots & automated recovery

### Normal operation

Every `save_profile` call:
1. Writes a pre-save **rotating snapshot** (`/home/data/snapshots/profile_<timestamp>.json`)
   with an optional `.sha256` sidecar.  The last 20 snapshots are kept.
2. Writes a **daily backup** (`/home/data/backups/profile_YYYYMMDD.json`) once per
   calendar day and prunes files older than 30 days.

### Automated recovery on corrupt profile

If `patient_profile.json` has invalid JSON or an unusable structural shape,
`load_profile` automatically:

1. Writes a forensic copy to `/home/data/quarantine/patient_profile_<ts>_<hash8>.json`.
2. Searches for the **newest valid pre-save snapshot**, then the **newest valid
   daily backup**.
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
| `newest_snapshot_age_seconds` | float\|null | Seconds since last snapshot |
| `newest_backup_age_seconds` | float\|null | Seconds since last daily backup |
| `jobs_healthy` | bool | False if jobs.json was quarantined |

**HTTP status codes:**
- `200 status=ok`: everything normal
- `200 status=degraded`: minor issues (interrupted jobs, stale backup)
- `503 status=error`: storage not writable, or profile corrupt with no recovery

Configure `/api/health` as the App Service health probe — Azure will recycle
the instance if it returns 503 persistently (e.g. Azure Files mount not writable).
All fields are aggregate operational metadata; no job content, PHI, path, or
secret is returned.

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

## 13. Retention and PHI artifacts

| Setting | Default | Scope |
|---|---:|---|
| `JOB_RETENTION_DAYS` / `JOB_RETENTION_COUNT` | `365` / `200` | Completed job metadata and indexed report/result artifacts |
| `REPORT_RETENTION_DAYS` / `REPORT_RETENTION_COUNT` | `30` / `200` | Unindexed files under `reports/`; the count rank includes indexed files |
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

New `jobs.json` records store an allowlisted PHI-safe metadata subset and
generic errors. Legacy retained records are not rewritten. Reports and
structured results are separate atomic artifacts; individual authenticated job
lookups read them through traversal-safe roots. Job-runner logs avoid input,
model output, prompts, and traceback. Keep all operator logs protected:
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
the authenticated SCM application process list and `/api/health` critical fields
for the exact packaged commit (300 seconds), and promotes
`.deploy/current-verified.*` only after success, preserving the former current
package as `.deploy/previous-known-good.*`. A usable `degraded` response is
accepted for interrupted-job history, but storage and job metadata must be healthy.
If candidate upload, Kudu completion, or readiness fails, a complete prevalidated
`current-verified` package is automatically redeployed and health-checked before
the candidate failure is returned. A first deployment has no automatic restore.
`-Rollback` requires that distinct previous package, verifies its SHA-256 and
embedded commit, redeploys it, then repeats both checks.
