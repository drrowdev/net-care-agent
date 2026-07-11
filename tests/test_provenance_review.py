"""Evidence provenance, lifecycle review, feedback, and API regression tests."""

from __future__ import annotations

import importlib
import json

import pytest

from tests._llm_fake import llm_text, patch_llm


@pytest.fixture
def client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def test_intake_preserves_immutable_source_and_exact_evidence(agent, empty_profile):
    text = "CgA:\t234 ng/mL (reference 0-100)."
    payload = {
        "document_type": "lab_result",
        "date": "2026-07-10",
        "summary": "Elevated CgA.",
        "biomarkers": [
            {
                "marker": "CgA",
                "value": 234,
                "unit": "ng/mL",
                "source_quote": "cga: 234 NG/ML (reference 0-100).",
            }
        ],
        "key_findings": ["CgA elevated"],
        "evidence": [{"field": "key_findings", "item_index": 0, "source_quote": "not in source"}],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake(text, empty_profile)

    source = profile["source_documents"][0]
    document = profile["documents"][0]
    biomarker = profile["biomarkers"][0]
    assert source["id"] == document["source_document_id"] == biomarker["source_document_id"]
    assert source["ingested_at"] == document["added_at"]
    assert biomarker["source_quote"] == text
    assert biomarker["evidence_status"] == "verified"
    assert text[biomarker["evidence_start"] : biomarker["evidence_end"]] == text
    assert document["evidence"][0]["evidence_status"] == "invalid"
    assert document["evidence"][0]["source_quote"] is None
    assert (agent.DATA_DIR / source["text"]["path"]).read_text(encoding="utf-8") == text
    assert len(source["source"]["sha256"]) == 64


def test_missing_quote_is_explicit_and_never_fabricated(agent, empty_profile):
    payload = {
        "document_type": "lab_result",
        "biomarkers": [{"marker": "NSE", "value": 20}],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake("NSE result unavailable", empty_profile)
    biomarker = profile["biomarkers"][0]
    assert biomarker["evidence_status"] == "missing"
    assert biomarker["source_quote"] is None


def test_unicode_expansion_cannot_verify_partial_numeric_quote(agent):
    from agent.provenance import anchor_source_quote

    assert anchor_source_quote("Dose: ½ mg", "1")["evidence_status"] == "invalid"
    assert anchor_source_quote("Dose: ½ mg", "2")["evidence_status"] == "invalid"
    exact = anchor_source_quote("Dose: ½ mg", "½")
    assert exact["evidence_status"] == "verified"
    assert exact["source_quote"] == "½"


def test_failed_intake_removes_new_source_artifacts(agent, empty_profile, monkeypatch):
    from agent import intake

    before = json.loads(json.dumps(empty_profile))
    source_root = agent.DATA_DIR / "source_documents"
    before_dirs = set(source_root.iterdir()) if source_root.exists() else set()
    monkeypatch.setattr(
        intake,
        "_extract_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        agent.run_intake("clinical source text", empty_profile)

    assert empty_profile == before
    after_dirs = set(source_root.iterdir()) if source_root.exists() else set()
    assert after_dirs == before_dirs


def test_orchestrator_failure_keeps_successful_intake_and_indexed_source(
    client,
    agent,
    monkeypatch,
):
    import app as app_module

    payload = {
        "document_type": "doctor_note",
        "date": "2026-07-10",
        "summary": "Important note",
    }
    monkeypatch.setattr(app_module, "_update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        agent,
        "run_orchestrator",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("research failed")),
    )

    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        app_module._run_feed_job("job", "Important source text")

    saved = agent.load_profile()
    assert saved["documents"][-1]["summary"] == "Important note"
    source = saved["source_documents"][-1]
    assert (agent.DATA_DIR / source["text"]["path"]).exists()


def test_list_evidence_requires_matching_item_index(agent, empty_profile):
    payload = {
        "document_type": "doctor_note",
        "key_findings": ["First supported finding", "Second unsupported finding"],
        "evidence": [
            {
                "field": "key_findings",
                "item_index": None,
                "source_quote": "First supported finding",
            }
        ],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake("First supported finding", empty_profile)
    evidence = profile["documents"][0]["evidence"]
    assert [item["evidence_status"] for item in evidence] == ["missing", "missing"]


def test_source_and_evidence_endpoints_hide_paths_and_block_tampering(client, agent, empty_profile):
    payload = {
        "document_type": "doctor_note",
        "summary": "Follow-up",
        "biomarkers": [{"marker": "CgA", "value": 42, "source_quote": "CgA 42"}],
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        profile, _ = agent.run_intake("CgA 42", empty_profile)
    agent.save_profile(profile)
    source_id = profile["source_documents"][0]["id"]
    evidence = profile["biomarkers"][0]

    metadata = client.get(f"/api/sources/{source_id}")
    assert metadata.status_code == 200
    assert "path" not in json.dumps(metadata.get_json())
    span = client.get(
        f"/api/evidence/{source_id}?start={evidence['evidence_start']}"
        f"&end={evidence['evidence_end']}"
    )
    assert span.get_json()["quote"] == "CgA 42"

    text_path = agent.DATA_DIR / profile["source_documents"][0]["text"]["path"]
    text_path.write_text("tampered", encoding="utf-8")
    assert client.get(f"/api/sources/{source_id}/text").status_code == 409
    text_path.write_text("CgA 42", encoding="utf-8")

    profile["source_documents"][0]["text"]["path"] = "../patient_profile.json"
    agent.save_profile(profile)
    assert client.get(f"/api/sources/{source_id}/text").status_code == 404


def test_non_ascii_source_length_is_bytes_and_artifact_is_retrievable(client, agent, empty_profile):
    text = "Ki-67 är 12 %"
    with patch_llm(
        agent,
        lambda **_: llm_text(json.dumps({"document_type": "pathology_report"})),
    ):
        profile, _ = agent.run_intake(text, empty_profile)
    agent.save_profile(profile)
    source = profile["source_documents"][0]
    assert source["text"]["length"] == len(text.encode("utf-8"))
    response = client.get(f"/api/sources/{source['id']}/text")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == text


def test_source_endpoint_requires_identity_when_hosted(client, monkeypatch):
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")
    assert client.get("/api/sources/doc_" + "0" * 32).status_code == 401


def test_questions_regeneration_preserves_asked_ai_and_dedupes(client, agent, monkeypatch):
    profile = agent.load_profile()
    profile["appointment_questions"] = [
        {"id": "asked", "text": "Was the scan stable?", "source": "ai", "asked": True},
        {"id": "old", "text": "Old unanswered?", "source": "ai", "asked": False},
        {"id": "manual", "text": "My manual question", "source": "manual", "asked": False},
    ]
    agent.save_profile(profile, clinical_change=False)
    generated = [
        {"id": "duplicate", "text": "  Was the scan stable? ", "source": "ai", "asked": False},
        {"id": "new", "text": "What is next?", "source": "ai", "asked": False},
    ]
    monkeypatch.setattr(agent, "generate_questions_for_profile", lambda *_: generated)
    response = client.post("/api/questions/generate", json={})
    texts = [item["text"].strip() for item in response.get_json()]
    assert texts == ["Was the scan stable?", "My manual question", "What is next?"]


def test_questions_regeneration_replaces_colliding_ids(client, agent, monkeypatch):
    profile = agent.load_profile()
    profile["appointment_questions"] = [
        {"id": "collision", "text": "Asked history", "source": "ai", "asked": True},
    ]
    agent.save_profile(profile, clinical_change=False)
    monkeypatch.setattr(
        agent,
        "generate_questions_for_profile",
        lambda *_: [
            {"id": "collision", "text": "New distinct question", "source": "ai", "asked": False}
        ],
    )

    response = client.post("/api/questions/generate", json={})

    assert response.status_code == 200
    ids = [item["id"] for item in response.get_json()]
    assert len(ids) == len(set(ids)) == 2


def test_judgment_lifecycle_excludes_expired_constraints(agent):
    profile = {
        "clinical_judgments": [
            {
                "id": "expired",
                "category": "constraint",
                "text": "Never use treatment X",
                "status": "active",
                "valid_until": "2000-01-01",
            },
            {
                "id": "active",
                "category": "constraint",
                "text": "Avoid treatment Y",
            },
        ]
    }
    context = agent.get_clinical_judgments_context(profile)
    active_section, review_section = context.split("⚠ NEEDS CLINICIAN REVIEW")
    assert "Avoid treatment Y" in active_section
    assert "Never use treatment X" not in active_section
    assert "Never use treatment X" in review_section


def test_judgment_lifecycle_transition_marks_summary_stale(client, agent):
    profile = agent.load_profile()
    judgment = {
        "id": "j1",
        "date": "2026-01-01",
        "category": "constraint",
        "text": "Avoid treatment X",
        "status": "active",
    }
    profile["clinical_judgments"] = [judgment]
    profile["profile_revision"] = 4
    profile["summary_stale"] = False
    profile["executive_summary"] = {
        "summary_revision": 4,
        "stale": False,
        "judgment_context_hash": agent.clinical_judgments_fingerprint(profile),
    }
    agent.save_profile(profile, clinical_change=False)

    # Simulate time/lifecycle advancement without another clinical write.
    stored = agent.load_profile()
    stored["clinical_judgments"][0]["review_after"] = "2000-01-01"
    agent.save_profile(stored, clinical_change=False)

    payload = client.get("/api/summary").get_json()
    assert payload["judgment_context_changed"] is True
    assert payload["stale"] is True


def test_judgment_api_applies_validated_supersession(client, agent):
    first = client.post(
        "/api/judgments/add",
        json={"text": "Old constraint", "category": "constraint"},
    ).get_json()
    replacement = client.post(
        "/api/judgments/add",
        json={
            "text": "Updated constraint",
            "category": "constraint",
            "scope": "PRRT",
            "status": "active",
            "review_after": "2027-01-01",
            "supersedes": first["id"],
        },
    )
    assert replacement.status_code == 200
    stored = agent.load_profile()["clinical_judgments"]
    assert next(item for item in stored if item["id"] == first["id"])["status"] == "superseded"
    assert replacement.get_json()["scope"] == "PRRT"
    invalid = client.post(
        "/api/judgments/add",
        json={"text": "Bad replacement", "supersedes": "does-not-exist"},
    )
    assert invalid.status_code == 400


def test_superseded_judgment_cannot_be_reactivated_with_active_successor(client):
    first = client.post(
        "/api/judgments/add",
        json={"text": "Old constraint", "category": "constraint"},
    ).get_json()
    client.post(
        "/api/judgments/add",
        json={"text": "Replacement", "category": "constraint", "supersedes": first["id"]},
    )
    response = client.patch(
        f"/api/judgments/{first['id']}",
        json={"status": "active"},
    )
    assert response.status_code == 409


def test_legacy_document_and_summary_freshness_payload(client, agent):
    profile = agent.load_profile()
    profile["documents"] = [
        {
            "date": "2020-01-01",
            "type": "doctor_note",
            "summary": "Legacy preview",
            "raw_text": "legacy raw text",
        }
    ]
    profile["profile_revision"] = 7
    profile["summary_stale"] = True
    profile["executive_summary"] = {
        "overall_status": "stable",
        "status_confidence": "medium",
        "status_rationale": "Imaging is old.",
        "generated_at": "2026-07-10",
        "generated_at_timestamp": "2026-07-10T21:00:00",
        "summary_revision": 6,
        "stale": True,
    }
    agent.save_profile(profile, clinical_change=False)
    loaded = agent.load_profile()
    assert loaded["documents"][0]["raw_text"] == "legacy raw text"
    response = client.get("/api/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status_confidence"] == "medium"
    assert payload["status_rationale"] == "Imaging is old."
    assert payload["profile_revision"] == 7
    assert payload["summary_revision"] == 6
    assert payload["stale"] is True
    assert payload["generated_at_timestamp"] == "2026-07-10T21:00:00"
    assert payload["source_links"] == []


def test_feedback_records_only_and_conservatively_invalidates_summary(client, agent):
    profile = agent.load_profile()
    profile["executive_summary"] = {"summary_revision": 1, "stale": False}
    profile["summary_stale"] = False
    profile["profile_revision"] = 1
    agent.save_profile(profile, clinical_change=False)
    before_patient = json.loads(json.dumps(profile["patient"]))
    response = client.post(
        "/api/feedback",
        json={
            "target": "summary",
            "item_id": "current",
            "assessment": "missed",
            "note": "A recent symptom was omitted",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["summary_invalidated"] is True
    feedback_id = response.get_json()["feedback"]["id"]
    updated = client.patch(
        f"/api/feedback/{feedback_id}",
        json={"assessment": "acted", "outcome": "Raised with the clinician"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["feedback"]["outcome"] == "Raised with the clinician"
    stored = agent.load_profile()
    assert stored["patient"] == before_patient
    assert stored["feedback"][0]["assessment"] == "acted"
    assert stored["summary_stale"] is True


def test_corrective_action_dismissal_invalidates_summary(client, agent):
    profile = agent.load_profile()
    profile["profile_revision"] = 4
    profile["summary_stale"] = False
    profile["executive_summary"] = {
        "summary_revision": 4,
        "stale": False,
        "next_actions": [{"action": "Discuss option X"}],
    }
    agent.save_profile(profile, clinical_change=False)

    response = client.post(
        "/api/summary/dismiss-action/0",
        json={"feedback": "This was already ruled out"},
    )

    assert response.status_code == 200
    stored = agent.load_profile()
    assert stored["summary_stale"] is True
    assert stored["executive_summary"]["stale"] is True
    assert stored["executive_summary"]["review_feedback_pending"] is True
    assert stored["feedback"][0]["assessment"] == "corrected"


def test_deep_sweep_truncation_is_explicit_and_raw_reports_survive(agent, empty_profile):
    def handler(**kwargs):
        if "SYNTHESISER" in str(kwargs.get("system", "")):
            return llm_text("partial synthesis", stop_reason="max_tokens")
        return llm_text("Raw grounded report")

    with patch_llm(agent, handler):
        result = agent.run_deep_sweep(
            empty_profile,
            models=["claude-opus-4-8"],
            synthesis_model="claude-opus-4-8",
        )
    assert result["truncated"] is True
    assert "Synthesis step failed" in result["report"]
    assert "Raw grounded report" in result["report"]
    assert "Reference verification" in result["report"]
    assert result["synthesis"]["stop_reason"] == "max_tokens"
