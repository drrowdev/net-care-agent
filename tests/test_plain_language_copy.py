"""Plain-language contracts for the copy the caregiver actually reads.

He is not a clinician and not a developer, and he reads this on bad days. The
copy audit turned a set of wording decisions into code changes; these tests pin
them so a regression back to stored codes, machine date notation, or the word
"terminal" in an oncology app fails loudly rather than quietly.

Every assertion here is about presentation only. Wire field names, element ids,
stored enum values and error reason codes are deliberately untouched, and some
assertions below prove that by pinning both sides at once.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
INDEX_HTML = Path("static/index.html").read_text(encoding="utf-8")
APP_PY = Path("app.py").read_text(encoding="utf-8")
TREATMENT_PY = Path("agent/treatment_reconciliation.py").read_text(encoding="utf-8")
RESEARCH_PY = Path("agent/research_disposition.py").read_text(encoding="utf-8")
FOLLOW_THROUGH_PY = Path("agent/follow_through.py").read_text(encoding="utf-8")
RECONCILIATION_PY = Path("agent/reconciliation.py").read_text(encoding="utf-8")
DATE_INPUT_PY = Path("agent/date_input.py").read_text(encoding="utf-8")

_NODE_STDIN_BOOTSTRAP = "eval(require('fs').readFileSync(0,'utf8'))"


def _slice(start_marker: str, end_marker: str) -> str:
    start = APP_JS.index(start_marker)
    end = APP_JS.index(end_marker, start)
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


# ── "terminal" is a prognosis word in an oncology app ────────────────────────


def test_the_word_terminal_never_reaches_the_caregiver():
    """The code means "end state"; he reads a sentence about his wife."""
    banned_display_wording = [
        "Neutral terminal outcome",
        "Recorded terminal outcome",
        "Record terminal outcome",
        "Other recorded outcome",
        "Ended after it had started",
        "Plan cancelled before starting",
        "Ending detail not recorded",
        "server-authorized terminal outcome",
    ]
    for phrase in banned_display_wording:
        assert phrase not in APP_JS, f"user-facing wording still says: {phrase}"

    banned_backend_messages = [
        "cannot have terminal authority",
        "terminal_qualifier must be one of",
        "terminal_detail is required",
        "terminal_detail is too long",
        "terminal_detail contains",
        "terminal_detail is only allowed",
        "terminal authority is inconsistent",
    ]
    for phrase in banned_backend_messages:
        assert phrase not in TREATMENT_PY, f"API message still says: {phrase}"


def test_the_replacement_end_of_treatment_vocabulary_is_coherent():
    """Heading, field, options, detail, button and error read as one voice."""
    for phrase in [
        "'How did this treatment end?'",
        "'How it ended'",
        "'Record how it ended'",
        "'It started and then stopped'",
        "'It never started'",
        "'The plan was cancelled before it started'",
        "'Something else'",
        "'How it ended was not recorded'",
        "'More detail about how it ended'",
        "'Choose how it ended'",
        "'Choose how the treatment ended.'",
    ]:
        assert phrase in APP_JS, f"missing replacement wording: {phrase}"

    assert "Only a past treatment record can say how it ended." in TREATMENT_PY
    assert "Choose how the treatment ended from the listed options." in TREATMENT_PY


def test_stored_end_of_treatment_codes_are_unchanged():
    """Only the words changed. The wire contract must not have moved."""
    for key in ["ended:", "not_started:", "cancelled:", "other:", "legacy_unspecified:"]:
        assert key in APP_JS
    for wire_name in ["terminal_qualifier", "terminal_detail"]:
        assert wire_name in APP_JS
        assert wire_name in TREATMENT_PY
    # The bounded PHI-free reason code survives the message rewrite.
    assert '"treatment_projection_invalid"' in TREATMENT_PY


# ── machine date notation ────────────────────────────────────────────────────


def test_no_user_facing_copy_instructs_in_machine_date_notation():
    """The record displays 14.8.2026, so YYYY-MM-DD only belongs in code."""
    assert "YYYY" not in INDEX_HTML

    for number, line in enumerate(APP_JS.splitlines(), start=1):
        if "YYYY" in line:
            assert line.lstrip().startswith("//"), (
                f"static/app.js:{number} shows machine date notation to the "
                f"caregiver: {line.strip()}"
            )


def test_api_date_messages_do_not_use_machine_notation_or_leak_field_plumbing():
    banned = [
        "must be a YYYY",
        "must be a valid YYYY",
        "must be YYYY-MM-DD",
        "must use YYYY",
        "Date must be YYYY",
        "occurred_on must be",
    ]
    for source, name in [
        (APP_PY, "app.py"),
        (FOLLOW_THROUGH_PY, "agent/follow_through.py"),
        (RECONCILIATION_PY, "agent/reconciliation.py"),
        (RESEARCH_PY, "agent/research_disposition.py"),
        (DATE_INPUT_PY, "agent/date_input.py"),
    ]:
        for phrase in banned:
            assert phrase not in source, f"{name} still says: {phrase}"

    # Every rejected date is answered with one shared sentence, so the wording
    # is asserted where it now lives rather than at each endpoint.
    # "null" is developer vocabulary; he is told to leave the field empty.
    assert "or leave it empty" in DATE_INPUT_PY
    assert "14.8.2026" in DATE_INPUT_PY
    assert "YYYY" not in DATE_INPUT_PY


def test_the_eight_leaking_date_sites_now_use_the_shared_finnish_formatter():
    """The old guard covered three functions, which is how these slipped through."""
    biomarker = _slice("function biomarkerScalar", "function biomarkerProjectionPayloadIsValid")
    assert "function biomarkerDate" in biomarker
    assert "fmtDate(String(value))" in biomarker

    imaging = _slice("function imagingScalar", "function setImagingFreshness")
    assert "function imagingDate" in imaging
    assert "fmtDate(String(value))" in imaging

    course = _slice("function treatmentDatePresentation", "function treatmentCourseById")
    assert "fmtDate(String(value))" in course
    assert "${value === null ? 'Not recorded' : value}" not in course

    symptom = _slice("function symptomScalar", "function symptomSeverityPresentation")
    assert "function symptomDate" in symptom
    assert "${symptomDate(date.value)}" in symptom

    # The symptom source-document date and follow-up due date sit outside the
    # helper block and were the two easiest siblings to miss.
    assert "symptomDate(observation.date.source_document_date)" in APP_JS
    assert "symptomScalar(observation.date.source_document_date)" not in APP_JS
    assert "due ${symptomDate(episode.follow_up.due_date)}" in APP_JS

    recap = _slice("function buildVisitRecapText", "function recapSectionMarkup")
    assert "fmtDate(visit.date)" in recap
    assert "['Date', visit.date]," not in recap
    assert "fmtDate(item.due_date)" in recap

    assert "fmtDate(event.occurred_on)" in APP_JS
    assert ": event.occurred_on)}" not in APP_JS
    assert "fmtDate(discrepancy.follow_up.due_date)" in APP_JS


# ── stored codes must not be dressed up as labels ────────────────────────────


def test_stored_codes_are_never_title_cased_into_fake_labels():
    """`caregiver_record_corrected` must not reach the screen as a "label"."""
    helpers = _slice("const ENUM_LABELS", "function revisionIsOlder")
    assert "replaceAll('_', ' ')" not in helpers

    result = _run_node(
        helpers
        + """
