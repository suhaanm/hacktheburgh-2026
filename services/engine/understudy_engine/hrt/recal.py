"""Online recalibration of the deployed model (``evals/hrt/PLAN_RECAL.md``): a third predictor in the ledger, fitted only on outcomes already resolved.

``recal`` passes the frozen model's forecast through ``p' = sigmoid(a + b logit(p))``. ``(a, b)`` starts at (0, 1) (the model unchanged) and is refitted every
``REFIT_EVERY`` newly resolved outcomes by damped Newton on the negative log likelihood plus a ridge that pulls ``(a, b)`` toward (0, 1). The ledger replay feeds it
an outcome only when that outcome has resolved, so a forecast never uses an outcome from its own future. No model is retrained: the model's parameters stay frozen.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import scoring as sc
from . import worlds as wd
from .ledger import Ledger
from .prospective import BASE, HORIZON_S, MODEL, ONLINE, PRIOR_W, SALT, TSP, Deployed
from .ledger import stream_key

RECAL = "recal"
RECAL_W = "recal_w"
RIDGE = 20.0
REFIT_EVERY = 200
WINDOW = 2000                      # amendment A1: the windowed arm fits the 2,000 most recent resolved outcomes
RECAL_K = tuple(range(21, 29))
DEV_K = (29, 30)


def fit_ridge(s: np.ndarray, y: np.ndarray, ridge: float = RIDGE) -> tuple[float, float]:
    """(a, b) minimising the summed logistic loss of ``a + b s`` plus ``0.5 ridge (a^2 + (b - 1)^2)``; damped Newton, convex."""
    s = np.asarray(s, dtype=float)
    y = np.asarray(y, dtype=float)

    def nll(a: float, b: float) -> float:
        z = np.clip(a + b * s, -30.0, 30.0)
        return float(np.sum(np.logaddexp(0.0, z) - y * z) + 0.5 * ridge * (a * a + (b - 1.0) ** 2))

    a, b = 0.0, 1.0
    cur = nll(a, b)
    for _ in range(50):
        z = np.clip(a + b * s, -30, 30)
        q = 1.0 / (1.0 + np.exp(-z))
        r = y - q
        g = np.array([r.sum() - ridge * a, (r * s).sum() - ridge * (b - 1.0)])
        v = q * (1.0 - q)
        H = np.array([[v.sum() + ridge, (v * s).sum()], [(v * s).sum(), (v * s * s).sum() + ridge]])
        step = np.linalg.solve(H, g)
        t = 1.0
        while t > 1e-6:
            na, nb = a + t * float(step[0]), b + t * float(step[1])
            new = nll(na, nb)
            if new <= cur + 1e-12:
                break
            t *= 0.5
        else:
            break
        moved = abs(cur - new)
        a, b, cur = na, nb, new
        if moved < 1e-10 * max(1.0, abs(cur)):
            break
    return a, b


class OnlineRecal:
    """Logistic recalibration learned online from resolved outcomes only. ``window`` (PLAN_RECAL.md amendment A1): fit only the most recent ``window`` resolved
    outcomes (all of them until that many have resolved); ``None`` fits all of them."""

    def __init__(self, ridge: float = RIDGE, refit_every: int = REFIT_EVERY, window: int | None = None) -> None:
        self.ridge, self.refit_every, self.window = ridge, refit_every, window
        self.s: list[float] = []
        self.y: list[float] = []
        self.n = 0
        self.a, self.b = 0.0, 1.0

    def observe(self, p_model: float, y: int) -> None:
        """An outcome has resolved: add it, and refit every ``refit_every`` of them."""
        self.s.append(float(sc._logit(np.array([p_model]))[0]))
        self.y.append(float(y))
        self.n += 1
        if self.window is not None and len(self.s) > 2 * self.window:         # keep memory bounded; only the last ``window`` are ever used
            self.s, self.y = self.s[-self.window:], self.y[-self.window:]
        if self.n % self.refit_every == 0:
            lo = 0 if self.window is None else max(0, len(self.s) - self.window)
            self.a, self.b = fit_ridge(np.array(self.s[lo:]), np.array(self.y[lo:]), self.ridge)

    def predict(self, p_model: float) -> float:
        z = self.a + self.b * float(sc._logit(np.array([p_model]))[0])
        return float(sc.clip(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))))


def replay_hazard_recal(dep: Deployed, eps: list, deployment: str, *, horizon_s: float = HORIZON_S) -> Ledger:
    """``prospective.replay_hazard`` with the recalibrated forecast written beside the model's: the same ledger rules, the same time order."""
    from understudy_engine.hazard.features import build_bins

    tab = build_bins(eps)
    rows = np.arange(tab.n)
    p_full = dep.models["full"].predict(tab, rows)
    p_tsp = dep.models["tsp"].predict(tab, rows)
    t, y = np.asarray(tab.t, dtype=float), np.asarray(tab.y)
    person = [stream_key(f"{deployment}|{p}", SALT) for p in tab.person]
    unit = [stream_key(f"{deployment}|ep{e}", SALT) for e in tab.episode]
    events = sorted([(float(t[i]), 1, i) for i in range(tab.n)] + [(float(t[i]) + horizon_s, 0, i) for i in range(tab.n)])
    led, rc, rcw, pid_of = Ledger(), OnlineRecal(), OnlineRecal(window=WINDOW), {}
    for when, is_pred, i in events:
        if is_pred:
            n_res, ones = led.resolved_before("stuck_hazard", when)
            p_online = (PRIOR_W * dep.base_rate + ones) / (PRIOR_W + n_res)
            pid_of[i] = led.predict(kind="stuck_hazard", stream=person[i], unit=unit[i], made_at=when, horizon_s=horizon_s, primary=RECAL, version="hazard-full-train-frozen+online-recal",
                                    forecasts={MODEL: float(p_full[i]), ONLINE: float(p_online), TSP: float(p_tsp[i]), BASE: dep.base_rate, RECAL: rc.predict(float(p_full[i])),
                                               RECAL_W: rcw.predict(float(p_full[i]))})
        else:
            led.resolve(pid_of[i], resolved_at=when, outcome=int(y[i]))
            rc.observe(float(p_full[i]), int(y[i]))
            rcw.observe(float(p_full[i]), int(y[i]))
    led.verify()
    return led


