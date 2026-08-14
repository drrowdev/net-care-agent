"""Deterministic treatment identity library — no model calls, no profile imports.

Pure text analysis over treatment strings: alias-based identity extraction,
certifiability checks, and composite splitting. This module must stay free of
any dependency on ``agent.profile``/``agent.llm`` because
``profile.sync_treatment_records`` and the frozen v6 migration both import
``split_treatment_components`` from here.

Its output feeds stable ``tx_*`` component IDs, so behaviour changes here
re-key persisted treatment component identity. Treat it as frozen.
"""

from __future__ import annotations

import re

_IDENTITY_ALIASES = {
    "lanreotide": ("somatuline", "lanreotide", "somatostatin analogue", "sst analogue"),
    "prrt": (
        "lutetium-177 dotatate",
        "lutetium-177",
        "lu-177-dotatate",
        "lu-177 dotatate",
        "177lu-octreotate",
        "lutathera",
        "lu-177",
        "177lu",
        "lutetium",
        "peptide receptor radionuclide therapy",
        "prrt",
    ),
    "octreotide": ("sandostatin", "octreotide"),
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
        "hepatectomy",
        "partial hepatectomy",
        "liver surgery",
    ),
    "pancreatectomy": (
        "pancreatectomy",
        "distal pancreatectomy",
        "whipple procedure",
        "pancreaticoduodenectomy",
    ),
    "cytoreductive_surgery": (
        "cytoreductive surgery",
        "debulking surgery",
        "tumor debulking",
        "tumour debulking",
    ),
    "metastasectomy": ("metastasectomy",),
}


_BENIGN_TREATMENT_WORDS = {
    "active",
    "and",
    "after",
    "autogel",
    "before",
    "by",
    "changed",
    "complete",
    "completed",
    "considered",
    "continue",
    "continued",
    "continuing",
    "current",
    "currently",
    "daily",
    "decrease",
    "decreased",
    "depot",
    "discontinued",
    "dose",
    "every",
    "for",
    "former",
    "from",
    "held",
    "hold",
    "historical",
    "injection",
    "intramuscular",
    "intravenous",
    "iv",
    "monthly",
    "now",
    "ongoing",
    "oral",
    "paused",
    "pause",
    "plan",
    "planned",
    "prior",
    "previous",
    "plus",
    "reduce",
    "reduced",
    "recommended",
    "restart",
    "restarted",
    "replaced",
    "resume",
    "resumed",
    "schedule",
    "scheduled",
    "start",
    "started",
    "starting",
    "status",
    "stop",
    "stopped",
    "stopping",
    "subcutaneous",
    "switch",
    "switched",
    "switching",
    "then",
    "therapy",
    "to",
    "transitioned",
    "versus",
    "via",
    "vs",
    "weekly",
    "with",
    "next",
    "immediately",
    "im",
    "lar",
    "po",
    "sc",
    "sq",
    "sl",
    "bid",
    "tid",
    "qid",
    "qd",
    "qod",
    "qam",
    "qpm",
    "qhs",
    "prn",
    "infusion",
    "infusions",
    "tablet",
    "tablets",
    "capsule",
    "capsules",
    "vial",
    "vials",
    "long-acting",
    "extended-release",
    "immediate-release",
    "treatment",
    "regimen",
}
_BENIGN_TREATMENT_TOKEN_RE = re.compile(
    r"(?:\d+(?:\.\d+)?(?:mcg|mg|g|kg|ml|units?|iu|miu|bq|kbq|mbq|gbq|mci|uci)?|"
    r"(?:mcg|mg|g|kg|ml|units?|iu|miu|bq|kbq|mbq|gbq|mci|uci)|"
    r"q\d+(?:h|hr|d|w|wk|m|mo)|"
    r"\d{4}(?:-\d{1,2}(?:-\d{1,2})?)?|"
    r"once|twice|times?|days?|weeks?|months?|cycles?|courses?)",
    re.IGNORECASE,
)


def _treatment_identity_scan(value: str) -> tuple[set[str], str]:
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
            normalized = re.sub(
                rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
                " ",
                normalized,
            )
    return identities | regimen_identity, normalized


def _treatment_identities(value: str) -> set[str]:
    return _treatment_identity_scan(value)[0]


def treatment_text_is_certifiable(value: str) -> bool:
    """Return whether every treatment-like token has an authoritative identity."""
    identities, residual = _treatment_identity_scan(value)
    if not identities:
        return False
    tokens = re.findall(r"[a-z0-9][a-z0-9-]*", residual.casefold())
    return all(
        token in _BENIGN_TREATMENT_WORDS or _BENIGN_TREATMENT_TOKEN_RE.fullmatch(token)
        for token in tokens
    )


def treatment_identity_set(value: str) -> set[str]:
    """Public deterministic identity extractor for stable source mappings."""
    return _treatment_identities(value)


def _protected_components(value: str) -> str:
    protected = re.sub(
        r"captem\s*\(\s*capecitabine\s*(?:and|plus|/|\+|&)\s*temozolomide\s*\)",
        "CAPTEM",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"capecitabine\s*(?:/|\+|\band\b|\bplus\b)\s*temozolomide",
        "CAPTEM",
        protected,
        flags=re.IGNORECASE,
    )


def _component_candidates(value: str) -> list[str]:
    protected = _protected_components(value)
    transition_patterns = (
        r"^\s*(?:switched|changed|transitioned)\s+from\s+(.+?)\s+to\s+(.+?)\s*$",
        r"^\s*(.+?)\s+(?:replaced\s+by|versus|vs\.?)\s+(.+?)\s*$",
    )
    for pattern in transition_patterns:
        match = re.match(pattern, protected, flags=re.IGNORECASE)
        if match:
            return [item.strip() for item in match.groups()]
    return [
        item.strip()
        for item in re.split(
            r"\s*(?:\+|&|[,;/])\s*|\s+(?:plus|and|with)\s+",
            protected,
            flags=re.IGNORECASE,
        )
        if item.strip()
    ]


def split_treatment_components(value: str) -> list[str]:
    """Split composites only when every candidate is a treatment identity."""
    candidates = _component_candidates(value)
    if len(candidates) > 1:
        identities = [_treatment_identities(item) for item in candidates]
        if all(
            len(identity) == 1 and treatment_text_is_certifiable(item)
            for identity, item in zip(identities, candidates, strict=True)
        ):
            custom_count = sum(
                all(item.startswith("custom:") for item in identity) for identity in identities
            )
            if custom_count <= 1:
                return candidates
    return [value]
