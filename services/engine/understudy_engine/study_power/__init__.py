"""Pure-statistics half of the study: what could the pre-registered analysis detect? (EVL-2, EVL-3)

`evaluate_study_power(fast=False)` simulates the exact counterbalanced S1 to S4 design with n = 4 (the real study) and with
n in {8, 12, 16, 24} balanced across the sequences, runs the plan's own analysis on each simulated study, and reports
power, bias, interval coverage and false-positive rate over a grid of true effects and of two nuisances (carry-over from
block 1 to block 2, and a block-order/fatigue shift). It shows what the design COULD see under our assumptions; it says
nothing about whether the effect exists.
"""
from __future__ import annotations

import math

import numpy as np

from understudy_engine.study_power.model import (
    DEFAULT_POP, Population, check_against_real, load_analysis, sequences, sign_flip_p_vec, simulate_differences,
    t_interval_vec, true_effect,
)
from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta
from understudy_engine.trust.stats import wilson_interval

NS = (4, 8, 12, 16, 24)
EFFECTS = (("none", 0.0), ("small", 0.5), ("medium", 1.0), ("large", 2.0))     # gamma, logit points
CARRYOVERS = (0.0, 0.5, 1.0)                                                    # share of block-1 training that transfers
ORDER_EFFECTS = (0.0, -0.7)                                                     # block-2 shift: 0 or fatigue
REPS = 10000
FAST_REPS = 500
LEVEL = 0.95


def _cell(n: int, gamma: float, kappa: float, omega: float, pop: Population, reps: int, seed: int, tau: float) -> dict:
    D = simulate_differences(n, reps, gamma, kappa, omega, pop=pop, seed=seed)
    mean, lo, hi = t_interval_vec(D, LEVEL)
    p = sign_flip_p_vec(D)
    excl = (lo > 0) | (hi < 0)
    excl_pos = lo > 0
    covers = (lo <= tau) & (tau <= hi)
    wins = reps
    ci_p = lambda k: list(wilson_interval(int(k), wins))                         # noqa: E731
    row = {
        "n": n, "true_effect_pp": 100.0 * tau, "carryover": kappa, "order_effect": omega,
        "power_ci": float(excl.mean()),                    # CI excludes 0 (either side)
        "power_ci_positive": float(excl_pos.mean()),       # CI entirely above 0: the directional H1
        "power_p05": float((p < 0.05).mean()),             # exact two-sided sign-flip p < 0.05
        "power_p05_positive": float(((p < 0.05) & (mean > 0)).mean()),
        "bias": float(mean.mean() - tau), "bias_pp": float(100.0 * (mean.mean() - tau)),
        "coverage": float(covers.mean()),
        "false_positive": float(excl.mean()) if gamma == 0.0 else None,
        "false_positive_p05": float((p < 0.05).mean()) if gamma == 0.0 else None,
        "wrong_sign_ci": float((hi < 0).mean()),
        "mean_estimate": float(mean.mean()), "sd_of_estimate": float(mean.std(ddof=1)),
        "median_sd_of_d": float(np.median(D.std(axis=1, ddof=1))),
        "ci_degenerate_share": float((D.std(axis=1, ddof=1) == 0).mean()),   # all differences identical: zero-width interval
        "replications": reps,
        "mc_intervals": {"power_ci": ci_p(excl.sum()), "false_positive": ci_p(excl.sum()) if gamma == 0.0 else None,
                         "power_p05": ci_p((p < 0.05).sum()), "coverage": ci_p(covers.sum())},
    }
    return row, D


def _exact_n4() -> dict:
    """Every possible set of four differences d in {-1, -1/2, 0, 1/2, 1} through the plan's own t interval: which ones exclude 0?"""
    import itertools
    an = load_analysis()
    vals = (-1.0, -0.5, 0.0, 0.5, 1.0)
    pos, neg, tot = [], 0, 0
    for tup in itertools.product(vals, repeat=4):
        m, lo, hi = an.t_interval(list(tup))
        tot += 1
        if lo > 0:
            pos.append((m, tuple(sorted(tup, reverse=True)), (lo, hi)))
        elif hi < 0:
            neg += 1
    multisets = {}
    for m, key, ci in pos:
        multisets[key] = (float(m), (float(ci[0]), float(ci[1])))
    ex = sorted(multisets.items(), key=lambda kv: kv[1][0])
    nondegenerate = [v[0] for k, v in ex if len(set(k)) > 1]
    return {
        "ordered_patterns": tot, "patterns_with_ci_above_zero": len(pos),
        "share_of_patterns_with_ci_above_zero": len(pos) / tot,
        "smallest_mean_with_ci_above_zero": ex[0][1][0] if ex else None,
        "smallest_mean_with_ci_above_zero_and_spread": min(nondegenerate) if nondegenerate else None,
        "every_difference_must_be_at_least": min(min(k) for k, _ in ex) if ex else None,
        "examples_ci_above_zero": [{"d_sorted": list(k), "mean": v[0], "ci": [v[1][0], v[1][1]]} for k, v in ex[:12]],
        "note": "Exact enumeration of the scores the design can produce. When all four d are identical (e.g. 0.5, 0.5, 0.5, 0.5) the "
                "t interval has zero width and 'excludes 0' trivially: a quirk of the plan's method on discrete scores.",
    }


