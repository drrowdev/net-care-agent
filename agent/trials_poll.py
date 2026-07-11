"""Deterministic refresh of tracked ClinicalTrials.gov records."""

from __future__ import annotations

import datetime
import re

import requests

from .schema import now_stamp


def _fetch_trial_status(nct: str) -> dict | None:
    """Return refreshable registry fields for an NCT ID, or None."""
    try:
        response = requests.get(
            f"https://clinicaltrials.gov/api/v2/studies/{nct.upper()}",
            params={"format": "json"},
            timeout=(5, 12),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        proto = response.json().get("protocolSection", {})
        stat = proto.get("statusModule", {})
        ident = proto.get("identificationModule", {})
        design = proto.get("designModule", {})
        eligibility = proto.get("eligibilityModule", {})
        phases = design.get("phases") if "phases" in design else None
        if isinstance(phases, str):
            phases = [phases]
        return {
            "status": stat.get("overallStatus") if "overallStatus" in stat else None,
            "title": ident.get("briefTitle") if "briefTitle" in ident else None,
            "phase": " / ".join(phases) if phases is not None else None,
            "phases": phases,
            "eligibility_excerpt": (
                eligibility.get("eligibilityCriteria")
                if "eligibilityCriteria" in eligibility
                else None
            ),
            "registry_last_update": (
                stat.get("lastUpdatePostDateStruct", {}).get("date")
                if "lastUpdatePostDateStruct" in stat
                else None
            ),
        }
    except (requests.RequestException, ValueError):
        return None


def _normalise_eligibility(text: object) -> str:
    return " ".join(str(text or "").lower().split())


def _material_eligibility_change(old: object, new: object) -> bool:
    """Ignore formatting-only and tiny editorial changes, but catch criterion changes."""
    old_text = _normalise_eligibility(old)
    new_text = _normalise_eligibility(new)
    if old_text and not new_text:
        return True
    if not old_text or old_text == new_text:
        return False
    old_tokens = set(re.findall(r"[a-z0-9.%+-]+", old_text))
    new_tokens = set(re.findall(r"[a-z0-9.%+-]+", new_text))
    changed = old_tokens.symmetric_difference(new_tokens)
    material_terms = {
        "inclusion",
        "exclusion",
        "prior",
        "allowed",
        "required",
        "not",
        "ecog",
        "age",
        "renal",
        "hepatic",
        "prrt",
        "ki-67",
    }
    return (
        bool(changed & material_terms)
        or len(changed) / max(len(old_tokens | new_tokens), 1) >= 0.05
    )


def _append_alert(profile: dict, *, priority: str, message: str, action: str, today: str) -> None:
    profile.setdefault("alerts", []).append(
        {
            "priority": priority,
            "message": message,
            "action_required": action,
            "resolved": False,
            "date": today,
            "added_at": now_stamp(),
            "source": "trial_status_poll",
        }
    )


def poll_tracked_trials(profile: dict) -> dict:
    """Refresh tracked registry fields, preserving every prior value in history."""
    tracked = profile.get("trials_tracked", [])
    today = datetime.date.today().isoformat()
    changed: list[dict] = []

    for trial in tracked:
        nct = trial.get("nct_id")
        if not nct:
            continue
        fetched = _fetch_trial_status(nct)
        if fetched is None:
            continue

        before: dict = {}
        after: dict = {}
        for field in (
            "status",
            "title",
            "phase",
            "phases",
            "eligibility_excerpt",
            "registry_last_update",
        ):
            new_value = fetched.get(field)
            if new_value is None:
                continue
            old_value = trial.get(field, [] if field == "phases" else "")
            if new_value != old_value:
                before[field] = old_value
                after[field] = new_value

        if not after:
            continue

        material_eligibility = _material_eligibility_change(
            before.get("eligibility_excerpt"),
            after.get("eligibility_excerpt"),
        )
        for field, value in after.items():
            trial[field] = value
        trial.setdefault("registry_history", []).append(
            {
                "date": today,
                "registry_last_update": fetched.get("registry_last_update", ""),
                "changed_fields": sorted(after),
                "before": before,
                "after": after,
            }
        )

        if "status" in after:
            old_status = before["status"]
            new_status = after["status"]
            trial.setdefault("status_history", []).append(
                {
                    "date": today,
                    "from": old_status,
                    "to": new_status,
                    "last_update_posted": fetched.get("registry_last_update", ""),
                }
            )
            _append_alert(
                profile,
                priority="high",
                message=(
                    f"Tracked trial {nct} status changed: {old_status or 'unknown'} → {new_status}."
                ),
                action=(
                    f"Review {nct} with the oncologist — a status change can open or "
                    f"close an option. {trial.get('url', '')}"
                ),
                today=today,
            )

        if material_eligibility:
            _append_alert(
                profile,
                priority="high",
                message=f"Tracked trial {nct} posted a material eligibility change.",
                action=(
                    f"Re-check the complete eligibility criteria for {nct} with the "
                    "trial coordinator and treating oncologist."
                ),
                today=today,
            )

        changed.append(
            {
                "nct_id": nct,
                "from": before.get("status", trial.get("status", "")),
                "to": after.get("status", trial.get("status", "")),
                "fields": sorted(after),
                "material_eligibility_change": material_eligibility,
            }
        )

    return {"checked": len(tracked), "changed": changed}
