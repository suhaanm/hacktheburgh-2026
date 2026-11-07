"""Validation of the independence score on SIMULATED learners with planted learning curves and known true mastery (CUE-7).

SIMULATED. Nobody here is a person. ``simlearn`` plants a latent mastery curve per skill, so the truth is known and the score can be
judged against it: bias, interval coverage, how often it "rises" when the learner did not improve, and how much dismissing cues
inflates it. Four learner kinds (improving, flat, forgetting after a 21-day absence, gamer who dismisses every cue) with 3 skills x 40
occurrences each. Cluster = learner; intervals are percentile bootstrap over learners.

Estimands, stated before any run:

* independence: the interval is the Wilson interval of the last 20 occurrences; the truth is the mean planted unaided-success
  probability ``q`` over the same 20 occurrences. The point estimate is the clean share, the composite uses the lower bound.
* mastery: the score's replay of the ledger (decayed to now) against the planted latent ``m`` (mean over skills).
* composite: against a TRUE composite built from the planted quantities with the same weights and the same available components
  (true independence, not a lower bound). The expected bias therefore includes the deliberate conservatism of the lower bound; it
  is reported as such (``lb_shift_points``).
* false rise: for FLAT learners, the share of replicates where (a) the trend interval says "less help", (b) the composite at occurrence
  120 is at least 10 points above the composite at occurrence 30, (c) the window independence share is 0.20 or more above the
  share at occurrence 30. Nominal for (a) is about 2.5%.
* gaming: independence inflation of a learner who dismisses cues versus one who accepts them, with the same true mastery; and the same
  numbers with the guards removed (errors and abandoned steps counted as independent), to show what the guards buy.

Two mastery replays are compared on the dev seeds: the engine's tracing defaults (a learning step after every counted run) and the
evidence-only variant (no learning step: mastery follows the outcomes, not the number of practices).
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

import numpy as np

from ..skills import tracing as T
from ..trust.meta import analytic_meta
from . import score as S
from . import simlearn as SL

KINDS = ("improving", "flat", "forgetting", "gamer")
N_PER_SKILL = 40
CHECK = 30                    # the early checkpoint (occurrences)
VARIANTS = tuple(S.MASTERY_VARIANTS)
DEV_SEED0, HELD_SEED0 = 0, 10_000
SKILLS = ("check-the-cliff", "reconcile-before-noting", "enter-household-once")


def _boot_mean(v: np.ndarray, n_boot: int = 400, seed: int = 0) -> list[float | None]:
    v = np.asarray(v, float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return [None, None]
    rng = np.random.default_rng(seed)
    m = v[rng.integers(0, v.size, (n_boot, v.size))].mean(1)
    return [round(float(x), 4) for x in np.quantile(m, [0.025, 0.975])]


def _stat(v: list[float | None], seed: int = 0) -> dict[str, Any]:
    a = np.array([x for x in v if x is not None], float)
    if a.size == 0:
        return {"mean": None, "ci": [None, None], "n": 0}
    return {"mean": round(float(a.mean()), 4), "ci": _boot_mean(a, seed=seed), "n": int(a.size)}


def _rate(flags: list[bool], seed: int = 0) -> dict[str, Any]:
    a = np.array(flags, float)
    return {"rate": round(float(a.mean()), 4) if a.size else None, "ci": _boot_mean(a, seed=seed), "n": int(a.size)}


def _true_quantities(rows: list[dict], truth: SL.Truth, now: float, comps: dict[str, Any]) -> dict[str, float | None]:
    q = np.array(truth.q)
    m = np.array(truth.m)
    t_ind = float(q[-20:].mean())
    ms = []
    for s in SKILLS:
        fm = truth.final_m[s]                                         # type: ignore[index]
        dt = (now - truth.last_t[s]) / SL.DAY                         # type: ignore[index]
        ms.append(fm * np.exp(-dt / truth.stability_days))
    t_m = float(np.mean(ms))
    t_gap = None
    if comps["gap_closure"]["value"] is not None:
        g0 = float((1 - m[:5]).mean())
        g1 = float((1 - m[-5:]).mean())
        t_gap = float(min(1.0, max(0.0, 1 - g1 / g0))) if g0 > 0 else None
    t_ret = None
    probes = S.retention_probes(S.assist_only(rows))
    if probes:
        pos = {r["id"]: i for i, r in enumerate(rows)}
        t_ret = float(np.mean([q[pos[r["id"]]] for r in probes]))
    return {"independence": t_ind, "mastery": t_m, "gap_closure": t_gap, "retention": t_ret}


def _conservative(occ: list[dict], comps: dict[str, Any], now: float, seed: int) -> float | None:
    """A variant for comparison only: the composite with a lower bound on EVERY estimated component (independence Wilson lower, gap
    closure bootstrap lower, retention Wilson lower) instead of the spec's point estimates for gap closure and retention."""
    gc = S.gap_closure(occ, n_boot=100, seed=seed)
    gap = None if gc["value"] is None else (gc["ci"][0] if gc["ci"] else gc["value"])
    ret = comps["retention"]
    rlo = None if ret["value"] is None else ret["wilson"][0]
    return S.composite(comps["independence"]["lower"], comps["mastery"]["value"], gap, rlo)["value"]


