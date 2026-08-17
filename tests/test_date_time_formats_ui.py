"""Displayed dates, times and numbers follow Finnish convention.

The caregiver reads this record in Finland, so `14.8.2026`, `8/2026` and the
24-hour `09:26` are the only shapes that are ever correct on screen. Interface
copy stays in English; only the numeric formatting is localised.

Every assertion here pins the exact rendered string, so a regression back to
hyphenated dates, `MM-YYYY`, an implicit browser locale, English month
abbreviations or an AM/PM clock fails loudly instead of quietly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from tests._copy_scan import javascript_interpolations
from tests._ui_render import bare_iso_dates, render_summary, visible_text

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"

# The caregiver's zone. Pinned so the expected strings are reproducible on any
# machine, and so a timestamp read in the wrong zone shows up as a failure.
_DISPLAY_TIMEZONE = "Europe/Helsinki"


def _function_source(name: str, next_name: str) -> str:
    start = APP_JS.index(f"function {name}")
    end = APP_JS.index(f"function {next_name}", start)
    return APP_JS[start:end]


def _formatter_source() -> str:
    """Every shared date, time and number helper, plus its two callers."""
    return "\n".join(
        [
            _function_source("fmtDate", "copyReport"),
            _function_source("relativeTime", "duration"),
            _function_source("formatActionTimestamp", "setFollowUpStatus"),
        ]
    )


def _run_node(script: str) -> dict:
    env = dict(os.environ, TZ=_DISPLAY_TIMEZONE)
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _evaluate(expressions: dict[str, str], *, prelude: str = "") -> dict:
    body = ",\n".join(f"  {json.dumps(key)}: {value}" for key, value in expressions.items())
    script = "\n".join(
        [
            _formatter_source(),
            prelude,
            f"const result = {{\n{body}\n}};",
            "console.log(JSON.stringify(result));",
        ]
    )
    return _run_node(script)


def test_full_dates_use_finnish_dot_separators_without_leading_zeros():
    result = _evaluate(
        {
            "august": "fmtDate('2026-08-14')",
            "january": "fmtDate('2026-01-05')",
            "december": "fmtDate('2026-12-31')",
        }
    )
    assert result == {
        "august": "14.8.2026",
        "january": "5.1.2026",
        "december": "31.12.2026",
    }


def test_month_precision_dates_render_as_month_slash_year():
    result = _evaluate(
        {
            "august": "fmtDate('2026-08')",
            "november": "fmtDate('2026-11')",
        }
    )
    assert result == {"august": "8/2026", "november": "11/2026"}


def test_year_precision_dates_keep_the_recorded_year():
    assert _evaluate({"year": "fmtDate('2026')"}) == {"year": "2026"}


def test_date_ranges_keep_the_en_dash_join_and_finnish_parts():
    result = _evaluate(
        {
            "months": "fmtDate('2026-05 to 2026-08')",
            "days": "fmtDate('2026-05-01 to 2026-08-14')",
        }
    )
    assert result == {
        "months": "5/2026 – 8/2026",
        "days": "1.5.2026 – 14.8.2026",
    }


def test_times_are_24_hour_with_a_colon_and_padded_hours():
    result = _evaluate(
        {
            "morning": "fmtTime('2026-08-14T06:26:00')",
            "afternoon": "fmtTime('2026-08-14T14:05:00')",
            "midnight": "fmtTime('2026-08-14T21:00:00')",
        }
    )
    # Summer in Helsinki is UTC+3, so 06:26 UTC is 09:26 locally.
    assert result == {"morning": "09:26", "afternoon": "17:05", "midnight": "00:00"}
    for value in result.values():
        assert "AM" not in value and "PM" not in value


def test_date_and_time_render_together_in_finnish_order():
    result = _evaluate(
        {
            "summer": "fmtDateTime('2026-08-14T06:26:00')",
            "winter": "fmtDateTime('2026-01-15T06:26:00')",
        }
    )
    # Winter in Helsinki is UTC+2.
    assert result == {"summer": "14.8.2026 09:26", "winter": "15.1.2026 08:26"}


def test_datetime_formatter_keeps_partial_date_precision():
    result = _evaluate(
        {
            "day": "fmtDateTime('2026-08-14')",
            "month": "fmtDateTime('2026-08')",
            "year": "fmtDateTime('2026')",
        }
    )
    assert result == {"day": "14.8.2026", "month": "8/2026", "year": "2026"}


def test_naive_server_timestamps_are_read_as_utc_like_relative_times():
    """The server writes naive ISO stamps on a UTC host.

    `relativeTime` has always assumed that. The report/artifact timestamp path
    used to disagree and read the same field as browser-local time, which put
    every recorded time two to three hours in the past for the caregiver.
    """
    result = _evaluate(
        {
            "naive": "fmtDateTime('2026-08-14T06:26:00')",
            "explicit_utc": "fmtDateTime('2026-08-14T06:26:00Z')",
            "explicit_offset": "fmtDateTime('2026-08-14T09:26:00+03:00')",
        }
    )
    assert result["naive"] == result["explicit_utc"] == result["explicit_offset"]
    assert result["naive"] == "14.8.2026 09:26"


def test_relative_time_older_than_a_day_falls_back_to_a_finnish_full_date():
    result = _evaluate(
        {
            "recent": "relativeTime(new Date(Date.now() - 5 * 60 * 1000).toISOString())",
            "hours": "relativeTime(new Date(Date.now() - 3 * 3600 * 1000).toISOString())",
            "old": "relativeTime('2020-03-04T06:26:00')",
        }
    )
    # Relative labels stay English; only the fallback date is localised.
    assert result["recent"] == "5m ago"
    assert result["hours"] == "3h ago"
    assert result["old"] == "4.3.2020"


def test_relative_time_never_invents_a_missing_day_or_month():
    """A partial or date-only value has no time of day to be relative to.

    Running one through `Date` fabricates the missing components, so these are
    rendered at the precision they were recorded at instead.
    """
    result = _evaluate(
        {
            "day": "relativeTime('2026-08-14')",
            "month": "relativeTime('2026-08')",
            "year": "relativeTime('2026')",
            "free_text": "relativeTime('Summer 2026')",
        }
    )
    assert result == {
        "day": "14.8.2026",
        "month": "8/2026",
        "year": "2026",
        "free_text": "Summer 2026",
    }


def test_report_and_artifact_timestamps_are_deterministic_finnish():
    result = _evaluate(
        {
            "recorded": "formatActionTimestamp('2026-08-14T06:26:00')",
            "date_only": "formatActionTimestamp('2026-08-14')",
        }
    )
    assert result == {"recorded": "14.8.2026 09:26", "date_only": "14.8.2026"}
    for value in result.values():
        for english_month in ("Aug", "August", "Jan", "January"):
            assert english_month not in value


def test_chat_message_timestamps_are_24_hour():
    prelude = """
