"""Online recalibration (evals/hrt/PLAN_RECAL.md): fitted only on resolved outcomes, starts as the model, learns a shift, does no harm without one."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.hazard.sim import simulate_people
from understudy_engine.hrt import prospective as pr
from understudy_engine.hrt import recal as rc
from understudy_engine.hrt import worlds as wd
from understudy_engine.store.paths import repo_root


def _stream(n: int, shift: float, slope: float = 1.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    s = rng.normal(-1.0, 1.2, n)
    p_model = 1 / (1 + np.exp(-s))
    y = (rng.random(n) < 1 / (1 + np.exp(-(slope * s + shift)))).astype(int)
    return p_model, y


def test_it_starts_as_the_model_and_changes_only_after_the_first_refit():
    p, y = _stream(500, 1.0)
    r = rc.OnlineRecal()
    for i in range(rc.REFIT_EVERY - 1):
        assert r.predict(p[i]) == pytest.approx(float(np.clip(p[i], 0.01, 0.99)), abs=1e-9)
        r.observe(p[i], y[i])
    r.observe(p[rc.REFIT_EVERY - 1], y[rc.REFIT_EVERY - 1])
    assert (r.a, r.b) != (0.0, 1.0)


def test_it_learns_an_intercept_shift_and_a_slope_change():
    p, y = _stream(6000, 1.0, seed=1)
    r = rc.OnlineRecal()
    for pi, yi in zip(p, y):
        r.observe(pi, yi)
    assert 0.8 < r.a < 1.2 and 0.85 < r.b < 1.15
    p2, y2 = _stream(6000, 0.0, slope=-0.3, seed=2)                    # a model that now points the wrong way
    r2 = rc.OnlineRecal()
    for pi, yi in zip(p2, y2):
        r2.observe(pi, yi)
    assert r2.b < 0.2


def test_the_ridge_keeps_a_barely_informed_fit_near_the_model():
    p, y = _stream(200, 2.0, seed=3)
    r = rc.OnlineRecal()
    for pi, yi in zip(p, y):
        r.observe(pi, yi)
    s = np.log(p / (1 - p))
    a, b = r.a, r.b
    a_free, b_free = rc.fit_ridge(s, y, ridge=0.0)
    # the penalised fit moves the forecast less (in logit units, on average) than the free fit does: it trusts the model until the outcomes say otherwise
    assert np.mean(np.abs(a + b * s - s)) < np.mean(np.abs(a_free + b_free * s - s))
    assert abs(a) < abs(a_free)


def test_a_forecast_never_uses_an_outcome_from_its_own_future():
    p, y = _stream(1000, 1.0, seed=4)
    y_changed = y.copy()
    y_changed[600:] = 1 - y_changed[600:]                              # only outcomes after index 600 differ
    a, b = rc.OnlineRecal(), rc.OnlineRecal()
    preds_a, preds_b = [], []
    for i in range(1000):
        preds_a.append(a.predict(p[i]))
        preds_b.append(b.predict(p[i]))
        a.observe(p[i], y[i])
        b.observe(p[i], y_changed[i])
    assert preds_a[:601] == preds_b[:601]                                # forecasts up to the first changed outcome are identical
    assert preds_a != preds_b


@pytest.fixture(scope="module")
def mini():
    train, _ = simulate_people(4, 40, seed=3)
    test, _ = simulate_people(4, 40, seed=104)
    dep = pr.fit_deployed(train)
    return dep, rc.replay_hazard_recal(dep, test, "mini")


def test_replay_writes_recal_beside_the_model_and_baselines_and_the_chain_verifies(mini):
    dep, led = mini
    arr = led.resolved("stuck_hazard")
    assert set(arr["names"]) == {pr.MODEL, pr.ONLINE, pr.TSP, pr.BASE, rc.RECAL, rc.RECAL_W} and arr["primary"] == rc.RECAL
    early_w = arr["made_at"] < np.sort(arr["resolved_at"])[rc.REFIT_EVERY - 1]
    assert np.allclose(arr["forecasts"][rc.RECAL_W][early_w], arr["forecasts"][rc.RECAL][early_w], atol=1e-6)         # until 2,000 have resolved the two arms agree
    assert led.verify() and led.pending("stuck_hazard") == 0
    order = np.argsort(arr["resolved_at"], kind="stable")
    first = order[: rc.REFIT_EVERY - 1]
    # before the first refit the recalibrated forecast is the model's, clipped
    early = arr["made_at"] < np.sort(arr["resolved_at"])[rc.REFIT_EVERY - 1]
    assert np.allclose(arr["forecasts"][rc.RECAL][early], np.clip(arr["forecasts"][pr.MODEL][early], 0.01, 0.99), atol=1e-5)
    assert not np.allclose(arr["forecasts"][rc.RECAL], np.clip(arr["forecasts"][pr.MODEL], 0.01, 0.99), atol=1e-5)
    assert first.size == rc.REFIT_EVERY - 1


def test_the_recalibrated_forecast_equals_a_fit_on_exactly_the_outcomes_resolved_by_then(mini):
    dep, led = mini
    arr = led.resolved("stuck_hazard")
    res = arr["resolved_at"]
    order = np.argsort(res, kind="stable")
    rs = res[order]
    s_all = np.log(np.clip(arr["forecasts"][pr.MODEL], 0.01, 0.99) / (1 - np.clip(arr["forecasts"][pr.MODEL], 0.01, 0.99)))
    checked = 0
    for i in np.random.default_rng(5).choice(arr["y"].size, 150, replace=False):
        n_res = int(np.searchsorted(rs, arr["made_at"][i], side="right"))
        k = (n_res // rc.REFIT_EVERY) * rc.REFIT_EVERY
        if k == 0 or k >= rs.size or rs[k - 1] == rs[k]:                 # skip before the first refit and ties that cut the batch
            continue
        use = order[:k]
        a, b = rc.fit_ridge(s_all[use], arr["y"][use])
        z = a + b * s_all[i]
        want = float(np.clip(1 / (1 + np.exp(-z)), 0.01, 0.99))
        assert arr["forecasts"][rc.RECAL][i] == pytest.approx(want, abs=1e-4)
        checked += 1
    assert checked >= 30


def test_the_claims_are_judged_by_the_registered_rules():
    def pv(est, lo, hi):
        return {"est": est, "ci": [lo, hi]}

    def world(vs_model, w_vs_model=None):
        return {"paired_log_loss_vs": {pr.MODEL: vs_model}, "w": {"paired_log_loss_vs": {pr.MODEL: w_vs_model or vs_model}}}

    cal_ok = {"intercept": 0.01, "intercept_ci": [-0.1, 0.1], "slope": 1.0, "slope_ci": [0.9, 1.1], "intercept_contains_0": True}
    drift = {"second_half": {"n": 100, "recal_vs_model": pv(-0.05, -0.07, -0.03), "recal_calibration": cal_ok, "model_calibration": {"intercept": 1.0},
                             "recal_w_vs_model": pv(-0.1, -0.12, -0.08), "recal_w_vs_recal": pv(-0.05, -0.07, -0.03), "recal_w_calibration": cal_ok}}
    good = {"v1": world(pv(-0.001, -0.003, 0.002)), "route_no_drift": world(pv(0.0, -0.002, 0.004)), "route_drift": drift,
            "markov": world(pv(-0.2, -0.3, -0.1)), "latent_skill": world(pv(-0.2, -0.3, -0.1)), "process_trace": world(pv(-0.2, -0.3, -0.1))}
    got = {c["id"]: c["pass"] for c in rc.judge_recal(good)}
    assert got == {"R1": True, "R2": True, "R3": True, "R4": True, "R5": True, "R6": True, "R7": True}
    bad = {**good, "v1": world(pv(0.01, 0.006, 0.014), pv(0.02, 0.012, 0.03)), "markov": world(pv(-0.2, -0.3, 0.01))}
    bad["route_drift"] = {"second_half": {**drift["second_half"], "recal_vs_model": pv(0.0, -0.02, 0.02), "recal_calibration": {**cal_ok, "intercept_contains_0": False},
                                          "recal_w_vs_recal": pv(0.01, -0.01, 0.03), "recal_w_calibration": {**cal_ok, "intercept_contains_0": False}}}
    got = {c["id"]: c["pass"] for c in rc.judge_recal(bad)}
    assert got == {"R1": False, "R2": False, "R3": False, "R4": False, "R5": False, "R6": False, "R7": False}
    # R7's margin is 0.01, R2's is 0.005: an upper end of 0.008 fails R2 and passes R7
    mid = {**good, "v1": world(pv(0.005, 0.0, 0.008))}
    got = {c["id"]: c["pass"] for c in rc.judge_recal(mid)}
    assert got["R2"] is False and got["R7"] is True


def test_the_windowed_arm_forgets_a_regime_and_the_growing_arm_does_not():
    p, y1 = _stream(3000, 0.0, seed=7)
    p2, y2 = _stream(3000, 1.5, seed=8)                                 # the world changes after 3,000 outcomes
    grow, win = rc.OnlineRecal(), rc.OnlineRecal(window=rc.WINDOW)
    for pi, yi in zip(np.concatenate([p, p2]), np.concatenate([y1, y2])):
        grow.observe(pi, yi)
        win.observe(pi, yi)
    assert rc.WINDOW == 2000
    assert abs(win.a - 1.5) < abs(grow.a - 1.5) and win.a > grow.a + 0.2
    assert len(win.s) <= 2 * rc.WINDOW                                  # memory stays bounded


def test_the_new_seeds_are_disjoint_from_every_earlier_evaluation_and_from_plan_md():
    new = {wd.v1_seed(s, k) for s in wd.BASES for k in (*rc.RECAL_K, *rc.DEV_K)} | {wd.v2_seed(f, k) for f in wd.FAMILIES for k in (*rc.RECAL_K, *rc.DEV_K)} | {wd.route_seed(k) for k in (*rc.RECAL_K, *rc.DEV_K)}
    earlier = {s for v in wd.all_seeds().values() for s in v} | wd.known_used_seeds()
    assert not (new & earlier), sorted(new & earlier)[:10]
    assert len(new) == len(list(new))


def test_the_plan_recal_hash_gates_the_recal_part_only():
    from understudy_engine.hrt import freeze as fz

    assert "PLAN_RECAL.md" in fz.code_hashes("recal") and "recal.py" in fz.code_hashes("recal") and "run_recal.py" in fz.code_hashes("recal")
    assert "PLAN_RECAL.md" not in fz.code_hashes("ledger") and "recal.py" not in fz.code_hashes("ledger")
    assert (repo_root() / "evals" / "hrt" / "PLAN_RECAL.md").exists()
