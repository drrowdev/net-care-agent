"""Longitudinal biomarker trend computation."""
from __future__ import annotations


def analyze_biomarker_trends(marker_name: str, profile: dict) -> dict:
    readings = [
        b for b in profile.get("biomarkers", [])
        if b.get("marker", "").lower() == marker_name.lower()
    ]
    readings.sort(key=lambda x: x.get("date", ""))

    if len(readings) == 0:
        return {"marker": marker_name, "trend": "no_data", "readings": []}
    if len(readings) == 1:
        return {
            "marker": marker_name, "trend": "single_reading",
            "readings": readings, "latest": readings[0],
        }

    numeric = [
        (r["date"], r["value"]) for r in readings
        if isinstance(r.get("value"), (int, float))
    ]
    if len(numeric) < 2:
        return {"marker": marker_name, "trend": "non_numeric", "readings": readings}

    first_val = numeric[0][1]
    last_val = numeric[-1][1]
    pct_change = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0

    trend = "stable"
    if pct_change > 25:
        trend = "increasing"
    elif pct_change < -25:
        trend = "decreasing"

    return {
        "marker": marker_name,
        "readings": readings,
        "trend": trend,
        "first_value": first_val,
        "latest_value": last_val,
        "percent_change": round(pct_change, 1),
        "latest_date": numeric[-1][0],
        "first_date": numeric[0][0],
        "number_of_readings": len(numeric),
    }
