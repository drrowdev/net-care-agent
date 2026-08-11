"""Tests for agent/migrations.py — schema versioning and idempotent migrations."""

from __future__ import annotations

import copy
import json

# ── helpers ───────────────────────────────────────────────────────────────────


def _unversioned() -> dict:
    """Minimal unversioned profile (no schema_version key)."""
    return {"patient": {"diagnosis": "NET"}, "biomarkers": [{"marker": "CgA"}]}


def _current() -> dict:
    """Profile already at current schema version."""
    from agent.migrations import CURRENT_SCHEMA_VERSION

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "patient": {"diagnosis": "NET"},
        "biomarkers": [],
    }


# ── migration tests ───────────────────────────────────────────────────────────


def test_unversioned_gets_schema_version():
    """Migration 0001 adds schema_version=1 to an unversioned profile."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION


def test_unversioned_migration_records_log_entry():
    """Migration 0001 records a log entry with an applied_at timestamp."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    assert "_migration_log" in result
    log = result["_migration_log"]
    assert isinstance(log, list)
    assert len(log) == 13
    entry = log[0]
    assert entry["id"] == "0001_add_schema_version"
    assert "applied_at" in entry
    # Timestamp must not be "backfilled" for an unversioned profile.
    assert entry["applied_at"] != "backfilled"
    assert log[1]["id"] == "0002_add_document_imports"
    assert log[2]["id"] == "0003_add_generated_content_provenance"
    assert log[3]["id"] == "0004_add_stable_alert_ids"
    assert log[4]["id"] == "0005_add_dependency_lifecycles"
    assert log[5]["id"] == "0006_add_stable_treatment_records"
    assert log[6]["id"] == "0007_harden_legacy_generated_alerts"
    assert log[7]["id"] == "0008_add_follow_through_foundation"
    assert log[8]["id"] == "0009_add_biomarker_projection_authority"
    assert log[9]["id"] == "0010_add_imaging_projection_authority"
    assert log[10]["id"] == "0011_add_symptom_episode_authority"
    assert log[11]["id"] == "0012_add_treatment_reconciliation_authority"
    assert log[12]["id"] == "0013_add_treatment_terminal_authority"


def test_already_current_fast_path_no_change():
    """apply_migrations on an already-current profile returns it unchanged."""
    from agent.migrations import apply_migrations

    data = _current()
    original = copy.deepcopy(data)
    result = apply_migrations(data)
    assert result is data  # same object (no copy)
    assert result == original  # no mutation


def test_idempotent_second_apply_no_change():
    """Applying migrations twice produces the same result; log not duplicated."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    once = apply_migrations(data)
    original_log = copy.deepcopy(once["_migration_log"])
    twice = apply_migrations(once)
    assert twice["_migration_log"] == original_log  # unchanged


def test_idempotent_preserves_original_timestamp():
    """A second apply_migrations call preserves the first applied_at timestamp."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    first = apply_migrations(data)
    original_ts = first["_migration_log"][0]["applied_at"]

    second = apply_migrations(first)
    assert second["_migration_log"][0]["applied_at"] == original_ts


def test_unknown_fields_preserved_through_migration():
    """Extra (unknown) fields survive migration unchanged — forward compat."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    data["custom_extension"] = {"flag": 42}
    data["patient"]["my_extra_field"] = "keep_me"

    result = apply_migrations(data)
    assert result["custom_extension"] == {"flag": 42}
    assert result["patient"]["my_extra_field"] == "keep_me"


def test_clinical_values_not_inferred():
    """Migration must not add clinical values that weren't present."""
    from agent.migrations import apply_migrations

    data = {"patient": {}}  # empty patient, unversioned
    result = apply_migrations(data)
    # No clinical fields should be invented.
    patient = result["patient"]
    assert patient.get("diagnosis") is None
    assert patient.get("ki67_percent") is None
    assert patient.get("sstr_status") is None


