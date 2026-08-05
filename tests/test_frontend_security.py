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
        "loadChanges()",
    ):
        assert loader in retry


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
