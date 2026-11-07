"""Agent-claim calibration (ANA-14): predict "the agent claimed success but the code check failed".

Each row is one agent run in which the agent said it was done. The label is 1 when the deterministic
completion check (services/agent completion.py) found the requested result missing. Features are things
known BEFORE that check, taken from the run trace: how many steps, retries, tier escalations and failed
preconditions, how much of the time budget was used, whether two navigators disagreed, and the agent's
own stated confidence. The classifier is a plain logistic regression; the only claim made is that it is
calibrated, which a reliability table shows. Code still decides success; this only says how much to
trust a claim that code has not yet checked.

Evaluation: grouped K-fold (groups = households or tasks, so near-duplicate runs never straddle the
split), beside a base-rate baseline and a "trust the agent's confidence" baseline.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.hazard.logreg import LogisticModel
from understudy_engine.trust.calibration import (
    PlattScaler, cluster_bootstrap_scores, ece, log_loss, brier, reliability_bins, sigmoid,
)

FEATURES = (
    "n_steps", "n_retries", "n_escalations", "n_precondition_failures", "time_ratio",
    "navigators_disagree", "stated_confidence", "n_recoveries",
)


@dataclass
class ClaimRuns:
    X: np.ndarray        # (n, len(FEATURES))
    y: np.ndarray        # 1 = claimed success but code check failed
    group: np.ndarray    # household / task id, for grouped splits
    origin: str = "synthetic"


def simulate_claim_runs(n: int = 600, n_groups: int = 40, seed: int = 0) -> ClaimRuns:
    """Synthetic runs with a known mechanism: failure odds grow with retries, escalations and failed
    preconditions, jump when the time budget is exceeded, and are partly (not fully) visible in the agent's
    stated confidence. A household-level random effect makes some groups harder than others."""
    rng = np.random.default_rng(seed)
    group = rng.integers(0, n_groups, n)
    g_eff = rng.normal(0, 0.5, n_groups)[group]
    steps = rng.integers(8, 26, n).astype(float)
    retries = rng.poisson(0.6 + 0.4 * (g_eff > 0.3), n).astype(float)
    esc = rng.binomial(2, 0.2, n).astype(float)
    pre = rng.poisson(0.4, n).astype(float)
    tratio = np.clip(rng.lognormal(-0.2, 0.4, n), 0.2, 3.0)
    disagree = (rng.random(n) < 0.15).astype(float)
    recov = np.minimum(retries, rng.poisson(0.5, n)).astype(float)
    z = (-3.0 + 0.45 * retries + 0.7 * esc + 0.9 * pre + 1.6 * (tratio > 1.2) + 1.8 * disagree
         + 0.02 * (steps - 15) + g_eff)
    y = (rng.random(n) < sigmoid(z)).astype(int)
    # stated confidence: informative but over-confident and noisy
    conf = np.clip(0.93 - 0.25 * y + rng.normal(0, 0.12, n), 0.05, 0.999)
    X = np.column_stack([steps, retries, esc, pre, tratio, disagree, conf, recov])
    return ClaimRuns(X, y, group)


def _folds(group: np.ndarray, k: int) -> list[np.ndarray]:
    uniq = np.unique(group)
    assign = {g: i % k for i, g in enumerate(uniq)}
    f = np.array([assign[g] for g in group])
    return [np.where(f == i)[0] for i in range(k)]


def _fit_predict(Xtr, ytr, Xte, l2: float) -> np.ndarray:
    m = LogisticModel(l2=l2).fit(Xtr, ytr)
    return m.predict_proba(Xte)


def evaluate_claims(runs: ClaimRuns | None = None, *, k_folds: int = 5, l2: float = 3.0,
                    n_boot: int = 300, seed: int = 0, review_budget: float = 0.2) -> dict:
    """Grouped K-fold evaluation. Returns a plain dict for the Evidence page."""
    runs = runs or simulate_claim_runs(seed=seed)
    X, y, g = runs.X, runs.y.astype(int), runs.group
    n = y.size
    folds = _folds(g, k_folds)
    p_model = np.full(n, np.nan)
    p_conf = np.full(n, np.nan)
    p_base = np.full(n, np.nan)
    conf_col = FEATURES.index("stated_confidence")
    for te in folds:
        tr = np.setdiff1d(np.arange(n), te)
        p_model[te] = _fit_predict(X[tr], y[tr], X[te], l2)
        # baseline 2: take the agent's stated confidence at face value, recalibrated by Platt on the training folds
        sc = np.clip(1 - X[:, conf_col], 1e-3, 1 - 1e-3)
        pl = PlattScaler().fit(sc[tr], y[tr])
        p_conf[te] = pl.transform(sc[te])
        p_base[te] = y[tr].mean()
    ci = cluster_bootstrap_scores(y.astype(float), p_model, g, n_boot=n_boot, seed=seed)

    def pack(p: np.ndarray, with_ci: bool = False) -> dict:
        d = {"log_loss": log_loss(y, p), "brier": brier(y, p), "ece": ece(y, p)}
        if with_ci:
            d.update({"ci_log_loss": list(ci["log_loss"]), "ci_brier": list(ci["brier"]), "ci_ece": list(ci["ece"])})
        return d

    # operating point: send the top `review_budget` share of claims to a human check
    kk = max(1, int(round(review_budget * n)))
    order = np.argsort(-p_model)
    flagged = np.zeros(n, bool)
    flagged[order[:kk]] = True
    caught = int((y[flagged] == 1).sum())
    total_bad = int(y.sum())
    return {
        "origin": runs.origin, "n": int(len(np.unique(g))), "n_unit": "households", "n_runs": int(n),
        "split": f"grouped {k_folds}-fold (by household)", "interval_level": 0.95,
        "base_failure_rate": float(y.mean()),
        "model": pack(p_model, True),
        "baselines": {"base_rate": pack(p_base), "stated_confidence_platt": pack(p_conf)},
        "calibration": reliability_bins(y, p_model),
        "operating_point": {
            "review_share": review_budget, "flagged_runs": int(kk), "false_claims_caught": caught,
            "false_claims_total": total_bad,
            "recall": caught / total_bad if total_bad else None,
            "precision": caught / kk,
        },
        "caveats": [
            "Synthetic runs generated from a known mechanism; real agent traces will differ and this has not been validated on them.",
            "Features are trace summaries, not content; claims about page text cannot be assessed here.",
            "Code still decides success. A low predicted risk never replaces the completion check.",
        ],
    }
