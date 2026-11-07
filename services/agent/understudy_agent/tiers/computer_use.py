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
import re
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


@dataclass(frozen=True)
class TargetRead:
    """What TRUSTED code read at the target of an action: the DOM element under the point, the accessibility element
    under the pointer, or the focused control. Never the model's own words about it. `label` is the accessible name
    (for Enter, the form's default submit button is appended); `role` its role; `field_attrs` the attributes a
    sensitive-field check needs. The gate classifies a pixel click, an Enter press or a newline from this alone."""

    label: str | None
    role: str | None = None
    url: str | None = None
    field_attrs: dict[str, Any] | None = None

    @property
    def key(self) -> tuple[str | None, str | None]:
        return (self.label, self.role)


class Actuator(Protocol):
    scale: float  # screenshot pixels per point

    async def screenshot(self) -> bytes: ...
    async def execute(self, action: Action) -> None: ...
    async def release_all(self) -> None: ...
    # Optional: async def read_target(self, action) -> TargetRead | None   (an actuator without it is gated as unreadable)
    # Optional: def bind_cancel(self, is_cancelled) -> None                 (stop wins inside a long action)


def merge_reads(reads: list["TargetRead | None"]) -> "TargetRead | None":
    """A drag touches two places: both must be readable, and the gate sees both labels."""
    if not reads or any(r is None for r in reads):
        return None
    first = reads[0]
    labels = [r.label for r in reads if r and r.label]
    return TargetRead(" / ".join(dict.fromkeys(labels)) if labels else first.label, first.role, first.url, first.field_attrs)


def blank_png(w: int = 1280, h: int = 720) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (245, 245, 245)).save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------- simulated
class SimulatedActuator:
    """Records actions and returns a blank screenshot. Nothing happens anywhere. The default and the test double."""

    def __init__(self, size: tuple[int, int] = (1280, 720), *, max_actions: int = 200,
                 targets: "TargetRead | Callable[[Action], TargetRead | None] | None" = None) -> None:
        self.size = size
        self.scale = 1.0
        self._targets = targets          # what "trusted code" reads at a target; None means unreadable (the safe default)
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

    async def read_target(self, action: Action) -> "TargetRead | None":
        t = self._targets
        return t(action) if callable(t) else t


_PW_KEYS = {"enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape", "escape": "Escape", "space": "Space",
            "backspace": "Backspace", "delete": "Delete", "del": "Delete", "up": "ArrowUp", "down": "ArrowDown",
            "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End", "pageup": "PageUp",
            "page_up": "PageUp", "pagedown": "PageDown", "page_down": "PageDown", "ctrl": "Control", "control": "Control",
            "alt": "Alt", "option": "Alt", "shift": "Shift", "cmd": "Meta", "command": "Meta", "meta": "Meta"}


def playwright_key(keys: list[str]) -> str:
    """The pipeline normalises key names to lower case; Playwright wants Enter, ArrowDown, Control and so on."""
    out = []
    for k in keys:
        low = k.lower()
        out.append(_PW_KEYS.get(low) or (low.upper() if re.fullmatch(r"f\d{1,2}", low) else k))
    return "+".join(out)


