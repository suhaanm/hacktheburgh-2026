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
from understudy_engine.hazard.events import choose_config, pool, score_rows
from understudy_engine.hazard.features import BinTable, build_bins
from understudy_engine.hazard.model import HazardModel
from understudy_engine.trust.limitations import limitations_for
from understudy_engine.trust.meta import analytic_meta
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


def _auc(score: np.ndarray, label: np.ndarray) -> float | None:
    """Mann-Whitney AUC of `score` for `label` (ties get average rank)."""
    from scipy.stats import rankdata
    pos = label == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return None
    ranks = rankdata(score)
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _vs_planted(tab: BinTable, res: dict, planted: dict[str, list[tuple[float, float]]], tol_s: float = 30.0) -> dict:
    """Check held-out predictions against planted stuck spells the model never saw (truth.json).

    bin-level  AUC of p for 'a planted spell overlaps [b, b + 60]'
    spell-level  with each held-out person's chosen alarm rule: share of planted spells with an alarm inside
                 [t0 - tol, t1 + tol], and alarms outside every planted spell per hour
    """
    from understudy_engine.hazard.events import alarms_for
    p = res["p"]
    lab = np.zeros(tab.n, dtype=int)
    for q, spells in planted.items():
        rows = tab.rows_of([q])
        if not rows.size or not spells:
            continue
        t = tab.t[rows]
        for t0, t1 in spells:
            lab[rows[(t + tab.horizon_s > t0) & (t < t1)]] = 1
    n_spells = det = fa = 0
    hours = 0.0
    lat: list[float] = []
    for q in tab.people:
        cfg = res["cfg"][q]
        spells = planted.get(q, [])
        for e in res["ep_of_person"][q]:
            a, b = int(tab.ep_offsets[e]), int(tab.ep_offsets[e + 1])
            t_e, ps = tab.t[a:b], p[a:b]
            lo, hi = t_e[0], t_e[-1] + tab.bin_s
            alarms = alarms_for(t_e, ps, cfg["threshold"], cfg["confirm_bins"])
            hours += (hi - lo) / 3600.0
            mine = [(t0, t1) for t0, t1 in spells if t1 > lo and t0 < hi]
            n_spells += len(mine)
            for t0, t1 in mine:
                inside = alarms[(alarms >= t0 - tol_s) & (alarms <= t1 + tol_s)]
                if inside.size:
                    det += 1
                    lat.append(max(0.0, float(inside.min() - t0)))
            fa += sum(1 for al in alarms if not any(t0 - tol_s <= al <= t1 + tol_s for t0, t1 in mine))
    return {
        "bin_label": "a planted stuck spell overlaps the 60 s after the bin",
        "n_positive_bins": int(lab.sum()), "n_bins": int(tab.n),
        "auc": _auc(p, lab),
        "auc_time_since_progress_proxy": _auc(tab.tsp_s.astype(float), lab),
        "planted_spells": int(n_spells), "detected": int(det),
        "detection_rate": det / n_spells if n_spells else None,
        "alarms_outside_planted_per_hour": float(fa / hours) if hours > 0 else None,
        "median_latency_s": float(np.median(lat)) if lat else None,
        "note": "Planted spells are short (often under 90 s) and independent of the 'no progress in 60 s' label.",
    }


