# HANDOFF — NET/Care Research Agent

**Audience:** the next AI coding assistant (or the next human) taking over this
repo. Read this **first** — it bundles everything you need to be productive on
day one without re-discovering it from chat history.

**Snapshot date:** 2026-05-13. **Repo HEAD at handoff:** `f940163` on `main`
(plus the doc commit that introduces this file).

> If anything here disagrees with the code, **the code wins**. Then update
> this file in the same PR.

---

## 1. What this project is, in one paragraph

A single-tenant clinical research assistant for one neuroendocrine tumour
(NET) patient. The caregiver feeds it clinical documents (lab reports,
imaging, oncology notes); intake/orchestrator/exec-summary agents (all
Claude Sonnet 5) parse them, search PubMed and ClinicalTrials.gov v2 for
relevant developments, and produce a JSON executive summary plus a
caregiver-language appointment-question list. Everything lives in **one
JSON file** on Azure Files. There is no database, no scheduler, no MSAL,
no multi-tenancy. The oncologist's `clinical_judgments` are injected into
every system prompt as hard constraints — the AI never argues with the
doctor. Patient-identifying details (age, sex, primary site, location,
caregiver relationship, output language, regions of interest) live only
in the live `patient_profile.json` on Azure Files; the repo itself ships
no PHI.

It is a **decision-support tool**, not a medical device.

## 2. Owner & deployment essentials

> Concrete resource names, the Azure subscription ID, and the operator
> contact email are intentionally **not** in the public repo. Keep them in
> a private operator runbook outside the repo (or in an untracked
> `docs/operator_setup.md`, which is already covered by `.gitignore`).
> The table below lists only the shape of what you need; substitute your
> own values when you stand up an instance.

| Thing | Value |
|---|---|
| Owner | See private operator runbook |
| Repo | https://github.com/drrowdev/net-care-agent |
| Default branch | `main` |
| Azure subscription | `<subscription-id>` |
| Resource group | `<resource-group>` (Sweden Central) |
| App Service | `<app-service>` (Linux, Python 3.11, B1 plan) |
| Public URL | `https://<app-service>.azurewebsites.net` (gated by Easy Auth — Microsoft personal account) |
| Storage account | `<storage-account>` (Azure Files share `<files-share>` mounted at `/home/data`) |
| Key Vault | `<keyvault-name>` (RBAC, secret `ANTHROPIC-API-KEY`) |
| Recovery Services Vault | `<recovery-vault>` (daily Azure Files backup, 30-day retention) |
| Resource lock | `AzureBackupProtectionLock` on the resource group (CanNotDelete) |

## 3. Where the source of truth lives

