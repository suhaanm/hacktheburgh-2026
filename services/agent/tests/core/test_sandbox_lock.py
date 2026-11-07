"""The shared sandbox lock: exclusive across processes, reentrant inside one, released when a process dies."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from understudy_agent.sandbox_sites.lock import SandboxBusy, acquire, lock_path, read_owner, release, sandbox_lock

HOLDER = r"""
import sys, time
from understudy_agent.sandbox_sites.lock import sandbox_lock
with sandbox_lock(sys.argv[1]):
    print("held", flush=True)
    time.sleep(60)
"""


def spawn_holder(owner: str, tmp_path) -> subprocess.Popen:
    env = dict(os.environ, UNDERSTUDY_DATA_DIR=str(tmp_path / "data"))
    p = subprocess.Popen([sys.executable, "-c", HOLDER, owner], env=env, stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_two_processes_exclude_each_other_and_the_error_names_the_owner(tmp_path):
    p = spawn_holder("study-sim", tmp_path)
    try:
        t0 = time.monotonic()
        with pytest.raises(SandboxBusy) as e:
            acquire("c4-live", timeout_s=0.4)
        assert 0.35 <= time.monotonic() - t0 < 2.0
        assert "study-sim" in str(e.value) and f"pid {p.pid}" in str(e.value)
        assert read_owner()["owner"] == "study-sim"
    finally:
        p.kill()
        p.wait()


def test_the_lock_is_released_when_the_holder_process_dies(tmp_path):
    p = spawn_holder("crashy", tmp_path)
    with pytest.raises(SandboxBusy):
        acquire("me", timeout_s=0.2)
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    with sandbox_lock("me", timeout_s=3):  # the kernel released it; no stale lock
        assert read_owner()["owner"] == "me" and read_owner()["pid"] == os.getpid()
    assert read_owner() is None


def test_a_waiting_process_gets_the_lock_when_the_holder_leaves(tmp_path):
    p = spawn_holder("first", tmp_path)
    got = {}

    def waiter():
        t0 = time.monotonic()
        with sandbox_lock("second", timeout_s=10):
            got["after"] = time.monotonic() - t0

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.5)
    assert "after" not in got
    p.kill()
    p.wait()
    t.join(10)
    assert "after" in got and got["after"] < 5


def test_reentrant_for_the_same_owner_and_blocking_for_another_in_the_same_process(tmp_path):
    with sandbox_lock("a", timeout_s=1):
        with sandbox_lock("a", timeout_s=1):              # same owner: reentrant
            assert read_owner()["owner"] == "a"
        assert read_owner()["owner"] == "a"               # still held after the inner exit
        with pytest.raises(SandboxBusy, match="'a'"):
            acquire("b", timeout_s=0.2)                   # a different owner in this process waits, then times out
    assert read_owner() is None and lock_path().exists()
    with sandbox_lock("b", timeout_s=1):
        pass


def test_release_by_a_non_holder_is_an_error(tmp_path):
    with sandbox_lock("a"):
        with pytest.raises(RuntimeError, match="does not hold"):
            release("someone-else")
    release("a")  # releasing when nothing is held is harmless
