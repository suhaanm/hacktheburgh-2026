"""How old an input to a Cue decision may be (REQ-8 context engineering). An input older than its limit is dropped and the decision says
``stale_input`` (and names what it dropped in ``stale``) instead of quietly using it. A missing input is marked, not silently defaulted.

Limits in seconds. ``None`` means "no age limit but it must exist". Names follow the Cue inputs; the shared freshness table of the CONTEXT
track replaces this one when it lands (the keys here are the ones Cue reads).
"""
from __future__ import annotations

MAX_AGE_S: dict[str, float | None] = {
    "p_stuck": 6.0,           # the stuck reading and the snapshot it came from: a few seconds
    "snapshot": 60.0,         # beyond this the whole context is too old to act on
    "grounding": 20.0,        # a grounding result for the step now on screen (a fresh frame, never an old one)
    "glance": 60.0,           # glance enums (Cue does not read them yet; listed so the table is complete)
    "input_rhythm": 10.0,     # last keyboard or pointer input time
    "progress": None,         # the last progress event: no limit, but the stall is measured from it (task start when there is none)
}
MAX_WINDOW_COGS = 120         # the decision sees a bounded window of the open task's cogs, never an event log
MAX_LEDGER_ROWS_PER_SKILL = 120   # ledger retrieval is keyed by skill and capped
MAX_GROWTH_ROWS = 3000        # the Growth payload reads at most the newest 3000 ledger rows of a person (an analytics read, not a decision input)
CANDIDATE_CACHE = 256         # candidate lists are cached per cog window and recomputed when the last cog changes


def is_fresh(name: str, age_s: float | None) -> bool:
    """False when the input is missing (``age_s`` None) or older than its limit."""
    if age_s is None:
        return False
    limit = MAX_AGE_S.get(name)
    return True if limit is None else age_s <= limit
