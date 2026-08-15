"""How the generated assessment reads on screen.

Two things the caregiver reported about the Today assessment are pinned here.

First, the evidence chip. The assessment is generated narrative, so most of its
claims legitimately have no verbatim source span, and the panel said so on every
recommendation, every key concern and every paragraph. A fixed sentence repeated
down the whole page carries no information. The chip is now drawn only when it
does: a link to the exact wording, or the genuine anomaly of linked wording that
has gone missing. Nothing about *which* claims are verified changes — that is
resolved server-side and is asserted in `test_claim_evidence.py`.

Second, ISO dates inside the model's own sentences. Every dated *field* is
localised, but a date the model wrote into a sentence is just text, so it
reached the screen as `2026-05-07` beside fields reading `7.5.2026`. Render-time
normalisation is a lossless transcription of an unambiguous pattern — no word is
added, removed or reordered, the stored text is untouched, and anything that
could be structural is left exactly as written.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _function_source(name: str, next_name: str) -> str:
    start = APP_JS.index(f"function {name}")
    end = APP_JS.index(f"function {next_name}", start)
    return APP_JS[start:end]


def _run_node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _render_claim_evidence(items: object) -> str:
    """Run the real chip renderer over one resolved evidence list."""
    script = "\n".join(
        [
            _function_source("escHtml", "fmtDate"),
            _function_source("renderClaimEvidence", "renderSummary"),
            f"const items = {json.dumps(items)};",
            "console.log(JSON.stringify({ html: renderClaimEvidence(items) }));",
        ]
    )
    return _run_node(script)["html"]


_SUMMARY_HARNESS = """
class FakeClassList {
  add() {}
  remove() {}
  toggle() {}
  contains() { return false; }
}

function fakeElement() {
  return {
    classList: new FakeClassList(),
    className: '',
    dataset: {},
    disabled: false,
    hidden: false,
    innerHTML: '',
    style: {},
    textContent: '',
    closest() { return null; },
    querySelector() { return null; },
    remove() {},
    removeAttribute() {},
    setAttribute() {},
  };
}

const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, fakeElement());
    return elements.get(id);
  },
  querySelectorAll() { return []; },
};

