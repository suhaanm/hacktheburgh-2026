"""The stuck-hazard model and its two baselines (ANA-5).

  full   logistic regression on hashed cog n-grams + dwell + repeats + reformulations + time since
         progress + role prior
  tsp    logistic regression on time since progress ONLY (the baseline to beat)
  base   a constant: the training base rate
"""
from __future__ import annotations

import numpy as np

from understudy_engine.hazard.features import BinTable, N_HASH, TSP_COLS
from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust.calibration import logit

VARIANTS = ("full", "tsp", "base")


class HazardModel:
    """Fit on a set of rows of a BinTable, predict on another set. Rows never leak across people."""

    def __init__(self, variant: str = "full", l2: float = 3.0) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")
        self.variant = variant
        self.l2 = l2
        self.base_rate_ = 0.5
        self.role_logit_: dict[str, float] = {}
        self._lr: LogisticModel | None = None

    # -- design matrices ---------------------------------------------------------------------
    def _design(self, tab: BinTable, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (X, standardize_mask)."""
        if self.variant == "tsp":
            X = tab.dense[rows][:, list(TSP_COLS)]
            return X, np.ones(X.shape[1], dtype=bool)
        role = np.array([self.role_logit_.get(r, logit(self.base_rate_)) for r in tab.role[rows]])
        X = np.hstack([tab.hashed[rows].astype(float), tab.dense[rows], role[:, None]])
        mask = np.zeros(X.shape[1], dtype=bool)
        mask[N_HASH:] = True  # z-score the dense columns and the role prior; hashed indicators stay raw
        return X, mask

    def fit(self, tab: BinTable, rows: np.ndarray) -> "HazardModel":
        y = tab.y[rows].astype(float)
        self.base_rate_ = float(np.clip(y.mean(), 1e-4, 1 - 1e-4)) if y.size else 0.5
        if self.variant == "base":
            return self
        # Role prior from the training rows only (a held-out person never leaks into it).
        self.role_logit_ = {}
        for r in np.unique(tab.role[rows]):
            m = tab.role[rows] == r
            self.role_logit_[str(r)] = float(logit(np.clip(y[m].mean(), 1e-4, 1 - 1e-4)))
        X, mask = self._design(tab, rows)
        self._lr = LogisticModel(l2=self.l2).fit(X, y, standardize=mask)
        return self

    def predict(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        if self.variant == "base":
            return np.full(len(rows), self.base_rate_)
        assert self._lr is not None, "fit first"
        X, _ = self._design(tab, rows)
        return self._lr.predict_proba(X)
