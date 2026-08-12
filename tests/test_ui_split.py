"""
Phase 4 UI hygiene checks: cache headers + static asset split integrity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HTML = Path("static/index.html").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")


def test_index_html_references_split_assets():
    """index.html should link to extracted styles.css and app.js, no inline blocks."""
    assert '<link rel="stylesheet" href="/static/styles.css">' in HTML
    assert '<script defer src="/static/app.js"></script>' in HTML
    # No leftover inline <style> or <script> blocks (other than the link/script tags).
    assert "<style>" not in HTML, "inline <style> survived the split"
    # A bare <script> tag (not the external one) would mean inline JS leaked through.
    assert not re.search(r"<script(?!\s+defer\s+src=)", HTML), "inline <script> survived"


def test_extracted_assets_exist_and_nonempty():
    css = Path("static/styles.css")
    js = Path("static/app.js")
    assert css.exists() and css.stat().st_size > 10_000
    assert js.exists() and js.stat().st_size > 10_000


def test_ui_uses_one_shared_responsive_workspace():
    for view in ("today", "patient", "questions", "activity"):
        assert f'id="view-{view}"' in HTML
        assert f'id="nav-{view}"' in HTML
    assert HTML.count("<main") == 1
    assert "mob-panel" not in HTML
    assert "mob-" not in HTML
    assert ".view-nav {" in CSS
    assert "position: fixed;" in CSS
    assert "env(safe-area-inset-bottom)" in CSS
    assert "aside, .panel { display: none !important; }" not in CSS


def test_primary_states_and_dialogs_are_accessible():
    assert 'id="app-state-banner" class="app-state-banner" role="alert"' in HTML
    assert 'role="dialog" aria-modal="true" aria-labelledby="feed-title"' in HTML
    assert 'role="tablist" aria-label="Document input method"' in HTML
    assert 'id="summary-toggle" aria-controls="summary-body" aria-expanded="true"' in HTML
    assert 'aria-label="Primary"' in HTML
    assert 'class="skip-link"' in HTML
    assert (
        'id="appointment-dialog" role="dialog" aria-modal="true" '
        'aria-labelledby="appointment-dialog-title"'
    ) in HTML
    assert ('role="tablist" aria-label="Appointment workspace sections"') in HTML
    for name in ("questions", "decisions", "followups"):
        assert f'id="appointment-tab-{name}"' in HTML
        assert f'id="appointment-panel-{name}"' in HTML
        assert f'aria-controls="appointment-panel-{name}"' in HTML
        assert f'aria-labelledby="appointment-tab-{name}"' in HTML


def test_research_uses_shared_today_and_complete_workspace():
    assert 'id="research-today-card"' in HTML
    assert 'id="view-research"' in HTML
    assert 'id="research-panel-current"' in HTML
    assert 'id="research-panel-considerations"' in HTML
    assert "openModal(" not in HTML
    assert "changes-overlay" not in HTML
    assert "Mark reviewed" not in HTML


def test_patient_has_authoritative_imaging_and_source_history():
    assert HTML.count('id="imaging-explorer"') == 1
    assert HTML.count('id="imaging-table-region"') == 1
    assert 'id="imaging-comparison"' in HTML
    assert "Compare selected records" in HTML
    assert 'id="source-history"' in HTML
    assert "Recorded imaging reports" in HTML
    assert "Loading source history" in HTML
    assert "imaging-table-region" in CSS
    assert "imaging-comparison-grid" in CSS
    assert "source-history-row" in CSS


def test_empty_submission_controls_have_inline_errors_and_disabled_defaults():
    for button_id in (
        "btn-feed",
        "q-add-btn",
        "judgment-add-btn",
        "symptom-details-submit",
        "chat-send-btn",
        "visit-create-submit",
        "visit-manual-question-submit",
        "visit-decision-submit",
        "visit-followup-submit",
    ):
        assert re.search(rf'id="{button_id}"[^>]*disabled', HTML)
    for error_id in (
        "feed-form-error",
        "q-form-error",
        "judgment-form-error",
        "symptom-details-error",
        "chat-form-error",
        "visit-create-error",
        "visit-details-error",
        "visit-question-error",
        "visit-decision-error",
        "visit-followup-error",
    ):
        assert f'id="{error_id}"' in HTML
        assert 'aria-live="polite"' in HTML


def test_mobile_controls_and_overflow_guards_are_explicit():
    assert ".header-actions .button {" in CSS
    assert "min-width: 44px;" in CSS
    assert "min-height: 44px;" in CSS
    assert ".judgment-action {" in CSS
    assert ".modal-close { min-width: 44px; min-height: 44px; }" in CSS
    assert "overflow-x: hidden;" in CSS
    assert "overflow-wrap: anywhere;" in CSS
    assert ".appointment-dialog {" in CSS
    assert "width: 100vw;" in CSS
    assert "height: 100dvh;" in CSS
    assert ".visit-answer { grid-template-columns: 1fr;" in CSS
    assert ".visit-form-grid.compact { grid-template-columns: 1fr;" in CSS
    assert ".appointment-tab { flex: 1;" in CSS
    assert re.search(
        r"\.visit-question-order \.button \{[^}]*min-height: 44px;",
        CSS,
        re.DOTALL,
    )
    assert ".visit-question-order select { min-height: 44px; }" in CSS
    assert "font-size: 9px" not in CSS
    assert "font-size: 10px" not in CSS
    assert "--text2: #625d56;" in CSS
    assert ".mob-nav" not in CSS


def test_questions_view_contains_one_shared_appointment_workspace():
    assert 'id="appointment-prep-heading">Appointment workspace</h2>' in HTML
    assert 'id="visit-list"' in HTML
    assert 'id="visit-source-appointment"' in HTML
    assert 'id="appointment-overlay"' in HTML
    assert HTML.count('id="appointment-dialog"') == 1
    assert "mob-appointment" not in HTML
    assert "You recorded this from the clinician" in HTML
    assert HTML.count('id="appointment-tab-recap"') == 1
    assert HTML.count('id="appointment-panel-recap"') == 1


def test_today_order_and_visible_appointments_label_preserve_internal_route():
    today = HTML[HTML.index('id="view-today"') : HTML.index('id="view-patient"')]
    ordered_ids = [
        'id="freshness-banner"',
        'id="summary-card"',
        'id="recent-updates-card"',
        'id="treatment-today-card"',
        'id="symptom-today-card"',
        'aria-labelledby="follow-through-heading"',
        'id="today-appointment-card"',
        'id="research-today-card"',
        'class="clinical-disclaimer"',
    ]
    positions = [today.index(value) for value in ordered_ids]
    assert positions == sorted(positions)
    assert 'id="nav-questions"' in HTML
    assert "<span>Appointments</span>" in HTML
    assert 'id="questions-heading">Appointments</h1>' in HTML
    assert "switchView('questions'" in HTML
    assert 'id="appointment-tab-questions"' in HTML


def test_appointment_controls_are_keyboard_and_phone_accessible():
    assert 'onkeydown="handleAppointmentTabKeydown(event)"' in HTML
    assert 'onclick="closeAppointmentFromBackdrop(event)"' in HTML
    assert 'tabindex="-1"' in HTML
    assert ".appointment-tab {" in CSS
    assert "min-height: 44px;" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS
    assert "overflow-y: auto;" in CSS
    assert "overflow-wrap: anywhere;" in CSS


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-used")
    import importlib

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config["TESTING"] = True
    with app_mod.app.test_client() as c:
        yield c


def test_static_assets_get_short_cache(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert "max-age=300" in r.headers.get("Cache-Control", "")


def test_api_responses_are_no_store(client):
    r = client.get("/api/health")
    assert r.status_code in (200, 503)
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_index_route_serves_split_html(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "/static/styles.css" in body
    assert "/static/app.js" in body
    assert "no-store" in r.headers.get("Cache-Control", "")
