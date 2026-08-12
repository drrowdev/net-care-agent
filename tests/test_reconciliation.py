from __future__ import annotations

import copy
import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def _retain_feed_job(app_module, profile, job_id="feed-job"):
    source_id = profile["document_imports"][0]["source_document_id"]
    app_module._jobs = [
        {
            "id": job_id,
            "type": "feed",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "source_document_id": source_id,
            "error": None,
        }
    ]


def _ingest(agent, profile, *, job_id="feed-job", ki67=12):
    text = "CgA 234 ng/mL. Ki-67 12%."
    payload = {
        "document_type": "lab_result",
        "date": "2026-08-01",
        "summary": "New lab and pathology values.",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 234,
                "unit": "ng/mL",
                "source_quote": "CgA 234 ng/mL",
            }
        ],
        "ki67_update": ki67,
        "key_findings": ["Ki-67 is 12%"],
        "evidence": [
            {
                "field": "ki67_update",
                "item_index": None,
                "source_quote": "Ki-67 12%",
            },
            {
                "field": "key_findings",
                "item_index": 0,
                "source_quote": "Ki-67 12%",
            },
        ],
    }
    before = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        updated, extracted = agent.run_intake(text, profile)
    record = agent.build_import_record(before, updated, extracted, job_id=job_id, text=text)
    return updated, record


def test_receipt_shows_additions_conflicts_and_exact_evidence(agent, empty_profile):
    empty_profile["patient"]["ki67_percent"] = 8
    profile, _ = _ingest(agent, empty_profile)

    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")
    scalar = next(item for item in receipt["changes"] if item["label"] == "Ki-67")

    assert biomarker["operation"] == "added"
    assert biomarker["evidence_status"] == "verified"
    assert "/api/evidence/" in biomarker["evidence_url"]
    assert scalar["operation"] == "conflict"
    assert scalar["before"] == 8
    assert scalar["after"] == 12
    assert receipt["source_document_id"].startswith("doc_")
    assert receipt["source_url"].endswith("/text")
    assert receipt["source_url"] != f"/api/sources/{receipt['source_document_id']}"
    assert receipt["counts"]["added"] >= 2
    assert receipt["counts"]["conflict"] == 1


