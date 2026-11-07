"""Tier 3: computer use through `ModelPort.computer_step` and an `Actuator` (AGT-3, OFF-4).

One action per turn, a fresh screenshot each time, a step cap, a time budget, an action-class gate and a
stuck-loop detector. A provider safety check is NEVER auto-acknowledged: it goes to the human queue.

Actuators
  SimulatedActuator    default; performs nothing, records everything. The only one used in tests.
  BrowserPageActuator  drives ONE headless Playwright page inside the agent's own context (not the desktop).
  MacActuator          real desktop events through Quartz CGEvent. Constructed only when
                       UNDERSTUDY_REAL_ACTUATOR=1. Never exercised by tests; the owner-supervised check is run
                       by the lead against TextEdit or Calculator only.
"""
from __future__ import annotations

import asyncio
import io
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from ..models.port import Action, Done, ModelPort, SafetyStop
from ..supervisor import kill_flag_path
from .base import Emit, StepBudgetExceeded, StepEvent, StuckDetector, StuckLoop, TierError
from .safety import Guard



class ProviderSafetyStop(TierError):
    """The provider returned a pending safety check. It is queued for a human, never acknowledged here."""

    def __init__(self, checks: list[dict[str, Any]], queue_id: str | None) -> None:
        super().__init__(f"provider safety check pending ({len(checks)})")
        self.checks, self.queue_id = checks, queue_id


class ActuatorRefused(TierError):
    """An actuator guard refused (wrong frontmost app, locked screen, budget, kill flag)."""


class Actuator(Protocol):
    scale: float  # screenshot pixels per point

    async def screenshot(self) -> bytes: ...
    async def execute(self, action: Action) -> None: ...
    async def release_all(self) -> None: ...


def blank_png(w: int = 1280, h: int = 720) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (245, 245, 245)).save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------- simulated
class SimulatedActuator:
    """Records actions and returns a blank screenshot. Nothing happens anywhere. The default and the test double."""

    def __init__(self, size: tuple[int, int] = (1280, 720), *, max_actions: int = 200) -> None:
        self.size = size
        self.scale = 1.0
        self.actions: list[Action] = []
        self.max_actions = max_actions
        self.released = 0
        self.typed = ""
        self.cursor = (size[0] // 2, size[1] // 2)

    async def screenshot(self) -> bytes:
        return blank_png(*self.size)

    async def execute(self, action: Action) -> None:
        if len(self.actions) >= self.max_actions:
            raise ActuatorRefused("simulated action budget used up")
        self.actions.append(action)
        if action.kind in ("click", "double_click", "move"):
            self.cursor = (action.args["x"], action.args["y"])
        elif action.kind == "type":
            self.typed += action.args["text"]

    async def release_all(self) -> None:
        self.released += 1


class BrowserPageActuator:
    """Mouse and keyboard on ONE headless Playwright page, in the agent's own context. Not the desktop."""

    def __init__(self, page: Any, *, max_actions: int = 100) -> None:
        self.page, self.scale, self.max_actions, self.n = page, 1.0, max_actions, 0

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(type="png")

    async def execute(self, action: Action) -> None:
        self.n += 1
        if self.n > self.max_actions:
            raise ActuatorRefused("page actuator action budget used up")
        a, p = action.args, self.page
        if action.kind == "click":
            await p.mouse.click(a["x"], a["y"])
        elif action.kind == "double_click":
            await p.mouse.dblclick(a["x"], a["y"])
        elif action.kind == "move":
            await p.mouse.move(a["x"], a["y"])
        elif action.kind == "type":
            await p.keyboard.type(a["text"])
        elif action.kind == "key":
            await p.keyboard.press("+".join(a["keys"]))
        elif action.kind == "scroll":
            await p.mouse.wheel(a.get("scroll_x", 0), a.get("scroll_y", 0))
        elif action.kind == "wait":
            await asyncio.sleep(float(a.get("seconds", 1)))

    async def release_all(self) -> None:
        return None


# ----------------------------------------------------------------------------- real desktop (guarded)
class MacBackend(Protocol):
    """Everything MacActuator needs from the operating system. `QuartzBackend` is the real one;
    tests pass a fake. Methods are synchronous and fast."""

    def frontmost_app(self) -> str: ...
    def screen_locked(self) -> bool: ...
    def display_scale(self) -> float: ...
    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None: ...   # move | down | up
    def type_text(self, text: str) -> None: ...
    def key(self, keys: list[str]) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def screenshot_png(self) -> bytes: ...
    def release_all(self) -> None: ...


class QuartzBackend:
    """Real macOS events via pyobjc (Quartz CGEvent, AppKit NSWorkspace). Imports lazily; install with
    `uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa ...`. Reference: scripts/s2_textedit_test.py."""

    def __init__(self) -> None:
        try:
            import AppKit  # noqa: F401
            import Quartz  # noqa: F401
        except ImportError as exc:  # pragma: no cover - needs pyobjc
            raise ImportError("QuartzBackend needs pyobjc-framework-Quartz and pyobjc-framework-Cocoa") from exc
        self._down = False

    def frontmost_app(self) -> str:  # pragma: no cover - real desktop
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName()) if app else ""

    def screen_locked(self) -> bool:  # pragma: no cover - real desktop
        import Quartz

        d = Quartz.CGSessionCopyCurrentDictionary() or {}
        asleep = bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))
        return bool(d.get("CGSSessionScreenIsLocked", 0)) or asleep

    def display_scale(self) -> float:  # pragma: no cover - real desktop
        import Quartz

        did = Quartz.CGMainDisplayID()
        return float(Quartz.CGDisplayPixelsWide(did)) / float(Quartz.CGDisplayBounds(did).size.width)

    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None:  # pragma: no cover - real desktop
        import Quartz as Q

        ev_type = {"move": Q.kCGEventMouseMoved, "down": Q.kCGEventLeftMouseDown, "up": Q.kCGEventLeftMouseUp}[kind]
        Q.CGEventPost(Q.kCGHIDEventTap, Q.CGEventCreateMouseEvent(None, ev_type, (x_pt, y_pt), Q.kCGMouseButtonLeft))
        self._down = kind == "down" or (self._down and kind != "up")

    def type_text(self, text: str) -> None:  # pragma: no cover - real desktop
        import Quartz as Q

        for ch in text:
            for down in (True, False):
                ev = Q.CGEventCreateKeyboardEvent(None, 0, down)
                Q.CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
                Q.CGEventPost(Q.kCGHIDEventTap, ev)
                time.sleep(0.012)

    def key(self, keys: list[str]) -> None:  # pragma: no cover - real desktop
        raise NotImplementedError("named key chords are not implemented; type_text covers the spike")

    def scroll(self, dx: int, dy: int) -> None:  # pragma: no cover - real desktop
        import Quartz as Q

        ev = Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitPixel, 2, dy, dx)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def screenshot_png(self) -> bytes:  # pragma: no cover - real desktop
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.png"
            subprocess.run(["screencapture", "-x", str(p)], check=True)
            return p.read_bytes()

    def release_all(self) -> None:  # pragma: no cover - real desktop
        if self._down:
            import Quartz as Q

            p = Q.CGEventGetLocation(Q.CGEventCreate(None))
            self.mouse("up", float(p.x), float(p.y))
            self._down = False