def _replicate(kind: str, seed: int, variant: str, n_boot_trend: int, spec_kw: dict | None = None) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    spec = SL.preset(kind, **(spec_kw or {}))
    rows, truth = SL.simulate_learner(spec, rng, person=f"p_v{seed % 100000}", skills=SKILLS, n_per_skill=N_PER_SKILL)
    S.MASTERY_VARIANT = variant
    try:
        occ = S.assist_only(rows)
        now = S.row_time(occ[-1]) + 1800.0
        end = S.compute(occ, now, n_boot=0, seed=seed)
        tr = S.trend(occ, n_boot=n_boot_trend, seed=seed)
        early_now = S.row_time(occ[CHECK - 1]) + 1800.0
        early = S.compute(occ[:CHECK], early_now, n_boot=0, seed=seed)
        tq = _true_quantities(rows, truth, now, end)
        comp_true = S.composite(tq["independence"], tq["mastery"], tq["gap_closure"], tq["retention"])["value"]
        ind = end["independence"]
        naive = float(np.mean([0.0 if r["accepted"] else 1.0 for r in occ[-20:]]))        # the guards removed
        comp_cons = _conservative(occ, end, now, seed)
        comp_cons_early = _conservative(occ[:CHECK], early, early_now, seed) if early["ready"] else None
        lb_shift = None if end["composite"]["value"] is None else 100.0 * S.WEIGHTS["independence_lb"] * (tq["independence"] - ind["lower"]) / max(end["composite"]["available_weight"], 1e-9)
        return {
            "ind_share": ind["share"], "ind_lower": ind["lower"], "true_ind": tq["independence"], "ind_covered": ind["wilson"][0] <= tq["independence"] <= ind["wilson"][1],
            "ind_bias": ind["share"] - tq["independence"], "lb_bias": ind["lower"] - tq["independence"], "naive_ind": naive,
            "m_est": end["mastery"]["value"], "m_true": tq["mastery"], "m_bias": end["mastery"]["value"] - tq["mastery"],
            "gap_est": end["gap_closure"]["value"], "gap_true": tq["gap_closure"],
            "ret_est": end["retention"]["value"], "ret_true": tq["retention"], "ret_n": end["retention"]["n"],
            "comp_est": end["composite"]["value"], "comp_true": comp_true,
            "comp_bias": None if comp_true is None or end["composite"]["value"] is None else end["composite"]["value"] - comp_true,
            "comp_cons": comp_cons, "comp_cons_early": comp_cons_early,
            "comp_cons_bias": None if comp_true is None or comp_cons is None else comp_cons - comp_true,
            "lb_shift": lb_shift, "comp_early": early["composite"]["value"] if early["ready"] else None,
            "ind_early": early["independence"]["share"], "trend_dir": tr["direction"], "trend_slope": tr["slope_per_10"],
            "true_q_early": float(np.array(truth.q)[:CHECK].mean()), "true_q_late": float(np.array(truth.q)[-CHECK:].mean()),
        }
    finally:
        S.MASTERY_VARIANT = "engine_default"


