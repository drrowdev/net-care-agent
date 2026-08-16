"""Fail if a secret-scrubber redaction placeholder was ever committed as real source.

A deployment outage was caused by a redaction artefact reaching ``main``: the
Authorization header in ``Scripts/deploy.ps1`` had been replaced by a run of
asterisks, so every Kudu request was sent with a malformed header and no deploy
or rollback could succeed. The damage was invisible to reviewers because the
scrubber redacts the same string again when the file is displayed, so this guard
detects artefacts by *measurement* over raw bytes rather than by reading.

Detection is deliberately case-sensitive for bare words. Ordinary lowercase
prose ("rows are redacted before they can be acted on") and lowercase test
fixtures (``{"error": "redacted"}``) are legitimate and must keep working; an
upper-case placeholder word standing alone in source is not.

The patterns below are written so their own source text does not match them
(``REDACT(?:ED)`` matches the word but is not the word), which keeps this file
inside its own coverage instead of needing a blind-spot exemption.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]

# Extensions whose contents are not reviewable text and are skipped wholesale.
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".woff",
        ".woff2",
        ".docx",
        ".xlsx",
        ".pptx",
    }
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # A run of asterisks: exactly what this scrubber emitted into deploy.ps1.
    ("asterisk-run", re.compile(r"\*{3,}")),
    # Bullet/block glyph masking used by other scrubbers.
    ("glyph-run", re.compile(r"[\u2022\u25cf\u25a0\u25ae\u2588]{3,}")),
    # Explicit bracketed placeholders, in any case.
    ("bracketed-placeholder", re.compile(r"[<\[]\s*redacted\s*[>\]]", re.IGNORECASE)),
    # Shouted placeholder words standing alone.
    (
        "shouted-placeholder",
        re.compile(r"\b(?:REDACT(?:ED)|SANITIZ(?:ED)|SCRUBB(?:ED)|MASK(?:ED))\b"),
    ),
)

# Narrow allowlist for masking that is genuinely intentional, e.g. a literal a
# module writes into its own log output. Entries are ``(posix path, category)``
# and exempt that whole file for that one category only.
#
# Empty on purpose: every legitimate use of these words in this repository is
# lowercase prose or a lowercase fixture value, so none of the rules above trip
# on them. Add an entry (with a comment saying why) rather than loosening a rule.
ALLOWLIST: frozenset[tuple[str, str]] = frozenset()


def _tracked_files() -> list[str]:
    """Every file git tracks. Fails closed: a broken git call fails the test."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(ROOT),
        capture_output=True,
        check=True,
    )
    return [name for name in completed.stdout.decode("utf-8").split("\0") if name]


def _findings() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for name in _tracked_files():
        path = ROOT / name
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:  # pragma: no cover - would be a new binary type
            found.append((name, 0, "undecodable-text-file"))
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for category, pattern in PATTERNS:
                if (name, category) in ALLOWLIST:
                    continue
                if pattern.search(line):
                    # Report the location and category only. The offending line
                    # may sit next to material that should not be echoed.
                    found.append((name, number, category))
    return found


def test_no_committed_redaction_artefacts_anywhere_in_the_repository():
    findings = _findings()
    assert not findings, "committed redaction artefacts: " + ", ".join(
        f"{name}:{number} ({category})" for name, number, category in findings
    )


def test_the_guard_can_actually_see_an_artefact():
    """A detector that never fires would pass silently forever."""
    # Assembled from fragments so this file stays clean under its own scan.
    samples = {
        "asterisk-run": "Authorization = " + '"' + "*" * 6 + '"',
        "glyph-run": "value = " + "\u2022" * 4,
        "bracketed-placeholder": "token = <" + "redacted" + ">",
        "shouted-placeholder": "token = RED" + "ACTED",
    }
    for category, pattern in PATTERNS:
        assert pattern.search(samples[category]), f"{category} failed to match its own sample"

    # ...and does not fire on the legitimate lowercase prose and fixtures that
    # already exist in this repository.
    benign = [
        "revisionless rows are redacted before they can be acted on",
        'body=json.dumps({"error": "redacted"}),',
        "Legacy retained jobs are sanitized and atomically replaced",
        "which masked the real signals the field exists to surface",
        "def wrapper(*args, **kwargs):",
    ]
    for line in benign:
        for category, pattern in PATTERNS:
            assert not pattern.search(line), f"{category} false-positived on: {line}"
