"""Decision value against prediction accuracy (``evals/hrt/PLAN_VALUE.md``).

The stuck forecasts are used to decide whether to interrupt. At every origin the policy interrupts when the forecast is at least the break-even point A / (A + S); an
interruption is worth S minutes when the person really makes no progress for a minute and costs A minutes of attention when they would have progressed anyway. The same rule
is applied to every recorded forecast of the ledger, in the same world, on the same origins, so net minutes can be read beside log loss. S and A are our assumptions, the
decision is at every origin with no cooldown, and nothing is tuned: the plan fixes them before any number exists. Written from the idea, in our own words.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import scoring as sc
from . import worlds as wd

S_MIN = 3.0
A_MIN = 1.0
A_GRID = (0.25, 0.5, 1.0, 2.0, 4.0)
ORIGINS_PER_HOUR = 120.0                    # origins are 30-second bins
DEV_K = (69, 70)
HELD_K = tuple(range(61, 69))
PREDICTORS = ("model", "online_base", "frozen_tsp", "frozen_base")
NAIVE = ("online_base", "frozen_tsp")
POLICIES = (*PREDICTORS, "guarded", "always", "never", "oracle")


def value_seeds() -> dict[str, list[int]]:
    """Every seed this plan uses, by pool (a test asserts they are new and distinct)."""
    return {"v1_dev": [wd.v1_seed(s, k) for k in DEV_K for s in wd.BASES], "v1_held": [wd.v1_seed(s, k) for k in HELD_K for s in wd.BASES],
            "v2_dev": [wd.v2_seed(f, k) for k in DEV_K for f in wd.FAMILIES], "v2_held": [wd.v2_seed(f, k) for k in HELD_K for f in wd.FAMILIES]}


# ------------------------------------------------------------------------------------------------------------ the rule
def threshold(a: float, s: float = S_MIN) -> float:
    """The break-even forecast: interrupting pays when p * S exceeds (1 - p) * A."""
    return a / (a + s)


def interrupts(p: np.ndarray, tau: float) -> np.ndarray:
    return np.asarray(p, dtype=float) >= tau - 1e-12


def net_values(y: np.ndarray, go: np.ndarray, s: float, a: float) -> np.ndarray:
    """Minutes gained per origin: S when it interrupts and the person really makes no progress, minus A when it interrupts and they would have, zero when quiet."""
    return np.where(go, np.where(np.asarray(y) == 1, s, -a), 0.0)


def always_values(y: np.ndarray, s: float, a: float) -> np.ndarray:
    return np.where(np.asarray(y) == 1, s, -a).astype(float)


def oracle_values(y: np.ndarray, s: float) -> np.ndarray:
    return s * np.asarray(y, dtype=float)


def gap_closed(value: float, floor: float, oracle: float) -> float:
    """The share of the gap between the floor (the better of never and always) and the oracle that a policy closes; undefined without a gap."""
    return float("nan") if oracle <= floor else float((value - floor) / (oracle - floor))


def rank_agreement(log_loss: list[float], value: list[float]) -> float:
    """Spearman correlation between "lower log loss" and "higher net value" over a set of forecasts (1 = the two orderings agree, -1 = they reverse)."""
    from scipy.stats import rankdata

    a, b = rankdata(-np.asarray(log_loss, dtype=float)), rankdata(np.asarray(value, dtype=float))
    if np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def guarded_forecast(arr: dict[str, Any], flag_time: float | None) -> np.ndarray:
    """The guard's forecast: the model's until the flag, the online base rate's for predictions made after it (the convention of ``guard.strategy_costs``)."""
    model, online = arr["forecasts"]["model"], arr["forecasts"]["online_base"]
    if flag_time is None:
        return np.asarray(model, dtype=float)
    return np.where(np.asarray(arr["made_at"], dtype=float) > flag_time, online, model).astype(float)


# ------------------------------------------------------------------------------------------------------------- scoring
def _stack(arrs: list[dict[str, Any]], flag_times: list[float | None]) -> dict[str, Any]:
    return {"y": np.concatenate([a["y"] for a in arrs]).astype(int), "stream": np.concatenate([a["stream"] for a in arrs]),
            "forecasts": {k: np.concatenate([a["forecasts"][k] for a in arrs]) for k in PREDICTORS},
            "guarded": np.concatenate([guarded_forecast(a, f) for a, f in zip(arrs, flag_times)])}


def _policies(st: dict[str, Any], s: float, a: float) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    tau = threshold(a, s)
    y = st["y"]
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for k in PREDICTORS:
        go = interrupts(st["forecasts"][k], tau)
        out[k] = (net_values(y, go, s, a), go)
    go = interrupts(st["guarded"], tau)
    out["guarded"] = (net_values(y, go, s, a), go)
    out["always"] = (always_values(y, s, a), np.ones(y.size, dtype=bool))
    out["never"] = (np.zeros(y.size), np.zeros(y.size, dtype=bool))
    out["oracle"] = (oracle_values(y, s), y == 1)
    return out


