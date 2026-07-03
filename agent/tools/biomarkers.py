"""Longitudinal biomarker trend computation."""

from __future__ import annotations

from collections import Counter


def analyze_biomarker_trends(marker_name: str, profile: dict) -> dict:
    readings = [
        b
        for b in profile.get("biomarkers", [])
        if b.get("marker", "").lower() == marker_name.lower()
    ]
    readings.sort(key=lambda x: x.get("date", ""))

    if len(readings) == 0:
        return {"marker": marker_name, "trend": "no_data", "readings": []}

    # Same-date guard. Multiple readings sharing one date cannot form a real
    # longitudinal trend and have historically produced spurious slopes (e.g. 8
    # same-date 5-HIAA readings yielded a bogus +38%). Exclude same-date clusters
    # from the slope arithmetic, but NEVER delete them — emit a caveat so the
    # artefact is visible and resolvable rather than silently trusted or silently
    # dropped (the latter could hide a real signal).
    date_counts = Counter(r.get("date", "") for r in readings if r.get("date"))
    dup_dates = sorted(d for d, c in date_counts.items() if c > 1)
    caveats = []
    if dup_dates:
        n_excluded = sum(date_counts[d] for d in dup_dates)
        caveats.append(
            f"{n_excluded} reading(s) on {len(dup_dates)} date(s) with multiple "
            f"same-date entries were excluded from trend arithmetic (possible "
            f"data-ingestion artefact): {dup_dates}. Resolve these in the record "
            f"before treating any trend as real."
        )

    def _with_caveats(result: dict) -> dict:
        if caveats:
            result["data_quality_caveats"] = caveats
        return result

    if len(readings) == 1:
        return _with_caveats(
            {
                "marker": marker_name,
                "trend": "single_reading",
                "readings": readings,
                "latest": readings[0],
            }
        )

    # Only single-per-date numeric readings feed the slope.
    numeric = [
        (r["date"], r["value"])
        for r in readings
        if isinstance(r.get("value"), int | float) and date_counts.get(r.get("date", ""), 0) == 1
    ]
    if len(numeric) < 2:
        # Too few unambiguous points to compute a trend. If the shortfall is
        # caused by same-date clusters, say so; otherwise it's non-numeric data.
        trend = "insufficient_data" if dup_dates else "non_numeric"
        return _with_caveats({"marker": marker_name, "trend": trend, "readings": readings})

    first_val = numeric[0][1]
    last_val = numeric[-1][1]
    pct_change = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0

    trend = "stable"
    if pct_change > 25:
        trend = "increasing"
    elif pct_change < -25:
        trend = "decreasing"

    return _with_caveats(
        {
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
    )
