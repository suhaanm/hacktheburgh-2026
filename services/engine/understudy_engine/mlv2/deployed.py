"""A deployable v2 stuck model with v1's interface (``fit(tab, rows)`` / ``predict(tab, rows)``), for the coach and the transfer test.

``make_hazard_model("v1")`` returns v1's ``HazardModel("full")``; ``make_hazard_model("v2")`` returns ``HazardModelV2``, the pre-registered primary
candidate (or any registered variant) with everything fitted on the training rows only: the base learner, the calibrator and the personal-shift
prior from inner out-of-fold predictions of the training people, and the alarm rule chosen on those inner predictions. v1 stays the default;
``variant="v2"`` is explicit and the result of the held-out test (accepted or not) is carried in ``pre_registered_verdict`` when it is known.
"""
from __future__ import annotations

import numpy as np

from understudy_engine.hazard.features import BinTable
from understudy_engine.hazard.model import HazardModel
from understudy_engine.mlv2.alarms import build_layout
from understudy_engine.mlv2.conformal import make_c0_rule, make_c1_rule
from understudy_engine.mlv2.models import A7_CANDIDATES, FAMILY_A, LEARNERS, Calibrator, VariantSpec, apply_personal_shift, fit_beta_prior_people
from understudy_engine.mlv2.protocol import DEFAULT_BUDGET, inner_assignments

DEFAULT_V2 = "A7_A4"          # the registry id of the DEV-picked primary candidate when none has been frozen (see results/frozen.json)


def spec_by_id(vid: str) -> VariantSpec:
    if vid in FAMILY_A:
        return FAMILY_A[vid]
    if vid in A7_CANDIDATES:
        return A7_CANDIDATES[vid]
    raise KeyError(vid)


class HazardModelV2:
    """Fit on a set of rows of a BinTable (people stay together), predict on another set. Rows of each person must be in chronological order
    (the bin table's native order) because the personal shift uses only a person's earlier episodes."""

    def __init__(self, spec: VariantSpec | str = DEFAULT_V2, *, inner_folds: int | None = 5, budget: float = DEFAULT_BUDGET, alarm: str = "C0") -> None:
        self.spec = spec_by_id(spec) if isinstance(spec, str) else spec
        self.inner_folds, self.budget, self.alarm = inner_folds, budget, alarm
        self.pre_registered_verdict: str | None = None      # "accepted" | "null" | "harmful" once the held-out result is attached
        self._base = None
        self._cal: Calibrator | None = None
        self._prior: tuple[float, float] | None = None
        self.alarm_config: dict | None = None

    def _transform_person(self, tab: BinTable, p: np.ndarray, rows_person: np.ndarray) -> np.ndarray:
        q = p.copy()
        if self._cal is not None:
            q[rows_person] = self._cal.transform(q[rows_person])
        if self._prior is not None:
            q[rows_person] = apply_personal_shift(tab, q, rows_person, self._prior)
        return q[rows_person]

    def fit(self, tab: BinTable, rows: np.ndarray) -> "HazardModelV2":
        rows = np.sort(np.asarray(rows, dtype=int))
        people = sorted(set(tab.person[rows].tolist()))
        factory = LEARNERS[self.spec.base]
        y = tab.y.astype(float)
        p_in = np.full(tab.n, np.nan)
        if len(people) >= 2:
            for g in inner_assignments(people, self.inner_folds):
                tr = rows[~np.isin(tab.person[rows], g)]
                te = rows[np.isin(tab.person[rows], g)]
                p_in[te] = factory().fit(tab, tr).predict(tab, te)
        else:
            p_in[rows] = factory().fit(tab, rows).predict(tab, rows)
        self._base = factory().fit(tab, rows)
        self._cal = Calibrator(self.spec.calib).fit(p_in[rows], y[rows]) if self.spec.calib else None
        if self._cal is not None:
            p_in[rows] = self._cal.transform(p_in[rows])
        if self.spec.shift:
            s = np.array([y[rows[tab.person[rows] == q]].sum() for q in people])
            n = np.array([float((tab.person[rows] == q).sum()) for q in people])
            self._prior = fit_beta_prior_people(s, n)
            for q in people:
                rq = rows[tab.person[rows] == q]
                p_in[rq] = apply_personal_shift(tab, p_in, rq, self._prior)
        layout = build_layout(tab)
        eps = np.unique(tab.episode[rows])
        rule = make_c1_rule() if self.alarm == "C1" else make_c0_rule()
        self.alarm_config = rule(layout, p_in, eps, self.budget, None)
        return self

    def predict(self, tab: BinTable, rows: np.ndarray) -> np.ndarray:
        assert self._base is not None, "fit first"
        rows = np.asarray(rows, dtype=int)
        order = np.argsort(rows, kind="stable")
        r = rows[order]
        p = np.full(tab.n, np.nan)
        p[r] = self._base.predict(tab, r)
        out = np.empty(r.size)
        for q in sorted(set(tab.person[r].tolist())):
            m = tab.person[r] == q
            out[m] = self._transform_person(tab, p, r[m])
        res = np.empty(rows.size)
        res[order] = out
        return res


def make_hazard_model(variant: str = "v1", **kw):
    """v1 (default) or v2. ``variant`` is explicit: nothing switches to v2 on its own."""
    if variant == "v1":
        return HazardModel("full", kw.get("l2", 3.0))
    if variant == "v2":
        return HazardModelV2(**kw)
    raise ValueError(f"variant must be 'v1' or 'v2', got {variant!r}")
