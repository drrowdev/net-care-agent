"""Filesystem helpers — atomic writes and small utilities."""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Writes to a sibling `.tmp` file first, then `os.replace` swaps it in.
    Prevents readers (or a crash mid-write) from seeing a half-written file
    on the Azure Files mount.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)