| Document | Purpose |
|---|---|
| `README.md` | Architecture overview, repo layout, "how it works" sequence, operating-loops table |
| `CHANGELOG.md` | Every user-visible / operationally meaningful change, Keep-a-Changelog format |
| `AGENTS.md` | **Read this before editing.** Doc-update policy, commit conventions, deploy mechanism, secrets rotation, common pitfalls |
| `HANDOFF.md` | This file. Single-page primer for new assistants |
| `docs/architecture.md` | Component diagram, agent topology, design rationale, **failure-modes table** (resilience checklist) |
| `docs/operating_manual.md` | Caregiver workflows (Feed → Digest → Judgments → Questions) |
| `docs/profile_schema.md` | Shape of `patient_profile.json` |
| `docs/architecture.excalidraw` | Editable architecture diagram (open in https://aka.ms/excalidraw) |

## 4. Repo layout (essentials only)

```
net-care-agent/
├── app.py                # Flask app: HTTP routes + background job runner + /api/health
├── net_agent.py          # Back-compat shim — re-exports the agent.* package
├── startup.sh            # gunicorn launcher (used by App Service)
├── requirements.txt
├── pyproject.toml
├── .env.example
│
├── agent/                # The agent core
│   ├── config.py         # Per-role ANTHROPIC_MODEL_* env vars, paths
│   ├── llm.py            # Anthropic client + JSON-fence stripper
│   ├── profile.py        # load/save (atomic) + DEFAULT_PROFILE + summary builder
│   ├── io.py             # atomic_write_text (tmp + os.replace)
│   ├── backups.py        # Daily JSON snapshot + 30-day retention
│   ├── logging_config.py # text/JSON log formatter
│   ├── judgments.py      # Renders clinical_judgments into the system prompt
│   ├── intake.py         # Document → structured JSON (single Claude call)
│   ├── orchestrator.py   # The only agentic loop; max 12 tool-use iterations
│   ├── classify.py       # Treatment dedup (Somatuline = lanreotide etc.)
│   ├── exec_summary.py   # JSON executive summary generator
│   ├── questions.py      # Appointment questions (language configurable via patient.language)
│   ├── chat.py           # /api/chat handler (pure function, no state)
│   ├── cli.py            # `python net_agent.py {feed|digest|status|update-profile}`
│   └── tools/            # PubMed, CT.gov, biomarker_trend, flag_alert + dispatcher
│
├── static/               # 3-file SPA (do not add a build pipeline)
│   ├── index.html        # Markup + header (📄 Feed popover, status pill, ✦ Ask Claude)
│   ├── app.js            # All client logic
│   └── styles.css        # All styles (incl. .feed-popover, unified main scroll)
│
├── templates/            # (very small, mostly empty — present for Flask convention)
├── tests/                # 45 tests, no network, no API key required
└── docs/                 # See section 3
```

## 5. The five things you'll regret learning the hard way

1. **Build the deploy zip in Python (`zipfile`), not PowerShell `Compress-Archive`.**
   `Compress-Archive` has hung indefinitely on this machine and left
   `wwwroot/` in a broken state with `agent/` missing. Symptom: gunicorn
   crashes with `ModuleNotFoundError: No module named 'agent'`.

2. **Easy Auth returns HTTP 401 to unauthenticated `curl` against the deployed
   site.** That's not a bug — it means the app is healthy and the auth gate is
   working. To smoke-test, hit `/api/health` from a signed-in browser, or
   temporarily disable Easy Auth in App Service settings (and re-enable when
   done).

3. **Repo-local `git config user.name` has been wrong before.** Always run
   `git config user.name` before your first commit. Confirm it matches the
   project owner's configured author name (kept in the private operator
   runbook).

4. **Loose files in `/home/site/wwwroot/` are leftovers from old deploys.**
   Oryx runs from `output.tar.zst`, NOT loose wwwroot files. Don't waste
   time cleaning wwwroot unless something is genuinely broken.

5. **Sonnet 4.6 produces longer JSON than Sonnet 4.0.** All `max_tokens`
   limits in `agent/*.py` were raised in v0.6.0 to 4000–8000 to fit the
   richer responses. If you ever swap models again, eyeball the limits and
   the new `stop_reason == "max_tokens"` guard in `exec_summary.py`.

## 6. Doing things — the boring runbooks

### 6.1 Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env       # then set ANTHROPIC_API_KEY
.\Scripts\run_local.ps1           # or:  python app.py --port 8000
```

Open http://localhost:8000. Local dev is unauthenticated; Easy Auth only
runs on the deployed site.

### 6.2 Run the tests

```powershell
pytest                            # 45 tests, ~2-3s, no network, no key
ruff check agent tests
ruff format agent tests           # auto-format
```

### 6.3 Deploy to Azure (the only way that works)

> Replace `<app-service>` with your App Service site name. The Azure
> resource group, subscription ID, and other identifiers stay in your
> private operator runbook — they're never committed to this repo.

```powershell
# Build zip (Python, not Compress-Archive!)
python -c "import zipfile,os; \
  incl=['app.py','net_agent.py','requirements.txt','startup.sh']; \
  dirs=['agent','static','templates']; \
  z=zipfile.ZipFile('deploy.zip','w',zipfile.ZIP_DEFLATED); \
  [z.write(f) for f in incl if os.path.exists(f)]; \
  [z.write(os.path.join(r,f)) for d in dirs for r,_,fs in os.walk(d) \
    if '__pycache__' not in r and '.pytest_cache' not in r \
    for f in fs if not f.endswith('.pyc')]; \
  z.close(); print('built deploy.zip')"

