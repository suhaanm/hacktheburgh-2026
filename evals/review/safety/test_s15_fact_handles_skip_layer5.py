"""S-15 (Medium): with fact handles, layer 5 (data-flow) is evaluated on the HANDLE string, never on the value that is actually typed, and
the value skips validate_action (length, control characters). A web-tainted value that a literal type would send to the queue is typed
silently when it goes through a handle, into any app or site (url is None in tier 3, so nothing is 'recorded')."""
from __future__ import annotations

import pytest

from fakes import Scripted, always_true, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.security.dataflow import Taint
from understudy_agent.tiers.base import GateStop
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator
from understudy_agent.tiers.facts import FactStore

TAINT = "WEB-SECRET-7731"


async def run(text, facts):
    guard = make_guard(recorded_hosts=("calc-a.example",))
    guard.pipe.dataflow.tag(TAINT, Taint.WEB, origin="evil.example")        # read from a web page by the reader
    sim = SimulatedActuator()
    try:
        await ComputerUse(Scripted(Action("type", {"text": text}), Done("done", True)), sim, guard, navigator="n", facts=facts).run("g", always_true)
    except GateStop:
        pass
    return sim


async def test_control_a_literal_tainted_value_is_stopped():
    assert (await run(TAINT, None)).typed == ""


async def test_the_same_value_through_a_handle_is_typed_without_approval():
    facts = FactStore({"x.note": "a note"}, {"x.note": lambda: TAINT + "\nsecond line"})
    sim = await run("{x.note}", facts)
    assert sim.typed == "", f"tainted value (plus a newline) typed through a handle with no check: {sim.typed!r}"


async def test_control_an_untainted_handle_value_is_typed():
    sim = await run("{x.note}", FactStore({"x.note": "a note"}, {"x.note": lambda: "plain value"}))
    assert sim.typed == "plain value", "CONTROL: the harness must reach the actuator, else the test above proves nothing"
