# Changelog

All notable changes to the NET/Care Research Agent are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow strict semantic versioning — versions are
incremented when something user-visible or operationally meaningful changes.

## [Unreleased]

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