def _scaled(d: dict[str, Any], k: float) -> dict[str, Any]:
    return {"est": d["est"] * k, "ci": [d["ci"][0] * k, d["ci"][1] * k]}


def _verdict(d: dict[str, Any]) -> dict[str, Any]:
    lo, hi = d["ci"]
    return {**d, "verdict": "model better" if lo > 0 else "model worse" if hi < 0 else "no clear difference"}


def _paired(pol: dict[str, tuple[np.ndarray, np.ndarray]], best: str, cl: sc.Clusters, M: np.ndarray) -> dict[str, Any]:
    """Model minus each naive policy in net value per origin (positive favours the model), on the same resamples."""
    m = pol["model"][0]
    return {"model_vs_online_base": _verdict(sc.paired_difference(m, pol["online_base"][0], cl, M)), "model_vs_frozen_tsp": _verdict(sc.paired_difference(m, pol["frozen_tsp"][0], cl, M)),
            "model_vs_frozen_base": _verdict(sc.paired_difference(m, pol["frozen_base"][0], cl, M)), "model_vs_best_naive": {"baseline": best, **_verdict(sc.paired_difference(m, pol[best][0], cl, M))}}


def _policy_rows(pol: dict[str, tuple[np.ndarray, np.ndarray]], cl: sc.Clusters, M: np.ndarray) -> dict[str, Any]:
    d_always = sc.mean_draws(pol["always"][0], cl, M)
    d_oracle = sc.mean_draws(pol["oracle"][0], cl, M)
    floor_d = np.maximum(0.0, d_always)
    always_est = float(pol["always"][0].mean())
    oracle_est = float(pol["oracle"][0].mean())
    floor = max(0.0, always_est)
    rows: dict[str, Any] = {}
    for name in POLICIES:
        v, go = pol[name]
        vi = sc.mean_with_interval(v, cl, M)
        gi = sc.mean_with_interval(go.astype(float), cl, M)
        n_go = float(go.sum())
        if n_go > 0:
            num, den = M @ cl.sums(v), M @ cl.sums(go.astype(float))
            ratio = sc.interval(num / np.maximum(den, 1e-12))
            per_int: dict[str, Any] | None = {"est": float(v.sum() / n_go), "ci": ratio}
        else:
            per_int = None
        d_v = sc.mean_draws(v, cl, M)
        with np.errstate(divide="ignore", invalid="ignore"):
            g_draws = np.where(d_oracle > floor_d, (d_v - floor_d) / (d_oracle - floor_d), np.nan)
        rows[name] = {"value_per_origin": vi, "per_hour": _scaled(vi, ORIGINS_PER_HOUR), "interruptions_per_hour": _scaled(gi, ORIGINS_PER_HOUR), "net_per_interruption": per_int,
                      "gap_closed": {"est": gap_closed(vi["est"], floor, oracle_est), "ci": sc.interval(g_draws)}}
    return rows


def score_world(world: str, arrs: list[dict[str, Any]], flag_times: list[float | None], s: float, a: float, *, B: int, seed: int = 0) -> dict[str, Any]:
    """Net value of every policy in one world, log loss beside it, the model's paired contrasts, the guard at the deployment level, the sensitivity grid and the rank agreement."""
    from . import prospective as pr

    st = _stack(arrs, flag_times)
    cl = sc.Clusters.from_labels(st["stream"])
    M = sc.multiplicities(cl.C, B, seed)
    ll = {k: sc.log_losses(st["y"], st["forecasts"][k]) for k in PREDICTORS}
    pooled = {k: float(ll[k].mean()) for k in NAIVE}
    best = min(pooled, key=pooled.get)
    pol = _policies(st, s, a)
    rows = _policy_rows(pol, cl, M)
    out: dict[str, Any] = {"world": world, "n_deployments": len(arrs), "n_origins": int(st["y"].size), "n_people": cl.C, "cost": {"s": s, "a": a, "threshold": threshold(a, s)},
                           "log_loss": {k: sc.mean_with_interval(ll[k], cl, M) for k in PREDICTORS}, "best_naive": best, "policies": rows, "paired": _paired(pol, best, cl, M),
                           "bootstrap": {"B": B, "seed": seed, "unit": "people"}}
    # the guard at the deployment level (n = number of deployments)
    per_dep, diffs = [], []
    tau = threshold(a, s)
    for arr, ft in zip(arrs, flag_times):
        y = np.asarray(arr["y"])
        v_model = net_values(y, interrupts(arr["forecasts"]["model"], tau), s, a)
        v_guard = net_values(y, interrupts(guarded_forecast(arr, ft), tau), s, a)
        per_dep.append({"flagged": ft is not None, "n": int(y.size), "always_model": float(v_model.mean()), "guarded": float(v_guard.mean())})
        diffs.append(float(v_guard.mean() - v_model.mean()))
    d = np.asarray(diffs)
    out["guard"] = {"flags": int(sum(f is not None for f in flag_times)), "of": len(flag_times), "flagged": [f is not None for f in flag_times], "per_deployment": per_dep,
                    "guarded_minus_always_model": {"est": float(d.mean()), "ci": pr._boot_over_deployments(d, B, seed + 1), "unit": "deployments"}}
    out["rank_agreement"] = {"spearman": rank_agreement([out["log_loss"][k]["est"] for k in PREDICTORS], [rows[k]["value_per_origin"]["est"] for k in PREDICTORS]),
                             "unit": "four forecasts in this world (descriptive)", "log_loss": {k: out["log_loss"][k]["est"] for k in PREDICTORS}, "value": {k: rows[k]["value_per_origin"]["est"] for k in PREDICTORS}}
    sens: dict[str, Any] = {}
    for a_grid in A_GRID:
        pg = _policies(st, s, a_grid)
        rg = _policy_rows(pg, cl, M)
        sens[str(a_grid)] = {"threshold": threshold(a_grid, s), "value_per_origin": {k: rg[k]["value_per_origin"] for k in (*PREDICTORS, "guarded", "always", "oracle")},
                             "model_vs_best_naive": _paired(pg, best, cl, M)["model_vs_best_naive"]}
    out["sensitivity"] = sens
    return out


