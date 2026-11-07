"""The hazard part of the v2 evaluation: families A and C, the time-to-event head, the controls and the M1 ablation, on one pool.

``run_hazard_part(pool, ...)`` is what both the dev run and the single frozen held-out run call. It returns plain JSON-safe dicts with n, split,
intervals and the origin badge in every block. Nothing here reads held-out data unless the pool is HELD (the pool loader enforces the token).
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from understudy_engine.hazard.features import build_bins
from understudy_engine.mlv2 import splits
from understudy_engine.mlv2.ablation import ablate
from understudy_engine.mlv2.alarms import build_layout
from understudy_engine.mlv2.controls import LL_TOL, shuffle_labels
from understudy_engine.mlv2.family_a import FamilyARun, choose_a7, choose_primary, compare_family_a, run_family_a
from understudy_engine.mlv2.family_c import compare_family_c, run_family_c
from understudy_engine.mlv2.models import A7_CANDIDATES, FAMILY_A, VariantSpec
from understudy_engine.mlv2.protocol import DEFAULT_BUDGET, make_folds
from understudy_engine.mlv2.stats import Clusters, boot_multiplicities, interval, metric_draws, metric_points, score_parts
from understudy_engine.mlv2.tte import build_tte, calibration_by_quantile, concordance, km_restricted_mean, oof_tte

ORIGIN = "synthetic"
HAZARD_NOTE = ("Persona replicates from our own generator: fresh draws of the same four persona types. They catch overfitting to one noise "
               "realisation; they cannot show that a model avoided learning the generator.")


def a_variants(frozen: dict | None) -> tuple[dict[str, VariantSpec], str | None]:
    """The family A variants to score: A0..A6 plus A7 (the registered A1-or-A4 base). With no frozen choice (dev) both A7 candidates run."""
    specs = dict(FAMILY_A)
    if frozen is None:
        specs.update(A7_CANDIDATES)
        return specs, None
    specs["A7"] = A7_CANDIDATES[frozen["a7_base"]]
    return specs, frozen.get("primary_a")


def _s60_block(tab, tte, o, a0_p, n_boot, seed, clusters, M) -> dict[str, Any]:
    y = tab.y.astype(float)
    parts = {"head": score_parts(y, o.s60, clusters), "tsp_discrete": score_parts(y, o.s60_tsp, clusters), "A0": score_parts(y, a0_p, clusters),
             "base_rate": score_parts(y, np.full(tab.n, y.mean()), clusters)}
    dr = {k: metric_draws(p, M) for k, p in parts.items()}
    pt = {k: metric_points(p) for k, p in parts.items()}
    out: dict[str, Any] = {k: {m: {"value": pt[k][m], "interval": list(interval(dr[k][m], 0.95))} for m in ("log_loss", "brier", "ece")} for k in parts}
    out["paired"] = {}
    for ref in ("A0", "tsp_discrete"):
        lo, hi = interval(dr["head"]["log_loss"] - dr[ref]["log_loss"], 0.95)
        out["paired"][f"head_minus_{ref}_log_loss"] = {"delta": pt["head"]["log_loss"] - pt[ref]["log_loss"], "interval": [lo, hi]}
    out["guard_within_0.02_of_A0"] = bool(out["paired"]["head_minus_A0_log_loss"]["interval"][1] <= 0.02)
    return out


def _cindex_jackknife(tab, tte, pred_min) -> dict[str, Any]:
    """Harrell's concordance with a delete-one-person jackknife t interval (a person-cluster interval that costs C evaluations)."""
    t, e = tte.time_s, tte.event
    full = concordance(t, e, pred_min)
    if full is None:
        return {"value": None, "interval": None}
    people = tab.people
    vals = []
    for q in people:
        keep = tab.person != q
        c = concordance(t[keep], e[keep], pred_min[keep])
        if c is not None:
            vals.append(c)
    C = len(vals)
    if C < 2:
        return {"value": full, "interval": None}
    vals = np.array(vals)
    se = float(np.sqrt((C - 1) / C * np.sum((vals - vals.mean()) ** 2)))
    from scipy.stats import t as tdist

    q = float(tdist.ppf(0.975, C - 1))
    return {"value": full, "interval": [full - q * se, full + q * se], "method": f"delete-one-person jackknife, t with {C - 1} df"}


