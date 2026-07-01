"""Treatment classifier — dedupe + active/planned/completed labelling."""

from __future__ import annotations

import datetime
import json

from . import config
from .llm import client, first_text, strip_code_fences
from .profile import build_patient_context

TREATMENT_CLASSIFIER_SYSTEM_TEMPLATE = """\
You are a clinical data analyst. Your job is to deduplicate, merge, and classify
treatment entries for {patient_context}.

The raw treatment list may contain duplicate entries, synonyms, or the same
treatment written differently across multiple documents. You must:

1. DEDUPLICATE: Merge entries that refer to the same treatment.
   - "Somatuline", "SST analogue", "lanreotide", "somatostatin analogue" → same drug
   - "Lu-177-DOTATATE", "Lutetium", "PRRT", "177Lu-octreotate" → same therapy
   - Keep the most informative/specific version as the label
   - If dose or frequency differs across duplicates, use the most recent/specific

2. CLASSIFY each unique treatment into exactly one category:
   - "active"    — currently ongoing treatment the patient is receiving right now
   - "planned"   — scheduled, recommended, or under consideration for the future
   - "completed" — finished, historical, or no longer ongoing

3. Extract a clean short label (max 60 chars) and an optional date string.

Return ONLY a valid JSON array, no markdown, no prose:
[
  {{
    "text": "canonical merged treatment description",
    "category": "active|planned|completed",
    "label": "Short readable label e.g. Somatuline 120mg q3w (lanreotide)",
    "date": "YYYY-MM or YYYY or null"
  }}
]

Rules:
- Words like "completed", "historical", "through MM/YYYY" → completed
- Words like "continuing", "ongoing", "every X weeks/months" → active
- Words like "plan to", "planned", "considering", "next review", "potential" → planned
- PRRT/Lutetium mentioned with a past end date → completed
- SBRT/radiotherapy with "completed" → completed
- Be conservative: if unclear, prefer "active" over "completed"
- The output list should have FEWER entries than the input if duplicates exist
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
        f"[{d.get('date','')} {d.get('type','')}]: {d.get('summary','')}" for d in recent_docs
    )

    try:
        system_prompt = TREATMENT_CLASSIFIER_SYSTEM_TEMPLATE.format(
            patient_context=build_patient_context(profile),
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
