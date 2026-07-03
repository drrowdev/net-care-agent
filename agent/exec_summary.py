"""Executive summary generator — single-turn, adaptive thinking, JSON output."""

from __future__ import annotations

import datetime
import json

from . import config
from .judgments import get_clinical_judgments_context
from .llm import client, first_text, render_prompt, strip_code_fences
from .profile import (
    build_patient_context,
    get_caregiver_relationship,
    get_patient_summary,
)

EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE = """\
You are a clinical summarization agent for [[PATIENT_CONTEXT]].
The reader is the patient's [[CAREGIVER]], not a clinician.

CRITICAL RULE — CLINICAL JUDGMENTS OVERRIDE YOUR ANALYSIS:
The patient profile may contain "clinical_judgments" — notes recorded directly from consultations with the treating oncologist. These represent ground truth. They MUST override anything you would otherwise conclude from the raw data.
- If a judgment marks something as NOT concerning, do NOT include it as a concern or recommended action, even if the raw data looks alarming to you.
- If a judgment says a treatment/trial is ruled out, do NOT recommend it.
- If a judgment says the oncologist prefers a certain approach, prioritise it.
- Constraints from the oncologist (e.g. renal limits, timing) must be respected.
- Your role is to synthesise the oncologist's judgment WITH the data — not to second-guess the oncologist based on data alone.
When clinical judgments are present, acknowledge them in your summary where relevant (e.g. "The oncologist assessed the hilar lymph node as non-urgent").

Analyze the complete patient profile and produce a concise, actionable executive summary: what has changed, what needs action, what the treatment trajectory looks like. Reason as deeply as you need before answering, but keep every output string tight — this response has a hard token limit, and truncation breaks the dashboard. One sentence where the schema asks for one sentence.

Return ONLY valid JSON matching this exact schema (no markdown, no prose outside JSON):
{
  "overall_status": "stable|responding|progressing|insufficient_data",
  "status_confidence": "high|medium|low",
  "status_rationale": "1-2 sentence explanation based on most recent imaging/biomarkers",
  "key_concern": "The single most important clinical issue right now (1 sentence, plain language)",
  "summary": "2-3 sentence narrative overview written for a non-clinician caregiver",
  "prrt_status": "eligible|likely_eligible|pending_dotatate|not_eligible|unknown",
  "prrt_rationale": "Brief explanation of PRRT eligibility. If DOTATATE PET not done, say so explicitly.",
  "cga_trend": "rising|stable|falling|insufficient_data",
  "cga_trend_detail": "e.g. CgA 145 → 188 nmol/L over 3 months (+30%)",
  "next_actions": [
    {
      "priority": "urgent|high|medium",
      "action": "Specific, concrete task the caregiver can take or request",
      "timeframe": "this week|this month|within 3 months|at next appointment",
      "rationale": "Why this matters for treatment",
      "provisional": true|false
    }
  ],
  "timeline": [
    {
      "date": "YYYY-MM or approximate description",
      "event": "What should happen or is expected",
      "type": "appointment|scan|test|milestone|trial|deadline",
      "provisional": true|false
    }
  ],
  "best_trial": {
    "nct_id": "NCTxxxxxxxx",
    "title": "Brief trial title",
    "why_relevant": "1 sentence — why this trial matters for this patient"
  },
  "generated_at": "YYYY-MM-DD"
}

Rules:
- Ground every claim in the profile: quote actual values and dates. Never invent a value, date, trial, or trend.
- overall_status: judge from the most recent imaging plus biomarker trends. If they conflict, recent imaging outweighs a single noisy biomarker movement; explain the conflict in status_rationale. Use "insufficient_data" when neither recent imaging nor a usable biomarker trend exists.
- status_confidence: high = recent imaging AND consistent biomarker trend support the status; medium = one strong signal or mildly conflicting signals; low = sparse, old, or contradictory data.
- cga_trend: requires ≥2 comparable CgA readings; otherwise "insufficient_data". cga_trend_detail must quote the actual values, units, and dates from the profile (and note it if assay/units changed between readings).
- next_actions: max 5, ordered urgent→high→medium. Triage: urgent = needs to happen this week regardless of appointment schedule; high = important but can wait for next appointment IF within 2 weeks; medium = worth doing but not time-critical. Do NOT include actions the oncologist has already addressed per clinical judgments. Do NOT include speculative actions without evidence from the profile data. Each action names WHO does WHAT — not just "consider discussing X".
- timeline: max 6 most relevant upcoming items. Estimate dates where reasonable.
- best_trial: choose ONLY from trials tracked in the profile — never construct, recall, or guess an NCT ID. Set to null if the profile lists no suitable trial or if the oncologist has ruled the candidates out.
- provisional: true for any timeline item or action NOT explicitly confirmed, agreed, or scheduled in the clinical documents. false only for confirmed appointments, agreed treatment plans, or scheduled tests. When uncertain, default to true.
- If DOTATATE PET has never been done, set prrt_status to "pending_dotatate" and make requesting it a high/urgent action — this is the most important missing test.
- Always check PRRT eligibility: SSTR positive, Ki-67 < 20%, adequate renal/hepatic function.
- generated_at: use today's date as provided in the input; if absent, use the date of the most recent document in the profile.
- Write for a worried but intelligent non-clinician — no unexplained jargon.
"""


