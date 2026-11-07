"""AGENTIC-3 item 1 inside the real tier-3 loop: a goal check that fails to run is retried, the ACTION is performed once.

The model proposes one click. The goal check (a model call) fails twice and then answers. The loop must call the computer-use model once
for that step, perform the click once, and spend no extra step. When every try fails the click is not performed at all and the run stops
at the gate, with the error class on the gate-stop row. Offline: a simulated actuator, a scripted model, a fake clock and sleeper.
"""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.errors import ProviderError
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.orchestrator import instrument_guard
from understudy_agent.queue import ApprovalQueue
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator, TargetRead
from understudy_agent.tiers.safety import Guard

HOST = "127.0.0.1:7801"
URL = f"http://{HOST}/"
CALCULATE = TargetRead("Calculate", "button", URL, None, ("submit_control",))


class CheckThatFailsFirst(MockProvider):
    """The goal-check call raises `failures` times and then behaves like the mock; every call is counted by method."""

    def __init__(self, failures: int, error: Exception | None = None) -> None:
        super().__init__("reader_basic")
        self.failures, self.error, self.tally = failures, error or ProviderError("APITimeoutError: Request timed out."), []

    def check(self, prompt, schema):
        self.tally.append("check")
        if self.failures > 0:
            self.failures -= 1
            raise self.error
        return {"serves_goal": True, "reason": "ordinary form step"}


class OneClickThenDone:
    name = "script"

    def __init__(self) -> None:
        self.calls = 0

    def computer_step(self, goal, shot, history, **kw):
        self.calls += 1
        return Action("click", {"x": 100, "y": 100}) if self.calls == 1 else Done("done", True)


def build(tmp_path, port):
    audit = AuditLog(tmp_path / "audit.jsonl")
    guard = Guard(port, run_id="r_retry", mode="model_driven", audit=audit, queue=ApprovalQueue(tmp_path / "q", audit=audit),
                  recorded_hosts=frozenset({HOST}))
    slept: list[float] = []
    guard.pipe.drift._sleep = slept.append
    rows: list[dict] = []
    instrument_guard(guard, "nav-x", rows, frozenset({HOST}))
    return guard, rows, slept


async def test_a_check_that_fails_twice_then_answers_does_not_repeat_the_click(tmp_path):
    port = CheckThatFailsFirst(failures=2)
    guard, rows, slept = build(tmp_path, port)
    model, act = OneClickThenDone(), SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    res = await ComputerUse(model, act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert res.outcome == "done"
    assert [a.kind for a in act.actions] == ["click"]                  # the action ran ONCE
    assert model.calls == 2                                            # one step for the click, one for the Done: no step was re-asked
    assert port.tally == ["check"] * 3                                 # the check ran three times: one try and two retries
    assert slept == [0.5, 1.5] and rows == []                          # a recovered check is no gate stop at all
    assert guard.pipe.drift.stats()["recovered"] == 1


async def test_when_every_try_fails_the_click_is_not_performed_and_the_stop_says_why(tmp_path):
    port = CheckThatFailsFirst(failures=99)
    guard, rows, slept = build(tmp_path, port)
    model, act = OneClickThenDone(), SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    with pytest.raises(GateStop):
        await ComputerUse(model, act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert act.actions == []                                           # nothing was done: fail closed
    assert model.calls == 1 and port.tally == ["check"] * 3 and slept == [0.5, 1.5]
    assert len(rows) == 1 and rows[0]["codes"] == ["drift:off_goal_unavailable"]
    assert rows[0]["check_error"] == "timeout" and rows[0]["check_attempts"] == 3


async def test_a_verdict_of_off_goal_is_one_call_and_still_stops_the_click(tmp_path):
    class Says(CheckThatFailsFirst):
        def check(self, prompt, schema):
            self.tally.append("check")
            return {"serves_goal": False, "reason": "unrelated"}

    port = Says(failures=0)
    guard, rows, slept = build(tmp_path, port)
    act = SimulatedActuator(targets=CALCULATE)

    async def verify():
        return True

    with pytest.raises(GateStop):
        await ComputerUse(OneClickThenDone(), act, guard, navigator="nav-x", stall_limit=5).run("press calculate", verify)
    assert act.actions == [] and port.tally == ["check"] and slept == []
    assert rows[0]["codes"] == ["drift:off_goal_model"] and rows[0]["check_error"] is None
