"""One exclusive lock for the shared sandbox sites on ports 7801 to 7803 (several agents reset and read their state).

    with sandbox_lock("study-sim", timeout_s=120):
        ...reset, run, read /__state...

* `fcntl.flock` on <data dir>/locks/sandbox.lock (UNDERSTUDY_DATA_DIR honoured): released by the kernel if the
  process dies, so a crashed run can never leave the sites locked.
* A sibling `sandbox.lock.owner` file holds {owner, pid, since} for diagnostics; a timeout error names the owner.
* Reentrant inside one process for the same owner name (a depth counter); a different owner in the same process
  waits like any other process.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..supervisor import data_dir


class SandboxBusy(TimeoutError):
    """Could not take the sandbox lock in time. The message names the current owner."""


def lock_path() -> Path:
    return data_dir() / "locks" / "sandbox.lock"


def _owner_path(p: Path) -> Path:
    return p.with_name(p.name + ".owner")


def read_owner() -> dict | None:
    try:
        return json.loads(_owner_path(lock_path()).read_text())
    except (OSError, ValueError):
        return None


class _State:
    cond = threading.Condition()
    depth = 0
    owner: str | None = None
    fd: int | None = None
    path: Path | None = None


def acquire(owner: str, timeout_s: float | None = None, poll_s: float = 0.05) -> None:
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    st = _State
    with st.cond:
        while True:
            if st.depth > 0 and st.owner == owner:       # reentrant for the same owner in this process
                st.depth += 1
                return
            if st.depth == 0:
                p = lock_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(fd)
                else:
                    st.fd, st.owner, st.depth, st.path = fd, owner, 1, p
                    tmp = _owner_path(p).with_suffix(".tmp")
                    tmp.write_text(json.dumps({"owner": owner, "pid": os.getpid(), "since": time.time()}))
                    os.replace(tmp, _owner_path(p))
                    return
            if deadline is not None and time.monotonic() >= deadline:
                cur = read_owner() if st.depth == 0 else {"owner": st.owner, "pid": os.getpid()}
                who = (f"{cur['owner']!r} (pid {cur['pid']})" if cur else "another process")
                raise SandboxBusy(f"the sandbox sites are in use by {who}; waited {timeout_s:g}s")
            st.cond.wait(timeout=poll_s)


def release(owner: str | None = None) -> None:
    st = _State
    with st.cond:
        if st.depth == 0:
            return
        if owner is not None and owner != st.owner:
            raise RuntimeError(f"{owner!r} does not hold the sandbox lock; {st.owner!r} does")
        st.depth -= 1
        if st.depth == 0:
            try:
                if st.path is not None:
                    _owner_path(st.path).unlink(missing_ok=True)
            finally:
                if st.fd is not None:
                    fcntl.flock(st.fd, fcntl.LOCK_UN)
                    os.close(st.fd)
                st.fd, st.owner, st.path = None, None, None
        st.cond.notify_all()


@contextmanager
def sandbox_lock(owner: str, timeout_s: float | None = None) -> Iterator[None]:
    acquire(owner, timeout_s)
    try:
        yield
    finally:
        release(owner)