function renderFreshness() {}
function summaryIsStale() { return false; }
function generatedActionAccepted() { return false; }
function refreshGeneratedActionControls() {}
function followUpControlsLocked() { return false; }
function setFollowUpMutationBusy() {}
function translateType(value) { return value; }
"""


def _render_summary(summary: dict) -> dict:
    """Render a whole assessment through the real `renderSummary`."""
    script = "\n".join(
        [
            _SUMMARY_HARNESS,
            _function_source("safeClassToken", "safeExternalUrl"),
            _function_source("escHtml", "fmtDate"),
            _function_source("fmtDate", "copyReport"),
            _function_source("summaryActionIsCurrent", "generatedActionAccepted"),
            _function_source("renderClaimEvidence", "renderSummary"),
            _function_source("renderSummary", "researchPlainObject"),
            f"renderSummary({json.dumps(summary)});",
            "console.log(JSON.stringify({",
            "  body: document.getElementById('summary-body').innerHTML,",
            "  updated: document.getElementById('summary-updated').textContent,",
            "}));",
        ]
    )
    return _run_node(script)


def _current_action(**overrides) -> dict:
    action = {
        "id": "act-1",
        "source_token": "tok-1",
        "generation_id": "gen-1",
        "source_profile_revision": 12,
        "stale": False,
        "priority": "high",
        "action": "Book the next dose",
        "rationale": "Keeps the interval on schedule.",
        "timeframe": "this month",
    }
    action.update(overrides)
    return action


def _summary(**overrides) -> dict:
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
        "timeline": [],
        "claim_evidence": {"claims": {}, "actions": []},
    }
    summary.update(overrides)
    return summary


_VERIFIED = {
    "evidence_id": "ev-1",
    "label": "CgA 234 ng/mL",
    "evidence_status": "verified",
    "evidence_url": "/api/evidence/doc-1?start=10&end=24",
}
_MISSING = {"label": "No exact source span linked", "evidence_status": "missing"}
_INVALID = {
    "evidence_id": "ev-invented",
    "label": "Invalid or unavailable evidence reference",
    "evidence_status": "invalid",
}


# ── The evidence chip ────────────────────────────────────────────────────────


def test_routine_missing_evidence_draws_no_chip_and_no_empty_container():
    """The ordinary case for generated prose is silent, container and all."""
    for items in ([_MISSING], [], None, [_MISSING, _MISSING]):
        assert _render_claim_evidence(items) == ""


def test_verified_evidence_still_links_to_the_exact_wording():
    html = _render_claim_evidence([_VERIFIED])
    assert 'class="claim-evidence"' in html
    assert 'href="/api/evidence/doc-1?start=10&amp;end=24"' in html
    assert "View exact wording: CgA 234 ng/mL" in html
    assert 'rel="noopener"' in html


def test_invalid_evidence_stays_visible_because_it_is_a_real_anomaly():
    html = _render_claim_evidence([_INVALID])
    assert 'class="claim-evidence"' in html
    assert "Linked wording is unavailable" in html


def test_missing_entries_drop_out_of_a_mixed_list_without_dropping_the_rest():
    html = _render_claim_evidence([_MISSING, _VERIFIED, _MISSING, _INVALID])
    assert html.count('class="claim-evidence"') == 1
    assert "View exact wording: CgA 234 ng/mL" in html
    assert "Linked wording is unavailable" in html
    assert "No exact wording is linked" not in html


def test_the_fixed_no_wording_sentence_is_gone_from_the_interface():
    assert "No exact wording is linked" not in APP_JS


def test_an_unverified_status_never_dresses_itself_up_as_a_link():
    """A status the interface does not recognise stays silent, never verified."""
    unknown = {"label": "x", "evidence_status": "speculative", "evidence_url": "/api/evidence/d"}
    assert _render_claim_evidence([unknown]) == ""
    assert _render_claim_evidence([{**_VERIFIED, "evidence_url": ""}]) == ""


def test_a_whole_generated_assessment_carries_no_chip_noise():
    rendered = _render_summary(
        _summary(
            key_concern="Watch the interval between doses.",
            status_rationale="Imaging and CgA agree.",
            summary="The plan is holding.",
            cga_trend_detail="CgA 145 to 188 nmol/L",
            prrt_rationale="Screening only.",
            next_actions=[_current_action()],
            claim_evidence={
                "claims": {
                    "key_concern": [_MISSING],
                    "status_rationale": [_MISSING],
                    "summary": [_MISSING],
                    "cga_trend_detail": [_MISSING],
                    "prrt_rationale": [_MISSING],
                },
                "actions": [[_MISSING]],
            },
        )
    )
    body = rendered["body"]
    assert "claim-evidence" not in body
    # The claims themselves are all still on screen.
    for text in (
        "Watch the interval between doses.",
        "Imaging and CgA agree.",
        "The plan is holding.",
        "Book the next dose",
    ):
        assert text in body


def test_a_verified_claim_inside_a_full_assessment_keeps_its_link():
    rendered = _render_summary(
        _summary(
            summary="The plan is holding.",
            next_actions=[_current_action()],
            claim_evidence={
                "claims": {"summary": [_VERIFIED]},
                "actions": [[_MISSING]],
            },
        )
    )
    assert rendered["body"].count('class="claim-evidence"') == 1
    assert "View exact wording: CgA 234 ng/mL" in rendered["body"]


# ── ISO dates inside generated prose ─────────────────────────────────────────


def test_generated_prose_dates_render_in_the_same_finnish_shape_as_every_field():
    rendered = _render_summary(
        _summary(
            key_concern="PET-CT on 2026-04-22 confirmed progression.",
            status_rationale="Doses run 2026-05 to 2026-08.",
            summary="Three doses every 8 weeks from 2026-05-07, third around late August 2026.",
            cga_trend_detail="CgA rose between 2026-02-11 and 2026-04-22.",
            prrt_rationale="Receptor imaging reviewed 2026-04-22.",
            next_actions=[
                _current_action(
                    action="Confirm the dose booked for 2026-09-01",
                    rationale="The interval closes 2026-08-26.",
                    timeframe="before 2026-08-20",
                )
            ],
            timeline=[
                {"date": "2026-09-01", "event": "Third dose due 2026-09-01", "type": "appointment"}
            ],
        )
    )
    body = rendered["body"]
    for finnish in (
        "PET-CT on 22.4.2026 confirmed progression.",
        "Doses run 5/2026 to 8/2026.",
        "Three doses every 8 weeks from 7.5.2026, third around late August 2026.",
        "CgA rose between 11.2.2026 and 22.4.2026.",
        "Receptor imaging reviewed 22.4.2026.",
        "Confirm the dose booked for 1.9.2026",
        "The interval closes 26.8.2026.",
        "before 20.8.2026",
        "Third dose due 1.9.2026",
    ):
        assert finnish in body
    # No ISO date survives anywhere the caregiver reads.
    for iso in ("2026-04-22", "2026-05-07", "2026-08-26", "2026-09-01</span>"):
        assert iso not in body


def test_machine_readable_and_server_bound_values_keep_the_stored_iso_text():
    """Only what the caregiver reads is reformatted; the wire stays ISO."""
    rendered = _render_summary(
        _summary(
            next_actions=[_current_action(action="Confirm the dose booked for 2026-09-01")],
            timeline=[{"date": "2026-09-01", "event": "Third dose", "type": "appointment"}],
        )
    )
    body = rendered["body"]
    # The concurrency token the dismiss call sends back must match stored text.
    assert 'data-action-text="Confirm the dose booked for 2026-09-01"' in body
    # <time datetime> is machine-readable and stays ISO-8601 by definition.
    assert '<time datetime="2026-09-01">1.9.2026</time>' in body


def test_a_year_alone_and_a_written_out_month_are_left_completely_untouched():
    rendered = _render_summary(
        _summary(summary="Reviewed in 2026, again in April 2026 and by late August 2026.")
    )
    assert "Reviewed in 2026, again in April 2026 and by late August 2026." in rendered["body"]


def test_a_date_like_identifier_or_url_in_prose_is_never_rewritten():
    prose = (
        "Report doc-2026-05-07-abc, file report-2026-05-07.pdf, stamp 2026-05-07T10:30:00 "
        "and https://example.org/reports/2026-05-07/summary all stay as recorded."
    )
    rendered = _render_summary(_summary(summary=prose))
    assert prose in rendered["body"]


def test_an_impossible_calendar_value_is_left_alone_rather_than_guessed_at():
    prose = "Range 1234-56, month 2026-13 and day 2026-05-45 are not dates."
    assert prose in _render_summary(_summary(summary=prose))["body"]


def test_escaping_still_holds_after_the_date_transformation():
    """The rewrite happens on the text value; escaping runs after it, once."""
    rendered = _render_summary(
        _summary(
            key_concern="<script>alert('x')</script> on 2026-05-07",
            summary='Ampersand & "quote" on 2026-05-07',
            next_actions=[
                _current_action(
                    action="<img src=x onerror=alert(1)> due 2026-05-07",
                    rationale="",
                    timeframe="<b>2026-05-07</b>",
                )
            ],
            timeline=[{"date": "2026-05-07", "event": "<i>2026-05-07</i>", "type": "scan"}],
        )
    )
    body = rendered["body"]
    assert "<script>" not in body
    assert "<img src=x" not in body
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt; on 7.5.2026" in body
    assert "&lt;img src=x onerror=alert(1)&gt; due 7.5.2026" in body
    assert "&lt;b&gt;7.5.2026&lt;/b&gt;" in body
    assert "&lt;i&gt;7.5.2026&lt;/i&gt;" in body
    # Escaped once, never twice.
    assert "Ampersand &amp; &quot;quote&quot; on 7.5.2026" in body
    assert "&amp;amp;" not in body
    assert "&amp;lt;" not in body
