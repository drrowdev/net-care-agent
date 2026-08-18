from __future__ import annotations

import copy
import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


def _row(row_id: str, date: str, value=10, **overrides):
    row = {
        "id": row_id,
        "marker": "CgA",
        "value": value,
        "unit": "ng/mL",
        "date": date,
        "date_precision": "day",
        "date_kind": "collection",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
        "reference_range": "0-100",
        "flag": None,
        "flag_authority": "unknown",
        "specimen": "Plasma",
        "assay": "Assay X",
        "method": None,
        "evidence_status": "missing",
    }
    row.update(overrides)
    return row


def _project(agent, rows, **profile_overrides):
    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    profile["profile_revision"] = profile_overrides.pop("profile_revision", 3)
    profile["workflow_revision"] = profile_overrides.pop("workflow_revision", 4)
    profile["biomarkers"] = rows
    profile.update(profile_overrides)
    return agent.project_biomarker_series(profile)


def test_groups_boundary_exact_aliases_and_builds_comparable_series(agent):
    projection = _project(
        agent,
        [
            _row("one", "2026-01-01", marker="CgA", value=10),
            _row("two", "2026-02-01", marker="S-CgA", value=20),
            _row("three", "2026-03-01", marker="P-CgA", value=30),
            _row("four", "2026-04-01", marker="Chromogranin A", value=40),
        ],
    )

    assert projection["profile_revision"] == 3
    assert projection["workflow_revision"] == 4
    assert projection["source_row_count"] == 4
    assert len(projection["analytes"]) == 1
    analyte = projection["analytes"][0]
    assert analyte["display_name"] == "Chromogranin A"
    assert analyte["observed_aliases"] == ["CgA", "Chromogranin A", "P-CgA", "S-CgA"]
    assert analyte["series"][0]["comparable"] is True
    assert [item["value"]["numeric_value"] for item in analyte["observations"]] == [10, 20, 30, 40]


def test_analyte_diagnostics_preserve_missing_dimensions_before_singleton_notes(agent):
    projection = _project(
        agent,
        [
            _row(
                "one",
                "2026-01-01",
                date_kind="clinical_unspecified",
                specimen=None,
                assay=None,
            ),
            _row(
                "two",
                "2026-02-01",
                date_kind="clinical_unspecified",
                specimen=None,
                assay=None,
            ),
        ],
    )

    diagnostics = projection["analytes"][0]["chart_diagnostics"]
    missing = {item["code"]: item["missing_count"] for item in diagnostics["requirements"]}
    assert missing["exact_date_kind"] == 2
    assert missing["specimen"] == 2
    assert missing["assay_or_method"] == 2
    assert diagnostics["comparable_series_count"] == 0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Chromogranin A", "pancreastatin"),
        ("glucose", "HbA1c"),
        ("AST", "ALT"),
    ],
)
def test_does_not_merge_distinct_markers(agent, left, right):
    projection = _project(
        agent,
        [
            _row("one", "2026-01-01", marker=left),
            _row("two", "2026-02-01", marker=right),
        ],
    )
    assert len(projection["analytes"]) == 2


def test_grouping_does_not_compare_5hiaa_specimens_or_unknown_context(agent):
    projection = _project(
        agent,
        [
            _row("urine", "2026-01-01", marker="5-HIAA", specimen="Urine"),
            _row(
                "plasma",
                "2026-02-01",
                marker="5-hydroxyindoleacetic acid",
                specimen="Plasma",
            ),
            _row("unknown", "2026-03-01", marker="5-HIAA", specimen=None),
        ],
    )
    analyte = projection["analytes"][0]
    assert len(projection["analytes"]) == 1
    assert len(analyte["series"]) == 3
    assert not any(series["comparable"] for series in analyte["series"])
    unknown = next(item for item in analyte["observations"] if "unknown" in item["source_row_ids"])
    assert "Specimen is not explicitly recorded." in unknown["comparability_notes"]


def test_unknown_assay_method_is_never_comparable(agent):
    projection = _project(
        agent,
        [
            _row("one", "2026-01-01", assay=None, method=None),
            _row("two", "2026-02-01", assay=None, method=None),
        ],
    )
    analyte = projection["analytes"][0]
    assert not any(series["comparable"] for series in analyte["series"])
    assert all(
        "Assay or method is not explicitly recorded." in item["comparability_notes"]
        for item in analyte["observations"]
    )


