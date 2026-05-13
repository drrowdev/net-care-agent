"""
Phase 4 UI hygiene checks: cache headers + static asset split integrity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_index_html_references_split_assets():
    """index.html should link to extracted styles.css and app.js, no inline blocks."""
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/styles.css">' in html
    assert '<script defer src="/static/app.js"></script>' in html
    # No leftover inline <style> or <script> blocks (other than the link/script tags).
    assert "<style>" not in html, "inline <style> survived the split"
    # A bare <script> tag (not the external one) would mean inline JS leaked through.
    assert not re.search(r"<script(?!\s+defer\s+src=)", html), "inline <script> survived"


def test_extracted_assets_exist_and_nonempty():
    css = Path("static/styles.css")
    js = Path("static/app.js")
    assert css.exists() and css.stat().st_size > 10_000
    assert js.exists() and js.stat().st_size > 10_000


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
