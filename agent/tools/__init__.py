"""Tool registry, schema for Claude tool-use, dispatcher, relevance filter."""

from __future__ import annotations

import datetime

from ..schema import now_stamp
from .biomarkers import analyze_biomarker_trends
from .clinical_trials import search_clinical_trials
from .pubmed import search_pubmed

# ─── JSON schema exposed to Claude ───────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "name": "search_pubmed",
        "description": (
            "Search PubMed for peer-reviewed literature relevant to the patient. "
            "Use for finding research on NET treatments, PRRT, biomarkers, "
            "grade-specific NET prognosis, or any emerging therapy. "
            "Tailor queries to the patient's primary site, grade, and region as "
            "described in the system prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PubMed search query. Use MeSH terms where applicable.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Results to return (default 6, max 10)",
                    "default": 6,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_clinical_trials",
        "description": (
            "Search ClinicalTrials.gov for active or enrolling clinical trials. "
            "Tailor searches to the patient's region (see the system prompt for "
            "configured regions of interest). Search broadly (e.g. "
            "'neuroendocrine tumor') if the patient's primary site is rare."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Condition to search for. E.g. 'neuroendocrine tumor'",
                },
                "status": {
                    "type": "string",
                    "description": "Trial status",
                    "enum": ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"],
                    "default": "RECRUITING",
                },
                "phase": {"type": "string", "description": "Trial phase filter, e.g. 'PHASE2'"},
                "country": {
                    "type": "string",
                    "description": "Country to filter by, e.g. 'USA', 'Germany', or a regional grouping",
                },
            },
            "required": ["condition"],
        },
    },
    {
        "name": "analyze_biomarker_trends",
        "description": (
            "Analyze the longitudinal trend for a specific biomarker from the patient's record. "
            "Use after new lab results are added. Key NET markers: CgA, NSE, 5-HIAA, Ki-67."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "marker_name": {
                    "type": "string",
                    "description": "Biomarker name, e.g. 'CgA', 'NSE', '5-HIAA'",
                },
            },
            "required": ["marker_name"],
        },
    },
    {
        "name": "generate_appointment_questions",
        "description": (
            "Generate a targeted list of questions and preparation items for an upcoming "
            "medical appointment, based on the patient's full profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appointment_type": {
                    "type": "string",
                    "description": "E.g. 'oncology follow-up', 'PRRT consultation', 'nuclear medicine review'",
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific areas to focus on",
                },
            },
            "required": ["appointment_type"],
        },
    },
    {
        "name": "flag_alert",
        "description": (
            "Raise an alert for findings that require action or attention. "
            "Use for: critical lab values, promising new trials found, PRRT eligibility confirmed, "
            "urgent treatment considerations, or significant disease progression."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low"]},
                "message": {
                    "type": "string",
                    "description": "Clear description of the finding or concern",
                },
                "action_required": {"type": "string", "description": "Specific recommended action"},
            },
            "required": ["priority", "message"],
        },
    },
]


# ─── Relevance filter ────────────────────────────────────────────────────────
NET_REQUIRED = [
    "neuroendocrine",
    "carcinoid",
    "net ",
    "nets ",
    "pnet",
    "dotatate",
    "dotatoc",
    "dotanoc",
    "somatostatin",
    "octreotide",
    "lanreotide",
    "pasireotide",
    "prrt",
    "lutathera",
    "lu-177",
    "lutetium",
    "everolimus",
    "sunitinib",
    "temozolomide",
    "streptozocin",
    "capecitabine",
    "chromogranin",
    "cga",
    "gastrinoma",
    "insulinoma",
    "glucagonoma",
    "vipoma",
    "paraganglioma",
    "pheochromocytoma",
]

EXCLUSION_TERMS = [
    "glioblastoma",
    "glioma",
    "melanoma",
    "lymphoma",
    "leukemia",
    "myeloma",
    "breast cancer",
    "prostate cancer",
    "lung cancer",
    "colorectal cancer",
    "pancreatic cancer",
    "hepatocellular",
    "cholangiocarcinoma",
    "cervical cancer",
    "ovarian cancer",
    "endometrial",
    "uterine cancer",
    "bladder cancer",
    "renal cell",
]

NET_TITLE_TERMS = [
    "neuroendocrine",
    "net",
    "carcinoid",
    "dotatate",
    "prrt",
    "somatostatin",
]


