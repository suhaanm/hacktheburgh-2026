"""Vectorised alarm scoring that reproduces v1's event-level scoring (``hazard.events``) bit for bit, many thresholds at once.

v1 scores one (threshold, confirm_bins) at a time with Python loops over episodes; with 30 to 40 people and a threshold grid that is
hours. This module evaluates the whole grid with numpy, walking position by position through every episode at once and using the same
floating-point expressions as v1 (``t[i] - last >= cooldown`` and ``e0 - tol <= a <= e1 + tol``), so the boundary cases agree. The
tests compare it with v1's functions on random data.

Definitions (from ``hazard.events``): stuck event = maximal run of at least MIN_RUN consecutive label-1 bins; alarm = probability at or
above a threshold for ``confirm_bins`` consecutive bins, at most one per COOLDOWN_S; a true alarm falls inside an event widened by TOL_S;
false alarms per hour use the hours outside stuck events.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from understudy_engine.hazard.events import COOLDOWN_S, MIN_RUN, TOL_S, stuck_events
from understudy_engine.hazard.features import BinTable


@dataclass
class Layout:
    """Label-only structure of a bin table (does not depend on any prediction)."""

    n_ep: int
    n_bins: int
    offsets: np.ndarray        # (n_ep + 1,)
    lengths: np.ndarray        # (n_ep,)
    order: np.ndarray          # episodes sorted by length, longest first
    zone: np.ndarray           # (n_bins,) bool: an alarm at this bin would count as true (v1 condition)
    ev_ep: np.ndarray          # (n_ev,) episode of each stuck event
    ev_lo: np.ndarray          # first bin (global index) inside the event's tolerance window
    ev_hi: np.ndarray          # last bin (global index) inside the window
    n_events: np.ndarray       # (n_ep,)
    non_event_h: np.ndarray    # (n_ep,)
    total_h: np.ndarray        # (n_ep,)
    t: np.ndarray
    bin_s: float


def build_layout(tab: BinTable, *, tol_s: float = TOL_S, min_run: int = MIN_RUN) -> Layout:
    n_ep = len(tab.ep_person)
    off = tab.ep_offsets
    lengths = np.diff(off)
    zone = np.zeros(tab.n, dtype=bool)
    ev_ep: list[int] = []
    ev_lo: list[int] = []
    ev_hi: list[int] = []
    n_events = np.zeros(n_ep, dtype=int)
    non_h = np.zeros(n_ep)
    tot_h = np.zeros(n_ep)
    for e in range(n_ep):
        a, b = int(off[e]), int(off[e + 1])
        t_e, y_e = tab.t[a:b], tab.y[a:b]
        evs = stuck_events(y_e, t_e, tab.bin_s, min_run)
        n_events[e] = len(evs)
        total = t_e.size * tab.bin_s / 3600.0
        ev_h = sum((e1 - e0) for e0, e1 in evs) / 3600.0
        tot_h[e] = total
        non_h[e] = max(0.0, total - ev_h)
        for e0, e1 in evs:
            inside = (t_e >= e0 - tol_s) & (t_e <= e1 + tol_s)      # v1's exact condition
            idx = np.where(inside)[0]
            if idx.size:
                zone[a + idx] = True
                ev_ep.append(e)
                ev_lo.append(a + int(idx[0]))
                ev_hi.append(a + int(idx[-1]))
            else:   # cannot happen for a real event, but keep the event counted as undetectable
                ev_ep.append(e)
                ev_lo.append(a)
                ev_hi.append(a - 1)
    return Layout(
        n_ep=n_ep, n_bins=tab.n, offsets=off, lengths=lengths, order=np.argsort(-lengths, kind="stable"), zone=zone,
        ev_ep=np.array(ev_ep, dtype=int), ev_lo=np.array(ev_lo, dtype=int), ev_hi=np.array(ev_hi, dtype=int),
        n_events=n_events, non_event_h=non_h, total_h=tot_h, t=tab.t, bin_s=tab.bin_s,
    )


@dataclass
class GridScores:
    """Per-episode counts for every threshold of a grid (columns) at one confirm setting."""

    thresholds: np.ndarray     # (n_thr,)
    confirm_bins: int
    false_alarms: np.ndarray   # (n_ep, n_thr) int
    true_alarms: np.ndarray    # (n_ep, n_thr) int
    detected: np.ndarray       # (n_ep, n_thr) int


def score_grid(layout: Layout, p: np.ndarray, thresholds: np.ndarray, confirm_bins: int = 1, *,
               episodes: np.ndarray | None = None, cooldown_s: float = COOLDOWN_S) -> GridScores:
    """Alarm counts per episode for each threshold. ``episodes`` restricts the computation (others stay zero)."""
    thr = np.asarray(thresholds, dtype=float)
    n_ep, n_thr = layout.n_ep, thr.size
    fa = np.zeros((n_ep, n_thr), dtype=np.int32)
    ta = np.zeros((n_ep, n_thr), dtype=np.int32)
    if episodes is None:
        sel = layout.order
    else:
        mask = np.zeros(n_ep, dtype=bool)
        mask[np.asarray(episodes, dtype=int)] = True
        sel = layout.order[mask[layout.order]]
    lens = layout.lengths[sel]
    starts = layout.offsets[sel]
    alarm = np.zeros((layout.n_bins, n_thr), dtype=bool) if layout.ev_ep.size else None
    last = np.full((sel.size, n_thr), -np.inf)
    run = np.zeros((sel.size, n_thr), dtype=np.int32)
    lmax = int(lens.max()) if lens.size else 0
    t = layout.t
    for pos in range(lmax):
        k = int(np.searchsorted(-lens, -pos, side="left"))      # episodes with length > pos are a prefix (sorted desc)
        if k == 0:
            break
        idx = starts[:k] + pos
        above = p[idx][:, None] >= thr[None, :]
        run[:k] = np.where(above, run[:k] + 1, 0)
        cand = run[:k] >= confirm_bins
        tt = t[idx][:, None]
        fire = cand & ((tt - last[:k]) >= cooldown_s)
        last[:k] = np.where(fire, tt, last[:k])
        z = layout.zone[idx][:, None]
        fa[sel[:k]] += (fire & ~z).astype(np.int32)
        ta[sel[:k]] += (fire & z).astype(np.int32)
        if alarm is not None:
            alarm[idx] = fire
    det = np.zeros((n_ep, n_thr), dtype=np.int32)
    if alarm is not None and layout.ev_ep.size:
        cs = np.vstack([np.zeros((1, n_thr), dtype=np.int32), np.cumsum(alarm, axis=0, dtype=np.int32)])
        hit = (cs[layout.ev_hi + 1] - cs[layout.ev_lo]) > 0          # (n_ev, n_thr); empty window -> negative -> False
        if episodes is not None:
            keep = mask[layout.ev_ep]
            hit = hit & keep[:, None]
        np.add.at(det, layout.ev_ep, hit.astype(np.int32))
    return GridScores(thr, confirm_bins, fa, ta, det)


def pooled(layout: Layout, gs: GridScores, episodes: np.ndarray) -> dict[str, np.ndarray]:
    """Pool a grid over episodes: false alarms per hour and detection rate per threshold."""
    ep = np.asarray(episodes, dtype=int)
    fa = gs.false_alarms[ep].sum(axis=0).astype(float)
    ta = gs.true_alarms[ep].sum(axis=0).astype(float)
    det = gs.detected[ep].sum(axis=0).astype(float)
    n_ev = float(layout.n_events[ep].sum())
    non_h = float(layout.non_event_h[ep].sum())
    fa_h = fa / non_h if non_h > 0 else np.full(fa.shape, np.nan)
    det_rate = det / n_ev if n_ev > 0 else np.full(det.shape, np.nan)
    return {"fa": fa, "ta": ta, "det": det, "fa_per_hour": fa_h, "detection": det_rate, "n_events": n_ev, "non_event_h": non_h}


def threshold_grid(pv: np.ndarray, n_thr: int = 60) -> np.ndarray:
    """v1's grid: quantiles 0.30 to 0.9995 of the training probabilities, plus 1.01 meaning 'never alarm'."""
    return np.unique(np.append(np.quantile(pv, np.linspace(0.30, 0.9995, n_thr)), 1.01))


