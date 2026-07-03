"""Test the pure scoring function of the eval harness (P9 scaffold)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent / "scripts" / "eval_harness.py"
_spec = importlib.util.spec_from_file_location("eval_harness", _HARNESS)
eval_harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_harness)


def test_score_extraction_perfect_recall():
    expected = {"biomarkers": [{"marker": "CgA"}, {"marker": "NSE"}]}
    actual = {"biomarkers": [{"marker": "cga"}, {"marker": "NSE"}, {"marker": "extra"}]}
    s = eval_harness.score_extraction(expected, actual)
    assert s["recall"] == 1.0
    assert s["missed"] == []
    assert s["precision"] < 1.0  # "extra" is a false positive


def test_score_extraction_flags_miss():
    expected = {"biomarkers": [{"marker": "CgA"}, {"marker": "5-HIAA"}]}
    actual = {"biomarkers": [{"marker": "CgA"}]}
    s = eval_harness.score_extraction(expected, actual)
    assert s["recall"] == 0.5
    assert s["missed"] == ["5-hiaa"]