READ_TARGET_JS = r"""
([x, y]) => {
  const txt = e => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  const CTRL = 'button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=menuitem],[role=checkbox],' +
               '[role=radio],[role=tab],[role=switch],[role=option],[onclick]';
  const BTN = ['submit', 'button', 'reset', 'image'];
  const name = e => {
    const al = e.getAttribute('aria-label'); if (al && al.trim()) return al.trim();
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(txt).join(' ').trim(); if (t) return t; }
    const tag = e.tagName.toLowerCase(), ty = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && BTN.includes(ty)) return (e.value || e.getAttribute('alt') || e.getAttribute('title') || '').trim();
    if (e.labels && e.labels.length) { const t = Array.from(e.labels).map(txt).join(' ').trim(); if (t) return t; }
    if (['input', 'textarea', 'select'].includes(tag)) return (e.getAttribute('placeholder') || e.getAttribute('title') || '').trim();
    const t = txt(e); if (t) return t.slice(0, 120);
    return (e.getAttribute('alt') || e.getAttribute('title') || '').trim();
  };
  const focus = (x === null || x === undefined);
  let el = focus ? document.activeElement : document.elementFromPoint(x, y);
  for (let i = 0; !focus && i < 5 && el && el.shadowRoot && el.shadowRoot.elementFromPoint; i++) {
    const inner = el.shadowRoot.elementFromPoint(x, y); if (!inner || inner === el) break; el = inner;
  }
  if (!el) return {ok: false, why: 'nothing there'};
  if (['iframe', 'frame', 'embed', 'object', 'canvas', 'video'].includes(el.tagName.toLowerCase()))
    return {ok: false, why: 'opaque content'};
  if (focus && (el === document.body || el === document.documentElement)) return {ok: true, label: '', role: 'document', field: null};
  let t = el.closest(CTRL);
  if (!t) { const lab = el.closest('label'); t = (lab && lab.control) ? lab.control : el; }
  const tag = t.tagName.toLowerCase(), ty = (t.getAttribute('type') || '').toLowerCase();
  const implicit = {button: 'button', a: 'link', select: 'combobox', textarea: 'textbox', summary: 'button'};
  const byType = {submit: 'button', button: 'button', reset: 'button', image: 'button', checkbox: 'checkbox', radio: 'radio'};
  const role = t.getAttribute('role') || (tag === 'input' ? (byType[ty] || 'textbox') : implicit[tag]) || 'generic';
  const own = role === 'generic' && !t.matches(CTRL) ? '' : name(t);
  const named = ['button', 'link', 'menuitem', 'tab', 'switch', 'option', 'checkbox', 'radio'].includes(role);
  if (named && !own) return {ok: false, why: 'unnamed control'};
  let label = own;
  if (focus && (tag === 'input' || tag === 'select') && !BTN.includes(ty)) {      // Enter here submits the form's default button
    const f = t.form || t.closest('form');
    const b = f && f.querySelector('input[type=submit],button[type=submit],button:not([type]),input[type=image]');
    if (b) { const sn = name(b); label = label ? label + ' / ' + sn : sn; }
  }
  const isField = ['input', 'textarea', 'select'].includes(tag);
  const field = isField ? {name: t.getAttribute('name') || '', id: t.id || '', label: own, placeholder: t.getAttribute('placeholder') || '',
                           autocomplete: t.getAttribute('autocomplete') || '', aria_label: t.getAttribute('aria-label') || '',
                           type: ty || (tag === 'input' ? 'text' : tag), role} : null;
  return {ok: true, label, role, field};
}
"""


class BrowserPageActuator:
    """Mouse and keyboard on ONE headless Playwright page, in the agent's own context. Not the desktop."""

    def __init__(self, page: Any, *, max_actions: int = 400) -> None:
        self.page, self.scale, self.max_actions, self.n = page, 1.0, max_actions, 0

    @property
    def url(self) -> str | None:
        try:
            return self.page.url
        except Exception:  # noqa: BLE001
            return None

    async def read_target(self, action: Action) -> TargetRead | None:
        """The element under the pointer (or the focused control, for typing and Enter), read from the DOM by this
        code. None when it cannot be read (nothing there, an iframe or canvas, a button with no name)."""
        a = action.args
        if action.kind in ("click", "double_click"):
            points: list[Any] = [[a["x"], a["y"]]]
        elif action.kind == "drag":
            path = a["path"]
            points = [[path[0]["x"], path[0]["y"]], [path[-1]["x"], path[-1]["y"]]]
        else:
            points = [[None, None]]
        reads: list[TargetRead | None] = []
        for pt in points:
            try:
                r = await self.page.evaluate(READ_TARGET_JS, pt)
            except Exception:  # noqa: BLE001 - a page mid-navigation cannot be read: unreadable, never "fine"
                return None
            reads.append(TargetRead(r["label"], r["role"], self.url, r.get("field")) if r and r.get("ok") else None)
        return merge_reads(reads)

    async def screenshot(self) -> bytes:
        """A click that submits a form can leave the page mid-navigation; wait for it, and retry once on a timeout."""
        last: Exception | None = None
        for _ in range(2):
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                return await self.page.screenshot(type="png", timeout=15000, animations="disabled")
            except Exception as exc:  # noqa: BLE001 - Playwright timeouts
                last = exc
                await asyncio.sleep(0.2)
        raise ActuatorRefused(f"could not take a screenshot: {type(last).__name__}")

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
            await p.keyboard.press(playwright_key(list(a["keys"])))
        elif action.kind == "scroll":
            await p.mouse.wheel(a.get("scroll_x", 0), a.get("scroll_y", 0))
        elif action.kind == "wait":
            await asyncio.sleep(float(a.get("seconds", 1)))
        elif action.kind != "screenshot":
            raise ActuatorRefused(f"the page actuator cannot perform {action.kind!r}")

    async def release_all(self) -> None:
        return None