def replay_error_recal(model: Any, base_rate: float, X: np.ndarray, y: np.ndarray, deployment: str, *, lag: int = wd.REVIEW_LAG, block: int = 100) -> Ledger:
    p_model = model.predict(X)
    n = len(y)
    stream = [stream_key(f"{deployment}|blk{i // block}", SALT) for i in range(n)]
    unit = [stream_key(f"{deployment}|case{i}", SALT) for i in range(n)]
    events = sorted([(float(i), 1, i) for i in range(n)] + [(float(i + lag), 0, i) for i in range(n)])
    led, rc, rcw, pid_of = Ledger(), OnlineRecal(), OnlineRecal(window=WINDOW), {}
    for when, is_pred, i in events:
        if is_pred:
            n_res, ones = led.resolved_before("error_risk", when)
            p_online = (PRIOR_W * base_rate + ones) / (PRIOR_W + n_res)
            pid_of[i] = led.predict(kind="error_risk", stream=stream[i], unit=unit[i], made_at=when, horizon_s=float(lag), primary=RECAL, version="routing-frozen+online-recal",
                                    forecasts={MODEL: float(p_model[i]), ONLINE: float(p_online), BASE: base_rate, RECAL: rc.predict(float(p_model[i])), RECAL_W: rcw.predict(float(p_model[i]))})
        else:
            led.resolve(pid_of[i], resolved_at=when, outcome=int(y[i]))
            rc.observe(float(p_model[i]), int(y[i]))
            rcw.observe(float(p_model[i]), int(y[i]))
    led.verify()
    return led


