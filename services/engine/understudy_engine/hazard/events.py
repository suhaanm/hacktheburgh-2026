"""Event-level scoring of stuck alarms: false alarms per hour (ANA-5, after the Stride idea).

Ground truth: a *stuck event* is a maximal run of at least `min_run` consecutive bins with y = 1
inside one episode (so a stretch with no progress for roughly two minutes or more). An *alarm* fires
when p >= threshold for `confirm_bins` consecutive bins, at most once per `cooldown_s`.

  true alarm    falls inside a stuck event, widened by `tol_s` on both sides
  false alarm   any other alarm
  detected      a stuck event containing at least one alarm
  non-event hours   total binned hours minus the hours covered by stuck events (denominator of FA/h)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from understudy_engine.hazard.features import BinTable

MIN_RUN = 2
TOL_S = 30.0
COOLDOWN_S = 120.0


@dataclass
class EpisodeEvents:
    n_events: int = 0
    detected: int = 0
    false_alarms: int = 0
    true_alarms: int = 0
    non_event_h: float = 0.0
    total_h: float = 0.0
    latencies: list[float] = field(default_factory=list)


@dataclass
class EventResult:
    n_events: int
    detected: int
    false_alarms: int
    true_alarms: int
    non_event_h: float
    latencies: list[float]
    total_h: float = 0.0

    @property
    def detection_rate(self) -> float:
        return self.detected / self.n_events if self.n_events else float("nan")

    @property
    def fa_per_hour(self) -> float:
        return self.false_alarms / self.non_event_h if self.non_event_h > 0 else float("nan")

    @property
    def median_latency_s(self) -> float:
        return float(np.median(self.latencies)) if self.latencies else float("nan")

    def as_dict(self) -> dict:
        return {
            "n_events": self.n_events, "detected": self.detected,
            "detection_rate": None if not self.n_events else self.detection_rate,
            "false_alarms": self.false_alarms, "true_alarms": self.true_alarms,
            "non_event_hours": self.non_event_h, "total_hours": self.total_h,
            "alarms_per_hour": None if self.total_h <= 0 else (self.false_alarms + self.true_alarms) / self.total_h,
            "false_alarms_per_hour": None if self.non_event_h <= 0 else self.fa_per_hour,
            "median_latency_s": None if not self.latencies else self.median_latency_s,
        }


def stuck_events(y: np.ndarray, t: np.ndarray, bin_s: float, min_run: int = MIN_RUN) -> list[tuple[float, float]]:
    """Maximal runs of y == 1 of at least `min_run` bins -> [(start_t, end_t)]."""
    out: list[tuple[float, float]] = []
    n = y.size
    i = 0
    while i < n:
        if y[i] == 1:
            j = i
            while j + 1 < n and y[j + 1] == 1:
                j += 1
            if j - i + 1 >= min_run:
                out.append((float(t[i]), float(t[j] + bin_s)))
            i = j + 1
        else:
            i += 1
    return out


def alarms_for(
    t: np.ndarray, p: np.ndarray, thr: float, confirm_bins: int = 1, cooldown_s: float = COOLDOWN_S,
) -> np.ndarray:
    """Alarm times for one episode."""
    above = p >= thr
    if not above.any():
        return np.zeros(0)
    if confirm_bins > 1:
        run = np.zeros(above.size, dtype=int)
        c = 0
        for i, a in enumerate(above):
            c = c + 1 if a else 0
            run[i] = c
        cand = np.where(run >= confirm_bins)[0]
    else:
        cand = np.where(above)[0]
    out = []
    last = -np.inf
    for i in cand:
        if t[i] - last >= cooldown_s:
            out.append(t[i])
            last = t[i]
    return np.array(out)


def score_alarms(
    t: np.ndarray, y: np.ndarray, alarms: np.ndarray, *, bin_s: float, tol_s: float = TOL_S,
    min_run: int = MIN_RUN,
) -> EpisodeEvents:
    """Event-level score for alarms that some other rule already produced (e.g. the dignity gate)."""
    ev = stuck_events(y, t, bin_s, min_run)
    al = np.asarray(alarms, dtype=float)
    res = EpisodeEvents()
    res.n_events = len(ev)
    total_h = t.size * bin_s / 3600.0
    ev_h = sum((e1 - e0) for e0, e1 in ev) / 3600.0
    res.non_event_h = max(0.0, total_h - ev_h)
    res.total_h = total_h
    for e0, e1 in ev:
        inside = al[(al >= e0 - tol_s) & (al <= e1 + tol_s)]
        if inside.size:
            res.detected += 1
            res.latencies.append(max(0.0, float(inside.min() - e0)))
    for a in al:
        if any(e0 - tol_s <= a <= e1 + tol_s for e0, e1 in ev):
            res.true_alarms += 1
        else:
            res.false_alarms += 1
    return res


def score_episode(
    t: np.ndarray, y: np.ndarray, p: np.ndarray, thr: float, *, bin_s: float, confirm_bins: int = 1,
    cooldown_s: float = COOLDOWN_S, tol_s: float = TOL_S, min_run: int = MIN_RUN,
) -> EpisodeEvents:
    al = alarms_for(t, p, thr, confirm_bins, cooldown_s)
    return score_alarms(t, y, al, bin_s=bin_s, tol_s=tol_s, min_run=min_run)


def score_rows(
    tab: BinTable, p_all: np.ndarray, episodes: list[int], thr: float, *, confirm_bins: int = 1,
    cooldown_s: float = COOLDOWN_S, tol_s: float = TOL_S, min_run: int = MIN_RUN,
) -> tuple[EventResult, dict[int, EpisodeEvents]]:
    """Score the given episodes. `p_all` is indexed by table row (only rows of these episodes are read)."""
    per: dict[int, EpisodeEvents] = {}
    for e in episodes:
        a, b = int(tab.ep_offsets[e]), int(tab.ep_offsets[e + 1])
        per[e] = score_episode(
            tab.t[a:b], tab.y[a:b], p_all[a:b], thr, bin_s=tab.bin_s, confirm_bins=confirm_bins,
            cooldown_s=cooldown_s, tol_s=tol_s, min_run=min_run,
        )
    return pool(per.values()), per


def pool(items) -> EventResult:
    n_events = detected = fa = ta = 0
    non_h = tot_h = 0.0
    lat: list[float] = []
    for r in items:
        n_events += r.n_events
        detected += r.detected
        fa += r.false_alarms
        ta += r.true_alarms
        non_h += r.non_event_h
        tot_h += r.total_h
        lat.extend(r.latencies)
    return EventResult(n_events, detected, fa, ta, non_h, lat, tot_h)


def choose_config(
    tab: BinTable, p_all: np.ndarray, episodes: list[int], budget_per_h: float, *,
    confirm_options: tuple[int, ...] = (1, 2), n_thr: int = 60, cooldown_s: float = COOLDOWN_S,
) -> dict:
    """Pick (threshold, confirm_bins) that maximises event detection subject to FA/h <= budget.

    Ties go to fewer false alarms, then to the higher threshold. If no config meets the budget the
    config with the fewest false alarms is returned with budget_met = False.
    """
    rows = np.concatenate([np.arange(tab.ep_offsets[e], tab.ep_offsets[e + 1]) for e in episodes]) if episodes else np.zeros(0, int)
    pv = p_all[rows]
    if pv.size == 0:
        return {"threshold": 1.01, "confirm_bins": 1, "budget_met": False, "train_fa_per_hour": float("nan"),
                "train_detection_rate": float("nan")}
    qs = np.unique(np.append(np.quantile(pv, np.linspace(0.30, 0.9995, n_thr)), 1.01))  # 1.01 = never alarm
    best = None
    fallback = None
    for conf in confirm_options:
        for thr in qs:
            res, _ = score_rows(tab, p_all, episodes, float(thr), confirm_bins=conf, cooldown_s=cooldown_s)
            fa = res.fa_per_hour if np.isfinite(res.fa_per_hour) else 0.0
            det = res.detection_rate if np.isfinite(res.detection_rate) else 0.0
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
    return {"threshold": thr, "confirm_bins": conf, "budget_met": met, "train_fa_per_hour": fa,
            "train_detection_rate": det}
