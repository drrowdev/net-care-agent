"""Run real render functions from `static/app.js` under Node.

`static/app.js` is a single browser script with no module boundary, so a test
cannot import one function from it. These helpers slice a function out by name
and run it under Node with a small fake DOM, which is how the existing UI tests
work. Sharing the summary harness keeps the date guard and the narrative guard
exercising the same code path instead of drifting apart.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from tests._copy_scan import strip_markup

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"

# The caregiver's zone. Pinned so expected strings are reproducible anywhere and
# so a value read in the wrong zone shows up as a failure rather than as flake.
DISPLAY_TIMEZONE = "Europe/Helsinki"


def function_source(name: str, next_name: str) -> str:
    """Return the text of `function name` up to `function next_name`."""
    start = APP_JS.index(f"function {name}")
    end = APP_JS.index(f"function {next_name}", start)
    return APP_JS[start:end]


def run_node(script: str, *, timezone: str = DISPLAY_TIMEZONE) -> dict:
    completed = subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, TZ=timezone),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


SUMMARY_HARNESS = """
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


def _summary_script(summary: dict, *, today: str | None = None) -> str:
    # `renderSummary` reads today's date through `localDateIso`, which lives far
    # from the functions under test. Pinning it keeps past/upcoming assertions
    # stable regardless of when the suite runs.
    clock = (
        f"function localDateIso() {{ return {json.dumps(today)}; }}"
        if today
        else function_source("localDateIso", "dueDatePresentation")
    )
    return "\n".join(
        [
            SUMMARY_HARNESS,
            function_source("safeClassToken", "safeExternalUrl"),
            function_source("escHtml", "fmtDate"),
            function_source("fmtDate", "copyReport"),
            clock,
            function_source("summaryActionIsCurrent", "generatedActionAccepted"),
            function_source("renderClaimEvidence", "renderSummary"),
            function_source("renderSummary", "researchPlainObject"),
            f"renderSummary({json.dumps(summary)});",
            "console.log(JSON.stringify({",
            "  body: document.getElementById('summary-body').innerHTML,",
            "  updated: document.getElementById('summary-updated').textContent,",
            "}));",
        ]
    )


def render_summary(summary: dict, *, today: str | None = None) -> dict:
    """Render a whole assessment through the real `renderSummary`."""
    return run_node(_summary_script(summary, today=today))


# ── reading what he can actually see ─────────────────────────────────────────

# `strip_markup` already knows the difference between plumbing and copy: it
# drops tags but keeps the attributes a screen reader speaks, which is exactly
# the boundary this guard needs. A date hidden in an `aria-label` is still a
# date he is read out, so it must not escape the check.
#
# `<time datetime>` is the one deliberate exception. It is the machine-readable
# half of the element by definition, it is never spoken in place of the text,
# and HTML requires it to be a valid date string. It is removed before the
# check so the element can keep doing its job.
_TIME_MACHINE_VALUE = re.compile(r"""\sdatetime\s*=\s*(?:"[^"]*"|'[^']*')""")

# A bare machine date anywhere in text he reads. Bounded so a longer digit run
# or an identifier fragment is not mistaken for one.
BARE_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}(?:-\d{2})?(?!\d)")


def visible_text(html: str) -> str:
    """Strip markup, leaving the words and the accessible names he receives."""
    return strip_markup(_TIME_MACHINE_VALUE.sub(" ", html))


def bare_iso_dates(html: str) -> list[str]:
    """Every machine date that survives into readable text."""
    return BARE_ISO_DATE.findall(visible_text(html))
