"""S-03 (High): a supervisor stop / yield-to-human / UI Stop must not let an action that is already in flight finish. Originally ComputerUse
checked is_current() only before the multi-second model call and MacActuator knew nothing of the supervisor (only the KILL file), so a
120-character `type` kept typing chunk after chunk into the app the worker had just taken over. Each test first runs a CONTROL (no stop) to prove
the action path is reachable, so a gate that blocks the click cannot make the test pass vacuously. Fakes only."""
from __future__ import annotations

from fakes import FakeBackend, Scripted, always_true, mac, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator, TargetRead

CLICK = Action("click", {"x": 600, "y": 500})


async def drive(model, act, stopped):
    try:
        await ComputerUse(model, act, make_guard(), navigator="n", is_current=lambda: not stopped["v"]).run("g", always_true)
    except BaseException:
        pass


async def test_a_stop_that_arrives_while_the_model_is_thinking_still_runs_the_action(tmp_path):
    ctl = FakeBackend()
    await drive(Scripted(CLICK, Done("done", True)), mac(ctl, tmp_path), {"v": False})
    assert ctl.downs(), "CONTROL: with no stop the click must reach the actuator, else this test proves nothing"
    stopped, be = {"v": False}, FakeBackend()
    await drive(Scripted(CLICK, Done("done", True), before=lambda n: stopped.update(v=True)), mac(be, tmp_path), stopped)
    assert be.downs() == [], f"an action was executed after the run had been stopped: {be.events}"


async def test_a_stop_during_a_long_type_does_not_stop_the_remaining_chunks(tmp_path):
    stopped, be = {"v": False}, FakeBackend()
    be.on_type = lambda text: stopped.update(v=len(be.typed_chunks()) >= 2)             # the worker presses Stop during the 2nd chunk
    await drive(Scripted(CLICK, Action("type", {"text": "x" * 120}), Done("done", True)), mac(be, tmp_path), stopped)
    assert len(be.typed_chunks()) >= 2, "CONTROL: the harness must reach the typing loop"
    assert len(be.typed_chunks()) <= 3, f"{len(be.typed_chunks())} chunks ({sum(map(len, be.typed_chunks()))} chars) typed after Stop"