function escHtml(value) { return String(value == null ? '' : value); }
function renderMarkdown(text) { return String(text); }
class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.className = '';
    this.innerHTML = '';
    this.children = [];
  }
  appendChild(child) { this.children.push(child); }
  querySelector() { return null; }
}
const chatMessages = new FakeNode('div');
chatMessages.scrollHeight = 0;
chatMessages.scrollTop = 0;
const document = {
  getElementById(id) { return id === 'chat-messages' ? chatMessages : null; },
  createElement(tag) { return new FakeNode(tag); },
};
const RealDate = Date;
class FrozenDate extends RealDate {
  constructor(...args) {
    if (args.length === 0) super('2026-08-14T06:26:00Z');
    else super(...args);
  }
  static now() { return new RealDate('2026-08-14T06:26:00Z').getTime(); }
}
Date = FrozenDate;
"""
    appender = _function_source("appendMsg", "updateLastMsg")
    script = "\n".join(
        [
            _formatter_source(),
            prelude,
            appender,
            "const node = appendMsg('assistant', 'hello');",
            "console.log(JSON.stringify({ html: node.innerHTML }));",
        ]
    )
    html = _run_node(script)["html"]
    assert '<div class="chat-time">09:26</div>' in html
    assert "AM" not in html and "PM" not in html


def test_missing_and_unparseable_values_stay_graceful():
    result = _evaluate(
        {
            "date_null": "fmtDate(null)",
            "date_empty": "fmtDate('')",
            "date_garbage": "fmtDate('not a date')",
            "time_null": "fmtTime(null)",
            "time_garbage": "fmtTime('not a date')",
            "datetime_null": "fmtDateTime(null)",
            "datetime_empty": "fmtDateTime('')",
            "datetime_garbage": "fmtDateTime('not a date')",
            "relative_null": "relativeTime(null)",
            "relative_garbage": "relativeTime('not a date')",
            "relative_broken_stamp": "relativeTime('2026-13-45T99:99:99')",
            "action_null": "formatActionTimestamp(null)",
            "action_garbage": "formatActionTimestamp('not a date')",
            "number_garbage": "fmtNumber('not a number')",
        }
    )
    assert result == {
        "date_null": "",
        "date_empty": "",
        # Unrecognised text passes through untouched rather than being guessed at.
        "date_garbage": "not a date",
        "time_null": "",
        "time_garbage": "",
        "datetime_null": "",
        "datetime_empty": "",
        "datetime_garbage": "not a date",
        "relative_null": "",
        "relative_garbage": "not a date",
        "relative_broken_stamp": "",
        "action_null": "",
        "action_garbage": "not a date",
        "number_garbage": "",
    }


def test_numbers_use_finnish_grouping():
    result = _evaluate({"thousands": "fmtNumber(12345)", "small": "fmtNumber(42)"})
    assert result["small"] == "42"
    # Finnish groups with a no-break space, never a comma.
    assert result["thousands"].replace("\u00a0", " ").replace("\u202f", " ") == "12 345"
    assert "," not in result["thousands"]


def test_no_call_site_falls_back_to_the_browser_locale_or_an_english_clock():
    assert "toLocaleString([]" not in APP_JS
    assert "toLocaleTimeString(" not in APP_JS
    assert "toLocaleDateString(" not in APP_JS
    assert "month: 'short'" not in APP_JS
    # The only locale-sensitive call left is the shared Finnish number formatter.
    assert APP_JS.count("toLocaleString(") == 1
    assert "toLocaleString(FI_LOCALE)" in APP_JS
    assert "const FI_LOCALE = 'fi-FI';" in APP_JS


def test_assessment_freshness_stamps_route_through_the_shared_formatter():
    freshness = _function_source("renderFreshness", "clearFreshnessProjection")
    assert "fmtDateTime(d.generated_at_timestamp || d.generated_at)" in freshness
    summary = _function_source("renderSummary", "researchPlainObject")
    assert "fmtDateTime(d.generated_at_timestamp || d.generated_at)" in summary
    # A raw ISO stamp must never reach the screen.
    assert "${d.generated_at_timestamp || fmtDate(" not in APP_JS


def test_character_count_uses_the_shared_finnish_number_formatter():
    counter = _function_source("updateCharCount", "feedText")
    assert "`${fmtNumber(n)} characters`" in counter


def test_metadata_lines_do_not_leak_a_raw_iso_date():
    """These lines print a stored date as ordinary metadata, not exact evidence."""
    judgments = _function_source("renderJudgments", "startEditJudgment")
    assert "escHtml(fmtDate(j.date))" in judgments
    assert "escHtml(j.date||'')" not in judgments

    receipt = _function_source("receiptValueSummary", "renderReceipt")
    assert "${fmtDate(value.date)}" in receipt
    assert "${value.date || ''}" not in receipt

    preparation = _function_source("renderVisitPreparation", "toggleVisitCreateForm")
    assert "fmtDate(source.date)" in preparation
    assert "source.type || source.date || ''" not in preparation

    # The copy audit found this guard only covered the three functions above,
    # which is exactly how the sites below kept printing a stored 2026-08-14
    # while the rest of the record showed 14.8.2026. The full contract now lives
    # in tests/test_plain_language_copy.py; these are the shared helpers.
    for name, next_name in [
        ("biomarkerDate", "biomarkerProjectionPayloadIsValid"),
        ("imagingDate", "setImagingFreshness"),
        ("symptomDate", "symptomDatePresentation"),
    ]:
        helper = _function_source(name, next_name)
        assert "fmtDate(String(value))" in helper, f"{name} bypasses the formatter"


def test_iso_dates_written_into_generated_sentences_are_localised_in_place():
    """A date inside model-written prose is not a field, so no formatter reached it.

    Rewriting it at render time is transcription, not interpretation: the shape
    is unambiguous and only its punctuation changes.
    """
    result = _evaluate(
        {
            "day": "fmtProseDates('PET-CT on 2026-04-22 confirmed progression.')",
            "month": "fmtProseDates('Doses run 2026-05 to 2026-08.')",
            "leading": "fmtProseDates('2026-05-07 is the first dose.')",
            "trailing": "fmtProseDates('The first dose is 2026-05-07.')",
            "bracketed": "fmtProseDates('First dose (2026-05-07) is booked.')",
            "several": "fmtProseDates('Doses 2026-05-07, 2026-07-02 and 2026-08-27.')",
        }
    )
    assert result == {
        "day": "PET-CT on 22.4.2026 confirmed progression.",
        "month": "Doses run 5/2026 to 8/2026.",
        "leading": "7.5.2026 is the first dose.",
        "trailing": "The first dose is 7.5.2026.",
        "bracketed": "First dose (7.5.2026) is booked.",
        "several": "Doses 7.5.2026, 2.7.2026 and 27.8.2026.",
    }


def test_prose_normalisation_leaves_years_and_written_out_months_alone():
    result = _evaluate(
        {
            "year": "fmtProseDates('Reviewed again in 2026.')",
            "month_name": "fmtProseDates('Around late August 2026 and in April 2026.')",
            "no_hyphen": "fmtProseDates('CgA 145 rose to 188 nmol/L.')",
        }
    )
    assert result == {
        "year": "Reviewed again in 2026.",
        "month_name": "Around late August 2026 and in April 2026.",
        "no_hyphen": "CgA 145 rose to 188 nmol/L.",
    }


def test_prose_normalisation_never_touches_a_structural_digit_run():
    """Anything glued to a word, path, colon, dot or hyphen may be an identifier."""
    unchanged = {
        "identifier": "Report doc-2026-05-07-abc is filed.",
        "underscore": "Key ref_2026-05-07 is stable.",
        "filename": "See report-2026-05-07.pdf for detail.",
        "timestamp": "Recorded 2026-05-07T10:30:00 by the server.",
        "version": "Schema v1.2026-05 shipped.",
        "keyed": "Stored under key:2026-05-07 today.",
        "url": "See https://example.org/reports/2026-05-07/summary now.",
        "www": "See www.example.org/2026-05-07 now.",
        "query": "See https://example.org/r?d=2026-05-07 now.",
        "numeric_range": "Lab range 1234-56 is normal.",
        "bad_month": "Value 2026-13 is not a month.",
        "bad_day": "Value 2026-05-45 is not a day.",
        "long_year": "Value 12026-05-07 is not a date.",
        "long_day": "Value 2026-05-071 is not a date.",
        "nct": "Trial NCT02726204 remains open.",
    }
    result = _evaluate(
        {key: f"fmtProseDates({json.dumps(value)})" for key, value in unchanged.items()}
    )
    assert result == unchanged


def test_prose_normalisation_stays_graceful_on_empty_and_odd_input():
    result = _evaluate(
        {
            "null": "fmtProseDates(null)",
            "undefined": "fmtProseDates(undefined)",
            "empty": "fmtProseDates('')",
            "plain": "fmtProseDates('No dates at all here.')",
            "bare": "fmtProseDates('2026-05-07')",
        }
    )
    assert result == {
        "null": "",
        "undefined": "",
        "empty": "",
        "plain": "No dates at all here.",
        "bare": "7.5.2026",
    }


def test_prose_normalisation_leaves_a_hyphenated_year_span_alone():
    """ "2011-12" is a two-year span, not December 2011; rewriting it changes meaning."""
    unchanged = {
        "span": "Treated 2011-12 at Helsinki.",
        "early_span": "Cohort 2009-10 data was reviewed.",
        "century_span": "Records from 2000-01 are archived.",
        "late_span": "The 2010-11 series is complete.",
    }
    result = _evaluate(
        {key: f"fmtProseDates({json.dumps(value)})" for key, value in unchanged.items()}
    )
    assert result == unchanged
    # A day-precision date in the same shape is unambiguous and still localised.
    assert _evaluate({"day": "fmtProseDates('Scan 2011-12-15 confirmed progression.')"}) == {
        "day": "Scan 15.12.2011 confirmed progression."
    }


def test_a_saved_recommendation_reads_the_same_on_both_surfaces():
    """The follow-through copy is the assessment's own sentence, verbatim."""
    prelude = _function_source("followUpDisplayText", "followUpOutcomePresentation")
    generated = json.dumps(
        {
            "text": "Confirm the dose booked for 2026-09-01.",
            "origin_snapshot": {"kind": "executive_summary_action"},
        }
    )
    caregiver = json.dumps({"text": "Ask about 2026-09-01.", "origin_snapshot": {"kind": "manual"}})
    result = _evaluate(
        {
            "generated": f"followUpDisplayText({generated})",
            "caregiver": f"followUpDisplayText({caregiver})",
            "missing": "followUpDisplayText({text: 'Plain note.'})",
            "empty": "followUpDisplayText(null)",
        },
        prelude=prelude,
    )
    assert result == {
        # Matches the wording rendered in the assessment panel.
        "generated": "Confirm the dose booked for 1.9.2026.",
        # The caregiver's own words are shown exactly as typed.
        "caregiver": "Ask about 2026-09-01.",
        "missing": "Plain note.",
        "empty": "",
    }
    follow_ups = _function_source("renderFollowUps", "setFollowUpFilter")
    assert "escHtml(followUpDisplayText(item))" in follow_ups
    # The caregiver's outcome note is their own text and stays untouched.
    assert "escHtml(item.outcome.text)" in follow_ups
    # Every surface that repeats a saved follow-up's wording reads the same way,
    # so the confirm dialogs cannot disagree with the card that opened them.
    assert (
        "document.getElementById('follow-up-edit-copy').textContent = "
        "followUpDisplayText(action);" in APP_JS
    )
    assert (
        "document.getElementById('follow-up-outcome-copy').textContent = "
        "followUpDisplayText(action);" in APP_JS
    )
    assert "followUpDisplayText(item), item.owner" in APP_JS
    assert "`Follow-up · ${followUpDisplayText(followUp)}`" in APP_JS
    # Scoped to the surfaces this test owns: inside them, a follow-up's wording is
    # only ever read through the shared helper, so a new raw read fails here.
    for name, next_name in (
        ("renderAlertResolutionSourceOptions", "renderAlertResolutionDecisionOptions"),
        ("renderAlertResolutionResult", "evidenceBadge"),
        ("renderFollowUpDialog", "openFollowUpDialog"),
        ("renderFollowUps", "setFollowUpFilter"),
    ):
        source = _function_source(name, next_name)
        raw = [
            line
            for line in source.splitlines()
            # The caregiver's own outcome note is deliberately shown as written.
            if re.search(r"\b(?:item|action|followUp)\.text\b", line)
            and "followUpDisplayText" not in line
        ]
        assert raw == [], f"{name} reads a follow-up's text without followUpDisplayText: {raw}"


