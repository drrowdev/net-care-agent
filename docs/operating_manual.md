# Operating manual

Day-to-day workflows for the caregiver. All actions happen in the web UI at the
deployed URL or `http://localhost:8000` for local development.

## 1. Feed a clinical document

When you receive new lab results, an imaging report, or a doctor's note:

1. In the header, click **📄 Feed**. A popover opens anchored under the button.
2. Either:
   - Stay on the **Paste text** tab and paste into the textarea, or
   - Switch to **Upload file** and drop / pick a `.txt` / `.pdf` (PDFs are extracted with `pdfplumber`).
3. Click **→ Process** (or just hit the upload). The popover auto-closes and the
   job appears in the activity log below the executive summary.

The job runs in the background:
   1. **Intake** parses the text and updates biomarkers / imaging / treatments.
   2. **Orchestrator** runs PubMed + ClinicalTrials.gov searches relevant to the new findings.
   3. **Executive summary** is regenerated.
   4. Treatments are re-classified into active / planned / completed.

Reload the dashboard. New papers / trials / alerts appear in their tabs. The job
status moves `running → done` in the activity log; press **Esc** or click the
backdrop to dismiss the Feed popover at any time without submitting.

## 2. Run a research-only digest

Use this when no new document has arrived but you want a fresh literature/trial sweep
(e.g. once a week):

1. UI → **Generate Digest** button.
2. Orchestrator runs without new input; existing biomarker trends are re-analysed,
   new papers / trials added.
3. The text report is saved to `/home/data/reports/report_digest_*.txt`.

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
back with each turn.

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
.\Scripts\run_local.ps1                           # starts Flask on :8000
pytest -q                                         # 45 tests, no network
python Scripts\seed_test_profile.py               # populate a fake profile
```

## 9. Backups & restore

Backups are written automatically every time `save_profile` is called (cheap:
copies once per day, then prunes anything older than 30 days).

To roll back manually:

```bash
# On Azure App Service SSH
ls /home/data/backups/
cp /home/data/backups/profile_20260315.json /home/data/patient_profile.json
```

## 10. Health check

`GET /api/health` returns:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "profile_loaded": true,
  "data_dir": "/home/data",
  "data_dir_writable": true
}
```

Configure this as the App Service health probe — App Service will recycle the
instance if `/api/health` returns 503 for too long (e.g. Azure Files mount is
not writable).

## 11. Running digests

The digest is run on demand via `POST /api/digest` (the "Run digest" button in
the web UI). There is no built-in scheduler — trigger it manually after
uploading new documents, or wire up an external cron (Azure Function timer,
GitHub Actions, etc.) to POST to `/api/digest` if you want automation.
