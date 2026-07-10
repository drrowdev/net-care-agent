"""Tests for agent.deep_sweep — the ensemble deep-sweep.

Pins the contracts that matter for a decision-support tool:
- it runs every configured model AND the synthesis pass;
- it UNIONS the per-model reports (both models' findings reach the synthesiser);
- it never mutates the caller's profile (read-only);
- one model failing does not kill the sweep;
- synthesis failure falls back to the raw per-model reports.
"""

from __future__ import annotations

import copy

from tests._llm_fake import llm_text, patch_llm

MODELS = ["claude-fable-5", "claude-opus-4-8"]
SYNTH = "claude-opus-4-8"


def _handler(**kwargs):
    """Route by call shape: synthesis calls carry the SYNTHESISER system prompt."""
    system = kwargs.get("system", "") or ""
    model = kwargs.get("model", "")
    if "SYNTHESISER" in system:
        joined = str(kwargs.get("messages", ""))
        tags = []
        if "fable-finding" in joined:
            tags.append("FABLEFOUND")
        if "opus-finding" in joined:
            tags.append("OPUSFOUND")
        return llm_text("## Summary\nMERGED " + " ".join(tags))
    if model == "claude-fable-5":
        return llm_text("Fable report — fable-finding: trial inversion")
    return llm_text("Opus report — opus-finding: platelet drop")


def test_runs_all_models_and_unions(agent, empty_profile):
    with patch_llm(agent, _handler):
        out = agent.run_deep_sweep(empty_profile, models=MODELS, synthesis_model=SYNTH)
    # Synthesis output present…
    assert "MERGED" in out["report"]
    # …and it received BOTH models' findings (true union, not intersection).
    assert "FABLEFOUND" in out["report"]
    assert "OPUSFOUND" in out["report"]
    # One breakdown per model + a cost footer.
    assert len(out["per_model"]) == 2
    assert {r["model"] for r in out["per_model"]} == set(MODELS)
    assert "Ensemble deep-sweep" in out["report"]
    assert "Total" in out["report"]
    assert "cost_total" in out


def test_is_non_mutating(agent, empty_profile):
    """The live profile must be untouched — deep-sweep is read-only."""
    before = copy.deepcopy(empty_profile)
    with patch_llm(agent, _handler):
        agent.run_deep_sweep(empty_profile, models=MODELS, synthesis_model=SYNTH)
    assert empty_profile == before


def test_one_model_failure_does_not_kill_sweep(agent, empty_profile):
    def handler(**kwargs):
        system = kwargs.get("system", "") or ""
        if "SYNTHESISER" not in system and kwargs.get("model") == "claude-fable-5":
            raise RuntimeError("fable unavailable")
        return _handler(**kwargs)

    with patch_llm(agent, handler):
        out = agent.run_deep_sweep(empty_profile, models=MODELS, synthesis_model=SYNTH)
    per = {r["model"]: r for r in out["per_model"]}
    assert per["claude-fable-5"]["error"] is not None
    assert per["claude-opus-4-8"]["error"] is None
    # Synthesis still ran on the surviving report.
    assert "OPUSFOUND" in out["report"]


def test_synthesis_failure_falls_back_to_raw_reports(agent, empty_profile):
    def handler(**kwargs):
        system = kwargs.get("system", "") or ""
        if "SYNTHESISER" in system:
            raise RuntimeError("synthesis model down")
        return _handler(**kwargs)

    with patch_llm(agent, handler):
        out = agent.run_deep_sweep(empty_profile, models=MODELS, synthesis_model=SYNTH)
    assert "Synthesis step failed" in out["report"]
    # Raw findings from both models are preserved in the fallback.
    assert "fable-finding" in out["report"]
    assert "opus-finding" in out["report"]


def test_synthesis_receives_actual_clinical_judgments(agent, empty_profile):
    judgment = "Do not pursue START-NET; prior PRRT is an exclusion."
    empty_profile["clinical_judgments"] = [
        {"category": "constraint", "date": "2026-05-11", "text": judgment}
    ]
    synthesis_systems = []

    def handler(**kwargs):
        system = kwargs.get("system", "") or ""
        if "SYNTHESISER" in system:
            synthesis_systems.append(system)
        return _handler(**kwargs)

    with patch_llm(agent, handler):
        agent.run_deep_sweep(empty_profile, models=MODELS, synthesis_model=SYNTH)

    assert len(synthesis_systems) == 1
    assert judgment in synthesis_systems[0]
    assert "HARD CONSTRAINTS" in synthesis_systems[0]
