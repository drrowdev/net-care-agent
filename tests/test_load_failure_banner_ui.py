"""The failure banner names what actually failed.

One section failing used to put "Patient data could not be loaded" across the
top of a page where the profile, treatments, biomarkers and symptoms were all
rendered underneath and only imaging was missing. For someone anxious about the
record, a banner claiming the patient data failed is both alarming and untrue.

The banner now names the part that failed — and, just as importantly, keeps the
wider sentence when the failure really is wider: an unrecognised area, several
at once, sign-in and access failures, being offline, and any failure that
cleared the browser's whole copy of the record.

These run the real `renderAppState` under Node against a small fake DOM, the
same way the other render guards in `tests/` work.
"""

from __future__ import annotations

import json

from tests._ui_render import function_source, run_node

_BANNER_HARNESS = """
function fakeElement() {
  return {
    hidden: false,
    textContent: '',
    classList: { add() {}, remove() {}, toggle() {} },
  };
}

const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, fakeElement());
    return elements.get(id);
  },
};
const navigator = { onLine: true };
"""


def _render_banner(failures: list[dict], *, evicted: bool = False, online: bool = True) -> dict:
    """Report each failure through the real reporter, then read the banner."""
    script = "\n".join(
        [
            _BANNER_HARNESS,
            function_source("isCrossOriginDenial", "authEvictsClientPhi"),
            "const CROSS_ORIGIN_DENIAL_MESSAGE = 'blocked address';",
            "const failedLoads = new Map();",
            "let wholeRecordCleared = false;",
            "let recoveryBatchInFlight = 0;",
            "let recordReloadedSinceClear = false;",
            function_source("reportLoadSuccess", "reportLoadError"),
            function_source("reportLoadError", "shouldEvictClientPhi"),
            function_source("failedSectionNames", "renderAppState"),
            function_source("renderAppState", "appIsOffline"),
            _labels_source(),
            f"navigator.onLine = {json.dumps(online)};",
            f"wholeRecordCleared = {json.dumps(evicted)};",
            f"for (const failure of {json.dumps(failures)}) {{",
            "  const error = new Error(failure.message || 'Something went wrong.');",
            "  if (failure.status) error.status = failure.status;",
            "  if (failure.reason) error.reason = failure.reason;",
            "  reportLoadError(failure.scope, error);",
            "}",
            "renderAppState();",
            "console.log(JSON.stringify({",
            "  title: document.getElementById('app-state-title').textContent,",
            "  message: document.getElementById('app-state-message').textContent,",
            "  hidden: document.getElementById('app-state-banner').hidden,",
            "}));",
        ]
    )
    return run_node(script)


def _labels_source() -> str:
    """The real scope-to-label table, lifted from `static/app.js`."""
    from tests._ui_render import APP_JS

    start = APP_JS.index("const LOAD_FAILURE_LABELS")
    end = APP_JS.index("});", start) + len("});")
    return APP_JS[start:end]


def test_one_failed_section_names_that_section_and_nothing_wider():
    assert _render_banner([{"scope": "imaging"}])["title"] == "Imaging could not be loaded"
    assert _render_banner([{"scope": "biomarkers"}])["title"] == "Biomarkers could not be loaded"
    assert _render_banner([{"scope": "research"}])["title"] == "Research could not be loaded"
    assert (
        _render_banner([{"scope": "treatment-reconciliation"}])["title"]
        == "Treatments could not be loaded"
    )


def test_the_message_still_carries_what_the_failed_section_reported():
    rendered = _render_banner([{"scope": "imaging", "message": "Imaging is unavailable."}])
    assert rendered["hidden"] is False
    assert rendered["message"] == "Imaging is unavailable."


def test_two_failed_sections_name_both_and_three_stay_general():
    assert (
        _render_banner([{"scope": "imaging"}, {"scope": "biomarkers"}])["title"]
        == "Imaging and Biomarkers could not be loaded"
    )
    assert (
        _render_banner([{"scope": "imaging"}, {"scope": "biomarkers"}, {"scope": "research"}])[
            "title"
        ]
        == "Patient data could not be loaded"
    )


