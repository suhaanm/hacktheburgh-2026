"""The error-probability model for review routing: logistic regression + Platt calibration on its own split."""
from __future__ import annotations

import numpy as np

from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust.calibration import IsotonicCalibrator, PlattScaler


class RoutingModel:
    """fit(train) learns the score; calibrate(cal) maps it to a probability. Platt scaling is monotone, so
    it changes probabilities but never the ORDER of cases, which keeps the risk-control guarantee (control.py)
    independent of how the calibration split was used. Isotonic is available but can create ties."""

    def __init__(self, columns: list[int] | None = None, l2: float = 2.0, calibrator: str = "platt") -> None:
        if calibrator not in ("platt", "isotonic", "none"):
            raise ValueError(calibrator)
        self.columns = columns
        self.l2 = l2
        self.calibrator_name = calibrator
        self._lr: LogisticModel | None = None
        self._cal: PlattScaler | IsotonicCalibrator | None = None

    def _sel(self, X: np.ndarray) -> np.ndarray:
        return X if self.columns is None else X[:, self.columns]

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RoutingModel":
        self._lr = LogisticModel(l2=self.l2).fit(self._sel(X), y)
        return self

    def raw(self, X: np.ndarray) -> np.ndarray:
        assert self._lr is not None, "fit first"
        return self._lr.predict_proba(self._sel(X))

    def calibrate(self, X: np.ndarray, y: np.ndarray) -> "RoutingModel":
        p = self.raw(X)
        if self.calibrator_name == "platt":
            self._cal = PlattScaler().fit(p, y)
        elif self.calibrator_name == "isotonic":
            self._cal = IsotonicCalibrator().fit(p, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        p = self.raw(X)
        return p if self._cal is None else self._cal.transform(p)
