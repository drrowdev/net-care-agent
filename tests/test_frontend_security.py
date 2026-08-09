"""Static regression checks for file upload and DOM rendering safety."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")
CSS = Path("static/styles.css").read_text(encoding="utf-8")


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


def _response_authority_source() -> str:
    return "\n".join(
        [
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("capturePatientRequest", "patientRequestIsCurrent"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("authorizePatientResponse", "setAppointmentMessage"),
        ]
    )


def _run_summary_auth_probe(status: int) -> dict:
    script = "\n".join(
        [
            """
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
    value: '',
    closest() { return null; },
    remove() {},
    removeAttribute() {},
    setAttribute() {},
  };
}

const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, fakeElement());
  return elements.get(id);
};
const document = {
  body: { children: [], classList: new FakeClassList() },
  getElementById: element,
  querySelector() { return null; },
  querySelectorAll() { return []; },
};

let selectedTaskId = 'patient-task';
let currentReportText = 'patient report';
let pendingSummary = { status: 'current' };
let currentReceipt = { patient: true };
let latestProfileRevision = 7;
let latestResearchUpdate = { trial_count: 1 };
let patientEvidence = { patient: true };
let allBiomarkers = [{ patient: true }];
let chatHistory = [{ patient: true }];
let chatHistoryRevision = 7;
let activeDialogSurface = null;
let lastDialogTrigger = null;
let chatOpen = true;
let taskSelectionEpoch = 0;
let phiEpoch = 0;
let summaryLoadEpoch = 0;
let workflowRevision = 3;
let visitsById = new Map([['visit-phi', { patient: true }]]);
let appointmentOptions = [{ patient: true }];
let appointmentQuestionSources = [{ patient: true }];
let questionLoadEpoch = 0;
let generatedQuestionsUnavailable = false;
let followUpsById = new Map([['follow-up-phi', { patient: true }]]);
let followUpFilter = 'active';
let followUpLoadEpoch = 0;
let followUpProjectionStale = false;
let selectedFollowUpId = 'follow-up-phi';
let followUpSelectionEpoch = 0;
let followUpDialogOpen = true;
let followUpDialogMode = 'edit';
let followUpOutcomeStatus = null;
let pendingFollowUpIntent = { patient: true };
let activeFollowUpIntent = null;
let followUpMutationPending = true;
let followUpDrafts = new Map([['edit:follow-up-phi', { patient: true }]]);
let selectedVisitId = 'visit-phi';
let visitSelectionEpoch = 0;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'decisions';
let pendingWorkflowIntent = { patient: true };
let activeWorkflowIntent = null;
let workflowMutationPending = true;
let appointmentDrafts = new Map([['visit-phi', { patient: true }]]);
let renderSummaryCalls = 0;
const loadErrors = [];

function renderLatestResearchUpdate() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
function setFollowUpMutationBusy() {}
function updateAppointmentFormValidity() {}
function loadFailureMarkup() { return 'transient failure'; }
function reportLoadSuccess() {}
function reportLoadError(scope, error) { loadErrors.push([scope, error.status]); }
function renderSummary(data) {
  renderSummaryCalls += 1;
  renderFreshness(data);
}
function summaryIsStale() { return false; }
function fmtDate(value) { return value; }
function advancePatientAuthority(revision) {
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
""",
            _response_authority_source(),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _function_source("shouldEvictClientPhi", "restoreDialogFocus"),
            _function_source("evictClientPhi", "renderLatestResearchUpdate"),
            _executable_function_source("loadSummary", "renderPendingSummary"),
            _function_source("renderFreshness", "renderClaimEvidence"),
            """
function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}