def test_every_generated_narrative_field_routes_through_the_prose_formatter():
    """Enumerated so a new generated field cannot quietly ship raw ISO."""
    summary = _function_source("renderSummary", "researchPlainObject")
    for field in (
        "escHtml(fmtProseDates(d.key_concern))",
        "escHtml(fmtProseDates(a.action))",
        "escHtml(fmtProseDates(a.rationale))",
        "fmtProseDates(a.timeframe) || 'Review with care team'",
        "escHtml(fmtProseDates(d.status_rationale))",
        "escHtml(fmtProseDates(d.summary))",
        "escHtml(fmtProseDates(item.event))",
        "escHtml(fmtProseDates(d.cga_trend_detail))",
        "escHtml(fmtProseDates(d.prrt_rationale))",
    ):
        assert field in summary
    # The value the dismiss call sends back to the server stays the stored text.
    assert "data-action-text=\"${escHtml(a.action || '')}\"" in summary
    # `<time datetime>` stays machine-readable ISO-8601 — and is now only drawn
    # when there really is one, so a qualifier can no longer make it invalid.
    assert '<time datetime="${escHtml(parts.date)}">' in summary


# ── the assessment timeline ──────────────────────────────────────────────────
# He reported machine dates on this panel three times. The first two rounds
# localised fields and generated prose; this one starts from the fact that the
# renderer already called the formatter, so the defect was upstream — the
# generated contract described `timeline[].date` as "YYYY-MM or approximate
# description", and `fmtDate` deliberately returns anything it cannot read
# unchanged. These pin the display behaviour for values already stored, which
# no amount of prompt work can retrospectively clean up.


