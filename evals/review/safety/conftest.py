"""Hermetic harness for the actuator safety review. Nothing here touches the real desktop, the network or a model.

* every test gets its own data dir (the shared guard in evals/review/conftest.py also blocks live ports and checks data/KILL)
* Quartz and AppKit are replaced by TRIPWIRE modules: importing either and using it raises, so no test can post a real event
* subprocess.run refuses screencapture / osascript / cliclick unless a FakeOS is installed (it then serves fake bytes)
"""
from __future__ import annotations

import functools
import struct
import subprocess
import sys
import types
import zlib
from pathlib import Path

import pytest

REAL_DATA = Path(__file__).resolve().parents[3] / "data"


@functools.lru_cache(maxsize=8)
def png_of_width(w: int, h: int | None = None) -> bytes:
    """A flat grey screenshot, w px wide and (by default) 0.65 w tall, like a real display capture (the S-10 fix validates against its size)."""
    h = h or max(1, round(w * 0.65))

    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = (b"\x00" + b"\xf5" * w) * h
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class _FakeQuartz(types.ModuleType):
    """Fake Quartz that tolerates the constants and event builders the real backend grows over time: any kCG constant is a stable int, any other
    CG function we did not model records a generic event. Modelled functions (window list, post, flags, keyboard, mouse) are set explicitly."""

    def __getattr__(self, name: str):
        if name.startswith("kCG"):
            return 100 + (sum(map(ord, name)) % 900)
        if name.startswith("CG"):
            return lambda *a, **k: {"kind": "other", "fn": name}
        raise AttributeError(name)


class _Trip(types.ModuleType):
    def __getattr__(self, name: str):  # pragma: no cover - only fires if a test would reach the real OS
        raise AssertionError(f"TRIPWIRE: a review test tried to use the real {self.__name__}.{name}")


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("AGENT_PORT", "1")
    monkeypatch.delenv("UNDERSTUDY_REAL_ACTUATOR", raising=False)
    for name in ("Quartz", "AppKit", "ApplicationServices"):
        monkeypatch.setitem(sys.modules, name, _Trip(name))
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name in {"screencapture", "osascript", "cliclick"}:
            raise AssertionError(f"TRIPWIRE: subprocess.run({args[0]!r}) from a review test")
        return real_run(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", guarded)
    had_kill = (REAL_DATA / "KILL").exists()
    yield
    if not had_kill:
        assert not (REAL_DATA / "KILL").exists(), "a review test left data/KILL in the REAL data dir"


class FakeOS:
    """A fake macOS: a window list (front to back), a keyboard that records events, and screencapture bytes."""

    def __init__(self, width_pts: float = 1000.0, scale: float = 2.0, front: str = "TextEdit") -> None:
        self.windows: list[dict] = []
        self.posted: list[dict] = []
        self.flag_calls: list[int] = []
        self.width_pts, self.scale, self.front, self.locked = width_pts, scale, front, False
        text_area = {"AXRole": "AXTextArea", "AXDescription": "text entry area"}
        self.ax_focused = text_area
        self.ax_at = lambda x, y: text_area            # override per test: the accessibility element under a point (None = unreadable)

    def win(self, owner: str, x: float, y: float, w: float, h: float, layer: int = 0, alpha: float = 1.0, name: str = "") -> None:
        self.windows.append({"kCGWindowOwnerName": owner, "kCGWindowLayer": layer, "kCGWindowAlpha": alpha,
                             "kCGWindowName": name, "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h}})

    def install(self, monkeypatch) -> "FakeOS":
        me = self
        Q = _FakeQuartz("Quartz")
        Q.kCGWindowListOptionOnScreenOnly, Q.kCGWindowListExcludeDesktopElements, Q.kCGNullWindowID = 1, 16, 0
        Q.kCGEventMouseMoved, Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp = 5, 1, 2
        Q.kCGMouseButtonLeft, Q.kCGHIDEventTap, Q.kCGScrollEventUnitPixel = 0, 0, 0
        Q.CGWindowListCopyWindowInfo = lambda opts, wid: list(me.windows)
        Q.CGEventCreateMouseEvent = lambda src, t, pt, b: {"kind": "mouse", "type": t, "pt": tuple(pt), "button": b}
        Q.CGEventCreateKeyboardEvent = lambda src, k, down: {"kind": "key", "down": down, "src": src, "text": "", "flags": None}
        Q.CGEventKeyboardSetUnicodeString = lambda ev, n, s: ev.__setitem__("text", s)
        Q.CGEventSetFlags = lambda ev, f: (ev.__setitem__("flags", f), me.flag_calls.append(f))
        Q.CGEventPost = lambda tap, ev: me.posted.append(ev)
        Q.CGSessionCopyCurrentDictionary = lambda: {"CGSSessionScreenIsLocked": int(me.locked)}
        Q.CGDisplayIsAsleep = lambda d: 0
        Q.CGMainDisplayID = lambda: 1
        Q.CGDisplayBounds = lambda d: types.SimpleNamespace(size=types.SimpleNamespace(width=me.width_pts, height=700.0))
        Q.CGEventGetLocation = lambda ev: types.SimpleNamespace(x=0.0, y=0.0)
        Q.CGEventCreate = lambda src: {}
        A = types.ModuleType("AppKit")
        app = types.SimpleNamespace(localizedName=lambda: me.front)
        A.NSWorkspace = types.SimpleNamespace(sharedWorkspace=lambda: types.SimpleNamespace(frontmostApplication=lambda: app))
        A.NSScreen = types.SimpleNamespace(mainScreen=lambda: types.SimpleNamespace(backingScaleFactor=lambda: me.scale))
        AS = types.ModuleType("ApplicationServices")                      # the accessibility reads the gate now relies on (fake)
        AS.AXUIElementCreateSystemWide = lambda: "system-wide"
        AS.AXUIElementCopyElementAtPosition = lambda sysw, x, y, _o: (0, me.ax_at(x, y)) if me.ax_at(x, y) is not None else (-1, None)
        def copy_attr(el, name, _o):
            if el == "system-wide":
                return (0, me.ax_focused) if name == "AXFocusedUIElement" and me.ax_focused is not None else (-1, None)
            return (0, el[name]) if isinstance(el, dict) and name in el else (-1, None)
        AS.AXUIElementCopyAttributeValue = copy_attr
        monkeypatch.setitem(sys.modules, "Quartz", Q)
        monkeypatch.setitem(sys.modules, "AppKit", A)
        monkeypatch.setitem(sys.modules, "ApplicationServices", AS)

        def fake_run(args, *a, **k):
            assert Path(str(args[0])).name == "screencapture", f"unexpected subprocess {args[0]!r}"
            Path(args[-1]).write_bytes(png_of_width(int(me.width_pts * me.scale)))
            return subprocess.CompletedProcess(args, 0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        return self

    def typed(self) -> str:
        return "".join(e["text"] for e in self.posted if e["kind"] == "key" and e["down"])

    def clicks(self) -> list[dict]:
        return [e for e in self.posted if e["kind"] == "mouse" and e["type"] == 1]


@pytest.fixture
def fake_os(monkeypatch) -> FakeOS:
    return FakeOS().install(monkeypatch)
