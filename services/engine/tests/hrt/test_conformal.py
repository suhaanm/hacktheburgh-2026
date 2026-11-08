"""Conformal intervals and sets (evals/hrt/PLAN_CONFORMAL.md): the quantile rule, the sets and ranges, the finish-time model, causal columns, seeds, claims."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.hrt import conformal as cf
from understudy_engine.hrt import recal as rc
from understudy_engine.hrt import worlds as wd


# ----------------------------------------------------------------------------------------------------- the quantile rule
def test_the_quantile_is_the_ceil_n_plus_1_times_1_minus_alpha_order_statistic():
    s = np.arange(1.0, 10.0)                       # n = 9: ceil(10 * 0.9) = 9, the largest
    assert cf.conformal_quantile(s, 0.10) == 9.0
    s = np.arange(1.0, 20.0)                       # n = 19: ceil(20 * 0.9) = 18
    assert cf.conformal_quantile(s, 0.10) == 18.0
    s = np.arange(1.0, 101.0)                      # n = 100: ceil(101 * 0.9) = 91
    assert cf.conformal_quantile(s[::-1], 0.10) == 91.0                    # order does not matter


def test_too_few_calibration_scores_give_the_whole_range_not_a_narrow_one():
    assert cf.conformal_quantile(np.arange(1.0, 9.0), 0.10) == float("inf")      # n = 8: ceil(9 * 0.9) = 9 > 8
    assert cf.conformal_quantile(np.array([]), 0.10) == float("inf")


def test_split_conformal_covers_at_least_the_nominal_level_for_exchangeable_draws():
    rng = np.random.default_rng(0)
    covered = []
    for _ in range(300):
        cal = np.abs(rng.normal(size=199))
        q = cf.conformal_quantile(cal, 0.10)
        covered.append(np.abs(rng.normal(size=50)) <= q)
    cov = float(np.mean(np.concatenate(covered)))
    assert 0.885 <= cov <= 0.925, cov                                      # the guarantee is 0.90 on average with a small excess of 1 / (n + 1)


# ------------------------------------------------------------------------------------------------------------ sets (T0)
def test_a_label_is_in_the_set_when_one_minus_its_probability_is_within_the_quantile():
    p1 = np.array([0.95, 0.5, 0.05])
    has0, has1 = cf.lac_sets(p1, 0.4)
    assert has1.tolist() == [True, False, False]                          # 1 - p1 = 0.05, 0.5, 0.95
    assert has0.tolist() == [False, False, True]                          # p1 = 0.95, 0.5, 0.05
    has0, has1 = cf.lac_sets(p1, 0.6)
    assert has1.tolist() == [True, True, False] and has0.tolist() == [False, True, True]       # an uncertain case gets both labels
    assert cf.lac_scores(p1, np.array([1, 0, 1])).tolist() == pytest.approx([0.05, 0.5, 0.95])


def test_set_coverage_and_sizes_count_the_true_label_and_the_set_size():
    y = np.array([1, 0, 1, 0])
    has0 = np.array([False, True, True, False])
    has1 = np.array([True, True, False, False])
    assert cf.set_covered(y, has0, has1).tolist() == [True, True, False, False]
    assert cf.set_sizes(has0, has1) == {"empty": 0.25, "single": 0.5, "both": 0.25, "n": 4}


# ---------------------------------------------------------------------------------------------------- step ranges (T1)
def test_step_quantiles_are_the_first_step_whose_cdf_reaches_the_level_else_beyond():
    assert cf.T1_STEPS == 4 and cf.BEYOND == 5                             # amendment A1: a two-minute horizon, step 5 means "not within two minutes"
    cdf = np.array([[0.02, 0.10, 0.50, 0.96], [0.0] * 4, [0.30, 0.55, 0.9, 0.9]])
    assert cf.step_quantile(cdf, 0.05).tolist() == [2, 5, 1]
    assert cf.step_quantile(cdf, 0.95).tolist() == [4, 5, 5]


def test_the_range_widens_by_the_calibrated_quantile_and_a_negative_one_narrows_it():
    lo, hi, y = np.array([2, 3, 4]), np.array([3, 3, 4]), np.array([1, 3, 5])
    assert cf.cqr_scores(lo, hi, y).tolist() == [1, 0, 1]                  # outside by one step; on the edge; outside by one step
    assert cf.cqr_covered(lo, hi, y, 1).tolist() == [True, True, True]     # [1, 4], [2, 4], [3, 5]
    assert cf.cqr_covered(lo, hi, y, 0).tolist() == [False, True, False]   # [2, 3], [3, 3], [4, 4]
    assert cf.cqr_covered(lo, hi, y, -1).tolist() == [False, False, False]  # every range emptied
    assert cf.cqr_lengths(lo, hi, 1).tolist() == [4, 3, 3]                 # [1, 4], [2, 4], [3, 5]
    assert cf.cqr_lengths(np.array([1]), np.array([5]), 3).tolist() == [5]  # cannot be longer than the support 1..5
    assert cf.cqr_lengths(lo, hi, -1).tolist() == [0, 0, 0]                # an emptied range has length 0


# ---------------------------------------------------------------------------------------------- the finish-time model (T2)
def test_the_ridge_recovers_a_log_linear_law_and_shrinks_a_noise_column():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(4000, 3))
    y = 5.0 + 0.8 * X[:, 0] - 0.4 * X[:, 1] + rng.normal(0, 0.05, 4000)
    m = cf.FinishModel(ridge=1.0).fit(X, y)
    pred = m.predict(X)
    assert np.corrcoef(pred, y)[0, 1] > 0.99
    assert abs(m.coef_[2]) < 0.05 < abs(m.coef_[0])                       # the unrelated column gets about nothing (coefficients are per standardised column)
    assert cf.FinishModel(ridge=1.0).fit(X, y).predict(X[:5]).tolist() == pytest.approx(pred[:5].tolist())      # deterministic


def test_the_finish_columns_use_only_what_had_happened_by_the_origin():
    from understudy_engine.core import Episode
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.hazard.sim import simulate_people

    eps, _ = simulate_people(3, 14, seed=11)
    checked = 0
    for ep in sorted(eps, key=lambda e: -len(e.progress_t))[:12]:
        tab = build_bins([ep])
        X, remaining = cf.finish_columns([ep], tab)
        assert X.shape == (tab.n, 7) and remaining.shape == (tab.n,) and np.all(remaining >= 60.0 - 1e-6)
        assert np.allclose(remaining, ep.t1 - tab.t)
        for i in range(0, tab.n, 3):
            b = float(tab.t[i])
            cogs = [c for c in ep.cogs if c.t0 <= b]
            if not cogs:
                continue
            cut = Episode(task_id=ep.task_id, person=ep.person, role=ep.role, origin=ep.origin, t0=ep.t0, t1=b + 60.0, cogs=cogs,
                          progress_t=[t for t in ep.progress_t if t <= b])
            part = build_bins([cut])
            X2, _ = cf.finish_columns([cut], part)
            assert np.isclose(part.t[-1], b)
            assert np.allclose(X2[-1], X[i])                       # all seven columns at the origin are identical when the future is removed
            checked += 1
    assert checked >= 30


# ------------------------------------------------------------------------------------------------------------- seeds
def test_the_conformal_seeds_are_new_and_distinct_from_every_other_pool():
    mine = cf.conformal_seeds()
    flat = [s for v in mine.values() for s in v]
    assert len(flat) == len(set(flat))
    other = {s for v in wd.all_seeds().values() for s in v}
    other |= {wd.v1_seed(slug, k) for k in (*rc.RECAL_K, *rc.DEV_K) for slug in wd.BASES}
    other |= {wd.v2_seed(f, k) for k in (*rc.RECAL_K, *rc.DEV_K) for f in wd.FAMILIES}
    assert not (set(flat) & other), sorted(set(flat) & other)[:5]
    assert not (set(flat) & wd.known_used_seeds())
    assert cf.HELD_K == tuple(range(41, 49)) and cf.CAL_K == (31, 32, 33, 34) and cf.CAL_SHIFT_K == 51 and cf.DEV_K == (35, 36)
    assert len(mine["v1_cal"]) == 16 and len(mine["v1_held"]) == 32 and len(mine["v2_held"]) == 24 and len(mine["v2_cal_shift"]) == 3


# ------------------------------------------------------------------------------------------------ origins and a small world
@pytest.fixture(scope="module")
def tiny():
    from understudy_engine.hazard.sim import simulate_people

    train, _ = simulate_people(4, 24, seed=21)
    cal, _ = simulate_people(4, 12, seed=22)
    test, _ = simulate_people(3, 10, seed=23)
    models = cf.fit_models(train)
    return models, cf.origins_for(models, cal, 0), cf.origins_for(models, test, 0)


def test_origins_line_up_with_the_bins_and_censoring_is_flagged(tiny):
    _, cal, _ = tiny
    assert cal.p_model.shape == cal.y.shape == cal.log_r.shape == cal.person.shape
    assert cal.cdf.shape == (cal.y.size, cf.T1_STEPS)
    assert np.all(cal.step_y[cal.full] >= 1) and np.all(cal.step_y[cal.full] <= cf.BEYOND) and np.all(cal.step_y[~cal.full] == 0)
    assert 0.0 < cal.full.mean() <= 1.0
    assert np.all((cal.cdf >= 0) & (cal.cdf <= 1 + 1e-9)) and np.all(np.diff(cal.cdf, axis=1) >= -1e-9)


def test_calibrating_on_a_pool_covers_that_pool_at_least_at_the_nominal_level(tiny):
    models, cal, _ = tiny
    c = cf.calibrate(cal, models)
    ev = cf.evaluate(cal, c, models, B=60, seed=0)
    for t in ("t0", "t1", "t2"):
        assert ev[t]["coverage"]["est"] >= 0.895, (t, ev[t]["coverage"])  # same pool: coverage is at least the level, up to one score of discreteness
    assert set(ev["t0"]["sizes"]) >= {"single", "both", "empty"}
    assert ev["t2"]["factor_model"] == pytest.approx(np.exp(2 * c["t2"]))


def test_recentring_removes_a_pure_bias_from_the_finish_range_and_changes_nothing_else(tiny):
    models, cal, _ = tiny
    biased = cf.Origins(**{**cal.__dict__, "yhat": cal.yhat + 2.0})
    c0, c1 = cf.calibrate(cal, models), cf.calibrate(biased, models)
    assert c1["t2"] > c0["t2"] + 1.0                                       # the plain quantile has to absorb the bias, so the range is far wider
    assert c1["t2_recentred"] == pytest.approx(c0["t2_recentred"], abs=1e-9)
    assert c1["t2_shift"] == pytest.approx(c0["t2_shift"] - 2.0)
    assert c1["t0"] == c0["t0"] and c1["t1"] == c0["t1"]                   # T0 and T1 do not look at the finish model
    ev = cf.evaluate(biased, c1, models, B=40, seed=0)
    assert ev["t2"]["recentred"]["coverage"]["est"] >= 0.895 and ev["t2"]["recentred"]["factor"] == pytest.approx(np.exp(2 * c1["t2_recentred"]))


def test_a_run_on_a_small_world_is_deterministic_and_has_the_claim_inputs(tiny):
    models, cal, test = tiny
    c = cf.calibrate(cal, models)
    a = cf.evaluate(test, c, models, B=60, seed=0)
    b = cf.evaluate(test, c, models, B=60, seed=0)
    assert a == b
    for t in ("t0", "t1", "t2"):
        lo, hi = a[t]["coverage"]["ci"]
        assert 0.0 <= lo <= a[t]["coverage"]["est"] <= hi <= 1.0
    assert "length_vs_km" in a["t1"] and "baseline" in a["t2"] and a["t0"]["baseline"]["coverage"]["est"] <= 1.0
    assert len(a["by_deployment"]) == 1 and set(a["by_deployment"][0]) >= {"t0", "t1", "t2", "n"}


# ----------------------------------------------------------------------------------------------------------------- claims
def _cov(lo, est, hi):
    return {"est": est, "ci": [lo, hi]}


def _world(t0, t1, t2, *, dep_cov=(0.9,), flags=(False,)):
    return {"standard": {"t0": {"coverage": t0}, "t1": {"coverage": t1, "length_vs_km": {"est": -1.0, "ci": [-1.5, -0.5]}}, "t2": {"coverage": t2, "q_model": 0.5, "q_baseline": 0.7},
                         "by_deployment": [{"t0": {"coverage": c}} for c in dep_cov]},
            "recalibrated": {"t0": {"coverage": t0}, "t1": {"coverage": t1}, "t2": {"coverage": t2}},
            "guard": {"flagged": list(flags)}}


def test_judge_applies_each_pass_rule_as_registered():
    good = _cov(0.88, 0.90, 0.92)
    under = _cov(0.60, 0.65, 0.70)
    worlds = {"v1": _world(good, good, good, dep_cov=[0.9] * 8, flags=[False] * 8)}
    for f in wd.FAMILIES:
        worlds[f] = _world(under, under, under, dep_cov=[0.7] * 8, flags=[True] * 8)
    claims = {c["id"]: c for c in cf.judge_conformal(worlds)}
    assert list(claims) == ["K1a", "K1b", "K1c", "K2a", "K2b", "K2c", "K3", "K4", "K5a", "K5b", "K5c"]
    assert all(claims[k]["pass"] is True for k in ("K1a", "K1b", "K1c", "K2a", "K2b", "K2c", "K3", "K4"))
    assert all(claims[k]["pass"] is False for k in ("K5a", "K5b", "K5c"))           # the recalibrated arm was given the under-covering numbers above


def test_k1_fails_when_the_interval_misses_the_nominal_and_k2_needs_two_of_three_worlds():
    good, low, under = _cov(0.88, 0.90, 0.92), _cov(0.80, 0.83, 0.86), _cov(0.60, 0.65, 0.70)
    worlds = {"v1": _world(low, good, good, dep_cov=[0.9] * 8, flags=[False] * 8)}
    for f, c in zip(wd.FAMILIES, (under, under, good)):
        worlds[f] = _world(c, c, c, dep_cov=[0.9] * 8, flags=[False] * 8)
    claims = {c["id"]: c for c in cf.judge_conformal(worlds)}
    assert claims["K1a"]["pass"] is False and claims["K1b"]["pass"] is True
    assert claims["K2a"]["pass"] is True and claims["K2a"]["evidence"]["worlds_under"] == 2
    worlds[wd.FAMILIES[1]] = _world(good, good, good)
    assert {c["id"]: c for c in cf.judge_conformal(worlds)}["K2a"]["pass"] is False


def test_k4_is_not_testable_with_fewer_than_three_low_coverage_deployments_and_fails_on_a_missed_flag():
    good = _cov(0.88, 0.90, 0.92)
    worlds = {"v1": _world(good, good, good, dep_cov=[0.9] * 8, flags=[False] * 8)}
    worlds["markov"] = _world(good, good, good, dep_cov=[0.9] * 7 + [0.8], flags=[False] * 8)          # one low deployment, never flagged
    worlds["latent_skill"] = _world(good, good, good, dep_cov=[0.9] * 8, flags=[False] * 8)
    worlds["process_trace"] = _world(good, good, good, dep_cov=[0.9] * 7 + [0.8], flags=[False] * 8)   # two low in all
    k4 = {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]
    assert k4["pass"] is None and k4["evidence"]["low_coverage_deployments"] == 2                       # fewer than three: not testable, neither passed nor failed
    worlds["markov"] = _world(good, good, good, dep_cov=[0.7] * 8, flags=[True] * 7 + [False])
    k4 = {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]
    assert k4["pass"] is False and k4["evidence"]["low_not_flagged"] == 2 and k4["evidence"]["low_coverage_deployments"] == 9      # one in markov, one in process trace
    worlds["markov"] = _world(good, good, good, dep_cov=[0.7] * 8, flags=[True] * 8)
    assert {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]["pass"] is False                      # the other low deployment (process trace) was not flagged
    worlds["process_trace"] = _world(good, good, good, dep_cov=[0.7] * 8, flags=[True] * 8)
    assert {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]["pass"] is True                       # every low deployment flagged and v1 quiet
    worlds["v1"] = _world(good, good, good, dep_cov=[0.9] * 8, flags=[True] * 2 + [False] * 6)
    k4 = {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]
    assert k4["pass"] is False and k4["evidence"]["v1_flags"] == 2
    worlds["v1"] = _world(good, good, good, dep_cov=[0.9] * 8, flags=[True] + [False] * 7)
    assert {c["id"]: c for c in cf.judge_conformal(worlds)}["K4"]["pass"] is True                       # one false flag in eight is within the registered bound


# --------------------------------------------------------------------------------------------------- a world, end to end
def test_run_world_returns_both_arms_the_guard_and_the_two_by_two_and_is_deterministic():
    from understudy_engine.hazard.sim import simulate_people

    train, _ = simulate_people(4, 24, seed=31)
    models = cf.fit_models(train)
    cal = cf.calibrate(cf.concat([cf.origins_for(models, simulate_people(3, 10, seed=32 + i)[0], i) for i in range(2)]), models)
    shift = cf.calibrate(cf.origins_for(models, simulate_people(3, 10, seed=40)[0], 0), models)
    deps = [(f"d{i}", simulate_people(2, 24, seed=50 + i)[0]) for i in range(3)]               # the ledger refuses to score fewer than 200 resolved forecasts
    a = cf.run_world("tiny", models, deps, cal, shift, B=40, seed=0)
    b = cf.run_world("tiny", models, deps, cal, shift, B=40, seed=0)
    assert a == b
    assert a["n_deployments"] == 3 and len(a["standard"]["by_deployment"]) == 3 and len(a["guard"]["flagged"]) == 3
    two = a["guard"]["low_vs_flag"]
    assert two["low_flagged"] + two["low_not_flagged"] + two["ok_flagged"] + two["ok_not_flagged"] == 3
    assert set(a["recalibrated"]) >= {"t0", "t1", "t2"} and a["recalibration_pool"]["people"] == 3
    only_standard = cf.run_world("tiny", models, deps, cal, None, B=40, seed=0)
    assert "recalibrated" not in only_standard


def test_the_heldout_command_refuses_without_the_token_and_without_a_freeze(monkeypatch):
    from understudy_engine.hrt import freeze as fz
    from understudy_engine.hrt import run_conformal as rcf

    monkeypatch.delenv(wd.HELDOUT_ENV, raising=False)
    assert rcf.main(["heldout"]) == 3                                           # no token
    monkeypatch.setenv(wd.HELDOUT_ENV, "1")
    monkeypatch.setattr(fz, "read_frozen", lambda: {"parts": {}})
    assert rcf.main(["heldout"]) == 3                                           # no freeze of this part
    assert "conformal" in fz.ALL_PARTS and "conformal" not in fz.PARTS          # `run.py dev|freeze all` still means the first two parts only
    h = fz.code_hashes("conformal")
    assert {"conformal.py", "run_conformal.py", "PLAN_CONFORMAL.md", "PLAN.md", "guard.py", "prospective.py"} <= set(h)
