"""analyze_biomarker_trends — longitudinal trend computation."""
from __future__ import annotations


def _profile_with(readings):
    return {"biomarkers": readings}


def test_no_data_returns_no_data(agent):
    result = agent.analyze_biomarker_trends("CgA", _profile_with([]))
    assert result["trend"] == "no_data"
    assert result["readings"] == []


def test_single_reading_returns_single_reading(agent):
    profile = _profile_with([
        {"marker": "CgA", "value": 100, "unit": "ng/mL", "date": "2026-01-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "single_reading"
    assert result["latest"]["value"] == 100


def test_increasing_trend_above_threshold(agent):
    profile = _profile_with([
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 200, "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "increasing"
    assert result["percent_change"] == 100.0
    assert result["first_value"] == 100
    assert result["latest_value"] == 200
    assert result["number_of_readings"] == 2


def test_decreasing_trend_below_threshold(agent):
    profile = _profile_with([
        {"marker": "5-HIAA", "value": 100, "date": "2026-01-01"},
        {"marker": "5-HIAA", "value": 50,  "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("5-HIAA", profile)
    assert result["trend"] == "decreasing"
    assert result["percent_change"] == -50.0


def test_stable_trend_within_threshold(agent):
    # 10% change should be "stable" (threshold is ±25%).
    profile = _profile_with([
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 110, "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "stable"


def test_marker_lookup_is_case_insensitive(agent):
    profile = _profile_with([
        {"marker": "CGA", "value": 100, "date": "2026-01-01"},
        {"marker": "cga", "value": 200, "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["number_of_readings"] == 2


def test_readings_sorted_chronologically(agent):
    # Insert out of order — analyzer must sort by date before computing first/last.
    profile = _profile_with([
        {"marker": "CgA", "value": 200, "date": "2026-02-01"},
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 150, "date": "2026-03-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["first_value"] == 100
    assert result["latest_value"] == 150


def test_non_numeric_values_are_handled(agent):
    profile = _profile_with([
        {"marker": "TestMarker", "value": "positive", "date": "2026-01-01"},
        {"marker": "TestMarker", "value": "negative", "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("TestMarker", profile)
    assert result["trend"] == "non_numeric"


def test_other_markers_are_ignored(agent):
    profile = _profile_with([
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "NSE", "value": 999, "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "single_reading"


def test_zero_baseline_does_not_divide_by_zero(agent):
    profile = _profile_with([
        {"marker": "X", "value": 0,   "date": "2026-01-01"},
        {"marker": "X", "value": 100, "date": "2026-02-01"},
    ])
    result = agent.analyze_biomarker_trends("X", profile)
    # Should not raise; pct_change defaults to 0 -> "stable"
    assert result["percent_change"] == 0
    assert result["trend"] == "stable"
