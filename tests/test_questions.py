"""Tests for agent.questions — language-aware system-prompt construction."""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def _profile(language=None, regions=None):
    return {
        "patient": {
            "diagnosis": "neuroendocrine tumor",
            "language": language,
            "regions_of_interest": regions or [],
        }
    }


def test_default_language_is_english_with_no_language_block(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile())
    assert "IMPORTANT: Generate all question text" not in prompt
    assert "Question text in English" in prompt


def test_non_english_language_adds_language_block(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile(language="German"))
    assert "Generate all question text and rationale IN GERMAN" in prompt
    assert "German-speaking oncologist" in prompt
    assert "Question text in German" in prompt


def test_empty_string_language_treated_as_english(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile(language=""))
    assert "IMPORTANT: Generate all question text" not in prompt


def test_referral_example_uses_generic_phrase_when_no_regions(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile())
    assert "centers in your country or region" in prompt


def test_referral_example_uses_configured_regions(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile(regions=["Germany", "Switzerland"]))
    assert "centers in Germany or Switzerland" in prompt


def test_patient_context_embedded(agent):
    from agent.questions import _build_questions_system_prompt

    prompt = _build_questions_system_prompt(_profile())
    assert "neuroendocrine tumor" in prompt


def test_question_generation_excludes_inactive_source_alerts(agent, empty_profile):
    empty_profile["profile_revision"] = 7
    empty_profile["alerts"] = [
        {
            "priority": "high",
            "message": "INVALIDATED SOURCE ALERT",
            "resolved": False,
            "source_dependency_active": False,
        }
    ]
    captured = {}

    def handler(**kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        return llm_text(
            json.dumps(
                [
                    {
                        "text": "What should we monitor?",
                        "category": "Monitoring",
                        "priority": "medium",
                        "rationale": "Current record",
                    }
                ]
            )
        )

    with patch_llm(agent, handler):
        questions = agent.generate_questions_for_profile(empty_profile)

    assert "INVALIDATED SOURCE ALERT" not in captured["content"]
    assert questions[0]["source_profile_revision"] == 7
    assert questions[0]["stale"] is False
