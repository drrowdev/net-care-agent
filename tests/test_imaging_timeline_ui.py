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


def _imaging_function_source() -> str:
    start = APP_JS.index("const IMAGING_MAX_RECORDS")
    end = APP_JS.index("// ── Status sidebar", start)
    return APP_JS[start:end]


def _record(
    record_id: str,
    token: str,
    date: str | None,
    *,
    precision: str = "day",
    kind: str = "study",
    modality: str | None = "CT",
    findings: str | None = "Exact stored finding",
    impression: str | None = "Exact stored impression",
    source_ref: str | None = None,
    evidence: bool = False,
    provenance_status: str = "source_unverified",
    provenance_label: str = "No exact source",
    source_document_date: str | None = None,
    source_document_date_precision: str = "unknown",
) -> dict:
    source_url = f"/api/patient/imaging-series/{source_ref}/source" if source_ref else None
    evidence_url = (
        f"/api/patient/imaging-series/{source_ref}/evidence" if source_ref and evidence else None
    )
    return {
        "id": record_id,
        "token": token,
        "date": {
            "value": date,
            "precision": precision,
            "kind": kind,
            "source_document_date": source_document_date,
            "source_document_date_precision": source_document_date_precision,
        },
        "modality": modality,
        "findings": findings,
        "impression": impression,
        "provenance": {
            "status": provenance_status,
            "label": provenance_label,
            "source_url": source_url,
            "evidence_url": evidence_url,
        },
    }


def _projection(
    token: str = "projection-current",
    *,
    profile_revision: int = 5,
    workflow_revision: int = 3,
    changed_suffix: str = "",
    include_all: bool = True,
) -> dict:
    records = [
        _record(
            "record-partial",
            f"row-partial-{token}",
            "2026-04",
            precision="month",
            kind="legacy_unknown",
            modality="MRI liver",
            findings=f"Stored partial-date wording{changed_suffix}",
            impression="Comparison is limited by motion artifact.",
            source_ref=f"imref_{'1' * 64}",
            source_document_date="2026-04-30",
            source_document_date_precision="day",
        ),
        _record(
            "record-duplicate-a",
            f"row-duplicate-a-{token}",
            "2026-03-15",
            findings="Target liver lesion increased from 2.1 cm to 3.0 cm.",
            impression="Consistent with progression.",
            source_ref=f"imref_{'2' * 64}",
            evidence=True,
            provenance_status="source_verified",
            provenance_label="Exact source",
        ),
        _record(
            "record-unknown",
            f"row-unknown-{token}",
            None,
            precision="unknown",
            kind="unknown",
            modality=None,
            findings=None,
            impression="Undated manual entry",
            provenance_status="unverified",
            provenance_label="Unverified",
        ),
        _record(
            "record-duplicate-b",
            f"row-duplicate-b-{token}",
            "2026-03-15",
            findings="Target liver lesion increased from 2.1 cm to 3.0 cm.",
            impression="Consistent with progression.",
            source_ref=f"imref_{'3' * 64}",
            provenance_status="caregiver_corrected_unverified",
            provenance_label="Caregiver-corrected · unverified",
        ),
    ]
    if not include_all:
        records = records[:2]
    return {
        "profile_revision": profile_revision,
        "workflow_revision": workflow_revision,
        "source_row_count": len(records),
        "projection_token": token,
        "records": records,
    }


