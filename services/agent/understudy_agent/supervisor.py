"""Supervisor (AGT-2): one worker, one replaceable pending request, monotonically increasing generation,
cancel events, deadlines, a watchdog, and a file kill flag.

Written from the pattern described in docs/reference-notes/vision-os.md (no code copied).

Guarantees
- `stop()` is synchronous and never calls a model or waits for the running task. It returns in
  microseconds; the running task sees `ctx.is_current() == False` and the generation has moved on,
  so whatever it returns later is dropped (a "stale result").
- Submitting a new task replaces any pending one and cancels the running one.
- A task that ignores cancellation does not block the next task: after `abandon_grace_s` the watchdog
  abandons that worker thread (daemon; its result is dropped) and starts a fresh worker.
- Deadlines are per task. The watchdog cancels overdue tasks.
- The file `data/KILL` (path from `UNDERSTUDY_DATA_DIR`, default `<repo>/data`) is polled by the
  watchdog and checked by `ctx.is_current()`; while it exists nothing runs and `submit()` refuses.
- Human input can be signalled (`HumanInputSignal`); tasks submitted with `yield_on_human=True` are
  cancelled with state `yielded` inside the watchdog interval (HND-5).
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ----------------------------------------------------------------------------- paths


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    """Shared data directory (queue, audit, KILL, runs, golden). Env override for tests."""
    env = os.environ.get("UNDERSTUDY_DATA_DIR")
    return Path(env) if env else repo_root() / "data"


def kill_flag_path() -> Path:
    return data_dir() / "KILL"


# ----------------------------------------------------------------------------- exceptions


class Cancelled(Exception):
    """Raised inside a task by `ctx.check()` when the task is no longer current."""


class KillSwitchActive(RuntimeError):
    """Raised by `submit()` while the kill flag exists."""


# ----------------------------------------------------------------------------- human input


class HumanInputSignal:
    """Thread-safe 'the human touched the machine' signal.

    The desktop app or engine (or a test) calls `signal()`. Background tasks submitted with
    `yield_on_human=True` are cancelled within one watchdog tick. `quiet_for(s)` says whether at least
    `s` seconds passed since the last input, so a resume can wait for the human to leave again.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._last: float | None = None
        self._seq = 0

    def signal(self) -> None:
        with self._lock:
            self._last = self._clock()
            self._seq += 1

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def quiet_for(self, seconds: float) -> bool:
        with self._lock:
            return self._last is None or (self._clock() - self._last) >= seconds


# ----------------------------------------------------------------------------- task plumbing

TERMINAL = {"done", "failed", "stopped", "timeout", "superseded", "yielded", "killed"}


class TaskHandle:
    """What `submit()` returns. Resolved exactly once (first resolution wins)."""

    def __init__(self, run_id: str, generation: int) -> None:
        self.run_id = run_id
        self.generation = generation
        self.state = "queued"  # queued | running | <terminal>
        self.result: Any = None
        self.error: BaseException | None = None
        self.reason: str = ""
        self.stale_results_dropped = 0
        self._done = threading.Event()
        self._lock = threading.Lock()

    def _resolve(self, state: str, *, result: Any = None, error: BaseException | None = None,
                 reason: str = "") -> bool:
        with self._lock:
            if self._done.is_set():
                return False
            self.state, self.result, self.error, self.reason = state, result, error, reason
            self._done.set()
            return True

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)


class TaskContext:
    def __init__(self, sup: "Supervisor", run_id: str, generation: int, deadline: float | None,
                 yield_on_human: bool) -> None:
        self._sup = sup
        self.run_id = run_id
        self.generation = generation
        self.deadline = deadline  # monotonic seconds, or None
        self.yield_on_human = yield_on_human
        self.cancelled = threading.Event()
        self.cancel_reason = ""
        self.checkpoints: list[dict[str, Any]] = []

    def is_current(self) -> bool:
        return (not self.cancelled.is_set() and self._sup._generation == self.generation
                and not self._sup.kill_flag_set())

    def check(self) -> None:
        if not self.is_current():
            raise Cancelled(self.cancel_reason or "not current")

    def remaining(self) -> float | None:
        return None if self.deadline is None else max(0.0, self.deadline - self._sup._clock())

    def sleep(self, seconds: float) -> bool:
        """Cancellable sleep. Returns True if it slept the full time, False if cancelled."""
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return True
            if self.cancelled.wait(min(left, 0.05)) or not self.is_current():
                return False

    def checkpoint(self, data: dict[str, Any]) -> None:
        """Record resumable progress (off-hours runs, yield and resume)."""
        self.checkpoints.append({"t": time.time(), **data})

    def emit(self, kind: str, **details: Any) -> None:
        self._sup._event(kind, run_id=self.run_id, generation=self.generation, **details)


