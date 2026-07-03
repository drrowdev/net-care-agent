# Changelog

All notable changes to the NET/Care Research Agent are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow strict semantic versioning — versions are
incremented when something user-visible or operationally meaningful changes.

## [Unreleased]

### Added
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
