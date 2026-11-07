"""Return-time hazard as kernel-smoothed empirical survival, and the start-or-wait rule (ANA-12, OFF-3).

Question: the worker has been idle for ``u`` minutes at time-of-week ``t``. What is ``S(D | t, u)``, the
chance the idle spell lasts at least ``D`` more minutes?

Estimator. Take every past idle spell that was still running at elapsed time ``u``. Weight each one by how
close it was, *at that elapsed time*, to the query's time of week: a Gaussian kernel on circular time of day,
times a day-of-week factor (same day 1, same kind of day ``w_same``, other kind ``w_other``). Then

    S(D | t, u) = ( sum_i w_i * 1~[d_i >= u + D]  +  m * S0 ) / ( sum_i w_i * 1~[d_i >= u]  +  m )

where ``1~[d >= x]`` is a smooth step (a normal CDF with a width that grows with ``x``, so the survival curve
has no staircase) and ``S0`` is the same ratio with no time weighting. ``m`` pseudo-spells shrink the answer
toward the pooled survival when few spells look like now. With no spell at all there is no estimate and the
rule says wait.

Decision (the critical fractile). Start a run of length ``D`` only if ``S(D | t, u) > L / (G + L)``, where
``G`` is the value of finishing and ``L`` the cost of a collision (the worker comes back mid-run). Equivalently,
the probability of a collision must be below ``G / (G + L)``.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats
from scipy.special import ndtr

from .timeline import Spell

DEFAULT_GRID_MIN = (5, 15, 30, 60, 120, 240, 480)


@dataclass(frozen=True)
class SurvivalConfig:
    h_tod_min: float = 75.0      # kernel bandwidth on time of day
    w_same_class: float = 0.30   # weight of a spell seen on another day of the same kind
    w_other_class: float = 0.08
    shrink: float = 1.0          # m, pseudo-spells of the pooled survival
    step_rel: float = 0.08       # smooth-step width, relative to the duration being tested
    step_min: float = 0.5        # and at least this many minutes


@dataclass(frozen=True)
class SurvivalEstimate:
    survival: float
    lo: float
    hi: float
    n_eff: float
    n_risk: int

    def as_dict(self) -> dict[str, float]:
        return {"survival": round(self.survival, 4), "lo": round(self.lo, 4), "hi": round(self.hi, 4), "n_eff": round(self.n_eff, 1)}


def _class(dow: np.ndarray | int) -> Any:
    return np.where(np.asarray(dow) < 5, 0, 1)


class ReturnTimeModel:
    def __init__(self, spells: Sequence[Spell], config: SurvivalConfig | None = None, *, min_gap_min: float = 5.0) -> None:
        self.cfg = config or SurvivalConfig()
        self.min_gap = min_gap_min
        self.spells = list(spells)
        self.dur = np.array([s.duration_min for s in self.spells], dtype=float)
        self.tod = np.array([s.tod_min for s in self.spells], dtype=float)
        self.dow = np.array([s.dow for s in self.spells], dtype=int)
        self.ended = np.array([s.ended for s in self.spells], dtype=bool)

    @property
    def n(self) -> int:
        return len(self.spells)

    def _step(self, d: np.ndarray, x: float) -> np.ndarray:
        """Smooth indicator that a spell lasting ``d`` minutes is still running at ``x`` minutes."""
        width = max(self.cfg.step_min, self.cfg.step_rel * x)
        return ndtr((d - x) / width)

    def _weights(self, t_tow_min: float, u: float) -> np.ndarray:
        """Weight each spell by closeness of its time of week at elapsed ``u`` to the query's time of week."""
        q_dow = int(t_tow_min // 1440) % 7
        q_tod = t_tow_min % 1440
        at = self.tod + u                              # where the spell's clock was at elapsed u
        day_shift = np.floor(at / 1440).astype(int)
        spell_dow = (self.dow + day_shift) % 7
        spell_tod = at % 1440
        d = np.abs(spell_tod - q_tod)
        d = np.minimum(d, 1440 - d)
        k = np.exp(-0.5 * (d / self.cfg.h_tod_min) ** 2)
        wd = np.where(spell_dow == q_dow, 1.0, np.where(_class(spell_dow) == _class(q_dow), self.cfg.w_same_class, self.cfg.w_other_class))
        return k * wd

    def survival(self, d_min: float, t_tow_min: float, u_min: float = 0.0) -> SurvivalEstimate:
        """S(D | t, u): chance a spell already ``u`` minutes old lasts at least ``D`` more minutes."""
        if self.n == 0:
            return SurvivalEstimate(0.0, 0.0, 1.0, 0.0, 0)
        at_u = self._step(self.dur, u_min)
        at_ud = self._step(self.dur, u_min + d_min)
        w = self._weights(t_tow_min, u_min)
        s0 = float(at_ud.sum() / at_u.sum()) if at_u.sum() > 1e-9 else 0.0
        num = float((w * at_ud).sum()) + self.cfg.shrink * s0
        den = float((w * at_u).sum()) + self.cfg.shrink
        s = min(1.0, max(0.0, num / den)) if den > 1e-9 else s0
        wr = w * at_u
        n_eff = float(wr.sum() ** 2 / max((wr ** 2).sum(), 1e-12)) if wr.sum() > 1e-9 else 0.0
        # interval: a Beta with n_eff pseudo-trials around s (honest about few similar spells)
        k = n_eff + self.cfg.shrink
        a, b = s * k + 0.5, (1 - s) * k + 0.5
        lo, hi = stats.beta.ppf(0.025, a, b), stats.beta.ppf(0.975, a, b)
        return SurvivalEstimate(s, float(lo), float(hi), n_eff, int((at_u > 0.5).sum()))

    def forecast(self, t_tow_min: float, u_min: float = 0.0, grid: Sequence[int] = DEFAULT_GRID_MIN) -> list[dict[str, float]]:
        out = []
        for d in grid:
            est = self.survival(float(d), t_tow_min, u_min)
            out.append({"d_min": int(d), **est.as_dict()})
        return out

    def pooled_survival(self, d_min: float, u_min: float = 0.0) -> float:
        """No time-of-week weighting: the baseline the weighted estimate must beat."""
        at_u = self._step(self.dur, u_min)
        at_ud = self._step(self.dur, u_min + d_min)
        return float(at_ud.sum() / at_u.sum()) if at_u.sum() > 1e-9 else 0.0

    def memoryless_survival(self, d_min: float) -> float:
        """Exponential baseline with the pooled mean spell length: S = exp(-D / mean)."""
        if self.n == 0:
            return 0.0
        return float(np.exp(-d_min / max(self.dur.mean(), 1e-9)))


# ------------------------------------------------------------------ the decision
def threshold(gain: float, loss: float) -> float:
    """L / (G + L): the survival a run has to beat. A loss of zero means always go; a gain of zero never."""
    if gain < 0 or loss < 0:
        raise ValueError("gain and loss must be non-negative")
    if gain + loss == 0:
        raise ValueError("gain and loss cannot both be zero")
    return loss / (gain + loss)


def loss_for_cap(gain: float, cap: float) -> float:
    """The loss that makes the rule accept a collision probability of at most ``cap``: L = G (1 - cap) / cap."""
    if not 0 < cap < 1:
        raise ValueError("cap must be between 0 and 1")
    return gain * (1 - cap) / cap


@dataclass(frozen=True)
class Decision:
    go: bool
    survival: float
    threshold: float
    reason: str
    lo: float = 0.0
    hi: float = 1.0
    n_eff: float = 0.0
    locked: bool = False


def decide(est: SurvivalEstimate, d_min: float, gain: float, loss: float, *, locked: bool = False,
           asleep: bool = False) -> Decision:
    thr = threshold(gain, loss)
    if asleep:
        return Decision(False, est.survival, thr, "The machine is asleep, so a run cannot start.", est.lo, est.hi, est.n_eff, locked)
    if locked:
        return Decision(False, est.survival, thr, "The screen is locked, so a desktop run will not start.", est.lo, est.hi, est.n_eff, True)
    if est.n_eff <= 0 and est.survival == 0.0:
        return Decision(False, 0.0, thr, "There is no history to judge how long you will be away, so I will wait.", est.lo, est.hi, 0.0, locked)
    go = est.survival > thr
    pct = f"{est.survival:.0%}"
    need = f"{thr:.0%}"
    if go:
        reason = f"A {int(d_min)} minute run finishes in about {pct} of similar gaps, above the {need} needed."
    else:
        reason = f"A {int(d_min)} minute run would finish in about {pct} of similar gaps, below the {need} needed, so I will wait."
    return Decision(go, est.survival, thr, reason, est.lo, est.hi, est.n_eff, locked)
