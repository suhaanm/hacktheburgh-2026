"""Stuck-model learners and post-hoc transforms for v2 (PLAN.md section 6.2).

Learners share v1's interface ``fit(tab, rows)`` / ``predict(tab, rows)`` on a ``hazard.features.BinTable``:

  V1Logit      v1's L2 logistic (``hazard.model.HazardModel("full")``), the reference learner L
  GbmHazard    G: histogram gradient boosting with monotone constraints (increasing in dwell and in time since progress)
  TspLogit     v1's time-since-progress-only baseline;  BaseRate  the training base rate
  LogitExtras  v1's design plus extra columns (used by the ablation harness)

Transforms act on out-of-fold probabilities and are fitted **inside the training fold only** (the protocol hands them the training people's
inner out-of-fold predictions): Platt, isotonic, and the personal prior shift (A6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from understudy_engine.hazard.features import BinTable, N_HASH, TSP_COLS
from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.hazard.model import HazardModel
from understudy_engine.trust.calibration import IsotonicCalibrator, PlattScaler, logit, sigmoid

# --------------------------------------------------------------------------------------------- learners
GBM_PARAMS = dict(max_iter=120, learning_rate=0.05, max_leaf_nodes=6, min_samples_leaf=80, l2_regularization=2.0,
                  early_stopping=False, random_state=0)


class Learner(Protocol):
    def fit(self, tab: BinTable, rows: np.ndarray) -> "Learner": ...
    def predict(self, tab: BinTable, rows: np.ndarray) -> np.ndarray: ...


class V1Logit:
    """v1's logistic regression on hashed cog n-grams, dwell, repeats, reformulations, time since progress and the role prior."""

    name = "L"

    def __init__(self, l2: float = 3.0) -> None:
        self._m = HazardModel("full", l2)

    def fit(self, tab, rows):
        self._m.fit(tab, rows)
        return self

    def predict(self, tab, rows):
        return self._m.predict(tab, rows)


class TspLogit:
    name = "TSP"

    def __init__(self, l2: float = 3.0) -> None:
        self._m = HazardModel("tsp", l2)

    def fit(self, tab, rows):
        self._m.fit(tab, rows)
        return self

    def predict(self, tab, rows):
        return self._m.predict(tab, rows)


class BaseRate:
    name = "BASE"

    def __init__(self) -> None:
        self._m = HazardModel("base")

    def fit(self, tab, rows):
        self._m.fit(tab, rows)
        return self

    def predict(self, tab, rows):
        return self._m.predict(tab, rows)


def _role_prior(tab: BinTable, rows: np.ndarray, y: np.ndarray) -> tuple[float, dict[str, float]]:
    base = float(np.clip(y.mean(), 1e-4, 1 - 1e-4)) if y.size else 0.5
    roles: dict[str, float] = {}
    for r in np.unique(tab.role[rows]):
        m = tab.role[rows] == r
        roles[str(r)] = float(logit(np.clip(y[m].mean(), 1e-4, 1 - 1e-4)))
    return base, roles


def monotone_constraints(n_features: int) -> list[int]:
    """+1 (increasing) for log dwell (column N_HASH) and both time-since-progress columns; 0 elsewhere. Order: hashed, dense, role."""
    from understudy_engine.hazard.features import DENSE_NAMES

    cst = [0] * n_features
    cst[N_HASH + DENSE_NAMES.index("log_dwell")] = 1
    for c in TSP_COLS:
        cst[N_HASH + c] = 1
    return cst


class GbmHazard:
    """G: ``HistGradientBoostingClassifier`` on v1's features (hashed n-grams, dense columns, role prior)."""

    name = "G"

    def __init__(self, **overrides) -> None:
        self.params = {**GBM_PARAMS, **overrides}
        self._const: float | None = None
        self._m = None
        self._base = 0.5
        self._roles: dict[str, float] = {}

    def _design(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        role = np.array([self._roles.get(str(r), logit(self._base)) for r in tab.role[rows]])
        return np.hstack([tab.hashed[rows].astype(float), tab.dense[rows], role[:, None]])

    def fit(self, tab, rows):
        from sklearn.ensemble import HistGradientBoostingClassifier

        y = tab.y[rows].astype(int)
        self._base, self._roles = _role_prior(tab, rows, y.astype(float))
        if y.min() == y.max():
            self._const = float(np.clip(y.mean(), 1e-4, 1 - 1e-4))
            return self
        X = self._design(tab, rows)
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=4):     # 4 threads is the fastest on these table sizes; the fit is identical for any count
            self._m = HistGradientBoostingClassifier(monotonic_cst=monotone_constraints(X.shape[1]), **self.params).fit(X, y)
        return self

    def predict(self, tab, rows):
        if self._const is not None:
            return np.full(len(rows), self._const)
        assert self._m is not None, "fit first"
        return np.clip(self._m.predict_proba(self._design(tab, rows))[:, 1], 1e-6, 1 - 1e-6)


