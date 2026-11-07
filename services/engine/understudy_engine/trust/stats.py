"""Small, hand-rolled interval and resampling helpers shared by the analytics modules.

Everything here is pure and deterministic (a seed is always explicit). No model calls.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from scipy import stats as _st

Z95 = 1.959963984540054  # two-sided 95% normal quantile; the trust ladder uses 1.96 (see trust.ladder)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Returns (lower, upper); (0, 1) when n == 0."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"need 0 <= successes <= n, got {successes}/{n}")
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    # Exact endpoints: the closed form leaves ~1e-17 residue at p = 0 or 1.
    if successes == 0:
        lo = 0.0
    if successes == n:
        hi = 1.0
    return lo, hi


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower end of the Wilson interval. 20 clean runs of 20 give about 0.839; 73 of 73 pass 0.95."""
    return wilson_interval(successes, n, z)[0]


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided Clopper-Pearson interval at level 1 - alpha."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got {k}/{n}")
    if n == 0:
        return 0.0, 1.0
    lo = 0.0 if k == 0 else float(_st.beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(_st.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lo, hi


def clopper_pearson_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """Exact ONE-sided upper bound at confidence 1 - alpha on a binomial rate (k errors in n cases).

    This is the bound used by the review-routing risk control: with prob >= 1 - alpha the true error
    rate of the auto-approved set is at most this value. n == 0 gives 1.0 (no evidence, no bound).
    """
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got {k}/{n}")
    if n == 0 or k == n:
        return 1.0
    return float(_st.beta.ppf(1 - alpha, k + 1, n - k))


def percentile_interval(samples: Sequence[float] | np.ndarray, level: float = 0.95) -> tuple[float, float]:
    a = np.asarray(samples, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return float("nan"), float("nan")
    tail = (1.0 - level) / 2.0
    return float(np.quantile(a, tail)), float(np.quantile(a, 1.0 - tail))


def bootstrap_ci(
    values: Sequence[float] | np.ndarray,
    stat: Callable[[np.ndarray], float] = np.mean,
    *,
    n_boot: int = 1000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Plain percentile bootstrap over i.i.d. units."""
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, a.size, size=(n_boot, a.size))
    draws = np.array([stat(a[i]) for i in idx])
    return percentile_interval(draws, level)


def cluster_resample_indices(n_clusters: int, n_boot: int, seed: int) -> np.ndarray:
    """(n_boot, n_clusters) integer matrix of cluster indices drawn with replacement."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_clusters, size=(n_boot, n_clusters))