# ----------------------------------------------------------------------------- real desktop (guarded)
TITLE_BAR_PT = 28.0       # a typing target must be below the window's title bar
TYPE_CHUNK = 6            # at most this many characters are typed per verification
FOCUS_POLL_S = 0.025
FOCUS_WAIT_S = 0.5


class MacBackend(Protocol):
    """Everything MacActuator needs from the operating system. `QuartzBackend` is the real one; tests pass a fake.
    Methods are synchronous and fast. Coordinates are in POINTS."""

    def frontmost_app(self) -> str: ...
    def screen_locked(self) -> bool: ...
    def backing_scale(self) -> float: ...                 # NSScreen.mainScreen().backingScaleFactor()
    def display_width_pts(self) -> float: ...             # CGDisplayBounds width, in points
    def window_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None: ...  # topmost layer-0 window there
    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None: ...   # move | down | up
    def type_text(self, text: str) -> None: ...
    def key(self, keys: list[str]) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def screenshot_png(self) -> bytes: ...
    def release_all(self) -> None: ...


def png_width(png: bytes) -> int:
    import struct

    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", png[16:24])[0]


class QuartzBackend:
    """Real macOS events via pyobjc (Quartz CGEvent, AppKit NSWorkspace/NSScreen). Imports lazily; install with
    `uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa ...`. Reference: scripts/s2_textedit_test.py.
    NOT exercised by tests: only the owner-supervised check runs it."""

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

    def backing_scale(self) -> float:  # pragma: no cover - real desktop
        from AppKit import NSScreen

        return float(NSScreen.mainScreen().backingScaleFactor())

    def display_width_pts(self) -> float:  # pragma: no cover - real desktop
        import Quartz

        return float(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width)

    def window_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None:  # pragma: no cover - real desktop
        """Topmost normal (layer 0) on-screen window containing the point. CGWindowList is ordered front to back."""
        import Quartz

        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
            if int(w.get("kCGWindowLayer", 1)) != 0 or float(w.get("kCGWindowAlpha", 1.0)) <= 0.0:
                continue
            b = w.get("kCGWindowBounds") or {}
            x, y, ww, hh = float(b.get("X", 0)), float(b.get("Y", 0)), float(b.get("Width", 0)), float(b.get("Height", 0))
            if x <= x_pt < x + ww and y <= y_pt < y + hh:
                return {"owner": str(w.get("kCGWindowOwnerName", "")), "bounds": (x, y, ww, hh), "layer": 0,
                        "title": str(w.get("kCGWindowName", "") or "")}
        return None

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
    """Real desktop actuator behind every guard. Only constructed when UNDERSTUDY_REAL_ACTUATOR=1, and only ever
    for the named harmless target app.

    Guards (a failure aborts, releases held buttons and keys, and raises ActuatorRefused):
      * scale: points come from the BACKING scale (NSScreen), cross-checked against screenshot pixel width divided by
        the display's width in points; if they disagree nothing is done. No pointer action runs before a screenshot
        has verified the scale.
      * hit test before EVERY pointer action (move, click, double click, scroll): the topmost normal window at the
        target point must belong to the target app, and for clicks the point must be below its title bar. Being the
        frontmost app is not enough.
      * after a click, poll up to 500 ms for two consecutive reads where the frontmost app AND the window at the click
        point are the target; otherwise abort (activation lag is exactly what this catches).
      * before EVERY typed chunk (at most 6 characters) and every key event the same check is repeated at the last
        verified click point. Typing without a verified click is refused.
      * kill flag, locked or asleep screen, action budget and time budget before every event.
    `report` records the scale cross-check and every hit test for the owner to read.
    """

    def __init__(self, target_app: str, *, backend: MacBackend | None = None, kill_flag: Path | None = None,
                 max_actions: int = 40, time_budget_s: float = 120.0,
                 clock: Callable[[], float] = time.monotonic, env: dict[str, str] | None = None,
                 focus_wait_s: float = FOCUS_WAIT_S, focus_poll_s: float = FOCUS_POLL_S) -> None:
        if (env if env is not None else os.environ).get("UNDERSTUDY_REAL_ACTUATOR") != "1":
            raise ActuatorRefused("the real actuator is disabled; set UNDERSTUDY_REAL_ACTUATOR=1 (owner present only)")
        if not target_app:
            raise ActuatorRefused("a target app name is required")
        self.target_app = target_app
        self.backend = backend or QuartzBackend()
        self._kill = kill_flag
        self.max_actions, self.time_budget_s, self._clock = max_actions, time_budget_s, clock
        self._focus_wait, self._focus_poll = focus_wait_s, focus_poll_s
        self._started = clock()
        self.n = 0
        self.scale = float(self.backend.backing_scale())
        self._scale_verified = False
        self._last_point: tuple[float, float] | None = None
        self.report: dict[str, Any] = {"target_app": target_app, "backing_scale": self.scale, "scale_check": None,
                                       "hits": [], "typed_chars": 0}

    # ------------------------------------------------------------------ guards
    def _abort(self, why: str) -> None:
        try:
            self.backend.release_all()
        finally:
            self.report["aborted"] = why
            raise ActuatorRefused(why)

    def _guard_passive(self) -> None:
        flag = self._kill or kill_flag_path()
        if flag.exists():
            self._abort("kill flag present")
        if self.backend.screen_locked():
            self._abort("screen is locked or asleep")

    def _guard(self) -> None:
        self._guard_passive()
        front = self.backend.frontmost_app()
        if front != self.target_app:
            self._abort(f"frontmost app is {front!r}, not {self.target_app!r}")
        if self.n >= self.max_actions:
            self._abort("action budget used up")
        if self._clock() - self._started > self.time_budget_s:
            self._abort("time budget used up")

    def _hit(self, x_pt: float, y_pt: float, *, label: str, need_body: bool) -> dict[str, Any]:
        """Refuse unless the topmost normal window at the point belongs to the target app."""
        w = self.backend.window_at(x_pt, y_pt)
        rec = {"at": label, "x_pt": round(x_pt, 2), "y_pt": round(y_pt, 2), "scale": self.scale,
               "owner": (w or {}).get("owner"), "bounds": (w or {}).get("bounds")}
        self.report["hits"].append(rec)
        if w is None:
            self._abort(f"no normal window at ({x_pt:.0f}, {y_pt:.0f}) pt; refusing to act there")
        if w["owner"] != self.target_app:
            self._abort(f"the window at ({x_pt:.0f}, {y_pt:.0f}) pt belongs to {w['owner']!r}, not {self.target_app!r}")
        bx, by, bw, bh = w["bounds"]
        if need_body and y_pt < by + TITLE_BAR_PT:
            self._abort("the point is in the window's title bar, not in its body")
        return rec

    def _pt(self, v: int) -> float:
        return v / self.scale

    async def _focus_stable(self, x_pt: float, y_pt: float, *, need_body: bool) -> None:
        """Wait up to 500 ms for TWO consecutive consistent reads; abort if they never come."""
        deadline = self._clock() + self._focus_wait
        good = 0
        while True:
            w = self.backend.window_at(x_pt, y_pt)
            ok = (self.backend.frontmost_app() == self.target_app and w is not None
                  and w["owner"] == self.target_app and (not need_body or y_pt >= w["bounds"][1] + TITLE_BAR_PT))
            good = good + 1 if ok else 0
            if good >= 2:
                return
            if self._clock() >= deadline:
                self._abort("focus did not settle on the target app and window after the click")
            await asyncio.sleep(self._focus_poll)

    async def _verify_typing_target(self) -> None:
        self._guard()
        if self._last_point is None:
            self._abort("no verified click target yet; refusing to type")
        await self._focus_stable(*self._last_point, need_body=True)

    # ------------------------------------------------------------------ screenshot and scale
    async def screenshot(self) -> bytes:
        self._guard_passive()
        png = self.backend.screenshot_png()
        px = png_width(png)
        pts = float(self.backend.display_width_pts())
        measured = px / pts if pts else 0.0
        ok = abs(measured - self.scale) <= 0.05
        self.report["scale_check"] = {"backing_scale": self.scale, "screenshot_px": px, "display_pts": pts,
                                      "measured_scale": round(measured, 3), "agree": ok}
        if not ok:
            self._abort(f"scale disagreement: backing scale {self.scale} but the screenshot says {measured:.3f}")
        self._scale_verified = True
        return png

    # ------------------------------------------------------------------ actions
    async def execute(self, action: Action) -> None:
        self._guard()
        a = action.args
        self.n += 1
        try:
            if action.kind in ("move", "click", "double_click", "scroll"):
                if not self._scale_verified:
                    self._abort("the display scale has not been verified against a screenshot yet")
                x, y = self._pt(a["x"]), self._pt(a["y"])
                self._hit(x, y, label=action.kind, need_body=action.kind != "move")
                self.backend.mouse("move", x, y)
                if action.kind == "move":
                    return
                await asyncio.sleep(0.05)
                self._guard()
                self._hit(x, y, label=f"{action.kind}:recheck", need_body=True)
                if action.kind == "scroll":
                    self.backend.scroll(int(a.get("scroll_x", 0)), int(a.get("scroll_y", 0)))
                    return
                for _ in range(2 if action.kind == "double_click" else 1):
                    self.backend.mouse("down", x, y)
                    await asyncio.sleep(0.04)
                    self.backend.mouse("up", x, y)
                await self._focus_stable(x, y, need_body=True)   # activation lag is caught here, before any typing
                self._last_point = (x, y)
            elif action.kind == "type":
                text = a["text"]
                for i in range(0, len(text), TYPE_CHUNK):
                    await self._verify_typing_target()     # re-verify before EVERY chunk
                    chunk = text[i:i + TYPE_CHUNK]
                    self.backend.type_text(chunk)
                    self.report["typed_chars"] += len(chunk)
            elif action.kind == "key":
                await self._verify_typing_target()
                self.backend.key(list(a["keys"]))
            elif action.kind == "wait":
                await asyncio.sleep(float(a.get("seconds", 1)))
            elif action.kind != "screenshot":
                self._abort(f"action kind {action.kind!r} is not supported by the real actuator")
        except ActuatorRefused:
            raise
        except BaseException:
            self.backend.release_all()
            raise

    async def release_all(self) -> None:
        self.backend.release_all()


