"""ClinicalTrials.gov API v2 client."""

from __future__ import annotations

import requests


def search_clinical_trials(
    condition: str, status: str = "RECRUITING", phase: str = None, country: str = None
) -> dict:
    params = {
        "query.cond": condition,
        "filter.overallStatus": status,
        "pageSize": 10,
        "format": "json",
    }
    if phase:
        params["filter.phase"] = phase
    if country:
        params["query.locn"] = country
    try:
        r = requests.get(
            "https://clinicaltrials.gov/api/v2/studies",
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        studies = []
        for s in data.get("studies", []):
            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            stat = proto.get("statusModule", {})
            desc = proto.get("descriptionModule", {})
            elig = proto.get("eligibilityModule", {})
            locs = proto.get("contactsLocationsModule", {}).get("locations", [])
            countries = list({loc.get("country", "") for loc in locs if loc.get("country")})

            studies.append(
                {
                    "nct_id": ident.get("nctId", ""),
                    "title": ident.get("briefTitle", ""),
                    "status": stat.get("overallStatus", ""),
                    "phase": stat.get("phase", ""),
                    "brief_summary": desc.get("briefSummary", "")[:400],
                    "eligibility_excerpt": elig.get("eligibilityCriteria", "")[:600],
                    "countries": countries,
                    "url": f"https://clinicaltrials.gov/study/{ident.get('nctId','')}",
                }
            )
        return {
            "trials": studies,
            "condition": condition,
            "total_found": data.get("totalCount", 0),
        }

    except requests.RequestException as e:
        return {"error": str(e), "trials": []}
