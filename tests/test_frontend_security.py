"""Static regression checks for file upload and DOM rendering safety."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

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


def _response_authority_source() -> str:
    return "\n".join(
        [
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("capturePatientRequest", "patientRequestIsCurrent"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("authorizePatientResponse", "setAppointmentMessage"),
        ]
    )


def _run_node_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", _NODE_STDIN_BOOTSTRAP, *args],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
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
let statusLoadEpoch = 0;
let summaryLoadEpoch = 0;
let taskLoadEpoch = 0;
let workflowRevision = 3;
let visitsById = new Map([['visit-phi', { patient: true }]]);
let appointmentOptions = [{ patient: true }];
let appointmentQuestionSources = [{ patient: true }];
let questionLoadEpoch = 0;
let visitLoadEpoch = 0;
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
let followUpMutationOwner = { patient: true };
let followUpDrafts = new Map([['edit:follow-up-phi', { patient: true }]]);
let selectedVisitId = 'visit-phi';
let visitSelectionEpoch = 0;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'decisions';
let pendingWorkflowIntent = { patient: true };
let activeWorkflowIntent = null;
let workflowMutationPending = true;
let appointmentDrafts = new Map([['visit-phi', { patient: true }]]);
let alertsById = new Map([['alert-phi', { patient: true }]]);
let alertProjectionStale = true;
let alertLinkSourcesStale = true;
let selectedAlertId = 'alert-phi';
let alertSelectionEpoch = 2;
let alertResolutionDialogOpen = true;
let alertResolutionIntentOwner = { patient: true };
let alertResolutionMutationPending = true;
let pendingAlertResolutionIntent = { body: { patient: true } };
let activeAlertResolutionIntent = { body: { patient: true } };
let alertResolutionDrafts = new Map([['resolve:alert-phi', { patient: true }]]);
let alertResolutionResult = { patient: true };
let renderSummaryCalls = 0;
const loadErrors = [];

function renderLatestResearchUpdate() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
function setFollowUpMutationBusy() {}
function setAlertResolutionBusy() {}
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
    completed = _run_node_script(script, str(status))
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize("status", [401, 403])
def test_summary_auth_eviction_cannot_repaint_freshness_or_accept_late_success(status):
    result = _run_summary_auth_probe(status)

    assert result == {
        "phiEpoch": 1,
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
        "ensureSymptomEpisodes()",
    ):
        assert loader in retry
    assert "updateHeaderStatus(null, e)" in APP_JS
    assert "loadFailureMarkup('Assessment'" in APP_JS
    assert "loadFailureMarkup('Processing activity'" in APP_JS
    assert "renderImagingUnavailable(" in APP_JS
    assert "'Imaging history could not be loaded." in APP_JS


def test_status_failure_clears_all_status_derived_phi_and_caches():
    failure = _function_source("renderStatusFailure", "renderLatestResearchUpdate")
    for expression in (
        "redactGeneratedQuestionChoices()",
        "latestResearchUpdate = null",
        "renderLatestResearchUpdate(null)",
        "patientMeta.innerHTML = ''",
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
        "clearBiomarkerProjection({",
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
        "clearSymptomProjection({",
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
    epoch_guard = auth_failure.index("if (!requestIsCurrent()) return null")
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
    for handler, next_name in (("addJudgment", "deleteJudgment"),):
        source = _function_source(handler, next_name)
        assert "const requestPhiEpoch = phiEpoch" in source
        assert "requestPhiEpoch !== phiEpoch" in source
    symptom_mutation = _function_source("performSymptomIntent", "retrySymptomIntent")
    assert "symptomIntentOwnsMutation(intent, intent.requestPhiEpoch)" in symptom_mutation
    assert "evictClientPhi(safeError)" in symptom_mutation
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
    sidebar = _function_source("renderSidebar", "renderAlerts")
    renderer = _function_source("renderAlerts", "alertResolutionProvenanceLabel")
    body = _function_source("createAlertResolutionBody", "alertResolutionIntentOwnsMutation")
    resolver = _function_source("performAlertResolutionIntent", "submitAlertResolution")
    assert "alertsById = new Map" in sidebar
    assert "data-alert-id" in renderer
    assert "data-resolve-token" in renderer
    assert "/api/alerts/${encodeURIComponent(intent.alertId)}/resolve" in resolver
    assert "expected_token: alert.resolve_token" in body
    assert "expected_profile_revision: latestProfileRevision" in body
    assert "mutation_id: newMutationId()" in body
    assert "authorizePatientResponse(intent, data" in resolver
    assert "alertResolution: true" in resolver
    submitter = _function_source("submitAlertResolution", "retryAlertResolution")
    assert "requestAlertId: alert.id" in submitter


def test_alert_resolution_intent_passes_real_shared_authority_guard():
    script = "\n".join(
        [
            """
let phiEpoch = 0;
let latestProfileRevision = 5;
let workflowRevision = 2;
let selectedTaskId = null;
let taskSelectionEpoch = 0;
let selectedVisitId = null;
let visitSelectionEpoch = 0;
let selectedFollowUpId = null;
let followUpSelectionEpoch = 0;
let selectedAlertId = 'alert-stable-id';
let alertSelectionEpoch = 3;
function advancePatientAuthority() { throw new Error('unexpected revision advance'); }
function requestClinicalConvergence() {
  throw new Error('unexpected convergence request');
}
""",
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("authorizePatientResponse", "setAppointmentMessage"),
            """
const intent = {
  requestPhiEpoch: 0,
  requestAlertEpoch: 3,
  requestAlertId: 'alert-stable-id',
  alertId: 'alert-stable-id',
};
const accepted = authorizePatientResponse(intent, {
  profile_revision: 5,
  workflow_revision: 2,
}, {
  workflow: 'targeted',
  alertResolution: true,
}).accepted;
selectedAlertId = 'different-alert';
const rejectedAfterSelectionChange = authorizePatientResponse(intent, {
  profile_revision: 5,
  workflow_revision: 2,
}, {
  workflow: 'targeted',
  alertResolution: true,
}).accepted;
console.log(JSON.stringify({ accepted, rejectedAfterSelectionChange }));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "accepted": True,
        "rejectedAfterSelectionChange": False,
    }


