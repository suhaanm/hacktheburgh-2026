"""Scoring the expert-envelope variants (M3) and the counterfactual variants (M4) against the planted prices (PLAN.md sections 6.5, 6.6)."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

import numpy as np

from understudy_engine.eval.deficit import DEFICIT_ORDER, MIN_X_S, X_QUANTILE
from understudy_engine.genome.labels import DEFICIT_OF_LABEL, LABEL_ORDER
from understudy_engine.mlv2.apprentice_pool import AppCohort
from understudy_engine.mlv2.envelope import VARIANTS, EnvelopeModel, EnvelopeVariant, deficit_view
from understudy_engine.mlv2.stats import Clusters, adjusted_level, boot_multiplicities, interval, ratio_draws

TARGET_DEFICITS = ("repeated_read_result", "copy_error")
OTHER_DEFICITS = tuple(d for d in DEFICIT_ORDER if d not in TARGET_DEFICITS)
LABEL_IDX = {l: i for i, l in enumerate(LABEL_ORDER)}
DEFICIT_LABEL = {d: l for l, d in DEFICIT_OF_LABEL.items()}


@dataclass
class VariantRows:
    """One variant's results over every (novice case, deficit) pair of a pool of cohorts."""

    vid: str
    cohort: list[str]
    person: list[str]        # cluster id: cohort label + person
    task: list[str]
    deficit: list[str]
    present: np.ndarray
    injected: np.ndarray
    point: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    threshold: np.ndarray    # X per row (from this variant's own expert-versus-expert placebo)
    placebo_gap: dict[str, list[float]]            # cohort label -> total attributed seconds of each expert case against other experts
    novice_gap: dict[str, list[float]]             # cohort label -> total attributed seconds of each novice case
    placebo_person: dict[str, list[str]] = None    # person of each placebo value


def run_variant(cohorts: list[AppCohort], vid_or_variant, *, fn=None, label: str | None = None, seed: int = 0, n_boot: int = 200,
                n_samples: int = 64, log=None) -> VariantRows:
    """Attribute every novice case and every expert case (the placebo) of each cohort under one variant."""
    v: EnvelopeVariant = VARIANTS[vid_or_variant] if isinstance(vid_or_variant, str) else vid_or_variant
    rows = {k: [] for k in ("cohort", "person", "task", "deficit", "present", "injected", "point", "lo", "hi", "X")}
    placebo_gap: dict[str, list[float]] = {}
    placebo_person: dict[str, list[str]] = {}
    novice_gap: dict[str, list[float]] = {}
    for c in cohorts:
        co = c.cohort
        model = EnvelopeModel(co.experts, seed=seed + c.seed, n_boot=n_boot, n_samples=n_samples)
        truth_by_task = {t["task_id"]: t for t in c.truth["traces"]}
        deficits = [d for d in DEFICIT_ORDER if d in c.truth["deficit_types"]]
        # placebo: each expert case against the other experts (never the same person), same procedure
        placebo_attr: dict[str, list[float]] = {d: [] for d in deficits}
        pg: list[float] = []
        pp: list[str] = []
        for ep in co.experts:
            a = model.attribute(ep, v, with_interval=False, fn=fn)
            dv = deficit_view(a)
            for d in deficits:
                placebo_attr[d].append(abs(dv[d]["point"]))
            pg.append(float(sum(a.point.values())))
            pp.append(f"{c.label}:{ep.person}")
        placebo_gap[c.label] = pg
        placebo_person[c.label] = pp
        X = {d: max(MIN_X_S, float(np.quantile(placebo_attr[d], X_QUANTILE))) for d in deficits}
        ng: list[float] = []
        for ep in co.novices:
            a = model.attribute(ep, v, with_interval=True, fn=fn)
            dv = deficit_view(a)
            ng.append(float(sum(a.point.values())))
            inj = {x["type"]: float(x["price_s"]) for x in truth_by_task[ep.task_id]["deficits"] if x["instances"] > 0}
            for d in deficits:
                rows["cohort"].append(c.label)
                rows["person"].append(f"{c.label}:{ep.person}")
                rows["task"].append(f"{c.label}:{ep.task_id}")
                rows["deficit"].append(d)
                rows["present"].append(d in inj)
                rows["injected"].append(inj.get(d, 0.0))
                rows["point"].append(dv[d]["point"])
                rows["lo"].append(dv[d]["lo"])
                rows["hi"].append(dv[d]["hi"])
                rows["X"].append(X[d])
        novice_gap[c.label] = ng
        if log:
            log(f"  {label or v.id}: cohort {c.label} done")
    arr = lambda k, dt=float: np.array(rows[k], dtype=dt)   # noqa: E731
    return VariantRows(label or v.id, rows["cohort"], rows["person"], rows["task"], rows["deficit"], arr("present", bool), arr("injected"),
                       arr("point"), arr("lo"), arr("hi"), arr("X"), placebo_gap, novice_gap, placebo_person)


