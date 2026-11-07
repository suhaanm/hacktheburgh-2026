"""Genome deficit recovery under mismatch, from the genome module's public pieces only (``Cohort.nearest``, ``components``,
``deficit_prices``).

Fit on X = the reference experts and the detection thresholds ``X_d = max(1 s, 95th percentile of the seconds the procedure
attributes to deficit d when two of X's experts are compared)``. Test on Y = Y's novices aligned to X's nearest expert,
scored against Y's own truth. Truth (``PLAN.md`` section 4): a (case, deficit) pair is *present* when the deficit cost at
least 5 s, *absent* when it never occurred, *indeterminate* (excluded, counted) otherwise.
"""
from __future__ import annotations

import numpy as np

from ..genome import Cohort, components, deficit_prices

DEFICITS = ("skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter")
MIN_X = 1.0
MATERIAL_S = 5.0


def _attr(al) -> dict[str, float]:
    return deficit_prices(components(al))


def placebo_thresholds(co: Cohort) -> tuple[dict[str, float], dict[str, float]]:
    """(X_d, max placebo attribution) from the cohort's experts against their nearest other expert."""
    vals = {d: [] for d in DEFICITS}
    for ep in co.experts:
        try:
            _ref, al = co.nearest(ep)
        except ValueError:
            continue
        a = _attr(al)
        for d in DEFICITS:
            vals[d].append(abs(a.get(d, 0.0)))
    X = {d: max(MIN_X, float(np.quantile(v, 0.95))) if v else MIN_X for d, v in vals.items()}
    mx = {d: float(max(v)) if v else 0.0 for d, v in vals.items()}
    return X, mx


def truth_index(truth: dict) -> dict[str, dict[str, dict]]:
    """task_id -> {deficit: {price, material}} for the deficits that occurred."""
    out: dict[str, dict[str, dict]] = {}
    for t in truth["traces"]:
        out[t["task_id"]] = {d["type"]: {"price": float(d["price_s"]), "material": bool(d.get("material", d["price_s"] >= MATERIAL_S))}
                             for d in t["deficits"] if d["instances"] > 0}
    return out


def expert_contamination(co: Cohort, truth: dict) -> float:
    idx = truth_index(truth)
    ex = [e for e in co.experts if e.task_id in idx]
    if not ex:
        return float("nan")
    return float(np.mean([any(v["material"] for v in idx[e.task_id].values()) for e in ex]))


def score_cell(experts_X: Cohort, X_thr: dict[str, float], novices_Y: Cohort, truth_Y: dict) -> dict[str, dict]:
    """Per-novice tallies of Y scored with X's references and thresholds. Keys are persons."""
    eps = list(experts_X.experts) + list(novices_Y.novices)
    levels = {**{e.person: "expert" for e in experts_X.experts}, **{e.person: "novice" for e in novices_Y.novices}}
    co = Cohort(eps, levels, experts_X.cost)
    idx = truth_index(truth_Y)
    known = {t["task_id"] for t in truth_Y["traces"]}
    nd = len(DEFICITS)
    out: dict[str, dict] = {}
    for ep in co.novices:
        if ep.task_id not in known:
            continue
        _ref, al = co.nearest(ep)
        rec = _attr(al)
        inj = idx.get(ep.task_id, {})
        row = out.setdefault(ep.person, {"tp": np.zeros(nd), "fp": np.zeros(nd), "fn": np.zeros(nd), "tn": np.zeros(nd), "n_present": np.zeros(nd),
                                         "rec_present": np.zeros(nd), "inj_present": np.zeros(nd), "n_absent": np.zeros(nd), "attr_absent": np.zeros(nd),
                                         "n_indet": np.zeros(nd), "gap_s": 0.0, "cases": 0})
        row["cases"] += 1
        row["gap_s"] += al.gap_s
        for i, d in enumerate(DEFICITS):
            r = rec.get(d, 0.0)
            hit = r >= X_thr[d]
            if d in inj:
                if inj[d]["material"]:
                    row["n_present"][i] += 1
                    row["rec_present"][i] += r
                    row["inj_present"][i] += inj[d]["price"]
                    row["tp" if hit else "fn"][i] += 1
                else:
                    row["n_indet"][i] += 1
            else:
                row["n_absent"][i] += 1
                row["attr_absent"][i] += r
                row["fp" if hit else "tn"][i] += 1
    return out
