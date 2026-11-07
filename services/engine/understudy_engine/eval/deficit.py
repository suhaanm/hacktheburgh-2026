"""EVL-1 and ANA-2/3: which deficit was injected, what it costs, and the two controls.

Data: ``data/synthetic/apprentices`` (8 experts, 16 novices, 2 cases each) and its ``truth.json``. Every novice trace
has some of five planted deficits; the price of each (seconds added minus seconds removed, against the same trace
without it) is exact by construction.

Method, all from engine-data's genome code:
- each novice case is aligned to its **nearest expert** (never the same person) and priced in seconds; the alignment
  columns are named by ``genome.labels`` and the ones that point at a planted deficit are summed into
  ``recovered`` seconds for that deficit;
- **recovered price** for a deficit is the mean recovered seconds over the traces that really have it; the interval is a
  **cluster bootstrap by person** (resample the 16 novices, pool their traces);
- a deficit is **detected** on a trace when the recovered seconds reach X, where
  ``X[d] = max(1 s, 95th percentile of the seconds the same procedure attributes to d when two experts are compared)``
  (the placebo: nothing is wrong, so anything above X is rarer than 1 in 20 by chance, and below one second is noise);
- **precision** = detected and present / detected; **recall** = detected and present / present, over every
  (trace, deficit) pair, with cluster-bootstrap intervals;
- controls: ``placebo`` (expert against nearest other expert) and the shuffled-label ``null`` (labels permuted across
  people, whole procedure repeated) should sit near zero while the real gap does not.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..genome import GenomeError, GenomeService, components, deficit_prices
from ..genome.service import TASK
from ..store import EventStore
from .meta import make_meta
from .stats import (
    boot_indices,
    cluster_mean_interval,
    interval,
    rnd,
)

MIN_X_S = 1.0           # a detection threshold is never below one second
X_QUANTILE = 0.95       # of the placebo attribution
SEED = 20261107

DEFICIT_LABEL = {
    "skipped_check_cliff": "Skips the cliff check",
    "repeated_read_result": "Reads the result again and again",
    "search_loop": "Searches in loops",
    "copy_error": "Copies the wrong figure",
    "idle_before_enter": "Freezes before entering the household",
}
DEFICIT_ORDER = ("skipped_check_cliff", "repeated_read_result", "search_loop", "copy_error", "idle_before_enter")


@dataclass
class Settings:
    B: int            # bootstrap resamples
    B_null: int       # label permutations

    @classmethod
    def for_mode(cls, fast: bool) -> Settings:
        return cls(B=300, B_null=150) if fast else cls(B=2000, B_null=1000)


@dataclass
class Result:
    deficit_recovery: dict[str, Any]
    null_placebo: dict[str, Any]


def load_bundle(root: Path | str | None):
    svc = GenomeService(EventStore(root))
    try:
        return svc.bundle(TASK, "synthetic")
    except GenomeError as e:
        raise FileNotFoundError(f"{e.message} (run `uv run --package understudy-engine understudy synth --all`)") from e


def _attribution(al) -> dict[str, float]:
    return deficit_prices(components(al))


def compute(root: Path | str | None = None, *, fast: bool = False, seed: int = SEED) -> Result:
    b = load_bundle(root)
    assert b.truth is not None
    return compute_from(b.cohort, b.truth, fast=fast, seed=seed)


def compute_from(co, truth: dict[str, Any], *, fast: bool = False, seed: int = SEED) -> Result:
    """The two sections from a cohort and a truth dict (``traces[].deficits[]`` and ``deficit_types``). Pure and seeded."""
    cfg = Settings.for_mode(fast)
    deficits = [d for d in DEFICIT_ORDER if d in truth["deficit_types"]] + [d for d in sorted(truth["deficit_types"]) if d not in DEFICIT_ORDER]
    truth_by_task = {t["task_id"]: t for t in truth["traces"]}

    # --- novices against their nearest expert -------------------------------------------------------------------
    novice_rows = []     # (person, task_id, injected {d: price}, recovered {d: s}, gap_s)
    for ep, _ref, al in co.novice_alignments("nearest_expert"):
        inj = {x["type"]: float(x["price_s"]) for x in truth_by_task[ep.task_id]["deficits"] if x["instances"] > 0}
        rec = _attribution(al)
        novice_rows.append((ep.person, ep.task_id, inj, rec, al.gap_s))
    # --- placebo: every expert case against its nearest other expert ---------------------------------------------
    placebo_attr: dict[str, list[float]] = {d: [] for d in deficits}   # absolute seconds attributed to d, per expert case
    placebo_gap: dict[str, list[float]] = defaultdict(list)
    for ep in co.experts:
        _ref, al = co.nearest(ep)
        rec = _attribution(al)
        for d in deficits:
            placebo_attr[d].append(abs(rec.get(d, 0.0)))
        placebo_gap[ep.person].append(al.gap_s)
    X = {d: max(MIN_X_S, float(np.quantile(placebo_attr[d], X_QUANTILE))) for d in deficits}
    placebo_max = {d: float(max(placebo_attr[d], default=0.0)) for d in deficits}
    floor_only = all(x == MIN_X_S for x in X.values())

    people = sorted({r[0] for r in novice_rows})
    pidx = {p: i for i, p in enumerate(people)}
    P = len(people)

    def per_person(fn) -> np.ndarray:
        out = np.zeros(P)
        for row in novice_rows:
            out[pidx[row[0]]] += fn(row)
        return out

    idx = boot_indices(P, cfg.B, seed)

    def ratio(num: np.ndarray, den: np.ndarray):
        n_, d_ = num[idx].sum(axis=1), den[idx].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(d_ > 0, n_ / d_, np.nan)

    rows = []
    tot = {"tp": np.zeros(P), "fp": np.zeros(P), "fn": np.zeros(P)}
    for d in deficits:
        x = X[d]
        present = lambda r, d=d: 1.0 if d in r[2] else 0.0
        absent = lambda r, d=d: 0.0 if d in r[2] else 1.0
        hit = lambda r, d=d, x=x: 1.0 if r[3].get(d, 0.0) >= x else 0.0
        cnt_pres = per_person(present)
        inj_sum = per_person(lambda r, d=d: r[2].get(d, 0.0))
        rec_sum = per_person(lambda r, d=d: r[3].get(d, 0.0) if d in r[2] else 0.0)
        tp = per_person(lambda r: present(r) * hit(r))
        fp = per_person(lambda r: absent(r) * hit(r))
        fn = per_person(lambda r: present(r) * (1 - hit(r)))
        n_pres = int(cnt_pres.sum())
        n_abs = len(novice_rows) - n_pres
        inj_mean = inj_sum.sum() / n_pres if n_pres else float("nan")
        rec_mean = rec_sum.sum() / n_pres if n_pres else float("nan")
        rec_absent = per_person(lambda r, d=d: r[3].get(d, 0.0) if d not in r[2] else 0.0)
        for k, arr in (("tp", tp), ("fp", fp), ("fn", fn)):
            tot[k] += arr
        prec = tp.sum() / (tp.sum() + fp.sum()) if (tp.sum() + fp.sum()) > 0 else float("nan")
        rec_ = tp.sum() / (tp.sum() + fn.sum()) if (tp.sum() + fn.sum()) > 0 else float("nan")
        rows.append({
            "deficit": d,
            "label": DEFICIT_LABEL.get(d, d),
            "injected_price_s": rnd(inj_mean, 2),
            "recovered_price_s": rnd(rec_mean, 2),
            "ci": interval(ratio(rec_sum, cnt_pres), nd=2),
            "bias_s": rnd(rec_mean - inj_mean, 2),
            "bias_ci": interval(ratio(rec_sum - inj_sum, cnt_pres), nd=2),
            "precision": rnd(prec),
            "precision_ci": interval(ratio(tp, tp + fp)),
            "recall": rnd(rec_),
            "recall_ci": interval(ratio(tp, tp + fn)),
            "threshold_s": rnd(x, 2), "placebo_max_s": rnd(placebo_max[d], 2),
            "n_present": n_pres, "n_absent": n_abs,
            "tp": int(tp.sum()), "fp": int(fp.sum()), "fn": int(fn.sum()),
            "false_attribution_s": rnd(rec_absent.sum() / n_abs if n_abs else float("nan"), 2),
            # the dashboard fixture's names for the same two numbers
            "true_s": rnd(inj_mean, 2), "est_s": rnd(rec_mean, 2),
        })
    TP, FP, FN = tot["tp"].sum(), tot["fp"].sum(), tot["fn"].sum()
    overall = {
        "precision": rnd(TP / (TP + FP) if TP + FP > 0 else float("nan")),
        "precision_ci": interval(ratio(tot["tp"], tot["tp"] + tot["fp"])),
        "recall": rnd(TP / (TP + FN) if TP + FN > 0 else float("nan")),
        "recall_ci": interval(ratio(tot["tp"], tot["tp"] + tot["fn"])),
        "tp": int(TP), "fp": int(FP), "fn": int(FN), "pairs": len(novice_rows) * len(deficits),
    }
    n_traces = len(novice_rows)
    dr_meta = make_meta(
        "synthetic", P, "people",
        f"{len(deficits)} planted deficits over {n_traces} novice cases ({P} novices vs {len({e.person for e in co.experts})} experts); "
        f"cluster bootstrap by person, B = {cfg.B}",
        note=("Which deficit was injected, and what it costs. Detected = the alignment attributes at least X seconds to the right "
              "cog family, X = max(1 s, 95th percentile of what the same procedure attributes when two experts are compared). "
              + (f"In this data the placebo attributes at most {max(placebo_max.values()):.1f} s to any family, so X is the 1 s floor for every deficit. "
                 if floor_only else "")
              + "Synthetic apprentices with a known price per trace; this shows the method recovers what we planted."),
    )
    dr = {
        "meta": dr_meta, "rows": rows, "overall": overall,
        "precision": overall["precision"], "recall": overall["recall"],      # aliases the dashboard fixture reads
        "detection_rule": ("detected when recovered seconds >= X; X = max(1 s, 95th percentile of the placebo attribution to "
                           "that cog family); precision and recall are pooled over every (case, deficit) pair"),
        "price_definition": "seconds the deficit added minus seconds it removed, against the same case without it (exact by construction)",
        "reference": "nearest expert by alignment cost, never the same person",
        "bootstrap_draws": cfg.B,
    }

    # --- controls ------------------------------------------------------------------------------------------------
    real = co.real_gap("nearest_expert")
    real_pp = list(real["per_person"].values())
    placebo_pp = [statistics.fmean(v) for v in placebo_gap.values()]
    observed = real["gap_s"]
    null = co.null(B=cfg.B_null, seed=seed + 3, observed=observed)
    n_nov, n_exp = len(real_pp), len(placebo_pp)
    gap_ci = cluster_mean_interval(real_pp, cfg.B, seed + 1)
    placebo_ci = cluster_mean_interval(placebo_pp, cfg.B, seed + 2)
    np_meta = make_meta(
        "synthetic", n_nov + n_exp, "people",
        f"cluster bootstrap by person, B = {cfg.B}; null = {cfg.B_null} permutations of the expert/novice label across people",
        note=("Real gap = novice minus nearest-expert seconds per case, mean over people. Placebo = each expert against the nearest other "
              "expert. Null = labels shuffled across people, whole procedure repeated (interval = 2.5th to 97.5th percentile of the "
              "permutation distribution). Both controls should include zero; the real gap should not."),
    )
    np_sec = {
        "meta": np_meta,
        "real": {"gap_s": rnd(observed, 2), "ci": gap_ci, "n_people": n_nov},
        "placebo": {"gap_s": rnd(statistics.fmean(placebo_pp), 2), "ci": placebo_ci, "n_people": n_exp},
        "null": {"gap_s": rnd(null["gap_s"], 2), "ci": [rnd(v, 2) for v in null["ci"]], "p_value": null.get("p_value"), "draws": null["draws"]},
        "unit": "seconds per case, novice minus reference",
        "controls_include_zero": bool(
            placebo_ci[0] is not None and placebo_ci[0] <= 0 <= placebo_ci[1] and null["ci"][0] <= 0 <= null["ci"][1]
        ),
    }
    return Result(dr, np_sec)
