"""Proper scoring rules, calibration and the paired person-cluster bootstrap, for scoring a ledger.

Every score is lower-is-better except the calibration slope (1 is perfect). Probabilities are clipped to [CLIP, 1 - CLIP] before any score,
so one bin can cost at most ``-log(CLIP)`` = 4.6 nats; that bound is also what makes the guard's e-process valid (guard.py).

A resample is a vector of multiplicities over clusters (people). Every statistic here is a function of per-cluster sufficient statistics, so a
draw costs a matrix product and two predictors scored on the same bins are compared on the same draws (a paired bootstrap).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

CLIP = 0.01
B_LOSS = float(-np.log(CLIP))        # the largest possible per-bin loss difference
N_ECE_BINS = 10


def clip(p: np.ndarray | float) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), CLIP, 1.0 - CLIP)


def log_losses(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    pc = clip(p)
    y = np.asarray(y, dtype=float)
    return -(y * np.log(pc) + (1.0 - y) * np.log(1.0 - pc))


def brier_losses(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    return (clip(p) - np.asarray(y, dtype=float)) ** 2


def reliability_table(y: np.ndarray, p: np.ndarray, n_bins: int = N_ECE_BINS) -> list[dict[str, float]]:
    """Equal-width bins on [0, 1]; each non-empty bin has the mean forecast, the observed frequency, n and the Wilson 95% interval of the frequency."""
    y = np.asarray(y, dtype=float)
    pc = clip(p)
    idx = np.minimum((pc * n_bins).astype(int), n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        if n == 0:
            continue
        k, fr = float(y[m].sum()), float(y[m].mean())
        z = 1.959963984540054
        d = 1 + z * z / n
        c = (fr + z * z / (2 * n)) / d
        h = z * np.sqrt(fr * (1 - fr) / n + z * z / (4 * n * n)) / d
        out.append({"p_mean": float(pc[m].mean()), "freq": fr, "n": n, "lo": b / n_bins, "hi": (b + 1) / n_bins,
                    "freq_lo": float(max(0.0, c - h)), "freq_hi": float(min(1.0, c + h)), "ones": k})
    return out


def ece(y: np.ndarray, p: np.ndarray, n_bins: int = N_ECE_BINS) -> float:
    t = reliability_table(y, p, n_bins)
    n = sum(r["n"] for r in t)
    return float(sum(r["n"] * abs(r["freq"] - r["p_mean"]) for r in t) / n) if n else float("nan")


def _logit(p: np.ndarray) -> np.ndarray:
    pc = clip(p)
    return np.log(pc / (1.0 - pc))


def _nll(a: float, b: float, s: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    z = np.clip(a + b * s, -30.0, 30.0)
    return float(np.sum(w * (np.logaddexp(0.0, z) - y * z)))


def calibration_fit(y: np.ndarray, p: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float]:
    """(intercept a, slope b) of ``logit P(y = 1) = a + b logit(p)``: damped Newton with a backtracking line search on the (convex) weighted
    negative log likelihood, so it converges when the forecast is badly miscalibrated or even anti-informative (a negative slope is a real answer)."""
    s = _logit(p)
    y = np.asarray(y, dtype=float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, dtype=float)
    a, b = 0.0, 1.0
    cur = _nll(a, b, s, y, w)
    for _ in range(60):
        z = np.clip(a + b * s, -30, 30)
        q = 1.0 / (1.0 + np.exp(-z))
        r = w * (y - q)
        g = np.array([r.sum(), (r * s).sum()])
        v = w * q * (1.0 - q)
        H = np.array([[v.sum(), (v * s).sum()], [(v * s).sum(), (v * s * s).sum()]]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g)
        t = 1.0
        while t > 1e-6:
            na, nb = a + t * float(step[0]), b + t * float(step[1])
            new = _nll(na, nb, s, y, w)
            if new <= cur + 1e-12:
                break
            t *= 0.5
        else:
            break
        a, b, moved = na, nb, abs(cur - new)
        cur = new
        if moved < 1e-10 * max(1.0, abs(cur)):
            break
    return a, b


@dataclass
class Clusters:
    inv: np.ndarray
    names: list[str]

    @classmethod
    def from_labels(cls, labels: Any) -> "Clusters":
        uniq, inv = np.unique(np.asarray(labels, dtype=object).astype(str), return_inverse=True)
        return cls(inv=inv.astype(int), names=[str(u) for u in uniq])

    @property
    def C(self) -> int:
        return len(self.names)

    def sums(self, x: np.ndarray) -> np.ndarray:
        return np.bincount(self.inv, weights=np.asarray(x, dtype=float), minlength=self.C)

    def counts(self) -> np.ndarray:
        return np.bincount(self.inv, minlength=self.C).astype(float)


def multiplicities(C: int, B: int, seed: int) -> np.ndarray:
    """(B, C): how often each cluster appears in each bootstrap resample of clusters."""
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, C, size=(B, C))
    M = np.zeros((B, C))
    np.add.at(M, (np.repeat(np.arange(B), C), picks.ravel()), 1.0)
    return M


def interval(draws: np.ndarray, level: float = 0.95) -> list[float]:
    d = np.asarray(draws, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return [float("nan"), float("nan")]
    tail = (1.0 - level) / 2.0
    return [float(np.quantile(d, tail)), float(np.quantile(d, 1.0 - tail))]


def mean_draws(per_row: np.ndarray, cl: Clusters, M: np.ndarray) -> np.ndarray:
    """Mean of a per-row loss over resampled clusters."""
    return (M @ cl.sums(per_row)) / (M @ cl.counts())


def mean_with_interval(per_row: np.ndarray, cl: Clusters, M: np.ndarray, level: float = 0.95) -> dict[str, Any]:
    n = cl.counts()
    point = float(cl.sums(per_row).sum() / n.sum())
    return {"est": point, "ci": interval(mean_draws(per_row, cl, M), level)}


def paired_difference(loss_a: np.ndarray, loss_b: np.ndarray, cl: Clusters, M: np.ndarray, level: float = 0.95) -> dict[str, Any]:
    """Mean of (a minus b) over rows, with the cluster-bootstrap interval of the same resamples. Negative favours ``a``."""
    d = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    out = mean_with_interval(d, cl, M, level)
    lo, hi = out["ci"]
    out["verdict"] = "a better" if hi < 0 else "a worse" if lo > 0 else "no clear difference"
    return out


def calibration_with_interval(y: np.ndarray, p: np.ndarray, cl: Clusters, M: np.ndarray, level: float = 0.95, max_draws: int = 500) -> dict[str, Any]:
    """Intercept and slope with person-cluster bootstrap intervals (the first ``max_draws`` resamples; each is a weighted logistic fit)."""
    a0, b0 = calibration_fit(y, p)
    B = min(M.shape[0], max_draws)
    A, Bs = np.empty(B), np.empty(B)
    for i in range(B):
        w = M[i][cl.inv]
        a, b = calibration_fit(y, p, weights=w)
        A[i], Bs[i] = a, b
    ia, ib = interval(A, level), interval(Bs, level)
    return {"intercept": a0, "intercept_ci": ia, "slope": b0, "slope_ci": ib, "n_draws": B,
            "intercept_contains_0": bool(ia[0] <= 0.0 <= ia[1]), "slope_contains_1": bool(ib[0] <= 1.0 <= ib[1])}


def score_binary(y: np.ndarray, forecasts: dict[str, np.ndarray], streams: Any, *, primary: str, B: int = 2000, seed: int = 0, level: float = 0.95,
                 calibration_draws: int = 500) -> dict[str, Any]:
    """Log loss, Brier, ECE, reliability and calibration of each predictor, and the paired log-loss difference of ``primary`` against every other
    predictor, on the same person-cluster resamples."""
    cl = Clusters.from_labels(streams)
    M = multiplicities(cl.C, B, seed)
    y = np.asarray(y, dtype=float)
    ll = {k: log_losses(y, v) for k, v in forecasts.items()}
    out: dict[str, Any] = {"n": int(y.size), "n_clusters": cl.C, "base_rate": float(y.mean()), "bootstrap": {"B": B, "seed": seed, "level": level, "unit": "people"},
                           "predictors": {}, "paired_log_loss_vs": {}}
    for k, v in forecasts.items():
        out["predictors"][k] = {"log_loss": mean_with_interval(ll[k], cl, M, level), "brier": mean_with_interval(brier_losses(y, v), cl, M, level),
                                "ece": ece(y, v), "reliability": reliability_table(y, v)}
    out["predictors"][primary]["calibration"] = calibration_with_interval(y, forecasts[primary], cl, M, level, calibration_draws)
    for k in forecasts:
        if k != primary:
            out["paired_log_loss_vs"][k] = paired_difference(ll[primary], ll[k], cl, M, level)
    return out


def truncated_crps(cdf: np.ndarray, event_step: np.ndarray, steps_obs: np.ndarray, step_s: float) -> np.ndarray:
    """Per-origin truncated CRPS in seconds of a discrete CDF over steps 1..K. ``cdf[:, s-1]`` = P(progress by the end of step s).

    The observed indicator at step s is 1 if the event happened at a step <= s (``event_step`` > 0), else 0. An origin observed for only
    ``steps_obs`` steps contributes those steps and no more (censoring handled by truncation; nothing imputed). Result: squared CDF error
    averaged over the observed steps, times the step length."""
    cdf = np.asarray(cdf, dtype=float)
    n, K = cdf.shape
    steps = np.arange(1, K + 1)[None, :]
    ev = np.asarray(event_step)[:, None]
    obs = ((ev > 0) & (ev <= steps)).astype(float)
    mask = (steps <= np.asarray(steps_obs)[:, None]).astype(float)
    sq = (cdf - obs) ** 2 * mask
    denom = np.maximum(mask.sum(axis=1), 1.0)
    return sq.sum(axis=1) / denom * step_s
