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
        "escHtml(nodeEl.dataset.event)",
        "escHtml(nodeEl.dataset.date)",
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
