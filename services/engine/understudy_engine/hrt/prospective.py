"""Prospective (predict first, score later) evaluation of the deployed models, through the ledger (``evals/hrt/PLAN.md`` sections 3 and 4).

A deployment is replayed in time order: at each moment the deployed model and every naive baseline write their forecast for the next minute (or
the next case) to the ledger, and an outcome is written only when its horizon has passed. The online base rate reads only outcomes the ledger
has already resolved. Scoring then reads the ledger and nothing else. The guard (guard.py) is fed from the same record.

Nothing here fits anything after deployment: the models are fitted once on the TRAIN pool and frozen.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import guard as gd
from . import scoring as sc
from . import worlds as wd
from .ledger import Ledger, stream_key

HORIZON_S = 60.0
PRIOR_W = 20.0
MODEL, ONLINE, TSP, BASE = "model", "online_base", "frozen_tsp", "frozen_base"
NAIVE = (ONLINE, TSP, BASE)
SALT = "hrt"


# ------------------------------------------------------------------------------------------------------- deployment
@dataclass
class Deployed:
    models: dict[str, Any]
    base_rate: float
    n_train_bins: int


def fit_deployed(train_eps: list) -> Deployed:
    """Fit the product's stuck model and the frozen baselines on the deployment history, once."""
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.hazard.model import HazardModel

    tab = build_bins(train_eps)
    rows = np.arange(tab.n)
    models = {v: HazardModel(v, 3.0).fit(tab, rows) for v in ("full", "tsp", "base")}
    return Deployed(models, float(tab.y.mean()), int(tab.n))


def replay_hazard(dep: Deployed, eps: list, deployment: str, *, horizon_s: float = HORIZON_S) -> Ledger:
    """Replay one deployment through a ledger and return it (verified). Predictions and outcomes are written in time order; an outcome at the same
    instant as a prediction goes first because it is then known."""
    from understudy_engine.hazard.features import build_bins

    tab = build_bins(eps)
    rows = np.arange(tab.n)
    p_full = dep.models["full"].predict(tab, rows)
    p_tsp = dep.models["tsp"].predict(tab, rows)
    t = np.asarray(tab.t, dtype=float)
    y = np.asarray(tab.y)
    person = [stream_key(f"{deployment}|{p}", SALT) for p in tab.person]
    unit = [stream_key(f"{deployment}|ep{e}", SALT) for e in tab.episode]
    events: list[tuple[float, int, int]] = []
    for i in range(tab.n):
        events.append((float(t[i]), 1, i))                     # a prediction
        events.append((float(t[i]) + horizon_s, 0, i))         # its outcome, written first if it ties with a prediction
    events.sort()
    led = Ledger()
    pid_of: dict[int, int] = {}
    for when, is_pred, i in events:
        if is_pred:
            n_res, ones = led.resolved_before("stuck_hazard", when)
            p_online = (PRIOR_W * dep.base_rate + ones) / (PRIOR_W + n_res)
            pid_of[i] = led.predict(kind="stuck_hazard", stream=person[i], unit=unit[i], made_at=when, horizon_s=horizon_s, primary=MODEL, version="hazard-full-l2=3-train-frozen",
                                    forecasts={MODEL: float(p_full[i]), ONLINE: float(p_online), TSP: float(p_tsp[i]), BASE: dep.base_rate})
        else:
            led.resolve(pid_of[i], resolved_at=when, outcome=int(y[i]))
    led.verify()
    return led