(async () => {
  const authStatus = Number(process.argv[1]);
  const banner = element('freshness-banner');
  const title = element('freshness-title');
  const message = element('freshness-message');
  const summaryBody = element('summary-body');
  banner.hidden = false;
  title.textContent = 'Patient-derived freshness';
  message.textContent = 'Patient-derived source';
  summaryBody.innerHTML = 'Patient-derived summary';

  let resolveLate;
  const lateResponse = new Promise(resolve => { resolveLate = resolve; });
  let fetchCalls = 0;
  globalThis.fetch = async () => {
    fetchCalls += 1;
    if (fetchCalls === 1) return lateResponse;
    return response(authStatus, { error: 'denied' });
  };

  const lateRequest = loadSummary();
  const authRequest = loadSummary();
  await authRequest;
  resolveLate(response(200, { status: 'current', generated_at: '2026-08-07' }));
  await lateRequest;

  console.log(JSON.stringify({
    phiEpoch,
    hidden: banner.hidden,
    title: title.textContent,
    message: message.textContent,
    summary: summaryBody.innerHTML,
    renderSummaryCalls,
    fetchCalls,
    loadErrors,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-e", script, str(status)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("status", [401, 403])
def test_summary_auth_eviction_cannot_repaint_freshness_or_accept_late_success(status):
    result = _run_summary_auth_probe(status)

    assert result == {
        "phiEpoch": 2,
        "hidden": True,
        "title": "",
        "message": "",
        "summary": '<div class="summary-empty">Patient assessment unavailable.</div>',
        "renderSummaryCalls": 0,
        "fetchCalls": 2,
        "loadErrors": [],
    }


def test_process_file_posts_multipart_to_file_endpoint():
    source = _function_source("processFile", "runDigest")
    assert "new FormData()" in source
    assert "form.append('file', file, file.name)" in source
    assert "fetch('/api/feed-file'" in source
    assert "body: form" in source
    assert "file.text()" not in source
    assert "Content-Type" not in source


def test_feed_paths_share_json_error_and_task_selection_handling():
    text_feed = _function_source("submitFeed", "activateSubmittedTask")
    file_feed = _function_source("processFile", "runDigest")
    for source in (text_feed, file_feed):
        assert "readJsonResponse(r)" in source
        assert "activateSubmittedTask(d)" in source
    assert "if (!response.ok)" in APP_JS
    assert "typeof data.error === 'string'" in APP_JS
    assert "data.job_id || data.task_id" in APP_JS


def test_duplicate_job_submissions_reattach_to_returned_job_id():
    helper = _function_source("readJobSubmission", "waitForJob")
    assert "response.status === 409" in helper
    assert "data.job_id" in helper
    for name, next_name in (
        ("generateSummary", "renderSummary"),
        ("runDigest", "runDeepSweep"),
        ("runDeepSweep", "startPolling"),
        ("generateQuestions", "addQuestion"),
    ):
        source = _function_source(name, next_name)
        assert "readJobSubmission(r)" in source
    assert "activateSubmittedTask(d)" in _function_source("runDigest", "runDeepSweep")
    assert "activateSubmittedTask(d)" in _function_source("runDeepSweep", "startPolling")


def test_interrupted_jobs_are_terminal_and_show_retry_guidance():
    waiter = _function_source("waitForJob", "relativeTime")
    assert "job.status === 'interrupted'" in waiter
    assert "job.retry_guidance || job.error" in waiter
    task_ui = _function_source("renderTasks", "updateHeaderStatus")
    detail_ui = _function_source("selectTask", "formatReport")
    assert "t.status === 'interrupted'" in task_ui
    assert "t.retry_guidance" in task_ui
    assert "task.status === 'interrupted'" in detail_ui
    assert "task.retry_guidance" in detail_ui
    polling = _function_source("startPolling", "toggleQuestions")
    assert "t.status === 'interrupted'" in polling


def test_idle_polling_backs_off_and_hidden_pages_poll_less_often():
    polling = _function_source("startPolling", "toggleQuestions")
    assert "hasActiveJobs ? 3000 : 30000" in polling
    assert "document.hidden ? 60000" in polling
    assert "setTimeout(poll" in polling
    assert "setInterval" not in polling
    assert "hadActiveJobs && !hasActiveJobs" in polling
    assert "if (hasActiveJobs || hadActiveJobs)" not in polling
    assert "if (selectedTaskId && hasActiveJobs)" not in polling
    assert "tasks.find(task => task.id === selectedTaskId)" in polling
    assert "activeView === 'today' && !document.hidden" in polling
    submission = _function_source("activateSubmittedTask", "showFeedError")
    assert "hadActiveJobs = true" in submission
    assert "startPolling()" in submission


def test_summary_refresh_preserves_open_action_feedback():
    loader = _function_source("loadSummary", "renderPendingSummary")
    assert "document.querySelector('.action-feedback')" in loader
    assert "pendingSummary = d" in loader
    pending = _function_source("renderPendingSummary", "summaryIsStale")
    assert "renderSummary(summary)" in pending
    dismiss = _function_source("quickDismiss", "reportMissedSummary")
    assert "expected_action: el?.dataset.actionText" in dismiss
    assert "summary_revision: el?.dataset.summaryRevision || null" in dismiss


def test_stale_summary_preempts_open_action_feedback_immediately():
    loader = _function_source("loadSummary", "renderPendingSummary")
    assert "const responseStale =" in loader
    assert "editor && responseStale" in loader
    assert "editor.querySelectorAll('button, input')" in loader
    assert "editor.remove()" in loader
    assert "pendingSummary = null" in loader
    assert "renderSummary(d)" in loader
    assert "editor && sameRevision" in loader


def test_escape_closes_only_the_topmost_open_surface():
    assert APP_JS.count("document.addEventListener('keydown'") == 1
    handler_start = APP_JS.index("document.addEventListener('keydown'")
    handler_end = APP_JS.index("function switchTab", handler_start)
    handler = APP_JS[handler_start:handler_end]
    assert "modal-overlay" in handler
    assert handler.count("return;") >= 4


def test_dialogs_trap_focus_and_make_background_inert():
    focus = _function_source("dialogFocusable", "setBackgroundInert")
    inert = _function_source("setBackgroundInert", "activateDialog")
    trap = _function_source("trapDialogFocus", "loadFailureMarkup")
    assert "button:not([disabled])" in focus
    assert "child.inert = true" in inert
    assert "child.inert = false" in inert
    assert "event.key !== 'Tab'" in trap
    assert "event.shiftKey" in trap
    assert "activateDialog(pop, trigger)" in APP_JS
    assert "activateDialog(overlay.querySelector('.modal'), trigger)" in APP_JS
    assert "activateDialog(report, lastDialogTrigger)" in APP_JS
    assert "activateDialog(panel, trigger)" in APP_JS


def test_feed_tabs_support_roving_arrow_home_and_end_keys():
    source = _function_source("handleFeedTabKeydown", "updateCharCount")
    for key in ("ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"):
        assert key in source
    switcher = _function_source("switchTab", "handleFeedTabKeydown")
    assert "textButton.tabIndex" in switcher
    assert "fileButton.tabIndex" in switcher


def test_load_failures_distinguish_auth_offline_and_retry_states():
    state = _function_source("renderAppState", "retryInitialLoad")
    assert "error?.status === 401" in state
    assert "error?.status === 403" in state
    assert "navigator.onLine === false" in state
    assert "Patient data has not been removed" in state
    retry = _function_source("retryInitialLoad", "switchView")
    for loader in (
        "loadStatus()",
        "loadTasks()",
        "loadSummary()",
        "loadQuestions()",
        "loadJudgments()",
        "loadSymptoms()",
    ):
        assert loader in retry
    assert "updateHeaderStatus(null, e)" in APP_JS
    assert "loadFailureMarkup('Assessment'" in APP_JS
    assert "loadFailureMarkup('Processing activity'" in APP_JS
    assert "loadFailureMarkup('Imaging history'" in APP_JS


def test_status_failure_clears_all_status_derived_phi_and_caches():
    failure = _function_source("renderStatusFailure", "renderLatestResearchUpdate")
    for expression in (
        "redactGeneratedQuestionChoices()",
        "latestResearchUpdate = null",
        "allBiomarkers = []",
        "renderLatestResearchUpdate(null)",
        "patientMeta.innerHTML = ''",
        "search.value = ''",
        "search.disabled = true",
    ):
        assert expression in failure
    evidence = _function_source("loadPatientEvidence", "evidenceBadge")
    assert "patientEvidence = null" in evidence
    assert evidence.index("const evidence = await") < evidence.index(
        "authorizePatientResponse(request, evidence)"
    )
    assert evidence.index("authorizePatientResponse(request, evidence)") < evidence.index(
        "patientEvidence = evidence"
    )


def test_central_phi_eviction_clears_patient_panels_dialogs_and_histories():
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    for expression in (
        "taskSelectionEpoch += 1",
        "summaryLoadEpoch += 1",
        "selectedTaskId = null",
        "currentReportText = ''",
        "currentReceipt = null",
        "pendingSummary = null",
        "chatHistory = []",
        "chatHistoryRevision = null",
        "clearFreshnessProjection()",
        "document.querySelectorAll('.action-feedback')",
        "clear('panel-body'",
        "clear('summary-body'",
        "'chat-messages'",
        "feedText.value = ''",
        "clearReportCopyState()",
        "'judgment-input'",
        "'q-add-input'",
        "'sym-name'",
        "'sym-note'",
        "severity.value = ''",
        ".judgment-edit-text",
        ".receipt-editor input",
    ):
        assert expression in eviction
    freshness = _function_source("clearFreshnessProjection", "renderClaimEvidence")
    assert "\n  function clearFreshnessProjection" in APP_JS
    assert "\n    function clearFreshnessProjection" not in _function_source(
        "renderFreshness", "renderClaimEvidence"
    )
    for expression in (
        "title.textContent = ''",
        "message.textContent = ''",
        "banner.hidden = true",
    ):
        assert expression in freshness
    summary = _function_source("loadSummary", "renderPendingSummary")
    auth_failure = summary[summary.index("catch(e)") :]
    epoch_guard = auth_failure.index("if (!patientRequestIsCurrent(request)")
    eviction = auth_failure.index("if (shouldEvictClientPhi(e))")
    repaint = auth_failure.index("renderFreshness(null, e)")
    assert epoch_guard < auth_failure.index("return null", epoch_guard) < eviction
    assert eviction < auth_failure.index("return null", eviction) < repaint
    for loader, next_name in (
        ("loadStatus", "renderStatusFailure"),
        ("loadPatientEvidence", "evidenceBadge"),
        ("loadSummary", "renderPendingSummary"),
        ("loadTasks", "renderTasks"),
    ):
        assert "evictClientPhi(" in _function_source(loader, next_name)
    submission = _function_source("readJobSubmission", "waitForJob")
    json_reader = _function_source("readJsonResponse", "readJobSubmission")
    assert json_reader.index("response.status === 401") < json_reader.index("response.json()")
    assert submission.index("response.status === 401") < submission.index("response.json()")
    assert "evictClientPhi(error)" in submission
    mutation = _function_source("submitReceiptMutation", "receiptRefreshFailureMarkup")
    assert "evictClientPhi(authError)" in mutation
    assert mutation.index("response.status === 401") < mutation.index("response.json()")
    close = _function_source("closePanel", "receiptValueSummary")
    assert "const request = capturePatientRequest()" in close
    assert "authorizePatientResponse(request, tasks)" in close
    questions = _function_source("generateQuestions", "addQuestion")
    assert "const request = capturePatientRequest()" in questions
    assert "patientRequestIsCurrent(request)" in questions
    for handler, next_name in (
        ("addJudgment", "deleteJudgment"),
        ("addSymptom", "deleteSymptom"),
    ):
        source = _function_source(handler, next_name)
        assert "const requestPhiEpoch = phiEpoch" in source
        assert "requestPhiEpoch !== phiEpoch" in source
    add_question = _function_source("addQuestion", "toggleQuestion")
    assert "const request = capturePatientRequest()" in add_question
    assert "authorizePatientResponse(request, result)" in add_question


def test_missing_selected_task_evicts_instead_of_restoring_cached_receipt():
    selection = _function_source("selectTask", "formatReport")
    missing = selection[selection.index("if (!task)") : selection.index("if (task.status")]
    assert "evictClientPhi(missingError)" in missing
    assert "receiptRefreshFailureMarkup" not in missing


def test_processing_status_never_claims_clinical_freshness():
    header = _function_source("updateHeaderStatus", "closePanel")
    assert "Processing ${running.length}" in header
    assert "lbl.textContent = 'Idle'" in header
    assert "lbl.textContent = 'Unavailable'" in header
    assert "Up to date" not in APP_JS


def test_receipt_is_job_scoped_and_has_no_global_review_flow():
    selector = _function_source("selectTask", "formatReport")
    assert "task.receipt_url" in selector
    assert "renderReceipt(receipt)" in selector
    assert "/receipt/changes/" in APP_JS
    assert "/receipt/undo" in APP_JS
    assert "/api/changes" not in APP_JS
    assert "Mark reviewed" not in APP_JS


def test_corrected_receipt_renders_effective_value_without_relabelling_original_evidence():
    receipt = _function_source("renderReceipt", "receiptFieldInput")
    assert "change.effective_value" in receipt
    assert "Caregiver correction" in receipt
    assert "Original extraction span (before correction)" in receipt


def test_receipt_editor_save_stays_disabled_until_clinical_value_changes():
    editor = _function_source("startReceiptCorrection", "parsedReceiptInput")
    assert 'class="button primary receipt-save"' in editor
    assert "disabled>Save correction" in editor
    assert "const initial = JSON.stringify" in editor
    assert "save.disabled =" in editor


def test_receipt_mutation_response_is_correlated_to_originating_job_and_revision():
    mutation = _function_source("submitReceiptMutation", "selectTask")
    assert "receiptMutationPending" in mutation
    assert "const originJobId = currentReceipt.job_id" in mutation
    assert "const originReceiptRevision = currentReceipt.receipt_revision" in mutation
    assert "selectedTaskId === originJobId" in mutation
    assert "currentReceipt?.job_id === originJobId" in mutation
    assert "currentReceipt?.receipt_revision === originReceiptRevision" in mutation
    assert "pendingWasDisabled" in mutation
    assert "const refreshSelectedJob =" in mutation
    assert "await selectTask(originJobId, originSelectionEpoch, data.receipt)" in mutation
    assert "data.receipt" in mutation
    assert "const originSelectionEpoch = taskSelectionEpoch" in mutation
    assert "taskSelectionEpoch === originSelectionEpoch" in mutation


def test_stale_job_result_is_hidden_in_activity_panel():
    detail = _function_source("selectTask", "formatReport")
    assert "if (task.result.stale)" in detail
    assert "const staleCopy = staleTaskCopy(task)" in detail
    assert "Regenerate it before use" in detail
    assert "if (task.report_stale)" in detail
    assert "staleTaskCopy({" in detail
    tasks = _function_source("renderTasks", "updateHeaderStatus")
    assert "t.derived_content_stale" in tasks
    assert "prior analysis hidden" in tasks
    assert "!task.derived_content_stale && task.key_findings" in detail


def test_open_task_is_revalidated_and_copy_state_cleared():
    loader = _function_source("loadTasks", "renderTasks")
    assert "revalidateOpenTask(tasks)" in loader
    stale = _function_source("staleTaskCopy", "clearReportCopyState")
    assert "source_document_corrected_or_undone" in stale
    assert "patient_record_changed_after_generation" not in stale
    assert "freshness_cannot_be_verified" in stale
    revalidate = _function_source("revalidateOpenTask", "updateHeaderStatus")
    assert "task?.derived_content_stale" in revalidate
    assert "clearReportCopyState()" in revalidate
    copy = _function_source("clearReportCopyState", "revalidateOpenTask")
    assert "currentReportText = ''" in copy
    assert "copy.disabled = true" in copy


def test_receipt_success_survives_detail_refresh_failure():
    helper = _function_source("receiptRefreshFailureMarkup", "selectTask")
    assert "Correction saved successfully." in helper
    assert "Retry detail refresh" in helper
    selection = _function_source("selectTask", "formatReport")
    assert "fallbackReceipt = null" in selection
    assert "receiptRefreshFailureMarkup(fallbackReceipt" in selection
    assert "Saved. Refreshing activity detail" in selection
    assert "if (error?.status === 401 || error?.status === 403)" in selection
    assert "evictClientPhi(error)" in selection
    assert "shouldEvictClientPhi(error) && !fallbackReceipt" in selection


def test_task_selection_epoch_guards_every_async_panel_update():
    selection = _function_source("selectTask", "formatReport")
    assert "const selectionEpoch = expectedEpoch == null ? ++taskSelectionEpoch" in selection
    assert "currentReceipt = fallbackReceipt" in selection
    assert "Loading activity detail" in selection
    assert "const request = capturePatientRequest({ taskSelection: true })" in selection
    assert selection.count("authorizePatientResponse(request,") >= 3
    assert selection.count("patientRequestIsCurrent(request)") >= 3
    assert "const detailResponse = await fetch" in selection
    assert "const receiptResponse = await fetch" in selection


def test_stale_task_copy_maps_reason_and_type_without_source_mislabeling():
    copy = _function_source("staleTaskCopy", "clearReportCopyState")
    assert "Deep-sweep report" in copy
    assert "Digest report" in copy
    assert "Document analysis" in copy
    assert "The source document was corrected or undone." in copy
    assert "The patient record changed after this task was generated." in copy
    assert "This retained legacy task has no source profile revision." in copy
    assert "Generated content was invalidated by a review-state change." in copy
    assert "A newer appointment-question generation replaced this result." in copy


def test_submitted_task_activation_reserves_and_checks_selection_epoch():
    activation = _function_source("activateSubmittedTask", "showFeedError")
    assert "const activationEpoch = ++taskSelectionEpoch" in activation
    assert "await loadTasks()" in activation
    assert "await selectTask(id, activationEpoch)" in activation
    assert activation.count("activationEpoch !== taskSelectionEpoch || selectedTaskId !== id") >= 3


def test_chat_history_is_bound_to_profile_revision_and_visibly_cleared():
    sync = _function_source("syncChatRevision", "toggleChat")
    assert "chatHistoryRevision" in sync
    assert "Patient record changed. Prior chat history was cleared" in sync
    sender = APP_JS[APP_JS.index("function sendChat") :]
    assert "history_revision: chatHistoryRevision" in sender
    assert "const authority = authorizePatientResponse(request, data)" in sender
    assert "if (!authority.accepted || authority.profileAdvanced) return" in sender
    assert "chatHistoryRevision = String(data.profile_revision)" not in sender
    assert "if (e.status === 409)" in sender
    assert "authorizePatientResponse(request, e.data || {})" in sender
    assert "?? latestProfileRevision" not in sender


def test_alert_resolution_uses_stable_id_token_and_revision():
    sidebar = _function_source("renderSidebar", "resolveAlert")
    assert "data-alert-id" in sidebar
    assert "data-resolve-token" in sidebar
    resolver = _function_source("resolveAlert", "loadPatientEvidence")
    assert "/api/alerts/${encodeURIComponent(alertId)}/resolve" in resolver
    assert "expected_token: expectedToken" in resolver
    assert "expected_profile_revision: latestProfileRevision" in resolver
    assert "authorizePatientResponse(request, result)" in resolver


def test_patient_history_joins_documents_and_keeps_orphaned_legacy_records():
    history = _function_source("renderPatientEvidence", "toggleImagingHistory")
    assert "const documents = patientEvidence.documents || []" in history
    assert "const sourcesById = new Map" in history
    assert "history_kind: 'document'" in history
    assert "Legacy document record" in history
    assert "source.source_url" in history


def test_claim_evidence_and_decision_support_wording_are_non_definitive():
    summary = _function_source("renderSummary", "removeItem")
    assert "POTENTIAL FIT" in summary
    assert "MAY FIT" in summary
    assert "Trial to discuss" in summary
    assert "Best matched trial" not in APP_JS
    assert "PRRT: ELIGIBLE" not in APP_JS
    assert "renderClaimEvidence" in summary
    assert "d.claim_evidence?.claims?.cga_trend_detail" in summary
    assert "Prior generated assessment is hidden" in summary


def test_empty_form_handlers_surface_inline_feedback():
    cases = (
        ("addQuestion", "toggleQuestion", "q-form-error"),
        ("addJudgment", "deleteJudgment", "judgment-form-error"),
        ("addSymptom", "deleteSymptom", "sym-form-error"),
    )
    for name, next_name, error_id in cases:
        source = _function_source(name, next_name)
        assert error_id in source
        assert "if (!" in source
    chat = APP_JS[APP_JS.index("function sendChat") :]
    assert "chat-form-error" in chat
    assert "if (!text)" in chat
    feed = _function_source("feedText", "submitFeed")
    assert "Paste clinical text before processing" in feed
    parser = _function_source("parsedReceiptInput", "saveReceiptCorrection")
    assert "if (!input.value.trim()) return null" in parser
    fields = _function_source("receiptFieldInput", "startReceiptCorrection")
    assert "field === 'severity'" in fields
    assert "field === 'new_lesions'" in fields


def test_latest_research_update_labels_only_exact_batch_records():
    sidebar = _function_source("renderSidebar", "toggleSummary")
    assert "d.latest_research_update" in sidebar
    assert "latestResearchUpdate?.trial_count" in sidebar
    assert "latestResearchUpdate?.paper_count" in sidebar

    modal = _function_source("renderModal", "loadTasks")
    assert "latestResearchUpdate[updateField].map(String)" in modal
    assert "newIds.has(String" in modal
    assert "new-research-badge" in modal
    assert "orderedItems" in modal
    assert "/api/changes" not in APP_JS


def test_stale_treatment_classification_visibly_falls_back_to_raw_entries():
    sidebar = _function_source("renderSidebar", "resolveAlert")
    assert "d.treatments_fallback?.length" in sidebar
    assert "d.treatments_classification_current === false" in sidebar
    assert "Classification outdated — showing raw treatment entries." in sidebar


def test_treatment_actions_use_stable_id_token_and_profile_revision():
    sidebar = _function_source("renderSidebar", "resolveAlert")
    assert "data-treatment-id" in sidebar
    assert "data-edit-token" in sidebar
    assert "editTreatment(this,'complete')" in sidebar
    assert "editTreatment(this,'remove')" in sidebar
    editor = _function_source("editTreatment", "generateSummary")
    assert "/api/treatments/${encodeURIComponent(treatmentId)}" in editor
    assert "expected_token: expectedToken" in editor
    assert "expected_profile_revision: latestProfileRevision" in editor
    assert "/api/treatments/update" not in editor


def test_latest_research_update_refreshes_after_missed_job_transitions():
    switch_view = _function_source("switchView", "refreshAfterVisibilityRestore")
    assert "name === 'today'" in switch_view
    assert "loadStatus()" in switch_view
    visibility = _function_source("refreshAfterVisibilityRestore", "relativeTime")
    assert "if (document.hidden) return" in visibility
    assert "loadTasks()" in visibility
    assert "loadStatus()" in visibility
    assert "visibilitychange" in visibility


def test_summary_revisions_are_authoritative_with_legacy_date_fallback():
    source = _function_source("summaryIsStale", "renderSummary")
    stale_flag = source.index("typeof d.stale === 'boolean'")
    revision_check = source.index("d.profile_revision")
    legacy_check = source.index("d.recent_documents")
    assert stale_flag < revision_check
    assert revision_check < legacy_check
    assert "d.summary_revision" in source
    assert "latestDoc.added_at || latestDoc.date" in source


def test_stored_values_are_not_interpolated_into_event_handlers():
    unsafe_patterns = (
        "selectTask('${t.id}')",
        "deleteJudgment('${j.id}')",
        "deleteSymptom('${s.id}')",
        "toggleQuestion('${q.id}')",
        "deleteQuestion('${q.id}')",
        "removeItem('trials','${",
        "removeItem('papers','${",
    )
    for pattern in unsafe_patterns:
        assert pattern not in APP_JS

    assert 'data-task-id="${escHtml(t.id)}"' in APP_JS
    assert 'data-judgment-id="${escHtml(j.id)}"' in APP_JS
    assert 'data-question-id="${escHtml(q.id)}"' in APP_JS
    assert 'data-id="${escHtml(s.id)}"' in APP_JS


def test_malicious_stored_display_fields_are_escaped():
    escaped_expressions = (
        "escHtml(b.value + ' ' + (b.unit||''))",
        "escHtml(b.reference_range || '—')",
        "escHtml(p.sex || '—')",
        "escHtml(a.priority || '—')",
        "escHtml(j.date||'')",
        "escHtml(s.date || '')",
        "escHtml(task.stage || 'processing')",
        "escHtml(translateCategory(q.category||'Other'))",
        "escHtml(item.event || '')",
        'datetime="${escHtml(date)}"',
    )
    for expression in escaped_expressions:
        assert expression in APP_JS

    escaper = _function_source("escHtml", "fmtDate")
    assert ".replace(/&/g,'&amp;')" in escaper
    assert ".replace(/</g,'&lt;')" in escaper
    assert ".replace(/\"/g,'&quot;')" in escaper
    assert ".replace(/'/g,'&#39;')" in escaper


def test_model_markdown_remains_escape_first_and_protocol_limited():
    markdown = _function_source("renderMarkdown", "appendMsg")
    assert "const lines = escHtml(text)" in markdown
    assert "mdInline(" in markdown
    sanitizer = _function_source("mdSanitizeUrl", "mdInline")
    assert "/^(https?:\\/\\/|mailto:|tel:|#|\\/)/i" in sanitizer
    assert "javascript:" not in sanitizer


def _run_workflow_epoch_probe() -> dict:
    script = "\n".join(
        [
            """
class FakeClassList {
  add() {}
  remove() {}
  toggle() {}
}
function fakeElement() {
  return {
    classList: new FakeClassList(),
    className: '',
    dataset: {},
    disabled: false,
    hidden: false,
    innerHTML: '',
    textContent: '',
    value: '',
    setAttribute() {},
  };
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, fakeElement());
  return elements.get(id);
};
const document = {
  getElementById: element,
  querySelectorAll() { return []; },
};
const navigator = { onLine: true };
let phiEpoch = 0;
let visitSelectionEpoch = 4;
let selectedVisitId = 'visit-a';
let appointmentDialogOpen = true;
let workflowRevision = 10;
let latestProfileRevision = 20;
let visitsById = new Map([
  ['visit-a', { id: 'visit-a', token: 'a-original' }],
  ['visit-b', { id: 'visit-b', token: 'b-original' }],
]);
let followUpsById = new Map();
let pendingWorkflowIntent = null;
let activeWorkflowIntent = null;
let workflowMutationPending = false;
let appointmentDrafts = new Map();
let renderPreparationCalls = 0;
let renderWorkspaceCalls = 0;
let successReports = 0;
let callerCleanupCalls = 0;
const evictions = [];
const loadErrors = [];
let followUpProjectionStale = false;
let followUpStaleMarks = 0;

function captureAppointmentDraft() {}
function renderVisitPreparation() { renderPreparationCalls += 1; }
function renderAppointmentWorkspace() { renderWorkspaceCalls += 1; }
function reportLoadSuccess() { successReports += 1; }
function reportLoadError(scope, error) { loadErrors.push([scope, error?.status || null]); }
async function refreshClinicalWorkflowState() { return true; }
async function handleWorkflowConflict() { return true; }
function shouldEvictClientPhi(error) { return Number(error?.status) >= 500; }
function evictClientPhi(error) { evictions.push(error.status); }
function setAppointmentMutationBusy() {}
function updateAppointmentFormValidity() {}
function safeClassToken(value) { return String(value || ''); }
function advancePatientAuthority(revision) {
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
function markFollowUpProjectionStale() {
  followUpProjectionStale = true;
  followUpStaleMarks += 1;
}
""",
            _response_authority_source(),
            _function_source("setAppointmentMessage", "clearWorkflowRetry"),
            _function_source("clearWorkflowRetry", "invalidateWorkflowRetryOnDraftChange"),
            _executable_function_source("workflowIntentCanRender", "refreshClinicalWorkflowState"),
            _executable_function_source("consumeWorkflowResponse", "handleWorkflowConflict"),
            _executable_function_source("performWorkflowIntent", "submitWorkflowMutation"),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            """
function response(data) {
  return {
    status: 200,
    ok: true,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}

(async () => {
  let resolveLate;
  globalThis.fetch = () => new Promise(resolve => { resolveLate = resolve; });
  const visitAIntent = {
    method: 'POST',
    url: '/api/visits/visit-a/questions',
    body: { source_kind: 'manual', mutation_id: 'mutation-a' },
    visitId: 'visit-a',
    requestPhiEpoch: 0,
    requestVisitEpoch: 4,
  };
  const lateRequest = performWorkflowIntent(visitAIntent);
  await Promise.resolve();

  selectedVisitId = 'visit-b';
  visitSelectionEpoch = 5;
  pendingWorkflowIntent = { visitId: 'visit-b', marker: 'keep-b-retry' };
  element('appointment-retry').hidden = false;
  element('appointment-status-message').textContent = 'Visit changed.';
  resolveLate(response({
    workflow_revision: 999,
    profile_revision: 999,
    item: { id: 'visit-a', token: 'a-late', question_snapshots: [] },
  }));
  const lateResult = await lateRequest;
  if (lateResult) callerCleanupCalls += 1;
  const lateRetryPreserved = pendingWorkflowIntent?.marker === 'keep-b-retry'
    && element('appointment-retry').hidden === false;

  globalThis.fetch = async () => {
    const error = new Error('hard server failure');
    error.status = 500;
    throw error;
  };
  const hardFailureResult = await performWorkflowIntent({
    ...visitAIntent,
    body: { source_kind: 'manual', mutation_id: 'mutation-a-hard-failure' },
  });

  appointmentDrafts = new Map([['visit-b', { manualQuestion: 'caregiver draft' }]]);
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  const offlineIntent = {
    method: 'POST',
    url: '/api/visits/visit-b/questions',
    body: { source_kind: 'manual', mutation_id: 'mutation-b' },
    visitId: 'visit-b',
    requestPhiEpoch: 0,
    requestVisitEpoch: 5,
  };
  const offlineResult = await performWorkflowIntent(offlineIntent);
  const offlineRetryPreserved = pendingWorkflowIntent === offlineIntent;

  globalThis.fetch = async () => { throw new TypeError('offline follow-up'); };
  const offlineFollowUpResult = await performWorkflowIntent({
    ...offlineIntent,
    url: '/api/visits/visit-b/follow-ups',
    body: { text: 'caregiver follow-up', mutation_id: 'mutation-follow-up-offline' },
  });
  followUpProjectionStale = false;
  const abortError = new Error('aborted follow-up');
  abortError.name = 'AbortError';
  globalThis.fetch = async () => { throw abortError; };
  const abortedFollowUpResult = await performWorkflowIntent({
    ...offlineIntent,
    url: '/api/visits/visit-b/follow-ups',
    body: { text: 'caregiver follow-up', mutation_id: 'mutation-follow-up-abort' },
  });

  console.log(JSON.stringify({
    lateResult,
    workflowRevision,
    latestProfileRevision,
    visitAToken: visitsById.get('visit-a').token,
    visitBToken: visitsById.get('visit-b').token,
    renderPreparationCalls,
    renderWorkspaceCalls,
    successReports,
    callerCleanupCalls,
    lateRetryPreserved,
    hardFailureResult,
    evictions,
    loadErrors,
    retryPreserved: offlineRetryPreserved,
    offlineRetryVisible: element('appointment-retry').hidden === false,
    offlineDraft: appointmentDrafts.get('visit-b').manualQuestion,
    offlineResult,
    offlineFollowUpResult,
    abortedFollowUpResult,
    followUpStaleMarks,
    followUpProjectionStale,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node"], input=script, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_late_visit_a_response_cannot_mutate_visit_b_or_trigger_success_cleanup():
    result = _run_workflow_epoch_probe()

    assert result == {
        "lateResult": None,
        "workflowRevision": 10,
        "latestProfileRevision": 20,
        "visitAToken": "a-original",
        "visitBToken": "b-original",
        "renderPreparationCalls": 0,
        "renderWorkspaceCalls": 0,
        "successReports": 0,
        "callerCleanupCalls": 0,
        "lateRetryPreserved": True,
        "hardFailureResult": None,
        "evictions": [500],
        "loadErrors": [
            ["appointment-workflow", 500],
            ["appointment-workflow", None],
            ["appointment-workflow", None],
            ["appointment-workflow", None],
        ],
        "retryPreserved": True,
        "offlineRetryVisible": True,
        "offlineDraft": "caregiver draft",
        "offlineResult": None,
        "offlineFollowUpResult": None,
        "abortedFollowUpResult": None,
        "followUpStaleMarks": 2,
        "followUpProjectionStale": True,
    }


def _run_appointment_eviction_probe(status: int) -> dict:
    script = "\n".join(
        [
            """
class FakeClassList {
  constructor() { this.values = new Set(); }
  add(name) { this.values.add(name); }
  remove(name) { this.values.delete(name); }
  toggle(name, active) { active ? this.values.add(name) : this.values.delete(name); }
  contains(name) { return this.values.has(name); }
}
function fakeElement() {
  return {
    attributes: {},
    classList: new FakeClassList(),
    className: '',
    dataset: {},
    disabled: false,
    hidden: false,
    inert: false,
    innerHTML: '',
    style: {},
    tabIndex: 0,
    textContent: '',
    value: '',
    closest() { return null; },
    remove() {},
    removeAttribute(name) { delete this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, fakeElement());
  return elements.get(id);
};
const appointmentDialog = element('appointment-dialog');
const followUpDialog = element('follow-up-dialog');
const focusedControl = { blurred: false, blur() { this.blurred = true; } };
appointmentDialog.contains = candidate => candidate === focusedControl;
followUpDialog.contains = () => false;
const background = fakeElement();
background.inert = true;
background.attributes['aria-hidden'] = 'true';
background.dataset.dialogAriaHidden = 'true';
const appointmentOverlay = element('appointment-overlay');
appointmentOverlay.classList.add('open');
appointmentOverlay.attributes['aria-hidden'] = 'false';
const followUpOverlay = element('follow-up-overlay');
followUpOverlay.classList.add('open');
followUpOverlay.attributes['aria-hidden'] = 'false';
const body = {
  children: [background, appointmentOverlay, followUpOverlay],
  classList: new FakeClassList(),
};
body.classList.add('dialog-open');
const document = {
  activeElement: focusedControl,
  body,
  getElementById: element,
  querySelectorAll() { return []; },
};

for (const id of [
  'visit-list', 'visit-source-questions', 'visit-question-list',
  'visit-decision-list', 'visit-followup-list', 'follow-up-list', 'follow-up-status'
]) element(id).innerHTML = `SECRET ${id}`;
for (const id of [
  'visit-create-title', 'visit-create-date', 'visit-create-time',
  'visit-create-clinician', 'visit-create-location',
  'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
  'visit-edit-clinician', 'visit-edit-location', 'visit-manual-question',
  'visit-decision-text', 'visit-decision-supersedes', 'visit-followup-text',
  'visit-followup-owner', 'visit-followup-due', 'follow-up-create-text',
  'follow-up-create-owner', 'follow-up-create-due', 'follow-up-edit-owner',
  'follow-up-edit-due', 'follow-up-outcome-text'
]) element(id).value = `SECRET ${id}`;
for (const id of [
  'visit-create-error', 'visit-details-error', 'visit-question-error',
  'visit-decision-error', 'visit-followup-error', 'follow-up-create-error',
  'follow-up-edit-error', 'follow-up-outcome-error'
]) element(id).textContent = `SECRET ${id}`;
element('appointment-dialog-title').textContent = 'SECRET title';
element('appointment-dialog-meta').textContent = 'SECRET clinician and location';
element('appointment-status-message').textContent = 'SECRET status';
element('visit-status-badge').textContent = 'SECRET visit state';
element('appointment-visit-select').innerHTML = '<option>SECRET visit name</option>';
element('appointment-visit-select').value = 'visit-phi';
element('visit-source-appointment').innerHTML = '<option>SECRET imported appointment</option>';
element('visit-source-appointment').value = 'appointment-phi';
element('visit-followup-decision').innerHTML = '<option>SECRET decision</option>';
element('visit-followup-decision').value = 'decision-phi';
element('visit-create-panel').hidden = false;
element('visit-create-toggle').attributes['aria-expanded'] = 'true';
element('appointment-retry').hidden = false;
element('visit-create-retry').hidden = false;
element('visit-decision-cancel-supersede').hidden = false;
element('visit-decision-label').textContent = 'SECRET successor';
element('follow-up-dialog-status').textContent = 'SECRET action status';
element('follow-up-dialog-title').textContent = 'SECRET follow-up title';
element('follow-up-edit-copy').textContent = 'SECRET edit copy';
element('follow-up-outcome-copy').textContent = 'SECRET outcome copy';
element('follow-up-outcome-guidance').textContent = 'SECRET outcome guidance';
element('follow-up-retry').hidden = false;
element('follow-up-dialog-retry').hidden = false;
element('follow-up-outcome-kind').value = 'clinician_attributed';
for (const id of [
  'follow-up-create-form', 'follow-up-edit-form', 'follow-up-outcome-form'
]) element(id).hidden = false;
for (const name of ['questions', 'decisions', 'followups']) {
  element(`appointment-tab-${name}`);
  element(`appointment-panel-${name}`);
}

let selectedTaskId = 'patient-task';
let currentReportText = 'patient report';
let currentReceipt = { patient: true };
let pendingSummary = { patient: true };
let latestProfileRevision = 41;
let latestResearchUpdate = { patient: true };
let patientEvidence = { patient: true };
let allBiomarkers = [{ patient: true }];
let workflowRevision = 17;
let visitsById = new Map([['visit-phi', { patient: true }]]);
let appointmentOptions = [{ patient: true }];
let appointmentQuestionSources = [{ patient: true }];
let questionLoadEpoch = 3;
let generatedQuestionsUnavailable = true;
let followUpsById = new Map([['follow-up-phi', { patient: true }]]);
let followUpFilter = 'active';
let followUpLoadEpoch = 3;
let followUpProjectionStale = true;
let selectedFollowUpId = 'follow-up-phi';
let followUpSelectionEpoch = 4;
let followUpDialogOpen = true;
let followUpDialogMode = 'outcome';
let followUpOutcomeStatus = 'completed';
const pendingFollowUpIntentRef = { body: { text: 'SECRET pending body' } };
let pendingFollowUpIntent = pendingFollowUpIntentRef;
const activeFollowUpIntentRef = { body: { text: 'SECRET active body' } };
let activeFollowUpIntent = activeFollowUpIntentRef;
let followUpMutationPending = true;
let followUpDrafts = new Map([['outcome:follow-up-phi:completed', { patient: true }]]);
let selectedVisitId = 'visit-phi';
let visitSelectionEpoch = 8;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'decisions';
const pendingWorkflowIntentRef = { body: { text: 'SECRET pending workflow body' } };
let pendingWorkflowIntent = pendingWorkflowIntentRef;
const activeWorkflowIntentRef = { body: { text: 'SECRET active workflow body' } };
let activeWorkflowIntent = activeWorkflowIntentRef;
let workflowMutationPending = true;
let appointmentDrafts = new Map([['visit-phi', { patient: true }]]);
let chatHistory = [{ patient: true }];
let chatHistoryRevision = 41;
let chatOpen = true;
let taskSelectionEpoch = 2;
let phiEpoch = 5;
let summaryLoadEpoch = 2;
let lastDialogTrigger = { patient: true };
let activeDialogSurface = appointmentDialog;

function renderLatestResearchUpdate() {}
function clearFreshnessProjection() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
function setFollowUpMutationBusy() {}
function updateAppointmentFormValidity() {}
""",
            _executable_function_source("workflowIntentCanRender", "refreshClinicalWorkflowState"),
            _executable_function_source("consumeWorkflowResponse", "handleWorkflowConflict"),
            _function_source("evictClientPhi", "renderLatestResearchUpdate"),
            """
(async () => {
  const authStatus = Number(process.argv[1]);
  const lateIntent = {
    visitId: 'visit-phi',
    requestPhiEpoch: phiEpoch,
    requestVisitEpoch: visitSelectionEpoch,
  };
  evictClientPhi({ status: authStatus });
  const lateResults = await Promise.all([
    consumeWorkflowResponse({
      workflow_revision: 101,
      profile_revision: 102,
      visit: { id: 'visit-phi', title: 'SECRET late visit' },
    }, lateIntent),
    consumeWorkflowResponse({
      workflow_revision: 103,
      profile_revision: 104,
      item: { id: 'followup-phi', visit_id: 'visit-phi', text: 'SECRET late follow-up' },
    }, lateIntent),
    consumeWorkflowResponse({
      workflow_revision: 105,
      profile_revision: 106,
      item: { id: 'visit-phi', question_snapshots: [{ text: 'SECRET late question' }] },
    }, lateIntent),
  ]);
  const projectionIds = [
    'appointment-dialog-title', 'appointment-dialog-meta',
    'appointment-status-message', 'visit-status-badge',
    'appointment-visit-select', 'visit-source-appointment',
    'visit-followup-decision', 'visit-list', 'visit-source-questions',
    'visit-question-list', 'visit-decision-list', 'visit-followup-list',
    'visit-create-error', 'visit-details-error', 'visit-question-error',
    'visit-decision-error', 'visit-followup-error', 'visit-decision-label',
    'follow-up-list', 'follow-up-status', 'follow-up-dialog-status',
    'follow-up-dialog-title', 'follow-up-edit-copy', 'follow-up-outcome-copy',
    'follow-up-outcome-guidance', 'follow-up-create-error',
    'follow-up-edit-error', 'follow-up-outcome-error'
  ];
  const formIds = [
    'visit-create-title', 'visit-create-date', 'visit-create-time',
    'visit-create-clinician', 'visit-create-location',
    'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
    'visit-edit-clinician', 'visit-edit-location', 'visit-manual-question',
    'visit-decision-text', 'visit-decision-supersedes', 'visit-followup-text',
    'visit-followup-owner', 'visit-followup-due', 'follow-up-create-text',
    'follow-up-create-owner', 'follow-up-create-due', 'follow-up-edit-owner',
    'follow-up-edit-due', 'follow-up-outcome-text'
  ];
  console.log(JSON.stringify({
    lateResults,
    phiEpoch,
    workflowRevision,
    latestProfileRevision,
    mapsEmpty: visitsById.size === 0
      && appointmentOptions.length === 0
      && appointmentQuestionSources.length === 0
      && followUpsById.size === 0,
    selectionCleared: selectedVisitId === null
      && appointmentDrafts.size === 0
      && selectedFollowUpId === null
      && followUpDrafts.size === 0,
    intentCleared: pendingWorkflowIntent === null
      && workflowMutationPending === false
      && pendingFollowUpIntent === null
      && activeFollowUpIntent === null
      && followUpMutationPending === false,
    intentBodiesScrubbed: Object.keys(pendingFollowUpIntentRef.body).length === 0
      && Object.keys(activeFollowUpIntentRef.body).length === 0
      && Object.keys(pendingWorkflowIntentRef.body).length === 0
      && Object.keys(activeWorkflowIntentRef.body).length === 0,
    projectionsScrubbed: projectionIds.every(id => {
      const node = element(id);
      return !`${node.innerHTML} ${node.textContent} ${node.value}`.includes('SECRET');
    }),
    formsScrubbed: formIds.every(id => element(id).value === ''),
    overlayClosed: !appointmentOverlay.classList.contains('open')
      && appointmentOverlay.attributes['aria-hidden'] === 'true'
      && !followUpOverlay.classList.contains('open')
      && followUpOverlay.attributes['aria-hidden'] === 'true',
    overlayInert: appointmentOverlay.inert && followUpOverlay.inert,
    dialogInert: appointmentDialog.inert && followUpDialog.inert,
    focusBlurred: focusedControl.blurred,
    refsCleared: activeDialogSurface === null && lastDialogTrigger === null,
    bodyReset: !body.classList.contains('dialog-open')
      && background.inert === false
      && !('aria-hidden' in background.attributes)
      && !('dialogAriaHidden' in background.dataset),
    createClosed: element('visit-create-panel').hidden
      && element('visit-create-toggle').attributes['aria-expanded'] === 'false',
    retriesHidden: element('appointment-retry').hidden
      && element('visit-create-retry').hidden
      && element('follow-up-retry').hidden
      && element('follow-up-dialog-retry').hidden,
    followUpFormsHidden: element('follow-up-create-form').hidden
      && element('follow-up-edit-form').hidden
      && element('follow-up-outcome-form').hidden,
    questionsTabReset: element('appointment-tab-questions').attributes['aria-selected']
      === 'true'
      && element('appointment-panel-questions').hidden === false
      && element('appointment-panel-decisions').hidden === true
      && element('appointment-panel-followups').hidden === true,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(
        ["node", "-e", script, str(status)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_eviction_scrubs_appointment_phi_and_rejects_all_late_successes(status):
    result = _run_appointment_eviction_probe(status)

    assert result == {
        "lateResults": [False, False, False],
        "phiEpoch": 6,
        "workflowRevision": None,
        "latestProfileRevision": None,
        "mapsEmpty": True,
        "selectionCleared": True,
        "intentCleared": True,
        "intentBodiesScrubbed": True,
        "projectionsScrubbed": True,
        "formsScrubbed": True,
        "overlayClosed": True,
        "overlayInert": True,
        "dialogInert": True,
        "focusBlurred": True,
        "refsCleared": True,
        "bodyReset": True,
        "createClosed": True,
        "retriesHidden": True,
        "followUpFormsHidden": True,
        "questionsTabReset": True,
    }


def _run_appointment_behavior_probe() -> dict:
    script = "\n".join(
        [
            """
let selectedVisitId = 'visit-1';
let visitsById = new Map([['visit-1', {
  id: 'visit-1',
  token: 'visit-token',
  question_snapshots: [
    { id: 'q-1', token: 'token-1', pinned: false, order: 0, created_at: '1' },
    { id: 'q-2', token: 'token-2', pinned: false, order: 1, created_at: '2' },
    { id: 'q-3', token: 'token-3', pinned: false, order: 2, created_at: '3' },
  ],
}]]);
let appointmentQuestionSources = [
  { id: 'stale', source: 'ai', stale: true, text: 'STALE PATIENT TEXT', rationale: 'SECRET' },
  {
    id: 'current',
    source: 'ai',
    stale: false,
    text: 'Current question',
    source_token: 'source-token',
    generation_job_id: 'generation-current',
    source_profile_revision: 7,
  },
];
let latestProfileRevision = 7;
let generatedQuestionsUnavailable = false;
class FakeClassList {
  constructor() { this.values = new Set(); }
  toggle(name, active) { active ? this.values.add(name) : this.values.delete(name); }
  contains(name) { return this.values.has(name); }
}
function fakeTabElement() {
  return {
    classList: new FakeClassList(),
    hidden: false,
    tabIndex: -1,
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const elements = new Map([['visit-source-questions', { innerHTML: '' }]]);
for (const name of ['questions', 'decisions', 'followups']) {
  elements.set(`appointment-tab-${name}`, fakeTabElement());
  elements.set(`appointment-panel-${name}`, fakeTabElement());
}
const document = { getElementById(id) { return elements.get(id) || null; } };
const submissions = [];
let activeAppointmentTab = 'questions';
function captureAppointmentDraft() {}
function escHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
async function submitWorkflowMutation(url, body, visitId, method) {
  submissions.push({ url, body, visitId, method });
}
""",
            _function_source("currentVisit", "visitStatusLabel"),
            _function_source("sortedVisitQuestions", "linkableAppointment"),
            _executable_function_source("persistVisitQuestionOrder", "reorderedQuestionList"),
            _executable_function_source("reorderedQuestionList", "moveVisitQuestion"),
            _function_source("generatedQuestionIsCurrent", "projectQuestionChoices"),
            _executable_function_source("renderVisitSourceQuestions", "addGeneratedVisitQuestion"),
            _function_source("switchAppointmentTab", "handleAppointmentTabKeydown"),
            """
(async () => {
  const ordered = reorderedQuestionList('q-3', 0);
  await persistVisitQuestionOrder(ordered);
  renderVisitSourceQuestions();
  switchAppointmentTab('decisions');
  console.log(JSON.stringify({
    ordered: ordered.map(item => item.id),
    submission: submissions[0],
    staleRedacted: !elements.get('visit-source-questions').innerHTML.includes('STALE PATIENT TEXT')
      && !elements.get('visit-source-questions').innerHTML.includes('SECRET'),
    currentVisible: elements.get('visit-source-questions').innerHTML.includes('Current question'),
    activeTab: activeAppointmentTab,
    decisionSelected: elements.get('appointment-tab-decisions').attributes['aria-selected'],
    decisionPanelHidden: elements.get('appointment-panel-decisions').hidden,
    questionsPanelHidden: elements.get('appointment-panel-questions').hidden,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _run_decision_lifecycle_probe() -> dict:
    script = "\n".join(
        [
            """
const decisions = ['active', 'needs_confirmation', 'superseded', 'retracted'].map(status => ({
  id: `decision-${status}`,
  text: `${status} decision`,
  status,
  token: `token-${status}`,
}));
const visit = { id: 'visit-1', decisions };
const elements = new Map([
  ['visit-decision-list', { innerHTML: '' }],
  ['visit-followup-decision', { innerHTML: '' }],
  ['visit-decision-text', { value: '' }],
  ['visit-decision-supersedes', { value: '' }],
  ['visit-decision-cancel-supersede', { hidden: true }],
  ['visit-decision-label', { textContent: '' }],
]);
const document = {
  getElementById(id) { return elements.get(id) || null; },
  querySelectorAll() { return []; },
};
const appointmentDrafts = new Map([['visit-1', {
  decisionText: 'Corrected decision wording',
  supersedesId: 'decision-active',
}]]);
let appointmentDialogOpen = true;
let selectedVisitId = 'visit-1';
const decisionSuccessorConflicts = new Set();
function currentVisit() { return visit; }
function updateAppointmentFormValidity() {}
function toggleVisitAnswerText() {}
function safeClassToken(value, fallback = '') {
  return /^[a-z0-9_-]+$/i.test(String(value || '')) ? String(value) : fallback;
}
function escHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
""",
            _function_source("activeDecisionSuccessorId", "restoreAppointmentDraft"),
            _function_source("restoreAppointmentDraft", "openAppointmentWorkspace"),
            _function_source("decisionLifecyclePresentation", "renderVisitDecisions"),
            _function_source("renderVisitDecisions", "prepareDecisionSuccessor"),
            """
renderVisitDecisions();
decisionSuccessorConflicts.add('decision-active');
renderVisitDecisions();
const conflictedHtml = elements.get('visit-decision-list').innerHTML;
decisionSuccessorConflicts.clear();
renderVisitDecisions();
restoreAppointmentDraft(visit);
const activeDraft = {
  supersedesId: elements.get('visit-decision-supersedes').value,
  correctionLabel: elements.get('visit-decision-label').textContent,
  cancelHidden: elements.get('visit-decision-cancel-supersede').hidden,
};
const changedVisit = {
  ...visit,
  decisions: decisions.map(decision => decision.id === 'decision-active'
    ? { ...decision, status: 'needs_confirmation' }
    : decision),
};
revalidateDecisionSuccessorState(changedVisit);
const immediateInvalidation = {
  supersedesId: elements.get('visit-decision-supersedes').value,
  correctionLabel: elements.get('visit-decision-label').textContent,
  cancelHidden: elements.get('visit-decision-cancel-supersede').hidden,
  storedSupersedesId: appointmentDrafts.get('visit-1').supersedesId,
};
restoreAppointmentDraft(changedVisit);
const nonActiveDraft = {
  supersedesId: elements.get('visit-decision-supersedes').value,
  correctionLabel: elements.get('visit-decision-label').textContent,
  cancelHidden: elements.get('visit-decision-cancel-supersede').hidden,
  decisionText: elements.get('visit-decision-text').value,
  storedSupersedesId: appointmentDrafts.get('visit-1').supersedesId,
};
console.log(JSON.stringify({
  lifecycle: Object.fromEntries(decisions.map(({ status }) => [
    status,
    decisionLifecyclePresentation(status),
  ])),
  html: elements.get('visit-decision-list').innerHTML,
  followupOptions: elements.get('visit-followup-decision').innerHTML,
  conflictedHtml,
  activeDraft,
  immediateInvalidation,
  nonActiveDraft,
}));
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_appointment_order_is_atomic_and_stale_generated_text_is_redacted_at_runtime():
    result = _run_appointment_behavior_probe()
    assert result["ordered"] == ["q-3", "q-1", "q-2"]
    assert result["submission"] == {
        "url": "/api/visits/visit-1/questions/order",
        "body": {
            "expected_visit_token": "visit-token",
            "questions": [
                {"id": "q-3", "expected_token": "token-3"},
                {"id": "q-1", "expected_token": "token-1"},
                {"id": "q-2", "expected_token": "token-2"},
            ],
        },
        "visitId": "visit-1",
        "method": "PATCH",
    }
    assert result["staleRedacted"] is True
    assert result["currentVisible"] is True
    assert result["activeTab"] == "decisions"
    assert result["decisionSelected"] == "true"
    assert result["decisionPanelHidden"] is False
    assert result["questionsPanelHidden"] is True


def _run_generated_question_redaction_probe() -> dict:
    script = "\n".join(
        [
            """
class FakeClassList {
  toggle() {}
}

function fakeElement(html = '') {
  return {
    classList: new FakeClassList(),
    hidden: false,
    innerHTML: html,
    textContent: '',
  };
}

const elements = new Map([
  ['q-list', fakeElement()],
  ['q-count-badge', fakeElement()],
  ['visit-source-questions', fakeElement()],
  ['visit-question-list', fakeElement('Accepted generated snapshot: KEEP ACCEPTED')],
  ['chat-messages', fakeElement()],
]);
const document = {
  getElementById(id) { return elements.get(id) || null; },
};
const navigator = { onLine: false };
let phiEpoch = 0;
let taskSelectionEpoch = 0;
let latestProfileRevision = null;
let workflowRevision = null;
let chatHistoryRevision = null;
let chatHistory = [{ patient: true }];
let questionLoadEpoch = 0;
let generatedQuestionsUnavailable = false;
let appointmentDialogOpen = true;
let appointmentQuestionSources = [
  {
    id: 'manual-profile',
    source: 'manual',
    text: 'KEEP MANUAL PROFILE QUESTION',
    category: 'Other',
    priority: 'medium',
    asked: false,
  },
  {
    id: 'old-generated',
    source: 'ai',
    stale: false,
    text: 'OLD GENERATED TEXT',
    rationale: 'OLD SECRET RATIONALE',
    category: 'Treatment',
    priority: 'urgent',
    source_token: 'OLD ACCEPTANCE TOKEN',
    generation_job_id: 'old-generation',
    source_profile_revision: 7,
    asked: false,
  },
];
const visitsById = new Map([['visit-1', {
  question_snapshots: [{ id: 'accepted', text: 'KEEP ACCEPTED SNAPSHOT' }],
}]]);
const appointmentDrafts = new Map([['visit-1', {
  manualQuestion: 'KEEP MANUAL DRAFT',
}]]);
const loadErrors = [];
const fetchQueue = [];

function escHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function safeClassToken(value, fallback = '') {
  const token = String(value == null ? '' : value);
  return /^[a-z0-9_-]+$/i.test(token) ? token : fallback;
}
function translateCategory(value) { return value; }
function reportLoadSuccess() {}
function reportLoadError(scope, error) { loadErrors.push([scope, error.status || error.name]); }
function shouldEvictClientPhi(error) { return error?.status === 401 || error?.status === 403; }
function evictClientPhi() { throw new Error('unexpected auth eviction'); }
function setAppointmentMessage() {}
function workflowIntentCanRender() { return true; }
function captureAppointmentDraft() {}
function clearWorkflowRetry() {}
function redactGeneratedSummaryActions() {}
function loadStatus() { return Promise.resolve(); }
function loadSummary() { return Promise.resolve(); }
function loadTasks() { return Promise.resolve(); }
function loadVisits() { return Promise.resolve(); }
function loadFollowUps() { return Promise.resolve(); }
function advancePatientAuthority(revision) {
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
globalThis.fetch = () => {
  if (!fetchQueue.length) throw new Error('missing queued response');
  return fetchQueue.shift();
};

function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}

function snapshot() {
  const cache = JSON.stringify(appointmentQuestionSources);
  const questions = elements.get('q-list').innerHTML;
  const picker = elements.get('visit-source-questions').innerHTML;
  const rendered = `${cache} ${questions} ${picker}`;
  return {
    cache,
    questions,
    picker,
    generatedQuestionsUnavailable,
    oldGone: !rendered.includes('OLD GENERATED TEXT')
      && !rendered.includes('OLD SECRET RATIONALE')
      && !rendered.includes('OLD ACCEPTANCE TOKEN'),
    staleGone: !rendered.includes('STALE GENERATED TEXT')
      && !rendered.includes('STALE RATIONALE')
      && !rendered.includes('REVISIONLESS TEXT')
      && !rendered.includes('INCOMPLETE RATIONALE'),
    noPriorityLeak: !questions.includes('q-priority-dot urgent'),
    noAcceptanceToken: !picker.includes('data-source-token'),
    noAddAction: !picker.includes('>Add</button>'),
    genericUnavailable: questions.includes('Generated questions unavailable')
      && picker.includes('Generated questions unavailable')
      && picker.includes('>Retry</button>'),
    manualVisible: questions.includes('KEEP MANUAL PROFILE QUESTION'),
    manualCached: cache.includes('KEEP MANUAL PROFILE QUESTION'),
    acceptedSnapshot: visitsById.get('visit-1').question_snapshots[0].text,
    acceptedDom: elements.get('visit-question-list').innerHTML,
    manualDraft: appointmentDrafts.get('visit-1').manualQuestion,
  };
}
""",
            _response_authority_source(),
            _executable_function_source("refreshClinicalWorkflowState", "consumeWorkflowResponse"),
            _executable_function_source("handleWorkflowConflict", "performWorkflowIntent"),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("renderVisitSourceQuestions", "addGeneratedVisitQuestion"),
            _function_source("generatedQuestionIsCurrent", "projectQuestionChoices"),
            _function_source("projectQuestionChoices", "redactGeneratedQuestionChoices"),
            _executable_function_source("redactGeneratedQuestionChoices", "loadQuestions"),
            _executable_function_source("loadQuestions", "renderQuestions"),
            _executable_function_source("renderQuestions", "generateQuestions"),
            _function_source("syncChatRevision", "toggleChat"),
            """
(async () => {
  renderQuestions(appointmentQuestionSources);
  renderVisitSourceQuestions();

  fetchQueue.push(Promise.resolve(response(200, [
    {
      id: 'manual-profile',
      source: 'manual',
      text: 'KEEP MANUAL PROFILE QUESTION',
      category: 'Other',
      priority: 'medium',
      asked: false,
    },
    {
      id: 'old-generated',
      source: 'ai',
      stale: false,
      text: 'OLD GENERATED TEXT',
      rationale: 'OLD SECRET RATIONALE',
      category: 'Treatment',
      priority: 'urgent',
      source_token: 'OLD ACCEPTANCE TOKEN',
      generation_job_id: 'old-generation',
      source_profile_revision: 6,
    },
  ])));
  await loadQuestions();
  const unknownRevision = snapshot();

  fetchQueue.push(Promise.resolve(response(200, [
    {
      id: 'manual-profile',
      source: 'manual',
      text: 'KEEP MANUAL PROFILE QUESTION',
      category: 'Other',
      priority: 'medium',
      asked: false,
    },
    {
      id: 'old-generated',
      source: 'ai',
      stale: false,
      text: 'OLD GENERATED TEXT',
      rationale: 'OLD SECRET RATIONALE',
      category: 'Treatment',
      priority: 'urgent',
      source_token: 'OLD ACCEPTANCE TOKEN',
      generation_job_id: 'old-generation',
      source_profile_revision: 7,
      asked: false,
    },
  ])));
  syncChatRevision(7);
  await new Promise(resolve => setImmediate(resolve));

  let resolveGeneratedConflict;
  fetchQueue.push(new Promise(resolve => { resolveGeneratedConflict = resolve; }));
  const generatedConflictRefresh = handleWorkflowConflict(
    { status: 409, message: 'generated source stale' },
    { body: { source_kind: 'generated' } },
  );
  const generatedMutationConflict = snapshot();
  resolveGeneratedConflict(response(200, [
    {
      id: 'manual-profile',
      source: 'manual',
      text: 'KEEP MANUAL PROFILE QUESTION',
      category: 'Other',
      priority: 'medium',
      asked: false,
    },
    {
      id: 'old-generated',
      source: 'ai',
      stale: false,
      text: 'OLD GENERATED TEXT',
      rationale: 'OLD SECRET RATIONALE',
      category: 'Treatment',
      priority: 'urgent',
      source_token: 'OLD ACCEPTANCE TOKEN',
      generation_job_id: 'old-generation',
      source_profile_revision: 7,
      asked: false,
    },
  ]));
  await generatedConflictRefresh;

  let resolveLateOld;
  fetchQueue.push(new Promise(resolve => { resolveLateOld = resolve; }));
  const lateOldRequest = loadQuestions();

  fetchQueue.push(Promise.reject(new TypeError('offline')));
  appointmentDialogOpen = false;
  phiEpoch += 1;
  taskSelectionEpoch += 1;
  syncChatRevision(8, true, false);
  const revisionRefresh = refreshClinicalWorkflowState(8);
  const immediateAfterRevision = snapshot();
  appointmentDialogOpen = true;
  await revisionRefresh;
  const offline = snapshot();

  const abortError = new Error('aborted');
  abortError.name = 'AbortError';
  fetchQueue.push(Promise.reject(abortError));
  await loadQuestions();
  const aborted = snapshot();

  resolveLateOld(response(200, [{
    id: 'old-generated',
    source: 'ai',
    stale: false,
    text: 'OLD GENERATED TEXT',
    rationale: 'OLD SECRET RATIONALE',
    category: 'Treatment',
    priority: 'urgent',
    source_token: 'OLD ACCEPTANCE TOKEN',
    generation_job_id: 'old-generation',
    source_profile_revision: 7,
  }]));
  await lateOldRequest;
  const afterLateOld = snapshot();

  fetchQueue.push(Promise.resolve(response(409, { error: 'stale revision' })));
  await loadQuestions();
  const conflict = snapshot();

  fetchQueue.push(Promise.resolve(response(200, [
    {
      id: 'manual-profile',
      source: 'manual',
      text: 'KEEP MANUAL PROFILE QUESTION',
      category: 'Other',
      priority: 'medium',
      asked: false,
    },
    {
      id: 'stale-generated',
      source: 'ai',
      stale: true,
      text: 'STALE GENERATED TEXT',
      rationale: 'STALE RATIONALE',
      category: 'Treatment',
      priority: 'urgent',
      source_token: 'STALE TOKEN',
      generation_job_id: 'stale-generation',
      source_profile_revision: 7,
    },
    {
      id: 'revisionless-generated',
      source: 'ai',
      stale: false,
      text: 'REVISIONLESS TEXT',
      rationale: 'REVISIONLESS RATIONALE',
      category: 'Diagnostics',
      priority: 'urgent',
      source_token: 'REVISIONLESS TOKEN',
      generation_job_id: 'new-generation',
    },
    {
      id: 'incomplete-generated',
      source: 'ai',
      stale: false,
      text: '   ',
      rationale: 'INCOMPLETE RATIONALE',
      category: 'Trials',
      priority: 'urgent',
      source_token: 'INCOMPLETE TOKEN',
      generation_job_id: 'new-generation',
      source_profile_revision: 8,
    },
  ])));
  appointmentDialogOpen = false;
  await loadQuestions();
  const staleAndRevisionless = snapshot();
  appointmentDialogOpen = true;

  fetchQueue.push(Promise.resolve(response(200, [
    {
      id: 'manual-profile',
      source: 'manual',
      text: 'KEEP MANUAL PROFILE QUESTION',
      category: 'Other',
      priority: 'medium',
      asked: false,
    },
    {
      id: 'new-generated',
      source: 'ai',
      stale: false,
      text: 'NEW CURRENT QUESTION',
      rationale: 'CURRENT RATIONALE',
      category: 'Monitoring',
      priority: 'high',
      source_token: 'NEW CURRENT TOKEN',
      generation_job_id: 'new-generation',
      source_profile_revision: 8,
      asked: false,
    },
  ])));
  await loadQuestions();
  const current = snapshot();

  let resolveMissingRevision;
  fetchQueue.push(new Promise(resolve => { resolveMissingRevision = resolve; }));
  syncChatRevision(null);
  const missingRevision = snapshot();
  resolveMissingRevision(response(200, [{
    id: 'new-generated',
    source: 'ai',
    stale: false,
    text: 'NEW CURRENT QUESTION',
    source_token: 'NEW CURRENT TOKEN',
    generation_job_id: 'new-generation',
    source_profile_revision: 8,
  }]));
  await new Promise(resolve => setImmediate(resolve));

  console.log(JSON.stringify({
    unknownRevision,
    generatedMutationConflict,
    immediateAfterRevision,
    offline,
    aborted,
    afterLateOld,
    conflict,
    staleAndRevisionless,
    current,
    missingRevision,
    loadErrors,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_generated_question_choices_fail_closed_across_revision_and_reload_paths():
    result = _run_generated_question_redaction_probe()

    for phase_name in (
        "unknownRevision",
        "generatedMutationConflict",
        "immediateAfterRevision",
        "offline",
        "aborted",
        "afterLateOld",
        "conflict",
        "staleAndRevisionless",
    ):
        phase = result[phase_name]
        assert phase["oldGone"] is True, phase_name
        assert phase["staleGone"] is True, phase_name
        assert phase["noPriorityLeak"] is True, phase_name
        assert phase["noAcceptanceToken"] is True, phase_name
        assert phase["noAddAction"] is True, phase_name
        assert phase["genericUnavailable"] is True, phase_name
        assert phase["manualVisible"] is True, phase_name
        assert phase["manualCached"] is True, phase_name
        assert phase["acceptedSnapshot"] == "KEEP ACCEPTED SNAPSHOT", phase_name
        assert phase["acceptedDom"] == "Accepted generated snapshot: KEEP ACCEPTED", phase_name
        assert phase["manualDraft"] == "KEEP MANUAL DRAFT", phase_name

    current = result["current"]
    assert current["generatedQuestionsUnavailable"] is False
    assert "NEW CURRENT QUESTION" in current["questions"]
    assert "NEW CURRENT QUESTION" in current["picker"]
    assert "NEW CURRENT TOKEN" in current["picker"]
    assert ">Add</button>" in current["picker"]
    assert "OLD GENERATED TEXT" not in current["cache"]
    assert current["manualDraft"] == "KEEP MANUAL DRAFT"
    assert current["acceptedSnapshot"] == "KEEP ACCEPTED SNAPSHOT"
    assert result["missingRevision"] == current
    assert result["loadErrors"] == [
        ["appointment-workflow", 409],
        ["questions", "TypeError"],
        ["questions", "AbortError"],
        ["questions", 409],
    ]


def test_decision_controls_match_the_server_lifecycle_matrix_at_runtime():
    result = _run_decision_lifecycle_probe()
    lifecycle = result["lifecycle"]

    assert "Needs confirmation" in lifecycle["active"]["controls"]
    assert "Correct with successor" in lifecycle["active"]["controls"]
    assert "Retract" in lifecycle["active"]["controls"]
    assert "Confirm active" in lifecycle["needs_confirmation"]["controls"]
    assert "Retract" in lifecycle["needs_confirmation"]["controls"]
    assert "Correct with successor" not in lifecycle["needs_confirmation"]["controls"]
    assert lifecycle["superseded"]["controls"] == ""
    assert lifecycle["retracted"]["controls"] == ""
    assert "only after confirmation" in lifecycle["needs_confirmation"]["copy"]
    assert "immutable history" in lifecycle["superseded"]["copy"]
    assert "immutable history" in lifecycle["retracted"]["copy"]

    assert result["html"].count("Correct with successor") == 1
    assert result["html"].count("Confirm active") == 1
    assert result["html"].count(">Retract</button>") == 2
    assert "decision-active" in result["followupOptions"]
    assert "decision-needs_confirmation" in result["followupOptions"]
    assert "decision-superseded" not in result["followupOptions"]
    assert "decision-retracted" not in result["followupOptions"]
    assert "Correct with successor" not in result["conflictedHtml"]
    assert "Reload this changed decision" in result["conflictedHtml"]
    assert result["activeDraft"] == {
        "supersedesId": "decision-active",
        "correctionLabel": "Correct with a successor decision",
        "cancelHidden": False,
    }
    assert result["immediateInvalidation"] == {
        "supersedesId": "",
        "correctionLabel": "Caregiver-entered decision attributed to the clinician",
        "cancelHidden": True,
        "storedSupersedesId": "",
    }
    assert result["nonActiveDraft"] == {
        "supersedesId": "",
        "correctionLabel": "Caregiver-entered decision attributed to the clinician",
        "cancelHidden": True,
        "decisionText": "Corrected decision wording",
        "storedSupersedesId": "",
    }
    consume = _function_source("consumeWorkflowResponse", "handleWorkflowConflict")
    assert "revalidateDecisionSuccessorState(data.visit)" in consume
    assert "renderAppointmentWorkspace()" in consume
    assert consume.index("revalidateDecisionSuccessorState(data.visit)") < consume.index(
        "if (authority.profileAdvanced)"
    )
    assert consume.index("renderAppointmentWorkspace()") < consume.index(
        "if (authority.profileAdvanced)"
    )
    conflicts = _function_source("handleWorkflowConflict", "performWorkflowIntent")
    assert "decisionSuccessorConflicts.add(intent.body.supersedes_id)" in conflicts
    assert "renderVisitDecisions()" in conflicts
    successor = _function_source("prepareDecisionSuccessor", "cancelDecisionSuccessor")
    assert "decision.status !== 'active'" in successor
    assert "decisionSuccessorConflicts.has(id)" in successor
    assert "loadVisits()" in successor


def test_narrow_appointment_order_controls_render_without_overflow_and_keep_focus():
    playwright_api = pytest.importorskip("playwright.sync_api")
    markup = """
      <main class="appointment-dialog">
        <div class="appointment-dialog-body">
          <section class="appointment-tab-panel active">
            <article class="visit-question">
              <div class="visit-question-order">
                <button class="button secondary" data-control="move-up">Move up</button>
                <button class="button secondary" data-control="move-down">Move down</button>
                <label><span>Rank</span><select data-control="rank"><option>1</option></select></label>
              </div>
            </article>
          </section>
        </div>
      </main>
    """

    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 800})
        page.set_content(markup)
        page.add_style_tag(content=CSS)

        controls = page.locator(".visit-question-order .button, .visit-question-order select")
        narrow_heights = controls.evaluate_all(
            "(items) => items.map(item => item.getBoundingClientRect().height)"
        )
        overflow = page.evaluate(
            """() => ({
              document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
              dialog: document.querySelector('.appointment-dialog').scrollWidth
                - document.querySelector('.appointment-dialog').clientWidth,
              question: document.querySelector('.visit-question').scrollWidth
                - document.querySelector('.visit-question').clientWidth,
            })"""
        )
        assert len(narrow_heights) == 3
        assert all(height >= 44 for height in narrow_heights)
        assert overflow == {"document": 0, "dialog": 0, "question": 0}

        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.dataset.control") == "move-up"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.dataset.control") == "move-down"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.dataset.control") == "rank"
        focus = page.evaluate(
            """() => {
              const style = getComputedStyle(document.activeElement);
              return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
            }"""
        )
        assert focus["style"] != "none"
        assert focus["width"] >= 3

        page.set_viewport_size({"width": 1024, "height": 800})
        desktop_heights = controls.evaluate_all(
            "(items) => items.map(item => item.getBoundingClientRect().height)"
        )
        assert all(35 <= height < 44 for height in desktop_heights)
        browser.close()


def test_appointment_mutations_use_stable_contracts_and_explicit_retry_only():
    mutation = _function_source("newMutationId", "setAppointmentMessage")
    intent = _function_source("createWorkflowIntent", "workflowIntentCanRender")
    performer = _function_source("performWorkflowIntent", "submitWorkflowMutation")
    retry = _function_source("retryWorkflowIntent", "readJsonResponse")
    invalidation = _function_source(
        "invalidateWorkflowRetryOnDraftChange", "setAppointmentMutationBusy"
    )
    generated = _function_source("addGeneratedVisitQuestion", "addManualVisitQuestion")
    ordering = _function_source("persistVisitQuestionOrder", "reorderedQuestionList")

    assert "crypto?.randomUUID" in mutation
    assert "mutation_id: newMutationId()" in intent
    assert "workflowMutationPending" in performer
    assert "setAppointmentMutationBusy(true)" in performer
    assert "response.status === 409" not in performer
    assert "error?.status === 409" in performer
    assert "performWorkflowIntent(intent, true)" in retry
    assert "clearWorkflowRetry()" in invalidation
    assert "The draft changed" in invalidation
    assert "addEventListener('input', handleAppointmentDraftChange)" in APP_JS
    assert "expected_source_token: sourceToken" in generated
    assert "source_question_id: sourceId" in generated
    assert "text:" not in generated
    assert "/questions/order" in ordering
    assert "questions: ordered.map" in ordering
    assert "/questions/${encodeURIComponent" not in ordering


def test_appointment_revision_epoch_conflict_and_eviction_guards_are_complete():
    context = _function_source("workflowIntentCanRender", "refreshClinicalWorkflowState")
    refresh = _function_source("refreshClinicalWorkflowState", "consumeWorkflowResponse")
    consume = _function_source("consumeWorkflowResponse", "handleWorkflowConflict")
    conflicts = _function_source("handleWorkflowConflict", "performWorkflowIntent")
    performer = _function_source("performWorkflowIntent", "submitWorkflowMutation")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")

    assert "requestPhiEpoch !== phiEpoch" in context
    assert "requestVisitEpoch !== visitSelectionEpoch" in context
    assert consume.index("if (!workflowIntentCanRender(intent)) return false") < consume.index(
        "captureAppointmentDraft()"
    )
    assert consume.index("if (!workflowIntentCanRender(intent)) return false") < consume.index(
        "authorizePatientResponse(intent, data, { workflow: 'targeted' })"
    )
    assert "return true" in consume
    assert conflicts.index("if (!workflowIntentCanRender(intent)) return false") < conflicts.index(
        "clearWorkflowRetry()"
    )
    consumed_guard = performer.index("if (!consumed) return null")
    assert consumed_guard < performer.index("clearWorkflowRetry()", consumed_guard)
    catch_source = performer[performer.index("catch (error)") :]
    assert catch_source.index("if (!workflowIntentCanRender(intent)) return null") < (
        catch_source.index("error?.status === 409")
    )
    authority = _function_source("advancePatientAuthority", "authorizePatientResponse")
    assert "phiEpoch += 1" in authority
    assert "taskSelectionEpoch += 1" in authority
    assert "syncChatRevision(revision, true, false)" in authority
    assert refresh.index("redactGeneratedQuestionChoices()") < refresh.index("loadQuestions()")
    assert "loadSummary()" in refresh
    assert "loadTasks()" in refresh
    assert "loadVisits()" in refresh
    assert "loadFollowUps()" in refresh
    assert "loadQuestions()" in conflicts
    assert conflicts.index("redactGeneratedQuestionChoices()") < conflicts.index(
        "Promise.allSettled"
    )
    assert "performWorkflowIntent" not in conflicts

    for expression in (
        "workflowRevision = null",
        "visitsById = new Map()",
        "appointmentOptions = []",
        "appointmentQuestionSources = []",
        "followUpsById = new Map()",
        "selectedVisitId = null",
        "visitSelectionEpoch += 1",
        "appointmentDialogOpen = false",
        "pendingWorkflowIntent = null",
        "workflowMutationPending = false",
        "appointmentDrafts = new Map()",
        "decisionSuccessorConflicts = new Set()",
        "clear('visit-list')",
        "clear('visit-question-list')",
        "clear('visit-decision-list')",
        "clear('visit-followup-list')",
    ):
        assert expression in eviction


def test_appointment_loops_use_arrays_and_live_drafts_survive_rerenders():
    assert not re.search(r"for \(const [^)]+ of \(", APP_JS)
    retry_clear = _function_source("clearWorkflowRetry", "invalidateWorkflowRetryOnDraftChange")
    assert "['appointment-retry', 'visit-create-retry']" in retry_clear
    tabs = _function_source("switchAppointmentTab", "handleAppointmentTabKeydown")
    assert "['questions', 'decisions', 'followups']" in tabs

    capture = _function_source("captureAppointmentDraft", "restoreAppointmentDraft")
    restore = _function_source("restoreAppointmentDraft", "openAppointmentWorkspace")
    consume = _function_source("consumeWorkflowResponse", "handleWorkflowConflict")
    assert "querySelectorAll('#visit-question-list .visit-question')" in capture
    assert "answers[row.dataset.visitQuestionId]" in capture
    assert "answers," in capture
    assert "Object.entries(values.answers || {})" in restore
    assert "toggleVisitAnswerText(status)" in restore
    assert "captureAppointmentDraft()" in consume
    assert "addEventListener('change', handleAppointmentDraftChange)" in APP_JS


def test_appointment_provenance_and_stale_source_wording_are_fixed():
    assert APP_JS.count("Caregiver-entered · attributed to clinician · unverified") >= 2
    source_picker = _function_source("renderVisitSourceQuestions", "addGeneratedVisitQuestion")
    assert "Generated questions unavailable" in source_picker
    assert "Reload the current questions" in source_picker
    unavailable = source_picker[
        source_picker.index("if (generatedQuestionsUnavailable)") : source_picker.index(
            "container.innerHTML = currentRows.join"
        )
    ]
    assert "question.text" not in unavailable
    assert "question.rationale" not in unavailable
    assert "data-source-token" not in unavailable
    assert ">Add</button>" not in unavailable
    accepted = _function_source("renderVisitQuestions", "toggleVisitAnswerText")
    assert "Generated snapshot · generation" in accepted
    assert "Manual caregiver question" in accepted


def test_appointment_flows_never_call_deferred_or_legacy_routes():
    assert "/api/visits/${encodeURIComponent(visit.id)}/follow-ups" in APP_JS
    assert "followUpItems().filter" in APP_JS
    assert "/api/alerts/resolve/" not in APP_JS
    assert "/api/follow-ups/${encodeURIComponent(action.id)}" in APP_JS
    assert "Save as follow-up" not in APP_JS


def _run_follow_up_request_probe() -> list[dict]:
    script = "\n".join(
        [
            """
const elements = new Map();
const element = (id, value = '') => {
  if (!elements.has(id)) elements.set(id, { value, textContent: '', disabled: false });
  return elements.get(id);
};
const document = { getElementById: element };
const calls = [];
let selectedFollowUpId = 'action-1';
let followUpDialogMode = 'outcome';
let followUpOutcomeStatus = 'completed';
let followUpProjectionStale = false;
const followUpsById = new Map([['action-1', {
  id: 'action-1',
  token: 'full-action-token',
  owner: 'Old owner',
  due_date: '2026-08-10',
  status: 'in_progress',
}]]);

element('follow-up-create-text').value = 'Contact the clinic to confirm timing';
element('follow-up-create-owner').value = 'Caregiver';
element('follow-up-create-due').value = '2026-08-15';
element('follow-up-edit-owner').value = 'Family';
element('follow-up-edit-due').value = '2026-08-18';
element('follow-up-outcome-kind').value = 'clinician_attributed';
element('follow-up-outcome-text').value = 'The clinician confirmed the next review date';

function setFormError() {}
function updateFollowUpFormValidity() {}
function followUpDraftKey(mode, actionId, status) {
  if (mode === 'create') return 'create';
  if (mode === 'outcome') return `outcome:${actionId}:${status}`;
  return `edit:${actionId}`;
}
async function submitFollowUpMutation(url, body, options = {}) {
  calls.push({ url, body, options });
  return { item: { id: 'saved' } };
}
""",
            _executable_function_source("acceptGeneratedFollowUp", "renderClaimEvidence"),
            _executable_function_source("createManualFollowUp", "saveFollowUpDetails"),
            _executable_function_source("saveFollowUpDetails", "submitFollowUpOutcome"),
            _executable_function_source("submitFollowUpOutcome", "changeFollowUpStatus"),
            _executable_function_source("changeFollowUpStatus", "renderAppointmentOptions"),
            """
(async () => {
  await acceptGeneratedFollowUp({
    dataset: {
      generatedActionSourceId: 'sumact-stable',
      generatedActionSourceToken: 'semantic-source-token',
    },
  });
  await createManualFollowUp();
  await saveFollowUpDetails();
  await submitFollowUpOutcome();
  await changeFollowUpStatus({
    dataset: { followUpId: 'action-1', followUpToken: 'full-action-token' },
  }, 'open');
  console.log(JSON.stringify(calls));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_requests_use_stable_ids_tokens_and_exact_bodies():
    calls = _run_follow_up_request_probe()

    assert calls == [
        {
            "url": "/api/follow-ups",
            "body": {
                "origin_kind": "executive_summary_action",
                "source_id": "sumact-stable",
                "expected_source_token": "semantic-source-token",
            },
            "options": {"sourceKind": "generated"},
        },
        {
            "url": "/api/follow-ups",
            "body": {
                "origin_kind": "manual",
                "text": "Contact the clinic to confirm timing",
                "owner": "Caregiver",
                "due_date": "2026-08-15",
            },
            "options": {"draftKey": "create"},
        },
        {
            "url": "/api/follow-ups/action-1",
            "body": {
                "expected_token": "full-action-token",
                "owner": "Family",
                "due_date": "2026-08-18",
            },
            "options": {
                "method": "PATCH",
                "actionId": "action-1",
                "draftKey": "edit:action-1",
            },
        },
        {
            "url": "/api/follow-ups/action-1",
            "body": {
                "expected_token": "full-action-token",
                "status": "completed",
                "outcome": {
                    "kind": "clinician_attributed",
                    "text": "The clinician confirmed the next review date",
                },
            },
            "options": {
                "method": "PATCH",
                "actionId": "action-1",
                "draftKey": "outcome:action-1:completed",
            },
        },
        {
            "url": "/api/follow-ups/action-1",
            "body": {"expected_token": "full-action-token", "status": "open"},
            "options": {"method": "PATCH", "actionId": "action-1"},
        },
    ]
    assert "generatedActionSourceId" not in json.dumps(calls[0]["body"])
    assert "text" not in calls[0]["body"]


def _run_follow_up_offline_projection_probe() -> dict:
    script = "\n".join(
        [
            """
class FakeClassList {
  constructor() { this.values = new Set(); }
  add(name) { this.values.add(name); }
  remove(name) { this.values.delete(name); }
  toggle(name, active) { active ? this.values.add(name) : this.values.delete(name); }
  contains(name) { return this.values.has(name); }
}
function fakeElement() {
  return {
    attributes: {},
    classList: new FakeClassList(),
    className: '',
    dataset: {},
    disabled: false,
    hidden: false,
    inert: false,
    innerHTML: '',
    textContent: '',
    value: '',
    removeAttribute(name) { delete this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, fakeElement());
  return elements.get(id);
};
for (const id of [
  'follow-up-list', 'follow-up-status', 'follow-up-dialog-status',
  'follow-up-create-button', 'follow-up-create-submit', 'follow-up-edit-submit',
  'follow-up-outcome-submit', 'follow-up-retry-button',
  'follow-up-dialog-retry-button', 'follow-up-create-text',
  'follow-up-create-owner', 'follow-up-create-due', 'follow-up-edit-owner',
  'follow-up-edit-due', 'follow-up-outcome-kind', 'follow-up-outcome-text',
  'visit-followup-list', 'visit-followup-submit', 'visit-followup-text',
  'visit-create-title', 'visit-manual-question', 'visit-decision-text',
  'visit-create-submit', 'visit-manual-question-submit', 'visit-decision-submit',
  'follow-up-create-error', 'follow-up-edit-error', 'follow-up-outcome-error',
  'visit-create-error', 'visit-question-error', 'visit-decision-error',
  'visit-followup-error'
]) element(id);
for (const name of ['active', 'completed', 'cancelled', 'all']) {
  element(`follow-up-count-${name}`);
}

function summaryRow(sourceId) {
  const button = fakeElement();
  button.textContent = 'Add to follow-through';
  return {
    button,
    classList: new FakeClassList(),
    dataset: { generatedActionSourceId: sourceId },
    querySelector(selector) { return selector === '.action-accept-btn' ? button : null; },
  };
}
const acceptedRow = summaryRow('summary-accepted');
const availableRow = summaryRow('summary-available');
const background = fakeElement();
background.inert = true;
background.attributes['aria-hidden'] = 'true';
background.dataset.dialogAriaHidden = 'true';
const body = { children: [background], classList: new FakeClassList() };
body.classList.add('dialog-open');
const document = {
  activeElement: null,
  body,
  getElementById: element,
  querySelectorAll(selector) {
    if (selector === '[data-generated-action-source-id]') {
      return [acceptedRow, availableRow];
    }
    return [];
  },
};
const navigator = { onLine: true };
const fetchQueue = [];
globalThis.fetch = () => {
  if (!fetchQueue.length) throw new Error('missing queued response');
  return fetchQueue.shift();
};
async function readJsonResponse(response) { return response; }
function escHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function safeClassToken(value, fallback = '') {
  const token = String(value == null ? '' : value);
  return /^[a-z0-9_-]+$/i.test(token) ? token : fallback;
}
function fmtDate(value) { return value || ''; }
function setFormError(id, message) { element(id).textContent = message || ''; }
function syncChatRevision() {}
function reportLoadSuccess() {}
function reportLoadError() {}
function shouldEvictClientPhi(error) { return error?.status === 401 || error?.status === 403; }
function evictClientPhi() { throw new Error('unexpected authorization eviction'); }
function loadFailureMarkup() { return '<div>load failed</div>'; }

let phiEpoch = 3;
let workflowRevision = 9;
let followUpLoadEpoch = 0;
let followUpProjectionStale = false;
let followUpFilter = 'all';
let selectedFollowUpId = 'action-today';
let followUpSelectionEpoch = 2;
let followUpDialogOpen = true;
let followUpDialogMode = 'outcome';
let followUpOutcomeStatus = 'completed';
let pendingFollowUpIntent = null;
let activeFollowUpIntent = null;
let pendingWorkflowIntent = null;
let activeWorkflowIntent = null;
let followUpMutationPending = false;
let followUpDrafts = new Map();
let appointmentDialogOpen = true;
let selectedVisitId = 'visit-1';
let visitSelectionEpoch = 4;
let visitsById = new Map([['visit-1', {
  id: 'visit-1',
  follow_up_ids: ['action-visit'],
}]]);
let activeDialogSurface = null;
let lastDialogTrigger = null;
let followUpsById = new Map([
  ['action-today', {
    id: 'action-today',
    token: 'today-token-old',
    text: 'Today cached action',
    status: 'open',
    origin_snapshot: {
      kind: 'executive_summary_action',
      source_id: 'summary-accepted',
      source_profile_revision: 10,
      generation_id: 'generation-10',
    },
    created_at: '2026-08-01T10:00:00Z',
    updated_at: '2026-08-01T10:00:00Z',
  }],
  ['action-visit', {
    id: 'action-visit',
    token: 'visit-token-old',
    text: 'Visit cached action',
    status: 'in_progress',
    visit_id: 'visit-1',
    origin_snapshot: { kind: 'manual' },
    created_at: '2026-08-02T10:00:00Z',
    updated_at: '2026-08-02T10:00:00Z',
  }],
]);
function currentVisit() {
  return selectedVisitId ? visitsById.get(selectedVisitId) || null : null;
}
element('follow-up-outcome-kind').value = 'caregiver_reported';
element('follow-up-outcome-text').value = 'Draft for Today action';
element('visit-followup-text').value = 'Draft resulting visit follow-up';
""",
            _function_source("generatedActionAccepted", "redactGeneratedSummaryActions"),
            _function_source("followUpItems", "setFollowUpFilter"),
            _function_source("followUpDraftKey", "invalidateFollowUpRetryOnDraftChange"),
            _function_source("updateFollowUpOutcomeGuidance", "updateFollowUpFormValidity"),
            _function_source("updateFollowUpFormValidity", "renderFollowUpDialog"),
            _function_source("clearFollowUpCachedProjection", "createFollowUpIntent"),
            _function_source("updateAppointmentFormValidity", "visitCreateBody"),
            _executable_function_source("renderVisitFollowUps", "createVisitFollowUp"),
            """
(async () => {
  renderFollowUps();
  renderVisitFollowUps();
  refreshGeneratedActionControls();

  fetchQueue.push(Promise.reject(new TypeError('offline')));
  const typeErrorItems = await loadFollowUps();
  const typeError = {
    returnedItems: typeErrorItems.length,
    mapSize: followUpsById.size,
    todayRows: element('follow-up-list').innerHTML,
    visitRows: element('visit-followup-list').innerHTML,
    headerDisabled: element('follow-up-create-button').disabled,
    visitSubmitDisabled: element('visit-followup-submit').disabled,
    acceptedText: acceptedRow.button.textContent,
    acceptedDisabled: acceptedRow.button.disabled,
    availableDisabled: availableRow.button.disabled,
    todayDraft: followUpDrafts.get('outcome:action-today:completed')?.text,
  };

  selectedFollowUpId = 'action-visit';
  element('follow-up-outcome-text').value = 'Draft for Visit action';
  captureFollowUpDraft();
  element('follow-up-outcome-text').value = '';
  selectedFollowUpId = 'action-today';
  restoreFollowUpDraft();
  const isolatedDrafts = {
    today: element('follow-up-outcome-text').value,
    visit: followUpDrafts.get('outcome:action-visit:completed')?.text,
  };
  followUpDialogOpen = false;

  const abortError = new Error('aborted');
  abortError.name = 'AbortError';
  fetchQueue.push(Promise.reject(abortError));
  const abortItems = await loadFollowUps();
  const abortState = {
    returnedItems: abortItems.length,
    mapSize: followUpsById.size,
    stale: followUpProjectionStale,
    todayRows: element('follow-up-list').innerHTML,
    visitRows: element('visit-followup-list').innerHTML,
  };

  fetchQueue.push(Promise.resolve({
    workflow_revision: 10,
    profile_revision: 10,
    items: [
      {
        ...followUpsById.get('action-today'),
        token: 'today-token-fresh',
        updated_at: '2026-08-03T10:00:00Z',
      },
      {
        ...followUpsById.get('action-visit'),
        token: 'visit-token-fresh',
        updated_at: '2026-08-03T10:00:00Z',
      },
    ],
  }));
  await loadFollowUps();
  const fresh = {
    stale: followUpProjectionStale,
    todayRows: element('follow-up-list').innerHTML,
    visitRows: element('visit-followup-list').innerHTML,
    headerDisabled: element('follow-up-create-button').disabled,
    visitSubmitDisabled: element('visit-followup-submit').disabled,
    acceptedText: acceptedRow.button.textContent,
    availableDisabled: availableRow.button.disabled,
    todayToken: followUpsById.get('action-today').token,
    visitToken: followUpsById.get('action-visit').token,
  };

  followUpDialogOpen = true;
  selectedFollowUpId = 'action-today';
  followUpDrafts.set('edit:action-today', { owner: 'SECRET hard draft' });
  const pendingWorkflowRef = {
    url: '/api/visits/visit-1/follow-ups',
    body: { text: 'SECRET pending appointment follow-up' },
  };
  const activeWorkflowRef = {
    url: '/api/visits/visit-1/follow-ups',
    body: { text: 'SECRET active appointment follow-up' },
  };
  pendingWorkflowIntent = pendingWorkflowRef;
  activeWorkflowIntent = activeWorkflowRef;
  activeDialogSurface = element('follow-up-dialog');
  lastDialogTrigger = { patient: true };
  element('follow-up-overlay').classList.add('open');
  element('follow-up-edit-copy').textContent = 'SECRET hard copy';
  element('follow-up-outcome-kind').value = 'clinician_attributed';
  for (const id of [
    'follow-up-create-form', 'follow-up-edit-form', 'follow-up-outcome-form',
    'follow-up-retry', 'follow-up-dialog-retry'
  ]) element(id).hidden = false;
  const hardError = new Error('hard failure');
  hardError.status = 500;
  fetchQueue.push(Promise.reject(hardError));
  await loadFollowUps();
  const hard = {
    mapSize: followUpsById.size,
    drafts: followUpDrafts.size,
    selectedFollowUpId,
    pendingWorkflowIntent,
    activeWorkflowIntent,
    pendingBody: pendingWorkflowRef.body,
    activeBody: activeWorkflowRef.body,
    visitSelectionEpoch,
    copy: element('follow-up-edit-copy').textContent,
    outcomeKind: element('follow-up-outcome-kind').value,
    formsHidden: element('follow-up-create-form').hidden
      && element('follow-up-edit-form').hidden
      && element('follow-up-outcome-form').hidden,
    retriesHidden: element('follow-up-retry').hidden
      && element('follow-up-dialog-retry').hidden,
    overlayClosed: !element('follow-up-overlay').classList.contains('open')
      && element('follow-up-overlay').inert,
    focusRefsCleared: activeDialogSurface === null && lastDialogTrigger === null,
    bodyReset: !body.classList.contains('dialog-open')
      && background.inert === false
      && !('aria-hidden' in background.attributes),
    todayRows: element('follow-up-list').innerHTML,
  };
  console.log(JSON.stringify({ typeError, isolatedDrafts, abortState, fresh, hard }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node"], input=script, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_transport_failures_keep_authoritative_rows_stale_and_read_only():
    result = _run_follow_up_offline_projection_probe()

    offline = result["typeError"]
    assert offline["mapSize"] == 2
    assert offline["returnedItems"] == 2
    assert "Today cached action" in offline["todayRows"]
    assert "Visit cached action" in offline["todayRows"]
    assert "Visit cached action" in offline["visitRows"]
    assert "Offline snapshot" in offline["todayRows"]
    assert "read-only" in offline["todayRows"]
    assert "Offline snapshot" in offline["visitRows"]
    assert "read-only" in offline["visitRows"]
    assert 'disabled onclick="changeFollowUpStatus' in offline["todayRows"]
    assert 'disabled onclick="openFollowUpEditDialog' in offline["todayRows"]
    assert offline["headerDisabled"] is True
    assert offline["visitSubmitDisabled"] is True
    assert offline["acceptedText"] == "Accepted"
    assert offline["acceptedDisabled"] is True
    assert offline["availableDisabled"] is True
    assert offline["todayDraft"] == "Draft for Today action"

    assert result["isolatedDrafts"] == {
        "today": "Draft for Today action",
        "visit": "Draft for Visit action",
    }
    aborted = result["abortState"]
    assert aborted["mapSize"] == 2
    assert aborted["returnedItems"] == 2
    assert aborted["stale"] is True
    assert "Today cached action" in aborted["todayRows"]
    assert "Visit cached action" in aborted["visitRows"]

    fresh = result["fresh"]
    assert fresh["stale"] is False
    assert "Offline snapshot" not in fresh["todayRows"]
    assert "Offline snapshot" not in fresh["visitRows"]
    assert fresh["headerDisabled"] is False
    assert fresh["visitSubmitDisabled"] is False
    assert fresh["acceptedText"] == "Accepted"
    assert fresh["availableDisabled"] is False
    assert fresh["todayToken"] == "today-token-fresh"
    assert fresh["visitToken"] == "visit-token-fresh"
    assert 'data-follow-up-token="today-token-fresh"' in fresh["todayRows"]

    hard = result["hard"]
    assert hard["mapSize"] == 0
    assert hard["drafts"] == 0
    assert hard["selectedFollowUpId"] is None
    assert hard["pendingWorkflowIntent"] is None
    assert hard["activeWorkflowIntent"] is None
    assert hard["pendingBody"] == {}
    assert hard["activeBody"] == {}
    assert hard["visitSelectionEpoch"] == 5
    assert hard["copy"] == ""
    assert hard["outcomeKind"] == "administrative"
    assert hard["formsHidden"] is True
    assert hard["retriesHidden"] is True
    assert hard["overlayClosed"] is True
    assert hard["focusRefsCleared"] is True
    assert hard["bodyReset"] is True
    assert "load failed" in hard["todayRows"]
    assert "Today cached action" not in hard["todayRows"]


def _run_follow_up_epoch_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 2;
let followUpSelectionEpoch = 5;
let selectedFollowUpId = 'action-b';
let latestProfileRevision = 20;
let workflowRevision = 4;
let followUpsById = new Map([
  ['action-a', { id: 'action-a', token: 'a-original' }],
  ['action-b', { id: 'action-b', token: 'b-original' }],
]);
let followUpDialogOpen = false;
const followUpDrafts = new Map();
let workflowLoads = 0;
let clinicalRefreshes = 0;
let renders = 0;

function closeFollowUpDialog() {}
function renderFollowUps() { renders += 1; }
function renderVisitFollowUps() {}
function setFollowUpStatus() {}
function reportLoadSuccess() {}
async function loadFollowUps() { workflowLoads += 1; return []; }
async function refreshClinicalWorkflowState() { clinicalRefreshes += 1; return true; }
function requestClinicalConvergence() {}
function advancePatientAuthority(revision) {
  latestProfileRevision = revision;
  phiEpoch += 1;
  clinicalRefreshes += 1;
  return true;
}
""",
            _response_authority_source(),
            _executable_function_source("followUpIntentCanRender", "handleFollowUpConflict"),
            _executable_function_source("consumeFollowUpResponse", "performFollowUpIntent"),
            """
(async () => {
  const lateA = {
    actionId: 'action-a',
    requestPhiEpoch: 2,
    requestActionEpoch: 4,
  };
  const lateAResult = await consumeFollowUpResponse({
    item: { id: 'action-a', token: 'a-late' },
    workflow_revision: 99,
    profile_revision: 99,
  }, lateA);

  const workflowB = {
    actionId: 'action-b',
    requestPhiEpoch: 2,
    requestActionEpoch: 5,
  };
  const workflowResult = await consumeFollowUpResponse({
    item: { id: 'action-b', token: 'b-workflow' },
    workflow_revision: 5,
    profile_revision: 20,
  }, workflowB);

  selectedFollowUpId = 'action-c';
  followUpSelectionEpoch = 6;
  followUpsById.set('action-c', { id: 'action-c', token: 'c-original' });
  const clinicalC = {
    actionId: 'action-c',
    requestPhiEpoch: 2,
    requestActionEpoch: 6,
  };
  const clinicalResult = await consumeFollowUpResponse({
    item: { id: 'action-c', token: 'c-clinical' },
    workflow_revision: 6,
    profile_revision: 21,
  }, clinicalC);

  phiEpoch = 3;
  const postEviction = await consumeFollowUpResponse({
    item: { id: 'action-c', token: 'c-late-auth' },
    workflow_revision: 7,
    profile_revision: 22,
  }, clinicalC);

  console.log(JSON.stringify({
    lateAResult,
    actionAToken: followUpsById.get('action-a').token,
    actionBToken: followUpsById.get('action-b').token,
    actionCToken: followUpsById.get('action-c').token,
    workflowResult,
    clinicalResult,
    postEviction,
    workflowLoads,
    clinicalRefreshes,
    workflowRevision,
    latestProfileRevision,
    renders,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_epochs_and_revision_paths_block_late_repaints():
    assert _run_follow_up_epoch_probe() == {
        "lateAResult": False,
        "actionAToken": "a-original",
        "actionBToken": "b-workflow",
        "actionCToken": "c-clinical",
        "workflowResult": True,
        "clinicalResult": True,
        "postEviction": False,
        "workflowLoads": 1,
        "clinicalRefreshes": 1,
        "workflowRevision": 6,
        "latestProfileRevision": 21,
        "renders": 2,
    }


def _run_generated_action_redaction_probe() -> dict:
    script = "\n".join(
        [
            """
class FakeRow {
  constructor() {
    this.dataset = {
      generatedActionSourceId: 'sumact-secret',
      generatedActionSourceToken: 'SECRET TOKEN',
    };
    this.className = 'action-item';
    this.innerHTML = 'SECRET GENERATED TEXT <button>Add to follow-through</button>';
  }
  removeAttribute(name) {
    if (name === 'data-generated-action-source-id') delete this.dataset.generatedActionSourceId;
    if (name === 'data-generated-action-source-token') delete this.dataset.generatedActionSourceToken;
  }
}
const row = new FakeRow();
const document = { querySelectorAll() { return [row]; } };
""",
            _function_source("summaryActionIsCurrent", "generatedActionAccepted"),
            _executable_function_source("redactGeneratedSummaryActions", "acceptGeneratedFollowUp"),
            """
const summary = { profile_revision: 9, summary_revision: 9, generation_id: 'generation-9' };
const current = {
  id: 'sumact-current',
  source_token: 'token',
  generation_id: 'generation-9',
  source_profile_revision: 9,
  stale: false,
};
const stale = { ...current, stale: true };
const revisionless = { ...current };
delete revisionless.source_profile_revision;
redactGeneratedSummaryActions();
console.log(JSON.stringify({
  current: summaryActionIsCurrent(current, summary),
  stale: summaryActionIsCurrent(stale, summary),
  revisionless: summaryActionIsCurrent(revisionless, summary),
  html: row.innerHTML,
  dataset: row.dataset,
  className: row.className,
}));
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_generated_action_staleness_redacts_text_token_and_control():
    result = _run_generated_action_redaction_probe()
    assert result["current"] is True
    assert result["stale"] is False
    assert result["revisionless"] is False
    assert result["dataset"] == {}
    assert result["className"] == "action-item unavailable"
    assert "Generated action unavailable" in result["html"]
    assert "SECRET" not in result["html"]
    assert "Add to follow-through" not in result["html"]


def test_summary_action_sources_use_load_and_profile_revision_guards():
    loader = _function_source("loadSummary", "renderPendingSummary")
    revision_sync = _function_source("syncChatRevision", "toggleChat")
    assert "requestSummaryEpoch = ++summaryLoadEpoch" in loader
    assert "requestSummaryEpoch !== summaryLoadEpoch" in loader
    assert "authorizePatientResponse(request, d)" in loader
    assert loader.index("redactGeneratedSummaryActions()") < loader.index("renderSummary({")
    assert revision_sync.count("redactGeneratedSummaryActions()") >= 2


def _run_revision_authority_probe() -> dict:
    script = "\n".join(
        [
            """
let selectedTaskId = null;
let taskSelectionEpoch = 0;
let selectedVisitId = null;
let visitSelectionEpoch = 0;
let selectedFollowUpId = null;
let followUpSelectionEpoch = 0;
let latestProfileRevision = null;
let workflowRevision = null;
let phiEpoch = 0;
let clinicalConvergenceRevision = null;
let clinicalConvergenceRunning = false;
let chatHistoryRevision = null;
let chatHistory = [{ role: 'assistant', content: 'keep me' }];
let appointmentQuestionSources = [];
let generatedQuestionsUnavailable = false;
let nestedRevision = null;
const convergenceTargets = [];
const document = { getElementById() { return null; } };

function redactGeneratedQuestionChoices() {}
function redactGeneratedSummaryActions() {}
function loadQuestions() {}
function reportLoadError() {}
async function refreshClinicalWorkflowState(target) {
  convergenceTargets.push(target);
  if (nestedRevision != null && target < nestedRevision) {
    const next = nestedRevision;
    nestedRevision = null;
    authorizePatientResponse(capturePatientRequest(), {
      profile_revision: next,
      workflow_revision: workflowRevision,
    }, { workflow: 'projection' });
  }
  await Promise.resolve();
  return true;
}
""",
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("capturePatientRequest", "patientRequestIsCurrent"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("requestClinicalConvergence", "advancePatientAuthority"),
            _function_source("advancePatientAuthority", "authorizePatientResponse"),
            _function_source("authorizePatientResponse", "setAppointmentMessage"),
            _function_source("syncChatRevision", "toggleChat"),
            """
const flush = async () => {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
};

(async () => {
  const actionRequest = capturePatientRequest();
  const visitRequest = capturePatientRequest();
  const action11 = authorizePatientResponse(actionRequest, {
    profile_revision: 11,
    workflow_revision: 4,
  }, { workflow: 'projection' });
  let renderedAction11 = action11.accepted;
  const visit10 = authorizePatientResponse(visitRequest, {
    profile_revision: 10,
    workflow_revision: 3,
  }, { workflow: 'projection' });
  let renderedVisit10 = visit10.accepted;
  await flush();
  const actionThenVisit = {
    renderedAction11,
    renderedVisit10,
    latestProfileRevision,
    chatHistoryRevision,
    workflowRevision,
  };

  latestProfileRevision = null;
  workflowRevision = null;
  chatHistoryRevision = null;
  chatHistory = [];
  const visitRequest2 = capturePatientRequest();
  const actionRequest2 = capturePatientRequest();
  const visit11 = authorizePatientResponse(visitRequest2, {
    profile_revision: 11,
    workflow_revision: 4,
  }, { workflow: 'projection' });
  const action10 = authorizePatientResponse(actionRequest2, {
    profile_revision: 10,
    workflow_revision: 3,
  }, { workflow: 'projection' });
  await flush();
  const visitThenAction = {
    renderedVisit11: visit11.accepted,
    renderedAction10: action10.accepted,
    latestProfileRevision,
    workflowRevision,
  };

  const lateStatus = capturePatientRequest();
  const lateSummary = capturePatientRequest();
  const lateQuestions = capturePatientRequest();
  const lateTasks = capturePatientRequest();
  const authorityRequest = capturePatientRequest();
  authorizePatientResponse(authorityRequest, {
    profile_revision: 12,
    workflow_revision: 5,
  }, { workflow: 'projection' });
  const lateLowerReads = {
    status: authorizePatientResponse(lateStatus, { profile_revision: 11 }).accepted,
    summary: authorizePatientResponse(lateSummary, { profile_revision: 11 }).accepted,
    questions: authorizePatientResponse(lateQuestions, []).accepted,
    tasks: authorizePatientResponse(lateTasks, []).accepted,
  };
  await flush();

  const equalWorkflowA = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 12,
    workflow_revision: 5,
  }, { workflow: 'projection' });
  const equalWorkflowB = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 12,
    workflow_revision: 5,
  }, { workflow: 'projection' });
  const missingWorkflow = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 12,
  }, { workflow: 'projection' });
  const missingProfile = authorizePatientResponse(capturePatientRequest(), {
    workflow_revision: 5,
  }, { workflow: 'projection' });
  const currentRevisionless = authorizePatientResponse(capturePatientRequest(), []);
  const oldRevisionlessRequest = capturePatientRequest();
  authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 13,
    workflow_revision: 6,
  }, { workflow: 'projection' });
  const lateRevisionless = authorizePatientResponse(oldRevisionlessRequest, []);
  await flush();

  workflowRevision = 9;
  const targetedLowerWorkflow = authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 13,
    workflow_revision: 8,
  }, { workflow: 'targeted' });
  const workflowAfterTargeted = workflowRevision;

  chatHistory = [{ role: 'assistant', content: 'current answer' }];
  chatHistoryRevision = 13;
  latestProfileRevision = 13;
  syncChatRevision(12, true, false);
  const chatAfterLower = {
    chatHistoryRevision,
    latestProfileRevision,
    historyLength: chatHistory.length,
  };
  syncChatRevision(14, true, false);
  const chatAfterNewer = {
    chatHistoryRevision,
    latestProfileRevision,
    historyLength: chatHistory.length,
  };

  nestedRevision = 16;
  authorizePatientResponse(capturePatientRequest(), {
    profile_revision: 15,
    workflow_revision: 10,
  }, { workflow: 'projection' });
  await flush();
  await flush();

  console.log(JSON.stringify({
    actionThenVisit,
    visitThenAction,
    lateLowerReads,
    equalWorkflow: [equalWorkflowA.accepted, equalWorkflowB.accepted],
    missingWorkflow: missingWorkflow.accepted,
    missingProfile: missingProfile.accepted,
    currentRevisionless: currentRevisionless.accepted,
    lateRevisionless: lateRevisionless.accepted,
    targetedLowerWorkflow: targetedLowerWorkflow.accepted,
    workflowAfterTargeted,
    chatAfterLower,
    chatAfterNewer,
    nested: {
      latestProfileRevision,
      chatHistoryRevision,
      workflowRevision,
      targets: convergenceTargets.slice(-2),
    },
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_response_authority_is_monotonic_across_patient_surface_interleavings():
    result = _run_revision_authority_probe()
    assert result["actionThenVisit"] == {
        "renderedAction11": True,
        "renderedVisit10": False,
        "latestProfileRevision": 11,
        "chatHistoryRevision": 11,
        "workflowRevision": 4,
    }
    assert result["visitThenAction"] == {
        "renderedVisit11": True,
        "renderedAction10": False,
        "latestProfileRevision": 11,
        "workflowRevision": 4,
    }
    assert result["lateLowerReads"] == {
        "status": False,
        "summary": False,
        "questions": False,
        "tasks": False,
    }
    assert result["equalWorkflow"] == [True, True]
    assert result["missingWorkflow"] is False
    assert result["missingProfile"] is True
    assert result["currentRevisionless"] is True
    assert result["lateRevisionless"] is False
    assert result["targetedLowerWorkflow"] is True
    assert result["workflowAfterTargeted"] == 9
    assert result["chatAfterLower"] == {
        "chatHistoryRevision": 13,
        "latestProfileRevision": 13,
        "historyLength": 1,
    }
    assert result["chatAfterNewer"] == {
        "chatHistoryRevision": 14,
        "latestProfileRevision": 14,
        "historyLength": 0,
    }
    assert result["nested"] == {
        "latestProfileRevision": 16,
        "chatHistoryRevision": 16,
        "workflowRevision": 10,
        "targets": [15, 16],
    }


def test_patient_loaders_authorize_before_projection_or_failure_mutation():
    checks = (
        ("loadStatus", "renderStatusFailure", "renderSidebar(d)"),
        ("loadSummary", "renderPendingSummary", "const editor ="),
        ("loadTasks", "renderTasks", "hadActiveJobs = true"),
        ("loadVisits", "followUpItems", "captureAppointmentDraft()"),
        ("loadFollowUps", "createFollowUpIntent", "captureFollowUpDraft()"),
        ("loadQuestions", "renderQuestions", "appointmentQuestionSources ="),
    )
    for name, next_name, first_mutation in checks:
        source = _function_source(name, next_name)
        assert source.index("authorizePatientResponse(") < source.index(first_mutation)
        catch = source[source.index("catch") :]
        assert "patientRequestIsCurrent(request)" in catch


def test_follow_up_retry_conflict_eviction_and_loading_contracts_are_strict():
    intent = _function_source("createFollowUpIntent", "followUpIntentCanRender")
    performer = _function_source("performFollowUpIntent", "submitFollowUpMutation")
    retry = _function_source("retryFollowUpIntent", "createManualFollowUp")
    conflict = _function_source("handleFollowUpConflict", "consumeFollowUpResponse")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    loader = _function_source("loadFollowUps", "createFollowUpIntent")
    polling = _function_source("startPolling", "currentVisit")

    assert "mutation_id: newMutationId()" in intent
    assert "performFollowUpIntent(intent, true)" in retry
    assert "pendingFollowUpIntent = intent" in performer
    assert "error?.status === 409" in performer
    assert "consumedSuccessfully || followUpIntentCanRender(intent)" in performer
    renderer = _function_source("renderFollowUps", "setFollowUpFilter")
    busy = _function_source("setFollowUpMutationBusy", "updateFollowUpOutcomeGuidance")
    closer = _function_source("closeFollowUpDialog", "closeFollowUpFromBackdrop")
    focus = _function_source("restoreFollowUpMutationFocus", "performFollowUpIntent")
    assert "if (followUpMutationPending) setFollowUpMutationBusy(true)" in renderer
    assert "if (!('followUpWasDisabled' in control.dataset))" in busy
    assert "if (followUpMutationPending && !force)" in closer
    assert "closeFollowUpDialog(false, true)" in _function_source(
        "consumeFollowUpResponse", "restoreFollowUpMutationFocus"
    )
    assert "document.querySelectorAll('.follow-up-item')" in focus
    assert "restoreFollowUpMutationFocus(intent)" in performer
    assert "performFollowUpIntent" not in conflict
    assert "redactGeneratedSummaryActions()" in conflict
    assert "loadFollowUps()" in conflict
    assert "loadSummary()" in conflict
    assert "loadFollowUps()" not in polling
    assert "shouldEvictClientPhi(error)" in loader
    assert "if (!patientRequestIsCurrent(request)" in loader
    assert "reportLoadError('follow-ups', error)" in loader
    for expression in (
        "followUpsById = new Map()",
        "followUpLoadEpoch += 1",
        "selectedFollowUpId = null",
        "followUpSelectionEpoch += 1",
        "followUpDialogOpen = false",
        "pendingFollowUpIntent = null",
        "followUpMutationPending = false",
        "followUpDrafts = new Map()",
        "clear('follow-up-list')",
        "clear('follow-up-status')",
    ):
        assert expression in eviction


def test_follow_up_outcomes_have_precise_unverified_provenance():
    presentation = _function_source("followUpOutcomePresentation", "formatActionTimestamp")
    assert "Caregiver-entered · attributed to clinician · unverified" in presentation
    assert "Caregiver-entered · caregiver reported · unverified" in presentation
    assert "Caregiver-entered administrative outcome · not clinical evidence" in presentation
    assert "verified" not in presentation.replace("unverified", "")
    renderer = _function_source("renderFollowUps", "setFollowUpFilter")
    visit_renderer = _function_source("renderVisitFollowUps", "createVisitFollowUp")
    assert "escHtml(item.outcome.text)" in renderer
    assert "source-verified" not in renderer
    assert "followUpOutcomePresentation(item.outcome)" in visit_renderer
    assert "escHtml(outcome.label)" in visit_renderer


def test_follow_up_surface_is_responsive_keyboard_operable_and_overflow_safe():
    playwright_api = pytest.importorskip("playwright.sync_api")
    markup = """
      <main>
        <section class="content-card follow-through-card">
          <div class="follow-up-filters">
            <button class="follow-up-filter active">Active <span>2</span></button>
            <button class="follow-up-filter">Completed <span>1</span></button>
            <button class="follow-up-filter">Cancelled <span>0</span></button>
            <button class="follow-up-filter">All <span>3</span></button>
          </div>
          <div class="follow-up-list">
            <article class="follow-up-item">
              <div class="follow-up-item-heading">
                <span class="visit-status-badge open">Open</span>
                <span class="follow-up-due soon">Due soon · 15-08-2026</span>
              </div>
              <p class="follow-up-copy">Contact the clinic to confirm a deliberately long follow-up description that must wrap without causing horizontal overflow on a narrow phone viewport.</p>
              <div class="follow-up-actions">
                <button class="button secondary">Edit owner or due date</button>
                <button class="button primary">Start</button>
                <button class="button secondary">Complete</button>
              </div>
            </article>
          </div>
        </section>
        <div class="follow-up-overlay open">
          <section class="follow-up-dialog">
            <div class="follow-up-dialog-body">
              <form class="follow-up-form">
                <label><span>What happened?</span><textarea>Outcome</textarea></label>
                <div class="follow-up-dialog-actions">
                  <button class="button primary">Save outcome</button>
                  <button class="button secondary">Cancel</button>
                </div>
              </form>
            </div>
          </section>
        </div>
      </main>
    """

    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 800})
        page.set_content(markup)
        page.add_style_tag(content=CSS)
        heights = page.locator(
            ".follow-up-filter, .follow-up-actions .button, "
            ".follow-up-dialog-actions .button, .follow-up-form textarea"
        ).evaluate_all("(items) => items.map(item => item.getBoundingClientRect().height)")
        overflow = page.evaluate(
            """() => ({
              document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
              card: document.querySelector('.follow-through-card').scrollWidth
                - document.querySelector('.follow-through-card').clientWidth,
              item: document.querySelector('.follow-up-item').scrollWidth
                - document.querySelector('.follow-up-item').clientWidth,
              dialog: document.querySelector('.follow-up-dialog').scrollWidth
                - document.querySelector('.follow-up-dialog').clientWidth,
            })"""
        )
        assert heights
        assert all(height >= 44 for height in heights)
        assert overflow == {"document": 0, "card": 0, "item": 0, "dialog": 0}
        page.keyboard.press("Tab")
        focus = page.evaluate(
            """() => {
              const style = getComputedStyle(document.activeElement);
              return { tag: document.activeElement.tagName, outline: style.outlineStyle };
            }"""
        )
        assert focus["tag"] in {"BUTTON", "TEXTAREA"}
        assert focus["outline"] != "none"
        browser.close()
