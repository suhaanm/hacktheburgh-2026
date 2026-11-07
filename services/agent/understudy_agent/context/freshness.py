"""How old an input to a model prompt or a decision may be. Pure data plus three tiny functions.

The table is the shared one that Cue (`understudy_engine/cue/freshness.py`, same names and limits for the keys it reads) and the
attention router adopt. A reading carries `t`, the time it was TAKEN by the producer's own clock (never the time it was
received). At assembly time its age is `now - t`:

* fresh   age is within the limit (or the kind has no limit and the reading exists)
* stale   older than the limit: the reading is DROPPED and its kind is listed under `stale`, so the model is told what it does not
          know instead of being given an old fact as if it were current
* missing there was no reading at all: listed under `missing` (distinct from stale; never defaulted)

Limits are in seconds. `None` means "no age limit, but it must exist" (the last progress event, a worker-owned memory line).
Adding a kind is one row here; nothing else changes.
"""
from __future__ import annotations

from enum import Enum

DAY = 86_400.0

MAX_AGE_S: dict[str, float | None] = {
    # Cue's inputs (names and limits as in understudy_engine/cue/freshness.py)
    "p_stuck": 6.0,              # the stuck reading and the snapshot it came from
    "snapshot": 60.0,            # beyond this the whole live context is too old to act on
    "grounding": 20.0,           # a grounding result for the step now on screen
    "glance": 60.0,              # glance enums (app kind, task phase, blocker)
    "input_rhythm": 10.0,        # last keyboard or pointer input time
    "progress": None,            # the last progress event: no limit, the stall is measured from it
    # attention router (asked for by the ATTENTION track)
    "worker_state": 10.0,        # typing, quiet_s, away, locked, dnd, screen sharing, on a call
    "meeting_state": 120.0,      # the calendar's in-meeting flag
    # the worker's analytics and sources
    "hazard_reading": 30.0,      # a stuck-hazard reading used as a feature in a prompt
    "page_observation": 30.0,    # a page or screen observation behind a planner step (as SecurityConfig.max_observation_age_s)
    "briefing_card": 3600.0,     # a prepared card is re-verified after an hour
    "ledger_summary": DAY,       # the assist ledger summary line
    "calendar_week": 7 * DAY,    # one week of calendar features
    "git_habits": 14 * DAY,      # commit habits over the recent window
    "skill_state": 90 * DAY,     # "last seen" on a skill-state line in the memory file
    "memory_line": None,         # a worker-owned preference, procedure or never-line: no age limit, but it is keyed
    "task_state": None,          # the code-maintained task state of a run: always current by construction
}


class Status(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


def limit_for(kind: str) -> float | None:
    """The limit of a kind. An unknown kind raises KeyError: a typo must not silently mean 'no limit'."""
    return MAX_AGE_S[kind]


def age_s(t: float | None, now: float) -> float | None:
    """`now - t`, or None when there is no reading. A reading dated in the future is treated as age 0 (clock skew), never negative."""
    if t is None:
        return None
    return max(0.0, float(now) - float(t))


def status_of(kind: str, t: float | None, now: float) -> Status:
    a = age_s(t, now)
    if a is None:
        return Status.MISSING
    lim = limit_for(kind)
    if lim is None or a <= lim:
        return Status.FRESH
    return Status.STALE


def is_fresh(kind: str, t: float | None, now: float) -> bool:
    return status_of(kind, t, now) is Status.FRESH
