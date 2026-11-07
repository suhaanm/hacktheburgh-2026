"""Fact handles: the model types a handle, code resolves the value; values never reach prompts, logs or the queue."""
from __future__ import annotations

import json
import re

import httpx
import pytest

from understudy_agent.audit import AuditLog
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import Adult, Household
from understudy_agent.sandbox_sites.specs import SELECT_LABELS, SITES
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.base import StuckLoop
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator, TargetRead

READABLE = TargetRead("Calculate", "button")   # what trusted code would read under the pointer in these tests
from understudy_agent.tiers.facts import (
    CALC_VOCAB, FactRefused, FactStore, NOTE_VOCAB, calculator_values, key_would_type_text,
)
from understudy_agent.tiers.safety import Guard

# Unusual values that would be easy to spot anywhere they leak.
CANARY = Household(id="hh_canary", case_ref="CASE-9999", region="england",
                   adults=(Adult(47, 7777.0), Adult(48, 6543.0)), children_ages=(9, 13), tenure="rent",
                   rent_monthly=4243.0, bedrooms=3, savings=7777321.0, childcare_monthly=5151.0)
CANARY_VALUES = ["7777321", "4243", "7777", "6543", "5151", "47", "48"]


def test_check_accepts_exactly_one_known_handle():
    fs = FactStore.for_calculator("a", CANARY)
    assert fs.check("{household.savings}") == "household.savings"
    assert fs.check("  {household.rent}  ") == "household.rent"
    for bad, code in [("7777321", "literal_text"), ("savings", "literal_text"), ("{household.ssn}", "unknown_handle"),
                      ("{household.savings}{household.rent}", "literal_text"), ("{household.savings} 5", "literal_text"),
                      ("{note.text}", "unknown_handle"), ("", "literal_text"), (None, "literal_text"), (5, "literal_text")]:
        with pytest.raises(FactRefused) as e:
            fs.check(bad)
        assert e.value.code == code, bad
    assert FactStore.for_casenote({"note_text": "x"}).check("{note.text}") == "note.text"


def test_the_goal_block_lists_handles_and_meanings_but_no_values():
    for fs in (FactStore.for_calculator("c", CANARY), FactStore.for_casenote({"note_text": "SECRET-NOTE"})):
        block = fs.goal_block()
        assert all("{" + h + "}" in block for h in fs.handles)
        for v in CANARY_VALUES + ["SECRET-NOTE"]:
            assert v not in block
    assert set(FactStore.for_calculator("a", CANARY).handles) == set(CALC_VOCAB)
    assert set(FactStore.for_casenote({}).handles) == set(NOTE_VOCAB)


def test_resolution_is_per_site():
    a, b, c = (calculator_values(s, CANARY) for s in "abc")
    assert a["household.adults"] == "2" and b["household.adults"] == "Me and a partner" and c["household.adults"] == "Two adults"
    assert a["household.adult1_earnings"] == "7777" and c["household.adult1_earnings"] == "93324.00"      # annual on site c
    assert a["household.rent"] == "4243" and c["household.rent"] == "979.15"                               # weekly on site c
    assert c["household.tenure"] == "Renting" and a["household.tenure"] == "Rent"
    single = Household(id="h", case_ref="CASE-1", region="england", adults=(Adult(30, 500.0),))
    v = calculator_values("a", single)
    assert v["household.adult2_age"] == "" and v["household.adult2_earnings"] == "" and v["household.children_ages"] == ""


