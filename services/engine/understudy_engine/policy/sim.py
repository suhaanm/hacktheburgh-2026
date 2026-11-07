"""A simulator with known ground truth for policy evaluation (ANA-7).

Contexts follow the shape of what the hazard model and the level engine produce (see context.py). The reward
model has a known, deliberately non-linear structure (the fitted linear reward model is therefore
misspecified), so the TRUE value of any target policy can be computed exactly:

    stuck ~ Bernoulli(p_stuck)                           (the hazard output is calibrated in the simulator)
    gain_a(x)   given stuck:  G * nudge   0.9 (0.25 + 0.75 mastery)
                              G * annotate 1.0 (1 - 0.35 mastery)
                              G * takeover 1.4 (1 - 0.7 risk)         (blocked-ish on risky steps), G = 2
    disruption  given not stuck: annotate / takeover -0.1
    cost_a(x) = interruption_cost_a * (1 + 1.5 (1 - since_prompt))      (prompting right after a prompt costs more)
    reliance(x) = 0.4 (1 - mastery) on takeover
    r = stuck*gain - (1-stuck)*disruption - cost - reliance + N(0, 0.25^2)

    q*(x, a) = p gain - (1 - p) disruption - cost - reliance        (exact, used for the true value)

The LOGGING policy is the epsilon-greedy online bandit (bandit.py), so the logged actions depend on the context.
That context dependence is what makes the naive averages biased.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from understudy_engine.policy.bandit import EPS, EpsGreedyBandit
from understudy_engine.policy.context import ANNOTATE, INTERRUPTION_COST, K, NUDGE, TAKEOVER
from understudy_engine.policy.context import RELIANCE_PENALTY_TAKEOVER

NOISE_SD = 0.25
GAIN_SCALE = 2.0   # progress events gained in the next two minutes when a stuck worker is helped well


def sample_contexts(n: int, rng: np.random.Generator) -> np.ndarray:
    p = rng.beta(1.3, 3.0, n)
    level = rng.choice([1, 2, 3, 4], size=n, p=[0.30, 0.30, 0.25, 0.15]).astype(float)
    mastery = np.clip(0.12 + 0.20 * (level - 1) + rng.normal(0, 0.10, n), 0.0, 1.0)
    consec = np.minimum(rng.poisson(4.0 * p ** 2), 4).astype(float)
    since = np.where(rng.random(n) < 0.4, 1.0, rng.random(n))
    risk = (rng.random(n) < 0.2).astype(float)
    return np.column_stack([p, level, since, consec, risk, mastery])


def _parts(X: np.ndarray):
    p, _lv, since, _c, risk, mastery = (X[:, i] for i in range(6))
    gain = np.zeros((X.shape[0], K))
    gain[:, NUDGE] = GAIN_SCALE * 0.9 * (0.25 + 0.75 * mastery)
    gain[:, ANNOTATE] = GAIN_SCALE * 1.0 * (1.0 - 0.35 * mastery)
    gain[:, TAKEOVER] = GAIN_SCALE * 1.4 * (1.0 - 0.7 * risk)
    disruption = np.zeros((X.shape[0], K))
    disruption[:, ANNOTATE] = 0.1
    disruption[:, TAKEOVER] = 0.1
    cost = np.array(INTERRUPTION_COST)[None, :] * (1.0 + 1.5 * (1.0 - since))[:, None]
    reliance = np.zeros((X.shape[0], K))
    reliance[:, TAKEOVER] = RELIANCE_PENALTY_TAKEOVER * (1.0 - mastery)
    return p, gain, disruption, cost, reliance


def true_q(X: np.ndarray) -> np.ndarray:
    """Exact expected reward q*(x, a), shape (n, K)."""
    p, gain, disr, cost, rel = _parts(np.atleast_2d(X))
    return p[:, None] * gain - (1 - p)[:, None] * disr - cost - rel


def sample_reward(x: np.ndarray, a: int, rng: np.random.Generator) -> float:
    p, gain, disr, cost, rel = _parts(x[None, :])
    stuck = rng.random() < p[0]
    base = (gain[0, a] if stuck else -disr[0, a]) - cost[0, a] - rel[0, a]
    return float(base + rng.normal(0, NOISE_SD))


def true_value(policy_probs: Callable[[np.ndarray], np.ndarray], n_mc: int = 200_000, seed: int = 12345) -> float:
    """Exact-in-expectation value of a policy: mean over fresh contexts of sum_a pi(a|x) q*(x, a)."""
    X = sample_contexts(n_mc, np.random.default_rng(seed))
    return float(np.mean((policy_probs(X) * true_q(X)).sum(1)))


def optimal_value(n_mc: int = 200_000, seed: int = 12345) -> float:
    X = sample_contexts(n_mc, np.random.default_rng(seed))
    return float(np.mean(true_q(X).max(1)))


def simulate_log(n: int, seed: int = 0, eps: float = EPS, snapshot_at: int | None = None):
    """Run the online epsilon-greedy bandit for n decisions in the simulator.

    Returns (X, a, r, p, greedy, bandit, snapshot) where `snapshot` is a copy of the bandit's reward model
    after `snapshot_at` decisions (default n // 2), usable as a target policy that did not see the later rows.
    """
    rng = np.random.default_rng(seed)
    X = sample_contexts(n, rng)
    bandit = EpsGreedyBandit(eps=eps, seed=seed + 1)
    snap_at = n // 2 if snapshot_at is None else snapshot_at
    a = np.zeros(n, int)
    p = np.zeros(n)
    r = np.zeros(n)
    g = np.zeros(n, int)
    snapshot = None
    for i in range(n):
        if i == snap_at:
            snapshot = EpsGreedyBandit(eps=eps, l2=bandit.l2, seed=seed)
            snapshot.theta = bandit.theta.copy()
        ai, pi, gi = bandit.act(X[i])
        ri = sample_reward(X[i], ai, rng)
        bandit.update(X[i], ai, ri)
        a[i], p[i], r[i], g[i] = ai, pi, ri, gi
    return X, a, r, p, g, bandit, snapshot