def _cluster_arrays(r: VariantRows, cl: Clusters, mask: np.ndarray, vals: np.ndarray) -> np.ndarray:
    return np.bincount(cl.inv[mask], weights=vals[mask], minlength=cl.C)


def per_deficit_table(r: VariantRows, cl: Clusters, M: np.ndarray, level: float = 0.95) -> list[dict]:
    rows = []
    for d in DEFICIT_ORDER:
        sel = np.array([x == d for x in r.deficit])
        pres = sel & r.present
        absn = sel & ~r.present
        det = r.point >= r.threshold
        n_pres = int(pres.sum())
        if n_pres == 0:
            continue
        err = r.point - r.injected
        bias_num = _cluster_arrays(r, cl, pres, err)
        cnt = _cluster_arrays(r, cl, pres, np.ones_like(err))
        tp = _cluster_arrays(r, cl, pres & det, np.ones_like(err))
        fn = _cluster_arrays(r, cl, pres & ~det, np.ones_like(err))
        fp = _cluster_arrays(r, cl, absn & det, np.ones_like(err))
        cov_hit = _cluster_arrays(r, cl, pres & (r.lo <= r.injected) & (r.injected <= r.hi), np.ones_like(err))
        ae = _cluster_arrays(r, cl, pres, np.abs(err))
        rows.append({
            "deficit": d, "n_present": n_pres, "n_absent": int(absn.sum()), "injected_mean": float(r.injected[pres].mean()),
            "recovered_mean": float(r.point[pres].mean()),
            "bias": {"value": float(err[pres].mean()), "interval": list(interval(ratio_draws(bias_num, cnt, M), level))},
            "abs_error": {"value": float(np.abs(err[pres]).mean()), "interval": list(interval(ratio_draws(ae, cnt, M), level))},
            "recall": {"value": float(tp.sum() / max(1.0, tp.sum() + fn.sum())), "interval": list(interval(ratio_draws(tp, tp + fn, M), level))},
            "precision": {"value": float(tp.sum() / max(1.0, tp.sum() + fp.sum())), "interval": list(interval(ratio_draws(tp, tp + fp, M), level))},
            "coverage_95": {"value": float(cov_hit.sum() / cnt.sum()), "interval": list(interval(ratio_draws(cov_hit, cnt, M), level))},
            "mean_threshold_s": float(r.threshold[sel].mean()),
        })
    return rows


def overall_pr(r: VariantRows, cl: Clusters) -> dict[str, np.ndarray]:
    det = r.point >= r.threshold
    one = np.ones(len(r.point))
    return {"tp": _cluster_arrays(r, cl, r.present & det, one), "fn": _cluster_arrays(r, cl, r.present & ~det, one),
            "fp": _cluster_arrays(r, cl, ~r.present & det, one)}


