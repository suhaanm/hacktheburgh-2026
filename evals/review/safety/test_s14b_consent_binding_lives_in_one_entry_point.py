"""S-14b (Medium, found re-testing the S-14 fix): the owner-token and unattended-consent checks live ONLY in run_desktop_task. (a) ComputerUse +
MacActuator built directly (what a navigator's actuator_factory or an R3 script does) skips them: an unattended Guard with no consent and no token
still sent a real click (fixed: MacActuator now needs a RunPermit). (b) a wrapped actuator going through run_desktop_task is refused (passes: a control). Fix for (a): enforce in
MacActuator itself (constructor takes a RunPermit that consumed the token; execute refuses without it), so no entry point can forget. When that lands
the harness `fakes.mac()` must pass a permit. Fakes only."""
from __future__ import annotations

from fakes import FakeBackend, Scripted, always_true, mac, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.offhours import FakeScreenState, ScreenGuardedActuator, run_desktop_task
from understudy_agent.tiers.computer_use import ComputerUse

CLICK = Action("click", {"x": 600, "y": 500})


async def test_a_directly_built_real_actuator_needs_no_consent_and_no_token(tmp_path):
    be = FakeBackend()
    guard = make_guard(unattended=True, routine_id="rt_nightly")        # no consent.json, no owner token anywhere
    try:
        await ComputerUse(Scripted(CLICK, Done("done", True)), mac(be, tmp_path, no_permit=True), guard, navigator="n").run("g", always_true)
    except BaseException:
        pass
    assert be.downs() == [], "a real click was sent by an unattended run with no consent record and no owner token (actuator built directly)"


async def test_a_wrapped_real_actuator_skips_the_check_in_run_desktop_task(tmp_path):
    be = FakeBackend()
    wrapped = ScreenGuardedActuator(mac(be, tmp_path), FakeScreenState())
    try:
        await run_desktop_task("g", model=Scripted(CLICK, Done("done", True)), guard=make_guard(unattended=True, routine_id="rt_nightly"), actuator=wrapped,
                               screen=FakeScreenState(), is_current=lambda: True, verify=always_true)
    except BaseException:
        pass
    assert be.downs() == [], "a real click was sent through run_desktop_task with a wrapped actuator and no consent or token"