class LogitExtras:
    """v1's logistic design with extra feature columns appended (z-scored with training statistics). ``extras`` is (n_bins, k),
    aligned with the bin table; used by the ablation harness (M1). With no columns it equals ``V1Logit`` up to optimiser tolerance."""

    name = "L+extras"

    def __init__(self, extras: np.ndarray | None, l2: float = 3.0) -> None:
        self.extras = None if extras is None else np.asarray(extras, dtype=float).reshape(len(extras), -1)
        self.l2 = l2
        self._base = 0.5
        self._roles: dict[str, float] = {}
        self._lr: LogisticModel | None = None

    def _design(self, tab: BinTable, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        role = np.array([self._roles.get(str(r), logit(self._base)) for r in tab.role[rows]])
        parts = [tab.hashed[rows].astype(float), tab.dense[rows], role[:, None]]
        if self.extras is not None:
            parts.append(self.extras[rows])
        X = np.hstack(parts)
        mask = np.zeros(X.shape[1], dtype=bool)
        mask[N_HASH:] = True
        return X, mask

    def fit(self, tab, rows):
        y = tab.y[rows].astype(float)
        self._base, self._roles = _role_prior(tab, rows, y)
        X, mask = self._design(tab, rows)
        self._lr = LogisticModel(l2=self.l2).fit(X, y, standardize=mask)
        return self

    def predict(self, tab, rows):
        assert self._lr is not None, "fit first"
        X, _ = self._design(tab, rows)
        return self._lr.predict_proba(X)


LEARNERS = {"L": V1Logit, "G": GbmHazard, "TSP": TspLogit, "BASE": BaseRate}


# ----------------------------------------------------------------------------------------- transforms
class Calibrator:
    """Platt or isotonic, fitted on training people's inner out-of-fold predictions only."""

    def __init__(self, kind: str) -> None:
        if kind not in ("platt", "isotonic"):
            raise ValueError(kind)
        self.kind = kind
        self._m = PlattScaler() if kind == "platt" else IsotonicCalibrator()

    def fit(self, p: np.ndarray, y: np.ndarray) -> "Calibrator":
        self._m.fit(np.asarray(p, float), np.asarray(y, float))
        return self

    def transform(self, p: np.ndarray) -> np.ndarray:
        out = np.asarray(self._m.transform(np.asarray(p, float)), dtype=float)
        return np.clip(out, 1e-6, 1 - 1e-6)


def fit_beta_prior_people(s: np.ndarray, n: np.ndarray) -> tuple[float, float]:
    """v1's empirical-Bayes Beta prior (``hazard.pooling.fit_beta_prior``) over the training people's stuck-bin counts."""
    from understudy_engine.hazard.pooling import fit_beta_prior

    return fit_beta_prior(np.asarray(s, float), np.asarray(n, float))


def personal_shift_logits(prior: tuple[float, float], s_before: np.ndarray, n_before: np.ndarray) -> np.ndarray:
    """Logit shift for each episode of one person from their earlier episodes: logit((s + a) / (n + a + b)) - logit(a / (a + b)).
    No own history (n = 0) gives exactly zero. The reference rate is the prior mean, so the shift measures only what the person's own
    data add to the pooled rate."""
    a, b = prior
    est = (np.asarray(s_before, float) + a) / (np.asarray(n_before, float) + a + b)
    return logit(est) - logit(a / (a + b))


def apply_personal_shift(tab: BinTable, p: np.ndarray, rows_person: np.ndarray, prior: tuple[float, float]) -> np.ndarray:
    """Shift one person's predictions. ``rows_person`` are that person's rows in chronological episode order (episodes are contiguous and
    chronological per person). For each episode the estimate uses only the person's earlier episodes: their 60 s labels are known
    once an episode has ended, so this is computable online with no human annotation."""
    rows_person = np.asarray(rows_person, dtype=int)
    if rows_person.size == 0:
        return p[rows_person]
    ep = tab.episode[rows_person]
    # episodes in order of appearance
    change = np.r_[True, ep[1:] != ep[:-1]]
    first = np.where(change)[0]
    y = tab.y[rows_person].astype(float)
    ep_id = np.cumsum(change) - 1
    s_ep = np.bincount(ep_id, weights=y)
    n_ep = np.bincount(ep_id).astype(float)
    s_before = np.concatenate([[0.0], np.cumsum(s_ep)[:-1]])
    n_before = np.concatenate([[0.0], np.cumsum(n_ep)[:-1]])
    shift = personal_shift_logits(prior, s_before, n_before)
    out = sigmoid(logit(np.clip(p[rows_person], 1e-6, 1 - 1e-6)) + shift[ep_id])
    return np.clip(out, 1e-6, 1 - 1e-6)


# --------------------------------------------------------------------------------------------- registry
@dataclass(frozen=True)
class VariantSpec:
    id: str
    base: str                      # learner key in LEARNERS
    calib: str | None = None       # "platt" | "isotonic" | None
    shift: bool = False            # personal prior shift (A6)
    label: str = ""


FAMILY_A: dict[str, VariantSpec] = {
    "A0": VariantSpec("A0", "L", None, False, "v1 logistic (reference)"),
    "A1": VariantSpec("A1", "L", "platt", False, "logistic + Platt"),
    "A2": VariantSpec("A2", "L", "isotonic", False, "logistic + isotonic"),
    "A3": VariantSpec("A3", "G", None, False, "gradient boosting (monotone)"),
    "A4": VariantSpec("A4", "G", "platt", False, "gradient boosting + Platt"),
    "A5": VariantSpec("A5", "G", "isotonic", False, "gradient boosting + isotonic"),
    "A6": VariantSpec("A6", "L", None, True, "logistic + personal prior shift (partial pooling)"),
}
# A7 is the A6 shift on top of the dev-better of A1 and A4; both candidate bases are registered, one is picked on DEV.
A7_CANDIDATES: dict[str, VariantSpec] = {
    "A7_A1": VariantSpec("A7", "L", "platt", True, "A1 + personal prior shift"),
    "A7_A4": VariantSpec("A7", "G", "platt", True, "A4 + personal prior shift"),
}
BASELINE_SPECS: dict[str, VariantSpec] = {
    "TSP": VariantSpec("TSP", "TSP", None, False, "time since progress only"),
    "BASE": VariantSpec("BASE", "BASE", None, False, "training base rate"),
}
