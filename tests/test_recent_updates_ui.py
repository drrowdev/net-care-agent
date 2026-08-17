"""What the Today "Recent updates" buttons actually open.

The card names one specific thing per row — "Latest document import", followed
by that import's own time and summary. Its button then called `switchView`
with no identifier, so it landed on the undifferentiated Activity list and the
caregiver had to find the import she had just been shown.

The identifier was available all along: `build_import_record` stamps the intake
job on the source document as `feed_job_id`, so document to job is an exact
stored lookup. `/api/status` now resolves it, and only offers it while that job
is still retained, because activity records are pruned by count and age while
the document they came from is kept.

These tests drive the real `renderRecentUpdates` in node against a fake DOM,
the same way `tests/test_summary_narrative_ui.py` drives `renderSummary`.
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


# A fake DOM small enough to read: it parses only the two data attributes the
# card renders, so the assertions are about the handler, not about HTML parsing.
_RECENT_UPDATES_HARNESS = """
const focusCalls = [];
const selectTaskCalls = [];
const switchViewCalls = [];
const deferred = [];

class FakeButton {
  constructor(dataset) {
    this.dataset = dataset;
    this.handlers = [];
  }
  addEventListener(type, handler) {
    if (type === 'click') this.handlers.push(handler);
  }
  click() { this.handlers.forEach(handler => handler()); }
}

const container = {
  buttons: [],
  html: '',
  set innerHTML(value) {
    this.html = value;
    // A browser decodes attribute entities before exposing dataset values.
    const decode = text => text
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, '&');
    this.buttons = [...value.matchAll(
      /data-update-view="([^"]*)"\\s+data-update-job="([^"]*)"/g
    )].map(match => new FakeButton({
      updateView: decode(match[1]),
      updateJob: decode(match[2]),
    }));
  },
  get innerHTML() { return this.html; },
  querySelectorAll() { return this.buttons; },
};

const elements = new Map();
const document = {
  getElementById(id) {
    if (id === 'recent-updates-list') return container;
    if (!elements.has(id)) {
      elements.set(id, { id, focus() { focusCalls.push(id); } });
    }
    return elements.get(id);
  },
};

function switchView(name) {
  switchViewCalls.push(name);
  // The real switchView focuses the destination nav when given no trigger.
  document.getElementById(`nav-${name}`).focus();
}
function selectTask(id, epoch, receipt, options) {
  selectTaskCalls.push({ id, options: options || null });
  return Promise.resolve(true);
}
function relativeTime(iso) { return `at ${iso}`; }
function enumLabel(value, fallback) { return value || fallback; }
function requestAnimationFrame(callback) { deferred.push(callback); }
function flushDeferred() {
  while (deferred.length) deferred.shift()();
}
"""


def _click_recent_update(status: dict, view: str) -> dict:
    """Render the card from one /api/status body and click one row's button."""
    script = "\n".join(
        [
            _RECENT_UPDATES_HARNESS,
            _function_source("escHtml", "fmtDate"),
            _function_source("renderRecentUpdates", "renderSidebar"),
            f"renderRecentUpdates({json.dumps(status)});",
            f"const target = container.buttons.find(b => b.dataset.updateView === {json.dumps(view)});",
            "target.click();",
            "flushDeferred();",
            "console.log(JSON.stringify({",
            "  html: container.html,",
            "  switchViewCalls,",
            "  selectTaskCalls,",
            "  focusCalls,",
            "}));",
        ]
    )
    return _run_node(script)


def _status(**overrides) -> dict:
    status = {
        "latest_document_import": {
            "added_at": "2026-08-12T10:00:00",
            "date": "2026-08-10",
            "type": "lab_result",
            "summary": "Bloods from the August visit.",
            "job_id": "job-feed-1",
        },
        "latest_research_update": {"completed_at": "2026-08-11T09:00:00", "trigger": "digest"},
        "alerts": [],
    }
    status.update(overrides)
    return status


def test_the_import_row_opens_the_import_it_names_not_the_default_list():
    result = _click_recent_update(_status(), "activity")

    assert result["switchViewCalls"] == ["activity"]
    assert result["selectTaskCalls"] == [
        {"id": "job-feed-1", "options": {"missingIsExpected": True}}
    ]


