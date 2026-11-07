"""Risk-controlled alarm thresholds (M2c, PLAN.md section 6.4): Learn-then-Test with fixed-sequence testing.

Goal: choose the alarm rule (threshold, 1 or 2 confirming bins) so that false alarms per non-stuck hour stay at most the budget alpha with
probability at least 1 - delta over the calibration sample, instead of v1's plain "largest detection with the training false-alarm rate at
most alpha", which overshoots on a held-out person (1.21 an hour against 1.0 in the v1 report).

C1  episode-level, exact. Calibration units are the training people's episodes with their out-of-fold probabilities. For a threshold the
    false-alarm count K over total non-event exposure H is bounded above by the exact one-sided Poisson (Garwood) limit
    ``chi2.ppf(1 - d, 2 K + 2) / 2 / H`` (the Clopper-Pearson analogue for counts). Thresholds are tried from the most conservative down;
    the first one whose bound exceeds alpha stops the search and the previous one is used. Fixed-sequence testing keeps the guarantee for
    the chosen threshold with no multiplicity correction for the threshold grid (the order is fixed in advance and each test is only
    reached if all earlier ones passed); the two confirm options are Bonferroni-corrected (d = delta / 2 each).
    PLAN.md section 6.4 first wrote the bound with Clopper-Pearson on "an episode contains a false alarm" and a Hoeffding bound on the
    exposure; an episode can hold more than one false alarm, so that bound would not bound the rate. The Poisson limit needs the exposure
    only through its observed total. This is recorded as amendment 1.

C2  cluster-aware, approximate. The same search, with the bound replaced by the 95% percentile bootstrap upper limit of the pooled
    false-alarm rate over resamples of the training PEOPLE (so between-person spread enters). No finite-sample guarantee.

STATED GUARANTEE (C1) and what breaks it. If the false alarms of a new episode behave like those of the calibration episodes, i.e.
(i) episodes are exchangeable across the calibration and the target population, (ii) false alarms arrive independently given the exposure
(Poisson), then with probability at least 1 - delta over the calibration sample the chosen rule has a false-alarm rate of at most alpha.
It is a guarantee for a random episode of the POOLED TRAINING POPULATION, not for any given new person. It fails when the new person differs
from the training people (speed, skill, task mix), when a person drifts (they improve over the 21 days), when a person's episodes are
positively correlated (the bound treats them as independent, so it is optimistic by the design effect), and when alarms cluster (over-
dispersion). The held-out check measures how far the claim is from true for new people.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import chi2

from understudy_engine.hazard.events import COOLDOWN_S
from understudy_engine.mlv2.alarms import Layout, choose_config_fast, pooled, score_grid, threshold_grid

DELTA = 0.05
STATED_GUARANTEE = (
    "With probability at least 1 - delta over the calibration sample, the chosen rule's false-alarm rate on a new episode from the pooled "
    "training population is at most the budget, assuming exchangeable episodes and false alarms that arrive independently given the exposure."
)
BREAKS = (
    "a held-out person who differs from the training people (speed, skill, task mix)",
    "a person who drifts (improves) over the weeks",
    "positively correlated episodes within a person (the bound treats episodes as independent)",
    "false alarms that cluster (over-dispersion relative to Poisson)",
)


def poisson_upper(k: float, delta: float) -> float:
    """Exact one-sided upper (1 - delta) confidence limit for a Poisson mean given k events (Garwood); the count analogue of
    ``trust.stats.clopper_pearson_upper``."""
    return float(chi2.ppf(1.0 - delta, 2.0 * k + 2.0) / 2.0)


def rate_upper_poisson(false_alarms: float, exposure_h: float, delta: float) -> float:
    if exposure_h <= 0:
        return float("inf")
    return poisson_upper(false_alarms, delta) / exposure_h


def _search(layout: Layout, p_in: np.ndarray, train_eps: np.ndarray, budget: float, confirm_options: tuple[int, ...], n_thr: int,
            bound_fn, cooldown_s: float = COOLDOWN_S) -> dict:
    """Fixed-sequence search shared by C1 and C2. ``bound_fn(gs, layout, train_eps) -> (n_thr,)`` upper bounds per threshold."""
    train_eps = np.asarray(train_eps, dtype=int)
    if train_eps.size == 0:
        return {"threshold": 1.01, "confirm_bins": 1, "budget_met": False, "validated": 0, "reason": "no training episodes"}
    rows = np.concatenate([np.arange(layout.offsets[e], layout.offsets[e + 1]) for e in train_eps])
    qs = threshold_grid(p_in[rows], n_thr)
    order = np.argsort(-qs)                                  # most conservative first (1.01 = never alarm)
    best = None
    for conf in confirm_options:
        gs = score_grid(layout, p_in, qs, conf, episodes=train_eps, cooldown_s=cooldown_s)
        ub = bound_fn(gs, layout, train_eps)
        pl = pooled(layout, gs, train_eps)
        last_ok = None
        for j in order:
            if ub[j] <= budget:
                last_ok = j
            else:
                break
        if last_ok is None:
            continue
        det = float(pl["detection"][last_ok]) if np.isfinite(pl["detection"][last_ok]) else 0.0
        cand = {"threshold": float(qs[last_ok]), "confirm_bins": conf, "budget_met": True, "bound_per_hour": float(ub[last_ok]),
                "train_fa_per_hour": float(pl["fa_per_hour"][last_ok]), "train_detection_rate": det,
                "validated": int(np.where(order == last_ok)[0][0] + 1)}
        if best is None or (det, -cand["bound_per_hour"]) > (best["train_detection_rate"], -best["bound_per_hour"]):
            best = cand
    if best is None:
        return {"threshold": 1.01, "confirm_bins": 1, "budget_met": False, "validated": 0,
                "reason": "no threshold had a bound within the budget; the rule never alarms"}
    return best


def make_c1_rule(delta: float = DELTA, *, confirm_options: tuple[int, ...] = (1, 2), n_thr: int = 60):
    d = delta / len(confirm_options)

    def bound(gs, layout, train_eps):
        fa = gs.false_alarms[train_eps].sum(axis=0).astype(float)
        h = float(layout.non_event_h[train_eps].sum())
        return np.array([rate_upper_poisson(k, h, d) for k in fa])

    def rule(layout, p_in, train_eps, budget, fold=None):
        out = _search(layout, p_in, train_eps, budget, confirm_options, n_thr, bound)
        out["rule"] = "C1"
        return out

    return rule


def make_c2_rule(tab, *, level: float = 0.95, n_boot: int = 2000, seed: int = 0, confirm_options: tuple[int, ...] = (1, 2), n_thr: int = 60):
    """C2: bootstrap-over-people upper limit of the pooled false-alarm rate (approximate)."""
    ep_person = np.asarray(tab.ep_person, dtype=object)

    def bound(gs, layout, train_eps):
        people = ep_person[train_eps]
        uniq, inv = np.unique(people.astype(str), return_inverse=True)
        C = uniq.size
        h_c = np.bincount(inv, weights=layout.non_event_h[train_eps], minlength=C)
        fa_c = np.zeros((C, gs.false_alarms.shape[1]))
        for c in range(C):
            fa_c[c] = gs.false_alarms[train_eps[inv == c]].sum(axis=0)
        rng = np.random.default_rng(seed)
        pick = rng.integers(0, C, size=(n_boot, C))
        M = np.zeros((n_boot, C))
        np.add.at(M, (np.repeat(np.arange(n_boot), C), pick.ravel()), 1.0)
        num = M @ fa_c                              # (B, n_thr)
        den = (M @ h_c)[:, None]
        with np.errstate(divide="ignore", invalid="ignore"):
            rate = np.where(den > 0, num / den, np.nan)
        return np.nanquantile(rate, level, axis=0)

    def rule(layout, p_in, train_eps, budget, fold=None):
        out = _search(layout, p_in, train_eps, budget, confirm_options, n_thr, bound)
        out["rule"] = "C2"
        return out

    return rule


def make_c0_rule():
    """v1's rule (reference): max detection subject to the training false-alarm rate at most the budget."""
    def rule(layout, p_in, train_eps, budget, fold=None):
        out = choose_config_fast(layout, p_in, train_eps, budget)
        out["rule"] = "C0"
        return out
    return rule