def test_two_scopes_for_one_section_name_that_section_once():
    """Loading symptoms and changing symptoms are one thing on screen."""
    rendered = _render_banner([{"scope": "symptom-episodes"}, {"scope": "symptom-mutation"}])
    assert rendered["title"] == "Symptoms could not be loaded"


def test_an_unrecognised_area_keeps_the_wider_sentence():
    """A scope nobody mapped must never be renamed into something narrower."""
    assert _render_banner([{"scope": "status"}])["title"] == "Patient data could not be loaded"
    assert (
        _render_banner([{"scope": "imaging"}, {"scope": "clinical-convergence"}])["title"]
        == "Patient data could not be loaded"
    )


def test_a_failure_that_cleared_the_whole_record_never_names_one_section():
    """A 500 on one section evicts every held record; the banner must say so."""
    rendered = _render_banner([{"scope": "imaging", "status": 500}], evicted=True)
    assert rendered["title"] == "Patient data could not be loaded"


def test_sign_in_access_address_and_offline_failures_keep_their_own_wording():
    assert _render_banner([{"scope": "biomarkers", "status": 401}])["title"] == "Sign-in required"
    assert (
        _render_banner([{"scope": "biomarkers", "status": 403}])["title"]
        == "Access to this patient record is denied"
    )
    assert (
        _render_banner([{"scope": "biomarkers", "status": 403, "reason": "cross_origin"}])["title"]
        == "Request blocked by the app’s address check"
    )
    assert _render_banner([{"scope": "imaging"}], online=False)["title"] == "Connection lost"


def test_the_banner_forgets_the_wider_failure_only_when_the_record_loads_again():
    """A routine success elsewhere is not the cleared record coming back."""
    script = "\n".join(
        [
            _BANNER_HARNESS,
            function_source("isCrossOriginDenial", "authEvictsClientPhi"),
            "const CROSS_ORIGIN_DENIAL_MESSAGE = 'blocked address';",
            "const failedLoads = new Map();",
            "let wholeRecordCleared = true;",
            "let recoveryBatchInFlight = 0;",
            "let recordReloadedSinceClear = false;",
            function_source("reportLoadSuccess", "reportLoadError"),
            function_source("reportLoadError", "shouldEvictClientPhi"),
            function_source("failedSectionNames", "renderAppState"),
            function_source("renderAppState", "appIsOffline"),
            _labels_source(),
            "const title = () => document.getElementById('app-state-title').textContent;",
            "const hidden = () => document.getElementById('app-state-banner').hidden;",
            "reportLoadError('imaging', new Error('Imaging is unavailable.'));",
            "const duringEviction = title();",
            "reportLoadSuccess('biomarkers');",
            "const afterOtherSuccess = title();",
            "reportLoadSuccess('imaging');",
            "const afterFailingSectionRecovers = hidden();",
            "reportLoadError('imaging', new Error('Imaging is unavailable.'));",
            "const beforeRecordReloads = title();",
            "reportLoadSuccess('imaging');",
            "reportLoadSuccess('status');",
            "reportLoadError('imaging', new Error('Imaging is unavailable.'));",
            "const afterRecordReloads = title();",
            "console.log(JSON.stringify({",
            "  duringEviction, afterOtherSuccess, afterFailingSectionRecovers,",
            "  beforeRecordReloads, afterRecordReloads,",
            "}));",
        ]
    )
    rendered = run_node(script)
    wider = "Patient data could not be loaded"
    # While the record is cleared, one section's name would understate it.
    assert rendered["duringEviction"] == wider
    assert rendered["afterOtherSuccess"] == wider
    assert rendered["afterFailingSectionRecovers"] is True
    assert rendered["beforeRecordReloads"] == wider
    # Once the patient record itself has loaded again, a fresh single failure
    # names itself.
    assert rendered["afterRecordReloads"] == "Imaging could not be loaded"


