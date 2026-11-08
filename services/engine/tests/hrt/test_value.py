"""Decision value against prediction accuracy (evals/hrt/PLAN_VALUE.md): the rule, the net value, the policies, the shares, the claims, the seeds."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.hrt import conformal as cf
from understudy_engine.hrt import recal as rc
from understudy_engine.hrt import value as vl
from understudy_engine.hrt import worlds as wd


# ---------------------------------------------------------------------------------------------------- rule and net value
def test_the_threshold_is_the_break_even_point_and_an_equal_forecast_interrupts():
    assert vl.threshold(1.0, 3.0) == pytest.approx(0.25)
    assert vl.threshold(3.0, 3.0) == pytest.approx(0.5)
    assert vl.interrupts(np.array([0.2499, 0.25, 0.9]), 0.25).tolist() == [False, True, True]


def test_net_value_is_s_when_it_helps_minus_a_when_it_does_not_and_zero_when_quiet():
    y = np.array([1, 0, 1, 0])
    go = np.array([True, True, False, False])
    assert vl.net_values(y, go, 3.0, 1.0).tolist() == [3.0, -1.0, 0.0, 0.0]
    assert vl.always_values(y, 3.0, 1.0).tolist() == [3.0, -1.0, 3.0, -1.0]
    assert vl.oracle_values(y, 3.0).tolist() == [3.0, 0.0, 3.0, 0.0]


def test_a_calibrated_forecast_is_worth_most_at_the_break_even_threshold():
    rng = np.random.default_rng(0)
    p = rng.random(200_000)
    y = (rng.random(p.size) < p).astype(int)
    vals = {tau: vl.net_values(y, vl.interrupts(p, tau), 3.0, 1.0).mean() for tau in (0.10, 0.25, 0.40)}
    assert vals[0.25] > vals[0.10] and vals[0.25] > vals[0.40]


def test_gap_closed_is_zero_at_the_floor_one_at_the_oracle_and_undefined_without_a_gap():
    assert vl.gap_closed(0.5, 0.5, 2.0) == 0.0 and vl.gap_closed(2.0, 0.5, 2.0) == 1.0 and vl.gap_closed(1.25, 0.5, 2.0) == pytest.approx(0.5)
    assert np.isnan(vl.gap_closed(1.0, 2.0, 2.0)) and np.isnan(vl.gap_closed(1.0, 3.0, 2.0))


def test_spearman_is_one_for_the_same_order_and_minus_one_for_the_reverse():
    assert vl.rank_agreement([0.1, 0.2, 0.3, 0.4], [4.0, 3.0, 2.0, 1.0]) == pytest.approx(1.0)          # lower loss with higher value agrees
    assert vl.rank_agreement([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, 4.0]) == pytest.approx(-1.0)


# --------------------------------------------------------------------------------------------------------------- guarded
def _arr(n=600, seed=0):
    rng = np.random.default_rng(seed)
    p = np.clip(rng.beta(2, 4, n), 0.02, 0.98)
    y = (rng.random(n) < p).astype(int)
    stream = np.array([f"s{i % 12}" for i in range(n)], dtype=object)
    return {"y": y, "stream": stream, "unit": np.array([f"u{i // 5}" for i in range(n)], dtype=object), "made_at": np.arange(n, dtype=float),
            "forecasts": {"model": p, "online_base": np.full(n, y.mean()), "frozen_tsp": np.clip(p + 0.1, 0.02, 0.98), "frozen_base": np.full(n, 0.3)}}


def test_the_guarded_forecast_is_the_model_until_the_flag_and_the_online_base_after_it():
    a = _arr(100)
    g_none = vl.guarded_forecast(a, None)
    assert np.array_equal(g_none, a["forecasts"]["model"])
    g = vl.guarded_forecast(a, 49.0)
    assert np.array_equal(g[:50], a["forecasts"]["model"][:50])                    # made at or before the flag time: still the model
    assert np.array_equal(g[50:], a["forecasts"]["online_base"][50:])


# -------------------------------------------------------------------------------------------------------------- a world
def test_score_world_reports_every_policy_and_pairs_the_model_with_each_naive_one():
    arrs = [_arr(600, 1), _arr(600, 2), _arr(600, 3)]
    flags = [None, None, 300.0]
    w = vl.score_world("tiny", arrs, flags, 3.0, 1.0, B=60, seed=0)
    assert set(w["policies"]) == {"model", "online_base", "frozen_tsp", "frozen_base", "guarded", "always", "never", "oracle"}
    for name, row in w["policies"].items():
        lo, hi = row["value_per_origin"]["ci"]
        assert lo <= row["value_per_origin"]["est"] <= hi, name
        assert row["per_hour"]["est"] == pytest.approx(120.0 * row["value_per_origin"]["est"])
    assert w["policies"]["never"]["value_per_origin"]["est"] == 0.0
    assert w["policies"]["oracle"]["value_per_origin"]["est"] >= max(w["policies"][k]["value_per_origin"]["est"] for k in ("model", "always", "never"))
    assert w["policies"]["oracle"]["gap_closed"]["est"] == pytest.approx(1.0)
    assert set(w["paired"]) == {"model_vs_online_base", "model_vs_frozen_tsp", "model_vs_frozen_base", "model_vs_best_naive"}
    assert w["best_naive"] in ("online_base", "frozen_tsp")
    assert w["guard"]["flags"] == 1 and len(w["guard"]["per_deployment"]) == 3
    assert set(w["log_loss"]) == {"model", "online_base", "frozen_tsp", "frozen_base"}
    assert set(w["sensitivity"]) == {str(a) for a in vl.A_GRID}
    assert -1.0 <= w["rank_agreement"]["spearman"] <= 1.0
    assert w == vl.score_world("tiny", arrs, flags, 3.0, 1.0, B=60, seed=0)


def test_a_better_ranking_than_the_naive_baselines_is_worth_more_net_minutes():
    rng = np.random.default_rng(5)
    n = 4000
    y = (rng.random(n) < 0.3).astype(int)
    good = np.clip(0.15 + 0.6 * y + rng.normal(0, 0.1, n), 0.02, 0.98)
    arr = {"y": y, "stream": np.array([f"s{i % 20}" for i in range(n)], dtype=object), "unit": np.array([f"u{i // 5}" for i in range(n)], dtype=object), "made_at": np.arange(n, dtype=float),
           "forecasts": {"model": good, "online_base": np.full(n, y.mean()), "frozen_tsp": np.full(n, 0.4), "frozen_base": np.full(n, y.mean())}}
    w = vl.score_world("good", [arr], [None], 3.0, 1.0, B=80, seed=0)
    assert w["paired"]["model_vs_online_base"]["ci"][0] > 0 and w["paired"]["model_vs_frozen_tsp"]["ci"][0] > 0


# ----------------------------------------------------------------------------------------------------------------- claims
def _est(lo, est, hi):
    return {"est": est, "ci": [lo, hi]}


def _vworld(vs_online, vs_tsp, vs_best, g):
    return {"paired": {"model_vs_online_base": vs_online, "model_vs_frozen_tsp": vs_tsp, "model_vs_best_naive": vs_best}, "best_naive": "online_base", "guard": {"guarded_minus_always_model": g, "flags": 0, "of": 8}}


def test_judge_applies_the_registered_rules():
    pos, neg, zero = _est(0.1, 0.2, 0.3), _est(-0.3, -0.2, -0.1), _est(-0.1, 0.0, 0.1)
    worlds = {"v1": _vworld(pos, pos, pos, _est(0.0, 0.0, 0.0))}
    for f in wd.FAMILIES:
        worlds[f] = _vworld(neg, neg, neg, pos)
    c = {x["id"]: x for x in vl.judge_value(worlds)}
    assert list(c) == ["V1", "V2", "V3a", "V3b"] and all(x["pass"] is True for x in c.values())
    worlds["v1"] = _vworld(pos, zero, pos, _est(-0.02, -0.01, 0.0))
    c = {x["id"]: x for x in vl.judge_value(worlds)}
    assert c["V1"]["pass"] is False and c["V3a"]["pass"] is False                   # one naive predictor not clearly beaten; the guard cost more than 0.01 minutes
    worlds["v1"] = _vworld(pos, pos, pos, _est(-0.01, -0.005, 0.0))
    assert {x["id"]: x for x in vl.judge_value(worlds)}["V3a"]["pass"] is True      # within the 0.01 bound
    worlds[wd.FAMILIES[0]] = _vworld(pos, pos, pos, zero)
    worlds[wd.FAMILIES[1]] = _vworld(neg, neg, zero, pos)
    c = {x["id"]: x for x in vl.judge_value(worlds)}
    assert c["V2"]["pass"] is False and c["V2"]["evidence"]["worlds_worse"] == 1     # the model is clearly worse for decisions in only one shifted world
    assert c["V3b"]["pass"] is True and c["V3b"]["evidence"]["worlds_paid"] == 2


# --------------------------------------------------------------------------------------------------------------- seeds, run
def test_the_value_seeds_are_new_and_distinct_from_every_other_pool():
    mine = vl.value_seeds()
    flat = [s for v in mine.values() for s in v]
    assert len(flat) == len(set(flat))
    other = {s for v in wd.all_seeds().values() for s in v}
    other |= {wd.v1_seed(slug, k) for k in (*rc.RECAL_K, *rc.DEV_K, *cf.CAL_K, *cf.DEV_K, *cf.HELD_K, cf.CAL_SHIFT_K, cf.DEV_CAL_SHIFT_K) for slug in wd.BASES}
    other |= {wd.v2_seed(f, k) for k in (*rc.RECAL_K, *rc.DEV_K, *cf.CAL_K, *cf.DEV_K, *cf.HELD_K, cf.CAL_SHIFT_K, cf.DEV_CAL_SHIFT_K) for f in wd.FAMILIES}
    assert not (set(flat) & other), sorted(set(flat) & other)[:5]
    assert not (set(flat) & wd.known_used_seeds())
    assert vl.HELD_K == tuple(range(61, 69)) and vl.DEV_K == (69, 70)
    assert len(mine["v1_held"]) == 32 and len(mine["v2_held"]) == 24


def test_run_world_replays_through_the_ledger_and_uses_the_guard_flag_time():
    from understudy_engine.hazard.sim import simulate_people

    train, _ = simulate_people(4, 24, seed=31)
    from understudy_engine.hrt import prospective as pr

    dep = pr.fit_deployed(train)
    deps = [(f"d{i}", simulate_people(2, 24, seed=70 + i)[0]) for i in range(3)]
    w = vl.run_world("tiny", dep, deps, B=40, seed=0)
    assert w["n_deployments"] == 3 and len(w["guard"]["flagged"]) == 3 and w["n_origins"] > 600
    assert w == vl.run_world("tiny", dep, deps, B=40, seed=0)


def test_the_heldout_command_refuses_without_the_token_and_a_freeze(monkeypatch):
    from understudy_engine.hrt import freeze as fz
    from understudy_engine.hrt import run_value as rv

    monkeypatch.delenv(wd.HELDOUT_ENV, raising=False)
    assert rv.main(["heldout"]) == 3
    monkeypatch.setenv(wd.HELDOUT_ENV, "1")
    monkeypatch.setattr(fz, "read_frozen", lambda: {"parts": {}})
    assert rv.main(["heldout"]) == 3
    assert "value" in fz.ALL_PARTS and "value" not in fz.PARTS
    assert {"value.py", "run_value.py", "PLAN_VALUE.md", "PLAN.md", "guard.py", "prospective.py"} <= set(fz.code_hashes("value"))
