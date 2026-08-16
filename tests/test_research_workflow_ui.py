from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")
GUIDANCE = (
    "NET/Care records research you choose to follow but does not determine relevance, "
    "eligibility, enrollment, or treatment suitability. Confirm clinical questions with "
    "the treating team and trial details with the study site."
)
GENERATED_LABEL = (
    "Machine-generated compatibility context · not relevance, eligibility, enrollment, "
    "suitability, or recommendation"
)


def _research_source() -> str:
    start = APP_JS.index("const RESEARCH_SAFETY_GUIDANCE")
    end = APP_JS.index("function setResearchStatus", start)
    return APP_JS[start:end]


def _item(
    record_id: str = "research_trial_abcdefghijklmnop",
    token: str = "item-token",
    *,
    latest: bool = True,
    consideration_id: str | None = None,
) -> dict:
    return {
        "id": record_id,
        "token": token,
        "item_type": "trial",
        "source_identity": {
            "external_id": "NCT12345678",
            "source_key": "ctgov:NCT12345678",
            "authority": "validated",
        },
        "external_facts": {
            "nct_id": "NCT12345678",
            "title": "Exact registry title",
            "status": "RECRUITING",
            "brief_summary": "",
        },
        "generated_context": {"eligibility_notes": "Machine-generated context"},
        "discovery_provenance": {"date_added": "2026-08-01"},
        "external_url": "https://clinicaltrials.gov/study/NCT12345678",
        "latest_batch_member": latest,
        "shortlist": {
            "eligible": consideration_id is None,
            "reason": None if consideration_id is None else "already_shortlisted",
        },
        "consideration_id": consideration_id,
    }


def _consideration(item: dict) -> dict:
    consideration_id = "research_consideration_exact"
    return {
        "id": consideration_id,
        "token": "consideration-token",
        "item_type": "trial",
        "research_record_id": item["id"],
        "source_key": "ctgov:NCT12345678",
        "status": "open",
        "snapshot": {
            "item_type": "trial",
            "research_record_id": item["id"],
            "source_key": "ctgov:NCT12345678",
            "external_facts": copy.deepcopy(item["external_facts"]),
            "generated_context": copy.deepcopy(item["generated_context"]),
            "discovery_provenance": copy.deepcopy(item["discovery_provenance"]),
        },
        "current_state": {
            "occurrence": "present",
            "external_facts": "unchanged",
            "generated_context": "unchanged",
            "discovery_provenance": "unchanged",
        },
        "events": [
            {
                "id": "research_event_exact",
                "token": "event-token",
                "event_type": "caregiver_note",
                "note": "Exact caregiver note",
                "who": None,
                "context": None,
                "occurred_on": "2026-08",
                "occurred_on_precision": "month",
                "provenance": {
                    "capture_method": "caregiver_entered",
                    "source_verification": "unverified",
                    "label": "Caregiver-entered · unverified",
                },
                "recorded_at": "2026-08-01T10:00:00",
            }
        ],
        "history": [
            {
                "operation": "created",
                "at": "2026-08-01T09:00:00",
                "changes": {"status": {"before": None, "after": "open"}},
            }
        ],
        "follow_up": None,
        "eligibility": {
            "close": {"eligible": True, "reason": None},
            "resume": {"eligible": False, "reason": "already_open"},
            "allowed_event_types": [
                "caregiver_note",
                "next_step_recorded",
                "treating_team_communication",
                "trial_site_communication",
            ],
            "follow_up_variants": ["link_existing", "create_and_link"],
        },
        "created_at": "2026-08-01T09:00:00",
        "updated_at": "2026-08-01T10:00:00",
        "closed_at": None,
    }


