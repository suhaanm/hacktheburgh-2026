"""Off-policy evaluation, hand-rolled (ANA-6): IPS, self-normalised IPS, direct method and doubly robust.

Given logs (x_i, a_i, r_i, p_i) where p_i = p(a_i | x_i) under the LOGGING policy at decision time, and a TARGET
policy pi (a matrix pi[i, a] = pi(a | x_i)), estimate the value V(pi) = E[ r under pi ] without running pi.

    w_i   = pi(a_i | x_i) / p_i                              importance weight
    IPS   = mean( w_i r_i )                                  unbiased if p is right; high variance
    SNIPS = sum( w_i r_i ) / sum( w_i )                      biased a little, much steadier
    DM    = mean( sum_a pi(a | x_i) q(x_i, a) )              direct method: only as good as q
    DR    = mean( sum_a pi(a | x_i) q(x_i, a) + w_i (r_i - q(x_i, a_i)) )
            for a deterministic pi this is  q(x, pi(x)) + 1[a = pi(x)] / p(a | x) * (r - q(x, a))
            unbiased if EITHER p is right OR q is right ("doubly robust")

q is a per-action ridge regression, cross-fitted (each row's q comes from a model that did not see that row).
Two naive numbers are reported on purpose, because they are what one gets without this machinery:
    naive_on_policy   mean of all logged rewards (that is the LOGGING policy's value, not pi's)
    naive_matched     mean reward over the rows where the logged action happened to equal pi's choice
                      (ignores that those rows are a context-biased subset)
Intervals: percentile bootstrap over decisions with q held fixed (it is already cross-fitted).
"""
from __future__ import annotations

import numpy as np

from understudy_engine.policy.bandit import feat
from understudy_engine.policy.context import K


def fit_reward_model(X: np.ndarray, a: np.ndarray, r: np.ndarray, *, l2: float = 1.0, folds: int = 2,
                     seed: int = 0) -> np.ndarray:
    """Cross-fitted q(x_i, k) for every row i and every action k. Returns an (n, K) matrix."""
    n = X.shape[0]
    F = np.vstack([feat(x) for x in X])
    rng = np.random.default_rng(seed)
    fold = rng.permutation(n) % folds
    Q = np.zeros((n, K))
    for f in range(folds):
        te = np.where(fold == f)[0]
        tr = np.where(fold != f)[0]
        for k in range(K):
            rows = tr[a[tr] == k]
            if rows.size < 5:
                Q[te, k] = float(r[rows].mean()) if rows.size else 0.0
                continue
            A = F[rows].T @ F[rows] + l2 * np.eye(F.shape[1])
            theta = np.linalg.solve(A, F[rows].T @ r[rows])
            Q[te, k] = F[te] @ theta
    return Q


def _weights(a: np.ndarray, p_log: np.ndarray, target: np.ndarray, clip: float | None) -> np.ndarray:
    w = target[np.arange(a.size), a] / p_log
    return w if clip is None else np.minimum(w, clip)


def point_estimates(a, r, p_log, target, Q, clip: float | None = None) -> dict[str, float]:
    n = a.size
    w = _weights(a, p_log, target, clip)
    dm_terms = (target * Q).sum(1)
    dr_terms = dm_terms + w * (r - Q[np.arange(n), a])
    greedy = np.argmax(target, axis=1)
    matched = a == greedy
    return {
        "ips": float(np.mean(w * r)),
        "snips": float(np.sum(w * r) / np.sum(w)) if np.sum(w) > 0 else float("nan"),
        "dm": float(np.mean(dm_terms)),
        "dr": float(np.mean(dr_terms)),
        "naive_on_policy": float(np.mean(r)),
        "naive_matched": float(np.mean(r[matched])) if matched.any() else float("nan"),
    }


def diagnostics(a, p_log, target, clip: float | None = None) -> dict[str, float]:
    w = _weights(a, p_log, target, clip)
    ess = float(w.sum() ** 2 / (w ** 2).sum()) if (w ** 2).sum() > 0 else 0.0
    return {"ess": ess, "ess_share": ess / a.size, "max_weight": float(w.max()),
            "match_rate": float(np.mean(a == np.argmax(target, axis=1))), "min_propensity": float(p_log.min())}


def bootstrap_estimates(a, r, p_log, target, Q, *, clip: float | None = None, n_boot: int = 500, seed: int = 0,
                        level: float = 0.95) -> dict[str, list[float]]:
    n = a.size
    rng = np.random.default_rng(seed)
    w = _weights(a, p_log, target, clip)
    wr = w * r
    dm_t = (target * Q).sum(1)
    dr_t = dm_t + w * (r - Q[np.arange(n), a])
    matched = (a == np.argmax(target, axis=1)).astype(float)
    idx = rng.integers(0, n, size=(n_boot, n))
    ips = wr[idx].mean(1)
    sw = w[idx].sum(1)
    snips = np.where(sw > 0, wr[idx].sum(1) / np.where(sw > 0, sw, 1.0), np.nan)
    dm = dm_t[idx].mean(1)
    dr = dr_t[idx].mean(1)
    on = r[idx].mean(1)
    m_cnt = matched[idx].sum(1)
    matched_mean = np.where(m_cnt > 0, (r * matched)[idx].sum(1) / np.where(m_cnt > 0, m_cnt, 1.0), np.nan)
    tail = (1 - level) / 2
    q = lambda d: [float(np.nanquantile(d, tail)), float(np.nanquantile(d, 1 - tail))]  # noqa: E731
    return {"ips": q(ips), "snips": q(snips), "dm": q(dm), "dr": q(dr), "naive_on_policy": q(on),
            "naive_matched": q(matched_mean)}


def evaluate_policy_value(X, a, r, p_log, target, *, clip: float | None = None, n_boot: int = 500, seed: int = 0,
                          l2: float = 1.0, folds: int = 2) -> dict:
    """Point estimates, intervals and diagnostics for one target policy."""
    X = np.asarray(X, float)
    a = np.asarray(a, int)
    r = np.asarray(r, float)
    p_log = np.asarray(p_log, float)
    Q = fit_reward_model(X, a, r, l2=l2, folds=folds, seed=seed)
    return {
        "estimates": point_estimates(a, r, p_log, target, Q, clip),
        "intervals": bootstrap_estimates(a, r, p_log, target, Q, clip=clip, n_boot=n_boot, seed=seed),
        "diagnostics": diagnostics(a, p_log, target, clip),
    }