def test_unit_range_and_date_kind_boundaries_split_without_conversion(agent):
    projection = _project(
        agent,
        [
            _row("base", "2026-01-01"),
            _row("unit", "2026-02-01", unit="µg/L"),
            _row("range", "2026-03-01", reference_range="0-90"),
            _row("result", "2026-04-01", date_kind="result"),
        ],
    )
    analyte = projection["analytes"][0]
    assert len(analyte["series"]) == 4
    assert not any(series["comparable"] for series in analyte["series"])
    assert {item["unit"] for item in analyte["observations"]} == {"ng/mL", "µg/L"}


def test_unit_case_is_preserved_for_comparability(agent):
    projection = _project(
        agent,
        [
            _row("molar", "2026-01-01", unit="mM"),
            _row("length", "2026-02-01", unit="mm"),
        ],
    )
    analyte = projection["analytes"][0]
    assert len(analyte["series"]) == 2
    assert not any(series["comparable"] for series in analyte["series"])


def test_partial_and_invalid_dates_remain_visible_outside_chronology(agent):
    projection = _project(
        agent,
        [
            _row("exact", "2026-01-01"),
            _row("partial", "2026-02", date_precision="month"),
            _row("invalid", "not-a-date", date_precision="unknown", date_kind="unknown"),
        ],
    )
    observations = projection["analytes"][0]["observations"]
    assert [item["source_row_ids"][0] for item in observations] == ["exact", "partial", "invalid"]
    assert observations[1]["date"]["precision"] == "month"
    assert observations[2]["date"] == {
        "value": "not-a-date",
        "precision": "unknown",
        "kind": "unknown",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }
    assert observations[1]["comparable"] is False


@pytest.mark.parametrize("value", ["<5", "> 8", "4-7", "positive", "negative", "trace"])
def test_qualifiers_ranges_and_text_are_never_comparable(agent, value):
    projection = _project(agent, [_row("one", "2026-01-01", value=value)])
    observation = projection["analytes"][0]["observations"][0]
    assert observation["value"]["raw"] == value
    assert observation["value"]["kind"] != "numeric"
    assert observation["value"]["numeric_value"] is None
    assert observation["report_range_comparison"] is None
    assert observation["comparable"] is False


@pytest.mark.parametrize(
    ("value", "reference_range", "expected"),
    [
        (5, "0-10", "within"),
        (11, "0-10", "above"),
        (-1, "0-10", "below"),
        (99, "<100", "within"),
        (100, "<100", "above"),
        (5, ">=5", "within"),
        (4, ">=5", "below"),
    ],
)
def test_range_comparison_is_observation_specific(agent, value, reference_range, expected):
    projection = _project(
        agent,
        [_row("one", "2026-01-01", value=value, reference_range=reference_range, flag="high")],
    )
    observation = projection["analytes"][0]["observations"][0]
    assert observation["reported_flag"] == "high"
    assert observation["reported_flag_authority"] == "unknown"
    assert observation["report_range_comparison"] == expected
    assert observation["report_range_label"] == "Compared with the report's reference range"


def test_same_source_exact_duplicates_collapse_without_losing_authority(agent):
    rows = [
        _row("one", "2026-01-01", source_document_id="doc_same"),
        _row("two", "2026-01-01", source_document_id="doc_same"),
    ]
    projection = _project(agent, rows)
    observation = projection["analytes"][0]["observations"][0]
    assert projection["source_row_count"] == 2
    assert projection["observation_count"] == 1
    assert observation["duplicate_count"] == 2
    assert observation["source_row_ids"] == ["one", "two"]
    assert len(observation["provenance"]["evidence"]) == 2


def test_unlinked_duplicate_rows_never_collapse(agent):
    projection = _project(
        agent,
        [
            _row("one", "2026-01-01"),
            _row("two", "2026-01-01"),
        ],
    )
    assert projection["source_row_count"] == projection["observation_count"] == 2


def test_cross_source_duplicates_never_collapse(agent):
    projection = _project(
        agent,
        [
            _row("one", "2026-01-01", source_document_id="doc_one"),
            _row("two", "2026-01-01", source_document_id="doc_two"),
        ],
    )
    assert projection["source_row_count"] == projection["observation_count"] == 2


def test_projection_tokens_bind_rows_sources_receipts_and_both_revisions(agent):
    base = _project(agent, [_row("one", "2026-01-01")])
    changed_unit = _project(agent, [_row("one", "2026-01-01", unit="µg/L")])
    changed_profile = _project(agent, [_row("one", "2026-01-01")], profile_revision=5)
    changed_workflow = _project(agent, [_row("one", "2026-01-01")], workflow_revision=5)
    assert (
        len(
            {
                base["projection_token"],
                changed_unit["projection_token"],
                changed_profile["projection_token"],
                changed_workflow["projection_token"],
            }
        )
        == 4
    )


