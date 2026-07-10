"""Intake agent: classify document, extract structured medical data, dedupe treatments."""

from __future__ import annotations

import copy
import datetime
import json
import re

from . import config
from . import profile as profile_mod
from .llm import client, first_text, render_prompt, strip_code_fences
from .profile import build_patient_context
from .provenance import (
    anchor_source_quote,
    attach_evidence,
    preserve_source_document,
    remove_source_document,
)
from .schema import now_stamp

INTAKE_SYSTEM_TEMPLATE = """\
You are a medical data extraction agent. The record is for [[PATIENT_CONTEXT]].

You will receive ONE clinical document as free text (possibly noisy OCR/PDF-extracted output). Extract all structured medical information. Reason through the document as much as you need internally, but your final output must be exactly ONE valid JSON object — no markdown fences, no prose before or after.

SCHEMA (omit keys that have no data; never add keys):
{
  "document_type": "lab_result|imaging_report|doctor_note|research_paper|appointment_summary|pathology_report|other",
  "date": "YYYY-MM-DD or null",
  "summary": "1-2 sentence summary of the key clinical message",
  "biomarkers": [
    {"marker": "name", "value": number_or_null, "unit": "string",
     "reference_range": "string_or_null", "flag": "high|low|normal",
     "source_quote": "verbatim source span proving this entire row"}
  ],
  "imaging_findings": {
    "modality": "CT|MRI|PET-CT|ultrasound|other",
    "findings": "detailed findings",
    "impression": "radiologist conclusion",
    "new_lesions": true|false|null,
    "source_quote": "verbatim source span proving these findings"
  },
  "treatment_changes": ["list any treatment starts, stops, or dose changes"],
  "ki67_update": number_or_null,
  "sstr_status_update": "positive|negative|null",
  "sstr_score_update": number_or_null,
  "symptoms_reported": [
    {"symptom": "name", "severity": 1-5_or_null, "note": "string_or_null",
     "related_treatment": "treatment_name_or_null",
     "source_quote": "verbatim source span proving this symptom"}
  ],
  "appointments": [
    {"date": "YYYY-MM-DD", "description": "what the event is", "type": "call|appointment|scan|review|infusion|other",
     "source_quote": "verbatim source span proving this appointment"}
  ],
  "key_findings": ["3-5 most clinically important findings"],
  "evidence": [
    {"field": "key_findings|treatment_changes|ki67_update|sstr_status_update|sstr_score_update",
     "item_index": 0_or_null, "source_quote": "verbatim source span proving the value"}
  ],
  "suggested_workflows": ["pubmed_search", "trial_search", "biomarker_analysis", "appointment_prep"],
  "workflow_rationale": "brief explanation of why these workflows are recommended"
}

EXTRACTION RULES
- Ground every field in the document text. Never infer, estimate, or fabricate a value, date, unit, or flag. If OCR damage makes a value unreadable, omit that entry rather than guess.
- EVIDENCE CONTRACT: every biomarker, imaging_findings object, symptom, and appointment MUST include source_quote copied verbatim from the input. Also include one evidence[] row for every key_finding, treatment_change, and scalar update. Quotes are validated deterministically; unsupported quotes are discarded and the persisted fact is explicitly marked evidence_status="invalid" (or "missing" when absent). Never paraphrase inside source_quote.
- date: the CLINICAL date — specimen collection date, scan date, or visit date. Not the print, report-issued, or fax date. null if no clinical date is determinable.
- biomarkers: serum/blood/urine lab values only (e.g. CgA, NSE, 5-HIAA, liver enzymes, kidney function, CBC, hemoglobin, radiation dose metrics). Do NOT include Ki-67 or MIB-1 here — use ki67_update instead. Fix obvious OCR unit artifacts (e.g. "ug/L" for "µg/L") but never convert units.
- flag: use the document's own flag if printed; otherwise derive from the stated reference range; if neither exists, omit the flag field — do not assume "normal".
- ki67_update: a number. If Ki-67 is stated as a range (e.g. "15-20%"), use the highest stated value and mention the full range in key_findings.
- sstr_status_update / sstr_score_update: only when explicitly reported (SSTR imaging such as DOTATATE/octreotide scans, or pathology IHC). The score is the Krenning score (0-4) or the stated IHC score — record it exactly as given.
- treatment_changes: explicit starts, stops, and dose/schedule changes only.
- symptoms_reported: ONLY explicitly-described patient symptoms or side effects (e.g. "patient reports nausea grade 2 since starting lanreotide"). Do NOT invent symptoms from biomarker values, imaging findings, or the clinician's own conclusions — those belong in key_findings. severity is 1=mild through 5=severe; null if the text doesn't specify.
- appointments: any scheduled or planned FUTURE event with a concrete date — follow-up calls, clinic visits, scans, infusions, MDT/tumour-board reviews (e.g. "follow-up call 14.7.2026", "next CT on 3 Aug", "review appointment in two weeks"). Convert the date to YYYY-MM-DD; if the text gives only a relative date, resolve it against the document's clinical date. Omit the entry if no concrete date can be determined. description is a short noun phrase; type is one of call/appointment/scan/review/infusion/other. Do NOT include past/completed events here.
- key_findings: the 3-5 most clinically important findings, each traceable to a specific statement in the document.
- suggested_workflows: choose only from the four listed values, and only when THIS document creates a concrete reason: new/changed abnormal lab → "biomarker_analysis"; new lesion, progression, grade change, or treatment question → "pubmed_search"; a change relevant to trial eligibility (Ki-67, SSTR, progression, organ function) → "trial_search"; an upcoming decision or consultation implied → "appointment_prep". workflow_rationale: one brief sentence tied to the specific finding.
- document_type: pick the best fit; use "other" when genuinely ambiguous.

Output: ONLY the JSON object."""


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


