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

from tests._copy_scan import html_visible_strings, javascript_string_literals, strip_markup

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

    Wave 3 finished the job in the forensic value views as well; see
    `test_no_forensic_type_names_survive_anywhere`.
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


def test_the_three_fixed_safety_paragraphs_say_the_same_things_in_plainer_words():
    """Wave 3 reworded all three. Every promise in them had to survive.

    These were byte-pinned and deliberately deferred by waves 1 and 2. They are
    reworded here together with `INVARIANTS.md` and their other pinning tests,
    which is the condition the earlier waves set for touching them. Each
    assertion below names a promise rather than a phrase, so a future rewrite
    that quietly narrows one of them fails here.
    """
    from agent.research_disposition import RESEARCH_SAFETY_GUIDANCE
    from agent.symptom_episodes import SYMPTOM_SAFETY_GUIDANCE
    from agent.treatment_reconciliation import TREATMENT_SAFETY_GUIDANCE

    assert TREATMENT_SAFETY_GUIDANCE == (
        "NET/Care records what you enter. It does not check whether treatment details "
        "are correct or give advice about starting, stopping, or changing treatment. "
        "Confirm treatment decisions with the treating team."
    )
    assert RESEARCH_SAFETY_GUIDANCE == (
        "NET/Care records the research you choose to follow. It does not decide "
        "whether research is relevant, whether someone is eligible for or enrolled in "
        "a study, or whether a treatment is suitable. Confirm clinical questions with "
        "the treating team and trial details with the study site."
    )
    assert SYMPTOM_SAFETY_GUIDANCE == (
        "NET/Care records what you enter. It does not decide how urgent symptoms are "
        "or monitor them. Contact the treating team about symptoms or concerns. If you "
        "think this may be a medical emergency, contact local emergency services."
    )

    # INVARIANTS.md:384 - records, does not verify, does not advise, confirm.
    assert "records what you enter" in TREATMENT_SAFETY_GUIDANCE
    assert "does not check whether treatment details are correct" in TREATMENT_SAFETY_GUIDANCE
    assert (
        "give advice about starting, stopping, or changing treatment" in TREATMENT_SAFETY_GUIDANCE
    )
    assert "Confirm treatment decisions with the treating team." in TREATMENT_SAFETY_GUIDANCE

    # INVARIANTS.md:270-273 - all four disclaimed capabilities are still named.
    for promise in ["relevant", "eligible", "enrolled", "suitable"]:
        assert promise in RESEARCH_SAFETY_GUIDANCE, f"research copy dropped: {promise}"
    assert "does not decide" in RESEARCH_SAFETY_GUIDANCE
    assert (
        "Confirm clinical questions with the treating team and trial details with the study site."
    ) in RESEARCH_SAFETY_GUIDANCE

    # INVARIANTS.md:208-214 - urgency, monitoring, treating team, emergency services.
    assert "does not decide how urgent symptoms are or monitor them" in SYMPTOM_SAFETY_GUIDANCE
    assert "Contact the treating team about symptoms or concerns." in SYMPTOM_SAFETY_GUIDANCE
    assert "contact local emergency services." in SYMPTOM_SAFETY_GUIDANCE
    # Non-personalized: the fixed copy never names or refers to the patient.
    for pronoun in [" she ", " her ", " his wife"]:
        assert pronoun not in SYMPTOM_SAFETY_GUIDANCE
        assert pronoun not in RESEARCH_SAFETY_GUIDANCE
        assert pronoun not in TREATMENT_SAFETY_GUIDANCE

    # The client validates the server copy byte for byte, so both must agree.
    assert f"const TREATMENT_SAFETY_GUIDANCE = '{TREATMENT_SAFETY_GUIDANCE}';" in APP_JS
    assert f"const RESEARCH_SAFETY_GUIDANCE = '{RESEARCH_SAFETY_GUIDANCE}';" in APP_JS
    assert SYMPTOM_SAFETY_GUIDANCE in APP_JS.replace("'\n    + '", "")


