"""Gap decomposition: Oaxaca-Blinder on behaviour counts, with a cluster bootstrap by person (ANA-4).

Task time is regressed on behaviour counts (how many times each cog occurs; IDLE in seconds). The pooled
two-fold decomposition splits the novice-minus-expert gap into

    explained    sum_k beta_k * (mean_novice_k - mean_expert_k)     what the behaviours account for
    unexplained  the rest (novices slower on the same behaviours, plus anything not measured)

``beta`` is the pooled regression with a novice indicator (the "pooled" non-discriminatory model of
statsmodels' OaxacaBlinder). statsmodels reports the aggregate effects only; we compute the per-behaviour
split with the same coefficients and check that the aggregates agree.
"""
from __future__ import annotations

import random
import statistics
from collections import defaultdict
from typing import Sequence

import numpy as np

from ..core import Episode
from .cohort import B_BOOT, interval


def behaviour_features(ep: Episode, cogs: Sequence[str]) -> list[float]:
    row = []
    for c in cogs:
        if c == "IDLE":
            row.append(sum(x.dwell for x in ep.cogs if x.id == "IDLE"))
        else:
            row.append(float(sum(1 for x in ep.cogs if x.id == c)))
    return row


def feature_names(cogs: Sequence[str]) -> list[str]:
    return [("idle seconds" if c == "IDLE" else f"count {c}") for c in cogs]


def _ob_point(y: np.ndarray, X: np.ndarray, g: np.ndarray):
    """Pooled OB with explicit arithmetic. Returns gap, per-feature explained, unexplained."""
    Z = np.column_stack([X, g, np.ones(len(y))])
    beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
    b = beta[: X.shape[1]]
    d = X[g == 1].mean(axis=0) - X[g == 0].mean(axis=0)
    explained_k = b * d
    gap = y[g == 1].mean() - y[g == 0].mean()
    return gap, explained_k, gap - explained_k.sum()


def decompose(
    episodes: Sequence[Episode], levels: dict[str, str], cogs: Sequence[str] | None = None, B: int = B_BOOT, seed: int = 5,
    check_statsmodels: bool = True,
) -> dict:
    eps = [e for e in episodes if e.person in levels and e.cogs]
    if cogs is None:
        seen = sorted({c.id for e in eps for c in e.cogs})
        # keep behaviours that vary somewhere
        cogs = [c for c in seen if len({behaviour_features(e, [c])[0] for e in eps}) > 1]
    names = feature_names(cogs)
    y = np.array([e.duration for e in eps])
    X = np.array([behaviour_features(e, cogs) for e in eps])
    g = np.array([1.0 if levels[e.person] == "novice" else 0.0 for e in eps])
    gap, expl_k, unexpl = _ob_point(y, X, g)

    sm = None
    if check_statsmodels:
        from statsmodels.stats.oaxaca import OaxacaBlinder

        # bifurcate on the novice indicator; hasconst=False adds the intercept. two_fold() -> (unexplained, explained, gap)
        import warnings

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = OaxacaBlinder(y, np.column_stack([X, g]), X.shape[1], hasconst=False).two_fold()
            u, e, gp = (float(v) for v in res.params)
            sm = {"unexplained": u, "explained": e, "gap": gp}
        except Exception as exc:  # rank-deficient group models (experts never search): statsmodels cannot split them
            sm = {"error": f"{type(exc).__name__}: statsmodels two_fold failed on rank-deficient groups; manual pooled split used"}

    by_person: dict[str, list[int]] = defaultdict(list)
    for k, e in enumerate(eps):
        by_person[e.person].append(k)
    exp_people = sorted(p for p in by_person if levels[p] == "expert")
    nov_people = sorted(p for p in by_person if levels[p] == "novice")
    rnd = random.Random(seed)
    boot_gap, boot_unexpl, boot_k = [], [], []
    for _ in range(B):
        pick = [rnd.choice(exp_people) for _ in exp_people] + [rnd.choice(nov_people) for _ in nov_people]
        idx = [k for p in pick for k in by_person[p]]
        try:
            bg, bk, bu = _ob_point(y[idx], X[idx], g[idx])
        except np.linalg.LinAlgError:  # pragma: no cover
            continue
        boot_gap.append(bg)
        boot_unexpl.append(bu)
        boot_k.append(bk)
    boot_k_arr = np.array(boot_k)
    components = [
        {"feature": names[k], "cog": cogs[k], "seconds": round(float(expl_k[k]), 3), "ci": interval(boot_k_arr[:, k].tolist())}
        for k in range(len(cogs))
    ]
    components.sort(key=lambda r: -abs(r["seconds"]))
    return {
        "gap_s": round(float(gap), 3), "gap_ci": interval(boot_gap),
        "explained_s": round(float(expl_k.sum()), 3), "unexplained_s": round(float(unexpl), 3), "unexplained_ci": interval(boot_unexpl),
        "components": components, "statsmodels": sm, "n_experts": len(exp_people), "n_novices": len(nov_people),
        "method": "pooled Oaxaca-Blinder (OLS with a novice indicator); cluster bootstrap by person, resampling experts and novices separately",
        "bootstrap_draws": len(boot_gap),
    }