process.stdout.write(JSON.stringify({
  known: enumLabel('caregiver_record_corrected'),
  clarify: enumLabel('source_clarification_needed'),
  status: enumLabel('in_progress'),
  trigger: enumLabel('digest', 'Research update'),
  unknownCode: enumLabel('some_unmapped_internal_code'),
  freeText: enumLabel('H'),
  underscoreFreeText: enumLabel('POST_DOSE'),
  blank: enumLabel(''),
}));
"""
    )
    assert result["known"] == "You corrected the record"
    assert result["clarify"] == "Needs checking with the treating team"
    assert result["status"] == "In progress"
    assert result["trigger"] == "Digest"
    assert result["blank"] == "Not recorded"
    # An unmapped value is shown exactly as recorded. It is never re-cased into
    # something that only looks like a label, and never replaced by "Not
    # recorded", which would be a false statement about what the document said.
    assert result["unknownCode"] == "some_unmapped_internal_code"
    assert result["unknownCode"] != "Some Unmapped Internal Code"
    assert result["freeText"] == "H"
    assert result["underscoreFreeText"] == "POST_DOSE"


def test_the_timeline_uses_the_vocabulary_the_summary_actually_produces():
    """agent/exec_summary.py:60 emits appointment|scan|test|milestone|trial|deadline."""
    result = _run_node(
        _slice("const ENUM_LABELS", "function revisionIsOlder")
        + """