def _run_alert_resolution_body_probe() -> dict:
    script = "\n".join(
        [
            """
let latestProfileRevision = 42;
let mutationIds = 0;
let mode = 'none';
const ALERT_RESOLUTION_OUTCOME_KINDS = new Set([
  'administrative', 'caregiver_reported', 'clinician_attributed'
]);
const elements = new Map([
  ['alert-resolution-outcome-kind', { value: 'clinician_attributed' }],
  ['alert-resolution-outcome-text', { value: 'Treating team confirmed monitoring' }],
  ['alert-resolution-follow-up-select', { value: 'action-stable-id' }],
  ['alert-resolution-follow-up-text', { value: 'Ask the treating team to confirm timing' }],
  ['alert-resolution-follow-up-owner', { value: 'Caregiver' }],
  ['alert-resolution-follow-up-due', { value: '2026-09-01' }],
  ['alert-resolution-visit-select', { value: 'visit-stable-id' }],
  ['alert-resolution-decision-select', { value: 'decision-stable-id' }],
]);
const document = {
  getElementById(id) { return elements.get(id); },
  querySelector() { return { value: mode }; },
};
function newMutationId() { mutationIds += 1; return `mutation-${mutationIds}`; }
""",
            _function_source("selectedAlertResolutionMode", "alertResolutionDraftKey"),
            _function_source("createAlertResolutionBody", "alertResolutionIntentOwnsMutation"),
            """
const alert = { id: 'alert-stable-id', resolve_token: 'full-semantic-token' };
const bodies = {};
for (const value of ['none', 'follow_up', 'inline', 'visit']) {
  mode = value;
  bodies[value] = createAlertResolutionBody(alert);
}
elements.get('alert-resolution-outcome-text').value = '';
mode = 'none';
bodies.noOutcome = createAlertResolutionBody(alert);
console.log(JSON.stringify({ bodies, mutationIds }));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_alert_resolution_bodies_use_only_server_contract_ids_and_optional_outcome():
    result = _run_alert_resolution_body_probe()
    bodies = result["bodies"]
    common = {
        "expected_token": "full-semantic-token",
        "expected_profile_revision": 42,
        "outcome": {
            "kind": "clinician_attributed",
            "text": "Treating team confirmed monitoring",
        },
    }
    assert result["mutationIds"] == 5
    assert bodies["none"] == {"mutation_id": "mutation-1", **common}
    assert bodies["follow_up"] == {
        "mutation_id": "mutation-2",
        **common,
        "follow_up_id": "action-stable-id",
    }
    assert bodies["inline"] == {
        "mutation_id": "mutation-3",
        **common,
        "follow_up": {
            "text": "Ask the treating team to confirm timing",
            "owner": "Caregiver",
            "due_date": "2026-09-01",
        },
    }
    assert bodies["visit"] == {
        "mutation_id": "mutation-4",
        **common,
        "visit_id": "visit-stable-id",
        "decision_id": "decision-stable-id",
    }
    assert bodies["noOutcome"] == {
        "mutation_id": "mutation-5",
        "expected_token": "full-semantic-token",
        "expected_profile_revision": 42,
    }
    serialized = json.dumps(bodies)
    assert "display text" not in serialized
    assert "/api/alerts/resolve/" not in APP_JS


def test_alert_resolution_modes_disable_non_selected_fields_and_reject_bad_provenance():
    script = "\n".join(
        [
            """
let mode = 'none';
let alertLinkSourcesStale = false;
let alertResolutionMutationPending = false;
const panels = new Map();
for (const id of [
  'alert-resolution-existing-follow-up',
  'alert-resolution-inline-follow-up',
  'alert-resolution-visit-link'
]) {
  const controls = [{ disabled: false }, { disabled: false }];
  panels.set(id, {
    hidden: false,
    controls,
    querySelectorAll() { return controls; },
  });
}
const document = {
  getElementById(id) { return panels.get(id); },
  querySelector() { return { value: mode }; },
};
function updateAlertResolutionFormValidity() {}
""",
            _function_source("selectedAlertResolutionMode", "alertResolutionDraftKey"),
            _function_source(
                "renderAlertResolutionLinkMode", "setAlertResolutionProjectionReadOnly"
            ),
            """
const states = {};
for (const value of ['none', 'follow_up', 'inline', 'visit']) {
  mode = value;
  renderAlertResolutionLinkMode();
  states[value] = Object.fromEntries([...panels].map(([id, panel]) => [
    id,
    { hidden: panel.hidden, disabled: panel.controls.every(control => control.disabled) },
  ]));
}
console.log(JSON.stringify(states));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    states = json.loads(completed.stdout)
    expected_panel = {
        "none": None,
        "follow_up": "alert-resolution-existing-follow-up",
        "inline": "alert-resolution-inline-follow-up",
        "visit": "alert-resolution-visit-link",
    }
    for mode, panels in states.items():
        for panel_id, state in panels.items():
            selected = panel_id == expected_panel[mode]
            assert state == {"hidden": not selected, "disabled": not selected}

    invalid_probe = _run_alert_resolution_body_probe()
    assert invalid_probe["bodies"]["noOutcome"].get("outcome") is None
    body = _function_source("createAlertResolutionBody", "alertResolutionIntentOwnsMutation")
    assert "ALERT_RESOLUTION_OUTCOME_KINDS.has(kind)" in body
    assert "throw new Error('Choose a valid outcome source.')" in body


def test_alert_resolution_owns_intent_before_epoch_id_fetch_and_revalidates_awaits():
    opener = _function_source("openAlertResolutionDialog", "closeAlertResolutionDialog")
    submitter = _function_source("submitAlertResolution", "retryAlertResolution")
    performer = _function_source("performAlertResolutionIntent", "submitAlertResolution")
    conflict = _function_source("handleAlertResolutionConflict", "performAlertResolutionIntent")
    assert opener.index("const owner = beginAlertResolutionOwner()") < opener.index(
        "alertSelectionEpoch += 1"
    )
    assert opener.index("const owner = beginAlertResolutionOwner()") < opener.index(
        "await refreshAlertResolutionSources(owner)"
    )
    assert submitter.index("alertResolutionMutationPending = true") < submitter.index(
        "createAlertResolutionBody(alert)"
    )
    assert "mutation_id: newMutationId()" in _function_source(
        "createAlertResolutionBody", "alertResolutionIntentOwnsMutation"
    )
    assert performer.count("alertResolutionIntentOwnsMutation") >= 9
    assert "readJsonResponse(" in performer
    assert "refreshClinicalWorkflowState(" in performer
    assert "authorizePatientResponse(intent, data" in performer
    assert "redactAlertResolutionCard(intent.alertId)" in conflict
    assert "loadStatus({" in conflict
    assert "refreshClinicalWorkflowState(" in conflict
    assert "responseGuard: refreshedGuard" in conflict
    assert "intent.body = {}" in conflict
    assert "performAlertResolutionIntent" not in conflict


def test_alert_resolution_locks_sources_while_loading_and_converges_removed_conflict():
    source_refresh = _function_source("refreshAlertResolutionSources", "openAlertResolutionDialog")
    assert source_refresh.index("alertLinkSourcesStale = true") < source_refresh.index(
        "Promise.allSettled"
    )
    assert source_refresh.index("setAlertResolutionProjectionReadOnly(true)") < (
        source_refresh.index("Promise.allSettled")
    )
    renderer = _function_source("renderAlerts", "alertResolutionProvenanceLabel")
    assert "alertResolutionIntentOwner !== null" in renderer

    script = "\n".join(
        [
            """
let phiEpoch = 0;
let latestProfileRevision = 5;
let selectedAlertId = 'alert-removed';
let selectedAlertToken = 'token-old';
let selectedAlertProfileRevision = 5;
let alertSelectionEpoch = 1;
let alertResolutionDialogOpen = true;
let alertResolutionMutationPending = true;
const owner = {};
let alertResolutionIntentOwner = owner;
let alertProjectionStale = false;
let alertLinkSourcesStale = false;
let alertsById = new Map([
  ['alert-removed', { id: 'alert-removed', resolve_token: 'token-old' }],
]);
let convergenceCalls = 0;
let contextRedactions = 0;
function alertResolutionIntentOwnsMutation(intent) {
  return alertResolutionMutationPending
    && alertResolutionIntentOwner === intent.owner
    && intent.requestAlertEpoch === alertSelectionEpoch
    && intent.alertId === selectedAlertId;
}
function captureAlertResolutionDraft() {}
function clearAlertResolutionRetry() {}
function redactAlertResolutionCard(id) { alertsById.delete(id); }
function redactAlertResolutionContext() { contextRedactions += 1; }
function renderAlerts() {}
function setAlertResolutionProjectionReadOnly() {}
function updateAlertResolutionFormValidity() {}
async function loadStatus() {
  latestProfileRevision = 6;
  return { profile_revision: 6, workflow_revision: 2 };
}
async function refreshClinicalWorkflowState() {
  convergenceCalls += 1;
  return { verified: true };
}
""",
            _executable_function_source(
                "handleAlertResolutionConflict", "performAlertResolutionIntent"
            ),
            """
(async () => {
  const intent = {
    owner,
    alertId: 'alert-removed',
    requestPhiEpoch: 0,
    requestAlertEpoch: 1,
    body: { mutation_id: 'must-be-scrubbed' },
  };
  await handleAlertResolutionConflict(new Error('changed'), intent);
  console.log(JSON.stringify({
    convergenceCalls,
    contextRedactions,
    bodyCleared: Object.keys(intent.body).length === 0,
    projectionAuthoritative: alertProjectionStale === false,
    linksLockedForMissingTarget: alertLinkSourcesStale === true,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "convergenceCalls": 1,
        "contextRedactions": 2,
        "bodyCleared": True,
        "projectionAuthoritative": True,
        "linksLockedForMissingTarget": True,
    }


def test_alert_resolution_filters_link_sources_and_labels_provenance_precisely():
    source_options = _function_source(
        "eligibleAlertFollowUps", "renderAlertResolutionDecisionOptions"
    )
    decision_options = _function_source(
        "renderAlertResolutionDecisionOptions", "renderAlertResolutionLinkMode"
    )
    provenance = _function_source(
        "alertResolutionProvenanceLabel", "updateAlertResolutionProvenance"
    )
    result = _function_source("renderAlertResolutionResult", "handleAlertResolutionConflict")
    assert "['open', 'in_progress'].includes(item.status)" in source_options
    assert "['planned', 'in_progress'].includes(item.status)" in source_options
    assert "['active', 'needs_confirmation'].includes(item.status)" in decision_options
    assert "escHtml(item.id)" in source_options
    assert "escHtml(visit.id)" in source_options
    assert "escHtml(label)" in source_options
    assert "escHtml(item.id)" in decision_options
    assert "escHtml(item.text)" in decision_options
    assert "Caregiver-entered · attributed to clinician · unverified" in provenance
    assert "Caregiver-entered · caregiver reported · unverified" in provenance
    assert "Caregiver-entered administrative outcome · not clinical evidence" in provenance
    assert "source-verified" not in provenance
    assert "resolution.provenance" in result
    assert "resolution.follow_up_id" in result
    assert "resolution.visit_id" in result
    assert "resolution.decision_id" in result
    assert "escHtml(link)" in result


def test_alert_resolution_conflict_offline_and_eviction_fail_closed():
    conflict = _function_source("handleAlertResolutionConflict", "performAlertResolutionIntent")
    performer = _function_source("performAlertResolutionIntent", "submitAlertResolution")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    polling = _function_source("startPolling", "currentVisit")
    assert "captureAlertResolutionDraft()" in conflict
    assert "clearAlertResolutionRetry()" in conflict
    assert "redactAlertResolutionContext(" in conflict
    assert "alertProjectionStale = true" in conflict
    assert "alertLinkSourcesStale = true" in conflict
    assert "pendingAlertResolutionIntent = intent" in performer
    assert "Retrying the unchanged request" in performer
    assert "alertResolutionDrafts = new Map()" in eviction
    assert "pendingAlertResolutionIntent.body = {}" in eviction
    assert "activeAlertResolutionIntent.body = {}" in eviction
    assert "selectedAlertToken = null" in eviction
    assert "alertSelectionEpoch += 1" in eviction
    assert "clear('alert-resolution-message')" in eviction
    assert "alertResolutionOverlay.inert = true" in eviction
    assert "'alert-resolution-outcome-text'" in eviction
    assert "'alert-resolution-follow-up-select'" in eviction
    assert '"alert-resolution-link-mode"' in eviction
    assert "alertResolutionDrafts = new Map()" in eviction
    assert "loadFollowUps()" not in polling
    assert "loadVisits()" not in polling


def test_alert_resolution_markup_is_shared_semantic_and_keyboard_managed():
    assert INDEX_HTML.count('id="alert-resolution-dialog"') == 1
    assert (
        'role="dialog"'
        in INDEX_HTML[
            INDEX_HTML.index('id="alert-resolution-dialog"') - 120 : INDEX_HTML.index(
                'id="alert-resolution-dialog"'
            )
            + 250
        ]
    )
    assert 'aria-modal="true"' in INDEX_HTML
    assert 'aria-labelledby="alert-resolution-title"' in INDEX_HTML
    assert 'role="status" aria-live="polite"' in INDEX_HTML
    assert 'role="alert" aria-live="polite"' in INDEX_HTML
    assert 'maxlength="2000"' in INDEX_HTML
    assert 'maxlength="1000"' in INDEX_HTML
    assert 'maxlength="100"' in INDEX_HTML
    assert 'name="alert-resolution-link-mode"' in INDEX_HTML
    assert "contact, ask, discuss, or confirm" in INDEX_HTML.lower()
    escape_handler = APP_JS[
        APP_JS.index("document.addEventListener('keydown'") : APP_JS.index("function switchTab")
    ]
    assert escape_handler.index("alertResolutionDialogOpen") < escape_handler.index(
        "followUpDialogOpen"
    )
    closer = _function_source("closeAlertResolutionDialog", "closeAlertResolutionFromBackdrop")
    assert "alertResolutionMutationPending && !force" in closer
    assert "deactivateDialog(dialog)" in closer
    opener = _function_source("openAlertResolutionDialog", "closeAlertResolutionDialog")
    assert "activateDialog(dialog, trigger)" in opener


def test_alert_resolution_dialog_is_responsive_focusable_and_overflow_safe():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        for width, height in ((1280, 900), (360, 800)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(INDEX_HTML)
            page.add_style_tag(content=CSS)
            page.evaluate(
                """() => {
                  const overlay = document.getElementById('alert-resolution-overlay');
                  const dialog = document.getElementById('alert-resolution-dialog');
                  overlay.inert = false;
                  dialog.inert = false;
                  overlay.classList.add('open');
                  overlay.setAttribute('aria-hidden', 'false');
                }"""
            )
            controls = page.locator(
                "#alert-resolution-dialog button, "
                "#alert-resolution-dialog input, "
                "#alert-resolution-dialog textarea, "
                "#alert-resolution-dialog select"
            )
            if width == 360:
                heights = controls.evaluate_all(
                    "(items) => items.filter(item => item.offsetParent !== null)"
                    ".map(item => item.getBoundingClientRect().height)"
                )
                assert heights
                assert all(item >= 44 for item in heights)
            overflow = page.evaluate(
                """() => ({
                  document: document.documentElement.scrollWidth
                    - document.documentElement.clientWidth,
                  dialog: document.getElementById('alert-resolution-dialog').scrollWidth
                    - document.getElementById('alert-resolution-dialog').clientWidth,
                })"""
            )
            assert overflow == {"document": 0, "dialog": 0}
            page.locator("#alert-resolution-close").focus()
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
            assert focus["id"] == "alert-resolution-close"
            assert focus["outline"] != "none"
            assert focus["width"] >= 3
            page.close()
        browser.close()


def test_alert_resolution_live_browser_modes_conflict_offline_auth_and_late_response():
    playwright_api = pytest.importorskip("playwright.sync_api")
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)
    status_v5 = {
        "profile_revision": 5,
        "workflow_revision": 1,
        "patient": {},
        "stats": {},
        "alerts": [
            {
                "id": "alert-a",
                "resolve_token": "token-a",
                "message": "Sensitive alert A",
                "action_required": "Ask the treating team",
                "priority": "high",
            },
            {
                "id": "alert-b",
                "resolve_token": "token-b",
                "message": "Sibling alert B",
                "priority": "normal",
            },
        ],
        "treatments_classified": [],
        "recent_biomarkers": [],
    }
    follow_ups_v5 = {
        "profile_revision": 5,
        "workflow_revision": 1,
        "items": [{"id": "action-a", "text": "Call clinic", "status": "open"}],
    }
    visits_v5 = {
        "profile_revision": 5,
        "workflow_revision": 1,
        "appointments": [],
        "items": [
            {
                "id": "visit-a",
                "title": "Oncology",
                "status": "planned",
                "decisions": [
                    {
                        "id": "decision-a",
                        "text": "Continue discussion",
                        "status": "active",
                    }
                ],
            }
        ],
    }
    summary_v5 = {"status": "not_generated", "profile_revision": 5}
    payloads = {
        "/api/status": status_v5,
        "/api/follow-ups": follow_ups_v5,
        "/api/visits": visits_v5,
        "/api/summary": summary_v5,
        "/api/jobs": [],
        "/api/questions": [],
        "/api/judgments": [],
        "/api/symptoms": [],
        "/api/patient/evidence": {},
    }

    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        for width, height in ((1280, 900), (360, 800)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page_errors = []
            page.on(
                "pageerror",
                lambda error, errors=page_errors: errors.append(str(error)),
            )

            def fulfill(route):
                path = "/" + route.request.url.split("/", 3)[-1].split("?", 1)[0]
                payload = payloads.get(path, {})
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                )

            page.route("**/api/**", fulfill)
            page.set_content(html)
            page.add_style_tag(content=CSS)
            page.add_script_tag(content=APP_JS)
            page.wait_for_function("() => !clinicalConvergenceRunning")
            page.evaluate(
                """() => {
                  clearTimeout(pollingInterval);
                  pollingInterval = null;
                }"""
            )
            page.locator("#nav-patient").click()
            page.locator('[data-alert-id="alert-a"] .resolve-btn').click()
            page.locator("#alert-resolution-dialog").wait_for(state="visible")
            page.wait_for_function(
                "() => document.getElementById('alert-resolution-follow-up-select').options.length > 1"
            )

            bodies = {}
            mode_inputs = {
                "none": None,
                "follow_up": ("#alert-resolution-follow-up-select", "action-a"),
                "inline": ("#alert-resolution-follow-up-text", "Ask the treating team"),
                "visit": ("#alert-resolution-visit-select", "visit-a"),
            }
            for mode, entry in mode_inputs.items():
                page.locator(f'input[name="alert-resolution-link-mode"][value="{mode}"]').check()
                if entry:
                    page.locator(entry[0]).fill(entry[1]) if entry[0].endswith(
                        "text"
                    ) else page.locator(entry[0]).select_option(entry[1])
                if mode == "visit":
                    page.locator("#alert-resolution-decision-select").select_option("decision-a")
                bodies[mode] = page.evaluate(
                    """() => {
                      const body = createAlertResolutionBody(alertsById.get('alert-a'));
                      delete body.mutation_id;
                      return body;
                    }"""
                )
                visible_panels = page.locator(
                    "#alert-resolution-existing-follow-up:not([hidden]), "
                    "#alert-resolution-inline-follow-up:not([hidden]), "
                    "#alert-resolution-visit-link:not([hidden])"
                ).count()
                assert visible_panels == (0 if mode == "none" else 1)

            assert set(bodies["none"]) == {
                "expected_token",
                "expected_profile_revision",
            }
            assert bodies["follow_up"]["follow_up_id"] == "action-a"
            assert bodies["inline"]["follow_up"] == {
                "text": "Ask the treating team",
                "owner": None,
                "due_date": None,
            }
            assert bodies["visit"]["visit_id"] == "visit-a"
            assert bodies["visit"]["decision_id"] == "decision-a"
            if width == 360:
                hit_targets = page.locator(
                    "#alert-resolution-close, "
                    ".alert-resolution-link-modes label, "
                    ".alert-resolution-confirm, "
                    ".follow-up-dialog-actions .button"
                )
                heights = hit_targets.evaluate_all(
                    """items => items
                      .filter(item => item.offsetParent !== null)
                      .map(item => item.getBoundingClientRect().height)"""
                )
                assert heights and all(item >= 44 for item in heights)
                assert page.evaluate(
                    "() => document.documentElement.scrollWidth === document.documentElement.clientWidth"
                )

            page.evaluate("alertResolutionMutationPending = true")
            page.keyboard.press("Escape")
            assert page.locator("#alert-resolution-overlay").get_attribute("aria-hidden") == "false"
            page.evaluate("alertResolutionMutationPending = false")
            page.keyboard.press("Escape")
            assert page.locator("#alert-resolution-overlay").get_attribute("aria-hidden") == "true"
            assert page.locator('[data-alert-id="alert-a"] .resolve-btn').evaluate(
                "button => button === document.activeElement"
            )

            page.locator('[data-alert-id="alert-a"] .resolve-btn').click()
            page.locator('input[name="alert-resolution-link-mode"][value="inline"]').check()
            page.locator("#alert-resolution-follow-up-text").fill(
                "Ask the treating team about timing"
            )
            page.locator("#alert-resolution-outcome-text").fill("Caregiver draft survives conflict")
            page.locator("#alert-resolution-confirm").check()
            page.evaluate(
                """({ status, followUps, visits, summary }) => {
                  const response = (value, code = 200) => new Response(
                    JSON.stringify(value),
                    { status: code, headers: { 'Content-Type': 'application/json' } }
                  );
                  const originalFetch = window.fetch;
                  window.__authoritativeFetch = (url, options = {}) => {
                    const path = new URL(String(url), document.baseURI).pathname;
                    if (path.endsWith('/resolve')) {
                      return Promise.resolve(response({ error: 'Alert changed' }, 409));
                    }
                    if (path === '/api/status') return Promise.resolve(response(status));
                    if (path === '/api/follow-ups') {
                      return Promise.resolve(response(followUps));
                    }
                    if (path === '/api/visits') return Promise.resolve(response(visits));
                    if (path === '/api/summary') return Promise.resolve(response(summary));
                    if (path === '/api/jobs' || path === '/api/questions') {
                      return Promise.resolve(response([]));
                    }
                    return originalFetch(url, options);
                  };
                  window.fetch = window.__authoritativeFetch;
                }""",
                {
                    "status": {
                        **status_v5,
                        "profile_revision": 6,
                        "workflow_revision": 2,
                        "alerts": [
                            {
                                **status_v5["alerts"][0],
                                "resolve_token": "token-a-fresh",
                                "message": "Fresh alert A",
                            },
                            status_v5["alerts"][1],
                        ],
                    },
                    "followUps": {
                        **follow_ups_v5,
                        "profile_revision": 6,
                        "workflow_revision": 2,
                    },
                    "visits": {
                        **visits_v5,
                        "profile_revision": 6,
                        "workflow_revision": 2,
                    },
                    "summary": {
                        "status": "not_generated",
                        "profile_revision": 6,
                    },
                },
            )
            page.locator("#alert-resolution-submit").click()
            page.wait_for_timeout(1000)
            conflict_state = page.evaluate(
                """() => ({
                  status: document.getElementById('alert-resolution-status').textContent,
                  pending: alertResolutionMutationPending,
                  owner: alertResolutionIntentOwner !== null,
                  selectedAlertId,
                  selectedAlertToken,
                  selectedAlertProfileRevision,
                  latestProfileRevision,
                  alertProjectionStale,
                  alertLinkSourcesStale,
                })"""
            )
            assert "Review the reloaded alert" in conflict_state["status"], json.dumps(
                {"state": conflict_state, "errors": page_errors}
            )
            assert (
                page.locator("#alert-resolution-outcome-text").input_value()
                == "Caregiver draft survives conflict"
            )
            assert page.locator("#alert-resolution-retry").is_hidden()
            assert page.locator('[data-alert-id="alert-b"]').count() == 1
            assert page.locator("#alert-resolution-message").text_content() == "Fresh alert A"

            page.evaluate(
                """async () => {
                  const authoritativeFetch = window.fetch;
                  let resolveLate;
                  window.fetch = (url, options = {}) => {
                    const path = new URL(String(url), document.baseURI).pathname;
                    if (path === '/api/follow-ups') {
                      return new Promise(resolve => { resolveLate = resolve; });
                    }
                    return authoritativeFetch(url, options);
                  };
                  const pending = refreshAlertResolutionSources(
                    alertResolutionIntentOwner
                  );
                  await Promise.resolve();
                  closeAlertResolutionDialog();
                  resolveLate(new Response(JSON.stringify({
                    profile_revision: 6,
                    workflow_revision: 2,
                    items: [{
                      id: 'late-action',
                      text: 'Late PHI must not render',
                      status: 'open'
                    }]
                  }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' }
                  }));
                  await pending;
                  window.fetch = authoritativeFetch;
                }"""
            )
            assert page.locator("#alert-resolution-overlay").get_attribute("aria-hidden") == "true"
            assert (
                "Late PHI must not render"
                not in page.locator("#alert-resolution-follow-up-select").inner_text()
            )

            page.locator('[data-alert-id="alert-a"] .resolve-btn').click()
            page.locator('input[name="alert-resolution-link-mode"][value="inline"]').check()
            page.locator("#alert-resolution-follow-up-text").fill("Caregiver offline draft")
            page.evaluate(
                """async () => {
                  const authoritativeFetch = window.fetch;
                  window.fetch = (url, options = {}) => {
                    const path = new URL(String(url), document.baseURI).pathname;
                    if (path === '/api/follow-ups' || path === '/api/visits') {
                      return Promise.reject(new TypeError('offline'));
                    }
                    return authoritativeFetch(url, options);
                  };
                  await refreshAlertResolutionSources(alertResolutionIntentOwner);
                }"""
            )
            assert (
                page.locator("#alert-resolution-follow-up-text").input_value()
                == "Caregiver offline draft"
            )
            assert (
                page.locator("#alert-resolution-link-modes").get_attribute("aria-disabled")
                == "true"
            )
            assert page.locator('[data-alert-id="alert-a"] .resolve-btn').is_disabled()

            page.locator("#alert-resolution-outcome-text").fill("Secret draft")
            page.evaluate(
                """async () => {
                  window.fetch = async () => new Response(
                    JSON.stringify({ error: 'denied' }),
                    { status: 401, headers: { 'Content-Type': 'application/json' } }
                  );
                  await loadStatus();
                }"""
            )
            assert page.locator("#alert-resolution-overlay").get_attribute("aria-hidden") == "true"
            assert page.locator("#alert-resolution-outcome-text").input_value() == ""
            assert page.locator("#alert-resolution-follow-up-select").inner_text() == ""
            assert page.locator("#alerts-list").inner_text() == ""
            assert page.evaluate(
                """() => alertResolutionIntentOwner === null
                  && alertResolutionDrafts.size === 0
                  && selectedAlertId === null"""
            )

            page.close()
        browser.close()


def _run_alert_resolution_race_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 0;
let latestProfileRevision = 5;
let workflowRevision = 1;
let selectedAlertId = 'alert-a';
let selectedAlertToken = 'token-a';
let selectedAlertProfileRevision = 5;
let alertSelectionEpoch = 1;
let alertResolutionDialogOpen = true;
let alertResolutionMutationPending = true;
let alertResolutionIntentOwner = { name: 'owner-a' };
let activeAlertResolutionIntent = null;
let pendingAlertResolutionIntent = null;
let alertProjectionStale = false;
let alertLinkSourcesStale = false;
let alertResolutionDrafts = new Map([['resolve:alert-a', { text: 'draft-a' }]]);
let alertsById = new Map([
  ['alert-a', { id: 'alert-a', resolve_token: 'token-a' }],
  ['alert-b', { id: 'alert-b', resolve_token: 'token-b' }],
  ['alert-c', { id: 'alert-c', resolve_token: 'token-c' }],
  ['alert-auth', { id: 'alert-auth', resolve_token: 'token-auth' }],
]);
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {
    disabled: false,
    hidden: true,
    textContent: '',
    className: '',
    dataset: {},
  });
  return elements.get(id);
};
const document = {
  getElementById: element,
  querySelectorAll() { return []; },
};
const navigator = { onLine: true };
const attempts = [];
const statuses = [];
let resultRenders = 0;
let successReports = 0;
let evictions = 0;
let draftCaptures = 0;

function alertResolutionOwnerIsCurrent(owner, expectedPhiEpoch = phiEpoch) {
  return alertResolutionIntentOwner === owner
    && alertResolutionDialogOpen
    && expectedPhiEpoch === phiEpoch;
}
function setAlertResolutionBusy() {}
function setAlertResolutionProjectionReadOnly() {}
function renderAlerts() {}
function updateAlertResolutionFormValidity() {}
function setAlertResolutionStatus(message, tone) { statuses.push([message, tone]); }
function clearAlertResolutionRetry() {
  if (pendingAlertResolutionIntent?.body) pendingAlertResolutionIntent.body = {};
  pendingAlertResolutionIntent = null;
  element('alert-resolution-retry').hidden = true;
}
function captureAlertResolutionDraft() { draftCaptures += 1; }
function reportLoadError() {}
function reportLoadSuccess() { successReports += 1; }
function setFormError() {}
function shouldEvictClientPhi(error) {
  return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
}
function evictClientPhi() {
  evictions += 1;
  phiEpoch += 1;
  if (pendingAlertResolutionIntent?.body) pendingAlertResolutionIntent.body = {};
  if (activeAlertResolutionIntent?.body) activeAlertResolutionIntent.body = {};
  pendingAlertResolutionIntent = null;
  activeAlertResolutionIntent = null;
  alertResolutionIntentOwner = null;
  alertResolutionMutationPending = false;
  alertResolutionDrafts = new Map();
  alertsById = new Map();
  selectedAlertId = null;
}
function authorizePatientResponse() { return { accepted: true, profileAdvanced: false }; }
async function refreshClinicalWorkflowState() { return { verified: true }; }
function renderAlertResolutionResult() { resultRenders += 1; }
""",
            _function_source("alertResolutionIntentOwnsMutation", "releaseAlertResolutionMutation"),
            _function_source("releaseAlertResolutionMutation", "renderAlertResolutionResult"),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("performAlertResolutionIntent", "submitAlertResolution"),
            _executable_function_source("retryAlertResolution", "loadPatientEvidence"),
            """
function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
function intent(id, token, owner, epoch, mutation) {
  return {
    owner,
    alertId: id,
    expectedToken: token,
    expectedProfileRevision: 5,
    requestPhiEpoch: phiEpoch,
    requestAlertEpoch: epoch,
    body: {
      mutation_id: mutation,
      expected_token: token,
      expected_profile_revision: 5,
      outcome: { kind: 'caregiver_reported', text: `outcome-${id}` },
    },
    draftKey: `resolve:${id}`,
  };
}

(async () => {
  let resolveLate;
  globalThis.fetch = (url, options) => {
    attempts.push(JSON.parse(options.body));
    return new Promise(resolve => { resolveLate = resolve; });
  };
  const ownerA = alertResolutionIntentOwner;
  const intentA = intent('alert-a', 'token-a', ownerA, 1, 'mutation-a');
  const lateA = performAlertResolutionIntent(intentA);
  await Promise.resolve();

  const ownerB = { name: 'owner-b' };
  selectedAlertId = 'alert-b';
  selectedAlertToken = 'token-b';
  alertSelectionEpoch = 2;
  alertResolutionIntentOwner = ownerB;
  alertResolutionMutationPending = true;
  resolveLate(response(200, {
    alert: { id: 'alert-a', resolution: {} },
    profile_revision: 6,
    workflow_revision: 2,
  }));
  const lateResult = await lateA;
  const bStillOwns = alertResolutionIntentOwner === ownerB
    && alertResolutionMutationPending
    && selectedAlertId === 'alert-b';

  selectedAlertId = 'alert-c';
  selectedAlertToken = 'token-c';
  selectedAlertProfileRevision = 5;
  alertSelectionEpoch = 3;
  const ownerC = { name: 'owner-c' };
  alertResolutionIntentOwner = ownerC;
  alertResolutionMutationPending = true;
  const intentC = intent('alert-c', 'token-c', ownerC, 3, 'mutation-c');
  globalThis.fetch = async (url, options) => {
    attempts.push(JSON.parse(options.body));
    throw new TypeError('offline');
  };
  const offlineResult = await performAlertResolutionIntent(intentC);
  const pendingAfterOffline = pendingAlertResolutionIntent === intentC;
  const exactBody = JSON.stringify(intentC.body);
  globalThis.fetch = async (url, options) => {
    attempts.push(JSON.parse(options.body));
    return response(200, {
      alert: {
        id: 'alert-c',
        resolution: {
          outcome_kind: 'caregiver_reported',
          outcome_text: 'outcome-alert-c',
          provenance: {
            capture_method: 'caregiver_entered',
            attributed_to: 'patient_or_caregiver',
            source_verification: 'unverified',
          },
        },
      },
      profile_revision: 5,
      workflow_revision: 1,
    });
  };
  await retryAlertResolution();
  const retryExact = exactBody === JSON.stringify(attempts[2]);

  selectedAlertId = 'alert-auth';
  selectedAlertToken = 'token-auth';
  selectedAlertProfileRevision = 5;
  alertSelectionEpoch = 4;
  const ownerAuth = { name: 'owner-auth' };
  alertResolutionIntentOwner = ownerAuth;
  alertResolutionMutationPending = true;
  alertResolutionDrafts = new Map([['resolve:alert-auth', { text: 'secret draft' }]]);
  const intentAuth = intent(
    'alert-auth', 'token-auth', ownerAuth, 4, 'mutation-auth'
  );
  globalThis.fetch = async (url, options) => {
    attempts.push(JSON.parse(options.body));
    return response(401, { error: 'denied' });
  };
  const authResult = await performAlertResolutionIntent(intentAuth);

  console.log(JSON.stringify({
    lateResult,
    bStillOwns,
    offlineResult,
    pendingAfterOffline,
    retryExact,
    retryMutation: attempts[2].mutation_id,
    resultRenders,
    successReports,
    authResult,
    evictions,
    authStateScrubbed: alertsById.size === 0
      && alertResolutionDrafts.size === 0
      && alertResolutionIntentOwner === null
      && alertResolutionMutationPending === false
      && selectedAlertId === null
      && Object.keys(intentAuth.body).length === 0,
    draftCaptures,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_alert_resolution_late_selection_offline_retry_and_auth_eviction_are_authoritative():
    result = _run_alert_resolution_race_probe()
    assert result == {
        "lateResult": None,
        "bStillOwns": True,
        "offlineResult": None,
        "pendingAfterOffline": True,
        "retryExact": True,
        "retryMutation": "mutation-c",
        "resultRenders": 1,
        "successReports": 1,
        "authResult": None,
        "evictions": 1,
        "authStateScrubbed": True,
        "draftCaptures": 1,
    }


def test_patient_history_joins_documents_and_keeps_orphaned_legacy_records():
    history = _function_source("renderPatientEvidence", "toggleSourceHistory")
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


def test_treatment_ui_has_no_status_fallback_or_legacy_mutation_authority():
    sidebar = _function_source("renderSidebar", "renderAlerts")
    assert "treatments_fallback" not in sidebar
    assert "treatments_classified" not in sidebar
    assert "current_treatments" not in sidebar
    assert "tx-list" not in APP_JS


def test_treatment_actions_use_only_reconciliation_projection_authority():
    assert "/api/patient/treatment-reconciliation" in APP_JS
    assert "/api/treatment-reconciliation/courses" in APP_JS
    assert "/api/treatment-reconciliation/discrepancies" in APP_JS
    assert "/api/treatments/" not in APP_JS
    assert "/api/treatments/update" not in APP_JS
    assert "expected_profile_revision: treatmentProjection.profile_revision" in APP_JS
    assert "expected_workflow_revision: treatmentProjection.workflow_revision" in APP_JS
    assert "expected_projection_token: treatmentProjection.projection_token" in APP_JS
    assert "body: intent.bodyText" in APP_JS


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
    assert "symptomElement('h3', '', episode.symptom_text)" in APP_JS


def test_malicious_stored_display_fields_are_escaped():
    escaped_expressions = (
        "escHtml(biomarkerScalar(observation.value.raw))",
        "escHtml(biomarkerScalar(observation.reference_range))",
        "escHtml(p.sex || '—')",
        "escHtml(alert.priority || '—')",
        "escHtml(j.date||'')",
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
let workflowMutationOwner = null;
let followUpMutationPending = false;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
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
async function refreshClinicalWorkflowState() { return { verified: true }; }
async function handleWorkflowConflict() { return true; }
function shouldEvictClientPhi(error) { return Number(error?.status) >= 500; }
function evictClientPhi(error) { evictions.push(error.status); }
function setAppointmentMutationBusy() {}
function setFollowUpMutationBusy() {}
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
function followUpControlsLocked() {
  return followUpMutationPending
    || pendingFollowUpCompletion !== null
    || summaryActionMutationOwner !== null
    || workflowMutationPending;
}
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
  workflowMutationOwner = {};
  workflowMutationPending = true;
  visitAIntent.mutationOwner = workflowMutationOwner;
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
  const hardIntent = {
    ...visitAIntent,
    body: { source_kind: 'manual', mutation_id: 'mutation-a-hard-failure' },
    visitId: 'visit-b',
    requestVisitEpoch: 5,
  };
  workflowMutationOwner = {};
  workflowMutationPending = true;
  hardIntent.mutationOwner = workflowMutationOwner;
  const hardFailureResult = await performWorkflowIntent(hardIntent);

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
  workflowMutationOwner = {};
  workflowMutationPending = true;
  offlineIntent.mutationOwner = workflowMutationOwner;
  const offlineResult = await performWorkflowIntent(offlineIntent);
  const offlineRetryPreserved = pendingWorkflowIntent === offlineIntent;

  globalThis.fetch = async () => { throw new TypeError('offline follow-up'); };
  const offlineFollowUpIntent = {
    ...offlineIntent,
    url: '/api/visits/visit-b/follow-ups',
    body: { text: 'caregiver follow-up', mutation_id: 'mutation-follow-up-offline' },
  };
  workflowMutationOwner = {};
  workflowMutationPending = true;
  offlineFollowUpIntent.mutationOwner = workflowMutationOwner;
  const offlineFollowUpResult = await performWorkflowIntent(offlineFollowUpIntent);
  followUpProjectionStale = false;
  const abortError = new Error('aborted follow-up');
  abortError.name = 'AbortError';
  globalThis.fetch = async () => { throw abortError; };
  const abortedFollowUpIntent = {
    ...offlineIntent,
    url: '/api/visits/visit-b/follow-ups',
    body: { text: 'caregiver follow-up', mutation_id: 'mutation-follow-up-abort' },
  };
  workflowMutationOwner = {};
  workflowMutationPending = true;
  abortedFollowUpIntent.mutationOwner = workflowMutationOwner;
  const abortedFollowUpResult = await performWorkflowIntent(abortedFollowUpIntent);

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
let visitLoadEpoch = 2;
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
let followUpMutationOwner = { patient: true };
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
let alertsById = new Map([['alert-phi', { patient: true }]]);
let alertProjectionStale = true;
let alertLinkSourcesStale = true;
let selectedAlertId = 'alert-phi';
let alertSelectionEpoch = 2;
let alertResolutionDialogOpen = true;
let alertResolutionIntentOwner = { patient: true };
let alertResolutionMutationPending = true;
const pendingAlertResolutionIntentRef = { body: { text: 'SECRET alert pending body' } };
let pendingAlertResolutionIntent = pendingAlertResolutionIntentRef;
const activeAlertResolutionIntentRef = { body: { text: 'SECRET alert active body' } };
let activeAlertResolutionIntent = activeAlertResolutionIntentRef;
let alertResolutionDrafts = new Map([['resolve:alert-phi', { patient: true }]]);
let alertResolutionResult = { patient: true };
let chatHistory = [{ patient: true }];
let chatHistoryRevision = 41;
let chatOpen = true;
let taskSelectionEpoch = 2;
let phiEpoch = 5;
let statusLoadEpoch = 2;
let summaryLoadEpoch = 2;
let taskLoadEpoch = 2;
let lastDialogTrigger = { patient: true };
let activeDialogSurface = appointmentDialog;

function renderLatestResearchUpdate() {}
function clearFreshnessProjection() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
function setFollowUpMutationBusy() {}
function setAlertResolutionBusy() {}
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
    completed = _run_node_script(script, str(status))
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
    completed = _run_node_script(script)
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
    completed = _run_node_script(script)
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
function workflowIntentOwnsMutation() { return true; }
function captureAppointmentDraft() {}
function clearWorkflowRetry() {}
function redactGeneratedSummaryActions() {}
function revisionArray(revision) {
  const items = [];
  items.profileRevision = revision;
  items.workflowRevision = 4;
  return items;
}
function loadStatus() { return Promise.resolve({ profile_revision: 8 }); }
function loadSummary() { return Promise.resolve({ profile_revision: 8 }); }
function loadTasks() { return Promise.resolve([]); }
function loadVisits() { return Promise.resolve(revisionArray(8)); }
function loadFollowUps() { return Promise.resolve(revisionArray(8)); }
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
    completed = _run_node_script(script)
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
    owner = _function_source("beginWorkflowMutation", "createWorkflowIntent")
    intent = _function_source("createWorkflowIntent", "workflowIntentCanRender")
    performer = _function_source("performWorkflowIntent", "submitWorkflowMutation")
    submitter = _function_source("submitWorkflowMutation", "retryWorkflowIntent")
    retry = _function_source("retryWorkflowIntent", "readJsonResponse")
    invalidation = _function_source(
        "invalidateWorkflowRetryOnDraftChange", "setAppointmentMutationBusy"
    )
    generated = _function_source("addGeneratedVisitQuestion", "addManualVisitQuestion")
    ordering = _function_source("persistVisitQuestionOrder", "reorderedQuestionList")

    assert "crypto?.randomUUID" in mutation
    assert "mutation_id: newMutationId()" in intent
    assert owner.index("workflowMutationOwner = owner") < owner.index(
        "workflowMutationPending = true"
    )
    assert submitter.index("beginWorkflowMutation()") < submitter.index("createWorkflowIntent(")
    assert "workflowIntentOwnsMutation(intent)" in performer
    assert "releaseWorkflowMutation(intent)" in performer
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


def test_stale_workflow_finally_cannot_release_newer_mutation_owner():
    script = "\n".join(
        [
            """
let phiEpoch = 4;
let visitSelectionEpoch = 7;
let selectedVisitId = 'visit-1';
let workflowMutationPending = false;
let workflowMutationOwner = null;
let activeWorkflowIntent = null;
let pendingWorkflowIntent = null;
let followUpMutationPending = false;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let mutationIds = 0;
let busyReleases = 0;
let resolveA;
let resolveB;
const fetches = [];
const document = { getElementById() { return null; } };

function newMutationId() { mutationIds += 1; return `mutation-${mutationIds}`; }
function setAppointmentMutationBusy(busy) { if (!busy) busyReleases += 1; }
function setFollowUpMutationBusy() {}
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
function updateAppointmentFormValidity() {}
function setAppointmentMessage() {}
function clearWorkflowRetry() { pendingWorkflowIntent = null; }
function reportLoadError() {}
function shouldEvictClientPhi() { return false; }
function handleWorkflowConflict() { return Promise.resolve(true); }
function consumeWorkflowResponse(data, intent) {
  return Promise.resolve(workflowIntentOwnsMutation(intent) && data.ok);
}
function followUpControlsLocked() {
  return followUpMutationPending
    || pendingFollowUpCompletion !== null
    || summaryActionMutationOwner !== null
    || workflowMutationPending;
}
function response(data) {
  return {
    status: 200,
    ok: true,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
function fetch(url) {
  fetches.push(url);
  return new Promise(resolve => {
    if (url === '/a') resolveA = resolve;
    else resolveB = resolve;
  });
}
""",
            _function_source("beginWorkflowMutation", "createWorkflowIntent"),
            _function_source("createWorkflowIntent", "workflowIntentCanRender"),
            _executable_function_source("workflowIntentCanRender", "refreshClinicalWorkflowState"),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("performWorkflowIntent", "submitWorkflowMutation"),
            _executable_function_source("submitWorkflowMutation", "retryWorkflowIntent"),
            """
(async () => {
  const a = submitWorkflowMutation('/a', { value: 'a' }, 'visit-1');
  await Promise.resolve();
  const ownerA = workflowMutationOwner;

  // Simulate central eviction releasing A before its transport resolves.
  workflowMutationPending = false;
  workflowMutationOwner = null;
  activeWorkflowIntent = null;

  const b = submitWorkflowMutation('/b', { value: 'b' }, 'visit-1');
  await Promise.resolve();
  const ownerB = workflowMutationOwner;
  resolveA(response({ ok: true, item: { id: 'a' } }));
  const aResult = await a;
  const afterA = {
    pending: workflowMutationPending,
    ownerIsB: workflowMutationOwner === ownerB,
    activeIsB: activeWorkflowIntent?.mutationOwner === ownerB,
  };
  resolveB(response({ ok: true, item: { id: 'b' } }));
  const bResult = await b;
  console.log(JSON.stringify({
    distinctOwners: ownerA !== ownerB,
    aResult,
    bResult,
    afterA,
    finalPending: workflowMutationPending,
    finalOwner: workflowMutationOwner,
    fetches,
    mutationIds,
    busyReleases,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "distinctOwners": True,
        "aResult": None,
        "bResult": {"ok": True, "item": {"id": "b"}},
        "afterA": {"pending": True, "ownerIsB": True, "activeIsB": True},
        "finalPending": False,
        "finalOwner": None,
        "fetches": ["/a", "/b"],
        "mutationIds": 2,
        "busyReleases": 1,
    }


def test_appointment_revision_epoch_conflict_and_eviction_guards_are_complete():
    context = _function_source("workflowIntentCanRender", "refreshClinicalWorkflowState")
    refresh = _function_source("refreshClinicalWorkflowState", "consumeWorkflowResponse")
    consume = _function_source("consumeWorkflowResponse", "handleWorkflowConflict")
    conflicts = _function_source("handleWorkflowConflict", "performWorkflowIntent")
    performer = _function_source("performWorkflowIntent", "submitWorkflowMutation")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")

    assert "expectedPhiEpoch !== phiEpoch" in context
    assert "requestVisitEpoch !== visitSelectionEpoch" in context
    assert consume.index("if (!workflowIntentOwnsMutation(intent)) return false") < consume.index(
        "captureAppointmentDraft()"
    )
    assert consume.index("if (!workflowIntentOwnsMutation(intent)) return false") < consume.index(
        "authorizePatientResponse(intent, data, { workflow: 'targeted' })"
    )
    assert "return true" in consume
    assert conflicts.index(
        "if (!workflowIntentOwnsMutation(intent)) return false"
    ) < conflicts.index("clearWorkflowRetry()")
    consumed_guard = performer.index("if (!consumed")
    assert consumed_guard < performer.index("clearWorkflowRetry()", consumed_guard)
    catch_source = performer[performer.index("catch (error)") :]
    assert catch_source.index("if (!workflowIntentOwnsMutation(intent)) return null") < (
        catch_source.index("error?.status === 409")
    )
    authority = _function_source("advancePatientAuthority", "authorizePatientResponse")
    assert "phiEpoch += 1" in authority
    assert "taskSelectionEpoch += 1" in authority
    assert "syncChatRevision(revision, true, false)" in authority
    assert "taskSelectionEpoch += 1" in refresh
    assert refresh.index("const status = await loadStatus(guardedOptions)") < refresh.index(
        "loadSummary(guardedOptions)"
    )
    assert "syncChatRevision(statusRevision, true, false)" in refresh
    assert refresh.index("redactGeneratedQuestionChoices()") < refresh.index(
        "loadQuestions(guardedOptions)"
    )
    assert "loadSummary(guardedOptions)" in refresh
    assert "loadTasks(guardedOptions)" in refresh
    assert "loadVisits(guardedOptions)" in refresh
    assert "loadFollowUps(guardedOptions)" in refresh
    assert "return { verified }" in refresh
    assert "refreshResults.every" in refresh
    assert "setAppointmentMessage('Saved." not in refresh
    assert "loadQuestions()" in conflicts
    assert conflicts.index("redactGeneratedQuestionChoices()") < conflicts.index(
        "Promise.allSettled"
    )
    assert "performWorkflowIntent" not in conflicts
    release = _function_source("releaseWorkflowMutation", "refreshClinicalWorkflowState")
    assert "workflowMutationOwner !== intent.mutationOwner" in release
    assert "refreshGeneratedActionControls()" in release
    assert "updateFollowUpFormValidity()" in release
    assert "updateAppointmentFormValidity()" in release

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
    assert "['questions', 'decisions', 'followups', 'recap']" in tabs

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


def test_visit_recap_uses_atomic_projection_and_strict_authority_gates():
    loader = _function_source("loadVisitRecap", "requireCurrentVisitRecap")
    projection = _function_source("applyVisitRecapProjection", "loadVisitRecap")
    authority = _function_source("visitRecapAuthorityIsCurrent", "updateVisitRecapExportControls")
    stale = _function_source("markVisitRecapStale", "visitRecapAuthorityIsCurrent")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    polling = _function_source("startPolling", "revokeVisitRecapDownloadUrl")

    assert "/recap?expected_visit_token=" in loader
    assert "capturePatientRequest({ visitSelection: true })" in loader
    assert "requestLoadEpoch === visitRecapLoadEpoch" in loader
    assert "currentVisit()?.token === requestVisitToken" in loader
    assert "authorizePatientResponse(request, data, { workflow: 'projection' })" in loader
    assert loader.index("authorizePatientResponse(") < loader.index("applyVisitRecapProjection(")
    assert "visitRecapProjection = data.recap" in projection
    for expression in (
        "!appIsOffline()",
        "authority.phiEpoch === phiEpoch",
        "authority.visitSelectionEpoch === visitSelectionEpoch",
        "authority.requestEpoch === visitRecapLoadEpoch",
        "authority.visitId === selectedVisitId",
        "authority.visitToken === visit?.token",
        "authority.profileRevision === normalizedRevision(latestProfileRevision)",
        "authority.workflowRevision === normalizedRevision(workflowRevision)",
        "authority.recapToken === visitRecapAuthority?.recapToken",
    ):
        assert expression in authority
    assert "visitRecapAuthority = null" in stale
    assert "visitRecapExportText = ''" in stale
    assert "revokeVisitRecapDownloadUrl()" in stale
    assert "clearVisitRecap(true)" in eviction
    assert "loadVisitRecap" not in polling
    assert "localStorage" not in loader
    assert "sessionStorage" not in loader
    assert "console." not in loader


def test_visit_recap_actual_functions_scrub_identity_and_hide_non_exportable_controls():
    script = "\n".join(
        [
            """
class FakeClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
}

const elements = new Map();
const document = {
  activeElement: null,
  body: null,
  getElementById(id) {
    if (!elements.has(id)) {
      const node = {
        id,
        hidden: false,
        disabled: false,
        className: '',
        innerHTML: '',
        textContent: '',
        classList: new FakeClassList(),
        contains(other) {
          return this.id === 'visit-recap-actions'
            && ['visit-recap-copy', 'visit-recap-download', 'visit-recap-print']
              .includes(other?.id);
        },
        focus() { document.activeElement = this; },
        blur() { if (document.activeElement === this) document.activeElement = null; },
      };
      elements.set(id, node);
    }
    return elements.get(id);
  },
};
document.body = document.getElementById('body');
const actions = document.getElementById('visit-recap-actions');
const copy = document.getElementById('visit-recap-copy');
document.getElementById('visit-recap-download');
document.getElementById('visit-recap-print');
const recapTab = document.getElementById('appointment-tab-recap');
const content = document.getElementById('visit-recap-content');
document.getElementById('visit-recap-status');

let selectedVisitId = 'visit-a';
let visitsById = new Map([['visit-a', {
  id: 'visit-a', token: 'token-a', status: 'in_progress',
}]]);
let visitRecapLoadEpoch = 0;
let visitRecapProjection = null;
let visitRecapAuthority = null;
let visitRecapExportText = '';
let visitRecapStale = false;
let visitRecapState = 'idle';
let visitRecapMessage = '';
let visitRecapDownloadUrl = null;
let visitRecapExportEpoch = 0;
let visitRecapExportOwner = null;
let visitRecapNetworkAmbiguous = false;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'recap';
let phiEpoch = 4;
let visitSelectionEpoch = 8;
let latestProfileRevision = 12;
let workflowRevision = 9;
const revoked = [];
const URL = { revokeObjectURL(value) { revoked.push(value); } };
function normalizedRevision(value) { return value; }
function appIsOffline() { return false; }
""",
            _function_source("revokeVisitRecapDownloadUrl", "clearVisitRecap"),
            _function_source("clearVisitRecap", "scrubVisitRecapBeforeSelectionChange"),
            _function_source("scrubVisitRecapBeforeSelectionChange", "markVisitRecapStale"),
            _function_source("visitRecapAuthorityIsCurrent", "updateVisitRecapExportControls"),
            _function_source("updateVisitRecapExportControls", "recapPlainText"),
            _function_source("currentVisit", "visitStatusLabel"),
            """
function accept(status = 'in_progress', state = 'current', exportable = true) {
  visitsById.set(selectedVisitId, {
    id: selectedVisitId,
    token: `token-${selectedVisitId}`,
    status,
  });
  visitRecapProjection = {
    state,
    exportable,
    visit: { id: selectedVisitId, status },
  };
  visitRecapAuthority = {
    phiEpoch,
    visitSelectionEpoch,
    visitId: selectedVisitId,
    visitToken: `token-${selectedVisitId}`,
    profileRevision: latestProfileRevision,
    workflowRevision,
    recapToken: `recap-${selectedVisitId}`,
    recapState: state,
    exportable,
    visitStatus: status,
    requestEpoch: visitRecapLoadEpoch,
  };
  visitRecapExportText = exportable ? `Exact answer ${selectedVisitId}` : '';
  visitRecapStale = false;
  updateVisitRecapExportControls();
}

accept();
content.textContent = 'Exact answer A';
visitRecapDownloadUrl = 'blob:visit-a';
document.body.classList.add('visit-recap-printing');
copy.focus();
const identityChanged = scrubVisitRecapBeforeSelectionChange('visit-b', 'token-visit-b');
const identityScrub = {
  identityChanged,
  projection: visitRecapProjection,
  authority: visitRecapAuthority,
  exportText: visitRecapExportText,
  content: content.textContent,
  revoked: [...revoked],
  printing: document.body.classList.contains('visit-recap-printing'),
  actionsHidden: actions.hidden,
  controlsDisabled: ['visit-recap-copy', 'visit-recap-download', 'visit-recap-print']
    .every(id => document.getElementById(id).disabled),
  focus: document.activeElement?.id || null,
};

accept();
const unchanged = scrubVisitRecapBeforeSelectionChange('visit-a', 'token-visit-a');
const sameIdentityRetained = !unchanged && visitRecapProjection !== null;
const tokenChanged = scrubVisitRecapBeforeSelectionChange('visit-a', 'token-a-2');
const tokenScrubbed = tokenChanged && visitRecapProjection === null && actions.hidden;

const visibility = {};
for (const [name, status, state, exportable, stale] of [
  ['in_progress', 'in_progress', 'current', true, false],
  ['completed', 'completed', 'current', true, false],
  ['planned', 'planned', 'unavailable', false, false],
  ['cancelled', 'cancelled', 'administrative', false, false],
  ['unavailable', 'in_progress', 'unavailable', false, false],
  ['stale', 'in_progress', 'current', true, true],
]) {
  accept(status, state, exportable);
  visitRecapStale = stale;
  updateVisitRecapExportControls();
  visibility[name] = {
    hidden: actions.hidden,
    disabled: copy.disabled,
  };
}
accept();
clearVisitRecap(true);
visibility.authCleared = { hidden: actions.hidden, disabled: copy.disabled };

console.log(JSON.stringify({
  identityScrub,
  sameIdentityRetained,
  tokenScrubbed,
  visibility,
}));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["identityScrub"] == {
        "identityChanged": True,
        "projection": None,
        "authority": None,
        "exportText": "",
        "content": "",
        "revoked": ["blob:visit-a"],
        "printing": False,
        "actionsHidden": True,
        "controlsDisabled": True,
        "focus": "appointment-tab-recap",
    }
    assert result["sameIdentityRetained"] is True
    assert result["tokenScrubbed"] is True
    assert result["visibility"] == {
        "in_progress": {"hidden": False, "disabled": False},
        "completed": {"hidden": False, "disabled": False},
        "planned": {"hidden": True, "disabled": True},
        "cancelled": {"hidden": True, "disabled": True},
        "unavailable": {"hidden": True, "disabled": True},
        "stale": {"hidden": True, "disabled": True},
        "authCleared": {"hidden": True, "disabled": True},
    }


def test_visit_recap_plain_text_is_deterministic_exact_and_control_safe():
    script = "\n".join(
        [
            """
function visitStatusLabel(status) {
  return { in_progress: 'In progress', completed: 'Completed' }[status] || status;
}
""",
            _function_source("recapPlainText", "buildVisitRecapText"),
            _function_source("buildVisitRecapText", "recapSectionMarkup"),
            """
const recap = {
  state: 'current',
  exportable: true,
  visit: {
    title: 'Visit =SUM(A1:A2)',
    date: '2026-08-10',
    clinician: 'Dr <Exact>',
    status: 'completed',
  },
  sections: {
    what_was_asked: [{
      text: 'What\\r\\nwas asked?',
      status: 'answered',
      provenance_label: 'Generated question snapshot · not clinician-attributed',
    }],
    what_we_heard: [{
      question: 'What\\nwas asked?',
      text: 'Exact answer\\nsecond line',
      provenance_label: 'Caregiver-entered · attributed to clinician · unverified',
    }],
    decisions: [],
    unresolved: [{
      text: 'Unknown item',
      kind: 'unknown',
      provenance_label: 'Caregiver-entered · attributed to clinician · unverified',
    }],
  },
};
const text = buildVisitRecapText(recap);
let controlError = '';
try {
  buildVisitRecapText({ ...recap, visit: { ...recap.visit, title: 'bad\\u0000value' } });
} catch (error) {
  controlError = error.message;
}
console.log(JSON.stringify({
  text,
  controlError,
  formulaPreserved: text.includes('Title: Visit =SUM(A1:A2)'),
  crNormalized: !text.includes('\\r') && text.includes('What\\nwas asked?'),
  exactAnswer: text.includes('Answer: Exact answer\\nsecond line'),
  omittedEmpty: !text.includes('Decisions / needs confirmation'),
}));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["formulaPreserved"] is True
    assert result["crNormalized"] is True
    assert result["exactAnswer"] is True
    assert result["omittedEmpty"] is True
    assert "unsupported control characters" in result["controlError"]
    assert result["text"].endswith("\n")


def test_visit_recap_exports_recheck_authority_before_every_side_effect():
    current = _function_source("visitRecapAuthorityIsCurrent", "updateVisitRecapExportControls")
    require = _function_source("requireCurrentVisitRecap", "beginVisitRecapExport")
    owner = _function_source("beginVisitRecapExport", "visitRecapExportSelectionIsCurrent")
    preflight = _function_source("preflightVisitRecapExport", "handleVisitRecapPreflightError")
    export = _function_source("performVisitRecapExport", "copyVisitRecap")
    copy = _function_source("copyVisitRecap", "downloadVisitRecap")
    download = _function_source("downloadVisitRecap", "printVisitRecap")
    printing = _function_source("printVisitRecap", "prepareVisitRecapPrint")

    assert "markVisitRecapStale" in require
    assert "requireCurrentVisitRecap()" in owner
    assert "credentials: 'same-origin'" in preflight
    assert "cache: 'no-store'" in preflight
    assert export.index("await preflightVisitRecapExport(owner)") < export.index(
        "navigator.clipboard.writeText"
    )
    assert export.index("await preflightVisitRecapExport(owner)") < export.index("new Blob")
    assert export.index("await preflightVisitRecapExport(owner)") < export.index("window.print()")
    assert export.count("visitRecapExportOwnerIsCurrent(owner)") >= 7
    assert export.index(
        "visitRecapExportOwnerIsCurrent(owner)", export.index("new Blob")
    ) < export.index("link.click()")
    assert "text/plain;charset=utf-8" in export
    assert "visit-recap-${date}.txt" in export
    assert "revokeVisitRecapDownloadUrl()" in export
    assert "visitRecapExportText" in current
    assert "performVisitRecapExport('copy')" in copy
    assert "performVisitRecapExport('download')" in download
    assert "performVisitRecapExport('print')" in printing
    assert "text/html" not in export


def _visit_recap_export_runtime_source() -> str:
    finish_start = APP_JS.index("function finishVisitRecapPrint")
    finish_end = APP_JS.index("window.addEventListener('beforeprint'", finish_start)
    return "\n".join(
        [
            _function_source("normalizedRevision", "capturePatientRequest"),
            _function_source("capturePatientRequest", "patientRequestIsCurrent"),
            _function_source("patientRequestIsCurrent", "requestClinicalConvergence"),
            _function_source("appIsOffline", "handleOfflineTransition"),
            _executable_function_source("handleOfflineTransition", "retryInitialLoad"),
            _function_source("revokeVisitRecapDownloadUrl", "clearVisitRecap"),
            _function_source("clearVisitRecap", "markVisitRecapStale"),
            _function_source("markVisitRecapStale", "visitRecapAuthorityIsCurrent"),
            _function_source("visitRecapAuthorityIsCurrent", "updateVisitRecapExportControls"),
            _function_source("updateVisitRecapExportControls", "recapPlainText"),
            _function_source("visitRecapResponseAuthority", "applyVisitRecapProjection"),
            _executable_function_source("applyVisitRecapProjection", "loadVisitRecap"),
            _function_source("requireCurrentVisitRecap", "beginVisitRecapExport"),
            _function_source("beginVisitRecapExport", "visitRecapExportSelectionIsCurrent"),
            _function_source(
                "visitRecapExportSelectionIsCurrent", "visitRecapExportOwnerIsCurrent"
            ),
            _function_source("visitRecapExportOwnerIsCurrent", "releaseVisitRecapExport"),
            _function_source("releaseVisitRecapExport", "visitRecapPreflightMatches"),
            _function_source("visitRecapPreflightMatches", "rejectVisitRecapPreflight"),
            _function_source("rejectVisitRecapPreflight", "acceptChangedVisitRecapPreflight"),
            _executable_function_source(
                "acceptChangedVisitRecapPreflight", "preflightVisitRecapExport"
            ),
            _executable_function_source(
                "preflightVisitRecapExport", "handleVisitRecapPreflightError"
            ),
            _executable_function_source(
                "handleVisitRecapPreflightError", "performVisitRecapExport"
            ),
            _executable_function_source("performVisitRecapExport", "copyVisitRecap"),
            _executable_function_source("copyVisitRecap", "downloadVisitRecap"),
            _executable_function_source("downloadVisitRecap", "printVisitRecap"),
            _executable_function_source("printVisitRecap", "prepareVisitRecapPrint"),
            _function_source("prepareVisitRecapPrint", "finishVisitRecapPrint"),
            APP_JS[finish_start:finish_end],
        ]
    )


def _visit_recap_export_probe_script() -> str:
    return "\n".join(
        [
            """
class FakeClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  toggle(value, force) {
    if (force === true) this.values.add(value);
    else if (force === false) this.values.delete(value);
    else if (this.values.has(value)) this.values.delete(value);
    else this.values.add(value);
  }
  contains(value) { return this.values.has(value); }
}

const elements = new Map();
const element = id => {
  if (!elements.has(id)) {
    elements.set(id, {
      className: '',
      disabled: false,
      innerHTML: '',
      textContent: '',
    });
  }
  return elements.get(id);
};
let linkClicks = 0;
const document = {
  body: { classList: new FakeClassList() },
  createElement(tag) {
    if (tag !== 'a') throw new Error(`unexpected element ${tag}`);
    return {
      href: '',
      download: '',
      rel: '',
      click() { linkClicks += 1; },
    };
  },
  getElementById: element,
};
let printCalls = 0;
const window = {
  addEventListener() {},
  print() { printCalls += 1; },
};
let offline = false;
let clipboardWrites = 0;
const navigator = {
  get onLine() { return !offline; },
  clipboard: {
    async writeText() { clipboardWrites += 1; },
  },
};
let blobCreates = 0;
class Blob {
  constructor(parts, options) {
    this.parts = parts;
    this.options = options;
    blobCreates += 1;
  }
}
let urlCreates = 0;
let urlRevokes = 0;
const URL = {
  createObjectURL() {
    urlCreates += 1;
    return `blob:recap-${urlCreates}`;
  },
  revokeObjectURL() { urlRevokes += 1; },
};
globalThis.Blob = Blob;
globalThis.URL = URL;

let selectedVisitId = 'visit-a';
let visitSelectionEpoch = 3;
let phiEpoch = 2;
let latestProfileRevision = 10;
let workflowRevision = 20;
let visitRecapLoadEpoch = 7;
let visitRecapProjection = null;
let visitRecapAuthority = null;
let visitRecapExportText = '';
let visitRecapStale = false;
let visitRecapState = 'idle';
let visitRecapMessage = '';
let visitRecapDownloadUrl = null;
let visitRecapExportOwner = null;
let visitRecapExportEpoch = 0;
let visitRecapNetworkAmbiguous = false;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'recap';
let visitsById = new Map();
const failedLoads = new Map();
let fetchCalls = [];
let fetchImpl = null;

function currentVisit() {
  return selectedVisitId ? visitsById.get(selectedVisitId) || null : null;
}
function buildVisitRecapText(recap) {
  if (!recap?.exportable || recap.state !== 'current') {
    throw new Error('This visit recap is not available for export.');
  }
  return `recap:${recap.marker}\\n`;
}
function renderVisitRecap() { updateVisitRecapExportControls(); }
function renderAppState() {}
function reportLoadSuccess(scope) { failedLoads.delete(scope); }
function reportLoadError(scope, error) { failedLoads.set(scope, error); }
function shouldEvictClientPhi(error) {
  return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
}
function evictClientPhi() {
  clearVisitRecap(true);
  phiEpoch += 1;
  selectedVisitId = null;
  visitSelectionEpoch += 1;
  visitsById = new Map();
  appointmentDialogOpen = false;
}
function authorizePatientResponse(request, data) {
  if (!patientRequestIsCurrent(request)) return { accepted: false };
  const profileRevision = normalizedRevision(data?.profile_revision);
  const nextWorkflowRevision = normalizedRevision(data?.workflow_revision);
  if (
    !Number.isSafeInteger(profileRevision)
    || !Number.isSafeInteger(nextWorkflowRevision)
    || profileRevision < latestProfileRevision
    || nextWorkflowRevision < workflowRevision
  ) return { accepted: false };
  if (profileRevision > latestProfileRevision) {
    latestProfileRevision = profileRevision;
    phiEpoch += 1;
  }
  workflowRevision = nextWorkflowRevision;
  return { accepted: true };
}
async function readJsonResponse(response, canEvictClientPhi = () => true) {
  if (response.throwError) throw response.throwError;
  if (!response.ok) {
    const error = new Error(response.message || `Request failed (${response.status})`);
    error.status = response.status;
    if ((response.status === 401 || response.status === 403) && canEvictClientPhi()) {
      evictClientPhi(error);
    }
    throw error;
  }
  return response.data;
}
async function fetch(url, options) {
  fetchCalls.push({ url, options });
  return fetchImpl(url, options);
}
""",
            _visit_recap_export_runtime_source(),
            """
function recapData(overrides = {}) {
  const visitId = overrides.visit_id || 'visit-a';
  const visitToken = overrides.visit_token || 'visit-token-a';
  const marker = overrides.marker || 'accepted';
  return {
    visit_id: visitId,
    visit_token: visitToken,
    recap_token: overrides.recap_token || 'recap-token-a',
    profile_revision: overrides.profile_revision ?? 10,
    workflow_revision: overrides.workflow_revision ?? 20,
    recap: overrides.recap || {
      state: overrides.state || 'current',
      exportable: overrides.exportable ?? true,
      marker,
      visit: {
        id: visitId,
        status: overrides.visit_status || 'completed',
        date: '2026-08-10',
      },
    },
  };
}
function response(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, data, message: data?.error };
}
function resetEffects() {
  fetchCalls = [];
  clipboardWrites = 0;
  blobCreates = 0;
  linkClicks = 0;
  printCalls = 0;
  urlCreates = 0;
  urlRevokes = 0;
}
function seed(data = recapData()) {
  offline = false;
  failedLoads.clear();
  selectedVisitId = 'visit-a';
  visitSelectionEpoch += 1;
  phiEpoch += 1;
  latestProfileRevision = data.profile_revision;
  workflowRevision = data.workflow_revision;
  visitRecapLoadEpoch += 1;
  visitRecapExportEpoch += 1;
  visitRecapExportOwner = null;
  visitRecapNetworkAmbiguous = false;
  appointmentDialogOpen = true;
  activeAppointmentTab = 'recap';
  visitsById = new Map([['visit-a', {
    id: 'visit-a',
    token: data.visit_token,
    status: data.recap.visit.status,
  }]]);
  applyVisitRecapProjection(data, { requestEpoch: visitRecapLoadEpoch });
  resetEffects();
}
async function runExport(kind) {
  return {
    copy: copyVisitRecap,
    download: downloadVisitRecap,
    print: printVisitRecap,
  }[kind]();
}
function effects() {
  return {
    fetches: fetchCalls.length,
    clipboardWrites,
    blobCreates,
    linkClicks,
    printCalls,
    urlCreates,
    urlRevokes,
    stale: visitRecapStale,
    authority: Boolean(visitRecapAuthority),
    text: visitRecapExportText,
    owner: Boolean(visitRecapExportOwner),
    disabled: element('visit-recap-copy').disabled,
  };
}

(async () => {
  const unchanged = {};
  for (const kind of ['copy', 'download', 'print']) {
    const accepted = recapData();
    seed(accepted);
    fetchImpl = async () => response(accepted);
    await runExport(kind);
    unchanged[kind] = effects();
  }

  seed(recapData());
  failedLoads.set('unrelated-workflow', new TypeError('unrelated transient failure'));
  fetchImpl = async () => response(recapData());
  await copyVisitRecap();
  const unrelatedFailure = effects();

  const changed = {};
  for (const [name, next] of Object.entries({
    token: recapData({ recap_token: 'recap-token-b', marker: 'replacement' }),
    revision: recapData({
      recap_token: 'recap-token-r',
      profile_revision: 11,
      workflow_revision: 21,
      marker: 'revised',
    }),
  })) {
    seed(recapData());
    fetchImpl = async () => response(next);
    const first = await copyVisitRecap();
    const afterFirst = effects();
    fetchImpl = async () => response(next);
    const second = await copyVisitRecap();
    changed[name] = { first, second, afterFirst, afterSecond: effects() };
  }

  seed(recapData());
  const changedVisit = recapData({
    visit_id: 'visit-b',
    visit_token: 'visit-token-b',
    recap_token: 'recap-token-b',
  });
  fetchImpl = async () => response(changedVisit);
  await copyVisitRecap();
  const visitMismatch = effects();

  const failures = {};
  const failureFactories = {
    conflict: async () => response({ error: 'changed' }, 409),
    typeError: async () => { throw new TypeError('offline'); },
    abort: async () => {
      const error = new Error('aborted');
      error.name = 'AbortError';
      throw error;
    },
    unauthorized: async () => response({ error: 'auth' }, 401),
    forbidden: async () => response({ error: 'forbidden' }, 403),
    hard: async () => response({ error: 'hard' }, 500),
    missing: async () => response({ visit_id: 'visit-a' }),
    lower: async () => response(recapData({
      recap_token: 'lower',
      profile_revision: 9,
      workflow_revision: 19,
    })),
  };
  for (const [failure, factory] of Object.entries(failureFactories)) {
    failures[failure] = {};
    for (const kind of ['copy', 'download', 'print']) {
      seed(recapData());
      fetchImpl = factory;
      await runExport(kind);
      failures[failure][kind] = effects();
    }
  }

  const offlineKinds = {};
  for (const kind of ['copy', 'download', 'print']) {
    seed(recapData());
    offline = true;
    await runExport(kind);
    offlineKinds[kind] = effects();
  }

  seed(recapData());
  let resolveConcurrent;
  fetchImpl = () => new Promise(resolve => { resolveConcurrent = resolve; });
  const concurrentCopy = copyVisitRecap();
  const concurrentDownload = downloadVisitRecap();
  const concurrentPrint = printVisitRecap();
  resolveConcurrent(response(recapData()));
  await Promise.all([concurrentCopy, concurrentDownload, concurrentPrint]);
  const concurrent = effects();

  seed(recapData());
  let resolveSelection;
  fetchImpl = () => new Promise(resolve => { resolveSelection = resolve; });
  const lateSelectionPromise = copyVisitRecap();
  selectedVisitId = 'visit-b';
  visitSelectionEpoch += 1;
  visitsById.set('visit-b', { id: 'visit-b', token: 'visit-token-b' });
  resolveSelection(response(recapData()));
  await lateSelectionPromise;
  const lateSelection = effects();

  seed(recapData());
  let resolveEviction;
  fetchImpl = () => new Promise(resolve => { resolveEviction = resolve; });
  const lateEvictionPromise = downloadVisitRecap();
  evictClientPhi(new Error('evicted'));
  resolveEviction(response(recapData()));
  await lateEvictionPromise;
  const lateEviction = effects();

  seed(recapData());
  fetchImpl = async () => response(recapData());
  await downloadVisitRecap();
  const blobRevocation = effects();

  seed(recapData());
  visitRecapDownloadUrl = URL.createObjectURL(new Blob(['old']));
  resetEffects();
  offline = true;
  handleOfflineTransition();
  const offlineEvent = effects();
  offline = false;
  const onlineWithoutReload = effects();
  applyVisitRecapProjection(recapData(), { requestEpoch: visitRecapLoadEpoch });
  reportLoadSuccess('visit-recap');
  updateVisitRecapExportControls();
  const afterReload = effects();

  console.log(JSON.stringify({
    unchanged,
    unrelatedFailure,
    changed,
    visitMismatch,
    failures,
    offlineKinds,
    concurrent,
    lateSelection,
    lateEviction,
    blobRevocation,
    offlineEvent,
    onlineWithoutReload,
    afterReload,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )


def test_visit_recap_actual_exports_preflight_and_revoke_authority():
    completed = _run_node_script(_visit_recap_export_probe_script())
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    for kind, effect_key in (
        ("copy", "clipboardWrites"),
        ("download", "linkClicks"),
        ("print", "printCalls"),
    ):
        effect = result["unchanged"][kind]
        assert effect["fetches"] == 1
        assert effect[effect_key] == 1
    assert result["unchanged"]["download"]["blobCreates"] == 1
    assert result["unchanged"]["download"]["urlRevokes"] == 1
    assert result["unrelatedFailure"]["fetches"] == 1
    assert result["unrelatedFailure"]["clipboardWrites"] == 1

    for changed in result["changed"].values():
        assert changed["first"] is False
        assert changed["afterFirst"]["fetches"] == 1
        assert changed["afterFirst"]["clipboardWrites"] == 0
        assert changed["afterFirst"]["authority"] is True
        assert changed["second"] is True
        assert changed["afterSecond"]["fetches"] == 2
        assert changed["afterSecond"]["clipboardWrites"] == 1

    assert result["visitMismatch"]["fetches"] == 1
    assert result["visitMismatch"]["clipboardWrites"] == 0
    assert result["visitMismatch"]["authority"] is False
    assert result["visitMismatch"]["stale"] is True

    for failure in result["failures"].values():
        for effect in failure.values():
            assert effect["clipboardWrites"] == 0
            assert effect["blobCreates"] == 0
            assert effect["linkClicks"] == 0
            assert effect["printCalls"] == 0
    for effect in result["offlineKinds"].values():
        assert effect["fetches"] == 0
        assert effect["clipboardWrites"] == 0
        assert effect["blobCreates"] == 0
        assert effect["printCalls"] == 0

    assert result["concurrent"]["fetches"] == 1
    assert result["concurrent"]["clipboardWrites"] == 1
    assert result["concurrent"]["blobCreates"] == 0
    assert result["concurrent"]["printCalls"] == 0
    for name in ("lateSelection", "lateEviction"):
        effect = result[name]
        assert effect["clipboardWrites"] == 0
        assert effect["blobCreates"] == 0
        assert effect["linkClicks"] == 0
        assert effect["printCalls"] == 0
    assert result["blobRevocation"]["urlCreates"] == 1
    assert result["blobRevocation"]["urlRevokes"] == 1
    assert result["blobRevocation"]["owner"] is False

    assert result["offlineEvent"]["authority"] is False
    assert result["offlineEvent"]["text"] == ""
    assert result["offlineEvent"]["stale"] is True
    assert result["offlineEvent"]["disabled"] is True
    assert result["onlineWithoutReload"]["disabled"] is True
    assert result["afterReload"]["disabled"] is False


def test_visit_recap_live_browser_preflight_and_offline_revocation():
    playwright_api = pytest.importorskip("playwright.sync_api")
    accepted = {
        "visit_id": "visit-a",
        "visit_token": "visit-token-a",
        "recap_token": "recap-token-a",
        "profile_revision": 10,
        "workflow_revision": 20,
        "recap": {
            "state": "current",
            "exportable": True,
            "marker": "accepted",
            "visit": {
                "id": "visit-a",
                "status": "completed",
                "title": "Oncology review",
                "date": "2026-08-10",
            },
            "sections": {},
        },
    }
    changed = {
        **accepted,
        "recap_token": "recap-token-b",
        "recap": {**accepted["recap"], "marker": "replacement"},
    }
    harness = """
window.__recapTest = {
  online: true,
  recapData: null,
  recapRequests: 0,
  clipboardWrites: 0,
  blobCreates: 0,
  linkClicks: 0,
  printCalls: 0,
  urlCreates: 0,
  urlRevokes: 0,
};
const testState = window.__recapTest;
Object.defineProperty(navigator, 'onLine', {
  configurable: true,
  get: () => testState.online,
});
Object.defineProperty(navigator, 'clipboard', {
  configurable: true,
  value: { writeText: async () => { testState.clipboardWrites += 1; } },
});
const NativeBlob = window.Blob;
window.Blob = class extends NativeBlob {
  constructor(parts, options) {
    super(parts, options);
    testState.blobCreates += 1;
  }
};
const nativeCreateObjectURL = URL.createObjectURL.bind(URL);
const nativeRevokeObjectURL = URL.revokeObjectURL.bind(URL);
URL.createObjectURL = blob => {
  testState.urlCreates += 1;
  return nativeCreateObjectURL(blob);
};
URL.revokeObjectURL = url => {
  testState.urlRevokes += 1;
  return nativeRevokeObjectURL(url);
};
HTMLAnchorElement.prototype.click = function() {
  testState.linkClicks += 1;
};
window.print = () => { testState.printCalls += 1; };
window.fetch = async (url, options) => {
  const path = String(url);
  if (path.includes('/recap?expected_visit_token=')) {
    testState.recapRequests += 1;
    return new Response(JSON.stringify(testState.recapData), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  let data = { profile_revision: 10, workflow_revision: 20, items: [] };
  if (path === '/api/jobs') data = [];
  if (path === '/api/summary') {
    data = { profile_revision: 10, workflow_revision: 20, summary: null };
  }
  if (path === '/api/status') {
    data = {
      profile_revision: 10,
      workflow_revision: 20,
      patient: {},
      biomarkers: [],
      treatments: [],
      alerts: [],
      imaging: [],
      documents: [],
      papers: [],
      trials: [],
    };
  }
  if (path === '/api/visits') {
    data = { profile_revision: 10, workflow_revision: 20, items: [], appointments: [] };
  }
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};
"""
    seed = """
window.__seedRecap = data => {
  failedLoads.clear();
  selectedVisitId = 'visit-a';
  visitSelectionEpoch += 1;
  phiEpoch += 1;
  latestProfileRevision = data.profile_revision;
  workflowRevision = data.workflow_revision;
  visitRecapLoadEpoch += 1;
  visitRecapExportEpoch += 1;
  visitRecapExportOwner = null;
  appointmentDialogOpen = true;
  activeAppointmentTab = 'recap';
  visitsById = new Map([['visit-a', {
    id: 'visit-a',
    token: data.visit_token,
    status: data.recap.visit.status,
  }]]);
  const overlay = document.getElementById('appointment-overlay');
  overlay.inert = false;
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  document.getElementById('appointment-dialog').inert = false;
  const panel = document.getElementById('appointment-panel-recap');
  panel.hidden = false;
  panel.classList.add('active');
  applyVisitRecapProjection(data, { requestEpoch: visitRecapLoadEpoch });
  updateVisitRecapExportControls();
};
window.__resetRecapEffects = () => {
  Object.assign(window.__recapTest, {
    recapRequests: 0,
    clipboardWrites: 0,
    blobCreates: 0,
    linkClicks: 0,
    printCalls: 0,
    urlCreates: 0,
    urlRevokes: 0,
  });
};
"""

    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        for width in (1280, 360):
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.set_content(INDEX_HTML)
            page.add_style_tag(content=CSS)
            page.add_script_tag(content=harness)
            page.add_script_tag(content=APP_JS)
            page.wait_for_timeout(100)
            page.add_script_tag(content=seed)
            page.evaluate(
                """data => {
                  window.__recapTest.recapData = data;
                  window.__seedRecap(data);
                  window.__resetRecapEffects();
                }""",
                accepted,
            )
            page.locator("#visit-recap-copy").click()
            page.wait_for_function("window.__recapTest.clipboardWrites === 1")
            unchanged = page.evaluate(
                """() => ({
                  requests: window.__recapTest.recapRequests,
                  copies: window.__recapTest.clipboardWrites,
                  disabled: document.getElementById('visit-recap-copy').disabled,
                  overflow: document.documentElement.scrollWidth
                    - document.documentElement.clientWidth,
                  height: document.getElementById('visit-recap-copy')
                    .getBoundingClientRect().height,
                })"""
            )
            assert unchanged["requests"] == 1
            assert unchanged["copies"] == 1
            assert unchanged["disabled"] is False
            assert unchanged["overflow"] == 0
            if width == 360:
                assert unchanged["height"] >= 44

            if width == 1280:
                page.evaluate(
                    """data => {
                      window.__seedRecap(data);
                      window.__resetRecapEffects();
                      window.__recapTest.recapData = {
                        ...data,
                        recap_token: 'recap-token-b',
                        recap: { ...data.recap, marker: 'replacement' },
                      };
                    }""",
                    accepted,
                )
                page.locator("#visit-recap-copy").click()
                page.wait_for_function("window.__recapTest.recapRequests === 1")
                page.wait_for_function("visitRecapExportOwner === null")
                first = page.evaluate(
                    """() => ({
                      copies: window.__recapTest.clipboardWrites,
                      authority: visitRecapAuthority?.recapToken,
                      message: visitRecapMessage,
                    })"""
                )
                assert first["copies"] == 0
                assert first["authority"] == changed["recap_token"]
                assert "Review the refreshed recap" in first["message"]
                page.locator("#visit-recap-copy").click()
                page.wait_for_function("window.__recapTest.clipboardWrites === 1")
                assert page.evaluate("window.__recapTest.recapRequests") == 2

                offline_state = page.evaluate(
                    """data => {
                      window.__seedRecap(data);
                      visitRecapDownloadUrl = URL.createObjectURL(new Blob(['old']));
                      window.__resetRecapEffects();
                      window.__recapTest.online = false;
                      window.dispatchEvent(new Event('offline'));
                      return {
                        authority: visitRecapAuthority,
                        text: visitRecapExportText,
                        stale: visitRecapStale,
                        disabled: document.getElementById('visit-recap-copy').disabled,
                        revoked: window.__recapTest.urlRevokes,
                      };
                    }""",
                    changed,
                )
                assert offline_state == {
                    "authority": None,
                    "text": "",
                    "stale": True,
                    "disabled": True,
                    "revoked": 1,
                }
                page.evaluate("window.__recapTest.online = true")
                assert page.locator("#visit-recap-copy").is_disabled()
                page.evaluate(
                    """data => {
                      window.__recapTest.recapData = data;
                      return loadVisitRecap();
                    }""",
                    changed,
                )
                assert page.locator("#visit-recap-copy").is_enabled()
            page.close()
        browser.close()


def test_visit_recap_markup_sections_are_shared_escaped_and_non_persistent():
    assert 'id="appointment-tab-recap"' in INDEX_HTML
    assert 'id="appointment-panel-recap"' in INDEX_HTML
    assert INDEX_HTML.count('id="appointment-panel-recap"') == 1
    assert "Copy" in INDEX_HTML
    assert "Download text" in INDEX_HTML
    assert "Print" in INDEX_HTML
    renderer = _function_source("renderVisitRecap", "loadVisitRecap")
    for label in (
        "Visit details",
        "What was asked",
        "What we heard",
        "Decisions / needs confirmation",
        "Follow-ups",
        "Related resolved alerts",
        "Unresolved / unknown items",
    ):
        assert label in renderer
    assert "recapSectionMarkup" in renderer
    assert "escHtml(item.text)" in renderer
    assert "innerHTML = `${html}</div>`" in renderer
    assert "localStorage" not in renderer
    assert "sessionStorage" not in renderer
    assert "window.location" not in renderer
    assert "console." not in renderer


def test_visit_recap_desktop_phone_and_print_layout_is_accessible():
    playwright_api = pytest.importorskip("playwright.sync_api")
    markup = """
      <header class="app-header">Navigation</header>
      <div class="appointment-overlay open">
        <section class="appointment-dialog">
          <header class="appointment-dialog-header"><h2>Visit</h2></header>
          <section class="appointment-metadata">Editable details</section>
          <div class="appointment-tabs"><button class="appointment-tab">Recap</button></div>
          <div class="appointment-dialog-body">
            <section id="appointment-panel-recap" class="appointment-tab-panel active visit-recap-panel">
              <div class="visit-recap-toolbar">
                <div><p class="eyebrow">Authoritative visit record</p><h3>Visit recap</h3></div>
                <div class="visit-recap-actions">
                  <button class="button secondary">Copy</button>
                  <button class="button secondary">Download text</button>
                  <button class="button secondary">Print</button>
                </div>
              </div>
              <div class="visit-recap-status current">Current authoritative recap.</div>
              <div class="visit-recap-content">
                <div class="visit-recap-document">
                  <section class="visit-recap-section visit-recap-details">
                    <h4>Visit details</h4>
                    <dl><div><dt>Title</dt><dd>Long exact visit wording that must wrap safely without horizontal overflow at phone width</dd></div></dl>
                  </section>
                  <section class="visit-recap-section">
                    <h4>What we heard</h4>
                    <div class="visit-recap-list"><article><strong>Exact answer</strong><p class="capture-provenance">Caregiver-entered · attributed to clinician · unverified</p></article></div>
                  </section>
                </div>
              </div>
            </section>
          </div>
          <div class="appointment-retry">Retry</div>
        </section>
      </div>
    """
    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        for width in (1280, 360):
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.set_content(markup)
            page.add_style_tag(content=CSS)
            overflow = page.evaluate(
                """() => ({
                  document: document.documentElement.scrollWidth
                    - document.documentElement.clientWidth,
                  panel: document.querySelector('.visit-recap-panel').scrollWidth
                    - document.querySelector('.visit-recap-panel').clientWidth,
                  section: document.querySelector('.visit-recap-section').scrollWidth
                    - document.querySelector('.visit-recap-section').clientWidth,
                })"""
            )
            assert overflow == {"document": 0, "panel": 0, "section": 0}
            if width == 360:
                heights = page.locator(".visit-recap-actions .button").evaluate_all(
                    "(items) => items.map(item => item.getBoundingClientRect().height)"
                )
                assert heights and all(height >= 44 for height in heights)
            page.keyboard.press("Tab")
            focus = page.evaluate(
                """() => ({
                  tag: document.activeElement.tagName,
                  outline: getComputedStyle(document.activeElement).outlineStyle,
                })"""
            )
            assert focus["tag"] == "BUTTON"
            assert focus["outline"] != "none"
            page.close()

        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.set_content(markup)
        page.add_style_tag(content=CSS)
        page.evaluate("document.body.classList.add('visit-recap-printing')")
        page.emulate_media(media="print")
        print_state = page.evaluate(
            """() => ({
              appHeader: getComputedStyle(document.querySelector('.app-header')).display,
              dialogHeader: getComputedStyle(document.querySelector('.appointment-dialog-header')).display,
              tabs: getComputedStyle(document.querySelector('.appointment-tabs')).display,
              actions: getComputedStyle(document.querySelector('.visit-recap-actions')).display,
              recap: getComputedStyle(document.querySelector('#appointment-panel-recap')).display,
              provenance: getComputedStyle(document.querySelector('.capture-provenance')).display,
            })"""
        )
        assert print_state == {
            "appHeader": "none",
            "dialogHeader": "none",
            "tabs": "none",
            "actions": "none",
            "recap": "block",
            "provenance": "block",
        }
        page.evaluate("document.body.classList.remove('visit-recap-printing')")
        unavailable = page.evaluate(
            "getComputedStyle(document.querySelector('.appointment-overlay')).display"
        )
        assert unavailable == "none"
        browser.close()


def test_visit_recap_live_browser_enforces_visit_identity_and_control_visibility():
    playwright_api = pytest.importorskip("playwright.sync_api")
    html = re.sub(r"<script[^>]+src=[^>]+></script>", "", INDEX_HTML)
    html = html.replace("<head>", '<head><base href="http://app.test/">', 1)

    def visit(visit_id: str, status: str, token: str) -> dict:
        return {
            "id": visit_id,
            "title": f"Visit {visit_id[-1].upper()}",
            "status": status,
            "token": token,
            "question_snapshots": [],
            "decisions": [],
        }

    visits_payload = {
        "profile_revision": 5,
        "workflow_revision": 1,
        "appointments": [],
        "items": [
            visit("visit-a", "in_progress", "token-a"),
            visit("visit-b", "in_progress", "token-b"),
            visit("visit-c", "cancelled", "token-c"),
            visit("visit-d", "completed", "token-d"),
            visit("visit-p", "planned", "token-p"),
        ],
    }
    generic_payloads = {
        "/api/status": {
            "profile_revision": 5,
            "workflow_revision": 1,
            "patient": {},
            "stats": {},
            "alerts": [],
            "treatments_classified": [],
            "recent_biomarkers": [],
        },
        "/api/jobs": [],
        "/api/summary": {"status": "not_generated", "profile_revision": 5},
        "/api/questions": [],
        "/api/judgments": [],
        "/api/symptoms": [],
        "/api/patient/evidence": {},
        "/api/follow-ups": {
            "profile_revision": 5,
            "workflow_revision": 1,
            "items": [],
        },
    }
    recap_modes: dict[str, str] = {}
    pending_routes: dict[str, list] = {}

    def recap_response(
        visit_id: str,
        answer: str | None = None,
        *,
        token: str | None = None,
        workflow_revision: int | None = None,
    ) -> dict:
        item = next(row for row in visits_payload["items"] if row["id"] == visit_id)
        status = item["status"]
        state = (
            "administrative"
            if status == "cancelled"
            else "unavailable"
            if status == "planned"
            else "current"
        )
        exportable = state == "current"
        sections = {
            "what_was_asked": [],
            "what_we_heard": [],
            "decisions": [],
            "follow_ups": [],
            "related_resolved_alerts": [],
            "unresolved": [],
        }
        if answer:
            sections["what_we_heard"] = [
                {
                    "question": f"Question {visit_id[-1].upper()}",
                    "text": answer,
                    "provenance_label": (
                        "Caregiver-entered · attributed to clinician · unverified"
                    ),
                }
            ]
        return {
            "profile_revision": 5,
            "workflow_revision": (
                workflow_revision
                if workflow_revision is not None
                else visits_payload["workflow_revision"]
            ),
            "visit_id": visit_id,
            "visit_token": token or item["token"],
            "recap_token": f"recap-{token or item['token']}",
            "recap": {
                "state": state,
                "exportable": exportable,
                "visit": {
                    "id": visit_id,
                    "title": item["title"],
                    "status": status,
                },
                "sections": sections,
            },
        }

    with playwright_api.sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Installed Playwright browser is unavailable")
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        def fulfill(route):
            path = "/" + route.request.url.split("/", 3)[-1].split("?", 1)[0]
            if path == "/api/visits":
                payload = visits_payload
            elif path.startswith("/api/visits/") and path.endswith("/recap"):
                visit_id = path.split("/")[3]
                mode = recap_modes.get(visit_id, "current")
                if mode == "pending":
                    pending_routes.setdefault(visit_id, []).append(route)
                    return
                if mode == "offline":
                    recap_modes[visit_id] = "current"
                    route.abort()
                    return
                payload = recap_response(visit_id, f"Exact answer {visit_id[-1].upper()}")
            else:
                payload = generic_payloads.get(path, {})
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            )

        page.route("**/api/**", fulfill)
        page.set_content(html)
        page.add_style_tag(content=CSS)
        page.add_script_tag(content=APP_JS)
        page.wait_for_function("() => visitsById.size === 5 && !clinicalConvergenceRunning")
        page.evaluate(
            """() => {
              clearTimeout(pollingInterval);
              pollingInterval = null;
              openAppointmentWorkspace(null, 'visit-a');
              switchAppointmentTab('recap');
            }"""
        )
        page.get_by_text("Exact answer A", exact=True).wait_for()
        assert page.locator("#visit-recap-actions").is_visible()
        assert page.locator("#visit-recap-copy").is_enabled()

        recap_modes["visit-b"] = "pending"
        page.evaluate(
            """() => {
              document.getElementById('visit-recap-copy').focus();
              selectVisitInWorkspace('visit-b');
            }"""
        )
        page.wait_for_timeout(20)
        assert pending_routes["visit-b"]
        immediate_b = page.evaluate(
            """() => ({
              title: document.getElementById('appointment-dialog-title').textContent,
              content: document.getElementById('visit-recap-content').textContent,
              actionsHidden: document.getElementById('visit-recap-actions').hidden,
              focus: document.activeElement.id,
            })"""
        )
        assert immediate_b == {
            "title": "Visit B",
            "content": "Loading the current visit recap…",
            "actionsHidden": True,
            "focus": "appointment-tab-recap",
        }

        recap_modes["visit-a"] = "pending"
        page.evaluate("selectVisitInWorkspace('visit-a')")
        page.wait_for_timeout(20)
        assert pending_routes["visit-a"]
        pending_routes["visit-b"].pop(0).fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(recap_response("visit-b", "Late exact answer B")),
        )
        page.wait_for_timeout(50)
        rapid_state = page.evaluate(
            """() => ({
              title: document.getElementById('appointment-dialog-title').textContent,
              content: document.getElementById('visit-recap-content').textContent,
            })"""
        )
        assert rapid_state["title"] == "Visit A"
        assert "Late exact answer B" not in rapid_state["content"]
        pending_routes["visit-a"].pop(0).fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(recap_response("visit-a", "Exact answer A fresh")),
        )
        page.get_by_text("Exact answer A fresh", exact=True).wait_for()

        recap_modes["visit-a"] = "offline"
        page.evaluate("loadVisitRecap()")
        stale = page.evaluate(
            """() => ({
              content: document.getElementById('visit-recap-content').textContent,
              stale: document.querySelector('.visit-recap-document')?.classList.contains('stale'),
              actionsHidden: document.getElementById('visit-recap-actions').hidden,
              status: document.getElementById('visit-recap-status').textContent,
            })"""
        )
        assert "Exact answer A fresh" in stale["content"]
        assert stale["stale"] is True
        assert stale["actionsHidden"] is True
        assert "Offline snapshot" in stale["status"]

        page.emulate_media(media="print")
        page.evaluate("prepareVisitRecapPrint()")
        assert page.evaluate("document.body.classList.contains('visit-recap-printing')") is False
        assert page.locator(".visit-recap-document").is_visible() is False
        assert (
            page.evaluate("getComputedStyle(document.body, '::before').content")
            == '"Visit recap unavailable for printing. Reload the current recap first."'
        )
        page.emulate_media(media="screen")

        recap_modes["visit-a"] = "current"
        page.evaluate("loadVisitRecap()")
        page.get_by_text("Exact answer A", exact=True).wait_for()
        recap_modes["visit-a"] = "pending"
        visits_payload["items"][0] = visit("visit-a", "in_progress", "token-a-2")
        page.locator("#visit-recap-copy").focus()
        page.evaluate("loadVisits()")
        page.wait_for_timeout(20)
        assert pending_routes["visit-a"]
        token_change = page.evaluate(
            """() => ({
              title: document.getElementById('appointment-dialog-title').textContent,
              content: document.getElementById('visit-recap-content').textContent,
              actionsHidden: document.getElementById('visit-recap-actions').hidden,
              focus: document.activeElement.id,
            })"""
        )
        assert token_change == {
            "title": "Visit A",
            "content": "Loading the current visit recap…",
            "actionsHidden": True,
            "focus": "appointment-tab-recap",
        }
        pending_routes["visit-a"].pop(0).fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                recap_response(
                    "visit-a",
                    "Exact answer A token 2",
                    token="token-a-2",
                )
            ),
        )
        page.get_by_text("Exact answer A token 2", exact=True).wait_for()
        assert page.locator("#visit-recap-actions").is_visible()

        recap_modes["visit-d"] = "current"
        page.evaluate("selectVisitInWorkspace('visit-d')")
        page.get_by_text("Exact answer D", exact=True).wait_for()
        assert page.locator("#visit-recap-actions").is_visible()

        for visit_id, notice in (
            ("visit-p", "A recap becomes available after the visit starts."),
            (
                "visit-c",
                "Cancelled visit · administrative record only. "
                "Copy, download, and print are unavailable.",
            ),
        ):
            recap_modes[visit_id] = "current"
            page.evaluate("(id) => selectVisitInWorkspace(id)", visit_id)
            page.get_by_text(notice, exact=True).wait_for()
            assert page.evaluate("document.getElementById('visit-recap-actions').hidden") is True
            assert page.locator("#visit-recap-actions").is_visible() is False

        page.evaluate("selectVisitInWorkspace('visit-d')")
        page.get_by_text("Exact answer D", exact=True).wait_for()
        page.set_viewport_size({"width": 360, "height": 800})
        heights = page.locator("#visit-recap-actions .button").evaluate_all(
            "(items) => items.map(item => item.getBoundingClientRect().height)"
        )
        overflow = page.evaluate(
            """() => ({
              document: document.documentElement.scrollWidth
                - document.documentElement.clientWidth,
              dialog: document.getElementById('appointment-dialog').scrollWidth
                - document.getElementById('appointment-dialog').clientWidth,
              recap: document.getElementById('appointment-panel-recap').scrollWidth
                - document.getElementById('appointment-panel-recap').clientWidth,
            })"""
        )
        assert heights and all(height >= 44 for height in heights)
        assert overflow == {"document": 0, "dialog": 0, "recap": 0}

        page.locator("#visit-recap-copy").focus()
        page.evaluate("evictClientPhi({ status: 401 })")
        auth_cleared = page.evaluate(
            """() => ({
              content: document.getElementById('visit-recap-content').textContent,
              actionsHidden: document.getElementById('visit-recap-actions').hidden,
              focus: document.activeElement.id,
            })"""
        )
        assert auth_cleared["content"] == ""
        assert auth_cleared["actionsHidden"] is True
        assert auth_cleared["focus"] not in {
            "visit-recap-copy",
            "visit-recap-download",
            "visit-recap-print",
        }
        assert page_errors == []
        browser.close()


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
function followUpControlsLocked() { return false; }
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
    completed = _run_node_script(script)
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
let latestProfileRevision = 10;
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
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let workflowMutationPending = false;
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
function followUpControlsLocked() {
  return followUpMutationPending
    || pendingFollowUpCompletion !== null
    || summaryActionMutationOwner !== null
    || workflowMutationPending;
}
function capturePatientRequest() { return { requestPhiEpoch: phiEpoch }; }
function patientRequestIsCurrent(request) { return request.requestPhiEpoch === phiEpoch; }
function authorizePatientResponse(request, data) {
  if (!patientRequestIsCurrent(request)) return { accepted: false };
  if (data.profile_revision < latestProfileRevision) return { accepted: false };
  if (data.workflow_revision < workflowRevision) return { accepted: false };
  latestProfileRevision = data.profile_revision;
  workflowRevision = data.workflow_revision;
  return { accepted: true };
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


def _run_follow_up_ownership_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 7;
let followUpSelectionEpoch = 10;
let selectedFollowUpId = 'original-action';
let followUpMutationPending = false;
let followUpMutationOwner = null;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let pendingFollowUpIntent = null;
let followUpProjectionStale = false;
let followUpDialogOpen = true;
let followUpDialogMode = 'create';
let followUpOutcomeStatus = null;
let followUpFilter = 'active';
const followUpDrafts = new Map();
let mutationIds = 0;
let fetches = 0;
let dialogMessages = [];
let focusChanges = 0;
let resolveActive;
let holdNext = true;
const attempts = [];
const elements = new Map([
  ['follow-up-create-text', { value: 'Contact the clinic about timing' }],
  ['follow-up-create-owner', { value: 'Caregiver' }],
  ['follow-up-create-due', { value: '2026-08-20' }],
]);
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {
      classList: { add() {}, remove() {}, toggle() {} },
      dataset: {},
      disabled: false,
      hidden: false,
      setAttribute() {},
      tabIndex: 0,
      textContent: '',
      value: '',
    });
    return elements.get(id);
  },
};

function newMutationId() { mutationIds += 1; return `mutation-${mutationIds}`; }
function setFormError() {}
function updateFollowUpFormValidity() {}
function setFollowUpStatus() {}
function setFollowUpDialogStatus(message) { dialogMessages.push(message); }
function clearFollowUpRetry() { pendingFollowUpIntent = null; }
function followUpDraftKey() { return 'create'; }
function renderFollowUps() {}
function captureFollowUpDraft() { throw new Error('busy intent changed a draft'); }
function activateDialog() { focusChanges += 1; }
function deactivateDialog() { focusChanges += 1; }

async function performFollowUpIntent(intent, explicitRetry = false) {
  fetches += 1;
  attempts.push({
    intent,
    explicitRetry,
    body: JSON.parse(JSON.stringify(intent.body)),
  });
  if (holdNext) {
    await new Promise(resolve => { resolveActive = resolve; });
    holdNext = false;
  }
  followUpMutationPending = false;
  followUpMutationOwner = null;
  return { item: { id: 'saved' } };
}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _function_source("beginFollowUpMutation", "createFollowUpIntent"),
            _function_source("createFollowUpIntent", "followUpIntentCanRender"),
            _executable_function_source("followUpIntentCanRender", "handleFollowUpConflict"),
            _executable_function_source("submitFollowUpMutation", "retryFollowUpIntent"),
            _executable_function_source("retryFollowUpIntent", "createManualFollowUp"),
            _executable_function_source("acceptGeneratedFollowUp", "renderClaimEvidence"),
            _executable_function_source("createManualFollowUp", "saveFollowUpDetails"),
            _function_source("setFollowUpFilter", "handleFollowUpFilterKeydown"),
            _function_source("openFollowUpDialog", "openFollowUpCreateDialog"),
            _function_source("openFollowUpOutcomeDialog", "closeFollowUpDialog"),
            _function_source("closeFollowUpDialog", "closeFollowUpFromBackdrop"),
            """
(async () => {
  const rowA = {
    dataset: {
      generatedActionSourceId: 'generated-a',
      generatedActionSourceToken: 'token-a',
    },
  };
  const rowB = {
    dataset: {
      generatedActionSourceId: 'generated-b',
      generatedActionSourceToken: 'token-b',
    },
  };
  const first = acceptGeneratedFollowUp(rowA);
  await Promise.resolve();
  const epochAfterFirst = followUpSelectionEpoch;
  const idCountAfterFirst = mutationIds;
  const rejectedB = await acceptGeneratedFollowUp(rowB);
  const rejectedDuplicate = await acceptGeneratedFollowUp(rowA);
  const rejectedManual = await createManualFollowUp();
  const rejectedDirect = await submitFollowUpMutation(
    '/api/follow-ups',
    { origin_kind: 'manual', text: 'Contact the clinic' },
  );
  setFollowUpFilter('completed');
  openFollowUpDialog('edit', null, 'other-action');
  openFollowUpOutcomeDialog(null, 'missing-action', 'completed');
  closeFollowUpDialog();
  const blockedState = {
    epoch: followUpSelectionEpoch,
    ids: mutationIds,
    fetches,
    selectedFollowUpId,
    filter: followUpFilter,
    focusChanges,
    rejectedB: rejectedB ?? null,
    rejectedDuplicate: rejectedDuplicate ?? null,
    rejectedManual: rejectedManual ?? null,
    rejectedDirect,
  };

  resolveActive();
  await first;
  const second = await acceptGeneratedFollowUp(rowB);
  const retryIntent = attempts[1].intent;
  pendingFollowUpIntent = retryIntent;
  const retryBodyBefore = JSON.stringify(retryIntent.body);
  await retryFollowUpIntent();

  console.log(JSON.stringify({
    epochAfterFirst,
    idCountAfterFirst,
    blockedState,
    totalIds: mutationIds,
    totalFetches: fetches,
    second: second?.item?.id || null,
    firstBody: attempts[0].body,
    secondBody: attempts[1].body,
    retryExact: retryBodyBefore === JSON.stringify(attempts[2].intent.body),
    retryMutationId: attempts[2].body.mutation_id,
    retryExplicit: attempts[2].explicitRetry,
    dialogMessages,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_intent_owner_precedes_ids_epochs_fetch_and_exact_retry():
    result = _run_follow_up_ownership_probe()
    assert result["epochAfterFirst"] == 11
    assert result["idCountAfterFirst"] == 1
    assert result["blockedState"] == {
        "epoch": 11,
        "ids": 1,
        "fetches": 1,
        "selectedFollowUpId": None,
        "filter": "active",
        "focusChanges": 0,
        "rejectedB": None,
        "rejectedDuplicate": None,
        "rejectedManual": None,
        "rejectedDirect": None,
    }
    assert result["firstBody"]["source_id"] == "generated-a"
    assert result["firstBody"]["mutation_id"] == "mutation-1"
    assert result["secondBody"]["source_id"] == "generated-b"
    assert result["secondBody"]["mutation_id"] == "mutation-2"
    assert result["totalIds"] == 2
    assert result["totalFetches"] == 3
    assert result["second"] is None
    assert result["retryExact"] is True
    assert result["retryMutationId"] == "mutation-2"
    assert result["retryExplicit"] is True
    assert result["dialogMessages"] == [
        "Saving is still in progress. Wait for the result before closing."
    ]


def _run_follow_up_busy_control_probe() -> dict:
    script = "\n".join(
        [
            """
let followUpMutationPending = true;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let followUpProjectionStale = false;
let followUpDialogOpen = false;
let followUpsById = new Map();
function control(disabled = false) {
  return { dataset: {}, disabled, textContent: '' };
}
const accept = control();
const retry = control();
const dismiss = control();
const filter = control();
const feedbackButton = control();
const feedbackInput = control();
const dialogInput = control();
const dialogTextarea = control();
const dialogSelect = control();
const summaryFeedback = control();
const row = {
  dataset: { generatedActionSourceId: 'generated-a' },
  querySelector(selector) { return selector === '.action-accept-btn' ? accept : null; },
};
const document = {
  getElementById(id) {
    if (id !== 'follow-up-retry') return null;
    return {
      hidden: true,
      querySelector() { return retry; },
    };
  },
  querySelectorAll(selector) {
    if (selector === '[data-generated-action-source-id]') return [row];
    return [
      accept, retry, dismiss, filter, feedbackButton, feedbackInput,
      dialogInput, dialogTextarea, dialogSelect, summaryFeedback,
    ];
  },
};
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _function_source("generatedActionAccepted", "refreshGeneratedActionControls"),
            _function_source("refreshGeneratedActionControls", "redactGeneratedSummaryActions"),
            _function_source("setFollowUpMutationBusy", "updateFollowUpOutcomeGuidance"),
            """
setFollowUpMutationBusy(true);
const during = {
  accept: accept.disabled,
  retry: retry.disabled,
  dismiss: dismiss.disabled,
  filter: filter.disabled,
  feedbackButton: feedbackButton.disabled,
  feedbackInput: feedbackInput.disabled,
  dialogInput: dialogInput.disabled,
  dialogTextarea: dialogTextarea.disabled,
  dialogSelect: dialogSelect.disabled,
  summaryFeedback: summaryFeedback.disabled,
};
followUpsById.set('saved', {
  origin_snapshot: {
    kind: 'executive_summary_action',
    source_id: 'generated-a',
  },
});
refreshGeneratedActionControls();
const acceptedDuringReload = {
  disabled: accept.disabled,
  text: accept.textContent,
};
followUpMutationPending = false;
setFollowUpMutationBusy(false);
refreshGeneratedActionControls();
const afterRelease = {
  disabled: accept.disabled,
  text: accept.textContent,
  snapshotCleared: !('followUpWasDisabled' in accept.dataset),
};
pendingFollowUpCompletion = { awaiting: true };
setFollowUpMutationBusy(true);
console.log(JSON.stringify({
  during,
  acceptedDuringReload,
  afterRelease,
  pendingRetry: {
    disabled: retry.disabled,
    text: retry.textContent,
  },
}));
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_busy_controls_cover_retry_and_preserve_accepted_state():
    assert _run_follow_up_busy_control_probe() == {
        "during": {
            "accept": True,
            "retry": True,
            "dismiss": True,
            "filter": True,
            "feedbackButton": True,
            "feedbackInput": True,
            "dialogInput": True,
            "dialogTextarea": True,
            "dialogSelect": True,
            "summaryFeedback": True,
        },
        "acceptedDuringReload": {"disabled": True, "text": "Accepted"},
        "afterRelease": {
            "disabled": True,
            "text": "Accepted",
            "snapshotCleared": True,
        },
        "pendingRetry": {
            "disabled": False,
            "text": "Retry authoritative reload",
        },
    }


def test_follow_up_owner_blocks_open_summary_feedback_mutations():
    script = "\n".join(
        [
            """
let followUpMutationPending = true;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let touchedDom = false;
let fetched = false;
const document = {
  getElementById() { touchedDom = true; throw new Error('DOM changed'); },
};
async function fetch() { fetched = true; throw new Error('request sent'); }
function renderPendingSummary() {}
function requireOk() {}
function loadSummary() {}
function loadJudgments() {}
function reportLoadError() {}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _executable_function_source("dismissAction", "quickDismiss"),
            _executable_function_source("quickDismiss", "reportMissedSummary"),
            _executable_function_source("reportMissedSummary", "loadJudgments"),
            """
(async () => {
  await dismissAction(0);
  await quickDismiss(0, 'reason', 'constraint');
  await reportMissedSummary();
  console.log(JSON.stringify({ touchedDom, fetched }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"touchedDom": False, "fetched": False}


def test_open_summary_feedback_owns_lock_before_dom_and_fetch_awaits():
    script = "\n".join(
        [
            """
let followUpMutationPending = false;
let followUpMutationOwner = null;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let phiEpoch = 0;
let summaryLoadEpoch = 0;
let fetches = 0;
let busyStarts = 0;
let busyEnds = 0;
let summaryLoads = 0;
let judgmentLoads = 0;
let resolveFetch;
const action = { dataset: { actionText: 'Action' }, style: { opacity: '1' } };
const dialog = { remove() {} };
const document = {
  getElementById(id) { return id.startsWith('action-') ? action : dialog; },
};
async function fetch() {
  fetches += 1;
  return new Promise(resolve => { resolveFetch = resolve; });
}
async function requireOk() {}
async function loadSummary() { summaryLoads += 1; summaryLoadEpoch += 1; return {}; }
async function loadJudgments() { judgmentLoads += 1; }
function reportLoadError() {}
function setFollowUpMutationBusy(busy) { if (busy) busyStarts += 1; else busyEnds += 1; }
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _function_source("beginFollowUpMutation", "createFollowUpIntent"),
            _executable_function_source("quickDismiss", "reportMissedSummary"),
            """
(async () => {
  const dismissal = quickDismiss(0, 'reason', 'constraint');
  await Promise.resolve();
  const competingOwner = beginFollowUpMutation();
  const during = {
    competingOwner: competingOwner === null,
    summaryActionOwned: summaryActionMutationOwner !== null,
    opacity: action.style.opacity,
    fetches,
  };
  resolveFetch({});
  await dismissal;
  console.log(JSON.stringify({
    during,
    after: {
      summaryActionOwned: summaryActionMutationOwner !== null,
      followUpMutationPending,
      busyStarts,
      busyEnds,
      summaryLoads,
      judgmentLoads,
    },
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "during": {
            "competingOwner": True,
            "summaryActionOwned": True,
            "opacity": "0.3",
            "fetches": 1,
        },
        "after": {
            "summaryActionOwned": False,
            "followUpMutationPending": False,
            "busyStarts": 1,
            "busyEnds": 1,
            "summaryLoads": 1,
            "judgmentLoads": 1,
        },
    }


def test_stale_summary_feedback_cannot_unlock_newer_owner():
    script = "\n".join(
        [
            """
let followUpMutationPending = false;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let phiEpoch = 0;
let summaryLoadEpoch = 0;
let busyEnds = 0;
let summaryLoads = 0;
const requests = [];
const actions = [
  { dataset: { actionText: 'A' }, style: { opacity: '1' } },
  { dataset: { actionText: 'B' }, style: { opacity: '1' } },
];
const document = {
  getElementById(id) {
    if (id.startsWith('action-')) return actions[Number(id.split('-')[1])];
    return { remove() {} };
  },
};
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
async function fetch() {
  const request = deferred();
  requests.push(request);
  return request.promise;
}
async function requireOk() {}
async function loadSummary() { summaryLoads += 1; summaryLoadEpoch += 1; return {}; }
async function loadJudgments() {}
function reportLoadError() {}
function setFollowUpMutationBusy(busy) { if (!busy) busyEnds += 1; }
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _executable_function_source("quickDismiss", "reportMissedSummary"),
            """
(async () => {
  const first = quickDismiss(0, 'first', 'constraint');
  await Promise.resolve();
  summaryActionMutationOwner = null;
  const second = quickDismiss(1, 'second', 'constraint');
  await Promise.resolve();
  const secondOwner = summaryActionMutationOwner;
  requests[0].resolve({});
  await first;
  const afterStale = {
    newerStillOwned: summaryActionMutationOwner === secondOwner,
    busyEnds,
    summaryLoads,
  };
  requests[1].resolve({});
  await second;
  console.log(JSON.stringify({
    afterStale,
    afterNewer: {
      ownerCleared: summaryActionMutationOwner === null,
      busyEnds,
      summaryLoads,
    },
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "afterStale": {
            "newerStillOwned": True,
            "busyEnds": 0,
            "summaryLoads": 0,
        },
        "afterNewer": {
            "ownerCleared": True,
            "busyEnds": 1,
            "summaryLoads": 1,
        },
    }


def test_summary_report_owns_lock_before_prompt_and_fetch_await():
    script = "\n".join(
        [
            """
let followUpMutationPending = false;
let followUpMutationOwner = null;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let phiEpoch = 0;
let summaryLoadEpoch = 0;
let prompts = 0;
let fetches = 0;
let resolveFetch;
function prompt() { prompts += 1; return 'Missed detail'; }
async function fetch() {
  fetches += 1;
  return new Promise(resolve => { resolveFetch = resolve; });
}
async function requireOk() {}
async function loadSummary() { summaryLoadEpoch += 1; return {}; }
function reportLoadError() {}
function setFollowUpMutationBusy() {}
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _function_source("beginFollowUpMutation", "createFollowUpIntent"),
            _executable_function_source("reportMissedSummary", "loadJudgments"),
            """
(async () => {
  const report = reportMissedSummary();
  await Promise.resolve();
  const competingOwner = beginFollowUpMutation();
  const during = {
    competingOwner: competingOwner === null,
    reportOwned: summaryActionMutationOwner !== null,
    prompts,
    fetches,
  };
  resolveFetch({});
  await report;
  console.log(JSON.stringify({
    during,
    after: {
      reportOwned: summaryActionMutationOwner !== null,
      followUpMutationPending,
    },
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "during": {
            "competingOwner": True,
            "reportOwned": True,
            "prompts": 1,
            "fetches": 1,
        },
        "after": {
            "reportOwned": False,
            "followUpMutationPending": False,
        },
    }


def _run_follow_up_nested_reload_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 3;
let followUpSelectionEpoch = 20;
let selectedFollowUpId = 'action-1';
let latestProfileRevision = 8;
let workflowRevision = 2;
let followUpMutationPending = false;
let followUpMutationOwner = null;
let pendingFollowUpCompletion = null;
let summaryActionMutationOwner = null;
let followUpProjectionStale = false;
let pendingFollowUpIntent = null;
let followUpDialogOpen = true;
let followUpDialogMode = 'edit';
let followUpOutcomeStatus = null;
let followUpFilter = 'active';
let followUpsById = new Map([['action-1', { id: 'action-1', token: 'old' }]]);
const followUpDrafts = new Map();
let nestedFailure = null;
let mutationProfileRevision = 8;
let mutationIds = 0;
let closeCalls = 0;
let focusCalls = 0;
let savedAnnouncements = 0;
let successReports = 0;
let busyReleases = 0;
let reloads = 0;

const document = {
  getElementById() {
    return {
      classList: { toggle() {} },
      querySelector() { return { disabled: false, textContent: '' }; },
      setAttribute() {},
      tabIndex: 0,
    };
  },
};
const navigator = { onLine: true };

function newMutationId() { mutationIds += 1; return `mutation-${mutationIds}`; }
function setFollowUpMutationBusy(busy) { if (!busy) busyReleases += 1; }
function refreshGeneratedActionControls() {}
function updateFollowUpFormValidity() {}
function setFollowUpStatus(message) { if (message === 'Saved.') savedAnnouncements += 1; }
function setFollowUpDialogStatus() {}
function clearFollowUpRetry() { pendingFollowUpIntent = null; }
function renderFollowUps() {}
function reportLoadSuccess(scope) {
  if (scope === 'follow-up-mutation') successReports += 1;
}
function reportLoadError() {}
function setFormError() {}
function clearFollowUpCachedProjection() {}
function authorizePatientResponse(intent, data) {
  if (!followUpIntentOwnsMutation(intent, intent.requestPhiEpoch)) {
    return { accepted: false, profileAdvanced: false };
  }
  if (
    data.profile_revision < latestProfileRevision
    || data.workflow_revision < workflowRevision
  ) return { accepted: false, profileAdvanced: false };
  const profileAdvanced = data.profile_revision > latestProfileRevision;
  latestProfileRevision = data.profile_revision;
  workflowRevision = Math.max(workflowRevision, data.workflow_revision);
  if (profileAdvanced) phiEpoch += 1;
  return { accepted: true, profileAdvanced };
}
function shouldEvictClientPhi(error) {
  return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
}
function evictClientPhi() {
  phiEpoch += 1;
  followUpSelectionEpoch += 1;
  selectedFollowUpId = null;
  followUpDialogOpen = false;
  followUpMutationPending = false;
  followUpMutationOwner = null;
}
function closeFollowUpDialog(preserveDraft, force, restoreFocus = true) {
  closeCalls += 1;
  if (restoreFocus) focusCalls += 1;
  followUpDialogOpen = false;
  selectedFollowUpId = null;
  followUpSelectionEpoch += 1;
}
function restoreFollowUpMutationFocus() { focusCalls += 1; }
async function handleFollowUpConflict() { return true; }
async function readJsonResponse(response) { return response.data; }
async function fetch() {
  return {
    data: {
      item: { id: 'action-1', status: 'in_progress', token: 'saved' },
      workflow_revision: 3,
      profile_revision: mutationProfileRevision,
    },
  };
}
async function loadFollowUps() {
  reloads += 1;
  if (
    nestedFailure != null
    && !['revision-advance', 'workflow-advance'].includes(nestedFailure)
  ) {
    const error = new Error('Nested authoritative reload failed');
    error.status = nestedFailure;
    if (shouldEvictClientPhi(error)) evictClientPhi(error);
    return null;
  }
  const authoritativeRevision = nestedFailure === 'revision-advance'
    ? mutationProfileRevision + 1
    : mutationProfileRevision;
  followUpsById = new Map([['action-1', {
    id: 'action-1',
    status: 'in_progress',
    token: 'authoritative',
  }]]);
  latestProfileRevision = authoritativeRevision;
  const items = [...followUpsById.values()];
  items.profileRevision = authoritativeRevision;
  items.workflowRevision = nestedFailure === 'workflow-advance' ? 4 : 3;
  return items;
}
async function refreshClinicalWorkflowState(profileRevision) {
  reloads += 1;
  latestProfileRevision = profileRevision;
  if (nestedFailure === 'profile-offline') return { verified: false };
  return { verified: true };
}
""",
            _function_source("followUpControlsLocked", "newMutationId"),
            _function_source("beginFollowUpMutation", "createFollowUpIntent"),
            _function_source("createFollowUpIntent", "followUpIntentCanRender"),
            _executable_function_source("followUpIntentCanRender", "handleFollowUpConflict"),
            _executable_function_source("consumeFollowUpResponse", "restoreFollowUpMutationFocus"),
            _executable_function_source("releaseFollowUpMutation", "performFollowUpIntent"),
            _executable_function_source("performFollowUpIntent", "submitFollowUpMutation"),
            _executable_function_source("submitFollowUpMutation", "retryFollowUpIntent"),
            _executable_function_source("retryFollowUpIntent", "createManualFollowUp"),
            """
async function runAttempt(failure, profileChanged = false) {
  nestedFailure = failure;
  mutationProfileRevision = profileChanged ? latestProfileRevision + 1 : latestProfileRevision;
  selectedFollowUpId = 'action-1';
  followUpDialogOpen = true;
  followUpSelectionEpoch += 1;
  const draftKey = `edit:action-1:${failure ?? 'fresh'}`;
  followUpDrafts.set(draftKey, { owner: 'Caregiver draft' });
  const before = {
    closeCalls,
    focusCalls,
    savedAnnouncements,
    successReports,
    busyReleases,
  };
  const result = await submitFollowUpMutation(
    '/api/follow-ups/action-1',
    { expected_token: 'old', owner: 'Caregiver' },
    { method: 'PATCH', actionId: 'action-1', draftKey },
  );
  return {
    returned: result?.item?.id || null,
    draftPresent: followUpDrafts.has(draftKey),
    closeCalls: closeCalls - before.closeCalls,
    focusCalls: focusCalls - before.focusCalls,
    savedAnnouncements: savedAnnouncements - before.savedAnnouncements,
    successReports: successReports - before.successReports,
    busyReleases: busyReleases - before.busyReleases,
  };
}

(async () => {
  const unauthorized = await runAttempt(401);
  const forbidden = await runAttempt(403);
  const hardFailure = await runAttempt(500);
  const revisionAdvance = await runAttempt('revision-advance');
  const workflowAdvance = await runAttempt('workflow-advance');
  const profileReloadFailure = await runAttempt('profile-offline', true);
  nestedFailure = null;
  phiEpoch += 1;
  const beforeRetry = {
    closeCalls,
    focusCalls,
    savedAnnouncements,
    successReports,
    busyReleases,
  };
  await retryFollowUpIntent();
  const completionRetry = {
    draftPresent: followUpDrafts.has('edit:action-1:profile-offline'),
    closeCalls: closeCalls - beforeRetry.closeCalls,
    focusCalls: focusCalls - beforeRetry.focusCalls,
    savedAnnouncements: savedAnnouncements - beforeRetry.savedAnnouncements,
    successReports: successReports - beforeRetry.successReports,
    busyReleases: busyReleases - beforeRetry.busyReleases,
  };
  const fresh = await runAttempt(null);
  console.log(JSON.stringify({
    unauthorized,
    forbidden,
    hardFailure,
    revisionAdvance,
    workflowAdvance,
    profileReloadFailure,
    completionRetry,
    fresh,
    mutationIds,
    reloads,
    finalPending: followUpMutationPending,
    finalOwner: followUpMutationOwner,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_follow_up_nested_eviction_has_no_stale_success_cleanup_or_focus():
    result = _run_follow_up_nested_reload_probe()
    stale = {
        "returned": None,
        "draftPresent": True,
        "closeCalls": 0,
        "focusCalls": 0,
        "savedAnnouncements": 0,
        "successReports": 0,
        "busyReleases": 0,
    }
    assert result["unauthorized"] == stale
    assert result["forbidden"] == stale
    assert result["hardFailure"] == stale
    assert result["revisionAdvance"] == {
        "returned": "action-1",
        "draftPresent": False,
        "closeCalls": 1,
        "focusCalls": 1,
        "savedAnnouncements": 1,
        "successReports": 1,
        "busyReleases": 1,
    }
    assert result["workflowAdvance"] == {
        "returned": "action-1",
        "draftPresent": False,
        "closeCalls": 1,
        "focusCalls": 1,
        "savedAnnouncements": 1,
        "successReports": 1,
        "busyReleases": 1,
    }
    assert result["profileReloadFailure"] == {
        **stale,
        "busyReleases": 1,
    }
    assert result["completionRetry"] == {
        "draftPresent": False,
        "closeCalls": 1,
        "focusCalls": 1,
        "savedAnnouncements": 1,
        "successReports": 1,
        "busyReleases": 1,
    }
    assert result["fresh"] == {
        "returned": "action-1",
        "draftPresent": False,
        "closeCalls": 1,
        "focusCalls": 1,
        "savedAnnouncements": 1,
        "successReports": 1,
        "busyReleases": 1,
    }
    assert result["mutationIds"] == 7
    assert result["reloads"] == 10
    assert result["finalPending"] is False
    assert result["finalOwner"] is None


def _run_stale_follow_up_auth_load_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 5;
let followUpLoadEpoch = 0;
let workflowRevision = 1;
let latestProfileRevision = 7;
let taskSelectionEpoch = 0;
let followUpDialogOpen = false;
let followUpDialogMode = null;
let appointmentDialogOpen = false;
let followUpsById = new Map();
let evictions = 0;
let loadErrors = 0;
let loadSuccesses = 0;
const requests = [];
const navigator = { onLine: true };
const document = { getElementById() { return null; } };

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
async function fetch() {
  const request = deferred();
  requests.push(request);
  return request.promise;
}
function evictClientPhi() { evictions += 1; phiEpoch += 1; followUpLoadEpoch += 1; }
function shouldEvictClientPhi(error) {
  return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
}
function revisionIsOlder(candidate, current) {
  return candidate != null && current != null && Number(candidate) < Number(current);
}
function captureFollowUpDraft() {}
function syncChatRevision() {}
function requestClinicalConvergence() {}
function advancePatientAuthority(revision) {
  if (Number(revision) <= Number(latestProfileRevision)) return false;
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
function followUpItems() { return [...followUpsById.values()]; }
function renderFollowUps() {}
function renderVisitFollowUps() {}
function renderFollowUpDialog() {}
function setFollowUpStatus() {}
function updateFollowUpFormValidity() {}
function updateAppointmentFormValidity() {}
function reportLoadSuccess() { loadSuccesses += 1; }
function reportLoadError() { loadErrors += 1; }
function clearFollowUpCachedProjection() {}
function loadFailureMarkup() { return 'failed'; }
""",
            _response_authority_source(),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("loadFollowUps", "beginFollowUpMutation"),
            """
(async () => {
  const stale = loadFollowUps();
  await Promise.resolve();
  const fresh = loadFollowUps();
  await Promise.resolve();
  requests[1].resolve(response(200, {
    items: [{ id: 'fresh-action' }],
    workflow_revision: 2,
    profile_revision: 8,
  }));
  const freshResult = await fresh;
  requests[0].resolve(response(401, { error: 'old authorization failure' }));
  const staleResult = await stale;
  console.log(JSON.stringify({
    freshIds: freshResult?.map(item => item.id) ?? null,
    staleResult,
    cacheIds: [...followUpsById.keys()],
    evictions,
    loadErrors,
    loadSuccesses,
    phiEpoch,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_stale_follow_up_401_after_newer_success_is_side_effect_free():
    assert _run_stale_follow_up_auth_load_probe() == {
        "freshIds": ["fresh-action"],
        "staleResult": None,
        "cacheIds": ["fresh-action"],
        "evictions": 0,
        "loadErrors": 0,
        "loadSuccesses": 1,
        "phiEpoch": 6,
    }


def test_regressive_follow_up_reload_cannot_overwrite_newer_revisions():
    script = "\n".join(
        [
            """
let phiEpoch = 4;
let followUpLoadEpoch = 0;
let workflowRevision = 3;
let latestProfileRevision = 8;
let taskSelectionEpoch = 0;
let followUpDialogOpen = false;
let appointmentDialogOpen = false;
let followUpsById = new Map([['old', { id: 'old' }]]);
let resolveFetch;
let renders = 0;
let successes = 0;
const navigator = { onLine: true };
const document = { getElementById() { return null; } };
async function fetch() {
  return new Promise(resolve => { resolveFetch = resolve; });
}
function response(data) {
  return {
    status: 200,
    ok: true,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
function revisionIsOlder(candidate, current) {
  return candidate != null && current != null && Number(candidate) < Number(current);
}
function shouldEvictClientPhi() { return false; }
function captureFollowUpDraft() {}
function syncChatRevision() {}
function requestClinicalConvergence() {}
function advancePatientAuthority(revision) {
  if (Number(revision) <= Number(latestProfileRevision)) return false;
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
function followUpItems() { return [...followUpsById.values()]; }
function renderFollowUps() { renders += 1; }
function renderVisitFollowUps() {}
function renderFollowUpDialog() {}
function setFollowUpStatus() {}
function updateFollowUpFormValidity() {}
function updateAppointmentFormValidity() {}
function reportLoadSuccess() { successes += 1; }
function reportLoadError() {}
function clearFollowUpCachedProjection() {}
function loadFailureMarkup() { return 'failed'; }
""",
            _response_authority_source(),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("loadFollowUps", "beginFollowUpMutation"),
            """
(async () => {
  const pending = loadFollowUps();
  await Promise.resolve();
  latestProfileRevision = 9;
  workflowRevision = 4;
  followUpsById = new Map([['newer', { id: 'newer' }]]);
  resolveFetch(response({
    items: [{ id: 'stale' }],
    profile_revision: 8,
    workflow_revision: 3,
  }));
  const result = await pending;
  console.log(JSON.stringify({
    result,
    ids: [...followUpsById.keys()],
    latestProfileRevision,
    workflowRevision,
    renders,
    successes,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "result": None,
        "ids": ["newer"],
        "latestProfileRevision": 9,
        "workflowRevision": 4,
        "renders": 0,
        "successes": 0,
    }


def test_authoritative_refresh_must_reach_mutation_revisions():
    script = "\n".join(
        [
            """
let phiEpoch = 2;
let taskSelectionEpoch = 0;
let latestProfileRevision = 9;
function redactGeneratedQuestionChoices() {}
function redactGeneratedSummaryActions() {}
function revisionIsOlder(candidate, current) {
  return candidate != null && current != null && Number(candidate) < Number(current);
}
function syncChatRevision(revision) { latestProfileRevision = revision; }
async function loadStatus() { return { profile_revision: 9 }; }
async function loadSummary() { return { profile_revision: 9 }; }
async function loadQuestions() { return { profileRevision: 9 }; }
async function loadTasks() { return []; }
async function loadVisits() {
  const value = [];
  value.profileRevision = 9;
  value.workflowRevision = 3;
  return value;
}
async function loadFollowUps() {
  const value = [];
  value.profileRevision = 9;
  value.workflowRevision = 3;
  return value;
}
""",
            _executable_function_source("refreshClinicalWorkflowState", "consumeWorkflowResponse"),
            """
(async () => {
  const staleProfile = await refreshClinicalWorkflowState(10, 3);
  const staleWorkflow = await refreshClinicalWorkflowState(9, 4);
  const reached = await refreshClinicalWorkflowState(9, 3);
  console.log(JSON.stringify({ staleProfile, staleWorkflow, reached }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "staleProfile": {"verified": False},
        "staleWorkflow": {"verified": False},
        "reached": {"verified": True},
    }


def _run_stale_status_auth_load_probe() -> dict:
    script = "\n".join(
        [
            """
let phiEpoch = 9;
let statusLoadEpoch = 0;
let latestProfileRevision = 8;
let workflowRevision = null;
let selectedTaskId = null;
let taskSelectionEpoch = 0;
let evictions = 0;
let failures = 0;
let loadErrors = 0;
let rendered = null;
const requests = [];

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
function response(status, data) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get() { return null; } },
    async json() { return data; },
  };
}
async function fetch() {
  const request = deferred();
  requests.push(request);
  return request.promise;
}
function evictClientPhi() { evictions += 1; phiEpoch += 1; statusLoadEpoch += 1; }
function shouldEvictClientPhi(error) {
  return error?.status === 401 || error?.status === 403 || Number(error?.status) >= 500;
}
function revisionIsOlder(candidate, current) {
  return candidate != null && current != null && Number(candidate) < Number(current);
}
function syncChatRevision() { return false; }
function requestClinicalConvergence() {}
function advancePatientAuthority(revision) {
  if (Number(revision) <= Number(latestProfileRevision)) return false;
  latestProfileRevision = revision;
  phiEpoch += 1;
  return true;
}
function renderSidebar(data) { rendered = data.marker; }
function loadTasks() {}
function reportLoadSuccess() {}
function reportLoadError() { loadErrors += 1; }
function renderStatusFailure() { failures += 1; rendered = 'failure'; }
""",
            _response_authority_source(),
            _executable_function_source("readJsonResponse", "readJobSubmission"),
            _executable_function_source("loadStatus", "renderStatusFailure"),
            """
(async () => {
  const stale = loadStatus();
  await Promise.resolve();
  const fresh = loadStatus();
  await Promise.resolve();
  requests[1].resolve(response(200, { marker: 'fresh', profile_revision: 9 }));
  await fresh;
  requests[0].resolve(response(401, { error: 'old authorization failure' }));
  const staleResult = await stale;
  console.log(JSON.stringify({
    staleResult,
    rendered,
    evictions,
    failures,
    loadErrors,
    phiEpoch,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_stale_nested_status_401_after_newer_success_is_side_effect_free():
    assert _run_stale_status_auth_load_probe() == {
        "staleResult": None,
        "rendered": "fresh",
        "evictions": 0,
        "failures": 0,
        "loadErrors": 0,
        "phiEpoch": 10,
    }


def test_clinical_refresh_loaders_gate_auth_eviction_on_current_request():
    loaders = (
        _function_source("loadStatus", "renderStatusFailure"),
        _function_source("loadSummary", "renderPendingSummary"),
        _function_source("loadTasks", "renderTasks"),
        _function_source("loadVisits", "followUpItems"),
        _function_source("loadQuestions", "renderQuestions"),
        _function_source("loadFollowUps", "beginFollowUpMutation"),
    )
    for loader in loaders:
        assert "requestIsCurrent" in loader
        assert "readJsonResponse(" in loader
        assert ", requestIsCurrent)" in loader
        catch_source = loader[loader.index("catch") :]
        assert "if (!requestIsCurrent())" in catch_source


def test_clinical_refresh_rejects_mixed_revision_batches():
    script = "\n".join(
        [
            """
let phiEpoch = 0;
let taskSelectionEpoch = 0;
let latestProfileRevision = 9;
let mode = 'mixed';
function redactGeneratedQuestionChoices() {}
function redactGeneratedSummaryActions() {}
function revisionIsOlder(candidate, current) {
  return candidate != null && current != null && Number(candidate) < Number(current);
}
function syncChatRevision(revision) { latestProfileRevision = revision; }
function revisionArray(revision) {
  const items = [];
  items.profileRevision = revision;
  items.workflowRevision = 4;
  return items;
}
async function loadStatus() {
  const revision = 10;
  latestProfileRevision = revision;
  return { profile_revision: revision };
}
async function loadSummary() {
  return { profile_revision: mode === 'mixed' ? 9 : 10 };
}
async function loadQuestions() {
  return revisionArray(mode === 'mixed' ? 9 : 10);
}
async function loadTasks() { return []; }
async function loadVisits() {
  return revisionArray(mode === 'mixed' ? 9 : 10);
}
async function loadFollowUps() {
  return revisionArray(mode === 'mixed' ? 9 : 10);
}
""",
            _executable_function_source("refreshClinicalWorkflowState", "consumeWorkflowResponse"),
            """
(async () => {
  const mixed = await refreshClinicalWorkflowState(9);
  mode = 'uniform';
  const uniform = await refreshClinicalWorkflowState(9);
  console.log(JSON.stringify({ mixed, uniform }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
""",
        ]
    )
    completed = _run_node_script(script)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "mixed": {"verified": False},
        "uniform": {"verified": True},
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
    completed = _run_node_script(script)
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
    assert "requestSummaryEpoch === summaryLoadEpoch" in loader
    assert "readJsonResponse(r, requestIsCurrent)" in loader
    assert "authorizePatientResponse(" in loader
    assert "options.authorizationOptions || {}" in loader
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
    completed = _run_node_script(script)
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
    assert result["targetedLowerWorkflow"] is False
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
        assert "requestIsCurrent()" in catch


def test_follow_up_retry_conflict_eviction_and_loading_contracts_are_strict():
    owner = _function_source("beginFollowUpMutation", "createFollowUpIntent")
    intent = _function_source("createFollowUpIntent", "followUpIntentCanRender")
    performer = _function_source("performFollowUpIntent", "submitFollowUpMutation")
    submitter = _function_source("submitFollowUpMutation", "retryFollowUpIntent")
    retry = _function_source("retryFollowUpIntent", "createManualFollowUp")
    conflict = _function_source("handleFollowUpConflict", "consumeFollowUpResponse")
    consumer = _function_source("consumeFollowUpResponse", "restoreFollowUpMutationFocus")
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    loader = _function_source("loadFollowUps", "beginFollowUpMutation")
    polling = _function_source("startPolling", "currentVisit")

    assert owner.index("followUpMutationOwner = owner") < owner.index(
        "followUpMutationPending = true"
    )
    assert "mutation_id: newMutationId()" in intent
    assert submitter.index("beginFollowUpMutation()") < submitter.index(
        "selectedFollowUpId = options.actionId"
    )
    assert submitter.index("beginFollowUpMutation()") < submitter.index("createFollowUpIntent(")
    assert "performFollowUpIntent(intent, true)" in retry
    assert "pendingFollowUpIntent = intent" in performer
    assert "error?.status === 409" in performer
    assert "followUpIntentOwnsMutation" in performer
    assert "releaseFollowUpMutation(intent)" in performer
    assert "followUpIntentOwnsMutation(intent, expectedPhiEpoch)" in consumer
    assert consumer.index("await refreshClinicalWorkflowState") < consumer.index(
        "followUpIntentOwnsMutation(intent, expectedPhiEpoch)"
    )
    assert consumer.index("await loadFollowUps()") < consumer.index(
        "followUpIntentOwnsMutation(intent, expectedPhiEpoch)"
    )
    renderer = _function_source("renderFollowUps", "setFollowUpFilter")
    busy = _function_source("setFollowUpMutationBusy", "updateFollowUpOutcomeGuidance")
    closer = _function_source("closeFollowUpDialog", "closeFollowUpFromBackdrop")
    focus = _function_source("restoreFollowUpMutationFocus", "performFollowUpIntent")
    finalizer = _function_source("releaseFollowUpMutation", "performFollowUpIntent")
    assert "if (followUpControlsLocked()) setFollowUpMutationBusy(true)" in renderer
    assert "if (!('followUpWasDisabled' in control.dataset))" in busy
    assert ".action-accept-btn" in busy
    assert ".action-dismiss-btn" in busy
    assert ".follow-up-filter" in busy
    assert "#follow-up-retry button" in busy
    assert ".action-feedback button" in busy
    assert ".action-feedback input" in busy
    assert "#follow-up-dialog input" in busy
    assert "#follow-up-dialog textarea" in busy
    assert "#follow-up-dialog select" in busy
    assert ".summary-feedback-button" in busy
    assert "refreshGeneratedActionControls()" in finalizer
    assert "intent.pendingPhiEpoch = expectedPhiEpoch" in consumer
    assert "authorizePatientResponse(intent, data, { workflow: 'targeted' })" in consumer
    assert "intent.pendingPhiEpoch" in _function_source(
        "followUpIntentOwnsMutation", "handleFollowUpConflict"
    )
    assert "if (followUpControlsLocked() && !force)" in closer
    assert "closeFollowUpDialog(false, true, false)" in finalizer
    assert "releaseFollowUpMutation(intent, true, true)" in finalizer
    assert "document.querySelectorAll('.follow-up-item')" in focus
    assert "restoreFollowUpMutationFocus(intent)" in finalizer
    assert "performFollowUpIntent" not in conflict
    assert "redactGeneratedSummaryActions()" in conflict
    assert "loadFollowUps()" in conflict
    assert "loadSummary()" in conflict
    assert "loadFollowUps()" not in polling
    assert "shouldEvictClientPhi(error)" in loader
    assert "if (!requestIsCurrent())" in loader
    assert "reportLoadError('follow-ups', error)" in loader
    assert "readJsonResponse(response, requestIsCurrent)" in loader
    assert "if (!requestIsCurrent()) return null" in loader
    for expression in (
        "followUpsById = new Map()",
        "followUpLoadEpoch += 1",
        "selectedFollowUpId = null",
        "followUpSelectionEpoch += 1",
        "followUpDialogOpen = false",
        "pendingFollowUpIntent = null",
        "followUpMutationPending = false",
        "followUpMutationOwner = null",
        "followUpDrafts = new Map()",
        "clear('follow-up-list')",
        "clear('follow-up-status')",
    ):
        assert expression in eviction


def test_follow_up_mutation_handlers_reject_before_dom_or_state_access():
    handlers = (
        _function_source("acceptGeneratedFollowUp", "renderClaimEvidence"),
        _function_source("createManualFollowUp", "saveFollowUpDetails"),
        _function_source("saveFollowUpDetails", "submitFollowUpOutcome"),
        _function_source("submitFollowUpOutcome", "changeFollowUpStatus"),
        _function_source("changeFollowUpStatus", "renderAppointmentOptions"),
    )
    for handler in handlers:
        guard = handler.index("if (followUpControlsLocked()) return")
        assert guard < handler.index("document.") if "document." in handler else True
        assert guard < handler.index("row?.dataset") if "row?.dataset" in handler else True
        assert (
            guard < handler.index("selectedFollowUpId") if "selectedFollowUpId" in handler else True
        )


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