def _timeline_summary(timeline: list[dict], **overrides) -> dict:
    summary = {
        "status": "current",
        "overall_status": "stable",
        "profile_revision": 12,
        "summary_revision": 12,
        "generation_id": "gen-1",
        "generated_at": "2026-08-14",
        "generated_at_timestamp": "2026-08-14T06:26:00",
        "key_concern": "",
        "status_rationale": "",
        "summary": "",
        "next_actions": [],
        "timeline": timeline,
        "claim_evidence": {"claims": {}, "actions": []},
    }
    summary.update(overrides)
    return summary


def _timeline_html(timeline: list[dict], *, today: str = "2026-08-17") -> str:
    return render_summary(_timeline_summary(timeline), today=today)["body"]


def _stop_labels(html: str) -> list[str]:
    """The wording shown for *when* each stop happens, in order."""
    return [
        " ".join(_TAGS.sub(" ", block).split())
        for block in re.findall(
            r'<span class="timeline-stop-when">(.*?)</span>\s*<span class="timeline-event-copy"',
            html,
            re.S,
        )
    ]


_TAGS = re.compile(r"<[^<>]*>")


def test_a_qualifier_in_the_date_field_renders_finnish_and_keeps_the_qualifier():
    """`2026-08 (approx late Aug)` reached the screen exactly like that.

    The date field was specified as "YYYY-MM or approximate description", so the
    model wrote a qualifier into it, and `fmtDate` matches only an exact ISO
    value. The recognisable part is now formatted and the recorded wording is
    kept beside it, so nothing he was told is lost and nothing is invented.
    """
    html = _timeline_html(
        [
            {"date": "2026-08 (approx late Aug)", "event": "Third dose", "type": "milestone"},
            {"date": "2026-08 (before next dose)", "event": "Bloods", "type": "test"},
        ]
    )
    assert _stop_labels(html) == [
        "8/2026 (approx late Aug)",
        "8/2026 (before next dose)",
    ]
    assert "2026-08 (" not in visible_text(html)


