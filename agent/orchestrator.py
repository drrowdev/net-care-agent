"""Orchestrator agentic loop."""

from __future__ import annotations

import json

from . import config
from .judgments import get_clinical_judgments_context
from .llm import client
from .profile import (
    build_patient_context,
    get_caregiver_relationship,
    get_patient_summary,
    get_trial_region_filter,
)
from .tools import TOOLS, execute_tool

ORCHESTRATOR_SYSTEM_TEMPLATE = """\
You are a specialist oncology research agent monitoring {patient_context}.
The caregiver reading your output is the patient's {caregiver_relationship} —
intelligent, engaged, and not a clinician.

━━━ STEP 1: READ CLINICAL JUDGMENTS — THESE ARE HARD CONSTRAINTS ━━━
{clinical_judgments}

If clinical judgments are present above, they represent the oncologist's actual
assessment from consultations. They OVERRIDE what you might conclude from raw data.
Do NOT recommend anything the oncologist has ruled out. Do NOT flag something as
urgent if the oncologist has assessed it as non-urgent. Shape your searches around
what the oncologist cares about, not around alarming data points the oncologist
has dismissed.

━━━ STEP 2: PATIENT CONTEXT ━━━
{patient_summary}

━━━ STEP 3: RESEARCH PROTOCOL ━━━
Run searches in this order, skipping any that aren't relevant to the new document:

A) BIOMARKER ANALYSIS (always run if new labs were received)
   - Call analyze_biomarker_trends for any marker with a new reading
   - Focus on CgA, NSE, 5-HIAA, hemoglobin, renal function (creatinine, GFR)
   - Compare to reference ranges AND longitudinal trend, not just latest value

B) LITERATURE SEARCH (run 2-3 targeted searches)
   - Search 1: Specific to new finding, e.g. "neuroendocrine tumor hilar lymph node progression"
   - Search 2: Treatment-relevant, e.g. "Lu-177 DOTATATE second cycle outcomes"
   - Search 3: If grade transformation suspected: "neuroendocrine tumor grade transformation Ki-67"
   - Always use specific MeSH-style terms — never broad queries like "cancer treatment"
   - Prioritise papers from the last 3 years
   - Skip this if new document is routine labs with no significant changes

C) TRIAL SEARCH (run when clinically meaningful, not every time)
   - Only run if: new eligibility data, treatment progression, or no search in past 2 weeks
   - {region_filter_instruction}
   - Priority targets: Ac-225 DOTATATE (alpha-PRRT), PRRT retreatment protocols,
     surufatinib, everolimus for progressive NET, NET-specific immunotherapy
   - Do NOT surface trials the oncologist has already ruled out (check clinical judgments)

D) ALERTS (flag only what is genuinely actionable)
   - Only call flag_alert for findings that require action within 2 weeks
   - Include specific action text, not just "discuss with doctor"

E) SIDE-EFFECT MANAGEMENT (run only when recent symptoms are present)
   - If the patient summary shows recent symptoms that match known
     side-effect profiles of any active treatment, run one targeted
     literature search for management strategies (e.g. "lanreotide-induced
     diarrhea management"). Skip otherwise.

━━━ STEP 4: REPORT STRUCTURE ━━━
Write your final report following this structure exactly:

## Summary
2-3 sentences: what the new document shows, and what it changes (if anything).

## Biomarker Assessment
Only include markers with new readings. State value, reference range, trend direction,
and clinical significance. If stable/normal, say so briefly and move on.

## New Literature Findings
For each relevant paper: title, authors, year, PMID, and 1-2 sentences on why it
matters specifically for this patient. Skip if nothing new found.

## Trial Updates
New or notably relevant trials only. NCT ID, phase, location, and specific eligibility
note for this patient. Skip if no new relevant trials found.

## Recommended Next Steps
Numbered list, maximum 4 items, ordered by urgency. Each item must:
- Be a specific action (not "consider discussing")
- Name who does what (caregiver, oncologist, hospital)
- Have a concrete timeframe
- Reference the evidence for it

Do NOT repeat actions the oncologist has already addressed per clinical judgments.
Do NOT include speculative actions without evidence from today's document or literature."""

MAX_ITERATIONS = 12


def _region_filter_instruction(profile: dict) -> str:
    expr = get_trial_region_filter(profile)
    if expr:
        return f"Always run one region-specific search: {expr}"
    return (
        "If the patient profile lists regions of interest, run one region-specific "
        "search to surface local trials"
    )


def run_orchestrator(profile: dict, extracted: dict) -> str:
    """Agentic loop: reads profile, executes workflows via tool use, returns report."""
    print("\n⚙  Running orchestrator (agentic loop) ...")

    system = ORCHESTRATOR_SYSTEM_TEMPLATE.format(
        patient_context=build_patient_context(profile),
        caregiver_relationship=get_caregiver_relationship(profile),
        patient_summary=get_patient_summary(profile),
        clinical_judgments=get_clinical_judgments_context(profile),
        region_filter_instruction=_region_filter_instruction(profile),
    )

    existing_pmids = [p["pmid"] for p in profile.get("literature_watched", [])]
    existing_ncts = [t["nct_id"] for t in profile.get("trials_tracked", [])]

    trigger_message = (
        f"New information just added to the patient record:\n\n"
        f"Document type: {extracted.get('document_type', 'unknown')}\n"
        f"Date        : {extracted.get('date', 'unknown')}\n"
        f"Summary     : {extracted.get('summary', '')}\n"
        f"Key findings: {json.dumps(extracted.get('key_findings', []))}\n"
        f"Suggested workflows: {json.dumps(extracted.get('suggested_workflows', []))}\n"
        f"Rationale   : {extracted.get('workflow_rationale', '')}\n\n"
        f"Already tracked — do NOT re-surface these:\n"
        f"  Papers (PMIDs): {existing_pmids[-20:] if existing_pmids else 'none'}\n"
        f"  Trials (NCT IDs): {existing_ncts if existing_ncts else 'none'}\n\n"
        "Follow the research protocol in your system prompt. "
        "Focus on what is NEW and clinically significant for this specific document. "
        "Be specific — every finding should tie directly to this patient's situation."
    )

    messages = [{"role": "user", "content": trigger_message}]
    report_parts: list[str] = []
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        resp = client.messages.create(
            model=config.MODEL_ORCHESTRATOR,
            max_tokens=12000,
            thinking=config.THINKING,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        for block in resp.content:
            if hasattr(block, "text") and block.text.strip():
                report_parts.append(block.text.strip())

        if resp.stop_reason == "end_turn":
            break

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                print(f"   → {block.name}({json.dumps(block.input)[:70]}…)")
                result = execute_tool(block.name, block.input, profile)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        if not tool_results:
            break

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})

    combined = "\n\n".join(report_parts).strip()
    if len(combined) < 300:
        print("  ⚙  Requesting explicit final synthesis...")
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Based on all the research you have conducted above, write the complete "
                            "report now. Include: key literature findings with PMIDs, relevant clinical "
                            "trials with NCT IDs and eligibility notes, biomarker trend assessment, and "
                            "specific recommended actions. Be comprehensive and detailed."
                        ),
                    }
                ],
            }
        )
        final_resp = client.messages.create(
            model=config.MODEL_ORCHESTRATOR,
            max_tokens=12000,
            thinking=config.THINKING,
            system=system,
            tools=[],
            messages=messages,
        )
        for block in final_resp.content:
            if hasattr(block, "text") and block.text.strip():
                report_parts.append(block.text.strip())

    print(f"  ✓  Orchestrator finished ({iteration} iteration(s))")
    return "\n\n".join(report_parts)