def _summarise(reps: list[dict[str, Any]], kind: str, seed: int) -> dict[str, Any]:
    g = lambda k: [r[k] for r in reps]                                                               # noqa: E731
    out: dict[str, Any] = {
        "n_learners": len(reps),
        "independence": {"covered_by_wilson": _rate(g("ind_covered"), seed), "point_minus_truth": _stat(g("ind_bias"), seed),
                         "lower_bound_minus_truth": _stat(g("lb_bias"), seed), "true_mean": _stat(g("true_ind"), seed), "estimate_mean": _stat(g("ind_share"), seed)},
        "mastery": {"estimate_minus_truth": _stat(g("m_bias"), seed), "true_mean": _stat(g("m_true"), seed), "estimate_mean": _stat(g("m_est"), seed)},
        "gap_closure": {"estimate": _stat(g("gap_est"), seed), "truth": _stat(g("gap_true"), seed),
                        "error": _stat([None if r["gap_est"] is None or r["gap_true"] is None else r["gap_est"] - r["gap_true"] for r in reps], seed)},
        "retention": {"estimate": _stat(g("ret_est"), seed), "truth": _stat(g("ret_true"), seed), "probes_mean": _stat(g("ret_n"), seed)},
        "composite": {"estimate": _stat(g("comp_est"), seed), "truth": _stat(g("comp_true"), seed), "bias_points": _stat(g("comp_bias"), seed),
                      "lb_shift_points": _stat(g("lb_shift"), seed),
                      "conservative_variant": {"estimate": _stat(g("comp_cons"), seed), "bias_points": _stat(g("comp_cons_bias"), seed)}},
        "trend": {"direction_counts": {d: sum(1 for r in reps if r["trend_dir"] == d) for d in ("less_help", "steady", "more_help", "too_early")},
                  "slope_per_10": _stat(g("trend_slope"), seed)},
        "true_q": {"first_30_mean": _stat(g("true_q_early"), seed), "last_30_mean": _stat(g("true_q_late"), seed)},
    }
    comp_rise = [None if r["comp_early"] is None or r["comp_est"] is None else (r["comp_est"] - r["comp_early"]) >= 10.0 for r in reps]
    ind_rise = [(r["ind_share"] - r["ind_early"]) >= 0.20 for r in reps]
    less = [r["trend_dir"] == "less_help" for r in reps]
    cons_rise = [None if r["comp_cons_early"] is None or r["comp_cons"] is None else (r["comp_cons"] - r["comp_cons_early"]) >= 10.0 for r in reps]
    out["rise"] = {"trend_says_less_help": _rate(less, seed), "composite_up_10_points": _rate([x for x in comp_rise if x is not None], seed),
                   "conservative_composite_up_10_points": _rate([x for x in cons_rise if x is not None], seed), "independence_up_0.20": _rate(ind_rise, seed)}
    return out


def validate_score(*, seed0: int = DEV_SEED0, n_rep: int = 60, n_boot_trend: int = 200, variants: tuple[str, ...] | None = None,
                   kinds: tuple[str, ...] = KINDS) -> dict[str, Any]:
    variants = variants or VARIANTS
    out: dict[str, Any] = {}
    for vname in variants:
        by_kind = {}
        for ki, kind in enumerate(kinds):
            reps = [_replicate(kind, seed0 + 1000 * ki + i, vname, n_boot_trend) for i in range(n_rep)]
            by_kind[kind] = _summarise(reps, kind, seed0 + ki)
        out[vname] = by_kind
    return out


def gaming_sweep(*, seed0: int = DEV_SEED0, n_rep: int = 40, accepts: tuple[float, ...] = (0.8, 0.4, 0.0), variant: str = "evidence_only") -> dict[str, Any]:
    """Flat learners (m0 = 0.30, no learning) who accept 80%, 40% or 0% of the cues they are shown: how far the score rises as they
    dismiss more, with the guards on and with the guards removed (errors and abandoned counted as independent)."""
    rows_out = []
    for ai, a in enumerate(accepts):
        reps = [_replicate("flat", seed0 + 5000 + 100 * ai + i, variant, 0, {"m0": 0.30, "accept": a, "cue_p": 0.95}) for i in range(n_rep)]
        rows_out.append({
            "accept_rate": a, "n_learners": len(reps),
            "independence_minus_truth": _stat([r["ind_bias"] for r in reps], ai),
            "independence_share": _stat([r["ind_share"] for r in reps], ai),
            "independence_share_guards_removed": _stat([r["naive_ind"] for r in reps], ai),
            "composite": _stat([r["comp_est"] for r in reps], ai), "true_independence": _stat([r["true_ind"] for r in reps], ai),
        })
    return {"rows": rows_out, "reading": "flat learners whose true skill never changes; a rising score as acceptance falls is gaming inflation"}


def validate_all(*, fast: bool = False, seed0: int = DEV_SEED0) -> dict[str, Any]:
    t0 = time.time()
    n = 12 if fast else 60
    v = validate_score(seed0=seed0, n_rep=n, n_boot_trend=120 if fast else 200)
    g = gaming_sweep(seed0=seed0, n_rep=10 if fast else 40)
    return {
        "meta": analytic_meta("synthetic", n * len(KINDS), "simulated learners", f"replicate seeds {seed0}..{seed0 + n - 1} per kind",
                              note="Simulated learners with planted curves and known truth; nobody here is a person."),
        "design": {"kinds": list(KINDS), "skills": len(SKILLS), "occurrences_per_skill": N_PER_SKILL, "early_checkpoint": CHECK, "window": S.WINDOW,
                   "guess": SL.GUESS, "variants": list(VARIANTS), "seconds": round(time.time() - t0, 1)},
        "variants": v, "gaming": g,
    }