def _is_relevant(item: dict, item_type: str) -> bool:
    """Rule-based filter: True only if plausibly relevant to neuroendocrine tumor research."""
    text = " ".join(
        [
            item.get("title", ""),
            item.get("brief_summary", ""),
            item.get("eligibility_excerpt", ""),
            item.get("journal", ""),
        ]
    ).lower()

    if not any(term in text for term in NET_REQUIRED):
        return False

    title_lower = item.get("title", "").lower()
    net_in_title = any(t in title_lower for t in NET_TITLE_TERMS)
    if not net_in_title and any(ex in title_lower for ex in EXCLUSION_TERMS):
        return False

    return True


# ─── Dispatcher ──────────────────────────────────────────────────────────────
def execute_tool(name: str, inputs: dict, profile: dict) -> dict:
    if name == "search_pubmed":
        result = search_pubmed(inputs["query"], inputs.get("max_results", 6))
        existing_pmids = {p["pmid"] for p in profile.get("literature_watched", [])}
        added_at = now_stamp()
        saved = 0
        for article in result.get("results", []):
            if not article.get("pmid") or article["pmid"] in existing_pmids:
                continue
            if not _is_relevant(article, "paper"):
                continue
            profile.setdefault("literature_watched", []).append(
                {
                    "pmid": article["pmid"],
                    "title": article.get("title", ""),
                    "authors": article.get("authors", ""),
                    "journal": article.get("journal", ""),
                    "date": article.get("date", ""),
                    "url": article.get("url", ""),
                    "query": inputs["query"],
                    "date_added": added_at,
                    "relevance_notes": "",
                }
            )
            existing_pmids.add(article["pmid"])
            saved += 1
        return result

    elif name == "search_clinical_trials":
        result = search_clinical_trials(
            inputs["condition"],
            inputs.get("status", "RECRUITING"),
            inputs.get("phase"),
            inputs.get("country"),
        )
        existing_ncts = {t["nct_id"] for t in profile.get("trials_tracked", [])}
        added_at = now_stamp()
        saved = 0
        omitted: list[dict] = []
        for trial in result.get("trials", []):
            if not trial.get("nct_id"):
                omitted.append({"nct_id": "", "reason": "missing_nct_id"})
                continue
            if trial["nct_id"] in existing_ncts:
                omitted.append({"nct_id": trial["nct_id"], "reason": "already_tracked"})
                continue
            if not _is_relevant(trial, "trial"):
                omitted.append({"nct_id": trial["nct_id"], "reason": "not_net_relevant"})
                continue
            profile.setdefault("trials_tracked", []).append(
                {
                    "nct_id": trial["nct_id"],
                    "title": trial.get("title", ""),
                    "status": trial.get("status", ""),
                    "phase": trial.get("phase", ""),
                    "phases": trial.get("phases", []),
                    "countries": trial.get("countries", []),
                    "url": trial.get("url", ""),
                    "brief_summary": trial.get("brief_summary", ""),
                    "eligibility_excerpt": trial.get("eligibility_excerpt", ""),
                    "registry_last_update": trial.get("registry_last_update", ""),
                    "date_added": added_at,
                    "eligibility_notes": "",
                }
            )
            existing_ncts.add(trial["nct_id"])
            saved += 1
        result["persistence_manifest"] = {
            "saved": saved,
            "omitted": omitted,
            "notice": (
                f"{len(omitted)} returned trial(s) were not newly tracked; reasons "
                "are listed explicitly."
                if omitted
                else ""
            ),
        }
        return result

    elif name == "analyze_biomarker_trends":
        return analyze_biomarker_trends(inputs["marker_name"], profile)

    elif name == "generate_appointment_questions":
        # Avoid circular import: questions module depends on tools schema.
        from ..questions import generate_appointment_questions

        return generate_appointment_questions(
            inputs["appointment_type"],
            inputs.get("focus_areas", []),
            profile,
        )

    elif name == "flag_alert":
        alert = {
            "date": datetime.date.today().isoformat(),
            "priority": inputs["priority"],
            "message": inputs["message"],
            "action_required": inputs.get("action_required", ""),
            "resolved": False,
            "added_at": now_stamp(),
        }
        profile["alerts"].append(alert)
        return {"status": "alert_flagged", **alert}

    return {"error": f"Unknown tool: {name}"}


__all__ = [
    "TOOLS",
    "_is_relevant",
    "execute_tool",
    "search_pubmed",
    "search_clinical_trials",
    "analyze_biomarker_trends",
]
