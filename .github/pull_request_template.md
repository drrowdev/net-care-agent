<!--
Thanks for opening a PR. Please complete this checklist before requesting review.
The repository has a strict doc-update policy and a public-safety review — see AGENTS.md.
-->

## What this PR does

<!-- One or two sentences. What changes for the user / operator? -->

## Doc updates included

Per `AGENTS.md` doc-update policy, when you change code you change the
matching docs in the same PR. Tick what applies:

- [ ] `README.md` — updated repo-layout tree / operating-loops table / env vars
- [ ] `CHANGELOG.md` — `[Unreleased]` entry for every user-visible change
- [ ] `docs/architecture.md` — component diagram / agent topology / failure modes
- [ ] `docs/operating_manual.md` — caregiver workflow changed
- [ ] `docs/profile_schema.md` — regenerated via `python -m agent.schema dump-md`
- [ ] `.env.example` — new env var added
- [ ] No doc update needed (internal refactor only — say so here)

## Public-repo safety

- [ ] No patient-identifying details added (age, sex, location, primary site,
      caregiver relationship, name, exact diagnosis string).
- [ ] No operator infrastructure identifiers (subscription ID, resource group,
      App Service name, Key Vault name, storage account, file share, recovery
      vault, custom domains).
- [ ] No personal email addresses (commits should use `@users.noreply.github.com`).
- [ ] If you added a new sensitive substring that the operator wants blocked,
      update **both** the local `.git/info/sensitive-patterns.txt` and the
      `SENSITIVE_PATTERNS` GitHub Actions secret — they live outside the repo.

## Testing

- [ ] `pytest` passes locally
- [ ] `ruff check agent tests` is clean
- [ ] `pre-commit run --all-files` is green (auto-runs on commit anyway)
- [ ] If user-facing: manually exercised the new flow in the deployed app

## Notes for reviewers

<!-- Anything reviewers should pay attention to: design trade-offs, follow-ups, etc. -->
