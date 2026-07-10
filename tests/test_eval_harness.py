"""Deterministic behavioral tests for the extraction evaluation gate; no network."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from Scripts import eval_harness as harness


def _case(text: str = "Lab 2026-01-02: CgA 20 ng/mL (0-10). Start lanreotide.") -> dict:
    quote = "CgA 20 ng/mL (0-10)"
    return {
        "schema_version": harness.SCHEMA_VERSION,
        "id": "unit-case",
        "text": text,
        "expected": {
            "document_type": "lab_result",
            "ki67_update": None,
            "sstr_status_update": None,
            "sstr_score_update": None,
            "biomarkers": [
                {
                    "marker": "CgA",
                    "value": "20",
                    "unit": "ng/mL",
                    "date": "2026-01-02",
                    "reference_range": "0-10",
                    "source_quote": quote,
                    "critical": True,
                }
            ],
            "treatment_changes": [
                {
                    "treatment": "lanreotide",
                    "state": "started",
                    "date": "2026-01-02",
                    "source_quote": "Start lanreotide",
                }
            ],
            "imaging_facts": [],
            "symptoms": [],
            "appointments": [],
            "key_findings": [],
            "critical_events": [],
            "source_quotes": [
                {"field": "biomarkers", "quote": quote},
                {"field": "treatment_changes", "quote": "Start lanreotide"},
            ],
            "must_not_infer": [{"statement": "disease progression", "critical": True}],
        },
        "tags": ["unit"],
    }


def _perfect_actual() -> dict:
    return {
        "document_type": "lab_result",
        "date": "2026-01-02",
        "biomarkers": [
            {
                "marker": "cga",
                "value": 20,
                "unit": "ng/ml",
                "reference_range": "0-10",
                "source_quote": "CgA 20 ng/mL (0-10)",
            }
        ],
        "treatment_changes": ["Start lanreotide"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "Start lanreotide",
            }
        ],
    }


def _permissive_thresholds() -> dict:
    return {key: (0 if key.startswith("min_") else 999) for key in harness.DEFAULT_THRESHOLDS}


def _contract_actual(case: dict) -> dict:
    expected = case["expected"]
    dates = [
        str(item["date"])
        for field in harness.LIST_FIELDS
        for item in expected[field]
        if item.get("date")
    ]
    key_items = [
        {
            "text": item["finding"],
            "quote": item["source_quote"],
        }
        for item in expected["key_findings"]
    ]
    for item in expected["critical_events"]:
        if any(
            harness.normalize_text(item["source_quote"])
            == harness.normalize_text(existing["quote"])
            or harness._expected_label_coverage(
                "critical_events",
                item,
                existing["text"],
            )
            >= 0.8
            for existing in key_items
        ):
            continue
        key_items.append({"text": item["event"], "quote": item["source_quote"]})

    actual: dict = {
        "document_type": expected["document_type"],
        "date": max(dates) if dates else None,
        "biomarkers": [
            {
                key: value
                for key, value in item.items()
                if key in {"marker", "value", "unit", "reference_range", "source_quote"}
            }
            for item in expected["biomarkers"]
        ],
        "treatment_changes": [item["source_quote"] for item in expected["treatment_changes"]],
        "symptoms_reported": [
            {
                "symptom": item["symptom"],
                "note": item["source_quote"],
                "source_quote": item["source_quote"],
            }
            for item in expected["symptoms"]
        ],
        "appointments": [
            {key: item[key] for key in ("date", "description", "type", "source_quote")}
            for item in expected["appointments"]
        ],
        "key_findings": [item["text"] for item in key_items],
        "evidence": [],
    }
    if expected["imaging_facts"]:
        item = expected["imaging_facts"][0]
        actual["imaging_findings"] = {
            "findings": item["finding"],
            "source_quote": item["source_quote"],
        }
    for index, item in enumerate(expected["treatment_changes"]):
        actual["evidence"].append(
            {
                "field": "treatment_changes",
                "item_index": index,
                "source_quote": item["source_quote"],
            }
        )
    for index, item in enumerate(key_items):
        actual["evidence"].append(
            {
                "field": "key_findings",
                "item_index": index,
                "source_quote": item["quote"],
            }
        )
    for field in harness.SCALAR_FIELDS:
        if expected[field] is None:
            continue
        actual[field] = expected[field]
        quote = next(item["quote"] for item in expected["source_quotes"] if item["field"] == field)
        actual["evidence"].append({"field": field, "item_index": None, "source_quote": quote})
    return actual


def test_fragment_cannot_satisfy_detailed_critical_finding():
    expected = {
        "event": "acute segmental pulmonary embolus in right lower lobe",
    }

    assert harness._label_similarity("critical_events", expected, "embolus") < 0.5


def test_negation_in_other_sentence_does_not_hide_prohibited_claim():
    claims = harness._claim_texts("No flushing. Patient thyroid cancer.")

    assert any(
        harness._contains_prohibited_statement(claim, "patient thyroid cancer") for claim in claims
    )


def test_one_key_finding_can_also_satisfy_overlapping_critical_event():
    case = _case("Acute segmental pulmonary embolus in right lower lobe.")
    expected = case["expected"]
    expected["document_type"] = "doctor_note"
    expected["biomarkers"] = []
    expected["treatment_changes"] = []
    expected["key_findings"] = [
        {
            "finding": "acute segmental pulmonary embolus in right lower lobe",
            "date": "2026-01-02",
            "source_quote": case["text"],
        }
    ]
    expected["critical_events"] = [
        {
            "event": "acute segmental pulmonary embolus in right lower lobe",
            "date": "2026-01-02",
            "source_quote": case["text"],
            "critical": True,
        }
    ]
    actual = {
        "document_type": "doctor_note",
        "date": "2026-01-02",
        "key_findings": [case["text"]],
        "evidence": [
            {
                "field": "key_findings",
                "item_index": 0,
                "source_quote": case["text"],
            }
        ],
    }

    score = harness.score_extraction(expected, actual, case["text"], case["id"])

    assert score["fields"]["key_findings"]["recall"] == 1.0
    assert score["critical_events"]["recall"] == 1.0


def test_wrong_appointment_type_does_not_match():
    case = _case("CT scan booked 2026-02-03.")
    expected = case["expected"]
    expected["document_type"] = "appointment_summary"
    expected["biomarkers"] = []
    expected["treatment_changes"] = []
    expected["appointments"] = [
        {
            "date": "2026-02-03",
            "description": "CT scan",
            "type": "scan",
            "source_quote": case["text"],
        }
    ]
    actual = {
        "document_type": "appointment_summary",
        "date": "2026-02-03",
        "appointments": [
            {
                "date": "2026-02-03",
                "description": "CT scan",
                "type": "other",
                "source_quote": case["text"],
            }
        ],
    }

    score = harness.score_extraction(expected, actual, case["text"], case["id"])

    assert score["fields"]["appointments"]["recall"] == 0.0


def test_schema_is_versioned_and_contract_validation_is_loud():
    case = _case()
    assert harness.validate_case(case) is case
    del case["expected"]["appointments"]
    with pytest.raises(harness.ValidationError, match="missing expected keys.*appointments"):
        harness.validate_case(case)

    for document_type in ("laboratory_report", "clinic_note"):
        case = _case()
        case["expected"]["document_type"] = document_type
        with pytest.raises(harness.ValidationError, match="document_type must be one of"):
            harness.validate_case(case)

    case = _case()
    case["expected"]["appointments"] = [
        {
            "date": "2026-02-01",
            "description": "scan",
            "type": "imaging",
            "source_quote": "Lab 2026-01-02",
        }
    ]
    with pytest.raises(harness.ValidationError, match="type must be one of"):
        harness.validate_case(case)


def test_validation_rejects_unknown_version_quote_and_scalar_ranges():
    case = _case()
    case["schema_version"] = "9"
    with pytest.raises(harness.ValidationError, match="unsupported schema"):
        harness.validate_case(case)
    case = _case()
    case["expected"]["source_quotes"][0]["quote"] = "not in source"
    with pytest.raises(harness.ValidationError, match="not in text"):
        harness.validate_case(case)
    for field, value in (
        ("ki67_update", math.nan),
        ("ki67_update", math.inf),
        ("ki67_update", 101),
        ("sstr_score_update", 5),
    ):
        case = _case()
        case["expected"][field] = value
        with pytest.raises(harness.ValidationError):
            harness.validate_case(case)
    case = _case()
    case["expected"]["biomarkers"][0]["unexpected"] = True
    with pytest.raises(harness.ValidationError, match="unknown keys"):
        harness.validate_case(case)
    case = _case()
    case["expected"]["treatment_changes"][0]["state"] = "administered"
    with pytest.raises(harness.ValidationError, match="state must be one of"):
        harness.validate_case(case)


def test_inventory_has_40_contract_aligned_substantive_cases():
    cases = harness.load_cases()
    assert len(cases) >= 40
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["schema_version"] == harness.SCHEMA_VERSION for case in cases)
    assert all(case["expected"]["document_type"] in harness.DOCUMENT_TYPES for case in cases)
    assert all(
        appointment["type"] in harness.APPOINTMENT_TYPES
        for case in cases
        for appointment in case["expected"]["appointments"]
    )
    assert all(
        biomarker["marker"].casefold() not in {"ki-67", "ki67", "mib-1", "mitotic rate"}
        for case in cases
        for biomarker in case["expected"]["biomarkers"]
    )
    assert all(len(case["expected"]["imaging_facts"]) <= 1 for case in cases)
    assert next(c for c in cases if c["id"] == "ki67-pathology")["expected"]["ki67_update"] == 8
    assert (
        next(c for c in cases if c["id"] == "sstr-dotatate-positive")["expected"][
            "sstr_score_update"
        ]
        == 4
    )
    tags = {tag for case in cases for tag in case["tags"]}
    assert {
        "ocr",
        "back-dated",
        "conflicting-units",
        "same-day",
        "recurring-treatment",
        "pathology",
        "ki-67",
        "sstr",
        "progression",
        "stability",
        "renal",
        "hepatic",
        "cbc",
        "appointment",
        "urgent",
        "negation",
        "distractor",
        "ambiguity",
        "must-not-infer",
    } <= tags


def test_all_40_goldens_can_pass_with_contract_shaped_fake_output():
    cases = harness.load_cases()
    by_text = {case["text"]: _contract_actual(case) for case in cases}
    artifact = harness.run_evaluation(
        cases,
        lambda text: copy.deepcopy(by_text[text]),
        runs=1,
        timestamp="2026-01-01T00:00:00+00:00",
    )
    assert artifact["pass"] is True, artifact["failures"]
    assert artifact["aggregate"]["overall_recall"] == 1
    assert artifact["aggregate"]["overall_precision"] == 1
    assert artifact["aggregate"]["source_support"] == 1


def test_private_corpus_must_be_outside_repository(tmp_path):
    inside = harness.ROOT / "eval_cases" / "private"
    with pytest.raises(harness.ValidationError, match="outside"):
        harness.load_cases(inside)
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "case.json").write_text(json.dumps(_case()), encoding="utf-8")
    assert len(harness.load_cases(outside)) == 1


def test_metrics_cover_precision_exact_treatment_scalar_and_support():
    score = harness.score_extraction(
        _case()["expected"], _perfect_actual(), _case()["text"], "unit-case"
    )
    assert score["overall"]["recall"] == 1
    assert score["overall"]["precision"] == 1
    assert score["exact"] == {
        "date": {"correct": 2, "expected": 2, "accuracy": 1},
        "value": {"correct": 1, "expected": 1, "accuracy": 1},
        "unit": {"correct": 1, "expected": 1, "accuracy": 1},
    }
    assert score["treatment_state"]["accuracy"] == 1
    assert score["special_scalars"]["accuracy"] == 1
    assert score["source_support"]["rate"] == 1


def test_wrong_values_and_100_hallucinations_fail_strict_gate():
    actual = _perfect_actual()
    actual["biomarkers"][0].update(value="21", unit="pmol/L")
    actual["date"] = "2026-01-03"
    actual["biomarkers"].extend(
        {
            "marker": f"invented-{index}",
            "value": "99",
            "unit": "ng/mL",
            "source_quote": "CgA 20 ng/mL (0-10)",
        }
        for index in range(100)
    )
    artifact = harness.run_evaluation([_case()], lambda _text: actual, runs=1)
    assert artifact["aggregate"]["unsupported_additions"] == 100
    assert artifact["aggregate"]["overall_precision"] < 0.03
    assert artifact["aggregate"]["date_accuracy"] == 0
    assert artifact["aggregate"]["value_accuracy"] == 0
    assert artifact["aggregate"]["unit_accuracy"] == 0
    assert artifact["pass"] is False
    assert any("unsupported_additions" in failure for failure in artifact["failures"]["worst"])


def test_model_owned_anchored_evidence_is_required_and_fact_specific():
    document = (
        "Lab 2026-01-02: CgA 20 ng/mL (0-10). "
        "Unrelated true sentence: patient feels well. Start lanreotide."
    )
    case = _case(document)
    actual = _perfect_actual()
    actual["biomarkers"][0]["source_quote"] = "patient feels well"
    actual["evidence"][0]["source_quote"] = "patient feels well"
    score = harness.score_extraction(case["expected"], actual, document, case["id"])
    assert score["source_support"]["rate"] == 0

    del actual["biomarkers"][0]["source_quote"]
    actual["evidence"] = []
    score = harness.score_extraction(case["expected"], actual, document, case["id"])
    assert score["source_support"]["rate"] == 0


def test_evidence_quote_must_support_scalar_value_unit_and_state():
    actual = _perfect_actual()
    actual["biomarkers"][0]["source_quote"] = "CgA 20"
    actual["evidence"][0]["source_quote"] = "lanreotide"
    score = harness.score_extraction(_case()["expected"], actual, _case()["text"])
    assert score["source_support"]["rate"] == 0


def test_null_index_evidence_cannot_support_multiple_list_facts():
    actual = _perfect_actual()
    actual["evidence"][0]["item_index"] = None
    score = harness.score_extraction(_case()["expected"], actual, _case()["text"])
    assert score["source_support"] == {"supported": 1, "total": 2, "rate": 0.5}


def test_maximum_quality_matching_pairs_reordered_repeated_labels():
    case = _case("Lab 2026-01-01: CgA 10 ng/mL. Lab 2026-02-01: CgA 20 ng/mL.")
    case["expected"]["treatment_changes"] = []
    case["expected"]["source_quotes"] = []
    case["expected"]["biomarkers"] = [
        {
            "marker": "CgA",
            "value": "10",
            "unit": "ng/mL",
            "date": "2026-01-01",
            "reference_range": None,
            "source_quote": "CgA 10 ng/mL",
        },
        {
            "marker": "CgA",
            "value": "20",
            "unit": "ng/mL",
            "date": "2026-02-01",
            "reference_range": None,
            "source_quote": "CgA 20 ng/mL",
        },
    ]
    actual = {
        "document_type": "lab_result",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 20,
                "unit": "ng/mL",
                "date": "2026-02-01",
                "source_quote": "CgA 20 ng/mL",
            },
            {
                "marker": "CgA",
                "value": 10,
                "unit": "ng/mL",
                "date": "2026-01-01",
                "source_quote": "CgA 10 ng/mL",
            },
        ],
    }
    score = harness.score_extraction(case["expected"], actual, case["text"])
    assert score["fields"]["biomarkers"]["recall"] == 1
    assert all(score["exact"][key]["accuracy"] == 1 for key in ("date", "value", "unit"))


def test_contract_shaped_compound_imaging_and_sstr_score_perfectly():
    cases = {case["id"]: case for case in harness.load_cases()}
    mixed = cases["imaging-mixed-response"]
    finding = mixed["expected"]["imaging_facts"][0]["finding"]
    actual = {
        "document_type": "imaging_report",
        "date": "2026-05-01",
        "imaging_findings": {
            "modality": "CT",
            "findings": finding,
            "impression": "overall mixed response",
            "new_lesions": False,
            "source_quote": finding,
        },
        "key_findings": ["overall mixed response"],
        "evidence": [
            {
                "field": "key_findings",
                "item_index": 0,
                "source_quote": "overall mixed response",
            }
        ],
    }
    score = harness.score_extraction(mixed["expected"], actual, mixed["text"], mixed["id"])
    assert score["fields"]["imaging_facts"]["recall"] == 1
    assert score["fields"]["imaging_facts"]["precision"] == 1
    assert score["source_support"]["rate"] == 1

    sstr = cases["sstr-negative-lesion"]
    actual = _contract_actual(sstr)
    assert isinstance(actual["imaging_findings"], dict)
    score = harness.score_extraction(sstr["expected"], actual, sstr["text"], sstr["id"])
    assert score["overall"]["recall"] == 1
    assert score["special_scalars"]["accuracy"] == 1
    assert score["source_support"]["rate"] == 1


def test_key_findings_partition_preserves_critical_mapping():
    case = _case("Note 2026-01-02: disease stable. Urgent emergency review required.")
    case["expected"]["biomarkers"] = []
    case["expected"]["treatment_changes"] = []
    case["expected"]["source_quotes"] = []
    case["expected"]["key_findings"] = [
        {
            "finding": "disease stable",
            "date": "2026-01-02",
            "source_quote": "disease stable",
        }
    ]
    case["expected"]["critical_events"] = [
        {
            "event": "Urgent emergency review required",
            "date": "2026-01-02",
            "source_quote": "Urgent emergency review required",
            "critical": True,
        }
    ]
    actual = {
        "document_type": "lab_result",
        "date": "2026-01-02",
        "key_findings": ["disease stable", "Urgent emergency review required"],
        "evidence": [
            {"field": "key_findings", "item_index": 0, "source_quote": "disease stable"},
            {
                "field": "key_findings",
                "item_index": 1,
                "source_quote": "Urgent emergency review required",
            },
        ],
    }
    score = harness.score_extraction(case["expected"], actual, case["text"])
    assert score["fields"]["key_findings"]["precision"] == 1
    assert score["fields"]["critical_events"]["precision"] == 1
    assert score["critical"]["unsupported_additions"] == 0
    assert score["source_support"]["rate"] == 1


def test_reordered_repeated_critical_findings_keep_original_evidence_indices():
    case = _case("Note: urgent review 2026-01-01. Follow-up: urgent review 2026-02-01.")
    case["expected"]["biomarkers"] = []
    case["expected"]["treatment_changes"] = []
    case["expected"]["source_quotes"] = []
    case["expected"]["critical_events"] = [
        {
            "event": "urgent review",
            "date": "2026-01-01",
            "source_quote": "urgent review 2026-01-01",
            "critical": True,
        },
        {
            "event": "urgent review",
            "date": "2026-02-01",
            "source_quote": "urgent review 2026-02-01",
            "critical": True,
        },
    ]
    actual = {
        "document_type": "lab_result",
        "key_findings": ["urgent review", "urgent review"],
        "evidence": [
            {
                "field": "key_findings",
                "item_index": 0,
                "source_quote": "urgent review 2026-02-01",
            },
            {
                "field": "key_findings",
                "item_index": 1,
                "source_quote": "urgent review 2026-01-01",
            },
        ],
    }
    score = harness.score_extraction(case["expected"], actual, case["text"])
    assert score["fields"]["critical_events"]["recall"] == 1
    assert score["exact"]["date"]["accuracy"] == 1
    assert score["source_support"]["rate"] == 1


def test_negation_and_treatment_state_accuracy_are_strict():
    expected = _case()["expected"]
    expected["biomarkers"] = []
    expected["treatment_changes"] = []
    expected["symptoms"] = [
        {
            "symptom": "flushing",
            "status": "absent",
            "date": "2026-01-02",
            "source_quote": "denies flushing",
        }
    ]
    text = "Visit 2026-01-02: patient denies flushing."
    absent = harness.score_extraction(
        expected,
        {
            "document_type": "lab_result",
            "date": "2026-01-02",
            "symptoms_reported": [
                {"symptom": "flushing", "note": "denies", "source_quote": "denies flushing"}
            ],
        },
        text,
    )
    present = harness.score_extraction(
        expected,
        {"document_type": "lab_result", "symptoms_reported": ["flushing"]},
        text,
    )
    assert absent["fields"]["symptoms"]["recall"] == 1
    assert present["fields"]["symptoms"]["recall"] == 0

    actual = _perfect_actual()
    actual["treatment_changes"] = ["Stopped lanreotide"]
    actual["evidence"][0]["source_quote"] = "Start lanreotide"
    score = harness.score_extraction(_case()["expected"], actual, _case()["text"])
    assert score["treatment_state"]["accuracy"] == 0


def test_must_not_infer_and_critical_additions_are_gated():
    actual = _perfect_actual()
    actual["key_findings"] = ["disease progression", "critical pulmonary embolus"]
    score = harness.score_extraction(_case()["expected"], actual, _case()["text"], "unit")
    assert score["must_not_infer_violations"] == 1
    assert score["critical"]["unsupported_additions"] >= 1


def test_three_run_worst_semantics_and_all_strict_metrics_are_reported():
    outputs = [_perfect_actual(), {"document_type": "lab_result"}, _perfect_actual()]

    def runner(_text):
        return outputs.pop(0)

    artifact = harness.run_evaluation(
        [_case()],
        runner,
        runs=3,
        timestamp="2026-01-01T00:00:00+00:00",
        thresholds=_permissive_thresholds(),
    )
    assert len(artifact["per_run"]) == 3
    assert artifact["cases"][0]["worst_run"] == 2
    for key in (
        "overall_precision",
        "unsupported_additions",
        "date_accuracy",
        "value_accuracy",
        "unit_accuracy",
        "treatment_state_accuracy",
        "special_scalar_accuracy",
    ):
        assert key in artifact["aggregate"]
        assert key in artifact["worst"]


@pytest.mark.parametrize(
    ("thresholds", "message"),
    [
        ({"min_overall_recall": math.nan}, "finite"),
        ({"min_overall_recall": math.inf}, "finite"),
        ({"min_overall_precision": 1.01}, "between 0 and 1"),
        ({"max_unsupported_additions": -1}, "non-negative"),
        ({"max_unsupported_additions": 1.5}, "non-negative"),
    ],
)
def test_threshold_validation_rejects_nan_infinity_and_ranges(thresholds, message):
    with pytest.raises(harness.ValidationError, match=message):
        harness.run_evaluation([_case()], lambda _text: _perfect_actual(), thresholds=thresholds)


def test_cli_rejects_invalid_threshold_before_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "load_cases", lambda _directory: [_case()])
    monkeypatch.setattr(
        harness,
        "_real_runner",
        lambda: (_ for _ in ()).throw(AssertionError("runner must not initialize")),
    )
    assert (
        harness.main(
            [
                "--min-overall-precision",
                "nan",
                "--artifact",
                str(tmp_path / "artifact.json"),
            ]
        )
        == harness.EXIT_HARNESS
    )


def test_real_runner_uses_deleted_isolated_data_dir(monkeypatch, tmp_path):
    import agent
    from agent import config

    production = tmp_path / "production"
    production.mkdir()
    sentinel = production / "sentinel.txt"
    sentinel.write_text("do not touch", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", production)
    monkeypatch.setattr(config, "PROFILE_PATH", production / "patient_profile.json")
    monkeypatch.setattr(config, "REPORTS_DIR", production / "reports")
    observed: list[Path] = []

    def fake_intake(text, _profile):
        observed.append(config.DATA_DIR)
        source = config.DATA_DIR / "sources" / "source-1"
        source.mkdir(parents=True)
        (source / "private.txt").write_text(text, encoding="utf-8")
        return {}, {
            "document_type": "lab_result",
            "summary": text,
            "biomarkers": [],
            "treatment_changes": [],
        }

    monkeypatch.setattr(agent, "run_intake", fake_intake)
    runner, _prompt_hash, _models = harness._real_runner()
    actual = runner("PRIVATE PATIENT TEXT")
    assert actual["summary"] == "PRIVATE PATIENT TEXT"
    assert observed and observed[0] != production
    assert not observed[0].exists()
    assert sentinel.read_text(encoding="utf-8") == "do not touch"
    artifact = harness.run_evaluation(
        [_case()], lambda _text: actual, runs=1, thresholds=_permissive_thresholds()
    )
    assert "PRIVATE PATIENT TEXT" not in json.dumps(artifact)


def test_artifact_records_dirty_head_source_hashes_and_no_private_text(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    case_file = private / "patient-name.json"
    case_file.write_text(json.dumps(_case("PRIVATE SENTINEL CgA 20 ng/mL")), encoding="utf-8")
    first_hashes = harness._evaluated_source_hashes(private, [])
    case_file.write_text(
        json.dumps(_case("CHANGED PRIVATE SENTINEL CgA 20 ng/mL")), encoding="utf-8"
    )
    second_hashes = harness._evaluated_source_hashes(private, [])
    assert first_hashes != second_hashes
    assert all("patient-name" not in key for key in first_hashes)

    artifact = harness.run_evaluation(
        [_case()],
        lambda _text: _perfect_actual(),
        runs=1,
        timestamp="2026-01-01T00:00:00+00:00",
        git_commit="abc",
        git_dirty=True,
        source_hashes=first_hashes,
        model_ids=["fake-model"],
        config={
            "model_intake": "fake-model",
            "thinking": {"type": "adaptive"},
            "intake_verify": False,
        },
        prompt_hash="effective-prompt-sha",
    )
    encoded = json.dumps(artifact)
    assert artifact["git"] == {"head": "abc", "dirty": True}
    assert artifact["evaluated_source_hashes"] == first_hashes
    assert artifact["prompt_hash"] == "effective-prompt-sha"
    assert "PRIVATE SENTINEL" not in encoded
    assert "Start lanreotide" not in encoded

    private_artifact = harness.run_evaluation(
        [_case()],
        lambda _text: _perfect_actual(),
        runs=1,
        anonymize_case_ids=True,
    )
    assert private_artifact["cases"][0]["id"] != "unit-case"


def test_equivalent_numeric_special_scalars_match():
    case = _case("Pathology 2026-01-02: Ki-67 index 8%.")
    case["expected"]["biomarkers"] = []
    case["expected"]["treatment_changes"] = []
    case["expected"]["ki67_update"] = 8
    case["expected"]["source_quotes"] = [{"field": "ki67_update", "quote": "Ki-67 index 8%"}]
    actual = {
        "document_type": "lab_result",
        "ki67_update": 8.0,
        "evidence": [
            {
                "field": "ki67_update",
                "item_index": None,
                "source_quote": "Ki-67 index 8%",
            }
        ],
    }
    score = harness.score_extraction(case["expected"], actual, case["text"])
    assert score["special_scalars"]["accuracy"] == 1


def test_runtime_failure_is_distinct():
    def broken(_text):
        raise TimeoutError("model timed out")

    with pytest.raises(harness.RuntimeEvaluationError, match="TimeoutError"):
        harness.run_evaluation([_case()], broken, runs=1)


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        ("pass", harness.EXIT_PASS),
        ("metrics", harness.EXIT_METRICS),
        ("runtime", harness.EXIT_RUNTIME),
        ("harness", harness.EXIT_HARNESS),
    ],
)
def test_main_exit_semantics(monkeypatch, tmp_path, setup, expected):
    if setup == "harness":
        monkeypatch.setattr(
            harness,
            "load_cases",
            lambda _directory: (_ for _ in ()).throw(harness.ValidationError("bad")),
        )
    else:
        monkeypatch.setattr(harness, "load_cases", lambda _directory: [_case()])

        def runner(_text):
            if setup == "runtime":
                raise TimeoutError("no response")
            return _perfect_actual() if setup == "pass" else {"document_type": "lab_result"}

        monkeypatch.setattr(harness, "_real_runner", lambda: (runner, "hash", ["fake"]))
    monkeypatch.setattr(harness, "_git_metadata", lambda: ("abc", True))
    monkeypatch.setattr(harness, "_evaluated_source_hashes", lambda *_args: {"source": "hash"})
    monkeypatch.setattr(
        harness,
        "_runtime_config",
        lambda: {
            "model_intake": "fake",
            "thinking": {"type": "adaptive"},
            "intake_verify": False,
        },
    )
    args = ["--runs", "1", "--artifact", str(tmp_path / "artifact.json")]
    assert harness.main(args) == expected
