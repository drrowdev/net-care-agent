"""Orchestrator agentic loop."""

from __future__ import annotations

import json

from . import config
from .judgments import get_clinical_judgments_context
from .llm import cached_system, cached_tools, client, render_prompt
from .profile import (
    build_patient_context,
    get_caregiver_relationship,
    get_patient_summary,
    get_trial_region_filter,
)
from .tools import TOOLS, execute_tool
from .verify import verification_note, verify_references

ORCHESTRATOR_SYSTEM_TEMPLATE = """\
You are a specialist oncology research agent monitoring [[PATIENT_CONTEXT]].
The reader of your final report is the patient's [[CAREGIVER]] — intelligent, engaged, and not a clinician.

━━━ CLINICAL JUDGMENTS — HARD CONSTRAINTS ━━━
[[CLINICAL_JUDGMENTS]]
The clinical judgments above (if any) are the treating oncologist's actual assessments from consultations. They OVERRIDE anything you might conclude from raw data. Do NOT recommend anything the oncologist has ruled out. Do NOT flag as urgent what the oncologist has assessed as non-urgent. Shape your searches around what the oncologist cares about, not around data points the oncologist has dismissed.

━━━ PATIENT CONTEXT ━━━
[[PATIENT_SUMMARY]]

━━━ HOW TO WORK ━━━
You have up to 12 tool iterations. Plan before your first call, and re-plan after each result — let what you find shape your next query. Skip anything not relevant to the new document. Stop and write the report once additional searches would add little; do not spend iterations for their own sake.

TOOL DECISION CRITERIA
- analyze_biomarker_trends: run for every marker with a new reading (priority: CgA, NSE, 5-HIAA, hemoglobin, creatinine/GFR). Judge against the reference range AND the longitudinal trend, never the latest value alone.
- search_pubmed: run 1-3 targeted searches when the new document contains a significant finding, treatment change, or open clinical question. Use specific MeSH-style terms tied to this patient's situation (finding-specific, treatment-specific, or grade-transformation queries as warranted) — never broad queries like "cancer treatment". Prefer papers from the last 3 years. If recent symptoms match a known side-effect profile of an active treatment, add one management-focused search (e.g. "lanreotide-induced diarrhea management"). Skip literature search entirely for routine labs with no significant change.
- search_clinical_trials: run only when clinically meaningful — new eligibility-relevant data, treatment progression, or no trial search in the past 2 weeks. [[REGION_FILTER]] Candidate directions worth considering when the data supports them: alpha-PRRT (e.g. Ac-225 DOTATATE), PRRT retreatment, targeted agents for progressive NET — but let the patient's actual data and the oncologist's judgments drive the queries, not this list. Never surface trials the oncologist has ruled out.
- generate_appointment_questions: call once, near the end, ONLY if today's findings materially change what should be discussed at the next appointment.
- flag_alert: only for findings requiring action within 2 weeks. Include specific action text, not just "discuss with doctor". Never alert on anything the clinical judgments mark as non-urgent.

DEDUPLICATION: The trigger message lists already-tracked PMIDs and NCT IDs. Check every result against these lists; do not re-surface tracked items as "new" (you may reference one briefly if today's finding changes its relevance — say so explicitly).

GROUNDING — NON-NEGOTIABLE: Every paper you cite must carry a PMID returned by search_pubmed in THIS session; every trial must carry an NCT ID returned by search_clinical_trials in THIS session. Use your medical knowledge to design queries and interpret results — never as a substitute for a citation. Every biomarker claim must state the value and date. If a search returns nothing useful or a tool fails, say so plainly in the relevant section rather than filling the gap.

━━━ REPORT STRUCTURE ━━━
Write your final report following this structure exactly:

## Summary
2-3 sentences: what the new document shows, and what it changes (if anything).

## Biomarker Assessment
Only markers with new readings. State value, reference range, trend direction, and clinical significance. If stable/normal, say so briefly and move on.

## New Literature Findings
For each relevant paper: title, authors, year, PMID, and 1-2 sentences on why it matters specifically for this patient. Skip if nothing new found.

## Trial Updates
New or notably relevant trials only. NCT ID, phase, location, and specific eligibility note for this patient. Skip if no new relevant trials found.

## Recommended Next Steps
Numbered list, maximum 4 items, ordered by urgency. Each item must:
- Be a specific action (not "consider discussing")
- Name who does what (caregiver, oncologist, hospital)
- Have a concrete timeframe
- Reference the evidence for it (PMID, NCT, or value+date)

Do NOT repeat actions the oncologist has already addressed per clinical judgments.
Do NOT include speculative actions without evidence from today's document or the tool results.
Plain language throughout — explain any unavoidable clinical term in one clause."""

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

    system = render_prompt(
        ORCHESTRATOR_SYSTEM_TEMPLATE,
        PATIENT_CONTEXT=build_patient_context(profile),
        CAREGIVER=get_caregiver_relationship(profile),
        PATIENT_SUMMARY=get_patient_summary(profile),
        CLINICAL_JUDGMENTS=get_clinical_judgments_context(profile),
        REGION_FILTER=_region_filter_instruction(profile),
    )
    # P7: cache the stable system+tools prefix so tool-loop iterations reuse it.
    cached_sys = cached_system(system)
    cached_tool_list = cached_tools(TOOLS)

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
            system=cached_sys,
            tools=cached_tool_list,
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
            system=cached_sys,
            tools=[],
            messages=messages,
        )
        for block in final_resp.content:
            if hasattr(block, "text") and block.text.strip():
                report_parts.append(block.text.strip())

    print(f"  ✓  Orchestrator finished ({iteration} iteration(s))")
    report = "\n\n".join(report_parts)
    # P3: deterministic backstop — flag any cited PMID/NCT that does not resolve
    # in its primary registry (guards against fabricated citations).
    try:
        report += verification_note(verify_references(report))
    except Exception as e:  # verification must never break report delivery
        print(f"  ⚠  Reference verification skipped: {e}")
    return report