def replay_error_risk(model: Any, base_rate: float, X: np.ndarray, y: np.ndarray, deployment: str, *, lag: int = wd.REVIEW_LAG, block: int = 100) -> Ledger:
    """Replay a case stream: case i arrives at time i, its outcome (was the agent's answer wrong?) is written ``lag`` arrivals later."""
    p_model = model.predict(X)
    led = Ledger()
    n = len(y)
    stream = [stream_key(f"{deployment}|blk{i // block}", SALT) for i in range(n)]
    unit = [stream_key(f"{deployment}|case{i}", SALT) for i in range(n)]
    events: list[tuple[float, int, int]] = []
    for i in range(n):
        events.append((float(i), 1, i))
        events.append((float(i + lag), 0, i))
    events.sort()
    pid_of: dict[int, int] = {}
    for when, is_pred, i in events:
        if is_pred:
            n_res, ones = led.resolved_before("error_risk", when)
            p_online = (PRIOR_W * base_rate + ones) / (PRIOR_W + n_res)
            pid_of[i] = led.predict(kind="error_risk", stream=stream[i], unit=unit[i], made_at=when, horizon_s=float(lag), primary=MODEL, version="routing-logistic-platt-frozen",
                                    forecasts={MODEL: float(p_model[i]), ONLINE: float(p_online), BASE: base_rate})
        else:
            led.resolve(pid_of[i], resolved_at=when, outcome=int(y[i]))
    led.verify()
    return led


# --------------------------------------------------------------------------------------------------------- scoring
def deployment_arrays(led: Ledger, kind: str) -> dict[str, Any]:
    return led.resolved(kind)


def cp_interval(k: int, n: int, level: float = 0.95) -> list[float]:
    """Exact (Clopper-Pearson) interval for k flags in n deployments."""
    from scipy.stats import beta

    a = (1 - level) / 2
    lo = 0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))
    return [lo, hi]


def guard_for(arr: dict[str, Any], *, horizon_s: float, fallback: str = ONLINE) -> dict[str, Any]:
    """Run the guard on one deployment's ledger arrays: units are the recorded unit keys; the loss difference is model minus fallback."""
    ll_m = sc.log_losses(arr["y"], arr["forecasts"][MODEL])
    ll_f = sc.log_losses(arr["y"], arr["forecasts"][fallback])
    units = gd.units_from_bins(arr["unit"], arr["made_at"], arr["made_at"] + horizon_s, ll_m, ll_f)
    run = gd.run_guard(units)
    costs = gd.strategy_costs(arr["made_at"], ll_m, ll_f, run["flag_time"])
    return {**run, "costs": costs, "model_log_loss": float(ll_m.mean()), "fallback_log_loss": float(ll_f.mean()), "n_bins": int(ll_m.size)}


def _stack(arrs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"y": np.concatenate([a["y"] for a in arrs]), "stream": np.concatenate([a["stream"] for a in arrs]), "made_at": np.concatenate([a["made_at"] for a in arrs]),
                           "forecasts": {k: np.concatenate([a["forecasts"][k] for a in arrs]) for k in arrs[0]["forecasts"]}}
    return out


def _subset(arr: dict[str, Any], mask: np.ndarray) -> dict[str, Any]:
    return {"y": arr["y"][mask], "stream": arr["stream"][mask], "made_at": arr["made_at"][mask], "forecasts": {k: v[mask] for k, v in arr["forecasts"].items()}}


def _boot_over_deployments(values: np.ndarray, B: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(B, values.size))
    return sc.interval(values[idx].mean(axis=1))


def strategy_summary(per_dep: list[dict[str, Any]], B: int = 2000, seed: int = 3) -> dict[str, Any]:
    """Mean over deployments of each strategy's per-bin log loss and regret against the oracle, with deployment-level bootstrap intervals, and the paired
    differences guarded minus always-model and guarded minus always-fallback (negative favours the guard)."""
    keys = ("always_model", "always_fallback", "guarded", "oracle", "regret_always_model", "regret_always_fallback", "regret_guarded", "share_on_fallback")
    cols = {k: np.array([d["costs"][k] for d in per_dep]) for k in keys}
    out: dict[str, Any] = {"n_deployments": len(per_dep), "bootstrap": {"B": B, "unit": "deployments", "seed": seed},
                           "mean": {k: {"est": float(v.mean()), "ci": _boot_over_deployments(v, B, seed)} for k, v in cols.items()}}
    for name, a, b in (("guarded_minus_always_model", "guarded", "always_model"), ("guarded_minus_always_fallback", "guarded", "always_fallback"), ("guarded_minus_oracle", "guarded", "oracle")):
        d = cols[a] - cols[b]
        out[name] = {"est": float(d.mean()), "ci": _boot_over_deployments(d, B, seed + 1)}
    return out


