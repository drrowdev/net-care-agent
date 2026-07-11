# Security Policy

## Reporting a vulnerability

Do **not** open a public issue or include PHI, credentials, prompts, logs, or
source artifacts in a public channel. Report privately to the operator or use
the repository host's private vulnerability-reporting facility when enabled.
Include the affected revision, impact, and a minimal PHI-free reproduction.

For operational support, contact the private operator through the existing
private project channel. This repository does not publish a support address or
promise a response time.

## Scope

This is a **single-tenant, single-patient** decision-support tool. The
threat model is therefore narrow:

- **In scope:** issues in this codebase (Flask app, agent modules,
  static assets, deploy scripts), credential / PHI leakage paths,
  injection vectors in agent prompts, dependency vulnerabilities.
- **Out of scope:** load testing or denial-of-service against a deployment,
  vulnerabilities in upstream services (Anthropic API, PubMed,
  ClinicalTrials.gov, Azure App Service, GitHub Actions), social
  engineering of the project owner.

## Supported versions

Only the latest deployed revision is supported. Older revisions receive no
security fixes.

## Hardening already in place

For transparency, here is what the project already does to reduce risk:

- All Anthropic API calls go through a Key Vault reference; no raw key
  in App Service settings.
- HTTPS-only on the deployed site; storage min TLS 1.2.
- Atomic profile writes (`tmp + os.replace`) — no half-written JSON on
  crash.
- Flask exempts only PHI-free health/liveness; all other hosted APIs require
  platform-enabled Azure App Service Easy Auth (which injects the protected
  `WEBSITE_AUTH_ENABLED` runtime value) and a valid principal.
  An Azure-hosted app without that explicit setting fails closed. External anonymous probing also
  requires matching App Service Easy Auth path exclusions; repository code
  alone cannot bypass the platform gate. An optional exact principal-ID allowlist can
  narrow access further. Local bypass is off unless
  `ALLOW_LOCAL_AUTH_BYPASS=1` is explicitly configured.
- State-changing hosted API requests compare `Origin` only with exact
  `APP_ORIGIN` or canonical HTTPS `WEBSITE_HOSTNAME`; forwarded headers are not trusted.
- In-process feed/general queues are independently bounded. Saturation returns
  `429` before a job record is created; queued/running jobs are interrupted by
  restart and must be re-submitted.
- PDF parsing runs in a child process with a hard timeout, page/text limits,
  output validation, and Unix resource limits. `pdfplumber` is child-only.
- Persisted jobs contain allowlisted metadata and generic errors.
  Reports/results are separate on-demand artifacts; job-runner logs avoid
  document/model content. Legacy retained jobs are sanitized and atomically
  rewritten on load, and protected
  operator logs outside the job runner may include path-bearing OS errors.
  Source access is path-confined, integrity-checked, authenticated, and
  non-cacheable.
- Retention limits prune completed job metadata/artifacts on job admission.
  Unreferenced sources are pruned only at startup or after jobs while holding
  the profile mutation lock. They are best-effort, do not securely erase
  provider/backups, and never prune profile-referenced source artifacts.
- Anthropic and external registry calls have explicit operation timeouts;
  Anthropic SDK retries default to zero and are bounded when configured.
- Branch protection blocks force-push and deletion on `main`.
- GitHub secret-scanning push protection + Dependabot security updates.
- Pre-commit / pre-push hooks + a GitHub Actions Security workflow
  (gitleaks + custom literal-substring scanner) prevent committing
  secrets, PHI, or operator infrastructure identifiers.

If something feels off about any of these, that is a vulnerability —
please report it through the channel above.