class MacActuator:
    """Real desktop actuator behind every guard the lead required. It is only constructed when
    UNDERSTUDY_REAL_ACTUATOR=1, and only ever for the named harmless target app.

    Guards, checked before EVERY event: the kill flag; the screen is not locked or asleep; the frontmost app is
    the target; the action budget and the time budget. Pixels from screenshots are divided by the display scale to
    get points. On any abort or refusal, held buttons and keys are released.
    """

    def __init__(self, target_app: str, *, backend: MacBackend | None = None, kill_flag: Path | None = None,
                 max_actions: int = 40, time_budget_s: float = 120.0,
                 clock: Callable[[], float] = time.monotonic, env: dict[str, str] | None = None) -> None:
        if (env if env is not None else os.environ).get("UNDERSTUDY_REAL_ACTUATOR") != "1":
            raise ActuatorRefused("the real actuator is disabled; set UNDERSTUDY_REAL_ACTUATOR=1 (owner present only)")
        if not target_app:
            raise ActuatorRefused("a target app name is required")
        self.target_app = target_app
        self.backend = backend or QuartzBackend()
        self._kill = kill_flag
        self.max_actions, self.time_budget_s, self._clock = max_actions, time_budget_s, clock
        self._started = clock()
        self.n = 0
        self.scale = float(self.backend.display_scale())

    def _guard(self) -> None:
        flag = self._kill or kill_flag_path()
        if flag.exists():
            self._abort("kill flag present")
        if self.backend.screen_locked():
            self._abort("screen is locked or asleep")
        front = self.backend.frontmost_app()
        if front != self.target_app:
            self._abort(f"frontmost app is {front!r}, not {self.target_app!r}")
        if self.n >= self.max_actions:
            self._abort("action budget used up")
        if self._clock() - self._started > self.time_budget_s:
            self._abort("time budget used up")

    def _abort(self, why: str) -> None:
        try:
            self.backend.release_all()
        finally:
            raise ActuatorRefused(why)

    def _pt(self, v: int) -> float:
        return v / self.scale

    async def screenshot(self) -> bytes:
        self._guard_passive()
        return self.backend.screenshot_png()

    def _guard_passive(self) -> None:
        flag = self._kill or kill_flag_path()
        if flag.exists():
            self._abort("kill flag present")
        if self.backend.screen_locked():
            self._abort("screen is locked or asleep")

    async def execute(self, action: Action) -> None:
        self._guard()
        a = action.args
        self.n += 1
        try:
            if action.kind == "move":
                self.backend.mouse("move", self._pt(a["x"]), self._pt(a["y"]))
            elif action.kind in ("click", "double_click"):
                x, y = self._pt(a["x"]), self._pt(a["y"])
                self.backend.mouse("move", x, y)
                await asyncio.sleep(0.05)
                self._guard_passive_front()
                for _ in range(2 if action.kind == "double_click" else 1):
                    self.backend.mouse("down", x, y)
                    await asyncio.sleep(0.04)
                    self.backend.mouse("up", x, y)
            elif action.kind == "type":
                self.backend.type_text(a["text"])
            elif action.kind == "key":
                self.backend.key(list(a["keys"]))
            elif action.kind == "scroll":
                self.backend.scroll(int(a.get("scroll_x", 0)), int(a.get("scroll_y", 0)))
            elif action.kind == "wait":
                await asyncio.sleep(float(a.get("seconds", 1)))
            elif action.kind != "screenshot":
                raise ActuatorRefused(f"action kind {action.kind!r} is not supported by the real actuator")
        except BaseException:
            self.backend.release_all()
            raise

    def _guard_passive_front(self) -> None:
        if self.backend.frontmost_app() != self.target_app:
            self._abort("target app lost focus before the click")

    async def release_all(self) -> None:
        self.backend.release_all()


