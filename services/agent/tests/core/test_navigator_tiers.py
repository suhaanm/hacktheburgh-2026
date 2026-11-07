"""Navigator ladder, tier 2 (browser agent), tier 3 (computer use) and the actuator guards."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done, SafetyStop
from understudy_agent.navigator import CalculatorJob, CaseNoteJob, Navigator
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.sandbox_sites.specs import CANARY
from understudy_agent.security.config import SecurityConfig
from understudy_agent.tiers.base import GateStop, InjectionStop
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import (
    ActuatorRefused, ComputerUse, MacActuator, ProviderSafetyStop, SimulatedActuator,
)
from understudy_agent.tiers.browser_agent import StuckLoop, convert_unit
from understudy_agent.tiers.heuristic import HeuristicModelPort, param_for, read_calculator_result
from understudy_agent.tiers.safety import Guard


@pytest.fixture
def sinks(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    return ApprovalQueue(tmp_path / "queue", audit=audit), audit


@pytest.fixture
def model():
    return HeuristicModelPort(MockProvider("benefits_clean"))


def mk_guard(sinks, port=None, run_id="r_test", **kw):
    q, a = sinks
    return Guard(port or HeuristicModelPort(MockProvider("benefits_clean")), audit=a, queue=q, denylist=Denylist(),
                 run_id=run_id, **kw)


@pytest.fixture
def safety(sinks, model):
    return mk_guard(sinks, model)


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


async def nav_for(host, cluster, model, safety, site, hid=0, **kw):
    ctx = await host.new_context()
    events: list[Any] = []
    h = generate_households(20)[hid]
    nav = Navigator(f"nav-{site}", context=ctx, model=model, guard=safety, base_url=cluster.urls[site],
                    emit=events.append, **kw)
    return nav, CalculatorJob(site, h.params()), h, events


# ------------------------------------------------------------------ the ladder
@pytest.mark.parametrize("site", ["a", "b", "c"])
async def test_tier1_only_when_nothing_goes_wrong(cluster, host, model, safety, site):
    nav, job, h, events = await nav_for(host, cluster, model, safety, site, hid=3)
    res = await nav.run(job)
    assert res.state == "done" and res.tiers_used == [1] and res.attempts == []
    assert res.value.amount == pytest.approx(site_expected(site, h)["uc_monthly"], abs=0.06)
    assert all(e.tier == 1 for e in events) and events
    assert model.calls == []  # not a single model call on the cheap path


@pytest.mark.parametrize("site", ["a", "b", "c"])
@pytest.mark.parametrize("hid", [1, 5])
async def test_layout_change_escalates_to_tier2_and_still_succeeds(cluster, host, model, safety, site, hid):
    nav, job, h, events = await nav_for(host, cluster, model, safety, site, hid=hid, query="?layout=v2")
    res = await nav.run(job)
    assert res.state == "done", res.attempts
    assert res.tiers_used[0] == 1 and 2 in res.tiers_used  # tier logged on every step
    assert res.attempts and res.attempts[0]["tier"] == 1
    assert res.value.amount == pytest.approx(site_expected(site, h)["uc_monthly"], abs=0.06)
    assert {e.tier for e in events} == {1, 2}
    assert all(isinstance(e.tier, int) for e in events)
    t2 = [e for e in events if e.tier == 2 and e.ok]
    assert t2 and sum(1 for e in t2 if e.action in ("fill", "select")) >= 5
    assert res.false_claims == 0


async def test_tier2_never_types_a_value_it_was_not_given(cluster, host, model, safety):
    """The planner names parameters; code supplies the values (SEC-5)."""
    nav, job, h, _ = await nav_for(host, cluster, model, safety, "b", hid=1, query="?layout=v2", use_tier1=False)
    res = await nav.run(job)
    assert res.state == "done" and res.tiers_used[0] == 2
    planned = [c for c in model.calls if c["method"] == "plan"]
    assert planned and all(set(m["messages"][1]["content"].split("STATE: ")[1].split("\n")[0]) for m in planned)
    assert model.calls[-1]["method"] in ("read", "plan")


async def test_transient_503_is_retried_on_a_fresh_page_with_tier1(cluster, host, model, safety):
    nav, job, h, events = await nav_for(host, cluster, model, safety, "b", hid=2, query="?glitch=503once")
    res = await nav.run(job)
    assert res.state == "done" and res.tiers_used == [1]
    assert len(res.attempts) == 1 and res.attempts[0]["tier"] == 1
    assert any(e.action == "escalate" for e in events)
    assert model.calls == []


async def test_permanent_failure_escalates_to_a_human_not_a_crash(cluster, host, model, safety, sinks):
    q, _ = sinks
    nav, job, h, events = await nav_for(host, cluster, model, safety, "c", hid=0, query="?glitch=503always")
    res = await nav.run(job)
    assert res.state == "escalated" and res.queue_id
    item = q.get(res.queue_id)
    assert item["kind"] == "batch_result" and item["status"] == "pending" and "Needs a human" in item["title"]
    assert len(res.attempts) >= 2
    assert nav.steps < 140  # bounded: tier-1 bundle, a fresh retry, then at most 20 model-driven actions


async def test_step_cap_is_enforced_for_model_driven_actions(cluster, host, safety):
    class Dither:
        name = "dither"
        calls = 0
        def plan(self, messages, schema=None):
            Dither.calls += 1
            return {"tool": "wait", "reason": "thinking"}
        def read(self, u, s): return {"amount_text": "", "status_text": "", "ref": ""}
    nav, job, h, events = await nav_for(host, cluster, Dither(), safety, "b", query="?layout=v2", max_actions=6)
    res = await nav.run(job)
    assert res.state == "escalated"
    assert Dither.calls <= 6 + 1  # never more than the cap (plus the stuck-loop probe)
    assert nav.t_left <= 0 or Dither.calls <= 7


async def test_false_finish_claim_is_recorded_as_a_false_claim(cluster, host, safety):
    class Liar:
        name = "liar"
        def plan(self, messages, schema=None): return {"tool": "finish", "reason": "all done"}
        def read(self, u, s): return {"amount_text": "", "status_text": "", "ref": ""}
    nav, job, h, _ = await nav_for(host, cluster, Liar(), safety, "b", query="?layout=v2")
    res = await nav.run(job)
    assert res.state == "escalated"
    assert nav.ledger.false_claims >= 3 and res.false_claims >= 3


async def test_cancellation_propagates(cluster, host, model, safety):
    n = {"i": 0}
    def cur():
        n["i"] += 1
        return n["i"] < 5
    nav, job, h, _ = await nav_for(host, cluster, model, safety, "a", is_current=cur)
    with pytest.raises(asyncio.CancelledError):
        await nav.run(job)


async def test_case_note_job_tier1_and_tier2(cluster, host, model, safety):
    params = {"case_ref": "CASE-1010", "result_a": "£1", "result_b": "£2", "result_c": "£3",
              "reconciliation": "agree", "note_text": "ok"}
    for query, want_tiers in (("", [1]), ("?layout=v2", [1, 2])):
        ctx = await host.new_context()
        nav = Navigator("scribe", context=ctx, model=model, guard=safety, base_url=cluster.urls["a"], query=query)
        res = await nav.run(CaseNoteJob(params))
        assert res.state == "done" and res.tiers_used == want_tiers, res.attempts
        assert res.value["note_id"].startswith("CN-")
    assert cluster.state.submissions == []


# ------------------------------------------------------------------ injection (red-team inputs)
@pytest.mark.parametrize("site", ["a", "b", "c"])
async def test_injected_page_pauses_the_run_and_is_not_obeyed(cluster, host, model, safety, sinks, site):
    q, _ = sinks
    nav, job, h, events = await nav_for(host, cluster, model, safety, site, query="?variant=injected")
    with pytest.raises(InjectionStop):
        await nav.run(job)
    assert cluster.state.exfil_hits == [] and cluster.state.submissions == []
    items = q.list()
    assert items and items[0]["kind"] == "injection_pause"
    assert all(len(x) <= 80 for x in items[0]["evidence"]["extracted"].get("excerpts", []))  # short excerpts only


async def test_with_the_detector_off_tier1_is_still_unaffected_by_page_text(cluster, host, model, sinks):
    q, a = sinks
    sf = mk_guard(sinks, model, config=SecurityConfig.all_on().without("detector"), run_id="r_x")
    nav, job, h, _ = await nav_for(host, cluster, model, sf, "b", query="?variant=injected")
    res = await nav.run(job)
    assert res.state == "done" and cluster.state.exfil_hits == []


async def test_ablation_hijacked_planner_follows_page_text_only_when_layers_are_off(cluster, host, sinks):
    """Vulnerable planner + injected page. Layers on: nothing happens. Reader and detector layers off: it is
    hijacked, and the action-class gate is what is left."""
    q, a = sinks
    inner = MockProvider("vulnerable_planner")
    # all layers on, tier 2 forced: planner never sees page text, so there is nothing to hijack
    on = mk_guard(sinks, HeuristicModelPort(inner), run_id="r_on")
    nav, job, h, _ = await nav_for(host, cluster, HeuristicModelPort(inner), on, "b", query="?variant=injected&layout=v2",
                                   use_tier1=False)
    with pytest.raises(InjectionStop):
        await nav.run(job)
    assert cluster.state.exfil_hits == []
    # reader, detector, sanitize, actions layers off: the planner is shown raw page text and obeys it
    off_cfg = SecurityConfig.all_on().without("reader", "detector", "sanitize", "actions", "drift")
    off = mk_guard(sinks, HeuristicModelPort(MockProvider("vulnerable_planner")), config=off_cfg, run_id="r_off")
    nav, job, h, _ = await nav_for(host, cluster, HeuristicModelPort(MockProvider("vulnerable_planner")), off, "b",
                                   query="?variant=injected&layout=v2", use_tier1=False, max_actions=6)
    res = await nav.run(job)
    assert cluster.state.exfil_hits, "attack should succeed with the layers off"
    assert res.state in ("escalated", "done")


# ------------------------------------------------------------------ heuristic planner pieces
@pytest.mark.parametrize("label,role,want", [
    ("How many adults live in your household?", "combobox", ("adults", "none")),
    ("Your age", "spinbutton", ("adult1_age", "none")),
    ("Partner's age (if any)", "spinbutton", ("adult2_age", "none")),
    ("Age of second adult", "spinbutton", ("adult2_age", "none")),
    ("First adult: earnings per YEAR after tax (£)", "textbox", ("adult1_earnings_monthly", "year")),
    ("Rent per WEEK (£)", "textbox", ("rent_monthly", "week")),
    ("Childcare per WEEK (£)", "textbox", ("childcare_monthly", "week")),
    ("Monthly rent (£)", "textbox", ("rent_monthly", "month")),
    ("Housing", "combobox", ("tenure", "none")),
    ("Rent or own?", "combobox", ("tenure", "none")),
    ("Children's ages, comma separated", "textbox", ("children_ages", "none")),
    ("Savings (£)", "textbox", ("savings", "none")),
    ("Health condition limiting work?", "combobox", ("limited_capability", "none")),
    ("Bedrooms needed", "combobox", ("bedrooms", "none")),
    ("Case reference", "textbox", ("case_ref", "none")),
    ("Note", "textbox", ("note_text", "none")),
])
def test_label_to_parameter_rules(label, role, want):
    assert param_for(label, role) == want


def test_unit_conversion_and_reader_rules():
    assert convert_unit("adult1_earnings_monthly", "1000", "year") == "12000.00"
    assert convert_unit("rent_monthly", "520", "week") == "120.00"
    assert convert_unit("savings", "5000", "year") == "5000"
    got = read_calculator_result("Estimated Universal Credit: £781 a month\nYou are likely to be eligible\nReference: GOV-1A2B3C")
    assert got == {"amount_text": "£781 a month", "status_text": "You are likely to be eligible", "ref": "GOV-1A2B3C"}


# ------------------------------------------------------------------ tier 3 (SimulatedActuator only)
GOAL3 = "click the text area, type a line and press a key"


async def run_cu(scenario: str, safety, **kw):
    act = SimulatedActuator()
    cu = ComputerUse(MockProvider(scenario), act, safety, navigator="nav-x", **kw)

    async def verify():
        return False

    return act, cu, verify


async def test_tier3_notepad_script_runs_on_the_simulated_actuator_only(safety):
    act, cu, _ = await run_cu("computer_notepad", safety)

    async def verify():
        return True

    res = await cu.run(GOAL3, verify)
    assert res.outcome == "done" and not res.false_claim
    assert [a.kind for a in act.actions] == ["click", "type", "key"]
    assert act.typed == "Understudy mock run" and act.released >= 1


async def test_tier3_false_done_is_caught(safety):
    act, cu, verify = await run_cu("computer_false_done", safety)
    res = await cu.run(GOAL3, verify)
    assert res.outcome == "claimed_not_verified" and res.false_claim and res.claimed_done


async def test_tier3_provider_safety_check_goes_to_the_queue_never_acked(safety, sinks):
    q, _ = sinks
    act, cu, verify = await run_cu("computer_safety_stop", safety)
    with pytest.raises(ProviderSafetyStop) as e:
        await cu.run(GOAL3, verify)
    assert e.value.queue_id and q.get(e.value.queue_id)["status"] == "pending"
    assert len(act.actions) == 1


async def test_tier3_stuck_loop_detected(safety):
    act, cu, verify = await run_cu("computer_stuck", safety)
    with pytest.raises(StuckLoop):
        await cu.run(GOAL3, verify)
    assert len(act.actions) <= 4


async def test_tier3_gate_blocks_a_delete_button(safety, sinks):
    q, _ = sinks
    act, cu, verify = await run_cu("computer_off_goal", safety)
    with pytest.raises(GateStop):
        await cu.run(GOAL3, verify)
    assert [a.kind for a in act.actions] == ["click"]  # the Delete click was never executed
    assert q.list()[0]["kind"] == "irreversible_step"


async def test_tier3_step_cap_and_cancellation(safety):
    class Forever:
        name = "forever"
        n = 0
        def computer_step(self, goal, shot, history, **kw):
            Forever.n += 1
            return Action("click", {"x": 100 * Forever.n, "y": 50 * Forever.n})
    act = SimulatedActuator()
    cu = ComputerUse(Forever(), act, safety, navigator="n", max_steps=5)

    async def never():
        return False
    from understudy_agent.tiers.base import StepBudgetExceeded
    with pytest.raises(StepBudgetExceeded):
        await cu.run("x", never)
    assert len(act.actions) == 5
    cu2 = ComputerUse(Forever(), SimulatedActuator(), safety, navigator="n", is_current=lambda: False)
    with pytest.raises(asyncio.CancelledError):
        await cu2.run("x", never)


# ------------------------------------------------------------------ MacActuator guards (fake backend, no desktop)
class FakeBackend:
    def __init__(self, front="TextEdit", locked=False, scale=2.0):
        self.front, self.locked, self.scale = front, locked, scale
        self.events: list[tuple] = []
        self.released = 0

    def frontmost_app(self): return self.front
    def screen_locked(self): return self.locked
    def display_scale(self): return self.scale
    def mouse(self, kind, x, y): self.events.append(("mouse", kind, x, y))
    def type_text(self, text): self.events.append(("type", text))
    def key(self, keys): self.events.append(("key", tuple(keys)))
    def scroll(self, dx, dy): self.events.append(("scroll", dx, dy))
    def screenshot_png(self): return b"png"
    def release_all(self): self.released += 1


ENV_ON = {"UNDERSTUDY_REAL_ACTUATOR": "1"}


def mac(backend, tmp_path, **kw):
    return MacActuator("TextEdit", backend=backend, kill_flag=tmp_path / "KILL", env=ENV_ON, **kw)


def test_mac_actuator_is_off_unless_env_says_so(tmp_path):
    with pytest.raises(ActuatorRefused):
        MacActuator("TextEdit", backend=FakeBackend(), env={})
    with pytest.raises(ActuatorRefused):
        MacActuator("TextEdit", backend=FakeBackend(), env={"UNDERSTUDY_REAL_ACTUATOR": "0"})


async def test_mac_actuator_maps_pixels_to_points_and_clicks(tmp_path):
    be = FakeBackend(scale=2.0)
    act = mac(be, tmp_path)
    await act.execute(Action("click", {"x": 1200, "y": 800}))
    assert ("mouse", "move", 600.0, 400.0) in be.events
    assert [e[1] for e in be.events if e[0] == "mouse"] == ["move", "down", "up"]
    await act.execute(Action("type", {"text": "hi"}))
    assert ("type", "hi") in be.events


async def test_mac_actuator_refuses_when_wrong_app_locked_killed_or_over_budget(tmp_path):
    be = FakeBackend(front="Safari")
    act = mac(be, tmp_path)
    with pytest.raises(ActuatorRefused, match="frontmost"):
        await act.execute(Action("type", {"text": "x"}))
    assert not [e for e in be.events if e[0] in ("type", "mouse")] and be.released >= 1
    be = FakeBackend(locked=True)
    with pytest.raises(ActuatorRefused, match="locked"):
        await mac(be, tmp_path).execute(Action("type", {"text": "x"}))
    be = FakeBackend()
    (tmp_path / "KILL").write_text("1")
    with pytest.raises(ActuatorRefused, match="kill"):
        await mac(be, tmp_path).execute(Action("type", {"text": "x"}))
    (tmp_path / "KILL").unlink()
    act = mac(FakeBackend(), tmp_path, max_actions=2)
    await act.execute(Action("wait", {"seconds": 0}))
    await act.execute(Action("wait", {"seconds": 0}))
    with pytest.raises(ActuatorRefused, match="action budget"):
        await act.execute(Action("wait", {"seconds": 0}))
    t = [0.0]
    act = mac(FakeBackend(), tmp_path, time_budget_s=10, clock=lambda: t[0])
    t[0] = 11.0
    with pytest.raises(ActuatorRefused, match="time budget"):
        await act.execute(Action("wait", {"seconds": 0}))


async def test_mac_actuator_rechecks_focus_between_move_and_click_and_releases_on_abort(tmp_path):
    be = FakeBackend()

    class Flip(FakeBackend):
        def mouse(self, kind, x, y):
            super().mouse(kind, x, y)
            if kind == "move":
                self.front = "Safari"  # the user switched apps right after the pointer moved

    be = Flip()
    act = mac(be, tmp_path)
    with pytest.raises(ActuatorRefused, match="lost focus"):
        await act.execute(Action("click", {"x": 10, "y": 10}))
    assert [e[1] for e in be.events if e[0] == "mouse"] == ["move"]  # no mouse down was ever posted
    assert be.released >= 1


async def test_mac_check_dry_run_goes_through_pipeline_and_guards(tmp_path, monkeypatch):
    from understudy_agent.tiers.mac_check import run_check

    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    out = await run_check("TextEdit", (1200, 800), "hello", real=False)
    assert out["ok"] and out["real"] is False and out["scale"] == 2.0
    assert [e[0] for e in out["events"] if e[0] in ("mouse", "type")][:4] == ["mouse", "mouse", "mouse", "type"]
    assert ["mouse", "move", 600.0, 400.0] in out["events"]
    refused = await run_check("Safari", (10, 10), "x", real=False)
    assert refused["ok"] is False and "harmless" in refused["reason"]
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "KILL").write_text("1")
    killed = await run_check("TextEdit", (10, 10), "x", real=False)
    assert killed["ok"] is False
