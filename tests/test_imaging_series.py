from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from tests._llm_fake import llm_text, patch_llm


def _row(row_id: str, date: str | None, **overrides):
    row = {
        "id": row_id,
        "date": date,
        "date_precision": (
            "day"
            if isinstance(date, str) and len(date) == 10
            else "month"
            if isinstance(date, str) and len(date) == 7
            else "year"
            if isinstance(date, str) and len(date) == 4
            else "unknown"
        ),
        "date_kind": "study" if date else "unknown",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
        "modality": "CT",
        "findings": "Exact stored finding",
        "impression": "Exact stored impression",
        "new_lesions": None,
        "evidence_status": "missing",
    }
    row.update(overrides)
    return row


def _project(agent, rows, **profile_overrides):
    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    profile["profile_revision"] = profile_overrides.pop("profile_revision", 3)
    profile["workflow_revision"] = profile_overrides.pop("workflow_revision", 4)
    profile["imaging"] = rows
    profile.update(profile_overrides)
    return agent.project_imaging_series(profile)


def _ingest_imaging(agent, profile, *, job_id="feed-imaging"):
    text = (
        "CT abdomen 2026-03-15: target liver lesion increased from 2.1 cm "
        "to 3.0 cm since 2025-12-10, consistent with progression."
    )
    quote = (
        "target liver lesion increased from 2.1 cm to 3.0 cm since "
        "2025-12-10, consistent with progression"
    )
    payload = {
        "document_type": "imaging_report",
        "date": "2026-03-15",
        "source_document_date": "2026-03-16",
        "summary": "Stored report summary",
        "imaging_findings": {
            "modality": "CT",
            "findings": "target liver lesion increased from 2.1 cm to 3.0 cm",
            "impression": "consistent with progression",
            "new_lesions": False,
            "source_quote": quote,
        },
    }
    before = copy.deepcopy(profile)
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        updated, extracted = agent.run_intake(text, profile)
    agent.build_import_record(before, updated, extracted, job_id=job_id, text=text)
    return updated


def test_projection_preserves_every_row_and_explicit_date_uncertainty(agent):
    rows = [
        _row("exact", "2026-03-15"),
        _row(
            "partial",
            "2026-04",
            date_kind="legacy_unknown",
            modality="MRI liver",
            findings="Stored partial-date wording",
        ),
        _row(
            "unknown",
            None,
            modality=None,
            findings=None,
            impression="Undated manual entry",
        ),
    ]

    projection = _project(agent, rows)

    assert projection["profile_revision"] == 3
    assert projection["workflow_revision"] == 4
    assert projection["source_row_count"] == 3
    assert [record["id"] for record in projection["records"]] == [
        "exact",
        "partial",
        "unknown",
    ]
    assert projection["records"][1]["date"] == {
        "value": "2026-04",
        "precision": "month",
        "kind": "legacy_unknown",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }
    assert projection["records"][2]["provenance"]["status"] == "unverified"


def test_projection_never_collapses_duplicates_or_exposes_lossy_private_fields(agent):
    rows = [
        _row(
            "one",
            "2026-03-15",
            source_document_id="doc_same",
            new_lesions=True,
            legacy_extra={"nested": ["kept"]},
        ),
        _row(
            "two",
            "2026-03-15",
            source_document_id="doc_same",
            new_lesions=True,
            legacy_extra={"nested": ["kept"]},
        ),
    ]

    projection = _project(agent, rows)
    serialized = json.dumps(projection)

    assert projection["source_row_count"] == len(projection["records"]) == 2
    assert [record["id"] for record in projection["records"]] == ["one", "two"]
    assert "new_lesions" not in serialized
    assert "legacy_extra" not in serialized
    assert "source_document_id" not in serialized

    changed = copy.deepcopy(rows)
    changed[0]["new_lesions"] = False
    changed_projection = _project(agent, changed)
    assert changed_projection["records"][0]["token"] != projection["records"][0]["token"]
    assert changed_projection["projection_token"] != projection["projection_token"]


def test_projection_order_and_token_do_not_depend_on_profile_list_order(agent):
    rows = [_row("later", "2026-05-01"), _row("earlier", "2026-01-01")]

    forward = _project(agent, copy.deepcopy(rows))
    reverse = _project(agent, list(reversed(copy.deepcopy(rows))))

    assert reverse == forward