def _projection(*, with_consideration: bool = True) -> dict:
    item = _item(consideration_id="research_consideration_exact" if with_consideration else None)
    consideration = _consideration(item)
    return {
        "profile_revision": 7,
        "workflow_revision": 3,
        "projection_token": "research-projection-token",
        "item_count": 1,
        "consideration_count": 1 if with_consideration else 0,
        "items": [item],
        "considerations": [consideration] if with_consideration else [],
        "eligible_actions": [
            {
                "id": "action-exact",
                "token": "action-token",
                "text": "Ask the treating team an exact caregiver question",
                "status": "open",
                "owner": None,
                "due_date": None,
            }
        ],
        "attribution_labels": {
            "caregiver": "Caregiver-entered · unverified",
            "clinician": "Caregiver-entered · attributed to clinician · unverified",
            "trial_site": "Caregiver-entered · attributed to trial site · unverified",
        },
        "authority_labels": {
            "external_facts": "External registry or bibliographic facts",
            "generated_context": GENERATED_LABEL,
            "discovery_provenance": "Research discovery provenance",
            "caregiver_workflow": "Caregiver-maintained shortlist and disposition workflow",
        },
        "safety_guidance": {"kind": "fixed_non_clinical", "text": GUIDANCE},
    }


def _run_validator(payloads: list[dict]) -> list[object]:
    runner = """
const payloads = __PAYLOAD__;
const results = payloads.map(payload => {
  try {
    validateResearchWorkspace(payload);
    return true;
  } catch (error) {
    return error.message;
  }
});
console.log(JSON.stringify(results));
""".replace("__PAYLOAD__", json.dumps(payloads))
    script = "\n".join(
        [
            _research_source(),
            runner,
        ]
    )
    completed = subprocess.run(
        ["node", "-e", "eval(require('fs').readFileSync(0,'utf8'))"],
        input=script,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_actual_validator_accepts_exact_projection_and_duplicate_occurrences():
    projection = _projection(with_consideration=False)
    duplicate = copy.deepcopy(projection["items"][0])
    duplicate["id"] = "research_trial_qrstuvwxyzabcdef"
    # Semantic tokens can legitimately match for duplicate exact rows.
    projection["items"].append(duplicate)
    projection["item_count"] = 2

    assert _run_validator([projection]) == [True]


def test_actual_validator_rejects_unsafe_links_copy_and_nested_rows_atomically():
    valid = _projection()
    query = copy.deepcopy(valid)
    query["items"][0]["external_url"] += "?utm=unsafe"
    encoded = copy.deepcopy(valid)
    encoded["items"][0]["external_url"] = "https://clinicaltrials.gov/study/%4eCT12345678"
    wrong_copy = copy.deepcopy(valid)
    wrong_copy["safety_guidance"]["text"] += " "
    wrong_current_state = copy.deepcopy(valid)
    wrong_current_state["considerations"][0]["current_state"]["generated_context"] = "changed"
    extra_nested_field = copy.deepcopy(valid)
    extra_nested_field["items"][0]["generated_context"]["rank"] = 1

    results = _run_validator(
        [valid, query, encoded, wrong_copy, wrong_current_state, extra_nested_field]
    )
    assert results[0] is True
    assert all(result is not True for result in results[1:])


def test_research_has_one_shared_projection_and_no_legacy_display_authority():
    assert APP_JS.count("fetch('/api/patient/research-workspace'") == 1
    assert "/api/trials" not in APP_JS
    assert "/api/papers" not in APP_JS
    assert "latestResearchUpdate" not in APP_JS
    assert "openModal(" not in APP_JS
    assert "removeItem(" not in APP_JS
    assert "best_trial" not in APP_JS
    assert "researchProjection.items.filter(item => item.latest_batch_member)" in APP_JS
    assert "latest.slice(0, 3)" in APP_JS
    assert "open.slice(0, 3)" in APP_JS
    assert "more in Research" in APP_JS
    patient_branch = APP_JS[
        APP_JS.index("} else if (name === 'patient')") : APP_JS.index(
            "} else if (name === 'activity')"
        )
    ]
    assert "loadResearchWorkspace" not in patient_branch


def test_research_authorities_remain_visible_without_routine_fixed_copy():
    assert GUIDANCE not in INDEX_HTML
    assert GENERATED_LABEL in APP_JS
    for section in (
        "Registry or publication details",
        "How this research was found",
        "Immutable saved snapshot",
        "Current tracked entry",
        "Your recorded events",
        "Consideration history",
    ):
        assert section in APP_JS or section in INDEX_HTML
    assert "Machine-generated context" not in INDEX_HTML
    assert "eligibility_notes" not in INDEX_HTML


def test_mutations_use_exact_authority_and_atomic_follow_up_only():
    source = APP_JS[
        APP_JS.index("function researchBaseMutationBody") : APP_JS.index("// ── Task log")
    ]
    for field in (
        "mutation_id",
        "expected_profile_revision",
        "expected_workflow_revision",
        "expected_projection_token",
        "expected_item_token",
        "expected_consideration_token",
        "expected_action_token",
    ):
        assert field in source
    assert "pendingResearchSubmission" in source
    assert "pendingResearchCompletion" in source
    assert "Retry submission" in INDEX_HTML
    assert "Retry refresh" in INDEX_HTML
    assert (
        "`/api/research-considerations/${encodeURIComponent(consideration.id)}/follow-up`" in source
    )
    assert "fetch('/api/follow-ups'" not in source
    assert "POST /api/follow-ups" not in source


def test_event_modes_scrub_fields_and_never_parse_or_default_dates():
    source = APP_JS[
        APP_JS.index("function configureResearchEventForm") : APP_JS.index(
            "function configureResearchLifecycleForm"
        )
    ]
    for field in (
        "research-event-note",
        "research-event-who",
        "research-event-context",
        "research-event-date",
    ):
        assert field in source
    assert "clearResearchSubmissionRetryOnly()" in source
    assert "new Date(" not in _research_source()
    # The placeholder shows the dates the way he reads them in the record, and
    # those are now the shapes the field accepts.
    assert 'placeholder="14.8.2026, 8/2026 or 2026"' in INDEX_HTML
    assert "Attribution preview" in APP_JS


def test_research_accessibility_and_phone_layout_contract():
    assert 'role="tablist" aria-label="Research workspace sections"' in INDEX_HTML
    assert 'class="research-history-list"' in APP_JS
    assert "JSON.stringify(entry.changes" not in APP_JS
    assert "trapDialogFocus" in APP_JS
    assert ".research-dialog {" in CSS
    assert "height: 100dvh" in CSS
    assert ".research-card-actions .button { min-height: 44px; }" in CSS
    assert "overflow-x: hidden" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def _open_research_page(playwright, width: int, height: int):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    projection = _projection()
    projection["items"] = [
        projection["items"][0],
        _item("research_trial_qrstuvwxyzabcdef", "duplicate-token"),
        _item("research_trial_ghijklmnopqrstuv", "third-token"),
        _item("research_trial_wxyzabcdefghijkl", "fourth-token"),
    ]
    projection["items"][0]["consideration_id"] = "research_consideration_exact"
    projection["items"][0]["shortlist"] = {
        "eligible": False,
        "reason": "already_shortlisted",
    }
    projection["item_count"] = len(projection["items"])
    requests: list[dict] = []

    def fulfill(route):
        path = urlsplit(route.request.url).path
        body = json.loads(route.request.post_data) if route.request.post_data else None
        requests.append(
            {
                "method": route.request.method,
                "path": path,
                "body": body,
                "raw": route.request.post_data,
            }
        )
        if path == "/api/patient/research-workspace":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(projection),
            )
            return
        if path.startswith("/api/research-considerations/"):
            consideration = projection["considerations"][0]
            projection["workflow_revision"] += 1
            consideration["token"] = f"consideration-token-{projection['workflow_revision']}"
            consideration["updated_at"] = f"2026-08-{projection['workflow_revision']:02d}T10:00:00"
            if path.endswith("/events"):
                event = {
                    "id": f"research_event_{projection['workflow_revision']}",
                    "token": f"event-token-{projection['workflow_revision']}",
                    "event_type": body["event_type"],
                    "note": body["note"],
                    "who": body["who"],
                    "context": body["context"],
                    "occurred_on": body["occurred_on"],
                    "occurred_on_precision": (
                        "month" if body["occurred_on"] == "2026-09" else "unknown"
                    ),
                    "provenance": {
                        "capture_method": "caregiver_entered",
                        "source_verification": "unverified",
                        "label": "Caregiver-entered · unverified",
                    },
                    "recorded_at": "2026-09-01T10:00:00",
                }
                consideration["events"].append(event)
                consideration["history"].append(
                    {
                        "operation": "event_recorded",
                        "at": "2026-09-01T10:00:00",
                        "changes": {
                            "event_id": event["id"],
                            "event_type": event["event_type"],
                        },
                    }
                )
                status = 201
            elif path.endswith("/close"):
                consideration["status"] = "closed"
                consideration["closed_at"] = "2026-09-02T10:00:00"
                consideration["eligibility"]["close"] = {
                    "eligible": False,
                    "reason": "closed",
                }
                consideration["eligibility"]["resume"] = {
                    "eligible": True,
                    "reason": None,
                }
                consideration["history"].append(
                    {
                        "operation": "closed",
                        "at": "2026-09-02T10:00:00",
                        "changes": {"status": {"before": "open", "after": "closed"}},
                    }
                )
                status = 200
            elif path.endswith("/resume"):
                consideration["status"] = "open"
                consideration["closed_at"] = None
                consideration["eligibility"]["close"] = {
                    "eligible": True,
                    "reason": None,
                }
                consideration["eligibility"]["resume"] = {
                    "eligible": False,
                    "reason": "already_open",
                }
                consideration["history"].append(
                    {
                        "operation": "resumed",
                        "at": "2026-09-03T10:00:00",
                        "changes": {"status": {"before": "closed", "after": "open"}},
                    }
                )
                status = 200
            elif path.endswith("/follow-up"):
                consideration["follow_up"] = {
                    "id": "research-action-created",
                    "token": "research-action-token",
                    "text": body["follow_up"]["text"],
                    "status": "open",
                    "owner": body["follow_up"]["owner"],
                    "due_date": body["follow_up"]["due_date"],
                }
                consideration["eligibility"]["follow_up_variants"] = ["unlink"]
                consideration["history"].append(
                    {
                        "operation": "follow_up_changed",
                        "at": "2026-09-04T10:00:00",
                        "changes": {
                            "caregiver_action_id": {
                                "before": None,
                                "after": "research-action-created",
                            }
                        },
                    }
                )
                status = 200
            else:
                route.fulfill(status=404, content_type="application/json", body="{}")
                return
            projection["projection_token"] = (
                f"research-projection-{projection['workflow_revision']}"
            )
            route.fulfill(
                status=status,
                content_type="application/json",
                body=json.dumps(
                    {
                        "consideration": consideration,
                        "profile_revision": projection["profile_revision"],
                        "workflow_revision": projection["workflow_revision"],
                    }
                ),
            )
            return
        route.fulfill(status=200, content_type="application/json", body="{}")

    page.route("**/api/**", fulfill)
    page.set_content(html)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content=APP_JS)
    page.evaluate("() => { clearTimeout(pollingInterval); pollingInterval = null; }")
    try:
        page.wait_for_function("() => researchProjectionState === 'current'", timeout=5000)
    except Exception as error:
        state = page.evaluate(
            "() => ({ state: researchProjectionState, status: "
            "document.getElementById('research-status')?.textContent })"
        )
        raise AssertionError(
            {"state": state, "errors": page_errors, "requests": requests}
        ) from error
    return browser, context, page, requests


