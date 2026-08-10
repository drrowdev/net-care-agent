from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _function_source(name: str, next_name: str) -> str:
    start = APP_JS.index(f"function {name}")
    end = APP_JS.index(f"function {next_name}", start)
    return APP_JS[start:end]


def _executable_function_source(name: str, next_name: str) -> str:
    source = _function_source(name, next_name).rstrip()
    if source.endswith("async"):
        source = source.removesuffix("async").rstrip()
    start = APP_JS.index(f"function {name}")
    return f"async {source}" if APP_JS[start - 6 : start] == "async " else source


def _biomarker_function_source() -> str:
    start = APP_JS.index("function safeBiomarkerEvidenceUrl")
    end = APP_JS.index("async function loadStatus", start)
    return APP_JS[start:end]


def _observation(
    observation_id: str,
    series_id: str,
    date: str,
    raw,
    *,
    comparable: bool,
    numeric_value=None,
    duplicate_count: int = 1,
    marker_context: str = "Plasma",
    notes: list[str] | None = None,
    evidence_status: str = "verified",
) -> dict:
    row_ids = [f"row-{observation_id}-{index}" for index in range(duplicate_count)]
    evidence_url = (
        f"/api/evidence/source-{observation_id}?start=1&end=8"
        if evidence_status == "verified"
        else None
    )
    return {
        "id": observation_id,
        "token": f"token-{observation_id}",
        "source_row_ids": row_ids,
        "duplicate_count": duplicate_count,
        "date": {
            "value": date,
            "precision": "day" if len(date) == 10 else "month",
            "kind": "collection" if len(date) == 10 else "unknown",
            "source_document_date": "2026-04-30",
            "source_document_date_precision": "day",
        },
        "value": {
            "raw": raw,
            "kind": "numeric" if numeric_value is not None else "qualified",
            "numeric_value": numeric_value,
        },
        "unit": "ng/mL",
        "reference_range": "0-100",
        "reference_range_semantics": {"kind": "interval", "lower": 0, "upper": 100},
        "reported_flag": None,
        "reported_flag_authority": "unknown",
        "report_range_comparison": "within" if numeric_value is not None else None,
        "report_range_label": (
            "Compared with the report's reference range" if numeric_value is not None else None
        ),
        "specimen": marker_context,
        "assay": "Assay X",
        "method": None,
        "series_id": series_id,
        "comparable": comparable,
        "comparability_notes": notes or [],
        "provenance": {
            "status": "source_verified" if evidence_status == "verified" else "source_unverified",
            "label": "Exact source" if evidence_status == "verified" else "No exact source",
            "source_document_ids": [f"source-{observation_id}"],
            "evidence": [
                {
                    "id": f"evidence-{observation_id}",
                    "status": evidence_status,
                    "evidence_url": evidence_url,
                    "source_url": f"/api/sources/source-{observation_id}/text",
                }
            ],
        },
    }


