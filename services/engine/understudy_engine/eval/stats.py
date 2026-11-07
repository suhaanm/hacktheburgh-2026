"""Small deterministic statistics helpers for the eval harness (numpy only, fixed seeds)."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

LEVEL = 0.95
Z95 = 1.959963984540054


def rnd(x, nd: int = 4):
    """Round a float for the report; NaN and inf become None (JSON has no NaN)."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(xf) or math.isinf(xf):
        return None
    return round(xf, nd)


def interval(samples: Sequence[float] | np.ndarray, level: float = LEVEL, nd: int = 3) -> list[float | None]:
    """Percentile interval of a bootstrap or permutation distribution; NaN draws are ignored."""
    a = np.asarray(samples, dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return [None, None]
    lo, hi = np.percentile(a, [100 * (1 - level) / 2, 100 * (1 + level) / 2])
    return [rnd(lo, nd), rnd(hi, nd)]


def wilson(k: int, n: int, z: float = Z95) -> list[float | None]:
    if n <= 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [rnd(max(0.0, c - h)), rnd(min(1.0, c + h))]


def boot_indices(n_clusters: int, B: int, seed: int) -> np.ndarray:
    """B x n_clusters matrix of cluster indices drawn with replacement (the cluster bootstrap)."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_clusters, size=(B, n_clusters))


def cluster_mean_interval(values: Sequence[float], B: int, seed: int, nd: int = 3) -> list[float | None]:
    """95% interval of the mean of per-cluster values, resampling clusters (people) with replacement."""
    v = np.asarray(list(values), dtype=float)
    if v.size == 0:
        return [None, None]
    if v.size == 1:
        return [rnd(v[0], nd), rnd(v[0], nd)]
    idx = boot_indices(v.size, B, seed)
    return interval(v[idx].mean(axis=1), nd=nd)


def ratio_interval(num: np.ndarray, den: np.ndarray, B: int, seed: int, nd: int = 3) -> list[float | None]:
    """Cluster bootstrap of sum(num)/sum(den) over clusters; draws with an empty denominator are dropped."""
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    if num.size == 0:
        return [None, None]
    idx = boot_indices(num.size, B, seed)
    n_ = num[idx].sum(axis=1)
    d_ = den[idx].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(d_ > 0, n_ / d_, np.nan)
    return interval(r, nd=nd)


def t_interval(values: Sequence[float], level: float = LEVEL, nd: int = 3) -> list[float | None]:
    """Student-t interval of the mean (df = n - 1). Used where n is tiny and a bootstrap would be too narrow."""
    from scipy import stats as sps

    v = np.asarray(list(values), dtype=float)
    n = v.size
    if n < 2:
        return [None, None]
    m, se = v.mean(), v.std(ddof=1) / math.sqrt(n)
    q = float(sps.t.ppf(0.5 + level / 2, n - 1))
    return [rnd(m - q * se, nd), rnd(m + q * se, nd)]
