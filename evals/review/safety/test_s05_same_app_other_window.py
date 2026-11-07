"""S-05 (High): both real actuators pin the target APP NAME, never the target WINDOW. Python: _hit() compares kCGWindowOwnerName only;
TS: ownerMatchesTarget(); `{browser:true}` accepts any browser. So the 7 Nov failure repeats at window level: a second window of the same
app (the owner's own browser window, another TextEdit document) that is on top at the click point passes every guard, and typed text goes
to whichever window of that app is key. R2/R3 (a browser, a "dedicated" window) is exactly this case. Fakes only."""
from __future__ import annotations

import pytest

from fakes import FakeBackend, mac
from understudy_agent.models.port import Action
from understudy_agent.tiers.computer_use import ActuatorRefused

SANDBOX = {"owner": "TextEdit", "bounds": (100.0, 100.0, 400.0, 300.0), "layer": 0, "title": "sandbox-practice.txt"}
PERSONAL = {"owner": "TextEdit", "bounds": (250.0, 150.0, 400.0, 300.0), "layer": 0, "title": "bank-recovery-codes.txt"}


async def test_a_click_that_lands_in_another_window_of_the_same_app_is_performed(tmp_path):
    be = FakeBackend(windows=[PERSONAL, SANDBOX])         # the owner's personal document is stacked above the sandbox one
    act = mac(be, tmp_path)
    await act.screenshot()
    # the plan was: click the sandbox document at point (300, 250); the topmost window there is the personal one
    try:
        await act.execute(Action("click", {"x": 600, "y": 500}))
    except ActuatorRefused:
        pass
    assert be.downs() == [], "a real click was sent into a window other than the one the run started in (same app, different window)"


async def test_typing_follows_the_app_not_the_window(tmp_path):
    be = FakeBackend(windows=[SANDBOX])
    act = mac(be, tmp_path)
    await act.screenshot()
    await act.execute(Action("click", {"x": 600, "y": 500}))              # verified click in the sandbox document
    be.windows = [PERSONAL, SANDBOX]                                       # another document of the same app comes to the front
    try:
        await act.execute(Action("type", {"text": "hello"}))
    except ActuatorRefused:
        pass
    assert be.typed_chunks() == [], "text was typed after the window under the verified click point changed identity"