def _projection(
    token: str = "projection-current",
    *,
    profile_revision: int = 5,
    workflow_revision: int = 3,
    nse_value: int = 14,
) -> dict:
    cga_series = {
        "id": "series-cga-comparable",
        "token": f"{token}-series-cga",
        "label": "Comparable numeric series",
        "unit": "ng/mL",
        "specimen": "Plasma",
        "assay": "Assay X",
        "method": None,
        "date_kind": "collection",
        "reference_range_semantics": {"kind": "interval", "lower": 0, "upper": 100},
        "comparable": True,
        "comparability_notes": [],
        "observation_ids": ["obs-cga-1", "obs-cga-2"],
    }
    cga_isolated = {
        "id": "series-cga-isolated",
        "token": f"{token}-series-isolated",
        "label": "Not comparable",
        "unit": "ng/mL",
        "specimen": "Plasma",
        "assay": "Assay X",
        "method": None,
        "date_kind": "unknown",
        "reference_range_semantics": {"kind": "interval", "lower": 0, "upper": 100},
        "comparable": False,
        "comparability_notes": ["Only finite unqualified numeric values are comparable."],
        "observation_ids": ["obs-cga-qualified"],
    }
    nse_series = {
        "id": "series-nse-single",
        "token": f"{token}-series-nse",
        "label": "Single compatible value",
        "unit": "ng/mL",
        "specimen": "Serum",
        "assay": "Assay Y",
        "method": None,
        "date_kind": "collection",
        "reference_range_semantics": {"kind": "interval", "lower": 0, "upper": 20},
        "comparable": False,
        "comparability_notes": ["Fewer than two compatible observations are recorded."],
        "observation_ids": ["obs-nse"],
    }
    cga_observations = [
        _observation(
            "obs-cga-1",
            cga_series["id"],
            "2026-01-01",
            10,
            comparable=True,
            numeric_value=10,
            duplicate_count=2,
        ),
        _observation(
            "obs-cga-2",
            cga_series["id"],
            "2026-02-01",
            nse_value,
            comparable=True,
            numeric_value=nse_value,
        ),
        _observation(
            "obs-cga-qualified",
            cga_isolated["id"],
            "2026-03",
            "<5",
            comparable=False,
            notes=["Only finite unqualified numeric values are comparable."],
            evidence_status="missing",
        ),
    ]
    nse_observation = _observation(
        "obs-nse",
        nse_series["id"],
        "2026-04-01",
        nse_value,
        comparable=False,
        numeric_value=nse_value,
        marker_context="Serum",
        notes=["Fewer than two compatible observations are recorded."],
    )
    return {
        "profile_revision": profile_revision,
        "workflow_revision": workflow_revision,
        "projection_token": token,
        "observation_count": 4,
        "source_row_count": 5,
        "analytes": [
            {
                "id": "analyte-cga",
                "token": f"{token}-analyte-cga",
                "display_name": "Chromogranin A",
                "observed_aliases": ["CgA", "S-<CgA>"],
                "observation_count": 3,
                "source_row_count": 4,
                "series_count": 2,
                "series": [cga_series, cga_isolated],
                "observations": cga_observations,
            },
            {
                "id": "analyte-nse",
                "token": f"{token}-analyte-nse",
                "display_name": "NSE",
                "observed_aliases": ["NSE"],
                "observation_count": 1,
                "source_row_count": 1,
                "series_count": 1,
                "series": [nse_series],
                "observations": [nse_observation],
            },
        ],
    }


