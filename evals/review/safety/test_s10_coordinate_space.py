"""S-10 (Medium): coordinates are validated in the wrong space. ComputerUse validates against screenshot_size (default 1280x720), but the
provider returns coordinates in the ORIGINAL screenshot's pixels (3456x2234 on this Mac, 2000x1 here): run_desktop_task never passes the
real size, so every click right of x=1280 or below y=720 px (63 percent of a Retina screen) is rejected as off-screen, the rest is not
checked against the display. MacActuator itself accepts negative or beyond-display points if some window owned by the target is there.
Fakes only."""
from __future__ import annotations

from fakes import FakeBackend, Scripted, always_true, mac, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.computer_use import ActuatorRefused, ComputerUse

RIGHT_SIDE = [{"owner": "TextEdit", "bounds": (600.0, 100.0, 300.0, 300.0), "layer": 0}]       # px (1200..1800, 200..800)


async def test_a_valid_click_in_the_target_window_on_the_right_of_the_screen_is_rejected_as_off_screen(tmp_path):
    be = FakeBackend(windows=RIGHT_SIDE)
    cu = ComputerUse(Scripted(Action("click", {"x": 1500, "y": 500}), Done("done", True)), mac(be, tmp_path), make_guard(), navigator="n",
                     stall_limit=3)
    try:
        await cu.run("g", always_true)
    except BaseException:
        pass
    assert be.downs(), "a click inside the target window (px 1500,500 of a 2000 px wide screenshot) never reached the actuator"


async def test_the_actuator_itself_accepts_a_point_outside_the_screenshot(tmp_path):
    be = FakeBackend(windows=[{"owner": "TextEdit", "bounds": (-500.0, 100.0, 400.0, 300.0), "layer": 0}])   # a display left of the main one
    act = mac(be, tmp_path)
    await act.screenshot()
    try:
        await act.execute(Action("click", {"x": -600, "y": 500}))
    except ActuatorRefused:
        return
    assert False, f"a click at a NEGATIVE pixel coordinate was posted (outside the screenshot the model saw): {be.events}"
