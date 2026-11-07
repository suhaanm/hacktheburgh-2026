"""S-06 (High): QuartzBackend.window_at() skips every window whose layer is not 0, so anything that floats above normal windows and DOES
take clicks is invisible to the hit test: the Dock, notification banners, always-on-top panels, system permission/alert dialogs, pop-up
menus. The TS probe (WINDOW_AT_JXA) keeps all layers and skips only own/Dock/Window-Server windows that cover the whole display; the
Python one does not. Runs the REAL QuartzBackend code against a fake Quartz module (conftest.FakeOS): no desktop is touched."""
from __future__ import annotations

import pytest

from fakes import permit
from understudy_agent.models.port import Action
from understudy_agent.tiers.computer_use import ActuatorRefused, MacActuator, QuartzBackend


@pytest.mark.parametrize("owner,layer", [("Dock", 20), ("NotificationCenter", 23), ("UserNotificationCenter", 8), ("Floating Panel App", 3), ("Window Server", 24)])
def test_a_window_above_the_target_that_would_take_the_click_is_reported(fake_os, owner, layer):
    fake_os.win(owner, 200, 150, 100, 100, layer=layer)       # front-most, covers point (250, 170)
    fake_os.win("TextEdit", 100, 100, 400, 300)
    hit = QuartzBackend().window_at(250.0, 170.0)
    assert hit is not None and hit["owner"] == owner, f"hit test reported {hit and hit['owner']!r}; the click would land in {owner!r} (layer {layer})"


async def test_end_to_end_a_click_under_a_notification_banner_is_sent(fake_os):
    fake_os.win("NotificationCenter", 200, 150, 100, 100, layer=23)    # a banner with a Reply / Close / Open button under the point
    fake_os.win("TextEdit", 100, 100, 400, 300)
    act = MacActuator("TextEdit", backend=QuartzBackend(), env={"UNDERSTUDY_REAL_ACTUATOR": "1"}, permit=permit(), focus_wait_s=0.2, focus_poll_s=0.005)
    await act.screenshot()
    try:
        await act.execute(Action("click", {"x": 500, "y": 340}))       # px / 2 = pt (250, 170)
    except ActuatorRefused:
        pass
    assert fake_os.clicks() == [], "a real mouse-down was posted at a point covered by another process's banner"
