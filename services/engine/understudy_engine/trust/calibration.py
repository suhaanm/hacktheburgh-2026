"""Proper scoring rules, calibration metrics and recalibration maps (Platt, isotonic).

Hand-rolled so every number in the evidence report can be traced to a few lines here.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

EPS = 1e-12


def _clip(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    p = _clip(p)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2))


def reliability_bins(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Equal-width bins on [0, 1]. Each non-empty bin: {p_mean, freq, n, lo, hi}."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    idx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        if n == 0:
            continue
        out.append({
            "p_mean": float(p[m].mean()), "freq": float(y[m].mean()), "n": n,
            "lo": b / n_bins, "hi": (b + 1) / n_bins,
        })
    return out


def ece(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error: bin-size-weighted mean |freq - p_mean| over equal-width bins."""
    bins = reliability_bins(y, p, n_bins)
    n = sum(b["n"] for b in bins)
    if n == 0:
        return float("nan")
    return float(sum(b["n"] * abs(b["freq"] - b["p_mean"]) for b in bins) / n)


def score_all(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict[str, float]:
    return {"log_loss": log_loss(y, p), "brier": brier(y, p), "ece": ece(y, p, n_bins)}


def logit(p: np.ndarray | float) -> np.ndarray:
    p = _clip(np.asarray(p, dtype=float))
    return np.log(p / (1 - p))


def sigmoid(z: np.ndarray | float) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


class PlattScaler:
    """p' = sigmoid(a * logit(p) + b), fitted by maximum likelihood on a calibration split."""

    def __init__(self) -> None:
        self.a = 1.0
        self.b = 0.0

    def fit(self, p: np.ndarray, y: np.ndarray) -> "PlattScaler":
        s = logit(p)
        y = np.asarray(y, dtype=float)

        def nll(w: np.ndarray) -> tuple[float, np.ndarray]:
            q = sigmoid(w[0] * s + w[1])
            q = _clip(q)
            loss = -np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))
            g = q - y
            return float(loss), np.array([np.mean(g * s), np.mean(g)])

        res = minimize(nll, x0=np.array([1.0, 0.0]), jac=True, method="L-BFGS-B")
        self.a, self.b = float(res.x[0]), float(res.x[1])
        return self

    def transform(self, p: np.ndarray) -> np.ndarray:
        return sigmoid(self.a * logit(p) + self.b)


class IsotonicCalibrator:
    """Monotone non-decreasing map p -> E[y | p] by pool-adjacent-violators, linear between knots."""

    def __init__(self) -> None:
        self.x: np.ndarray = np.array([0.0, 1.0])
        self.y: np.ndarray = np.array([0.0, 1.0])

    def fit(self, p: np.ndarray, y: np.ndarray) -> "IsotonicCalibrator":
        p = np.asarray(p, dtype=float)
        y = np.asarray(y, dtype=float)
        order = np.argsort(p, kind="mergesort")
        ps, ys = p[order], y[order]
        # blocks of pooled adjacent points: (sum_y, weight, x_min, x_max)
        blocks: list[list[float]] = []
        for xi, yi in zip(ps, ys):
            blocks.append([float(yi), 1.0, float(xi), float(xi)])
            while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
                b2 = blocks.pop()
                b1 = blocks.pop()
                blocks.append([b1[0] + b2[0], b1[1] + b2[1], b1[2], b2[3]])
        xs: list[float] = []
        vs: list[float] = []
        for s_, w_, x0, x1 in blocks:  # flat inside a block, linear between blocks
            xs.append(x0); vs.append(s_ / w_)
            if x1 > x0:
                xs.append(x1); vs.append(s_ / w_)
        self.x = np.array(xs)
        self.y = np.array(vs)
        if self.x.size == 1:
            self.x = np.array([self.x[0], self.x[0] + 1e-9])
            self.y = np.array([self.y[0], self.y[0]])
        return self

    def transform(self, p: np.ndarray) -> np.ndarray:
        return np.interp(np.asarray(p, dtype=float), self.x, self.y)


def cluster_bootstrap_scores(
    y: np.ndarray, p: np.ndarray, clusters: np.ndarray, *, n_bins: int = 10, n_boot: int = 300,
    level: float = 0.95, seed: int = 0,
) -> dict[str, tuple[float, float]]:
    """Percentile intervals for log loss, Brier and ECE, resampling whole clusters (e.g. episodes).

    Each cluster contributes additive sums, so a resample is a weighted sum; no per-draw refit.
    The interval reflects sampling variation of clusters, NOT of people when there are few people.
    """
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    uniq, inv = np.unique(clusters, return_inverse=True)
    c = uniq.size
    if c == 0:
        nan = (float("nan"), float("nan"))
        return {"log_loss": nan, "brier": nan, "ece": nan}
    pc = _clip(p)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    br = (p - y) ** 2
    bidx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    n_c = np.bincount(inv, minlength=c).astype(float)
    ll_c = np.bincount(inv, weights=ll, minlength=c)
    br_c = np.bincount(inv, weights=br, minlength=c)
    # per-cluster, per-bin sums
    flat = inv * n_bins + bidx
    cnt = np.bincount(flat, minlength=c * n_bins).reshape(c, n_bins).astype(float)
    sp = np.bincount(flat, weights=p, minlength=c * n_bins).reshape(c, n_bins)
    sy = np.bincount(flat, weights=y, minlength=c * n_bins).reshape(c, n_bins)
    rng = np.random.default_rng(seed)
    draws_ll, draws_br, draws_ece = [], [], []
    for _ in range(n_boot):
        pick = rng.integers(0, c, size=c)
        nn = n_c[pick].sum()
        draws_ll.append(ll_c[pick].sum() / nn)
        draws_br.append(br_c[pick].sum() / nn)
        cb, spb, syb = cnt[pick].sum(0), sp[pick].sum(0), sy[pick].sum(0)
        ok = cb > 0
        draws_ece.append(float(np.sum(np.abs(syb[ok] - spb[ok])) / cb.sum()))
    tail = (1 - level) / 2
    q = lambda d: (float(np.quantile(d, tail)), float(np.quantile(d, 1 - tail)))  # noqa: E731
    return {"log_loss": q(draws_ll), "brier": q(draws_br), "ece": q(draws_ece)}
