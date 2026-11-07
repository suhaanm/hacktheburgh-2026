"""Small, deterministic statistics for the insights layer (REQ-9). Pure functions; every resampling takes an explicit seed.

* ``one_sample`` / ``welch``: t intervals and two-sided p-values for a mean and a difference of means (person-level means for admin).
* ``newcombe``: hybrid-score interval for a difference of two proportions (Wilson bounds), with a two-proportion z p-value.
* ``bonferroni_z``: the interval multiplier at the family-adjusted level. ``bh_pass``: the Benjamini-Hochberg step-up set.
* ``km``: Kaplan-Meier with Greenwood log-log intervals (right-censored times, used for time to independence).
* ``seed_from``: a stable integer seed from ids, so a bootstrap is the same on every machine and every run.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as _st

from ..trust.stats import wilson_interval

Z95 = 1.959963984540054
_EPS = 1e-12


def seed_from(*parts: object) -> int:
    return int(hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def norm_two_sided_p(z: float) -> float:
    return float(2.0 * _st.norm.sf(abs(z)))


def bonferroni_z(alpha: float, m: int) -> float:
    """The normal multiplier for a two-sided interval at family-wise level ``alpha`` shared over ``m`` tests."""
    m = max(1, int(m))
    return float(_st.norm.ppf(1.0 - alpha / (2.0 * m)))


def t_mult(df: float, level: float = 0.95) -> float:
    return float(_st.t.ppf(0.5 + level / 2.0, max(1.0, df)))


@dataclass(frozen=True)
class Est:
    value: float
    lo: float
    hi: float
    se: float
    p: float
    n: int
    df: float

    def ci(self) -> list[float]:
        return [self.lo, self.hi]


def one_sample(x: Sequence[float], level: float = 0.95) -> Est | None:
    a = np.asarray(list(x), float)
    n = int(a.size)
    if n < 2:
        return None
    m = float(a.mean())
    se = max(float(a.std(ddof=1)) / math.sqrt(n), _EPS)
    df = n - 1.0
    tt = t_mult(df, level)
    p = float(2.0 * _st.t.sf(abs(m / se), df))
    return Est(m, m - tt * se, m + tt * se, se, p, n, df)


def welch(x: Sequence[float], y: Sequence[float], level: float = 0.95) -> Est | None:
    """The difference ``mean(x) - mean(y)`` with a Welch interval and a two-sided Welch p."""
    a, b = np.asarray(list(x), float), np.asarray(list(y), float)
    na, nb = int(a.size), int(b.size)
    if na < 2 or nb < 2:
        return None
    va, vb = float(a.var(ddof=1)) / na, float(b.var(ddof=1)) / nb
    se = max(math.sqrt(va + vb), _EPS)
    d = float(a.mean() - b.mean())
    den = (va * va / (na - 1)) + (vb * vb / (nb - 1))
    df = (va + vb) ** 2 / den if den > 0 else float(na + nb - 2)
    tt = t_mult(df, level)
    p = float(2.0 * _st.t.sf(abs(d / se), df))
    return Est(d, d - tt * se, d + tt * se, se, p, na + nb, df)


def newcombe(k1: int, n1: int, k2: int, n2: int, z: float = Z95) -> tuple[float, float, float, float] | None:
    """``(diff, lo, hi, p)`` for ``p1 - p2`` (Newcombe hybrid score interval; z test with unpooled variance for p). None when a side is empty."""
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson_interval(k1, n1, z)
    l2, u2 = wilson_interval(k2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    p = norm_two_sided_p(d / max(se, _EPS)) if se > 0 else (1.0 if abs(d) < _EPS else 0.0)
    return d, lo, hi, p


def bh_pass(items: Sequence[tuple[str, float]], q: float) -> set[str]:
    """Benjamini-Hochberg step-up: the ids whose p-value is at or below the largest ``p_(i) <= q * i / m``. Ties in p order by id."""
    m = len(items)
    if m == 0:
        return set()
    order = sorted(items, key=lambda t: (t[1], t[0]))
    cut = -1
    for i, (_id, p) in enumerate(order, start=1):
        if p <= q * i / m:
            cut = i
    return {order[j][0] for j in range(cut)} if cut > 0 else set()


@dataclass(frozen=True)
class KMPoint:
    x: float
    s: float
    lo: float
    hi: float
    at_risk: int
    events: int


def km(times: Sequence[float], events: Sequence[bool], grid: Sequence[float]) -> list[KMPoint]:
    """Kaplan-Meier survival S(x) at the grid points with Greenwood log-log 95% intervals. ``events[i]`` False means censored at ``times[i]``."""
    t = np.asarray(list(times), float)
    e = np.asarray(list(events), bool)
    out: list[KMPoint] = []
    uniq = sorted(set(float(v) for v in t[e]))
    for x in grid:
        s, gw = 1.0, 0.0
        for u in uniq:
            if u > x:
                break
            n_at = int((t >= u).sum())
            d = int(((t == u) & e).sum())
            if n_at <= 0:
                continue
            s *= 1.0 - d / n_at
            if n_at > d:
                gw += d / (n_at * (n_at - d))
        at_risk = int((t >= x).sum())
        if s <= 0.0 or s >= 1.0 or gw <= 0.0:
            # a Greenwood interval has zero width when nobody (or everybody) has had the event: fall back to the Wilson interval on the people whose
            # status at x is known (event by x, or followed to x), so the interval never claims certainty it does not have
            k_ev = int(((t <= x) & e).sum())
            n_known = k_ev + int((t > x).sum()) + int(((t == x) & ~e).sum())
            if n_known > 0:
                wl, wh = wilson_interval(k_ev, n_known)
                lo, hi = 1.0 - wh, 1.0 - wl
            else:
                lo = hi = s
        else:
            se = math.sqrt(gw) / abs(math.log(s))
            lo = s ** math.exp(Z95 * se)
            hi = s ** math.exp(-Z95 * se)
        out.append(KMPoint(float(x), float(s), float(min(lo, hi)), float(max(lo, hi)), at_risk, int(((t <= x) & e).sum())))
    return out


def km_median(times: Sequence[float], events: Sequence[bool]) -> float | None:
    """The smallest time at which S falls to 0.5 or below, or None when it never does (more than half censored before that)."""
    t = np.asarray(list(times), float)
    e = np.asarray(list(events), bool)
    s = 1.0
    for u in sorted(set(float(v) for v in t[e])):
        n_at = int((t >= u).sum())
        d = int(((t == u) & e).sum())
        if n_at <= 0:
            continue
        s *= 1.0 - d / n_at
        if s <= 0.5:
            return u
    return None


def boot_means(groups: Sequence[Sequence[float]], n_boot: int, seed: int) -> np.ndarray:
    """Person-level bootstrap of the mean of per-person values (resample people with replacement)."""
    a = np.asarray(list(groups), float)
    if a.size == 0:
        return np.zeros(0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, a.size, size=(n_boot, a.size))
    return a[idx].mean(axis=1)


def round_or_none(x: float | None, nd: int = 4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), nd)


def median_est(x: Sequence[float], level: float = 0.95) -> Est | None:
    """The median with a distribution-free (exact binomial order-statistic) interval and a sign-test p-value against 0. Robust to the heavy tail
    of task times; the expert reference is itself a median, so "is this person slower than the expert's median" is exactly the sign test."""
    a = sorted(float(v) for v in x)
    n = len(a)
    if n < 2:
        return None
    med = float(np.median(a))
    alpha = 1.0 - level
    r = 0
    for j in range(1, n // 2 + 1):
        if _st.binom.cdf(j - 1, n, 0.5) <= alpha / 2.0:
            r = j
        else:
            break
    lo, hi = (a[r - 1], a[n - r]) if r >= 1 else (a[0], a[-1])
    pos = sum(1 for v in a if v > 0)
    m = sum(1 for v in a if v != 0)
    p = float(_st.binomtest(pos, m, 0.5).pvalue) if m > 0 else 1.0
    return Est(med, float(lo), float(hi), float("nan"), p, n, float("nan"))


def median_diff(x: Sequence[float], y: Sequence[float], n_boot: int, seed: int, level: float = 0.95) -> Est | None:
    """``median(x) - median(y)`` with a seeded percentile bootstrap interval and a two-sided Mann-Whitney p-value."""
    a, b = np.asarray(list(x), float), np.asarray(list(y), float)
    if a.size < 2 or b.size < 2:
        return None
    d = float(np.median(a) - np.median(b))
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a.size, size=(n_boot, a.size))
    ib = rng.integers(0, b.size, size=(n_boot, b.size))
    draws = np.median(a[ia], axis=1) - np.median(b[ib], axis=1)
    tail = (1.0 - level) / 2.0
    lo, hi = float(np.quantile(draws, tail)), float(np.quantile(draws, 1.0 - tail))
    p = float(_st.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    return Est(d, lo, hi, float(draws.std(ddof=1)), p, int(a.size + b.size), float("nan"))