def test_tokens_bind_both_revisions_and_document_lifecycle(agent):
    row = _row("one", "2026-01-01", source_document_id="missing-source")
    base = _project(agent, [copy.deepcopy(row)])
    workflow = _project(agent, [copy.deepcopy(row)], workflow_revision=5)
    clinical = _project(agent, [copy.deepcopy(row)], profile_revision=5)
    excluded = _project(
        agent,
        [copy.deepcopy(row)],
        documents=[
            {
                "id": "document",
                "source_document_id": "missing-source",
                "excluded_from_clinical_context": True,
            }
        ],
    )

    assert (
        len(
            {
                base["projection_token"],
                workflow["projection_token"],
                clinical["projection_token"],
                excluded["projection_token"],
            }
        )
        == 4
    )
    assert (
        len(
            {
                base["records"][0]["token"],
                workflow["records"][0]["token"],
                clinical["records"][0]["token"],
                excluded["records"][0]["token"],
            }
        )
        == 4
    )


def test_verified_source_is_validated_once_and_uses_opaque_row_routes(
    agent, empty_profile, monkeypatch
):
    text = "CT 2026-03-15: exact report-authored wording."
    source = agent.preserve_source_document(text)
    anchored = agent.anchor_source_quote(text, "exact report-authored wording")
    rows = [
        _row(
            "one",
            "2026-03-15",
            source_document_id=source["id"],
            **anchored,
        ),
        _row(
            "two",
            "2026-03-15",
            source_document_id=source["id"],
            findings="Second stored row",
            evidence_status="missing",
        ),
    ]
    profile = copy.deepcopy(empty_profile)
    profile["imaging"] = rows
    profile["source_documents"] = [source]
    module = importlib.import_module("agent.imaging_series")
    original_validate = module.validate_source_artifact
    validations = []

    def counted_validate(source_record, artifact, content):
        validations.append((source_record["id"], artifact))
        return original_validate(source_record, artifact, content)

    monkeypatch.setattr(module, "validate_source_artifact", counted_validate)
    projection = agent.project_imaging_series(profile)
    first = projection["records"][0]
    serialized = json.dumps(projection)

    assert validations == [(source["id"], "text")]
    assert first["provenance"]["source_url"].startswith("/api/patient/imaging-series/imref_")
    assert first["provenance"]["source_url"].endswith("/source")
    assert first["provenance"]["evidence_url"] == first["provenance"]["source_url"].replace(
        "/source", "/evidence"
    )
    assert "/one/" not in first["provenance"]["source_url"]
    for forbidden in (
        source["id"],
        "evidence_start",
        "evidence_end",
        "source_quote",
        '"path"',
        "?start=",
        "?end=",
    ):
        assert forbidden not in serialized


def test_source_tampering_fails_the_complete_projection(agent, empty_profile):
    text = "CT exact wording"
    source = agent.preserve_source_document(text)
    profile = copy.deepcopy(empty_profile)
    profile["imaging"] = [_row("one", "2026-01-01", source_document_id=source["id"])]
    profile["source_documents"] = [source]
    (agent.DATA_DIR / source["text"]["path"]).write_text("tampered", encoding="utf-8")

    with pytest.raises(agent.ImagingProjectionError) as exc:
        agent.project_imaging_series(profile)

    assert exc.value.code == "imaging_projection_invalid"
    assert "source authority" in exc.value.public_message


def test_inconsistent_receipt_fails_the_complete_projection(agent, empty_profile):
    profile = _ingest_imaging(agent, empty_profile)
    change = next(
        item
        for item in profile["document_imports"][0]["changes"]
        if item.get("target", {}).get("collection") == "imaging"
    )
    change["effective_value"]["findings"] = "Conflicting receipt wording"

    with pytest.raises(agent.ImagingProjectionError) as exc:
        agent.project_imaging_series(profile)

    assert exc.value.code == "imaging_projection_invalid"
    assert "source authority" in exc.value.public_message