def test_already_at_version_with_existing_log_unchanged():
    """Profile at current version with a migration log: log is not touched."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "patient": {},
        "_migration_log": [{"id": "0001_add_schema_version", "applied_at": "2026-01-01T00:00:00"}],
    }
    original_log = copy.deepcopy(data["_migration_log"])
    result = apply_migrations(data)
    assert result["_migration_log"] == original_log  # untouched


def test_non_dict_raises_type_error():
    """apply_migrations on non-dict raises TypeError."""
    import pytest

    from agent.migrations import apply_migrations

    with pytest.raises(TypeError, match="expected dict"):
        apply_migrations(["not", "a", "dict"])


def test_null_schema_version_treated_as_unversioned():
    """Explicit schema_version=null is treated as unversioned."""
    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    data = {"schema_version": None, "patient": {}}
    result = apply_migrations(data)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION


def test_migration_timestamp_is_iso_seconds():
    """Applied-at timestamp uses second-precision ISO format."""
    from agent.migrations import apply_migrations

    data = _unversioned()
    result = apply_migrations(data)
    ts = result["_migration_log"][0]["applied_at"]
    import datetime

    parsed = datetime.datetime.fromisoformat(ts)
    assert parsed.microsecond == 0  # seconds precision


def test_forward_schema_version_passes_through_unchanged():
    """A profile with schema_version > CURRENT_SCHEMA_VERSION is returned
    completely unchanged — no backfill, no mutation, no log entries added."""
    import copy

    from agent.migrations import CURRENT_SCHEMA_VERSION, apply_migrations

    future_version = CURRENT_SCHEMA_VERSION + 5
    data = {
        "schema_version": future_version,
        "patient": {"diagnosis": "NET"},
        "biomarkers": [],
        "future_field": {"x": 1},
    }
    original = copy.deepcopy(data)
    result = apply_migrations(data)
    assert result is data  # same object, no copy
    assert result == original  # no mutation whatsoever
    assert "_migration_log" not in result


def test_v1_adds_empty_document_import_ledger_without_clinical_inference():
    from agent.migrations import apply_migrations

    data = {"schema_version": 1, "patient": {"diagnosis": "NET"}}
    result = apply_migrations(data)

    assert result["schema_version"] == 13
    assert result["document_imports"] == []
    assert result["patient"]["diagnosis"] == "NET"
    assert result["patient"]["current_treatment_records"] == []


def test_v2_conservatively_stales_legacy_ai_questions_without_generation_identity():
    from agent.migrations import apply_migrations

    data = {
        "schema_version": 2,
        "patient": {"diagnosis": "NET"},
        "appointment_questions": [
            {"id": "legacy-ai", "text": "Old generated question", "source": "ai"},
            {"id": "manual", "text": "Caregiver question", "source": "manual"},
        ],
    }

    result = apply_migrations(data)

    assert result["schema_version"] == 13
    assert result["questions_generation_id"] is None
    assert result["appointment_questions"][0]["stale"] is True
    assert (
        result["appointment_questions"][0]["stale_reason"] == "legacy_missing_generation_provenance"
    )
    assert "stale" not in result["appointment_questions"][1]


def test_v3_deterministically_backfills_stable_alert_ids():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 3,
        "patient": {"diagnosis": "NET"},
        "alerts": [
            {"message": "First", "resolved": False},
            {"message": "First", "resolved": False},
            {"id": "existing", "message": "Existing", "resolved": False},
        ],
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    assert first["schema_version"] == 13
    assert first["alerts"][0]["id"].startswith("alert_legacy_")
    assert first["alerts"][1]["id"].startswith("alert_legacy_")
    assert first["alerts"][0]["id"] != first["alerts"][1]["id"]
    assert first["alerts"][2]["id"] == "existing"
    assert [item["id"] for item in first["alerts"]] == [item["id"] for item in second["alerts"]]


def test_v4_migrates_alert_lifetimes_and_invalidates_legacy_classification():
    from agent.migrations import apply_migrations

    data = {
        "schema_version": 4,
        "patient": {"current_treatments": ["lanreotide"]},
        "treatments_classified": [{"text": "lanreotide", "category": "active"}],
        "alerts": [
            {"id": "intake", "source": "intake_extraction_failure"},
            {"id": "trial", "source": "trial_status_poll"},
            {"id": "source", "source_document_id": "doc_" + "a" * 32},
            {"id": "snapshot", "generation_profile_revision": 4},
            {"id": "legacy"},
        ],
        "document_imports": [
            {
                "job_id": "feed",
                "changes": [
                    {
                        "target": {"collection": "alerts", "record_id": "intake"},
                        "effective_value": {
                            "id": "intake",
                            "source": "intake_extraction_failure",
                        },
                    }
                ],
            }
        ],
    }

    result = apply_migrations(data)

    assert result["schema_version"] == 13
    assert result["treatments_classification_revision"] is None
    assert result["treatments_classification_job_id"] is None
    assert [item["dependency_kind"] for item in result["alerts"]] == [
        "durable",
        "durable",
        "source",
        "profile_snapshot",
        "profile_snapshot",
    ]
    assert (
        result["document_imports"][0]["changes"][0]["effective_value"]["dependency_kind"]
        == "durable"
    )


def test_v5_backfills_stable_composite_treatment_records_and_stales_classification():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 5,
        "patient": {
            "current_treatments": ["lanreotide plus everolimus"],
        },
        "treatments_classified": [
            {"text": "lanreotide", "category": "active"},
            {"text": "everolimus", "category": "active"},
        ],
        "treatments_classification_revision": 5,
        "treatments_classification_job_id": "legacy",
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    assert first["schema_version"] == 13
    records = first["patient"]["current_treatment_records"]
    assert [item["text"] for item in records] == ["lanreotide", "everolimus"]
    assert len({item["id"] for item in records}) == 2
    assert len({item["source_entry_id"] for item in records}) == 1
    assert [item["id"] for item in records] == [
        item["id"] for item in second["patient"]["current_treatment_records"]
    ]
    assert first["treatments_classification_revision"] is None
    assert first["treatments_classification_job_id"] is None


def test_v6_legacy_generated_alerts_are_sanitized_and_snapshot_bound():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 6,
        "profile_revision": 8,
        "patient": {"diagnosis": "NET"},
        "alerts": [
            {
                "id": "legacy-treatment",
                "message": "Hold PRRT now",
                "action_required": "The patient should receive Lutathera",
                "dependency_kind": "durable",
                "resolved": False,
            },
            {
                "id": "operational",
                "source": "intake_extraction_failure",
                "message": "Document extraction failed",
                "dependency_kind": "durable",
                "resolved": False,
            },
        ],
        "document_imports": [
            {
                "changes": [
                    {
                        "target": {
                            "collection": "alerts",
                            "record_id": "legacy-treatment",
                        },
                        "effective_value": {
                            "id": "legacy-treatment",
                            "message": "Hold PRRT now",
                            "dependency_kind": "durable",
                        },
                    }
                ]
            }
        ],
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    legacy = first["alerts"][0]
    assert legacy["dependency_kind"] == "profile_snapshot"
    assert legacy["generation_profile_revision"] == 8
    assert "confirm before any treatment change" in legacy["message"]
    assert "must review the complete criteria" in legacy["action_required"]
    assert first["alerts"][1]["dependency_kind"] == "durable"
    assert first["alerts"][1]["message"] == "Document extraction failed"
    effective = first["document_imports"][0]["changes"][0]["effective_value"]
    assert effective["message"] == legacy["message"]
    assert effective["dependency_kind"] == "profile_snapshot"
    assert effective["generation_profile_revision"] == 8
    assert first["alerts"] == second["alerts"]
    assert first["document_imports"] == second["document_imports"]

    from agent.profile import active_alerts

    assert [item["id"] for item in active_alerts(first)] == [
        "legacy-treatment",
        "operational",
    ]
    first["profile_revision"] = 9
    assert [item["id"] for item in active_alerts(first)] == ["operational"]


def test_v1_null_scaffolding_migrates_deterministically_without_inventing_clinical_data():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 1,
        "profile_revision": 2,
        "patient": None,
        "alerts": [{"message": "Document extraction failed", "resolved": False}],
        "appointment_questions": None,
        "document_imports": None,
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    assert first["schema_version"] == 13
    assert first["patient"] == {"current_treatment_records": []}
    assert first["document_imports"] == []
    assert first["alerts"][0]["dependency_kind"] == "profile_snapshot"
    assert first["patient"] == second["patient"]
    assert first["alerts"] == second["alerts"]


def test_v7_adds_follow_through_defaults_and_deterministic_summary_action_ids():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 7,
        "profile_revision": 12,
        "patient": {"diagnosis": "NET"},
        "executive_summary": {
            "summary_revision": 12,
            "next_actions": [
                {"action": "Ask the treating team about timing"},
                {"action": "Ask the treating team about timing"},
            ],
        },
        "alerts": [{"id": "done", "resolved": True}],
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    assert first == second
    assert first["schema_version"] == 13
    assert first["workflow_revision"] == 0
    assert first["caregiver_actions"] == []
    assert first["visits"] == []
    ids = [item["id"] for item in first["executive_summary"]["next_actions"]]
    assert ids[0].startswith("sumact_")
    assert ids[0] != ids[1]
    assert first["summary_stale"] is True
    assert first["executive_summary"]["stale"] is True
    assert first["executive_summary"]["stale_reason"] == "legacy_missing_generation_provenance"
    assert first["alerts"][0]["history"] == []
    assert first["alerts"][0]["resolution"]["outcome_kind"] == "legacy_unknown"


def test_v8_backfills_biomarker_ids_from_stable_source_authority():
    from agent.migrations import apply_migrations

    rows = [
        {
            "source_document_id": "doc_" + "a" * 32,
            "evidence_status": "verified",
            "evidence_start": 10,
            "evidence_end": 20,
            "marker": "CgA",
            "value": 12,
            "date": "2026-08-01",
        },
        {
            "source_document_id": "doc_" + "b" * 32,
            "evidence_status": "verified",
            "evidence_start": 30,
            "evidence_end": 40,
            "marker": "CgA",
            "value": 13,
            "date": "2026-08",
        },
    ]
    first = apply_migrations(
        {"schema_version": 8, "patient": {}, "biomarkers": copy.deepcopy(rows)}
    )
    reordered = apply_migrations(
        {"schema_version": 8, "patient": {}, "biomarkers": list(reversed(copy.deepcopy(rows)))}
    )

    first_ids = {row["source_document_id"]: row["id"] for row in first["biomarkers"]}
    reordered_ids = {row["source_document_id"]: row["id"] for row in reordered["biomarkers"]}
    assert first_ids == reordered_ids
    assert first["biomarkers"][0]["date_precision"] == "day"
    assert first["biomarkers"][0]["date_kind"] == "clinical_unspecified"
    assert first["biomarkers"][1]["date_precision"] == "month"
    assert first["biomarkers"][0]["specimen"] is None


def test_v8_preserves_existing_ids_and_distinguishes_identical_occurrences():
    from agent.migrations import apply_migrations

    identical = {"marker": "NSE", "value": "positive", "date": None}
    source = {
        "schema_version": 8,
        "patient": {},
        "biomarkers": [
            {"id": "existing", **identical},
            copy.deepcopy(identical),
            copy.deepcopy(identical),
        ],
    }
    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    ids = [row["id"] for row in first["biomarkers"]]
    assert ids[0] == "existing"
    assert len(ids) == len(set(ids)) == 3
    assert ids == [row["id"] for row in second["biomarkers"]]
    assert all(row["date_precision"] == "unknown" for row in first["biomarkers"])
    assert all(row["date_kind"] == "unknown" for row in first["biomarkers"])


def test_load_profile_persists_v9_biomarker_backfill_idempotently(agent):
    legacy = {
        "schema_version": 8,
        "patient": {"diagnosis": "NET"},
        "biomarkers": [{"marker": "CgA", "value": 12, "date": "2026"}],
    }
    agent.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    agent.PROFILE_PATH.write_text(json.dumps(legacy), encoding="utf-8")

    first = agent.load_profile()
    second = agent.load_profile()

    assert first["schema_version"] == 13
    assert first["biomarkers"][0]["id"] == second["biomarkers"][0]["id"]
    assert (
        json.loads(agent.PROFILE_PATH.read_text(encoding="utf-8"))["biomarkers"][0]["id"]
        == (first["biomarkers"][0]["id"])
    )


def test_v7_preserves_fully_identified_current_summary():
    from agent.migrations import apply_migrations

    source = {
        "schema_version": 7,
        "profile_revision": 12,
        "summary_stale": False,
        "patient": {"diagnosis": "NET"},
        "executive_summary": {
            "generation_id": "summary-job-current",
            "summary_revision": 12,
            "stale": False,
            "next_actions": [{"action": "Ask the treating team about timing"}],
        },
    }

    result = apply_migrations(source)

    assert result["summary_stale"] is False
    assert result["executive_summary"]["stale"] is False
    assert result["executive_summary"]["generation_id"] == "summary-job-current"


def test_v9_backfills_imaging_authority_without_rewriting_legacy_facts():
    from agent.migrations import apply_migrations

    existing = {
        "id": "existing-imaging-id",
        "date": "2026-03-18",
        "modality": "MRI liver",
        "findings": "multiple hepatic metastases are unchanged",
        "impression": "No new lesion.",
        "new_lesions": False,
        "source_document_id": "doc_" + "a" * 32,
        "source_quote": "multiple hepatic metastases are unchanged",
        "evidence_status": "verified",
        "evidence_start": 10,
        "evidence_end": 50,
        "legacy_extra": {"keep": ["exact", 2]},
    }
    missing_id = {
        "date": "2026-05",
        "modality": "CT",
        "findings": "Stored wording",
        "source_document_id": "doc_" + "b" * 32,
        "evidence_status": "missing",
    }
    source = {
        "schema_version": 9,
        "patient": {"diagnosis": "NET"},
        "imaging": [copy.deepcopy(existing), copy.deepcopy(missing_id)],
    }

    result = apply_migrations(copy.deepcopy(source))

    assert result["schema_version"] == 13
    assert result["imaging"][0]["id"] == "existing-imaging-id"
    for key, value in existing.items():
        assert result["imaging"][0][key] == value
    assert result["imaging"][0]["date_precision"] == "day"
    assert result["imaging"][0]["date_kind"] == "legacy_unknown"
    assert result["imaging"][0]["source_document_date"] is None
    assert result["imaging"][1]["date_precision"] == "month"
    assert result["imaging"][1]["date_kind"] == "legacy_unknown"
    assert result["imaging"][1]["id"].startswith("fact_imaging_")


def test_v9_imaging_ids_are_reorder_stable_and_duplicates_remain_a_multiset():
    from agent.migrations import apply_migrations

    distinct = [
        {
            "source_document_id": "doc_" + char * 32,
            "evidence_status": "verified",
            "evidence_start": index * 10,
            "evidence_end": index * 10 + 5,
            "date": f"2026-0{index + 1}",
            "findings": f"finding {index}",
        }
        for index, char in enumerate(("a", "b"))
    ]
    identical = {"date": None, "modality": "other", "findings": "same"}

    forward = apply_migrations(
        {
            "schema_version": 9,
            "patient": {},
            "imaging": copy.deepcopy(distinct)
            + [copy.deepcopy(identical), copy.deepcopy(identical)],
        }
    )
    reversed_rows = apply_migrations(
        {
            "schema_version": 9,
            "patient": {},
            "imaging": list(reversed(copy.deepcopy(distinct)))
            + [copy.deepcopy(identical), copy.deepcopy(identical)],
        }
    )

    forward_distinct = {
        row["source_document_id"]: row["id"]
        for row in forward["imaging"]
        if row.get("source_document_id")
    }
    reversed_distinct = {
        row["source_document_id"]: row["id"]
        for row in reversed_rows["imaging"]
        if row.get("source_document_id")
    }
    assert forward_distinct == reversed_distinct
    duplicate_ids = [row["id"] for row in forward["imaging"] if not row.get("source_document_id")]
    assert len(duplicate_ids) == len(set(duplicate_ids)) == 2
    reversed_duplicate_ids = [
        row["id"] for row in reversed_rows["imaging"] if not row.get("source_document_id")
    ]
    assert set(duplicate_ids) == set(reversed_duplicate_ids)


def test_v9_imaging_migration_keeps_active_receipt_semantics_consistent():
    from agent.migrations import apply_migrations

    row = {
        "id": "imaging-row",
        "date": "2026",
        "modality": "CT",
        "findings": "Exact stored finding",
        "source_document_id": "doc_" + "a" * 32,
        "evidence_status": "missing",
    }
    profile = {
        "schema_version": 9,
        "patient": {},
        "imaging": [copy.deepcopy(row)],
        "document_imports": [
            {
                "id": "import",
                "job_id": "feed",
                "source_document_id": row["source_document_id"],
                "status": "active",
                "receipt_revision": 1,
                "changes": [
                    {
                        "id": "change",
                        "state": "active",
                        "target": {
                            "kind": "collection",
                            "collection": "imaging",
                            "record_id": row["id"],
                            "path": [],
                        },
                        "effective_value": copy.deepcopy(row),
                    }
                ],
            }
        ],
    }

    result = apply_migrations(profile)
    migrated = result["imaging"][0]
    effective = result["document_imports"][0]["changes"][0]["effective_value"]

    for field in (
        "date_precision",
        "date_kind",
        "source_document_date",
        "source_document_date_precision",
    ):
        assert effective[field] == migrated[field]


def test_v9_duplicate_existing_imaging_ids_do_not_rebind_receipt_authority():
    from agent.migrations import apply_migrations

    row = {
        "id": "duplicate-id",
        "date": "2026",
        "findings": "First row",
    }
    effective = copy.deepcopy(row)
    expected_effective = copy.deepcopy(effective)
    profile = {
        "schema_version": 9,
        "patient": {},
        "imaging": [copy.deepcopy(row), {**copy.deepcopy(row), "findings": "Second row"}],
        "document_imports": [
            {
                "source_document_id": "source",
                "changes": [
                    {
                        "target": {
                            "collection": "imaging",
                            "record_id": "duplicate-id",
                        },
                        "effective_value": effective,
                    }
                ],
            }
        ],
    }

    result = apply_migrations(profile)

    assert result["imaging"][0]["id"] == result["imaging"][1]["id"] == "duplicate-id"
    assert result["document_imports"][0]["changes"][0]["effective_value"] == expected_effective


def test_v10_adds_separate_episode_authority_without_promoting_legacy_symptoms():
    from agent.migrations import apply_migrations

    existing = {
        "id": "existing symptom/id",
        "date": "2026-08",
        "symptom": "Exact legacy wording",
        "severity": 4,
        "source": "ai",
        "source_document_id": "doc_" + "a" * 32,
        "evidence_status": "missing",
        "unknown_extra": {"keep": ["exact", 2]},
    }
    missing = {
        "date": None,
        "symptom": "Undated duplicate",
        "severity": None,
        "source": "manual",
        "unknown_extra": "preserve",
    }
    source = {
        "schema_version": 10,
        "patient": {"diagnosis": "NET"},
        "symptoms": [
            copy.deepcopy(existing),
            copy.deepcopy(missing),
            copy.deepcopy(missing),
        ],
    }

    first = apply_migrations(copy.deepcopy(source))
    second = apply_migrations(copy.deepcopy(source))

    assert first == second
    assert first["schema_version"] == 13
    assert first["symptom_episodes"] == []
    assert first["symptoms"][0]["id"] == existing["id"]
    for key, value in existing.items():
        assert first["symptoms"][0][key] == value
    assert first["symptoms"][0]["date_precision"] == "month"
    assert first["symptoms"][0]["date_kind"] == "legacy_unknown"
    assert first["symptoms"][0]["source_document_date"] is None
    duplicate_ids = [row["id"] for row in first["symptoms"][1:]]
    assert len(duplicate_ids) == len(set(duplicate_ids)) == 2
    assert all(row["date_kind"] == "unknown" for row in first["symptoms"][1:])


def test_v10_symptom_ids_are_reorder_stable_and_receipts_sync_only_unique_targets():
    from agent.migrations import apply_migrations

    distinct = [
        {
            "source_document_id": "doc_" + char * 32,
            "evidence_status": "verified",
            "evidence_start": index * 10,
            "evidence_end": index * 10 + 5,
            "date": "2026-08-01",
            "symptom": f"wording {index}",
        }
        for index, char in enumerate(("a", "b"))
    ]
    duplicate_id_rows = [
        {"id": "ambiguous", "date": "2026", "symptom": "first"},
        {"id": "ambiguous", "date": "2026", "symptom": "second"},
    ]
    effective = copy.deepcopy(duplicate_id_rows[0])
    profile = {
        "schema_version": 10,
        "patient": {},
        "symptoms": copy.deepcopy(distinct + duplicate_id_rows),
        "document_imports": [
            {
                "source_document_id": "source",
                "changes": [
                    {
                        "target": {
                            "collection": "symptoms",
                            "record_id": "ambiguous",
                        },
                        "effective_value": effective,
                    }
                ],
            }
        ],
    }

    forward = apply_migrations(copy.deepcopy(profile))
    reordered = copy.deepcopy(profile)
    reordered["symptoms"][:2] = reversed(reordered["symptoms"][:2])
    reverse = apply_migrations(reordered)

    forward_ids = {
        row["source_document_id"]: row["id"]
        for row in forward["symptoms"]
        if row.get("source_document_id")
    }
    reverse_ids = {
        row["source_document_id"]: row["id"]
        for row in reverse["symptoms"]
        if row.get("source_document_id")
    }
    assert forward_ids == reverse_ids
    assert forward["symptoms"][-2:][0]["id"] == "ambiguous"
    assert forward["symptoms"][-2:][1]["id"] == "ambiguous"
    assert forward["document_imports"][0]["changes"][0]["effective_value"] == effective
