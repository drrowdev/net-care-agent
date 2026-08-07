"""Tool registry, schema for Claude tool-use, dispatcher, relevance filter."""

from __future__ import annotations

import datetime
import re

from ..provenance import new_record_id
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
            "Use for critical values, potentially relevant trial/PRRT screening findings "
            "requiring clinician confirmation, urgent treatment considerations, or significant "
            "disease progression. Never claim eligibility, qualification, or a best match."
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
_DEFINITIVE_SCREENING_RE = re.compile(
    r"\b(?:eligib\w*|qualif\w*|inclusion\s+criteria|"
    r"inclusion\s+requirements?|"
    r"meets?\s+(?:all\s+)?(?:inclusion|criteria)|"
    r"satisf(?:y|ies|ied)\s+(?:all\s+)?(?:inclusion\s+)?(?:criteria|requirements?)|"
    r"(?:should|must|can)\s+be\s+includ\w*|"
    r"enroll\w*|enrol\w*|"
    r"(?:one\s+of\s+the\s+)?(?:best|ideal|perfect\w*)[- ]+(?:fit|match\w*)|"
    r"(?:ideal|suitable)\s+candidate|candidate\s+for|"
    r"matches?\s+(?:the\s+)?(?:trial\s+)?criteria|"
    r"(?:good|strong)\s+fit)\b",
    re.IGNORECASE,
)
_NEGATED_SCREENING_RE = re.compile(
    r"\b(?:not\s+eligible|ineligible|not\s+qualified|unqualified|"
    r"does\s+not\s+qualify|cannot\s+qualify|"
    r"(?:patient\s+is\s+)?excluded\s+(?:from|because)|"
    r"(?:do|should)\s+not\s+enroll|cannot\s+enroll|"
    r"excludes?\s+enrollment|fails?\s+(?:the\s+)?inclusion)\b",
    re.IGNORECASE,
)
_SCREENING_CONTEXT_RE = re.compile(r"\b(?:trial|study|protocol|prrt|nct\d+)\b", re.IGNORECASE)
_SCREENING_ASSERTION_RE = re.compile(
    r"\b(?:candidate|suitable|fit|match\w*|criteria|eligib\w*|qualif\w*|"
    r"inclusion|exclusion|enroll\w*|enrol\w*|excellent|compelling|ideal|top|"
    r"indicat\w*|appropriate|benefit\w*|receive|offer\w*)\b",
    re.IGNORECASE,
)
_SCREENING_HISTORICAL_RE = re.compile(
    r"\b(?:(?:was|were|had\s+been)\s+(?:considered\s+)?(?:indicat\w*|appropriate|suitable|"
    r"eligible|qualified|a\s+candidate)|"
    r"(?:prior|previous|historical)\s+(?:note|plan|assessment)\s+(?:said|stated|"
    r"recorded)?(?:(?![.;]|\b(?:and|but|however|then|now)\b).)*?"
    r"(?:benefit\w*|candidate|fit|match\w*|indicat\w*))\b",
    re.IGNORECASE,
)
_SCREENING_CLAUSE_SPLIT_RE = re.compile(
    r"(?:[.;]|\s+[–—-]\s+|,\s*(?:but|and)\s+|\s+(?:but|however)\s+)",
    re.IGNORECASE,
)
_TREATMENT_CHANGE_VERB = (
    r"(?:start(?:ing)?|stop(?:ping)?|hold(?:ing)?|paus(?:e|ing)|resum(?:e|ing)|"
    r"switch(?:ing)?|increas(?:e|ing)|decreas(?:e|ing)|redos(?:e|ing)|"
    r"titrat(?:e|ing)|discontinu(?:e|ing)|withhold(?:ing)?|omit(?:ting)?|"
    r"skip(?:ping)?|administer(?:ing)?|tak(?:e|ing)|reduc(?:e|ing)|"
    r"restart(?:ing)?|continu(?:e|ing)|initiat(?:e|ing)|escalat(?:e|ing)|"
    r"de-escalat(?:e|ing))"
)
_TREATMENT_RECOMMENDATION_RE = re.compile(
    rf"\b(?:recommend\w*|advis\w*|needs?\s*(?::|to)|should|must|"
    rf"plan(?:\s+is)?\s*(?::|to)|consider(?:ed|ing)?\s+).*?\b"
    rf"{_TREATMENT_CHANGE_VERB}\b",
    re.IGNORECASE,
)
_TREATMENT_MODAL_PASSIVE_RE = re.compile(
    r"\b(?:should|must|needs?\s+to)\s+be\s+"
    r"(?:started|stopped|held|paused|resumed|switched|increased|decreased|"
    r"redosed|titrated|discontinued|withheld|omitted|skipped|administered|taken|"
    r"reduced|restarted|continued|initiated|escalated|de-escalated)\b",
    re.IGNORECASE,
)
_TREATMENT_COMMAND_RE = re.compile(
    rf"^\s*(?:(?:please|immediately|now)\s+)*(?:do\s+not\s+)?" rf"{_TREATMENT_CHANGE_VERB}\b",
    re.IGNORECASE,
)
_TREATMENT_GERUND_RE = re.compile(
    r"^\s*(?:starting|stopping|holding|pausing|resuming|switching|increasing|"
    r"decreasing|redosing|titrating|discontinuing|withholding|omitting|skipping|"
    r"administering|taking)\b",
    re.IGNORECASE,
)
_TREATMENT_HISTORICAL_RE = re.compile(
    r"\b(?:was|were|has\s+been|had\s+been)\s+"
    r"(?:started|stopped|held|paused|resumed|switched|increased|decreased|"
    r"redosed|titrated|discontinued|withheld|omitted|skipped|administered|taken|"
    r"reduced|restarted|continued|initiated|escalated|de-escalated)\b",
    re.IGNORECASE,
)
_TREATMENT_NOUN_EVENT_RE = re.compile(
    r"^\s*(?:start\s+of|hold\s+on)\b.*\b(?:was|were|has\s+been|had\s+been)\b",
    re.IGNORECASE,
)
_TREATMENT_CANCELLED_HISTORY_RE = re.compile(
    rf"(?:\b(?:plan|recommendation|advice|proposal)\b.*?\b{_TREATMENT_CHANGE_VERB}\b|"
    rf"^\s*{_TREATMENT_CHANGE_VERB}\b.*?)"
    r".*?\b(?:was|were|has\s+been|had\s+been)\s+"
    r"(?:cancelled|canceled|abandoned|withdrawn|postponed|deferred|discontinued)\b",
    re.IGNORECASE,
)