def test_the_old_stiffer_safety_wording_is_gone_from_every_file():
    """A regression to the old paragraphs must fail loudly, not silently."""
    retired = [
        "does not verify treatment details or advise",
        "does not determine relevance, eligibility, enrollment, or treatment suitability",
        "does not assess urgency or monitor symptoms",
    ]
    for source, name in [
        (APP_JS, "static/app.js"),
        (INDEX_HTML, "static/index.html"),
        (Path("INVARIANTS.md").read_text(encoding="utf-8"), "INVARIANTS.md"),
        (RESEARCH_PY, "agent/research_disposition.py"),
        (TREATMENT_PY, "agent/treatment_reconciliation.py"),
        (
            Path("agent/symptom_episodes.py").read_text(encoding="utf-8"),
            "agent/symptom_episodes.py",
        ),
    ]:
        for phrase in retired:
            assert phrase not in source, f"{name} still carries the old wording: {phrase}"


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


# ── wave 3: the medium and low findings, and the deferred stragglers ─────────


def _js_copy() -> list[tuple[int, str]]:
    """Every readable string in `static/app.js`, markup plumbing removed."""
    return [(line, strip_markup(text)) for line, text in javascript_string_literals(APP_JS)]


def _html_copy() -> list[tuple[int, str]]:
    return html_visible_strings(INDEX_HTML)


_CSS_DECLARATION = re.compile(r"[\w-]+\s*:\s*[^;\s][^;]*;")
_CSS_SELECTOR_CHARS = re.compile(r"[#.\w\s,>:+~\[\]='\"()*-]+")
_TWO_WORDS = re.compile(r"[A-Za-z]{2,} [A-Za-z]{2,}")


def looks_like_a_sentence(text: str) -> bool:
    """Is this a phrase he reads, rather than a token the code needs?

    `static/app.js` is one file holding copy, CSS selectors, inline styles,
    element ids, API paths and `typeof` comparisons. The reliable separator is
    that copy has words with spaces between them. A single token is therefore
    outside this guard on purpose: `'object'` in a `typeof` check and
    `'treatment-workspace'` as a class name are not copy, and single-word
    labels are pinned individually by the per-family tests below instead.
    """
    stripped = text.strip()
    if stripped.startswith("/"):
        return False
    if _CSS_DECLARATION.search(stripped):
        return False
    # A selector list has spaces but no prose: it is all ids, classes and tags.
    if ("#" in stripped or stripped.startswith(".")) and _CSS_SELECTOR_CHARS.fullmatch(stripped):
        return False
    return bool(_TWO_WORDS.search(stripped))


# Two research labels and two treatment labels are wire-integrity values, not
# copy: the client compares them field for field and never prints them (see
# static/app.js validateResearchProjection, treatmentLegacyRowIsValid and
# treatmentUnlinkedGeneratedRowIsValid). Rewording them would be a protocol
# change with nothing to show for it, so they are named here rather than
# quietly skipped.
WIRE_ONLY_LABELS = (
    "Research discovery provenance",
    "Caregiver-maintained shortlist and disposition workflow",
    "Machine-generated compatibility context",
    "Legacy/generated · not caregiver lifecycle authority",
    "External registry or bibliographic facts",
)

# Words that belong to the database or the source tree, never to the screen.
BANNED_VOCABULARY = (
    "array",
    "object",
    "boolean",
    "enum",
    "null",
    "fed",
    "working visit",
    "follow-through task",
    "provenance",
    "durable",
    "superseded",
    "disposition",
    "workspace",
    "snapshot",
    "endpoint",
    "read-only",
    "immutable",
)
_BANNED = re.compile(
    "|".join(rf"\b{re.escape(word)}\b" for word in BANNED_VOCABULARY),
    re.IGNORECASE,
)


def test_no_developer_vocabulary_survives_in_anything_he_reads():
    """The words that made the app sound like a database must stay gone.

    This scans real string literals — including multi-line template literals
    and the accessible names hiding inside them — plus HTML text nodes and the
    attributes a screen reader speaks. An earlier guard used a single-line
    regex and missed exactly those places.
    """
    offences: list[str] = []
    for label, entries in [("static/app.js", _js_copy()), ("static/index.html", _html_copy())]:
        for line, text in entries:
            if not looks_like_a_sentence(text):
                continue
            if any(wire in text for wire in WIRE_ONLY_LABELS):
                continue
            match = _BANNED.search(text)
            if match:
                offences.append(f"{label}:{line} [{match.group(0)}] {text.strip()[:110]}")
    assert not offences, "developer vocabulary reached the screen:\n" + "\n".join(offences)


