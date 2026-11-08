"""The real backend's hit test skips the app's own full-display click-through overlay (it is never the click's target) and nothing else that covers the display.
The overlay is named for the app that owns it: the app is called Knack now, and a stale name left every point refused with "belongs to 'Knack'"."""
from __future__ import annotations

import sys
import types

import pytest

from understudy_agent.tiers.computer_use import QuartzBackend

DISPLAY = (1728.0, 1117.0)


def _win(owner: str, layer: int, x: float, y: float, w: float, h: float, number: int) -> dict:
    return {"kCGWindowOwnerName": owner, "kCGWindowLayer": layer, "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
            "kCGWindowAlpha": 1.0, "kCGWindowNumber": number, "kCGWindowOwnerPID": 100 + number, "kCGWindowName": "w"}


@pytest.fixture()
def fake_quartz(monkeypatch):
    windows: list[dict] = []
    q = types.ModuleType("Quartz")
    q.kCGWindowListOptionOnScreenOnly = 1
    q.kCGWindowListExcludeDesktopElements = 16
    q.kCGNullWindowID = 0
    q.CGMainDisplayID = lambda: 1
    q.CGDisplayBounds = lambda _id: types.SimpleNamespace(size=types.SimpleNamespace(width=DISPLAY[0], height=DISPLAY[1]))
    q.CGWindowListCopyWindowInfo = lambda _opts, _id: list(windows)
    monkeypatch.setitem(sys.modules, "Quartz", q)
    return windows


def _top(fake_quartz, x=1004.0, y=471.0):
    return QuartzBackend.__new__(QuartzBackend).window_at(x, y)


def test_the_apps_own_full_display_overlay_is_not_the_click_target(fake_quartz):
    fake_quartz += [_win("Knack", 1000, 0, 0, *DISPLAY, 1), _win("TextEdit", 0, 703, 199, 603, 505, 2)]
    assert _top(fake_quartz)["owner"] == "TextEdit"


def test_another_apps_full_display_window_still_blocks_the_click(fake_quartz):
    fake_quartz += [_win("SomeBanner", 1000, 0, 0, *DISPLAY, 1), _win("TextEdit", 0, 703, 199, 603, 505, 2)]
    assert _top(fake_quartz)["owner"] == "SomeBanner"


def test_the_apps_own_normal_window_still_blocks_the_click(fake_quartz):
    fake_quartz += [_win("Knack", 0, 173, 97, 1382, 839, 1), _win("TextEdit", 0, 703, 199, 603, 505, 2)]
    assert _top(fake_quartz)["owner"] == "Knack"