def test_projection_order_and_token_do_not_depend_on_profile_list_order(agent):
    rows = [
        _row("one", "2026-01-01"),
        _row("two", "2026-02-01"),
    ]
    forward = _project(agent, copy.deepcopy(rows))
    reverse = _project(agent, list(reversed(copy.deepcopy(rows))))
    assert reverse == forward


def test_source_metadata_and_evidence_status_change_projection_token(agent, empty_profile):
    source = agent.preserve_source_document("CgA 42")
    row = _row(
        "one",
        "2026-01-01",
        source_document_id=source["id"],
        evidence_status="missing",
    )
    profile = copy.deepcopy(empty_profile)
    profile["biomarkers"] = [row]
    profile["source_documents"] = [source]
    initial = agent.project_biomarker_series(profile)

    profile["source_documents"][0]["media_type"] = "application/pdf"
    source_changed = agent.project_biomarker_series(profile)
    profile["biomarkers"][0]["evidence_status"] = "invalid"
    evidence_changed = agent.project_biomarker_series(profile)

    assert (
        len(
            {
                initial["projection_token"],
                source_changed["projection_token"],
                evidence_changed["projection_token"],
            }
        )
        == 3
    )


def test_intake_correction_and_undo_revoke_projection_authority(agent, empty_profile):
    quote = "Plasma CgA by Assay X: 42 ng/mL (0-100) on 2026-01-01."
    payload = {
        "document_type": "lab_result",
        "date": "2026-01-01",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 42,
                "unit": "ng/mL",
                "date": "2026-01-01",
                "date_kind": "collection",
                "reference_range": "0-100",
                "specimen": "Plasma",
                "assay": "Assay X",
                "source_quote": quote,
            }
        ],
    }
    before = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, extracted = agent.run_intake(quote, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed", text=quote)
    initial = agent.project_biomarker_series(profile)
    receipt = agent.public_receipt(profile, "feed")
    change = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    agent.correct_change(
        profile,
        "feed",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
        replacement={"value": 43},
    )
    corrected = agent.project_biomarker_series(profile)
    observation = corrected["analytes"][0]["observations"][0]
    assert corrected["projection_token"] != initial["projection_token"]
    assert observation["provenance"]["status"] == "caregiver_corrected_unverified"
    assert observation["provenance"]["label"] == "Caregiver-corrected · unverified"

    corrected_receipt = agent.public_receipt(profile, "feed")
    agent.undo_import(
        profile,
        "feed",
        receipt_revision=corrected_receipt["receipt_revision"],
        undo_token=corrected_receipt["undo_token"],
    )
    undone = agent.project_biomarker_series(profile)
    assert undone["source_row_count"] == 0
    assert undone["analytes"] == []


def test_corrected_row_does_not_invalidate_verified_sibling_projection(agent, empty_profile):
    quote = "CgA 42 ng/mL and NSE 12 ng/mL."
    payload = {
        "document_type": "lab_result",
        "date": "2026-01-01",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 42,
                "unit": "ng/mL",
                "source_quote": "CgA 42 ng/mL",
            },
            {
                "marker": "NSE",
                "value": 12,
                "unit": "ng/mL",
                "source_quote": "NSE 12 ng/mL",
            },
        ],
    }
    before = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, extracted = agent.run_intake(quote, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed", text=quote)
    receipt = agent.public_receipt(profile, "feed")
    cga = next(item for item in receipt["changes"] if item["label"] == "CgA")
    agent.correct_change(
        profile,
        "feed",
        cga["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=cga["target_token"],
        replacement={"value": 43},
    )

    projection = agent.project_biomarker_series(profile)
    by_name = {item["display_name"]: item for item in projection["analytes"]}
    assert by_name["Chromogranin A"]["observations"][0]["provenance"]["status"] == (
        "caregiver_corrected_unverified"
    )
    assert by_name["NSE"]["observations"][0]["provenance"]["status"] == "source_verified"


def test_verified_evidence_returns_safe_links_and_rejects_tampering(agent, empty_profile):
    text = "CgA 42 ng/mL"
    source = agent.preserve_source_document(text)
    anchored = agent.anchor_source_quote(text, text)
    row = _row(
        "one",
        "2026-01-01",
        value=42,
        source_document_id=source["id"],
        **anchored,
    )
    profile = copy.deepcopy(empty_profile)
    profile["biomarkers"] = [row]
    profile["source_documents"] = [source]

    projection = agent.project_biomarker_series(profile)
    evidence = projection["analytes"][0]["observations"][0]["provenance"]["evidence"][0]
    assert evidence["status"] == "verified"
    assert evidence["id"].startswith("bmev_")
    assert evidence["evidence_url"].startswith(f"/api/evidence/{source['id']}?")
    assert "evidence_start" not in json.dumps(projection)
    assert "source_quote" not in json.dumps(projection)
    assert '"path"' not in json.dumps(projection)

    (agent.DATA_DIR / source["text"]["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(agent.BiomarkerProjectionError, match="source authority"):
        agent.project_biomarker_series(profile)


def test_valid_incomplete_fact_is_visible_but_structural_failures_abort(agent):
    incomplete = _row(
        "one",
        None,
        marker=None,
        unit=None,
        reference_range=None,
        specimen=None,
        assay=None,
    )
    projection = _project(agent, [incomplete])
    observation = projection["analytes"][0]["observations"][0]
    assert projection["analytes"][0]["display_name"] == "Unclassified"
    assert observation["comparable"] is False

    with pytest.raises(agent.BiomarkerProjectionError):
        _project(agent, [{**incomplete, "id": "duplicate"}, {**incomplete, "id": "duplicate"}])
    with pytest.raises(agent.BiomarkerProjectionError):
        _project(agent, [_row("nested", "2026-01-01", value={"unsafe": 1})])
    with pytest.raises(agent.BiomarkerProjectionError):
        _project(agent, [_row("nan", "2026-01-01", value=float("nan"))])
    with pytest.raises(agent.BiomarkerProjectionError):
        _project(agent, ["not-a-row"])
    with pytest.raises(agent.BiomarkerProjectionError):
        _project(agent, [_row("one", "2026-01-01")], profile_revision="bad")


def test_projection_row_limit_fails_without_partial_payload(agent):
    from agent.biomarker_series import MAX_BIOMARKER_ROWS

    rows = [
        _row(f"row-{index}", "2026-01-01", marker=f"Marker {index}")
        for index in range(MAX_BIOMARKER_ROWS + 1)
    ]
    with pytest.raises(agent.BiomarkerProjectionError) as exc:
        _project(agent, rows)
    assert exc.value.code == "biomarker_projection_too_large"


@pytest.mark.parametrize(
    "profile_change",
    [
        lambda profile: profile["source_documents"][0].update(source="bad"),
        lambda profile: profile["document_imports"][0]["changes"][0].update(target="bad"),
    ],
)
def test_malformed_nested_source_authority_is_bounded(agent, empty_profile, profile_change):
    quote = "CgA 42 ng/mL"
    payload = {
        "document_type": "lab_result",
        "date": "2026-01-01",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 42,
                "unit": "ng/mL",
                "source_quote": quote,
            }
        ],
    }
    before = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, extracted = agent.run_intake(quote, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed", text=quote)
    profile_change(profile)

    with pytest.raises(agent.BiomarkerProjectionError) as exc:
        agent.project_biomarker_series(profile)
    assert exc.value.code == "biomarker_projection_invalid"


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def test_biomarker_endpoint_is_no_store_complete_and_read_only(app_client, agent):
    _, client = app_client
    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    profile["profile_revision"] = 7
    profile["workflow_revision"] = 8
    profile["biomarkers"] = [_row("one", "2026-01-01")]
    agent.save_profile(profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()

    response = client.get("/api/patient/biomarker-series")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.get_json()["profile_revision"] == 7
    assert response.get_json()["workflow_revision"] == 8
    assert response.get_json()["source_row_count"] == 1
    assert agent.PROFILE_PATH.read_bytes() == before


def test_biomarker_endpoint_maps_projection_failures_to_bounded_422(app_client, monkeypatch):
    app_module, client = app_client
    malformed = copy.deepcopy(app_module.agent.DEFAULT_PROFILE)
    malformed["biomarkers"] = [{"id": "same"}, {"id": "same"}]
    monkeypatch.setattr(app_module.agent, "load_profile", lambda: malformed)

    response = client.get("/api/patient/biomarker-series")

    assert response.status_code == 422
    assert response.get_json() == {
        "code": "biomarker_projection_invalid",
        "error": "Biomarker identity is missing or inconsistent.",
    }


def test_biomarker_endpoint_requires_hosted_identity(app_client, monkeypatch):
    _, client = app_client
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    response = client.get("/api/patient/biomarker-series")
    assert response.status_code == 401


def test_projection_module_has_no_model_network_or_persistence_calls():
    from pathlib import Path

    source = Path("agent/biomarker_series.py").read_text(encoding="utf-8")
    for forbidden in (
        "save_profile",
        "requests.",
        "httpx.",
        "client.messages",
        "run_intake",
        "run_orchestrator",
    ):
        assert forbidden not in source
