# INVARIANTS — load-bearing rules for the NET/Care Research Agent

**Read this before changing code — especially if you are a smaller/cheaper AI
session.** These are the rules that, if broken, silently corrupt a caregiver's
clinical tool. CI enforces some of them (`tests/test_invariants.py`); the rest
are on you. Nothing here may be routed around. Last verified: 2026-07-03.

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
- **intake** JSON object keys: `document_type, date, summary, biomarkers[],
  imaging_findings, treatment_changes[], ki67_update, sstr_status_update,
  sstr_score_update, symptoms_reported[], key_findings[], suggested_workflows[],
  workflow_rationale`. Biomarker items: `marker, value, unit, reference_range,
  flag`.
- **exec_summary** JSON keys: `overall_status` (enum
  `stable|responding|progressing|insufficient_data`), `status_confidence`
  (`high|medium|low`), `status_rationale, key_concern, summary, prrt_status`
  (`eligible|likely_eligible|pending_dotatate|not_eligible|unknown`),
  `prrt_rationale, cga_trend` (`rising|stable|falling|insufficient_data`),
  `cga_trend_detail, next_actions[], timeline[], best_trial, generated_at`.
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
- **`_run_feed_job` and `_run_digest_job` MUTATE** the profile (they call
  `save_profile`). They MUST run under the single mutating slot
  (`agent.serialized_mutation` / `agent.mutating_lock`) — see §4.
- **`deep_sweep` NEVER saves.** It deep-copies the profile and returns a report
  artifact only. Do not add a `save_profile` call to `agent/deep_sweep.py`;
  `tests/test_invariants.py` asserts its source contains none.
- **`chat` never mutates.** Read-only Q&A.

## 4. Single gunicorn worker is load-bearing
The lost-update protection (`agent/serialize.py`) and the jobs list lock
(`_jobs_lock`) are **in-process** `threading.Lock`s. They only work with ONE
worker. Do NOT scale gunicorn to multiple workers or add autoscale/containers
without first moving these to a cross-process lock (e.g. a file lock on the
Azure Files mount) — otherwise you re-introduce the concurrency bug they fix.

## 5. Prompt templating
System prompts that embed JSON schemas use `agent.llm.render_prompt` with
`[[SENTINEL]]` placeholders (NOT `str.format`, which would need brace-doubling).
`tests/test_prompt_rendering.py` fails if any placeholder leaks into a live
prompt. Preserve every injection point when editing a template.

## 6. Deploy
Manual, via `scripts/deploy.ps1` (test-gated: refuses to build the zip unless
pytest/ruff/gitleaks pass; retains the previous zip as `deploy.prev.zip` for a
one-command rollback). B1 plan has no staging slot — a bad deploy hits
production, so use the script. See `AGENTS.md → Deploy`.

## Provenance and maintenance
- Contract lists here mirror the prompt templates in `agent/*.py`. If you change
  a template's schema, update §2 AND `tests/test_invariants.py` in the same PR.
- Re-verify the read/write discipline: `grep -n save_profile agent/deep_sweep.py`
  (expect no matches) and check `_run_feed_job`/`_run_digest_job` acquire
  `mutating_lock`.
