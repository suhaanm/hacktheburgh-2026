"""Split-conformal prediction sets and ranges for the deployed forecasts (``evals/hrt/PLAN_CONFORMAL.md``).

A held-back calibration pool turns a frozen predictor into a set or range whose coverage is at least the nominal level **when calibration and test cases are
exchangeable**. Three targets: T0 a set of labels for "no progress in the next 60 s" (score: one minus the probability of the true label); T1 a range of
30-second steps for the next progress event (conformalised quantile regression on the head's step quantiles); T2 a range of seconds until the episode ends (absolute
residual in log seconds of a ridge regression). Nothing is fitted after deployment: the only thing computed from calibration data is the conformal quantile.
Written from the idea, in our own words; the rules are fixed in the plan before any number existed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from . import scoring as sc
from . import worlds as wd

ALPHA = 0.10
NOMINAL = 1.0 - ALPHA
LOW_COVERAGE = 0.85                  # nominal less five points: the line K4 draws under a deployment's T0 coverage
T1_STEPS = 4                         # amendment A1: a two-minute horizon (the longest whole-minute horizon observable for at least 25% of the calibration origins)
BEYOND = T1_STEPS + 1                # "not within two minutes"
STEP_S = 30.0
HORIZON_S = 60.0
RIDGE = 1.0
CAL_K = (31, 32, 33, 34)
CAL_SHIFT_K = 51
DEV_K = (35, 36)
DEV_CAL_SHIFT_K = 52
HELD_K = tuple(range(41, 49))
TARGETS = ("t0", "t1", "t2")


def conformal_seeds() -> dict[str, list[int]]:
    """Every seed this plan uses, by pool (a test asserts they are new and distinct)."""
    return {
        "v1_cal": [wd.v1_seed(s, k) for k in CAL_K for s in wd.BASES],
        "v1_dev": [wd.v1_seed(s, k) for k in DEV_K for s in wd.BASES],
        "v1_held": [wd.v1_seed(s, k) for k in HELD_K for s in wd.BASES],
        "v2_dev": [wd.v2_seed(f, k) for k in DEV_K for f in wd.FAMILIES],
        "v2_held": [wd.v2_seed(f, k) for k in HELD_K for f in wd.FAMILIES],
        "v2_cal_shift": [wd.v2_seed(f, CAL_SHIFT_K) for f in wd.FAMILIES],
        "v2_dev_cal_shift": [wd.v2_seed(f, DEV_CAL_SHIFT_K) for f in wd.FAMILIES],
    }


# ------------------------------------------------------------------------------------------------------ the quantile rule
def conformal_quantile(scores: np.ndarray, alpha: float = ALPHA) -> float:
    """The order statistic number ceil((n + 1)(1 - alpha)) of the n calibration scores; infinite (the whole range) when that exceeds n."""
    s = np.sort(np.asarray(scores, dtype=float))
    n = s.size
    if n == 0:
        return float("inf")
    k = int(np.ceil((n + 1) * (1.0 - alpha) - 1e-9))
    return float("inf") if k > n else float(s[max(k, 1) - 1])


# ---------------------------------------------------------------------------------------------------------- sets (T0)
def lac_scores(p1: np.ndarray, y: np.ndarray) -> np.ndarray:
    """One minus the probability the model gave to the label that occurred."""
    p1 = np.asarray(p1, dtype=float)
    return np.where(np.asarray(y) == 1, 1.0 - p1, p1)


def lac_sets(p1: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray]:
    """(label 0 in the set, label 1 in the set): a label is in when one minus its probability is within the calibrated quantile."""
    p1 = np.asarray(p1, dtype=float)
    return p1 <= q, (1.0 - p1) <= q


def set_covered(y: np.ndarray, has0: np.ndarray, has1: np.ndarray) -> np.ndarray:
    return np.where(np.asarray(y) == 1, has1, has0)


def set_sizes(has0: np.ndarray, has1: np.ndarray) -> dict[str, float]:
    n = int(has0.size)
    both = float(np.mean(has0 & has1)) if n else float("nan")
    empty = float(np.mean(~has0 & ~has1)) if n else float("nan")
    return {"empty": empty, "single": 1.0 - both - empty if n else float("nan"), "both": both, "n": n}


# ------------------------------------------------------------------------------------------------------- step ranges (T1)
def step_quantile(cdf: np.ndarray, level: float) -> np.ndarray:
    """The first step (1 to K) whose CDF reaches ``level``, or K + 1 when none does."""
    cdf = np.asarray(cdf, dtype=float)
    ge = cdf >= level - 1e-12
    return np.where(ge.any(axis=1), ge.argmax(axis=1) + 1, BEYOND)


def cqr_scores(lo: np.ndarray, hi: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.maximum(np.asarray(lo) - np.asarray(y), np.asarray(y) - np.asarray(hi))


def cqr_covered(lo: np.ndarray, hi: np.ndarray, y: np.ndarray, q: float) -> np.ndarray:
    return (np.asarray(y) >= np.asarray(lo) - q) & (np.asarray(y) <= np.asarray(hi) + q)


def cqr_lengths(lo: np.ndarray, hi: np.ndarray, q: float) -> np.ndarray:
    """Steps inside the widened range, clipped to the support 1 to K + 1 (a range cannot hold steps that do not exist); 0 for an emptied range."""
    a = np.clip(np.asarray(lo, dtype=float) - q, 1, BEYOND)
    b = np.clip(np.asarray(hi, dtype=float) + q, 1, BEYOND)
    return np.maximum(b - a + 1, 0).astype(int)


# --------------------------------------------------------------------------------------------- the finish-time model (T2)
class FinishModel:
    """Ridge regression of log seconds remaining on standardised causal columns (strength fixed in the plan, not tuned)."""

    def __init__(self, ridge: float = RIDGE) -> None:
        self.ridge = float(ridge)
        self.mean_ = np.zeros(0)
        self.scale_ = np.ones(0)
        self.coef_ = np.zeros(0)
        self.intercept_ = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> FinishModel:
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        self.mean_ = X.mean(axis=0)
        sd = X.std(axis=0)
        self.scale_ = np.where(sd > 1e-9, sd, 1.0)
        Z = (X - self.mean_) / self.scale_
        self.intercept_ = float(y.mean())
        self.coef_ = np.linalg.solve(Z.T @ Z + self.ridge * np.eye(Z.shape[1]), Z.T @ (y - self.intercept_))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.intercept_ + ((np.asarray(X, dtype=float) - self.mean_) / self.scale_) @ self.coef_


def finish_columns(eps: list, tab: Any) -> tuple[np.ndarray, np.ndarray]:
    """The seven T2 columns and the seconds remaining, for exactly the bins of ``tab`` (episodes in the order ``build_bins`` consumed them). The two columns that
    are not in the hazard table are the log of one plus the seconds since the episode began and the log of one plus the progress events so far: both known at the origin."""
    el, npg, rem = [], [], []
    for ep in eps:
        k_max = int(np.floor((ep.t1 - HORIZON_S - ep.t0) / STEP_S)) + 1 if ep.t1 - ep.t0 >= HORIZON_S else 0
        if k_max <= 0:
            continue
        b = ep.t0 + STEP_S * np.arange(k_max)
        pt = np.sort(np.asarray(ep.progress_t, dtype=float))
        el.append(b - ep.t0)
        npg.append(np.searchsorted(pt, b, side="right").astype(float))
        rem.append(ep.t1 - b)
    if not el:
        return np.zeros((0, 7)), np.zeros(0)
    el_a, npg_a, rem_a = np.concatenate(el), np.concatenate(npg), np.concatenate(rem)
    if el_a.size != tab.n:
        raise ValueError(f"finish rows {el_a.size} do not match the bin table {tab.n}: pass the same episodes that built the table")
    return np.column_stack([np.log1p(el_a), np.log1p(npg_a), tab.dense]), rem_a


# ------------------------------------------------------------------------------------------------------------- deployment
@dataclass
class Models:
    dep: Any                     # prospective.Deployed (the stuck model and the frozen base rate)
    tte: Any                     # prospective.DeployedTTE (the head and the Kaplan-Meier constant)
    fin: FinishModel
    fin_const: float             # median log seconds remaining over TRAIN: the constant baseline of T2
    km_cdf: np.ndarray           # the Kaplan-Meier constant CDF over steps 1 to 4: the constant baseline of T1

    @property
    def base_rate(self) -> float:
        return float(self.dep.base_rate)


def fit_models(train_eps: list) -> Models:
    """Fit everything once on the deployment history (TRAIN) and freeze it."""
    from understudy_engine.hazard.features import build_bins

    from . import prospective as pr

    dep = pr.fit_deployed(train_eps)
    tte = pr.fit_deployed_tte(train_eps)
    tab = build_bins(train_eps)
    X, rem = finish_columns(train_eps, tab)
    logr = np.log(rem)
    return Models(dep, tte, FinishModel(RIDGE).fit(X, logr), float(np.median(logr)), 1.0 - tte.km.survival_row()[1:T1_STEPS + 1])


@dataclass
class Origins:
    deployment: np.ndarray
    person: np.ndarray
    y: np.ndarray                # T0 label
    p_model: np.ndarray          # T0 probability of label 1
    cdf: np.ndarray              # (n, K) the head's CDF over steps
    step_y: np.ndarray           # T1 outcome 1..K+1 on fully observed origins, 0 elsewhere
    full: np.ndarray             # all ten steps observable
    log_r: np.ndarray            # T2 target
    yhat: np.ndarray             # T2 prediction

    @property
    def n(self) -> int:
        return int(self.y.size)


def origins_for(models: Models, eps: list, deployment: int) -> Origins:
    """Per-origin forecasts and truths for one deployment's episodes (every 30 s bin)."""
    from understudy_engine.hazard.features import build_bins
    from understudy_engine.mlv2.tte import build_tte

    tab = build_bins(eps)
    rows = np.arange(tab.n)
    p = models.dep.models["full"].predict(tab, rows)
    tte = build_tte(eps, tab)
    cdf = 1.0 - models.tte.model.survival(tab, rows)[:, 1:T1_STEPS + 1]                    # the head's CDF over steps 1 to 4
    step_event = np.where(tte.event == 1, np.ceil(tte.time_s / STEP_S - 1e-9).astype(int), 0)
    full = tte.steps_obs >= T1_STEPS
    step_y = np.where(full, np.where((step_event >= 1) & (step_event <= T1_STEPS), step_event, BEYOND), 0)
    X, rem = finish_columns(eps, tab)
    return Origins(deployment=np.full(tab.n, deployment), person=np.array([f"{deployment}|{x}" for x in tab.person], dtype=object), y=np.asarray(tab.y).astype(int), p_model=np.asarray(p, dtype=float),
                   cdf=np.asarray(cdf, dtype=float), step_y=step_y.astype(int), full=np.asarray(full, dtype=bool), log_r=np.log(rem), yhat=models.fin.predict(X))


