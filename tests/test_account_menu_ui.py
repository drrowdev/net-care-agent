"""Guard the header account control's copy through the real render function.

Sign-in is invisible here: the identity provider is the caregiver's own
Microsoft account, so Easy Auth completes the check silently and the app looks
unauthenticated even though it is not. This control is the only place the
session is named and the only way to end it, so what it says has to be true.
"""

from __future__ import annotations

import json

from tests._ui_render import function_source, run_node

_ACCOUNT = "care.giver@example.invalid"

_HARNESS = """
function fakeElement() {
  return {
    textContent: '',
    title: '',
    hidden: true,
    attributes: {},
    focus() {},
    setAttribute(name, value) { this.attributes[name] = value; },
    getAttribute(name) { return this.attributes[name] ?? null; },
  };
}

const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, fakeElement());
    return elements.get(id);
  },
  addEventListener() {},
};
"""

_READ = """
console.log(JSON.stringify({
  avatar: document.getElementById('account-avatar').textContent,
  label: document.getElementById('account-trigger-label').textContent,
  identity: document.getElementById('account-identity').textContent,
  note: document.getElementById('account-note').textContent,
  title: document.getElementById('account-trigger').title,
  expanded: document.getElementById('account-trigger').getAttribute('aria-expanded'),
  popoverHidden: document.getElementById('account-popover').hidden,
}));
"""


def _script(account: object, *, tail: str = "") -> str:
    return "\n".join(
        [
            _HARNESS,
            function_source("accountInitials", "renderAccountMenu"),
            function_source("renderAccountMenu", "clearAccountMenu"),
            function_source("clearAccountMenu", "toggleAccountMenu"),
            function_source("toggleAccountMenu", "toggleFeedPopover"),
            f"renderAccountMenu({json.dumps(account)});",
            tail,
            _READ,
        ]
    )


def _render(account: object) -> dict:
    return run_node(_script(account))


def _render_then_toggle(account: object, force: object) -> dict:
    return run_node(_script(account, tail=f"toggleAccountMenu({json.dumps(force)});"))


def test_the_signed_in_account_is_shown_exactly_as_the_platform_reported_it():
    """A rewritten address would be worse than none: he must recognise his own."""
    rendered = _render(_ACCOUNT)

    assert rendered["identity"] == _ACCOUNT
    assert _ACCOUNT in rendered["title"]
    assert _ACCOUNT in rendered["label"]


def test_the_avatar_carries_initials_a_caregiver_can_recognise_at_a_glance():
    """The chip is the persistent 'you are signed in' signal, so it must read."""
    assert _render(_ACCOUNT)["avatar"] == "cg"
    assert _render("first_last@example.invalid")["avatar"] == "fl"
    assert _render("solo@example.invalid")["avatar"] == "so"


def test_a_missing_account_name_never_invents_one():
    """Hosted responses can omit the name candidate; silence beats a wrong name."""
    for absent in (None, "", "   "):
        rendered = _render(absent)
        assert rendered["identity"] == "Signed in"
        assert rendered["avatar"] == "\u00b7"
        assert "not available" in rendered["note"]


def test_the_note_only_claims_a_verified_sign_in_when_an_account_was_named():
    """Reassurance without an identity is exactly the false comfort to avoid."""
    named = _render(_ACCOUNT)["note"]
    unnamed = _render(None)["note"]

    assert "Microsoft verified" in named
    assert "Microsoft verified" not in unnamed


def test_opening_the_menu_reveals_the_popover_and_reports_it_to_assistive_tech():
    opened = _render_then_toggle(_ACCOUNT, True)

    assert opened["popoverHidden"] is False
    assert opened["expanded"] == "true"


def test_closing_the_menu_hides_the_popover_again():
    closed = _render_then_toggle(_ACCOUNT, False)

    assert closed["popoverHidden"] is True
    assert closed["expanded"] == "false"


def test_losing_authorization_stops_the_chip_claiming_a_verified_session():
    """A stale name after a 401/403 is the exact false reassurance to avoid.

    `evictClientPhi` clears the browser's copy of the record; the header must
    stop asserting a live, verified sign-in at the same moment, or it goes on
    vouching for a session the server has already refused.
    """
    cleared = run_node(_script(_ACCOUNT, tail="clearAccountMenu();"))

    assert _ACCOUNT not in json.dumps(cleared)
    assert cleared["identity"] == "Session not confirmed"
    assert cleared["avatar"] == "\u00b7"
    assert "Microsoft verified" not in cleared["note"]
    assert "no longer has a confirmed sign-in" in cleared["note"]


def test_clearing_the_account_also_shuts_an_open_menu():
    """The popover names the account, so it must not survive the eviction."""
    cleared = run_node(
        _script(
            _ACCOUNT, tail="toggleAccountMenu(true); clearAccountMenu(); toggleAccountMenu(false);"
        )
    )

    assert cleared["popoverHidden"] is True
    assert cleared["expanded"] == "false"
