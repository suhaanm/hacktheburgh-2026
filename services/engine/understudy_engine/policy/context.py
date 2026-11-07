"""Shared vocabulary for the intervention policy: actions, context features, cost constants."""
from __future__ import annotations

import numpy as np

ACTIONS = ("silent", "nudge", "annotate", "takeover")
K = len(ACTIONS)
SILENT, NUDGE, ANNOTATE, TAKEOVER = range(K)

# A decision context x (one row per decision point), natural units:
CONTEXT_FEATURES = (
    "p_stuck",        # hazard model probability of no progress in the next 60 s, in [0, 1]
    "level",          # help level L1..L4 of the cog involved (1 = most help needed)
    "since_prompt",   # fraction of the cooldown elapsed since the last prompt, in [0, 1] (1 = long ago)
    "consec",         # consecutive stuck signals so far, 0..4
    "risk",           # 1 if the next step is irreversible or outward-facing, else 0
    "mastery",        # decayed mastery of the cog, in [0, 1]
)
D = len(CONTEXT_FEATURES)

# Reward = progress in the next two minutes - interruption cost - reliance penalty on takeover.
INTERRUPTION_COST = (0.0, 0.12, 0.20, 0.45)   # per action, before the "just prompted" surcharge
RELIANCE_PENALTY_TAKEOVER = 0.40               # a takeover teaches nothing; base penalty
PROGRESS_WINDOW_S = 120.0


def make_context(p_stuck: float, level: int, since_prompt: float, consec: int, risk: int, mastery: float) -> np.ndarray:
    return np.array([p_stuck, level, min(max(since_prompt, 0.0), 1.0), consec, risk, mastery], dtype=float)


def as_matrix(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return x[None, :] if x.ndim == 1 else x
