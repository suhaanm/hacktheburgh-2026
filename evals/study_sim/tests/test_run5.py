"""Exploratory run 5: design, pilot criterion, gates, planner tier. Made-up numbers and a stub port only."""
from __future__ import annotations

import json
from collections import Counter

import pytest

from evals.study_sim import design, pilot
from evals.study_sim.budget import Budget
from evals.study_sim.design import build_pilot_participants, build_run5_participants

from .conftest import made_up_rows
from .test_observe_participant import StubPort, _ctx


def test_run5_design_is_balanced_and_ids_do_not_clash():
    r5, pil, r4 = build_run5_participants(), build_pilot_participants(), design.build_participants()
    assert len(r5) == 12 and Counter(s.arm for s in r5) == {"coached": 8, "aa": 4}
    assert Counter(s.sequence for s in r5 if s.arm == "coached") == {q: 2 for q in design.SEQUENCES}
    assert Counter(s.sequence for s in r5 if s.arm == "aa") == {q: 1 for q in design.SEQUENCES}
    assert [s.arm for s in r5[:8]] == ["coached"] * 8                               # the A/A control is what a budget stop would lose
    for k in (4, 8):
        c = Counter(s.sequence for s in r5[:k] if s.arm == "coached")
        assert max(c.values()) - min(c.get(q, 0) for q in design.SEQUENCES) <= 1
    assert len(pil) == 3 and {s.arm for s in pil} == {"aa"} and [s.sequence for s in pil] == ["S1", "S2", "S3"]
    ids = [s.pid for s in r5 + pil + r4]
    assert len(ids) == len(set(ids)) and all(s.pid.startswith("p_ex") for s in r5) and all(s.pid.startswith("p_pil") for s in pil)
    # run 4's participants are unchanged by the refactor
    assert [s.pid for s in r4] == [f"p_sim{i:02d}" for i in range(1, 25)] and Counter(s.arm for s in r4) == {"coached": 16, "aa": 8}


def _pilot_rows(specs, scores):
    it = iter(scores)
    return made_up_rows(specs, lambda s, b: next(it))


def test_pilot_passes_when_half_the_post_tests_are_off_the_floor():
    pil = build_pilot_participants()
    # 6 post-tests; block order per participant, scores as checks done (cliff out of 2, reconcile out of 1)
    rows = _pilot_rows(pil, [1, 1, 0, 0, 2, 0])                                     # 3 of 6 above zero
    d = pilot.decide(rows, pilot_spend_usd=0.6)
    assert d["pass"] and d["post_tests_above_zero"] == 3 and d["needed_above_zero"] == 3 and d["n_planned"] == 12
    assert d["mean_cost_per_participant_usd"] == 0.2 and d["projected_cost_per_participant_usd"] == 0.25 and d["affordable_participants"] == 25


def test_pilot_fails_on_the_floor_and_on_exclusions_and_when_unaffordable():
    pil = build_pilot_participants()
    low = pilot.decide(_pilot_rows(pil, [1, 0, 0, 0, 0, 0]), 0.5)
    assert not low["pass"] and low["n_planned"] == 0 and "scored above zero" in low["reasons_for_stopping"][0]
    rows = _pilot_rows(pil, [1, 1, 1, 1, 1, 1])
    rows[0]["exclusion"] = "harness error"
    ex = pilot.decide(rows, 0.5)
    assert not ex["pass"] and "incomplete" in ex["reasons_for_stopping"][0]
    ok_rows = _pilot_rows(pil, [1, 1, 1, 1, 1, 1])
    cheap = pilot.decide(ok_rows, 0.6)                                              # US$0.20 each: projected 0.25, 6.4 left -> 25 affordable
    assert cheap["pass"] and cheap["n_planned"] == 12
    mid = pilot.decide(ok_rows, 3.0)                                                # US$1 each: projected 1.25, 4.0 left -> 3 affordable: stop
    assert not mid["pass"] and mid["n_planned"] == 0 and "not affordable" in mid["reasons_for_stopping"][0]
    eight = pilot.decide(ok_rows, 1.5)                                              # US$0.5 each: projected 0.625, 5.5 left -> 8 affordable
    assert eight["pass"] and eight["n_planned"] == 8
    twelve_no = pilot.decide(ok_rows, 1.8)                                          # 0.75 projected, 5.2 left -> 6 affordable: stop
    assert not twelve_no["pass"]


def test_run5_gates(monkeypatch, tmp_path, capsys):
    from evals.study_sim import __main__ as m

    class A:
        stage = "pilot"; pace = 0.1; cap = 1; poll = 1.0; workers = 1

    monkeypatch.setattr(m, "GO5_FILE", tmp_path / "no-go5")
    assert m.cmd_run5(A()) == 2 and "no GO5" in capsys.readouterr().out
    go = tmp_path / "GO5"
    go.write_text("x")
    monkeypatch.setattr(m, "GO5_FILE", go)
    monkeypatch.delenv("STUDY_SIM_PRICE_IN", raising=False)
    monkeypatch.delenv("STUDY_SIM_PRICE_OUT", raising=False)
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    assert m.cmd_run5(A()) == 2 and "STUDY_SIM_PRICE_IN" in capsys.readouterr().out
    monkeypatch.setenv("STUDY_SIM_PRICE_IN", "1")
    monkeypatch.setenv("STUDY_SIM_PRICE_OUT", "5")
    monkeypatch.setattr(m, "RESULTS5", tmp_path / "r5")
    A.stage = "main"
    assert m.cmd_run5(A()) == 2 and "pilot has not passed" in capsys.readouterr().out      # no PILOT_DECISION.json


@pytest.mark.asyncio
async def test_planner_tier_uses_plan_not_check(specs, tmp_path):
    from evals.study_sim.participant import ModelParticipant

    class PlanPort(StubPort):
        def plan(self, messages, schema=None):
            self.prompts.append(("plan", messages[0]["role"]))
            self.stats["input_tokens"] += 500
            self.stats["output_tokens"] += 40
            return {"thought": "t", "actions": [{"kind": "wait", "seconds": 1}]}

        def check(self, prompt, schema):
            raise AssertionError("the planner tier must not call check")

    port = PlanPort([])
    mp = ModelParticipant(port, specs[0], Budget(), "planner-model", cache_dir=tmp_path / "c", tier="planner")
    assert [a.kind for a in await mp.decide(_ctx(specs[0]))] == ["wait"] and port.prompts == [("plan", "user")]
    other = ModelParticipant(port, specs[0], Budget(), "planner-model", cache_dir=tmp_path / "c", tier="fast")
    assert other.tier == "fast"
    from evals.study_sim.participant import cache_key
    assert cache_key("planner-model", "p", {}) != cache_key("planner:planner-model", "p", {})


def test_frozen_pipeline_fingerprints_match_the_declared_ones():
    import pytest as _p
    from evals.study_sim import __main__ as m
    from evals.study_sim.infra import fingerprint_dir
    if not (m.FROZEN4 / "snapshot").is_dir():
        _p.skip("frozen_run4/ is not on this machine")
    assert fingerprint_dir(m.FROZEN4 / "snapshot") == m.RUN5_PIPELINE_FINGERPRINT
    for k, v in m.RUN5_EXT_FINGERPRINTS.items():
        assert fingerprint_dir(m.FROZEN4 / k, ()) == v
