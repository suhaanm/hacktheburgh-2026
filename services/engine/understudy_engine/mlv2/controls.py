"""Negative controls that must come out null (PLAN.md section 6.2 controls, amendment 3)."""
from __future__ import annotations

import dataclasses

import numpy as np

from understudy_engine.hazard.features import BinTable

LL_TOL = 0.003      # a model may not beat the base rate by more than this on shuffled labels


def shuffle_labels(tab: BinTable, seed: int = 0, scope: str = "global") -> BinTable:
    """Labels permuted so that nothing in the features can predict them.

    scope "global" (the control): the label vector is permuted over ALL bins of the pool. Features, ids and episode structure stay, the
    overall base rate stays, and everything else (what was happening, position in the episode, who the person is) is cut from the label,
    so every model must score about the base rate.
    scope "person": permuted over each person's own bins. This keeps each person's own stuck rate, so a model that learns a person's rate
    (the personal prior shift, A6) legitimately beats the pooled base rate here; it is a diagnostic, not the control.

    PLAN.md first said 'permuted across that person's episodes, bins of one episode together'. That keeps position-in-episode structure
    and each person's rate, both of which a model may legitimately use, so the control would fail for a harmless reason (amendment 3).
    """
    if scope not in ("global", "person"):
        raise ValueError(scope)
    rng = np.random.default_rng(seed)
    y = tab.y.copy()
    if scope == "global":
        y = tab.y[rng.permutation(tab.n)]
    else:
        for q in tab.people:
            r = tab.rows_of([q])
            y[r] = tab.y[rng.permutation(r)]
    return dataclasses.replace(tab, y=y)


def beats_base_rate(log_loss_model: float, log_loss_base: float, tol: float = LL_TOL) -> bool:
    """True if the model's log loss is better than the base rate's by more than ``tol`` (a control FAILURE on shuffled labels)."""
    return (log_loss_base - log_loss_model) > tol
