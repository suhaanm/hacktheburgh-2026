"""Epsilon-greedy contextual bandit with logged propensities (ANA-6).

One ridge regression per action estimates the expected reward q(x, a). With probability `eps` (0.2) the bandit
picks an action uniformly at random, otherwise the greedy one. The probability of the action actually taken is
recorded at decision time:

    p(a | x) = (1 - eps) * 1[a == greedy(x)] + eps / K

That logged propensity is what makes off-policy evaluation of any other policy possible later (ope.py). The
bandit learns online, so its propensities change over time; each log row keeps the value used at that moment.

Deterministic given a seed. Ties go to the lowest action index (so cold start is silent).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from understudy_engine.policy.context import D, K

EPS = 0.2


@dataclass
class LoggedDecision:
    x: np.ndarray
    a: int
    p: float          # propensity of the logged action under the logging policy at that moment
    r: float
    greedy: int = -1  # the greedy action at that moment (diagnostics)


def feat(x: np.ndarray) -> np.ndarray:
    """Design row: bias plus the context columns, roughly scaled to [0, 1]."""
    x = np.asarray(x, dtype=float)
    scale = np.array([1.0, 3.0, 1.0, 4.0, 1.0, 1.0])
    off = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    return np.concatenate([[1.0], (x - off) / scale])


@dataclass
class EpsGreedyBandit:
    eps: float = EPS
    l2: float = 1.0
    seed: int = 0
    A: np.ndarray = field(default=None)  # type: ignore[assignment]
    b: np.ndarray = field(default=None)  # type: ignore[assignment]
    theta: np.ndarray = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        d = D + 1
        self.A = np.stack([self.l2 * np.eye(d) for _ in range(K)])
        self.b = np.zeros((K, d))
        self.theta = np.zeros((K, d))
        self._rng = np.random.default_rng(self.seed)

    def q(self, x: np.ndarray) -> np.ndarray:
        return self.theta @ feat(x)

    def greedy(self, x: np.ndarray) -> int:
        return int(np.argmax(self.q(x)))  # argmax returns the first maximum: ties -> lowest index

    def probs(self, x: np.ndarray) -> np.ndarray:
        p = np.full(K, self.eps / K)
        p[self.greedy(x)] += 1.0 - self.eps
        return p

    def act(self, x: np.ndarray) -> tuple[int, float, int]:
        """Returns (action, propensity of that action, greedy action)."""
        pr = self.probs(x)
        a = int(self._rng.choice(K, p=pr))
        return a, float(pr[a]), self.greedy(x)

    def update(self, x: np.ndarray, a: int, r: float) -> None:
        f = feat(x)
        self.A[a] += np.outer(f, f)
        self.b[a] += r * f
        self.theta[a] = np.linalg.solve(self.A[a], self.b[a])

    def policy_probs(self, X: np.ndarray) -> np.ndarray:
        """Greedy (eps = 0) policy as a (n, K) probability matrix: a target policy for OPE."""
        X = np.atleast_2d(X)
        P = np.zeros((X.shape[0], K))
        for i, row in enumerate(X):
            P[i, self.greedy(row)] = 1.0
        return P