def choose_config_fast(layout: Layout, p_all: np.ndarray, episodes: np.ndarray, budget_per_h: float, *,
                       confirm_options: tuple[int, ...] = (1, 2), n_thr: int = 60, cooldown_s: float = COOLDOWN_S) -> dict:
    """The same selection as ``hazard.events.choose_config`` (max detection subject to FA/h <= budget; ties to fewer false alarms,
    then the higher threshold; fewest false alarms when nothing meets the budget), computed on the vectorised grid."""
    episodes = np.asarray(episodes, dtype=int)
    if episodes.size == 0:
        return {"threshold": 1.01, "confirm_bins": 1, "budget_met": False, "train_fa_per_hour": float("nan"),
                "train_detection_rate": float("nan")}
    rows = np.concatenate([np.arange(layout.offsets[e], layout.offsets[e + 1]) for e in episodes])
    pv = p_all[rows]
    if pv.size == 0:
        return {"threshold": 1.01, "confirm_bins": 1, "budget_met": False, "train_fa_per_hour": float("nan"),
                "train_detection_rate": float("nan")}
    qs = threshold_grid(pv, n_thr)
    best = None
    fallback = None
    for conf in confirm_options:
        gs = score_grid(layout, p_all, qs, conf, episodes=episodes, cooldown_s=cooldown_s)
        pl = pooled(layout, gs, episodes)
        for j, thr in enumerate(qs):
            fa = pl["fa_per_hour"][j]
            det = pl["detection"][j]
            fa = float(fa) if np.isfinite(fa) else 0.0
            det = float(det) if np.isfinite(det) else 0.0
            key = (det, -fa, float(thr))
            if fa <= budget_per_h and (best is None or key > best[0]):
                best = (key, float(thr), conf, fa, det)
            fkey = (-fa, det)
            if fallback is None or fkey > fallback[0]:
                fallback = (fkey, float(thr), conf, fa, det)
    if best is not None:
        _, thr, conf, fa, det = best
        met = True
    else:
        _, thr, conf, fa, det = fallback  # type: ignore[misc]
        met = False
    return {"threshold": thr, "confirm_bins": conf, "budget_met": met, "train_fa_per_hour": fa, "train_detection_rate": det}


def person_event_counts(layout: Layout, p: np.ndarray, threshold: float, confirm_bins: int, episodes: np.ndarray,
                        *, cooldown_s: float = COOLDOWN_S) -> dict[str, float]:
    """Counts for one person's episodes under one alarm rule (the quantities v1 sums into ``EventResult``)."""
    ep = np.asarray(episodes, dtype=int)
    gs = score_grid(layout, p, np.array([threshold]), confirm_bins, episodes=ep, cooldown_s=cooldown_s)
    return {
        "n_events": float(layout.n_events[ep].sum()), "detected": float(gs.detected[ep, 0].sum()),
        "false_alarms": float(gs.false_alarms[ep, 0].sum()), "true_alarms": float(gs.true_alarms[ep, 0].sum()),
        "non_event_h": float(layout.non_event_h[ep].sum()), "total_h": float(layout.total_h[ep].sum()),
    }