def evaluate_study_power(fast: bool = False, seed: int = 20261107, reps: int | None = None, pop: Population = DEFAULT_POP) -> dict:
    """Monte Carlo of the pre-registered analysis. Deterministic given `seed`. `fast=True`: 500 replications per cell."""
    reps = reps or (FAST_REPS if fast else REPS)
    an = load_analysis()
    multiplier = float(an.stats.t.ppf(1 - (1 - LEVEL) / 2, 3)) / math.sqrt(4)
    taus = {g: true_effect(g, pop) for _, g in EFFECTS}
    rows: list[dict] = []
    fidelity = {"max_abs_diff_ci": 0.0, "max_abs_diff_p": 0.0, "replications_checked": 0, "sign_flip_cells_checked": 0}
    sd_n4: dict[str, np.ndarray] = {}
    for n in NS:
        for label, gamma in EFFECTS:
            for kappa in CARRYOVERS:
                for omega in ORDER_EFFECTS:
                    row, D = _cell(n, gamma, kappa, omega, pop, reps, seed, taus[gamma])
                    row["effect_label"] = label
                    rows.append(row)
                    if kappa == 0.0 and omega == 0.0:
                        chk = check_against_real(D, n_check=15 if n > 8 else 25)
                        fidelity["max_abs_diff_ci"] = max(fidelity["max_abs_diff_ci"], chk["max_abs_diff_ci"])
                        fidelity["replications_checked"] += chk["replications_checked"]
                        if chk["sign_flip_checked_against_plan"]:
                            fidelity["max_abs_diff_p"] = max(fidelity["max_abs_diff_p"], chk["max_abs_diff_p"])
                            fidelity["sign_flip_cells_checked"] += 1
                    if n == 4 and kappa == 0.0 and omega == 0.0:
                        sd_n4[label] = D.std(axis=1, ddof=1)
    min_p = {str(n): 2.0 / 2 ** n for n in NS}
    sd_q = {lab: {q: float(np.quantile(v, q / 100)) for q in (25, 50, 75)} for lab, v in sd_n4.items()}
    exact = _exact_n4()
    needed = {
        "rule": f"the 95% t interval (df = 3) excludes 0 only when the mean of the four differences exceeds {multiplier:.3f} x the "
                f"standard deviation of those four differences",
        "multiplier": multiplier, "max_possible_mean_difference": 1.0,
        "sd_of_the_four_differences_in_simulation": sd_q,
        "needed_mean_at_median_sd": {lab: multiplier * q[50] for lab, q in sd_q.items()},
        "needed_mean_at_median_sd_pp": {lab: 100 * multiplier * q[50] for lab, q in sd_q.items()},
        "exact_enumeration": exact,
        "reading": (f"Of all {exact['ordered_patterns']} possible sets of four differences, only {exact['patterns_with_ci_above_zero']} "
                    f"({exact['share_of_patterns_with_ci_above_zero']:.1%}) put the interval above 0: every one of the four differences must be at "
                    f"least {exact['every_difference_must_be_at_least']:g} (half a point on the 0-to-1 scale), and with any spread the mean must be at "
                    f"least {exact['smallest_mean_with_ci_above_zero_and_spread']:g}. In the simulation the typical spread of the four differences is "
                    f"about {sd_q['none'][50]:.2f}, which would need a mean of about {multiplier * sd_q['none'][50]:.2f}. Only a very large effect, "
                    f"seen in every participant, can show."),
    }
    base = [r for r in rows if r["carryover"] == 0.0 and r["order_effect"] == 0.0]
    n4 = {r["effect_label"]: r for r in base if r["n"] == 4}
    n24 = {r["effect_label"]: r for r in base if r["n"] == 24}
    note = (
        f"Monte Carlo of the pre-registered analysis ({reps} replications per cell, seed {seed}) on the exactly counterbalanced design. "
        f"At n = 4 the smallest attainable two-sided sign-flip p is {min_p['4']:.3f}, so p < 0.05 is impossible (power_p05 = 0 in every "
        f"n = 4 cell). With no nuisance, the t-interval power at n = 4 is {n4['none']['power_ci']:.1%} at no effect (false positives), "
        f"{n4['small']['power_ci']:.1%} / {n4['medium']['power_ci']:.1%} / {n4['large']['power_ci']:.1%} at a "
        f"{n4['small']['true_effect_pp']:.0f} / {n4['medium']['true_effect_pp']:.0f} / {n4['large']['true_effect_pp']:.0f} point effect; "
        f"at n = 24 it is {n24['none']['power_ci']:.1%}, {n24['small']['power_ci']:.1%}, {n24['medium']['power_ci']:.1%}, "
        f"{n24['large']['power_ci']:.1%}. This shows what the design could detect under our assumptions, not that the effect exists.")
    sens = _sensitivity(reps, seed)
    return {
        "rows": rows, "min_p_by_n": min_p, "needed_difference_n4": needed, "note": note,
        "effects": [{"label": lab, "gamma_logit": g, "true_effect_pp": 100.0 * taus[g]} for lab, g in EFFECTS],
        "grid": {"n": list(NS), "carryover": list(CARRYOVERS), "order_effect": list(ORDER_EFFECTS), "replications_per_cell": reps},
        "design": {"sequences": {k: [list(x) for x in v] for k, v in sequences().items()},
                   "people_per_sequence": {str(n): n // 4 for n in NS}},
        "population": {"mu_cliff": pop.mu_cliff, "mu_reconcile": pop.mu_reconcile, "sd_person": pop.sd_person, "sd_skill": pop.sd_skill,
                       "g_uncoached": 0.4},
        "sensitivity": sens,
        "analysis_fidelity": {**{k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in fidelity.items()}, "checked_functions": ["t_interval", "sign_flip_p (n <= 8)"],
                              "note": "The bulk of the replications use a vectorised copy of the plan's t interval and an exact sign-flip table; "
                                      "the plan's own functions were run on the first replications of every no-nuisance cell and agree to rounding."},
        "origin": "synthetic", "n": reps, "n_unit": "replications", "interval_level": LEVEL,
        "split": "Monte Carlo of the pre-registered analysis; counterbalanced S1 to S4, n people balanced across sequences",
        "meta": analytic_meta("synthetic", reps, "replications", "Monte Carlo of the pre-registered analysis (power, bias, coverage)",
                              note="What the study design could detect under our assumptions. Not evidence that an effect exists."),
        "limitations": limitations_for("study_power"),
        "caveats": [
            "Every number depends on invented assumptions: baseline propensities, how much people differ, the size of the training gain, "
            "independent checks within a case, and the form of carry-over and fatigue. The sensitivity block varies the first four.",
            "The estimand is the direct coaching gain averaged over the two skills; carry-over that spills the coached gain onto the other skill "
            "dilutes the contrast and the design cannot cancel it (see bias).",
            "A balanced design cancels a fixed block-2 shift and generic carry-over in expectation, which is why false positives stay near the "
            "nominal rate when the true effect is 0; it adds variance, which costs power.",
            "The plan's t interval is not exact for discrete bounded scores, and it has zero width when all differences are identical; coverage "
            "and the false-positive rate are reported as simulated, with Monte Carlo intervals.",
            "Real participants are four teammates who know the project; demand effects and facilitator bias are not in this model.",
        ],
    }


def _sensitivity(reps: int, seed: int) -> list[dict]:
    scenarios = {
        "low_heterogeneity": Population(sd_person=0.4, sd_skill=0.25),
        "high_heterogeneity": Population(sd_person=1.2, sd_skill=0.8),
        "high_baseline_ceiling": Population(mu_cliff=0.2, mu_reconcile=0.6),
        "low_baseline_floor": Population(mu_cliff=-1.8, mu_reconcile=-1.4),
    }
    out = []
    for name, pop in scenarios.items():
        for n in (4, 24):
            for label, gamma in (("none", 0.0), ("medium", 1.0)):
                tau = true_effect(gamma, pop)
                row, _ = _cell(n, gamma, 0.0, 0.0, pop, max(reps // 2, 200), seed + 1, tau)
                out.append({"scenario": name, "n": n, "effect_label": label, "true_effect_pp": row["true_effect_pp"],
                            "power_ci": row["power_ci"], "power_p05": row["power_p05"], "coverage": row["coverage"],
                            "false_positive": row["false_positive"], "bias_pp": row["bias_pp"]})
    return out


__all__ = ["evaluate_study_power"]
