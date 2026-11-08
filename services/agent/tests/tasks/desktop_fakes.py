"""Fakes for the desktop route. A fake Mac (windows, permissions, the events it was asked to make) and a scripted computer-use model.
Nothing here clicks, types or captures anything real: it is all in memory, and the real desktop is never touched."""
from __future__ import annotations

import struct
import zlib
from typing import Any

from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Done
from understudy_agent.tasks.desktop import WindowRef


def png(w: int, h: int = 1) -> bytes:
    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = (b"\x00" + b"\xff" * (w * 3)) * h
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def win(owner: str = "TextEdit", bounds: tuple[float, float, float, float] = (100.0, 100.0, 400.0, 300.0), number: int = 11,
        pid: int = 900, title: str = "Notes", layer: int = 0) -> dict[str, Any]:
    return {"owner": owner, "bounds": bounds, "layer": layer, "number": number, "pid": pid, "title": title}


TEXT_AREA = {"role": "AXTextArea", "description": "text entry area"}
SEND_BUTTON = {"role": "AXButton", "title": "Send", "actions": ["AXPress"]}


class FakeMac:
    """Both the desktop the route reads (`DesktopEnv`) and the backend the actuator drives (`MacBackend`). 1000 pt wide display at scale 2.
    `windows_list` is front to back. `events` records every mouse, key, type and scroll the actuator asked for; a refused flow leaves it empty."""

    def __init__(self, windows: list[dict[str, Any]] | None = None, *, front: str | None = None, ax: bool | None = True,
                 sr: bool | None = True, helper: str | None = None, element: Any = TEXT_AREA, secure: bool = False) -> None:
        self.windows_list = windows if windows is not None else [win()]
        self.front = front if front is not None else (self.windows_list[0]["owner"] if self.windows_list else "")
        self.ax, self.sr, self.helper, self.element, self.secure = ax, sr, helper, element, secure
        self.focus: Any = TEXT_AREA
        self.events: list[tuple] = []
        self.captures = 0
        self.released = 0
        self.locked = False
        self.stop: Any = None
        self.on_type: Any = None

    # ---- DesktopEnv
    def helper_missing(self) -> str | None: return self.helper
    def accessibility(self) -> bool | None: return self.ax
    def screen_recording(self) -> bool | None: return self.sr
    def backend(self) -> "FakeMac": return self

    def windows(self) -> list[WindowRef]:
        return [WindowRef(w["owner"], w["number"], w["pid"], w.get("title", ""), tuple(w["bounds"])) for w in self.windows_list
                if w["layer"] == 0 and w["bounds"][2] * w["bounds"][3] >= 10000.0]

    # ---- MacBackend
    def set_stop_check(self, fn: Any) -> None: self.stop = fn
    def frontmost_app(self) -> str: return self.front
    def screen_locked(self) -> bool: return self.locked
    def backing_scale(self) -> float: return 2.0
    def display_width_pts(self) -> float: return 1000.0
    def secure_input(self) -> bool: return self.secure

    def window_at(self, x: float, y: float) -> dict[str, Any] | None:
        for w in self.windows_list:
            bx, by, bw, bh = w["bounds"]
            if bx <= x < bx + bw and by <= y < by + bh:
                return w
        return None

    def windows_of(self, owner: str) -> list[dict[str, Any]]: return [w for w in self.windows_list if w["owner"] == owner]
    def all_windows_of(self, owner: str) -> list[dict[str, Any]]: return self.windows_of(owner)

    def element_at(self, x: float, y: float) -> Any:
        w = self.window_at(x, y)
        e = self.element(x, y) if callable(self.element) else self.element
        return e if w is not None else None

    def focused_element(self) -> Any: return self.focus
    def read_document(self, app: str) -> str | None: return None
    def mouse(self, kind: str, x: float, y: float) -> None: self.events.append(("mouse", kind, x, y))
    def key(self, keys: list[str]) -> None: self.events.append(("key", tuple(keys)))
    def scroll(self, dx: int, dy: int) -> None: self.events.append(("scroll", dx, dy))
    def release_all(self) -> None: self.released += 1

    def type_text(self, text: str) -> None:
        self.events.append(("type", text))
        if self.on_type:
            self.on_type(text)

    def screenshot_png(self) -> bytes:
        raise AssertionError("a typed task shows the model ONE window; the display must never be captured")

    def window_png(self, number: int) -> bytes:
        self.captures += 1
        w = next(x for x in self.windows_list if x["number"] == number)
        return png(int(w["bounds"][2] * 2), int(w["bounds"][3] * 2))

    def downs(self) -> list[tuple]: return [e for e in self.events if e[0] == "mouse" and e[1] == "down"]
    def typed(self) -> list[str]: return [e[1] for e in self.events if e[0] == "type"]


class Scripted(MockProvider):
    """A computer-use model that plays a fixed list of actions, then says it is done. `on_step(n)` runs while the model is 'thinking'."""

    def __init__(self, script: list[Any], summary: str = "Typed the word into the note", claimed: bool = True, on_step: Any = None) -> None:
        super().__init__("benefits_clean")
        self.script, self.summary, self.claimed, self.on_step = list(script), summary, claimed, on_step
        self.n = 0
        self.frames = 0

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]], **kw: Any) -> Any:
        self.frames += 1
        if self.on_step:
            self.on_step(self.n)
        if self.n >= len(self.script):
            return Done(summary=self.summary, claimed_success=self.claimed)
        a = self.script[self.n]
        self.n += 1
        return a
