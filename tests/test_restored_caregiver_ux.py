"""Guards for the three things the caregiver lost in the redesign.

The audit of the redesigned interface found that biomarkers went from a
searchable list of every recent result to a one-at-a-time dropdown, that one
blood result grew to about twelve lines mostly reading "Not recorded", and that
logging a symptom went from one line on Today to a ten-field dialog. These
tests fail against the interface as it stood before those three were restored.

Everything here is presentation. No test asserts that the browser decides
whether a result is abnormal, and one test below asserts the opposite: that the
colour on a row only repeats a comparison the server already made.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.test_biomarker_explorer_ui import (
    _node_prelude,
    _open_biomarker_page,
    _projection,
    _run_node,
)
from tests.test_symptom_workflow_ui import _open_symptom_page

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")

WIDTHS = ((1280, 900), (768, 1024), (360, 800))


def _flagged_projection() -> dict:
    """The standard projection, with one result the report itself flagged."""
    projection = _projection()
    nse = projection["analytes"][1]["observations"][0]
    nse["reported_flag"] = "H"
    nse["reported_flag_authority"] = "source_reported"
    nse["report_range_comparison"] = "above"
    nse["reference_range"] = "0-20"
    return projection


# ── the overview he lost ─────────────────────────────────────────────────────


@pytest.mark.parametrize("width,height", WIDTHS)
def test_every_biomarker_is_on_one_line_without_choosing_one_first(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_biomarker_page(
            playwright,
            width,
            height,
            _flagged_projection(),
        )
        errors: list[str] = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        try:
            rows = page.locator("#biomarker-overview-list .biomarker-overview-row")
            assert rows.count() == 2, "every recorded biomarker should be listed at once"

            cga = rows.nth(0).inner_text()
            nse = rows.nth(1).inner_text()
            # Name, value with its unit, the flag, the date and the reference
            # range — the five facts the pre-redesign row carried. The newest
            # Chromogranin A entry is the month-precision one, so that is the
            # one shown.
            assert "Chromogranin A" in cga
            assert "<5 ng/mL" in cga
            assert "3/2026" in cga
            assert "Reference: 0-100" in cga
            assert "No flag recorded" in cga

            assert "NSE" in nse
            assert "14 ng/mL" in nse
            assert "1.4.2026" in nse
            assert "Reference: 0-20" in nse
            assert "H" in nse

            assert (
                "Showing all 2 biomarkers."
                in page.locator("#biomarker-overview-count").inner_text()
            )

            overflow = page.evaluate(
                """() => document.documentElement.scrollWidth
                     - document.documentElement.clientWidth"""
            )
            assert overflow == 0, f"horizontal overflow at {width}px"

            heights = page.locator(".biomarker-overview-action, #biomarker-search").evaluate_all(
                "items => items.map(item => item.getBoundingClientRect().height)"
            )
            assert heights
            assert all(item >= 44 for item in heights), (width, heights)
            assert errors == []
        finally:
            context.close()
            browser.close()


@pytest.mark.parametrize("width,height", WIDTHS)
def test_search_filters_the_overview_and_the_detailed_table_still_works(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_biomarker_page(
            playwright,
            width,
            height,
            _flagged_projection(),
        )
        errors: list[str] = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        try:
            search = page.locator("#biomarker-search")
            assert search.is_enabled()

            search.fill("nse")
            rows = page.locator("#biomarker-overview-list .biomarker-overview-row")
            assert rows.count() == 1
            assert "NSE" in rows.nth(0).inner_text()
            assert (
                "Showing 1 of 2 biomarkers."
                in page.locator("#biomarker-overview-count").inner_text()
            )

            # The old box matched the recorded aliases too, not just the name
            # the app displays.
            search.fill("s-<cga>")
            assert rows.count() == 1
            assert "Chromogranin A" in rows.nth(0).inner_text()

            search.fill("nothing here")
            assert rows.count() == 0
            assert (
                "No biomarker name matches that search."
                in page.locator("#biomarker-overview-list").inner_text()
            )

            search.fill("nse")
            rows.nth(0).locator(".biomarker-overview-action").click()
            # The detailed table is the point of the row, so it follows the
            # choice and takes the focus with it.
            assert page.locator("#biomarker-analyte-select").input_value() == "analyte-nse"
            assert "NSE" in page.locator("#biomarker-table-caption").inner_text()
            assert page.locator("#biomarker-table-body tr").count() == 1
            assert page.evaluate("() => document.activeElement.id") == "biomarker-table-region"
            assert search.input_value() == "nse", "the search survives choosing a marker"
            assert errors == []
        finally:
            context.close()
            browser.close()


def test_the_latest_result_is_the_newest_date_not_the_most_precise_one():
    """A month-precision 2026 result beats an exact 2020 one.

    The server groups observations by date precision before sorting, so simply
    reading the end of the list would show a six-year-old result as the latest.
    """
    projection = _projection()
    analyte = projection["analytes"][0]
    analyte["observations"][0]["date"] = {
        "value": "2020-01-01",
        "precision": "day",
        "kind": "collection",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }
    analyte["observations"][1]["date"] = {
        "value": "2019-05-01",
        "precision": "day",
        "kind": "collection",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }
    analyte["observations"][2]["date"] = {
        "value": "2026-03",
        "precision": "month",
        "kind": "unknown",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }
    undated = copy.deepcopy(analyte["observations"][2])
    undated["id"] = "obs-cga-undated"
    undated["token"] = "token-obs-cga-undated"
    undated["date"] = {
        "value": None,
        "precision": "unknown",
        "kind": "unknown",
        "source_document_date": None,
        "source_document_date_precision": "unknown",
    }

    script = "\n".join(
        [
            _node_prelude(),
            f"const analyte = {json.dumps(analyte)};",
            f"const undated = {json.dumps(undated)};",
            """
