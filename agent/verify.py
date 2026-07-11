"""Deterministic reference verification (architecture-review P3).

A fabricated-but-plausible citation is the worst trust failure this tool can
produce, and adaptive-thinking models with a recent knowledge cutoff can invent
PMIDs/NCT IDs. The agents' grounding rules are prompt-level; this is a hard,
non-LLM backstop that checks every cited identifier against its primary registry.

Design (per the review's Phase-3 revision):
- EXISTENCE is the only hard check (does the ID resolve in PubMed / CT.gov). We
  deliberately do NOT enforce title similarity here — report text paraphrases
  titles, so fuzzy matching would false-positive and erode trust in the warning.
- A network error yields "unavailable", NEVER "unverified": an outage must not
  flag a legitimate reference as fake.
"""

from __future__ import annotations

import re

import requests

_PMID_RE = re.compile(r"PMID[:\s]*(\d{6,9})", re.IGNORECASE)
_NCT_RE = re.compile(r"(NCT\d{8})", re.IGNORECASE)


def check_pmid_exists(pmid: str) -> bool | None:
    """True if the PMID resolves in PubMed, False if not, None if unavailable."""
    try:
        r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": pmid, "retmode": "json"},
            timeout=(5, 12),
        )
        r.raise_for_status()
        result = r.json().get("result", {})
        entry = result.get(str(pmid))
        if not entry or "error" in entry:
            return False
        return True
    except requests.RequestException:
        return None
    except ValueError:  # non-JSON body
        return None


def check_nct_exists(nct: str) -> bool | None:
    """True if the NCT ID resolves in ClinicalTrials.gov, False/None otherwise."""
    try:
        r = requests.get(
            f"https://clinicaltrials.gov/api/v2/studies/{nct.upper()}",
            params={"format": "json"},
            timeout=(5, 12),
        )
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return bool(r.json().get("protocolSection"))
    except requests.RequestException:
        return None
    except ValueError:
        return None


def verify_references(text: str) -> dict:
    """Extract and existence-check every PMID/NCT ID in ``text``.

    Returns {"verified": [...], "unverified": [...], "unavailable": [...]} of
    canonical reference strings (e.g. "PMID:40137978", "NCT05477576").
    """
    pmids = sorted({m.group(1) for m in _PMID_RE.finditer(text or "")})
    ncts = sorted({m.group(1).upper() for m in _NCT_RE.finditer(text or "")})
    verified: list[str] = []
    unverified: list[str] = []
    unavailable: list[str] = []

    def _bucket(ref: str, exists: bool | None):
        if exists is True:
            verified.append(ref)
        elif exists is None:
            unavailable.append(ref)
        else:
            unverified.append(ref)

    for pmid in pmids:
        _bucket(f"PMID:{pmid}", check_pmid_exists(pmid))
    for nct in ncts:
        _bucket(nct, check_nct_exists(nct))

    return {"verified": verified, "unverified": unverified, "unavailable": unavailable}


def verification_note(result: dict) -> str:
    """Render a report footer ONLY when something needs flagging (else empty)."""
    if not result.get("unverified") and not result.get("unavailable"):
        return ""
    lines = ["\n\n## ⚠ Reference verification"]
    if result.get("unverified"):
        lines.append(
            "These cited references could NOT be found in their primary registry "
            "and may be inaccurate — do not rely on them without checking: "
            + ", ".join(result["unverified"])
            + "."
        )
    if result.get("unavailable"):
        lines.append(
            "Could not verify (registry unavailable at report time): "
            + ", ".join(result["unavailable"])
            + "."
        )
    return "\n".join(lines)
