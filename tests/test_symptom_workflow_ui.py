from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
GUIDANCE = (
    "NET/Care records what you enter but does not assess urgency or monitor symptoms. "
    "Contact the treating team about symptoms or concerns. If you think this may be a "
    "medical emergency, contact local emergency services."
)
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _symptom_source() -> str:
    start = APP_JS.index("const SYMPTOM_SAFETY_GUIDANCE")
    end = APP_JS.index("async function loadSummary", start)
    return APP_JS[start:end]


def _action(action_id: str = "action-eligible", token: str = "action-token") -> dict:
    return {
        "id": action_id,
        "token": token,
        "text": "Call the treating team with the exact update",
        "status": "open",
        "owner": "Caregiver",
        "due_date": "2026-09-03",
    }


def _episode(
    episode_id: str,
    token: str,
    text: str,
    *,
    status: str = "current",
    severity: str | None = "moderate",
    detail: str | None = "",
    onset: str | None = "2026-08",
    onset_precision: str = "month",
    follow_up: dict | None = None,
) -> dict:
    resolution = None
    if status == "resolved":
        resolution = {
            "value": "2026",
            "precision": "year",
            "kind": "caregiver_entered",
            "recorded_at": "2026-09-01T10:00:00",
        }
    return {
        "id": episode_id,
        "token": token,
        "status": status,
        "symptom_text": text,
        "severity": {
            "level": severity,
            "detail": detail,
            "authority": "caregiver_entered_unverified",
        },
        "reported_subject": "patient",
        "timing_text": "",
        "frequency_text": None,
        "triggers_text": "After breakfast",
        "notes": None,
        "onset": {
            "value": onset,
            "precision": onset_precision,
            "kind": "caregiver_entered" if onset is not None else "unknown",
        },
        "resolution": resolution,
        "provenance": {
            "status": "caregiver_entered_unverified",
            "label": "Caregiver-entered · unverified",
        },
        "follow_up": copy.deepcopy(follow_up),
        "created_at": "2026-08-01T09:00:00",
        "updated_at": "2026-08-01T09:00:00",
    }


def _observation(
    observation_id: str,
    token: str,
    route_character: str,
    *,
    symptom: str = "Duplicate source wording",
    date: str | None = "2026-07",
) -> dict:
    ref = f"symref_{route_character * 64}"
    return {
        "id": observation_id,
        "token": token,
        "date": {
            "value": date,
            "precision": "month" if date else "unknown",
            "kind": "legacy_unknown" if date else "unknown",
            "source_document_date": "2026-07-31",
            "source_document_date_precision": "day",
        },
        "symptom": symptom,
        "severity": None,
        "note": "",
        "related_treatment": None,
        "provenance": {
            "status": "source_verified",
            "label": "Exact source",
            "source_url": (f"/api/patient/symptom-episodes/observations/{ref}/source"),
            "evidence_url": (f"/api/patient/symptom-episodes/observations/{ref}/evidence"),
        },
    }


def _projection(profile_revision: int = 5, workflow_revision: int = 3) -> dict:
    observations = [
        _observation("observation-one", "observation-token-one", "1"),
        _observation("observation-two", "observation-token-two", "2"),
        _observation(
            "observation-unknown",
            "observation-token-three",
            "3",
            symptom="",
            date=None,
        ),
    ]
    episodes = [
        _episode(
            f"syme_{'a' * 32}",
            "episode-token-current",
            "Exact current wording",
        ),
        _episode(
            f"syme_{'b' * 32}",
            "episode-token-resolved",
            "Exact resolved wording",
            status="resolved",
            severity=None,
            detail=None,
            onset=None,
            onset_precision="unknown",
        ),
    ]
    return {
        "profile_revision": profile_revision,
        "workflow_revision": workflow_revision,
        "projection_token": f"projection-{profile_revision}-{workflow_revision}",
        "observation_count": len(observations),
        "episode_count": len(episodes),
        "observations": observations,
        "episodes": episodes,
        "eligible_actions": [_action()],
        "safety_guidance": {
            "kind": "fixed_non_diagnostic",
            "text": GUIDANCE,
        },
    }


