"""Build timing by ski rental with predictions (ANA-11).

Rule (Kumar, Purohit, Svitkina, NeurIPS 2018, Algorithm 2; see docs/reference-notes/ski-rental.md). Renting is one
manual run (cost 1). Buying is building the automation (cost ``b``, in manual runs). The true number of future runs
``x`` is unknown; a forecast gives ``y``. With trust ``lam`` in (0, 1):

    if y >= b: buy at the start of run ceil(lam * b)         (trust the prediction: buy early)
    else:      buy at the start of run ceil(b / lam)         (the prediction says it will not pay: wait longer)

"Buy at the start of run t" means t - 1 manual runs first. Against the offline optimum ``min(x, b)`` the rule is
(1 + lam)-consistent (prediction exact) and (1 + 1/lam)-robust (prediction arbitrarily wrong). Integer rounding by
``ceil`` is ours; ``tests/handoff/test_skirental.py`` checks both constants by brute force with the rounding.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


def buy_run(y: float, b: float, lam: float) -> int:
    """The run (1-based) at whose start the automation is bought."""
    if not 0 < lam < 1:
        raise ValueError("lam must be in (0, 1)")
    if b <= 0:
        return 1
    return max(1, math.ceil(lam * b)) if y >= b else max(1, math.ceil(b / lam))


def buy_after_runs(y: float, b: float, lam: float) -> int:
    """Manual runs done before building."""
    return buy_run(y, b, lam) - 1


def cost(x: float, t: int, b: float) -> float:
    """Cost in manual-run units when buying at the start of run ``t`` and ``x`` runs actually happen."""
    return (t - 1) + b if x >= t else float(x)


def optimum(x: float, b: float) -> float:
    return min(float(x), b)


def break_even_run(b: float) -> int:
    """Classic deterministic rule: rent until the rent paid equals the price, then buy (2-competitive)."""
    return max(1, math.ceil(b))


def robustness(lam: float) -> float:
    return 1.0 + 1.0 / lam


def consistency(lam: float) -> float:
    return 1.0 + lam


def choose_lambda(rel_errors: Sequence[float], lo: float = 0.15, hi: float = 0.85) -> float:
    """Trust parameter from past forecast error (a heuristic of ours, not from the paper).

    ``rel_errors`` are past ``|log(y / x)|``. A median of 0 (forecasts exact) gives ``lo`` (small lambda: buy early,
    consistency 1 + lo); a median of 1 or more (off by a factor of e) gives ``hi`` (large lambda: robustness 1 + 1/hi).
    With no history it returns 0.5.
    """
    if len(rel_errors) == 0:
        return 0.5
    eps = float(np.median(np.abs(rel_errors)))
    return float(np.clip(lo + (hi - lo) * min(eps / 1.0, 1.0), lo, hi))


@dataclass(frozen=True)
class BuildTiming:
    rule: str
    lam: float
    b: float
    y: float
    buy_after_runs: int
    runs_done: int | None
    consistency: float
    robustness: float
    regret_vs_hindsight: float | None   # expected regret in manual runs under the forecast distribution
    note: str

    def contract(self) -> dict:
        return {"rule": "ski-rental", "buy_after_runs": self.buy_after_runs, "regret_vs_hindsight": self.regret_vs_hindsight,
                "lambda": round(self.lam, 2), "buy_cost_runs": round(self.b, 2), "predicted_runs": round(self.y, 1),
                "consistency": round(self.consistency, 2), "robustness": round(self.robustness, 2), "note": self.note}


def plan_build(y: float, b: float, lam: float, run_draws: np.ndarray | None = None, runs_done: int | None = None) -> BuildTiming:
    t = buy_run(y, b, lam)
    regret = None
    if run_draws is not None and len(run_draws):
        regret = round(float(np.mean([cost(x, t, b) - optimum(x, b) for x in run_draws])), 2)
    side = "the forecast says it will pay, so build early" if y >= b else "the forecast says it may not pay, so wait longer"
    return BuildTiming("ski-rental", lam, b, y, t - 1, runs_done, consistency(lam), robustness(lam), regret,
                       f"{side}: do {t - 1} more runs by hand, then build (cost of building is {b:.1f} manual runs)")
