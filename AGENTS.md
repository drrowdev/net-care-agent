# AGENTS.md — onboarding for AI assistants

This file orients any AI coding assistant (Copilot, Claude, Cursor, etc.)
working in the NET/Care Research Agent repo. **Read it before making changes.**

## What this repo is

A single-tenant clinical research assistant for one Grade 2 metastatic NET
patient. One caregiver user, one patient, one Flask app on Azure App Service.
The patient profile is a single JSON file on an Azure Files mount. Background
agents (intake → orchestrator → exec summary) run via Anthropic Claude with
tool use against PubMed and ClinicalTrials.gov.

Read these in order if you're new:
1. `HANDOFF.md` — single-page primer for new assistants (start here).
2. `README.md` — high-level architecture, repo layout, operating loops.
3. `docs/architecture.md` — component diagram, agent topology, design
   decisions, failure modes.
4. `docs/operating_manual.md` — caregiver workflows.
5. `docs/profile_schema.md` — shape of `patient_profile.json`.

## Project coordination (Chief of Staff)

The user-designated coordinating session is the main point of contact for
software-project work. It maintains the overview, delegates suitable tasks,
reviews the results, and brings decisions back to the user. This is a working
agreement, not a new clinical agent, a permission system, or an always-on service.
A delegated session owns its assigned task, not the coordinator's authority.

### Agreed authority

The coordinator may plan, delegate, implement, validate, document, commit, and
open pull requests for **work the user has agreed**. It may choose implementation
details within that scope. Newly discovered work is a recommendation, not
permission to expand the task or start a new feature.

**Get explicit user approval for every merge and every deployment**, including
a separately requested rollback. Name the exact PR and revision, or release
and deployment target, when asking. If the proposed content changes after
approval, ask again. Approval to implement is not approval to merge; approval
to merge is not approval to deploy. Do not enable automatic merging or bypass
repository protections. A deployment approval must cover the deploy script's
existing automatic failure recovery, not disable or interrupt that safety net.

Also ask before new spending, access or secret changes, changes to live patient
data, or clinical-behavior changes not explicitly included in the agreed task.
Tool access and GitHub admin permissions do not grant user approval. These
boundaries apply to every delegate; a coordinator cannot approve a merge or
deployment on the user's behalf. Existing clinical, privacy, evaluation, and
release safeguards still apply.

### Working loop

- Start or resume from this guidance, `HANDOFF.md`, current GitHub work, and the
  relevant project sessions. Read `INVARIANTS.md` before code changes. Compare
  dated handoff observations with live records; do not assume they are current.
- Keep the agreed priorities, work underway, blockers, and decisions needed
  clear in the coordinating session. Use existing issues and PRs for work that
  needs to survive the session, and the matching docs for lasting decisions.
  Do not create a second task system or duplicate status logs.
- Handle small tasks directly. Delegate substantial, separable work with one
  owner and an isolated branch/session where appropriate. Reuse an existing
  assignment rather than duplicate it; do not take over unrelated sessions.
  Each brief includes the goal, scope, relevant context, approval boundaries,
  completion criteria, and where to report back. Coordinate dependencies before
  assigning overlapping work.
- Before presenting a plan to the user, have a strong model from a different
  provider challenge it. The coordinator owns this step, including for plans
  returned by delegates, and explicitly tells the user it was done. Apply useful
  feedback rather than accepting every suggestion.
- Collect concrete changes, commit/PR references, validation results, and
  remaining blockers from delegates. Inspect the result before recommending
  acceptance. Distinguish implemented, reviewed, merged, and deployed work.
  Report outcomes and decisions in plain English, not tool-by-tool narration.

### Continuity and limits

Shared guidance reaches new default-branch sessions after it is merged into
`main`. Existing sessions do not automatically receive new messages or updated
files; brief active delegates explicitly. Session history can help recover
context, but important decisions must not depend on one assistant remembering
them. A replacement coordinator starts from the shared records and identifies
any gaps.

Production health and the deployed revision are known only from authorized,
dated observations, never inferred from a clean branch or a merged PR. Mark
unobserved state as unknown. Keep patient data, secrets, and private operator
details out of public docs, issues, PRs, and delegation briefs.