def score_world(world: str, led_arrs: list[dict[str, Any]], per_dep_guard: list[dict[str, Any]], *, B: int = 2000, seed: int = 0, calibration_draws: int = 500) -> dict[str, Any]:
    """The pooled scores of a world (all deployments' resolved predictions, people as clusters) and the guard's counts and strategy costs."""
    st = _stack(led_arrs)
    scores = sc.score_binary(st["y"], st["forecasts"], st["stream"], primary=MODEL, B=B, seed=seed, calibration_draws=calibration_draws)
    cl = sc.Clusters.from_labels(st["stream"])
    M = sc.multiplicities(cl.C, B, seed)                       # the same resamples score_binary used (same seed and size)
    ll = {k: sc.log_losses(st["y"], v) for k, v in st["forecasts"].items()}
    pooled = {k: float(ll[k].mean()) for k in NAIVE if k in ll}
    best = min(pooled, key=pooled.get)
    vs_best = sc.paired_difference(ll[MODEL], ll[best], cl, M)
    flags = int(sum(d["flagged"] for d in per_dep_guard))
    n = len(per_dep_guard)
    return {"world": world, "n_deployments": n, "n_bins": int(st["y"].size), "n_people": cl.C, "scores": scores, "best_naive": best,
            "best_naive_pooled_log_loss": pooled[best], "model_vs_best_naive": {"baseline": best, **vs_best},
            "guard": {"flags": flags, "of": n, "flag_rate_ci": cp_interval(flags, n), "strategies": strategy_summary(per_dep_guard),
                      "flag_units": [d["flag_unit"] for d in per_dep_guard], "n_units": [d["n_units"] for d in per_dep_guard]},
            "deployments": [{"model_log_loss": d["model_log_loss"], "fallback_log_loss": d["fallback_log_loss"], "flagged": d["flagged"], "flag_unit": d["flag_unit"],
                             "n_units": d["n_units"], "n_bins": d["n_bins"], "peak_capital": d["peak_capital"], "costs": d["costs"]} for d in per_dep_guard]}


def run_hazard_world(world: str, dep: Deployed, deployments: list[tuple[str, list]], *, B: int = 2000, seed: int = 0, calibration_draws: int = 500, log=None) -> dict[str, Any]:
    arrs, guards, ledgers = [], [], []
    for name, eps in deployments:
        led = replay_hazard(dep, eps, name)
        arr = led.resolved("stuck_hazard")
        arrs.append(arr)
        guards.append(guard_for(arr, horizon_s=HORIZON_S))
        ledgers.append({"deployment": name, **led.summary(), "verified": True})
        if log:
            log(f"  {world} {name}: {arr['y'].size} bins, flagged={guards[-1]['flagged']}")
    out = score_world(world, arrs, guards, B=B, seed=seed, calibration_draws=calibration_draws)
    out["ledgers"] = ledgers
    return out


# ------------------------------------------------------------------------------------------------------ error risk
def fit_error_model() -> tuple[Any, float]:
    """The routing model fitted on the first 1,000 and calibrated on the next 500 cases of the ROUTE TRAIN stream, frozen."""
    from understudy_engine.routing.model import RoutingModel

    c = wd.simulate_cases_stream(wd.ROUTE_TRAIN_N, wd.route_seed(wd.ROUTE_TRAIN_K))
    m = RoutingModel().fit(c.X[:1000], c.y[:1000])
    m.calibrate(c.X[1000:], c.y[1000:])
    return m, float(c.y.mean())