# ----------------------------------------------------------------------------- the tier-3 loop
@dataclass
class Tier3Result:
    outcome: str                       # done | claimed_not_verified | gave_up | stalled | step_cap | stopped
    steps: int = 0
    claimed_done: bool = False
    false_claim: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)
    progress_steps: int = 0            # steps after which the screen had visibly changed
    refusals: int = 0                  # typed literals, unknown handles or letter keys refused by the fact-handle check
    done_summary_len: int = 0
    last_summary: str = ""             # the model's own closing words (model output, never page text or values)


FP_SIZE = (640, 400)
PIXEL_DELTA = 24        # grey levels a pixel must move to count as changed
CHANGED_PIXELS = 12     # changed pixels (at 640 x 400) that make a screen "different": a typed digit is 15 to 25


def screen_fingerprint(png: bytes) -> bytes | None:
    """A half-size grey-scale copy of a screenshot, to tell whether the screen changed. None if undecodable."""
    try:
        from PIL import Image

        return Image.open(io.BytesIO(png)).convert("L").resize(FP_SIZE).tobytes()
    except Exception:  # noqa: BLE001
        return None


def screen_changed(a: bytes, b: bytes, min_pixels: int = CHANGED_PIXELS) -> bool:
    """True if at least `min_pixels` pixels moved by more than PIXEL_DELTA grey levels. One typed character changes
    well over a dozen pixels; a pointer shadow or anti-aliasing flicker does not."""
    if len(a) != len(b) or not a:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y and abs(x - y) > PIXEL_DELTA:
            n += 1
            if n >= min_pixels:
                return True
    return False


