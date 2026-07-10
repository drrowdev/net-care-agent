"""analyze_biomarker_trends — longitudinal trend computation."""

from __future__ import annotations


def _profile_with(readings):
    return {"biomarkers": readings}


def test_no_data_returns_no_data(agent):
    result = agent.analyze_biomarker_trends("CgA", _profile_with([]))
    assert result["trend"] == "no_data"
    assert result["readings"] == []


def test_single_reading_returns_single_reading(agent):
    profile = _profile_with(
        [
            {"marker": "CgA", "value": 100, "unit": "ng/mL", "date": "2026-01-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "single_reading"
    assert result["latest"]["value"] == 100


def test_increasing_trend_above_threshold(agent):
    profile = _profile_with(
        [
            {"marker": "CgA", "value": 100, "date": "2026-01-01"},
            {"marker": "CgA", "value": 200, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "increasing"
    assert result["percent_change"] == 100.0
    assert result["first_value"] == 100
    assert result["latest_value"] == 200
    assert result["number_of_readings"] == 2


def test_decreasing_trend_below_threshold(agent):
    profile = _profile_with(
        [
            {"marker": "5-HIAA", "value": 100, "date": "2026-01-01"},
            {"marker": "5-HIAA", "value": 50, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("5-HIAA", profile)
    assert result["trend"] == "decreasing"
    assert result["percent_change"] == -50.0


def test_stable_trend_within_threshold(agent):
    # 10% change should be "stable" (threshold is ±25%).
    profile = _profile_with(
        [
            {"marker": "CgA", "value": 100, "date": "2026-01-01"},
            {"marker": "CgA", "value": 110, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "stable"


def test_marker_lookup_is_case_insensitive(agent):
    profile = _profile_with(
        [
            {"marker": "CGA", "value": 100, "date": "2026-01-01"},
            {"marker": "cga", "value": 200, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["number_of_readings"] == 2


def test_readings_sorted_chronologically(agent):
    # Insert out of order — analyzer must sort by date before computing first/last.
    profile = _profile_with(
        [
            {"marker": "CgA", "value": 200, "date": "2026-02-01"},
            {"marker": "CgA", "value": 100, "date": "2026-01-01"},
            {"marker": "CgA", "value": 150, "date": "2026-03-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["first_value"] == 100
    assert result["latest_value"] == 150


def test_non_numeric_values_are_handled(agent):
    profile = _profile_with(
        [
            {"marker": "TestMarker", "value": "positive", "date": "2026-01-01"},
            {"marker": "TestMarker", "value": "negative", "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("TestMarker", profile)
    assert result["trend"] == "non_numeric"


def test_other_markers_are_ignored(agent):
    profile = _profile_with(
        [
            {"marker": "CgA", "value": 100, "date": "2026-01-01"},
            {"marker": "NSE", "value": 999, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("CgA", profile)
    assert result["trend"] == "single_reading"


def test_zero_baseline_does_not_divide_by_zero(agent):
    profile = _profile_with(
        [
            {"marker": "X", "value": 0, "date": "2026-01-01"},
            {"marker": "X", "value": 100, "date": "2026-02-01"},
        ]
    )
    result = agent.analyze_biomarker_trends("X", profile)
    assert result["percent_change"] is None
    assert result["trend"] == "indeterminate"
    assert "baseline is zero" in " ".join(result["data_quality_caveats"])


def test_mixed_units_are_not_compared_or_converted(agent):
    result = agent.analyze_biomarker_trends(
        "CgA",
        _profile_with(
            [
                {"marker": "CgA", "value": 10, "unit": "ng/mL", "date": "2026-01-01"},
                {"marker": "CgA", "value": 20, "unit": "nmol/L", "date": "2026-02-01"},
            ]
        ),
    )
    assert result["trend"] == "incompatible_units"
    assert result["unit_compatibility"]["conversion_performed"] is False
    assert set(result["unit_compatibility"]["units"]) == {"ng/ml", "nmol/l"}


def test_partly_missing_units_are_not_compared(agent):
    result = agent.analyze_biomarker_trends(
        "CgA",
        _profile_with(
            [
                {"marker": "CgA", "value": 10, "unit": "ng/mL", "date": "2026-01-01"},
                {"marker": "CgA", "value": 20, "date": "2026-02-01"},
            ]
        ),
    )
    assert result["trend"] == "incompatible_units"
    assert result["unit_compatibility"]["missing_count"] == 1


def test_full_and_latest_three_windows_surface_reversal(agent):
    result = agent.analyze_biomarker_trends(
        "CgA",
        _profile_with(
            [
                {"marker": "CgA", "value": 100, "unit": "ng/mL", "date": "2026-01-01"},
                {"marker": "CgA", "value": 300, "unit": "ng/mL", "date": "2026-02-01"},
                {"marker": "CgA", "value": 250, "unit": "ng/mL", "date": "2026-03-01"},
                {"marker": "CgA", "value": 200, "unit": "ng/mL", "date": "2026-04-01"},
            ]
        ),
    )
    assert result["full_period"]["trend"] == "increasing"
    assert result["latest_3"]["trend"] == "decreasing"
    assert result["latest_3"]["number_of_readings"] == 3
    assert result["trend_reversal"] is True


def test_reference_range_changes_are_caveated(agent):
    result = agent.analyze_biomarker_trends(
        "CgA",
        _profile_with(
            [
                {
                    "marker": "CgA",
                    "value": 100,
                    "unit": "ng/mL",
                    "reference_range": "0-100",
                    "date": "2026-01-01",
                },
                {
                    "marker": "CgA",
                    "value": 110,
                    "unit": "ng/mL",
                    "reference_range": "0-90",
                    "date": "2026-02-01",
                },
            ]
        ),
    )
    assert "Reference ranges differ" in " ".join(result["data_quality_caveats"])


def test_same_date_readings_retained_but_excluded(agent):
    readings = [
        {"marker": "CgA", "value": 10, "unit": "ng/mL", "date": "2026-01-01"},
        {"marker": "CgA", "value": 20, "unit": "ng/mL", "date": "2026-01-01"},
        {"marker": "CgA", "value": 30, "unit": "ng/mL", "date": "2026-02-01"},
    ]
    result = agent.analyze_biomarker_trends("CgA", _profile_with(readings))
    assert result["readings"] == readings
    assert result["trend"] == "insufficient_data"
    assert "same-date" in " ".join(result["data_quality_caveats"])