@pytest.mark.parametrize("width,height", [(1280, 900), (360, 800)])
def test_live_shared_research_projection_totals_order_and_accessibility(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, requests = _open_research_page(playwright, width, height)
        try:
            assert page.locator("#today-latest-research-list article").count() == 3
            totals = page.locator("#today-latest-research-totals").inner_text()
            assert "4 tracked entries in the latest batch" in totals
            assert "Showing 3; 1 more in Research" in totals
            assert GUIDANCE not in page.locator("#research-today-card").inner_text()

            page.locator("#nav-research").click()
            assert page.locator("#research-occurrence-list article").count() == 4
            titles = page.locator(
                "#research-occurrence-list .research-card-header h3"
            ).all_inner_texts()
            assert titles == ["Exact registry title"] * 4
            assert page.locator("#research-occurrence-list .research-latest-badge").count() == 4
            workspace_text = page.locator("#research-workspace").inner_text()
            assert "NET/Care-generated context - not a clinical conclusion" in workspace_text
            assert GENERATED_LABEL not in workspace_text
            assert GUIDANCE not in page.locator("#research-workspace").inner_text()
            assert (
                sum(request["path"] == "/api/patient/research-workspace" for request in requests)
                == 1
            )

            page.locator("#research-tab-current").focus()
            page.evaluate("() => loadResearchWorkspace({ force: true })")
            assert page.evaluate("() => document.activeElement.id") == ("research-tab-current")
            page.keyboard.press("End")
            assert page.evaluate("() => document.activeElement.id") == "research-tab-considerations"
            page.locator("#research-tab-considerations").click()
            assert page.locator(".research-history-list").count() >= 1
            record_event = page.get_by_role("button", name="Record event")
            record_event.focus()
            assert page.evaluate("() => document.activeElement.textContent") == "Record event"
            overflow = page.evaluate(
                """() => document.documentElement.scrollWidth
                  - document.documentElement.clientWidth"""
            )
            assert overflow == 0
            if width == 360:
                heights = page.locator(
                    "#research-workspace button, #research-workspace summary"
                ).evaluate_all(
                    "items => items.filter(item => item.offsetParent !== null)"
                    ".map(item => item.getBoundingClientRect().height)"
                )
                assert heights
                assert min(heights) >= 44
        finally:
            context.close()
            browser.close()


def test_live_events_lifecycle_and_atomic_follow_up_use_full_reloads():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, requests = _open_research_page(playwright, 1280, 900)
        try:
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            card = page.locator(".research-consideration-card")

            card.get_by_role("button", name="Record event").click()
            assert page.locator("#research-event-note").input_value() == ""
            assert page.locator("#research-event-date").input_value() == ""
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("Must be cleared")
            page.locator("#research-event-who").fill("Must be cleared")
            page.locator("#research-event-context").fill("Must be cleared")
            page.locator("#research-event-date").fill("2026")
            page.locator("#research-event-type").select_option("treating_team_communication")
            for field in (
                "#research-event-note",
                "#research-event-who",
                "#research-event-context",
                "#research-event-date",
            ):
                assert page.locator(field).input_value() == ""
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("Exact caregiver-entered note")
            page.locator("#research-event-date").fill("2026-09")
            page.locator("#research-event-submit").click()
            page.wait_for_function("() => researchProjection.considerations[0].events.length === 2")
            assert "Exact caregiver-entered note" in card.inner_text()
            event_request = next(
                request for request in requests if request["path"].endswith("/events")
            )
            assert event_request["body"]["occurred_on"] == "2026-09"
            assert event_request["body"]["note"] == "Exact caregiver-entered note"

            card.get_by_role("button", name="Close consideration").click()
            assert (
                "does not mean this research is irrelevant"
                in page.locator("#research-lifecycle-copy").inner_text()
            )
            page.locator("#research-lifecycle-submit").click()
            page.wait_for_function("() => researchProjection.considerations[0].status === 'closed'")
            assert card.get_by_role("button", name="Resume consideration").count() == 1
            card.get_by_role("button", name="Resume consideration").click()
            page.locator("#research-lifecycle-submit").click()
            page.wait_for_function("() => researchProjection.considerations[0].status === 'open'")

            card.get_by_role("button", name="Link or create follow-up").click()
            page.get_by_label("Create one manual action and link atomically").check()
            assert page.locator("#research-follow-up-text").input_value() == ""
            page.locator("#research-follow-up-text").fill(
                "Ask the treating team about the exact registry questions"
            )
            page.locator("#research-follow-up-owner").fill("Caregiver")
            page.locator("#research-follow-up-submit").click()
            page.wait_for_function("() => researchProjection.considerations[0].follow_up !== null")
            assert "Ask the treating team" in card.inner_text()

            mutation_requests = [
                request
                for request in requests
                if request["path"].startswith("/api/research-considerations/")
            ]
            assert [request["method"] for request in mutation_requests] == [
                "POST",
                "POST",
                "POST",
                "PATCH",
            ]
            assert not any(
                request["path"] == "/api/follow-ups" and request["method"] != "GET"
                for request in requests
            )
            for request in mutation_requests:
                assert request["body"]["mutation_id"]
                assert request["body"]["expected_profile_revision"] == 7
                assert isinstance(request["body"]["expected_workflow_revision"], int)
                assert request["body"]["expected_projection_token"]
                assert request["body"]["expected_consideration_token"]
            research_gets = [
                request
                for request in requests
                if request["path"] == "/api/patient/research-workspace"
            ]
            assert len(research_gets) == 5
        finally:
            context.close()
            browser.close()


def test_live_conflict_requires_reselection_and_restores_only_caregiver_draft():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _requests = _open_research_page(playwright, 1280, 900)
        try:
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            page.locator(".research-consideration-card").get_by_role(
                "button", name="Record event"
            ).click()
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("Retain this caregiver note")
            page.locator("#research-event-who").fill("Caregiver")
            page.locator("#research-event-context").fill("Question list")
            page.locator("#research-event-date").fill("2026-10")
            page.route(
                "**/api/research-considerations/*/events",
                lambda route: route.fulfill(
                    status=409,
                    content_type="application/json",
                    body=json.dumps({"error": "conflict"}),
                ),
                times=1,
            )
            page.locator("#research-event-submit").click()
            page.wait_for_function("() => !researchDialogOpen")
            assert page.evaluate("() => pendingResearchSubmission") is None
            assert page.evaluate("() => Object.keys(researchDraft).sort()") == [
                "context",
                "event_type",
                "kind",
                "note",
                "occurred_on",
                "who",
            ]

            page.locator(".research-consideration-card").get_by_role(
                "button", name="Record event"
            ).click()
            assert page.locator("#research-event-type").input_value() == "caregiver_note"
            assert page.locator("#research-event-note").input_value() == (
                "Retain this caregiver note"
            )
            assert page.locator("#research-event-who").input_value() == "Caregiver"
            assert page.locator("#research-event-context").input_value() == ("Question list")
            assert page.locator("#research-event-date").input_value() == "2026-10"
            assert (
                "Review it before submitting"
                in page.locator("#research-dialog-status").inner_text()
            )
        finally:
            context.close()
            browser.close()


def test_live_submission_retry_reuses_bytes_and_refresh_retry_never_resubmits():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")

        browser, context, page, _requests = _open_research_page(playwright, 1280, 900)
        attempts: list[str] = []

        def fail_once_then_continue(route):
            attempts.append(route.request.post_data)
            if len(attempts) == 1:
                route.abort("failed")
            else:
                route.fallback()

        try:
            page.route(
                "**/api/research-considerations/*/events",
                fail_once_then_continue,
            )
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            page.locator(".research-consideration-card").get_by_role(
                "button", name="Record event"
            ).click()
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("Retry these exact bytes")
            page.locator("#research-event-submit").click()
            page.wait_for_function("() => pendingResearchSubmission !== null")
            first_body = page.evaluate("() => pendingResearchSubmission.bodyText")
            page.locator("#research-retry-submission").click()
            page.wait_for_function("() => researchProjection.considerations[0].events.length === 2")
            assert attempts == [first_body, first_body]
            assert page.evaluate("() => pendingResearchSubmission") is None
        finally:
            context.close()
            browser.close()

        browser, context, page, requests = _open_research_page(playwright, 1280, 900)
        accepted = _projection()["considerations"][0]
        accepted["token"] = "consideration-token-4"
        accepted["updated_at"] = "2026-09-05T10:00:00"
        accepted["status"] = "closed"
        accepted["closed_at"] = "2026-09-05T10:00:00"
        accepted["eligibility"]["close"] = {"eligible": False, "reason": "closed"}
        accepted["eligibility"]["resume"] = {"eligible": True, "reason": None}
        accepted["history"].append(
            {
                "operation": "closed",
                "at": "2026-09-05T10:00:00",
                "changes": {
                    "status": {"before": "open", "after": "closed"},
                },
            }
        )
        mutation_count = 0

        def accept_without_replacement(route):
            nonlocal mutation_count
            mutation_count += 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "consideration": accepted,
                        "profile_revision": 7,
                        "workflow_revision": 4,
                    }
                ),
            )

        try:
            page.route(
                "**/api/research-considerations/*/close",
                accept_without_replacement,
                times=1,
            )
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            page.locator(".research-consideration-card").get_by_role(
                "button", name="Close consideration"
            ).click()
            page.locator("#research-lifecycle-submit").click()
            page.wait_for_function(
                "() => pendingResearchCompletion !== null "
                "&& !document.getElementById('research-retry-verification').hidden"
            )
            assert page.evaluate("() => pendingResearchSubmission") is None
            get_count = sum(
                request["path"] == "/api/patient/research-workspace" for request in requests
            )
            page.locator("#research-retry-verification").click()
            page.wait_for_timeout(100)
            assert (
                sum(request["path"] == "/api/patient/research-workspace" for request in requests)
                > get_count
            )
            assert mutation_count == 1
        finally:
            context.close()
            browser.close()


