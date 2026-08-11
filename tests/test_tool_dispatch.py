"""execute_tool: dispatch + side effects on the profile.

Network calls (PubMed, ClinicalTrials.gov) are intercepted with the
`responses` library to assert behaviour without external dependencies.
"""

from __future__ import annotations

import json

import pytest
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


def test_feed_derived_alert_is_source_scoped_and_uses_screening_language(agent, empty_profile):
    result = agent.execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": "Patient is eligible and best matched for PRRT trial",
            "action_required": "Confirm eligibility",
        },
        empty_profile,
        source_document_id="doc_" + "a" * 32,
        source_job_id="feed-job",
    )

    alert = empty_profile["alerts"][0]
    assert result["status"] == "alert_flagged"
    assert alert["source_document_id"] == "doc_" + "a" * 32
    assert alert["source_job_id"] == "feed-job"
    assert alert["source_dependency_active"] is True
    assert alert["dependency_kind"] == "source"
    assert "eligible" not in alert["message"].lower()
    assert "best match" not in alert["message"].lower()
    assert "eligibility" not in alert["action_required"].lower()
    assert "must review the complete criteria and enrollment status" in alert["message"].lower()


def test_best_match_variant_is_also_softened(agent, empty_profile):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "medium",
            "message": "Patient is the best match for PRRT",
        },
        empty_profile,
    )

    assert "best match" not in empty_profile["alerts"][0]["message"].lower()
    assert "must review the complete criteria" in empty_profile["alerts"][0]["message"].lower()


def test_qualification_and_ideal_match_variants_are_softened(agent, empty_profile):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "medium",
            "message": "Patient is qualified as the ideal match for PRRT trial",
        },
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert "qualified" not in message
    assert "ideal match" not in message
    assert "must review the complete criteria" in message


@pytest.mark.parametrize(
    "claim",
    [
        "Patient is one of the best matches for PRRT",
        "Patient is perfectly matched for PRRT",
        "Trial qualifications confirmed",
    ],
)
def test_additional_definitive_fit_variants_are_softened(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "medium", "message": claim},
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert "best match" not in message
    assert "perfectly matched" not in message
    assert "qualifications" not in message
    assert "must review the complete criteria" in message


def test_inclusion_and_enrollment_assertion_is_replaced_not_prefixed(agent, empty_profile):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": "Patient meets all inclusion criteria and should enroll now",
            "action_required": "Enroll immediately because all criteria are met",
        },
        empty_profile,
    )

    alert = empty_profile["alerts"][0]
    for value in (alert["message"], alert["action_required"]):
        lowered = value.lower()
        assert "meets all inclusion criteria" not in lowered
        assert "enroll now" not in lowered
        assert "enroll immediately" not in lowered
        assert "must review the complete criteria and enrollment status" in lowered


@pytest.mark.parametrize(
    "claim",
    [
        "Patient should be included in this trial now",
        "Patient satisfies all inclusion requirements",
    ],
)
def test_inclusion_verb_and_requirement_claims_are_replaced(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": claim,
            "action_required": claim,
        },
        empty_profile,
    )

    for value in (
        empty_profile["alerts"][0]["message"],
        empty_profile["alerts"][0]["action_required"],
    ):
        assert claim.lower() not in value.lower()
        assert "must review the complete criteria" in value.lower()


@pytest.mark.parametrize(
    "claim",
    [
        "Patient is not eligible because prior therapy excludes enrollment",
        "Do not enroll because the patient fails inclusion criteria",
    ],
)
def test_negative_screening_claims_are_not_reversed_to_positive_fit(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": claim, "action_required": claim},
        empty_profile,
    )

    for value in (
        empty_profile["alerts"][0]["message"],
        empty_profile["alerts"][0]["action_required"],
    ):
        lowered = value.lower()
        assert "potential research or treatment fit" not in lowered
        assert "potential exclusion or non-fit" not in lowered
        assert "screening information identified" in lowered
        assert "must review the complete criteria" in lowered


@pytest.mark.parametrize(
    "claim",
    [
        "Patient is ineligible for this trial",
        "Patient is excluded because of prior therapy",
    ],
)
def test_standalone_exclusion_claims_are_bounded(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": claim},
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert claim.lower() not in message
    assert "screening information identified" in message


def test_no_exclusion_criteria_does_not_invert_affirmative_fit(agent, empty_profile):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "medium",
            "message": "Patient is eligible and has no exclusion criteria",
        },
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert "screening information identified" in message
    assert "potential exclusion or non-fit" not in message


