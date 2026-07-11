"""Serialization of profile-mutating work (architecture-review P6).

All patient state is one JSON file. A mutating job does load -> mutate in memory
-> save, with no read-modify-write lock spanning that window. Two concurrent
mutating jobs (e.g. a document feed and a digest, each a ~2-minute LLM pipeline)
can therefore both load, both mutate, and both save — last writer wins, silently
discarding one job's extracted clinical data. That is the worst failure class
this system has.

This module provides one re-entrant in-process slot plus an advisory
cross-process file lock on the shared data mount. The file lock matters even
with one gunicorn worker: CLI maintenance commands and deployment overlap run
in separate processes and must not overwrite a web transaction.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from . import config

# The single mutating slot. It is re-entrant so a complete outer transaction may
# safely call a helper that also participates in mutation serialization.
mutating_lock = threading.RLock()
_thread_state = threading.local()


def _lock_path() -> Path:
    return config.DATA_DIR / ".profile-mutation.lock"


def _try_process_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _acquire_process_lock(on_wait: Callable[[], None] | None) -> BinaryIO:
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"\0")
        handle.flush()
    if _try_process_lock(handle):
        return handle

    if on_wait is not None:
        try:
            on_wait()
        except Exception:
            pass

    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _release_process_lock(handle: BinaryIO) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def serialized_mutation(on_wait: Callable[[], None] | None = None):
    """Run a profile-mutating critical section under the single mutating slot.

    If the slot is already held, ``on_wait`` (if given) is invoked once so the
    caller can surface a "waiting for current job" status before blocking.
    """
    acquired_thread = mutating_lock.acquire(blocking=False)
    if not acquired_thread and on_wait is not None:
        try:
            on_wait()
        except Exception:  # a status callback must never break the pipeline
            pass
    if not acquired_thread:
        mutating_lock.acquire()

    depth = getattr(_thread_state, "depth", 0)
    process_handle = None
    try:
        if depth == 0:
            process_handle = _acquire_process_lock(on_wait if acquired_thread else None)
            _thread_state.process_handle = process_handle
        _thread_state.depth = depth + 1
        yield
    finally:
        next_depth = getattr(_thread_state, "depth", 1) - 1
        _thread_state.depth = next_depth
        if next_depth == 0:
            handle = getattr(_thread_state, "process_handle", process_handle)
            if handle is not None:
                _release_process_lock(handle)
            if hasattr(_thread_state, "process_handle"):
                del _thread_state.process_handle
        mutating_lock.release()
