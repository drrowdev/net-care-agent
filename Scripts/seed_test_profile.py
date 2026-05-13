"""Seed a minimal patient_profile.json for local testing.

Writes to ${DATA_DIR}/patient_profile.json. Refuses to overwrite an existing file
unless --force is passed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path


def _seed() -> dict:
    today = dt.date.today().isoformat()
    return {
        "patient": {
            "name_alias": "Test Patient",
            "dob": "1960-01-01",
            "age": 65,
            "sex": "female",
            "diagnosis": "neuroendocrine tumor",
            "ki67_percent": 8,
            "location": None,
            "caregiver_relationship": None,
            "language": None,
            "regions_of_interest": [],
        },
        "biomarkers": [
            {"date": today, "marker": "CgA",    "value": 230, "unit": "ng/mL", "ref_low": 0,  "ref_high": 100},
            {"date": today, "marker": "5-HIAA", "value": 18,  "unit": "mg/24h","ref_low": 2,  "ref_high": 9},
        ],
        "imaging": [],
        "treatments": [
            {"name": "lanreotide", "status": "active", "start_date": "2025-01-15"},
        ],
        "documents": [],
        "trials": [],
        "papers": [],
        "alerts": [],
        "judgments": [],
        "questions": [],
        "exec_summary": {},
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true", help="Overwrite existing profile")
    args = p.parse_args()

    data_dir = Path(os.environ.get("DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "patient_profile.json"

    if target.exists() and not args.force:
        print(f"Refusing to overwrite {target} (pass --force).", file=sys.stderr)
        return 1

    target.write_text(json.dumps(_seed(), indent=2))
    print(f"Wrote seed profile to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