const withUndatedLast = { ...analyte, observations: [...analyte.observations, undated] };
const onlyUndated = { ...analyte, observations: [undated] };
const tied = {
  ...analyte,
  observations: [
    analyte.observations[0],
    { ...analyte.observations[1], date: { ...analyte.observations[2].date } },
    analyte.observations[2],
  ],
};
console.log(JSON.stringify({
  latest: biomarkerLatestObservation(analyte).id,
  ignoresUndated: biomarkerLatestObservation(withUndatedLast).id,
  fallsBack: biomarkerLatestObservation(onlyUndated).id,
  empty: biomarkerLatestObservation({ observations: [] }),
  untied: biomarkerSameDateCount(analyte, biomarkerLatestObservation(analyte)),
  tiedCount: biomarkerSameDateCount(tied, biomarkerLatestObservation(tied)),
  undatedCount: biomarkerSameDateCount(onlyUndated, undated),
}));
""",
        ]
    )
    result = _run_node(script)

    assert result["latest"] == "obs-cga-qualified"
    assert result["ignoresUndated"] == "obs-cga-qualified"
    assert result["fallsBack"] == "obs-cga-undated"
    assert result["empty"] is None
    # Nothing in the record says which of two same-day results came first, so
    # the line says how many there are rather than presenting one as later.
    assert result["untied"] == 1
    assert result["tiedCount"] == 2
    assert result["undatedCount"] == 1


def test_two_results_with_the_same_date_are_disclosed_not_silently_picked():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        projection = _flagged_projection()
        cga = projection["analytes"][0]["observations"]
        cga[1]["date"] = copy.deepcopy(cga[2]["date"])
        browser, context, page, _ = _open_biomarker_page(playwright, 1280, 900, projection)
        try:
            row = page.locator("#biomarker-overview-list .biomarker-overview-row").nth(0)
            assert "2 results carry this date" in row.inner_text()
            assert (
                "results carry this date"
                not in page.locator("#biomarker-overview-list .biomarker-overview-row")
                .nth(1)
                .inner_text()
            )
        finally:
            context.close()
            browser.close()


# ── the twelve-line row ──────────────────────────────────────────────────────


def test_a_row_no_longer_fills_itself_with_not_recorded_but_keeps_every_detail():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        projection = _flagged_projection()
        # Nothing about how this one was measured was recorded, which is the
        # case that used to print "Not recorded" three times in the row itself.
        for observation in projection["analytes"][0]["observations"]:
            observation["specimen"] = None
            observation["assay"] = None
            observation["method"] = None
        browser, context, page, _ = _open_biomarker_page(playwright, 1280, 900, projection)
        errors: list[str] = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        try:
            row = page.locator("#biomarker-table-body tr").first
            closed = row.inner_text()
            assert closed.count("Not recorded") == 0
            assert "Specimen:" not in closed
            assert "Can this be charted?" not in closed
            assert closed.count("\n") <= 5, f"row is still long:\n{closed}"
            # The four things he reads at a glance are still on the row.
            assert "1.1.2026" in closed
            assert "10 ng/mL" in closed
            assert "0-100" in closed
            assert "Show detail" in closed

            row.locator("summary").click()
            opened = row.inner_text()
            # Every fact the old seven-column row carried is still here, missing
            # ones named rather than dropped.
            assert "Specimen: Not recorded" in opened
            assert "Assay: Not recorded" in opened
            assert "Method: Not recorded" in opened
            assert "Can this be charted?" in opened
            assert "Collection date" in opened
            assert "Compared with the report's reference range" in opened
            assert "Flag printed in the document" in opened or "Flag source" in opened
            assert "2 recorded entries" in opened
            assert row.locator("details[open] a").count() >= 1
            assert errors == []
        finally:
            context.close()
            browser.close()


def test_the_browser_never_decides_that_a_result_is_abnormal():
    """Colour repeats a comparison the server made; it does not make one."""
    start = APP_JS.index("const BIOMARKER_RANGE_COMPARISONS")
    end = APP_JS.index("function renderBiomarkerProjection", start)
    region = APP_JS[start:end]

    # No client-side arithmetic against a reference range anywhere in the
    # overview or the row renderer.
    for forbidden in (
        "reference_range_semantics.lower",
        "reference_range_semantics.upper",
        "numeric_value >",
        "numeric_value <",
        "parseFloat(observation.reference_range",
    ):
        assert forbidden not in region, f"the browser is judging results: {forbidden}"

    assert "observation.report_range_comparison" in region
    assert "BIOMARKER_RANGE_COMPARISONS[comparison] || null" in region

    script = "\n".join(
        [
            _node_prelude(),
            """
