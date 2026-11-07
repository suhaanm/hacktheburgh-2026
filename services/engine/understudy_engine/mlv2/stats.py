"""Person-cluster bootstrap for paired comparisons (PLAN.md section 6: every interval resamples people, not episodes or bins).

A resample is a vector of multiplicities ``m`` over the C people (``M`` stacks B of them). Every statistic is written as a function of
per-person sufficient statistics, so a draw costs a matrix product, and two variants scored on the same bins are compared **on the same
draws** (a paired bootstrap). Metrics: log loss, Brier, ECE (v1's equal-width 10 bins), AUC (Mann-Whitney, ties half), false alarms an hour,
detection share and budget overshoot.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-12
N_ECE_BINS = 10


def adjusted_level(m: int, alpha: float = 0.05) -> float:
    """Bonferroni-adjusted two-sided interval level for m comparisons."""
    return 1.0 - alpha / max(1, int(m))


def interval(draws: np.ndarray, level: float = 0.95) -> tuple[float, float]:
    d = np.asarray(draws, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return (float("nan"), float("nan"))
    tail = (1.0 - level) / 2.0
    return (float(np.quantile(d, tail)), float(np.quantile(d, 1.0 - tail)))


@dataclass
class Clusters:
    """Person clusters of some per-bin (or per-episode) array."""

    inv: np.ndarray            # cluster index per row
    names: list[str]

    @classmethod
    def from_labels(cls, labels) -> "Clusters":
        uniq, inv = np.unique(np.asarray(labels, dtype=object).astype(str), return_inverse=True)
        return cls(inv=inv.astype(int), names=[str(u) for u in uniq])

    @property
    def C(self) -> int:
        return len(self.names)

    def sums(self, x: np.ndarray) -> np.ndarray:
        return np.bincount(self.inv, weights=np.asarray(x, dtype=float), minlength=self.C)

    def counts(self) -> np.ndarray:
        return np.bincount(self.inv, minlength=self.C).astype(float)


def boot_multiplicities(C: int, B: int, seed: int) -> np.ndarray:
    """(B, C) integer matrix: how many times each person appears in each bootstrap resample of people."""
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, C, size=(B, C))
    M = np.zeros((B, C), dtype=np.float64)
    rows = np.repeat(np.arange(B), C)
    np.add.at(M, (rows, picks.ravel()), 1.0)
    return M


def ratio_draws(num_c: np.ndarray, den_c: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Sum(num)/Sum(den) over resampled people; draws with an empty denominator are NaN."""
    n = M @ np.asarray(num_c, dtype=float)
    d = M @ np.asarray(den_c, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, n / d, np.nan)


def _clip(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)


@dataclass
class ScoreParts:
    """Per-person sufficient statistics of one prediction vector."""

    n_c: np.ndarray            # rows per person
    ll_c: np.ndarray           # summed log loss
    br_c: np.ndarray           # summed squared error
    cnt: np.ndarray            # (C, n_bins) rows per ECE bin
    sp: np.ndarray             # (C, n_bins) summed p
    sy: np.ndarray             # (C, n_bins) summed y
    W: np.ndarray              # (C, C) concordance of positives of a over negatives of b
    P: np.ndarray              # positives per person
    N: np.ndarray              # negatives per person


