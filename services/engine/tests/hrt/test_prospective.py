"""The prospective replay: the ledger is written in time order, baselines see only what had resolved, the guard reads the record (PLAN.md sections 3 and 4)."""
from __future__ import annotations

import numpy as np
import pytest

from understudy_engine.hazard.sim import simulate_people
from understudy_engine.hrt import prospective as pr
from understudy_engine.hrt import scoring as sc
from understudy_engine.hrt.ledger import Ledger


@pytest.fixture(scope="module")
def mini():
    train, _ = simulate_people(4, 40, seed=3)
    test, _ = simulate_people(4, 40, seed=104)
    dep = pr.fit_deployed(train)
    led = pr.replay_hazard(dep, test, "mini")
    return dep, test, led


def test_replay_writes_a_verified_ledger_in_time_order_with_every_outcome_after_its_prediction(mini):
    dep, test, led = mini
    from understudy_engine.hazard.features import build_bins

    n = build_bins(test).n
    assert led.verify() and led.n_predictions("stuck_hazard") == n and led.pending("stuck_hazard") == 0 and len(led.entries) == 2 * n
    seen: set[int] = set()
    last_pred_t = -1.0
    for e in led.entries:
        if e["type"] == "prediction":
            assert e["made_at"] >= last_pred_t
            last_pred_t = e["made_at"]
            seen.add(e["pid"])
        else:
            assert e["pid"] in seen                      # the prediction was written before its outcome
    # the ledger holds the model and every baseline for the same moment, and no text
    names = set(led.resolved("stuck_hazard")["names"])
    assert names == {pr.MODEL, pr.ONLINE, pr.TSP, pr.BASE}
    assert all(len(e["stream"]) == 16 for e in led.entries if e["type"] == "prediction")


def test_the_online_base_rate_equals_the_running_mean_of_what_had_resolved_by_then(mini):
    dep, test, led = mini
    arr = led.resolved("stuck_hazard")
    t, y, p_online = arr["made_at"], arr["y"], arr["forecasts"][pr.ONLINE]
    res = t + pr.HORIZON_S
    order = np.argsort(res, kind="stable")
    rs, ys = res[order], y[order]
    csum = np.concatenate([[0.0], np.cumsum(ys)])
    for i in np.random.default_rng(0).choice(t.size, 200, replace=False):
        k = int(np.searchsorted(rs, t[i], side="right"))          # outcomes resolved at or before the prediction's own time
        expect = (pr.PRIOR_W * dep.base_rate + csum[k]) / (pr.PRIOR_W + k)
        assert np.isclose(p_online[i], expect, atol=1e-5), (i, p_online[i], expect)
    # the very first predictions have nothing resolved: they equal the training base rate
    first = int(np.argmin(t))
    assert np.isclose(p_online[first], dep.base_rate, atol=1e-5)


def test_the_deployed_model_is_frozen_its_forecast_is_what_it_would_have_said_without_any_outcome(mini):
    dep, test, led = mini
    from understudy_engine.hazard.features import build_bins

    tab = build_bins(test)
    direct = dep.models["full"].predict(tab, np.arange(tab.n))
    arr = led.resolved("stuck_hazard")
    # match by (made_at, person) since the ledger is in time order
    key = {(round(float(tab.t[i]), 3), pr.stream_key(f"mini|{tab.person[i]}", pr.SALT)): float(direct[i]) for i in range(tab.n)}
    got = {(round(float(t), 3), s): float(p) for t, s, p in zip(arr["made_at"], arr["stream"], arr["forecasts"][pr.MODEL])}
    assert set(key) == set(got)
    assert max(abs(key[k] - got[k]) for k in key) < 1e-5


def test_guard_for_returns_units_flags_and_costs_from_the_ledger_arrays(mini):
    dep, test, led = mini
    arr = led.resolved("stuck_hazard")
    g = pr.guard_for(arr, horizon_s=pr.HORIZON_S)
    assert g["n_units"] == len(set(arr["unit"].tolist())) and g["n_bins"] == arr["y"].size
    c = g["costs"]
    assert c["oracle"] == min(c["always_model"], c["always_fallback"]) and 0.0 <= c["share_on_fallback"] <= 1.0
    if not g["flagged"]:
        assert c["guarded"] == c["always_model"]


def test_time_to_progress_replay_scores_a_distribution_with_censoring_handled():
    train, _ = simulate_people(4, 40, seed=3)
    test, _ = simulate_people(4, 40, seed=104)
    dep = pr.fit_deployed_tte(train)
    led = pr.replay_tte(dep, test, "mini")
    arr = led.resolved("time_to_progress")
    assert led.verify() and arr["forecasts"][pr.MODEL].shape[1] == 10 and arr["forecasts"][pr.KM].shape == arr["forecasts"][pr.MODEL].shape
    cdf = arr["forecasts"][pr.MODEL]
    assert np.all(np.diff(cdf, axis=1) >= -1e-9) and np.all((cdf >= 0) & (cdf <= 1))                 # a CDF is non-decreasing
    assert arr["steps_obs"].min() >= 2 and arr["steps_obs"].max() <= 10 and (arr["steps_obs"] < 10).any()      # some origins are censored
    out = pr.score_tte([arr], B=200)
    assert np.isfinite(out["model"]["est"]) and np.isfinite(out["frozen_km"]["est"]) and out["n"] == arr["event_step"].size
    assert out["model_minus_km"]["verdict"] in ("a better", "a worse", "no clear difference")
    # an outcome may not be written before the observed span has passed
    pid = 0
    from understudy_engine.hrt.ledger import Ledger, LedgerError

    fresh = Ledger()
    k = fresh.predict(kind="time_to_progress", stream="a", made_at=0.0, horizon_s=300.0, forecasts={"model": [0.1] * 10}, primary="model")
    with pytest.raises(LedgerError, match="observed span"):
        fresh.resolve(k, resolved_at=119.0, outcome={"event_step": None, "steps_obs": 4})
    fresh.resolve(k, resolved_at=120.0, outcome={"event_step": None, "steps_obs": 4})