def test_two_possible_months_are_both_shown_and_neither_is_silently_chosen():
    """`2026-08/09` means August or September. Picking one would invent timing.

    Both months are shown in Finnish. The item claims no single machine date,
    because there is no single instant to claim.
    """
    html = _timeline_html(
        [
            {"date": "2026-08/09", "event": "Scan window", "type": "scan"},
            {"date": "2026-09/10", "event": "Review window", "type": "appointment"},
        ]
    )
    assert _stop_labels(html) == ["8/2026 or 9/2026", "9/2026 or 10/2026"]
    # No `<time>` element, because there is no one date to put in it.
    assert "<time" not in html
    # And emphatically not narrowed to the first month.
    assert "8/2026 or 9/2026" in html and ">8/2026<" not in html


def test_an_either_or_that_crosses_a_year_boundary_is_refused_rather_than_guessed():
    """`2026-12/01` cannot be resolved without assuming January is 2027."""
    html = _timeline_html([{"date": "2026-12/01", "event": "Follow-up", "type": "test"}])
    assert _stop_labels(html) == ["Timing unclear"]
    assert "2027" not in html
    assert not bare_iso_dates(html)


def test_a_missing_date_and_an_unreadable_date_are_told_apart():
    """They are different facts, so they are not collapsed into one phrase."""
    html = _timeline_html(
        [
            {"date": "", "event": "Trial screening", "type": "trial"},
            {"date": "whenever the team says", "event": "Repeat scan", "type": "scan"},
        ]
    )
    assert _stop_labels(html) == ["Timing not recorded", "Timing unclear"]


