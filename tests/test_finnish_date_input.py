"""Typed dates may be Finnish, and mean exactly what he typed.

The record shows `14.8.2026`, `8/2026` and `2026`, so those are now the shapes
he may type as well. Storage does not move: the same ISO text is kept, at the
same precision. The ISO forms he learned earlier still work.

What matters clinically is what is *refused*. A date that is silently misread
is far worse than one that is turned away, so `14/8/2026` (day/month order
cannot be trusted), `31.2.2026` (no such day) and `14.8.26` (which century?)
are rejected rather than guessed at. Every case below is asserted twice — once
against the Python parser and once against the browser's — because a form the
browser accepts and the server refuses would strand him mid-entry.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from agent.date_input import (
    DateInputError,
    parse_full_date,
    parse_partial_date,
    read_date_input,
)

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")

# (typed, stored, precision). A stored value of None means the entry is refused.
GRAMMAR: list[tuple[str, str | None, str | None]] = [
    # ── Finnish, the way he reads the record ─────────────────────────────────
    ("14.8.2026", "2026-08-14", "day"),
    ("14.08.2026", "2026-08-14", "day"),
    ("04.08.2026", "2026-08-04", "day"),
    ("4.8.2026", "2026-08-04", "day"),
    ("1.1.2026", "2026-01-01", "day"),
    ("31.12.2026", "2026-12-31", "day"),
    # Finnish writing ends an ordinal date with a full stop. He may type it.
    ("14.8.2026.", "2026-08-14", "day"),
    ("4.8.2026.", "2026-08-04", "day"),
    ("8/2026", "2026-08", "month"),
    ("08/2026", "2026-08", "month"),
    ("12/2026", "2026-12", "month"),
    ("2026", "2026", "year"),
    # Surrounding whitespace is his keyboard, not his meaning.
    ("  14.8.2026  ", "2026-08-14", "day"),
    (" 8/2026 ", "2026-08", "month"),
    (" 2026 ", "2026", "year"),
    # Leap days are real days, and only in leap years.
    ("29.2.2024", "2024-02-29", "day"),
    ("29.2.2000", "2000-02-29", "day"),
    # ── ISO, which he already knows, unchanged ───────────────────────────────
    ("2026-08-14", "2026-08-14", "day"),
    ("2026-08", "2026-08", "month"),
    ("2026-02-29", None, None),  # 2026 is not a leap year, in either notation
    # ── refused ──────────────────────────────────────────────────────────────
    ("", None, None),
    ("   ", None, None),
    ("-", None, None),
    ("today", None, None),
    ("13.13.2026", None, None),  # no thirteenth month
    ("31.2.2026", None, None),  # no such day
    ("29.2.2026", None, None),  # not a leap year
    ("0.8.2026", None, None),  # no zeroth day
    ("14.0.2026", None, None),  # no zeroth month
    ("8/13", None, None),  # the year is missing
    ("13/2026", None, None),  # no thirteenth month
    ("0/2026", None, None),
    ("8/0000", None, None),
    ("0000", None, None),
    ("2026-13-01", None, None),
    ("2026-00", None, None),
    ("2026-02-30", None, None),
    ("2026-8-14", None, None),  # not the ISO he was ever shown
    ("14.8.26", None, None),  # a two-digit year is a century guess
    ("14/8/2026", None, None),  # day and month order cannot be trusted
    ("8/14/2026", None, None),
    ("2026.8.14", None, None),  # reversed Finnish is not a Finnish date
    ("2026/8", None, None),
    ("2026.", None, None),
    ("8/2026.", None, None),
    ("14. 8. 2026", None, None),  # only the listed shapes, no near-misses
    ("14.8.2026..", None, None),
    ("2026-W01-1", None, None),  # week notation is not a date he types
    ("20260814", None, None),
    ("+2026", None, None),
    ("١٤.٨.٢٠٢٦", None, None),  # digits from another script are not digits here
    ("2026-08-14T00:00:00", None, None),
]

FULL_DATE_ONLY = [typed for typed, _, precision in GRAMMAR if precision in {"month", "year"}]


# ── the grammar, in Python ───────────────────────────────────────────────────


@pytest.mark.parametrize(("typed", "stored", "precision"), GRAMMAR)
def test_python_reads_every_accepted_form_and_refuses_the_rest(typed, stored, precision):
    read = read_date_input(typed)
    if stored is None:
        assert read is None
    else:
        assert read == (stored, precision)


@pytest.mark.parametrize(("typed", "stored", "precision"), GRAMMAR)
def test_partial_date_stores_exactly_what_was_typed(typed, stored, precision):
    if stored is None:
        with pytest.raises(DateInputError):
            parse_partial_date(typed)
    else:
        assert parse_partial_date(typed) == stored


@pytest.mark.parametrize("typed", FULL_DATE_ONLY)
def test_fields_that_need_a_whole_day_refuse_a_partial_date(typed):
    assert parse_partial_date(typed)  # readable, just not complete
    with pytest.raises(DateInputError) as refused:
        parse_full_date(typed)
    assert str(refused.value) == "Enter the full date as 14.8.2026."


def test_a_refused_date_says_what_may_be_typed_in_plain_words():
    with pytest.raises(DateInputError) as refused:
        parse_partial_date("31.2.2026")
    message = str(refused.value)
    assert message == "Enter the date as 14.8.2026, 8/2026 or 2026."
    for machine in ["YYYY", "ISO", "None", "null", "_date", "regex"]:
        assert machine not in message


def test_nothing_is_ever_filled_in_for_him():
    """A year stays a year. INVARIANTS.md forbids completing what he omitted."""
    assert parse_partial_date("2026") == "2026"
    assert parse_partial_date("8/2026") == "2026-08"


def test_a_value_that_is_not_text_is_refused_rather_than_coerced():
    for value in [None, 2026, 20260814, ["2026-08-14"], {"date": "2026-08-14"}, True]:
        assert read_date_input(value) is None


def test_stored_values_still_classify_at_the_precision_that_was_typed():
    from agent.schema import derive_date_precision

    for typed, stored, precision in GRAMMAR:
        if stored is None:
            continue
        assert derive_date_precision(parse_partial_date(typed)) == precision


# ── the same grammar, in the browser ─────────────────────────────────────────

_NODE_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _js_slice(name: str, next_name: str) -> str:
    start = APP_JS.index(f"function {name}")
    return APP_JS[start : APP_JS.index(f"function {next_name}", start)]


def _caregiver_date_source() -> str:
    """The typed-date parser, plus the formatter it prefills boxes with."""
    return "\n".join(
        [
            _js_slice("readCaregiverDate", "fmtDate"),
            _js_slice("fmtDate", "copyReport"),
        ]
    )


def _run_node(script: str):
    completed = subprocess.run(
        ["node", "-e", _NODE_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, TZ="Europe/Helsinki"),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _browser_reads(values: list[str]):
    script = f"""
{_caregiver_date_source()}
const typed = {json.dumps(values)};
process.stdout.write(JSON.stringify(typed.map(value => ({{
  partial: parseCaregiverDate(value),
  full: parseCaregiverFullDate(value),
  read: readCaregiverDate(value),
}}))));
"""
    return _run_node(script)


def test_the_browser_accepts_and_refuses_exactly_what_the_server_does():
    typed = [case[0] for case in GRAMMAR]
    for case, seen in zip(GRAMMAR, _browser_reads(typed), strict=True):
        entered, stored, precision = case
        assert seen["partial"] == stored, entered
        if stored is None:
            assert seen["read"] is None, entered
        else:
            assert seen["read"] == {"value": stored, "precision": precision}, entered
        assert seen["full"] == (stored if precision == "day" else None), entered


def test_the_browser_and_the_server_trim_exactly_the_same_characters():
    """str.strip() and String.trim() disagree, so neither one is used."""
    padded = [
        " 2026 ",
        "\t2026\n",
        "\r\n2026\x0b\x0c",
        "\ufeff2026",  # byte-order mark: trimmed by String.trim, not str.strip
        "\x1f2026",  # unit separator: trimmed by str.strip, not String.trim
        "\x852026",  # next line: trimmed by str.strip, not String.trim
        "\xa02026",  # non-breaking space: trimmed by both
    ]
    expected = ["2026", "2026", "2026", None, None, None, None]
    for value, want in zip(padded, expected, strict=True):
        if want is None:
            with pytest.raises(DateInputError):
                parse_partial_date(value)
        else:
            assert parse_partial_date(value) == want
    assert [seen["partial"] for seen in _browser_reads(padded)] == expected


def test_a_saved_date_comes_back_in_the_box_exactly_as_he_typed_it():
    """Prefill uses the display format, which is also an accepted input format."""
    round_trip = [
        ("14.8.2026", "14.8.2026"),
        ("04.08.2026", "4.8.2026"),
        ("14.8.2026.", "14.8.2026"),
        ("8/2026", "8/2026"),
        ("08/2026", "8/2026"),
        ("2026", "2026"),
        ("2026-08-14", "14.8.2026"),
        ("2026-08", "8/2026"),
    ]
    stored = [parse_partial_date(typed) for typed, _ in round_trip]
    script = f"""
{_caregiver_date_source()}
const stored = {json.dumps(stored)};
process.stdout.write(JSON.stringify(stored.map(value => caregiverDateFieldValue(value))));
"""
    shown = _run_node(script)
    assert shown == [expected for _, expected in round_trip]

    # And what the box shows can be typed straight back in, unchanged.
    assert [parse_partial_date(value) for value in shown] == stored


def test_a_stored_date_the_parser_cannot_read_is_shown_not_blanked():
    """Blanking it would drop a recorded date on the next save, unasked."""
    script = f"""
{_caregiver_date_source()}
const stored = ['2026-W01-1', '20260814', 'summer 2026', '', null, undefined];
process.stdout.write(JSON.stringify(stored.map(value => caregiverDateFieldValue(value))));
"""
    assert _run_node(script) == ["2026-W01-1", "20260814", "summer 2026", "", "", ""]


def test_an_unreadable_box_never_submits_a_missing_date():
    """A typo must stop the save, not quietly record "no date"."""
    script = f"""
{_caregiver_date_source()}
{_js_slice("caregiverDateEntry", "caregiverFullDateEntry")}
global.document = {{ getElementById: () => ({{ value: '31.2.2026' }}) }};
let thrown = null;
try {{ caregiverDateEntry('x', 'Enter the date as 14.8.2026, 8/2026 or 2026.'); }}
catch (error) {{ thrown = error.message; }}
global.document = {{ getElementById: () => ({{ value: '   ' }}) }};
const empty = caregiverDateEntry('x', 'unused');
global.document = {{ getElementById: () => ({{ value: ' 14.8.2026 ' }}) }};
const good = caregiverDateEntry('x', 'unused');
process.stdout.write(JSON.stringify({{ thrown, empty, good }}));
"""
    assert _run_node(script) == {
        "thrown": "Enter the date as 14.8.2026, 8/2026 or 2026.",
        "empty": None,
        "good": "2026-08-14",
    }


# ── the boxes he actually types into ─────────────────────────────────────────


def test_every_typed_date_box_shows_a_finnish_example():
    for element_id in [
        "research-event-date",
        "symptom-onset-date",
        "symptom-edit-resolved-date",
        "symptom-resolved-date",
    ]:
        line = next(line for line in INDEX_HTML.splitlines() if f'id="{element_id}"' in line)
        assert 'placeholder="14.8.2026, 8/2026 or 2026"' in line, element_id
        # A digits-only phone keypad has no full stop and no slash, which would
        # make Finnish entry impossible on the phone he uses.
        assert 'inputmode="numeric"' not in line, element_id
        # `14.8.2026.` is eleven characters and must not be cut short.
        assert 'maxlength="11"' in line, element_id


def test_the_treatment_and_receipt_boxes_show_a_finnish_example_too():
    assert "input.placeholder = '14.8.2026, 8/2026 or 2026';" in APP_JS
    assert "date.placeholder = '14.8.2026, 8/2026 or 2026';" in APP_JS
    assert "due.placeholder = '14.8.2026';" in APP_JS
    assert "input.maxLength = 11;" in APP_JS
    assert "inputMode = 'numeric'" not in APP_JS


def test_no_typed_date_box_is_validated_against_a_stored_value_classifier():
    """Those classifiers also check server responses; they must stay strict."""
    for validator in ["symptomDateInputIsValid", "treatmentDateInputIsValid"]:
        start = APP_JS.index(f"function {validator}")
        body = APP_JS[start : APP_JS.index("\n  }", start)]
        assert "parseCaregiverDate" in body, validator
        assert "DatePrecision" not in body, validator


# ── the server side, endpoint by endpoint ────────────────────────────────────


@pytest.fixture
def app_module(agent):
    import app as module

    importlib.reload(module)
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def client(app_module):
    with app_module.app.test_client() as test_client:
        yield test_client


def test_symptom_episode_dates_accept_finnish(app_module):
    assert app_module._episode_date("14.8.2026", "onset_date") == ("2026-08-14", "day")
    assert app_module._episode_date("8/2026", "onset_date") == ("2026-08", "month")
    assert app_module._episode_date("2026", "onset_date") == ("2026", "year")
    assert app_module._episode_date("2026-08-14", "onset_date") == ("2026-08-14", "day")
    assert app_module._episode_date(None, "onset_date") == (None, "unknown")
    assert app_module._episode_date("", "onset_date") == (None, "unknown")
    # `DateInputError` subclasses `ValueError`, which is what the endpoints
    # already catch. The reloaded app module carries its own class object, so
    # the base class is what can be asserted here.
    with pytest.raises(ValueError, match="Enter the date as 14.8.2026"):
        app_module._episode_date("31.2.2026", "onset_date")


def test_treatment_course_dates_accept_finnish(app_module):
    assert app_module._treatment_date("14.8.2026", "start_date") == (
        "2026-08-14",
        "day",
        "caregiver_entered",
    )
    assert app_module._treatment_date("8/2026", "start_date") == (
        "2026-08",
        "month",
        "caregiver_entered",
    )
    assert app_module._treatment_date(None, "start_date") == (None, "unknown", "unknown")
    with pytest.raises(ValueError, match="Enter the date as 14.8.2026"):
        app_module._treatment_date("14/8/2026", "start_date")


def test_research_event_dates_accept_finnish():
    from agent.research_disposition import validate_research_date

    assert validate_research_date("14.8.2026") == ("2026-08-14", "day")
    assert validate_research_date("8/2026") == ("2026-08", "month")
    assert validate_research_date("2026") == ("2026", "year")
    assert validate_research_date(None) == (None, "unknown")
    with pytest.raises(ValueError, match="Enter the date as 14.8.2026"):
        validate_research_date("13.13.2026")


def test_follow_up_due_dates_accept_finnish_but_need_a_whole_day():
    from agent.follow_through import FollowThroughError, validate_date

    assert validate_date("14.8.2026", "due_date") == "2026-08-14"
    assert validate_date("2026-08-14", "due_date") == "2026-08-14"
    assert validate_date(None, "due_date") is None
    assert validate_date("", "due_date") is None
    for refused in ["8/2026", "2026", "31.2.2026"]:
        with pytest.raises(FollowThroughError):
            validate_date(refused, "due_date")


def test_receipt_corrections_accept_finnish_at_the_right_precision():
    from agent.reconciliation import ReconciliationError, _validate_collection_value

    imaging = _validate_collection_value(
        "imaging",
        {
            "date": "14.8.2026",
            "date_kind": "study",
            "source_document_date": "8/2026",
            "modality": "CT",
            "impression": "Stable disease.",
        },
    )
    assert imaging["date"] == "2026-08-14"
    assert imaging["date_precision"] == "day"
    assert imaging["source_document_date"] == "2026-08"
    assert imaging["source_document_date_precision"] == "month"

    appointment = _validate_collection_value(
        "appointments",
        {"date": "14.8.2026", "description": "Oncology review", "type": "appointment"},
    )
    assert appointment["date"] == "2026-08-14"

    # An appointment needs a whole day, and an impossible one is refused.
    for refused in ["8/2026", "2026", "31.2.2026"]:
        with pytest.raises(ReconciliationError):
            _validate_collection_value(
                "appointments",
                {"date": refused, "description": "Oncology review", "type": "appointment"},
            )


def test_the_symptom_endpoint_stores_the_finnish_date_he_typed(client, agent):
    created = client.post("/api/symptoms", json={"symptom": "nausea", "date": "14.8.2026"})
    assert created.status_code == 200
    stored = agent.load_profile()["symptoms"][-1]
    assert stored["date"] == "2026-08-14"
    assert stored["date_precision"] == "day"

    patched = client.patch(f"/api/symptoms/{stored['id']}", json={"date": "8/2026"})
    assert patched.status_code == 200
    updated = agent.load_profile()["symptoms"][-1]
    assert updated["date"] == "2026-08"
    assert updated["date_precision"] == "month"


def test_an_impossible_date_is_refused_and_changes_nothing(client, agent):
    before = agent.load_profile().get("symptoms", [])
    refused = client.post("/api/symptoms", json={"symptom": "nausea", "date": "31.2.2026"})
    assert refused.status_code == 400
    assert refused.get_json()["error"] == "Enter the date as 14.8.2026, 8/2026 or 2026."
    assert agent.load_profile().get("symptoms", []) == before


def test_judgment_review_dates_accept_finnish_and_need_a_whole_day(client, agent):
    created = client.post(
        "/api/judgments/add",
        json={
            "text": "Renal function acceptable per oncologist",
            "category": "context",
            "review_after": "14.8.2026",
        },
    )
    assert created.status_code == 200
    judgment = agent.load_profile()["clinical_judgments"][-1]
    assert judgment["review_after"] == "2026-08-14"

    patched = client.patch(f"/api/judgments/{judgment['id']}", json={"valid_until": "31.12.2026"})
    assert patched.status_code == 200
    assert agent.load_profile()["clinical_judgments"][-1]["valid_until"] == "2026-12-31"

    refused = client.patch(f"/api/judgments/{judgment['id']}", json={"valid_until": "8/2026"})
    assert refused.status_code == 400
    assert refused.get_json()["error"] == "Enter the full date as 14.8.2026, or leave it empty."
    assert agent.load_profile()["clinical_judgments"][-1]["valid_until"] == "2026-12-31"