def evaluate_hazard(
    episodes: list[Episode], *, budget_per_h: float = DEFAULT_BUDGET_PER_H, l2: float = 3.0,
    n_boot: int = 300, seed: int = 0, include_series: bool = True,
    planted: dict[str, list[tuple[float, float]]] | None = None, series_person: str | None = None,
    series_max: int | None = 480, note: str | None = None, fast: bool = False,
) -> dict:
    """Run the full protocol. Needs episodes from at least two people. `fast=True` caps bootstrap resamples at 40."""
    if fast:
        n_boot = min(n_boot, 40)
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
        "false_alarms_within_budget": (s_full["events"].get("false_alarms_per_hour") is not None
                                       and s_full["events"]["false_alarms_per_hour"] <= budget_per_h),
        "per_person": per_person,
        "params": {"bin_s": tab.bin_s, "horizon_s": tab.horizon_s, "l2": l2, "n_boot": n_boot, "seed": seed},
        "caveats": [
            "Labels and events are defined from `progress` events in the data; the model predicts 'no progress in the next 60 s', not 'the person is confused'.",
            "Intervals resample episodes, not people; with few people the person-level spread (per_person) is the honest uncertainty.",
            "Alarm threshold is chosen on training people only under the false-alarm budget; it can overshoot on the held-out person "
            "(see false_alarms_within_budget). The budget is a design choice, not a measured tolerance of real workers.",
            "Synthetic origin: results show the pipeline recovers planted structure, not that real people behave this way."
            if origin != "real" else "Real data: person count is small; treat as indicative.",
        ],
    }
    if planted:
        out["vs_planted"] = _vs_planted(tab, full, planted)
    sp = series_person if series_person in people else people[0]

    def _series(q: str) -> list[dict]:
        return [
            {"t": _dt.datetime.fromtimestamp(float(tab.t[r]), tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "p": round(float(full["p"][r]), 5)} for r in tab.rows_of([q])
        ]

    if include_series:
        rep = _series(sp)
        out["series"] = rep[:series_max] if series_max else rep   # contract: [{t, p}] for one person
        out["series_person"] = sp
        out["series_by_person"] = {q: _series(q) for q in people}
    out["limitations"] = limitations_for("hazard")
    out["meta"] = analytic_meta(origin, len(people), "people", "leave-one-person-out", note or (
        f"{tab.n} scored 30-second bins from {len(tab.ep_person)} episodes; label = no progress in the next 60 s."))
    return out


def evaluate_hazard_data(root=None, *, n_boot: int = 300, seed: int = 0, budget_per_h: float = DEFAULT_BUDGET_PER_H,
                         include_series: bool = True, include_secondary: bool = True, fast: bool = False) -> dict:
    """Hazard evaluation on engine-data's synthetic data. Falls back to this module's own simulator when the
    data directory is absent (then `origin` still says synthetic and `data_source` says which).

    Primary: the four personas (21 days each, 3.6k episodes, 4 people). Secondary: the 24 scripted apprentices.
    The primary result is what the Evidence page shows; the secondary is under `secondary` with its own caveat.
    """
    from understudy_engine.hazard.data import load_persona_episodes
    from understudy_engine.hazard.sim import simulate_people

    try:
        eps, planted, info = load_persona_episodes(root)
        source = "engine-data synthetic personas (4 people, 21 days)"
    except FileNotFoundError:
        eps, _ = simulate_people(4, 60, seed=seed)
        planted, info, source = None, {}, "fallback: hazard.sim (engine-data files not found)"
    out = evaluate_hazard(eps, budget_per_h=budget_per_h, n_boot=n_boot, seed=seed, include_series=include_series,
                          planted=planted, series_person="p_ninetofive", fast=fast)
    out["data_source"] = source
    out["data_info"] = info
    if include_secondary:
        sec = evaluate_apprentice_hazard(root, n_boot=n_boot, seed=seed, budget_per_h=budget_per_h,
                                         include_series=include_series, fast=fast)
        if sec is not None:
            out["secondary"] = sec
    return out


def evaluate_apprentice_hazard(root=None, *, n_boot: int = 300, seed: int = 0,
                               budget_per_h: float = DEFAULT_BUDGET_PER_H, include_series: bool = True,
                               fast: bool = False) -> dict | None:
    """The 24 scripted apprentices as a second dataset (None if the files are absent)."""
    from understudy_engine.hazard.data import load_apprentice_episodes
    try:
        a_eps, a_planted, a_info = load_apprentice_episodes(root)
    except FileNotFoundError:
        return None
    sec = evaluate_hazard(a_eps, budget_per_h=budget_per_h, n_boot=n_boot, seed=seed, include_series=include_series,
                          planted=a_planted, series_person="p_nov01", fast=fast)
    sec["data_source"] = "engine-data synthetic apprentices (24 people, 2 scripted cases each)"
    sec["data_info"] = a_info
    sec["caveats"] = sec["caveats"] + [
        "Apprentice traces follow a fixed task script, so when progress happens is partly predictable from the cog "
        "grammar itself; the large gain over the baselines here mostly reflects that, not stuck prediction. "
        "Treat the four-persona result as the headline."]
    return sec
