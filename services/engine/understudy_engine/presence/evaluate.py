"""Held-out evaluation of presence: map calibration, window-forecast calibration, and the decision rule (ANA-12, OFF-3).

Everything is measured on days the model never saw, against baselines, with intervals. ``evaluate_presence``
returns a plain dict for the eval harness (``origin``, ``n``, ``n_unit``, ``split``, ``interval_level``, ``metrics``,
``baselines``). Two splits are reported: ``forward`` (train on the first days, test on the last block; how it
would be used) and ``interleaved`` (every k-th day held out; robust to a schedule change in the data).

Three questions:

1. **Map.** Does P(active) for a held-out bin match how often the worker was active? Brier score and reliability
   against (a) the pack prior only, (b) one global rate, (c) the per-bin empirical frequency without smoothing.
2. **Window forecast.** For a spell that is ``u`` minutes old, does ``S(D | t, u)`` match how often it lasted ``D``
   more minutes? Brier and reliability against (a) pooled survival with no time of week, (b) an exponential
   with the pooled mean.
3. **Decision.** Replaying held-out spells, how often does "start only if S > L / (G + L)" collide with the worker's
   return (the interruption rate, against a cap), and how much idle time does it use, against two baselines: a fixed
   overnight window, and "run whenever idle five minutes".
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from .model import PresenceModel, PriorHours, Smoothing
from .survival import ReturnTimeModel, SurvivalConfig, loss_for_cap, threshold
from .timeline import ACTIVE, SLOTS, DayObs, Spell

WINDOW_GRID = (15, 30, 60, 120, 240)


# ------------------------------------------------------------------------------ small stats helpers
def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2)) if len(p) else float("nan")


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))) if len(p) else float("nan")


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> tuple[list[dict[str, float]], float]:
    """Reliability table and expected calibration error (equal-width bins)."""
    out, ece = [], 0.0
    if len(p) == 0:
        return out, float("nan")
    idx = np.minimum((p * bins).astype(int), bins - 1)
    for b in range(bins):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append({"p_mean": round(float(p[m].mean()), 4), "freq": round(float(y[m].mean()), 4), "n": int(m.sum())})
        ece += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return out, float(ece)


def boot_ci(values_by_cluster: Sequence[np.ndarray | float], stat=np.mean, n_boot: int = 400, seed: int = 11) -> list[float]:
    """Cluster bootstrap (resample days) of a statistic computed over the concatenated cluster values."""
    clusters = [np.atleast_1d(np.asarray(v, dtype=float)) for v in values_by_cluster]
    clusters = [c for c in clusters if len(c)]
    if len(clusters) < 2:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    n = len(clusters)
    vals = []
    for _ in range(n_boot):
        pick = rng.integers(0, n, n)
        vals.append(stat(np.concatenate([clusters[i] for i in pick])))
    return [round(float(np.quantile(vals, 0.025)), 4), round(float(np.quantile(vals, 0.975)), 4)]


def _ratio_ci(num_by_day: list[float], den_by_day: list[float], n_boot: int = 400, seed: int = 13) -> list[float]:
    num, den = np.array(num_by_day), np.array(den_by_day)
    if len(num) < 2:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        i = rng.integers(0, len(num), len(num))
        d = den[i].sum()
        out.append(num[i].sum() / d if d > 0 else 0.0)
    return [round(float(np.quantile(out, 0.025)), 4), round(float(np.quantile(out, 0.975)), 4)]


# ------------------------------------------------------------------------------ splits
def split_days(days: Sequence[DayObs], mode: str, test_frac: float = 0.3, every: int = 3) -> tuple[list[DayObs], list[DayObs]]:
    days = list(days)
    if mode == "forward":
        cut = max(1, int(round(len(days) * (1 - test_frac))))
        return days[:cut], days[cut:]
    if mode == "interleaved":
        test = [d for i, d in enumerate(days) if i % every == every - 1]
        train = [d for i, d in enumerate(days) if i % every != every - 1]
        return train, test
    raise ValueError(mode)


# ------------------------------------------------------------------------------ 1. map
def evaluate_map(train: Sequence[DayObs], test: Sequence[DayObs], prior: PriorHours, smoothing: Smoothing | None = None,
                 tune: bool = True, n_boot: int = 400) -> dict[str, Any]:
    model = PresenceModel(prior, smoothing).fit(train)
    if tune and smoothing is None and len(train) >= 7:
        model.tune(train, fast=n_boot < 400)  # smoothing weights picked on the last 30% of the training days only
    unsmoothed = PresenceModel(prior, Smoothing(0, 0, 0, 0, prior_strength=0.5)).fit(train)
    prior_only = prior.prior_probs()[..., ACTIVE]
    global_rate = float(np.mean([(d.states == ACTIVE).mean() for d in train])) if train else 0.1
    preds = {
        "model": model.p_active(), "prior_only": prior_only,
        "global_rate": np.full((7, SLOTS), global_rate), "unsmoothed": unsmoothed.p_active(),
    }
    per_day = {k: [] for k in preds}
    ps, ys = {k: [] for k in preds}, []
    for d in test:
        y = (d.states == ACTIVE).astype(float)
        ys.append(y)
        for k, mat in preds.items():
            p = mat[d.day.weekday()]
            per_day[k].append((p - y) ** 2)
            ps[k].append(p)
    y_all = np.concatenate(ys) if ys else np.array([])
    sm = model.smoothing
    out: dict[str, Any] = {"n_test_days": len(test), "n_bins": int(len(y_all)),
                           "smoothing": {"adjacent1": sm.adjacent1, "adjacent2": sm.adjacent2, "same_class": sm.same_class, "other_class": sm.other_class,
                                         "half_life_days": sm.half_life_days}}
    for k in preds:
        p_all = np.concatenate(ps[k]) if ps[k] else np.array([])
        out[k] = {"brier": round(brier(p_all, y_all), 5), "log_loss": round(log_loss(p_all, y_all), 5),
                  "brier_ci": boot_ci(per_day[k], n_boot=n_boot)}
    rel, ece = reliability(np.concatenate(ps["model"]) if ps["model"] else np.array([]), y_all)
    out["reliability"], out["ece"] = rel, round(ece, 5)
    lo, hi = model.active_interval()
    # a coarse check on spread: share of held-out bins whose outcome lies within 1.96 sd of the predicted Bernoulli
    inside = []
    for d in test:
        y = (d.states == ACTIVE).astype(float)
        p = model.p_active()[d.day.weekday()]
        sd = np.sqrt(np.maximum(p * (1 - p), 1e-9))
        inside.append(np.abs(y - p) <= 1.96 * sd)
    out["outcome_within_1.96_sd"] = round(float(np.mean(np.concatenate(inside))), 4) if inside else None
    out["idle_capacity_h"] = model.idle_capacity_interval(n_boot=max(40, n_boot // 2))
    out["mean_interval_width"] = round(float((hi - lo).mean()), 4)
    return out


# ------------------------------------------------------------------------------ 2. window forecast
def _tow(s: Spell, u: float) -> float:
    return (s.dow * 1440 + s.tod_min + u) % 10080


def evaluate_windows(train_spells: Sequence[Spell], test_spells: Sequence[Spell], *, cfg: SurvivalConfig | None = None,
                     u0: float = 5.0, grid: Sequence[int] = WINDOW_GRID, day_of: Any = None, n_boot: int = 400) -> dict[str, Any]:
    rt = ReturnTimeModel(train_spells, cfg)
    ps, pp, pe, ys, cluster = [], [], [], [], []
    for s in test_spells:
        if s.duration_min < u0:
            continue
        for D in grid:
            ps.append(rt.survival(D, _tow(s, u0), u0).survival)
            pp.append(rt.pooled_survival(D, u0))
            pe.append(rt.memoryless_survival(D))
            ys.append(1.0 if s.duration_min >= u0 + D else 0.0)
            cluster.append(day_of(s) if day_of else 0)
    p, q, e, y = (np.array(a) for a in (ps, pp, pe, ys))
    out: dict[str, Any] = {"n_pairs": int(len(y)), "n_spells": int(len({id(s) for s in test_spells if s.duration_min >= u0})), "u0_min": u0, "grid_min": list(grid)}
    if len(y) == 0:
        return out
    cl = np.array([hash(c) for c in cluster])
    for name, arr in (("model", p), ("pooled", q), ("exponential", e)):
        by = [((arr - y) ** 2)[cl == c] for c in np.unique(cl)]
        out[name] = {"brier": round(brier(arr, y), 5), "log_loss": round(log_loss(arr, y), 5), "brier_ci": boot_ci(by, n_boot=n_boot)}
    rel, ece = reliability(p, y)
    out["reliability"], out["ece"] = rel, round(ece, 5)
    out["by_d_min"] = {}
    for i, D in enumerate(grid):
        m = np.arange(len(y)) % len(grid) == i
        out["by_d_min"][str(D)] = {"n": int(m.sum()), "mean_pred": round(float(p[m].mean()), 4), "freq": round(float(y[m].mean()), 4)}
    return out


# ------------------------------------------------------------------------------ 3. decision replay
@dataclass
class PolicyResult:
    started: int = 0
    collisions: int = 0
    completed_min: float = 0.0
    completed_runs: int = 0


def _in_window(tod_min: float, start: float = 22 * 60, end: float = 6 * 60) -> bool:
    t = tod_min % 1440
    return t >= start or t < end if start > end else start <= t < end


def replay_policy(spells: Sequence[Spell], policy, *, d_min: float, u0: float = 5.0, recheck_min: float = 15.0,
                  gap_min: float = 1.0) -> PolicyResult:
    """Replay held-out spells. At every decision point the policy sees only (time of week, elapsed idle)."""
    res = PolicyResult()
    for s in spells:
        if s.duration_min < u0:
            continue
        u = u0
        while u + 1e-9 < s.duration_min:
            if policy(s, u):
                res.started += 1
                if s.duration_min - u >= d_min:
                    res.completed_runs += 1
                    res.completed_min += d_min
                    u += d_min + gap_min
                else:
                    res.collisions += 1
                    break
            else:
                u += recheck_min
    return res


def evaluate_decisions(train_spells: Sequence[Spell], test_spells: Sequence[Spell], *, d_min: float = 30.0, cap: float = 0.10,
                       gain: float = 1.0, cfg: SurvivalConfig | None = None, u0: float = 5.0, day_of: Any = None,
                       window: tuple[float, float] = (22 * 60, 6 * 60), n_boot: int = 400) -> dict[str, Any]:
    rt = ReturnTimeModel(train_spells, cfg)
    loss = loss_for_cap(gain, cap)
    thr = threshold(gain, loss)

    def ours(s: Spell, u: float) -> bool:
        return rt.survival(d_min, _tow(s, u), u).survival > thr

    def overnight(s: Spell, u: float) -> bool:
        return _in_window((s.tod_min + u) % 1440, *window)

    def always(s: Spell, u: float) -> bool:
        return True

    usable = [s for s in test_spells if s.duration_min >= u0]
    total_idle = sum(s.duration_min - u0 for s in usable)
    out: dict[str, Any] = {"d_min": d_min, "cap": cap, "gain": gain, "loss": round(loss, 3), "threshold": round(thr, 4),
                           "n_spells": len(usable), "idle_minutes": round(total_idle, 1)}
    for name, pol in (("rule", ours), ("fixed_overnight", overnight), ("run_whenever_idle_5min", always)):
        res = replay_policy(usable, pol, d_min=d_min, u0=u0)
        # per-day clusters for the idle-use interval
        by_day: dict[Any, list[float]] = {}
        for s in usable:
            by_day.setdefault(day_of(s) if day_of else 0, [0.0, 0.0])
            by_day[day_of(s) if day_of else 0][1] += s.duration_min - u0
        # replay again per day to attribute used time (cheap: spells are few)
        used_by_day: dict[Any, float] = {k: 0.0 for k in by_day}
        for s in usable:
            used_by_day[day_of(s) if day_of else 0] += replay_policy([s], pol, d_min=d_min, u0=u0).completed_min
        keys = list(by_day)
        rate = res.collisions / res.started if res.started else 0.0
        out[name] = {
            "runs_started": res.started, "collisions": res.collisions, "completed_runs": res.completed_runs,
            "interruption_rate": round(rate, 4), "interruption_ci": wilson(res.collisions, res.started),
            "share_idle_used": round(res.completed_min / total_idle, 4) if total_idle else 0.0,
            "share_idle_used_ci": _ratio_ci([used_by_day[k] for k in keys], [by_day[k][1] for k in keys], n_boot=n_boot),
            "value": round(gain * res.completed_runs - loss * res.collisions, 2),
            "within_cap": bool(rate <= cap),
        }
    return out


# ------------------------------------------------------------------------------ top level
def evaluate_presence(days: Sequence[DayObs], spells: Sequence[Spell], prior: PriorHours | None = None, *,
                      origin: str = "synthetic", d_min: float = 30.0, cap: float = 0.10, tz_offset_s: float = 0.0,
                      note: str | None = None, person: str | None = None, fast: bool = False) -> dict[str, Any]:
    """The plain-dict report for the eval harness. ``days``/``spells`` come from ``timeline`` (times only)."""
    prior = prior or PriorHours()
    days = list(days)
    n_boot = 100 if fast else 400

    def day_of(s: Spell) -> date:
        return date.fromordinal(date(1970, 1, 1).toordinal() + int((s.start + tz_offset_s) // 86400))

    result: dict[str, Any] = {
        "name": "presence", "origin": origin, "n": len(days), "n_unit": "days", "interval_level": 0.95,
        "person": person, "note": note, "by_split": {},
    }
    for mode in ("forward", "interleaved"):
        train, test = split_days(days, mode)
        if len(train) < 3 or len(test) < 1:
            continue
        tr_days, te_days = {d.day for d in train}, {d.day for d in test}
        tr_sp = [s for s in spells if day_of(s) in tr_days]
        te_sp = [s for s in spells if day_of(s) in te_days]
        result["by_split"][mode] = {
            "split": f"{mode}: {len(train)} train days, {len(test)} held-out days",
            "map": evaluate_map(train, test, prior, n_boot=n_boot),
            "window": evaluate_windows(tr_sp, te_sp, day_of=day_of, n_boot=n_boot),
            "decision": evaluate_decisions(tr_sp, te_sp, d_min=d_min, cap=cap, day_of=day_of, n_boot=n_boot),
        }
    primary = result["by_split"].get("forward") or result["by_split"].get("interleaved")
    if primary:
        result["split"] = primary["split"]
        result["metrics"] = {"map": primary["map"], "window": primary["window"], "decision": primary["decision"]}
        result["baselines"] = {
            "map": [k for k in ("prior_only", "global_rate", "unsmoothed")],
            "window": ["pooled", "exponential"],
            "decision": ["fixed_overnight", "run_whenever_idle_5min"],
        }
    return result
