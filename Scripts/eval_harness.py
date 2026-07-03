"""PHI-safe extraction eval harness (architecture-review P9) — scaffold.

Makes intake extraction QUALITY measurable so future model retiers and prompt
edits can be judged by numbers instead of by eye. It runs `run_intake` over a set
of golden documents with hand-verified expected extractions and scores recall /
precision on biomarkers and treatment_changes.

PHI: real golden cases are patient data. Keep them OUT of the repo — place them
on the Azure Files mount at ``$DATA_DIR/golden/*.json`` (each: {"text": ...,
"expected": {"biomarkers": [...], "treatment_changes": [...]}}). This file ships
only a synthetic, de-identified sample so the harness is runnable and testable.

Usage (needs ANTHROPIC_API_KEY; not run in CI):
    python scripts/eval_harness.py                 # synthetic sample
    python scripts/eval_harness.py --golden-dir <dir>
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

SAMPLE = [
    {
        "text": "Labs 2026-01-10: CgA 210 ng/mL (high). NSE 12 ng/mL. Plan: continue lanreotide 120mg q4w.",
        "expected": {
            "biomarkers": [{"marker": "CgA"}, {"marker": "NSE"}],
            "treatment_changes": ["continue lanreotide"],
        },
    }
]


def _marker_set(biomarkers) -> set[str]:
    return {(b.get("marker") or "").lower().strip() for b in biomarkers if b.get("marker")}


def score_extraction(expected: dict, actual: dict) -> dict:
    """Recall/precision of extracted biomarker markers vs expected (pure fn)."""
    exp = _marker_set(expected.get("biomarkers", []))
    act = _marker_set(actual.get("biomarkers", []))
    tp = len(exp & act)
    recall = tp / len(exp) if exp else 1.0
    precision = tp / len(act) if act else 1.0
    return {
        "expected_markers": sorted(exp),
        "found_markers": sorted(act),
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "missed": sorted(exp - act),
    }


def _load_cases(golden_dir: str | None) -> list[dict]:
    if not golden_dir:
        return SAMPLE
    cases = []
    for path in sorted(glob.glob(os.path.join(golden_dir, "*.json"))):
        cases.append(json.loads(open(path, encoding="utf-8").read()))
    return cases or SAMPLE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-dir", default=os.environ.get("GOLDEN_DIR"))
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import agent  # noqa: E402  (needs ANTHROPIC_API_KEY at import)

    cases = _load_cases(args.golden_dir)
    recalls = []
    for i, case in enumerate(cases, 1):
        profile = json.loads(json.dumps(agent.DEFAULT_PROFILE))
        _, extracted = agent.run_intake(case["text"], profile)
        s = score_extraction(case["expected"], extracted)
        recalls.append(s["recall"])
        print(f"case {i}: recall={s['recall']} precision={s['precision']} missed={s['missed']}")
    if recalls:
        print(f"\nmean recall = {sum(recalls)/len(recalls):.3f} over {len(recalls)} case(s)")


if __name__ == "__main__":
    main()