console.log(JSON.stringify({
  above: biomarkerRangeComparison({ report_range_comparison: 'above' }),
  within: biomarkerRangeComparison({ report_range_comparison: 'within' }),
  unknown: biomarkerRangeComparison({ report_range_comparison: 'critical' }),
  missing: biomarkerRangeComparison({ report_range_comparison: null }),
  nonString: biomarkerRangeComparison({ report_range_comparison: 1 }),
}));
""",
        ]
    )
    result = _run_node(script)

    assert result["above"]["tone"] == "outside"
    assert result["above"]["short"] == "Above range"
    # "Within" is not a clean bill of health, so it is not coloured as one.
    assert result["within"]["tone"] == "within"
    assert result["unknown"] is None
    assert result["missing"] is None
    assert result["nonString"] is None
    assert "abnormal" not in APP_JS.lower()


# ── the one-line symptom entry ───────────────────────────────────────────────


def _symptom_creates(state) -> list[dict]:
    return [
        body
        for method, path, body in state.requests
        if method == "POST" and path == "/api/symptom-episodes"
    ]


@pytest.mark.parametrize("width,height", WIDTHS)
def test_a_symptom_can_be_recorded_in_one_line_from_today(width: int, height: int):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(playwright, width, height)
        errors: list[str] = []
        page.on("pageerror", lambda error, target=errors: target.append(str(error)))
        try:
            assert page.locator("#symptom-quick-submit").is_disabled()
            page.locator("#symptom-quick-text").fill("Felt sick after breakfast")
            page.locator("#symptom-quick-severity").select_option("moderate")
            assert page.locator("#symptom-quick-submit").is_enabled()

            page.locator("#symptom-quick-submit").click()
            page.wait_for_function(
                "() => document.getElementById('symptom-quick-text').value === ''"
            )

            creates = _symptom_creates(state)
            assert len(creates) == 1, "exactly one episode is created"
            body = creates[0]
            # The same guarded contract the full form sends: the compare-and-set
            # fields, the replay identifier and every field of the create body.
            assert set(body) == {
                "expected_profile_revision",
                "expected_workflow_revision",
                "expected_projection_token",
                "mutation_id",
                "symptom_text",
                "severity_level",
                "severity_detail",
                "reported_subject",
                "onset_date",
                "timing_text",
                "frequency_text",
                "triggers_text",
                "notes",
            }
            assert body["symptom_text"] == "Felt sick after breakfast"
            assert body["severity_level"] == "moderate"
            assert body["reported_subject"] == "unspecified"
            assert body["onset_date"] is None
            assert body["notes"] is None
            assert isinstance(body["mutation_id"], str) and body["mutation_id"]
            assert isinstance(body["expected_projection_token"], str)

            assert "Felt sick after breakfast" in page.locator("#today-symptom-list").inner_text()
            assert page.locator("#symptom-quick-severity").input_value() == ""
            assert page.evaluate("() => document.getElementById('symptom-dialog').inert") is True
            assert page.evaluate("() => document.activeElement.id") == "today-symptoms-heading"

            overflow = page.evaluate(
                """() => document.documentElement.scrollWidth
                     - document.documentElement.clientWidth"""
            )
            assert overflow == 0, f"horizontal overflow at {width}px"
            heights = page.locator(
                "#symptom-quick-entry input, #symptom-quick-entry select, "
                "#symptom-quick-entry button"
            ).evaluate_all("items => items.map(item => item.getBoundingClientRect().height)")
            assert heights
            assert all(item >= 44 for item in heights), (width, heights)
            assert errors == []
        finally:
            context.close()
            browser.close()


def test_the_quick_line_refuses_exactly_what_the_full_form_refuses():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(playwright, 1280, 900)
        try:
            # Blank, then whitespace only: the full form rejects both, so the
            # quick line must never turn either into a request.
            for typed in ("", "   "):
                page.locator("#symptom-quick-text").fill(typed)
                assert page.locator("#symptom-quick-submit").is_disabled()
                page.evaluate("() => submitQuickSymptom()")
                page.wait_for_timeout(50)
                assert _symptom_creates(state) == []
                assert (
                    "Write what she felt before recording it."
                    in page.locator("#symptom-quick-error").inner_text()
                )
                assert page.evaluate("() => symptomDialogOpen") is False

            # And a request that the record no longer authorises is refused by
            # the same precondition the dialog uses.
            page.locator("#symptom-quick-text").fill("Something real")
            page.evaluate("() => { symptomProjectionState = 'stale'; }")
            page.evaluate("() => submitQuickSymptom()")
            page.wait_for_timeout(50)
            assert _symptom_creates(state) == []
            assert (
                "Load the current symptom record again"
                in page.locator("#symptom-quick-error").inner_text()
            )
        finally:
            context.close()
            browser.close()


def test_the_quick_line_does_not_throw_away_a_detailed_entry_he_saved():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(playwright, 1280, 900)
        try:
            page.locator("#today-symptom-add").click()
            page.locator("#symptom-text").fill("Long story he was still writing")
            page.locator("#symptom-notes").fill("With notes he had not finished")
            page.locator("#symptom-details-form button:has-text('Cancel')").click()

            page.locator("#symptom-quick-text").fill("Quick one")
            page.locator("#symptom-quick-submit").click()
            page.wait_for_function(
                "() => document.getElementById('symptom-quick-text').value === ''"
            )

            body = _symptom_creates(state)[-1]
            assert body["symptom_text"] == "Quick one"
            assert body["notes"] is None, "the saved entry must not ride along"

            page.locator("#today-symptom-add").click()
            assert page.locator("#symptom-text").input_value() == (
                "Long story he was still writing"
            )
            assert page.locator("#symptom-notes").input_value() == (
                "With notes he had not finished"
            )
        finally:
            context.close()
            browser.close()


def test_losing_authorisation_clears_the_quick_line_and_the_search_box():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_symptom_page(playwright, 1280, 900)
        try:
            page.locator("#symptom-quick-text").fill("Something private about her")
            page.evaluate(
                """() => clearSymptomProjection({
                  state: 'error',
                  statusLabel: 'Patient data unavailable',
                  message: 'Symptom records could not be loaded.',
                })"""
            )
            assert page.locator("#symptom-quick-text").input_value() == ""
            assert page.locator("#symptom-quick-submit").is_disabled()
        finally:
            context.close()
            browser.close()

    with playwright_api.sync_playwright() as playwright:
        browser, context, page, _ = _open_biomarker_page(
            playwright,
            1280,
            900,
            _flagged_projection(),
        )
        try:
            page.locator("#biomarker-search").fill("cga")
            page.evaluate(
                """() => clearBiomarkerProjection({
                  state: 'error',
                  statusLabel: 'Patient data unavailable',
                  message: 'Biomarker history could not be loaded.',
                })"""
            )
            assert page.locator("#biomarker-search").input_value() == ""
            assert page.locator("#biomarker-search").is_disabled()
            assert page.locator("#biomarker-overview-list .biomarker-overview-row").count() == 0
        finally:
            context.close()
            browser.close()


def test_the_restored_surfaces_are_labelled_and_reachable():
    assert 'id="biomarker-search"' in INDEX_HTML
    assert 'for="biomarker-search"' in INDEX_HTML
    assert 'id="symptom-quick-text"' in INDEX_HTML
    assert 'for="symptom-quick-text"' in INDEX_HTML
    assert 'for="symptom-quick-severity"' in INDEX_HTML
    # The action's accessible name carries the marker name and still contains
    # the words on the button, so saying "Show history" reaches it.
    assert 'aria-labelledby="${nameId} ${actionId}"' in APP_JS
    assert ">Show history</button>" in APP_JS
    # The identifier is carried in data, never interpolated into a handler.
    assert "selectBiomarkerAnalyteFromRow(this)" in APP_JS
    assert "selectBiomarkerAnalyte('" not in APP_JS
