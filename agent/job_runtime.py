"""Bounded in-process job execution and PHI-safe artifact helpers."""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from threading import Thread

from .io import atomic_write_text

log = logging.getLogger(__name__)


class SaturatedError(RuntimeError):
    """Raised when an executor has no active or queued capacity."""


class BoundedExecutor:
    """Small fixed worker pool with a hard active+queued admission bound."""

    def __init__(self, *, workers: int, queue_size: int, name: str):
        self.workers = max(1, min(workers, 4))
        self.queue_size = max(0, min(queue_size, 50))
        self._queue: queue.Queue = queue.Queue()
        self._slots = threading.BoundedSemaphore(self.workers + self.queue_size)
        self._stopping = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._active = 0
        self._lock = threading.Lock()
        self._threads = [
            Thread(target=self._worker, name=f"{name}-{i}", daemon=True)
            for i in range(self.workers)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, func: Callable, *args, **kwargs) -> None:
        with self._lifecycle_lock:
            if self._stopping.is_set():
                raise SaturatedError("executor stopping")
            if not self._slots.acquire(blocking=False):
                raise SaturatedError("executor saturated")
            self._queue.put_nowait((func, args, kwargs))

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            func, args, kwargs = item
            with self._lock:
                self._active += 1
            try:
                func(*args, **kwargs)
            except Exception as exc:
                log.warning("executor_task_failed type=%s", type(exc).__name__)
            finally:
                with self._lock:
                    self._active -= 1
                self._slots.release()
                self._queue.task_done()

    def counts(self) -> tuple[int, int]:
        with self._lock:
            active = self._active
        return active, self._queue.qsize()

    def shutdown(self, wait: bool = True) -> None:
        with self._lifecycle_lock:
            if self._stopping.is_set():
                return
            self._stopping.set()
            for _ in self._threads:
                self._queue.put(None, timeout=1)
        if wait:
            for thread in self._threads:
                thread.join(timeout=5)


def write_json_artifact(path: Path, value: object) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def safe_artifact_path(data_dir: Path, reference: str, roots: set[str]) -> Path:
    root = data_dir.resolve()
    candidate = (data_dir / reference).resolve()
    relative = candidate.relative_to(root)
    if not relative.parts or relative.parts[0] not in roots:
        raise ValueError("Artifact reference is outside an allowed root")
    return candidate


def extract_pdf_subprocess(
    input_path: Path,
    output_path: Path,
    *,
    timeout_seconds: int,
    max_pages: int,
    max_chars: int,
) -> str:
    """Extract PDF text in a child interpreter with strict output and time limits."""
    command = [
        sys.executable,
        "-m",
        "agent.pdf_extract_helper",
        str(input_path),
        str(output_path),
        str(max_pages),
        str(max_chars),
        str(timeout_seconds),
        os.environ.get("PDF_MAX_MEMORY_MB", "384"),
    ]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
        "PYTHONIOENCODING": "utf-8",
    }
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("pdf_timeout") from exc
    if completed.returncode != 0 or not output_path.is_file():
        raise RuntimeError("pdf_invalid")
    raw = output_path.read_bytes()
    if len(raw) > max_chars * 4 + 4:
        raise RuntimeError("pdf_text_limit")
    text = raw.decode("utf-8")
    if len(text) > max_chars:
        raise RuntimeError("pdf_text_limit")
    return text


def prune_orphan_sources(
    data_dir: Path, protected_ids: set[str], *, age_days: int, max_count: int
) -> None:
    root = data_dir / "source_documents"
    if not root.is_dir():
        return
    import time

    candidates = [
        path for path in root.iterdir() if path.is_dir() and path.name not in protected_ids
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    cutoff = time.time() - max(1, age_days) * 86400
    for index, path in enumerate(candidates):
        try:
            if index >= max(0, max_count) or path.stat().st_mtime < cutoff:
                shutil.rmtree(path)
        except OSError:
            continue
