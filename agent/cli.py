"""Command-line interface (used for ad-hoc local testing)."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from . import config
from .classify import classify_treatments
from .exec_summary import generate_executive_summary  # noqa: F401  (kept for callers)
from .intake import run_intake
from .orchestrator import run_orchestrator
from .profile import get_patient_summary, load_profile, save_profile
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
        profile, extracted = run_intake(
            text,
            profile,
            raw_bytes=raw_bytes,
            filename=filename,
            media_type="text/plain",
        )
        report = run_orchestrator(profile, extracted)
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
        report = run_orchestrator(profile, extracted)
        save_profile(profile)
    _print_and_save_report(report, "digest")


def cmd_status(args) -> None:
    profile = load_profile()
    print(get_patient_summary(profile))
    unresolved = [a for a in profile.get("alerts", []) if not a.get("resolved")]
    if unresolved:
        print(
            f"\n⚠  {len(unresolved)} unresolved alert(s) — run `status` to review, "
            "or edit patient_profile.json to mark as resolved."
        )


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
        profile["treatments_classified"] = classify_treatments(profile)
        save_profile(profile)
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

    update_p = sub.add_parser("update-profile", help="Interactively update patient fields")
    update_p.set_defaults(func=cmd_update_profile)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(0)
    args.func(args)