def concat(parts: list[Origins]) -> Origins:
    return Origins(*[np.concatenate([getattr(o, f) for o in parts]) for f in ("deployment", "person", "y", "p_model", "cdf", "step_y", "full", "log_r", "yhat")])


# --------------------------------------------------------------------------------------------------------------- calibrate
def _km_bounds(models: Models) -> tuple[int, int]:
    row = models.km_cdf[None, :]
    return int(step_quantile(row, ALPHA / 2)[0]), int(step_quantile(row, 1 - ALPHA / 2)[0])


def calibrate(o: Origins, models: Models) -> dict[str, Any]:
    """The conformal quantile of each target and of its baseline, from one calibration pool."""
    f = o.full
    lo, hi = step_quantile(o.cdf[f], ALPHA / 2), step_quantile(o.cdf[f], 1 - ALPHA / 2)
    klo, khi = _km_bounds(models)
    pb = np.full(o.n, models.base_rate)
    shift = float(np.median(o.log_r - o.yhat))
    return {"t0": conformal_quantile(lac_scores(o.p_model, o.y)), "t0_base": conformal_quantile(lac_scores(pb, o.y)),
            "t1": conformal_quantile(cqr_scores(lo, hi, o.step_y[f])), "t1_km": conformal_quantile(cqr_scores(np.full(lo.size, klo), np.full(lo.size, khi), o.step_y[f])),
            "t2": conformal_quantile(np.abs(o.log_r - o.yhat)), "t2_const": conformal_quantile(np.abs(o.log_r - models.fin_const)),
            "t2_shift": shift, "t2_recentred": conformal_quantile(np.abs(o.log_r - o.yhat - shift)),          # amendment A1: the reported "recentred" arm of T2
            "n": {"origins": o.n, "t1_origins": int(f.sum()), "people": len(np.unique(o.person))}}


