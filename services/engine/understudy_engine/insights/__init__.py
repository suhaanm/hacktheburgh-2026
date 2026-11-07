"""The insights layer (REQ-9): a few deterministic pointers for the worker, granular detail for the admin.

Pure Python over data the product already computes (the assist ledger and the routine, risk and profile summaries). No model call, no network, no
clock of its own. Candidates are fixed lists of pure functions; selection is a pure function (reliability gate, family control, guard metrics,
score, diversity, caps); wording is fixed templates. See ``docs/INSIGHTS_DESIGN.md``. Off by default (``UNDERSTUDY_X_INSIGHTS`` or ``UNDERSTUDY_X``).
For coaching and onboarding, not for evaluating individuals.
"""
from __future__ import annotations

from .paths import FLAG, enabled

__all__ = ["FLAG", "enabled", "evaluate_insights"]


def evaluate_insights(fast: bool = False, **kw):
    from .evaluate import evaluate_insights as f

    return f(fast=fast, **kw)
