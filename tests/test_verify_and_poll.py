"""Tests for deterministic reference verification (P3) and trial polling (P5)."""

from __future__ import annotations

import responses


# ── P3: reference verifier ───────────────────────────────────────────────────
@responses.activate
def test_verify_references_flags_fabricated_pmid(agent):
    # A real PMID resolves; a fabricated one returns an error entry.
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        json={"result": {"40137978": {"uid": "40137978", "title": "Real paper"}}},
    )
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        json={"result": {"99999999": {"error": "cannot get document summary"}}},
    )
    result = agent.verify_references("See PMID: 40137978 and also PMID 99999999.")
    assert "PMID:40137978" in result["verified"]
    assert "PMID:99999999" in result["unverified"]


@responses.activate
def test_verify_references_nct_existence(agent):
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05477576",
        json={"protocolSection": {"identificationModule": {"nctId": "NCT05477576"}}},
    )
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT00000000",
        status=404,
    )
    result = agent.verify_references("Trial NCT05477576 looks relevant, unlike NCT00000000.")
    assert "NCT05477576" in result["verified"]
    assert "NCT00000000" in result["unverified"]


@responses.activate
def test_verify_network_error_is_unavailable_not_unverified(agent):
    responses.add(
        responses.GET,
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        status=500,
    )
    result = agent.verify_references("PMID: 12345678")
    assert "PMID:12345678" in result["unavailable"]
    assert result["unverified"] == []  # an outage must not brand a ref as fake


def test_verification_note_empty_when_all_clean(agent):
    assert (
        agent.verification_note({"verified": ["PMID:1"], "unverified": [], "unavailable": []}) == ""
    )


def test_verification_note_flags_unverified(agent):
    note = agent.verification_note(
        {"verified": [], "unverified": ["PMID:99999999"], "unavailable": []}
    )
    assert "Reference verification" in note
    assert "PMID:99999999" in note


# ── P5: trial status poller ──────────────────────────────────────────────────
def _trial_profile():
    return {
        "trials_tracked": [
            {"nct_id": "NCT05477576", "status": "RECRUITING", "url": "http://x"},
            {"nct_id": "NCT05387603", "status": "RECRUITING"},
        ],
        "alerts": [],
    }


@responses.activate
def test_poll_detects_status_change_and_alerts(agent):
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05477576",
        json={
            "protocolSection": {
                "statusModule": {
                    "overallStatus": "ACTIVE_NOT_RECRUITING",
                    "lastUpdatePostDateStruct": {"date": "2026-06-01"},
                }
            }
        },
    )
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05387603",
        json={"protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}}},
    )
    profile = _trial_profile()
    result = agent.poll_tracked_trials(profile)
    assert result["checked"] == 2
    assert len(result["changed"]) == 1
    assert result["changed"][0]["nct_id"] == "NCT05477576"
    assert profile["trials_tracked"][0]["status"] == "ACTIVE_NOT_RECRUITING"
    assert profile["trials_tracked"][0]["status_history"][0]["from"] == "RECRUITING"
    alerts = [a for a in profile["alerts"] if a.get("source") == "trial_status_poll"]
    assert len(alerts) == 1 and alerts[0]["priority"] == "high"


@responses.activate
def test_poll_network_error_does_not_clobber_status(agent):
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05477576",
        status=503,
    )
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05387603",
        status=503,
    )
    profile = _trial_profile()
    result = agent.poll_tracked_trials(profile)
    assert result["changed"] == []
    assert profile["trials_tracked"][0]["status"] == "RECRUITING"  # unchanged
    assert profile["alerts"] == []


@responses.activate
def test_poll_refreshes_registry_fields_preserves_history_and_alerts_eligibility(agent):
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05477576",
        json={
            "protocolSection": {
                "identificationModule": {"briefTitle": "Updated NET trial title"},
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "lastUpdatePostDateStruct": {"date": "2026-07-09"},
                },
                "designModule": {"phases": ["PHASE1", "PHASE2"]},
                "eligibilityModule": {
                    "eligibilityCriteria": "NET required. Prior PRRT is not allowed."
                },
            }
        },
    )
    responses.add(
        responses.GET,
        "https://clinicaltrials.gov/api/v2/studies/NCT05387603",
        json={"protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}}},
    )
    profile = _trial_profile()
    trial = profile["trials_tracked"][0]
    trial.update(
        {
            "title": "Old title",
            "phase": "PHASE1",
            "phases": ["PHASE1"],
            "eligibility_excerpt": "NET required. Prior PRRT is allowed.",
            "registry_last_update": "2026-01-01",
        }
    )

    result = agent.poll_tracked_trials(profile)

    assert result["changed"][0]["material_eligibility_change"] is True
    assert trial["title"] == "Updated NET trial title"
    assert trial["phase"] == "PHASE1 / PHASE2"
    assert trial["eligibility_excerpt"].endswith("not allowed.")
    assert trial["registry_last_update"] == "2026-07-09"
    history = trial["registry_history"][0]
    assert history["before"]["title"] == "Old title"
    assert history["after"]["title"] == "Updated NET trial title"
    assert history["before"]["eligibility_excerpt"].endswith("is allowed.")
    assert any("material eligibility change" in alert["message"] for alert in profile["alerts"])