No recurring coordinator checks are enabled by this agreement. Scheduling
requires a separate request and an available execution environment; it does not
make an assistant continuously present. The app's manual research/digest
workflow remains unchanged.

## Doc-update policy

**When you change code, you change the matching doc(s) in the same commit
or PR.** No exceptions. CI does not check this; it is a discipline.

| Kind of change | Update these docs |
|---|---|
| New / changed UI flow (header button, popover, tab, panel) | `README.md` (operating-loops table) · `docs/operating_manual.md` |
| New / changed HTTP endpoint | `docs/architecture.md` (component diagram) · `docs/operating_manual.md` if user-facing |
| New / changed agent or tool | `docs/architecture.md` (agent topology + "Why this shape") · `README.md` (repo layout if file added) |
| Profile schema change | `docs/profile_schema.md` · `README.md` (profile schema block) |
| New env var or config | `README.md` (Deployment) · `.env.example` |
| New file or moved file | `README.md` (repo layout tree) |
| Any user-visible change | `CHANGELOG.md` under `[Unreleased]` |
| Operational fix or recovery procedure | `CHANGELOG.md` (Operations subsection) · `docs/operating_manual.md` if it's a runbook |

If a change genuinely needs no doc update, say so explicitly in the PR
description ("no doc update needed — internal refactor only") so reviewers
know it was considered.

## Commit conventions

- **Imperative, present tense** subject (`Add feed popover`, not `Added`).
- Wrap subject at ~72 chars; body wrapped at ~80.
- Co-author trailer on every Copilot-authored commit:

  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  ```

- Don't squash unrelated changes into one commit.

## Deploy

- **Source of truth:** `main` branch on GitHub.
- **Hosting:** Azure App Service (Linux, Sweden Central), behind Easy Auth
  (Microsoft account). Concrete resource names live in a private operator
  runbook, never in the repo.
- **Deploy mechanism:** zip-deploy via Kudu (`POST /api/zipdeploy`), which
  triggers Oryx to build `output.tar.zst` from the uploaded zip. Build the
  zip in Python (`zipfile` module), **not** PowerShell `Compress-Archive` —
  the latter has hung indefinitely on this machine and left wwwroot in a
  broken state.
- Always include in the deploy zip:
  `app.py net_agent.py requirements.txt startup.sh agent/ static/ templates/`
  (skip `__pycache__`, `.pytest_cache`, `*.pyc`).
- Use `Scripts/deploy.ps1`, not a hand-built upload. It gates on
  pytest/ruff/gitleaks, verifies SHA-256, records HEAD, polls asynchronous Kudu
  and authenticated terminal Kudu status plus `/api/health`
  critical fields and exact packaged commit, and promotes
  the release to `current-verified` only after success, keeping the former
  current release as `previous-known-good`. A dirty working tree is
  rejected. `-Rollback`
  verifies and redeploys that exact package.
- **Release state is per-machine, not per-worktree.** Deploys are run from
  throwaway git worktrees, so state kept inside the working copy was empty every
  time and `-Rollback` never had a baseline. It now lives in
  `%LOCALAPPDATA%\net-care-agent\deploy\apps\<app-service>\` (non-Windows:
  `$XDG_STATE_HOME`, else `~/.local/state/net-care-agent/deploy`), keyed by app
  name. Override with `-StateRoot` or `NET_CARE_DEPLOY_STATE_ROOT`; the path
  must be absolute and is created on demand. Back this directory up — it is the
  only copy of the rollback packages.
- Releases are immutable and content-addressed (`<commit>-<sha256>`), and
  `state.json` names current/previous in one atomically replaced file, so a
  partially written baseline cannot exist. `Scripts/deploy-state.ps1` owns this;
  `Scripts/Test-DeployState.ps1` exercises it without deploying, and `pytest`
  runs that harness.
- A legacy in-worktree `.deploy/` is adopted once, after verification, if the
  durable store has no current release. Its files are only ever read and copied,
  never moved or deleted.
- One deploy at a time per app: the script holds an exclusive lock for the whole
  remote window and fails fast if another deploy holds it. The lock is per
  machine and per user — it cannot coordinate two different machines.
- Keep `.deployment` (`SCM_DO_BUILD_DURING_DEPLOYMENT=true`) and exact runtime,
  dev, and setuptools build pins. The script includes `.deployment`, ensuring
  Oryx build-on-deploy is active.
  One Gunicorn worker is load-bearing because queues/execution are in-process.

## Secrets

`ANTHROPIC_API_KEY` is **not** in App Service app settings. It lives in an
Azure Key Vault secret named `ANTHROPIC-API-KEY`, resolved by the webapp's
system-assigned managed identity via an
`@Microsoft.KeyVault(SecretUri=…)` reference. Don't paste a raw key back
into appsettings — that defeats the audit trail.

**Rotate the Anthropic key:**

```powershell
az keyvault secret set --vault-name <keyvault-name> `
  --name ANTHROPIC-API-KEY --value <new-key>
az webapp restart -g <resource-group> -n <app-service>
```

