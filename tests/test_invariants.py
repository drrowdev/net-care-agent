"""Contract-conformance tests (architecture-review P10).

These pin the machine-parsed output contracts and read/write discipline listed
in INVARIANTS.md, so a future edit (human or AI) that renames a JSON key the UI
depends on, or adds a save to the read-only deep-sweep, fails CI loudly.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_invariants_doc_exists_and_lists_contracts():
    doc = (REPO / "INVARIANTS.md").read_text(encoding="utf-8")
    for token in ("overall_status", "prrt_status", "gunicorn worker", "deep_sweep"):
        assert token in doc, f"INVARIANTS.md missing {token!r}"


def test_deep_sweep_never_saves_profile():
    """The ensemble deep-sweep must stay read-only (INVARIANTS §3)."""
    src = (REPO / "agent" / "deep_sweep.py").read_text(encoding="utf-8")
    assert "save_profile" not in src


def test_exec_summary_contract_keys_present(agent):
    from agent import exec_summary

    tpl = exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    for key in (
        '"overall_status"',
        '"status_confidence"',
        '"prrt_status"',
        '"cga_trend"',
        '"next_actions"',
        '"best_trial"',
        '"generated_at"',
    ):
        assert key in tpl
    for enum in ("stable|responding|progressing|insufficient_data", "pending_dotatate"):
        assert enum in tpl


def test_questions_and_classify_enums_present(agent):
    from agent import classify
    from agent import questions as q_mod

    qp = q_mod._build_questions_system_prompt(agent.DEFAULT_PROFILE)
    assert "Treatment|Diagnostics|Symptoms|Trials|Monitoring|Other" in qp
    assert "urgent|high|medium" in qp
    assert "active|planned|completed" in classify.TREATMENT_CLASSIFIER_SYSTEM_TEMPLATE


def test_intake_schema_keys_present(agent):
    from agent import intake

    tpl = intake.INTAKE_SYSTEM_TEMPLATE
    for key in ('"document_type"', '"biomarkers"', '"suggested_workflows"', '"ki67_update"'):
        assert key in tpl


def test_feed_and_digest_jobs_acquire_mutating_lock():
    """INVARIANTS §3/§4: mutating background jobs run under the single slot."""
    src = (REPO / "app.py").read_text(encoding="utf-8")
    assert src.count("with agent.serialized_mutation(") >= 2
    assert "@serialized_profile_mutation" in src
