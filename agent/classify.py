"""Treatment classifier — dedupe + active/planned/completed labelling."""

from __future__ import annotations

import datetime
import json

from . import config
from .llm import client, first_text, render_prompt, strip_code_fences
from .profile import build_patient_context

TREATMENT_CLASSIFIER_SYSTEM_TEMPLATE = """\
You are a clinical data analyst. Your job is to deduplicate, merge, and classify treatment entries for [[PATIENT_CONTEXT]]. You are given the raw treatment entries, recent clinical context, and today's date — use today's date and document recency as your PRIMARY evidence for classification; keyword cues are fallbacks.

1. DEDUPLICATE: Merge entries that refer to the same treatment.
   - "Somatuline", "SST analogue", "lanreotide", "somatostatin analogue" → same drug
   - "Lu-177-DOTATATE", "Lutetium", "PRRT", "177Lu-octreotate" → same therapy
   - Keep the most informative/specific version as the label.
   - If dose or frequency differs across duplicates, use the most recent/specific. Never synthesize a dose or frequency that appears in no source entry.
   - If one raw entry names multiple distinct treatments (e.g. "lanreotide plus everolimus"), output one object per treatment.
   - If the same treatment has conflicting statuses across documents, the most recent document wins.

2. CLASSIFY each unique treatment into exactly one category:
   - "active"    — currently ongoing as of today's date
   - "planned"   — scheduled, recommended, or under consideration for the future
   - "completed" — finished, historical, or no longer ongoing
   Temporal checks: a "planned" item whose planned date is already past today should be re-evaluated against recent context (it likely happened → completed, or was superseded). A recurring treatment ("every X weeks") is active unless a later document says it stopped.

3. Extract a clean short label (max 60 chars) and an optional date string. date = start date for active/planned, end/completion date for completed; if only one date is known, use it; null if none.

Return ONLY a valid JSON array, no markdown, no prose:
[
  {
    "text": "canonical merged treatment description",
    "category": "active|planned|completed",
    "label": "Short readable label e.g. Somatuline 120mg q3w (lanreotide)",
    "date": "YYYY-MM or YYYY or null"
  }
]

Fallback keyword cues (use when dates don't settle it):
- "completed", "historical", "through MM/YYYY" → completed
- "continuing", "ongoing", "every X weeks/months" → active
- "plan to", "planned", "considering", "next review", "potential" → planned
- PRRT/Lutetium with a past end date → completed; SBRT/radiotherapy with "completed" → completed
- Be conservative: if genuinely unclear, prefer "active" over "completed" (a wrongly-active entry is visible and gets corrected at review; a wrongly-completed one hides ongoing therapy).

If the input contains no treatment entries, return []. After merging, the output should have fewer entries than the input if duplicates exist (splitting multi-drug entries is the only reason it may not).
"""


def classify_treatments(profile: dict) -> list:
    """Classify all treatment strings into active/planned/completed categories.
    Preserves any manual category overrides already in treatments_classified."""
    treatments = profile.get("patient", {}).get("current_treatments", [])
    if not treatments:
        return []

    existing = profile.get("treatments_classified", [])
    manual_overrides: dict[str, dict] = {}
    for e in existing:
        key = (e.get("label") or e.get("text") or "").lower().strip()
        if key:
            manual_overrides[key] = e

    recent_docs = sorted(
        profile.get("documents", []),
        key=lambda x: x.get("date", ""),
        reverse=True,
    )[:5]
    doc_context = "\n\n".join(
        f"[{d.get('date', '')} {d.get('type', '')}]: {d.get('summary', '')}" for d in recent_docs
    )

    try:
        system_prompt = render_prompt(
            TREATMENT_CLASSIFIER_SYSTEM_TEMPLATE,
            PATIENT_CONTEXT=build_patient_context(profile),
        )
        resp = client.messages.create(
            model=config.MODEL_CLASSIFY,
            max_tokens=6000,
            thinking=config.THINKING,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Classify these treatment entries:\n\n"
                        f"{json.dumps(treatments, indent=2)}\n\n"
                        f"Recent clinical context:\n{doc_context}\n\n"
                        f"Today: {datetime.date.today().isoformat()}"
                    ),
                }
            ],
        )
        raw = strip_code_fences(first_text(resp))
        classified = json.loads(raw)
        if not isinstance(classified, list):
            classified = []

        for item in classified:
            item_key = (item.get("label") or item.get("text") or "").lower().strip()
            for override_key, override in manual_overrides.items():
                if item_key in override_key or override_key in item_key or item_key == override_key:
                    item["category"] = override["category"]
                    break

        return classified

    except Exception as e:
        print(f"  ⚠  Treatment classification failed: {e}")
        return [
            {"text": t, "category": "active", "label": t[:60], "date": None} for t in treatments
        ]
