"""S-07 (Medium): MacActuator.execute() never reads args["button"] or args["hold_keys"]. The validated action can say right button, cmd/shift
held, the actuator performs a plain left click and reports success. A right click meant to open a context menu instead activates whatever is
under the point; a cmd-click meant to open in a new tab navigates in place. Fakes only."""
from __future__ import annotations

import pytest

from fakes import FakeBackend, mac
from understudy_agent.models.port import Action
from understudy_agent.tiers.computer_use import ActuatorRefused


@pytest.mark.parametrize("extra", [{"button": "right"}, {"button": "left", "hold_keys": ["cmd"]}, {"button": "left", "hold_keys": ["shift"]}])
async def test_the_requested_button_and_modifiers_are_honoured_or_refused(tmp_path, extra):
    be = FakeBackend()
    act = mac(be, tmp_path)
    await act.screenshot()
    try:
        await act.execute(Action("click", {"x": 600, "y": 500, **extra}))
    except ActuatorRefused:
        return                                                          # refusing what it cannot do is acceptable
    assert False, f"{extra} was silently turned into a plain left click: {be.events}"
