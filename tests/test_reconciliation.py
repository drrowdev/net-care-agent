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
