"""Off-hours runs (OFF-1 to OFF-7, D8): run an unattended routine while the worker is away, and get out of the way
the moment they return.

    decide   poll the engine's /offhours/decide (the start-or-wait rule S(D|t) > L/(G+L)) with the real screen state
    refuse   when the screen is locked or asleep, when consent does not allow an unattended run, when the kill flag is
             set, or when the engine says wait; the refusal reason is written to the audit log and returned
    run      keep-awake only while the run is active (`caffeinate`), the run is the background workflow in its own
             browser context under the supervisor with a time budget; steps are checkpointed
    yield    a presence watcher turns "the worker touched the machine" into a human-input signal; the supervisor
             cancels the run inside the watchdog interval, well under one second
    report   the morning report is read from the audit log (and the approval queue)

Screen state is an interface (`ScreenState`). `FakeScreenState` drives tests and the simulated-clock demo.
`QuartzScreenState` reads the real session and needs pyobjc; without it the runner refuses to start (fails closed).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .audit import AuditLog
from .handoff_io import EngineClient, EngineError, consent_allows, read_consent
from .models.port import ModelPort
from .queue import ApprovalQueue
from .sandbox_sites.households import Household
from .security.killflag import is_killed
from .shadow import BackgroundRunner, ConsentRefused
from .supervisor import HumanInputSignal, Supervisor, TaskHandle

REASONS = {
    "consent": "The routine is not switched on for runs while you are away.",
    "kill": "The kill switch is set.",
    "screen_locked": "The screen is locked, so I did not start.",
    "screen_asleep": "The screen is asleep, so I did not start.",
    "screen_unknown": "I cannot read the screen state, so I did not start.",
    "engine_wait": "The window is probably too short to finish a run, so I waited.",
    "engine_unreachable": "The presence service is not reachable, so I did not start.",
    "already_running": "A run is already in progress.",
}


# ----------------------------------------------------------------------------- screen state
class ScreenState(Protocol):
    def locked(self) -> bool: ...
    def asleep(self) -> bool: ...
    def idle_seconds(self) -> float: ...


class ScreenStateUnavailable(RuntimeError):
    pass


@dataclass
class FakeScreenState:
    """Settable screen state for tests and the simulated-clock demo."""

    is_locked: bool = False
    is_asleep: bool = False
    idle: float = 600.0

    def locked(self) -> bool: return self.is_locked
    def asleep(self) -> bool: return self.is_asleep
    def idle_seconds(self) -> float: return self.idle


class QuartzScreenState:
    """The real session. Lock state and sleep from Quartz; idle time from the HID event source. Needs pyobjc."""

    def __init__(self) -> None:
        try:
            import Quartz  # noqa: F401
        except ImportError as exc:
            raise ScreenStateUnavailable("pyobjc-framework-Quartz is not installed") from exc

    def locked(self) -> bool:  # pragma: no cover - real session
        import Quartz

        return bool((Quartz.CGSessionCopyCurrentDictionary() or {}).get("CGSSessionScreenIsLocked", 0))

    def asleep(self) -> bool:  # pragma: no cover - real session
        import Quartz

        return bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))

    def idle_seconds(self) -> float:  # pragma: no cover - real session
        import Quartz

        return float(Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, 0xFFFFFFFF))


def default_screen_state() -> ScreenState | None:
    try:
        return QuartzScreenState()
    except ScreenStateUnavailable:
        return None


# ----------------------------------------------------------------------------- keep-awake
class KeepAwake:
    """`caffeinate` held only while a run is active; it also exits if this process dies (-w)."""

    def __init__(self, popen: Callable[..., Any] = subprocess.Popen) -> None:
        self._popen = popen
        self._proc: Any = None
        self.starts = 0

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.active:
            return
        self._proc = self._popen(["caffeinate", "-dis", "-w", str(os.getpid())], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        self.starts += 1

    def stop(self) -> None:
        p, self._proc = self._proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except Exception:  # noqa: BLE001
                p.kill()


# ----------------------------------------------------------------------------- presence watcher
class PresenceWatcher(threading.Thread):
    """Turns 'the worker is back' into a human-input signal. It polls every `poll_s` (0.2 s), so a return is seen
    well inside one second. Input the AGENT produced itself (a desktop actuator) is ignored via `own_activity`."""

    def __init__(self, screen: ScreenState, human: HumanInputSignal, *, poll_s: float = 0.2, return_idle_s: float = 2.0,
                 own_activity: Callable[[], float | None] = lambda: None) -> None:
        super().__init__(daemon=True, name="presence-watcher")
        self.screen, self.human, self.poll_s, self.return_idle_s = screen, human, poll_s, return_idle_s
        self.own_activity = own_activity
        self._halt = threading.Event()
        self.signalled_at: float | None = None

    def run(self) -> None:
        last = self.screen.idle_seconds()
        while not self._halt.wait(self.poll_s):
            try:
                idle = self.screen.idle_seconds()
            except Exception:  # noqa: BLE001 - an unreadable screen is treated as a reason to yield
                idle = 0.0
            own = self.own_activity()
            mine = own is not None and (time.monotonic() - own) < 0.5
            if (idle < last - 0.25 or idle < self.return_idle_s) and not mine:
                self.signalled_at = time.monotonic()
                self.human.signal()
            last = idle

    def stop(self) -> None:
        self._halt.set()


# ----------------------------------------------------------------------------- the runner
@dataclass
class StartResult:
    started: bool
    code: str
    reason: str
    decision: dict[str, Any] | None = None
    handle: TaskHandle | None = None
    run_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"started": self.started, "code": self.code, "reason": self.reason, "decision": self.decision,
                "run_id": self.run_id}


class OffHoursRunner:
    def __init__(self, routine_id: str, *, engine: EngineClient, screen: ScreenState | None, keepawake: KeepAwake,
                 background: BackgroundRunner, human: HumanInputSignal, audit: AuditLog, supervisor: Supervisor,
                 root: Any = None, time_budget_s: float = 600.0, poll_s: float = 0.2,
                 own_activity: Callable[[], float | None] = lambda: None) -> None:
        self.routine_id, self.engine, self.screen, self.keepawake = routine_id, engine, screen, keepawake
        self.background, self.human, self.audit, self.sup = background, human, audit, supervisor
        self.root, self.time_budget_s, self.poll_s, self.own_activity = root, time_budget_s, poll_s, own_activity
        self._watcher: PresenceWatcher | None = None
        self._finalizer: threading.Thread | None = None
        self.last: StartResult | None = None

    def _refuse(self, code: str, decision: dict[str, Any] | None = None) -> StartResult:
        self.audit.append("agent", "offhours", routine=self.routine_id, outcome="refused", note_code=code)
        self.last = StartResult(False, code, REASONS[code], decision)
        return self.last

    def tick(self, household: Household | dict[str, Any], *, person: str, d_min: float, gain: float, loss: float,
             now: str | None = None, run_id: str | None = None, query: dict[str, str] | None = None) -> StartResult:
        """One poll: decide, and start a checkpointed unattended run only if everything allows it."""
        if self._finalizer is not None and self._finalizer.is_alive():
            return self._refuse("already_running")
        # 1. things that never depend on the engine
        ok, _ = consent_allows(read_consent(self.routine_id, self.root), "unattended")
        if not ok:
            return self._refuse("consent")
        if is_killed():
            return self._refuse("kill")
        if self.screen is None:
            return self._refuse("screen_unknown")
        try:
            locked, asleep = self.screen.locked(), self.screen.asleep()
        except Exception:  # noqa: BLE001
            return self._refuse("screen_unknown")
        if asleep:
            return self._refuse("screen_asleep")
        if locked:
            return self._refuse("screen_locked")
        # 2. the start-or-wait rule, with the real screen state
        try:
            dec = self.engine.offhours_decide(person=person, d_min=d_min, gain=gain, loss=loss,
                                              screen="unlocked", now=now)
        except EngineError:
            return self._refuse("engine_unreachable")
        if not dec.get("go"):
            return self._refuse("engine_wait", dec)
        # 3. start: keep-awake only while active, watch for the worker's return, run under the supervisor
        self.keepawake.start()
        self._watcher = PresenceWatcher(self.screen, self.human, poll_s=self.poll_s, own_activity=self.own_activity)
        self._watcher.start()
        t0 = time.time()
        try:
            handle = self.background.start(household, run_id=run_id, query=query, deadline_s=self.time_budget_s)
        except ConsentRefused:
            self._cleanup()
            return self._refuse("consent")
        except Exception:
            self._cleanup()
            raise
        self.audit.append("agent", "offhours", routine=self.routine_id, run_id=handle.run_id, outcome="started",
                          note_code="go", meta={"survival": float(dec.get("survival", 0)), "d_min": d_min})

        def finish() -> None:
            handle.wait()
            self.background.join_after(2.0)   # the `yielded` line is written before the `ended` line
            minutes = round((time.time() - t0) / 60, 3)
            self._cleanup()
            self.audit.append("agent", "offhours", routine=self.routine_id, run_id=handle.run_id, outcome=handle.state,
                              note_code="ended", meta={"minutes": minutes, "tier": _top_tier(self.background.last)})

        self._finalizer = threading.Thread(target=finish, daemon=True, name="offhours-finalizer")
        self._finalizer.start()
        self.last = StartResult(True, "go", "Started: the worker is away and the window is long enough.", dec, handle,
                                handle.run_id)
        return self.last

    def _cleanup(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self.keepawake.stop()

    def join(self, timeout: float = 30.0) -> None:
        if self._finalizer is not None:
            self._finalizer.join(timeout)


def _top_tier(res: dict[str, Any]) -> int | None:
    tiers = [e.get("tier") for e in (res or {}).get("tier_log", []) if isinstance(e.get("tier"), int)]
    return max(tiers) if tiers else None


# ----------------------------------------------------------------------------- morning report
def morning_report(audit: AuditLog, queue: ApprovalQueue | None = None, since: str | None = None) -> dict[str, Any]:
    """OFF-7: what ran, what is queued, what failed, what yielded, what was refused. Built from the redacted audit
    log and the queue; no page text anywhere in it."""
    t0 = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else datetime.fromtimestamp(0, timezone.utc)

    def when(line: dict[str, Any]) -> datetime:
        return datetime.fromisoformat(str(line["t"]).replace("Z", "+00:00"))

    lines = [ln for ln in audit.read(100000) if when(ln) >= t0]
    ended: dict[str, dict[str, Any]] = {}
    tiers: dict[str, int] = {}
    runs_for_routine: dict[str, str | None] = {}
    for ln in lines:
        rid = ln.get("run_id")
        if rid and ln.get("routine"):
            runs_for_routine[rid] = ln["routine"]
        if ln["kind"] == "agent_step" and rid and isinstance(ln.get("tier"), int):
            tiers[rid] = max(tiers.get(rid, 0), ln["tier"])
        if ln["kind"] == "offhours" and ln.get("note") == "ended" and rid:
            ended[rid] = ln
    ran, failed, yielded, refused = [], [], [], []
    starts = {ln["run_id"]: when(ln) for ln in lines if ln["kind"] in ("run_start", "offhours") and ln.get("run_id")}
    # routine runs that were not off-hours runs (an approved background run) are listed from their `run_end` line
    plain_end = {ln["run_id"]: ln for ln in lines
                 if ln["kind"] == "run_end" and ln.get("routine") and ln.get("run_id") and ln["run_id"] not in ended}
    for rid, ln in plain_end.items():
        t_start = starts.get(rid)
        ran.append({"routine": ln["routine"], "run_id": rid, "outcome": ln["outcome"],
                    "minutes": round((when(ln) - t_start).total_seconds() / 60, 3) if t_start else None,
                    "tier": tiers.get(rid)})
        if ln["outcome"] == "failed":
            failed.append({"routine": ln["routine"], "reason": "failed"})
        elif ln["outcome"] == "paused":
            failed.append({"routine": ln["routine"], "reason": "paused: the detector or the gate stopped the run"})
    for rid, ln in ended.items():
        meta = ln.get("meta") or {}
        outcome = ln["outcome"]
        ran.append({"routine": ln.get("routine"), "run_id": rid, "outcome": outcome,
                    "minutes": meta.get("minutes"), "tier": meta.get("tier") or tiers.get(rid)})
        if outcome in ("failed", "timeout"):
            failed.append({"routine": ln.get("routine"), "reason": outcome})
    for ln in lines:
        if ln["kind"] == "yielded":
            yielded.append({"routine": ln.get("routine") or runs_for_routine.get(ln.get("run_id") or ""), "at": ln["t"],
                            "run_id": ln.get("run_id")})
        elif ln["kind"] == "offhours" and ln["outcome"] == "refused":
            refused.append({"routine": ln.get("routine"), "at": ln["t"], "code": ln.get("note"),
                            "reason": REASONS.get(str(ln.get("note")), "refused")})
        elif ln["kind"] == "injection_pause" and ln.get("run_id") in ended:
            failed.append({"routine": ln.get("routine"), "reason": "a page tried to instruct the agent; the run was paused"})
    queued = []
    if queue is not None:
        run_ids = set(ended) | set(plain_end)
        for it in queue.list("all"):
            if it.get("run_id") in run_ids and datetime.fromisoformat(it["created_at"].replace("Z", "+00:00")) >= t0:
                queued.append(it["id"])
    return {"since": since, "ran": ran, "queued": queued, "failed": failed, "yielded": yielded, "refused": refused}


# ----------------------------------------------------------------------------- desktop computer-use runner (OFF-4)
class ScreenGuardedActuator:
    """Wraps any actuator: refuses to act when the screen locks or sleeps or the kill flag appears, and records when
    the AGENT last produced an input event so the presence watcher can tell its own input from the worker's."""

    def __init__(self, inner: Any, screen: ScreenState) -> None:
        self.inner, self.screen = inner, screen
        self.last_own_event: float | None = None

    @property
    def scale(self) -> float:
        return self.inner.scale

    @property
    def url(self) -> Any:
        return getattr(self.inner, "url", None)

    async def read_target(self, action: Any) -> Any:
        """Trusted target reading passes straight through: a wrapper that hid it would leave every click unreadable."""
        reader = getattr(self.inner, "read_target", None)
        return await reader(action) if reader is not None else None

    def bind_cancel(self, is_cancelled: Any) -> None:
        bind = getattr(self.inner, "bind_cancel", None)
        if callable(bind):
            bind(is_cancelled)

    def expect_target(self, target: Any) -> None:
        expect = getattr(self.inner, "expect_target", None)
        if callable(expect):
            expect(target)

    @property
    def is_real(self) -> bool:
        return bool(getattr(self.inner, "is_real", False))

    @property
    def target_app(self) -> Any:
        return getattr(self.inner, "target_app", None)

    @property
    def permit(self) -> Any:
        return getattr(self.inner, "permit", None)

    def _check(self) -> None:
        from .tiers.computer_use import ActuatorRefused

        if is_killed():
            raise ActuatorRefused("kill flag present")
        if self.screen.locked() or self.screen.asleep():
            raise ActuatorRefused("the screen is locked or asleep")

    async def screenshot(self) -> bytes:
        self._check()
        return await self.inner.screenshot()

    async def execute(self, action: Any) -> None:
        self._check()
        self.last_own_event = time.monotonic()
        await self.inner.execute(action)
        self.last_own_event = time.monotonic()

    async def release_all(self) -> None:
        await self.inner.release_all()