def _screening_clause_is_historical(clause: str) -> bool:
    matches = list(_SCREENING_HISTORICAL_RE.finditer(clause))
    if not matches:
        return False
    remainder = list(clause)
    for match in matches:
        remainder[match.start() : match.end()] = " " * (match.end() - match.start())
    return not _SCREENING_ASSERTION_RE.search("".join(remainder))


def _screening_safe_alert_text(value: object) -> str:
    original = str(value or "").strip()
    treatment_directive = False
    for clause in (
        item.strip()
        for item in re.split(
            r"[.;,:]|\s+[-–—]\s+|\b(?:but|then)\b",
            original,
            flags=re.IGNORECASE,
        )
        if item.strip()
    ):
        if _TREATMENT_CANCELLED_HISTORY_RE.search(clause):
            continue
        recommendation = bool(_TREATMENT_RECOMMENDATION_RE.search(clause))
        historical = bool(
            _TREATMENT_HISTORICAL_RE.search(clause) or _TREATMENT_NOUN_EVENT_RE.search(clause)
        )
        directive = bool(
            recommendation
            or _TREATMENT_MODAL_PASSIVE_RE.search(clause)
            or _TREATMENT_COMMAND_RE.search(clause)
            or _TREATMENT_GERUND_RE.search(clause)
        )
        if directive and (recommendation or not historical):
            treatment_directive = True
            break
    if treatment_directive:
        return (
            "A treatment-change question was identified; contact the treating team and "
            "confirm before any treatment change."
        )
    screening_clauses = [
        clause.strip() for clause in _SCREENING_CLAUSE_SPLIT_RE.split(original) if clause.strip()
    ]
    if _SCREENING_CONTEXT_RE.search(original) and any(
        _SCREENING_ASSERTION_RE.search(clause) and not _screening_clause_is_historical(clause)
        for clause in screening_clauses
    ):
        return (
            "Trial or PRRT screening information identified; the treating team and trial "
            "site must review the complete criteria and enrollment status before action."
        )
    if _NEGATED_SCREENING_RE.search(original) or _DEFINITIVE_SCREENING_RE.search(original):
        return (
            "Trial or PRRT screening information identified; the treating team and trial "
            "site must review the complete criteria and enrollment status before action."
        )
    text = original
    replacements = (
        (r"\beligibility confirmed\b", "potential fit requiring clinician confirmation"),
        (r"\beligibility\b", "potential fit requiring clinician confirmation"),
        (r"\beligible\b", "a potential fit"),
        (r"\bqualif\w*\b", "potential fit"),
        (
            r"\b(?:one of the )?(?:best|ideal|perfect\w*)[- ]+match(?:es|ed)?\b",
            "potentially relevant",
        ),
        (r"\bperfectly[- ]matched\b", "potentially relevant"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    if text != original and "clinician confirmation" not in text.casefold():
        text = f"{text} — clinician confirmation required"
    return text


def execute_tool(
    name: str,
    inputs: dict,
    profile: dict,
    *,
    source_document_id: str | None = None,
    source_job_id: str | None = None,
    generation_profile_revision: int | None = None,
    dependency_kind: str | None = None,
) -> dict:
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
            "id": new_record_id("alert"),
            "date": datetime.date.today().isoformat(),
            "priority": inputs["priority"],
            "message": _screening_safe_alert_text(inputs["message"]),
            "action_required": _screening_safe_alert_text(inputs.get("action_required", "")),
            "resolved": False,
            "added_at": now_stamp(),
            "source_document_id": source_document_id,
            "source_job_id": source_job_id or "direct-tool-call",
            "generation_profile_revision": (
                generation_profile_revision
                if generation_profile_revision is not None
                else profile.get("profile_revision")
            ),
            "source_dependency_active": True,
            "dependency_kind": dependency_kind
            or ("source" if source_document_id else "profile_snapshot"),
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
