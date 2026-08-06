"""Static regression checks for file upload and DOM rendering safety."""

from __future__ import annotations

from pathlib import Path

APP_JS = Path("static/app.js").read_text(encoding="utf-8")


def _function_source(name: str, next_name: str) -> str:
    start = APP_JS.index(f"function {name}")
    end = APP_JS.index(f"function {next_name}", start)
    return APP_JS[start:end]


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


def test_claim_evidence_and_decision_support_wording_are_non_definitive():
    summary = _function_source("renderSummary", "removeItem")
    assert "POTENTIAL FIT" in summary
    assert "MAY FIT" in summary
    assert "Trial to discuss" in summary
    assert "Best matched trial" not in APP_JS
    assert "PRRT: ELIGIBLE" not in APP_JS
    assert "renderClaimEvidence" in summary
    assert "d.claim_evidence?.claims?.cga_trend_detail" in summary


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
