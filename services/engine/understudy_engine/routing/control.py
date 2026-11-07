"""Risk control for auto-approval (ANA-8).

Goal: auto-approve as many cases as possible while the error rate among the auto-approved stays at most `alpha`,
with confidence 1 - delta.

Procedure on a CALIBRATION split:
  1. order cases by calibrated risk, lowest first
  2. try auto-approving the lowest-risk `c` share for c on a grid of `n_grid` coverages
  3. for each, the exact (Clopper-Pearson) one-sided upper bound on the error rate among those cases, at
     confidence 1 - delta / n_grid when `correction="bonferroni"` (a union bound over the grid, so picking
     the best grid point does not inflate the guarantee) or 1 - delta when `correction="none"` (the naive
     version: pick the largest set whose bound is at most alpha; reported so the held-out check can show what
     the naive choice costs)
  4. take the largest coverage whose bound is at most alpha; its risk value is the approval threshold

Then CHECK on a held-out split the model never saw: apply the threshold, count errors among the approved
cases, and report the observed rate with its own Clopper-Pearson interval. The claim is "true error rate of the
auto-approved set <= alpha with probability >= 1 - delta"; the held-out data contradicts it only if the lower
end of that interval exceeds alpha (`violated`).
"""
from __future__ import annotations

import numpy as np

from understudy_engine.trust.stats import clopper_pearson, clopper_pearson_upper


def risk_control(risk_cal: np.ndarray, y_cal: np.ndarray, alpha: float, delta: float = 0.05, *, n_grid: int = 40,
                 correction: str = "bonferroni") -> dict:
    if correction not in ("bonferroni", "none"):
        raise ValueError(correction)
    risk_cal = np.asarray(risk_cal, float)
    y_cal = np.asarray(y_cal, int)
    n = risk_cal.size
    order = np.argsort(risk_cal, kind="mergesort")
    r_sorted, y_sorted = risk_cal[order], y_cal[order]
    cum_err = np.cumsum(y_sorted)
    d = delta / n_grid if correction == "bonferroni" else delta
    best = {"threshold": -np.inf, "coverage": 0.0, "k": 0, "errors": 0, "upper_bound": 1.0, "feasible": False}
    tested = []
    for j in range(1, n_grid + 1):
        k = int(np.ceil(j / n_grid * n))
        e = int(cum_err[k - 1])
        ub = clopper_pearson_upper(e, k, d)
        tested.append({"coverage": k / n, "k": k, "errors": e, "upper_bound": ub})
        if ub <= alpha and k >= best["k"]:
            best = {"threshold": float(r_sorted[k - 1]), "coverage": k / n, "k": k, "errors": e,
                    "upper_bound": ub, "feasible": True}
    return {**best, "alpha": alpha, "delta": delta, "delta_per_test": d, "correction": correction,
            "n_cal": int(n), "n_grid": n_grid, "grid": tested}


def check_heldout(threshold: float, risk_test: np.ndarray, y_test: np.ndarray, alpha: float) -> dict:
    """Apply the threshold to unseen cases and test the claim 'error rate among approved <= alpha'."""
    approved = np.asarray(risk_test, float) <= threshold
    k = int(approved.sum())
    e = int(np.asarray(y_test, int)[approved].sum())
    if k == 0:
        return {"approved": 0, "coverage": 0.0, "errors": 0, "error_rate": None, "ci": None, "violated": False,
                "observed_within_alpha": True, "note": "nothing auto-approved"}
    lo, hi = clopper_pearson(e, k, 0.05)
    return {"approved": k, "coverage": k / approved.size, "errors": e, "error_rate": e / k, "ci": [lo, hi],
            "violated": bool(lo > alpha), "observed_within_alpha": bool(e / k <= alpha)}


def risk_coverage_curve(risk: np.ndarray, y: np.ndarray, n_points: int = 40, delta: float = 0.05) -> list[dict]:
    """Empirical risk-coverage: for each coverage c, the error rate among the lowest-risk c share, with an exact
    upper bound. The lowest coverage points are noisy; the `n` field says how many cases back each point."""
    risk = np.asarray(risk, float)
    y = np.asarray(y, int)
    n = risk.size
    order = np.argsort(risk, kind="mergesort")
    ys = y[order]
    cum = np.cumsum(ys)
    out = []
    for j in range(1, n_points + 1):
        k = max(1, int(np.ceil(j / n_points * n)))
        e = int(cum[k - 1])
        out.append({"coverage": k / n, "n": k, "error_rate": e / k, "upper_bound": clopper_pearson_upper(e, k, delta)})
    return out


def aurc(curve: list[dict]) -> float:
    """Area under the risk-coverage curve (lower is better), trapezoid rule over the curve's points."""
    c = np.array([0.0] + [p["coverage"] for p in curve])
    r = np.array([curve[0]["error_rate"]] + [p["error_rate"] for p in curve])
    return float(np.trapezoid(r, c))
