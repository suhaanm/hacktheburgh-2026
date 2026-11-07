"""The genome part of the v2 evaluation: expert envelope (M3, family E) and counterfactual seconds (M4, family Q) on one pool of apprentice cohorts."""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from understudy_engine.genome.decompose import decompose
from understudy_engine.mlv2 import apprentice_pool as AP
from understudy_engine.mlv2.counterfactual import q1_functional, shapley_values, splice_value_function, stress_test_interaction
from understudy_engine.mlv2.envelope import VARIANTS
from understudy_engine.mlv2.genome_stats import DEFICIT_LABEL, compare_variants, null_gap, run_variant

ORIGIN = "synthetic"
NOTE = ("Apprentice cohorts from our own generator (8 experts, 16 novices, 2 cases each, planted deficits with exact prices): fresh seeds of the "
        "same generator. They show recovery of what we planted, and cannot show that a method avoided learning the generator.")
E_CANDIDATES = ["E1", "E2", "E3", "E4"]
Q_CANDIDATES = ["Q1", "Q1b"]


def run_genome_part(pool: str, *, frozen: dict | None = None, n_boot: int = 4000, fast: bool = False, b_null: int | None = None,
                    limit: int | None = None, seed: int = 0, log=None) -> dict[str, Any]:
    log = log or (lambda m: None)
    t0 = time.time()
    cohorts = AP.load_pool(pool, limit=limit)
    if fast:
        n_boot = min(n_boot, 300)
    b_null = (4 if fast else (20 if pool != "APP-HELD" else 30)) if b_null is None else b_null
    n_samples = 32 if fast else 64
    primary_e = (frozen or {}).get("primary_e", "E4")
    primary_q = (frozen or {}).get("primary_q", "Q1")
    results = {}
    for vid in VARIANTS:
        results[vid] = run_variant(cohorts, vid, seed=seed, n_boot=60 if fast else 200, n_samples=n_samples, log=log)
        log(f"{vid} done at {time.time() - t0:.0f}s")
    # Q family: Q0 = v1's attribution (E0 numbers); Q1 = E4 ensemble read through the pace-scaled splice; Q1b = the same ensemble priced at the
    # unscaled expert dwell, which is v1's pricing and therefore equal to E4's numbers (checked in the tests)
    q = {"Q0": results["E0"], "Q1": run_variant(cohorts, VARIANTS["E4"], fn=q1_functional, label="Q1", seed=seed, n_boot=60 if fast else 200,
                                                n_samples=n_samples, log=log), "Q1b": results["E4"]}
    log(f"Q family done at {time.time() - t0:.0f}s")
    nulls = {vid: null_gap(cohorts, VARIANTS[vid], b_null=b_null, seed=seed + 11) for vid in VARIANTS if vid in ("E0", "E1", "E2", "E3", "E4")}
    log(f"nulls done at {time.time() - t0:.0f}s")
    cmp_e = compare_variants(results, ref="E0", primary=primary_e, candidates=E_CANDIDATES, n_boot=n_boot, seed=seed, nulls=nulls)
    cmp_q = compare_variants(q, ref="Q0", primary=primary_q, candidates=Q_CANDIDATES, n_boot=n_boot, seed=seed,
                             primary_deficits=tuple(DEFICIT_LABEL), guard_deficits=None, guard_margin_s=2.0)
    # Shapley over the habits present, on the replay accounting (additive by construction) for one cohort's novice cases, plus the stress test
    r = q["Q1"]
    interact = []
    for task in sorted(set(r.task))[:6]:
        sel = np.array([t == task for t in r.task])
        sec = {d: float(p) for d, p, pr in zip(np.array(r.deficit)[sel], r.point[sel], r.present[sel]) if pr}
        if len(sec) >= 2:
            phi = shapley_values(sorted(sec), splice_value_function(sec))
            interact.append(max(abs(phi[h] - sec[h]) for h in sec))
    first = cohorts[0]
    levels = {p["person"]: p["level"] for p in first.truth["people"]}
    ob = decompose(first.cohort.episodes, levels, B=100, check_statsmodels=False)
    stress = stress_test_interaction()
    return {
        "pool": pool, "origin": ORIGIN, "n_cohorts": len(cohorts), "n_unit": "people",
        "n_novices": int(sum(len(c.cohort.novices) // 2 for c in cohorts)), "n_experts": int(sum(len(c.cohort.experts) // 2 for c in cohorts)),
        "split": "apprentice replicate cohorts; clusters are people (cohort label + person id)", "note": NOTE, "seeds": [c.seed for c in cohorts],
        "primary_e": primary_e, "primary_q": primary_q, "family_e": cmp_e, "family_q": cmp_q, "nulls": nulls,
        "learned_costs_example": {k: v for k, v in list(__import__("understudy_engine.mlv2.envelope", fromlist=["x"]).EnvelopeModel(
            cohorts[0].cohort.experts).learn_info["pairs"].items()) if v["hand"] != v["cost"]},
        "shapley": {"max_abs_interaction_on_replay": float(max(interact)) if interact else None, "cases_checked": len(interact),
                    "stress_test": {"habits": stress.habits, "true_shapley": stress.true_shapley, "single_replay": stress.single_replay,
                                    "fitted_shapley": stress.fitted_shapley, "total_true": stress.total_true,
                                    "single_replay_sum": stress.single_replay_sum, "note": stress.note, "origin": "invented by us (planted interaction)"}},
        "oaxaca_blinder_cohort_level": {"cohort": first.label, "gap_s": ob["gap_s"], "explained_s": ob["explained_s"], "unexplained_s": ob["unexplained_s"],
                                        "components": ob["components"][:8],
                                        "note": "cohort-level behaviour-count decomposition; not comparable case by case with the replay"},
        "assumption": "The counterfactual assumes the rest of the path would be unchanged when the habit is fixed; it fails when habits interact.",
        "seconds": round(time.time() - t0, 1),
    }
