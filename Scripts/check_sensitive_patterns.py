#!/usr/bin/env python3
"""Block commits/pushes that contain sensitive substrings.

This hook is deliberately content-agnostic: the list of forbidden
substrings is loaded from outside the repository so the patterns
themselves never enter source control. The repo's only job is to run
this script — the operator supplies the patterns.

Pattern source resolution order (first non-empty wins, all are merged):
  1. ``$NETCARE_PATTERNS_FILE`` — path to a text file with one pattern
     per line. Use this on a developer machine; point it at a file in
     your private storage.
  2. ``.git/info/sensitive-patterns.txt`` — convenient default location
     for local checkouts (``.git/`` is never tracked by git).
  3. ``$SENSITIVE_PATTERNS`` — newline-separated patterns supplied via
     environment variable. Used by CI where there is no filesystem to
     read from.

Lines beginning with ``#`` and blank lines are ignored. Matching is a
case-insensitive literal substring check.

Modes:
  --staged                  Scan blobs staged for the current commit.
  --commit-range A..B       Scan files changed in a commit range
                            (use for pre-push to catch ``--no-verify``
                            bypasses).
  --all                     Scan every tracked file at HEAD (use for CI).
  --files <paths>           Scan the explicit list of files.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def load_patterns() -> list[str]:
    sources: list[str] = []

    env_file = os.environ.get("NETCARE_PATTERNS_FILE", "").strip()
    if env_file and Path(env_file).is_file():
        sources.append(_read_text_safely(Path(env_file)))

    git_info = Path(".git/info/sensitive-patterns.txt")
    if git_info.is_file():
        sources.append(_read_text_safely(git_info))

    env_raw = os.environ.get("SENSITIVE_PATTERNS", "")
    if env_raw:
        sources.append(env_raw)

    patterns: list[str] = []
    for source in sources:
        for line in source.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)

    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in patterns:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def check_text(text: str, patterns: list[str]) -> list[str]:
    """Return the patterns that appear (case-insensitively) in ``text``."""
    lower = text.lower()
    return [p for p in patterns if p.lower() in lower]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, errors="replace", stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _staged_files() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [f for f in out.splitlines() if f.strip()]


def _range_files(rev_range: str) -> list[str]:
    out = _git("diff", "--name-only", "--diff-filter=ACM", rev_range)
    return [f for f in out.splitlines() if f.strip()]


def _all_tracked_files() -> list[str]:
    out = _git("ls-files")
    return [f for f in out.splitlines() if f.strip()]


def _staged_blob(path: str) -> str:
    return _git("show", f":{path}")


def _committed_blob(rev: str, path: str) -> str:
    return _git("show", f"{rev}:{path}")


def _scan(files: list[str], read_fn) -> list[tuple[str, list[str]]]:
    patterns = load_patterns()
    if not patterns:
        return []
    findings: list[tuple[str, list[str]]] = []
    for f in files:
        text = read_fn(f)
        if not text:
            continue
        hits = check_text(text, patterns)
        if hits:
            findings.append((f, hits))
    return findings


def _print_findings(findings: list[tuple[str, list[str]]]) -> None:
    sys.stderr.write(
        "\n  ┌──────────────────────────────────────────────────────────┐\n"
        "  │  SENSITIVE PATTERN MATCH — operation blocked              │\n"
        "  └──────────────────────────────────────────────────────────┘\n"
    )
    for path, hits in findings:
        sys.stderr.write(f"\n  {path}\n")
        for h in hits:
            # Redact the matched pattern itself so logs don't echo it
            preview = h[:3] + "…" if len(h) > 3 else h
            sys.stderr.write(f"    - matched {len(h)}-char pattern (starts {preview!r})\n")
    sys.stderr.write(
        "\n  Remove the offending content and retry.\n"
        "  If the match is a false positive, narrow the pattern in your\n"
        "  pattern file so it no longer triggers on legitimate content.\n\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true")
    group.add_argument("--commit-range")
    group.add_argument("--all", action="store_true")
    group.add_argument("--files", nargs="+")
    args = parser.parse_args()

    patterns = load_patterns()
    if not patterns:
        sys.stderr.write(
            "check_sensitive_patterns: no patterns configured — skipping.\n"
            "  Configure one of:\n"
            "    - NETCARE_PATTERNS_FILE env var pointing at a pattern file\n"
            "    - .git/info/sensitive-patterns.txt in your local checkout\n"
            "    - SENSITIVE_PATTERNS env var (newline-separated)\n"
        )
        return 0

    if args.staged:
        findings = _scan(_staged_files(), _staged_blob)
    elif args.commit_range:
        rev = args.commit_range.split("..")[-1] or "HEAD"
        findings = _scan(_range_files(args.commit_range), lambda f: _committed_blob(rev, f))
    elif args.all:
        findings = _scan(_all_tracked_files(), lambda f: _read_text_safely(Path(f)))
    else:  # args.files
        findings = _scan(args.files, lambda f: _read_text_safely(Path(f)))

    if findings:
        _print_findings(findings)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