process.stdout.write(JSON.stringify({
  milestone: translateType('milestone'),
  deadline: translateType('deadline'),
  trial: translateType('trial'),
  appointment: translateType('appointment'),
  scan: translateType('scan'),
  test: translateType('test'),
  unknown: translateType('not_a_real_type'),
}));
"""
    )
    assert result == {
        "milestone": "Milestone",
        "deadline": "Deadline",
        "trial": "Trial",
        "appointment": "Appointment",
        "scan": "Scan",
        "test": "Test",
        "unknown": "Event",
    }


def test_plain_display_words_are_not_routed_through_the_code_lookup():
    """The activity cards read "Result expired", not "result expired"."""
    markup = _slice("function artifactStateMarkup", "function staleReportMarkup")
    assert "${Noun} expired" in markup
    assert "${Noun} not retained" in markup
    assert "${Noun} unavailable" in markup
    assert "enumLabel(noun)" not in markup


def test_label_helpers_are_no_longer_identity_stubs():
    localisation = _slice("// ── UI label localization", "// ── Formatting helpers")
    assert "return cat;" not in localisation
    assert "return t;" not in localisation
    assert "QUESTION_CATEGORY_LABELS" in localisation
    assert "TIMELINE_TYPE_LABELS" in localisation


def test_blank_values_are_described_in_words_not_in_database_terms():
    """The three summary scalar helpers stopped speaking in database terms.

    The forensic "exact stored value" displays in the treatment differences and
    research tabs still distinguish a stored null from a stored empty string on
    purpose, so they are deliberately left for a later pass.
    """
    for start, end in [
        ("function biomarkerScalar", "function biomarkerProjectionPayloadIsValid"),
        ("function imagingScalar", "function setImagingFreshness"),
        ("function symptomScalar", "function symptomSeverityPresentation"),
    ]:
        helper = _slice(start, end)
        assert 'Empty string ("")' not in helper
        assert "Empty string recorded" not in helper
        assert "'Recorded as blank'" in helper


# ── safety meanings must survive the rewrite ─────────────────────────────────


def test_the_assessment_pill_stays_the_assessments_own_language():
    """INVARIANTS.md:153 - NET/Care never decides progression itself."""
    assert "'PROGRESSING'" not in APP_JS
    assert "progressing: 'Assessment: progression'" in APP_JS
    assert "stable: 'Assessment: stable'" in APP_JS
    assert "insufficient_data: 'Assessment pending'" in APP_JS
    # All four read the same way. Hedging only the adverse status would soften
    # bad news and conflate overall_status with the separate status_confidence.
    assert "possible progression" not in APP_JS
    # The raw stored status must not be used as a display fallback.
    assert "statusLabels[d.overall_status] || d.overall_status" not in APP_JS


def test_the_chat_panel_does_not_offer_to_triage_or_advise():
    assert "What are the most urgent actions right now?" not in APP_JS
    assert "or treatment options." not in APP_JS
    assert "This is not medical advice." in APP_JS


def test_the_app_never_claims_it_verified_treatment_or_research():
    assert "Treatment reconciliation saved and verified." not in APP_JS
    assert "Saved and verified against the complete authoritative research workspace." not in APP_JS
    assert "'Treatment changes saved.'" in APP_JS


def test_the_pinned_safety_paragraphs_are_untouched_by_this_wave():
    """Wave 1 changed no byte of the fixed safety paragraphs.

    Rewording these needs their pinning tests and INVARIANTS.md updated in the
    same commit, so they are deliberately left for a later pass.
    """
    from agent.research_disposition import RESEARCH_SAFETY_GUIDANCE
    from agent.treatment_reconciliation import TREATMENT_SAFETY_GUIDANCE

    assert TREATMENT_SAFETY_GUIDANCE == (
        "NET/Care records what you enter but does not verify treatment details or "
        "advise starting, stopping, or changing treatment. Confirm treatment "
        "decisions with the treating team."
    )
    assert RESEARCH_SAFETY_GUIDANCE == (
        "NET/Care records research you choose to follow but does not determine "
        "relevance, eligibility, enrollment, or treatment suitability. Confirm "
        "clinical questions with the treating team and trial details with the "
        "study site."
    )


def test_the_caregiver_entered_and_unverified_distinction_survives():
    """INVARIANTS.md:231-233 - attribution wording is load-bearing."""
    for label in [
        "Caregiver-entered \u00b7 unverified",
        "Caregiver-entered \u00b7 attributed to clinician \u00b7 unverified",
        "Caregiver-entered \u00b7 attributed to trial site \u00b7 unverified",
    ]:
        assert label in APP_JS, f"attribution label lost: {label}"
    assert "not caregiver lifecycle authority" in APP_JS


# ── wave 2: jargon that survived the first pass ──────────────────────────────


def test_the_word_workspace_is_gone_from_everything_he_reads():
    """ "This isn't a god damn workspace, this is about recording treatment."""
    for line in INDEX_HTML.splitlines():
        assert (
            "workspace" not in line.lower() or "class=" in line or "id=" in line
        ), f"index.html still shows the word workspace: {line.strip()[:110]}"
    # In app.js the word may survive only as a function or element name.
    for number, line in enumerate(APP_JS.splitlines(), start=1):
        if "workspace" not in line.lower():
            continue
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        for quoted in re.findall(r"['`]([^'`\n]*)['`]", line):
            if "workspace" not in quoted.lower():
                continue
            # CSS selectors and element ids are not copy.
            is_selector = bool(re.fullmatch(r"[#.\w\s,>:()\[\]=\"'-]+", quoted)) and (
                "#" in quoted or quoted.startswith(".")
            )
            is_identifier = bool(re.fullmatch(r"[\w-]+", quoted))
            is_api_path = quoted.startswith("/")
            assert (
                is_selector or is_identifier or is_api_path
            ), f"static/app.js:{number} still shows the word workspace: {quoted[:100]}"


