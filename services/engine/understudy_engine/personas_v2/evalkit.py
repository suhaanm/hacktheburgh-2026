"""Small statistics for the realism evaluation: person-cluster bootstrap, paired differences, ratios.

Everything is numpy, seeded and cluster-aware: the resampling unit is always a *person* (never a bin or an episode), and
a delta between two cells is computed on the same resampled people (paired).
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

B_FULL = 1000
B_FAST = 200


def boot_idx(n: int, B: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, max(n, 1), size=(B, max(n, 1)))


def interval(draws: np.ndarray, level: float = 0.95, nd: int = 4) -> list[float | None]:
    d = np.asarray(draws, dtype=float)
    d = d[~np.isnan(d)]
    if d.size < 10:
        return [None, None]
    lo, hi = np.percentile(d, [100 * (1 - level) / 2, 100 * (1 + level) / 2])
    return [round(float(lo), nd), round(float(hi), nd)]


def rnd(x, nd: int = 4):
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    return None if math.isnan(xf) or math.isinf(xf) else round(xf, nd)


def mean_draws(vals: np.ndarray, idx: np.ndarray) -> np.ndarray:
    return vals[idx].mean(axis=1)


def ratio_draws(num: np.ndarray, den: np.ndarray, idx: np.ndarray) -> np.ndarray:
    n_, d_ = num[idx].sum(axis=1), den[idx].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d_ > 0, n_ / d_, np.nan)


def point_mean(vals: np.ndarray) -> float:
    return float(vals.mean()) if vals.size else float("nan")


def point_ratio(num: np.ndarray, den: np.ndarray) -> float:
    d = float(den.sum())
    return float(num.sum() / d) if d > 0 else float("nan")


def est(point: float, draws: np.ndarray, nd: int = 4) -> dict:
    return {"est": rnd(point, nd), "ci": interval(draws, nd=nd)}


def verdict(delta_point: float, ci: Sequence[float | None], margin: float, higher_is_better: bool = True) -> str:
    """The pre-registered rule: degrades / transfers / inconclusive (``PLAN.md`` section 4)."""
    if ci[0] is None or delta_point is None or math.isnan(delta_point):
        return "inconclusive"
    harm_pt = -delta_point if higher_is_better else delta_point
    lo, hi = ci
    entirely_harmful = (hi < 0) if higher_is_better else (lo > 0)
    if entirely_harmful and harm_pt > margin:
        return "degrades"
    if lo <= 0 <= hi and abs(delta_point) <= margin:
        return "transfers"
    return "inconclusive"


def sd_across(vals: Sequence[float]) -> float | None:
    v = [x for x in vals if x is not None and not math.isnan(x)]
    return rnd(float(np.std(v, ddof=1)), 4) if len(v) >= 2 else None