def tte_block(tab, episodes, a0_p, *, n_boot: int, seed: int, clusters: Clusters, M: np.ndarray, with_cindex: bool = True) -> dict[str, Any]:
    tte = build_tte(episodes, tab)
    o = oof_tte(tab, tte)
    blk: dict[str, Any] = {"s60": _s60_block(tab, tte, o, a0_p, n_boot, seed, clusters, M)}
    if with_cindex:
        blk["c_index"] = {"head": _cindex_jackknife(tab, tte, o.minutes), "tsp_discrete": _cindex_jackknife(tab, tte, o.minutes_tsp)}
    blk["calibration_expected_minutes"] = calibration_by_quantile(tab.person, tte.time_s, tte.event, o.minutes, 5)
    blk["mean_expected_min"] = float(o.minutes.mean())
    blk["km_restricted_mean_min"] = km_restricted_mean(tte.time_s, tte.event)
    blk["definition"] = ("Discrete-time survival, 30 s steps to 5 minutes, logistic hazard on v1's features plus a step one-hot; expected minutes = "
                         "restricted mean survival time to 5 minutes (features held at the origin). S(60 s) is scored on v1's own label.")
    return blk


def controls_block(tab, specs: dict[str, VariantSpec], inner_folds: int | None, seed: int) -> dict[str, Any]:
    """Shuffled-label controls: no variant may beat the base rate by more than LL_TOL (global shuffle); the within-person shuffle is a diagnostic."""
    out: dict[str, Any] = {}
    for scope in ("global", "person"):
        sh = shuffle_labels(tab, seed + 31, scope)
        use = specs if scope == "global" else {k: specs[k] for k in ("A0", "A6") if k in specs}
        run = run_family_a(sh, variants=use, include_baselines=True, inner_folds=inner_folds)
        y = sh.y.astype(float)
        from understudy_engine.trust.calibration import log_loss

        base = log_loss(y, run.outputs["BASE"].p)
        rows = {}
        for vid in use:
            ll = log_loss(y, run.outputs[vid].p)
            rows[vid] = {"log_loss": ll, "gain_over_base_rate": base - ll, "passes": bool(base - ll <= LL_TOL)}
        out[f"shuffle_{scope}"] = {"base_rate_log_loss": base, "tolerance": LL_TOL, "rows": rows,
                                   "all_pass": bool(all(r["passes"] for r in rows.values())),
                                   "role": "control" if scope == "global" else "diagnostic (keeps each person's own stuck rate)"}
    return out


