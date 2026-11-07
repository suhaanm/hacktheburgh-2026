"""Review routing evaluation (ANA-8). Plain-dict output shaped for the Evidence page.

One detailed run: cases are split train / calibration / held-out test; the model learns on train, is
calibrated on the calibration split, the approval threshold is chosen by risk control on the calibration split
(control.py), and the claim 'error rate among auto-approved <= alpha' is CHECKED on the held-out split.
Then `n_resplits` fresh case draws repeat the whole procedure to count how often the held-out check fails, for
the corrected rule and for the naive one.

Also reported: the risk-coverage curve beside two single-signal baselines (agent confidence, worker-vs-agent
disagreement) and random review; a fixed expert-review budget k (send the k riskiest cases to the expert, bound
what is left); expert minutes per case under an ASSUMED per-review time.
"""
from __future__ import annotations

import numpy as np

from understudy_engine.routing.cases import (
    AGENT_FEATURES, COMPLEXITY_FEATURES, FEATURES, TRACE_FEATURES, Cases, simulate_cases, split_indices,
)
from understudy_engine.routing.control import aurc, check_heldout, risk_control, risk_coverage_curve
from understudy_engine.routing.model import RoutingModel
from understudy_engine.trust.calibration import brier, ece, log_loss
from understudy_engine.trust.meta import analytic_meta
from understudy_engine.trust.stats import clopper_pearson, clopper_pearson_upper

REVIEW_MIN_PER_CASE = 10.0   # ASSUMED minutes for an expert to review one agent-worked case


def _fit_scores(cases: Cases, tr, ca, te, columns=None, calibrator: str = "platt"):
    m = RoutingModel(columns=columns, calibrator=calibrator).fit(cases.X[tr], cases.y[tr])
    m.calibrate(cases.X[ca], cases.y[ca])
    return m, m.predict(cases.X[ca]), m.predict(cases.X[te])


def _signal_scores(cases: Cases) -> dict[str, np.ndarray]:
    """Single-signal rankings, higher = riskier. Only the ORDER matters for risk control."""
    rng = np.random.default_rng(12345)
    return {
        "agent_confidence_only": 1.0 - cases.col("agent_confidence"),
        "disagreement_only": cases.col("disagree") + 1e-6 * rng.random(cases.n),  # tiny jitter breaks the many ties at 0
        "random": rng.random(cases.n),
    }


def _budget(risk_cal, y_cal, risk_te, y_te, budget: float, review_min: float, delta: float) -> dict:
    """Fixed expert budget k: in a batch of N cases the k = budget * N highest-risk go to the expert exactly, the
    rest are auto-approved. The calibration split gives the bound that this budget can guarantee: the exact upper
    bound on the error rate among the lowest-risk (1 - budget) share of calibration cases."""
    def split_at(risk: np.ndarray) -> float:
        k_auto = int(np.floor((1 - budget) * risk.size))
        return float(np.sort(risk)[k_auto - 1]) if k_auto > 0 else -np.inf

    thr_cal = split_at(risk_cal)
    auto_cal = risk_cal <= thr_cal
    k_cal, e_cal = int(auto_cal.sum()), int(y_cal[auto_cal].sum())
    n = risk_te.size
    k_review = int(round(budget * n))
    order = np.argsort(-risk_te, kind="mergesort")           # riskiest first
    review = np.zeros(n, bool)
    review[order[:k_review]] = True
    k, e = int((~review).sum()), int(y_te[~review].sum())
    caught = int(y_te[review].sum())
    return {
        "budget_share": budget, "reviewed": int(review.sum()), "auto_approved": k,
        "guaranteed_error_upper_bound_cal": clopper_pearson_upper(e_cal, k_cal, delta) if k_cal else 1.0,
        "held_out_error": e / k if k else None, "held_out_ci": list(clopper_pearson(e, k)) if k else None,
        "errors_escaping": e, "errors_caught_by_expert": caught,
        "errors_total": int(y_te.sum()), "share_of_errors_caught": caught / max(1, int(y_te.sum())),
        "expert_minutes_per_case": float(review.mean() * review_min),
    }


def _one_resplit(seed: int, n: int, alpha: float, delta: float, correction: str) -> dict:
    c = simulate_cases(n, seed)
    tr, ca, te = split_indices(c.n, seed)
    _, rc, rt = _fit_scores(c, tr, ca, te)
    ctl = risk_control(rc, c.y[ca], alpha, delta, correction=correction)
    chk = check_heldout(ctl["threshold"], rt, c.y[te], alpha)
    return {"coverage": chk["coverage"], "error": chk["error_rate"], "violated": chk["violated"],
            "within_alpha": chk["observed_within_alpha"], "feasible": ctl["feasible"]}