def test_a_batch_that_left_one_section_failing_recovers_when_that_section_does():
    """The last outstanding section is often reloaded from its own Retry.

    A retry can bring the record back and still leave one section failing. That
    section then recovers on its own, with no further record-wide load, and the
    wider wording has to be released even so.
    """
    script = "\n".join(
        [
            _BANNER_HARNESS,
            function_source("isCrossOriginDenial", "authEvictsClientPhi"),
            "const CROSS_ORIGIN_DENIAL_MESSAGE = 'blocked address';",
            "const failedLoads = new Map();",
            "let wholeRecordCleared = true;",
            "let recoveryBatchInFlight = 1;",
            "let recordReloadedSinceClear = false;",
            function_source("reportLoadSuccess", "reportLoadError"),
            function_source("reportLoadError", "shouldEvictClientPhi"),
            function_source("failedSectionNames", "renderAppState"),
            function_source("renderAppState", "appIsOffline"),
            _labels_source(),
            "const title = () => document.getElementById('app-state-title').textContent;",
            # The retry batch settles with imaging still failing.
            "reportLoadError('imaging', new Error('Imaging is unavailable.'));",
            "recoveryBatchInFlight = 0;",
            "recordReloadedSinceClear = true;",
            "const afterBatch = title();",
            # Imaging is then reloaded from its own Retry — no `status` involved.
            "reportLoadSuccess('imaging');",
            "reportLoadError('imaging', new Error('Imaging is unavailable.'));",
            "console.log(JSON.stringify({ afterBatch, afterSectionRetry: title() }));",
        ]
    )
    rendered = run_node(script)
    assert rendered["afterBatch"] == "Patient data could not be loaded"
    assert rendered["afterSectionRetry"] == "Imaging could not be loaded"


def test_the_static_default_matches_the_wider_sentence_the_script_falls_back_to():
    """index.html holds the pre-script default; the two layers must agree."""
    from pathlib import Path

    html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<strong id="app-state-title">Patient data could not be loaded</strong>' in html