def _node_prelude() -> str:
    return "\n".join(
        [
            """
class FakeElement {
  constructor(id) {
    this.id = id;
    this.className = '';
    this.disabled = false;
    this.hidden = false;
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.signal = null;
  }
  blur() { if (document.activeElement === this) document.activeElement = null; }
  contains(node) {
    return node === this || (
      this.id === 'biomarker-explorer'
      && String(node?.id || '').startsWith('biomarker-')
    );
  }
  focus() { document.activeElement = this; }
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, new FakeElement(id));
  return elements.get(id);
};
const document = {
  activeElement: null,
  getElementById: element,
};
const window = { location: { origin: 'http://app.test' } };
const navigator = { onLine: true };
let activeView = 'patient';
let phiEpoch = 0;
let latestProfileRevision = 0;
let workflowRevision = 0;
let taskSelectionEpoch = 0;
let selectedTaskId = null;
let visitSelectionEpoch = 0;
let selectedVisitId = null;
let followUpSelectionEpoch = 0;
let selectedFollowUpId = null;
let alertSelectionEpoch = 0;
let selectedAlertId = null;
let biomarkerProjection = null;
let biomarkerResponseOwner = null;
let selectedBiomarkerAnalyteId = null;
let biomarkerLoadEpoch = 0;
let biomarkerSelectionEpoch = 0;
let biomarkerRequestController = null;
let biomarkerProjectionState = 'idle';
let biomarkerNetworkAmbiguous = false;
const loadEvents = [];
function requestClinicalConvergence() {}
function markVisitRecapStale() {}
function advancePatientAuthority(revision) {
  const normalized = normalizedRevision(revision);
  if (!Number.isSafeInteger(normalized) || normalized <= latestProfileRevision) return false;
  latestProfileRevision = normalized;
  phiEpoch += 1;
  return true;
}
function reportLoadSuccess(scope) { loadEvents.push(['success', scope]); }
function reportLoadError(scope, error) {
  loadEvents.push(['error', scope, error?.status || error?.name || 'network']);
}
function evictClientPhi(error) {
  phiEpoch += 1;
  latestProfileRevision = null;
  workflowRevision = null;
  clearBiomarkerProjection({
    state: 'error',
    statusLabel: 'Patient data unavailable',
    message: `Biomarker authority evicted (${error.status}).`,
    retry: false,
  });
}
""",
            _function_source("safeClassToken", "safeExternalUrl"),
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("capturePatientRequest", "patientRequestIsCurrent"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("authorizePatientResponse", "setAppointmentMessage"),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _function_source("shouldEvictClientPhi", "restoreDialogFocus"),
            _function_source("escHtml", "fmtDate"),
            _biomarker_function_source(),
            """
function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
""",
        ]
    )


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


def test_actual_biomarker_functions_preserve_raw_authority_and_exact_series_partition():
    projection = _projection()
    script = "\n".join(
        [
            _node_prelude(),
            f"const payload = {json.dumps(projection)};",
            """
biomarkerLoadEpoch = 1;
biomarkerSelectionEpoch = 1;
phiEpoch = 2;
latestProfileRevision = payload.profile_revision;
workflowRevision = payload.workflow_revision;
biomarkerProjection = payload;
selectedBiomarkerAnalyteId = 'analyte-cga';
biomarkerProjectionState = 'current';
biomarkerResponseOwner = newBiomarkerResponseOwner(
  biomarkerProjection,
  selectedBiomarkerAnalyte(),
);
const valid = biomarkerProjectionPayloadIsValid(payload);
const rendered = renderBiomarkerProjection(biomarkerResponseOwner);
const first = {
  select: element('biomarker-analyte-select').innerHTML,
  context: element('biomarker-context').innerHTML,
  table: element('biomarker-table-body').innerHTML,
  charts: element('biomarker-chart-region').innerHTML,
  ownerToken: biomarkerResponseOwner.projectionToken,
};
const switched = selectBiomarkerAnalyte('analyte-nse');
const second = {
  selected: selectedBiomarkerAnalyteId,
  table: element('biomarker-table-body').innerHTML,
  charts: element('biomarker-chart-region').innerHTML,
  selectionEpoch: biomarkerSelectionEpoch,
  ownerToken: biomarkerResponseOwner.analyteToken,
};
activeView = 'today';
const workflowAuthority = authorizePatientResponse(capturePatientRequest(), {
  profile_revision: payload.profile_revision,
  workflow_revision: payload.workflow_revision + 1,
});
const workflowAdvance = {
  accepted: workflowAuthority.accepted,
  state: biomarkerProjectionState,
  freshness: element('biomarker-freshness').textContent,
  status: element('biomarker-status').textContent,
  ownerCurrent: biomarkerResponseOwnerIsCurrent(biomarkerResponseOwner),
};
console.log(JSON.stringify({
  valid,
  rendered,
  switched,
  first,
  second,
  workflowAdvance,
  emptyScalar: biomarkerScalar(''),
  missingScalar: biomarkerScalar(null),
}));
""",
        ]
    )
    result = _run_node(script)

    assert result["valid"] is True
    assert result["rendered"] is True
    assert result["switched"] is True
    assert "S-&lt;CgA&gt;" in result["first"]["context"]
    assert "&lt;5" in result["first"]["table"]
    assert "Only finite unqualified numeric values are comparable." in result["first"]["table"]
    assert "2 recorded source rows" in result["first"]["table"]
    assert "row-obs-cga-1-0" in result["first"]["table"]
    assert "evidence-obs-cga-1" in result["first"]["table"]
    assert "Open exact span" in result["first"]["table"]
    assert result["first"]["charts"].count("<circle") == 2
    assert "series-cga-isolated" not in result["first"]["charts"]
    assert "<polyline" not in result["first"]["charts"]
    assert "<path" not in result["first"]["charts"]
    assert result["first"]["ownerToken"] == projection["projection_token"]
    assert result["second"]["selected"] == "analyte-nse"
    assert str(14) in result["second"]["table"]
    assert "fewer than two observations" in result["second"]["charts"].lower()
    assert result["second"]["selectionEpoch"] == 2
    assert result["second"]["ownerToken"] == projection["analytes"][1]["token"]
    assert result["workflowAdvance"]["accepted"] is True
    assert result["workflowAdvance"]["state"] == "stale"
    assert result["workflowAdvance"]["freshness"] == "Stale snapshot"
    assert "workflow changed" in result["workflowAdvance"]["status"]
    assert result["workflowAdvance"]["ownerCurrent"] is True
    assert result["emptyScalar"] == 'Empty string ("")'
    assert result["missingScalar"] == "Not recorded"


def test_actual_loader_rejects_late_response_retains_offline_snapshot_and_evicts():
    late = _projection("projection-late", profile_revision=5, workflow_revision=2, nse_value=15)
    fresh = _projection("projection-fresh", profile_revision=6, workflow_revision=3, nse_value=16)
    recovered = _projection(
        "projection-recovered",
        profile_revision=7,
        workflow_revision=4,
        nse_value=17,
    )
    script = "\n".join(
        [
            _node_prelude(),
            f"const latePayload = {json.dumps(late)};",
            f"const freshPayload = {json.dumps(fresh)};",
            f"const recoveredPayload = {json.dumps(recovered)};",
            """
(async () => {
  let resolveLate;
  let fetchCount = 0;
  globalThis.fetch = async () => {
    fetchCount += 1;
    if (fetchCount === 1) {
      return new Promise(resolve => { resolveLate = () => resolve(response(200, latePayload)); });
    }
    return response(200, freshPayload);
  };
  const lateLoad = loadBiomarkerSeries();
  await Promise.resolve();
  const freshLoad = loadBiomarkerSeries();
  await freshLoad;
  resolveLate();
  await lateLoad;
  const afterRace = {
    token: biomarkerProjection?.projection_token,
    table: element('biomarker-table-body').innerHTML,
    ownerCurrent: biomarkerResponseOwnerIsCurrent(biomarkerResponseOwner),
  };

  globalThis.fetch = async () => { throw new TypeError('offline'); };
  await loadBiomarkerSeries();
  const afterOffline = {
    token: biomarkerProjection?.projection_token,
    state: biomarkerProjectionState,
    table: element('biomarker-table-body').innerHTML,
    status: element('biomarker-status').textContent,
  };

  globalThis.fetch = async () => response(200, recoveredPayload);
  await loadBiomarkerSeries();
  const afterRecovery = {
    token: biomarkerProjection?.projection_token,
    state: biomarkerProjectionState,
    freshness: element('biomarker-freshness').textContent,
  };

  document.activeElement = element('biomarker-analyte-select');
  globalThis.fetch = async () => response(401, { error: 'denied' });
  await loadBiomarkerSeries();
  const afterAuth = {
    projection: biomarkerProjection,
    owner: biomarkerResponseOwner,
    selected: selectedBiomarkerAnalyteId,
    table: element('biomarker-table-body').innerHTML,
    retryHidden: element('biomarker-retry').hidden,
    activeElement: document.activeElement?.id || null,
    caption: element('biomarker-table-caption').textContent,
  };

  globalThis.fetch = async () => response(422, {
    code: 'biomarker_projection_invalid',
    error: 'Biomarker identity is missing or inconsistent.',
  });
  await loadBiomarkerSeries();
  const after422 = {
    projection: biomarkerProjection,
    state: biomarkerProjectionState,
    status: element('biomarker-status').textContent,
    table: element('biomarker-table-body').innerHTML,
  };
  console.log(JSON.stringify({
    fetchCount,
    afterRace,
    afterOffline,
    afterRecovery,
    afterAuth,
    after422,
    loadEvents,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    result = _run_node(script)

    assert result["fetchCount"] == 2
    assert result["afterRace"]["token"] == "projection-fresh"
    assert "16" in result["afterRace"]["table"]
    assert "15" not in result["afterRace"]["table"]
    assert result["afterRace"]["ownerCurrent"] is True
    assert result["afterOffline"]["token"] == "projection-fresh"
    assert result["afterOffline"]["state"] == "stale"
    assert result["afterOffline"]["table"] == result["afterRace"]["table"]
    assert "read-only" in result["afterOffline"]["status"]
    assert result["afterRecovery"] == {
        "token": "projection-recovered",
        "state": "current",
        "freshness": "Current",
    }
    assert result["afterAuth"]["projection"] is None
    assert result["afterAuth"]["owner"] is None
    assert result["afterAuth"]["selected"] is None
    assert "authority evicted (401)" in result["afterAuth"]["table"].lower()
    assert result["afterAuth"]["retryHidden"] is True
    assert result["afterAuth"]["activeElement"] == "nav-patient"
    assert result["afterAuth"]["caption"] == "Complete observations for the selected biomarker"
    assert result["after422"]["projection"] is None
    assert result["after422"]["state"] == "corrupt"
    assert "stored record could not be projected safely" in result["after422"]["status"]
    assert "identity is missing" not in result["after422"]["table"]


def test_actual_loader_distinguishes_empty_record_and_ordinary_hard_failure():
    empty = {
        "profile_revision": 2,
        "workflow_revision": 1,
        "projection_token": "projection-empty",
        "observation_count": 0,
        "source_row_count": 0,
        "analytes": [],
    }
    script = "\n".join(
        [
            _node_prelude(),
            f"const emptyPayload = {json.dumps(empty)};",
            """
(async () => {
  globalThis.fetch = async () => response(200, emptyPayload);
  await loadBiomarkerSeries();
  const emptyState = {
    token: biomarkerProjection?.projection_token,
    state: biomarkerProjectionState,
    status: element('biomarker-status').textContent,
    table: element('biomarker-table-body').innerHTML,
    disabled: element('biomarker-analyte-select').disabled,
    caption: element('biomarker-table-caption').textContent,
  };
  globalThis.fetch = async () => response(400, { error: 'SECRET server detail' });
  await loadBiomarkerSeries();
  const failureState = {
    projection: biomarkerProjection,
    state: biomarkerProjectionState,
    status: element('biomarker-status').textContent,
    table: element('biomarker-table-body').innerHTML,
  };
  console.log(JSON.stringify({ emptyState, failureState }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    result = _run_node(script)

    assert result["emptyState"]["token"] == "projection-empty"
    assert result["emptyState"]["state"] == "empty"
    assert "no biomarker observations recorded" in result["emptyState"]["status"].lower()
    assert "No biomarker observations are recorded" in result["emptyState"]["table"]
    assert result["emptyState"]["disabled"] is True
    assert result["emptyState"]["caption"] == "Complete observations for the selected biomarker"
    assert result["failureState"]["projection"] is None
    assert result["failureState"]["state"] == "error"
    assert "could not be loaded" in result["failureState"]["status"]
    assert "SECRET" not in result["failureState"]["table"]


def test_biomarker_markup_is_shared_semantic_and_status_is_not_a_data_source():
    assert INDEX_HTML.count('id="biomarker-explorer"') == 1
    assert INDEX_HTML.count('id="biomarker-analyte-select"') == 1
    assert 'role="region"' in INDEX_HTML
    assert 'aria-labelledby="biomarker-table-caption"' in INDEX_HTML
    assert "<caption" in INDEX_HTML
    assert 'role="status" aria-live="polite"' in INDEX_HTML
    assert (
        "copy"
        not in INDEX_HTML[
            INDEX_HTML.index('id="biomarker-explorer"') : INDEX_HTML.index(
                'aria-labelledby="alerts-heading"'
            )
        ].lower()
    )
    assert (
        "download"
        not in INDEX_HTML[
            INDEX_HTML.index('id="biomarker-explorer"') : INDEX_HTML.index(
                'aria-labelledby="alerts-heading"'
            )
        ].lower()
    )
    assert "recent_biomarkers" not in APP_JS
    assert "allBiomarkers" not in APP_JS
    assert "/api/patient/biomarker-series" in APP_JS


def _standard_payloads(projection: dict) -> dict[str, object]:
    revision = projection["profile_revision"]
    workflow = projection["workflow_revision"]
    return {
        "/api/status": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "patient": {},
            "stats": {},
            "alerts": [],
            "treatments_classified": [],
            "treatments_fallback": [],
        },
        "/api/patient/biomarker-series": projection,
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
        "/api/symptoms": [],
        "/api/patient/evidence": {"documents": [], "source_documents": []},
    }


def _open_biomarker_page(playwright, width: int, height: int, projection: dict):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    payloads = _standard_payloads(projection)

    def fulfill(route):
        path = urlsplit(route.request.url).path
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payloads.get(path, {})),
        )

    page.route("**/api/**", fulfill)
    page.set_content(html)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content=APP_JS)
    page.evaluate(
        """() => {
          clearTimeout(pollingInterval);
          pollingInterval = null;
        }"""
    )
    page.locator("#nav-patient").click()
    page.locator("#biomarker-analyte-select").wait_for(state="visible")
    page.wait_for_function("() => !document.getElementById('biomarker-analyte-select').disabled")
    return browser, context, page, payloads


def test_live_biomarker_explorer_is_semantic_responsive_and_overflow_safe():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        for width, height in ((1280, 900), (360, 800)):
            browser, context, page, _ = _open_biomarker_page(
                playwright,
                width,
                height,
                _projection(),
            )
            errors = []
            page.on("pageerror", lambda error, target=errors: target.append(str(error)))
            try:
                assert page.locator("#biomarker-table-body tr").count() == 3
                assert page.locator(".biomarker-chart-card").count() == 1
                assert page.locator(".biomarker-chart-card circle").count() == 2
                assert page.locator(".biomarker-chart-card polyline").count() == 0
                assert page.locator(".biomarker-chart-card path").count() == 0
                assert "S-<CgA>" in page.locator("#biomarker-context").inner_text()
                assert "<5" in page.locator("#biomarker-table-body").inner_text()
                assert (
                    "Only finite unqualified numeric values are comparable."
                    in page.locator("#biomarker-table-body").inner_text()
                )

                page.locator("#biomarker-analyte-select").select_option("analyte-nse")
                assert page.locator("#biomarker-table-body tr").count() == 1
                assert "NSE" in page.locator("#biomarker-table-caption").inner_text()
                assert (
                    "fewer than two observations"
                    in page.locator("#biomarker-chart-region").inner_text().lower()
                )

                overflow = page.evaluate(
                    """() => ({
                      document: document.documentElement.scrollWidth
                        - document.documentElement.clientWidth,
                      tableScrolls: document.getElementById('biomarker-table-region').scrollWidth
                        > document.getElementById('biomarker-table-region').clientWidth,
                      chartContained: document.getElementById('biomarker-chart-region').scrollWidth
                        <= document.getElementById('biomarker-explorer').clientWidth,
                    })"""
                )
                assert overflow == {
                    "document": 0,
                    "tableScrolls": True,
                    "chartContained": True,
                }
                select_height = page.locator("#biomarker-analyte-select").evaluate(
                    "element => element.getBoundingClientRect().height"
                )
                assert select_height >= 44

                page.locator("#biomarker-table-region").focus()
                focus = page.evaluate(
                    """() => {
                      const style = getComputedStyle(document.activeElement);
                      return {
                        id: document.activeElement.id,
                        outline: style.outlineStyle,
                        width: parseFloat(style.outlineWidth),
                      };
                    }"""
                )
                assert focus["id"] == "biomarker-table-region"
                assert focus["outline"] != "none"
                assert focus["width"] >= 3

                if width == 360:
                    page.locator("#biomarker-table-body summary").first.click()
                    link_heights = page.locator(
                        "#biomarker-table-body details[open] a"
                    ).evaluate_all(
                        "items => items.map(item => item.getBoundingClientRect().height)"
                    )
                    assert link_heights
                    assert all(item >= 44 for item in link_heights)
                assert errors == []
            finally:
                context.close()
                browser.close()


def test_live_biomarker_late_response_offline_recovery_and_hard_eviction():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, payloads = _open_biomarker_page(
            playwright,
            1280,
            900,
            _projection(),
        )
        try:
            late = _projection("projection-browser-late", profile_revision=6, nse_value=26)
            fresh = _projection("projection-browser-fresh", profile_revision=7, nse_value=27)
            page.evaluate(
                """([latePayload, freshPayload]) => {
                  window.__realFetch = window.fetch.bind(window);
                  window.__biomarkerFetchCount = 0;
                  window.fetch = (url, options) => {
                    if (!String(url).includes('/api/patient/biomarker-series')) {
                      return window.__realFetch(url, options);
                    }
                    window.__biomarkerFetchCount += 1;
                    if (window.__biomarkerFetchCount === 1) {
                      return new Promise(resolve => {
                        window.__resolveLateBiomarker = () => resolve(new Response(
                          JSON.stringify(latePayload),
                          { status: 200, headers: { 'Content-Type': 'application/json' } },
                        ));
                      });
                    }
                    return Promise.resolve(new Response(
                      JSON.stringify(freshPayload),
                      { status: 200, headers: { 'Content-Type': 'application/json' } },
                    ));
                  };
                }""",
                [late, fresh],
            )
            page.evaluate("() => { window.__lateBiomarkerLoad = loadBiomarkerSeries(); }")
            page.wait_for_function("() => window.__biomarkerFetchCount === 1")
            page.locator("#biomarker-analyte-select").select_option("analyte-nse")
            page.evaluate("() => loadBiomarkerSeries()")
            page.evaluate(
                """async () => {
                  window.__resolveLateBiomarker();
                  await window.__lateBiomarkerLoad;
                }"""
            )
            assert page.evaluate("() => biomarkerProjection.projection_token") == (
                "projection-browser-fresh"
            )
            assert page.locator("#biomarker-analyte-select").input_value() == "analyte-nse"
            assert (
                page.locator("#biomarker-table-body td:nth-child(2) > strong").inner_text()
                == "27 ng/mL"
            )

            page.evaluate("() => { window.fetch = window.__realFetch; }")
            context.set_offline(True)
            page.evaluate("() => window.dispatchEvent(new Event('offline'))")
            assert "Stale snapshot" in page.locator("#biomarker-freshness").inner_text()
            stale_table = page.locator("#biomarker-table-body").inner_text()
            assert "27" in stale_table
            assert "read-only" in page.locator("#biomarker-status").inner_text()

            recovered = _projection(
                "projection-browser-recovered",
                profile_revision=8,
                workflow_revision=4,
                nse_value=28,
            )
            payloads["/api/patient/biomarker-series"] = recovered
            payloads["/api/status"]["profile_revision"] = 8
            payloads["/api/status"]["workflow_revision"] = 4
            context.set_offline(False)
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_function(
                "() => biomarkerProjection?.projection_token === 'projection-browser-recovered'"
            )
            assert page.locator("#biomarker-freshness").inner_text() == "Current"
            assert (
                page.locator("#biomarker-table-body td:nth-child(2) > strong").inner_text()
                == "28 ng/mL"
            )

            page.locator("#biomarker-analyte-select").focus()
            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (!String(url).includes('/api/patient/biomarker-series')) {
                      return window.__realFetch(url, options);
                    }
                    return Promise.resolve(new Response(
                      JSON.stringify({ error: 'denied' }),
                      { status: 403, headers: { 'Content-Type': 'application/json' } },
                    ));
                  };
                }"""
            )
            page.evaluate("() => loadBiomarkerSeries()")
            assert page.evaluate("() => biomarkerProjection") is None
            assert page.evaluate("() => biomarkerResponseOwner") is None
            assert "28" not in page.locator("#biomarker-explorer").inner_text()
            assert page.locator("#biomarker-analyte-select").is_disabled()
            assert page.evaluate("() => document.activeElement.id") == "nav-patient"
            assert page.locator("#biomarker-table-caption").inner_text() == (
                "Complete observations for the selected biomarker"
            )

            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (!String(url).includes('/api/patient/biomarker-series')) {
                      return window.__realFetch(url, options);
                    }
                    return Promise.resolve(new Response(
                      JSON.stringify({
                        code: 'biomarker_projection_invalid',
                        error: 'Biomarker identity is missing or inconsistent.',
                      }),
                      { status: 422, headers: { 'Content-Type': 'application/json' } },
                    ));
                  };
                }"""
            )
            page.evaluate("() => loadBiomarkerSeries()")
            assert (
                "stored record could not be projected safely"
                in page.locator("#biomarker-status").inner_text()
            )
            assert "identity is missing" not in page.locator("#biomarker-explorer").inner_text()

            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (!String(url).includes('/api/patient/biomarker-series')) {
                      return window.__realFetch(url, options);
                    }
                    return Promise.resolve(new Response(
                      JSON.stringify({ error: 'internal secret detail' }),
                      { status: 500, headers: { 'Content-Type': 'application/json' } },
                    ));
                  };
                }"""
            )
            page.evaluate("() => loadBiomarkerSeries()")
            assert page.evaluate("() => biomarkerProjection") is None
            assert "internal secret detail" not in page.locator("#biomarker-explorer").inner_text()
            assert "internal secret detail" not in page.locator("#app-state-banner").inner_text()
        finally:
            context.close()
            browser.close()