def test_clopper_pearson_known_values():
    lo, hi = pr.cp_interval(0, 8)
    assert lo == 0.0 and abs(hi - 0.3694) < 1e-3
    lo, hi = pr.cp_interval(8, 8)
    assert hi == 1.0 and abs(lo - 0.6306) < 1e-3
    lo, hi = pr.cp_interval(2, 8)
    assert abs(lo - 0.0319) < 1e-3 and abs(hi - 0.6509) < 1e-3


def _world(model_vs_best, flags, *, baseline="online_base", slope=(0.9, 1.1), icpt=(-0.1, 0.1), est=0.0, n=8, strat=None):
    st = strat or {"always_model": {"est": 0.5}, "always_fallback": {"est": 0.6}}
    return {"scores": {"paired_log_loss_vs": {pr.ONLINE: {"est": est, "ci": model_vs_best}, pr.TSP: {"est": est, "ci": model_vs_best}},
                       "predictors": {pr.MODEL: {"calibration": {"slope": 1.0, "slope_ci": list(slope), "intercept": 0.0, "intercept_ci": list(icpt),
                                                                 "slope_contains_1": slope[0] <= 1 <= slope[1], "intercept_contains_0": icpt[0] <= 0 <= icpt[1]}}}},
            "model_vs_best_naive": {"baseline": baseline, "est": est, "ci": model_vs_best},
            "guard": {"flags": flags, "of": n, "flag_rate_ci": [0.0, 1.0],
                      "strategies": {"guarded_minus_always_model": {"est": 0.0, "ci": [0.0, 0.0]}, "mean": st}}}


def test_judge_claims_applies_the_registered_pass_rules():
    v1 = _world([-0.1, -0.05], 0, est=-0.08)
    worse = lambda flags: _world([0.2, 0.4], flags, est=0.3, strat={"always_model": {"est": 1.1}, "always_fallback": {"est": 0.6}})  # noqa: E731
    shifted = {"markov": worse(8), "latent_skill": worse(7), "process_trace": worse(6)}
    for r in shifted.values():
        r["guard"]["strategies"]["guarded_minus_always_model"] = {"est": -0.4, "ci": [-0.5, -0.3]}
    claims = {c["id"]: c for c in pr.judge_claims(v1, shifted)}
    assert claims["P1"]["pass"] and claims["P2"]["pass"] and claims["P3"]["pass"] and claims["P4a"]["pass"] and claims["P4b"]["pass"] and claims["P4c"]["pass"] and claims["P4d"]["pass"]
    # fail cases: the model not better than a baseline, a slope that excludes 1, a guard that flags in the quiet world and misses in the bad one
    v1_bad = _world([-0.1, 0.01], 3, slope=(1.02, 1.14), est=-0.04)
    shifted_bad = {"markov": worse(2), "latent_skill": worse(8), "process_trace": _world([-0.2, -0.05], 4, est=-0.1)}
    bad = {c["id"]: c for c in pr.judge_claims(v1_bad, shifted_bad)}
    assert not bad["P1"]["pass"] and not bad["P2"]["pass"] and not bad["P4a"]["pass"]
    assert bad["P3"]["pass"] is True                               # markov and latent_skill are worse: 2 of 3
    assert bad["P4b"]["pass"] is False                              # markov: worse but 2 flags; process_trace: better but 4 flags
    assert bad["P4b"]["evidence"]["markov"]["ok"] is False and bad["P4b"]["evidence"]["process_trace"]["ok"] is False and bad["P4b"]["evidence"]["latent_skill"]["ok"] is True
    # a family with no clear difference is reported and not counted against the guard
    mixed = {"a": _world([-0.1, 0.1], 5), "b": worse(8), "c": worse(8)}
    m = {c["id"]: c for c in pr.judge_claims(v1, mixed)}
    assert m["P4b"]["pass"] is True and m["P4b"]["evidence"]["a"]["ok"] is None


def test_error_risk_claims_are_two_sided():
    v1 = _world([-0.1, -0.05], 0)
    shifted = {f: _world([0.2, 0.4], 8, strat={"always_model": {"est": 1.1}, "always_fallback": {"est": 0.6}}) for f in ("markov", "latent_skill", "process_trace")}
    same = _world([-0.2, -0.1], 0)
    still_better = {**_world([-0.2, -0.1], 0), "second_half": {"model_vs_online_base": {"est": -0.15, "ci": [-0.2, -0.1]}}}
    got = {c["id"]: c for c in pr.judge_claims(v1, shifted, same, still_better)}
    assert got["P6a"]["pass"] and got["P6b"]["pass"] and got["P6b"]["evidence"]["post_change_model_worse"] is False
    now_worse = {**_world([0.1, 0.3], 7), "second_half": {"model_vs_online_base": {"est": 0.2, "ci": [0.1, 0.3]}}}
    got2 = {c["id"]: c for c in pr.judge_claims(v1, shifted, same, now_worse)}
    assert got2["P6b"]["pass"] and got2["P6b"]["evidence"]["post_change_model_worse"] is True
    silent_when_worse = {**_world([0.1, 0.3], 1), "second_half": {"model_vs_online_base": {"est": 0.2, "ci": [0.1, 0.3]}}}
    assert not {c["id"]: c for c in pr.judge_claims(v1, shifted, same, silent_when_worse)}["P6b"]["pass"]
