"""ClinicalTrials.gov API v2 client."""

from __future__ import annotations

import re

import requests

MAX_SELECTED_TRIALS = 20

_NET_TERMS = (
    "neuroendocrine",
    "carcinoid",
    "dotatate",
    "prrt",
    "somatostatin",
    "lutetium",
    "lu-177",
    "net",
)


def _parse_study(study: dict) -> dict:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    stat = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    desc = proto.get("descriptionModule", {})
    elig = proto.get("eligibilityModule", {})
    locations = proto.get("contactsLocationsModule", {}).get("locations", [])
    countries = sorted({loc["country"] for loc in locations if loc.get("country")})
    phases = design.get("phases") or []
    if isinstance(phases, str):
        phases = [phases]
    return {
        "nct_id": ident.get("nctId", ""),
        "title": ident.get("briefTitle", ""),
        "status": stat.get("overallStatus", ""),
        "phase": " / ".join(phases),
        "phases": phases,
        "brief_summary": desc.get("briefSummary", ""),
        # Eligibility is intentionally retained verbatim. It is safety-critical
        # context and must not be silently shortened for prompt convenience.
        "eligibility_excerpt": elig.get("eligibilityCriteria", ""),
        "countries": countries,
        "registry_last_update": stat.get("lastUpdatePostDateStruct", {}).get("date", ""),
        "url": f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}",
    }


def _plausibility_key(trial: dict, condition: str, country: str | None) -> tuple:
    text = " ".join(
        (
            trial.get("title", ""),
            trial.get("brief_summary", ""),
            trial.get("eligibility_excerpt", ""),
        )
    ).lower()
    condition_terms = {
        token for token in re.findall(r"[a-z0-9-]+", condition.lower()) if len(token) >= 4
    }
    score = sum(3 for term in _NET_TERMS if re.search(rf"\b{re.escape(term)}\b", text))
    score += sum(1 for term in condition_terms if term in text)
    if trial.get("status") == "RECRUITING":
        score += 2
    if country and country.lower() in {c.lower() for c in trial.get("countries", [])}:
        score += 2
    # Negative score gives descending relevance while NCT ID provides a stable tie-break.
    return (-score, trial.get("nct_id", ""))


def search_clinical_trials(
    condition: str, status: str = "RECRUITING", phase: str = None, country: str = None
) -> dict:
    params = {
        "query.cond": condition,
        "filter.overallStatus": status,
        "pageSize": 100,
        "countTotal": "true",
        "format": "json",
    }
    if phase:
        params["filter.phase"] = phase
    if country:
        params["query.locn"] = country
    try:
        response = requests.get(
            "https://clinicaltrials.gov/api/v2/studies",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        parsed = [_parse_study(study) for study in data.get("studies", [])]
        ranked = sorted(parsed, key=lambda trial: _plausibility_key(trial, condition, country))
        selected = ranked[:MAX_SELECTED_TRIALS]
        omitted = ranked[MAX_SELECTED_TRIALS:]
        total = data.get("totalCount", len(parsed))
        not_fetched = max(0, total - len(parsed))

        manifest = {
            "registry_total": total,
            "evaluated": len(parsed),
            "returned": len(selected),
            "omitted": len(omitted) + not_fetched,
            "returned_nct_ids": [trial["nct_id"] for trial in selected],
            "omitted_nct_ids": [trial["nct_id"] for trial in omitted],
            "selection_rule": (
                "Deterministic plausibility rank using NET/condition terms, recruiting "
                "status, requested country, then NCT ID; no patient eligibility inferred."
            ),
        }
        omission_notice = ""
        if manifest["omitted"]:
            omission_notice = (
                f"{manifest['omitted']} registry result(s) are not included in the "
                "returned trial details. Review selection_manifest before concluding "
                "that no other trials exist."
            )
            if not_fetched:
                omission_notice += (
                    f" {not_fetched} result(s) were beyond the registry page and were "
                    "not evaluated."
                )
        return {
            "trials": selected,
            "condition": condition,
            "total_found": total,
            "selection_manifest": manifest,
            "omission_notice": omission_notice,
        }
    except (requests.RequestException, ValueError) as exc:
        return {"error": str(exc), "trials": []}