@pytest.mark.parametrize(
    "instruction",
    [
        "Hold PRRT cycle",
        "Start 120 mg lanreotide now",
        "Stop everolimus treatment",
        "Pause therapy",
        "Resume octreotide",
        "Switch treatment to sunitinib",
        "Increase lanreotide dose",
        "Decrease medication dose",
        "Stop chemotherapy now",
        "Increase capecitabine",
        "Discontinue everolimus immediately",
        "Withhold the next PRRT dose",
        "Skip the next lanreotide injection",
        "Administer 120 mg lanreotide",
        "Recommendation: stop everolimus immediately",
        "The patient needs to stop everolimus now",
        "We recommend stopping lanreotide and starting sunitinib",
        "Plan is to pause PRRT",
        "Plan: stop everolimus",
        "Starting everolimus now",
        "Titrating lanreotide upward",
        "Redosing PRRT",
        "Reduce everolimus dose now",
        "Restart lanreotide tomorrow",
        "Continue taking everolimus",
        "Renal decline: hold everolimus",
        "Initiate sunitinib",
        "Escalate everolimus dose",
        "De-escalate lanreotide",
        "Everolimus should be held now",
        "Lanreotide must be stopped",
        "Advise stopping everolimus immediately",
        "Renal decline - hold everolimus",
    ],
)
def test_treatment_imperatives_are_replaced_wholesale(agent, empty_profile, instruction):
    agent.execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": instruction,
            "action_required": instruction,
        },
        empty_profile,
    )

    for value in (
        empty_profile["alerts"][0]["message"],
        empty_profile["alerts"][0]["action_required"],
    ):
        assert instruction.lower() not in value.lower()
        assert "contact the treating team" in value.lower()
        assert "confirm before any treatment change" in value.lower()


def test_factual_past_treatment_alert_is_not_rewritten(agent, empty_profile):
    for factual in (
        "Lanreotide was stopped on 2026-07-01 because of intolerance",
        "Lanreotide dose was increased during the prior visit",
        "Everolimus was discontinued during the prior visit",
        "The prior PRRT dose was withheld",
        "Start of lanreotide was delayed on 2026-07-01",
        "Hold on everolimus was discontinued at the prior visit",
        "The plan to stop everolimus was discontinued last week",
        "Starting everolimus was postponed",
    ):
        profile = {**empty_profile, "alerts": []}
        agent.execute_tool(
            "flag_alert",
            {"priority": "medium", "message": factual},
            profile,
        )
        assert profile["alerts"][0]["message"] == factual


@pytest.mark.parametrize(
    "instruction",
    [
        "Start sunitinib now; the prior plan to stop everolimus was cancelled.",
        "The plan to stop everolimus was cancelled last week. Start sunitinib now.",
        "The plan to stop everolimus was cancelled last week, but start sunitinib now.",
    ],
)
def test_cancelled_history_clause_does_not_exempt_live_directive(agent, empty_profile, instruction):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": instruction},
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert instruction.lower() not in message
    assert "contact the treating team" in message


@pytest.mark.parametrize(
    "claim",
    [
        "Enrollment is closed for this trial",
        "Patient is not excluded from enrollment",
    ],
)
def test_ambiguous_screening_polarity_is_neutralized(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "medium", "message": claim},
        empty_profile,
    )

    message = empty_profile["alerts"][0]["message"].lower()
    assert claim.lower() not in message
    assert "screening information identified" in message
    assert "potential research or treatment fit" not in message
    assert "potential exclusion or non-fit" not in message


@pytest.mark.parametrize(
    "claim",
    [
        "Patient is an ideal candidate for PRRT",
        "Patient is a suitable candidate for this trial",
        "Patient matches the trial criteria",
        "Patient is a strong fit for PRRT",
        "Patient is an excellent fit for PRRT",
        "Patient is a compelling match for trial NCT123",
        "Patient is the top match for this trial",
    ],
)
def test_candidate_and_fit_assertions_are_neutralized(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": claim, "action_required": claim},
        empty_profile,
    )
    for value in (
        empty_profile["alerts"][0]["message"],
        empty_profile["alerts"][0]["action_required"],
    ):
        assert claim.casefold() not in value.casefold()
        assert "must review the complete criteria and enrollment status" in value.casefold()


