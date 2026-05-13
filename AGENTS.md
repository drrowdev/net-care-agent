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
- **Easy Auth returns 401 on `curl`.** That's expected for the deployed
  site. To smoke-test the app, check `/api/health` from a signed-in browser
  or temporarily disable Easy Auth in App Service settings (then re-enable).
- **No scheduler.** Daily digest + ntfy were intentionally removed in
  v0.4.0. Don't reintroduce them without a strong reason — the user
  prefers manual `↻ Run digest` triggered from the header.
- **Single source of truth.** All patient state is `patient_profile.json`.
  No conversation memory persists between requests. Don't add hidden
  per-session state.

## Tests, lint, format

```powershell
pytest                           # 45 tests, no network, no API key
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
