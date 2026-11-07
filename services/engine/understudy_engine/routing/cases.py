"""A synthetic case generator for review routing (ANA-8), with a known error mechanism.

A case is one benefits entitlement check the agent has done and a worker has also looked at. The agent's answer
is WRONG (y = 1) or right (y = 0) against the oracle. The true error probability is a deliberately different
functional form from the fitted logistic regression (a threshold plus interactions), so the router is not
graded on a model of its own making:

    z = -3.4 + 2.3 * c + 1.5 * near_cliff * self_employed + 0.9 * scotland * disability + 0.5 * [income_sources >= 3]
    c = complexity in [0, 1] built from household size, income sources, housing and benefits in play
    P(wrong) = sigmoid(z)

Observable features (the router sees only these, never y):
    household complexity   n_adults, n_children, income_sources, self_employed, housing, disability, scotland,
                           benefits_in_play, near_cliff
    worker trace           log_worker_time_s, worker_retries, worker_backtracks
    worker-vs-agent        disagree (0 or the relative gap), agent_confidence (over-confident, noisy)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.trust.calibration import sigmoid

FEATURES = (
    "n_adults", "n_children", "income_sources", "self_employed", "housing", "disability", "scotland",
    "benefits_in_play", "near_cliff", "log_worker_time_s", "worker_retries", "worker_backtracks",
    "disagree", "agent_confidence",
)
COMPLEXITY_FEATURES = FEATURES[:9]
TRACE_FEATURES = FEATURES[9:12]
AGENT_FEATURES = FEATURES[12:]


@dataclass
class Cases:
    X: np.ndarray            # (n, len(features))
    y: np.ndarray            # 1 = the agent's answer is wrong
    p_true: np.ndarray | None = None   # the true error probability (known only for the pure generator)
    features: tuple[str, ...] = FEATURES
    origin: str = "synthetic"
    # optional, for case sets with a different feature layout (the sandbox households):
    groups: dict[str, tuple[str, ...]] | None = None        # feature groups for the ablation
    signals: dict[str, np.ndarray] | None = None            # single-signal rankings (higher = riskier) for baselines
    extra: dict | None = None                                # free-form diagnostics carried into the report

    @property
    def n(self) -> int:
        return int(self.y.size)

    def col(self, name: str) -> np.ndarray:
        return self.X[:, self.features.index(name)]


def simulate_cases(n: int = 4000, seed: int = 0) -> Cases:
    rng = np.random.default_rng(seed)
    n_adults = rng.choice([1, 2], n, p=[0.45, 0.55]).astype(float)
    n_children = np.minimum(rng.poisson(1.1, n), 5).astype(float)
    income_sources = np.minimum(1 + rng.poisson(0.7, n), 5).astype(float)
    self_emp = (rng.random(n) < 0.18).astype(float)
    housing = rng.choice([0, 1, 2], n, p=[0.15, 0.55, 0.30]).astype(float)
    disability = (rng.random(n) < 0.15).astype(float)
    scotland = (rng.random(n) < 0.09).astype(float)
    benefits = np.minimum(1 + rng.poisson(1.2, n) + (n_children > 0), 6).astype(float)
    near_cliff = (rng.random(n) < 0.12).astype(float)

    c = np.clip(0.10 * n_adults + 0.07 * n_children + 0.12 * (income_sources - 1) + 0.10 * (housing > 0)
                + 0.06 * (benefits - 1) + 0.10 * self_emp + 0.05 * disability + rng.normal(0, 0.05, n), 0.0, 1.0)
    z = (-3.4 + 2.3 * c + 1.5 * near_cliff * self_emp + 0.9 * scotland * disability
         + 0.5 * (income_sources >= 3))
    p_true = sigmoid(z)
    y = (rng.random(n) < p_true).astype(int)

    # worker trace: slower, more retries on complex or wrongly-handled cases (weakly: workers see the same case)
    time_s = np.exp(rng.normal(np.log(240) + 0.5 * c + 0.15 * y, 0.35))
    retries = rng.poisson(0.4 + 1.2 * c + 0.3 * y).astype(float)
    backtracks = rng.poisson(0.3 + 0.8 * c).astype(float)
    # disagreement: a wrong agent answer is often noticed; a right one is occasionally mis-challenged
    noticed = rng.random(n) < np.where(y == 1, 0.55, 0.10)
    disagree = np.where(noticed, np.clip(rng.lognormal(-1.0, 0.6, n), 0.02, 3.0), 0.0)
    conf = np.clip(0.93 - 0.10 * y - 0.12 * c + rng.normal(0, 0.09, n), 0.05, 0.999)
    X = np.column_stack([
        n_adults, n_children, income_sources, self_emp, housing, disability, scotland, benefits, near_cliff,
        np.log(time_s), retries, backtracks, disagree, conf,
    ])
    return Cases(X, y, p_true, groups={"complexity_only": COMPLEXITY_FEATURES, "worker_trace_only": TRACE_FEATURES,
                                       "agent_signals_only": AGENT_FEATURES, "all_features": FEATURES})


def split_indices(n: int, seed: int, fractions: tuple[float, float, float] = (0.5, 0.25, 0.25)):
    """Random train / calibration / held-out test split."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    a = int(round(fractions[0] * n))
    b = a + int(round(fractions[1] * n))
    return perm[:a], perm[a:b], perm[b:]
