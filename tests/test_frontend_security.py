"""Static regression checks for file upload and DOM rendering safety."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

APP_JS = Path("static/app.js").read_text(encoding="utf-8")


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
let workflowRevision = 3;
let visitsById = new Map([['visit-phi', { patient: true }]]);
let appointmentOptions = [{ patient: true }];
let appointmentQuestionSources = [{ patient: true }];
let questionLoadEpoch = 0;
let generatedQuestionsUnavailable = false;
let visitFollowUps = [{ patient: true }];
let selectedVisitId = 'visit-phi';
let visitSelectionEpoch = 0;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'decisions';
let pendingWorkflowIntent = { patient: true };
let workflowMutationPending = true;
let appointmentDrafts = new Map([['visit-phi', { patient: true }]]);
let renderSummaryCalls = 0;
const loadErrors = [];

function renderLatestResearchUpdate() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
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
""",
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
        "loadErrors": [["summary", status]],
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
        "latestProfileRevision = null",
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
    assert evidence.index("const evidence = await") < evidence.index("requestPhiEpoch !== phiEpoch")
    assert evidence.index("requestPhiEpoch !== phiEpoch") < evidence.index(
        "patientEvidence = evidence"
    )


def test_central_phi_eviction_clears_patient_panels_dialogs_and_histories():
    eviction = _function_source("evictClientPhi", "renderLatestResearchUpdate")
    for expression in (
        "taskSelectionEpoch += 1",
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
    epoch_guard = auth_failure.index("if (requestPhiEpoch !== phiEpoch)")
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
    assert "const requestPhiEpoch = phiEpoch" in close
    assert "requestPhiEpoch === phiEpoch" in close
    questions = _function_source("generateQuestions", "addQuestion")
    assert "const requestPhiEpoch = phiEpoch" in questions
    assert "requestPhiEpoch !== phiEpoch" in questions
    for handler, next_name in (
        ("addJudgment", "deleteJudgment"),
        ("addSymptom", "deleteSymptom"),
        ("addQuestion", "toggleQuestion"),
    ):
        source = _function_source(handler, next_name)
        assert "const requestPhiEpoch = phiEpoch" in source
        assert "requestPhiEpoch !== phiEpoch" in source


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
    assert selection.count("selectionEpoch !== taskSelectionEpoch || selectedTaskId !== id") >= 7
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
    assert "const revisionChanged = syncChatRevision(data.profile_revision)" in sender
    assert "if (revisionChanged) return" in sender
    assert "chatHistoryRevision = String(data.profile_revision)" not in sender
    assert "if (e.status === 409)" in sender
    assert "syncChatRevision(e.data?.profile_revision, true)" in sender
    assert "?? latestProfileRevision" not in sender


def test_alert_resolution_uses_stable_id_token_and_revision():
    sidebar = _function_source("renderSidebar", "resolveAlert")
    assert "data-alert-id" in sidebar
    assert "data-resolve-token" in sidebar
    resolver = _function_source("resolveAlert", "loadPatientEvidence")
    assert "/api/alerts/${encodeURIComponent(alertId)}/resolve" in resolver
    assert "expected_token: expectedToken" in resolver
    assert "expected_profile_revision: latestProfileRevision" in resolver
    assert "syncChatRevision(result.profile_revision, true)" in resolver


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
let visitFollowUps = [];
let pendingWorkflowIntent = null;
let workflowMutationPending = false;
let appointmentDrafts = new Map();
let renderPreparationCalls = 0;
let renderWorkspaceCalls = 0;
let successReports = 0;
let callerCleanupCalls = 0;

function captureAppointmentDraft() {}
function renderVisitPreparation() { renderPreparationCalls += 1; }
function renderAppointmentWorkspace() { renderWorkspaceCalls += 1; }
function reportLoadSuccess() { successReports += 1; }
function reportLoadError() {}
async function refreshClinicalWorkflowState() { return true; }
async function handleWorkflowConflict() { return true; }
function shouldEvictClientPhi() { return false; }
function evictClientPhi() {}
function setAppointmentMutationBusy() {}
function updateAppointmentFormValidity() {}
function safeClassToken(value) { return String(value || ''); }
""",
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
    retryPreserved: pendingWorkflowIntent === offlineIntent,
    offlineRetryVisible: element('appointment-retry').hidden === false,
    offlineDraft: appointmentDrafts.get('visit-b').manualQuestion,
    offlineResult,
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
        "retryPreserved": True,
        "offlineRetryVisible": True,
        "offlineDraft": "caregiver draft",
        "offlineResult": None,
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
const focusedControl = { blurred: false, blur() { this.blurred = true; } };
appointmentDialog.contains = candidate => candidate === focusedControl;
const background = fakeElement();
background.inert = true;
background.attributes['aria-hidden'] = 'true';
background.dataset.dialogAriaHidden = 'true';
const appointmentOverlay = element('appointment-overlay');
appointmentOverlay.classList.add('open');
appointmentOverlay.attributes['aria-hidden'] = 'false';
const body = { children: [background, appointmentOverlay], classList: new FakeClassList() };
body.classList.add('dialog-open');
const document = {
  activeElement: focusedControl,
  body,
  getElementById: element,
  querySelectorAll() { return []; },
};

for (const id of [
  'visit-list', 'visit-source-questions', 'visit-question-list',
  'visit-decision-list', 'visit-followup-list'
]) element(id).innerHTML = `SECRET ${id}`;
for (const id of [
  'visit-create-title', 'visit-create-date', 'visit-create-time',
  'visit-create-clinician', 'visit-create-location',
  'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
  'visit-edit-clinician', 'visit-edit-location', 'visit-manual-question',
  'visit-decision-text', 'visit-decision-supersedes', 'visit-followup-text',
  'visit-followup-owner', 'visit-followup-due'
]) element(id).value = `SECRET ${id}`;
for (const id of [
  'visit-create-error', 'visit-details-error', 'visit-question-error',
  'visit-decision-error', 'visit-followup-error'
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
let visitFollowUps = [{ patient: true }];
let selectedVisitId = 'visit-phi';
let visitSelectionEpoch = 8;
let appointmentDialogOpen = true;
let activeAppointmentTab = 'decisions';
let pendingWorkflowIntent = { patient: true };
let workflowMutationPending = true;
let appointmentDrafts = new Map([['visit-phi', { patient: true }]]);
let chatHistory = [{ patient: true }];
let chatHistoryRevision = 41;
let chatOpen = true;
let taskSelectionEpoch = 2;
let phiEpoch = 5;
let lastDialogTrigger = { patient: true };
let activeDialogSurface = appointmentDialog;

function renderLatestResearchUpdate() {}
function clearFreshnessProjection() {}
function clearReportCopyState() {}
function updateCharCount() {}
function setAppointmentMutationBusy() {}
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
    'visit-decision-error', 'visit-followup-error', 'visit-decision-label'
  ];
  const formIds = [
    'visit-create-title', 'visit-create-date', 'visit-create-time',
    'visit-create-clinician', 'visit-create-location',
    'visit-edit-title', 'visit-edit-date', 'visit-edit-time',
    'visit-edit-clinician', 'visit-edit-location', 'visit-manual-question',
    'visit-decision-text', 'visit-decision-supersedes', 'visit-followup-text',
    'visit-followup-owner', 'visit-followup-due'
  ];
  console.log(JSON.stringify({
    lateResults,
    phiEpoch,
    workflowRevision,
    latestProfileRevision,
    mapsEmpty: visitsById.size === 0
      && appointmentOptions.length === 0
      && appointmentQuestionSources.length === 0
      && visitFollowUps.length === 0,
    selectionCleared: selectedVisitId === null && appointmentDrafts.size === 0,
    intentCleared: pendingWorkflowIntent === null && workflowMutationPending === false,
    projectionsScrubbed: projectionIds.every(id => {
      const node = element(id);
      return !`${node.innerHTML} ${node.textContent} ${node.value}`.includes('SECRET');
    }),
    formsScrubbed: formIds.every(id => element(id).value === ''),
    overlayClosed: !appointmentOverlay.classList.contains('open')
      && appointmentOverlay.attributes['aria-hidden'] === 'true',
    overlayInert: appointmentOverlay.inert,
    dialogInert: appointmentDialog.inert,
    focusBlurred: focusedControl.blurred,
    refsCleared: activeDialogSurface === null && lastDialogTrigger === null,
    bodyReset: !body.classList.contains('dialog-open')
      && background.inert === false
      && !('aria-hidden' in background.attributes)
      && !('dialogAriaHidden' in background.dataset),
    createClosed: element('visit-create-panel').hidden
      && element('visit-create-toggle').attributes['aria-expanded'] === 'false',
    retriesHidden: element('appointment-retry').hidden
      && element('visit-create-retry').hidden,
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
function loadStatus() { return Promise.resolve(); }
function loadSummary() { return Promise.resolve(); }
function loadTasks() { return Promise.resolve(); }
function loadVisits() { return Promise.resolve(); }
function loadVisitFollowUps() { return Promise.resolve(); }
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
        "missingRevision",
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
    assert result["loadErrors"] == [
        ["appointment-workflow", 409],
        ["questions", "TypeError"],
        ["questions", "AbortError"],
        ["questions", 409],
    ]


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
        "workflowRevision = data.workflow_revision"
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
    assert "phiEpoch += 1" in refresh
    assert "taskSelectionEpoch += 1" in refresh
    assert "syncChatRevision(profileRevision, true, false)" in refresh
    assert refresh.index("redactGeneratedQuestionChoices()") < refresh.index("loadQuestions()")
    assert "loadSummary()" in refresh
    assert "loadTasks()" in refresh
    assert "loadVisits()" in refresh
    assert "loadVisitFollowUps()" in refresh
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
        "visitFollowUps = []",
        "selectedVisitId = null",
        "visitSelectionEpoch += 1",
        "appointmentDialogOpen = false",
        "pendingWorkflowIntent = null",
        "workflowMutationPending = false",
        "appointmentDrafts = new Map()",
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
    assert "visitFollowUps.filter" in APP_JS
    assert "/api/alerts/resolve/" not in APP_JS
    assert "/api/follow-ups/" not in APP_JS
    assert "Save as follow-up" not in APP_JS
    assert "follow-up filters" not in APP_JS