def make_actuator(target_app: str, *, real: bool = False, backend: Any = None, env: dict[str, str] | None = None,
                  permit: Any = None) -> Any:
    """SimulatedActuator unless `real` is asked for explicitly AND UNDERSTUDY_REAL_ACTUATOR=1 (MacActuator checks) AND a
    RunPermit (the owner's one-time token consumed, plus the routine's consent when unattended) is passed (S-14b): the
    MacActuator itself refuses every action without a valid permit."""
    from .tiers.computer_use import MacActuator, SimulatedActuator

    if not real:
        return SimulatedActuator()
    return MacActuator(target_app, backend=backend, env=env, permit=permit)


async def run_desktop_task(goal: str, *, model: ModelPort, guard: Any, actuator: Any, screen: ScreenState,
                           is_current: Callable[[], bool], verify: Callable[[], Any], max_steps: int = 20,
                           deadline_s: float = 120.0, max_nudges: int | None = None, stall_limit: int | None = None,
                           emit: Callable[[Any], None] | None = None) -> Any:
    """Tier 3 on the desktop with the screen guard in front of every action. Defaults to simulated actuators. A REAL
    actuator must carry a permit granted for THIS routine (and, if the run is unattended, granted with its consent).

    `max_nudges=0` (a typed task) means a claim of success ends the run: the model is never told to carry on after it said it was done,
    because on the real screen another action is not free. `stall_limit` ends a run whose screen stops changing."""
    from .tiers.computer_use import ActuatorRefused, ComputerUse

    if getattr(actuator, "is_real", False):
        permit = getattr(actuator, "permit", None)
        rid = getattr(guard, "routine_id", None)
        if permit is None or not permit.valid_for(getattr(actuator, "target_app", "") or ""):
            raise ActuatorRefused("a real-desktop run needs the owner's permit (one-time token consumed for this run)")
        if permit.routine_id != rid or (getattr(guard, "unattended", False) and not permit.unattended):
            raise ActuatorRefused("the permit was not granted for this routine or for an unattended run")
    guarded = ScreenGuardedActuator(actuator, screen)
    extra: dict[str, Any] = {}
    if max_nudges is not None:
        extra["max_nudges"] = max_nudges
    if stall_limit is not None:
        extra["stall_limit"] = stall_limit
    if emit is not None:
        extra["emit"] = emit
    cu = ComputerUse(model, guarded, guard, navigator="desktop", is_current=is_current, max_steps=max_steps,
                     deadline_s=deadline_s, **extra)
    return await cu.run(goal, verify)