def _node_prelude() -> str:
    return "\n".join(
        [
            """
class FakeClassList {
  constructor(node) { this.node = node; }
  _set() { return new Set(String(this.node.className || '').split(/\\s+/).filter(Boolean)); }
  add(...names) {
    const values = this._set();
    names.forEach(name => values.add(name));
    this.node.className = [...values].join(' ');
  }
  remove(...names) {
    const values = this._set();
    names.forEach(name => values.delete(name));
    this.node.className = [...values].join(' ');
  }
  toggle(name, force) {
    const values = this._set();
    const enabled = force == null ? !values.has(name) : Boolean(force);
    if (enabled) values.add(name); else values.delete(name);
    this.node.className = [...values].join(' ');
    return enabled;
  }
  contains(name) { return this._set().has(name); }
}
class FakeNode {
  constructor(tagName = 'div', id = '') {
    this.tagName = String(tagName).toUpperCase();
    this.id = id;
    this.className = '';
    this.classList = new FakeClassList(this);
    this.children = [];
    this.parentNode = null;
    this._text = '';
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.name = '';
    this.type = '';
    this.href = '';
    this.target = '';
    this.rel = '';
    this.colSpan = 1;
    this.listeners = {};
  }
  set textContent(value) {
    this.children = [];
    this._text = value == null ? '' : String(value);
  }
  get textContent() {
    return this._text + this.children.map(child => child.textContent || '').join('');
  }
  get childElementCount() {
    return this.children.filter(child => child.tagName !== '#TEXT').length;
  }
  append(...nodes) {
    for (const node of nodes) {
      const child = typeof node === 'string' ? new FakeNode('#text') : node;
      if (typeof node === 'string') child.textContent = node;
      if (!child) continue;
      if (child.parentNode) {
        child.parentNode.children = child.parentNode.children.filter(item => item !== child);
      }
      child.parentNode = this;
      this.children.push(child);
    }
  }
  replaceChildren(...nodes) {
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
    this._text = '';
    this.append(...nodes);
  }
  contains(node) {
    if (node === this) return true;
    return this.children.some(child => child.contains?.(node));
  }
  querySelector(selector) {
    const wanted = selector.toUpperCase();
    for (const child of this.children) {
      if (child.tagName === wanted) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
  querySelectorAll(selector) {
    const matches = [];
    const inputName = selector.match(/^input\\[name="([^"]+)"\\]$/);
    const tag = inputName ? null : selector.toUpperCase();
    for (const child of this.children) {
      if (
        (inputName && child.tagName === 'INPUT' && child.name === inputName[1])
        || (!inputName && child.tagName === tag)
      ) matches.push(child);
      matches.push(...(child.querySelectorAll?.(selector) || []));
    }
    return matches;
  }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  focus() { document.activeElement = this; }
  blur() { if (document.activeElement === this) document.activeElement = null; }
}
const elements = new Map();
const make = (id, tag = 'div') => {
  const node = new FakeNode(tag, id);
  elements.set(id, node);
  return node;
};
const explorer = make('imaging-explorer', 'section');
[
  ['imaging-freshness', 'span'],
  ['imaging-refresh-button', 'button'],
  ['imaging-summary', 'div'],
  ['imaging-status', 'div'],
  ['imaging-table-caption', 'caption'],
  ['imaging-table-region', 'div'],
  ['imaging-table-body', 'tbody'],
  ['imaging-selection-status', 'p'],
  ['imaging-clear-selection', 'button'],
  ['imaging-compare-button', 'button'],
  ['imaging-comparison', 'section'],
  ['imaging-comparison-grid', 'div'],
  ['imaging-comparison-heading', 'h3'],
  ['imaging-retry', 'div'],
].forEach(([id, tag]) => explorer.append(make(id, tag)));
elements.get('imaging-table-region').append(elements.get('imaging-table-body'));
elements.get('imaging-comparison').append(
  elements.get('imaging-comparison-heading'),
  elements.get('imaging-comparison-grid'),
);
elements.get('imaging-comparison').hidden = true;
make('nav-patient', 'button');
make('main-content', 'main');
const document = {
  baseURI: 'http://app.test/',
  activeElement: null,
  createElement(tag) { return new FakeNode(tag); },
  createTextNode(text) {
    const node = new FakeNode('#text');
    node.textContent = text;
    return node;
  },
  getElementById(id) { return elements.get(id) || null; },
  querySelectorAll(selector) { return explorer.querySelectorAll(selector); },
};
const window = {
  location: {
    origin: 'http://app.test',
    href: 'http://app.test/',
  },
};
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
let imagingProjection = null;
let imagingResponseOwner = null;
let selectedImagingRecordIds = [];
let comparedImagingRecordIds = [];
let imagingLoadEpoch = 0;
let imagingSelectionEpoch = 0;
let imagingComparisonEpoch = 0;
let imagingRequestController = null;
let imagingProjectionState = 'idle';
let imagingNetworkAmbiguous = false;
let biomarkerProjection = null;
let biomarkerRequestController = null;
let unrelatedPhi = 'kept';
const loadEvents = [];
function requestClinicalConvergence() {}
function markVisitRecapStale() {}
function markBiomarkerProjectionStale() {}
function loadBiomarkerSeries() {}
function advancePatientAuthority(revision, options = {}) {
  const normalized = normalizedRevision(revision);
  if (
    !Number.isSafeInteger(normalized)
    || (Number.isSafeInteger(normalizedRevision(latestProfileRevision))
      && normalized <= latestProfileRevision)
  ) return false;
  const hadImaging = imagingProjection !== null || imagingRequestController !== null;
  latestProfileRevision = normalized;
  phiEpoch += 1;
  if (hadImaging) {
    markImagingProjectionStale('Patient revision changed.', {
      abortRequest: options.preserveImagingRequest !== true,
      ownerPhiEpoch: phiEpoch,
    });
  }
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
  unrelatedPhi = 'cleared';
  clearImagingProjection({
    state: 'error',
    statusLabel: 'Patient data unavailable',
    message: `Imaging authority evicted (${error.status}).`,
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
            _imaging_function_source(),
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


def test_imaging_markup_is_shared_semantic_and_has_no_legacy_authority_path():
    start = INDEX_HTML.index('id="imaging-explorer"')
    end = INDEX_HTML.index('aria-labelledby="source-history-heading"', start)
    imaging_markup = INDEX_HTML[start:end].lower()

    assert INDEX_HTML.count('id="imaging-explorer"') == 1
    assert INDEX_HTML.count('id="imaging-table-region"') == 1
    assert 'role="region"' in imaging_markup
    assert 'aria-labelledby="imaging-table-caption"' in imaging_markup
    assert "<caption" in imaging_markup
    assert 'role="status" aria-live="polite"' in imaging_markup
    assert "compare selected records" in imaging_markup
    for forbidden in ("copy", "download", "print", "export", "chart", "image viewer"):
        assert forbidden not in imaging_markup

    patient_evidence = _function_source("renderPatientEvidence", "toggleSourceHistory")
    assert "patientEvidence.imaging" not in patient_evidence
    assert "imagingHistoryExpanded" not in APP_JS
    assert "/api/patient/imaging-series" in APP_JS
    assert "recent_imaging" not in APP_JS
    assert not re.search(r"(?:data|imagingProjection)\.records\.sort\(", _imaging_function_source())
    assert ".filter(record => selected.has(record.id))" in _imaging_function_source()
    assert "navigator.onLine" not in _imaging_function_source()
    retry = _function_source("retryInitialLoad", "switchView")
    assert "options.onlineRecovery !== true" in retry


def test_actual_imaging_validator_rendering_selection_and_safe_links():
    projection = _projection()
    unsafe = _projection("projection-unsafe")
    unsafe["records"][0]["provenance"]["source_url"] = (
        "https://evil.example/api/patient/imaging-series/" f"imref_{'1' * 64}/source"
    )
    query_link = _projection("projection-query")
    query_link["records"][0]["provenance"]["source_url"] += "?start=1"
    dangling = _projection("projection-dangling")
    dangling["records"][0]["provenance"]["source_url"] = None
    dangling["records"][0]["provenance"]["evidence_url"] = (
        f"/api/patient/imaging-series/imref_{'1' * 64}/evidence"
    )
    duplicate_id = _projection("projection-duplicate-id")
    duplicate_id["records"][1]["id"] = duplicate_id["records"][0]["id"]

    script = "\n".join(
        [
            _node_prelude(),
            f"const payload = {json.dumps(projection)};",
            f"const unsafe = {json.dumps(unsafe)};",
            f"const queryLink = {json.dumps(query_link)};",
            f"const dangling = {json.dumps(dangling)};",
            f"const duplicateId = {json.dumps(duplicate_id)};",
            """
latestProfileRevision = payload.profile_revision;
workflowRevision = payload.workflow_revision;
imagingLoadEpoch = 1;
imagingProjection = payload;
imagingProjectionState = 'current';
imagingResponseOwner = newImagingResponseOwner(payload);
const rendered = renderImagingProjection(imagingResponseOwner);
const tableText = document.getElementById('imaging-table-body').textContent;
const checkboxes = document.querySelectorAll('input[name="imaging-record-select"]');
selectImagingRecord(payload.records[0].id, true);
selectImagingRecord(payload.records[1].id, true);
const twoSelected = {
  selected: [...selectedImagingRecordIds],
  compareDisabled: document.getElementById('imaging-compare-button').disabled,
  uncheckedDisabled: checkboxes.slice(2).every(item => item.disabled),
};
const compared = compareSelectedImagingRecords();
const comparisonText = document.getElementById('imaging-comparison-grid').textContent;
document.getElementById('imaging-comparison-heading').focus();
selectImagingRecord(payload.records[0].id, false);
const afterChange = {
  hidden: document.getElementById('imaging-comparison').hidden,
  text: document.getElementById('imaging-comparison-grid').textContent,
  focus: document.activeElement?.id || null,
};
console.log(JSON.stringify({
  valid: imagingProjectionPayloadIsValid(payload),
  invalid: {
    unsafe: imagingProjectionPayloadIsValid(unsafe),
    query: imagingProjectionPayloadIsValid(queryLink),
    dangling: imagingProjectionPayloadIsValid(dangling),
    duplicateId: imagingProjectionPayloadIsValid(duplicateId),
  },
  rendered,
  tableText,
  rowCount: document.getElementById('imaging-table-body').children.length,
  checkboxCount: checkboxes.length,
  twoSelected,
  compared,
  comparisonText,
  comparisonHidden: document.getElementById('imaging-comparison').hidden,
  afterChange,
}));
""",
        ]
    )
    result = _run_node(script)

    assert result["valid"] is True
    assert result["invalid"] == {
        "unsafe": False,
        "query": False,
        "dangling": False,
        "duplicateId": False,
    }
    assert result["rendered"] is True
    assert result["rowCount"] == result["checkboxCount"] == 4
    assert result["tableText"].index("2026-04") < result["tableText"].index("2026-03-15")
    assert result["tableText"].count("Target liver lesion increased") == 2
    assert "Legacy date; study-date authority not confirmed" in result["tableText"]
    assert "Source document date (not used for study chronology)" in result["tableText"]
    assert "projection-current" not in result["tableText"]
    assert "row-partial-projection-current" not in result["tableText"]
    assert result["twoSelected"]["selected"] == [
        "record-partial",
        "record-duplicate-a",
    ]
    assert result["twoSelected"]["compareDisabled"] is False
    assert result["twoSelected"]["uncheckedDisabled"] is True
    assert result["compared"] is True
    assert "Findings (report wording)" in result["comparisonText"]
    assert "Consistent with progression." in result["comparisonText"]
    assert result["afterChange"] == {
        "hidden": True,
        "text": "",
        "focus": "imaging-table-region",
    }


def test_actual_imaging_loader_owns_races_replacement_failures_and_phi():
    late = _projection("projection-late", profile_revision=5, workflow_revision=2)
    fresh = _projection("projection-fresh", profile_revision=6, workflow_revision=3)
    replacement = _projection(
        "projection-replacement",
        profile_revision=6,
        workflow_revision=3,
        changed_suffix=" after correction",
    )
    missing_pair = _projection(
        "projection-missing-pair",
        profile_revision=6,
        workflow_revision=3,
        include_all=False,
    )
    recovered = _projection(
        "projection-recovered",
        profile_revision=7,
        workflow_revision=4,
    )
    script = "\n".join(
        [
            _node_prelude(),
            f"const latePayload = {json.dumps(late)};",
            f"const freshPayload = {json.dumps(fresh)};",
            f"const replacementPayload = {json.dumps(replacement)};",
            f"const missingPairPayload = {json.dumps(missing_pair)};",
            f"const recoveredPayload = {json.dumps(recovered)};",
            """
(async () => {
  let resolveLate;
  let fetchCount = 0;
  globalThis.fetch = async () => {
    fetchCount += 1;
    if (fetchCount === 1) {
      return new Promise(resolve => {
        resolveLate = () => resolve(response(200, latePayload));
      });
    }
    return response(200, freshPayload);
  };
  const lateLoad = loadImagingSeries();
  await Promise.resolve();
  const freshLoad = loadImagingSeries({ force: true });
  await freshLoad;
  resolveLate();
  await lateLoad;
  const afterRace = {
    token: imagingProjection?.projection_token,
    table: document.getElementById('imaging-table-body').textContent,
    owner: imagingResponseOwnerIsCurrent(),
    controllerCleared: imagingRequestController === null,
  };

  selectImagingRecord(freshPayload.records[0].id, true);
  selectImagingRecord(freshPayload.records[2].id, true);
  compareSelectedImagingRecords();
  globalThis.fetch = async () => response(200, replacementPayload);
  await loadImagingSeries({ force: true });
  const afterReplacement = {
    selected: [...selectedImagingRecordIds],
    compared: [...comparedImagingRecordIds],
    comparison: document.getElementById('imaging-comparison-grid').textContent,
  };

  globalThis.fetch = async () => response(200, missingPairPayload);
  await loadImagingSeries({ force: true });
  const afterMissing = {
    selected: [...selectedImagingRecordIds],
    compared: [...comparedImagingRecordIds],
    hidden: document.getElementById('imaging-comparison').hidden,
    comparison: document.getElementById('imaging-comparison-grid').textContent,
  };

  globalThis.fetch = async () => { throw new TypeError('SECRET transport'); };
  await loadImagingSeries({ force: true });
  const afterTransport = {
    token: imagingProjection?.projection_token,
    state: imagingProjectionState,
    ambiguous: imagingNetworkAmbiguous,
    unrelatedPhi,
    table: document.getElementById('imaging-table-body').textContent,
    status: document.getElementById('imaging-status').textContent,
  };

  globalThis.fetch = async () => response(500, { error: 'SECRET server body' });
  await loadImagingSeries({ force: true });
  const afterHard = {
    projection: imagingProjection,
    state: imagingProjectionState,
    unrelatedPhi,
    table: document.getElementById('imaging-table-body').textContent,
    status: document.getElementById('imaging-status').textContent,
  };

  globalThis.fetch = async () => response(200, recoveredPayload);
  await loadImagingSeries({ force: true });
  document.activeElement = document.getElementById('imaging-table-region');
  globalThis.fetch = async () => response(403, { error: 'SECRET denied body' });
  await loadImagingSeries({ force: true });
  const afterAuth = {
    projection: imagingProjection,
    owner: imagingResponseOwner,
    selected: [...selectedImagingRecordIds],
    compared: [...comparedImagingRecordIds],
    unrelatedPhi,
    table: document.getElementById('imaging-table-body').textContent,
    comparison: document.getElementById('imaging-comparison-grid').textContent,
    focus: document.activeElement?.id || null,
  };

  console.log(JSON.stringify({
    fetchCount,
    afterRace,
    afterReplacement,
    afterMissing,
    afterTransport,
    afterHard,
    afterAuth,
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
    assert "projection-late" not in result["afterRace"]["table"]
    assert result["afterRace"]["owner"] is True
    assert result["afterRace"]["controllerCleared"] is True
    assert result["afterReplacement"]["selected"] == [
        "record-partial",
        "record-unknown",
    ]
    assert result["afterReplacement"]["compared"] == [
        "record-partial",
        "record-unknown",
    ]
    assert "after correction" in result["afterReplacement"]["comparison"]
    assert result["afterMissing"] == {
        "selected": [],
        "compared": [],
        "hidden": True,
        "comparison": "",
    }
    assert result["afterTransport"]["token"] == "projection-missing-pair"
    assert result["afterTransport"]["state"] == "stale"
    assert result["afterTransport"]["ambiguous"] is True
    assert result["afterTransport"]["unrelatedPhi"] == "kept"
    assert "SECRET" not in result["afterTransport"]["status"]
    assert result["afterHard"]["projection"] is None
    assert result["afterHard"]["state"] == "error"
    assert result["afterHard"]["unrelatedPhi"] == "kept"
    assert "SECRET" not in result["afterHard"]["table"]
    assert "SECRET" not in result["afterHard"]["status"]
    assert result["afterAuth"]["projection"] is None
    assert result["afterAuth"]["owner"] is None
    assert result["afterAuth"]["selected"] == []
    assert result["afterAuth"]["compared"] == []
    assert result["afterAuth"]["unrelatedPhi"] == "cleared"
    assert result["afterAuth"]["comparison"] == ""
    assert result["afterAuth"]["focus"] == "nav-patient"


def test_actual_revision_authority_stales_both_revisions_and_skips_unchanged_fetch():
    projection = _projection(profile_revision=8, workflow_revision=5)
    script = "\n".join(
        [
            _node_prelude(),
            f"const payload = {json.dumps(projection)};",
            """
latestProfileRevision = payload.profile_revision;
workflowRevision = payload.workflow_revision;
imagingLoadEpoch = 1;
imagingProjection = payload;
imagingProjectionState = 'current';
imagingResponseOwner = newImagingResponseOwner(payload);
activeView = 'today';
let fetches = 0;
globalThis.fetch = async () => {
  fetches += 1;
  return response(200, payload);
};
(async () => {
  await ensureImagingSeries();
  await ensureImagingSeries();
  reportLoadError('tasks', new TypeError('unrelated failure'));
  const unchanged = {
    fetches,
    state: imagingProjectionState,
    token: imagingProjection.projection_token,
  };

  const profileAuthority = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: payload.profile_revision + 1,
    workflow_revision: payload.workflow_revision,
  });
  const profileChanged = {
    accepted: profileAuthority.accepted,
    state: imagingProjectionState,
    disabled: document.getElementById('imaging-compare-button').disabled,
    status: document.getElementById('imaging-status').textContent,
  };

  latestProfileRevision = payload.profile_revision + 1;
  workflowRevision = payload.workflow_revision;
  imagingLoadEpoch += 1;
  imagingProjection = {
    ...payload,
    profile_revision: payload.profile_revision + 1,
    projection_token: 'profile-current',
    records: payload.records.map((record, index) => ({
      ...record,
      token: `profile-row-${index}`,
    })),
  };
  imagingProjectionState = 'current';
  imagingResponseOwner = newImagingResponseOwner(imagingProjection);
  renderImagingProjection(imagingResponseOwner);
  const workflowAuthority = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: payload.profile_revision + 1,
    workflow_revision: payload.workflow_revision + 1,
  });
  const workflowChanged = {
    accepted: workflowAuthority.accepted,
    state: imagingProjectionState,
    disabled: document.getElementById('imaging-compare-button').disabled,
    status: document.getElementById('imaging-status').textContent,
  };
  console.log(JSON.stringify({ unchanged, profileChanged, workflowChanged }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    result = _run_node(script)

    assert result["unchanged"] == {
        "fetches": 0,
        "state": "current",
        "token": "projection-current",
    }
    assert result["profileChanged"]["accepted"] is True
    assert result["profileChanged"]["state"] == "stale"
    assert result["profileChanged"]["disabled"] is True
    assert "Patient revision changed" in result["profileChanged"]["status"]
    assert result["workflowChanged"]["accepted"] is True
    assert result["workflowChanged"]["state"] == "stale"
    assert result["workflowChanged"]["disabled"] is True
    assert "workflow changed" in result["workflowChanged"]["status"]


def test_actual_empty_imaging_projection_is_current_not_stale():
    projection = {
        "profile_revision": 4,
        "workflow_revision": 2,
        "source_row_count": 0,
        "projection_token": "projection-empty",
        "records": [],
    }
    script = "\n".join(
        [
            _node_prelude(),
            f"const payload = {json.dumps(projection)};",
            """
latestProfileRevision = payload.profile_revision;
workflowRevision = payload.workflow_revision;
imagingLoadEpoch = 1;
imagingProjection = payload;
imagingProjectionState = 'empty';
imagingResponseOwner = newImagingResponseOwner(payload);
const rendered = renderImagingProjection(imagingResponseOwner);
console.log(JSON.stringify({
  rendered,
  state: imagingProjectionState,
  freshness: document.getElementById('imaging-freshness').textContent,
  status: document.getElementById('imaging-status').textContent,
  selection: document.getElementById('imaging-selection-status').textContent,
  compareDisabled: document.getElementById('imaging-compare-button').disabled,
}));
""",
        ]
    )
    result = _run_node(script)

    assert result == {
        "rendered": True,
        "state": "empty",
        "freshness": "Current · empty",
        "status": (
            "Authoritative imaging loaded · patient revision 4 · " "no imaging records recorded."
        ),
        "selection": "No imaging records are available to select or compare.",
        "compareDisabled": True,
    }


def _standard_payloads(projection: dict) -> dict[str, object]:
    revision = projection["profile_revision"]
    workflow = projection["workflow_revision"]
    return {
        "/api/status": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "patient": {"diagnosis": "Status patient"},
            "stats": {},
            "alerts": [],
            "treatments_classified": [],
            "treatments_fallback": [],
            "imaging": [{"findings": "STATUS IMAGING MUST NOT RENDER"}],
        },
        "/api/patient/imaging-series": projection,
        "/api/patient/biomarker-series": {
            "profile_revision": revision,
            "workflow_revision": workflow,
            "projection_token": "biomarker-empty",
            "observation_count": 0,
            "source_row_count": 0,
            "analytes": [],
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
        "/api/symptoms": [],
        "/api/patient/evidence": {
            "imaging": [{"findings": "EVIDENCE IMAGING MUST NOT RENDER"}],
            "documents": [],
            "sources": [],
        },
    }


def _open_imaging_page(playwright, width: int, height: int, projection: dict):
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    browser = playwright.chromium.launch()
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    payloads = _standard_payloads(projection)
    request_counts: dict[str, int] = {}

    def fulfill(route):
        path = urlsplit(route.request.url).path
        request_counts[path] = request_counts.get(path, 0) + 1
        if path.endswith("/source") or path.endswith("/evidence"):
            route.fulfill(status=200, content_type="text/plain", body="Exact source text")
            return
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
    page.wait_for_function("() => imagingProjectionState === 'current'")
    return browser, context, page, payloads, request_counts


def test_live_imaging_is_exact_semantic_responsive_and_overflow_safe():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        for width, height in ((1280, 900), (360, 800)):
            browser, context, page, _, request_counts = _open_imaging_page(
                playwright,
                width,
                height,
                _projection(),
            )
            errors = []
            page.on("pageerror", lambda error, target=errors: target.append(str(error)))
            try:
                rows = page.locator("#imaging-table-body tr")
                assert rows.count() == 4
                dates = rows.locator("td:nth-child(2) > strong").all_inner_texts()
                assert dates == ["2026-04", "2026-03-15", "Not recorded", "2026-03-15"]
                table_text = page.locator("#imaging-table-body").inner_text()
                assert table_text.count("Target liver lesion increased") == 2
                assert "Legacy date; study-date authority not confirmed" in table_text
                assert "Study date not recorded" in table_text
                assert (
                    "STATUS IMAGING MUST NOT RENDER"
                    not in page.locator("#imaging-explorer").inner_text()
                )
                assert (
                    "EVIDENCE IMAGING MUST NOT RENDER"
                    not in page.locator("#imaging-explorer").inner_text()
                )
                assert request_counts["/api/patient/imaging-series"] == 1

                checkboxes = page.locator('#imaging-table-body input[name="imaging-record-select"]')
                checkboxes.nth(0).check()
                checkboxes.nth(1).check()
                assert page.locator("#imaging-compare-button").is_enabled()
                assert checkboxes.nth(2).is_disabled()
                page.locator("#imaging-compare-button").click()
                assert page.locator(".imaging-comparison-card").count() == 2
                comparison_text = page.locator("#imaging-comparison").inner_text()
                assert "Findings (report wording)" in comparison_text
                assert "Consistent with progression." in comparison_text
                assert "NET/Care does not infer a clinical conclusion" in comparison_text
                assert "Change detected" not in comparison_text
                assert "Better" not in comparison_text

                overflow = page.evaluate(
                    """() => {
                      const table = document.getElementById('imaging-table-region');
                      const columns = getComputedStyle(
                        document.getElementById('imaging-comparison-grid')
                      ).gridTemplateColumns.split(' ').filter(Boolean).length;
                      return {
                        document: document.documentElement.scrollWidth
                          - document.documentElement.clientWidth,
                        tableScrolls: table.scrollWidth > table.clientWidth,
                        columns,
                      };
                    }"""
                )
                assert overflow["document"] == 0
                assert overflow["tableScrolls"] is True
                assert overflow["columns"] == (1 if width == 360 else 2)

                page.locator("#imaging-table-region").focus()
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
                assert focus["id"] == "imaging-table-region"
                assert focus["outline"] != "none"
                assert focus["width"] >= 3

                if width == 360:
                    page.locator(".imaging-source-details summary").first.click()
                    heights = page.locator(
                        "#imaging-explorer button, "
                        ".imaging-select-label, "
                        ".imaging-source-details[open] a"
                    ).evaluate_all(
                        "items => items.filter(item => !item.hidden && item.offsetParent !== null)"
                        ".map(item => ({"
                        "tag: item.tagName, id: item.id, className: item.className,"
                        "height: item.getBoundingClientRect().height"
                        "}))"
                    )
                    assert heights
                    undersized = [item for item in heights if item["height"] < 44]
                    assert not undersized, undersized
                assert errors == []
            finally:
                context.close()
                browser.close()


def test_live_imaging_transport_recovery_hard_boundary_and_hidden_phi_scrub():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser, context, page, payloads, request_counts = _open_imaging_page(
            playwright,
            1280,
            900,
            _projection(),
        )
        try:
            page.locator('#imaging-table-body input[type="checkbox"]').nth(0).check()
            page.locator('#imaging-table-body input[type="checkbox"]').nth(1).check()
            page.locator("#imaging-compare-button").click()
            assert (
                "Stored partial-date wording"
                in page.locator("#imaging-comparison-grid").inner_text()
            )

            baseline = request_counts["/api/patient/imaging-series"]
            page.evaluate("() => ensureImagingSeries()")
            page.wait_for_timeout(50)
            assert request_counts["/api/patient/imaging-series"] == baseline
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_timeout(100)
            assert request_counts["/api/patient/imaging-series"] == baseline

            page.evaluate(
                """() => {
                  window.__realFetch = window.fetch.bind(window);
                  window.fetch = (url, options) => {
                    if (String(url).includes('/api/patient/imaging-series')) {
                      return Promise.reject(new TypeError('SECRET transport'));
                    }
                    return window.__realFetch(url, options);
                  };
                }"""
            )
            page.evaluate("() => loadImagingSeries({ force: true })")
            page.wait_for_function("() => imagingProjectionState === 'stale'")
            assert "Stale snapshot" in page.locator("#imaging-freshness").inner_text()
            assert (
                "Stored partial-date wording"
                in page.locator("#imaging-comparison-grid").inner_text()
            )
            assert page.locator("#imaging-compare-button").is_disabled()
            assert "SECRET" not in page.locator("#imaging-status").inner_text()

            recovered = _projection(
                "projection-browser-recovered",
                profile_revision=6,
                workflow_revision=4,
                changed_suffix=" recovered",
            )
            payloads["/api/patient/imaging-series"] = recovered
            payloads["/api/status"]["profile_revision"] = 6
            payloads["/api/status"]["workflow_revision"] = 4
            page.evaluate("() => { window.fetch = window.__realFetch; }")
            page.evaluate("() => window.dispatchEvent(new Event('online'))")
            page.wait_for_function(
                "() => imagingProjection?.projection_token === " "'projection-browser-recovered'"
            )
            assert page.locator("#imaging-freshness").inner_text() == "Current"
            assert "recovered" in page.locator("#imaging-comparison-grid").inner_text()

            page.locator("#imaging-comparison-heading").focus()
            page.evaluate(
                """() => {
                  window.fetch = (url, options) => {
                    if (!String(url).includes('/api/patient/imaging-series')) {
                      return window.__realFetch(url, options);
                    }
                    return Promise.resolve(new Response(
                      JSON.stringify({ error: 'SECRET hard body' }),
                      { status: 422, headers: { 'Content-Type': 'application/json' } },
                    ));
                  };
                }"""
            )
            page.evaluate("() => loadImagingSeries({ force: true })")
            page.wait_for_function("() => imagingProjectionState === 'corrupt'")
            assert page.evaluate("() => imagingProjection") is None
            assert page.locator("#imaging-comparison").is_hidden()
            assert page.locator("#imaging-comparison-grid").inner_text() == ""
            assert "SECRET" not in page.locator("#imaging-explorer").inner_text()
            assert page.locator("#patient-dx").inner_text() != "Patient data unavailable"
            assert page.evaluate("() => document.activeElement?.id") == "nav-patient"
        finally:
            context.close()
            browser.close()
