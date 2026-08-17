"""Longitudinal biomarker trend computation."""

from __future__ import annotations

from collections import Counter

from ..biomarker_series import BiomarkerProjectionError, _marker_key, project_biomarker_series


def _period(readings: list[dict]) -> dict:
    first_val = readings[0]["value"]
    last_val = readings[-1]["value"]
    if first_val == 0:
        return {
            "trend": "indeterminate",
            "first_value": first_val,
            "latest_value": last_val,
            "percent_change": None,
            "first_date": readings[0].get("date", ""),
            "latest_date": readings[-1].get("date", ""),
            "number_of_readings": len(readings),
        }

    pct_change = (last_val - first_val) / first_val * 100
    trend = "stable"
    if pct_change > 25:
        trend = "increasing"
    elif pct_change < -25:
        trend = "decreasing"
    return {
        "trend": trend,
        "first_value": first_val,
        "latest_value": last_val,
        "percent_change": round(pct_change, 1),
        "first_date": readings[0].get("date", ""),
        "latest_date": readings[-1].get("date", ""),
        "number_of_readings": len(readings),
    }


def analyze_biomarker_trends(marker_name: str, profile: dict) -> dict:
    """Compare only one exact server-declared comparable series."""
    try:
        projection = project_biomarker_series(profile)
    except BiomarkerProjectionError:
        return {
            "marker": marker_name,
            "trend": "insufficient_data",
            "readings": [],
            "eligibility": "projection_unavailable",
            "eligibility_explanation": (
                "The complete biomarker record could not be checked safely, so no trend "
                "claim is available."
            ),
        }

    marker_family = _marker_key(marker_name)
    analyte = next(
        (
            item
            for item in projection["analytes"]
            if any(_marker_key(alias) == marker_family for alias in item["observed_aliases"])
        ),
        None,
    )
    if analyte is None:
        return {
            "marker": marker_name,
            "trend": "no_data",
            "readings": [],
            "eligibility": "no_data",
            "eligibility_explanation": "No matching biomarker results are recorded.",
        }

    observations_by_id = {item["id"]: item for item in analyte["observations"]}
    all_readings = [
        {
            "value": item["value"]["numeric_value"]
            if item["value"]["kind"] == "numeric"
            else item["value"]["raw"],
            "unit": item["unit"],
            "date": item["date"]["value"],
            "reference_range": item["reference_range"],
        }
        for item in analyte["observations"]
    ]
    comparable_series = [item for item in analyte["series"] if item["comparable"]]
    if not comparable_series:
        observed_units = sorted(
            {
                str(reading["unit"]).strip()
                for reading in all_readings
                if reading.get("unit") not in {None, ""}
            }
        )
        missing = [
            requirement["label"]
            for requirement in analyte["chart_diagnostics"]["requirements"]
            if requirement["missing_count"]
        ]
        if missing:
            reason = "results are missing " + ", ".join(missing)
        else:
            reason = (
                "fewer than two results have the same recorded unit, date type, specimen, "
                "assay or method, and reference range"
            )
        non_numeric = all(
            not isinstance(reading.get("value"), int | float) for reading in all_readings
        )
        trend = (
            "single_reading"
            if len(all_readings) == 1
            else "non_numeric"
            if non_numeric
            else "insufficient_data"
        )
        result = {
            "marker": marker_name,
            "trend": trend,
            "readings": [],
            "recorded_observation_count": len(all_readings),
            "eligibility": "no_comparable_series",
            "eligibility_explanation": f"No trend claim is available because {reason}.",
            "chart_diagnostics": analyte["chart_diagnostics"],
            "unit_compatibility": {
                "compatible": False,
                "units": observed_units,
                "missing_count": sum(reading.get("unit") in {None, ""} for reading in all_readings),
                "conversion_performed": False,
            },
        }
        return result
    if len(comparable_series) > 1:
        return {
            "marker": marker_name,
            "trend": "insufficient_data",
            "readings": [],
            "recorded_observation_count": len(all_readings),
            "eligibility": "multiple_comparable_series",
            "eligibility_explanation": (
                "More than one separately comparable series is recorded; NET/Care does "
                "not combine them into one trend claim."
            ),
            "chart_diagnostics": analyte["chart_diagnostics"],
        }

    series = comparable_series[0]
    readings = [
        {
            "value": observations_by_id[observation_id]["value"]["numeric_value"],
            "unit": observations_by_id[observation_id]["unit"],
            "date": observations_by_id[observation_id]["date"]["value"],
            "reference_range": observations_by_id[observation_id]["reference_range"],
        }
        for observation_id in series["observation_ids"]
    ]
    included_source_row_ids = [
        row_id
        for observation_id in series["observation_ids"]
        for row_id in observations_by_id[observation_id]["source_row_ids"]
    ]
    readings.sort(key=lambda item: item["date"])
    caveats: list[str] = []
    excluded_observation_count = len(analyte["observations"]) - len(readings)
    if excluded_observation_count:
        caveats.append(
            f"{excluded_observation_count} other matching-marker result(s) are not included "
            "because Patient cannot show them in this same comparable series."
        )
    date_counts = Counter(r.get("date", "") for r in readings if r.get("date"))
    duplicate_dates = sorted(date for date, count in date_counts.items() if count > 1)
    if duplicate_dates:
        excluded = sum(date_counts[date] for date in duplicate_dates)
        caveats.append(
            f"{excluded} reading(s) on {len(duplicate_dates)} date(s) with multiple "
            "same-date entries were excluded from trend arithmetic (possible "
            f"data-ingestion artefact): {duplicate_dates}."
        )

    numeric = [r for r in readings if date_counts.get(r.get("date", ""), 0) <= 1]

    result: dict = {
        "marker": marker_name,
        "readings": readings,
        "eligibility": "one_comparable_series",
        "eligibility_explanation": (
            "The values come from one server-declared comparable series with matching "
            "unit, date type, specimen, assay or method, and reference range."
        ),
        "unit_compatibility": {
            "compatible": True,
            "units": [series["unit"]],
            "missing_count": 0,
            "conversion_performed": False,
        },
        "comparison_context": {
            "specimen": series["specimen"],
            "assay": series["assay"],
            "method": series["method"],
            "date_kind": series["date_kind"],
            "reference_range_semantics": series["reference_range_semantics"],
        },
        "excluded_observation_count": excluded_observation_count,
        "included_source_row_ids": included_source_row_ids,
    }
    if len(numeric) < 2:
        result["trend"] = "insufficient_data" if duplicate_dates else "non_numeric"
    else:
        full = _period(numeric)
        latest_three = _period(numeric[-3:]) if len(numeric) >= 2 else None
        result.update(full)
        result["full_period"] = full
        result["latest_3"] = latest_three
        result["trend_reversal"] = bool(
            latest_three
            and full["trend"] in {"increasing", "decreasing"}
            and latest_three["trend"] in {"increasing", "decreasing"}
            and full["trend"] != latest_three["trend"]
        )
        if full["percent_change"] is None:
            caveats.append(
                "The full-period baseline is zero, so percent change and direction "
                "cannot be calculated."
            )
        if latest_three and latest_three["percent_change"] is None:
            caveats.append(
                "The latest-three baseline is zero, so its percent change and direction "
                "cannot be calculated."
            )
        if result["trend_reversal"]:
            caveats.append(
                "The latest-three direction reverses the full-period direction; review "
                "both windows rather than relying on one summary."
            )
    result["arithmetic_excluded_count"] = len(readings) - len(numeric)

    if caveats:
        result["data_quality_caveats"] = caveats
    return result