_TARGETED = ("click", "double_click", "drag", "type", "key")   # actions whose effect depends on what is under them


class ComputerUse:
    """The tier-3 loop. Budgeting is by PROGRESS, not a flat cap: the run may go on while the screen keeps changing
    (a form being filled, pages advancing) up to `max_steps`, and stops early after `stall_limit` consecutive steps in
    which the screen did not change (the stuck-loop detector covers repeats on top of that).

    `facts` switches on fact handles: typed text must be exactly one handle from the closed vocabulary, which is
    resolved to the real value only at the moment of actuation. Without `facts` the loop behaves as before."""

    def __init__(self, model: ModelPort, actuator: Actuator, guard: Guard, *, navigator: str,
                 emit: Emit | None = None, is_current: Callable[[], bool] = lambda: True, step_start: int = 0,
                 max_steps: int = 120, deadline_s: float = 600.0, screenshot_size: tuple[int, int] = (1280, 720),
                 facts: Any = None, stall_limit: int = 12, pause: Any = None) -> None:
        self.model, self.actuator, self.guard, self.navigator = model, actuator, guard, navigator
        self.emit, self.is_current, self.step_start = emit, is_current, step_start
        self.max_steps, self.deadline_s, self.size = max_steps, deadline_s, screenshot_size
        self.facts, self.stall_limit, self.pause = facts, stall_limit, pause
        self.stuck = StuckDetector()

    async def _read_target(self, out: Action) -> TargetRead | None:
        reader = getattr(self.actuator, "read_target", None)
        if reader is None or out.kind not in _TARGETED:
            return None
        try:
            return await reader(out)
        except ActuatorRefused:
            raise
        except Exception:  # noqa: BLE001 - an unreadable target is unresolved, which the gate sends to a human
            return None

    def _event(self, n: int, action: str, ok: bool, detail: str = "") -> None:
        ev = StepEvent(navigator=self.navigator, step=n, tier=3, action=action, ok=ok, detail=detail)
        self.guard.record_step(ev)
        if self.emit:
            self.emit(ev)

    async def run(self, goal: str, verify: Callable[[], Awaitable[bool]]) -> Tier3Result:
        from .facts import FactRefused, UnresolvedFact, key_would_type_text

        base_goal = goal + ("\n\n" + self.facts.goal_block() if self.facts is not None else "")
        self.guard.set_mode("model_driven")
        self.guard.set_goal(goal)
        bind = getattr(self.actuator, "bind_cancel", None)
        if callable(bind):            # Stop wins inside a long action too (a chunked type checks this between chunks)
            bind(lambda: not self.is_current())
        attach = getattr(self.model, "attach", None)
        if callable(attach):          # test doubles that need the actuator's page; real providers have no such hook
            attach(self.navigator, self.actuator)
        res = Tier3Result("step_cap")
        t0 = time.monotonic()
        n = self.step_start
        last_fp: bytes | None = None
        stalled = 0
        refused_streak = 0
        retargets = 0
        feedback = ""
        try:
            while res.steps < self.max_steps:
                if not self.is_current():
                    raise asyncio.CancelledError()
                if self.pause is not None:
                    await self.pause.wait_if_paused()          # step-level pause: the run keeps its place and its page
                if time.monotonic() - t0 > self.deadline_s:
                    res.outcome = "stopped"
                    raise StepBudgetExceeded("tier 3 time budget used up")
                shot = await self.actuator.screenshot()
                fp = screen_fingerprint(shot)
                if fp is not None and last_fp is not None:
                    changed = screen_changed(fp, last_fp)
                    stalled = 0 if changed else stalled + 1
                    res.progress_steps += 1 if changed else 0
                    if stalled >= self.stall_limit:
                        res.outcome = "stalled"
                        raise StepBudgetExceeded(f"tier 3 made no visible progress in {stalled} steps")
                last_fp = fp if fp is not None else last_fp
                pobs = self.guard.observe_screen()  # one fresh observation authorises exactly one action
                out = await asyncio.to_thread(self.model.computer_step, base_goal + feedback, shot, list(res.history),
                                              session=self.navigator)
                feedback = ""
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
                    res.done_summary_len = len(out.summary or "")
                    res.last_summary = out.summary or ""
                    ok = await verify()
                    res.false_claim = bool(out.claimed_success and not ok)
                    res.outcome = "done" if ok else ("claimed_not_verified" if out.claimed_success else "gave_up")
                    self._event(n, "done", ok, "claim verified" if ok else (
                        "claim NOT verified by code" if out.claimed_success else "the model said it could not finish"))
                    return res
                handle: str | None = None
                if self.facts is not None:
                    try:
                        if out.kind == "type":
                            handle = self.facts.check(out.args.get("text"))
                        elif out.kind == "key" and key_would_type_text(list(out.args.get("keys", []))):
                            raise FactRefused("key_types_text", "a letter or digit key would type a literal value")
                    except FactRefused as exc:
                        res.refusals += 1
                        refused_streak += 1
                        res.history.append({"kind": out.kind, "ok": False, "why": exc.code})
                        self.guard.note("fact_refused", "refused", exc.code, tier=3)
                        self._event(n, "type_fact" if out.kind == "type" else out.kind, False, f"refused: {exc.code}")
                        feedback = ("\nNOTE: your last action was refused. Type only a handle from the FACTS list, "
                                    "exactly, as the whole text of one type action. Do not type values or press letter keys.")
                        if refused_streak >= 4:
                            raise StuckLoop(f"the model keeps trying to type literal values ({exc.code})") from None
                        continue
                refused_streak = 0
                if self.pause is not None and await self.pause.wait_if_paused():
                    res.steps -= 1                              # the human arrived while the model was thinking:
                    n -= 1                                      # that action is stale, look at the screen again
                    continue
                if not self.is_current():                       # Stop or a human taking over while the model thought (S-03)
                    raise asyncio.CancelledError()
                # What the gate sees is what TRUSTED code reads at the target. The model's own `label` is only a hint
                # that can add risk (it stays in the action's args); it never makes a step "resolved" (S-01).
                tr = await self._read_target(out)
                dec = self.guard.authorise(out, pobs, label=tr.label if tr else None, role=tr.role if tr else None,
                                           url=(tr.url if tr else None) or getattr(self.actuator, "url", None),
                                           field_attrs=tr.field_attrs if tr else None, screen=self.size)
                if dec.verdict == "block" and dec.layer == "actions":
                    res.history.append({"kind": getattr(out, "kind", "?"), "ok": False})
                    self._event(n, getattr(out, "kind", "?"), False, f"rejected: {dec.codes[:1]}")
                    continue
                if dec.verdict != "allow":
                    self._event(n, out.kind, False, f"{dec.verdict} {dec.layer or ''}".strip())
                self.guard.require(dec, (tr.label if tr else None) or out.kind, navigator=self.navigator)
                if self.stuck.push((out.kind, tuple(sorted((k, str(v)) for k, v in out.args.items())), fp)):
                    self._event(n, out.kind, False, "stuck loop")
                    raise StuckLoop("tier 3 stuck loop")
                act = Action(dec.action.kind, dict(dec.action.args)) if dec.action else out  # the validated form
                # Stop wins, and the page may have moved under the pointer since the read: look once more, right before
                # the event. A different target, or one that became unreadable, voids this action (nothing was done).
                if not self.is_current():
                    raise asyncio.CancelledError()
                if out.kind in _TARGETED:
                    tr2 = await self._read_target(out)
                    if (tr is None) != (tr2 is None) or (tr is not None and tr.key != tr2.key):
                        res.steps -= 1
                        n -= 1
                        retargets += 1
                        if retargets > 5:
                            raise StepBudgetExceeded("the target under the pointer keeps changing before the action runs")
                        self.guard.note("target_changed", "refused", out.kind, tier=3)
                        self._event(n + 1, out.kind, False, "the target changed before the action; looking again")
                        feedback = "\nNOTE: the screen changed before your last action ran, so it was not performed."
                        continue
                if handle is not None:
                    try:
                        value = self.facts.resolve(handle)      # the ONLY place a value exists, and it goes straight out
                    except UnresolvedFact as exc:  # pragma: no cover - the vocabulary check already passed
                        raise TierError(str(exc)) from None
                    self.guard.record(dec, True)
                    if value == "":
                        res.history.append({"kind": "type", "handle": handle, "ok": True, "empty": True})
                        self._event(n, "type_fact", True, f"handle={handle} (no value for this household)")
                        continue
                    await self.actuator.execute(Action("type", {"text": value}))
                    del value
                    res.history.append({"kind": "type", "handle": handle, "ok": True})
                    self._event(n, "type_fact", True, f"handle={handle}")
                    continue
                retargets = 0
                await self.actuator.execute(act)
                self.guard.record(dec, True)
                res.history.append({"kind": act.kind, "args": {k: v for k, v in act.args.items() if k != "text"}, "ok": True})
                self._event(n, act.kind, True)
            raise StepBudgetExceeded(f"tier 3 step cap {self.max_steps} reached")
        finally:
            await self.actuator.release_all()