def _by_deployment(o: Origins, cov: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows = []
    for d in sorted(set(o.deployment.tolist())):
        m = o.deployment == d
        mf = m & o.full
        rows.append({"deployment": int(d), "n": int(m.sum()), "t0": {"coverage": float(cov["t0"][m].mean())},
                     "t1": {"coverage": float(cov["t1_full"][(o.deployment[o.full] == d)].mean()) if mf.any() else None, "n": int(mf.sum())},
                     "t2": {"coverage": float(cov["t2"][m].mean())}})
    return rows


def evaluate(o: Origins, c: dict[str, Any], models: Models, *, B: int, seed: int) -> dict[str, Any]:
    """Coverage with a person-cluster bootstrap interval, width, and the baselines, of the quantiles ``c`` on the origins ``o``."""
    cl = sc.Clusters.from_labels(o.person)
    M = sc.multiplicities(cl.C, B, seed)
    mwi = lambda v, cl_=cl, M_=M: sc.mean_with_interval(np.asarray(v, dtype=float), cl_, M_)
    out: dict[str, Any] = {"n_origins": o.n, "n_people": cl.C, "nominal": NOMINAL, "bootstrap": {"B": B, "seed": seed, "unit": "people"}}
    # T0
    has0, has1 = lac_sets(o.p_model, c["t0"])
    cov0 = set_covered(o.y, has0, has1)
    pb = np.full(o.n, models.base_rate)
    b0, b1 = lac_sets(pb, c["t0_base"])
    covb = set_covered(o.y, b0, b1)
    out["t0"] = {"coverage": mwi(cov0), "sizes": set_sizes(has0, has1), "q": c["t0"], "baseline": {"coverage": mwi(covb), "sizes": set_sizes(b0, b1), "q": c["t0_base"]}}
    # T1: fully observed origins only
    f = o.full
    cov1_full = np.zeros(0, dtype=bool)
    if f.any():
        cl1 = sc.Clusters.from_labels(o.person[f])
        M1 = sc.multiplicities(cl1.C, B, seed)
        lo, hi = step_quantile(o.cdf[f], ALPHA / 2), step_quantile(o.cdf[f], 1 - ALPHA / 2)
        klo, khi = _km_bounds(models)
        klo_v, khi_v = np.full(lo.size, klo), np.full(lo.size, khi)
        y1 = o.step_y[f]
        cov1_full = cqr_covered(lo, hi, y1, c["t1"])
        len1, lenk = cqr_lengths(lo, hi, c["t1"]), cqr_lengths(klo_v, khi_v, c["t1_km"])
        covk = cqr_covered(klo_v, khi_v, y1, c["t1_km"])
        out["t1"] = {"coverage": mwi(cov1_full, cl1, M1), "length": mwi(len1, cl1, M1), "q": c["t1"], "n": int(f.sum()), "n_people": cl1.C, "share_excluded": float(1.0 - f.mean()),
                     "baseline": {"coverage": mwi(covk, cl1, M1), "length": mwi(lenk, cl1, M1), "q": c["t1_km"]}, "length_vs_km": sc.paired_difference(len1, lenk, cl1, M1)}
    else:
        out["t1"] = {"coverage": None, "n": 0, "share_excluded": 1.0}
    # T2
    resid = np.abs(o.log_r - o.yhat)
    cov2 = resid <= c["t2"]
    covc = np.abs(o.log_r - models.fin_const) <= c["t2_const"]
    cov_rc = np.abs(o.log_r - o.yhat - c["t2_shift"]) <= c["t2_recentred"]
    out["t2"] = {"coverage": mwi(cov2), "q_model": c["t2"], "factor_model": float(np.exp(2 * c["t2"])), "q_baseline": c["t2_const"], "factor_baseline": float(np.exp(2 * c["t2_const"])),
                 "baseline": {"coverage": mwi(covc)}, "median_abs_residual": float(np.median(resid)),
                 "recentred": {"coverage": mwi(cov_rc), "q": c["t2_recentred"], "factor": float(np.exp(2 * c["t2_recentred"])), "shift": c["t2_shift"]}}
    out["by_deployment"] = _by_deployment(o, {"t0": cov0, "t1_full": cov1_full, "t2": cov2})
    return out


# ------------------------------------------------------------------------------------------------------------------ worlds
def run_world(world: str, models: Models, deployments: list[tuple[str, list]], cal: dict[str, Any], shift_cal: dict[str, Any] | None, *, B: int, seed: int = 0, log=None) -> dict[str, Any]:
    """One world: the standard arm (the deployment-time quantiles ``cal``), the recalibrated arm (``shift_cal``, shifted worlds only) and the guard of ``PLAN.md`` on the
    same deployments' stuck forecasts, replayed through the ledger."""
    from . import prospective as pr

    pools, flagged = [], []
    for i, (name, eps) in enumerate(deployments):
        pools.append(origins_for(models, eps, i))
        led = pr.replay_hazard(models.dep, eps, name)
        flagged.append(bool(pr.guard_for(led.resolved("stuck_hazard"), horizon_s=pr.HORIZON_S)["flagged"]))
        if log:
            log(f"  {world} {name}: {pools[-1].n} origins, guard flagged={flagged[-1]}")
    o = concat(pools)
    std = evaluate(o, cal, models, B=B, seed=seed)
    low = [d["t0"]["coverage"] < LOW_COVERAGE for d in std["by_deployment"]]
    out = {"world": world, "n_deployments": len(deployments), "standard": std,
           "guard": {"flagged": flagged, "flags": int(sum(flagged)), "of": len(flagged), "flag_rate_ci": pr.cp_interval(int(sum(flagged)), len(flagged)),
                     "low_vs_flag": {"low_flagged": int(sum(l and f for l, f in zip(low, flagged))), "low_not_flagged": int(sum(l and not f for l, f in zip(low, flagged))),
                                     "ok_flagged": int(sum((not l) and f for l, f in zip(low, flagged))), "ok_not_flagged": int(sum((not l) and not f for l, f in zip(low, flagged))), "line": LOW_COVERAGE}},
           "calibration": cal["n"]}
    if shift_cal is not None:
        out["recalibrated"] = evaluate(o, shift_cal, models, B=B, seed=seed)
        out["recalibration_pool"] = shift_cal["n"]
    return out


# ------------------------------------------------------------------------------------------------------------------ claims
def _contains(ci: list[float], x: float) -> bool:
    return bool(ci[0] <= x <= ci[1])


def judge_conformal(worlds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The registered pass rules of PLAN_CONFORMAL.md section 5, applied as written. ``pass`` is None when the plan's own rule makes a claim not testable."""
    v1, shifted = worlds["v1"], [(f, worlds[f]) for f in wd.FAMILIES]
    label = {"t0": "stuck set", "t1": "time to next progress", "t2": "time to finish"}
    out: list[dict[str, Any]] = []
    for t, suffix in zip(TARGETS, "abc"):
        cov = v1["standard"][t]["coverage"]
        out.append({"id": f"K1{suffix}", "claim": f"v1 world: the standard arm's coverage of {label[t]} is consistent with the nominal 90%", "pass": bool(_contains(cov["ci"], NOMINAL)),
                    "evidence": {"coverage": cov["est"], "ci": cov["ci"], "nominal": NOMINAL}})
    for t, suffix in zip(TARGETS, "abc"):
        under = {f: bool(w["standard"][t]["coverage"]["ci"][1] < NOMINAL) for f, w in shifted}
        out.append({"id": f"K2{suffix}", "claim": f"shifted worlds: the standard arm under-covers {label[t]} in at least 2 of 3", "pass": bool(sum(under.values()) >= 2),
                    "evidence": {"worlds_under": int(sum(under.values())), "under": under, **{f: {"coverage": w["standard"][t]["coverage"]["est"], "ci": w["standard"][t]["coverage"]["ci"]} for f, w in shifted}}})
    t1 = v1["standard"]["t1"]["length_vs_km"]
    q_m, q_b = v1["standard"]["t2"]["q_model"], v1["standard"]["t2"]["q_baseline"]
    out.append({"id": "K3", "claim": "v1 world: the models' ranges are shorter than the baselines' at the same nominal level (T1 against Kaplan-Meier, T2 against the constant)",
                "pass": bool(t1["ci"][1] < 0 and q_m < q_b), "evidence": {"t1_length_difference": t1["est"], "t1_ci": t1["ci"], "t2_q_model": q_m, "t2_q_baseline": q_b}})
    low_total = low_missed = 0
    for _, w in shifted:
        for d, fl in zip(w["standard"]["by_deployment"], w["guard"]["flagged"]):
            if d["t0"]["coverage"] < LOW_COVERAGE:
                low_total += 1
                low_missed += int(not fl)
    v1_flags = int(sum(v1["guard"]["flagged"]))
    testable = low_total >= 3
    out.append({"id": "K4", "claim": "every shifted deployment whose stuck-set coverage is below 0.85 is one the guard flagged, and the guard flags at most 1 of 8 v1 deployments",
                "pass": (bool(low_missed == 0 and v1_flags <= 1) if testable else None),
                "evidence": {"low_coverage_deployments": low_total, "low_not_flagged": low_missed, "v1_flags": v1_flags, "v1_of": len(v1["guard"]["flagged"]), "testable": testable}})
    for t, suffix in zip(TARGETS, "abc"):
        ok = {f: bool(_contains(w["recalibrated"][t]["coverage"]["ci"], NOMINAL)) for f, w in shifted}
        out.append({"id": f"K5{suffix}", "claim": f"shifted worlds: recalibrating the quantile on one deployment of the new world restores {label[t]} coverage in at least 2 of 3", "pass": bool(sum(ok.values()) >= 2),
                    "evidence": {"worlds_restored": int(sum(ok.values())), "restored": ok, **{f: {"coverage": w["recalibrated"][t]["coverage"]["est"], "ci": w["recalibrated"][t]["coverage"]["ci"]} for f, w in shifted}}})
    return out