def run_error_world(world: str, model: Any, base_rate: float, ks: tuple[int, ...], *, drift: bool, B: int = 2000, seed: int = 0, calibration_draws: int = 500, log=None) -> dict[str, Any]:
    arrs, guards, post = [], [], []
    for k in ks:
        c = wd.simulate_cases_stream(wd.ROUTE_STREAM_N, wd.route_seed(k), drift_at=wd.ROUTE_DRIFT_AT if drift else None)
        led = replay_error_risk(model, base_rate, c.X, c.y, f"{world}{k}")
        arr = led.resolved("error_risk")
        arrs.append(arr)
        guards.append(guard_for(arr, horizon_s=float(wd.REVIEW_LAG)))
        # the first half (before the rule change) and the second half scored apart, for the "still better than the fallback?" question
        post.append(_subset(arr, arr["made_at"] >= wd.ROUTE_DRIFT_AT))
        if log:
            log(f"  {world} dep {k}: {arr['y'].size} cases, flagged={guards[-1]['flagged']}")
    out = score_world(world, arrs, guards, B=B, seed=seed, calibration_draws=calibration_draws)
    st = _stack(post)
    cl = sc.Clusters.from_labels(st["stream"])
    M = sc.multiplicities(cl.C, B, seed)
    out["second_half"] = {"n": int(st["y"].size), "model_vs_online_base": sc.paired_difference(sc.log_losses(st["y"], st["forecasts"][MODEL]), sc.log_losses(st["y"], st["forecasts"][ONLINE]), cl, M),
                          "calibration_model": sc.calibration_with_interval(st["y"], st["forecasts"][MODEL], cl, M, 0.95, calibration_draws)}
    first = [_subset(a, a["made_at"] < wd.ROUTE_DRIFT_AT) for a in arrs]
    st1 = _stack(first)
    cl1 = sc.Clusters.from_labels(st1["stream"])
    M1 = sc.multiplicities(cl1.C, B, seed)
    out["first_half"] = {"n": int(st1["y"].size), "model_vs_online_base": sc.paired_difference(sc.log_losses(st1["y"], st1["forecasts"][MODEL]), sc.log_losses(st1["y"], st1["forecasts"][ONLINE]), cl1, M1),
                         "calibration_model": sc.calibration_with_interval(st1["y"], st1["forecasts"][MODEL], cl1, M1, 0.95, calibration_draws)}
    out["drift"] = drift
    return out


