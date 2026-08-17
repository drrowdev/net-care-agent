"""The assessment timeline in a real browser, at the widths he actually uses.

He asked for the horizontal timeline back. The one that was removed was an SVG
graph with hover-only tooltips, a 400px floor that overflowed a phone, and event
labels cut to 19 characters, so it could not simply be restored. This checks the
replacement keeps the horizontal reading on a desktop, keeps its list semantics
and keyboard reach everywhere, and never pushes the page sideways — including at
360px, where it falls back to the vertical arrangement on purpose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
APP_JS = Path("static/app.js").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")

# Two past stops, one inside the current month, one clearly ahead, one that only
# ever had a qualifier, one either/or and one with no timing at all.
_TIMELINE = [
    {"date": "2026-05-02", "event": "PET-CT before the third dose", "type": "scan"},
    {"date": "2026-07-01", "event": "Bloods reviewed with the team", "type": "test"},
    {
        "date": "2026-08 (approx late Aug)",
        "event": "Third dose",
        "type": "milestone",
        "provisional": True,
    },
    {"date": "2026-08/09", "event": "Scan window", "type": "scan", "provisional": True},
    {"date": "2026-11-02", "event": "Oncology review", "type": "appointment"},
    {"date": "", "event": "Trial screening", "type": "trial", "provisional": True},
]

_SUMMARY = {
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
    "timeline": _TIMELINE,
    "claim_evidence": {"claims": {}, "actions": []},
}


def _open(playwright, width: int, height: int):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.route(
        "**/api/**",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    page.set_content(html)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content=APP_JS)
    page.evaluate("() => { clearTimeout(pollingInterval); pollingInterval = null; }")
    # Pin today so past/upcoming is stable whenever the suite runs.
    page.evaluate("() => { localDateIso = () => '2026-08-17'; }")
    page.evaluate("summary => renderSummary(summary)", _SUMMARY)
    page.locator(".timeline-track").wait_for(state="visible")
    return browser, context, page


def test_the_timeline_is_horizontal_readable_and_overflow_safe_at_every_width():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        for width, height in ((1280, 900), (768, 900), (360, 800)):
            browser, context, page = _open(playwright, width, height)
            errors: list[str] = []
            page.on("pageerror", lambda error, target=errors: target.append(str(error)))
            try:
                horizontal = width > 720

                # Every stop is present and the list is a real ordered list.
                assert page.locator(".timeline-track").evaluate("el => el.tagName") == "OL"
                assert page.locator(".timeline-stop").count() == len(_TIMELINE)

                # Dates read Finnish, the qualifier survives, and neither month
                # of the either/or has been quietly dropped.
                text = page.locator(".timeline-track").inner_text()
                assert "2.5.2026" in text
                assert "8/2026 (approx late Aug)" in text
                assert "8/2026 or 9/2026" in text
                assert "Timing not recorded" in text
                assert not re.search(r"(?<!\d)\d{4}-\d{2}(?:-\d{2})?(?!\d)", text), text

                # The provisional marker and the type chips survived the change.
                assert page.locator(".timeline-provisional").count() == 3
                assert page.locator(".timeline-type").count() == len(_TIMELINE)
                # Past and upcoming are still told apart, and the month that
                # still contains today is not filed as past.
                assert page.locator(".timeline-stop.past").count() == 2

                # `<time datetime>` is only written when there is a real date.
                machine = page.locator(".timeline-stop time").evaluate_all(
                    "nodes => nodes.map(n => n.getAttribute('datetime'))"
                )
                assert machine == ["2026-05-02", "2026-07-01", "2026-08", "2026-11-02"]

                layout = page.evaluate(
                    """() => {
                      const doc = document.documentElement;
                      const track = document.querySelector('.timeline-track');
                      const scroll = document.querySelector('.timeline-scroll');
                      const axis = document.querySelector('.timeline-axis');
                      const stops = [...document.querySelectorAll('.timeline-stop')];
                      const tops = new Set(stops.map(s => Math.round(
                        s.getBoundingClientRect().top)));
                      return {
                        pageOverflow: doc.scrollWidth - doc.clientWidth,
                        axisShown: axis ? getComputedStyle(axis).display !== 'none' : false,
                        sameRow: tops.size === 1,
                        rowCount: tops.size,
                        scrollFits: scroll.scrollWidth <= scroll.clientWidth,
                        trackWidth: track.scrollWidth,
                      };
                    }"""
                )

                # Nothing ever pushes the page sideways.
                assert layout["pageOverflow"] == 0, (width, layout)

                if horizontal:
                    # Time runs left to right: the stops share one row.
                    assert layout["sameRow"], (width, layout)
                    assert layout["axisShown"], width
                else:
                    # On a phone the stops stack and the axis is dropped, so the
                    # row is not a sideways-scrolling region at all.
                    assert layout["rowCount"] == len(_TIMELINE), (width, layout)
                    assert not layout["axisShown"], width
                    assert layout["scrollFits"], (width, layout)

                # The scrolling row is reachable by keyboard alone and named.
                region = page.locator(".timeline-scroll")
                assert region.get_attribute("role") == "region"
                assert region.get_attribute("tabindex") == "0"
                labelled = region.get_attribute("aria-labelledby")
                # The section label is upper-cased by CSS, so compare the words.
                assert (
                    page.locator(f"#{labelled}").inner_text().lower() == "what changed / upcoming"
                )
                page.evaluate("() => document.querySelector('.timeline-scroll').focus()")
                assert page.evaluate(
                    "() => document.activeElement.classList.contains('timeline-scroll')"
                )

                # The axis is decoration; the facts are all in the stops.
                if layout["axisShown"]:
                    assert page.locator(".timeline-axis").get_attribute("aria-hidden") == "true"
                    assert page.locator(".timeline-axis").inner_text().strip() == ""
                    # Only the four dated stops are placed on it.
                    assert page.locator(".timeline-axis-mark").count() == 4

                assert errors == []
            finally:
                context.close()
                browser.close()


def test_the_axis_positions_stops_by_elapsed_time_not_by_even_steps():
    """Even spacing would be a stepper. The gaps have to reflect real time."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open(playwright, 1280, 900)
        try:
            offsets = page.evaluate(
                """() => [...document.querySelectorAll('.timeline-axis-mark')]
                     .map(el => parseFloat(el.style.getPropertyValue('--stop-offset')))"""
            )
            assert offsets == sorted(offsets)
            gaps = [round(b - a, 2) for a, b in zip(offsets, offsets[1:], strict=False)]
            # May→July, July→August and August→November are different lengths of
            # time, so they must be different distances on the axis.
            assert len(set(gaps)) == len(gaps), gaps
            # A month-precision stop is a band across the month it names, never
            # a point on an invented day inside it.
            spans = page.evaluate(
                """() => [...document.querySelectorAll('.timeline-axis-mark')]
                     .map(el => parseFloat(el.style.getPropertyValue('--stop-span')))"""
            )
            assert spans[0] == 0 and spans[1] == 0 and spans[3] == 0
            assert spans[2] > 0
        finally:
            context.close()
            browser.close()


def test_the_stored_assessment_is_never_rewritten_to_make_it_display():
    """Display improves the reading; it does not edit the record."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open(playwright, 1280, 900)
        try:
            after = page.evaluate(
                "summary => { renderSummary(summary); return summary; }",
                json.loads(json.dumps(_SUMMARY)),
            )
            assert after["timeline"] == _TIMELINE
        finally:
            context.close()
            browser.close()
