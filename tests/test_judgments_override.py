"""Safety regression tests: the oncologist's clinical judgments must be framed
as HARD OVERRIDES in every agent that receives them.

Before this fix, chat and questions included the judgments only as context
(chat listed them; questions passed them in the user turn) without instructing
the model to let them override data-derived conclusions. These tests pin the
override framing so it can't silently regress.
"""

from __future__ import annotations

import copy

_JUDGMENT = {
    "category": "constraint",
    "date": "2026-05-11",
    "text": "Do not pursue START-NET; prior PRRT is an exclusion.",
}


def _with_judgment(profile: dict) -> dict:
    p = copy.deepcopy(profile)
    p["clinical_judgments"] = [_JUDGMENT]
    return p


def test_chat_system_prompt_includes_override_when_judgments_present(agent, empty_profile):
    from agent.judgments import CLINICAL_JUDGMENTS_OVERRIDE

    sys_prompt = agent.build_chat_system(_with_judgment(empty_profile))
    assert CLINICAL_JUDGMENTS_OVERRIDE in sys_prompt
    assert "HARD CONSTRAINTS" in sys_prompt
    # the actual judgment text is still shown as context
    assert "START-NET" in sys_prompt


def test_chat_no_override_noise_when_no_judgments(agent, empty_profile):
    """Empty profile has no judgments — the override block should not appear."""
    from agent.judgments import CLINICAL_JUDGMENTS_OVERRIDE

    sys_prompt = agent.build_chat_system(empty_profile)
    assert CLINICAL_JUDGMENTS_OVERRIDE not in sys_prompt


def test_questions_system_prompt_includes_override(agent, empty_profile):
    from agent import questions as q_mod
    from agent.judgments import CLINICAL_JUDGMENTS_OVERRIDE

    prompt = q_mod._build_questions_system_prompt(_with_judgment(empty_profile))
    assert CLINICAL_JUDGMENTS_OVERRIDE in prompt
    assert "OVERRIDE" in prompt


def test_override_is_one_shared_verbatim_block(agent):
    """chat and questions must use the exact same canonical block (no drift)."""
    from agent import chat as chat_mod
    from agent import questions as q_mod
    from agent.judgments import CLINICAL_JUDGMENTS_OVERRIDE

    assert chat_mod.CLINICAL_JUDGMENTS_OVERRIDE == CLINICAL_JUDGMENTS_OVERRIDE
    assert q_mod.CLINICAL_JUDGMENTS_OVERRIDE == CLINICAL_JUDGMENTS_OVERRIDE


def test_existing_agents_still_have_override_language(agent):
    """Regression guard: exec_summary and orchestrator already framed judgments
    as overrides in their own prompts — make sure that language is intact."""
    from agent import exec_summary as ex_mod
    from agent import orchestrator as orch_mod

    assert "OVERRIDE" in ex_mod.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    assert "HARD CONSTRAINTS" in orch_mod.ORCHESTRATOR_SYSTEM_TEMPLATE