def test_opening_the_detail_leaves_focus_to_the_panel_not_the_inert_nav():
    """The nav goes inert the moment the report panel opens (see PR #60).

    switchView still moves focus there first, so it is what the panel records
    as the control to return to, but nothing may focus it again afterwards.
    """
    result = _click_recent_update(_status(), "activity")

    assert result["focusCalls"] == ["nav-activity"]


def test_a_pruned_import_still_navigates_the_old_way():
    """No identifier means retention removed the job; the list is the honest
    destination, and the deferred nav focus that has always run must survive."""
    result = _click_recent_update(
        _status(
            latest_document_import={
                "added_at": "2026-08-12T10:00:00",
                "type": "lab_result",
                "summary": "Bloods from the August visit.",
            }
        ),
        "activity",
    )

    assert result["switchViewCalls"] == ["activity"]
    assert result["selectTaskCalls"] == []
    assert result["focusCalls"] == ["nav-activity", "nav-activity"]


def test_no_import_at_all_still_renders_a_working_row():
    result = _click_recent_update(_status(latest_document_import=None), "activity")

    assert result["selectTaskCalls"] == []
    assert result["switchViewCalls"] == ["activity"]
    assert "No import time is available." in result["html"]


def test_the_sibling_rows_keep_their_own_destinations():
    """Alerts are a list, and Open Research promises the research workspace
    rather than one run's job log. Neither row changes."""
    for view in ("research", "patient"):
        result = _click_recent_update(_status(), view)
        assert result["switchViewCalls"] == [view]
        assert result["selectTaskCalls"] == []


def test_the_button_keeps_its_visible_text_as_its_accessible_name():
    result = _click_recent_update(_status(), "activity")

    assert 'type="button" data-update-view="activity"' in result["html"]
    assert ">Open Activity</button>" in result["html"]
    assert "aria-label" not in result["html"]


def test_a_hostile_job_identifier_cannot_break_out_of_the_attribute():
    result = _click_recent_update(
        _status(
            latest_document_import={
                "added_at": "2026-08-12T10:00:00",
                "summary": "Bloods",
                "job_id": '"><img src=x onerror=alert(1)>',
            }
        ),
        "activity",
    )

    assert "<img src=x" not in result["html"]
    assert "&quot;&gt;&lt;img src=x" in result["html"]
    assert result["selectTaskCalls"] == [
        {"id": '"><img src=x onerror=alert(1)>', "options": {"missingIsExpected": True}}
    ]


def test_a_non_string_job_identifier_is_ignored_rather_than_stringified():
    result = _click_recent_update(
        _status(
            latest_document_import={
                "added_at": "2026-08-12T10:00:00",
                "summary": "Bloods",
                "job_id": 17,
            }
        ),
        "activity",
    )

    assert result["selectTaskCalls"] == []


def test_a_missing_activity_record_is_an_expected_outcome_not_an_eviction():
    """Retention can remove the job between the render and the click.

    That path must not run the authorization eviction the ordinary missing-task
    branch runs; it closes the panel and explains itself instead.
    """
    selection = APP_JS[
        APP_JS.index("async function selectTask") : APP_JS.index("function formatReport")
    ]
    expected = selection[
        selection.index("if (options.missingIsExpected)") : selection.index("const missingError")
    ]
    assert "closePanel()" in expected
    assert "setActivityNotice(" in expected
    assert "evictClientPhi" not in expected
    # The ordinary path is untouched: a task that vanished under a direct click
    # is still treated as a record-access failure.
    assert "evictClientPhi(missingError)" in selection


def test_the_retention_message_names_what_is_and_is_not_gone():
    selection = APP_JS[
        APP_JS.index("async function selectTask") : APP_JS.index("function formatReport")
    ]
    assert "The activity record for that import is no longer kept" in selection
    assert "The document itself and everything imported from it are unchanged." in selection


def test_the_notice_region_announces_politely_and_is_hidden_when_empty():
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<p class="activity-notice" id="activity-notice" role="status" hidden></p>' in html
    notice = _function_source("setActivityNotice", "selectTask")
    assert "notice.textContent = message" in notice
    assert "notice.hidden = !message" in notice
