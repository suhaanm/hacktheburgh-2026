"""Tier 3 (computer use) end to end, OFFLINE: a grounded test double drives the sandbox sites through screenshots,
pixel clicks and typed FACT HANDLES. This proves the loop, the handles, the actuator and the verification work; it says
nothing about any real model (that is what the live iterations measure)."""
from __future__ import annotations

import json

import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.navigator import CalculatorJob, CaseNoteJob, Navigator
from understudy_agent.orchestrator import BenefitsRun, RunOptions
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.sandbox_sites.oracle import site_expected
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.browser import BrowserHost
from understudy_agent.tiers.computer_use import BrowserPageActuator
from understudy_agent.tiers.heuristic import DomOracleComputerModel
from understudy_agent.tiers.safety import Guard


@pytest.fixture
async def host():
    async with BrowserHost() as h:
        yield h


@pytest.fixture
def sinks(tmp_path):
    a = AuditLog(tmp_path / "audit.jsonl")
    return ApprovalQueue(tmp_path / "queue", audit=a), a


def hh(i):
    return generate_households(20, 7001)[i]


async def one_nav(host, cluster, sinks, site, h, *, query="", literal_every=0):
    q, a = sinks
    model = DomOracleComputerModel(literal_every=literal_every)
    guard = Guard(model, run_id="r_t3", routine_id=None, audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    events = []
    nav = Navigator(f"nav-{site}", context=ctx, model=model, guard=guard, base_url=cluster.urls[site], query=query,
                    emit=events.append, use_tier1=False, start_tier=3, allow_tier3=True, defer_cliff=False)
    res = await nav.run(CalculatorJob(site, h.params()))
    return res, model, events, nav


@pytest.mark.parametrize("site", ["a", "b", "c"])
@pytest.mark.parametrize("idx", [1, 3])
async def test_tier3_enters_a_household_on_each_site_by_typing_handles(cluster, host, sinks, site, idx):
    h = hh(idx)
    res, model, events, nav = await one_nav(host, cluster, sinks, site, h)
    assert res.state == "done", (res.attempts, [e.detail for e in events][-6:])
    assert res.value.amount == pytest.approx(site_expected(site, h)["uc_monthly"], abs=0.06)
    assert res.tiers_used == [3] and res.cliff_checked and res.false_claims == 0
    kinds = {e.action for e in events}
    assert "type_fact" in kinds and "click" in kinds
    assert all(e.tier == 3 for e in events)
    # the model never saw a value: every goal it was shown is value-free
    values = [v for v in (str(int(h.savings)), str(int(h.rent_monthly))) if len(v) >= 3]
    typed_goals = [g for g in model.goals if "FACTS you may type" in g]
    assert typed_goals and len(typed_goals) < len(model.goals)       # the cliff goal needs no facts
    for g in model.goals:
        assert not any(f" {v}" in g for v in values)
    assert all("{household.savings}" in g for g in typed_goals)
    blob = json.dumps([e.as_dict() for e in events]) + json.dumps(sinks[1].read(5000))
    assert "handle=household.savings" in blob


async def test_tier3_saves_the_case_note_draft_by_typing_note_handles(cluster, host, sinks):
    q, a = sinks
    model = DomOracleComputerModel()
    guard = Guard(model, run_id="r_t3n", audit=a, queue=q, denylist=Denylist(), mode="model_driven")
    ctx = await host.new_context()
    params = {"case_ref": "CASE-7001", "result_a": "£781", "result_b": "£955.00 per month", "result_c": "0.00 GBP / month",
              "reconciliation": "discrepancy", "note_text": "Calculators disagree near the 16,000 limit. Cliff checked on all three."}
    nav = Navigator("scribe", context=ctx, model=model, guard=guard, base_url=cluster.urls["a"], use_tier1=False,
                    start_tier=3, allow_tier3=True)
    res = await nav.run(CaseNoteJob(params))
    assert res.state == "done" and res.value["note_id"].startswith("CN-") and res.tiers_used == [3]
    note = list(cluster.state.notes.values())[-1]
    assert note["reconciliation"] == "discrepancy" and note["note_text"] == params["note_text"]
    assert note["result_b"] == "£955.00 per month" and cluster.state.submissions == []


async def test_literal_values_typed_by_the_model_are_refused_and_the_run_still_completes(cluster, host, sinks):
    h = hh(1)
    res, model, events, nav = await one_nav(host, cluster, sinks, "a", h, literal_every=7)
    assert res.state == "done" and nav.refusals >= 2
    assert any(e.action == "type_fact" and e.detail.startswith("refused: literal_text") for e in events)
    # a literal "12345" never reached the page
    assert "12345" not in json.dumps(list(cluster.state.calculations))


async def test_tier3_recovers_from_a_503_by_going_back_and_trying_again(cluster, host, sinks):
    h = hh(1)
    res, model, events, nav = await one_nav(host, cluster, sinks, "b", h, query="?glitch=503once")
    assert res.state == "done", (res.attempts, [(e.action, e.detail) for e in events][-8:])
    assert res.value.amount == pytest.approx(site_expected("b", h)["uc_monthly"], abs=0.06)


async def test_tier3_works_on_the_changed_layout(cluster, host, sinks):
    h = hh(2)
    for site in "abc":
        res, model, events, nav = await one_nav(host, cluster, sinks, site, h, query="?layout=v2")
        assert res.state == "done", (site, res.attempts)
        assert res.value.amount == pytest.approx(site_expected(site, h)["uc_monthly"], abs=0.06)


async def test_a_full_household_through_the_orchestrator_with_tier3_only(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    h = hh(3)   # the 16,000 savings cliff household: sites disagree
    run = BenefitsRun("r_t3_full", h, model=DomOracleComputerModel(), base_urls=cluster.urls, queue=queue, audit=audit,
                      options=RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3,
                                         screenshots=False))
    res = await run.execute()
    assert res.state == "done", res.reason
    assert res.completion == {"ok": True, "missing": []} and res.false_claims == 0
    assert res.reconciliation["status"] == "discrepancy" and res.cliff_checked == {"a": True, "b": True, "c": True}
    tiers = {e["tier"] for e in res.tier_log}
    assert tiers == {3}, tiers
    assert cluster.state.submissions == [] and res.awaiting_approval
    assert [i["kind"] for i in queue.list()] == ["irreversible_step"]
    assert len(res.tier_log) > 100          # a long-horizon run: well over 100 steps for one household


async def test_an_injected_page_pauses_a_tier3_run_before_the_model_is_asked(cluster, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    audit = AuditLog(tmp_path / "data" / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "data" / "queue", audit=audit)
    model = DomOracleComputerModel()
    run = BenefitsRun("r_t3_inj", hh(1), model=model, base_urls=cluster.urls, queue=queue, audit=audit,
                      options=RunOptions(denylist=Denylist(), use_tier1=False, allow_tier3=True, start_tier=3,
                                         query={"b": "?variant=injected"}, screenshots=False))
    res = await run.execute()
    assert res.state == "paused" and "injection" in res.reason
    assert cluster.state.exfil_hits == [] and cluster.state.submissions == []
    assert not any(e["navigator"] == "nav-b" for e in res.tier_log)
