"""The dignity gate (COA-4): code decides whether the coach may speak at all.

  - act only after `need` CONSECUTIVE stuck signals (a signal = p_stuck at or above `p_signal`)
  - after acting, stay quiet for `cooldown_s`
  - silent when unsure: anything that is not a clear signal (below threshold, or flagged unsure by the caller:
    unknown cog, away from the screen, low confidence) resets the chain and keeps the coach silent

Pure functions of (state, observation). The model proposes a probability; this gate disposes.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class GateParams:
    need: int = 2
    cooldown_s: float = 120.0
    p_signal: float = 0.6
    min_confidence: float = 0.0   # if a confidence is supplied and below this, the reading counts as unsure


@dataclass(frozen=True)
class GateState:
    consecutive: int = 0
    last_act_t: float = -1e18


@dataclass(frozen=True)
class GateDecision:
    state: GateState
    act: bool
    reason: str   # act | wait_signals | cooldown | unsure | below_threshold


def gate_step(state: GateState, p: float, t: float, *, unsure: bool = False, confidence: float | None = None,
              params: GateParams = GateParams()) -> GateDecision:
    if unsure or (confidence is not None and confidence < params.min_confidence):
        return GateDecision(replace(state, consecutive=0), False, "unsure")
    if p < params.p_signal:
        return GateDecision(replace(state, consecutive=0), False, "below_threshold")
    consec = state.consecutive + 1
    if t - state.last_act_t < params.cooldown_s:
        return GateDecision(replace(state, consecutive=consec), False, "cooldown")
    if consec < params.need:
        return GateDecision(replace(state, consecutive=consec), False, "wait_signals")
    return GateDecision(GateState(0, t), True, "act")


def gate_alarms(t: np.ndarray, p: np.ndarray, params: GateParams = GateParams(),
                unsure: np.ndarray | None = None) -> np.ndarray:
    """Run the gate over one episode's bins and return the times at which it would act."""
    st = GateState()
    out = []
    for i in range(t.size):
        d = gate_step(st, float(p[i]), float(t[i]), unsure=bool(unsure[i]) if unsure is not None else False,
                      params=params)
        st = d.state
        if d.act:
            out.append(float(t[i]))
    return np.array(out)