@pytest.mark.parametrize(
    "claim",
    [
        "PRRT is indicated for this patient",
        "The patient is appropriate for PRRT",
        "This patient would benefit from trial NCT12345678",
        "The patient should receive PRRT",
        "Offer trial NCT12345678 now",
    ],
)
def test_indication_benefit_and_offer_assertions_are_neutralized(agent, empty_profile, claim):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": claim, "action_required": claim},
        empty_profile,
    )
    for value in (
        empty_profile["alerts"][0]["message"],
        empty_profile["alerts"][0]["action_required"],
    ):
        assert claim.casefold() not in value.casefold()
        assert "must review the complete criteria and enrollment status" in value.casefold()


@pytest.mark.parametrize(
    "historical",
    [
        "PRRT was indicated in the 2024 treatment plan",
        "The patient was considered appropriate for PRRT in 2023",
        "A prior note said the patient would benefit from trial review",
    ],
)
def test_historical_screening_assertions_remain_factual(agent, empty_profile, historical):
    agent.execute_tool(
        "flag_alert",
        {"priority": "medium", "message": historical},
        empty_profile,
    )
    assert empty_profile["alerts"][0]["message"] == historical


@pytest.mark.parametrize(
    "mixed",
    [
        (
            "The patient was considered appropriate for PRRT in 2023. "
            "The patient is appropriate for PRRT now."
        ),
        "Patient was considered suitable previously. Patient is appropriate for PRRT now.",
        (
            "Prior note said benefit from PRRT was seen; patient is appropriate "
            "for the trial and should receive PRRT."
        ),
        ("The prior plan recorded stable disease and the patient is now " "indicated for PRRT"),
        ("A prior note said benefit from PRRT was seen and the patient " "should receive PRRT"),
    ],
)
def test_historical_clause_does_not_exempt_live_screening_assertion(agent, empty_profile, mixed):
    agent.execute_tool(
        "flag_alert",
        {"priority": "high", "message": mixed},
        empty_profile,
    )
    message = empty_profile["alerts"][0]["message"].lower()
    assert "screening information identified" in message
    assert "appropriate for prrt now" not in message
    assert "should receive prrt" not in message


@pytest.mark.parametrize(
    "unsafe",
    [
        "Renal function is worsening and hold PRRT now",
        "It is recommended that everolimus be stopped immediately",
        "The patient should receive Lutathera",
        "Lutetium-177 dotatate is indicated for this patient",
        "Consider reducing everolimus and restart lanreotide",
        "The plan is to initiate sunitinib",
        "Everolimus needs to be held",
        "The patient is suitable for 177Lu-octreotate",
        "It is recommended that everolimus and octreotide be stopped",
        "Recommend PRRT and octreotide be discontinued now",
        "It is advised that PRRT and octreotide be held",
        "Consider that everolimus and sunitinib be stopped",
        "Plan is that lanreotide and everolimus be switched",
        "Patient needs everolimus stopped",
        "Patient needs PRRT held",
        "Lu-177 dotatate is recommended",
        "Octreotide was stopped and everolimus should be started",
        "Lanreotide was discontinued and sunitinib should be started",
        "PRRT was administered and everolimus must be held",
        "Capecitabine was reduced and octreotide should be increased",
        "Everolimus was held and lanreotide should be resumed",
        "Recommendation to start sunitinib was withdrawn and everolimus should be stopped",
        "Advice to hold PRRT was cancelled and recommend restarting lanreotide",
    ],
)
@pytest.mark.parametrize("field", ["message", "action_required"])
def test_generated_alert_containment_covers_passive_alias_and_conjunction_variants(
    agent, empty_profile, unsafe, field
):
    inputs = {"priority": "high", "message": "Renal finding"}
    inputs[field] = unsafe
    agent.execute_tool("flag_alert", inputs, empty_profile)

    persisted = empty_profile["alerts"][0][field].lower()
    assert unsafe.lower() != persisted
    assert (
        "confirm before any treatment change" in persisted
        or "must review the complete criteria" in persisted
    )


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
    assert all(
        paper["research_record_id"].startswith("research_paper_")
        for paper in empty_profile["literature_watched"]
    )
    assert len({paper["research_record_id"] for paper in empty_profile["literature_watched"]}) == 2

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
    assert saved["research_record_id"].startswith("research_trial_")
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
