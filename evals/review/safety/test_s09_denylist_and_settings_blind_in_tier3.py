"""S-09 (High): in tier 3 the SafetyPipeline is never told which page it is acting on. ComputerUse calls guard.authorise(..., url=None), so
`denylist: current_page_denied` (the worker's own never-go list) and layer 8 `protected_target` (Understudy's control pages on :7700, :7710,
:5173) can never fire for clicks, typing or keys. Tier 2 passes the URL; tier 3 clicks links, so it can walk onto a denylisted site (or the
control API's HTML pages) and keep acting there. BrowserPageActuator.page.url is available; MacActuator has no URL at all. Fakes only. (After the S-01 fix an unreadable click is queued, so the fake page answers the DOM read with a plain button: that unmasks this check.)"""
from __future__ import annotations

import pytest

from fakes import Scripted, always_true, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.computer_use import BrowserPageActuator, ComputerUse, blank_png


class FakePage:
    def __init__(self, url): self.url, self.clicked, self.mouse = url, [], self
    async def wait_for_load_state(self, *a, **k): return None
    async def screenshot(self, **k): return blank_png()
    async def click(self, x, y): self.clicked.append((x, y))
    async def evaluate(self, js, arg=None): return {"ok": True, "label": "Continue", "role": "button", "field": None}   # trusted DOM read


@pytest.mark.parametrize("url,deny", [("https://bank.example/login", True), ("http://127.0.0.1:7700/docs", False), ("http://127.0.0.1:7710/docs", False)])
async def test_a_click_on_a_forbidden_page_is_performed(url, deny):
    page = FakePage(url)
    guard = make_guard(denylist=Denylist([{"kind": "domain", "value": "bank.example"}]) if deny else Denylist())
    cu = ComputerUse(Scripted(Action("click", {"x": 10, "y": 10, "label": "Continue"}), Done("done", True)), BrowserPageActuator(page), guard, navigator="n", stall_limit=3)
    try:
        await cu.run("g", always_true)
    except BaseException:
        pass
    assert page.clicked == [], f"a real click was made on {url}, a page the worker denied / Understudy protects"


async def test_control_a_click_on_an_ordinary_page_is_performed():
    page = FakePage("https://calc-a.example/step/1")        # proves the harness reaches the actuator, so the tests above cannot pass vacuously
    cu = ComputerUse(Scripted(Action("click", {"x": 10, "y": 10}), Done("done", True)), BrowserPageActuator(page), make_guard(), navigator="n", stall_limit=3)
    try:
        await cu.run("g", always_true)
    except BaseException:
        pass
    assert page.clicked == [(10, 10)]
