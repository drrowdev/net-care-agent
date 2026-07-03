"""Tests for the deterministic accuracy/robustness guards (arch-review P2/P4/P11)."""

from __future__ import annotations

from tests._llm_fake import llm_text, patch_llm


# ── P4: biomarker same-date trend guard ──────────────────────────────────────
def _prof(readings):
    return {"biomarkers": readings}


def test_same_date_cluster_excluded_from_trend_with_caveat(agent):
    # 8 same-date readings (the 5-HIAA artefact) must NOT yield a real trend.
    readings = [
        {"marker": "5-HIAA", "value": v, "date": "2025-08-14"}
        for v in (34, 40, 47, 33, 60, 29, 44, 51)
    ]
    result = agent.analyze_biomarker_trends("5-HIAA", _prof(readings))
    assert result["trend"] == "insufficient_data"
    assert "data_quality_caveats" in result
    assert "2025-08-14" in result["data_quality_caveats"][0]
    assert "percent_change" not in result  # no spurious slope emitted


def test_mixed_same_date_and_clean_dates(agent):
    readings = [
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 999, "date": "2026-02-01"},
        {"marker": "CgA", "value": 111, "date": "2026-02-01"},  # duplicate date -> excluded
        {"marker": "CgA", "value": 150, "date": "2026-03-01"},
    ]
    result = agent.analyze_biomarker_trends("CgA", _prof(readings))
    # trend computed only from the two clean single-date points (100 -> 150)
    assert result["first_value"] == 100
    assert result["latest_value"] == 150
    assert "data_quality_caveats" in result


def test_clean_series_unaffected_no_caveats(agent):
    readings = [
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 200, "date": "2026-02-01"},
    ]
    result = agent.analyze_biomarker_trends("CgA", _prof(readings))
    assert result["trend"] == "increasing"
    assert "data_quality_caveats" not in result


# ── P2: loud intake failure + repair retry ───────────────────────────────────
def test_intake_repair_retry_recovers(agent, empty_profile):
    calls = {"n": 0}

    def handler(**_):
        calls["n"] += 1
        if calls["n"] == 1:
            return llm_text("not json at all")  # first attempt fails
        return llm_text('{"document_type": "lab_result", "summary": "ok", "biomarkers": []}')

    with patch_llm(agent, handler):
        profile, extracted = agent.run_intake("some lab text", empty_profile)
    assert calls["n"] == 2  # one repair retry happened
    assert extracted.get("extraction_failed") is not True
    assert not [
        a for a in profile.get("alerts", []) if a.get("source") == "intake_extraction_failure"
    ]


def test_intake_double_failure_raises_loud_alert(agent, empty_profile):
    with patch_llm(agent, lambda **_: llm_text("still not json")):
        profile, extracted = agent.run_intake("garbled scan", empty_profile)
    assert extracted["extraction_failed"] is True
    alerts = [a for a in profile["alerts"] if a.get("source") == "intake_extraction_failure"]
    assert len(alerts) == 1
    assert alerts[0]["priority"] == "urgent"
    assert alerts[0]["resolved"] is False


def test_intake_dedups_exact_biomarker_triples(agent, empty_profile):
    payload = '{"document_type": "lab_result", "summary": "s", "biomarkers": [{"marker": "CgA", "value": 120, "unit": "ng/mL"}]}'
    with patch_llm(agent, lambda **_: llm_text(payload)):
        agent.run_intake("doc one", empty_profile)
        # Re-feed the identical document; the CgA reading must not double-log.
        agent.run_intake("doc one", empty_profile)
    cga = [b for b in empty_profile["biomarkers"] if b.get("marker") == "CgA"]
    assert len(cga) == 1


# ── P11: exec_summary brevity retry ──────────────────────────────────────────
def test_exec_summary_retries_once_on_truncation_then_succeeds(agent, empty_profile):
    calls = {"n": 0}

    def handler(**_):
        calls["n"] += 1
        if calls["n"] == 1:
            return llm_text('{"overall_status": "stable"', stop_reason="max_tokens")
        return llm_text('{"overall_status": "stable", "status_confidence": "high"}')

    with patch_llm(agent, handler):
        out = agent.generate_executive_summary(empty_profile)
    assert calls["n"] == 2
    assert out["overall_status"] == "stable"
    assert out["generated_at"] != ""
