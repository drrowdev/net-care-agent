"""Tests for P6 mutating-job serialization and P12 pre-save snapshots."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time


# ── P6: serialized_mutation ──────────────────────────────────────────────────
def test_serialized_mutation_serializes_concurrent_sections(agent):
    from agent.serialize import serialized_mutation

    active = {"count": 0, "max": 0}
    lock = threading.Lock()

    def worker():
        with serialized_mutation():
            with lock:
                active["count"] += 1
                active["max"] = max(active["max"], active["count"])
            time.sleep(0.05)
            with lock:
                active["count"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # If the slot serializes, no two critical sections are ever active at once.
    assert active["max"] == 1


def test_serialized_mutation_calls_on_wait_when_held(agent):
    from agent.serialize import mutating_lock, serialized_mutation

    waited = {"n": 0}
    mutating_lock.acquire()  # simulate a job already holding the slot
    try:
        t = threading.Thread(
            target=lambda: _enter_and_exit(
                serialized_mutation, lambda: waited.__setitem__("n", waited["n"] + 1)
            )
        )
        t.start()
        time.sleep(0.05)  # let it reach the wait
        assert waited["n"] == 1  # on_wait fired because the slot was held
    finally:
        mutating_lock.release()
        t.join()


def _enter_and_exit(cm_factory, on_wait):
    with cm_factory(on_wait=on_wait):
        pass


def _hold_process_lock(data_dir: str, ready, release) -> None:
    os.environ["DATA_DIR"] = data_dir
    from agent.serialize import serialized_mutation

    with serialized_mutation():
        ready.set()
        release.wait(5)


def test_serialized_mutation_blocks_another_process(agent):
    from agent import config
    from agent.serialize import serialized_mutation

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    process = ctx.Process(
        target=_hold_process_lock,
        args=(str(config.DATA_DIR), ready, release),
    )
    process.start()
    assert ready.wait(5)

    entered = threading.Event()

    def enter_parent():
        with serialized_mutation():
            entered.set()

    thread = threading.Thread(target=enter_parent)
    thread.start()
    time.sleep(0.1)
    assert not entered.is_set()

    release.set()
    process.join(5)
    thread.join(5)
    assert process.exitcode == 0
    assert entered.is_set()


# ── P12: rotating_snapshot ───────────────────────────────────────────────────
def test_rotating_snapshot_captures_and_prunes(agent, monkeypatch):
    from agent import backups, config

    monkeypatch.setattr(backups, "PRESAVE_SNAPSHOT_COUNT", 3)
    config.PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    for i in range(5):
        config.PROFILE_PATH.write_text(f'{{"v": {i}}}', encoding="utf-8")
        snap = backups.rotating_snapshot(config.PROFILE_PATH)
        assert snap is not None and snap.exists()
        time.sleep(0.005)  # ensure distinct microsecond timestamps

    snaps = sorted((config.DATA_DIR / "snapshots").glob("profile_*.json"))
    assert len(snaps) == 3  # pruned to the most recent N


def test_rotating_snapshot_no_source_is_noop(agent, tmp_path, monkeypatch):
    from agent import backups

    missing = tmp_path / "does_not_exist.json"
    assert backups.rotating_snapshot(missing) is None


def test_save_profile_writes_presave_snapshot(agent, empty_profile):
    from agent import config, save_profile

    save_profile(empty_profile)  # creates the file (no prior state to snapshot)
    empty_profile["patient"]["diagnosis"] = "changed"
    save_profile(empty_profile)  # now the prior state should be snapshotted
    snaps = list((config.DATA_DIR / "snapshots").glob("profile_*.json"))
    assert len(snaps) >= 1