def test_offline_and_stale_notices_say_what_is_happening():
    assert "Offline snapshot" not in APP_JS
    assert "Stale · read-only" not in APP_JS
    assert "Read-only snapshot" not in APP_JS
    assert "Showing the last version that loaded" in APP_JS
    assert "showing the last version that loaded" in APP_JS


def test_internal_consistency_machinery_is_not_narrated():
    for phrase in [
        "authoritative reload",
        "authoritative workspace",
        "authoritative research",
        "transport is uncertain",
        "atomically",
        "atomic follow-up",
        "immutable history",
        "immutable successor",
        "Immutable saved snapshot",
        "lifecycle actions are available",
        "This lifecycle change is not available",
    ]:
        assert phrase not in APP_JS, f"still narrated to the caregiver: {phrase}"


def test_forensic_value_views_say_it_in_words_but_keep_the_distinction():
    """A stored null and a stored empty string still read differently."""
    node = _slice("function treatmentScalarNode", "function treatmentAppendFact")
    assert "'Null'" not in node
    assert 'Empty string ("")' not in node
    assert "'Nothing recorded'" in node
    assert "'Recorded as blank'" in node
    assert "'Not in the record'" in node

    research = _slice("function researchValueMarkup", "function researchItemTitle")
    assert ">Null<" not in research
    assert ">Empty string<" not in research
    assert ">Missing field<" not in research
    assert ">Nothing recorded<" in research
    assert ">Recorded as blank<" in research
    assert ">Not in the record<" in research