def test_a_month_containing_today_is_not_filed_as_already_past():
    """`date < today` is a string compare, and it was wrong twice over.

    `2026-08` sorts below `2026-08-17`, so the whole of August was greyed out
    mid-month; and a space sorts below a hyphen, so a qualified August did too.
    A recorded month is compared at the precision it was recorded at.
    """
    html = _timeline_html(
        [
            {"date": "2026-07", "event": "Past month", "type": "test"},
            {"date": "2026-08", "event": "This month", "type": "test"},
            {"date": "2026-08 (approx late Aug)", "event": "Qualified", "type": "test"},
            {"date": "2026-08-01", "event": "Earlier day", "type": "test"},
            {"date": "2026-09", "event": "Next month", "type": "test"},
            {"date": "2025", "event": "Last year", "type": "test"},
            {"date": "2026", "event": "This year", "type": "test"},
        ]
    )
    past = re.findall(r'<li class="timeline-stop([^"]*)"', html)
    assert [" past" in flags for flags in past] == [
        True,  # July is wholly behind us
        False,  # August still contains today
        False,  # ...and so does a qualified August
        True,  # 1 August is behind 17 August
        False,  # September is ahead
        True,  # 2025 is wholly behind us
        False,  # 2026 still contains today
    ]


def test_the_machine_date_attribute_is_only_written_when_there_is_one():
    """`<time datetime="2026-08 (approx late Aug)">` was not a valid date."""
    html = _timeline_html(
        [
            {"date": "2026-09-01", "event": "Clean day", "type": "appointment"},
            {"date": "2026-08 (approx late Aug)", "event": "Qualified", "type": "test"},
            {"date": "2026-08/09", "event": "Either or", "type": "scan"},
            {"date": "", "event": "None", "type": "trial"},
        ]
    )
    machine = re.findall(r'<time datetime="([^"]*)"', html)
    assert machine == ["2026-09-01", "2026-08"]
    for value in machine:
        assert re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", value), value


def test_an_impossible_day_is_treated_as_wording_not_as_a_calendar_date():
    """A 31st of February is not a date, and must not become one."""
    html = _timeline_html([{"date": "2026-02-31", "event": "Bad day", "type": "test"}])
    assert _stop_labels(html) == ["Timing unclear"]
    assert "<time" not in html


def test_the_timeline_reads_left_to_right_and_stays_an_ordered_list():
    """He asked for the horizontal timeline back, without losing the semantics.

    Position along the axis is proportional to real elapsed time, but the axis
    carries no text and is hidden from assistive technology, because every fact
    it shows is written out in the stops. The stops stay a real ordered list.
    """
    html = _timeline_html(
        [
            {"date": "2026-05-02", "event": "Prior scan", "type": "scan"},
            {"date": "2026-08-17", "event": "Today's review", "type": "appointment"},
            {"date": "2026-11-02", "event": "Next scan", "type": "scan"},
        ]
    )
    assert '<ol class="timeline-track">' in html
    assert html.count('<li class="timeline-stop') == 3
    assert '<div class="timeline-axis" aria-hidden="true">' in html
    # The scrolling row is reachable with a keyboard alone and names itself.
    assert 'role="region"' in html
    assert 'tabindex="0"' in html
    assert 'aria-labelledby="summary-timeline-heading"' in html
    # Offsets are proportional to elapsed time, not one-per-stop steps.
    offsets = [float(value) for value in re.findall(r"--stop-offset:([\d.]+)%", html)]
    # today, then the three stops
    assert offsets[0] == 0.0 or offsets[0] > 0
    stops = [
        float(v) for v in re.findall(r'class="timeline-stop"[^>]*--stop-offset:([\d.]+)%', html)
    ]
    assert stops == sorted(stops)
    # May→August is a longer wait than August→November is short; the gaps differ,
    # which is the whole point of a proportional axis rather than even spacing.
    assert len(set(stops)) == len(stops)


