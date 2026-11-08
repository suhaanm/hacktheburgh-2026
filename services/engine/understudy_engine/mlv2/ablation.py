"""M1: ablation harness for extra signals (PLAN.md section 6.1). A tool, not a decision.

``ablate`` reruns the leave-one-person-out protocol with and without a group of extra feature columns and reports the paired log-loss,
Brier, AUC, false-alarm and detection differences, each with a person-cluster bootstrap interval. Every group is accompanied by two controls
that can fail: a pure-noise column of the same width, and the same group **permuted within person** (a placebo that keeps each person's
marginal distribution and breaks its link to when they are stuck). A control passes when it shows no gain (an uninformative column costs a little, which is expected).

IMPORTANT (honesty): extra columns that come from our own synthetic generator (for example the awareness events planted around the planted
stuck spells) can only show that the pipeline uses a planted signal. A gain here is not evidence that real cursors predict being stuck.

Columns arrive from a *provider*: a callable ``provider(tab, episodes) -> {name: array of shape (n_bins,) or (n_bins, k)}`` aligned to the rows
of the bin table. ``stub_provider`` builds a planted-signal stub for the tests.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from understudy_engine.core import Episode
from understudy_engine.hazard.features import BinTable
from understudy_engine.mlv2.alarms import build_layout
from understudy_engine.mlv2.models import FAMILY_A, LEARNERS, LogitExtras
from understudy_engine.mlv2.protocol import DEFAULT_BUDGET, apply_variant, fit_base_oof, make_folds
from understudy_engine.mlv2.stats import (
    Clusters, boot_multiplicities, event_draws, event_points, interval, metric_draws, metric_points, score_parts,
)

ColumnProvider = Callable[[BinTable, list[Episode]], dict[str, np.ndarray]]


def stub_provider(strength: float = 1.0, seed: int = 0) -> ColumnProvider:
    """A stub with one informative group and one noise group. ``informative`` carries a noisy copy of the label (so a correct harness
    must report a gain), ``noise`` is independent of everything."""
    def provider(tab: BinTable, episodes: list[Episode]) -> dict[str, np.ndarray]:
        rng = np.random.default_rng(seed)
        y = tab.y.astype(float)
        informative = (strength * (y - y.mean()) + rng.normal(0, 1.0, tab.n))[:, None]
        noise = rng.normal(0, 1.0, (tab.n, 2))
        return {"informative": informative, "noise": noise}
    return provider


def permute_within_person(cols: np.ndarray, tab: BinTable, seed: int) -> np.ndarray:
    """The placebo: rows of the group shuffled among the bins of the same person."""
    rng = np.random.default_rng(seed)
    out = np.array(cols, dtype=float, copy=True)
    for q in tab.people:
        r = tab.rows_of([q])
        out[r] = cols[rng.permutation(r)]
    return out


def _run(tab, extras, folds, layout, inner_folds, budget):
    if extras is None:
        factory = LEARNERS["L"]
    else:
        factory = lambda: LogitExtras(extras)          # noqa: E731
    base = fit_base_oof(tab, factory, inner_folds=inner_folds, folds=folds)
    return apply_variant(tab, base, FAMILY_A["A0"], layout=layout, budget=budget, folds=folds)


def ablate(tab: BinTable, groups: dict[str, np.ndarray], *, inner_folds: int | None = None, budget: float = DEFAULT_BUDGET,
           n_boot: int = 2000, seed: int = 0, level: float = 0.95, controls: bool = True) -> dict:
    """Paired comparison of 'without' (v1's logistic) against 'with' each group, plus controls. Intervals resample people."""
    folds = make_folds(tab)
    layout = build_layout(tab)
    cl = Clusters.from_labels(tab.person)
    M = boot_multiplicities(cl.C, n_boot, seed)
    y = tab.y.astype(float)
    runs: dict[str, object] = {"without": _run(tab, None, folds, layout, inner_folds, budget)}
    labels: dict[str, str] = {}
    for g, cols in groups.items():
        cols = np.asarray(cols, dtype=float).reshape(tab.n, -1)
        runs[f"with:{g}"] = _run(tab, cols, folds, layout, inner_folds, budget)
        labels[f"with:{g}"] = "group"
        if controls:
            runs[f"placebo:{g}"] = _run(tab, permute_within_person(cols, tab, seed + 17), folds, layout, inner_folds, budget)
            labels[f"placebo:{g}"] = "placebo (permuted within person)"
    if controls:
        width = max(np.asarray(c).reshape(tab.n, -1).shape[1] for c in groups.values()) if groups else 1
        noise = np.random.default_rng(seed + 99).normal(0, 1.0, (tab.n, width))
        runs["control:noise"] = _run(tab, noise, folds, layout, inner_folds, budget)
        labels["control:noise"] = "pure-noise column"
    parts = {k: score_parts(y, o.p, cl) for k, o in runs.items()}
    dr = {k: metric_draws(p, M) for k, p in parts.items()}
    pt = {k: metric_points(p) for k, p in parts.items()}
    ed = {k: event_draws(o.events, M, budget) for k, o in runs.items()}
    ep = {k: event_points(o.events, budget) for k, o in runs.items()}
    rows = {}
    for k in runs:
        if k == "without":
            continue
        d = {}
        for m in ("log_loss", "brier", "auc"):
            lo, hi = interval(dr[k][m] - dr["without"][m], level)
            d[m] = {"delta": pt[k][m] - pt["without"][m], "interval": [lo, hi]}
        for m in ("false_alarms_per_hour", "detection"):
            lo, hi = interval(ed[k][m] - ed["without"][m], level)
            d[m] = {"delta": ep[k][m] - ep["without"][m], "interval": [lo, hi]}
        ll = d["log_loss"]["interval"]
        rows[k] = {
            "kind": labels[k], "paired_vs_without": d,
            "improves_log_loss": bool(ll[1] < 0), "interval_includes_zero": bool(ll[0] <= 0 <= ll[1]),
            "with": {m: pt[k][m] for m in pt[k]}, "events": ep[k],
        }
    # a control passes when it shows no GAIN (the interval's upper end is not below zero); an uninformative extra column costs a little
    # log loss (it adds a parameter), which a paired bootstrap on identical rows can detect, so "includes zero" would fail for a harmless reason
    controls_ok = all(not r["improves_log_loss"] for k, r in rows.items() if not k.startswith("with:")) if controls else None
    return {
        "n_people": cl.C, "n_bins": int(tab.n), "level": level, "n_boot": n_boot, "inner": runs["without"].inner,
        "without": {m: pt["without"][m] for m in pt["without"]}, "without_events": ep["without"],
        "rows": rows, "controls_ok": controls_ok,
        "note": "Extra columns from a generator show that the pipeline uses the planted signal, not that real signals predict stuck.",
    }