def test_the_cga_badge_does_not_shout_either():
    assert "CgA RISING" not in APP_JS
    assert "CgA FALLING" not in APP_JS
    assert "rising: 'CgA rising'" in APP_JS


def test_the_recap_export_says_status_not_lifecycle():
    recap = _slice("function buildVisitRecapText", "function recapSectionMarkup")
    # The word must be gone from every literal form, not just the quoted one:
    # the decision and follow-up rows were template literals and slipped past an
    # earlier version of this check.
    assert "Lifecycle" not in recap
    assert "['Status', visitStatusLabel(visit.status)]" in recap
    assert "Status: ${recapPlainText(enumLabel(item.status))}" in recap
    # The follow-up row printed the stored token with its underscores stripped.
    assert "String(item.status).replaceAll('_', ' ')" not in recap


def test_the_transition_note_does_not_print_stored_status_codes():
    assert "Server-authorized transition from" not in APP_JS
    assert "TREATMENT_STATUS_PHRASES" in APP_JS
    assert "current: 'a current treatment'" in APP_JS


def test_restart_reasons_speak_to_the_caregiver_not_as_the_server():
    reasons = _slice("const TREATMENT_RESTART_REASONS", "function treatmentElement")
    for phrase in ["The server permits", "The saved workflow does not establish", "is not past."]:
        assert phrase not in reasons, f"restart reason still speaks as the server: {phrase}"
    assert "This treatment is not recorded as ended." in reasons
    assert "You can add a new treatment record linked to this one." in reasons


def test_wave_two_safety_wording_keeps_its_meaning():
    """Plainer words, same promises. Each of these is load-bearing."""
    # INVARIANTS.md:153 - never infers a clinical conclusion.
    assert "NET/Care does not draw a clinical conclusion." in INDEX_HTML
    # INVARIANTS.md:226-233 - open/closed imply nothing clinical.
    assert "They say nothing about relevance, eligibility, availability, enrolment," in INDEX_HTML
    assert (
        "Saving this says nothing about relevance, eligibility, enrolment, "
        "availability, suitability, or what is recommended."
    ) in INDEX_HTML
    assert "NET/Care does not rank it or work out whether she is eligible." in INDEX_HTML
    # INVARIANTS.md:296-297 - naming a record first carries no preference.
    assert "naming one first does not mean it is the right one" in INDEX_HTML
    # INVARIANTS.md:99-100 - decisions are the caregiver's own record of the
    # clinician, never verified or model-written. The static label is reset by
    # four JS paths, so the wording has to match in both files or the change
    # never reaches the screen.
    assert "What the clinician decided, as you recorded it" in INDEX_HTML
    assert APP_JS.count("'What the clinician decided, as you recorded it'") == 4
    assert "Decision you recorded from the clinician" not in APP_JS
    # INVARIANTS.md:358-369 - hiding is presentation only and always reversible.
    assert "Nothing was deleted or changed" in APP_JS
    assert "NET/Care still uses them when answering your questions" in APP_JS


def test_labels_rebuilt_in_js_match_the_static_markup():
    """A caption or label reset by JS must not disagree with index.html.

    Three wave 2 edits were initially inert because a render path overwrote the
    static text on every render.
    """
    assert APP_JS.count("'Imaging reports, in the order they were recorded'") == 2
    assert "Recorded imaging reports in their stored order" not in APP_JS
    assert "Imaging reports, in the order they were recorded" in INDEX_HTML


def test_accessible_names_match_the_visible_button():
    """Voice control needs the accessible name to contain the visible label."""
    assert "in my workspace" not in APP_JS
    assert "from my workspace" not in APP_JS
    assert "`Show ${row.raw_text} again`" in APP_JS
    assert "`Mark ${row.raw_text} as not useful to me`" in APP_JS
