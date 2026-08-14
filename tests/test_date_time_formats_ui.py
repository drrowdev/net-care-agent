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
import subprocess
from pathlib import Path

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
