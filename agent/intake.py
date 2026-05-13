"""Intake agent: classify document, extract structured medical data, dedupe treatments."""

from __future__ import annotations

import datetime
import json
import re

from . import config
from . import profile as profile_mod
from .llm import client, strip_code_fences
from .profile import build_patient_context

INTAKE_SYSTEM_TEMPLATE = """\
You are a medical data extraction agent. The record is for {patient_context}.

Extract all structured medical information from the provided text.

Return ONLY a valid JSON object with this schema (omit keys that have no data):
{{
  "document_type": "lab_result|imaging_report|doctor_note|research_paper|appointment_summary|pathology_report|other",
  "date": "YYYY-MM-DD or null",
  "summary": "1-2 sentence summary of the key clinical message",
  "biomarkers": [
    {{"marker": "name", "value": number_or_null, "unit": "string",
     "reference_range": "string_or_null", "flag": "high|low|normal"}}
  ],

Note: Do NOT include Ki-67 or MIB-1 in biomarkers — use ki67_update instead.
Biomarkers should be serum/blood/urine lab values only (e.g. CgA, NSE, 5-HIAA,
liver enzymes, kidney function, CBC, hemoglobin, radiation dose metrics).
  "imaging_findings": {{
    "modality": "CT|MRI|PET-CT|ultrasound|other",
    "findings": "detailed findings",
    "impression": "radiologist conclusion",
    "new_lesions": true|false|null
  }},
  "treatment_changes": ["list any treatment starts, stops, or dose changes"],
  "ki67_update": number_or_null,
  "sstr_status_update": "positive|negative|null",
  "sstr_score_update": number_or_null,
  "symptoms_reported": [
    {{"symptom": "name", "severity": 1-5_or_null, "note": "string_or_null",
     "related_treatment": "treatment_name_or_null"}}
  ],
  "key_findings": ["3-5 most clinically important findings"],
  "suggested_workflows": ["pubmed_search", "trial_search", "biomarker_analysis", "appointment_prep"],
  "workflow_rationale": "brief explanation of why these workflows are recommended"
}}

Notes on symptoms_reported: extract ONLY explicitly-described patient symptoms
or side effects (e.g. "patient reports nausea grade 2 since starting lanreotide").
Do NOT invent symptoms from biomarker values, imaging findings, or the
clinician's own conclusions — those belong in key_findings. severity is 1=mild
through 5=severe; leave null if the source text doesn't specify.

No markdown, no prose outside the JSON object."""


# Treatment-name synonyms used by the fuzzy similarity check below.
_TREATMENT_SYNONYMS: dict[str, str] = {
    "somatuline": "lanreotide",
    "lanreotide": "lanreotide",
    "sst analogue": "lanreotide",
    "somatostatin analogue": "lanreotide",
    "octreotide": "lanreotide",
    "lu-177": "prrt",
    "lutetium": "prrt",
    "177lu": "prrt",
    "dotatate": "prrt",
    "lutathera": "prrt",
    "lu177": "prrt",
    "177lu-octreotate": "prrt",
    "lu-177-dotatate": "prrt",
}


def _treatment_similarity(a: str, b: str) -> float:
    """Word-overlap similarity (Jaccard) between two treatment strings, after synonym normalization."""

    def normalize(s: str) -> set[str]:
        for k, v in _TREATMENT_SYNONYMS.items():
            s = s.replace(k, v)
        # Split on whitespace AND hyphens so "177lu-octreotate" → {"prrt"}
        # rather than the unsplit hyphenated token.
        return {tok for tok in re.split(r"[\s\-]+", s) if tok}

    words_a = normalize(a)
    words_b = normalize(b)
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _persist_symptoms(profile: dict, reported: list, doc_date: str) -> None:
    """Append AI-extracted symptoms to profile["symptoms"], deduping against
    same-day same-name entries so re-feeding a document doesn't double-log."""
    profile.setdefault("symptoms", [])
    existing = profile["symptoms"]
    for s in reported:
        name = (s.get("symptom") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        dup = any(
            (e.get("symptom") or "").lower() == name_lower and (e.get("date") or "") == doc_date
            for e in existing
        )
        if dup:
            continue
        existing.append(
            {
                "id": f"sym_ai_{doc_date.replace('-', '')}_{len(existing)}",
                "date": doc_date,
                "symptom": name,
                "severity": s.get("severity"),
                "note": (s.get("note") or "").strip() or None,
                "related_treatment": (s.get("related_treatment") or "").strip() or None,
                "source": "ai",
            }
        )


def run_intake(text: str, profile: dict) -> tuple[dict, dict]:
    """Classify and extract structured data from free-form text."""
    print("\n⚙  Running intake agent ...")

    system_prompt = INTAKE_SYSTEM_TEMPLATE.format(
        patient_context=build_patient_context(profile),
    )
    resp = client.messages.create(
        model=config.MODEL_INTAKE,
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Extract structured data:\n\n{text}"}],
    )

    raw = strip_code_fences(resp.content[0].text)
    try:
        extracted: dict = json.loads(raw)
    except json.JSONDecodeError:
        print("  ⚠  Intake JSON parse failed — storing as unstructured document")
        extracted = {
            "document_type": "other",
            "summary": text[:200],
            "key_findings": [],
            "suggested_workflows": ["pubmed_search"],
        }

    today = datetime.date.today().isoformat()
    doc_date = extracted.get("date") or today

    profile["documents"].append(
        {
            "date": doc_date,
            "type": extracted.get("document_type", "other"),
            "summary": extracted.get("summary", ""),
            "key_findings": extracted.get("key_findings", []),
            "raw_text": text[:3000],
        }
    )

    KI67_MARKERS = {"ki-67", "ki67", "mib-1", "mib1", "ki 67", "mib 1"}

    for bm in extracted.get("biomarkers", []):
        marker_name = bm.get("marker", "").lower().strip()
        if any(k in marker_name for k in KI67_MARKERS):
            continue
        bm["date"] = doc_date
        profile["biomarkers"].append(bm)

    if extracted.get("imaging_findings"):
        img = {**extracted["imaging_findings"], "date": doc_date}
        profile["imaging"].append(img)

    if extracted.get("ki67_update") is not None:
        profile["patient"]["ki67_percent"] = extracted["ki67_update"]

    if extracted.get("sstr_status_update"):
        profile["patient"]["sstr_status"] = extracted["sstr_status_update"]

    if extracted.get("sstr_score_update") is not None:
        profile["patient"]["sstr_score"] = extracted["sstr_score_update"]

    _persist_symptoms(profile, extracted.get("symptoms_reported") or [], doc_date)

    for tx in extracted.get("treatment_changes", []):
        tx_lower = tx.lower().strip()
        existing = profile["patient"]["current_treatments"]
        is_duplicate = any(
            tx_lower in e.lower()
            or e.lower() in tx_lower
            or _treatment_similarity(tx_lower, e.lower()) > 0.7
            for e in existing
        )
        if not is_duplicate:
            existing.append(tx)

    print(f"  ✓  Type    : {extracted.get('document_type','?')}")
    print(f"     Date    : {doc_date}")
    print(f"     Summary : {extracted.get('summary','')[:100]}")
    if extracted.get("key_findings"):
        print("     Findings:")
        for f in extracted["key_findings"]:
            print(f"       • {f}")
    if extracted.get("workflow_rationale"):
        print(f"     Workflows: {extracted.get('workflow_rationale','')}")

    return profile, extracted


# Keep get_patient_summary discoverable from this module too (some legacy callers).
get_patient_summary = profile_mod.get_patient_summary
