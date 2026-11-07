"""Family A (probability models): run the registered variants and decide against v1 (PLAN.md section 6.2).

``run_family_a`` fits the two base learners once per outer fold, applies each variant's calibrator or personal shift inside the fold, and
returns the variants' held-out predictions with per-person alarm counts. ``compare_family_a`` computes the paired differences against A0
on the same person-cluster resamples, the guard checks, and the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from understudy_engine.hazard.features import BinTable
from understudy_engine.mlv2.alarms import Layout, build_layout
from understudy_engine.mlv2.models import A7_CANDIDATES, BASELINE_SPECS, FAMILY_A, LEARNERS, VariantSpec
from understudy_engine.mlv2.protocol import (
    DEFAULT_BUDGET, BaseOOF, VariantOutput, apply_variant, fit_base_oof, make_folds,
)
from understudy_engine.mlv2.stats import (
    Clusters, adjusted_level, boot_multiplicities, event_draws, event_points, interval, metric_draws, metric_points, score_parts,
)

GUARDS = {  # non-inferiority margins (PLAN.md section 6.2): (metric, direction, margin)
    "brier": ("upper", 0.002),            # upper end of (variant - reference) must be <= margin
    "ece": ("upper", 0.01),
    "auc": ("lower", -0.01),              # lower end of (variant - reference) must be >= margin
    "detection": ("lower", -0.03),
}
PRIMARY_METRIC = "log_loss"
CONTROL_LL_TOL = 0.003


@dataclass
class FamilyARun:
    tab: BinTable
    layout: Layout
    outputs: dict[str, VariantOutput]
    bases: dict[str, BaseOOF]
    inner: str = ""


def run_family_a(tab: BinTable, *, variants: dict[str, VariantSpec] | None = None, include_baselines: bool = True,
                 inner_folds: int | None = None, budget: float = DEFAULT_BUDGET, include_a7: bool = True,
                 layout: Layout | None = None) -> FamilyARun:
    """Score A0..A6 (and both A7 candidates, unless ``include_a7`` is False) plus the TSP and base-rate baselines."""
    specs: dict[str, VariantSpec] = dict(variants or FAMILY_A)
    if variants is None and include_a7:
        specs.update(A7_CANDIDATES)
    if include_baselines:
        specs.update(BASELINE_SPECS)
    layout = layout or build_layout(tab)
    folds = make_folds(tab)
    keys = sorted({s.base for s in specs.values()})
    bases = {k: fit_base_oof(tab, LEARNERS[k], inner_folds=inner_folds, name=k, folds=folds) for k in keys}
    outputs = {vid: apply_variant(tab, bases[s.base], s, layout=layout, budget=budget, folds=folds) for vid, s in specs.items()}
    return FamilyARun(tab, layout, outputs, bases, next(iter(bases.values())).inner)


def _guard_checks(deltas: dict[str, dict]) -> dict[str, dict]:
    out = {}
    for g, (side, margin) in GUARDS.items():
        d = deltas.get(g)
        if d is None:
            continue
        lo, hi = d["interval"]
        ok = (hi <= margin) if side == "upper" else (lo >= margin)
        out[g] = {"ok": bool(ok), "side": side, "margin": margin, "bound": hi if side == "upper" else lo, "delta": d["delta"]}
    return out


def _point_guards_hold(deltas: dict[str, dict]) -> bool:
    for g, (side, margin) in GUARDS.items():
        d = deltas.get(g)
        if d is None:
            continue
        if side == "upper" and d["delta"] > margin:
            return False
        if side == "lower" and d["delta"] < margin:
            return False
    return True


def compare_family_a(run: FamilyARun, *, ref: str = "A0", primary: str | None = None, n_boot: int = 4000, seed: int = 0,
                     budget: float = DEFAULT_BUDGET, candidates: list[str] | None = None) -> dict:
    """Paired comparison of every variant against ``ref``. Intervals resample people. ``primary`` is tested at 95%; the other
    candidates at the Bonferroni-adjusted level with m = (number of non-primary candidates + 1)."""
    tab = run.tab
    cl = Clusters.from_labels(tab.person)
    M = boot_multiplicities(cl.C, n_boot, seed)
    y = tab.y.astype(float)
    parts = {vid: score_parts(y, o.p, cl) for vid, o in run.outputs.items()}
    draws = {vid: metric_draws(p, M) for vid, p in parts.items()}
    points = {vid: metric_points(p) for vid, p in parts.items()}
    ev_draws = {vid: event_draws(o.events, M, budget) for vid, o in run.outputs.items()}
    ev_points = {vid: event_points(o.events, budget) for vid, o in run.outputs.items()}
    cand = candidates or [v for v in run.outputs if v.startswith("A") and v != ref]
    m = len(cand)
    rows: dict[str, dict] = {}
    for vid, o in run.outputs.items():
        lvl = 0.95 if (vid == primary or vid == ref or vid not in cand) else adjusted_level(m)
        row = {
            "id": vid, "label": o.spec.label, "level": lvl, "is_primary": vid == primary,
            "metrics": {k: {"value": points[vid][k], "interval": list(interval(draws[vid][k], 0.95))} for k in points[vid]},
            "events": {k: {"value": ev_points[vid][k], "interval": list(interval(ev_draws[vid][k], 0.95))} for k in ev_points[vid]},
        }
        deltas: dict[str, dict] = {}
        for k in points[vid]:
            d = draws[vid][k] - draws[ref][k]
            lo, hi = interval(d, lvl)
            deltas[k] = {"delta": points[vid][k] - points[ref][k], "interval": [lo, hi], "level": lvl}
        for k in ("detection", "false_alarms_per_hour", "overshoot"):
            d = ev_draws[vid][k] - ev_draws[ref][k]
            lo, hi = interval(d, lvl)
            deltas[k] = {"delta": ev_points[vid][k] - ev_points[ref][k], "interval": [lo, hi], "level": lvl}
        row["paired_vs_ref"] = deltas
        row["guards"] = _guard_checks(deltas)
        pl = deltas[PRIMARY_METRIC]
        guards_ok = all(g["ok"] for g in row["guards"].values())
        if vid == ref:
            verdict = "reference"
        elif pl["interval"][1] < 0 and guards_ok:
            verdict = "accepted"
        elif pl["interval"][0] > 0:
            verdict = "harmful"
        else:
            verdict = "null"
        row["verdict"] = verdict
        row["primary_improves"] = bool(pl["interval"][1] < 0)
        row["guards_ok"] = bool(guards_ok)
        row["point_guards_hold"] = _point_guards_hold(deltas)
        rows[vid] = row
    return {"reference": ref, "primary": primary, "n_people": cl.C, "n_bins": int(tab.n), "n_boot": n_boot, "adjusted_level": adjusted_level(m),
            "m_candidates": m, "rows": rows, "inner": run.inner}


def choose_primary(dev_cmp: dict, candidates: list[str] | None = None) -> str | None:
    """PLAN.md section 6.2: the candidate with the lowest DEV log loss among those whose guards hold by point estimate; ties go to the
    simpler (lower id). Returns None when none qualifies (then v1 stays and no primary is declared)."""
    rows = dev_cmp["rows"]
    cand = candidates or [v for v in rows if v.startswith("A") and v != dev_cmp["reference"]]
    ok = [v for v in cand if rows[v]["point_guards_hold"] and rows[v]["metrics"]["log_loss"]["value"] < rows[dev_cmp["reference"]]["metrics"]["log_loss"]["value"]]
    if not ok:
        return None
    return sorted(ok, key=lambda v: (round(rows[v]["metrics"]["log_loss"]["value"], 6), v))[0]


def choose_a7(dev_cmp: dict) -> str:
    """A7 is the personal shift on top of the dev-better of A1 and A4: the one of ``A7_A1`` / ``A7_A4`` with the lower DEV log loss."""
    rows = dev_cmp["rows"]
    a = rows["A7_A1"]["metrics"]["log_loss"]["value"]
    b = rows["A7_A4"]["metrics"]["log_loss"]["value"]
    return "A7_A1" if a <= b else "A7_A4"
