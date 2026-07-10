"""Ensemble deep-sweep — on-demand, high-effort pre-appointment research pass.

Runs the research orchestrator across several strong models (default:
Claude Fable 5 + Claude Opus 4.8) with the routine dedup/suppression rules
relaxed, so each model is free to surface non-obvious cross-connections a
routine digest would skip. A final synthesis pass merges the per-model reports
into one *unioned* report — every unique catch from either model is preserved.

Design notes
------------
- **Non-mutating.** Each model runs against a deep copy of the profile, so the
  real ``patient_profile.json`` is never modified. This is deliberate: the
  deep-sweep re-surfaces already-tracked items on purpose, so writing its
  findings back would pollute the tracked lists and contaminate future runs.
  The routine ``run_orchestrator`` remains the only path that updates state.
- **Faithful.** It reuses the production orchestrator system prompt, tool
  schemas, and tool dispatcher — only the model, the exploratory addendum, and
  the relaxed trigger differ.
- **Ensemble, not intersection.** The synthesiser is told to keep every unique,
  grounded finding and to surface disagreements for clinician confirmation,
  rather than averaging the reports down to their overlap.

Everything produced here is decision-support for the treating oncologist only.
"""

from __future__ import annotations

import copy
import json
import time

from . import config
from . import orchestrator as orch
from .judgments import get_clinical_judgments_context
from .llm import cached_system, cached_tools, client, first_text, render_prompt
from .profile import (
    build_patient_context,
    get_caregiver_relationship,
    get_patient_summary,
)
from .tools import TOOLS, execute_tool
from .verify import verification_note, verify_references

MAX_ITERATIONS = 12
MAX_TOKENS = 16000