def test_live_mutation_validation_retains_draft_but_hard_get_clears_research_phi():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _requests = _open_research_page(playwright, 1280, 900)
        try:
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            page.locator(".research-consideration-card").get_by_role(
                "button", name="Record event"
            ).click()
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("PHI draft to retain once")
            page.route(
                "**/api/research-considerations/*/events",
                lambda route: route.fulfill(
                    status=422,
                    content_type="application/json",
                    body=json.dumps({"error": "raw private validation body"}),
                ),
                times=1,
            )
            page.locator("#research-event-submit").click()
            page.wait_for_function(
                "() => document.getElementById('research-dialog-status')"
                ".textContent.includes('not accepted')"
            )
            assert page.locator("#research-event-note").input_value() == (
                "PHI draft to retain once"
            )
            assert page.evaluate("() => researchProjectionState") == "current"
            assert (
                "raw private validation body" not in page.locator("#research-dialog").inner_text()
            )

            page.route(
                "**/api/patient/research-workspace",
                lambda route: route.fulfill(
                    status=422,
                    content_type="application/json",
                    body=json.dumps({"error": "raw private projection body"}),
                ),
                times=1,
            )
            page.evaluate("() => loadResearchWorkspace({ force: true })")
            page.wait_for_function("() => researchProjection === null")
            assert page.locator("#research-event-note").input_value() == ""
            assert page.locator("#research-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert page.locator("#research-occurrence-list article").count() == 0
            assert page.locator("#research-consideration-list article").count() == 0
            assert GUIDANCE not in page.locator("#research-workspace").inner_text()
            assert (
                "raw private projection body"
                not in page.locator("#research-workspace").inner_text()
            )
            assert page.evaluate(
                "() => ({draft: researchDraft, submission: pendingResearchSubmission,"
                " completion: pendingResearchCompletion})"
            ) == {"draft": None, "submission": None, "completion": None}
        finally:
            context.close()
            browser.close()


def test_live_global_phi_eviction_scrubs_hidden_and_live_research_content():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _requests = _open_research_page(playwright, 1280, 900)
        try:
            page.locator("#nav-research").click()
            page.locator("#research-tab-considerations").click()
            page.locator(".research-consideration-card").get_by_role(
                "button", name="Record event"
            ).click()
            page.locator("#research-event-type").select_option("caregiver_note")
            page.locator("#research-event-note").fill("Hidden PHI draft")
            page.locator("#research-event-note").focus()
            page.evaluate(
                """() => {
                  setResearchStatus('Live PHI status text', 'current');
                  setResearchDialogStatus('Dialog PHI status text', 'error');
                  evictClientPhi();
                }"""
            )
            page.wait_for_function("() => document.activeElement.id !== 'research-event-note'")
            assert page.evaluate("() => document.activeElement.id") != ("research-event-note")
            assert page.evaluate("() => document.activeElement.id") == "nav-research"
            assert page.locator("#research-event-note").input_value() == ""
            assert page.locator("#research-dialog-overlay").get_attribute("aria-hidden") == "true"
            visible = " ".join(
                page.locator(selector).inner_text()
                for selector in ("#research-today-card", "#research-workspace")
            )
            assert "Exact caregiver note" not in visible
            assert "Live PHI status text" not in visible
            assert "Dialog PHI status text" not in page.locator("#research-dialog").inner_text()
            assert GUIDANCE not in visible
            assert page.evaluate(
                "() => ({projection: researchProjection, draft: researchDraft,"
                " submission: pendingResearchSubmission,"
                " completion: pendingResearchCompletion})"
            ) == {
                "projection": None,
                "draft": None,
                "submission": None,
                "completion": None,
            }
        finally:
            context.close()
            browser.close()