def _persist_symptoms(
    profile: dict,
    reported: list,
    doc_date: str,
    text: str = "",
    source_document_id: str | None = None,
) -> None:
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
        item = {
            "id": f"sym_ai_{doc_date.replace('-', '')}_{len(existing)}",
            "date": doc_date,
            "added_at": now_stamp(),
            "symptom": name,
            "severity": s.get("severity"),
            "note": (s.get("note") or "").strip() or None,
            "related_treatment": (s.get("related_treatment") or "").strip() or None,
            "source": "ai",
            "source_quote": s.get("source_quote"),
        }
        if source_document_id:
            item = attach_evidence(item, text, source_document_id)
        else:
            item.pop("source_quote", None)
        existing.append(item)


def _persist_appointments(
    profile: dict,
    appointments: list,
    doc_date: str,
    text: str = "",
    source_document_id: str | None = None,
) -> None:
    """Append AI-extracted appointments to profile["appointments"], deduping by
    (date, description) so re-feeding a document doesn't double-log. Only entries
    with a concrete date are kept; the dashboard timeline merge surfaces upcoming
    ones deterministically."""
    profile.setdefault("appointments", [])
    existing = profile["appointments"]
    for a in appointments:
        if not isinstance(a, dict):
            continue
        date = (a.get("date") or "").strip()[:10]
        desc = (a.get("description") or a.get("notes") or "").strip()
        if not date or not desc:
            continue
        desc_lower = desc.lower()
        dup = any(
            (e.get("date") or "")[:10] == date
            and (e.get("description") or e.get("notes") or "").strip().lower() == desc_lower
            for e in existing
        )
        if dup:
            continue
        item = {
            "date": date,
            "description": desc,
            "type": (a.get("type") or "").strip().lower() or "appointment",
            "source": "ai",
            "recorded_from_date": doc_date or None,
            "added_at": now_stamp(),
            "source_quote": a.get("source_quote"),
        }
        if source_document_id:
            item = attach_evidence(item, text, source_document_id)
        else:
            item.pop("source_quote", None)
        existing.append(item)


def _extract_json(text: str, system_prompt: str) -> tuple[dict, bool]:
    """Call the intake model and parse strict JSON, with one repair retry.

    Returns ``(extracted, failed)``. On the first JSON-decode failure it feeds
    the invalid output and the decoder error back to the model and asks for
    corrected JSON only. If that still fails, ``failed`` is True and a minimal
    unstructured record is returned so the document is at least logged — but the
    caller raises a loud, caregiver-visible alert (a silently-unstructured
    document is data loss dressed up as a soft fallback).
    """
    resp = client.messages.create(
        model=config.MODEL_INTAKE,
        max_tokens=12000,
        thinking=config.THINKING,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Extract structured data:\n\n{text}"}],
    )
    raw = strip_code_fences(first_text(resp))
    try:
        return json.loads(raw), False
    except json.JSONDecodeError as err:
        print("  ⚠  Intake JSON parse failed — attempting one repair retry")
        repair = client.messages.create(
            model=config.MODEL_INTAKE,
            max_tokens=12000,
            thinking=config.THINKING,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Extract structured data:\n\n{text}"},
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"That was not valid JSON (json.loads error: {err}). "
                        "Return ONLY the corrected JSON object — no prose, no fences."
                    ),
                },
            ],
        )
        raw2 = strip_code_fences(first_text(repair))
        try:
            return json.loads(raw2), False
        except json.JSONDecodeError:
            print("  ⚠  Repair retry also failed — storing unstructured + raising alert")
            return (
                {
                    "document_type": "other",
                    "summary": text[:200],
                    "key_findings": [],
                    "suggested_workflows": ["pubmed_search"],
                },
                True,
            )