def test_correction_preserves_source_and_records_history(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    source = profile["source_documents"][0]
    source_path = agent.DATA_DIR / source["text"]["path"]
    original_text = source_path.read_bytes()
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    profile["alerts"].append({"id": "unrelated", "message": "Later unrelated change"})
    agent.correct_change(
        profile,
        "feed-job",
        biomarker["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=biomarker["target_token"],
        replacement={"value": 243},
    )

    assert profile["biomarkers"][0]["value"] == 243
    change = next(
        item for item in profile["document_imports"][0]["changes"] if item["id"] == biomarker["id"]
    )
    assert change["state"] == "corrected"
    assert change["history"][0]["before"]["value"] == 234
    assert change["history"][0]["after"]["value"] == 243
    assert profile["biomarkers"][0]["evidence_status"] == "missing"
    assert profile["biomarkers"][0]["source_quote"] is None
    assert not any(
        item["label"].startswith("Biomarker CgA")
        for item in agent.build_evidence_catalog(profile).values()
    )
    assert agent.active_documents(profile) == []
    public = agent.public_receipt(profile, "feed-job")
    public_change = next(item for item in public["changes"] if item["id"] == biomarker["id"])
    assert public_change["effective_value"]["value"] == 243
    assert public_change["evidence_status"] == "missing"
    assert "/api/evidence/" in public_change["original_evidence_url"]
    assert source_path.read_bytes() == original_text


def test_biomarker_authority_fields_are_correctable_and_derived(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    assert {"date_kind", "source_document_date", "specimen", "assay", "method"} <= set(
        biomarker["editable_fields"]
    )
    agent.correct_change(
        profile,
        "feed-job",
        biomarker["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=biomarker["target_token"],
        replacement={
            "date": "2026-08",
            "date_kind": "collection",
            "source_document_date": "2026",
            "specimen": "Plasma",
            "assay": "Assay X",
        },
    )

    row = profile["biomarkers"][0]
    assert row["date"] == "2026-08"
    assert row["date_precision"] == "month"
    assert row["date_kind"] == "collection"
    assert row["source_document_date_precision"] == "year"
    assert row["specimen"] == "Plasma"
    assert row["assay"] == "Assay X"
    assert row["provenance_status"] == "caregiver_corrected"
    assert row["evidence_status"] == "missing"
    assert row["flag_authority"] == "unknown"


def test_unrelated_biomarker_correction_preserves_printed_flag_authority(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    profile["biomarkers"][0]["flag"] = "high"
    profile["biomarkers"][0]["flag_authority"] = "source_reported"
    change = next(
        item
        for item in profile["document_imports"][0]["changes"]
        if item["category"] == "biomarkers"
    )
    change["effective_value"] = copy.deepcopy(profile["biomarkers"][0])
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    agent.correct_change(
        profile,
        "feed-job",
        biomarker["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=biomarker["target_token"],
        replacement={"value": 243},
    )

    assert profile["biomarkers"][0]["flag"] == "high"
    assert profile["biomarkers"][0]["flag_authority"] == "source_reported"


def test_changed_target_rejects_correction_without_mutation(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")
    profile["biomarkers"][0]["value"] = 999

    with pytest.raises(agent.ImportConflict, match="changed"):
        agent.correct_change(
            profile,
            "feed-job",
            biomarker["id"],
            receipt_revision=receipt["receipt_revision"],
            target_token=biomarker["target_token"],
            replacement={"value": 243},
        )

    assert profile["biomarkers"][0]["value"] == 999
    assert profile["document_imports"][0]["receipt_revision"] == 1


def test_resolved_imported_alert_blocks_undo_without_deletion(agent, empty_profile):
    before = copy.deepcopy(empty_profile)
    text = "critical extraction could not be completed"
    with patch_llm(agent, lambda **_: llm_text("not-json")):
        profile, extracted = agent.run_intake(text, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed-alert", text=text)
    profile["alerts"][0]["generation_profile_revision"] = 2
    agent.sync_alert_system_state(profile, profile["alerts"][0])
    receipt = agent.public_receipt(profile, "feed-alert")
    alert_change = next(item for item in receipt["changes"] if item["category"] == "alerts")

    profile["alerts"][0]["resolved"] = True
    refreshed = agent.public_receipt(profile, "feed-alert")
    refreshed_alert = next(
        item for item in refreshed["changes"] if item["id"] == alert_change["id"]
    )

    assert refreshed_alert["conflicted"] is True
    assert refreshed["can_undo"] is False
    with pytest.raises(agent.ImportConflict):
        agent.undo_import(
            profile,
            "feed-alert",
            receipt_revision=receipt["receipt_revision"],
            undo_token=receipt["undo_token"],
        )
    assert len(profile["alerts"]) == 1
    assert profile["alerts"][0]["resolved"] is True


def test_legacy_alert_receipt_default_dependency_does_not_false_conflict(agent, empty_profile):
    before = copy.deepcopy(empty_profile)
    text = "critical extraction could not be completed"
    with patch_llm(agent, lambda **_: llm_text("not-json")):
        profile, extracted = agent.run_intake(text, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed-alert", text=text)
    alert_change = next(
        item for item in profile["document_imports"][0]["changes"] if item["category"] == "alerts"
    )
    alert_change["after"].pop("source_dependency_active", None)
    alert_change["effective_value"].pop("source_dependency_active", None)

    receipt = agent.public_receipt(profile, "feed-alert")
    public_alert = next(item for item in receipt["changes"] if item["id"] == alert_change["id"])

    assert public_alert["conflicted"] is False
    assert receipt["can_undo"] is True


def test_correction_then_whole_undo_succeeds_with_source_alert_dependency_sync(
    agent, empty_profile
):
    before = copy.deepcopy(empty_profile)
    text = "critical extraction could not be completed"
    with patch_llm(agent, lambda **_: llm_text("not-json")):
        profile, extracted = agent.run_intake(text, empty_profile)
    extracted["source_job_id"] = "feed-alert"
    agent.build_import_record(before, profile, extracted, job_id="feed-alert", text=text)
    receipt = agent.public_receipt(profile, "feed-alert")
    document = next(item for item in receipt["changes"] if item["category"] == "documents")

    agent.correct_change(
        profile,
        "feed-alert",
        document["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=document["target_token"],
        replacement={"summary": "Caregiver-corrected extraction failure summary"},
    )
    corrected_receipt = agent.public_receipt(profile, "feed-alert")
    alert = next(item for item in corrected_receipt["changes"] if item["category"] == "alerts")

    assert alert["conflicted"] is False
    assert corrected_receipt["can_undo"] is True
    agent.undo_import(
        profile,
        "feed-alert",
        receipt_revision=corrected_receipt["receipt_revision"],
        undo_token=corrected_receipt["undo_token"],
    )

    assert profile["document_imports"][0]["status"] == "undone"
    assert len(profile["alerts"]) == 1
    assert profile["alerts"][0]["dependency_kind"] == "durable"
    assert agent.active_alerts(profile)[0]["id"] == profile["alerts"][0]["id"]
    preserved = next(
        item for item in profile["document_imports"][0]["changes"] if item["category"] == "alerts"
    )
    assert preserved["state"] == "unchanged"
    assert preserved["preserved_reason"] == "durable_alert_requires_resolution"


def test_durable_alert_cannot_be_removed_from_receipt(agent, empty_profile):
    before = copy.deepcopy(empty_profile)
    text = "critical extraction could not be completed"
    with patch_llm(agent, lambda **_: llm_text("not-json")):
        profile, extracted = agent.run_intake(text, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="feed-alert", text=text)
    receipt = agent.public_receipt(profile, "feed-alert")
    alert = next(item for item in receipt["changes"] if item["category"] == "alerts")

    assert alert["removable"] is False
    with pytest.raises(agent.ReconciliationError, match="resolved explicitly"):
        agent.remove_change(
            profile,
            "feed-alert",
            alert["id"],
            receipt_revision=receipt["receipt_revision"],
            target_token=alert["target_token"],
        )
    assert len(profile["alerts"]) == 1


@pytest.mark.parametrize(
    "replacement",
    [
        {"date": "not-a-date"},
        {"marker": None},
        {"value": None},
        {"value": ""},
        {"value": float("nan")},
    ],
)
def test_invalid_biomarker_correction_is_rejected_without_mutation(
    agent, empty_profile, replacement
):
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")
    original = copy.deepcopy(profile["biomarkers"][0])

    with pytest.raises(agent.ReconciliationError):
        agent.correct_change(
            profile,
            "feed-job",
            biomarker["id"],
            receipt_revision=receipt["receipt_revision"],
            target_token=biomarker["target_token"],
            replacement=replacement,
        )

    assert profile["biomarkers"][0] == original
    assert profile["document_imports"][0]["receipt_revision"] == 1


def test_identical_correction_is_noop_with_profile_bytes_unchanged(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    profile, _ = _ingest(agent, empty_profile)
    agent.save_profile(profile)
    _retain_feed_job(app_module, profile)
    receipt = client.get("/api/jobs/feed-job/receipt").get_json()
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")
    before_bytes = agent.PROFILE_PATH.read_bytes()

    response = client.post(
        f"/api/jobs/feed-job/receipt/changes/{biomarker['id']}/correct",
        json={
            "receipt_revision": receipt["receipt_revision"],
            "target_token": biomarker["target_token"],
            "replacement": {"value": 234},
        },
    )

    assert response.status_code == 400
    assert "identical" in response.get_json()["error"]
    assert agent.PROFILE_PATH.read_bytes() == before_bytes
    saved = agent.load_profile()
    saved_change = next(
        item for item in saved["document_imports"][0]["changes"] if item["id"] == biomarker["id"]
    )
    assert saved["biomarkers"][0]["evidence_status"] == "verified"
    assert saved_change["history"] == []
    assert saved_change["state"] == "active"


def test_blank_scalar_correction_is_rejected_without_mutation(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    scalar = next(item for item in receipt["changes"] if item["label"] == "Ki-67")

    with pytest.raises(agent.ReconciliationError):
        agent.correct_change(
            profile,
            "feed-job",
            scalar["id"],
            receipt_revision=receipt["receipt_revision"],
            target_token=scalar["target_token"],
            replacement=None,
        )

    assert profile["patient"]["ki67_percent"] == 12


def test_non_finite_scalar_correction_is_rejected(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    scalar = next(item for item in receipt["changes"] if item["label"] == "Ki-67")

    with pytest.raises(agent.ReconciliationError):
        agent.correct_change(
            profile,
            "feed-job",
            scalar["id"],
            receipt_revision=receipt["receipt_revision"],
            target_token=scalar["target_token"],
            replacement=float("nan"),
        )

    assert profile["patient"]["ki67_percent"] == 12


def test_patient_summary_falls_back_to_findings_after_imaging_correction(agent, empty_profile):
    empty_profile["imaging"] = [
        {
            "id": "fact_imaging_test",
            "date": "2026-08-01",
            "modality": "CT",
            "findings": "Stable liver lesions.",
            "impression": None,
        }
    ]

    summary = agent.get_patient_summary(empty_profile)

    assert "Stable liver lesions." in summary


def test_document_undo_is_atomic_when_one_target_changed(agent, empty_profile):
    empty_profile["patient"]["ki67_percent"] = 8
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    profile["patient"]["ki67_percent"] = 20

    with pytest.raises(agent.ImportConflict):
        agent.undo_import(
            profile,
            "feed-job",
            receipt_revision=receipt["receipt_revision"],
            undo_token=receipt["undo_token"],
        )

    assert len(profile["biomarkers"]) == 1
    assert profile["patient"]["ki67_percent"] == 20
    assert profile["documents"][0].get("excluded_from_clinical_context", False) is False


def test_document_undo_removes_only_direct_effects_and_keeps_source(agent, empty_profile):
    empty_profile["patient"]["ki67_percent"] = 8
    profile, _ = _ingest(agent, empty_profile)
    source = profile["source_documents"][0]
    source_path = agent.DATA_DIR / source["text"]["path"]
    receipt = agent.public_receipt(profile, "feed-job")

    agent.undo_import(
        profile,
        "feed-job",
        receipt_revision=receipt["receipt_revision"],
        undo_token=receipt["undo_token"],
    )

    assert profile["biomarkers"] == []
    assert profile["patient"]["ki67_percent"] == 8
    assert profile["documents"][0]["excluded_from_clinical_context"] is True
    assert profile["source_documents"][0]["id"] == source["id"]
    assert source_path.exists()
    assert profile["document_imports"][0]["status"] == "undone"
    assert all(
        item["state"] in {"undone", "unchanged", "derived"}
        for item in profile["document_imports"][0]["changes"]
    )
    assert "New lab and pathology values." not in agent.get_patient_summary(profile)
    document_change = next(
        item
        for item in profile["document_imports"][0]["changes"]
        if item["category"] == "documents"
    )
    undo_event = next(item for item in document_change["history"] if item["event"] == "undone")
    assert undo_event["before"]["excluded_from_clinical_context"] is False
    assert undo_event["after"]["excluded_from_clinical_context"] is True
    assert undo_event["before"] != undo_event["after"]


def test_remove_single_scalar_restores_prior_value(agent, empty_profile):
    empty_profile["patient"]["ki67_percent"] = 8
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    scalar = next(item for item in receipt["changes"] if item["label"] == "Ki-67")

    agent.remove_change(
        profile,
        "feed-job",
        scalar["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=scalar["target_token"],
    )

    assert profile["patient"]["ki67_percent"] == 8
    assert profile["document_imports"][0]["status"] == "partially_removed"


def test_receipt_api_survives_profile_reload_and_allows_unrelated_revision(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    profile, _ = _ingest(agent, empty_profile)
    agent.save_profile(profile)
    _retain_feed_job(app_module, profile)

    first = client.get("/api/jobs/feed-job/receipt")
    assert first.status_code == 200
    receipt = first.get_json()
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    reloaded = agent.load_profile()
    reloaded["alerts"].append({"id": "later", "message": "Unrelated"})
    agent.save_profile(reloaded)
    response = client.post(
        f"/api/jobs/feed-job/receipt/changes/{biomarker['id']}/correct",
        json={
            "receipt_revision": receipt["receipt_revision"],
            "target_token": biomarker["target_token"],
            "replacement": {"value": 243},
        },
    )

    assert response.status_code == 200, response.get_json()
    assert agent.load_profile()["biomarkers"][0]["value"] == 243
    assert client.get("/api/jobs/feed-job/receipt").get_json()["status"] == "corrected"


def test_receipt_api_returns_explicit_409_for_changed_target(app_client, agent, empty_profile):
    app_module, client = app_client
    profile, _ = _ingest(agent, empty_profile)
    agent.save_profile(profile)
    _retain_feed_job(app_module, profile)
    receipt = client.get("/api/jobs/feed-job/receipt").get_json()
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    changed = agent.load_profile()
    changed["biomarkers"][0]["value"] = 999
    agent.save_profile(changed)
    response = client.post(
        f"/api/jobs/feed-job/receipt/changes/{biomarker['id']}/correct",
        json={
            "receipt_revision": receipt["receipt_revision"],
            "target_token": biomarker["target_token"],
            "replacement": {"value": 243},
        },
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "import_conflict"
    refreshed = response.get_json()["receipt"]
    assert (
        next(item for item in refreshed["changes"] if item["category"] == "biomarkers")[
            "conflicted"
        ]
        is True
    )
    assert agent.load_profile()["biomarkers"][0]["value"] == 999


def test_patient_evidence_api_is_path_free_and_links_receipt(app_client, agent, empty_profile):
    app_module, client = app_client
    profile, _ = _ingest(agent, empty_profile)
    agent.save_profile(profile)
    _retain_feed_job(app_module, profile)

    response = client.get("/api/patient/evidence")
    payload = response.get_json()
    serialized = json.dumps(payload)

    assert response.status_code == 200
    assert payload["documents"][0]["receipt_url"] == "/api/jobs/feed-job/receipt"
    assert payload["sources"][0]["artifacts"]["text"]["url"].startswith("/api/sources/")
    assert '"path"' not in serialized
    assert str(agent.DATA_DIR) not in serialized


def test_patient_evidence_keeps_excluded_and_orphaned_legacy_documents(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["documents"] = [
        {
            "date": "2020-01-01",
            "type": "doctor_note",
            "summary": "Legacy document without source index",
            "excluded_from_clinical_context": True,
        }
    ]
    agent.save_profile(empty_profile)

    payload = client.get("/api/patient/evidence").get_json()

    assert payload["documents"][0]["summary"] == "Legacy document without source index"
    assert payload["documents"][0]["excluded_from_clinical_context"] is True
    assert "source_url" not in payload["documents"][0]


def test_document_undo_api_works_after_normalized_profile_reload(app_client, agent, empty_profile):
    app_module, client = app_client
    empty_profile["patient"]["ki67_percent"] = 8
    profile, _ = _ingest(agent, empty_profile)
    agent.save_profile(profile)
    _retain_feed_job(app_module, profile)
    receipt = client.get("/api/jobs/feed-job/receipt").get_json()
    assert receipt["can_undo"], [
        (item["category"], item.get("conflict_reason"))
        for item in receipt["changes"]
        if item.get("conflicted")
    ]

    response = client.post(
        "/api/jobs/feed-job/receipt/undo",
        json={
            "receipt_revision": receipt["receipt_revision"],
            "undo_token": receipt["undo_token"],
        },
    )

    assert response.status_code == 200, response.get_json()
    saved = agent.load_profile()
    assert saved["biomarkers"] == []
    assert saved["patient"]["ki67_percent"] == 8
    assert saved["documents"][0]["excluded_from_clinical_context"] is True


def test_post_intake_failure_keeps_job_scoped_receipt(app_client, agent, monkeypatch):
    app_module, client = app_client
    app_module._jobs = [
        {
            "id": "feed-job",
            "type": "feed",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
            "error": None,
        }
    ]
    monkeypatch.setattr(
        agent,
        "run_orchestrator",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("research failed")),
    )
    payload = {
        "document_type": "lab_result",
        "date": "2026-08-01",
        "summary": "Lab imported before research failed.",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 234,
                "unit": "ng/mL",
                "source_quote": "CgA 234 ng/mL",
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        app_module._run_feed_job("feed-job", "CgA 234 ng/mL")

    detail = client.get("/api/jobs/feed-job").get_json()
    receipt = client.get("/api/jobs/feed-job/receipt")

    assert detail["status"] == "error"
    assert detail["receipt_url"] == "/api/jobs/feed-job/receipt"
    assert receipt.status_code == 200
    assert receipt.get_json()["document_summary"] == "Lab imported before research failed."
    assert agent.load_profile()["biomarkers"][0]["value"] == 234


def test_orchestration_failure_keeps_versioned_intake_alert_dependency(
    app_client, agent, monkeypatch
):
    app_module, client = app_client
    app_module._jobs = [
        {
            "id": "failed-feed",
            "type": "feed",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
            "error": None,
        }
    ]
    monkeypatch.setattr(
        agent,
        "run_orchestrator",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("research failed")),
    )
    with patch_llm(agent, lambda **_: llm_text("not-json")):
        app_module._run_feed_job("failed-feed", "unstructured clinical text")

    detail = client.get("/api/jobs/failed-feed").get_json()
    saved = agent.load_profile()
    alert = saved["alerts"][0]
    receipt = client.get("/api/jobs/failed-feed/receipt").get_json()
    receipt_alert = next(item for item in receipt["changes"] if item["category"] == "alerts")

    assert detail["status"] == "error"
    assert alert["source_job_id"] == "failed-feed"
    assert alert["generation_profile_revision"] == saved["profile_revision"]
    assert receipt_alert["conflicted"] is False
    assert agent.active_alerts(saved)[0]["id"] == alert["id"]

    saved["patient"]["diagnosis"] = "Updated diagnosis"
    agent.save_profile(saved)
    reloaded = agent.load_profile()
    assert reloaded["alerts"][0]["dependency_kind"] == "durable"
    assert agent.active_alerts(reloaded)[0]["id"] == alert["id"]


def test_correction_invalidates_source_alerts_questions_and_summary(agent, empty_profile):
    profile, _ = _ingest(agent, empty_profile)
    source_id = profile["document_imports"][0]["source_document_id"]
    profile["profile_revision"] = 4
    profile["summary_stale"] = False
    profile["executive_summary"] = {
        "summary_revision": 4,
        "stale": False,
        "overall_status": "stable",
        "summary": "OLD GENERATED SUMMARY",
        "next_actions": [{"action": "OLD ACTION"}],
        "prrt_status": "eligible",
    }
    profile["appointment_questions"] = [
        {
            "id": "generated",
            "text": "OLD GENERATED QUESTION",
            "source": "ai",
            "asked": False,
            "stale": False,
        },
        {
            "id": "manual",
            "text": "Manual caregiver question",
            "source": "manual",
            "asked": False,
        },
    ]
    profile["alerts"].append(
        {
            "id": "source-alert",
            "priority": "high",
            "message": "Potential PRRT fit to confirm",
            "resolved": False,
            "source_document_id": source_id,
            "source_job_id": "feed-job",
            "source_dependency_active": True,
            "dependency_kind": "source",
        }
    )
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")

    agent.correct_change(
        profile,
        "feed-job",
        biomarker["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=biomarker["target_token"],
        replacement={"value": 243},
    )

    assert profile["summary_stale"] is True
    assert profile["executive_summary"]["stale"] is True
    assert profile["appointment_questions"][0]["stale"] is True
    assert profile["appointment_questions"][1].get("stale", False) is False
    assert profile["alerts"][-1]["source_dependency_active"] is False
    assert agent.active_alerts(profile) == []
    prompt = agent.build_chat_system(profile)
    assert "OLD GENERATED SUMMARY" not in prompt
    assert "OLD ACTION" not in prompt
    assert "Potential PRRT fit to confirm" not in prompt


def test_stale_summary_api_hides_generated_content_and_excluded_documents(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 5
    empty_profile["summary_stale"] = True
    empty_profile["executive_summary"] = {
        "summary_revision": 4,
        "stale": True,
        "overall_status": "stable",
        "status_rationale": "OLD RATIONALE",
        "key_concern": "OLD CONCERN",
        "summary": "OLD SUMMARY",
        "prrt_status": "eligible",
        "prrt_rationale": "OLD PRRT",
        "next_actions": [{"action": "OLD ACTION"}],
        "timeline": [{"event": "OLD EVENT"}],
        "best_trial": {"nct_id": "NCT00000001"},
    }
    empty_profile["documents"] = [
        {
            "date": "2026-08-01",
            "summary": "Excluded corrected source",
            "excluded_from_clinical_context": True,
        },
        {
            "date": "2026-08-02",
            "summary": "Active source",
            "excluded_from_clinical_context": False,
        },
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    payload = client.get("/api/summary").get_json()

    assert payload["status"] == "stale"
    assert payload["content_hidden"] is True
    for field in (
        "overall_status",
        "status_rationale",
        "key_concern",
        "summary",
        "prrt_status",
        "next_actions",
        "timeline",
        "best_trial",
    ):
        assert field not in payload
    assert [item["summary"] for item in payload["recent_documents"]] == ["Active source"]


@pytest.mark.parametrize("job_type", ["questions", "summary"])
def test_dependent_job_artifacts_are_marked_or_hidden_after_profile_change(
    app_client, agent, empty_profile, job_type
):
    app_module, client = app_client
    empty_profile["profile_revision"] = 2
    agent.save_profile(empty_profile, clinical_change=False)
    result = (
        {
            "questions": [{"text": "OLD GENERATED QUESTION", "source": "ai"}],
            "source_profile_revision": 1,
        }
        if job_type == "questions"
        else {
            "summary": {"summary": "OLD GENERATED SUMMARY"},
            "profile_revision": 1,
        }
    )
    result_ref = app_module._write_job_result("dependent-job", result)
    app_module._jobs = [
        {
            "id": "dependent-job",
            "type": job_type,
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "generation_id": "old-generation",
            "profile_revision": 1,
            "result_file": result_ref,
            "error": None,
        }
    ]

    payload = client.get("/api/jobs/dependent-job").get_json()["result"]

    assert payload["stale"] is True
    assert payload["stale_reason"] == "patient_record_changed_after_generation"
    if job_type == "summary":
        assert "summary" not in payload
    else:
        assert payload["questions"][0]["stale"] is True


def test_revisionless_legacy_question_artifact_is_conservatively_stale(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    result_ref = app_module._write_job_result(
        "legacy-questions",
        {"questions": [{"text": "LEGACY GENERATED QUESTION", "source": "ai"}]},
    )
    app_module._jobs = [
        {
            "id": "legacy-questions",
            "type": "questions",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "generation_id": "old-generation",
            "profile_revision": 7,
            "result_file": result_ref,
            "error": None,
        }
    ]

    payload = client.get("/api/jobs/legacy-questions").get_json()["result"]

    assert payload["stale"] is True
    assert payload["questions"][0]["stale"] is True


def test_same_revision_superseded_question_generation_is_stale(app_client, agent, empty_profile):
    app_module, client = app_client
    empty_profile["profile_revision"] = 7
    empty_profile["questions_generation_id"] = "new-generation"
    empty_profile["appointment_questions"] = [
        {
            "id": "new",
            "text": "Current generated question",
            "source": "ai",
            "generation_job_id": "new-generation",
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    result_ref = app_module._write_job_result(
        "old-generation",
        {
            "questions": [{"text": "OBSOLETE GENERATED QUESTION", "source": "ai"}],
            "source_profile_revision": 7,
            "generation_id": "old-generation",
        },
    )
    app_module._jobs = [
        {
            "id": "old-generation",
            "type": "questions",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "generation_id": "old-generation",
            "profile_revision": 7,
            "result_file": result_ref,
            "error": None,
        }
    ]

    listed = client.get("/api/jobs").get_json()[0]
    payload = client.get("/api/jobs/old-generation").get_json()["result"]

    assert listed["derived_content_stale"] is True
    assert listed["derived_content_stale_reason"] == "question_generation_superseded"
    assert payload["stale"] is True
    assert payload["questions"][0]["stale"] is True


def test_same_generation_review_staleness_has_distinct_reason(app_client, agent, empty_profile):
    app_module, client = app_client
    empty_profile["profile_revision"] = 7
    empty_profile["questions_generation_id"] = "current-generation"
    empty_profile["appointment_questions"] = [
        {
            "id": "current",
            "text": "Generated question invalidated by correction",
            "source": "ai",
            "generation_job_id": "current-generation",
            "source_profile_revision": 7,
            "stale": True,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    result_ref = app_module._write_job_result(
        "current-generation",
        {
            "questions": copy.deepcopy(empty_profile["appointment_questions"]),
            "source_profile_revision": 7,
            "generation_id": "current-generation",
        },
    )
    app_module._jobs = [
        {
            "id": "current-generation",
            "type": "questions",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "generation_id": "current-generation",
            "profile_revision": 7,
            "result_file": result_ref,
            "error": None,
        }
    ]

    listed = client.get("/api/jobs").get_json()[0]
    assert listed["derived_content_stale_reason"] == "generated_content_invalidated"


def test_historical_stale_asked_question_does_not_poison_current_generation_artifact(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    empty_profile["profile_revision"] = 7
    empty_profile["questions_generation_id"] = "new-generation"
    empty_profile["appointment_questions"] = [
        {
            "id": "historical",
            "text": "Historical asked question",
            "source": "ai",
            "asked": True,
            "generation_job_id": "old-generation",
            "stale": True,
        },
        {
            "id": "new",
            "text": "Current generated question",
            "source": "ai",
            "generation_job_id": "new-generation",
            "stale": False,
        },
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    result_ref = app_module._write_job_result(
        "new-generation",
        {
            "questions": copy.deepcopy(empty_profile["appointment_questions"]),
            "source_profile_revision": 7,
            "generation_id": "new-generation",
        },
    )
    app_module._jobs = [
        {
            "id": "new-generation",
            "type": "questions",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "result_file": result_ref,
            "error": None,
        }
    ]

    payload = client.get("/api/jobs/new-generation").get_json()["result"]

    assert payload.get("stale") is not True
    assert payload["questions"][1]["text"] == "Current generated question"


def test_corrected_feed_report_is_retained_but_hidden_from_job_detail(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    profile, _ = _ingest(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-job")
    biomarker = next(item for item in receipt["changes"] if item["category"] == "biomarkers")
    agent.correct_change(
        profile,
        "feed-job",
        biomarker["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=biomarker["target_token"],
        replacement={"value": 243},
    )
    agent.save_profile(profile)
    report_path = app_module.DATA_DIR / "reports" / "corrected-feed.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("OBSOLETE FEED ANALYSIS", encoding="utf-8")
    app_module._jobs = [
        {
            "id": "feed-job",
            "type": "feed",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "source_document_id": profile["document_imports"][0]["source_document_id"],
            "report_file": app_module._artifact_ref(report_path),
            "summary": "OBSOLETE JOB PREVIEW",
            "key_findings": ["OBSOLETE FINDING"],
            "error": None,
        }
    ]

    job_list = client.get("/api/jobs").get_json()
    payload = client.get("/api/jobs/feed-job").get_json()

    assert job_list[0]["derived_content_stale"] is True
    assert "summary" not in job_list[0]
    assert "key_findings" not in job_list[0]
    assert payload["report_stale"] is True
    assert payload["derived_content_stale"] is True
    assert payload["derived_content_stale_reason"] == "source_document_corrected_or_undone"
    assert "summary" not in payload
    assert "key_findings" not in payload
    assert payload["report_available_for_audit"] is True
    assert "report" not in payload
    assert report_path.read_text(encoding="utf-8") == "OBSOLETE FEED ANALYSIS"


@pytest.mark.parametrize("job_type", ["digest", "deep-sweep"])
def test_profile_dependent_report_is_stale_after_revision_change(
    app_client, agent, empty_profile, job_type
):
    app_module, client = app_client
    empty_profile["profile_revision"] = 2
    agent.save_profile(empty_profile, clinical_change=False)
    report_path = app_module.DATA_DIR / "reports" / f"{job_type}.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("OBSOLETE PROFILE REPORT", encoding="utf-8")
    app_module._jobs = [
        {
            "id": f"{job_type}-job",
            "type": job_type,
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "profile_revision": 1,
            "report_file": app_module._artifact_ref(report_path),
            "error": None,
        }
    ]

    detail = client.get(f"/api/jobs/{job_type}-job").get_json()

    assert detail["derived_content_stale"] is True
    assert detail["report_stale"] is True
    assert detail["report_stale_reason"] == "patient_record_changed_after_generation"
    assert detail["report_available_for_audit"] is True
    assert "report" not in detail
    assert report_path.exists()


def test_legacy_profile_dependent_report_without_revision_is_stale(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    agent.save_profile(empty_profile, clinical_change=False)
    report_path = app_module.DATA_DIR / "reports" / "legacy-digest.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("LEGACY DIGEST REPORT", encoding="utf-8")
    app_module._jobs = [
        {
            "id": "legacy-digest",
            "type": "digest",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "report_file": app_module._artifact_ref(report_path),
            "error": None,
        }
    ]

    detail = client.get("/api/jobs/legacy-digest").get_json()

    assert detail["report_stale"] is True
    assert detail["report_stale_reason"] == "freshness_cannot_be_verified"
    assert detail["derived_content_stale_reason"] == "freshness_cannot_be_verified"
    assert "report" not in detail


def test_profile_derived_alert_becomes_inactive_after_revision_change(agent, empty_profile):
    alert = agent.execute_tool(
        "flag_alert",
        {
            "priority": "high",
            "message": "Renal function requires review",
            "action_required": "Contact the treating team",
        },
        empty_profile,
        source_job_id="digest-job",
        generation_profile_revision=4,
    )
    empty_profile["profile_revision"] = 4
    assert empty_profile["alerts"][0]["dependency_kind"] == "profile_snapshot"
    assert agent.active_alerts(empty_profile)[0]["id"] == alert["id"]

    empty_profile["profile_revision"] = 5

    assert agent.active_alerts(empty_profile) == []
    assert empty_profile["alerts"][0]["resolved"] is False
    assert "Renal function requires review" not in agent.build_chat_system(empty_profile)


def test_alert_dependency_kinds_have_distinct_lifetimes(agent, empty_profile):
    empty_profile["profile_revision"] = 4
    empty_profile["alerts"] = [
        {
            "id": "durable",
            "message": "Durable ingestion alert",
            "resolved": False,
            "dependency_kind": "durable",
            "generation_profile_revision": 1,
        },
        {
            "id": "source",
            "message": "Source-scoped alert",
            "resolved": False,
            "dependency_kind": "source",
            "source_document_id": "doc_" + "a" * 32,
            "source_dependency_active": True,
            "generation_profile_revision": 1,
        },
        {
            "id": "snapshot",
            "message": "Snapshot conclusion",
            "resolved": False,
            "dependency_kind": "profile_snapshot",
            "generation_profile_revision": 3,
        },
    ]

    assert [item["id"] for item in agent.active_alerts(empty_profile)] == [
        "durable",
        "source",
    ]

    empty_profile["profile_revision"] = 5
    assert [item["id"] for item in agent.active_alerts(empty_profile)] == [
        "durable",
        "source",
    ]
    empty_profile["alerts"][1]["source_dependency_active"] = False
    assert [item["id"] for item in agent.active_alerts(empty_profile)] == ["durable"]


def test_alert_resolution_advances_context_revision_and_preserves_durable_sibling(
    app_client, agent, empty_profile
):
    app_module, client = app_client
    empty_profile["profile_revision"] = 4
    empty_profile["alerts"] = [
        {
            "id": "first",
            "priority": "high",
            "message": "First alert",
            "resolved": False,
            "generation_profile_revision": 4,
            "source_dependency_active": True,
            "dependency_kind": "durable",
        },
        {
            "id": "second",
            "priority": "medium",
            "message": "Second alert",
            "resolved": False,
            "generation_profile_revision": 4,
            "source_dependency_active": True,
            "dependency_kind": "durable",
        },
    ]
    reports_dir = app_module.DATA_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "before-alert-resolution.md"
    report_path.write_text("OLD ALERT REPORT", encoding="utf-8")
    chat_ref = app_module._write_job_result(
        "chat-before-resolution",
        {"reply": "OLD ALERT CHAT", "source_profile_revision": 4},
    )
    app_module._jobs = [
        {
            "id": "report-before-resolution",
            "type": "deep-sweep",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "report_file": app_module._artifact_ref(report_path),
            "profile_revision": 4,
        },
        {
            "id": "chat-before-resolution",
            "type": "chat",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "result_file": chat_ref,
            "profile_revision": 4,
        },
    ]
    empty_profile["summary_stale"] = False
    empty_profile["executive_summary"] = {
        "summary_revision": 4,
        "stale": False,
        "next_actions": [{"action": "Respond to first alert"}],
    }
    empty_profile["appointment_questions"] = [
        {
            "id": "generated",
            "text": "Question based on first alert",
            "source": "ai",
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    first = next(item for item in status["alerts"] if item["id"] == "first")

    response = client.post(
        "/api/alerts/first/resolve",
        json={
            "expected_token": first["resolve_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )
    saved = agent.load_profile()

    assert response.status_code == 200
    assert saved["profile_revision"] == 5
    assert saved["alerts"][0]["resolved"] is True
    assert [item["id"] for item in agent.active_alerts(saved)] == ["second"]
    assert saved["summary_stale"] is True
    assert saved["executive_summary"]["stale"] is True
    assert saved["appointment_questions"][0]["stale"] is True
    summary_payload = client.get("/api/summary").get_json()
    assert summary_payload["status"] == "stale"
    dismissal = client.post(
        "/api/summary/dismiss-action/0",
        json={
            "expected_action": "Respond to first alert",
            "summary_revision": 4,
        },
    )
    assert dismissal.status_code == 409
    stale_chat = client.post(
        "/api/chat",
        json={
            "message": "What changed?",
            "history": [{"role": "assistant", "content": "Old alert context"}],
            "history_revision": 4,
        },
    )
    assert stale_chat.status_code == 409
    assert stale_chat.get_json()["profile_revision"] == 5
    report_task = client.get("/api/jobs/report-before-resolution").get_json()
    chat_task = client.get("/api/jobs/chat-before-resolution").get_json()
    assert report_task["derived_content_stale"] is True
    assert report_task["report_stale"] is True
    assert "report" not in report_task
    assert chat_task["derived_content_stale"] is True
    assert chat_task["result"]["stale"] is True
    assert "reply" not in chat_task["result"]


def test_chat_worker_revalidates_revision_after_model_response(
    app_client, agent, empty_profile, monkeypatch
):
    app_module, _ = app_client
    empty_profile["profile_revision"] = 4
    agent.save_profile(empty_profile, clinical_change=False)
    app_module._jobs = [
        {
            "id": "interleaved-chat",
            "type": "chat",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
        }
    ]

    def interleaving_chat(_profile, _message, _history):
        changed = agent.load_profile()
        agent.save_profile(changed)
        return "STALE MODEL RESPONSE"

    monkeypatch.setattr(agent, "handle_chat", interleaving_chat)

    app_module._run_chat_job("interleaved-chat", "Question", [], 4)

    job = next(item for item in app_module._jobs if item["id"] == "interleaved-chat")
    assert job["status"] == "error"
    assert not job.get("result_file")


def test_alert_resolution_by_id_survives_reorder_and_rejects_stale_token(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 4
    empty_profile["alerts"] = [
        {
            "id": "first",
            "priority": "high",
            "message": "First alert",
            "resolved": False,
            "generation_profile_revision": 4,
            "source_dependency_active": True,
            "dependency_kind": "durable",
        },
        {
            "id": "second",
            "priority": "medium",
            "message": "Second alert",
            "resolved": False,
            "generation_profile_revision": 4,
            "source_dependency_active": True,
            "dependency_kind": "durable",
        },
    ]
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    target = next(item for item in status["alerts"] if item["id"] == "second")

    reordered = agent.load_profile()
    reordered["alerts"].reverse()
    agent.save_profile(reordered, clinical_change=False)
    response = client.post(
        "/api/alerts/second/resolve",
        json={
            "expected_token": target["resolve_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert next(item for item in saved["alerts"] if item["id"] == "second")["resolved"] is True
    assert next(item for item in saved["alerts"] if item["id"] == "first")["resolved"] is False

    stale_status = client.get("/api/status").get_json()
    stale_target = next(item for item in stale_status["alerts"] if item["id"] == "first")
    changed = agent.load_profile()
    next(item for item in changed["alerts"] if item["id"] == "first")["message"] = "Changed alert"
    agent.save_profile(changed, clinical_change=False)
    stale = client.post(
        "/api/alerts/first/resolve",
        json={
            "expected_token": stale_target["resolve_token"],
            "expected_profile_revision": stale_status["profile_revision"],
        },
    )

    assert stale.status_code == 409
    assert (
        next(item for item in agent.load_profile()["alerts"] if item["id"] == "first")["resolved"]
        is False
    )
    assert client.post("/api/alerts/resolve/0").status_code == 410


def test_chat_rejects_history_from_prior_profile_revision(app_client, agent, empty_profile):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    agent.save_profile(empty_profile, clinical_change=False)

    response = client.post(
        "/api/chat",
        json={
            "message": "What changed?",
            "history": [{"role": "assistant", "content": "Old answer"}],
            "history_revision": 2,
        },
    )

    assert response.status_code == 409
    assert response.get_json()["profile_revision"] == 3
    assert "Clear the prior chat history" in response.get_json()["error"]


def test_chat_artifact_is_hidden_after_profile_revision_change(app_client, agent, empty_profile):
    app_module, client = app_client
    empty_profile["profile_revision"] = 5
    agent.save_profile(empty_profile, clinical_change=False)
    result_ref = app_module._write_job_result(
        "chat-job",
        {"reply": "OBSOLETE CHAT ANSWER", "source_profile_revision": 4},
    )
    app_module._jobs = [
        {
            "id": "chat-job",
            "type": "chat",
            "status": "done",
            "stage": "done",
            "created_at": "2026-08-01T12:00:00",
            "result_file": result_ref,
            "error": None,
        }
    ]

    result = client.get("/api/jobs/chat-job").get_json()["result"]

    assert result["stale"] is True
    assert "reply" not in result


def test_treatment_correction_invalidates_classification_and_chat_falls_back_raw(
    agent, empty_profile
):
    empty_profile["patient"]["current_treatments"] = ["lanreotide"]
    empty_profile["profile_revision"] = 2
    empty_profile["treatments_classified"] = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"}
    ]
    empty_profile["treatments_classification_revision"] = 2
    text = "Start everolimus"
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-01",
        "summary": "Treatment change",
        "treatment_changes": ["everolimus"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "Start everolimus",
            }
        ],
    }
    before = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, extracted = agent.run_intake(text, empty_profile)
    agent.build_import_record(before, profile, extracted, job_id="treatment-feed", text=text)
    receipt = agent.public_receipt(profile, "treatment-feed")
    treatment = next(item for item in receipt["changes"] if item["category"] == "treatments")

    assert profile["treatments_classification_revision"] is None
    agent.correct_change(
        profile,
        "treatment-feed",
        treatment["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=treatment["target_token"],
        replacement="everolimus 10 mg",
    )

    records = agent.current_treatment_records(profile)
    assert [item["text"] for item in records] == ["lanreotide", "everolimus 10 mg"]
    assert all(item["category"] == "unclassified" for item in records)
    prompt = agent.build_chat_system(profile)
    assert "[UNCLASSIFIED] lanreotide" in prompt
    assert "[UNCLASSIFIED] everolimus 10 mg" in prompt

    corrected = agent.public_receipt(profile, "treatment-feed")
    agent.undo_import(
        profile,
        "treatment-feed",
        receipt_revision=corrected["receipt_revision"],
        undo_token=corrected["undo_token"],
    )
    assert [item["text"] for item in agent.current_treatment_records(profile)] == ["lanreotide"]


def test_feed_classification_failure_keeps_raw_treatment_fallback(app_client, agent, monkeypatch):
    app_module, client = app_client
    profile = agent.load_profile()
    profile["patient"]["current_treatments"] = ["lanreotide"]
    agent.save_profile(profile)
    profile["treatments_classified"] = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"}
    ]
    profile["treatments_classification_revision"] = profile["profile_revision"]
    agent.save_profile(profile, clinical_change=False)
    app_module._jobs = [
        {
            "id": "classification-failure",
            "type": "feed",
            "status": "queued",
            "stage": "queued",
            "created_at": "2026-08-01T12:00:00",
            "error": None,
        }
    ]
    monkeypatch.setattr(agent, "run_orchestrator", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(
        agent,
        "classify_treatments",
        lambda _profile: (_ for _ in ()).throw(RuntimeError("classification failed")),
    )
    payload = {
        "document_type": "doctor_note",
        "date": "2026-08-01",
        "summary": "Treatment change",
        "treatment_changes": ["everolimus"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "Start everolimus",
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        app_module._run_feed_job("classification-failure", "Start everolimus")

    saved = agent.load_profile()
    status = client.get("/api/status").get_json()
    assert saved["treatments_classification_revision"] is None
    assert saved["patient"]["current_treatments"] == ["lanreotide", "everolimus"]
    assert status["treatments_classified"] == []
    assert status["treatments_fallback"] == ["lanreotide", "everolimus"]
    assert status["treatments_classification_current"] is False


def test_stale_and_legacy_treatment_edits_are_rejected_without_raw_mutation(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["patient"]["current_treatments"] = ["lanreotide", "everolimus"]
    empty_profile["treatments_classified"] = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"}
    ]
    empty_profile["treatments_classification_revision"] = 2
    agent.save_profile(empty_profile, clinical_change=False)

    stale_edit = client.post(
        "/api/treatments/fake-id",
        json={
            "action": "complete",
            "expected_token": "stale-token",
            "expected_profile_revision": 3,
        },
    )
    assert stale_edit.status_code == 409

    assert client.post("/api/treatments/update", json={"idx": 0}).status_code == 410
    assert client.post("/api/treatments/delete", json={"text": "everolimus"}).status_code == 410
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["lanreotide", "everolimus"]
    assert saved["treatments_classification_revision"] == 2


def _seed_current_composite_classification(agent, profile):
    profile["profile_revision"] = 3
    profile["patient"]["current_treatments"] = ["lanreotide plus everolimus"]
    agent.sync_treatment_records(profile)
    payload = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"},
        {"text": "everolimus", "label": "Everolimus", "category": "active"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile["treatments_classified"] = agent.classify_treatments(profile)
    profile["treatments_classification_revision"] = 3
    profile["treatments_classification_job_id"] = "seed"
    agent.save_profile(profile, clinical_change=False)


def test_composite_remove_by_id_preserves_sibling_after_reorder(app_client, agent, empty_profile):
    _, client = app_client
    _seed_current_composite_classification(agent, empty_profile)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    reordered = agent.load_profile()
    reordered["treatments_classified"].reverse()
    agent.save_profile(reordered, clinical_change=False)
    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "remove",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["everolimus"]
    assert [item["text"] for item in saved["treatments_classified"]] == ["everolimus"]
    assert saved["treatments_classification_revision"] == saved["profile_revision"]


def test_symbolic_composite_remove_preserves_sibling(app_client, agent, empty_profile):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["patient"]["current_treatments"] = ["lanreotide + everolimus"]
    agent.sync_treatment_records(empty_profile)
    payload = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"},
        {"text": "everolimus", "label": "Everolimus", "category": "active"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        empty_profile["treatments_classified"] = agent.classify_treatments(empty_profile)
    empty_profile["treatments_classification_revision"] = 3
    empty_profile["treatments_classification_job_id"] = "seed"
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "remove",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["everolimus"]
    assert [item["text"] for item in saved["treatments_classified"]] == ["everolimus"]


def test_surgery_and_medication_composite_preserves_surgery_on_remove(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["patient"]["current_treatments"] = ["hepatectomy and lanreotide"]
    agent.sync_treatment_records(empty_profile)
    payload = [
        {"text": "hepatectomy", "label": "Hepatectomy", "category": "completed"},
        {"text": "lanreotide", "label": "Lanreotide", "category": "active"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        empty_profile["treatments_classified"] = agent.classify_treatments(empty_profile)
    empty_profile["treatments_classification_revision"] = 3
    empty_profile["treatments_classification_job_id"] = "seed"
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "remove",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": 3,
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["hepatectomy"]
    assert [item["text"] for item in saved["treatments_classified"]] == ["hepatectomy"]


@pytest.mark.parametrize("action", ["remove", "complete"])
def test_treatment_edit_rejects_nonexclusive_uncertified_source_mapping(
    app_client, agent, empty_profile, action
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["patient"]["current_treatments"] = ["Switched from lanreotide to ABC-123"]
    records = agent.sync_treatment_records(empty_profile)
    treatment = {
        "id": "txclass_lanreotide",
        "text": "lanreotide",
        "label": "lanreotide",
        "category": "active",
        "source_treatment_ids": [records[0]["id"]],
    }
    empty_profile["treatments_classified"] = [treatment]
    empty_profile["treatments_classification_revision"] = 3
    empty_profile["treatments_classification_job_id"] = "legacy-unsafe"
    agent.save_profile(empty_profile, clinical_change=False)
    token = agent.treatment_edit_token(empty_profile, treatment)

    response = client.post(
        "/api/treatments/txclass_lanreotide",
        json={
            "action": action,
            "expected_token": token,
            "expected_profile_revision": 3,
        },
    )

    assert response.status_code == 409
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["Switched from lanreotide to ABC-123"]


@pytest.mark.parametrize(
    "raw",
    [
        "Treatment with everolimus was stopped",
        "Everolimus with dose reduction",
        "Everolimus with dose reduction due to diarrhea",
        "Lanreotide and follow-up imaging",
        "Octreotide with symptom control",
    ],
)
def test_narrative_with_is_not_split_into_meaningless_component(agent, empty_profile, raw):
    empty_profile["patient"]["current_treatments"] = [raw]
    records = agent.sync_treatment_records(empty_profile)
    assert len(records) == 1
    assert records[0]["text"] == raw


@pytest.mark.parametrize(
    "raw",
    [
        "lanreotide, everolimus",
        "lanreotide / everolimus",
        "lanreotide; everolimus",
    ],
)
def test_identity_aware_delimiters_create_disjoint_component_records(agent, empty_profile, raw):
    empty_profile["patient"]["current_treatments"] = [raw]
    records = agent.sync_treatment_records(empty_profile)
    assert [item["text"] for item in records] == ["lanreotide", "everolimus"]
    assert len({item["id"] for item in records}) == 2


def test_composite_complete_by_id_preserves_sibling_component(app_client, agent, empty_profile):
    _, client = app_client
    _seed_current_composite_classification(agent, empty_profile)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "complete",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["lanreotide [completed] plus everolimus"]
    by_text = {item["text"]: item for item in saved["treatments_classified"]}
    assert by_text["lanreotide"]["category"] == "completed"
    assert by_text["everolimus"]["category"] == "active"


def test_treatment_edit_rejects_changed_mapped_component(app_client, agent, empty_profile):
    _, client = app_client
    _seed_current_composite_classification(agent, empty_profile)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    changed = agent.load_profile()
    mapped_id = lanreotide["source_treatment_ids"][0]
    next(
        item for item in changed["patient"]["current_treatment_records"] if item["id"] == mapped_id
    )["text"] = "changed lanreotide"
    agent.save_profile(changed, clinical_change=False)
    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "remove",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": status["profile_revision"],
        },
    )

    assert response.status_code == 409
    assert len(agent.load_profile()["treatments_classified"]) == 2


def test_transition_treatment_mapping_is_exclusive_and_preserves_destination(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 3
    empty_profile["patient"]["current_treatments"] = ["Switched from lanreotide to everolimus"]
    payload = [
        {"text": "lanreotide", "label": "Lanreotide", "category": "completed"},
        {"text": "everolimus", "label": "Everolimus", "category": "active"},
    ]
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        empty_profile["treatments_classified"] = agent.classify_treatments(empty_profile)
    empty_profile["treatments_classification_revision"] = 3
    empty_profile["treatments_classification_job_id"] = "seed"
    agent.save_profile(empty_profile, clinical_change=False)
    status = client.get("/api/status").get_json()
    lanreotide = next(
        item for item in status["treatments_classified"] if item["text"] == "lanreotide"
    )

    response = client.post(
        f"/api/treatments/{lanreotide['id']}",
        json={
            "action": "remove",
            "expected_token": lanreotide["edit_token"],
            "expected_profile_revision": 3,
        },
    )

    assert response.status_code == 200
    saved = agent.load_profile()
    assert saved["patient"]["current_treatments"] == ["everolimus"]
    assert [item["text"] for item in saved["treatments_classified"]] == ["everolimus"]


def test_generated_questions_are_dynamically_stale_after_profile_revision_change(
    app_client, agent, empty_profile
):
    _, client = app_client
    empty_profile["profile_revision"] = 8
    empty_profile["questions_generation_id"] = "question-job"
    empty_profile["appointment_questions"] = [
        {
            "id": "generated",
            "text": "Question from revision seven",
            "source": "ai",
            "source_profile_revision": 7,
            "generation_job_id": "question-job",
            "stale": False,
        }
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    questions = client.get("/api/questions").get_json()

    assert questions[0]["stale"] is True
    assert questions[0]["stale_reason"] == "missing_or_superseded_generation_provenance"


@pytest.mark.parametrize(
    ("collection", "first_payload", "second_payload", "text", "expected_operation"),
    [
        (
            "symptoms",
            {
                "document_type": "doctor_note",
                "date": "2026-08-01",
                "summary": "Symptom note.",
                "symptoms_reported": [
                    {
                        "symptom": "nausea",
                        "severity": 2,
                        "source_quote": "nausea grade 2",
                    }
                ],
            },
            {
                "document_type": "doctor_note",
                "date": "2026-08-01",
                "summary": "Repeated symptom note.",
                "symptoms_reported": [
                    {
                        "symptom": "nausea",
                        "severity": 2,
                        "source_quote": "nausea grade 2",
                    }
                ],
            },
            "nausea grade 2",
            "added",
        ),
        (
            "appointments",
            {
                "document_type": "doctor_note",
                "date": "2026-08-01",
                "summary": "Appointment note.",
                "appointments": [
                    {
                        "date": "2026-09-01",
                        "description": "Oncology review",
                        "type": "review",
                        "source_quote": "Oncology review 2026-09-01",
                    }
                ],
            },
            {
                "document_type": "doctor_note",
                "date": "2026-08-01",
                "summary": "Repeated appointment note.",
                "appointments": [
                    {
                        "date": "2026-09-01",
                        "description": "Oncology review",
                        "type": "review",
                        "source_quote": "Oncology review 2026-09-01",
                    }
                ],
            },
            "Oncology review 2026-09-01",
            "unchanged",
        ),
    ],
)
def test_later_duplicate_claim_preserves_symptoms_but_blocks_deduplicated_collections(
    agent,
    empty_profile,
    collection,
    first_payload,
    second_payload,
    text,
    expected_operation,
):
    before_first = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(first_payload))):
        profile, extracted = agent.run_intake(text, empty_profile)
    agent.build_import_record(before_first, profile, extracted, job_id="first", text=text)

    before_second = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(second_payload))):
        profile, extracted = agent.run_intake(text, profile)
    agent.build_import_record(before_second, profile, extracted, job_id="second", text=text)

    second_receipt = agent.public_receipt(profile, "second")
    repeated = next(item for item in second_receipt["changes"] if item["category"] == collection)
    first_receipt = agent.public_receipt(profile, "first")
    original = next(item for item in first_receipt["changes"] if item["category"] == collection)

    assert repeated["operation"] == expected_operation
    if collection == "symptoms":
        assert repeated["target"]["record_id"] != original["target"]["record_id"]
        assert original["conflicted"] is False
        assert first_receipt["can_undo"] is True
    else:
        assert repeated["target"]["record_id"] == original["target"]["record_id"]
        assert original["conflicted"] is True
        assert "later document" in original["conflict_reason"]
        assert first_receipt["can_undo"] is False


def test_synonym_deduplicated_treatment_blocks_older_undo(agent, empty_profile):
    first_payload = {
        "document_type": "doctor_note",
        "date": "2026-08-01",
        "summary": "Treatment started.",
        "treatment_changes": ["Somatuline 120mg q4w"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "Somatuline 120mg q4w",
            }
        ],
    }
    second_payload = {
        "document_type": "doctor_note",
        "date": "2026-08-02",
        "summary": "Same treatment restated.",
        "treatment_changes": ["lanreotide 120mg q4w"],
        "evidence": [
            {
                "field": "treatment_changes",
                "item_index": 0,
                "source_quote": "lanreotide 120mg q4w",
            }
        ],
    }
    before_first = copy.deepcopy(empty_profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(first_payload))):
        profile, extracted = agent.run_intake("Somatuline 120mg q4w", empty_profile)
    agent.build_import_record(
        before_first,
        profile,
        extracted,
        job_id="first",
        text="Somatuline 120mg q4w",
    )

    before_second = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(second_payload))):
        profile, extracted = agent.run_intake("lanreotide 120mg q4w", profile)
    agent.build_import_record(
        before_second,
        profile,
        extracted,
        job_id="second",
        text="lanreotide 120mg q4w",
    )

    later = next(
        item
        for item in agent.public_receipt(profile, "second")["changes"]
        if item["category"] == "treatments"
    )
    older = next(
        item
        for item in agent.public_receipt(profile, "first")["changes"]
        if item["category"] == "treatments"
    )

    assert later["operation"] == "unchanged"
    assert later["effective_value"] == "Somatuline 120mg q4w"
    assert older["conflicted"] is True
