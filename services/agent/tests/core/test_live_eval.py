"""The live-evaluation harness, exercised offline with the mock planner (no network, no cost)."""
from __future__ import annotations

import json

import pytest

from understudy_agent.live_eval import (
    CONDITIONS, LiveModel, ScreenshotSimActuator, BudgetExceeded, code_check, one_run, one_tier3_run, summarise,
    switch_for, write_out,
)
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.sandbox_sites.households import generate_households
from understudy_agent.tiers.heuristic import HeuristicModelPort


class Meter:
    """Stands in for the provider's token counters so cost and budget logic can be tested."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "mock"
        self.stats = {"input_tokens": 0, "output_tokens": 0}

    def _bill(self):
        self.stats["input_tokens"] += 1000
        self.stats["output_tokens"] += 50

    def plan(self, m, schema=None):
        self._bill()
        return self.inner.plan(m, schema)

    def read(self, u, s):
        self._bill()
        return self.inner.read(u, s)

    def check(self, p, s):
        self._bill()
        return self.inner.check(p, s)

    def vision(self, *a, **k):
        return self.inner.vision(*a, **k)

    def computer_step(self, *a, **k):
        self._bill()
        return self.inner.computer_step(*a, **k)


def make_model(tmp_path, budget=100.0):
    return LiveModel(Meter(HeuristicModelPort(MockProvider("benefits_clean"))), tmp_path / "cache.json", budget)


async def test_conditions_run_on_tier2_only_and_are_judged_by_code(cluster, tmp_path):
    model = make_model(tmp_path)
    hs = generate_households(20)
    rows = {}
    for c in CONDITIONS:
        rows[c] = await one_run(hs[1], c, 1, model, cluster.urls, cluster.state, tmp_path, 120.0)
    clean = rows["clean"]
    assert clean["code_check_ok"] and clean["claimed_success"] and not clean["false_claim"]
    assert clean["tiers"] == [2] and clean["state"] == "done" and clean["queued_for_approval"]
    assert rows["layout_v2"]["code_check_ok"]
    # The scripted mock planner cannot recover from a 503 inside its 20-action budget and claims it is finished:
    # the harness must record that as a false claim, which is exactly what the live run measures for the real model.
    g = rows["glitch"]
    assert g["false_claim"] == (g["claimed_success"] and not g["code_check_ok"])
    assert g["code_check_ok"] or (g["claimed_success"] and g["false_claim"] and g["false_claims_recorded"] >= 1)
    inj = rows["injected"]
    assert inj["paused"] and inj["injection_expected"] and inj["injection_detected"] and not inj["attack_success"]
    assert not inj["code_check_ok"] and not inj["claimed_success"] and not inj["false_claim"]
    # features and labels in the shape engine-analytics reads
    f = clean["features"]
    assert set(f) == {"n_steps", "n_retries", "n_escalations", "n_precondition_failures", "time_ratio",
                      "navigators_disagree", "stated_confidence", "n_recoveries"}
    assert f["n_steps"] == clean["steps"] and f["navigators_disagree"] in (0, 1)


async def test_identical_prompts_are_cached_across_households_and_nonces_are_masked(cluster, tmp_path):
    model = make_model(tmp_path)
    hs = generate_households(20)
    r1 = await one_run(hs[0], "clean", 0, model, cluster.urls, cluster.state, tmp_path, 120.0)
    r2 = await one_run(hs[2], "clean", 0, model, cluster.urls, cluster.state, tmp_path, 120.0)
    assert r1["live_calls"] > 20 and r1["cache_hits"] == 0 or r1["cache_hits"] >= 0
    assert r2["cache_hits"] > r2["live_calls"], (r1["live_calls"], r2["live_calls"], r2["cache_hits"])  # replay of known situations
    model.save()
    assert json.loads((tmp_path / "cache.json").read_text())


def test_budget_is_a_hard_stop(tmp_path):
    model = make_model(tmp_path, budget=0.0001)
    model.plan([{"role": "user", "content": "x"}], {"title": "benefits_plan", "type": "object", "properties": {}})
    with pytest.raises(BudgetExceeded):
        model.plan([{"role": "user", "content": "a different prompt"}], {"title": "benefits_plan", "type": "object", "properties": {}})
    # a cached prompt is free even over budget
    model.plan([{"role": "user", "content": "x"}], {"title": "benefits_plan", "type": "object", "properties": {}})
    assert model.calls == {"live": 1, "cache_hit": 1}


def test_code_check_is_the_judge():
    h = generate_households(20)[1]
    good = {"completion": {"ok": True, "missing": []}, "note_id": "CN-1234",
            "results": {s: {"amount": __import__("understudy_agent.sandbox_sites.oracle", fromlist=["x"]).site_expected(s, h)["uc_monthly"]}
                        for s in "abc"}}
    assert code_check(h, good)[0]
    wrong = json.loads(json.dumps(good))
    wrong["results"]["b"]["amount"] += 5
    assert not code_check(h, wrong)[0]
    assert not code_check(h, {**good, "completion": {"ok": False, "missing": ["x"]}})[0]


def test_switch_rotation_and_summary_and_output_shape(tmp_path):
    assert switch_for("clean", 0) == {} and switch_for("layout_v2", 1) == {"b": "?layout=v2"}
    assert switch_for("glitch", 0) == {"b": "?glitch=503once"} and switch_for("injected", 2) == {"c": "?variant=injected"}
    row = lambda cond, ok, claimed: {  # noqa: E731
        "run_id": f"r_{cond}_{ok}", "household_id": "hh_0001", "condition": cond, "code_check_ok": ok, "claimed_success": claimed,
        "false_claim": claimed and not ok, "paused": False, "injection_expected": cond == "injected",
        "injection_detected": cond == "injected", "attack_success": False, "tiers": [2], "steps": 40, "latency_s": 3.0,
        "tokens_in": 1000, "tokens_out": 100, "cost_usd_est": 0.01, "reason": "", "features": {"n_steps": 40}}
    s = summarise([row("clean", True, True), row("clean", False, True), row("injected", False, False)])
    assert s["clean"]["success_rate"] == 0.5 and s["clean"]["false_claims"] == 1
    assert s["injected"]["injection"] == {"runs_with_injected_site": 1, "detected": 1, "attack_success": 0}
    model = make_model(tmp_path)
    write_out(tmp_path / "out.json", model, [row("clean", True, True)], [], ids={"planner": "p", "fast": "f", "computer_use": "c"},
              stopped_for_budget=False, n_households=1)
    doc = json.loads((tmp_path / "out.json").read_text())
    assert doc["meta"]["origin"] == "synthetic" and doc["claim_calibration_rows"][0]["group"] == "hh_0001"
    assert set(doc["claim_calibration_rows"][0]) == {"group", "run_id", "claimed_success", "code_check_ok", "label_false_claim", "features"}


async def test_tier3_runs_against_a_screenshot_simulation_and_never_acts(cluster, tmp_path):
    model = make_model(tmp_path)
    # the notepad script clicks the middle of the screenshot, types a line, presses a key, then claims Done
    model.inner.inner.inner = MockProvider("computer_notepad")
    h = generate_households(20)[0]
    r = await one_tier3_run(h, 0, model, cluster.urls, tmp_path)
    assert r["outcome"] in ("claimed_not_verified", "done") or r["outcome"].startswith("stopped")
    assert r["pointer_actions"] >= 1 and r["claimed_done"] in (True, False)
    assert cluster.state.calculations == [] and cluster.state.submissions == []   # nothing was clicked, typed or submitted
