"""Leave-one-person-out evaluation of the stuck hazard, with baselines and event-level scoring.

`evaluate_hazard(episodes)` returns a plain dict (JSON-safe) that `routes_analytics` and the eval
harness reuse. The protocol, in words:

  outer loop   hold one person out
  inner loop   on the remaining people only, leave one out again to get out-of-fold probabilities,
               then pick the alarm threshold (and 1 or 2 confirming bins) that maximises detected stuck
               events subject to the false-alarm budget (alarms per non-stuck hour)
  score        train on all remaining people, predict the held-out person, apply the chosen alarm rule

So the held-out person influences neither the model nor the threshold. The same procedure is applied
to the base-rate and time-since-progress baselines.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np

from understudy_engine.core import Episode
from understudy_engine.hazard.events import EventResult, choose_config, pool, score_rows
from understudy_engine.hazard.features import BinTable, build_bins
from understudy_engine.hazard.model import HazardModel
from understudy_engine.trust.calibration import (
    cluster_bootstrap_scores, ece, log_loss, brier, reliability_bins,
)

DEFAULT_BUDGET_PER_H = 1.0
LEVEL = 0.95


def _lopo_variant(tab: BinTable, variant: str, budget: float, l2: float) -> dict:
    people = tab.people
    p_oof = np.full(tab.n, np.nan)
    cfgs: dict[str, dict] = {}
    per_ep = {}
    ep_of_person = {q: [e for e, pp in enumerate(tab.ep_person) if pp == q] for q in people}
    for o in people:
        rest = [q for q in people if q != o]
        rows_o = tab.rows_of([o])
        rows_rest = tab.rows_of(rest)
        p_in = np.full(tab.n, np.nan)
        if len(rest) >= 2:
            for q in rest:
                tr = tab.rows_of([x for x in rest if x != q])
                te = tab.rows_of([q])
                p_in[te] = HazardModel(variant, l2).fit(tab, tr).predict(tab, te)
            inner = "leave-one-person-out within training people"
        else:  # two people only: no honest inner split exists
            m_in = HazardModel(variant, l2).fit(tab, rows_rest)
            p_in[rows_rest] = m_in.predict(tab, rows_rest)
            inner = "in-sample (only one training person)"
        eps_rest = [e for q in rest for e in ep_of_person[q]]
        cfg = choose_config(tab, p_in, eps_rest, budget)
        cfg["inner"] = inner
        model = HazardModel(variant, l2).fit(tab, rows_rest)
        p_oof[rows_o] = model.predict(tab, rows_o)
        _, per = score_rows(tab, p_oof, ep_of_person[o], cfg["threshold"], confirm_bins=cfg["confirm_bins"])
        per_ep.update(per)
        cfgs[o] = cfg
    return {"p": p_oof, "cfg": cfgs, "per_episode": per_ep, "ep_of_person": ep_of_person}


def oof_predictions(episodes: list[Episode], *, variant: str = "full", l2: float = 3.0) -> tuple[BinTable, np.ndarray]:
    """Plain leave-one-person-out predictions for every bin (no threshold selection). For downstream
    consumers (the dignity gate, the policy simulator) that need held-out probabilities per bin."""
    tab = build_bins(episodes)
    people = tab.people
    if len(people) < 2:
        raise ValueError("leave-one-person-out needs at least two people")
    p = np.full(tab.n, np.nan)
    for o in people:
        tr = tab.rows_of([q for q in people if q != o])
        te = tab.rows_of([o])
        p[te] = HazardModel(variant, l2).fit(tab, tr).predict(tab, te)
    return tab, p


def _event_ci(per_ep: dict, n_boot: int, seed: int) -> dict:
    """Cluster bootstrap (episodes) for detection rate and FA/h given the already-fixed alarm rules."""
    eps = sorted(per_ep)
    if not eps:
        return {}
    ne = np.array([per_ep[e].n_events for e in eps], float)
    de = np.array([per_ep[e].detected for e in eps], float)
    fa = np.array([per_ep[e].false_alarms for e in eps], float)
    nh = np.array([per_ep[e].non_event_h for e in eps], float)
    rng = np.random.default_rng(seed)
    det, far = [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(eps), size=len(eps))
        if ne[pick].sum() > 0:
            det.append(de[pick].sum() / ne[pick].sum())
        if nh[pick].sum() > 0:
            far.append(fa[pick].sum() / nh[pick].sum())
    q = lambda d: [float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))] if d else None  # noqa: E731
    return {"detection_rate_ci": q(det), "false_alarms_per_hour_ci": q(far)}


def _paired_delta_ci(loss_a: np.ndarray, loss_b: np.ndarray, clusters: np.ndarray, n_boot: int, seed: int) -> list[float]:
    """CI for mean(loss_a) - mean(loss_b), resampling clusters."""
    uniq, inv = np.unique(clusters, return_inverse=True)
    c = uniq.size
    n_c = np.bincount(inv, minlength=c).astype(float)
    d_c = np.bincount(inv, weights=loss_a - loss_b, minlength=c)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, c, size=c)
        draws.append(d_c[pick].sum() / n_c[pick].sum())
    return [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))]


def _pointwise_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(pc) + (1 - y) * np.log(1 - pc))


def _summ(tab: BinTable, res: dict, n_boot: int, seed: int) -> dict:
    y = tab.y.astype(float)
    p = res["p"]
    ci = cluster_bootstrap_scores(y, p, tab.episode, n_boot=n_boot, seed=seed)
    pooled = pool(res["per_episode"].values())
    evci = _event_ci(res["per_episode"], n_boot, seed)
    return {
        "log_loss": log_loss(y, p), "brier": brier(y, p), "ece": ece(y, p),
        "ci_log_loss": list(ci["log_loss"]), "ci_brier": list(ci["brier"]), "ci_ece": list(ci["ece"]),
        "events": {**pooled.as_dict(), **evci},
    }


def evaluate_hazard(
    episodes: list[Episode], *, budget_per_h: float = DEFAULT_BUDGET_PER_H, l2: float = 3.0,
    n_boot: int = 300, seed: int = 0, include_series: bool = True,
) -> dict:
    """Run the full protocol. Needs episodes from at least two people."""
    tab = build_bins(episodes)
    people = tab.people
    if len(people) < 2:
        raise ValueError("leave-one-person-out needs at least two people")
    origins = {e.origin for e in episodes}
    origin = origins.pop() if len(origins) == 1 else "mixed"

    full = _lopo_variant(tab, "full", budget_per_h, l2)
    tsp = _lopo_variant(tab, "tsp", budget_per_h, l2)
    base = _lopo_variant(tab, "base", budget_per_h, l2)
    y = tab.y.astype(float)

    s_full = _summ(tab, full, n_boot, seed)
    s_tsp = _summ(tab, tsp, n_boot, seed)
    s_base = _summ(tab, base, n_boot, seed)
    lf, lt, lb = (_pointwise_loss(y, r["p"]) for r in (full, tsp, base))

    per_person = {}
    for q in people:
        rows = tab.rows_of([q])
        per_person[q] = {
            "n_bins": int(rows.size), "stuck_rate": float(y[rows].mean()),
            "model": {"log_loss": log_loss(y[rows], full["p"][rows]), "brier": brier(y[rows], full["p"][rows])},
            "time_since_progress": {"log_loss": log_loss(y[rows], tsp["p"][rows]), "brier": brier(y[rows], tsp["p"][rows])},
            "base_rate": {"log_loss": log_loss(y[rows], base["p"][rows]), "brier": brier(y[rows], base["p"][rows])},
            "alarm_rule": {k: full["cfg"][q][k] for k in ("threshold", "confirm_bins", "budget_met")},
            "events": pool(full["per_episode"][e] for e in full["ep_of_person"][q]).as_dict(),
        }

    out = {
        "origin": origin,
        "n": len(people), "n_unit": "people",
        "n_bins": tab.n, "n_episodes": len(tab.ep_person), "n_stuck_bins": int(y.sum()),
        "split": "leave-one-person-out",
        "interval_level": LEVEL,
        "interval_note": "Intervals resample episodes (clusters) within the pooled held-out predictions; "
                         "they do not capture person-to-person variation (see per_person).",
        "budget_fa_per_hour": budget_per_h,
        "model": s_full,
        "baselines": {"base_rate": s_base, "time_since_progress": s_tsp},
        "model_minus_tsp_log_loss": float(lf.mean() - lt.mean()),
        "model_minus_tsp_log_loss_ci": _paired_delta_ci(lf, lt, tab.episode, n_boot, seed),
        "model_minus_base_log_loss": float(lf.mean() - lb.mean()),
        "model_minus_base_log_loss_ci": _paired_delta_ci(lf, lb, tab.episode, n_boot, seed),
        "calibration": reliability_bins(y, full["p"]),
        "false_alarms_per_hour": s_full["events"].get("false_alarms_per_hour"),
        "per_person": per_person,
        "params": {"bin_s": tab.bin_s, "horizon_s": tab.horizon_s, "l2": l2, "n_boot": n_boot, "seed": seed},
        "caveats": [
            "Labels and events are defined from `progress` events in the data; the model predicts 'no progress in the next 60 s', not 'the person is confused'.",
            "Intervals resample episodes, not people; with few people the person-level spread (per_person) is the honest uncertainty.",
            "Alarm threshold is chosen on training people only; the false-alarm budget is a design choice, not a measured tolerance of real workers.",
            "Synthetic origin: results show the pipeline recovers planted structure, not that real people behave this way."
            if origin != "real" else "Real data: person count is small; treat as indicative.",
        ],
    }
    if include_series:
        series = {}
        for q in people:
            rows = tab.rows_of([q])
            series[q] = [
                {"t": _dt.datetime.fromtimestamp(float(tab.t[r]), tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "p": round(float(full["p"][r]), 5)} for r in rows
            ]
        out["series"] = series
    return out