# ------------------------------------------------------------------------------------------------------------ scoring
def _vs(arr_list: list[dict[str, Any]], names: tuple[str, ...], B: int, seed: int, cal_draws: int, primary: str = RECAL) -> dict[str, Any]:
    """Pooled scores with ``primary`` as the primary predictor: paired differences against every other predictor, its calibration, and the frozen model's."""
    from .prospective import _stack

    st = _stack(arr_list)
    out = sc.score_binary(st["y"], st["forecasts"], st["stream"], primary=primary, B=B, seed=seed, calibration_draws=cal_draws)
    cl = sc.Clusters.from_labels(st["stream"])
    M = sc.multiplicities(cl.C, B, seed)
    ll = {k: sc.log_losses(st["y"], v) for k, v in st["forecasts"].items()}
    naive = {k: float(ll[k].mean()) for k in (ONLINE, TSP) if k in ll}
    best = min(naive, key=naive.get)
    out["best_naive"] = best
    out["recal_vs_best_naive"] = {"baseline": best, **sc.paired_difference(ll[primary], ll[best], cl, M)}
    out["model_calibration"] = sc.calibration_with_interval(st["y"], st["forecasts"][MODEL], cl, M, 0.95, cal_draws)
    out["n_bins"] = int(st["y"].size)
    out["primary_predictor"] = primary
    return out


def _both(arr_list: list[dict[str, Any]], names: tuple[str, ...], B: int, seed: int, cal_draws: int) -> dict[str, Any]:
    """The registered arm (``recal``, all resolved outcomes) as the main result, and the windowed arm of amendment A1 under ``w``."""
    out = _vs(arr_list, names, B, seed, cal_draws, RECAL)
    w = _vs(arr_list, names, B, seed, cal_draws, RECAL_W)
    out["w"] = {"log_loss": w["predictors"][RECAL_W]["log_loss"], "ece": w["predictors"][RECAL_W]["ece"], "calibration": w["predictors"][RECAL_W]["calibration"],
                "paired_log_loss_vs": w["paired_log_loss_vs"], "vs_best_naive": w["recal_vs_best_naive"], "best_naive": w["best_naive"]}
    return out


def run_hazard_world_recal(world: str, dep: Deployed, deployments: list[tuple[str, list]], *, B: int, seed: int, cal_draws: int, log=None) -> dict[str, Any]:
    arrs = []
    for name, eps in deployments:
        led = replay_hazard_recal(dep, eps, name)
        arrs.append(led.resolved("stuck_hazard"))
        if log:
            log(f"  {world} {name}: {arrs[-1]['y'].size} bins")
    out = _both(arrs, (MODEL, ONLINE, TSP, BASE, RECAL, RECAL_W), B, seed, cal_draws)
    out.update({"world": world, "n_deployments": len(arrs)})
    return out


def run_error_world_recal(world: str, model: Any, base_rate: float, ks: tuple[int, ...], *, drift: bool, B: int, seed: int, cal_draws: int, log=None) -> dict[str, Any]:
    from .prospective import _subset

    arrs = []
    for k in ks:
        c = wd.simulate_cases_stream(wd.ROUTE_STREAM_N, wd.route_seed(k), drift_at=wd.ROUTE_DRIFT_AT if drift else None)
        arrs.append(replay_error_recal(model, base_rate, c.X, c.y, f"{world}{k}").resolved("error_risk"))
        if log:
            log(f"  {world} dep {k}: {arrs[-1]['y'].size} cases")
    names = (MODEL, ONLINE, BASE, RECAL, RECAL_W)
    out = _both(arrs, names, B, seed, cal_draws)
    for half, pick in (("first_half", lambda a: a["made_at"] < wd.ROUTE_DRIFT_AT), ("second_half", lambda a: a["made_at"] >= wd.ROUTE_DRIFT_AT)):
        h = _both([_subset(a, pick(a)) for a in arrs], names, B, seed, cal_draws)
        out[half] = {"n": h["n_bins"], "recal_vs_model": h["paired_log_loss_vs"][MODEL], "recal_calibration": h["predictors"][RECAL]["calibration"],
                     "model_calibration": h["model_calibration"], "recal_w_vs_model": h["w"]["paired_log_loss_vs"][MODEL], "recal_w_vs_recal": h["w"]["paired_log_loss_vs"][RECAL],
                     "recal_w_calibration": h["w"]["calibration"]}
    out.update({"world": world, "n_deployments": len(arrs), "drift": drift})
    return out


