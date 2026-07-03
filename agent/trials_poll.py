"""Deterministic trial-status poller (architecture-review P5).

A tracked trial opening, closing, or posting results is the single most
actionable event class for a metastatic-NET patient — and it is exactly what the
orchestrator's "do not re-surface tracked items" dedup suppresses. Trial status
is a deterministic ClinicalTrials.gov field, so poll it by ID instead of hoping
an LLM chooses to re-search it.

Read-only against the registry; the only profile mutations are: updating a
tracked trial's ``status`` (with a ``status_history`` audit entry) and appending
an alert. Network errors skip a trial silently — never clobber a stored status.
"""

from __future__ import annotations

import datetime

import requests


def _fetch_trial_status(nct: str) -> dict | None:
    """Return {"status", "last_update"} for an NCT ID, or None if unavailable."""
    try:
        r = requests.get(
            f"https://clinicaltrials.gov/api/v2/studies/{nct.upper()}",
            params={"format": "json"},
            timeout=12,
        )
        if r.status_code == 404:
            return None  # conservative: a bad/delisted ID shouldn't raise a false alarm
        r.raise_for_status()
        stat = r.json().get("protocolSection", {}).get("statusModule", {})
        return {
            "status": stat.get("overallStatus", ""),
            "last_update": stat.get("lastUpdatePostDateStruct", {}).get("date", ""),
        }
    except (requests.RequestException, ValueError):
        return None


def poll_tracked_trials(profile: dict) -> dict:
    """Check each tracked trial's live status; alert on changes. Mutates profile.

    Returns {"checked": N, "changed": [{"nct_id", "from", "to"}, ...]}.
    """
    tracked = profile.get("trials_tracked", [])
    today = datetime.date.today().isoformat()
    changed: list[dict] = []

    for t in tracked:
        nct = t.get("nct_id")
        if not nct:
            continue
        fetched = _fetch_trial_status(nct)
        if fetched is None:
            continue
        new_status = fetched["status"]
        old_status = t.get("status", "")
        if new_status and new_status != old_status:
            t["status"] = new_status
            t.setdefault("status_history", []).append(
                {
                    "date": today,
                    "from": old_status,
                    "to": new_status,
                    "last_update_posted": fetched.get("last_update", ""),
                }
            )
            profile.setdefault("alerts", []).append(
                {
                    "priority": "high",
                    "message": (
                        f"Tracked trial {nct} status changed: "
                        f"{old_status or 'unknown'} → {new_status}."
                    ),
                    "action_required": (
                        f"Review {nct} with the oncologist — a status change can "
                        f"open or close an option. {t.get('url', '')}"
                    ),
                    "resolved": False,
                    "date": today,
                    "source": "trial_status_poll",
                }
            )
            changed.append({"nct_id": nct, "from": old_status, "to": new_status})

    if changed:
        print(f"   → Trial poll: {len(changed)} status change(s) across {len(tracked)} tracked")
    return {"checked": len(tracked), "changed": changed}
