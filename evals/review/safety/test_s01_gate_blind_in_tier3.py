"""S-01 (Critical, fixed): the gate could not see what a tier-3 pointer click, Enter key or typed newline will do (the provider sends
x, y, button only; nothing read the element under the point). Fake model, fake screen that knows where its Submit button is."""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import ComputerUse, blank_png
from understudy_agent.tiers.safety import Guard


class ButtonScreen:
    """A 1280x720 'screen' whose only button, 'Submit application', is at (400..600, 300..340) and holds the keyboard focus."""
    scale = 1.0

    def __init__(self): self.pressed, self.typed = [], ""
    async def screenshot(self): return blank_png()
    async def release_all(self): return None

    async def execute(self, a):
        if a.kind == "click" and 400 <= a.args["x"] < 600 and 300 <= a.args["y"] < 340: self.pressed.append("Submit application")
        if a.kind == "key" and [k.lower() for k in a.args["keys"]] == ["enter"]: self.pressed.append("Submit application (Enter)")
        if a.kind == "type": self.typed += a.args["text"]; self.pressed += ["Submit application (newline)"] if "\n" in a.args["text"] else []


class Scripted:
    def __init__(self, *acts): self.acts = list(acts)
    def computer_step(self, goal, shot, history, **kw): return self.acts[min(len(history), len(self.acts) - 1)]


def run(*acts):
    guard = Guard(MockProvider(), run_id="r_s01", mode="model_driven", audit=AuditLog(), queue=ApprovalQueue(), denylist=Denylist())
    screen = ButtonScreen()
    async def verify(): return True
    async def go():
        try:
            await ComputerUse(Scripted(*acts, Done("done", True)), screen, guard, navigator="n").run("fill in the form", verify)
        except GateStop:
            pass
    return screen, go()


async def test_a_pixel_click_on_the_submit_button_is_not_gated():
    screen, coro = run(Action("click", {"x": 500, "y": 320, "button": "left"}))   # exactly the shape OpenAIProvider._to_action emits
    await coro
    assert screen.pressed == [], f"the irreversible control was pressed with no human click: {screen.pressed}"


async def test_enter_on_a_focused_submit_button_is_not_gated():
    screen, coro = run(Action("key", {"keys": ["Enter"]}))
    await coro
    assert screen.pressed == [], f"Enter activated the focused Submit button ungated: {screen.pressed}"


async def test_typed_newline_is_an_enter_key_that_no_layer_classifies():
    screen, coro = run(Action("type", {"text": "claim ref 1234\n"}))
    await coro
    assert "\n" not in screen.typed, "a newline inside a type action reached the actuator (it is an Enter press = implicit form submit)"
