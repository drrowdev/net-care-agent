"""Clinical-judgment context formatter.

Judgments captured from oncologist consultations are injected verbatim
into the orchestrator and exec-summary system prompts. They override
data-driven conclusions in those agents.
"""

from __future__ import annotations


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
