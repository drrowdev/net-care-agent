"""execute_tool: dispatch + side effects on the profile.

Network calls (PubMed, ClinicalTrials.gov) are intercepted with the
`responses` library to assert behaviour without external dependencies.
"""

from __future__ import annotations

import json

import responses

# ─── flag_alert ──────────────────────────────────────────────────────────────


def test_flag_alert_appends_to_profile(agent, empty_profile):
    result = agent.execute_tool(
        "flag_alert",
        {
            "priority": "urgent",
            "message": "Renal function declining",
            "action_required": "Hold PRRT cycle",
        },
        empty_profile,
    )
    assert result["status"] == "alert_flagged"
    assert len(empty_profile["alerts"]) == 1
    assert empty_profile["alerts"][0]["priority"] == "urgent"
    assert empty_profile["alerts"][0]["resolved"] is False
    assert empty_profile["alerts"][0]["date"]  # ISO date filled in


# ─── analyze_biomarker_trends ────────────────────────────────────────────────


def test_dispatch_to_biomarker_trends(agent, empty_profile):
    empty_profile["biomarkers"] = [
        {"marker": "CgA", "value": 100, "date": "2026-01-01"},
        {"marker": "CgA", "value": 200, "date": "2026-02-01"},
    ]
    result = agent.execute_tool(
        "analyze_biomarker_trends",
        {"marker_name": "CgA"},
        empty_profile,
    )
    assert result["trend"] == "increasing"


# ─── search_pubmed ───────────────────────────────────────────────────────────


@responses.activate
def test_search_pubmed_filters_irrelevant_and_dedupes(agent, empty_profile, fixtures_dir):
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        json=json.loads((fixtures_dir / "pubmed_search.json").read_text()),
    )
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        json=json.loads((fixtures_dir / "pubmed_summary.json").read_text()),
    )

    result = agent.execute_tool(
        "search_pubmed",
        {"query": "neuroendocrine tumor PRRT", "max_results": 6},
        empty_profile,
    )
    assert "results" in result

    saved_pmids = {p["pmid"] for p in empty_profile["literature_watched"]}
    # Two NET-relevant papers saved, the glioblastoma paper filtered out.
    assert saved_pmids == {"40000001", "40000002"}

    # Re-running with same fixtures should NOT add duplicates.
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        json=json.loads((fixtures_dir / "pubmed_search.json").read_text()),
    )
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        json=json.loads((fixtures_dir / "pubmed_summary.json").read_text()),
    )
    agent.execute_tool(
        "search_pubmed",
        {"query": "neuroendocrine tumor PRRT", "max_results": 6},
        empty_profile,
    )
    assert len(empty_profile["literature_watched"]) == 2  # still 2, no dupes


# ─── search_clinical_trials ──────────────────────────────────────────────────


@responses.activate
def test_search_clinical_trials_filters_unrelated(agent, empty_profile, fixtures_dir):
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies",
        json=json.loads((fixtures_dir / "ctgov_studies.json").read_text()),
    )

    result = agent.execute_tool(
        "search_clinical_trials",
        {"condition": "metastatic neuroendocrine tumor"},
        empty_profile,
    )
    assert "trials" in result

    nct_ids = {t["nct_id"] for t in empty_profile["trials_tracked"]}
    # NET trial saved, melanoma trial filtered out.
    assert nct_ids == {"NCT09000001"}

    saved = empty_profile["trials_tracked"][0]
    assert "Germany" in saved["countries"]
    assert saved["status"] == "RECRUITING"
    assert saved["phase"] == "PHASE1 / PHASE2"
    assert saved["phases"] == ["PHASE1", "PHASE2"]
    assert saved["eligibility_excerpt"].endswith("adequate renal function.")
    assert result["selection_manifest"]["returned_nct_ids"] == [
        "NCT09000001",
        "NCT09000099",
    ]
    assert result["persistence_manifest"]["omitted"] == [
        {"nct_id": "NCT09000099", "reason": "not_net_relevant"}
    ]


@responses.activate
def test_trial_selection_is_deterministic_and_discloses_omissions(agent):
    studies = []
    for number in range(21, 0, -1):
        studies.append(
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": f"NCT{number:08d}",
                        "briefTitle": "Neuroendocrine tumor study",
                    },
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "designModule": {"phases": ["PHASE2"]},
                    "descriptionModule": {"briefSummary": "NET treatment"},
                    "eligibilityModule": {
                        "eligibilityCriteria": "X" * 900 + f"-criterion-{number}"
                    },
                }
            }
        )
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies",
        json={"totalCount": 21, "studies": studies},
    )

    result = agent.search_clinical_trials("neuroendocrine tumor")

    assert len(result["trials"]) == 20
    assert result["trials"][0]["nct_id"] == "NCT00000001"
    assert result["selection_manifest"]["omitted"] == 1
    assert result["selection_manifest"]["omitted_nct_ids"] == ["NCT00000021"]
    assert "not included" in result["omission_notice"]
    assert len(result["trials"][0]["eligibility_excerpt"]) > 900


# ─── unknown tool ────────────────────────────────────────────────────────────


def test_unknown_tool_returns_error(agent, empty_profile):
    result = agent.execute_tool("does_not_exist", {}, empty_profile)
    assert "error" in result


# ─── network failure (PubMed) ────────────────────────────────────────────────


@responses.activate
def test_pubmed_network_error_is_handled(agent, empty_profile):
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        status=500,
    )
    result = agent.execute_tool(
        "search_pubmed",
        {"query": "anything"},
        empty_profile,
    )
    assert "error" in result
    # Profile must NOT be polluted with any saved papers.
    assert empty_profile["literature_watched"] == []