def test_the_scanner_would_actually_catch_a_regression():
    """A guard that cannot fail is not a guard.

    `strip_markup` removes class names and data attributes, which is exactly
    what could make this test blind, so prove it still sees a real sentence, a
    banned word inside a multi-line template, and an accessible name that a
    single-line regex would have walked straight past.
    """
    literals = javascript_string_literals(
        "const a = 'plain copy here';\n"
        "// 'not copy at all'\n"
        "const b = /'[a-z]'/;\n"
        'const c = `<p class="x-object">\n  documents you have fed in\n</p>`;\n'
        'const d = `<button aria-label="Show exact array">go</button>`;\n'
        "const e = 'font-size:11px;padding:4px 6px';\n"
        "const f = `<h3>${t === null ? 'Title is null here' : t}</h3>`;\n"
        "function g() { return /['\"]/; }\n"
        "const h = 'workspace in copy here';\n"
    )
    texts = [strip_markup(text) for _, text in literals]
    copy = [text for text in texts if looks_like_a_sentence(text)]
    assert "plain copy here" in copy
    # Comments, regex literals and inline styles are not copy.
    assert not any("not copy at all" in text for text in texts)
    assert not any("[a-z]" in text for text in texts)
    assert not any("font-size" in text for text in copy)
    # A banned word inside a multi-line template is caught, and the class name
    # that contains "object" is not mistaken for one.
    caught = [text for text in copy if _BANNED.search(text)]
    assert any("fed in" in text for text in caught)
    assert not any("x-object" in text for text in caught)
    # An accessible name inside a tag survives markup stripping.
    assert any("Show exact array" in text for text in caught)
    # Conditional copy inside a `${...}` expression is copy too. The saved
    # research card hid "Title is null" in exactly this shape, and an earlier
    # version of this scanner threw those literals away.
    assert any("Title is null here" in text for text in caught)
    # A regex after `return` is a regex, not division. Reading it as division
    # swallows the following string literal and blinds the guard silently.
    assert any("workspace in copy here" in text for text in caught)


def test_the_forensic_value_views_stopped_naming_javascript_types():
    """`Boolean:` and `Number:` were the last stored-type prefixes on screen."""
    node = _slice("function treatmentScalarNode", "function treatmentAppendFact")
    assert "Boolean:" not in node
    assert "Number:" not in node
    assert "Show exact array" not in node
    assert "Show exact object" not in node
    assert "Show exact text" not in node
    assert "value ? 'Yes' : 'No'" in node
    assert "'Show full details'" in node
    assert "'Show full wording'" in node
    # The distinction wave 1 kept on purpose is still there.
    assert "'Nothing recorded'" in node
    assert "'Recorded as blank'" in node
    assert "'Not in the record'" in node


def test_no_forensic_type_names_survive_anywhere():
    """Research values used a second, separate vocabulary for the same idea."""
    research = _slice("function researchValueMarkup", "function researchAuthorityMarkup")
    assert "Show exact object" not in research
    assert "Show exact content" not in research
    assert "Empty object" not in research
    assert ">Show full details<" in research
    assert ">Show full wording<" in research
    assert ">Recorded as empty<" in research

    title = _slice("function researchItemTitle", "function appendResearchControl")
    for phrase in [
        "Title is null",
        "Title is empty",
        "Title field missing",
        "External identifier is null",
        "External identifier is empty",
        "External identifier missing",
    ]:
        # The saved-consideration card had its own copy of this wording, so the
        # check is against the whole file rather than one helper.
        assert phrase not in APP_JS, f"forensic wording survived: {phrase}"
    assert "'No title recorded'" in title
    assert "'No source ID recorded'" in title
    # Saved consideration cards render the snapshot title on a second path.
    card = _slice("function renderResearchConsideration", "const actions = document")
    assert "'Title not in the record'" in card
    assert "'No title recorded'" in card
    assert "'Title recorded as blank'" in card


