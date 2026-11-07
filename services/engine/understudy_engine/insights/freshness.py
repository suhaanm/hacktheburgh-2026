"""How old the evidence behind an insight may be (REQ-9; the conventions of docs/CONTEXT_ENGINEERING.md).

A reading carries the time its producer took it. Evidence older than its limit is dropped and NAMED (``stale``), never quietly used and never
silently defaulted. Insights are weekly summaries, so the limits are days, not seconds. ``None`` means "no limit, but it must exist".
Keys are additions to the shared table; the shared one keeps its own.
"""
from __future__ import annotations

DAY = 86400.0

MAX_AGE_S: dict[str, float | None] = {
    "ledger": 21 * DAY,         # newest assist row behind an insight
    "offloaded": 30 * DAY,      # delegated and automation rows
    "routines": 30 * DAY,       # routine finder values and shadow statistics
    "hitlist": 14 * DAY,        # the repeat list's top row
    "calendar": 14 * DAY,       # the calendar layer's flagged suggestion
    "git": 21 * DAY,            # the git layer's flagged habit
    "risk_feed": 2 * DAY,       # approval ages and risk-event counts
    "profile": None,
}


def age_s(now: float, t: float | None) -> float | None:
    return None if t is None else max(0.0, now - t)


def is_fresh(source: str, now: float, t: float | None) -> bool:
    """False when the reading is missing or older than its limit."""
    if t is None:
        return False
    limit = MAX_AGE_S.get(source)
    return True if limit is None else (now - t) <= limit