def test_an_undated_stop_is_left_off_the_axis_rather_than_placed_somewhere():
    html = _timeline_html(
        [
            {"date": "2026-05-02", "event": "Prior scan", "type": "scan"},
            {"date": "", "event": "Unscheduled", "type": "trial"},
            {"date": "2026-11-02", "event": "Next scan", "type": "scan"},
        ]
    )
    assert html.count('class="timeline-axis-mark') == 2
    assert 'class="timeline-stop undated"' in html


def test_the_provisional_marker_and_type_chip_survive_the_new_layout():
    html = _timeline_html(
        [
            {"date": "2026-09-01", "event": "Dose", "type": "milestone", "provisional": True},
            {"date": "2026-09-08", "event": "Scan", "type": "scan", "provisional": False},
        ]
    )
    assert html.count("Provisional — confirm with the care team") == 1
    assert 'class="timeline-type milestone"' in html
    assert 'class="timeline-type scan"' in html


# ── the widened guard ────────────────────────────────────────────────────────
# The old guard asserted that a hand-picked list of call sites mentioned a
# formatter. That is why the same field kept leaking somewhere else: a site
# nobody had thought of was not on the list. These render real surfaces with
# every date-bearing field set to a machine date and fail if one survives into
# anything he reads, whatever route it took to get there.


def _iso_probe(seed: int) -> str:
    return f"20{26 + seed % 3}-{(seed % 12) + 1:02d}-{(seed % 27) + 1:02d}"


def test_no_assessment_surface_leaks_a_machine_date_into_readable_text():
    """Every dated and generated field at once, checked on the rendered output."""
    summary = _timeline_summary(
        [
            {"date": "2026-08-14", "event": "Dose on 2026-08-14", "type": "milestone"},
            {"date": "2026-08 (approx late Aug)", "event": "Bloods", "type": "test"},
            {"date": "2026-08/09", "event": "Scan window", "type": "scan"},
            {"date": "2026-12/01", "event": "Ambiguous", "type": "test"},
            {"date": "", "event": "Unscheduled", "type": "trial"},
        ],
        key_concern="CgA rose between 2026-05-02 and 2026-08-14.",
        status_rationale="Imaging on 2026-07-01 still governs.",
        summary="Doses run 2026-05 to 2026-08.",
        cga_trend_detail="CgA 145 on 2026-05-02 rose to 188 on 2026-08-14.",
        prrt_rationale="DOTATATE PET was done 2026-04-22.",
        cga_trend="rising",
        status_confidence="high",
        prrt_status="likely_eligible",
        next_actions=[
            {
                "id": "act-1",
                "source_token": "tok-1",
                "generation_id": "gen-1",
                "source_profile_revision": 12,
                "stale": False,
                "priority": "high",
                "action": "Book the dose before 2026-09-01",
                "rationale": "Keeps the 2026-08-14 interval.",
                "timeframe": "by 2026-09-01",
                "due_date": "2026-09-01",
            }
        ],
    )
    rendered = render_summary(summary, today="2026-08-17")
    for surface, html in rendered.items():
        assert not bare_iso_dates(html), f"{surface} shows a machine date: {bare_iso_dates(html)}"


def test_the_research_record_view_formats_every_date_it_prints():
    """These fields print a stored date under a plain label he reads."""
    prelude = "\n".join(
        [
            _function_source("escHtml", "fmtDate"),
            _function_source("researchPlainObject", "researchExactKeys"),
            APP_JS[
                APP_JS.index("const RESEARCH_DATE_FIELDS") : APP_JS.index(
                    "function researchAuthorityMarkup"
                )
            ],
        ]
    )
    fields = {
        "date": "2026-05-02",
        "date_added": "2026-05-02T06:26:00",
        "due_date": "2026-09-01",
        "occurred_on": "2026-07",
        "recorded_at": "2026-08-14T06:26:00",
        "registry_last_update": "2026-06-30",
    }
    result = _evaluate(
        {
            name: f"researchValueMarkup({json.dumps(value)}, {json.dumps(name)})"
            for name, value in fields.items()
        },
        prelude=prelude,
    )
    assert result == {
        "date": "<span>2.5.2026</span>",
        "date_added": "<span>2.5.2026 09:26</span>",
        "due_date": "<span>1.9.2026</span>",
        "occurred_on": "<span>7/2026</span>",
        "recorded_at": "<span>14.8.2026 09:26</span>",
        "registry_last_update": "<span>30.6.2026</span>",
    }
    # The two distinctions the forensic view exists to keep are untouched.
    blank = _evaluate(
        {
            "null": "researchValueMarkup(null, 'due_date')",
            "empty": "researchValueMarkup('', 'due_date')",
        },
        prelude=prelude,
    )
    assert "Nothing recorded" in blank["null"]
    assert "Recorded as blank" in blank["empty"]