# Push via Kudu zipdeploy
$tok = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv
Invoke-WebRequest -Uri "https://<app-service>.scm.azurewebsites.net/api/zipdeploy?isAsync=false" `
  -Method POST -Headers @{Authorization="Bearer $tok"} `
  -InFile deploy.zip -ContentType "application/zip" -TimeoutSec 600 `
  -SkipHttpErrorCheck -UseBasicParsing
Remove-Item deploy.zip

# Verify
(Invoke-WebRequest "https://<app-service>.azurewebsites.net/api/health" `
  -SkipHttpErrorCheck -UseBasicParsing).StatusCode    # 200 = ok
```

Oryx will rebuild `output.tar.zst` from your zip; the runtime executes from
the tarball.

### 6.4 Rotate the Anthropic API key

```powershell
az keyvault secret set --vault-name <keyvault-name> `
  --name ANTHROPIC-API-KEY --value <new-key>
az webapp restart -g <resource-group> -n <app-service>
```

Verify the Key Vault reference still resolves:

```powershell
$sub = az account show --query id -o tsv
az rest --method GET `
  --uri "https://management.azure.com/subscriptions/$sub/resourceGroups/<resource-group>/providers/Microsoft.Web/sites/<app-service>/config/configreferences/appsettings?api-version=2022-03-01" `
  --query "value[?properties.secretName=='ANTHROPIC-API-KEY'].properties.status" -o tsv
```

Should print `Resolved`. `InitialFailure` or `RotationFailure` means the
managed identity lost its **Key Vault Secrets User** role on the vault.

### 6.5 Restore the patient profile from a backup

In-app daily snapshots: `/home/data/backups/profile_YYYYMMDD.json` (last 30
days). Just copy one over `/home/data/patient_profile.json` (the runtime
loader is tolerant — restart isn't required, but doesn't hurt).

If `/home/data` itself is gone: restore the Azure Files share from the
Recovery Services Vault listed in your operator runbook.

## 7. Where the bodies are buried (architectural quirks)

- **Single source of truth.** `patient_profile.json` is everything. There is
  no database, no Redis, no per-session state. Don't add hidden caches.
- **`agent.io.atomic_write_text`** wraps every profile write (tmp file +
  `os.replace`) so a crash mid-write never corrupts the JSON.
- **The orchestrator is the only agentic loop.** Max 12 iterations of
  tool-use. Other agents (intake, exec-summary, questions, classify, chat)
  are single-turn, `temperature=0`, return JSON.
- **JSON-decode fallback in every agent.** If Claude returns malformed JSON
  the agent returns an `insufficient_data` shaped object instead of 500-ing
  the whole request. Look for `try: json.loads(raw) except` in each module.
- **Relevance filtering before persist.** `agent/tools/_is_relevant` (rule-
  based, not LLM) drops obviously off-topic PubMed/CT.gov hits before they
  ever touch the profile.
- **Treatment dedup** uses a synonym map (`agent/intake._treatment_similarity`)
  so "Somatuline" and "lanreotide" resolve to the same record.
- **Clinical judgments are hard constraints.** `agent/judgments.py` formats
  every captured oncologist judgment into the system prompt of the
  orchestrator and exec-summary agents — they cannot recommend something
  the doctor has already decided against.
- **No scheduler.** APScheduler + ntfy were intentionally removed in v0.4.0.
  The user prefers the manual **↻ Run digest** button. Don't reintroduce
  background polling without an explicit ask.