def _verify_intake(text: str, extracted: dict) -> list:
    """Second, monotonically-safe extraction pass (P1, gated by INTAKE_VERIFY).

    Asks the model to surface biomarkers / treatment_changes the first pass may
    have missed, each REQUIRING a verbatim ``source_quote``. Only candidates whose
    quote is actually a substring of the document are merged — a hallucinated
    "miss" cannot enter the profile. Returns the list of additions (also appended
    into ``extracted`` in place). Never raises.
    """
    system = (
        "You are a verification agent. Given a clinical document and a prior "
        "extraction, find biomarker readings or treatment changes the prior "
        "extraction MISSED. Return ONLY a JSON array; each item: "
        '{"field": "biomarkers"|"treatment_changes", "item": <same shape as the '
        'intake schema for that field>, "source_quote": "<verbatim text copied '
        'from the document proving this item exists>"}. If nothing was missed, '
        "return []. Never invent — every source_quote must be copied exactly."
    )
    try:
        resp = client.messages.create(
            model=config.MODEL_INTAKE,
            max_tokens=6000,
            thinking=config.THINKING,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"DOCUMENT:\n{text}\n\nPRIOR EXTRACTION:\n"
                        f"{json.dumps(extracted, default=str)}"
                    ),
                }
            ],
        )
        candidates = json.loads(strip_code_fences(first_text(resp)))
    except Exception:  # noqa: BLE001 — verification is best-effort, never fatal
        return []
    if not isinstance(candidates, list):
        return []

    added: list = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        quote = c.get("source_quote")
        anchored = anchor_source_quote(text, quote)
        if anchored["evidence_status"] != "verified":
            continue  # unanchored / hallucinated — discard programmatically
        field = c.get("field")
        item = c.get("item")
        if field == "biomarkers" and isinstance(item, dict) and item.get("marker"):
            item["source_quote"] = anchored["source_quote"]
            extracted.setdefault("biomarkers", []).append(item)
            added.append({"field": field, "item": item})
        elif field == "treatment_changes" and isinstance(item, str) and item.strip():
            extracted.setdefault("treatment_changes", []).append(item)
            added.append({"field": field, "item": item})
    return added