def run_world(world: str, dep: Any, deployments: list[tuple[str, list]], *, B: int, seed: int = 0, log=None) -> dict[str, Any]:
    """Replay every deployment through the ledger (as ``PLAN.md``), read the guard's flag time from the same record, then score the policies."""
    from . import prospective as pr

    arrs, flags = [], []
    for name, eps in deployments:
        led = pr.replay_hazard(dep, eps, name)
        arr = led.resolved("stuck_hazard")
        g = pr.guard_for(arr, horizon_s=pr.HORIZON_S)
        arrs.append(arr)
        flags.append(g["flag_time"] if g["flagged"] else None)
        if log:
            log(f"  {world} {name}: {arr['y'].size} origins, guard flagged={g['flagged']}")
    return score_world(world, arrs, flags, S_MIN, A_MIN, B=B, seed=seed)


# ------------------------------------------------------------------------------------------------------------------ claims
def judge_value(worlds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The registered pass rules of PLAN_VALUE.md section 4, applied as written."""
    v1 = worlds["v1"]
    shifted = [(f, worlds[f]) for f in wd.FAMILIES]
    out: list[dict[str, Any]] = []
    p_on, p_ts = v1["paired"]["model_vs_online_base"], v1["paired"]["model_vs_frozen_tsp"]
    out.append({"id": "V1", "claim": "v1 world: the model's decisions are worth more than either naive predictor's", "pass": bool(p_on["ci"][0] > 0 and p_ts["ci"][0] > 0),
                "evidence": {"vs_online_base": {"est": p_on["est"], "ci": p_on["ci"]}, "vs_frozen_tsp": {"est": p_ts["est"], "ci": p_ts["ci"]}}})
    worse = {f: bool(w["paired"]["model_vs_best_naive"]["ci"][1] < 0) for f, w in shifted}
    out.append({"id": "V2", "claim": "shifted worlds: the model that is worse on log loss is also worse in decision value, in at least 2 of 3", "pass": bool(sum(worse.values()) >= 2),
                "evidence": {"worlds_worse": int(sum(worse.values())), "worse": worse,
                             **{f: {"baseline": w["best_naive"], "est": w["paired"]["model_vs_best_naive"]["est"], "ci": w["paired"]["model_vs_best_naive"]["ci"]} for f, w in shifted}}})
    g1 = v1["guard"]["guarded_minus_always_model"]
    out.append({"id": "V3a", "claim": "v1 world: the guard costs at most 0.01 minutes per origin in decision value", "pass": bool(g1["ci"][0] >= -0.01),
                "evidence": {"est": g1["est"], "ci": g1["ci"], "flags": v1["guard"]["flags"], "of": v1["guard"]["of"]}})
    paid = {f: bool(w["guard"]["guarded_minus_always_model"]["ci"][0] > 0) for f, w in shifted}
    out.append({"id": "V3b", "claim": "shifted worlds: the guard earns decision value where the model fails, in at least 2 of 3", "pass": bool(sum(paid.values()) >= 2),
                "evidence": {"worlds_paid": int(sum(paid.values())), "paid": paid, **{f: {"est": w["guard"]["guarded_minus_always_model"]["est"], "ci": w["guard"]["guarded_minus_always_model"]["ci"]} for f, w in shifted}}})
    return out
