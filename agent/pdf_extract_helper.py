"""Minimal child-process entry point for untrusted PDF parsing."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 7:
        return 2
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    max_pages, max_chars = int(sys.argv[3]), int(sys.argv[4])
    timeout_seconds, max_memory_mb = int(sys.argv[5]), int(sys.argv[6])
    if sys.platform != "win32":
        import resource

        memory = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (max(1, timeout_seconds), max(1, timeout_seconds)),
        )
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (max_chars * 4 + 4096, max_chars * 4 + 4096),
        )
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))

    import pdfplumber

    from .io import atomic_write_text

    chunks: list[str] = []
    total = 0
    try:
        with pdfplumber.open(source) as pdf:
            if len(pdf.pages) > max_pages:
                return 3
            for page in pdf.pages:
                text = page.extract_text() or ""
                total += len(text)
                if total > max_chars:
                    return 4
                chunks.append(text)
        atomic_write_text(destination, "\n\n".join(chunks))
        return 0
    except Exception:
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