def _run_validator(payloads: list[dict]) -> list[object]:
    script = "\n".join(
        [
            """
const document = { baseURI: 'http://app.test/' };
const window = {
  location: { href: 'http://app.test/', origin: 'http://app.test' },
};
""",
            _symptom_source(),
            """
const payloads = JSON.parse(process.argv[1]);
console.log(JSON.stringify(payloads.map(payload => symptomProjectionPayloadIsValid(payload))));
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP, json.dumps(payloads)],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_real_validator_rejects_duplicate_dangling_and_unsafe_authority_atomically():
    valid = _projection()
    duplicate_episode = copy.deepcopy(valid)
    duplicate_episode["episodes"][1]["id"] = duplicate_episode["episodes"][0]["id"]
    dangling_evidence = copy.deepcopy(valid)
    dangling_evidence["observations"][0]["provenance"]["source_url"] = None
    unsafe_host = copy.deepcopy(valid)
    unsafe_host["observations"][0]["provenance"]["source_url"] = (
        "https://evil.example/api/patient/symptom-episodes/observations/"
        f"symref_{'1' * 64}/source"
    )
    encoded_path = copy.deepcopy(valid)
    encoded_path["observations"][0]["provenance"]["source_url"] = (
        "/api/patient/symptom-episodes/observations/" f"symref_{'1' * 64}/%73ource"
    )
    mismatched_precision = copy.deepcopy(valid)
    mismatched_precision["episodes"][0]["onset"]["precision"] = "day"
    wrong_guidance = copy.deepcopy(valid)
    wrong_guidance["safety_guidance"]["text"] = "Call now."

    assert _run_validator(
        [
            valid,
            duplicate_episode,
            dangling_evidence,
            unsafe_host,
            encoded_path,
            mismatched_precision,
            wrong_guidance,
        ]
    ) == [True, False, False, False, False, False, False]


def test_symptom_module_has_one_authority_and_no_clinical_or_date_inference():
    source = _symptom_source()
    assert "/api/patient/symptom-episodes" in source
    assert "/api/symptoms" not in APP_JS
    assert "fetch('/api/status" not in source
    assert "new Date(" not in source
    assert "Date.parse" not in source
    assert "episodes.sort(" not in source
    assert "observations.sort(" not in source
    assert ".dedupe" not in source
    assert GUIDANCE in INDEX_HTML
    assert INDEX_HTML.count(GUIDANCE) == 3
    assert "Caregiver-entered · unverified" in INDEX_HTML
    assert "patient-reported" not in source.lower()
    assert "triage" not in source.lower()
    assert "treatment advice" not in source.lower()


def test_symptom_mutations_are_atomic_owned_and_replay_exact():
    source = _symptom_source()
    assert "bodyText: JSON.stringify(canonicalBody)" in source
    assert "body: intent.bodyText" in source
    assert "mutation_id: newMutationId()" in source
    assert "expected_profile_revision: symptomProjection.profile_revision" in source
    assert "expected_workflow_revision: symptomProjection.workflow_revision" in source
    assert "expected_projection_token: symptomProjection.projection_token" in source
    assert "expected_episode_token" in source
    assert "expected_action_token" in source
    assert "symptomMutationPending" in source
    assert "/api/follow-ups" not in source
    assert "pendingSymptomCompletion" in source
    assert "preserveMutation: true" in source


class _LiveState:
    def __init__(self, empty: bool = False) -> None:
        self.projection = _projection()
        if empty:
            self.projection["observations"] = []
            self.projection["observation_count"] = 0
            self.projection["episodes"] = []
            self.projection["episode_count"] = 0
            self.projection["eligible_actions"] = []
        self.requests: list[tuple[str, str, dict | None]] = []
        self.counter = 0

    def _advance(self) -> None:
        self.counter += 1
        self.projection["profile_revision"] += 1
        self.projection["workflow_revision"] += 1
        self.projection["projection_token"] = (
            f"projection-live-{self.projection['profile_revision']}"
        )

    def _retoken(self, episode: dict) -> None:
        episode["token"] = f"episode-live-{self.counter}"
        episode["updated_at"] = f"2026-09-{self.counter + 1:02d}T10:00:00"

    def mutate(self, method: str, path: str, body: dict) -> dict:
        self._advance()
        if method == "POST" and path == "/api/symptom-episodes":
            episode = _episode(
                f"syme_{'c' * 32}",
                f"episode-live-{self.counter}",
                body["symptom_text"],
                severity=body["severity_level"],
                detail=body["severity_detail"],
                onset=body["onset_date"],
                onset_precision="year",
            )
            if "follow_up" in body:
                episode["follow_up"] = _action(
                    "action-inline",
                    f"action-inline-{self.counter}",
                )
                episode["follow_up"]["text"] = body["follow_up"]["text"]
                episode["follow_up"]["owner"] = body["follow_up"]["owner"]
                episode["follow_up"]["due_date"] = body["follow_up"]["due_date"]
            self.projection["episodes"].append(episode)
        else:
            episode_id = path.split("/")[3]
            episode = next(item for item in self.projection["episodes"] if item["id"] == episode_id)
            if path.endswith("/follow-up"):
                if body.get("caregiver_action_id") is None:
                    old = episode["follow_up"]
                    episode["follow_up"] = None
                    if old and old["id"] == "action-eligible":
                        old["token"] = f"action-token-{self.counter}"
                        self.projection["eligible_actions"] = [old]
                elif body.get("caregiver_action_id"):
                    action = next(
                        item
                        for item in self.projection["eligible_actions"]
                        if item["id"] == body["caregiver_action_id"]
                    )
                    self.projection["eligible_actions"] = []
                    action["token"] = f"action-token-{self.counter}"
                    episode["follow_up"] = action
                else:
                    episode["follow_up"] = _action(
                        f"action-inline-{self.counter}",
                        f"action-inline-token-{self.counter}",
                    )
                    episode["follow_up"]["text"] = body["follow_up"]["text"]
                    episode["follow_up"]["owner"] = body["follow_up"]["owner"]
                    episode["follow_up"]["due_date"] = body["follow_up"]["due_date"]
            elif path.endswith("/resolve"):
                episode["status"] = "resolved"
                value = body["resolved_date"]
                episode["resolution"] = {
                    "value": value,
                    "precision": "month" if value else "unknown",
                    "kind": "caregiver_entered" if value else "unknown",
                    "recorded_at": "2026-09-02T10:00:00",
                }
            else:
                episode["symptom_text"] = body["symptom_text"]
                episode["severity"]["level"] = body["severity_level"]
                episode["severity"]["detail"] = body["severity_detail"]
            self._retoken(episode)
        self.projection["episode_count"] = len(self.projection["episodes"])
        return {
            "episode": copy.deepcopy(episode),
            "follow_up": copy.deepcopy(episode["follow_up"]),
            "workflow_revision": self.projection["workflow_revision"],
            "profile_revision": self.projection["profile_revision"],
        }


def _standard_payload(path: str, state: _LiveState) -> object:
    revision = state.projection["profile_revision"]
    workflow = state.projection["workflow_revision"]
    payloads = {
        "/api/status": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "patient": {"diagnosis": "Status patient"},
            "stats": {},
            "alerts": [],
            "treatments_classified": [],
            "treatments_fallback": [],
        },
        "/api/patient/biomarker-series": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "projection_token": "biomarker-empty",
            "observation_count": 0,
            "source_row_count": 0,
            "analytes": [],
        },
        "/api/patient/imaging-series": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "source_row_count": 0,
            "projection_token": "imaging-empty",
            "records": [],
        },
        "/api/follow-ups": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "items": [],
        },
        "/api/visits": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "appointments": [],
            "items": [],
        },
        "/api/summary": {"status": "not_generated", "profile_revision": revision},
        "/api/jobs": [],
        "/api/questions": [],
        "/api/judgments": [],
        "/api/patient/evidence": {"documents": [], "sources": []},
    }
    return payloads.get(path, {})


def _open_symptom_page(playwright, width: int, height: int, *, empty: bool = False):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    state = _LiveState(empty=empty)

    def fulfill(route):
        request = route.request
        path = urlsplit(request.url).path
        body = json.loads(request.post_data) if request.post_data else None
        state.requests.append((request.method, path, body))
        if path == "/api/patient/symptom-episodes":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(state.projection),
            )
            return
        if path.startswith("/api/symptom-episodes") and request.method != "GET":
            result = state.mutate(request.method, path, body or {})
            route.fulfill(
                status=201 if path == "/api/symptom-episodes" else 200,
                content_type="application/json",
                body=json.dumps(result),
            )
            return
        if path.endswith("/source") or path.endswith("/evidence"):
            route.fulfill(status=200, content_type="text/plain", body="Exact source")
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_standard_payload(path, state)),
        )

    page.route("**/api/**", fulfill)
    page.set_content(html)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content=APP_JS)
    page.evaluate("() => { clearTimeout(pollingInterval); pollingInterval = null; }")
    page.wait_for_function("() => ['current', 'empty'].includes(symptomProjectionState)")
    return browser, context, page, state


@pytest.mark.parametrize("width,height", [(1280, 900), (360, 800)])
def test_live_symptom_projection_is_separate_exact_accessible_and_overflow_safe(
    width: int,
    height: int,
):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(
            playwright,
            width,
            height,
        )
        try:
            assert page.locator("#today-symptom-list .symptom-episode-card").count() == 1
            page.locator("#nav-patient").click()
            assert page.locator("#patient-current-symptom-list .symptom-episode-card").count() == 1
            assert page.locator("#patient-resolved-symptom-list .symptom-episode-card").count() == 1
            assert page.locator("#symptom-observation-table-body tr").count() == 3
            page.locator("#symptom-tab-observations").click()
            observation_text = page.locator("#symptom-panel-observations").inner_text()
            assert observation_text.count("Duplicate source wording") == 2
            assert "Exact current wording" not in observation_text
            assert "Source observations are read-only mentions" in observation_text
            page.locator("#symptom-tab-current").click()
            episode_text = page.locator("#patient-current-symptom-list").inner_text()
            assert "Moderate · Empty string recorded" in episode_text
            assert "2026-08 · month precision" in episode_text
            assert "Caregiver-entered · unverified" in episode_text
            assert GUIDANCE in page.locator("#symptom-workspace").inner_text()
            assert not any(path == "/api/symptoms" for _, path, _ in state.requests)
            baseline = sum(path == "/api/patient/symptom-episodes" for _, path, _ in state.requests)
            page.evaluate("() => ensureSymptomEpisodes()")
            page.wait_for_timeout(50)
            assert (
                sum(path == "/api/patient/symptom-episodes" for _, path, _ in state.requests)
                == baseline
            )

            page.locator("#symptom-tab-observations").click()
            overflow = page.evaluate(
                """() => {
                  const table = document.getElementById('symptom-observation-table-region');
                  return {
                    document: document.documentElement.scrollWidth
                      - document.documentElement.clientWidth,
                    tableScrolls: table.scrollWidth > table.clientWidth,
                  };
                }"""
            )
            assert overflow["document"] == 0
            assert overflow["tableScrolls"] is (width == 360)
            page.locator("#symptom-observation-table-region").focus()
            assert page.evaluate("() => document.activeElement.id") == (
                "symptom-observation-table-region"
            )
            if width == 360:
                heights = page.locator(
                    "#symptom-workspace button, #symptom-workspace summary"
                ).evaluate_all(
                    "items => items.filter(item => item.offsetParent !== null)"
                    ".map(item => item.getBoundingClientRect().height)"
                )
                assert heights
                assert min(heights) >= 44
        finally:
            context.close()
            browser.close()


def test_live_symptom_lifecycle_and_atomic_follow_up_mutations():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            current_card = page.locator(
                "#patient-current-symptom-list .symptom-episode-card"
            ).filter(has_text="Exact current wording")

            current_card.get_by_role("button", name="Add follow-up").click()
            page.locator("#symptom-follow-up-submit").click()
            page.wait_for_function("() => !symptomMutationPending")
            current_card = page.locator(
                "#patient-current-symptom-list .symptom-episode-card"
            ).filter(has_text="Exact current wording")
            assert "Linked caregiver follow-up" in current_card.inner_text()

            current_card.get_by_role("button", name="Review linked follow-up").click()
            page.locator("#symptom-unlink-submit").click()
            page.wait_for_function("() => !symptomMutationPending")

            current_card = page.locator(
                "#patient-current-symptom-list .symptom-episode-card"
            ).filter(has_text="Exact current wording")
            current_card.get_by_role("button", name="Edit episode facts").click()
            page.locator("#symptom-text").fill("Corrected exact current wording")
            page.locator("#symptom-details-submit").click()
            page.wait_for_function("() => !symptomMutationPending")
            assert (
                "Corrected exact current wording"
                in page.locator("#patient-current-symptom-list").inner_text()
            )

            current_card = page.locator(
                "#patient-current-symptom-list .symptom-episode-card"
            ).filter(has_text="Corrected exact current wording")
            current_card.get_by_role("button", name="Resolve episode").click()
            assert page.locator("#symptom-resolved-date").input_value() == ""
            page.locator("#symptom-resolved-date").fill("2026-09")
            page.locator("#symptom-resolve-confirm").check()
            page.locator("#symptom-resolve-submit").click()
            page.wait_for_function("() => !symptomMutationPending")
            assert (
                "Corrected exact current wording"
                not in page.locator("#patient-current-symptom-list").inner_text()
            )
            page.locator("#symptom-tab-resolved").click()
            resolved_text = page.locator("#patient-resolved-symptom-list").inner_text()
            assert "Corrected exact current wording" in resolved_text
            assert "Reopen" not in resolved_text

            page.locator("#patient-symptom-add").click()
            page.locator("#symptom-text").fill("New recurrence wording")
            page.locator("#symptom-severity").select_option("mild")
            page.locator("#symptom-onset-date").fill("2026")
            page.locator('input[name="symptom-create-follow-up-mode"][value="inline"]').check()
            page.locator("#symptom-create-follow-up-text").fill(
                "Write down the next treating-team update"
            )
            page.locator("#symptom-details-submit").click()
            page.wait_for_function("() => !symptomMutationPending")
            page.locator("#symptom-tab-current").click()
            assert (
                "New recurrence wording"
                in page.locator("#patient-current-symptom-list").inner_text()
            )

            symptom_mutations = [
                item
                for item in state.requests
                if item[1].startswith("/api/symptom-episodes") and item[0] != "GET"
            ]
            assert [item[0] for item in symptom_mutations] == [
                "PATCH",
                "PATCH",
                "PATCH",
                "POST",
                "POST",
            ]
            assert all(item[2]["mutation_id"] for item in symptom_mutations)
            assert all(
                item[2]["expected_profile_revision"] >= 5
                and item[2]["expected_workflow_revision"] >= 3
                and item[2]["expected_projection_token"]
                for item in symptom_mutations
            )
            create_body = symptom_mutations[-1][2]
            assert create_body["follow_up"] == {
                "text": "Write down the next treating-team update",
                "owner": None,
                "due_date": None,
            }
            assert "caregiver_action_id" not in create_body
            assert not any(
                method == "POST" and path == "/api/follow-ups" for method, path, _ in state.requests
            )
        finally:
            context.close()
            browser.close()


def test_live_empty_projection_can_record_the_first_episode():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, _ = _open_symptom_page(
            playwright,
            360,
            800,
            empty=True,
        )
        try:
            assert page.evaluate("() => symptomProjectionState") == "empty"
            assert page.locator("#today-symptom-add").is_enabled()
            page.locator("#today-symptom-add").click()
            assert page.locator("#symptom-dialog-overlay").get_attribute("aria-hidden") == "false"
            assert page.evaluate(
                "() => document.getElementById('symptom-dialog').contains(document.activeElement)"
            )
        finally:
            context.close()
            browser.close()


def test_live_symptom_transport_hard_failure_and_replacement_scrub_boundaries():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, state = _open_symptom_page(playwright, 1280, 900)
        try:
            page.locator("#nav-patient").click()
            page.locator("#patient-symptom-add").click()
            page.locator("#symptom-text").fill("Unsent exact draft")
            baseline = sum(path == "/api/patient/symptom-episodes" for _, path, _ in state.requests)
            page.evaluate(
                """() => {
                  window.__symptomRealFetch = window.fetch.bind(window);
                  window.fetch = (url, options) => {
                    if (String(url).includes('/api/patient/symptom-episodes')) {
                      return Promise.reject(new TypeError('private transport detail'));
                    }
                    return window.__symptomRealFetch(url, options);
                  };
                }"""
            )
            page.evaluate("() => loadSymptomEpisodes({ force: true })")
            page.wait_for_function("() => symptomProjectionState === 'stale'")
            assert "Unsent exact draft" == page.locator("#symptom-text").input_value()
            assert page.locator("#symptom-details-submit").is_disabled()
            assert (
                "private transport detail"
                not in page.locator("#patient-symptom-status").inner_text()
            )

            page.evaluate("() => { window.fetch = window.__symptomRealFetch; }")
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_function("() => symptomProjectionState === 'current'")
            assert (
                sum(path == "/api/patient/symptom-episodes" for _, path, _ in state.requests)
                == baseline + 1
            )
            assert page.locator("#symptom-text").input_value() == "Unsent exact draft"

            page.locator("#symptom-dialog-close").click()
            current_card = page.locator(
                "#patient-current-symptom-list .symptom-episode-card"
            ).filter(has_text="Exact current wording")
            current_card.get_by_role("button", name="Edit episode facts").click()
            page.locator("#symptom-text").fill("Draft tied to old token")
            state.projection["episodes"][0]["token"] = "replacement-episode-token"
            state.projection["projection_token"] = "replacement-projection-token"
            page.evaluate("() => loadSymptomEpisodes({ force: true })")
            page.wait_for_function("() => symptomProjectionState === 'current'")
            assert page.locator("#symptom-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert page.locator("#symptom-text").input_value() == ""
            assert page.evaluate("() => selectedSymptomEpisodeId") is None
            assert page.evaluate("() => pendingSymptomIntent") is None

            patient_before = page.locator("#patient-dx").inner_text()
            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (String(url).includes('/api/patient/symptom-episodes')) {
                      return Promise.resolve(new Response(
                        JSON.stringify({ error: 'private server detail' }),
                        { status: 500, headers: { 'Content-Type': 'application/json' } }
                      ));
                    }
                    return window.__symptomRealFetch(url, options);
                  };
                }"""
            )
            page.evaluate("() => loadSymptomEpisodes({ force: true })")
            page.wait_for_function("() => symptomProjectionState === 'error'")
            assert page.locator("#patient-dx").inner_text() == patient_before
            assert (
                "Exact current wording"
                not in page.locator("#patient-current-symptom-list").inner_text()
            )
            assert (
                "private server detail" not in page.locator("#patient-symptom-status").inner_text()
            )

            page.evaluate("() => { window.fetch = window.__symptomRealFetch; }")
            page.evaluate("() => loadSymptomEpisodes({ force: true })")
            page.wait_for_function("() => symptomProjectionState === 'current'")
            page.locator("#patient-symptom-add").click()
            page.locator("#symptom-text").fill("PHI that must be evicted")
            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (String(url).includes('/api/patient/symptom-episodes')) {
                      return Promise.resolve(new Response(
                        JSON.stringify({ error: 'denied' }),
                        { status: 401, headers: { 'Content-Type': 'application/json' } }
                      ));
                    }
                    return window.__symptomRealFetch(url, options);
                  };
                }"""
            )
            page.evaluate("() => loadSymptomEpisodes({ force: true })")
            page.wait_for_function("() => latestProfileRevision === null")
            assert page.locator("#patient-dx").inner_text() == "Patient data unavailable"
            assert page.locator("#symptom-text").input_value() == ""
            assert page.locator("#symptom-dialog-overlay").get_attribute("aria-hidden") == "true"
            assert page.evaluate("() => symptomProjection") is None
        finally:
            context.close()
            browser.close()
