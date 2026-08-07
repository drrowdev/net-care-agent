"""Treatment classifier — dedupe + active/planned/completed labelling."""

from __future__ import annotations

import datetime
import hashlib
import json
import re

from . import config
from .llm import client, first_text, is_timeout_error, render_prompt, strip_code_fences
from .profile import active_documents, build_patient_context, sync_treatment_records


class TreatmentClassificationError(RuntimeError):
    """The model did not return a lossless classification of raw treatments."""


_IDENTITY_ALIASES = {
    "lanreotide": ("somatuline", "lanreotide", "somatostatin analogue", "sst analogue"),
    "prrt": (
        "lutetium-177 dotatate",
        "lutetium-177",
        "lu-177-dotatate",
        "177lu-octreotate",
        "lutathera",
        "lu-177",
        "177lu",
        "lutetium",
        "peptide receptor radionuclide therapy",
        "prrt",
    ),
    "octreotide": ("octreotide",),
    "everolimus": ("everolimus",),
    "sunitinib": ("sunitinib",),
    "capecitabine": ("capecitabine",),
    "temozolomide": ("temozolomide",),
    "streptozocin": ("streptozocin",),
    "radiotherapy": ("radiotherapy", "radiation therapy", "sbrt"),
    "chemotherapy": ("chemotherapy",),
    "captem": ("captem",),
    "tace": ("tace", "transarterial chemoembolization"),
    "y90_radioembolization": (
        "y-90 radioembolization",
        "y90 radioembolization",
        "radioembolization",
        "sirt",
    ),
    "pasireotide": ("pasireotide",),
    "telotristat": ("telotristat",),
    "interferon_alfa": ("interferon alfa", "interferon alpha"),
    "hepatic_artery_embolization": (
        "hepatic artery embolization",
        "hepatic arterial embolization",
        "liver embolization",
    ),
    "radiofrequency_ablation": (
        "radiofrequency ablation",
        "rfa",
    ),
    "liver_resection": (
        "liver resection",
        "hepatic resection",
    ),
}


def _treatment_identities(value: str) -> set[str]:
    normalized = value.casefold()
    captem_expansion = bool(
        "captem" in normalized or ("capecitabine" in normalized and "temozolomide" in normalized)
    )
    if captem_expansion:
        normalized = normalized.replace("captem", " ")
        normalized = normalized.replace("capecitabine", " ")
        normalized = normalized.replace("temozolomide", " ")
        regimen_identity = {"captem"}
    else:
        regimen_identity = set()
    identities = set()
    for identity, aliases in _IDENTITY_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            if re.search(pattern, normalized):
                identities.add(identity)
                normalized = re.sub(pattern, " ", normalized)
    for token in re.findall(r"[a-z][a-z0-9-]+", normalized):
        if re.search(
            r"(?:mab|nib|limus|ciclib|parib|taxel|platin|mycin|zomib|sertib|tinib)$",
            token,
        ):
            identities.add(f"drug:{token}")
    return identities | regimen_identity


def treatment_identity_set(value: str) -> set[str]:
    """Public deterministic identity extractor for stable source mappings."""
    return _treatment_identities(value)


def split_treatment_components(value: str) -> list[str]:
    """Split composites only when every candidate is a treatment identity."""
    protected = re.sub(
        r"captem\s*\(\s*capecitabine\s*(?:and|plus|/|\+|&)\s*temozolomide\s*\)",
        "CAPTEM",
        value,
        flags=re.IGNORECASE,
    )
    protected = re.sub(
        r"capecitabine\s*(?:/|\+|\band\b|\bplus\b)\s*temozolomide",
        "CAPTEM",
        protected,
        flags=re.IGNORECASE,
    )
    candidates = [
        item.strip()
        for item in re.split(
            r"\s*(?:\+|&|[,;/])\s*|\s+(?:plus|and|with)\s+",
            protected,
            flags=re.IGNORECASE,
        )
        if item.strip()
    ]
    if len(candidates) > 1:
        identities = [_treatment_identities(item) for item in candidates]
        if all(identity for identity in identities):
            custom_count = sum(
                all(item.startswith("custom:") for item in identity) for identity in identities
            )
            if custom_count <= 1:
                return candidates
    return [value]


def _classification_is_lossless(treatments: list[str], classified: object) -> bool:
    if not isinstance(classified, list) or not classified:
        return False
    outputs = [
        str(item.get("text") or item.get("label") or "").casefold().strip()
        for item in classified
        if isinstance(item, dict)
    ]
    for item in classified:
        if (
            not isinstance(item, dict)
            or item.get("category") not in {"active", "planned", "completed"}
            or not str(item.get("text") or item.get("label") or "").strip()
        ):
            return False
    raw_identity_sets = [
        _treatment_identities(component)
        for item in treatments
        for component in split_treatment_components(item)
    ]
    output_identity_sets = [_treatment_identities(item) for item in outputs]
    if any(not identities for identities in raw_identity_sets):
        return False
    if any(len(identities) != 1 for identities in output_identity_sets):
        return False
    raw_identities = set().union(*raw_identity_sets)
    output_identities = set().union(*output_identity_sets)
    return output_identities == raw_identities and len(output_identity_sets) == len(
        output_identities
    )


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
        active_documents(profile),
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
        if not _classification_is_lossless(treatments, classified):
            raise TreatmentClassificationError(
                "Treatment classification did not preserve every raw treatment"
            )
        records = sync_treatment_records(profile)
        for item in classified:
            identity = next(
                iter(_treatment_identities(item.get("text") or item.get("label") or ""))
            )
            source_ids = sorted(
                record["id"]
                for record in records
                if identity in _treatment_identities(record.get("text", ""))
            )
            digest = hashlib.sha256(f"{identity}:{'|'.join(source_ids)}".encode()).hexdigest()[:20]
            item["id"] = f"txclass_{digest}"
            item["source_treatment_ids"] = source_ids

        for item in classified:
            item_key = (item.get("label") or item.get("text") or "").lower().strip()
            for override_key, override in manual_overrides.items():
                if item_key in override_key or override_key in item_key or item_key == override_key:
                    item["category"] = override["category"]
                    break

        return classified

    except TreatmentClassificationError:
        raise
    except Exception as exc:
        if is_timeout_error(exc):
            raise
        raise TreatmentClassificationError("Treatment classification failed") from exc