@dataclass
class _Task:
    fn: Callable[[TaskContext], Any]
    ctx: TaskContext
    handle: TaskHandle
    name: str
    started_at: float | None = None
    cancelled_at: float | None = None
    worker_epoch: int = 0


class Supervisor:
    def __init__(
        self,
        *,
        kill_flag: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        watchdog_interval_s: float = 0.05,
        abandon_grace_s: float = 1.0,
        human_input: HumanInputSignal | None = None,
        kill_poll_interval_s: float = 0.05,
    ) -> None:
        self._kill_flag = kill_flag
        self._clock = clock
        self._interval = watchdog_interval_s
        self._grace = abandon_grace_s
        self.human_input = human_input
        self._kill_poll = kill_poll_interval_s
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._generation = 0
        self._pending: _Task | None = None
        self._current: _Task | None = None
        self._state = "idle"
        self._closed = False
        self._epoch = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=512)
        self._stop_hooks: list[Callable[[], None]] = []
        self._human_seen = human_input.seq if human_input else 0
        self._kill_cache: tuple[float, bool] = (0.0, False)
        self.stale_results_dropped = 0
        self._spawn_worker()
        self._watchdog = threading.Thread(target=self._watch, daemon=True, name="supervisor-watchdog")
        self._watchdog.start()

    # ----- kill flag
    @property
    def kill_flag(self) -> Path:
        return self._kill_flag or kill_flag_path()

    def kill_flag_set(self) -> bool:
        now = time.monotonic()
        last_t, last_v = self._kill_cache
        if now - last_t < self._kill_poll:
            return last_v
        try:
            v = self.kill_flag.exists()
        except OSError:
            v = False
        self._kill_cache = (now, v)
        return v

    # ----- events
    def _event(self, kind: str, **details: Any) -> None:
        self._events.append({"t": time.time(), "kind": kind, "generation": self._generation, **details})

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def add_stop_hook(self, fn: Callable[[], None]) -> None:
        """Hooks run on stop/kill/timeout in a background thread; they must not call a model."""
        self._stop_hooks.append(fn)

    # ----- workers
    def _spawn_worker(self) -> None:
        with self._lock:
            self._epoch += 1
            epoch = self._epoch
        t = threading.Thread(target=self._work, args=(epoch,), daemon=True, name=f"supervisor-worker-{epoch}")
        t.start()

    def _work(self, epoch: int) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._closed and epoch == self._epoch:
                    self._cond.wait(timeout=0.25)
                if self._closed or epoch != self._epoch:
                    return
                task = self._pending
                self._pending = None
                assert task is not None
                if task.ctx.cancelled.is_set() or task.ctx.generation != self._generation:
                    task.handle._resolve("superseded", reason="replaced before start")
                    continue
                self._current = task
                task.worker_epoch = epoch
                task.started_at = self._clock()
                task.handle.state = "running"
                self._state = "running"
                self._event("started", run_id=task.ctx.run_id, name=task.name)
            result: Any = None
            error: BaseException | None = None
            try:
                result = task.fn(task.ctx)
            except Cancelled:
                error = None
                result = None
            except BaseException as exc:  # noqa: BLE001 - task errors are data, not crashes
                error = exc
            self._finish(task, result, error, epoch)

    def _finish(self, task: _Task, result: Any, error: BaseException | None, epoch: int) -> None:
        with self._cond:
            current_ok = (task.ctx.generation == self._generation and not task.ctx.cancelled.is_set()
                          and not self.kill_flag_set())
            if current_ok:
                if error is not None:
                    task.handle._resolve("failed", error=error, reason=repr(error)[:200])
                    self._state = "failed"
                else:
                    task.handle._resolve("done", result=result)
                    self._state = "idle"
                self._event("finished", run_id=task.ctx.run_id, state=task.handle.state)
            else:
                # Stale: the generation moved on or the task was cancelled. Drop the result.
                task.handle.stale_results_dropped += 1
                self.stale_results_dropped += 1
                self._event("stale_result_dropped", run_id=task.ctx.run_id, task_generation=task.ctx.generation)
                task.handle._resolve("stopped", reason=task.ctx.cancel_reason or "stale")
            if self._current is task and epoch == self._epoch:
                self._current = None
            self._cond.notify_all()

    # ----- public API
    def submit(self, fn: Callable[[TaskContext], Any], *, name: str = "task", run_id: str | None = None,
               deadline_s: float | None = None, yield_on_human: bool = False) -> TaskHandle:
        if self.kill_flag_set():
            raise KillSwitchActive(f"kill flag present at {self.kill_flag}")
        with self._cond:
            if self._closed:
                raise RuntimeError("supervisor closed")
            old_pending = self._pending
            if self._current is not None:
                self._cancel_task(self._current, "superseded by a new request", "superseded")
            if old_pending is not None:
                old_pending.ctx.cancelled.set()
                old_pending.handle._resolve("superseded", reason="replaced by a newer request")
            self._generation += 1
            gen = self._generation
            rid = run_id or "r_" + uuid.uuid4().hex[:8]
            deadline = self._clock() + deadline_s if deadline_s is not None else None
            ctx = TaskContext(self, rid, gen, deadline, yield_on_human)
            handle = TaskHandle(rid, gen)
            self._pending = _Task(fn=fn, ctx=ctx, handle=handle, name=name)
            self._state = "queued"
            self._event("submitted", run_id=rid, name=name)
            self._cond.notify_all()
        return handle

    def _cancel_task(self, task: _Task, reason: str, state: str) -> None:
        """Caller holds the lock."""
        if task.ctx.cancelled.is_set():
            return
        task.ctx.cancel_reason = reason
        task.ctx.cancelled.set()
        task.cancelled_at = self._clock()
        task.handle._resolve(state, reason=reason)

    def stop(self, reason: str = "stopped by user", *, _state: str = "stopped") -> dict[str, Any]:
        """Synchronous, model-free. Bumps the generation so every in-flight result is stale."""
        with self._cond:
            if self._current is not None:
                self._cancel_task(self._current, reason, _state)
            if self._pending is not None:
                self._pending.ctx.cancelled.set()
                self._pending.handle._resolve(_state, reason=reason)
                self._pending = None
            self._generation += 1
            self._state = "stopped" if _state != "killed" else "killed"
            gen = self._generation
            self._event("stop", reason=reason[:160], state=_state)
            self._cond.notify_all()
        self._run_hooks()
        return {"stopped": True, "generation": gen}

    def kill(self, reason: str = "kill switch") -> dict[str, Any]:
        """Global stop. Does not itself write the flag file; the server and engine do."""
        out = self.stop(reason, _state="killed")
        return {"killed": True, **out}

    def yield_to_human(self, reason: str = "human input") -> dict[str, Any]:
        out = self.stop(reason, _state="yielded")
        self._state = "yielded"
        return out

    def _run_hooks(self) -> None:
        hooks = list(self._stop_hooks)
        if not hooks:
            return

        def run() -> None:
            for h in hooks:
                try:
                    h()
                except Exception:  # noqa: BLE001
                    pass

        threading.Thread(target=run, daemon=True, name="supervisor-stop-hooks").start()

    # ----- status
    @property
    def generation(self) -> int:
        return self._generation

    @property
    def state(self) -> str:
        if self.kill_flag_set():
            return "killed"
        return self._state

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            cur = self._current
            return {
                "generation": self._generation,
                "state": self.state,
                "run_id": cur.ctx.run_id if cur else None,
                "pending": self._pending is not None,
                "stale_results_dropped": self.stale_results_dropped,
            }

    # ----- watchdog
    def _watch(self) -> None:
        while not self._closed:
            time.sleep(self._interval)
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - the watchdog must never die
                pass

    def _tick(self) -> None:
        # 1. file kill flag
        if self.kill_flag_set():
            with self._lock:
                active = self._current is not None and not self._current.ctx.cancelled.is_set()
                active = active or self._pending is not None
            if active:
                self.stop("kill flag present", _state="killed")
        # 2. human input -> yield
        if self.human_input is not None:
            seq = self.human_input.seq
            if seq != self._human_seen:
                self._human_seen = seq
                with self._lock:
                    cur = self._current
                    should = cur is not None and cur.ctx.yield_on_human and not cur.ctx.cancelled.is_set()
                if should:
                    self.yield_to_human("human input signalled")
        # 3. deadlines and abandoned workers
        now = self._clock()
        with self._cond:
            cur = self._current
            if cur is not None:
                if (cur.ctx.deadline is not None and now >= cur.ctx.deadline
                        and not cur.ctx.cancelled.is_set()):
                    self._cancel_task(cur, "deadline exceeded", "timeout")
                    self._generation += 1
                    self._state = "timeout"
                    self._event("timeout", run_id=cur.ctx.run_id)
                    self._cond.notify_all()
                    self._run_hooks()
                if (cur.ctx.cancelled.is_set() and cur.cancelled_at is not None
                        and now - cur.cancelled_at >= self._grace):
                    # The task ignored cancellation. Leave it running, drop its result, start a new worker.
                    self._current = None
                    self._event("worker_abandoned", run_id=cur.ctx.run_id)
                    self._spawn_worker()
                    self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            if self._current is not None:
                self._cancel_task(self._current, "supervisor closed", "stopped")
            if self._pending is not None:
                self._pending.handle._resolve("stopped", reason="supervisor closed")
                self._pending = None
            self._cond.notify_all()