def auc_parts(score: np.ndarray, y: np.ndarray, cl: Clusters) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pairwise-cluster concordance counts so a cluster bootstrap of the AUC is a quadratic form."""
    score = np.asarray(score, dtype=float)
    y = np.asarray(y).astype(int)
    C = cl.C
    pos_idx = [np.where((cl.inv == c) & (y == 1))[0] for c in range(C)]
    neg_idx = [np.where((cl.inv == c) & (y == 0))[0] for c in range(C)]
    P = np.array([i.size for i in pos_idx], dtype=float)
    N = np.array([i.size for i in neg_idx], dtype=float)
    all_pos = np.concatenate(pos_idx) if pos_idx else np.zeros(0, int)
    pos_owner = np.repeat(np.arange(C), [i.size for i in pos_idx])
    W = np.zeros((C, C))
    spos = score[all_pos]
    for b in range(C):
        if neg_idx[b].size == 0 or spos.size == 0:
            continue
        sn = np.sort(score[neg_idx[b]])
        less = np.searchsorted(sn, spos, side="left")
        right = np.searchsorted(sn, spos, side="right")
        contrib = less + 0.5 * (right - less)
        W[:, b] = np.bincount(pos_owner, weights=contrib, minlength=C)
    return W, P, N


def score_parts(y: np.ndarray, p: np.ndarray, cl: Clusters, *, n_bins: int = N_ECE_BINS, with_auc: bool = True) -> ScoreParts:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    pc = _clip(p)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    br = (p - y) ** 2
    bidx = np.minimum((p * n_bins).astype(int), n_bins - 1)
    flat = cl.inv * n_bins + bidx
    size = cl.C * n_bins
    cnt = np.bincount(flat, minlength=size).reshape(cl.C, n_bins).astype(float)
    sp = np.bincount(flat, weights=p, minlength=size).reshape(cl.C, n_bins)
    sy = np.bincount(flat, weights=y, minlength=size).reshape(cl.C, n_bins)
    if with_auc:
        W, P, N = auc_parts(p, y, cl)
    else:
        W, P, N = np.zeros((cl.C, cl.C)), np.zeros(cl.C), np.zeros(cl.C)
    return ScoreParts(cl.counts(), cl.sums(ll), cl.sums(br), cnt, sp, sy, W, P, N)


def metric_draws(parts: ScoreParts, M: np.ndarray) -> dict[str, np.ndarray]:
    n = M @ parts.n_c
    ll = (M @ parts.ll_c) / n
    br = (M @ parts.br_c) / n
    cnt, sp, sy = M @ parts.cnt, M @ parts.sp, M @ parts.sy
    ece = np.abs(sy - sp).sum(axis=1) / cnt.sum(axis=1)
    out = {"log_loss": ll, "brier": br, "ece": ece}
    if parts.P.sum() > 0 and parts.N.sum() > 0:
        num = np.einsum("bi,ij,bj->b", M, parts.W, M)
        den = (M @ parts.P) * (M @ parts.N)
        with np.errstate(divide="ignore", invalid="ignore"):
            out["auc"] = np.where(den > 0, num / den, np.nan)
    return out


def metric_points(parts: ScoreParts) -> dict[str, float]:
    one = np.ones((1, parts.n_c.size))
    return {k: float(v[0]) for k, v in metric_draws(parts, one).items()}


@dataclass
class PairedResult:
    """A paired difference (variant minus reference) with its interval at the stated level."""

    metric: str
    point: float
    lo: float
    hi: float
    level: float
    ref: float
    variant: float
    n_people: int
    note: str = ""

    def as_dict(self) -> dict:
        return {"metric": self.metric, "delta": self.point, "interval": [self.lo, self.hi], "level": self.level,
                "reference": self.ref, "variant": self.variant, "n_people": self.n_people, "note": self.note}


def paired(metric: str, d_var: np.ndarray, d_ref: np.ndarray, p_var: float, p_ref: float, level: float, n_people: int) -> PairedResult:
    lo, hi = interval(np.asarray(d_var) - np.asarray(d_ref), level)
    return PairedResult(metric, p_var - p_ref, lo, hi, level, p_ref, p_var, n_people)


@dataclass
class EventCounts:
    """Per-person alarm counts of one rule (summing v1's EventResult over a person's episodes)."""

    n_events: np.ndarray
    detected: np.ndarray
    false_alarms: np.ndarray
    true_alarms: np.ndarray
    non_event_h: np.ndarray
    total_h: np.ndarray
    thresholds: list[float] = field(default_factory=list)
    confirm_bins: list[int] = field(default_factory=list)
    budget_met_train: list[bool] = field(default_factory=list)


def event_draws(ev: EventCounts, M: np.ndarray, budget: float) -> dict[str, np.ndarray]:
    fa_h = ratio_draws(ev.false_alarms, ev.non_event_h, M)
    det = ratio_draws(ev.detected, ev.n_events, M)
    return {"false_alarms_per_hour": fa_h, "detection": det, "overshoot": np.maximum(0.0, fa_h - budget)}


def event_points(ev: EventCounts, budget: float) -> dict[str, float]:
    one = np.ones((1, ev.n_events.size))
    return {k: float(v[0]) for k, v in event_draws(ev, one, budget).items()}


def mean_interval(values: np.ndarray, weights: np.ndarray | None, M: np.ndarray, level: float = 0.95) -> tuple[float, tuple[float, float]]:
    """Cluster-bootstrap interval of a (weighted) mean of per-person values."""
    v = np.asarray(values, dtype=float)
    w = np.ones_like(v) if weights is None else np.asarray(weights, dtype=float)
    draws = ratio_draws(v * w, w, M)
    return float((v * w).sum() / w.sum()), interval(draws, level)
