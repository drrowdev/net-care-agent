"""Serialization of profile-mutating work (architecture-review P6).

All patient state is one JSON file. A mutating job does load -> mutate in memory
-> save, with no read-modify-write lock spanning that window. Two concurrent
mutating jobs (e.g. a document feed and a digest, each a ~2-minute LLM pipeline)
can therefore both load, both mutate, and both save — last writer wins, silently
discarding one job's extracted clinical data. That is the worst failure class
this system has.

This module provides ONE in-process mutating slot. Mutating jobs run through it
serially (FIFO-ish via a simple lock); read-only work (deep_sweep, chat) bypasses
it entirely. Correct because the app runs a single gunicorn worker with daemon
threads — one process, so an in-process lock covers every writer. If the app is
ever scaled to multiple workers this guarantee breaks (see INVARIANTS.md): the
lock would need to move to a file lock on the Azure Files mount.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import contextmanager

# The single mutating slot. Module-level so every importer shares one lock.
mutating_lock = threading.Lock()


@contextmanager
def serialized_mutation(on_wait: Callable[[], None] | None = None):
    """Run a profile-mutating critical section under the single mutating slot.

    If the slot is already held, ``on_wait`` (if given) is invoked once so the
    caller can surface a "waiting for current job" status before blocking.
    """
    if on_wait is not None and mutating_lock.locked():
        try:
            on_wait()
        except Exception:  # a status callback must never break the pipeline
            pass
    mutating_lock.acquire()
    try:
        yield
    finally:
        mutating_lock.release()
