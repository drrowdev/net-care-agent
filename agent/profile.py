"""Patient profile load/save and human-readable summary."""

from __future__ import annotations

import json
import logging

from . import backups, config
from .io import atomic_write_text
from .schema import normalize_profile, validate_profile

log = logging.getLogger(__name__)


DEFAULT_PROFILE: dict = {
    "patient": {
        "birth_year": None,
        "age": None,
        "sex": None,
        "diagnosis": "neuroendocrine tumor",
        "ki67_percent": None,
        "sstr_status": None,
        "sstr_score": None,
        "current_treatments": [],
        "allergies": [],
        "comorbidities": [],
        "oncologist": None,
        "treating_center": None,
        "location": None,
        "caregiver_relationship": None,
        "language": None,
        "regions_of_interest": [],
    },
    "biomarkers": [],
    "imaging": [],
    "appointments": [],
    "documents": [],
    "trials_tracked": [],
    "literature_watched": [],
    "alerts": [],
}


def load_profile() -> dict:
    if config.PROFILE_PATH.exists():
        raw = json.loads(config.PROFILE_PATH.read_text())
        # Lenient validation: never blocks the app — bad data is logged and
        # passed through unchanged so existing JSON keeps working.
        return normalize_profile(raw)
    profile = json.loads(json.dumps(DEFAULT_PROFILE))  # deep copy
    save_profile(profile)
    print(f"✓  Created new patient profile at {config.PROFILE_PATH}")
    return profile


def save_profile(profile: dict) -> None:
    config.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Run a strict validation pass for the log only — we still write the
    # caller's dict verbatim so ad-hoc / in-flight fields aren't dropped.
    try:
        validate_profile(profile)
    except Exception as e:
        log.warning("save_profile: validation issues (writing anyway): %s", e)
    atomic_write_text(
        config.PROFILE_PATH,
        json.dumps(profile, indent=2, default=str),
    )
    # Cheap: only copies once per day, then prunes.
    try:
        backups.daily_backup(config.PROFILE_PATH)
    except Exception as e:  # never let backup failure block a save
        log.warning("daily_backup raised: %s", e)


def get_patient_summary(profile: dict) -> str:
    """Concise text summary of the patient's current state, used as LLM context."""
    p = profile["patient"]
    bms = sorted(profile.get("biomarkers", []), key=lambda x: x.get("date", ""), reverse=True)[:6]
    docs = sorted(profile.get("documents", []), key=lambda x: x.get("date", ""), reverse=True)[:3]
    imgs = sorted(profile.get("imaging", []), key=lambda x: x.get("date", ""), reverse=True)[:2]
    active_alerts = [a for a in profile.get("alerts", []) if not a.get("resolved")]

    lines = [
        "═══ PATIENT PROFILE ═══",
        f"Diagnosis : {p.get('diagnosis') or 'unknown'}",
        f"Age / Sex : {p.get('age') or 'unknown'} / {p.get('sex') or 'unknown'}",
        f"Ki-67     : {p.get('ki67_percent', 'unknown')}%",
        f"SSTR      : {p.get('sstr_status', 'unknown')} (score: {p.get('sstr_score', 'unknown')})",
        f"Treatments: {', '.join(p.get('current_treatments', [])) or 'none documented'}",
        f"Center    : {p.get('treating_center', 'not specified')}",
        "",
        "─── Recent biomarkers ───",
    ]
    if bms:
        for b in bms:
            flag = (
                f" [{b.get('flag','').upper()}]" if b.get("flag") and b["flag"] != "normal" else ""
            )
            lines.append(
                f"  {b.get('date','')}  {b.get('marker','?')} = {b.get('value','?')} "
                f"{b.get('unit','')} (ref: {b.get('reference_range','?')}){flag}"
            )
    else:
        lines.append("  None recorded")

    lines += ["", "─── Recent imaging ───"]
    if imgs:
        for i in imgs:
            lines.append(
                f"  {i.get('date','')}  {i.get('modality','?')}: {i.get('impression','')[:120]}"
            )
    else:
        lines.append("  None recorded")

    lines += ["", "─── Recent documents ───"]
    if docs:
        for d in docs:
            lines.append(f"  [{d.get('date','')}] {d.get('type','?')}: {d.get('summary','')[:100]}")
    else:
        lines.append("  None recorded")

    lines += [
        "",
        f"Tracked trials     : {len(profile.get('trials_tracked', []))}",
        f"Tracked literature : {len(profile.get('literature_watched', []))} papers",
        f"Active alerts      : {len(active_alerts)}",
    ]
    if active_alerts:
        lines.append("")
        for a in active_alerts:
            lines.append(f"  ⚠  [{a['priority'].upper()}] {a['message']}")

    return "\n".join(lines)


def build_patient_context(profile: dict) -> str:
    """Compose a one-line identifying patient description from the live profile.

    System prompts call this instead of embedding identifying details in source
    code. When demographic fields are absent (fresh profile or scrubbed test
    fixture), it returns a generic phrase so the repo can be public without
    leaking PHI.
    """
    p = (profile or {}).get("patient", {}) or {}
    age = p.get("age")
    sex = (p.get("sex") or "").strip()
    if age and sex:
        head = f"a {age}-year-old {sex}"
    elif age:
        head = f"a {age}-year-old patient"
    elif sex:
        head = f"a {sex} patient"
    else:
        head = "a patient"
    diagnosis = (p.get("diagnosis") or "").strip() or "a neuroendocrine tumor"
    parts = [f"{head} with {diagnosis}"]
    location = (p.get("location") or "").strip()
    if location:
        parts.append(f"based in {location}")
    return ", ".join(parts)


def get_caregiver_relationship(profile: dict) -> str:
    """Relationship of the caregiver to the patient (e.g. 'spouse'). Defaults
    to the neutral 'caregiver' when unset so source code ships no relationship
    detail."""
    p = (profile or {}).get("patient", {}) or {}
    return (p.get("caregiver_relationship") or "").strip() or "caregiver"


def get_output_language(profile: dict) -> str:
    """Preferred output language for caregiver-facing artifacts. Defaults to
    English so a fresh deployment ships in a neutral language; override via
    `patient.language` (e.g. 'German', 'Spanish') in the live profile."""
    p = (profile or {}).get("patient", {}) or {}
    return (p.get("language") or "").strip() or "English"


def get_trial_region_filter(profile: dict) -> str | None:
    """Return a CT.gov-style country filter expression derived from
    `patient.regions_of_interest`, or None when no regions are configured."""
    p = (profile or {}).get("patient", {}) or {}
    regions = [r for r in (p.get("regions_of_interest") or []) if r]
    if not regions:
        return None
    return " or ".join(f'country="{r}"' for r in regions)