# ----------------------------------------------------------------------------- the tier-3 loop
@dataclass
class Tier3Result:
    outcome: str                       # done | claimed_not_verified | step_cap | stopped
    steps: int = 0
    claimed_done: bool = False
    false_claim: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)


class ComputerUse:
    def __init__(self, model: ModelPort, actuator: Actuator, guard: Guard, *, navigator: str,
                 emit: Emit | None = None, is_current: Callable[[], bool] = lambda: True, step_start: int = 0,
                 max_steps: int = 20, deadline_s: float = 120.0, screenshot_size: tuple[int, int] = (1280, 720)) -> None:
        self.model, self.actuator, self.guard, self.navigator = model, actuator, guard, navigator
        self.emit, self.is_current, self.step_start = emit, is_current, step_start
        self.max_steps, self.deadline_s, self.size = max_steps, deadline_s, screenshot_size
        self.stuck = StuckDetector()

    def _event(self, n: int, action: str, ok: bool, detail: str = "") -> None:
        ev = StepEvent(navigator=self.navigator, step=n, tier=3, action=action, ok=ok, detail=detail)
        self.guard.record_step(ev)
        if self.emit:
            self.emit(ev)

    async def run(self, goal: str, verify: Callable[[], Awaitable[bool]]) -> Tier3Result:
        self.guard.set_mode("model_driven")
        self.guard.set_goal(goal)
        res = Tier3Result("step_cap")
        t0 = time.monotonic()
        n = self.step_start
        try:
            while res.steps < self.max_steps:
                if not self.is_current():
                    raise asyncio.CancelledError()
                if time.monotonic() - t0 > self.deadline_s:
                    res.outcome = "stopped"
                    raise StepBudgetExceeded("tier 3 time budget used up")
                shot = await self.actuator.screenshot()
                pobs = self.guard.observe_screen()  # one fresh observation authorises exactly one action
                out = await asyncio.to_thread(self.model.computer_step, goal, shot, list(res.history),
                                              session=self.navigator)
                res.steps += 1
                n += 1
                if isinstance(out, SafetyStop):
                    item = self.guard.enqueue(
                        kind="injection_pause", title=f"Model provider raised a safety check ({self.navigator})",
                        summary="A pending safety check from the model provider was not acknowledged. A human decides.",
                        risk_class="normal",
                        evidence={"screenshots": [], "extracted": {"checks": [c.get("code") for c in out.checks]},
                                  "expected": {}, "diff": [], "tier_log": []})
                    self._event(n, "safety_stop", False, "provider safety check")
                    raise ProviderSafetyStop(out.checks, item["id"])
                if isinstance(out, Done):
                    res.claimed_done = out.claimed_success
                    ok = await verify()
                    res.false_claim = bool(out.claimed_success and not ok)
                    res.outcome = "done" if ok else "claimed_not_verified"
                    self._event(n, "done", ok, "claim verified" if ok else "claim NOT verified by code")
                    return res
                label = str(out.args.get("label") or "") or None
                dec = self.guard.authorise(out, pobs, label=label, url=None, screen=self.size)
                if dec.verdict == "block" and dec.layer == "actions":
                    res.history.append({"kind": getattr(out, "kind", "?"), "ok": False})
                    self._event(n, getattr(out, "kind", "?"), False, f"rejected: {dec.codes[:1]}")
                    continue
                if dec.verdict != "allow":
                    self._event(n, out.kind, False, f"{dec.verdict} {dec.layer or ''}".strip())
                self.guard.require(dec, label or out.kind, navigator=self.navigator)
                if self.stuck.push((out.kind, tuple(sorted((k, str(v)) for k, v in out.args.items())))):
                    self._event(n, out.kind, False, "stuck loop")
                    raise StuckLoop("tier 3 stuck loop")
                act = Action(dec.action.kind, dict(dec.action.args)) if dec.action else out  # the validated form
                await self.actuator.execute(act)
                self.guard.record(dec, True)
                res.history.append({"kind": act.kind, "args": {k: v for k, v in act.args.items() if k != "text"}, "ok": True})
                self._event(n, act.kind, True)
            raise StepBudgetExceeded(f"tier 3 step cap {self.max_steps} reached")
        finally:
            await self.actuator.release_all()