def test_correction_and_undo_update_projection_authority(agent, empty_profile):
    profile = _ingest_imaging(agent, empty_profile)
    initial = agent.project_imaging_series(profile)
    receipt = agent.public_receipt(profile, "feed-imaging")
    change = next(item for item in receipt["changes"] if item["category"] == "imaging")

    agent.correct_change(
        profile,
        "feed-imaging",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
        replacement={
            "date": "2026-03",
            "date_kind": "unknown",
            "modality": "CT abdomen",
        },
    )
    corrected = agent.project_imaging_series(profile)
    record = corrected["records"][0]

    assert corrected["projection_token"] != initial["projection_token"]
    assert record["date"]["precision"] == "month"
    assert record["date"]["kind"] == "unknown"
    assert record["modality"] == "CT abdomen"
    assert record["provenance"]["status"] == "caregiver_corrected_unverified"
    assert record["provenance"]["evidence_url"] is None

    refreshed = agent.public_receipt(profile, "feed-imaging")
    agent.undo_import(
        profile,
        "feed-imaging",
        receipt_revision=refreshed["receipt_revision"],
        undo_token=refreshed["undo_token"],
    )
    undone = agent.project_imaging_series(profile)
    assert undone["source_row_count"] == 0
    assert undone["records"] == []


def test_imaging_correction_supports_null_dates_and_separate_source_date(agent, empty_profile):
    profile = _ingest_imaging(agent, empty_profile)
    receipt = agent.public_receipt(profile, "feed-imaging")
    change = next(item for item in receipt["changes"] if item["category"] == "imaging")

    agent.correct_change(
        profile,
        "feed-imaging",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
        replacement={
            "date": None,
            "date_kind": "unknown",
            "source_document_date": "2026-03",
            "modality": "Exact legacy modality wording",
        },
    )

    row = profile["imaging"][0]
    assert row["date"] is None
    assert row["date_precision"] == "unknown"
    assert row["date_kind"] == "unknown"
    assert row["source_document_date"] == "2026-03"
    assert row["source_document_date_precision"] == "month"
    assert row["modality"] == "Exact legacy modality wording"


def test_valid_incomplete_rows_remain_visible_but_invalid_authority_aborts(agent):
    incomplete = _row("incomplete", None, modality=None, findings=None, impression=None)
    projection = _project(agent, [incomplete])
    assert projection["records"][0]["date"]["kind"] == "unknown"

    with pytest.raises(agent.ImagingProjectionError):
        _project(agent, [{**incomplete, "id": "same"}, {**incomplete, "id": "same"}])
    with pytest.raises(agent.ImagingProjectionError):
        _project(agent, [{**incomplete, "legacy_extra": float("nan")}])
    with pytest.raises(agent.ImagingProjectionError):
        _project(agent, [{**incomplete, "date_precision": "day"}])
    with pytest.raises(agent.ImagingProjectionError):
        _project(agent, ["not-a-row"])
    with pytest.raises(agent.ImagingProjectionError):
        _project(agent, [incomplete], profile_revision="bad")


def test_projection_row_limit_fails_without_partial_payload(agent):
    from agent.imaging_series import MAX_IMAGING_ROWS

    rows = [_row(f"row-{index}", "2026-01-01") for index in range(MAX_IMAGING_ROWS + 1)]
    with pytest.raises(agent.ImagingProjectionError) as exc:
        _project(agent, rows)
    assert exc.value.code == "imaging_projection_too_large"


