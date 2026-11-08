"""The guard: an e-process with a bounded false-flag rate, a premium and a payout, scored against the oracle (PLAN.md section 4.1)."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.hrt import guard as g


def test_capital_moves_by_the_bet_and_never_goes_negative():
    ep = g.EProcess(lam=0.8, B=4.6, threshold=20.0)
    ep.update(0.0)
    assert ep.capital == 1.0
    ep.update(4.6)                                     # the model lost by the maximum: capital grows by 1 + lambda
    assert np.isclose(ep.capital, 1.8)
    ep.update(-4.6)                                    # the model won by the maximum: capital falls to the floor 1 - lambda
    assert np.isclose(ep.capital, 1.8 * 0.2)
    ep.update(100.0)                                   # clipped to B
    ep.update(-100.0)
    assert ep.capital > 0


def test_lambda_must_be_inside_zero_one():
    with pytest.raises(ValueError):
        g.EProcess(lam=1.0).update(0.1)
    with pytest.raises(ValueError):
        g.EProcess(lam=0.0).update(0.1)


def test_flag_is_raised_once_when_the_capital_first_reaches_the_threshold():
    ep = g.EProcess(lam=0.8, B=4.6, threshold=20.0)
    flags = [ep.update(2.0) for _ in range(40)]
    assert sum(flags) == 1 and ep.flagged and ep.flagged_at == flags.index(True) + 1


def test_ville_bound_holds_by_simulation_under_the_null():
    """When the model is no worse (the loss difference has conditional mean <= 0), the chance of ever flagging is at most 5%."""
    rng = np.random.default_rng(0)
    n_runs, flags = 600, 0
    for _ in range(n_runs):
        d = np.clip(rng.normal(0.0, 0.8, 400), -4.6, 4.6)          # mean exactly 0: the boundary of the null
        ep = g.EProcess()
        for x in d:
            ep.update(x)
        flags += ep.flagged
    assert flags / n_runs <= 0.05 + 0.025                           # 5% plus Monte Carlo slack


def test_a_model_that_is_worse_is_flagged_and_a_model_that_is_better_is_not():
    rng = np.random.default_rng(1)
    worse = [g.EProcess() for _ in range(50)]
    better = [g.EProcess() for _ in range(50)]
    for ep in worse:
        for x in np.clip(rng.normal(0.4, 0.8, 300), -4.6, 4.6):
            ep.update(x)
    for ep in better:
        for x in np.clip(rng.normal(-0.2, 0.8, 300), -4.6, 4.6):
            ep.update(x)
    assert sum(e.flagged for e in worse) >= 48
    assert sum(e.flagged for e in better) == 0


def _bins(n_units: int, per: int, model_extra: float, seed: int = 0):
    """n_units episodes of ``per`` bins each, made at increasing times; the model's loss is the fallback's plus ``model_extra`` on average."""
    rng = np.random.default_rng(seed)
    n = n_units * per
    unit = np.repeat(np.arange(n_units), per)
    made = np.arange(n, dtype=float) * 30.0
    res = made + 60.0
    fb = np.clip(rng.normal(0.5, 0.2, n), 0.05, 3.0)
    mo = np.clip(fb + rng.normal(model_extra, 0.2, n), 0.01, 4.6)
    return unit, made, res, mo, fb


def test_units_are_ordered_by_when_their_last_outcome_resolved_and_the_guard_returns_a_flag_time():
    unit, made, res, mo, fb = _bins(80, 10, model_extra=0.6)
    u = g.units_from_bins(unit, made, res, mo, fb)
    assert np.all(np.diff(u.resolved_at) >= 0) and u.n_bins.sum() == 800
    r = g.run_guard(u)
    assert r["flagged"] and r["flag_time"] is not None and r["flag_time"] <= u.resolved_at.max()
    assert r["flag_unit"] < 80


def test_the_guard_does_not_flag_a_better_model_and_costs_nothing_then():
    unit, made, res, mo, fb = _bins(80, 10, model_extra=-0.15)
    r = g.run_guard(g.units_from_bins(unit, made, res, mo, fb))
    assert not r["flagged"] and r["flag_time"] is None
    c = g.strategy_costs(made, mo, fb, r["flag_time"])
    assert c["guarded"] == c["always_model"] and c["regret_guarded"] == c["regret_always_model"] == 0.0 and c["share_on_fallback"] == 0.0


def test_premium_and_payout_are_accounted_against_the_oracle():
    unit, made, res, mo, fb = _bins(80, 10, model_extra=0.6)
    r = g.run_guard(g.units_from_bins(unit, made, res, mo, fb))
    c = g.strategy_costs(made, mo, fb, r["flag_time"])
    assert c["oracle"] == min(c["always_model"], c["always_fallback"]) == c["always_fallback"]
    assert c["guarded"] < c["always_model"]                                        # the payout
    assert c["guarded"] >= c["always_fallback"] - 1e-12                            # it cannot beat the oracle here
    assert c["regret_guarded"] < c["regret_always_model"] and c["regret_always_fallback"] == 0.0
    assert 0.0 < c["share_on_fallback"] < 1.0
    # switching is by the time the prediction was made, not by the unit order: predictions made before the flag keep the model
    pre = made <= r["flag_time"]
    assert np.isclose(c["guarded"], np.mean(np.where(pre, mo, fb)))


def test_the_guard_uses_only_what_had_resolved_when_the_flag_was_raised():
    """The e-process is fed unit by unit in resolution order; shuffling the input rows must not change the result."""
    unit, made, res, mo, fb = _bins(60, 8, model_extra=0.5, seed=3)
    a = g.run_guard(g.units_from_bins(unit, made, res, mo, fb))
    perm = np.random.default_rng(9).permutation(unit.size)
    b = g.run_guard(g.units_from_bins(unit[perm], made[perm], res[perm], mo[perm], fb[perm]))
    assert (a["flagged"], a["flag_unit"], a["flag_time"], a["n_units"]) == (b["flagged"], b["flag_unit"], b["flag_time"], b["n_units"])
    assert np.isclose(a["final_capital"], b["final_capital"], rtol=1e-9)           # summation order differs in the last digits only
