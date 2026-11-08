"""AGENTIC-3 round 6: a transient provider failure on the computer-use call no longer costs a whole attempt, or the household.

Found in Gemini dev round 6: one `GeminiHTTPError` on the model call of the cliff step ended that step at once (`cliff_check` failed),
no calculator was affected, and the household failed at the critic ("expert step cliff_c was not done"). A failed model call means
nothing was done on the screen, so asking again cannot repeat an action: the loop asks again (at most twice, fixed waits) when the class
of the failure says "try again", and raises everything else unchanged. Offline: scripted models, a simulated actuator, a fake sleeper.
"""
from __future__ import annotations

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.errors import ModelRefusal, ProviderError, SchemaViolation
from understudy_agent.models.gemini_http import GeminiHTTPError
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done, SafetyStop
from understudy_agent.queue import ApprovalQueue
from understudy_agent.live_eval import BudgetExceeded, CacheMiss
from understudy_agent.tiers.base import StepEvent
from understudy_agent.tiers.computer_use import ComputerUse, ProviderSafetyStop, SimulatedActuator, TargetRead
from understudy_agent.tiers.safety import Guard

HOST = "127.0.0.1:7802"
URL = f"http://{HOST}/"
BUTTON = TargetRead("Next", "button", URL, None, ())


class Flaky:
    """Fails with each error in `errors` (one per call), then clicks once and says DONE. Every call is counted."""

    name = "script"

    def __init__(self, errors) -> None:
        self.errors, self.calls, self.answered = list(errors), 0, 0

    def computer_step(self, goal, shot, history, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        self.answered += 1
        return Action("click", {"x": 100, "y": 100}) if self.answered == 1 else Done("done", True)


def build(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    guard = Guard(MockProvider("reader_basic"), run_id="r_mr", mode="model_driven", audit=audit,
                  queue=ApprovalQueue(tmp_path / "q", audit=audit), recorded_hosts=frozenset({HOST}))
    return guard


async def run(tmp_path, model, *, is_current=lambda: True, retries=2):
    guard = build(tmp_path)
    slept: list[float] = []
    events: list[StepEvent] = []

    async def sleeper(s: float) -> None:
        slept.append(s)

    act = SimulatedActuator(targets=BUTTON)
    cu = ComputerUse(model, act, guard, navigator="nav-x", stall_limit=5, emit=events.append, is_current=is_current,
                     model_retries=retries, sleep=sleeper)

    async def verify():
        return True

    try:
        res = await cu.run("press next", verify)
        err = None
    except BaseException as exc:  # noqa: BLE001
        res, err = None, exc
    return res, err, act, slept, events, cu


@pytest.mark.parametrize("err,cls", [
    (GeminiHTTPError("api", "x", 503), "transport"),
    (GeminiHTTPError("api", "x", 500), "transport"),
    (GeminiHTTPError("rate_limit", "x", 429), "rate_limit"),
    (GeminiHTTPError("timeout", "x"), "timeout"),
    (GeminiHTTPError("network", "x"), "transport"),
    (GeminiHTTPError("empty", "x"), "invalid_answer"),
    (GeminiHTTPError("incomplete", "x"), "invalid_answer"),
    (SchemaViolation("the reply did not match the schema"), "invalid_answer"),
    (ProviderError("APITimeoutError: Request timed out."), "timeout"),
])
async def test_a_transient_failure_is_asked_again_and_the_action_runs_once(tmp_path, err, cls):
    model = Flaky([err])
    res, exc, act, slept, events, cu = await run(tmp_path, model)
    assert exc is None and res.outcome == "done"
    assert [a.kind for a in act.actions] == ["click"]                  # the action ran ONCE: only the answer was lost
    assert model.calls == 3                                            # the failed call, its ask again, and the Done
    assert slept == [0.5] and res.model_retries == 1 and res.model_retry_classes == [cls]
    assert cu.model_retry_classes == [cls]
    assert [e.action for e in events if e.action == "model_retry"] == ["model_retry"]
    assert cls in next(e.detail for e in events if e.action == "model_retry") and "x" != next(e.detail for e in events if e.action == "model_retry")


async def test_two_failures_in_a_row_use_both_waits_and_a_third_is_raised_unchanged(tmp_path):
    model = Flaky([GeminiHTTPError("api", "a", 503), GeminiHTTPError("timeout", "b")])
    res, exc, act, slept, events, _ = await run(tmp_path, model)
    assert exc is None and res.model_retries == 2 and slept == [0.5, 1.5] and res.model_retry_classes == ["transport", "timeout"]

    third = GeminiHTTPError("api", "still down", 503)
    model = Flaky([GeminiHTTPError("api", "a", 503), GeminiHTTPError("api", "b", 503), third])
    res, exc, act, slept, events, cu = await run(tmp_path, model)
    assert exc is third                                                # the last failure, exactly as the provider raised it
    assert model.calls == 3 and slept == [0.5, 1.5] and act.actions == []
    assert cu.model_retry_classes == ["transport", "transport"]


@pytest.mark.parametrize("err", [
    GeminiHTTPError("auth", "key refused", 401),
    GeminiHTTPError("auth", "forbidden", 403),
    GeminiHTTPError("blocked", "blocked by policy"),
    GeminiHTTPError("api", "bad request", 400),
    ModelRefusal("the model refused"),
    RuntimeError("something nothing classifies"),
    BudgetExceeded("estimated cost 12.00 USD reached the budget of 12.00"),
    CacheMiss("cache-only mode: this prompt is not in the cache"),
])
async def test_a_failure_that_will_not_change_is_raised_at_once_and_not_asked_again(tmp_path, err):
    model = Flaky([err])
    res, exc, act, slept, events, cu = await run(tmp_path, model)
    assert exc is err and model.calls == 1 and slept == [] and act.actions == []
    assert cu.model_retry_classes == [] and not [e for e in events if e.action == "model_retry"]


async def test_a_stop_is_not_waited_out(tmp_path):
    state = {"current": True}

    class StopsWhileFailing(Flaky):
        def computer_step(self, goal, shot, history, **kw):
            state["current"] = False                                   # the worker pressed Stop while the model call failed
            return super().computer_step(goal, shot, history, **kw)

    model = StopsWhileFailing([GeminiHTTPError("api", "x", 503)])
    res, exc, act, slept, events, _ = await run(tmp_path, model, is_current=lambda: state["current"])
    assert model.calls == 1 and slept == [] and act.actions == []      # no wait, no second ask; the loop's own stop handling ends the run


async def test_retries_can_be_switched_off(tmp_path):
    err = GeminiHTTPError("api", "x", 503)
    model = Flaky([err])
    res, exc, act, slept, events, cu = await run(tmp_path, model, retries=0)
    assert exc is err and model.calls == 1 and slept == []


async def test_a_provider_safety_check_is_never_asked_again(tmp_path):
    class Checks:
        name = "script"
        calls = 0

        def computer_step(self, goal, shot, history, **kw):
            self.calls += 1
            return SafetyStop([{"code": "require_confirmation"}])

    model = Checks()
    res, exc, act, slept, events, _ = await run(tmp_path, model)
    assert isinstance(exc, ProviderSafetyStop) and model.calls == 1 and slept == [] and act.actions == []


# ----------------------------------------------------------------------------- the cliff step, end to end on a real sandbox page
async def _nav_with_flaky_cliff(host, cluster, tmp_path, errors, result=None):
    from understudy_agent.navigator import CLIFF_GOAL, CalculatorJob, Navigator
    from understudy_agent.sandbox_sites.households import generate_households
    from understudy_agent.security.denylist import Denylist
    from understudy_agent.tiers.heuristic import DomOracleComputerModel

    class Model(DomOracleComputerModel):
        def __init__(self) -> None:
            super().__init__()
            self.cliff_calls, self.errors = 0, list(errors)

        def computer_step(self, goal, screenshot, history, **kw):
            if goal.startswith(CLIFF_GOAL[:40]) or CLIFF_GOAL[:40] in goal:
                self.cliff_calls += 1
                if self.errors:
                    raise self.errors.pop(0)
            return super().computer_step(goal, screenshot, history, **kw)

    audit = AuditLog(tmp_path / "audit.jsonl")
    q = ApprovalQueue(tmp_path / "queue", audit=audit)
    model = Model()
    guard = Guard(model, run_id="r_cl", routine_id=None, audit=audit, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    events: list[StepEvent] = []
    nav = Navigator("nav-c", context=ctx, model=model, guard=guard, base_url=cluster.urls["c"], query="", emit=events.append,
                    use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=False)
    res = await nav.run(CalculatorJob("c", generate_households(20, 7001)[1].params()))
    return nav, res, model, events


@pytest.fixture
async def host():
    from understudy_agent.tiers.browser import BrowserHost

    async with BrowserHost() as h:
        yield h


async def test_the_cliff_step_survives_one_transient_provider_error(cluster, host, tmp_path):
    nav, res, model, events = await _nav_with_flaky_cliff(host, cluster, tmp_path, [GeminiHTTPError("api", "unavailable", 503)])
    assert res.state == "done" and res.cliff_checked                    # the step that used to fail the whole household
    assert model.cliff_calls >= 2
    assert nav.cliff_runs and nav.cliff_runs[0]["outcome"] == "done"
    assert nav.cliff_runs[0]["model_retries"] == 1 and nav.cliff_runs[0]["model_retry_classes"] == ["transport"]
    assert [e.action for e in events].count("model_retry") == 1
    assert not [e for e in events if e.action == "cliff_check" and not e.ok]


async def test_the_cliff_step_that_keeps_failing_is_recorded_with_its_class(cluster, host, tmp_path):
    errs = [GeminiHTTPError("api", "unavailable", 503) for _ in range(3)]
    nav, res, model, events = await _nav_with_flaky_cliff(host, cluster, tmp_path, errs)
    assert res.state == "done" and not res.cliff_checked                # the calculator is fine; only the cliff panel is missing
    assert nav.cliff_runs[0]["outcome"] == "stopped:GeminiHTTPError" and nav.cliff_runs[0]["model_retries"] == 2
    assert any(e.action == "cliff_check" and not e.ok for e in events)


async def test_the_navigator_re_raises_a_provider_safety_stop_from_the_cliff_step(cluster, host, tmp_path):
    from understudy_agent.navigator import CLIFF_GOAL, CalculatorJob, Navigator
    from understudy_agent.sandbox_sites.households import generate_households
    from understudy_agent.security.denylist import Denylist
    from understudy_agent.tiers.heuristic import DomOracleComputerModel

    class Model(DomOracleComputerModel):
        def computer_step(self, goal, screenshot, history, **kw):
            if CLIFF_GOAL[:40] in goal:
                return SafetyStop([{"code": "require_confirmation"}])
            return super().computer_step(goal, screenshot, history, **kw)

    audit = AuditLog(tmp_path / "audit.jsonl")
    q = ApprovalQueue(tmp_path / "queue", audit=audit)
    model = Model()
    guard = Guard(model, run_id="r_cl2", routine_id=None, audit=audit, queue=q, denylist=Denylist(), mode="model_driven")
    nav = Navigator("nav-c", context=await host.new_context(), model=model, guard=guard, base_url=cluster.urls["c"], query="",
                    use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=False)
    with pytest.raises(ProviderSafetyStop):
        await nav.run(CalculatorJob("c", generate_households(20, 7001)[1].params()))
    assert q.list("pending")                                                  # it went to the human queue, and nothing acknowledged it
