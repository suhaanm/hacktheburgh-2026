"""Per-cog knowledge tracing with forgetting (ANA-13).

Mastery m in [0, 1] is the probability the person has the skill now. Two parts:

  evidence   a Bayesian-knowledge-tracing step per counted run. A clean run is evidence for mastery (the
             person could have guessed); an error is evidence against (the person could have slipped); an
             assisted run is NO evidence. Each counted run also carries a small learning gain.
  forgetting between runs, mastery decays toward a floor with a memory stability S (days):
                 m(t + d) = floor + (m(t) - floor) * exp(-d / S)
             Stability grows with clean practice (spaced-practice effect) and shrinks after an error, so a
             well-practised cog fades slowly and a fresh one fast. `days_until` is the decay clock: how long
             until mastery would fall below a threshold if the person does not practise.

Pure and deterministic. The level engine (levels.py) stays the authority; it reads `mastery_at` only to cap the
level after absence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from understudy_engine.skills.levels import Outcome

DAY_S = 86400.0


@dataclass(frozen=True)
class TracingParams:
    p_init: float = 0.15
    slip: float = 0.10          # P(error | has the skill)
    guess: float = 0.25         # P(clean | lacks the skill)
    learn_clean: float = 0.12   # learning gain after a counted clean run
    learn_error: float = 0.04   # smaller gain after an error (feedback still teaches)
    floor: float = 0.10         # mastery never decays below this
    s0_days: float = 7.0        # initial memory stability
    s_growth: float = 1.5       # stability multiplier per clean run
    s_shrink: float = 0.7       # stability multiplier per error
    s_min_days: float = 2.0
    s_max_days: float = 90.0


DEFAULT = TracingParams()


@dataclass(frozen=True)
class CogMastery:
    m: float = DEFAULT.p_init
    stability_days: float = DEFAULT.s0_days
    t: float | None = None      # unix seconds of the last update (None: never seen)
    n_clean: int = 0
    n_error: int = 0
    n_assisted: int = 0


def decayed(state: CogMastery, t: float, p: TracingParams = DEFAULT) -> float:
    """Mastery at time t (>= state.t) given no practice in between."""
    if state.t is None or t <= state.t:
        return state.m
    d = (t - state.t) / DAY_S
    return p.floor + (state.m - p.floor) * math.exp(-d / state.stability_days)


mastery_at = decayed


def observe(state: CogMastery, outcome: Outcome, t: float, p: TracingParams = DEFAULT) -> CogMastery:
    """Decay to time t, then fold in one outcome."""
    m = decayed(state, t, p)
    if outcome == "assisted":  # no evidence, but time has passed: re-anchor at t (decay composes exactly)
        return replace(state, m=m, t=t, n_assisted=state.n_assisted + 1)
    if outcome == "clean":
        post = m * (1 - p.slip) / (m * (1 - p.slip) + (1 - m) * p.guess)
        m2 = post + (1 - post) * p.learn_clean
        s2 = min(p.s_max_days, state.stability_days * p.s_growth)
        return replace(state, m=min(1.0, m2), stability_days=s2, t=t, n_clean=state.n_clean + 1)
    if outcome == "error":
        post = m * p.slip / (m * p.slip + (1 - m) * (1 - p.guess))
        m2 = post + (1 - post) * p.learn_error
        s2 = max(p.s_min_days, state.stability_days * p.s_shrink)
        return replace(state, m=min(1.0, m2), stability_days=s2, t=t, n_error=state.n_error + 1)
    raise ValueError(f"unknown outcome {outcome!r}")


def days_until(state: CogMastery, threshold: float, t_now: float, p: TracingParams = DEFAULT) -> float:
    """Decay clock: days from t_now until mastery falls to `threshold` with no practice.
    0 if already below; inf if the threshold is at or below the floor."""
    m = decayed(state, t_now, p)
    if m <= threshold:
        return 0.0
    if threshold <= p.floor:
        return math.inf
    return state.stability_days * math.log((m - p.floor) / (threshold - p.floor))
