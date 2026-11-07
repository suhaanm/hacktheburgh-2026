"""Family C (alarm rules): v1's rule against the risk-controlled rules, on the same probabilities (PLAN.md section 6.4)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.hazard.features import BinTable
from understudy_engine.mlv2.alarms import Layout, build_layout
from understudy_engine.mlv2.conformal import BREAKS, STATED_GUARANTEE, make_c0_rule, make_c1_rule, make_c2_rule
from understudy_engine.mlv2.models import FAMILY_A, LEARNERS, VariantSpec
from understudy_engine.mlv2.protocol import DEFAULT_BUDGET, BaseOOF, VariantOutput, apply_variant, fit_base_oof, make_folds
from understudy_engine.mlv2.stats import (
    Clusters, adjusted_level, boot_multiplicities, event_draws, event_points, interval,
)

GUARD_DETECTION_MARGIN = -0.05      # lower end of (variant detection - C0 detection) must be at least this
RULE_IDS = ("C0", "C1", "C2")


@dataclass
class FamilyCRun:
    tab: BinTable
    outputs: dict[str, VariantOutput]
    prob_label: str


def run_family_c(tab: BinTable, base: BaseOOF, spec: VariantSpec, *, budget: float = DEFAULT_BUDGET, layout: Layout | None = None,
                 rules: tuple[str, ...] = RULE_IDS, n_boot_rule: int = 2000, prob_label: str = "A0", delta: float = 0.05) -> FamilyCRun:
    layout = layout or build_layout(tab)
    folds = make_folds(tab)
    makers = {"C0": make_c0_rule, "C1": lambda: make_c1_rule(delta), "C2": lambda: make_c2_rule(tab, n_boot=n_boot_rule)}
    outs = {r: apply_variant(tab, base, spec, layout=layout, budget=budget, rule=makers[r](), folds=folds) for r in rules}
    return FamilyCRun(tab, outs, prob_label)


def compare_family_c(run: FamilyCRun, *, ref: str = "C0", primary: str = "C1", n_boot: int = 4000, seed: int = 0,
                     budget: float = DEFAULT_BUDGET) -> dict:
    tab = run.tab
    cl = Clusters.from_labels(tab.person)
    M = boot_multiplicities(cl.C, n_boot, seed)
    draws = {r: event_draws(o.events, M, budget) for r, o in run.outputs.items()}
    pts = {r: event_points(o.events, budget) for r, o in run.outputs.items()}
    cand = [r for r in run.outputs if r != ref]
    m = len(cand)
    rows = {}
    for r, o in run.outputs.items():
        lvl = 0.95 if r in (primary, ref) else adjusted_level(m)
        deltas = {}
        for k in ("overshoot", "detection", "false_alarms_per_hour"):
            lo, hi = interval(draws[r][k] - draws[ref][k], lvl)
            deltas[k] = {"delta": pts[r][k] - pts[ref][k], "interval": [lo, hi], "level": lvl}
        fa_lo, fa_hi = interval(draws[r]["false_alarms_per_hour"], 0.95)
        det_lo, det_hi = interval(draws[r]["detection"], 0.95)
        guard_ok = deltas["detection"]["interval"][0] >= GUARD_DETECTION_MARGIN
        impr = deltas["overshoot"]["interval"][1] < 0
        verdict = "reference" if r == ref else ("accepted" if impr and guard_ok else ("harmful" if deltas["overshoot"]["interval"][0] > 0 else "null"))
        rows[r] = {
            "id": r, "level": lvl, "is_primary": r == primary,
            "false_alarms_per_hour": {"value": pts[r]["false_alarms_per_hour"], "interval": [fa_lo, fa_hi]},
            "detection": {"value": pts[r]["detection"], "interval": [det_lo, det_hi]},
            "overshoot": pts[r]["overshoot"],
            "budget_met": bool(pts[r]["false_alarms_per_hour"] <= budget),
            "budget_demonstrated": bool(fa_hi <= budget),
            "paired_vs_ref": deltas, "guard_detection_ok": bool(guard_ok), "verdict": verdict,
            "thresholds": [float(t) for t in o.events.thresholds], "confirm_bins": [int(c) for c in o.events.confirm_bins],
            "never_alarms_in_folds": int(sum(1 for t in o.events.thresholds if t > 1.0)),
            "train_budget_validated_folds": int(sum(o.events.budget_met_train)),
            "n_events": float(o.events.n_events.sum()), "non_event_hours": float(o.events.non_event_h.sum()),
        }
    return {"reference": ref, "primary": primary, "prob_model": run.prob_label, "n_people": cl.C, "budget_per_hour": budget,
            "n_boot": n_boot, "guarantee": STATED_GUARANTEE, "breaks": list(BREAKS),
            "per_person_fa_per_hour": {r: [(float(o.events.false_alarms[i] / o.events.non_event_h[i]) if o.events.non_event_h[i] > 0 else None)
                                           for i in range(cl.C)] for r, o in run.outputs.items()},
            "people": cl.names, "rows": rows}
