"""Clinical-judgment context formatter.

Judgments captured from oncologist consultations are injected verbatim
into the orchestrator and exec-summary system prompts. They override
data-driven conclusions in those agents.

``CLINICAL_JUDGMENTS_OVERRIDE`` is the shared, verbatim override instruction
used by the agents that receive judgments only as context (chat, questions) so
they treat them as hard constraints — matching the stronger, structured blocks
already embedded in the orchestrator and exec-summary prompts.
"""

from __future__ import annotations

# One canonical override block, reused across agents so the safety framing is
# identical everywhere. Decision-support only: the oncologist reviews all output.
CLINICAL_JUDGMENTS_OVERRIDE = (
    "━━━ CLINICAL JUDGMENTS ARE HARD CONSTRAINTS ━━━\n"
    "The record may include clinical judgments recorded directly from "
    "consultations with the treating oncologist. They are ground truth and "
    "OVERRIDE anything you would otherwise conclude from the raw data:\n"
    "- If a judgment marks something as NOT concerning, do not raise it as a "
    "concern or an action.\n"
    "- If a judgment rules out a treatment or trial, do not recommend or "
    "suggest it.\n"
    "- If a judgment states a preference or constraint (e.g. renal limits, "
    "timing), respect it.\n"
    "- Synthesise the oncologist's judgment WITH the data — never second-guess "
    "the oncologist on the basis of data alone.\n"
)


def get_clinical_judgments_context(profile: dict) -> str:
    judgments = profile.get("clinical_judgments", [])
    if not judgments:
        return ""

    lines = [
        "═══ ACCUMULATED CLINICAL JUDGMENTS ═══",
        "These are real outcomes and constraints from consultations with the treating team.",
        "They must shape your search priorities, recommendations, and assessments.",
        "",
    ]

    by_cat: dict[str, list] = {}
    for j in sorted(judgments, key=lambda x: x.get("date", ""), reverse=True):
        cat = j.get("category", "context")
        by_cat.setdefault(cat, []).append(j)

    cat_labels = {
        "constraint": "⛔ Constraints (rules out or limits certain approaches)",
        "preference": "★ Oncologist preferences and areas of interest",
        "outcome": "✓ Treatment/trial outcomes and responses",
        "context": "ℹ Clinical context and background",
    }
    for cat in ["constraint", "preference", "outcome", "context"]:
        items = by_cat.get(cat, [])
        if items:
            lines.append(cat_labels[cat])
            for j in items:
                lines.append(f"  [{j.get('date', '')}] {j.get('text', '')}")
            lines.append("")

    return "\n".join(lines)
