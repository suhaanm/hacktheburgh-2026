"""L2-regularised logistic regression, hand-rolled on numpy and fitted with L-BFGS.

Deterministic (convex objective, fixed start). Columns flagged in `standardize` are z-scored with
training statistics; the rest (e.g. hashed indicator columns) are used as they are.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from understudy_engine.trust.calibration import EPS, sigmoid


@dataclass
class LogisticModel:
    l2: float = 1.0                      # penalty strength on the SUMMED loss (bias is not penalised)
    max_iter: int = 200
    coef_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    bias_: float = 0.0
    mean_: np.ndarray = field(default_factory=lambda: np.zeros(0))
    scale_: np.ndarray = field(default_factory=lambda: np.ones(0))

    def fit(
        self, X: np.ndarray, y: np.ndarray, *, standardize: np.ndarray | None = None,
        sample_weight: np.ndarray | None = None,
    ) -> "LogisticModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        n, d = X.shape
        self.mean_ = np.zeros(d)
        self.scale_ = np.ones(d)
        if standardize is None:
            standardize = np.ones(d, dtype=bool)
        std_idx = np.where(np.asarray(standardize, dtype=bool))[0]
        if std_idx.size:
            self.mean_[std_idx] = X[:, std_idx].mean(0)
            s = X[:, std_idx].std(0)
            self.scale_[std_idx] = np.where(s > 1e-9, s, 1.0)
        Z = (X - self.mean_) / self.scale_
        w8 = np.ones(n) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        wsum = w8.sum()
        lam = self.l2

        def obj(theta: np.ndarray) -> tuple[float, np.ndarray]:
            w, b = theta[:d], theta[d]
            z = Z @ w + b
            q = sigmoid(z)
            qc = np.clip(q, EPS, 1 - EPS)
            loss = -np.sum(w8 * (y * np.log(qc) + (1 - y) * np.log(1 - qc))) + 0.5 * lam * float(w @ w)
            r = w8 * (q - y)
            g = np.empty(d + 1)
            g[:d] = Z.T @ r + lam * w
            g[d] = r.sum()
            return loss / wsum, g / wsum

        # Start the bias at the base-rate log odds so rare-event problems converge quickly.
        base = float(np.clip((w8 * y).sum() / wsum, 1e-6, 1 - 1e-6))
        theta0 = np.zeros(d + 1)
        theta0[d] = np.log(base / (1 - base))
        res = minimize(obj, theta0, jac=True, method="L-BFGS-B", options={"maxiter": self.max_iter})
        self.coef_ = res.x[:d]
        self.bias_ = float(res.x[d])
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - self.mean_) / self.scale_
        return Z @ self.coef_ + self.bias_

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return sigmoid(self.decision_function(X))
