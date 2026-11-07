"""Weekly presence map: 672 bins of 15 minutes, each a posterior over {active, idle, off} (ANA-12, OFF-1).

Method. For each (day of week, 15-minute slot) the model keeps a Dirichlet posterior over three states, so
the chance of "active" is a Beta posterior with an interval, and idle time (machine on, nobody there) is
the Dirichlet's middle state. Counts come from the worker's own days, **smoothed**: a bin also borrows
fractional pseudo-observations from the bins either side of it (+-1, +-2 slots, wrapping the week) and from the
same slot on other days (other weekdays count more than the weekend, and the reverse). The prior comes from the
role pack's working hours (``priors.yaml: presence``), worth ``prior_strength`` pseudo-observations. Borrowed
counts are weights below one, so a bin with little data of its own gets a wide interval, not a falsely sharp one.

The smoothing weights are fixed defaults (and can be tuned on a validation split); nothing is fitted by a
black box.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

from .timeline import ACTIVE, BINS, IDLE, OFF, SLOTS, DayObs

DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class Smoothing:
    adjacent1: float = 0.5     # weight of an observation one slot away
    adjacent2: float = 0.25    # two slots away
    same_class: float = 0.30   # same slot on another day of the same kind (weekday / weekend)
    other_class: float = 0.05  # same slot on the other kind of day
    prior_strength: float = 2.0


@dataclass
class PriorHours:
    """Prior from the pack: working window, days, and P(active) inside and outside it."""

    start_min: int = 9 * 60
    end_min: int = 17 * 60 + 30
    days: tuple[int, ...] = (0, 1, 2, 3, 4)
    p_in: float = 0.7
    p_out: float = 0.03
    awake_share_in: float = 0.95   # of the non-active mass inside hours, share where the machine is on
    awake_share_out: float = 0.25

    @classmethod
    def from_pack_prior(cls, prior: dict[str, Any]) -> PriorHours:
        h = prior.get("hours", {})
        s, e = h.get("start", "09:00"), h.get("end", "17:30")
        days = tuple(DOW_NAMES.index(d) for d in h.get("days", DOW_NAMES[:5]) if d in DOW_NAMES)
        return cls(
            start_min=int(s[:2]) * 60 + int(s[3:5]), end_min=int(e[:2]) * 60 + int(e[3:5]), days=days or (0, 1, 2, 3, 4),
            p_in=float(prior.get("active_in_hours", 0.7)), p_out=float(prior.get("active_out_of_hours", 0.03)),
        )

    def mask(self) -> np.ndarray:
        """Boolean (7, 96): slot starts inside the working window on a working day (windows past midnight wrap)."""
        m = np.zeros((7, SLOTS), dtype=bool)
        for d in self.days:
            for s in range(SLOTS):
                t = s * 15
                if self.start_min <= self.end_min:
                    inside = self.start_min <= t < self.end_min
                else:
                    inside = t >= self.start_min
                m[d, s] = inside
            if self.start_min > self.end_min:  # the part after midnight belongs to the next calendar day
                nxt = (d + 1) % 7
                for s in range(SLOTS):
                    if s * 15 < self.end_min:
                        m[nxt, s] = True
        return m

    def prior_probs(self) -> np.ndarray:
        """(7, 96, 3) prior mean over (OFF, IDLE, ACTIVE)."""
        inside = self.mask()
        p_act = np.where(inside, self.p_in, self.p_out)
        awake = np.where(inside, self.awake_share_in, self.awake_share_out)
        rest = 1.0 - p_act
        out = np.zeros((7, SLOTS, 3))
        out[..., ACTIVE] = p_act
        out[..., IDLE] = rest * awake
        out[..., OFF] = rest * (1 - awake)
        return out


def _class_of(dow: int) -> int:
    return 0 if dow < 5 else 1


class PresenceModel:
    """Fit once on days of observations, then read the map, intervals and idle capacity."""

    def __init__(self, prior: PriorHours | None = None, smoothing: Smoothing | None = None) -> None:
        self.prior = prior or PriorHours()
        self.smoothing = smoothing or Smoothing()
        self.counts = np.zeros((7, SLOTS, 3))        # raw observed counts per dow, slot, state
        self.n_days = np.zeros(7, dtype=int)         # observed days per day of week
        self.alpha = self.prior.prior_probs() * self.smoothing.prior_strength  # (7, 96, 3)
        self.total_days = 0

    # ------------------------------------------------------------------ fitting
    def fit(self, days: Sequence[DayObs]) -> PresenceModel:
        self.counts[:] = 0
        self.n_days[:] = 0
        for d in days:
            dow = d.day.weekday()
            self.n_days[dow] += 1
            for st in (OFF, IDLE, ACTIVE):
                self.counts[dow, :, st] += (d.states == st)
        self.total_days = int(self.n_days.sum())
        self._days = list(days)
        self._smooth()
        return self

    def _smooth(self) -> None:
        sm = self.smoothing
        S = self.counts.copy()
        flat = self.counts.reshape(BINS, 3)
        borrowed = np.zeros_like(flat)
        for k, w in ((1, sm.adjacent1), (2, sm.adjacent2)):
            borrowed += w * (np.roll(flat, k, axis=0) + np.roll(flat, -k, axis=0))
        S += borrowed.reshape(7, SLOTS, 3)
        by_dow = self.counts  # (7, 96, 3)
        for d in range(7):
            for e in range(7):
                if e == d:
                    continue
                w = sm.same_class if _class_of(e) == _class_of(d) else sm.other_class
                S[d] += w * by_dow[e]
        self.smoothed = S
        self.alpha = self.prior.prior_probs() * sm.prior_strength + S

    # ------------------------------------------------------------------ reading
    def p_active(self) -> np.ndarray:
        a = self.alpha
        return a[..., ACTIVE] / a.sum(axis=-1)

    def active_interval(self, level: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
        a = self.alpha[..., ACTIVE]
        b = self.alpha.sum(axis=-1) - a
        tail = (1 - level) / 2
        return stats.beta.ppf(tail, a, b), stats.beta.ppf(1 - tail, a, b)

    def p_state(self) -> np.ndarray:
        return self.alpha / self.alpha.sum(axis=-1, keepdims=True)

    def heatmap(self, level: float = 0.95) -> list[dict[str, Any]]:
        p = self.p_active()
        lo, hi = self.active_interval(level)
        return [
            {"dow": d, "slot": s, "p": round(float(p[d, s]), 4), "lo": round(float(lo[d, s]), 4), "hi": round(float(hi[d, s]), 4)}
            for d in range(7) for s in range(SLOTS)
        ]

    def idle_capacity_h(self, *, level: float = 0.95, draws: int = 600, seed: int = 7, mask: np.ndarray | None = None) -> dict[str, float]:
        """Hours per week the machine is on and nobody is using it, with a posterior interval.

        ``mask`` (7, 96) restricts the count to some bins (for example the worker's quiet hours).
        Draws come from the per-bin Dirichlet posteriors, so the interval carries the uncertainty of
        every bin, including the borrowed ones.
        """
        rng = np.random.default_rng(seed)
        a = self.alpha.reshape(BINS, 3)
        sel = np.ones(BINS, dtype=bool) if mask is None else mask.reshape(BINS)
        g = rng.gamma(a[sel][None, :, :], 1.0, size=(draws, int(sel.sum()), 3))
        idle = g[..., IDLE] / g.sum(axis=-1)
        tot = idle.sum(axis=1) * 0.25
        mean = float(self.p_state().reshape(BINS, 3)[sel, IDLE].sum() * 0.25)
        tail = (1 - level) / 2
        return {"mean": round(mean, 2), "lo": round(float(np.quantile(tot, tail)), 2), "hi": round(float(np.quantile(tot, 1 - tail)), 2)}

    def idle_capacity_bootstrap(self, *, level: float = 0.95, n_boot: int = 200, seed: int = 5) -> dict[str, float] | None:
        """Interval from resampling whole days and refitting: it carries day-to-day variation, which the
        per-bin posteriors (independent by construction) leave out. ``None`` with fewer than 7 days."""
        days = getattr(self, "_days", [])
        if len(days) < 7:
            return None
        rng = np.random.default_rng(seed)
        vals = []
        for _ in range(n_boot):
            pick = [days[i] for i in rng.integers(0, len(days), len(days))]
            m = PresenceModel(self.prior, self.smoothing).fit(pick)
            vals.append(float(m.p_state().reshape(BINS, 3)[:, IDLE].sum() * 0.25))
        tail = (1 - level) / 2
        return {"lo": round(float(np.quantile(vals, tail)), 2), "hi": round(float(np.quantile(vals, 1 - tail)), 2)}

    def idle_capacity_interval(self, *, level: float = 0.95, mask: np.ndarray | None = None) -> dict[str, float]:
        """Mean from the posterior; interval = the wider of the posterior and the day bootstrap (conservative)."""
        post = self.idle_capacity_h(level=level, mask=mask)
        if mask is None:
            boot = self.idle_capacity_bootstrap(level=level)
            if boot:
                post = {"mean": post["mean"], "lo": min(post["lo"], boot["lo"], post["mean"]), "hi": max(post["hi"], boot["hi"], post["mean"])}
        return post

    def active_hours_per_week(self) -> float:
        return float(self.p_active().sum() * 0.25)

    def log_loss_active(self, days: Sequence[DayObs]) -> float:
        p = np.clip(self.p_active(), 1e-4, 1 - 1e-4)
        tot, n = 0.0, 0
        for d in days:
            y = (d.states == ACTIVE).astype(float)
            pd = p[d.day.weekday()]
            tot += float(-(y * np.log(pd) + (1 - y) * np.log(1 - pd)).sum())
            n += SLOTS
        return tot / max(n, 1)

    def tune(self, days: Sequence[DayObs], grid: Sequence[Smoothing] | None = None, val_frac: float = 0.3) -> Smoothing:
        """Pick smoothing weights by log loss on the last ``val_frac`` of ``days``; refit on all days."""
        grid = grid or default_grid()
        cut = max(1, int(len(days) * (1 - val_frac)))
        train, val = list(days[:cut]), list(days[cut:])
        best, best_ll = self.smoothing, float("inf")
        if val:
            for sm in grid:
                m = PresenceModel(self.prior, sm).fit(train)
                ll = m.log_loss_active(val)
                if ll < best_ll:
                    best, best_ll = sm, ll
        self.smoothing = best
        self.fit(days)
        return best


def default_grid() -> list[Smoothing]:
    out = []
    for a1, a2 in ((0.0, 0.0), (0.4, 0.2), (0.6, 0.3), (0.8, 0.5)):
        for sc in (0.0, 0.2, 0.4, 0.7):
            out.append(Smoothing(adjacent1=a1, adjacent2=a2, same_class=sc, other_class=0.05 if sc else 0.0))
    return out


def slot_of(minute_of_day: float) -> int:
    return int(minute_of_day // 15) % SLOTS


def window_mask(window: dict[str, Any]) -> np.ndarray:
    """Boolean (7, 96) for a quiet-hours window ``{start, end, days}``; a window past midnight wraps to the next day."""
    ph = PriorHours(
        start_min=int(window["start"][:2]) * 60 + int(window["start"][3:5]),
        end_min=int(window["end"][:2]) * 60 + int(window["end"][3:5]),
        days=tuple(DOW_NAMES.index(d) for d in window.get("days", DOW_NAMES) if d in DOW_NAMES),
    )
    return ph.mask()
