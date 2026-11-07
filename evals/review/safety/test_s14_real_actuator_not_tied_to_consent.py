"""S-14 (Medium, structural): nothing in code ties the real desktop actuator to the unattended-run consent. run_desktop_task() takes any actuator
and any Guard; make_actuator(real=True) needs only UNDERSTUDY_REAL_ACTUATOR=1, a process-wide, sticky switch. An unattended Guard
(unattended=True, routine_id set) with NO consent.json for that routine still performs real clicks. Today no caller does this (the nightly runner
is browser-only), but the first R4 / overnight script that wires them will have no refusal to hit. Fakes only."""
from __future__ import annotations

from fakes import FakeBackend, Scripted, always_true, mac, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.offhours import FakeScreenState, run_desktop_task


async def test_an_unattended_real_run_without_a_consent_record_performs_a_real_click(tmp_path):
    be = FakeBackend()
    guard = make_guard(unattended=True, routine_id="rt_nightly")        # data/routines/rt_nightly/consent.json does not exist
    try:
        await run_desktop_task("g", model=Scripted(Action("click", {"x": 600, "y": 500}), Done("done", True)), guard=guard,
                               actuator=mac(be, tmp_path), screen=FakeScreenState(), is_current=lambda: True, verify=always_true)
    except BaseException:
        pass
    assert be.downs() == [], "a real click was sent in an unattended run that has no consent record and no per-routine opt-in"
