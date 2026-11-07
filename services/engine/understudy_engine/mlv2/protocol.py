"""The v1 leave-one-person-out protocol, generalised to many learners and post-hoc variants (PLAN.md section 4).

v1 (`hazard.evaluate._lopo_variant`): for each held-out person, (1) out-of-fold predictions on the training people (leave one person out
inside them), (2) pick the alarm configuration on those, (3) fit on all training people, predict the held-out person, apply the
configuration. This module does the same, but

  * fits each base learner once per fold and lets calibrators, the personal shift and alternative alarm rules be applied on top, so
    seven variants cost two learners' worth of fits;
  * uses grouped K-fold inner folds when the training set has more than ``loo_max`` people (a pool of 30 people would otherwise need
    about a thousand inner fits per learner); with at most ``loo_max`` training people it is leave-one-person-out exactly as in v1;
  * scores alarms with the vectorised, v1-identical code in ``alarms``.

``reproduces_v1`` checks the numbers against ``hazard.evaluate.evaluate_hazard`` (used by a test and by the harness on D0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from understudy_engine.hazard.features import BinTable
from understudy_engine.mlv2.alarms import Layout, build_layout, choose_config_fast, person_event_counts
from understudy_engine.mlv2.models import (
    LEARNERS, Calibrator, VariantSpec, apply_personal_shift, fit_beta_prior_people,
)
from understudy_engine.mlv2.stats import Clusters, EventCounts

LOO_MAX = 7
DEFAULT_BUDGET = 1.0


def inner_assignments(train_people: list[str], inner_folds: int | None, loo_max: int = LOO_MAX) -> list[list[str]]:
    """Groups of training people held out together in the inner loop: singletons (leave one person out, v1's protocol) when there
    are at most ``loo_max`` of them or ``inner_folds`` is None, otherwise ``inner_folds`` groups assigned round-robin over sorted ids."""
    people = sorted(train_people)
    if inner_folds is None or len(people) <= loo_max:
        return [[q] for q in people]
    k = max(2, min(inner_folds, len(people)))
    groups: list[list[str]] = [[] for _ in range(k)]
    for i, q in enumerate(people):
        groups[i % k].append(q)
    return groups


@dataclass
class BaseOOF:
    """One learner's predictions in every outer fold."""

    name: str
    p_out: np.ndarray                          # (n,) held-out person's rows, from the model trained on the other people
    p_in: dict[str, np.ndarray]                # held-out person -> (n,) inner out-of-fold predictions (NaN outside the training rows)
    inner: str = ""


@dataclass
class Fold:
    person: str
    rows: np.ndarray
    train_people: list[str]
    train_rows: np.ndarray
    train_eps: np.ndarray
    eps: np.ndarray


def make_folds(tab: BinTable, people: list[str] | None = None) -> list[Fold]:
    people = people or tab.people
    eps_of = {q: np.array([e for e, pp in enumerate(tab.ep_person) if pp == q], dtype=int) for q in tab.people}
    out = []
    for o in people:
        rest = [q for q in tab.people if q != o]
        out.append(Fold(o, tab.rows_of([o]), rest, tab.rows_of(rest),
                        np.concatenate([eps_of[q] for q in rest]) if rest else np.zeros(0, int), eps_of[o]))
    return out


def fit_base_oof(tab: BinTable, factory: Callable[[], object], *, inner_folds: int | None = None, name: str = "",
                 folds: list[Fold] | None = None, loo_max: int = LOO_MAX) -> BaseOOF:
    folds = folds or make_folds(tab)
    p_out = np.full(tab.n, np.nan)
    p_in: dict[str, np.ndarray] = {}
    inner = "leave-one-person-out within training people"
    for f in folds:
        pin = np.full(tab.n, np.nan)
        groups = inner_assignments(f.train_people, inner_folds, loo_max)
        if len(f.train_people) >= 2:
            for g in groups:
                tr = tab.rows_of([q for q in f.train_people if q not in g])
                te = tab.rows_of(g)
                pin[te] = factory().fit(tab, tr).predict(tab, te)
            if len(groups) < len(f.train_people):
                inner = f"grouped {len(groups)}-fold within training people"
        else:
            m = factory().fit(tab, f.train_rows)
            pin[f.train_rows] = m.predict(tab, f.train_rows)
            inner = "in-sample (only one training person)"
        p_in[f.person] = pin
        p_out[f.rows] = factory().fit(tab, f.train_rows).predict(tab, f.rows)
    return BaseOOF(name or getattr(factory(), "name", "?"), p_out, p_in, inner)


@dataclass
class VariantOutput:
    spec: VariantSpec
    p: np.ndarray                              # (n,) final held-out predictions
    events: EventCounts                        # one row per person, in ``people`` order
    people: list[str]
    configs: dict[str, dict] = field(default_factory=dict)
    inner: str = ""

    def person_index(self) -> Clusters:
        return Clusters(inv=np.zeros(0, int), names=self.people)


AlarmRule = Callable[[Layout, np.ndarray, np.ndarray, float, "Fold"], dict]


def v1_rule(layout: Layout, p_in: np.ndarray, train_eps: np.ndarray, budget: float, fold: "Fold") -> dict:
    return choose_config_fast(layout, p_in, train_eps, budget)


def apply_variant(tab: BinTable, base: BaseOOF, spec: VariantSpec, *, layout: Layout | None = None, budget: float = DEFAULT_BUDGET,
                  rule: AlarmRule = v1_rule, folds: list[Fold] | None = None) -> VariantOutput:
    """Calibrate and/or personalise the base learner's out-of-fold predictions inside each fold, choose the alarm rule on the training
    people only, and score the held-out person."""
    layout = layout or build_layout(tab)
    folds = folds or make_folds(tab)
    y = tab.y.astype(float)
    p_final = np.full(tab.n, np.nan)
    cols = {k: [] for k in ("n_events", "detected", "false_alarms", "true_alarms", "non_event_h", "total_h")}
    cfgs: dict[str, dict] = {}
    for f in folds:
        p_in = base.p_in[f.person].copy()
        p_out = base.p_out.copy()
        if spec.calib:
            cal = Calibrator(spec.calib).fit(p_in[f.train_rows], y[f.train_rows])
            p_in[f.train_rows] = cal.transform(p_in[f.train_rows])
            p_out[f.rows] = cal.transform(p_out[f.rows])
        if spec.shift:
            s = np.array([y[tab.rows_of([q])].sum() for q in f.train_people])
            n = np.array([float(tab.rows_of([q]).size) for q in f.train_people])
            prior = fit_beta_prior_people(s, n)
            for q in f.train_people:
                rq = tab.rows_of([q])
                p_in[rq] = apply_personal_shift(tab, p_in, rq, prior)
            p_out[f.rows] = apply_personal_shift(tab, p_out, f.rows, prior)
        p_final[f.rows] = p_out[f.rows]
        cfg = rule(layout, p_in, f.train_eps, budget, f)
        cfgs[f.person] = cfg
        cnt = person_event_counts(layout, p_final, cfg["threshold"], cfg["confirm_bins"], f.eps)
        for k in cols:
            cols[k].append(cnt[k])
    ev = EventCounts(**{k: np.array(v, dtype=float) for k, v in cols.items()},
                     thresholds=[cfgs[f.person]["threshold"] for f in folds],
                     confirm_bins=[cfgs[f.person]["confirm_bins"] for f in folds],
                     budget_met_train=[bool(cfgs[f.person].get("budget_met", False)) for f in folds])
    return VariantOutput(spec, p_final, ev, [f.person for f in folds], cfgs, base.inner)


def make_learner_factories(keys=("L", "G", "TSP", "BASE")) -> dict[str, Callable[[], object]]:
    return {k: LEARNERS[k] for k in keys}


def reproduces_v1(tab: BinTable, v1_result: dict, out: VariantOutput, *, tol: float = 1e-9) -> dict:
    """Compare an A0 run with ``hazard.evaluate.evaluate_hazard``'s dict for the same episodes (log loss, false alarms, detection)."""
    from understudy_engine.trust.calibration import log_loss

    y = tab.y.astype(float)
    ll = log_loss(y, out.p)
    fa = out.events.false_alarms.sum() / out.events.non_event_h.sum()
    det = out.events.detected.sum() / out.events.n_events.sum()
    ref = v1_result["model"]
    ref_ev = ref["events"]
    d = {
        "log_loss": (ll, ref["log_loss"]), "false_alarms_per_hour": (float(fa), ref_ev["false_alarms_per_hour"]),
        "detection": (float(det), ref_ev["detection_rate"]),
    }
    ok = all(abs(a - b) <= tol for a, b in d.values())
    return {"ok": bool(ok), "pairs": {k: {"mlv2": a, "v1": b} for k, (a, b) in d.items()}}
