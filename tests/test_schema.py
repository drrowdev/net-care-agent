"""Pydantic profile schema tests."""

from __future__ import annotations

import json

import pytest

from agent.profile import DEFAULT_PROFILE
from agent.schema import (
    PatientProfile,
    normalize_profile,
    render_schema_markdown,
    validate_profile,
)


def test_default_profile_validates():
    model = validate_profile(DEFAULT_PROFILE)
    assert isinstance(model, PatientProfile)
    # Default ships a generic diagnosis only; identifying detail (grade,
    # primary site, location) is filled in on the live profile.
    assert "neuroendocrine" in (model.patient.diagnosis or "").lower()


def test_normalize_fills_missing_top_level_keys():
    raw = {"patient": {"sex": "female"}}
    out = normalize_profile(raw)
    # All documented top-level keys present after normalization
    for k in (
        "patient",
        "biomarkers",
        "imaging",
        "documents",
        "trials_tracked",
        "literature_watched",
        "alerts",
        "treatments_classified",
        "clinical_judgments",
        "questions",
        "appointments",
    ):
        assert k in out
    assert out["biomarkers"] == []


def test_normalize_preserves_extras():
    """Forward-compat: unknown fields must round-trip."""
    raw = {
        "patient": {"sex": "female", "favourite_color": "blue"},
        "custom_block": {"foo": 1},
    }
    out = normalize_profile(raw)
    assert out["patient"]["favourite_color"] == "blue"
    assert out["custom_block"] == {"foo": 1}


def test_normalize_does_not_raise_on_bad_data(caplog):
    """Lenient mode: bad data is logged + returned unchanged."""
    raw = {"patient": "not-a-dict"}  # invalid
    with caplog.at_level("WARNING"):
        out = normalize_profile(raw)
    assert out == raw  # untouched
    assert any("validation failed" in r.message for r in caplog.records)


def test_load_profile_normalizes_real_data(tmp_path, monkeypatch):
    """End-to-end: save raw JSON, load it back, get normalized dict.

    Uses monkeypatch.setattr (not module reload) so that mutating PROFILE_PATH
    is automatically reverted after the test — preventing pollution of later
    tests that share the session-scoped DATA_DIR.
    """
    import agent.config as cfg
    import agent.profile as prof

    pp = tmp_path / "patient_profile.json"
    monkeypatch.setattr(cfg, "PROFILE_PATH", pp)

    minimal = {"patient": {"sex": "female", "diagnosis": "test"}}
    pp.write_text(json.dumps(minimal))

    loaded = prof.load_profile()
    assert loaded["patient"]["sex"] == "female"
    assert loaded["biomarkers"] == []
    assert loaded["alerts"] == []


def test_save_profile_logs_warning_on_bad_data(tmp_path, monkeypatch, caplog):
    import agent.config as cfg
    import agent.profile as prof

    pp = tmp_path / "patient_profile.json"
    monkeypatch.setattr(cfg, "PROFILE_PATH", pp)

    bad = {"patient": {"sstr_score": 99}}  # out of 0..4 range
    with caplog.at_level("WARNING"):
        prof.save_profile(bad)
    # File still written (lenient)
    assert pp.exists()
    assert any("validation issues" in r.message for r in caplog.records)


def test_render_schema_markdown_contains_all_models():
    md = render_schema_markdown()
    assert "# Patient profile schema" in md
    assert "Auto-generated" in md
    for cls_name in (
        "patient",
        "biomarkers[]",
        "imaging[]",
        "documents[]",
        "trials_tracked[]",
        "alerts[]",
        "questions[]",
    ):
        assert f"`{cls_name}`" in md
    # Pipes inside type signatures must be escaped for markdown tables
    assert "\\|" in md


@pytest.mark.parametrize("score", [-1, 5, 99])
def test_sstr_score_range_rejected_in_strict_mode(score):
    """Strict validation enforces the Krenning 0..4 range."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        validate_profile({"patient": {"sstr_score": score}})


def test_appointment_with_alias_round_trips():
    """`with` is a Python keyword; we use the alias to expose it."""
    data = {"appointments": [{"date": "2026-04-01", "with": "Dr X"}]}
    out = normalize_profile(data)
    assert out["appointments"][0]["with"] == "Dr X"
