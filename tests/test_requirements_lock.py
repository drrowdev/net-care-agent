"""Production requirements are a complete exact lock derived from local metadata."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.utils import canonicalize_name

ROOT = Path(__file__).parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^;\s]+)$")


def _locked_requirements() -> dict[str, str]:
    locked = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        match = PIN.fullmatch(line)
        assert match, f"production requirement is not an exact pin: {line!r}"
        locked[canonicalize_name(match.group(1))] = match.group(2)
    return locked


def test_direct_runtime_requirements_match_production_lock():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    locked = _locked_requirements()
    for requirement in project["dependencies"]:
        match = PIN.fullmatch(requirement)
        assert match, f"direct runtime requirement is not exact: {requirement!r}"
        assert locked[canonicalize_name(match.group(1))] == match.group(2)


def test_production_lock_contains_resolved_runtime_closure():
    expected = {
        "annotated-types",
        "anthropic",
        "anyio",
        "blinker",
        "certifi",
        "cffi",
        "charset-normalizer",
        "click",
        "colorama",
        "cryptography",
        "distro",
        "docstring-parser",
        "flask",
        "gunicorn",
        "h11",
        "httpcore",
        "httpx",
        "idna",
        "itsdangerous",
        "jinja2",
        "jiter",
        "markupsafe",
        "packaging",
        "pdfminer-six",
        "pdfplumber",
        "pillow",
        "pycparser",
        "pydantic",
        "pydantic-core",
        "pypdfium2",
        "python-dotenv",
        "requests",
        "sniffio",
        "typing-extensions",
        "typing-inspection",
        "urllib3",
        "werkzeug",
    }
    assert set(_locked_requirements()) == expected
