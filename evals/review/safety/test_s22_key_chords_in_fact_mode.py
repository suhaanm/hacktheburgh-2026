"""S-22 (Medium): the fact-handle rule says the model may type only handles and may not enter a literal through another route; `key_would_type_text`
refuses bare printable keys but any chord with cmd/ctrl/alt passes, and QuartzBackend.key now PERFORMS chords. cmd+v pastes whatever is on the owner's
clipboard (a password they just copied) into the target; option+letter types a symbol. Fakes only (the actuator records what it was asked to do)."""
from __future__ import annotations

import pytest

from fakes import Scripted, always_true, make_guard
from understudy_agent.models.port import Action, Done
from understudy_agent.tiers.computer_use import ComputerUse, SimulatedActuator, TargetRead
from understudy_agent.tiers.facts import FactStore


@pytest.mark.parametrize("keys", [["cmd", "v"], ["ctrl", "v"], ["alt", "1"]])
async def test_a_paste_or_option_chord_is_a_literal_typed_by_another_route(keys):
    sim = SimulatedActuator(targets=TargetRead("Notes", "textbox", None, None))
    cu = ComputerUse(Scripted(Action("key", {"keys": keys}), Done("done", True)), sim, make_guard(), navigator="n", facts=FactStore({"a.b": "x"}, {"a.b": lambda: "1"}))
    try:
        await cu.run("g", always_true)
    except BaseException:
        pass
    assert sim.actions == [], f"{keys} reached the actuator in fact-handle mode: {sim.actions}"
