"""Hazard cross-fit for the generator-mismatch matrix, from the hazard module's public pieces only.

Fit on X (``fit_rule``): the full, time-since-progress and base-rate models on all of X's bins; the alarm rule chosen from X's
leave-one-person-out out-of-fold predictions at the false-alarm budget. Test on Y (``apply_rule``): per-person held-out log
loss of the three models, and false alarms and detections of the transferred alarm rule. Per-person numbers are what the
person-cluster bootstrap resamples.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core import Episode
from ..hazard import HazardModel, build_bins, oof_predictions
from ..hazard.events import choose_config, score_rows
from ..trust.calibration import brier as _brier

VARIANTS = ("full", "tsp", "base")
BUDGET = 1.0
N_THR = 30
L2 = 3.0


@dataclass
class Rule:
    models: dict[str, HazardModel]
    cfg: dict
    n_people: int
    n_bins: int


def _pointwise(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(pc) + (1 - y) * np.log(1 - pc))


def fit_rule(eps_train: list[Episode], budget: float = BUDGET, n_thr: int = N_THR) -> Rule:
    tab, p_oof = oof_predictions(eps_train, variant="full", l2=L2)
    cfg = choose_config(tab, p_oof, list(range(len(tab.ep_person))), budget, n_thr=n_thr)
    rows = np.arange(tab.n)
    models = {v: HazardModel(v, L2).fit(tab, rows) for v in VARIANTS}
    return Rule(models, cfg, len(tab.people), tab.n)


def apply_rule(rule: Rule, eps_test: list[Episode]) -> dict[str, dict]:
    """Per-person held-out metrics. A person with no scored bin is omitted."""
    tab = build_bins(eps_test)
    if tab.n == 0:
        return {}
    rows = np.arange(tab.n)
    y = tab.y.astype(float)
    p = {v: rule.models[v].predict(tab, rows) for v in VARIANTS}
    ll = {v: _pointwise(y, p[v]) for v in VARIANTS}
    _res, per = score_rows(tab, p["full"], list(range(len(tab.ep_person))), rule.cfg["threshold"], confirm_bins=rule.cfg["confirm_bins"])
    out: dict[str, dict] = {}
    people = np.asarray(tab.person)
    for q in tab.people:
        m = people == q
        n = int(m.sum())
        d = {"n_bins": n, "y_rate": float(y[m].mean()),
             "ll_full": float(ll["full"][m].mean()), "ll_tsp": float(ll["tsp"][m].mean()), "ll_base": float(ll["base"][m].mean()),
             "brier_full": float(_brier(y[m], p["full"][m])), "fa": 0, "non_h": 0.0, "n_ev": 0, "det": 0, "hours": 0.0, "alarms": 0}
        for e, person in enumerate(tab.ep_person):
            if person != q:
                continue
            r = per[e]
            d["fa"] += r.false_alarms
            d["alarms"] += r.false_alarms + r.true_alarms
            d["non_h"] += r.non_event_h
            d["n_ev"] += r.n_events
            d["det"] += r.detected
            d["hours"] += r.total_h
        out[q] = d
    return out


def split_by_person(eps: list[Episode]) -> dict[str, list[Episode]]:
    by: dict[str, list[Episode]] = {}
    for e in eps:
        by.setdefault(e.person, []).append(e)
    return by


def lopo_cells(by_person: dict[str, list[Episode]]) -> dict[str, dict]:
    """Leave-one-person-out inside one small dataset (used for v1's four personas and for LOPO diagnostics)."""
    out: dict[str, dict] = {}
    for q in sorted(by_person):
        rest = [e for p, es in by_person.items() if p != q for e in es]
        rule = fit_rule(rest)
        out.update(apply_rule(rule, by_person[q]))
    return out