def test_research_field_names_are_written_out_not_de_underscored():
    """`registry_last_update` reached the screen as "registry last update"."""
    markup = _slice("function researchAuthorityMarkup", "function researchItemTitle")
    assert "replaceAll('_', ' ')" not in markup
    assert "researchFieldLabel(key)" in markup

    result = _run_node(
        _slice("const RESEARCH_FIELD_LABELS", "function researchItemTitle")
        + """
process.stdout.write(JSON.stringify({
  registry: researchFieldLabel('registry_last_update'),
  excerpt: researchFieldLabel('eligibility_excerpt'),
  nct: researchFieldLabel('nct_id'),
  added: researchFieldLabel('date_added'),
  unmapped: researchFieldLabel('some_new_field'),
}));
"""
    )
    assert result["registry"] == "Registry last updated"
    assert result["excerpt"] == "Who the trial is looking for"
    assert result["nct"] == "Trial number"
    assert result["added"] == "Added on"
    # An unmapped key keeps its recorded spelling rather than being re-cased
    # into something that only looks like a label.
    assert result["unmapped"] == "some_new_field"


def test_appointments_are_appointments_not_working_visits():
    for phrase in [
        "No working visit is set up yet",
        "A working visit is ready for preparation",
        "follow-through tasks",
        "Create without imported appointment",
        "Linked imported appointment",
        "Enter a manual caregiver question",
    ]:
        assert phrase not in APP_JS, f"still on screen: {phrase}"
    assert (
        "'No appointment has been set up yet. Add the next appointment and collect questions for it.'"
        in APP_JS
    )
    assert "'An appointment is ready to prepare.'" in APP_JS
    assert "active: 'No active follow-ups.'," in APP_JS
    assert "'Enter the question you want to ask.'" in APP_JS


def test_visit_answers_stay_the_caregivers_record_of_the_clinician():
    """INVARIANTS.md:99-100 - clinician-attributed, caregiver-entered, unverified."""
    assert "Clinician answer explicitly unknown" not in APP_JS
    assert "Clinician-attributed answer" not in APP_JS
    assert "No clinician-attributed decisions captured." not in APP_JS
    assert "'Clinician said the answer is not known'" in APP_JS
    assert "Answer you heard from the clinician" in APP_JS
    assert "No decisions from the clinician have been recorded yet." in APP_JS
    # The attribution labels that carry the actual safety meaning are untouched,
    # and the answer card still shows one next to the recorded answer.
    assert "clinician: 'You recorded this from the clinician'," in APP_JS
    assert "RECORD_SOURCE_COPY.clinician" in _slice(
        "function renderVisitQuestions", "function toggleVisitAnswerText"
    )
    # The static eyebrow keeps the "as you recorded it" tail wave 2 established.
    assert "From the clinician, as you recorded it" in INDEX_HTML


def test_retry_copy_still_says_the_request_is_unchanged():
    """Load-bearing: a retry re-sends the saved body, and an edit cancels it."""
    assert "Retrying the unchanged request" not in APP_JS
    assert APP_JS.count("'Sending the same details again…'") == 6
    assert ("'The details changed. Review the latest follow-up and send it again.',") in APP_JS
    assert "submit it as a new request" not in APP_JS


def test_difference_copy_still_forbids_every_inference_it_used_to():
    """The helper listed four forbidden inferences; all four survive."""
    helper = _slice(
        "'What difference did you notice?'", "function renderTreatmentDifferenceVariant"
    )
    for forbidden in [
        "which came first",
        "which is preferred",
        "what caused the difference",
        "which is correct",
    ]:
        assert forbidden in helper, f"difference helper dropped: {forbidden}"
    assert "Caregiver comparison wording" not in APP_JS
    # Linking components still refuses both equivalence and source confirmation.
    link_helper = _slice("Link recorded treatment components", "const componentOptions")
    assert "does not confirm that they mean the same thing" in link_helper
    assert "does not confirm the source" in link_helper