# -------------------------------------------------------------------------------------------------------------- claims
def judge_recal(worlds: dict[str, dict]) -> list[dict[str, Any]]:
    """The pass rules of PLAN_RECAL.md section 4. Pure."""
    d = worlds["route_drift"]
    r1 = d["second_half"]["recal_vs_model"]
    out = [{"id": "R1", "claim": "Error risk, rule change: after the change the recalibrated forecast beats the frozen model on log loss", "pass": bool(r1["ci"][1] < 0),
            "evidence": {"est": r1["est"], "ci": r1["ci"], "n": d["second_half"]["n"]}}]
    nh = {k: worlds[k]["paired_log_loss_vs"][MODEL] for k in ("v1", "route_no_drift")}
    out.append({"id": "R2", "claim": "No harm without a change: in the v1 world and the error-risk world with no change, recal is not worse than the frozen model by more than 0.005 nats",
                "pass": bool(all(v["ci"][1] <= 0.005 for v in nh.values())), "evidence": {k: {"est": v["est"], "ci": v["ci"]} for k, v in nh.items()}})
    fam = {k: worlds[k]["paired_log_loss_vs"][MODEL] for k in ("markov", "latent_skill", "process_trace")}
    out.append({"id": "R3", "claim": "Shifted hazard worlds: recal beats the frozen model in each of the three families", "pass": bool(all(v["ci"][1] < 0 for v in fam.values())),
                "evidence": {k: {"est": v["est"], "ci": v["ci"]} for k, v in fam.items()}})
    cal = d["second_half"]["recal_calibration"]
    out.append({"id": "R4", "claim": "Calibration is restored: in the drift world after the change the interval of recal's calibration intercept contains 0", "pass": bool(cal["intercept_contains_0"]),
                "evidence": {"intercept": cal["intercept"], "intercept_ci": cal["intercept_ci"], "slope": cal["slope"], "slope_ci": cal["slope_ci"],
                             "frozen_model_intercept": d["second_half"]["model_calibration"]["intercept"]}})
    # amendment A1: the windowed arm
    sh = d["second_half"]
    vm, vr = sh["recal_w_vs_model"], sh["recal_w_vs_recal"]
    out.append({"id": "R5", "claim": "Error risk, rule change: after the change recal_w beats the frozen model and beats recal on log loss", "pass": bool(vm["ci"][1] < 0 and vr["ci"][1] < 0),
                "evidence": {"vs_model": {"est": vm["est"], "ci": vm["ci"]}, "vs_recal": {"est": vr["est"], "ci": vr["ci"]}, "n": sh["n"]}})
    cw = sh["recal_w_calibration"]
    out.append({"id": "R6", "claim": "Error risk, rule change: after the change the interval of recal_w's calibration intercept contains 0", "pass": bool(cw["intercept_contains_0"]),
                "evidence": {"intercept": cw["intercept"], "intercept_ci": cw["intercept_ci"], "slope": cw["slope"], "slope_ci": cw["slope_ci"]}})
    nhw = {k: worlds[k]["w"]["paired_log_loss_vs"][MODEL] for k in ("v1", "route_no_drift")}
    out.append({"id": "R7", "claim": "No harm for recal_w: in the v1 world and the error-risk world with no change it is not worse than the frozen model by more than 0.01 nats",
                "pass": bool(all(v["ci"][1] <= 0.01 for v in nhw.values())), "evidence": {k: {"est": v["est"], "ci": v["ci"]} for k, v in nhw.items()}})
    return out
