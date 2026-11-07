"""The rule baseline (ANA-6): the level engine plus the dignity gate, no learning.

The help level comes from skills.levels (3 clean up, 2 errors in the last 5 down, assisted neutral). When the
gate allows a prompt, the rule picks the action by level:
    L1, L2  annotate   (point at the thing: the person still needs the full hint)
    L3      nudge      (a hypothesis or a question, not the answer)
    L4      silent     (the worker has it)
It never takes over by itself; a takeover is the worker's request or an approved routine.

`rule_action(x)` is the same rule expressed on a context row so it can be a target policy for off-policy
evaluation. The gate part is read from the row: `consec >= 2`, the cooldown elapsed (`since_prompt` >= 1) and
`p_stuck` at or above the signal threshold.
"""
from __future__ import annotations

import numpy as np

from understudy_engine.policy.context import ANNOTATE, K, NUDGE, SILENT, as_matrix
from understudy_engine.policy.gate import GateParams


def rule_action_for_level(level: int) -> int:
    if level <= 2:
        return ANNOTATE
    if level == 3:
        return NUDGE
    return SILENT


def rule_action(x: np.ndarray, params: GateParams = GateParams()) -> int:
    p_stuck, level, since_prompt, consec, _risk, _mastery = (float(v) for v in np.asarray(x, float)[:6])
    gate_open = consec >= params.need and since_prompt >= 1.0 and p_stuck >= params.p_signal
    return rule_action_for_level(int(round(level))) if gate_open else SILENT


def rule_probs(X: np.ndarray, params: GateParams = GateParams()) -> np.ndarray:
    X = as_matrix(X)
    P = np.zeros((X.shape[0], K))
    for i, row in enumerate(X):
        P[i, rule_action(row, params)] = 1.0
    return P