# ------------------------------------------------------------------------------------------------------------ claims
def judge_claims(v1: dict, shifted: dict[str, dict], route_same: dict | None = None, route_drift: dict | None = None) -> list[dict[str, Any]]:
    """Apply the pass rules of PLAN.md section 4 (with amendment A1) to the world results. Pure; no data beyond the dicts."""
    out: list[dict[str, Any]] = []
    pv = v1["scores"]["paired_log_loss_vs"]
    p1_each = {k: pv[k]["ci"][1] < 0 for k in (ONLINE, TSP) if k in pv}
    out.append({"id": "P1", "claim": "In the v1 world the deployed stuck hazard beats both the online base rate and frozen time-since-progress on log loss",
                "pass": all(p1_each.values()) and len(p1_each) == 2, "evidence": {k: {"est": pv[k]["est"], "ci": pv[k]["ci"]} for k in p1_each}})
    cal = v1["scores"]["predictors"][MODEL]["calibration"]
    out.append({"id": "P2", "claim": "In the v1 world the model is calibrated: the slope interval contains 1 and the intercept interval contains 0",
                "pass": bool(cal["slope_contains_1"] and cal["intercept_contains_0"]),
                "evidence": {"slope": cal["slope"], "slope_ci": cal["slope_ci"], "intercept": cal["intercept"], "intercept_ci": cal["intercept_ci"]}})
    worse = {f: bool(r["model_vs_best_naive"]["ci"][0] > 0) for f, r in shifted.items()}
    better = {f: bool(r["model_vs_best_naive"]["ci"][1] < 0) for f, r in shifted.items()}
    out.append({"id": "P3", "claim": "In the shifted worlds the deployed model is worse than the better naive baseline in at least 2 of 3 families",
                "pass": sum(worse.values()) >= 2, "evidence": {f: {"worse": worse[f], "better": better[f], **{k: shifted[f]["model_vs_best_naive"][k] for k in ("est", "ci", "baseline")}} for f in shifted}})
    flags = v1["guard"]["flags"]
    out.append({"id": "P4a", "claim": "The guard raises no flag in at least 7 of 8 v1 deployments", "pass": flags <= 1, "evidence": {"flags": flags, "of": v1["guard"]["of"], "ci": v1["guard"]["flag_rate_ci"]}})
    per_family, ok_b = {}, True
    for f, r in shifted.items():
        g = r["guard"]
        if worse[f]:
            per_family[f] = {"state": "model worse", "flags": g["flags"], "of": g["of"], "ok": g["flags"] >= 6}
        elif better[f]:
            per_family[f] = {"state": "model better", "flags": g["flags"], "of": g["of"], "ok": g["flags"] <= 1}
        else:
            per_family[f] = {"state": "no clear difference", "flags": g["flags"], "of": g["of"], "ok": None}
        ok_b = ok_b and per_family[f]["ok"] is not False
    out.append({"id": "P4b", "claim": "The guard flags at least 6 of 8 where the model is worse and at most 1 of 8 where it is clearly better", "pass": ok_b, "evidence": per_family})
    st1 = v1["guard"]["strategies"]
    prem = st1["guarded_minus_always_model"]
    out.append({"id": "P4c", "claim": "Premium: in the v1 world the guarded system is within 0.01 nats of always trusting the model", "pass": prem["est"] <= 0.01, "evidence": {"est": prem["est"], "ci": prem["ci"]}})
    pay = {}
    for f, r in shifted.items():
        gap = r["guard"]["strategies"]["mean"]["always_model"]["est"] - r["guard"]["strategies"]["mean"]["always_fallback"]["est"]
        if gap > 0.05:
            d = r["guard"]["strategies"]["guarded_minus_always_model"]
            pay[f] = {"model_minus_fallback": gap, "est": d["est"], "ci": d["ci"], "ok": d["est"] <= -0.02}
    out.append({"id": "P4d", "claim": "Payout: where the model is worse than the fallback by more than 0.05 nats the guard saves more than 0.02 nats against always-model",
                "pass": (all(v["ok"] for v in pay.values()) if pay else None), "evidence": pay or "no family met the 0.05-nat condition"})
    if route_same is not None:
        pr = route_same["scores"]["paired_log_loss_vs"][ONLINE]
        cr = route_same["scores"]["predictors"][MODEL]["calibration"]
        out.append({"id": "P6a", "claim": "Error risk, no drift: the model beats the online base rate and its calibration slope interval contains 1",
                    "pass": bool(pr["ci"][1] < 0 and cr["slope_contains_1"]), "evidence": {"vs_online": {"est": pr["est"], "ci": pr["ci"]}, "slope": cr["slope"], "slope_ci": cr["slope_ci"]}})
    if route_same is not None and route_drift is not None:
        post = route_drift["second_half"]["model_vs_online_base"]
        post_worse = bool(post["ci"][0] > 0)
        f_same, f_drift = route_same["guard"]["flags"], route_drift["guard"]["flags"]
        ok = (f_drift >= 6 if post_worse else f_drift <= 1) and f_same <= 1
        out.append({"id": "P6b", "claim": "Error risk: the guard flags a rule change when the post-change model is worse than the fallback, and stays quiet when it is not or when nothing changed",
                    "pass": bool(ok), "evidence": {"post_change_model_vs_online_base": {"est": post["est"], "ci": post["ci"]}, "post_change_model_worse": post_worse,
                                                   "flags_drift": f"{f_drift} of {route_drift['guard']['of']}", "flags_no_drift": f"{f_same} of {route_same['guard']['of']}"}})
    return out
