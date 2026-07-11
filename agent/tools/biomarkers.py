"""Longitudinal biomarker trend computation."""

from __future__ import annotations

from collections import Counter


def _normalise_unit(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


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
    """Compare like-for-like readings without performing unit conversions."""
    readings = [
        b
        for b in profile.get("biomarkers", [])
        if b.get("marker", "").lower() == marker_name.lower()
    ]
    readings.sort(key=lambda x: x.get("date", ""))

    if not readings:
        return {"marker": marker_name, "trend": "no_data", "readings": []}

    caveats: list[str] = []
    date_counts = Counter(r.get("date", "") for r in readings if r.get("date"))
    duplicate_dates = sorted(date for date, count in date_counts.items() if count > 1)
    if duplicate_dates:
        excluded = sum(date_counts[date] for date in duplicate_dates)
        caveats.append(
            f"{excluded} reading(s) on {len(duplicate_dates)} date(s) with multiple "
            "same-date entries were excluded from trend arithmetic (possible "
            f"data-ingestion artefact): {duplicate_dates}."
        )

    numeric = [
        r
        for r in readings
        if isinstance(r.get("value"), int | float) and date_counts.get(r.get("date", ""), 0) <= 1
    ]
    units = [_normalise_unit(r.get("unit")) for r in numeric]
    known_units = sorted({unit for unit in units if unit})
    missing_units = units.count("")
    units_compatible = len(known_units) <= 1 and not (known_units and missing_units)

    if len(known_units) > 1:
        caveats.append(
            "Mixed units were found "
            f"({', '.join(known_units)}); no values were converted or compared."
        )
    elif known_units and missing_units:
        caveats.append(
            f"{missing_units} numeric reading(s) lack units while other readings use "
            f"{known_units[0]}; no values were converted or compared."
        )
    elif not known_units and numeric:
        caveats.append(
            "Units are missing from all numeric readings; trend arithmetic is retained "
            "for legacy compatibility, but unit compatibility cannot be verified."
        )

    ranges = {
        " ".join(str(r.get("reference_range") or "").strip().lower().split())
        for r in readings
        if r.get("reference_range")
    }
    missing_ranges = sum(not r.get("reference_range") for r in readings)
    if len(ranges) > 1:
        caveats.append(
            "Reference ranges differ across readings; trend direction does not establish "
            "whether a value is normal or abnormal."
        )
    elif missing_ranges:
        caveats.append(
            f"Reference range is missing for {missing_ranges} reading(s); trend direction "
            "must not be interpreted as normality."
        )

    result: dict = {
        "marker": marker_name,
        "readings": readings,
        "unit_compatibility": {
            "compatible": units_compatible,
            "units": known_units,
            "missing_count": missing_units,
            "conversion_performed": False,
        },
    }
    if len(readings) == 1:
        result.update({"trend": "single_reading", "latest": readings[0]})
    elif len(numeric) < 2:
        result["trend"] = "insufficient_data" if duplicate_dates else "non_numeric"
    elif not units_compatible:
        result["trend"] = "incompatible_units"
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

    if caveats:
        result["data_quality_caveats"] = caveats
    return result
