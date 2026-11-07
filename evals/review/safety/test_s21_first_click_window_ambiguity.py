"""S-21 (Medium): the Python actuator pins the window at the FIRST click, and its only ambiguity check is `len(windows_of(app)) == 1`, where the real
QuartzBackend.windows_of() ignores windows under 10 000 pt2 and anything not layer 0. A second, small window of the same app (a find panel, a
popover, a tiny document) that is topmost at the point is not counted, so it is pinned and clicked. Runs the REAL QuartzBackend over FakeOS."""
from __future__ import annotations

from fakes import permit
from understudy_agent.models.port import Action
from understudy_agent.tiers.computer_use import ActuatorRefused, MacActuator, QuartzBackend


async def test_a_small_window_of_the_target_app_over_the_point_is_pinned_and_clicked(fake_os):
    fake_os.win("TextEdit", 280, 230, 90, 90, name="Find")                 # 90x90 pt: under the 10 000 pt2 floor, topmost at the click
    fake_os.win("TextEdit", 100, 100, 400, 300, name="Untitled")           # the document the owner has in mind (the only window counted)
    assert len(QuartzBackend().windows_of("TextEdit")) == 1                # so the 'exactly one window' rule is satisfied
    act = MacActuator("TextEdit", backend=QuartzBackend(), env={"UNDERSTUDY_REAL_ACTUATOR": "1"}, permit=permit(), focus_wait_s=0.2, focus_poll_s=0.005)
    await act.screenshot()
    try:
        await act.execute(Action("click", {"x": 600, "y": 520}))           # px / 2 = pt (300, 260): inside the small window, below its title bar
    except ActuatorRefused:
        return
    assert False, f"the click went to the small 'Find' window, not the one document; pinned {act.report.get('pinned_window')}"