def test_projection_source_and_authority_limits_fail_without_partial_payload(agent):
    from agent.imaging_series import (
        MAX_AUTHORITY_BYTES,
        MAX_SOURCE_TEXT_BYTES,
        MAX_TOTAL_SOURCE_TEXT_BYTES,
        MAX_UNIQUE_SOURCES,
    )

    unique_source_rows = [
        _row(f"row-{index}", "2026-01-01", source_document_id=f"source-{index}")
        for index in range(MAX_UNIQUE_SOURCES + 1)
    ]
    with pytest.raises(agent.ImagingProjectionError) as exc:
        _project(agent, unique_source_rows)
    assert exc.value.code == "imaging_projection_too_large"

    with pytest.raises(agent.ImagingProjectionError) as exc:
        _project(
            agent,
            [_row("authority", "2026-01-01", legacy_extra="x" * (MAX_AUTHORITY_BYTES + 1))],
        )
    assert exc.value.code == "imaging_projection_too_large"

    source = {
        "id": "oversized-source",
        "source": {"path": "unused", "sha256": "a" * 64, "length": 1},
        "text": {
            "path": "unused",
            "sha256": "b" * 64,
            "length": MAX_SOURCE_TEXT_BYTES + 1,
        },
    }
    with pytest.raises(agent.ImagingProjectionError) as exc:
        _project(
            agent,
            [_row("oversized-text", "2026-01-01", source_document_id=source["id"])],
            source_documents=[source],
        )
    assert exc.value.code == "imaging_projection_too_large"

    per_source = MAX_SOURCE_TEXT_BYTES
    source_count = MAX_TOTAL_SOURCE_TEXT_BYTES // per_source + 1
    sources = [
        {
            "id": f"aggregate-{index}",
            "source": {"path": "unused", "sha256": "a" * 64, "length": 1},
            "text": {"path": "unused", "sha256": "b" * 64, "length": per_source},
        }
        for index in range(source_count)
    ]
    rows = [
        _row(f"aggregate-row-{index}", "2026-01-01", source_document_id=source["id"])
        for index, source in enumerate(sources)
    ]
    with pytest.raises(agent.ImagingProjectionError) as exc:
        _project(agent, rows, source_documents=sources)
    assert exc.value.code == "imaging_projection_too_large"


@pytest.fixture
def app_client(agent):
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    app_module._initialized = True
    with app_module.app.test_client() as client:
        yield app_module, client


def test_imaging_endpoint_is_no_store_complete_and_read_only(app_client, agent):
    _, client = app_client
    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    profile["profile_revision"] = 7
    profile["workflow_revision"] = 8
    profile["imaging"] = [_row("one", "2026-01-01")]
    agent.save_profile(profile, clinical_change=False)
    before = agent.PROFILE_PATH.read_bytes()

    response = client.get("/api/patient/imaging-series")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.get_json()["profile_revision"] == 7
    assert response.get_json()["workflow_revision"] == 8
    assert response.get_json()["source_row_count"] == 1
    assert agent.PROFILE_PATH.read_bytes() == before


def test_imaging_endpoint_maps_projection_failures_to_bounded_422(app_client, monkeypatch):
    app_module, client = app_client
    malformed = copy.deepcopy(app_module.agent.DEFAULT_PROFILE)
    malformed["imaging"] = [{"id": "same"}, {"id": "same"}]
    monkeypatch.setattr(app_module.agent, "load_profile", lambda: malformed)

    response = client.get("/api/patient/imaging-series")

    assert response.status_code == 422
    assert response.get_json() == {
        "code": "imaging_projection_invalid",
        "error": "Imaging identity is missing or inconsistent.",
    }


def test_imaging_endpoint_and_opaque_routes_require_hosted_identity(app_client, monkeypatch):
    _, client = app_client
    monkeypatch.setenv("WEBSITE_AUTH_ENABLED", "true")

    assert client.get("/api/patient/imaging-series").status_code == 401
    assert client.get("/api/patient/imaging-series/row/source").status_code == 401
    assert client.get("/api/patient/imaging-series/row/evidence").status_code == 401


def test_opaque_source_and_evidence_routes_serve_validated_text(app_client, agent):
    _, client = app_client
    profile = _ingest_imaging(agent, copy.deepcopy(agent.DEFAULT_PROFILE))
    agent.save_profile(profile, clinical_change=False)
    row = profile["imaging"][0]
    record = client.get("/api/patient/imaging-series").get_json()["records"][0]

    source = client.get(record["provenance"]["source_url"])
    evidence = client.get(record["provenance"]["evidence_url"])

    assert source.status_code == 200
    assert evidence.status_code == 200
    assert "no-store" in source.headers["Cache-Control"]
    assert "no-store" in evidence.headers["Cache-Control"]
    assert "CT abdomen 2026-03-15" in source.get_data(as_text=True)
    assert evidence.get_data(as_text=True) == row["source_quote"]
    assert "start" not in source.headers.get("Content-Location", "")
    assert "end" not in evidence.headers.get("Content-Location", "")
    ignored_query = client.get(
        f"{record['provenance']['evidence_url']}?source_id=other&start=0&end=1"
    )
    assert ignored_query.get_data(as_text=True) == row["source_quote"]