# Approximate per-MTok USD pricing for the cost footer. Informational only and
# may drift (e.g. Sonnet 5 intro pricing ends 2026-08-31); unknown models fall
# back to a conservative estimate so a new model never crashes the run.
_PRICING = {
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_FALLBACK_RATE = (10.0, 50.0)

_EXPLORATORY_ADDENDUM = """

━━━ EXPLORATORY DEEP-REVIEW MODE (one-off, not a routine digest) ━━━
Your goal is to surface NON-OBVIOUS connections and insights across this
patient's ENTIRE record that a routine pass might miss.
- You MAY revisit an already-tracked paper or trial if it gains new relevance
  when connected to another finding — state the connection explicitly.
- Actively hunt for cross-links: biomarker trend x treatment timing x imaging x
  symptom x trial eligibility x clinical judgment. Draw the connective reasoning
  out in the report, not just conclusions.
- Prioritise depth of synthesis over brevity; it is fine to be longer than a
  routine digest. Still ground EVERY claim in a concrete source (PMID / NCT /
  biomarker value+date / imaging date / judgment).
- Do NOT suppress a finding merely because it is already tracked. Suppress only
  true noise. Respect the oncologist's clinical judgments as hard constraints.
"""

_TRIGGER = (
    "Perform a comprehensive exploratory DEEP REVIEW of this patient's entire "
    "record. Analyse biomarker trends, search current NET literature and trials, "
    "and synthesise cross-cutting connections. Surface anything clinically "
    "meaningful that links separate parts of the record — especially insights a "
    "routine monthly digest might overlook. Follow the report structure in your "
    "system prompt, then add a final section '## Cross-Cutting Insights' with the "
    "non-obvious connections you found."
)

_SYNTHESIS_SYSTEM_TEMPLATE = """\
You are a clinical research SYNTHESISER preparing a single deep-review briefing
for a treating oncologist. You are given two or more independent deep-review
reports produced by different AI models from the SAME patient record.

━━━ ACTUAL CLINICAL JUDGMENTS — HARD CONSTRAINTS ━━━
[[CLINICAL_JUDGMENTS]]
Only judgments shown above as active and not expired/review-due override the
source reports. Items under NEEDS CLINICIAN REVIEW are historical context only.

Your job is to UNION them, not average them:
- Merge findings the reports share into one clean statement (keep the specific
  grounding — PMIDs, NCT IDs, biomarker values + dates).
- PRESERVE EVERY unique, grounded catch that appears in only one report. Do not
  drop a finding just because the other model missed it — those are the highest
  value items.
- Where the reports DISAGREE, or one flags a concern the other explicitly
  dismisses, surface BOTH positions and mark the item "⚠ needs clinician
  confirmation".
- Do NOT invent new medical claims, citations, or numbers. Only merge, organise,
  and de-duplicate what the source reports contain. If a claim is unsourced in
  the originals, keep it but mark it "unverified".
- Respect the oncologist's clinical judgments as hard constraints.

Output clean Markdown with these sections:
## Summary
## Biomarker Assessment
## New Literature Findings
## Trial Updates
## Recommended Next Steps
## Cross-Cutting Insights
## Where the models diverged
Keep it decision-support only. The oncologist reviews everything before acting.
"""


def _build_system(profile: dict) -> str:
    return (
        render_prompt(
            orch.ORCHESTRATOR_SYSTEM_TEMPLATE,
            PATIENT_CONTEXT=build_patient_context(profile),
            CAREGIVER=get_caregiver_relationship(profile),
            PATIENT_SUMMARY=get_patient_summary(profile),
            CLINICAL_JUDGMENTS=get_clinical_judgments_context(profile),
            REGION_FILTER=orch._region_filter_instruction(profile),
        )
        + _EXPLORATORY_ADDENDUM
    )


def _cost(model: str, usage: dict) -> float:
    in_rate, out_rate = _PRICING.get(model, _FALLBACK_RATE)
    return usage["input"] / 1e6 * in_rate + usage["output"] / 1e6 * out_rate


def _run_single_model(model: str, base_profile: dict) -> dict:
    """Run the exploratory agentic loop for one model on a private profile copy.

    Operates on a deep copy so tool side effects never touch the caller's
    profile. Returns the report text, token usage, cost, and tool order.
    """
    profile = copy.deepcopy(base_profile)
    system = _build_system(profile)
    messages: list[dict] = [{"role": "user", "content": _TRIGGER}]
    report_parts: list[str] = []
    tool_order: list[str] = []
    usage = {"input": 0, "output": 0}
    t0 = time.time()
    iterations = 0
    error = None
    stop_reason = None
    truncated = False

    try:
        while iterations < MAX_ITERATIONS:
            iterations += 1
            resp = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                thinking=config.THINKING,
                system=cached_system(system),
                tools=cached_tools(TOOLS),
                messages=messages,
            )
            u = getattr(resp, "usage", None)
            if u is not None:
                usage["input"] += getattr(u, "input_tokens", 0) or 0
                usage["output"] += getattr(u, "output_tokens", 0) or 0

            stop_reason = getattr(resp, "stop_reason", None)
            for block in resp.content:
                if getattr(block, "type", None) == "text" and block.text.strip():
                    report_parts.append(block.text.strip())

            if stop_reason == "max_tokens":
                truncated = True
                error = f"response truncated at max_tokens={MAX_TOKENS}"
                report_parts.append(
                    f"⚠ Explicit truncation: {model} reached max_tokens={MAX_TOKENS}; "
                    "this report may be incomplete."
                )
                break
            if stop_reason == "end_turn":
                break

            tool_results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_order.append(block.name)
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
    except Exception as e:  # noqa: BLE001 — one model failing must not kill the sweep
        error = f"{type(e).__name__}: {e}"

    if iterations >= MAX_ITERATIONS and stop_reason != "end_turn" and not error:
        truncated = True
        error = f"agent loop stopped at MAX_ITERATIONS={MAX_ITERATIONS}"
        report_parts.append(
            f"⚠ Explicit truncation: {model} reached the {MAX_ITERATIONS}-iteration limit."
        )

    return {
        "model": model,
        "report": "\n\n".join(report_parts),
        "usage": usage,
        "cost_usd": round(_cost(model, usage), 4),
        "tool_calls": len(tool_order),
        "tool_order": tool_order,
        "iterations": iterations,
        "seconds": round(time.time() - t0, 1),
        "error": error,
        "stop_reason": stop_reason,
        "max_tokens": MAX_TOKENS,
        "truncated": truncated,
    }


def _synthesise(reports: list[dict], synthesis_model: str, clinical_judgments: str = "") -> dict:
    """Merge the per-model reports into one unioned briefing."""
    usable = [r for r in reports if r.get("report")]
    if not usable:
        return {
            "report": "",
            "usage": {"input": 0, "output": 0},
            "cost_usd": 0.0,
            "error": "no usable model reports to synthesise",
        }

    blocks = []
    for i, r in enumerate(usable, 1):
        blocks.append(f"=== REPORT {i} — model: {r['model']} ===\n{r['report']}")
    user_content = (
        "Union the following independent deep-review reports into one briefing, "
        "following your system instructions exactly.\n\n" + "\n\n".join(blocks)
    )

    usage = {"input": 0, "output": 0}
    error = None
    text = ""
    stop_reason = None
    truncated = False
    try:
        resp = client.messages.create(
            model=synthesis_model,
            max_tokens=MAX_TOKENS,
            thinking=config.THINKING,
            system=render_prompt(
                _SYNTHESIS_SYSTEM_TEMPLATE,
                CLINICAL_JUDGMENTS=clinical_judgments or "None recorded.",
            ),
            messages=[{"role": "user", "content": user_content}],
        )
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["input"] += getattr(u, "input_tokens", 0) or 0
            usage["output"] += getattr(u, "output_tokens", 0) or 0
        stop_reason = getattr(resp, "stop_reason", None)
        if stop_reason == "max_tokens":
            truncated = True
            error = f"synthesis truncated at max_tokens={MAX_TOKENS}"
        else:
            text = first_text(resp)
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"

    return {
        "report": text,
        "usage": usage,
        "cost_usd": round(_cost(synthesis_model, usage), 4),
        "model": synthesis_model,
        "error": error,
        "stop_reason": stop_reason,
        "max_tokens": MAX_TOKENS,
        "truncated": truncated,
    }


