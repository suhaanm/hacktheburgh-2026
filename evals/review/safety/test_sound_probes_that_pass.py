"""SOUND: properties I tried hard to break and could not. These PASS today; they are regression guards, not findings."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from fakes import FakeBackend, Scripted, always_true, mac, make_guard
from understudy_agent.audit import AuditLog
from understudy_agent.models.port import Action, Done
from understudy_agent.queue import ApprovalQueue
from understudy_agent.sandbox_sites.households import Adult, Household
from understudy_agent.security.actions import validate_action
from understudy_agent.security.killflag import set_kill
from understudy_agent.security.settings import Origin
from understudy_agent.tiers.computer_use import ActuatorRefused, ComputerUse
from understudy_agent.tiers.facts import FactStore


async def test_kill_file_written_mid_type_stops_within_one_chunk(tmp_path):
    be = FakeBackend()
    act = mac(be, tmp_path)
    await act.screenshot()
    await act.execute(Action("click", {"x": 600, "y": 500}))
    be.on_type = lambda t: (tmp_path / "KILL").write_text("x") if len(be.typed_chunks()) == 2 else None
    with pytest.raises(ActuatorRefused, match="kill"):
        await act.execute(Action("type", {"text": "y" * 120}))
    assert len(be.typed_chunks()) == 2 and be.released >= 1


async def test_mixed_scale_screens_are_refused_not_guessed(tmp_path):
    with pytest.raises(ActuatorRefused, match="scale disagreement"):
        await mac(FakeBackend(backing=1.0, shot_scale=2.0), tmp_path).screenshot()      # the 7 Nov bug, both directions
    with pytest.raises(ActuatorRefused, match="scale disagreement"):
        await mac(FakeBackend(backing=2.0, shot_scale=1.0), tmp_path).screenshot()


def test_approvals_expire_after_30_minutes_and_work_once(tmp_path):
    t = [datetime.now(timezone.utc).timestamp()]
    q = ApprovalQueue(tmp_path / "q", clock=lambda: t[0])
    sig = validate_action("click_element", {"selector": "#go"}).signature
    it = q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature=sig)
    q.approve(it["id"], origin=Origin.HUMAN_UI)
    assert q.consume_approval(it["id"], sig) and not q.consume_approval(it["id"], sig)               # once
    it2 = q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature=sig)
    q.approve(it2["id"], origin=Origin.HUMAN_UI)
    t[0] += 1801
    assert q.try_consume_approval(it2["id"], sig).code == "expired"                                  # 30 minutes + 1 s
    with pytest.raises(Exception):
        q.approve(it2["id"], origin=Origin.AGENT)                                                    # only HUMAN_UI decides


def test_the_pipeline_blocks_everything_while_the_kill_flag_exists():
    set_kill("test")
    dec = make_guard().authorise(Action("wait", {}), make_guard().observe_screen())
    assert dec.verdict == "block" and dec.codes == ["kill:kill_flag"]


async def test_canary_values_reach_only_the_actuator(tmp_path):
    canary = Household(id="hh_c", case_ref="CASE-9999", region="england", adults=(Adult(47, 7777.0),), children_ages=(), tenure="rent",
                       rent_monthly=4243.0, bedrooms=3, savings=7777321.0, childcare_monthly=0.0)
    facts, be, events = FactStore.for_calculator("a", canary), FakeBackend(), []
    model = Scripted(Action("click", {"x": 600, "y": 500}), Action("type", {"text": "{household.savings}"}), Action("type", {"text": "{household.rent}"}), Done("done", True))
    guard = make_guard()
    res = await ComputerUse(model, mac(be, tmp_path), guard, navigator="n", facts=facts, emit=events.append).run("g", always_true)
    assert "".join(be.typed_chunks()) == "7777321" + "4243"                                           # the OS got the values...
    blob = json.dumps([e.as_dict() for e in events]) + json.dumps(res.history) + "".join(p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file())
    assert "7777321" not in blob and "4243" not in blob                                               # ...and nothing written or logged did
