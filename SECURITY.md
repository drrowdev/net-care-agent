# Security Policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in this project,
please **do not open a public GitHub issue**. Instead, use GitHub's
private vulnerability reporting:

1. Go to https://github.com/drrowdev/net-care-agent/security
2. Click **"Report a vulnerability"** under *Advisories*
3. Describe the issue, the affected version (e.g. `v0.7.0`), and ideally
   a minimal reproduction. Mark "I think this is a vulnerability" so it
   becomes a private advisory only the owner and you can see.

You should receive an acknowledgement within a few days. There is no
bug-bounty programme attached to this project.

## Scope

This is a **single-tenant, single-patient** decision-support tool. The
threat model is therefore narrow:

- **In scope:** issues in this codebase (Flask app, agent modules,
  static assets, deploy scripts), credential / PHI leakage paths,
  injection vectors in agent prompts, dependency vulnerabilities.
- **Out of scope:** denial-of-service against the demo deployment,
  vulnerabilities in upstream services (Anthropic API, PubMed,
  ClinicalTrials.gov, Azure App Service, GitHub Actions), social
  engineering of the project owner.

## Supported versions

Only the latest release (`v0.7.0` at time of writing) receives security
fixes. Older versions have no support.

## Hardening already in place

For transparency, here is what the project already does to reduce risk:

- All Anthropic API calls go through a Key Vault reference; no raw key
  in App Service settings.
- HTTPS-only on the deployed site; storage min TLS 1.2.
- Atomic profile writes (`tmp + os.replace`) — no half-written JSON on
  crash.
- Single-user gate via Azure App Service Easy Auth.
- Branch protection blocks force-push and deletion on `main`.
- GitHub secret-scanning push protection + Dependabot security updates.
- Pre-commit / pre-push hooks + a GitHub Actions Security workflow
  (gitleaks + custom literal-substring scanner) prevent committing
  secrets, PHI, or operator infrastructure identifiers.

If something feels off about any of these, that is a vulnerability —
please report it through the channel above.