def run_hazard_part(pool: str, *, frozen: dict | None = None, fast: bool = False, n_boot: int = 4000, seed: int = 0, inner_folds: int | None = 5,
                    with_tte: bool = True, with_controls: bool = True, with_ablation: bool = True, n_days: int = 21,
                    limit_replicates: int | None = None, log=None) -> dict[str, Any]:
    """Families A and C, the head, the controls and the ablation on ``pool`` (D0, DEV or HELD). ``frozen`` carries the dev-picked primary."""
    log = log or (lambda m: None)
    t_start = time.time()
    if fast:
        n_boot = min(n_boot, 300)
    episodes = splits.load_pool(pool, n_days=n_days, limit_replicates=limit_replicates)
    tab = build_bins(episodes)
    layout = build_layout(tab)
    cl = Clusters.from_labels(tab.person)
    people = tab.people
    specs, primary = a_variants(frozen)
    log(f"hazard part: pool {pool}, {len(people)} people, {tab.n} bins")
    run = run_family_a(tab, variants=specs, include_baselines=True, inner_folds=inner_folds, layout=layout)
    log(f"family A scored in {time.time() - t_start:.0f}s")
    cand = [v for v in specs if v != "A0"]
    cmp_a = compare_family_a(run, primary=primary, n_boot=n_boot, seed=seed, candidates=cand)
    out: dict[str, Any] = {
        "pool": pool, "origin": ORIGIN, "n_people": len(people), "n_unit": "people", "n_bins": int(tab.n), "n_episodes": len(tab.ep_person),
        "split": "leave-one-person-out within the pool", "inner": run.inner, "interval_level": 0.95, "n_boot": n_boot, "note": HAZARD_NOTE,
        "persona_types": sorted({splits.persona_type(p) for p in people}), "primary_a": primary, "family_a": cmp_a,
        "dev_primary_rule_result": choose_primary(cmp_a, [v for v in cand if v in cmp_a["rows"]]) if frozen is None else None,
        "dev_a7_base": choose_a7(cmp_a) if frozen is None and "A7_A1" in cmp_a["rows"] else None,
    }
    M = boot_multiplicities(cl.C, n_boot, seed)
    if with_tte:
        out["tte"] = tte_block(tab, episodes, run.outputs["A0"].p, n_boot=n_boot, seed=seed, clusters=cl, M=M, with_cindex=not fast)
        log(f"time-to-event head done at {time.time() - t_start:.0f}s")
    # family C: the alarm rules on A0's probabilities (the rule judged alone), and on the frozen primary candidate of family A
    base_a0 = run.bases["L"]
    fc0 = run_family_c(tab, base_a0, FAMILY_A["A0"], layout=layout, prob_label="A0", n_boot_rule=300 if fast else 2000)
    out["family_c"] = {"on_A0": compare_family_c(fc0, n_boot=n_boot, seed=seed)}
    prim_id = primary or (cmp_a and choose_primary(cmp_a, [v for v in cand if v in cmp_a["rows"]]))
    if prim_id and prim_id in run.outputs and not fast:
        pspec = run.outputs[prim_id].spec
        fcp = run_family_c(tab, run.bases[pspec.base], pspec, layout=layout, prob_label=prim_id, n_boot_rule=2000)
        out["family_c"]["on_primary_a"] = compare_family_c(fcp, n_boot=n_boot, seed=seed)
    log(f"family C done at {time.time() - t_start:.0f}s")
    if with_controls:
        ctl_specs = {k: v for k, v in specs.items() if k in ("A0", "A1", "A3", "A6", "A7", "A7_A1", "A7_A4")} if fast else specs
        if fast:
            ctl_specs = {k: specs[k] for k in ("A0", "A1", "A6") if k in specs}
        out["controls"] = controls_block(tab, ctl_specs, inner_folds, seed)
        log(f"controls done at {time.time() - t_start:.0f}s")
    if with_ablation and not fast:
        from understudy_engine.mlv2.ablation_awareness import (
            AWARENESS_NOTE, awareness_groups, planted_label_table, planted_spells_for,
        )

        members = splits.pool_members(pool)
        if limit_replicates is not None:
            members = [m for m in members if m[1] <= limit_replicates]
        groups = awareness_groups(tab, members, n_days)
        abl = ablate(tab, groups, inner_folds=inner_folds, n_boot=min(n_boot, 2000), seed=seed)
        abl["label"] = "no progress in the next 60 s (the label the hazard model is trained on; the planned ablation)"
        sup_tab = planted_label_table(tab, planted_spells_for(members, n_days))
        abl_s = ablate(sup_tab, groups, inner_folds=inner_folds, n_boot=min(n_boot, 2000), seed=seed)
        abl_s["label"] = "a planted stuck spell overlaps the next 60 s (supplementary: the label the awareness events were planted against)"
        out["ablation"] = {"primary_label": abl, "planted_label_supplementary": abl_s, "note": AWARENESS_NOTE, "origin": ORIGIN}
        log(f"ablation done at {time.time() - t_start:.0f}s")
    out["seconds"] = round(time.time() - t_start, 1)
    return out
