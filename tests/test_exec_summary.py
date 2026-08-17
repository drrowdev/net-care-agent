"""Tests for agent.exec_summary — JSON output generator.

The exec_summary agent must never raise on LLM weirdness — caregiver UX
depends on getting a structured ``insufficient_data`` placeholder rather
than a 500. These tests pin that contract.
"""

from __future__ import annotations

import json

from tests._llm_fake import llm_text, patch_llm


def test_malformed_json_falls_back_to_insufficient_data(agent, empty_profile):
    with patch_llm(agent, lambda **_: llm_text("definitely not json")):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "insufficient_data"
    assert out["status_confidence"] == "low"
    assert out["next_actions"] == []
    assert out["best_trial"] is None
    assert "generated_at" in out


def test_max_tokens_stop_reason_falls_back_with_clear_error(agent, empty_profile):
    """If Sonnet truncates, the agent should return the insufficient_data
    shape with a message that mentions max_tokens — so the operator
    knows to bump the limit."""
    with patch_llm(
        agent, lambda **_: llm_text('{"overall_status": "stable"', stop_reason="max_tokens")
    ):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "insufficient_data"
    assert "max_tokens" in out["summary"].lower() or "truncated" in out["summary"].lower()


def test_valid_json_passes_through(agent, empty_profile):
    payload = {
        "overall_status": "stable",
        "status_confidence": "high",
        "status_rationale": "no change since last scan",
        "key_concern": "monitoring",
        "summary": "Stable disease.",
        "prrt_status": "eligible",
        "prrt_rationale": "SSTR+, Ki-67 8%",
        "cga_trend": "stable",
        "cga_trend_detail": "CgA 180 -> 185 over 3 months",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "generated_at": "ignored",
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        out = agent.generate_executive_summary(empty_profile)
    assert out["overall_status"] == "stable"
    assert out["status_confidence"] == "high"
    # generated_at must be re-stamped to today (not the dummy 'ignored')
    assert out["generated_at"] != "ignored"
    assert len(out["generated_at"]) == 10  # YYYY-MM-DD


def test_exec_summary_context_uses_raw_treatments_when_classification_stale(agent, empty_profile):
    empty_profile["profile_revision"] = 5
    empty_profile["patient"]["current_treatments"] = ["raw sunitinib"]
    empty_profile["treatments_classified"] = [{"text": "stale lanreotide", "category": "active"}]
    empty_profile["treatments_classification_revision"] = 4
    captured = {}
    payload = {
        "overall_status": "insufficient_data",
        "status_confidence": "low",
        "status_rationale": "Sparse data.",
        "key_concern": "None established.",
        "summary": "Review current record.",
        "prrt_status": "unknown",
        "prrt_rationale": "Not assessed.",
        "cga_trend": "insufficient_data",
        "cga_trend_detail": "No trend.",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "claim_evidence": {},
    }

    def handler(**kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        return llm_text(json.dumps(payload))

    with patch_llm(agent, handler):
        agent.generate_executive_summary(empty_profile)

    assert "raw sunitinib" in captured["content"]
    assert "stale lanreotide" not in captured["content"]


def test_generated_prose_is_stored_and_prompted_exactly_as_the_model_wrote_it(agent, empty_profile):
    """Finnish dates are a rendering concern and must stay one.

    The interface rewrites ISO dates inside generated sentences on the way to
    the screen. That must never reach back into what is stored or into what is
    sent to the model: the record keeps the model's words verbatim, and the
    prompt asks nothing about date formatting.
    """
    prose = {
        "status_rationale": "PET-CT on 2026-04-22 confirmed progression.",
        "key_concern": "The interval closes 2026-08-26.",
        "summary": "Three doses every 8 weeks from 2026-05-07.",
        "prrt_rationale": "Receptor imaging reviewed 2026-04-22.",
        "cga_trend_detail": "CgA rose between 2026-02-11 and 2026-04-22.",
    }
    payload = {
        "overall_status": "progressing",
        "status_confidence": "medium",
        "prrt_status": "likely_eligible",
        "cga_trend": "rising",
        "next_actions": [
            {
                "priority": "high",
                "action": "Confirm the dose booked for 2026-09-01",
                "timeframe": "before 2026-08-20",
                "rationale": "The interval closes 2026-08-26.",
                "provisional": True,
            }
        ],
        "timeline": [{"date": "2026-09-01", "event": "Third dose due 2026-09-01", "type": "scan"}],
        "best_trial": None,
        "claim_evidence": {},
        **prose,
    }
    captured = {}

    def handler(**kwargs):
        captured["content"] = kwargs["messages"][0]["content"]
        captured["system"] = kwargs.get("system")
        return llm_text(json.dumps(payload))

    with patch_llm(agent, handler):
        out = agent.generate_executive_summary(empty_profile)

    for field, text in prose.items():
        assert out[field] == text
    assert out["next_actions"][0]["action"] == "Confirm the dose booked for 2026-09-01"
    assert out["next_actions"][0]["timeframe"] == "before 2026-08-20"
    assert out["next_actions"][0]["rationale"] == "The interval closes 2026-08-26."
    assert out["timeline"][0]["event"] == "Third dose due 2026-09-01"
    assert out["timeline"][0]["date"] == "2026-09-01"
    # Nothing Finnish-shaped was written into the record.
    assert "22.4.2026" not in json.dumps(out)

    prompt = json.dumps(captured, default=str)
    for instruction in ("D.M.YYYY", "Finnish", "dd.mm.yyyy", "day.month.year"):
        assert instruction not in prompt

    from agent import exec_summary

    assert '"generated_at": "YYYY-MM-DD"' in exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE


# ── PRRT status vocabulary ───────────────────────────────────────────────────
# The caregiver read "PRRT: POTENTIAL FIT" directly above a rationale saying the
# patient is already receiving her second Lu-177-octreotate series. That chip is
# `prrt_status == "eligible"`. The vocabulary simply had no value for a course
# already under way, so the strongest screening token was the closest thing the
# model could say. The fix is vocabulary, not prose inspection: nothing reads
# `prrt_rationale` to decide what the chip says.


def test_the_status_vocabulary_can_say_a_course_is_already_under_way(agent):
    from agent import exec_summary

    template = exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    assert (
        '"prrt_status": "course_in_progress|eligible|likely_eligible|'
        'pending_dotatate|not_eligible|unknown"'
    ) in template
    # The screening tokens survive unchanged for someone not yet receiving PRRT.
    for token in ("eligible", "likely_eligible", "pending_dotatate", "not_eligible", "unknown"):
        assert token in template


def test_the_prompt_forbids_calling_a_running_course_a_potential_fit(agent):
    from agent import exec_summary

    template = exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    assert "Never call a course that is already under way a potential" in template
    assert "not a judgment that treatment should continue" in template
    # A running course must never swallow a concern about continuing it.
    assert "reflect it in key_concern and next_actions" in template
    # The original non-eligibility promise is still made.
    assert "never a definitive eligibility decision" in template


def test_a_course_in_progress_status_passes_through_untouched(agent, empty_profile):
    payload = {
        "overall_status": "stable",
        "status_confidence": "high",
        "status_rationale": "Imaging is stable.",
        "key_concern": "Cumulative renal dose is being tracked.",
        "summary": "Treatment is continuing as planned.",
        "prrt_status": "course_in_progress",
        "prrt_rationale": (
            "She is SSTR-positive and is already receiving Series 2 Lu-177-octreotate; "
            "the treating team confirms candidacy and tracks cumulative renal dose."
        ),
        "cga_trend": "stable",
        "cga_trend_detail": "CgA 180 to 185",
        "next_actions": [],
        "timeline": [],
        "best_trial": None,
        "generated_at": "ignored",
    }
    with patch_llm(agent, lambda **_: llm_text(json.dumps(payload))):
        out = agent.generate_executive_summary(empty_profile)
    assert out["prrt_status"] == "course_in_progress"
    assert "already receiving Series 2" in out["prrt_rationale"]


# ── the timeline date field ──────────────────────────────────────────────────
# The prompt used to describe `timeline[].date` as "YYYY-MM or approximate
# description", so the model wrote qualifiers and alternatives into a date field
# and they reached the screen as machine text. The prompt now forbids that, and
# these pin the deterministic backstop, because a prompt is a request and a model
# can drift back.


def test_the_prompt_asks_for_a_calendar_date_and_nothing_else():
    from agent import exec_summary

    template = exec_summary.EXECUTIVE_SUMMARY_SYSTEM_TEMPLATE
    assert '"date": "YYYY-MM or approximate description"' not in template
    assert "a calendar date ONLY, nothing else" in template
    # The instruction that invited invention is gone.
    assert "Estimate dates where reasonable" not in template
    assert "Never estimate or invent a date that the record does not state." in template
    # And it says where a qualifier belongs instead.
    assert "Any timing wording belongs in timeline[].event" in template


def test_a_qualifier_is_moved_out_of_the_date_field_into_the_event():
    from agent.exec_summary import _normalise_timeline_dates

    summary = _normalise_timeline_dates(
        {
            "timeline": [
                {"date": "2026-08 (approx late Aug)", "event": "Third dose"},
                {"date": "2026-08 (before next dose)", "event": "Bloods"},
                {"date": "2026-09-01", "event": "Review"},
            ]
        }
    )
    assert summary["timeline"] == [
        {"date": "2026-08", "event": "Third dose (approx late Aug)"},
        {"date": "2026-08", "event": "Bloods (before next dose)"},
        {"date": "2026-09-01", "event": "Review"},
    ]


def test_two_possible_months_are_left_for_the_display_to_read_once():
    """Clearing a value the generator cannot split would make the same recorded
    timing read differently depending on when it was generated. It is left
    exactly as recorded, and the browser decides how to show it — for a new
    assessment and an old one alike."""
    from agent.exec_summary import _normalise_timeline_dates

    summary = _normalise_timeline_dates(
        {"timeline": [{"date": "2026-08/09", "event": "Scan window"}]}
    )
    assert summary["timeline"] == [{"date": "2026-08/09", "event": "Scan window"}]


def test_wording_with_no_date_at_all_is_kept_as_recorded():
    from agent.exec_summary import _normalise_timeline_dates

    summary = _normalise_timeline_dates(
        {"timeline": [{"date": "when the team decides", "event": "Repeat scan"}]}
    )
    assert summary["timeline"] == [{"date": "when the team decides", "event": "Repeat scan"}]


def test_an_impossible_day_is_not_accepted_as_a_calendar_date():
    """It stays recorded, but nothing downstream may read it as a date."""
    from agent.exec_summary import _normalise_timeline_dates
    from agent.schema import derive_date_precision

    summary = _normalise_timeline_dates({"timeline": [{"date": "2026-02-31", "event": "Scan"}]})
    assert derive_date_precision(summary["timeline"][0]["date"]) == "unknown"


def test_normalising_a_broken_timeline_never_costs_him_the_summary():
    from agent.exec_summary import _normalise_timeline_dates

    for timeline in (None, "not a list", [None], [{"date": 5}], [[]]):
        assert _normalise_timeline_dates({"timeline": timeline}) is not None


def test_an_undated_item_sorts_last_rather_than_leading_the_timeline():
    """An empty date used to sort first, so an unscheduled item read as the
    nearest thing coming up."""
    from agent.exec_summary import _merge_upcoming_appointments

    summary = _merge_upcoming_appointments(
        {
            "timeline": [
                {"date": "", "event": "Unscheduled"},
                {"date": "2026-09-01", "event": "Review"},
            ]
        },
        {"appointments": []},
    )
    assert [item["event"] for item in summary["timeline"]] == ["Review", "Unscheduled"]
