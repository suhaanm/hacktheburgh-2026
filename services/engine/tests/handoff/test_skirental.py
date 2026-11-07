"""ANA-11: ski rental with predictions. The constants are checked by brute force, with the integer rounding."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.routines import skirental as sk
from understudy_engine.routines.simulate import SimConfig, regret_table


def test_the_rule_buys_early_when_the_prediction_says_it_pays_and_late_otherwise():
    assert sk.buy_run(y=20, b=10, lam=0.5) == 5          # y >= b: start of run ceil(lam b)
    assert sk.buy_run(y=5, b=10, lam=0.5) == 20          # y < b: start of run ceil(b / lam)
    assert sk.buy_after_runs(20, 10, 0.5) == 4 and sk.buy_after_runs(5, 10, 0.5) == 19
    assert sk.buy_run(y=10, b=10, lam=0.5) == 5          # y == b counts as "pays"
    assert sk.buy_run(0, 0, 0.5) == 1
    with pytest.raises(ValueError):
        sk.buy_run(1, 1, 1.0)
    assert sk.break_even_run(10) == 10


def test_cost_and_optimum():
    assert sk.cost(x=3, t=5, b=10) == 3                  # the run count ends before the purchase
    assert sk.cost(x=9, t=5, b=10) == 14                 # four rentals, then buy
    assert sk.optimum(3, 10) == 3 and sk.optimum(30, 10) == 10


@pytest.mark.parametrize("b", [1, 2, 3, 5, 8, 13, 40])
@pytest.mark.parametrize("lam", [0.1, 0.25, 0.5, 0.75, 0.9])
def test_robustness_and_consistency_hold_by_brute_force(b, lam):
    xs = range(0, 6 * b + 20)
    ys = sorted({0, 1, b - 1, b, b + 1, 2 * b, 5 * b} | set(range(0, 4 * b, max(1, b // 3))))
    worst_all, worst_exact = 0.0, 0.0
    for y in ys:
        t = sk.buy_run(y, b, lam)
        for x in xs:
            opt = sk.optimum(x, b)
            if opt == 0:
                assert sk.cost(x, t, b) == 0
                continue
            ratio = sk.cost(x, t, b) / opt
            worst_all = max(worst_all, ratio)
            if x == y:
                worst_exact = max(worst_exact, ratio)
    assert worst_all <= sk.robustness(lam) + 1e-9, (b, lam, worst_all)
    assert worst_exact <= sk.consistency(lam) + 1e-9, (b, lam, worst_exact)


def test_break_even_is_two_competitive():
    for b in (1, 4, 10, 33):
        t = sk.break_even_run(b)
        assert max(sk.cost(x, t, b) / sk.optimum(x, b) for x in range(1, 5 * b + 5)) < 2.0 + 1e-9


def test_choose_lambda_is_small_for_good_forecasts_and_large_for_bad_ones():
    assert sk.choose_lambda([]) == 0.5
    assert sk.choose_lambda([0.0, 0.0, 0.01]) == pytest.approx(0.15, abs=0.02)
    assert sk.choose_lambda([1.5, 2.0, -1.2]) == pytest.approx(0.85)
    assert sk.choose_lambda([0.2, -0.2, 0.2]) < sk.choose_lambda([0.8, -0.8, 0.8])


def test_plan_build_contract_fields():
    draws = np.array([5.0, 40.0, 40.0, 60.0])
    p = sk.plan_build(y=40, b=8, lam=0.5, run_draws=draws, runs_done=3)
    c = p.contract()
    assert c["rule"] == "ski-rental" and c["buy_after_runs"] == 3 and c["lambda"] == 0.5
    assert c["consistency"] == 1.5 and c["robustness"] == 3.0 and c["regret_vs_hindsight"] >= 0


def test_simulated_workdays_regret_against_hindsight_and_break_even():
    t = regret_table(SimConfig(n_routines=2500, b_values=(8.0, 16.0), lambdas=(0.2, 0.5, 0.8)))
    rows = t["rows"]
    for b in (8.0, 16.0):
        be = next(r for r in rows if r["rule"] == "break-even" and r["b"] == b)
        for lam in (0.2, 0.5):
            r = next(r for r in rows if r["rule"] == "predictions" and r.get("lambda") == lam and r["b"] == b)
            assert r["regret"] >= 0                                             # nothing beats hindsight
            assert r["vs_break_even"] < 0 and r["vs_break_even_ci"][1] < 0      # better than break-even, interval excludes 0
            assert r["worst_ratio"] <= r["bound_ratio"] + 1e-9                  # the robustness bound held on every simulated routine
        assert be["worst_ratio"] < 2.0
    # honest control: with useless predictions (shuffled) the rule still respects its robustness bound
    x, y = t["x"], t["y"].copy()
    np.random.default_rng(0).shuffle(y)
    b, lam = 8.0, 0.5
    worst = max((sk.cost(xi, sk.buy_run(yi, b, lam), b) / max(sk.optimum(xi, b), 1e-9)) for xi, yi in zip(x, y) if sk.optimum(xi, b) > 0)
    assert worst <= sk.robustness(lam) + 1e-9