def _cost_footer(per_model: list[dict], synth: dict, total: float) -> str:
    lines = [
        "\n\n---",
        "_Ensemble deep-sweep — exploratory, decision-support only. "
        "Review with your oncologist before any action._",
        "",
        "| Model | Role | Tool calls | Cost (USD) |",
        "| --- | --- | --- | --- |",
    ]
    for r in per_model:
        note = " (failed)" if r.get("error") else ""
        lines.append(
            f"| {r['model']}{note} | research | {r.get('tool_calls', 0)} | "
            f"${r.get('cost_usd', 0):.2f} |"
        )
    snote = " (failed)" if synth.get("error") else ""
    lines.append(
        f"| {synth.get('model', '—')}{snote} | synthesis | — | ${synth.get('cost_usd', 0):.2f} |"
    )
    lines.append(f"| **Total** | | | **${total:.2f}** |")
    return "\n".join(lines)


def _verification_footer(result: dict) -> str:
    warning = verification_note(result)
    if warning:
        return warning
    verified = result.get("verified") or []
    detail = ", ".join(verified) if verified else "No PMID/NCT identifiers were present."
    return (
        "\n\n## Reference verification\n"
        "Deterministic primary-registry verification completed. "
        f"{detail}"
    )


def run_deep_sweep(
    profile: dict,
    models: list[str] | None = None,
    synthesis_model: str | None = None,
) -> dict:
    """Run the ensemble deep-sweep and return the unioned report + metadata.

    ``profile`` is NEVER mutated — each model runs against a private deep copy.
    Returns a dict with ``report`` (Markdown, ready to display), ``per_model``
    breakdowns, the synthesis metadata, and ``cost_total``.
    """
    models = models or config.DEEPSWEEP_MODELS
    synthesis_model = synthesis_model or config.DEEPSWEEP_SYNTHESIS_MODEL

    per_model = [_run_single_model(m, profile) for m in models]
    synth = _synthesise(
        per_model,
        synthesis_model,
        get_clinical_judgments_context(profile),
    )

    cost_total = round(
        sum(r.get("cost_usd", 0.0) for r in per_model) + synth.get("cost_usd", 0.0), 4
    )

    body = synth.get("report") or ""
    if not body:
        # Synthesis failed — fall back to concatenating the raw model reports so
        # the caregiver still gets the findings.
        parts = [f"## {r['model']}\n\n{r['report']}" for r in per_model if r.get("report")]
        body = (
            (
                "> ⚠ Synthesis step failed; showing raw per-model reports.\n\n"
                + "\n\n---\n\n".join(parts)
            )
            if parts
            else "Deep-sweep produced no output (all models failed)."
        )

    truncated = bool(synth.get("truncated") or any(r.get("truncated") for r in per_model))
    if truncated:
        body += (
            "\n\n> ⚠ **Explicit truncation notice:** at least one model reached a "
            "token or iteration limit. The briefing may be incomplete."
        )
        truncated_reports = [
            f"### {item['model']}\n\n{item['report']}"
            for item in per_model
            if item.get("truncated") and item.get("report")
        ]
        if truncated_reports:
            body += "\n\n## Raw truncated model reports\n\n" + "\n\n---\n\n".join(truncated_reports)
    verification = verify_references(body)
    report_md = (
        body + _verification_footer(verification) + _cost_footer(per_model, synth, cost_total)
    )

    return {
        "report": report_md,
        "per_model": [{k: v for k, v in r.items() if k != "tool_order"} for r in per_model],
        "synthesis": {k: v for k, v in synth.items() if k != "report"},
        "cost_total": cost_total,
        "models": models,
        "verification": verification,
        "truncated": truncated,
    }