def paired_abs_error(r: VariantRows, ref: VariantRows, cl: Clusters, M: np.ndarray, deficits: tuple[str, ...], level: float) -> dict:
    sel = np.array([d in deficits for d in r.deficit]) & r.present
    if int(sel.sum()) == 0:
        return {"delta": None, "interval": [None, None], "n_pairs": 0}
    d_ae = np.abs(r.point - r.injected) - np.abs(ref.point - ref.injected)
    num = _cluster_arrays(r, cl, sel, d_ae)
    cnt = _cluster_arrays(r, cl, sel, np.ones_like(d_ae))
    draws = ratio_draws(num, cnt, M)
    return {"delta": float(num.sum() / cnt.sum()), "interval": list(interval(draws, level)), "n_pairs": int(sel.sum()),
            "variant_mae": float(np.abs(r.point - r.injected)[sel].mean()), "reference_mae": float(np.abs(ref.point - ref.injected)[sel].mean())}


def controls_row(r: VariantRows, M_e: np.ndarray | None, level: float = 0.95) -> dict:
    """Placebo (expert against another expert): mean total attributed seconds per case with an interval over expert people."""
    vals, pers = [], []
    for lab, g in r.placebo_gap.items():
        vals.extend(g)
        pers.extend(r.placebo_person[lab])
    cl = Clusters.from_labels(pers)
    v = np.array(vals)
    num = np.bincount(cl.inv, weights=v, minlength=cl.C)
    cnt = np.bincount(cl.inv, minlength=cl.C).astype(float)
    M = boot_multiplicities(cl.C, 2000, 7)
    draws = ratio_draws(num, cnt, M)
    lo, hi = interval(draws, level)
    return {"gap_s": float(v.mean()), "interval": [lo, hi], "includes_zero": bool(lo <= 0 <= hi), "n_expert_people": cl.C}


def null_gap(cohorts: list[AppCohort], v: EnvelopeVariant, *, b_null: int, seed: int, n_samples: int = 16) -> dict:
    """Shuffled-label null: expert and novice labels permuted across people; the whole procedure (cost learning, nearest references, attribution)
    repeated; the statistic is the mean total attributed seconds per pseudo-novice case (as v1's null)."""
    rng = np.random.default_rng(seed)
    draws = []
    for c in cohorts:
        eps_by = {}
        for e in c.cohort.episodes:
            eps_by.setdefault(e.person, []).append(e)
        people = sorted(eps_by)
        n_exp = len({e.person for e in c.cohort.experts})
        for b in range(b_null):
            perm = list(rng.permutation(people))
            pseudo_exp = [e for p in perm[:n_exp] for e in eps_by[p]]
            model = EnvelopeModel(pseudo_exp, seed=int(rng.integers(1 << 30)), n_boot=1, n_samples=n_samples)
            per_person = []
            for p in perm[n_exp:]:
                g = [float(sum(model.attribute(ep, v, with_interval=False).point.values())) for ep in eps_by[p]]
                per_person.append(statistics.fmean(g))
            draws.append(statistics.fmean(per_person))
    d = np.array(draws)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"gap_s": float(d.mean()), "interval": [float(lo), float(hi)], "includes_zero": bool(lo <= 0 <= hi), "draws": int(d.size)}