@pytest.mark.parametrize("site", ["a", "b", "c"])
def test_select_label_table_matches_the_real_pages(cluster, site):
    """SELECT_LABELS must be the option text each site really shows, or type-ahead would pick the wrong option."""
    base = cluster.urls[site]
    pages = []
    if site == "a":
        data = {"adults": "1", "your_age": "30", "partner_age": "", "children_ages": ""}
        pages.append(httpx.get(base + "/step/1").text)
        pages.append(httpx.post(base + "/step/2", data=data).text)
        data.update({"your_earnings": "0", "partner_earnings": "0", "limited_capability": "no"})
        pages.append(httpx.post(base + "/step/3", data=data).text)
    else:
        pages.append(httpx.get(base + "/").text)
    found: dict[str, dict[str, str]] = {}
    keys = SITES[site].fields_v1
    inv = {v: k for k, v in keys.items()}
    for html in pages:
        for m in re.finditer(r'<select[^>]*?(?:name|data-testid)="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
            canon = inv.get(m.group(1))
            if canon:
                found[canon] = {v: t for v, t in re.findall(r'<option value="([^"]*)">([^<]*)</option>', m.group(2))}
    assert set(found) == set(SELECT_LABELS[site]), (site, set(found))
    for canon, opts in SELECT_LABELS[site].items():
        assert found[canon] == opts, (site, canon)


def test_key_presses_that_would_type_text_are_recognised():
    assert key_would_type_text(["7"]) and key_would_type_text(["a"]) and key_would_type_text(["shift", "a"])
    assert not key_would_type_text(["Enter"]) and not key_would_type_text(["Tab"]) and not key_would_type_text(["cmd", "a"])
    assert not key_would_type_text(["ctrl", "c"]) and not key_would_type_text(["Escape"])


# ------------------------------------------------------------------ the loop
class Scripted:
    """A computer-use model that replays a script and records every goal it was shown."""

    name = "scripted"

    def __init__(self, script):
        self.script, self.goals, self.histories = list(script), [], []

    def computer_step(self, goal, shot, history, **kw):
        self.goals.append(goal)
        self.histories.append(json.dumps(history))
        i = len(self.goals) - 1
        return self.script[min(i, len(self.script) - 1)]


@pytest.fixture
def world(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = ApprovalQueue(tmp_path / "queue", audit=audit)
    guard = Guard(MockProvider("benefits_clean"), run_id="r_facts", mode="model_driven", audit=audit, queue=queue,
                  denylist=Denylist())
    return guard, audit, queue, tmp_path


def everything_written(audit, queue, tmp_path, events, res):
    blob = json.dumps(audit.read(5000)) + json.dumps(queue.list("all")) + json.dumps(events) + json.dumps(res.history)
    for p in tmp_path.rglob("*"):
        if p.is_file():
            blob += p.read_text(errors="ignore")
    return blob


async def test_the_model_types_handles_and_only_the_actuator_ever_sees_values(world):
    guard, audit, queue, tmp = world
    facts = FactStore.for_calculator("a", CANARY)
    model = Scripted([Action("click", {"x": 100, "y": 100}), Action("type", {"text": "{household.savings}"}),
                      Action("click", {"x": 300, "y": 200}), Action("type", {"text": "{household.adult1_age}"}),
                      Action("type", {"text": "{household.adult2_earnings}"}), Done("done", True)])
    sim, events = SimulatedActuator(targets=READABLE), []
    cu = ComputerUse(model, sim, guard, navigator="t3", facts=facts, emit=events.append)

    async def verify():
        return True

    res = await cu.run("enter the household", verify)
    assert res.outcome == "done" and sim.typed == "7777321" + "47" + "6543"          # the actuator got the real values
    assert [a.kind for a in sim.actions] == ["click", "type", "click", "type", "type"]
    assert res.refusals == 0 and facts.resolved == ["household.savings", "household.adult1_age", "household.adult2_earnings"]
    # the model's prompts carry the vocabulary, never a value
    assert model.goals and all("{household.savings}" in g for g in model.goals)
    for g in model.goals:
        assert not any(v in g for v in CANARY_VALUES), "a value reached a prompt"
    assert not any(v in " ".join(model.histories) for v in CANARY_VALUES)
    blob = everything_written(audit, queue, tmp, [e.as_dict() for e in events], res)
    assert not any(v in blob for v in ["7777321", "4243", "6543", "5151"]), "a value reached a log, the audit trail or the queue"
    assert "handle=household.savings" in blob and any(e.action == "type_fact" for e in events)
    # the SafetyPipeline saw a type action with a handle
    assert any(x["kind"] == "step" and x.get("note") == "type" for x in audit.read(500))


async def test_literals_unknown_handles_and_letter_keys_are_refused_and_never_typed(world):
    guard, audit, queue, tmp = world
    facts = FactStore.for_calculator("a", CANARY)
    model = Scripted([Action("type", {"text": "7777321"}), Action("type", {"text": "{household.passport}"}),
                      Action("key", {"keys": ["7"]}), Action("type", {"text": "{household.savings}"}),
                      Action("key", {"keys": ["Enter"]}), Done("done", True)])
    sim, events = SimulatedActuator(targets=READABLE), []
    cu = ComputerUse(model, sim, guard, navigator="t3", facts=facts, emit=events.append)

    async def verify():
        return True

    res = await cu.run("enter the household", verify)
    assert res.refusals == 3 and res.outcome == "done"
    assert sim.typed == "7777321"                      # only the resolved handle was typed, once
    assert [a.kind for a in sim.actions] == ["type", "key"]      # the Enter key is fine
    refused = [e for e in events if not e.ok]
    assert [e.detail for e in refused] == ["refused: literal_text", "refused: unknown_handle", "refused: key_types_text"]
    # the model is told why on its next turn (trusted wording, no values)
    assert "refused" in model.goals[1] and "FACTS" in model.goals[1]
    assert any(x["kind"] == "fact_refused" for x in audit.read(500))
    assert "{household.passport}" not in json.dumps(audit.read(500))      # a refused string is not copied into the audit log


async def test_a_model_that_keeps_typing_literals_is_stopped(world):
    guard, audit, queue, tmp = world
    facts = FactStore.for_calculator("a", CANARY)
    model = Scripted([Action("type", {"text": "7777321"})])
    sim = SimulatedActuator(targets=READABLE)
    cu = ComputerUse(model, sim, guard, navigator="t3", facts=facts)

    async def verify():
        return False

    with pytest.raises(StuckLoop, match="literal"):
        await cu.run("x", verify)
    assert sim.actions == []


async def test_a_fact_with_no_value_types_nothing_and_carries_on(world):
    guard, audit, queue, tmp = world
    single = Household(id="h", case_ref="CASE-1", region="england", adults=(Adult(30, 500.0),))
    model = Scripted([Action("type", {"text": "{household.adult2_age}"}), Done("done", True)])
    sim = SimulatedActuator(targets=READABLE)
    cu = ComputerUse(model, sim, guard, navigator="t3", facts=FactStore.for_calculator("a", single))

    async def verify():
        return True

    res = await cu.run("x", verify)
    assert sim.actions == [] and res.outcome == "done" and res.history[0]["empty"] is True


async def test_without_facts_the_loop_still_allows_literal_typing_for_other_tasks(world):
    guard, audit, queue, tmp = world
    model = Scripted([Action("type", {"text": "hello"}), Done("done", True)])
    sim = SimulatedActuator(targets=READABLE)

    async def verify():
        return True

    res = await ComputerUse(model, sim, guard, navigator="t3").run("click type key", verify)
    assert sim.typed == "hello" and res.outcome == "done"


async def test_progress_budget_stops_a_run_whose_screen_never_changes(world):
    guard, audit, queue, tmp = world

    class Wanderer:
        name = "wanderer"
        n = 0

        def computer_step(self, goal, shot, history, **kw):
            Wanderer.n += 1
            return Action("move", {"x": 10 * Wanderer.n, "y": 20 * Wanderer.n})

    sim = SimulatedActuator(targets=READABLE)
    cu = ComputerUse(Wanderer(), sim, guard, navigator="t3", stall_limit=4, max_steps=100)

    async def verify():
        return False

    from understudy_agent.tiers.base import StepBudgetExceeded

    with pytest.raises(StepBudgetExceeded, match="no visible progress"):
        await cu.run("x", verify)
    assert 3 <= len(sim.actions) <= 6                     # stopped by stalling, long before the 100-step cap