Verify the reference still resolves:

```powershell
$sub = az account show --query id -o tsv
az rest --method GET --uri "https://management.azure.com/subscriptions/$sub/resourceGroups/<resource-group>/providers/Microsoft.Web/sites/<app-service>/config/configreferences/appsettings?api-version=2022-03-01" --query "value[?properties.secretName=='ANTHROPIC-API-KEY'].properties.status" -o tsv
```

Should print `Resolved`. If it prints `InitialFailure` or `RotationFailure`,
the managed identity lost its **Key Vault Secrets User** role on the vault.

## Common pitfalls

- **Local git user override.** This repo has had `user.name` set locally to
  the wrong value, overriding the global config. Run `git config user.name`
  before your first commit and confirm it matches the project owner's
  configured author name.
- **Stale `wwwroot/`.** Loose files in `/home/site/wwwroot/` (e.g. old
  `app.py`, `staticindex.html`) are leftovers from earlier deploys and are
  ignored at runtime — Oryx runs from `output.tar.zst`. Don't waste time
  trying to clean them unless it's actually causing a problem.
- **Easy Auth returns 401 on unauthenticated API `curl`.** Flask exempts
  PHI-free `/api/health` and `/api/live`, but App Service path exclusions are
  also required for anonymous external probes. Do not disable Easy Auth to
  smoke-test. Local APIs require explicit
  `ALLOW_LOCAL_AUTH_BYPASS=1`, and hosted mode ignores it.
- **Never ship `Referrer-Policy: no-referrer`.** The Easy Auth middleware runs
  its own CSRF check ahead of Flask and rejects any state-changing request whose
  `Referer` is empty with `403` sub-status `60`, so a `no-referrer` document
  policy takes the whole API down while `/api/health` still looks fine. Ship
  `same-origin`; off-site anchors opt out individually with
  `rel="noopener noreferrer"`.
- **Two typed allowlists.** `AUTH_ALLOWED_PRINCIPAL_IDS` is exact and
  case-sensitive and matches only a stable ID;
  `AUTH_ALLOWED_PRINCIPAL_NAMES` matches only the account name/email with
  trimming plus `casefold()`. Either may authorize a request. Migrate values
  between them one step at a time (`docs/operating_manual.md` §14a); never edit
  both settings in one command.
- **No scheduler.** Daily digest + ntfy were intentionally removed in
  v0.4.0. Don't reintroduce them without a strong reason — the user
  prefers manual `↻ Run digest` triggered from the header.
- **Single source of truth.** All patient state is `patient_profile.json`.
  No conversation memory persists between requests. Don't add hidden
  per-session state.

## Tests, lint, format

```powershell
pytest                           # no network, no API key
ruff check agent tests           # CI runs this
ruff format agent tests          # auto-format
pre-commit install               # one-time
```

Add a test for any non-trivial agent or tool change. Use the recorded HTTP
fixtures and the fake Anthropic client (`tests/conftest.py`) — never call
the real APIs from a test.

## Out of scope

- Multi-tenant. One patient, one caregiver. Don't add user accounts.
- Mobile app. The SPA works on phones; that's enough.
- Real-time push. The digest is on-demand by design.