def evaluate_routing(cases: Cases | None = None, *, alpha: float = 0.05, delta: float = 0.05, budget: float = 0.30,
                     seed: int = 0, n_cases: int = 4000, n_resplits: int = 40, resplit_n: int = 3000,
                     review_min: float = REVIEW_MIN_PER_CASE, n_grid: int = 40) -> dict:
    cases = cases or simulate_cases(n_cases, seed)
    tr, ca, te = split_indices(cases.n, seed)
    y_cal, y_te = cases.y[ca], cases.y[te]
    model, rc, rt = _fit_scores(cases, tr, ca, te)
    raw_te = model.raw(cases.X[te])

    ctl = risk_control(rc, y_cal, alpha, delta, n_grid=n_grid, correction="bonferroni")
    chk = check_heldout(ctl["threshold"], rt, y_te, alpha)
    naive = risk_control(rc, y_cal, alpha, delta, n_grid=n_grid, correction="none")
    naive_chk = check_heldout(naive["threshold"], rt, y_te, alpha)

    curve_pts = risk_coverage_curve(rt, y_te, n_points=40, delta=delta)
    curve = [{"coverage": p["coverage"], "risk": p["error_rate"], "ci": p["ci"], "n": p["n"],
              "upper_bound": p["upper_bound"]} for p in curve_pts]

    # baselines and ablations: same risk control, same splits
    sigs = _signal_scores(cases)
    baselines = {}
    for name, sc in sigs.items():
        c_ = risk_control(sc[ca], y_cal, alpha, delta, n_grid=n_grid)
        k_ = check_heldout(c_["threshold"], sc[te], y_te, alpha)
        baselines[name] = {"certified_coverage_cal": c_["coverage"], "held_out_coverage": k_["coverage"],
                           "held_out_error": k_["error_rate"], "violated": k_["violated"],
                           "aurc": aurc(risk_coverage_curve(sc[te], y_te))}
    ablation = {}
    groups = {"complexity_only": COMPLEXITY_FEATURES, "worker_trace_only": TRACE_FEATURES,
              "agent_signals_only": AGENT_FEATURES, "all_features": FEATURES}
    for name, feats in groups.items():
        cols = [FEATURES.index(f) for f in feats]
        _, rc_g, rt_g = _fit_scores(cases, tr, ca, te, columns=cols)
        c_ = risk_control(rc_g, y_cal, alpha, delta, n_grid=n_grid)
        k_ = check_heldout(c_["threshold"], rt_g, y_te, alpha)
        ablation[name] = {"held_out_coverage": k_["coverage"], "held_out_error": k_["error_rate"],
                          "violated": k_["violated"], "aurc": aurc(risk_coverage_curve(rt_g, y_te)),
                          "log_loss": log_loss(y_te, rt_g)}
    prior_curve = risk_coverage_curve(cases.p_true[te], y_te)   # ranking by the case's TRUE prior error probability

    # repeated fresh draws: how often does the held-out check fail?
    reps = {}
    for corr in ("bonferroni", "none"):
        rows = [_one_resplit(seed + 1000 + i, resplit_n, alpha, delta, corr) for i in range(n_resplits)]
        reps[corr] = {
            "n_resplits": n_resplits,
            "violation_rate": float(np.mean([r["violated"] for r in rows])),
            "observed_over_alpha_rate": float(np.mean([not r["within_alpha"] for r in rows])),
            "mean_held_out_error": float(np.mean([r["error"] for r in rows if r["error"] is not None])),
            "mean_coverage": float(np.mean([r["coverage"] for r in rows])),
            "share_with_certified_set": float(np.mean([r["feasible"] for r in rows])),
        }

    review_share = 1.0 - chk["coverage"]
    out = {
        # --- keys the Evidence page reads
        "alpha": alpha,
        "curve": curve,
        "chosen_coverage": chk["coverage"],
        "held_out_error": chk["error_rate"],
        "held_out_ci": chk["ci"],
        "bound_held": (not chk["violated"]),
        "expert_minutes_per_case": review_share * review_min,
        # --- detail
        "origin": cases.origin, "n": cases.n, "n_unit": "households",
        "split": f"train {tr.size} / calibration {ca.size} / held-out {te.size}",
        "interval_level": 0.95, "delta": delta,
        "bound_held_definition": "the held-out data does not contradict 'true error rate of the auto-approved set <= alpha': "
                                 "the lower end of its Clopper-Pearson interval is not above alpha",
        "held_out_within_alpha": chk["observed_within_alpha"],
        "risk_control": {k: v for k, v in ctl.items() if k != "grid"},
        "risk_control_naive": {**{k: v for k, v in naive.items() if k != "grid"}, "held_out": naive_chk},
        "held_out": chk,
        "base_error_rate": float(cases.y.mean()),
        "expert_minutes_review_all": review_min,
        "review_minutes_assumed_per_case": review_min,
        "calibration": {"ece_raw": ece(y_te, raw_te), "ece_calibrated": ece(y_te, rt), "brier": brier(y_te, rt),
                        "log_loss": log_loss(y_te, rt), "log_loss_base_rate": log_loss(y_te, np.full(te.size, cases.y[tr].mean())),
                        "calibrator": "platt"},
        "aurc_model": aurc(curve_pts), "aurc_true_prior_probability": aurc(prior_curve),
        "baselines": baselines, "feature_ablation": ablation,
        "fixed_review_budget": _budget(rc, y_cal, rt, y_te, budget, review_min, delta),
        "random_review_at_budget": {"budget_share": budget, "expected_held_out_error": float(cases.y[te].mean())},
        "resplits": reps,
        "meta": analytic_meta(cases.origin, cases.n, "households",
                              f"train {tr.size} / calibration {ca.size} / held-out {te.size}",
                              note="Auto-approve the safest cases, send the rest to an expert. Synthetic cases with a known error mechanism."),
        "caveats": [
            "Synthetic cases drawn from a mechanism we wrote; no real agent errors were used. The bound is a statement about this generator.",
            "The guarantee covers the error rate of the auto-approved set under exchangeable cases; distribution shift (a new benefit rule, "
            "a new calculator site) breaks it silently.",
            f"Expert review time ({review_min:g} min per case) is an assumption, not a measurement.",
            "The held-out interval is exact for the approved cases but wide when few are approved; a point estimate under alpha is not the same as a proof.",
            "The true-prior ranking (generator's error probability before the outcome) is shown for reference. The model can beat it "
            "because worker-versus-agent disagreement and agent confidence are generated from the realised error, as they would be in practice.",
        ],
    }
    return out