def test_hidden_treatment_rows_still_disclose_the_count_and_offer_restore():
    """INVARIANTS.md:368-369 survived the wording change."""
    assert "`${hiddenRecordedRows.length} hidden by you · show list`," in APP_JS
    assert "Nothing was deleted or changed" in APP_JS
    assert "NET/Care still uses them when answering your questions" in APP_JS


def test_recorded_treatment_rows_are_never_worded_as_outstanding_work():
    """INVARIANTS.md:370-372 - an unlinked row is a legitimate resting state."""
    card = _slice("function treatmentRecordedCard", "const card = treatmentElement(")
    assert "Linked to reviewed status" not in card
    assert "Linked to a treatment status you entered" in card
    assert "No treatment status you entered refers to this wording." in card
    for badge in ["needs review", "outstanding", "incomplete", "action required"]:
        assert badge not in card.lower()


def test_imaging_copy_never_claims_the_app_compared_the_scans():
    """INVARIANTS.md:153 - no interval change, no progression label."""
    assert "NET/Care does not infer chronology or change" not in APP_JS
    assert "NET/Care does not decide whether anything has changed." in APP_JS
    assert "NET/Care does not draw a trend line." in APP_JS
    assert "Confirm this exact pair" not in APP_JS
    assert "'Two reports selected. Show them side by side.'" in APP_JS
    assert "Select two imaging reports to compare the recorded findings." in INDEX_HTML


def test_backend_messages_stopped_speaking_about_jobs_and_workspaces():
    for phrase in [
        "This job was interrupted by a server restart",
        "The research workspace changed",
        "not eligible for this lifecycle change",
        "A caregiver treatment workspace preference changed",
        "does not have two cited authorities",
    ]:
        assert phrase not in APP_PY, f"app.py still says: {phrase}"
    assert "This task stopped when the server restarted." in APP_PY
    assert "The research list changed. Reload it and try again." in APP_PY
    # The legacy-difference message must not claim both records are sources:
    # record B may be a caregiver treatment record instead.
    assert "two linked source statements" not in APP_PY
    assert "does not have both of its linked records" in APP_PY
    assert "treatment workspace unreadable" not in RECONCILIATION_PY

    # The PHI-free reason codes behind these messages are untouched.
    assert '"treatment_projection_invalid"' in TREATMENT_PY
    assert '"research_projection_too_large"' in RESEARCH_PY


def test_labels_rebuilt_in_js_still_match_the_static_markup():
    """Wave 3 changed five more labels that live in both files."""
    pairs = [
        ("What do you want to do with the follow-up?", 2, 2),
        ("Choose what kind of update this is.", 1, 1),
        ("Your treatment record", 1, 1),
        ("Create a new appointment", 1, 2),
        ("Administrative note, not clinical evidence", 2, 1),
    ]
    for phrase, html_count, js_count in pairs:
        assert INDEX_HTML.count(phrase) == html_count, f"index.html count changed: {phrase}"
        assert APP_JS.count(phrase) == js_count, f"app.js count changed: {phrase}"
    # The retired wording must be gone from both layers, not just one.
    for retired in [
        "Follow-up operation",
        "Choose an allowed event type",
        "You enter and review this",
        "Create without imported appointment",
        "Administrative note - not clinical evidence",
    ]:
        assert retired not in INDEX_HTML, f"index.html still shows: {retired}"
        assert retired not in APP_JS, f"static/app.js still shows: {retired}"


def test_the_imaging_selection_status_is_not_rewritten_with_the_old_wording():
    """`updateImagingSelectionControls` overwrites the static text on render.

    The static markup was rewritten first and the render path still put the old
    sentence back, which is the same inert-change trap wave 2 hit.
    """
    assert "Select exactly two current records" not in APP_JS
    assert "Select exactly two current records" not in INDEX_HTML
    assert "Select two imaging reports to compare the recorded findings." in INDEX_HTML
    controls = _slice("function updateImagingSelectionControls", "function selectImagingRecord")
    assert "Select two imaging reports to compare the recorded findings." in controls
    assert "raw report facts" not in controls
