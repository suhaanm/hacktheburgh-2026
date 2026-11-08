"""The guard: notice, from the ledger's own scored predictions, that a model has stopped being better than a naive predictor, and fall back.

A decision rule, so it is code and it is scored (a premium when nothing is wrong, a payout when the model is wrong), not a model's opinion.

Evidence is an **e-process** (a betting capital) against the null "the model is no worse than the fallback". For each unit (an episode, or a
case) that has resolved, ``d`` is the unit's mean log loss of the model minus that of the fallback, clipped to [-B, B]. The capital is

    K_t = K_{t-1} * (1 + lambda * d_t / B),   K_0 = 1,   0 < lambda < 1,

which is positive because |d_t / B| <= 1. If each d_t has conditional mean at most 0 given the past (the model is no worse), K is a
non-negative supermartingale, so the probability that it ever reaches 1 / alpha is at most alpha (Ville's inequality). The flag is the first
time K reaches ``THRESHOLD`` = 20 (alpha = 5%). That guarantee needs the conditional-mean condition; units of one person are not independent,
so in this repository it is a design target that the no-drift deployments check, not a proof (PLAN.md section 9).

After a flag the system uses the fallback for every prediction made after the flag was raised. There is no return rule in this version.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .scoring import B_LOSS

LAMBDA = 0.8
THRESHOLD = 20.0


@dataclass
class EProcess:
    lam: float = LAMBDA
    B: float = B_LOSS
    threshold: float = THRESHOLD
    capital: float = 1.0
    n: int = 0
    flagged_at: int | None = None
    peak: float = 1.0

    def update(self, d: float) -> bool:
        """Feed one unit's loss difference (model minus fallback). Returns True if this update raised the flag."""
        if not 0.0 < self.lam < 1.0:
            raise ValueError("lambda must be in (0, 1)")
        d = float(np.clip(d, -self.B, self.B))
        self.capital *= 1.0 + self.lam * d / self.B
        self.peak = max(self.peak, self.capital)
        self.n += 1
        if self.flagged_at is None and self.capital >= self.threshold:
            self.flagged_at = self.n
            return True
        return False

    @property
    def flagged(self) -> bool:
        return self.flagged_at is not None


@dataclass
class Units:
    """One row per unit (episode or case): when its last outcome resolved, the model's and the fallback's summed loss, and how many bins it has."""

    resolved_at: np.ndarray
    sum_model: np.ndarray
    sum_fallback: np.ndarray
    n_bins: np.ndarray


def units_from_bins(unit_id: np.ndarray, made_at: np.ndarray, resolved_at: np.ndarray, ll_model: np.ndarray, ll_fallback: np.ndarray) -> Units:
    """Group per-bin losses into units, ordered by the time each unit's last outcome resolved."""
    uniq, inv = np.unique(np.asarray(unit_id), return_inverse=True)
    n = np.bincount(inv, minlength=uniq.size).astype(float)
    res = np.full(uniq.size, -np.inf)
    np.maximum.at(res, inv, np.asarray(resolved_at, dtype=float))
    sm = np.bincount(inv, weights=ll_model, minlength=uniq.size)
    sf = np.bincount(inv, weights=ll_fallback, minlength=uniq.size)
    order = np.argsort(res, kind="mergesort")
    return Units(res[order], sm[order], sf[order], n[order])


def run_guard(units: Units, *, lam: float = LAMBDA, threshold: float = THRESHOLD, B: float = B_LOSS) -> dict[str, Any]:
    """Run the e-process over the units in resolution order. Returns the flag time (the resolved_at of the unit that raised it), the unit index and
    the capital path summary."""
    ep = EProcess(lam=lam, B=B, threshold=threshold)
    flag_t: float | None = None
    path_max = 1.0
    for i in range(units.resolved_at.size):
        d = (units.sum_model[i] - units.sum_fallback[i]) / max(units.n_bins[i], 1.0)
        if ep.update(d) and flag_t is None:
            flag_t = float(units.resolved_at[i])
        path_max = max(path_max, ep.capital)
    return {"flagged": ep.flagged, "flag_unit": ep.flagged_at, "flag_time": flag_t, "n_units": int(units.resolved_at.size), "final_capital": ep.capital,
            "peak_capital": path_max}


def strategy_costs(made_at: np.ndarray, ll_model: np.ndarray, ll_fallback: np.ndarray, flag_time: float | None) -> dict[str, float]:
    """Mean per-bin log loss of four strategies over one deployment: always the model, always the fallback, the guard (the model until the flag, the
    fallback for predictions made after it), and the oracle (the better of the first two in hindsight). Regret = mean loss minus the oracle's."""
    made_at = np.asarray(made_at, dtype=float)
    use_fb = np.zeros(made_at.size, dtype=bool) if flag_time is None else made_at > flag_time
    guarded = np.where(use_fb, ll_fallback, ll_model)
    a, b, g = float(np.mean(ll_model)), float(np.mean(ll_fallback)), float(np.mean(guarded))
    o = min(a, b)
    return {"always_model": a, "always_fallback": b, "guarded": g, "oracle": o,
            "regret_always_model": a - o, "regret_always_fallback": b - o, "regret_guarded": g - o,
            "share_on_fallback": float(use_fb.mean())}
