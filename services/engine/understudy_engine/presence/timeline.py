"""From timestamps to what the presence model fits: day-by-bin states and idle spells.

Only times are used. Events from the agent are dropped (CAP-6: agent actions never enter the human trace).

States per 15-minute bin of a local calendar day::

    ACTIVE = 2   at least one human input event in the bin
    IDLE   = 1   machine on, no input (the worker is away or thinking)
    OFF    = 0   machine asleep or shut down (after a ``sleep`` event, until the next event)

A **spell** is the gap between two consecutive human input events that is at least ``min_gap_min`` long:
the worker is idle from the last input until they come back. Spell durations are what the return-time
model learns from. ``lock``, ``idle`` and ``sleep`` events are not inputs; ``unlock`` and ``resume`` are
(the worker is back).
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

SLOTS = 96
BINS = 672
OFF, IDLE, ACTIVE = 0, 1, 2
# Things the worker does with the machine. Task and progress markers, stuck labels, coach events, the idle monitor
# and lock/sleep are derived or system events: they are not presence on their own.
INPUT_TYPES = frozenset({"nav", "click", "scroll", "focus", "tab", "copy", "paste", "search", "undo", "unlock", "resume"})
NOT_INPUT = {"idle", "lock", "sleep", "task_start", "task_end", "progress", "stuck", "coach_shown", "coach_followed",
             "coach_dismissed", "agent_step", "approval"}
MIN_PER_WEEK = 7 * 24 * 60


@dataclass(frozen=True)
class Spell:
    """An idle spell: the worker stopped at ``start`` (unix seconds) and came back ``duration_min`` later."""

    start: float
    duration_min: float
    tod_min: float      # local minute of day at the start
    dow: int            # local day of week at the start, Monday = 0
    ended: bool = True  # False for a spell still open at the end of the data (right-censored)


@dataclass
class DayObs:
    day: date
    states: np.ndarray  # shape (96,), values OFF/IDLE/ACTIVE


def _to_seconds(t: Any) -> float:
    if isinstance(t, datetime):
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(t, (int, float)):
        return float(t)
    return datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()


def normalise_events(events: Iterable[Any]) -> list[tuple[float, str]]:
    """Accept core.Event objects or dicts; keep human events as (unix seconds, type), sorted."""
    out: list[tuple[float, str]] = []
    for e in events:
        get = (lambda k, d=None: e.get(k, d)) if isinstance(e, dict) else (lambda k, d=None: getattr(e, k, d))
        if str(get("actor", "human")) != "human":
            continue
        out.append((_to_seconds(get("t")), str(get("type", "click"))))
    out.sort()
    return out


def _local(ts: float, tz: ZoneInfo | timezone) -> datetime:
    return datetime.fromtimestamp(ts, tz)


def get_tz(name: str | None) -> ZoneInfo | timezone:
    return timezone.utc if not name or name.upper() == "UTC" else ZoneInfo(name)


def spells_from_events(events: Iterable[Any], *, tz: str | None = "UTC", min_gap_min: float = 5.0,
                       censor_at: float | None = None) -> list[Spell]:
    """Idle spells of at least ``min_gap_min`` between consecutive human inputs."""
    zone = get_tz(tz)
    ev = [(t, k) for t, k in normalise_events(events)]
    inputs = [t for t, k in ev if k in INPUT_TYPES]
    out: list[Spell] = []
    for a, b in zip(inputs, inputs[1:]):
        gap = (b - a) / 60.0
        if gap >= min_gap_min:
            loc = _local(a, zone)
            out.append(Spell(a, gap, loc.hour * 60 + loc.minute + loc.second / 60.0, loc.weekday(), True))
    if censor_at is not None and inputs and censor_at > inputs[-1]:
        gap = (censor_at - inputs[-1]) / 60.0
        if gap >= min_gap_min:
            loc = _local(inputs[-1], zone)
            out.append(Spell(inputs[-1], gap, loc.hour * 60 + loc.minute, loc.weekday(), False))
    return out


def day_states_from_events(events: Iterable[Any], *, tz: str | None = "UTC", min_events: int = 1,
                           first_day: date | None = None, last_day: date | None = None,
                           awake_grace_min: float = 60.0) -> list[DayObs]:
    """One 96-bin state vector per local calendar day (``first_day`` to ``last_day``, default first to last event).

    Machine state: a ``sleep`` event switches the machine off until the next event of any kind. With no ``sleep``
    event the machine is assumed to go to sleep ``awake_grace_min`` minutes after the last event of any kind (a
    screen lock, an idle report, an input): a real auto-sleep timer, and the reason a Friday evening that ends with a
    lock still shows an off weekend. Days with no events at all are therefore off, not idle. Pass ``first_day`` and
    ``last_day`` when the observation window is known (install date to today) so trailing quiet days are not dropped.
    """
    zone = get_tz(tz)
    ev = normalise_events(events)
    if not ev:
        return []
    d0 = first_day or _local(ev[0][0], zone).date()
    d1 = last_day or _local(ev[-1][0], zone).date()
    ndays = (d1 - d0).days + 1
    origin = datetime.combine(d0, datetime.min.time(), tzinfo=zone).timestamp()
    counts = np.zeros((ndays, SLOTS), dtype=np.int32)
    grace = awake_grace_min * 60.0
    asleep_iv: list[tuple[float, float]] = []
    if ev[0][0] > origin:
        asleep_iv.append((origin, ev[0][0]))  # nothing observed yet: the machine state is unknown, treat as off
    for i, (t, kind) in enumerate(ev):
        nxt = ev[i + 1][0] if i + 1 < len(ev) else None
        awake_end = t if kind == "sleep" else t + grace
        if nxt is not None and awake_end < nxt:
            asleep_iv.append((awake_end, nxt))
        elif nxt is None:
            asleep_iv.append((awake_end, origin + ndays * 86400.0))
        if kind in INPUT_TYPES:
            loc = _local(t, zone)
            di = (loc.date() - d0).days
            if 0 <= di < ndays:
                counts[di, (loc.hour * 60 + loc.minute) // 15] += 1
    asleep = np.zeros(ndays * SLOTS, dtype=bool)
    for a, b in asleep_iv:
        # bins are 15 local minutes; test the bin centre. (Local days of 23 or 25 hours across a DST change are
        # approximated by 24 hours; the synthetic data is UTC and a real install can pass its own window.)
        i0 = max(0, int(np.ceil((a - origin - 450.0) / 900.0)))
        i1 = min(ndays * SLOTS, int(np.floor((b - origin - 450.0) / 900.0)) + 1)
        if i1 > i0:
            asleep[i0:i1] = True
    asleep = asleep.reshape(ndays, SLOTS)
    states = np.where(counts >= min_events, ACTIVE, np.where(asleep, OFF, IDLE)).astype(np.int8)
    return [DayObs(d0 + timedelta(days=i), states[i]) for i in range(ndays)]


def days_from_matrix(states: Sequence[Sequence[int]], start: date) -> list[DayObs]:
    """Helper for tests and fixtures: rows of 96 states starting at ``start``."""
    return [DayObs(start + timedelta(days=i), np.asarray(row, dtype=np.int8)) for i, row in enumerate(states)]