- **3-file SPA, no framework.** `index.html` + `app.js` + `styles.css`. The
  caregiver sometimes runs the UI on a phone; zero build pipeline beats any
  framework. Cache headers handle revisions.
- **Unified main scroll.** Exec summary, timeline, and activity log share
  one scrollbar (the timeline used to clip at 55vh — fixed in v0.5.0). The
  document feed is a header-anchored popover (`📄 Feed`), not an inline
  panel.

## 8. Resilience posture (audited 2026-05-07)

| Layer | What protects it |
|---|---|
| Resource group deletion | `AzureBackupProtectionLock` (CanNotDelete) |
| Azure Files share deletion | (a) Recovery Services Vault daily backup, 30d retention; (b) file-share soft-delete, 14d |
| Single-blob overwrite | Blob versioning enabled; blob + container soft-delete, 30d |
| Profile mid-write crash | `atomic_write_text` (tmp + rename) |
| Daily accidental edit | `agent.backups.daily_backup` snapshot, 30d retention, lives on Azure Files (so covered by both backup layers above) |
| Anthropic API outage | Per-agent JSON-decode fallback returning `insufficient_data` |
| HTTPS leakage | App Service `httpsOnly: true`; storage min TLS 1.2 |
| Secret leakage | `ANTHROPIC_API_KEY` in Key Vault, resolved by managed identity, never in plain `appsettings` output |

**Not yet done:**
- App Service plan is Basic (B1) → no deployment slots, no built-in webapp
  config backup. Upgrade to Standard if you need either.
- GitHub branch protection on `main` was never verified (no PAT). Owner
  should add: require PR, block force-push, block deletion.

## 9. Conventions that matter

- **Commits:** imperative present tense (`Add X`, not `Added X`). 72-char
  subject. Always include the Copilot co-author trailer:

  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  ```

- **Doc-update policy:** when you change code, you change the matching
  doc(s) **in the same commit or PR**. The full mapping table is in
  `AGENTS.md` § Doc-update policy. CI does not enforce this — it's
  discipline.

- **No new tooling without an ask.** Don't introduce React, FastAPI,
  Postgres, Docker, Celery, MSAL, an SDK wrapper around Anthropic, or
  anything else that adds a moving part. The simplicity is deliberate.

## 10. Recent history (last ~10 commits)

```
f940163  fix: bump max_tokens for sonnet-4-6 verbosity
f056e49  feat: upgrade Anthropic model to claude-sonnet-4-6
219e9cc  docs(AGENTS): add Secrets section with Anthropic key rotation runbook
ce72cef  docs: log Key Vault migration for ANTHROPIC_API_KEY
5b84624  docs: log resilience hardening (httpsOnly, blob versioning, soft-delete 30d)
9b7b096  Add CHANGELOG.md and AGENTS.md
7dab757  Refresh docs to match current UI
b4a32b9  Unify main column scroll
928591f  Move feed input into header popover
e0c9635  Enlarge activity log scroll surface
```

Older history (Phase 0–6) is summarised in `CHANGELOG.md` v0.1.0–v0.5.0.

## 11. Open work / nice-to-haves

Nothing in flight. The state at handoff is:

- ✅ All 45 tests pass
- ✅ Production app healthy on Sonnet 4.6
- ✅ Secrets in Key Vault, storage hardened, RG locked
- ✅ Working tree clean, `main` pushed to GitHub
- ⚠️ GitHub branch protection on `main` still needs to be enabled in the UI
  by the owner (see §8)
- 💭 Optional next: upgrade to App Service Standard tier to unlock a staging
  deployment slot (would have prevented the 2026-04-29 stuck-deploy outage)

## 12. Contact

- Owner: see private operator runbook
- This handoff written by: GitHub Copilot CLI (Claude Opus 4.7), 2026-05-13
- If you're a future AI assistant: **read `AGENTS.md` next**, then this
  file's referenced docs, then start work. Don't ask the owner questions
  whose answers are already in these files.