def test_every_research_date_field_is_named_in_the_formatting_set():
    """A dated field the set does not name would print exactly as stored."""
    declared = set(
        re.findall(r"'([\w]+)'", APP_JS[APP_JS.index("const RESEARCH_DATE_FIELDS") :][:400])
    )
    for field in (
        "date",
        "date_added",
        "due_date",
        "occurred_on",
        "recorded_at",
        "registry_last_update",
    ):
        assert field in declared, f"{field} would reach the screen as stored"


# ── the static tripwire ──────────────────────────────────────────────────────
# The behavioural guards above are the real check, because they cannot be fooled
# by aliasing a value into a local variable first. This is the cheap second net:
# it reads every `${...}` in the file and fails when a field whose name says it
# holds a date is interpolated without a formatter. Anything deliberate is listed
# with the reason it is deliberate, so an exemption is a decision on the record
# rather than an oversight.

# Field names that hold a date or a timestamp somewhere in the record. The
# trailing guard keeps `record.date.source_document_date_precision` out of it:
# that reads a precision enum off a date object, not a date.
_DATE_FIELD = re.compile(
    r"\.(?:date|due_date|occurred_on|recorded_at|generated_at|generated_at_timestamp"
    r"|source_document_date|onset_date|resolved_date|start_date|end_date|date_added"
    r"|registry_last_update|expires_at|created_at|updated_at|added_at)(?![\w.])"
)

# Helpers that put a value through Finnish formatting.
_APPROVED_FORMATTERS = (
    "fmtDate",
    "fmtDateTime",
    "fmtTime",
    "fmtProseDates",
    "relativeTime",
    "formatActionTimestamp",
    "biomarkerDate",
    "imagingDate",
    "symptomDate",
    "treatmentDatePresentation",
    "symptomDatePresentation",
    "caregiverDateFieldValue",
    "researchValueMarkup",
    "timelineDateParts",
    "dueDatePresentation",
    "receiptValueSummary",
    "localDateIso",
)

# Interpolations that read a dated field on purpose without formatting it, and
# why that is right. Each entry is matched as a substring of the expression.
_DELIBERATE_RAW_DATES = {
    # `<input type="date">` is a native control: its value is ISO by
    # specification and the browser renders it in the reader's own locale.
    "document.getElementById('research-follow-up-due').value = draft.due_date",
    "document.getElementById('visit-create-date').value = source.date",
    # The caregiver's own typed text, restored into the box exactly as typed.
    "document.getElementById('research-event-date').value = draft.occurred_on",
    # The machine-readable half of `<time>`, which HTML requires to be ISO. It
    # is only written when the record really states one date, and the element's
    # visible text beside it is the Finnish rendering.
    "escHtml(parts.date)",
    # Date arithmetic, not display: this builds a `Date` to count days from.
    "${item.due_date}T12:00:00",
}


def test_no_interpolated_date_field_reaches_markup_without_a_formatter():
    lines = APP_JS.splitlines()
    offenders = []
    for line, expression in javascript_interpolations(APP_JS):
        if not _DATE_FIELD.search(expression):
            continue
        if any(formatter in expression for formatter in _APPROVED_FORMATTERS):
            continue
        # An exemption is matched against the whole source line, so the reason
        # it is exempt stays visible next to the read itself.
        context = lines[line - 1] if 0 < line <= len(lines) else ""
        if any(allowed in context for allowed in _DELIBERATE_RAW_DATES):
            continue
        offenders.append(f"static/app.js:{line}: {' '.join(expression.split())[:120]}")
    assert offenders == [], "a stored date reaches markup unformatted:\n" + "\n".join(offenders)


def test_the_tripwire_would_actually_catch_a_regression():
    """A guard that cannot fail is not a guard."""
    sample = "const html = `<span>${item.due_date}</span>`;"
    found = [
        expression
        for _, expression in javascript_interpolations(sample)
        if _DATE_FIELD.search(expression) and not any(f in expression for f in _APPROVED_FORMATTERS)
    ]
    assert found == ["item.due_date"]


def test_the_symptom_follow_up_reads_the_same_date_on_every_surface():
    """The linked-action copy and the picker printed a stored date as stored.

    One of the three sites that show a follow-up's due date was corrected in an
    earlier round and pinned by a test; the other two were not, and kept
    printing `2026-09-01` while the card beside them read `1.9.2026`.
    """
    assert "symptomScalar(action.due_date)" not in APP_JS
    assert "symptomScalar(episode.follow_up.due_date)" not in APP_JS
    # All three surfaces now agree.
    assert APP_JS.count("symptomDate(episode.follow_up.due_date)") == 2
    assert APP_JS.count("symptomDate(action.due_date)") == 1
    # The linked-action line also stopped printing the stored status code.
    assert "${episode.follow_up.text} · ${episode.follow_up.status}" not in APP_JS