def _open_page(playwright, width: int = 1280, height: int = 900):
    """Load the real page with every API stubbed, as the other UI tests do."""
    import re
    from pathlib import Path

    html = re.sub(
        r"<script[^>]+src=[^>]+></script>",
        "",
        Path("static/index.html").read_text(encoding="utf-8"),
    )
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.route(
        "**/api/**",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    page.set_content(html)
    page.add_style_tag(content=Path("static/styles.css").read_text(encoding="utf-8"))
    page.add_script_tag(content=Path("static/app.js").read_text(encoding="utf-8"))
    page.evaluate("() => { clearTimeout(pollingInterval); pollingInterval = null; }")
    return browser, context, page


def test_live_a_section_error_that_clears_the_record_widens_the_banner_it_drew():
    """The real order is report-then-evict, so the banner must be redrawn.

    A server error on one section names that section first and clears every
    browser-held record a moment later. The harness above cannot see that
    ordering, so this drives the two real functions in the order the app does.
    The page's own loads run against stubs, so each step clears the map first
    and reads the banner in the same synchronous turn.
    """
    import pytest

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        from pathlib import Path

        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open_page(playwright)
        try:
            titles = page.evaluate(
                """() => {
                  const title = () => document.getElementById('app-state-title').textContent;
                  const failure = () => {
                    const error = new Error('Biomarker data could not be loaded safely.');
                    error.status = 500;
                    return error;
                  };
                  failedLoads.clear();
                  wholeRecordCleared = false;
                  reportLoadError('biomarkers', failure());
                  const named = title();
                  evictClientPhi(failure());
                  return { named, afterEviction: title() };
                }"""
            )
            assert titles == {
                "named": "Biomarkers could not be loaded",
                "afterEviction": "Patient data could not be loaded",
            }
        finally:
            context.close()
            browser.close()


def test_live_an_eviction_with_no_failure_recorded_still_widens_the_next_banner():
    """Some loaders evict and then go stale without reporting their own failure.

    `loadPatientEvidence` is one: it clears the record, and the epoch check that
    follows stops it reporting. Nothing must treat that quiet eviction as a
    clean state, or the next single-section failure would name one section while
    the whole record is still missing.
    """
    import pytest

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        from pathlib import Path

        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open_page(playwright)
        try:
            result = page.evaluate(
                """() => {
                  const title = () => document.getElementById('app-state-title').textContent;
                  const error = new Error('Patient evidence could not be confirmed.');
                  error.status = 500;
                  failedLoads.clear();
                  wholeRecordCleared = false;
                  evictClientPhi(error);
                  const quiet = document.getElementById('app-state-banner').hidden;
                  failedLoads.clear();
                  reportLoadError('imaging', new Error('Imaging is unavailable.'));
                  const afterFailure = title();
                  // A routine success elsewhere is not the record coming back.
                  reportLoadSuccess('tasks');
                  return { quiet, afterFailure, afterOtherSuccess: title() };
                }"""
            )
            assert result == {
                "quiet": True,
                "afterFailure": "Patient data could not be loaded",
                "afterOtherSuccess": "Patient data could not be loaded",
            }
        finally:
            context.close()
            browser.close()


def test_live_a_retry_holds_the_wider_wording_until_the_whole_batch_settles():
    """Status can finish first while every other reload is still running."""
    import pytest

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        from pathlib import Path

        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open_page(playwright)
        try:
            result = page.evaluate(
                """() => {
                  const title = () => document.getElementById('app-state-title').textContent;
                  const error = new Error('Patient evidence could not be confirmed.');
                  error.status = 500;
                  failedLoads.clear();
                  wholeRecordCleared = false;
                  evictClientPhi(error);
                  // A retry that has not settled: the record is still coming back.
                  recoveryBatchInFlight = 1;
                  failedLoads.clear();
                  reportLoadSuccess('status');
                  reportLoadError('imaging', new Error('Imaging is unavailable.'));
                  const duringRetry = title();
                  recoveryBatchInFlight = 0;
                  reportLoadSuccess('imaging');
                  reportLoadSuccess('status');
                  failedLoads.clear();
                  reportLoadError('imaging', new Error('Imaging is unavailable.'));
                  return { duringRetry, afterRetry: title() };
                }"""
            )
            assert result == {
                "duringRetry": "Patient data could not be loaded",
                "afterRetry": "Imaging could not be loaded",
            }
        finally:
            context.close()
            browser.close()


def test_live_a_retry_that_clears_the_record_again_is_not_a_recovery():
    """One loader can wipe everything mid-retry without recording a failure.

    The requests still in flight then go stale and settle quietly, so a batch
    that finished is not on its own evidence that the record came back. This
    runs the real `retryInitialLoad` against a server error on the evidence
    load, which is one of the loaders that clears the record silently.
    """
    import pytest

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        from pathlib import Path

        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open_page(playwright)
        try:
            page.route(
                "**/api/patient/evidence",
                lambda route: route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"error": "not exposed"}',
                ),
            )
            state = page.evaluate(
                """async () => {
                  failedLoads.clear();
                  wholeRecordCleared = true;
                  recordReloadedSinceClear = false;
                  await retryInitialLoad();
                  return {
                    wholeRecordCleared,
                    recordReloadedSinceClear,
                    recoveryBatchInFlight,
                  };
                }"""
            )
            assert state == {
                "wholeRecordCleared": True,
                "recordReloadedSinceClear": False,
                "recoveryBatchInFlight": 0,
            }
        finally:
            context.close()
            browser.close()


def test_live_every_digest_control_is_held_together_while_one_is_submitting():
    """Three places can start a digest; a second one must not slip through."""
    import pytest

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        from pathlib import Path

        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page = _open_page(playwright)
        try:
            page.route("**/api/digest", lambda route: None)  # never resolves
            page.evaluate("() => { runDigest(); }")
            page.wait_for_function("() => digestSubmissionsActive === 1")
            assert page.evaluate(
                """() => [...document.querySelectorAll('.digest-trigger')]
                  .every(button => button.disabled)"""
            )
            # A control drawn while the request is in flight is born disabled.
            drawn = page.evaluate(
                """() => {
                  const host = document.createElement('div');
                  host.innerHTML = artifactStateMarkup({
                    id: 'job-1',
                    type: 'digest',
                    status: 'done',
                    artifact: { kind: 'report', state: 'expired', freshness: 'unknown' },
                  });
                  document.body.append(host);
                  const button = host.querySelector('.digest-trigger');
                  return { found: Boolean(button), disabled: button?.disabled };
                }"""
            )
            assert drawn == {"found": True, "disabled": True}
        finally:
            context.close()
            browser.close()