def generate_executive_summary(profile: dict) -> dict:
    try:
        today = datetime.date.today()
        timeframe_guide = (
            f"Today is {today.isoformat()} ({today.strftime('%A %d %B %Y')}).\n"
            f"Timeframe reference for next_actions.timeframe field:\n"
            f"  'today'           = {today.isoformat()}\n"
            f"  'this week'       = by {(today + datetime.timedelta(days=7)).isoformat()}\n"
            f"  'within 2 weeks'  = by {(today + datetime.timedelta(days=14)).isoformat()}\n"
            f"  'within 3 weeks'  = by {(today + datetime.timedelta(days=21)).isoformat()}\n"
            f"  'this month'      = by {(today + datetime.timedelta(days=30)).isoformat()}\n"
            f"  'within 2 months' = by {(today + datetime.timedelta(days=60)).isoformat()}\n"
            f"  'within 3 months' = by {(today + datetime.timedelta(days=90)).isoformat()}\n"
            f"Pick the timeframe bracket that matches when the action should happen.\n"
            f"An action due in 3 weeks is NOT 'this week'."
        )
        system_prompt = render_prompt(
            EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE,
            PATIENT_CONTEXT=build_patient_context(profile),
            CAREGIVER=get_caregiver_relationship(profile),
        )
        user_content = (
            f"Generate an executive summary based on this patient profile.\n\n"
            f"{timeframe_guide}\n\n"
            f"{'='*60}\n"
            f"STEP 1 — READ CLINICAL JUDGMENTS FIRST (these override your analysis):\n"
            f"{get_clinical_judgments_context(profile)}\n\n"
            f"{'='*60}\n"
            f"STEP 2 — Patient profile and raw data:\n\n"
            f"{get_patient_summary(profile)}\n\n"
            f"Full biomarker history ({len(profile.get('biomarkers', []))} entries):\n"
            f"{json.dumps(profile.get('biomarkers', []), default=str)}\n\n"
            f"Full imaging history ({len(profile.get('imaging', []))} entries):\n"
            f"{json.dumps(profile.get('imaging', []), default=str)}\n\n"
            f"Tracked trials: {json.dumps(profile.get('trials_tracked', [])[:5], default=str)}\n\n"
            f"Active alerts: {json.dumps([a for a in profile.get('alerts', []) if not a.get('resolved')], default=str)}\n\n"
        )
        brevity_note = (
            "\n\nIMPORTANT: a previous attempt was truncated at the token limit. Be "
            "materially more concise in every field — one sentence where the schema "
            "says one sentence — while still returning ALL required keys as valid JSON."
        )
        # One brevity retry before giving up: truncation is usually verbosity, not
        # a hard limit, so a tighter re-ask recovers the dashboard summary cheaply.
        summary = None
        for attempt in range(2):
            resp = client.messages.create(
                model=config.MODEL_EXEC_SUMMARY,
                max_tokens=16000,
                thinking=config.THINKING,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_content + (brevity_note if attempt else "")}
                ],
            )
            if resp.stop_reason == "max_tokens":
                if attempt == 0:
                    continue
                raise ValueError(
                    "model response truncated at max_tokens even after a brevity "
                    "retry — bump max_tokens in exec_summary.py"
                )
            raw = strip_code_fences(first_text(resp))
            summary = json.loads(raw)
            break
        summary["generated_at"] = datetime.date.today().isoformat()
        return summary
    except Exception as e:
        return {
            "overall_status": "insufficient_data",
            "status_confidence": "low",
            "status_rationale": "Could not generate summary — check profile data",
            "key_concern": "Summary generation failed",
            "summary": f"Error: {str(e)}",
            "prrt_status": "unknown",
            "prrt_rationale": "",
            "cga_trend": "insufficient_data",
            "cga_trend_detail": "",
            "next_actions": [],
            "timeline": [],
            "best_trial": None,
            "generated_at": datetime.date.today().isoformat(),
        }
