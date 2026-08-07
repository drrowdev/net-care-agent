"""Command-line interface (used for ad-hoc local testing)."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from . import config
from .classify import classify_treatments
from .exec_summary import generate_executive_summary  # noqa: F401  (kept for callers)
from .follow_through import (
    append_history,
    increment_workflow_revision,
    invalidate_generated_context,
    new_workflow_id,
    validate_text,
)
from .intake import run_intake
from .orchestrator import run_orchestrator
from .profile import (
    active_alerts,
    alert_token,
    get_patient_summary,
    get_research_ids,
    invalidate_treatment_classification,
    load_profile,
    record_latest_research_update,
    save_profile,
    sync_treatment_records,
)
from .schema import now_stamp
from .serialize import serialized_mutation


def _print_and_save_report(report: str, tag: str) -> None:
    header = "═" * 60
    print(f"\n{header}\n📋  REPORT\n{header}\n{report}\n{header}")

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.REPORTS_DIR / f"report_{tag}_{stamp}.txt"
    path.write_text(report, encoding="utf-8")
    print(f"\n✓  Report saved → {path}")


def cmd_feed(args) -> None:
    raw_bytes = None
    filename = None
    if args.file:
        path = Path(args.file)
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8", errors="replace")
        filename = path.name
        print(f"📄  Reading {path.name} ({len(text):,} chars)")
    elif args.text:
        text = args.text
    else:
        print("❌  Provide --text '...' or --file path/to/file.txt")
        sys.exit(1)

    with serialized_mutation():
        profile = load_profile()
        job_id = f"cli-feed-{datetime.datetime.now():%Y%m%d%H%M%S}"
        previous_trial_ids = set(get_research_ids(profile, "trial"))
        previous_paper_ids = set(get_research_ids(profile, "paper"))
        profile, extracted = run_intake(
            text,
            profile,
            raw_bytes=raw_bytes,
            filename=filename,
            media_type="text/plain",
        )
        extracted["source_job_id"] = job_id
        intake_revision = int(profile.get("profile_revision") or 0) + 1
        for alert in profile.get("alerts", []):
            if alert.get("source_document_id") != extracted.get("source_document_id"):
                continue
            alert["source_job_id"] = job_id
            alert["generation_profile_revision"] = intake_revision
            alert["source_dependency_active"] = True
        save_profile(profile)
        extracted["generation_profile_revision"] = int(profile.get("profile_revision") or 0) + 1
        report = run_orchestrator(profile, extracted)
        profile["treatments_classified"] = classify_treatments(profile)
        record_latest_research_update(
            profile,
            job_id=job_id,
            trigger="feed",
            previous_trial_ids=previous_trial_ids,
            previous_paper_ids=previous_paper_ids,
            record_empty=False,
        )
        final_revision = int(profile.get("profile_revision") or 0) + 1
        profile["treatments_classification_revision"] = final_revision
        profile["treatments_classification_job_id"] = job_id
        for alert in profile.get("alerts", []):
            if alert.get("source_job_id") == job_id:
                alert["generation_profile_revision"] = final_revision
        save_profile(profile)
    _print_and_save_report(report, "feed")


def cmd_digest(args) -> None:
    print("⚙  Generating research digest …")
    extracted = {
        "document_type": "scheduled_digest",
        "summary": "Scheduled weekly research review",
        "key_findings": [],
        "suggested_workflows": ["pubmed_search", "trial_search", "biomarker_analysis"],
        "workflow_rationale": (
            "Periodic review: search for new NET literature from the past 4 weeks, "
            "check for newly opened European trials, review all recorded biomarker trends."
        ),
    }
    with serialized_mutation():
        profile = load_profile()
        job_id = f"cli-digest-{datetime.datetime.now():%Y%m%d%H%M%S}"
        extracted["source_job_id"] = job_id
        extracted["generation_profile_revision"] = int(profile.get("profile_revision") or 0) + 1
        previous_trial_ids = set(get_research_ids(profile, "trial"))
        previous_paper_ids = set(get_research_ids(profile, "paper"))
        report = run_orchestrator(profile, extracted)
        profile["treatments_classified"] = classify_treatments(profile)
        record_latest_research_update(
            profile,
            job_id=job_id,
            trigger="digest",
            previous_trial_ids=previous_trial_ids,
            previous_paper_ids=previous_paper_ids,
            record_empty=True,
        )
        final_revision = int(profile.get("profile_revision") or 0) + 1
        profile["treatments_classification_revision"] = final_revision
        profile["treatments_classification_job_id"] = job_id
        for alert in profile.get("alerts", []):
            if alert.get("source_job_id") == job_id:
                alert["generation_profile_revision"] = final_revision
        save_profile(profile)
    _print_and_save_report(report, "digest")


def cmd_status(args) -> None:
    profile = load_profile()
    print(get_patient_summary(profile))
    unresolved = active_alerts(profile)
    if unresolved:
        print(
            f"\n⚠  {len(unresolved)} unresolved alert(s) — run `resolve-alert ALERT_ID` "
            "after reviewing the current stable ID."
        )


def cmd_resolve_alert(args) -> None:
    with serialized_mutation():
        profile = load_profile()
        alert = next(
            (item for item in active_alerts(profile) if item.get("id") == args.alert_id),
            None,
        )
        if alert is None:
            print("❌  Alert not found or no longer active")
            sys.exit(1)
        outcome_text = validate_text(
            args.outcome or "Marked resolved from the CLI",
            "outcome",
            limit=2000,
        )
        mutation_id = new_workflow_id("cli")
        before_token = alert_token(alert)
        timestamp = now_stamp()
        alert["resolved"] = True
        alert["resolution"] = {
            "status": "resolved",
            "resolved_at": timestamp,
            "outcome_kind": "administrative",
            "outcome_text": outcome_text,
            "provenance": {
                "capture_method": "caregiver_entered",
                "attributed_to": "caregiver",
                "source_verification": "not_applicable",
            },
            "follow_up_id": None,
            "visit_id": None,
            "decision_id": None,
        }
        append_history(
            alert,
            operation="resolved",
            mutation_id=mutation_id,
            payload={"alert_id": args.alert_id, "outcome": outcome_text},
            before_token=before_token,
            changes={"resolved": {"before": False, "after": True}},
        )
        increment_workflow_revision(profile)
        invalidate_generated_context(profile, "active_alert_resolved_after_generation")
        save_profile(profile)
    print(f"✓  Resolved alert {args.alert_id}")


def cmd_update_profile(args) -> None:
    # Gather slow interactive input without holding the shared mutation lock.
    # Reload under the lock before applying so web/background changes made while
    # the user was typing are preserved.
    snapshot = load_profile()
    current_patient = snapshot["patient"]
    fields = {
        "ki67_percent": ("Ki-67 %", float),
        "sstr_status": ("SSTR status (positive/negative/unknown)", str),
        "sstr_score": ("SSTR Krenning score (0-4)", int),
        "treating_center": ("Treating center", str),
        "oncologist": ("Oncologist name", str),
    }
    updates = {}
    print("Leave blank to keep current value.\n")
    for key, (label, cast) in fields.items():
        current = current_patient.get(key, "not set")
        raw = input(f"  {label} [{current}]: ").strip()
        if raw:
            try:
                updates[key] = cast(raw) if cast is not str else raw
            except ValueError:
                print(f"  ⚠  Could not parse '{raw}', keeping current value")

    print(f"\n  Current treatments: {current_patient.get('current_treatments', [])}")
    tx_raw = input("  Add treatment (leave blank to skip): ").strip()

    with serialized_mutation():
        profile = load_profile()
        profile["patient"].update(updates)
        if tx_raw:
            profile["patient"].setdefault("current_treatments", []).append(tx_raw)
            invalidate_treatment_classification(profile)
            sync_treatment_records(profile)
        save_profile(profile)
        job_id = f"cli-update-{datetime.datetime.now():%Y%m%d%H%M%S}"
        profile["treatments_classified"] = classify_treatments(profile)
        profile["treatments_classification_revision"] = profile.get("profile_revision")
        profile["treatments_classification_job_id"] = job_id
        save_profile(profile, clinical_change=False)
    print("\n✓  Profile updated.")
    print(get_patient_summary(profile))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="NET Care Agent — AI research assistant for NET cancer management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    feed_p = sub.add_parser("feed", help="Feed a document or text into the system")
    feed_p.add_argument("--text", type=str, help="Inline text to process")
    feed_p.add_argument("--file", type=str, help="Path to a text file to process")
    feed_p.set_defaults(func=cmd_feed)

    digest_p = sub.add_parser("digest", help="Run a scheduled research digest")
    digest_p.set_defaults(func=cmd_digest)

    status_p = sub.add_parser("status", help="Show current patient status summary")
    status_p.set_defaults(func=cmd_status)

    resolve_p = sub.add_parser("resolve-alert", help="Resolve an active alert by stable ID")
    resolve_p.add_argument("alert_id", help="Stable alert ID shown by status")
    resolve_p.add_argument("--outcome", help="Administrative resolution outcome")
    resolve_p.set_defaults(func=cmd_resolve_alert)

    update_p = sub.add_parser("update-profile", help="Interactively update patient fields")
    update_p.set_defaults(func=cmd_update_profile)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    args.func(args)