def compare_variants(results: dict[str, VariantRows], *, ref: str, primary: str | None, candidates: list[str], n_boot: int = 4000, seed: int = 0,
                     primary_deficits: tuple[str, ...] = TARGET_DEFICITS, guard_deficits: tuple[str, ...] | None = OTHER_DEFICITS,
                     guard_margin_s: float = 1.5, nulls: dict[str, dict] | None = None) -> dict:
    r0 = results[ref]
    cl = Clusters.from_labels(r0.person)
    M = boot_multiplicities(cl.C, n_boot, seed)
    m = len(candidates)
    out_rows = {}
    pr_ref = overall_pr(r0, cl)
    placebo_ref = controls_row(r0, None)
    for vid, r in results.items():
        lvl = 0.95 if (vid == primary or vid == ref) else adjusted_level(m)
        pr = overall_pr(r, cl)
        tp, fn, fp = pr["tp"], pr["fn"], pr["fp"]
        rec_d = ratio_draws(tp, tp + fn, M) - ratio_draws(pr_ref["tp"], pr_ref["tp"] + pr_ref["fn"], M)
        prec_d = ratio_draws(tp, tp + fp, M) - ratio_draws(pr_ref["tp"], pr_ref["tp"] + pr_ref["fp"], M)
        rec = float(tp.sum() / max(1.0, tp.sum() + fn.sum()))
        prec = float(tp.sum() / max(1.0, tp.sum() + fp.sum()))
        rec0 = float(pr_ref["tp"].sum() / max(1.0, pr_ref["tp"].sum() + pr_ref["fn"].sum()))
        prec0 = float(pr_ref["tp"].sum() / max(1.0, pr_ref["tp"].sum() + pr_ref["fp"].sum()))
        paired_target = paired_abs_error(r, r0, cl, M, primary_deficits, lvl)
        paired_other = paired_abs_error(r, r0, cl, M, guard_deficits, lvl) if guard_deficits else None
        per_def = {d: paired_abs_error(r, r0, cl, M, (d,), lvl) for d in DEFICIT_ORDER}
        ctl = controls_row(r, None)
        guards = {}
        if guard_deficits is not None and vid != ref:
            guards["other_deficits_abs_error"] = {"ok": bool(paired_other["interval"][1] is not None and paired_other["interval"][1] <= guard_margin_s),
                                                   "bound": paired_other["interval"][1], "margin": guard_margin_s}
        elif guard_deficits is None and vid != ref:
            # Q family: each deficit separately, upper bound at most +2 s
            ok = all((x["interval"][1] is None) or x["interval"][1] <= guard_margin_s for x in per_def.values())
            guards["each_deficit_abs_error"] = {"ok": bool(ok), "margin": guard_margin_s,
                                                 "bounds": {d: x["interval"][1] for d, x in per_def.items()}}
        if vid != ref:
            guards["recall"] = {"ok": bool(interval(rec_d, lvl)[0] >= -0.03), "bound": interval(rec_d, lvl)[0], "margin": -0.03}
            guards["precision"] = {"ok": bool(interval(prec_d, lvl)[0] >= -0.03), "bound": interval(prec_d, lvl)[0], "margin": -0.03}
            guards["placebo_includes_zero_and_close_to_v1"] = {"ok": bool(ctl["includes_zero"] and ctl["gap_s"] <= placebo_ref["gap_s"] + 3.0),
                                                                "gap_s": ctl["gap_s"], "v1_gap_s": placebo_ref["gap_s"]}
            if nulls and vid in nulls:
                guards["null_includes_zero"] = {"ok": bool(nulls[vid]["includes_zero"]), "gap_s": nulls[vid]["gap_s"], "interval": nulls[vid]["interval"]}
        improves = paired_target["interval"][1] is not None and paired_target["interval"][1] < 0
        guards_ok = all(g["ok"] for g in guards.values())
        harmful = paired_target["interval"][0] is not None and paired_target["interval"][0] > 0
        verdict = "reference" if vid == ref else ("accepted" if improves and guards_ok else ("harmful" if harmful else "null"))
        out_rows[vid] = {
            "id": vid, "level": lvl, "is_primary": vid == primary,
            "paired_primary_abs_error": paired_target, "paired_other_abs_error": paired_other, "paired_by_deficit": per_def,
            "recall": rec, "recall_delta": {"delta": rec - rec0, "interval": list(interval(rec_d, lvl))},
            "precision": prec, "precision_delta": {"delta": prec - prec0, "interval": list(interval(prec_d, lvl))},
            "per_deficit": per_deficit_table(r, cl, M), "placebo": ctl, "null": (nulls or {}).get(vid),
            "guards": guards, "guards_ok": bool(guards_ok), "primary_improves": bool(improves), "verdict": verdict,
        }
    return {"reference": ref, "primary": primary, "n_clusters": cl.C, "n_boot": n_boot, "m_candidates": m, "adjusted_level": adjusted_level(m),
            "primary_deficits": list(primary_deficits), "rows": out_rows}