def _run_intake_impl(
    text: str,
    profile: dict,
    *,
    raw_bytes: bytes | None = None,
    filename: str | None = None,
    media_type: str = "text/plain",
) -> tuple[dict, dict]:
    """Classify and extract structured data from free-form text."""
    print("\n⚙  Running intake agent ...")

    source_document = preserve_source_document(
        text,
        raw_bytes=raw_bytes,
        filename=filename,
        media_type=media_type,
    )
    source_document_id = source_document["id"]
    profile.setdefault("source_documents", []).append(source_document)
    system_prompt = render_prompt(
        INTAKE_SYSTEM_TEMPLATE,
        PATIENT_CONTEXT=build_patient_context(profile),
    )
    extracted, extraction_failed = _extract_json(text, system_prompt)
    extracted["source_document_id"] = source_document_id
    extracted["ingested_at"] = source_document["ingested_at"]

    # P1: optional quote-anchored verification pass (off unless INTAKE_VERIFY set).
    if config.INTAKE_VERIFY and not extraction_failed:
        added = _verify_intake(text, extracted)
        if added:
            extracted["verification_added"] = added
            print(f"  ✓  Verification pass added {len(added)} source-anchored item(s)")

    today = datetime.date.today().isoformat()
    doc_date = extracted.get("date") or today

    if extraction_failed:
        # Loud, recoverable failure surfaced through the existing alerts UI —
        # the caregiver must know a fed document is structurally invisible to
        # analysis rather than silently believing it was ingested.
        profile.setdefault("alerts", []).append(
            {
                "priority": "urgent",
                "message": (
                    "A fed document could NOT be structurally extracted — its "
                    "contents are invisible to biomarker, trend, and summary "
                    "analysis. Only a raw copy was stored."
                ),
                "action_required": (
                    "Re-feed the document (ideally as cleaner text), or review it "
                    "manually with the oncologist. Then resolve this alert."
                ),
                "resolved": False,
                "date": doc_date,
                "added_at": now_stamp(),
                "source": "intake_extraction_failure",
                "source_document_id": source_document_id,
            }
        )
        extracted["extraction_failed"] = True

    evidence_candidates: dict[tuple[str, int | None], dict] = {}
    for candidate in extracted.get("evidence") or []:
        if not isinstance(candidate, dict):
            continue
        field = candidate.get("field")
        index = candidate.get("item_index")
        if not isinstance(index, int):
            index = None
        evidence_candidates[(field, index)] = candidate

    expected_evidence: list[tuple[str, int | None]] = []
    expected_evidence.extend(
        ("key_findings", index) for index, _ in enumerate(extracted.get("key_findings") or [])
    )
    expected_evidence.extend(
        ("treatment_changes", index)
        for index, _ in enumerate(extracted.get("treatment_changes") or [])
    )
    expected_evidence.extend(
        (field, None)
        for field in ("ki67_update", "sstr_status_update", "sstr_score_update")
        if extracted.get(field) is not None
    )
    document_evidence = []
    for field, index in expected_evidence:
        candidate = evidence_candidates.get((field, index))
        if index is None:
            candidate = candidate or evidence_candidates.get((field, None))
        anchored = anchor_source_quote(text, candidate.get("source_quote") if candidate else None)
        document_evidence.append(
            {
                "field": field,
                "item_index": index,
                **anchored,
            }
        )

    profile["documents"].append(
        {
            "date": doc_date,
            "type": extracted.get("document_type", "other"),
            "summary": extracted.get("summary", ""),
            "key_findings": extracted.get("key_findings", []),
            "raw_text": text[:3000],
            "added_at": source_document["ingested_at"],
            "source_document_id": source_document_id,
            "evidence": document_evidence,
        }
    )

    KI67_MARKERS = {"ki-67", "ki67", "mib-1", "mib1", "ki 67", "mib 1"}

    existing_triples = {
        (b.get("marker", "").lower().strip(), b.get("date", ""), b.get("value"))
        for b in profile["biomarkers"]
    }
    for bm in extracted.get("biomarkers", []):
        marker_name = bm.get("marker", "").lower().strip()
        if any(k in marker_name for k in KI67_MARKERS):
            continue
        bm["date"] = doc_date
        # Skip exact (marker, date, value) duplicates so re-feeding the same
        # document does not double-log readings (which would also trip the
        # same-date trend guard downstream).
        triple = (marker_name, doc_date, bm.get("value"))
        if triple in existing_triples:
            continue
        existing_triples.add(triple)
        bm["added_at"] = now_stamp()
        profile["biomarkers"].append(attach_evidence(bm, text, source_document_id))

    if extracted.get("imaging_findings"):
        img = {**extracted["imaging_findings"], "date": doc_date, "added_at": now_stamp()}
        profile["imaging"].append(attach_evidence(img, text, source_document_id))

    if extracted.get("ki67_update") is not None:
        profile["patient"]["ki67_percent"] = extracted["ki67_update"]

    if extracted.get("sstr_status_update"):
        profile["patient"]["sstr_status"] = extracted["sstr_status_update"]

    if extracted.get("sstr_score_update") is not None:
        profile["patient"]["sstr_score"] = extracted["sstr_score_update"]

    _persist_symptoms(
        profile,
        extracted.get("symptoms_reported") or [],
        doc_date,
        text,
        source_document_id,
    )
    _persist_appointments(
        profile,
        extracted.get("appointments") or [],
        doc_date,
        text,
        source_document_id,
    )

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

    print(f"  ✓  Type    : {extracted.get('document_type', '?')}")
    print(f"     Date    : {doc_date}")
    print(f"     Summary : {extracted.get('summary', '')[:100]}")
    if extracted.get("key_findings"):
        print("     Findings:")
        for f in extracted["key_findings"]:
            print(f"       • {f}")
    if extracted.get("workflow_rationale"):
        print(f"     Workflows: {extracted.get('workflow_rationale', '')}")

    return profile, extracted


def run_intake(
    text: str,
    profile: dict,
    *,
    raw_bytes: bytes | None = None,
    filename: str | None = None,
    media_type: str = "text/plain",
) -> tuple[dict, dict]:
    """Run intake atomically with respect to newly-created evidence artifacts."""
    before = copy.deepcopy(profile)
    existing_ids = {
        item.get("id") for item in profile.get("source_documents", []) if isinstance(item, dict)
    }
    try:
        return _run_intake_impl(
            text,
            profile,
            raw_bytes=raw_bytes,
            filename=filename,
            media_type=media_type,
        )
    except BaseException:
        for source in profile.get("source_documents", []):
            if isinstance(source, dict) and source.get("id") not in existing_ids:
                remove_source_document(source)
        profile.clear()
        profile.update(before)
        raise


# Keep get_patient_summary discoverable from this module too (some legacy callers).
get_patient_summary = profile_mod.get_patient_summary