def test_opaque_routes_support_preserved_legacy_ids_with_reserved_characters(app_client, agent):
    _, client = app_client
    text = "MRI 2026-03-15: exact source wording."
    source = agent.preserve_source_document(text)
    anchored = agent.anchor_source_quote(text, "exact source wording")
    profile = copy.deepcopy(agent.DEFAULT_PROFILE)
    profile["imaging"] = [
        _row(
            "legacy/row?reserved",
            "2026-03-15",
            source_document_id=source["id"],
            **anchored,
        )
    ]
    profile["source_documents"] = [source]
    agent.save_profile(profile, clinical_change=False)

    record = client.get("/api/patient/imaging-series").get_json()["records"][0]

    assert record["id"] == "legacy/row?reserved"
    assert "legacy/row" not in record["provenance"]["source_url"]
    assert client.get(record["provenance"]["source_url"]).status_code == 200
    assert (
        client.get(record["provenance"]["evidence_url"]).get_data(as_text=True)
        == "exact source wording"
    )


def test_corrected_row_has_source_access_but_no_exact_evidence_route(app_client, agent):
    _, client = app_client
    profile = _ingest_imaging(agent, copy.deepcopy(agent.DEFAULT_PROFILE))
    receipt = agent.public_receipt(profile, "feed-imaging")
    change = next(item for item in receipt["changes"] if item["category"] == "imaging")
    agent.correct_change(
        profile,
        "feed-imaging",
        change["id"],
        receipt_revision=receipt["receipt_revision"],
        target_token=change["target_token"],
        replacement={"findings": "Caregiver correction"},
    )
    agent.save_profile(profile, clinical_change=False)
    record = client.get("/api/patient/imaging-series").get_json()["records"][0]
    source_url = record["provenance"]["source_url"]
    evidence_url = source_url.replace("/source", "/evidence")

    assert client.get(source_url).status_code == 200
    response = client.get(evidence_url)
    assert response.status_code == 404
    assert response.get_json()["code"] == "imaging_evidence_unavailable"


def test_projection_module_has_no_model_network_or_persistence_calls():
    from pathlib import Path

    source = Path("agent/imaging_series.py").read_text(encoding="utf-8")
    for forbidden in (
        "save_profile",
        "requests.",
        "httpx.",
        "client.messages",
        "run_intake",
        "run_orchestrator",
    ):
        assert forbidden not in source


def test_authority_fields_are_not_added_to_existing_llm_imaging_context(agent, empty_profile):
    profile_module = importlib.import_module("agent.profile")
    empty_profile["imaging"] = [
        _row(
            "one",
            "2026-03-15",
            source_document_date="2026-03-16",
            source_document_date_precision="day",
        )
    ]

    context = profile_module.imaging_context_rows(empty_profile)
    serialized = json.dumps(context)

    assert "date_precision" not in serialized
    assert "date_kind" not in serialized
    assert "source_document_date" not in serialized
    assert context[0]["date"] == "2026-03-15"
    assert context[0]["findings"] == "Exact stored finding"


def test_existing_llm_prompts_exclude_imaging_authority_metadata(agent, empty_profile):
    empty_profile["imaging"] = [
        _row(
            "one",
            "2026-03-15",
            date_kind="legacy_unknown",
            source_document_date="2099-12-31",
            source_document_date_precision="day",
        )
    ]
    captured = []

    def summary_handler(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        return llm_text(
            json.dumps(
                {
                    "overall_status": "insufficient_data",
                    "timeline": [],
                    "next_actions": [],
                }
            )
        )

    with patch_llm(agent, summary_handler):
        agent.generate_executive_summary(empty_profile)

    def questions_handler(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        return llm_text("[]")

    with patch_llm(agent, questions_handler):
        agent.generate_questions_for_profile(empty_profile)

    assert len(captured) == 2
    for prompt in captured:
        assert "legacy_unknown" not in prompt
        assert "2099-12-31" not in prompt
        assert "source_document_date" not in prompt

    for module_name in ("agent/exec_summary.py", "agent/questions.py"):
        source = Path(module_name).read_text(encoding="utf-8")
        assert "project_imaging_series" not in source
