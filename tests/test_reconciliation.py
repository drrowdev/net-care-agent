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
    assert profile["alerts"] == []


@pytest.mark.parametrize(
    "replacement",
    [
        {"date": None},
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
    assert agent.active_alerts(agent.load_profile()) == []


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
            "result_file": result_ref,
            "error": None,
        }
    ]

    payload = client.get("/api/jobs/old-generation").get_json()["result"]

    assert payload["stale"] is True
    assert payload["questions"][0]["stale"] is True


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
    assert agent.active_alerts(empty_profile)[0]["id"] == alert["id"]

    empty_profile["profile_revision"] = 5

    assert agent.active_alerts(empty_profile) == []
    assert empty_profile["alerts"][0]["resolved"] is False
    assert "Renal function requires review" not in agent.build_chat_system(empty_profile)


def test_resolving_one_alert_does_not_expire_sibling_versioned_alert(
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
        },
        {
            "id": "second",
            "priority": "medium",
            "message": "Second alert",
            "resolved": False,
            "generation_profile_revision": 4,
            "source_dependency_active": True,
        },
    ]
    agent.save_profile(empty_profile, clinical_change=False)

    response = client.post("/api/alerts/resolve/0")
    saved = agent.load_profile()

    assert response.status_code == 200
    assert saved["profile_revision"] == 4
    assert saved["alerts"][0]["resolved"] is True
    assert [item["id"] for item in agent.active_alerts(saved)] == ["second"]


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
    ("collection", "first_payload", "second_payload", "text"),
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
        ),
    ],
)
def test_later_deduplicated_claim_blocks_older_undo(
    agent,
    empty_profile,
    collection,
    first_payload,
    second_payload,
    text,
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

    assert repeated["operation"] == "unchanged"
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
