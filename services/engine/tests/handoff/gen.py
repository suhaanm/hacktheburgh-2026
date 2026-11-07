"""Tiny deterministic generators for the handoff tests. Each uses a different mechanism from the models it tests.

* ``presence_events``: block schedules with jitter, bursts of input with exponential gaps, short pauses.
* ``routine_episodes``: episodes (cog sequences with dwell times) with planted routines plus noise episodes.
* ``workdays``: counts of a routine per day for ski-rental simulation.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta, timezone

from understudy_engine.core import Cog, Episode

UTC = timezone.utc

SCHEDULES = {
    # day-of-week (Mon=0) -> list of (start_hour, end_hour); hours past 24 run into the next day
    "nine_to_five": {d: [(9.0, 12.5), (13.5, 17.5)] for d in range(5)},
    "night_owl": {d: [(14.0, 19.0), (21.0, 26.0)] for d in range(7)},
    "shift": {d: [(6.0, 14.0)] for d in (0, 1, 2, 5, 6)},
    "irregular": {},
}


def _dt(day: date, hour: float) -> datetime:
    return datetime.combine(day, time(0), tzinfo=UTC) + timedelta(hours=hour)


def presence_events(persona: str = "nine_to_five", days: int = 21, seed: int = 1, start: date = date(2026, 10, 12),
                    with_sleep: bool = True, p_pause: float = 0.04):
    """Human input events for ``days`` days from 12 Oct 2026 (a Monday). Returns (events, windows_by_dow)."""
    rng = random.Random(seed * 1009 + sum(map(ord, persona)))
    events = []
    sched = SCHEDULES[persona]
    for i in range(days):
        day = start + timedelta(days=i)
        dow = day.weekday()
        blocks = list(sched.get(dow, []))
        if persona == "irregular":
            blocks = []
            for _ in range(rng.choice([0, 1, 1, 2, 3])):
                a = rng.uniform(7, 21)
                blocks.append((a, a + rng.uniform(0.5, 3.5)))
        if persona == "nine_to_five" and rng.random() < 0.04:
            blocks = []  # a sick day
        last = None
        for (a, b) in blocks:
            a += rng.gauss(0, 0.2)
            b += rng.gauss(0, 0.2)
            t = _dt(day, a)
            end = _dt(day, b)
            if with_sleep and last is None:
                events.append({"t": t - timedelta(seconds=30), "type": "resume", "actor": "human"})
            while t < end:
                events.append({"t": t, "type": rng.choice(["click", "scroll", "nav", "focus"]), "actor": "human"})
                gap = rng.expovariate(1 / 45.0)
                if rng.random() < p_pause:
                    gap += math.exp(rng.gauss(math.log(7 * 60), 0.7))
                t += timedelta(seconds=min(gap, 3 * 3600))
            last = end
        if with_sleep and last is not None:
            events.append({"t": last + timedelta(minutes=20), "type": "sleep", "actor": "human"})
        # an agent action must never count as presence
        if blocks:
            events.append({"t": _dt(day, 3.0), "type": "agent_step", "actor": "agent"})
    events.sort(key=lambda e: e["t"])
    return events, sched


def truth_active_matrix(persona: str):
    """(7, 96) booleans: slot lies inside a planted block (hours past 24 wrap to the next day)."""
    import numpy as np

    m = np.zeros((7, 96), dtype=bool)
    for dow, blocks in SCHEDULES[persona].items():
        for a, b in blocks:
            for s in range(96):
                h = s * 0.25
                if a <= h < min(b, 24):
                    m[dow, s] = True
                if b > 24 and h < b - 24:
                    m[(dow + 1) % 7, s] = True
    return m


# ------------------------------------------------------------------------------ routines
BASE_PATTERNS = {
    # planted routines: label -> cog sequence
    "calc-entry": ["OPEN", "ENTER", "READ", "OPEN", "ENTER", "READ", "COPY"],
    "result-to-note": ["READ", "COPY", "PASTE", "CHECK"],
    "weekly-refresh": ["SEARCH", "NAVIGATE", "COPY", "PASTE", "ENTER", "CHECK"],
}
NOISE_COGS = ["READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE", "COMPARE", "CHECK", "DECIDE", "ASK", "REVERT"]


def routine_episodes(seed: int = 3, days: int = 21, start: date = date(2026, 10, 12), planted: dict[str, float] | None = None,
                     n_noise_per_day: float = 5.0, person: str = "p_t", slip: float = 0.12):
    """Episodes: planted routines (daily Poisson rate, one random slip per run with prob ``slip``) plus random noise.

    Returns (episodes, labels) where labels[i] is the planted routine name or None for noise.
    """
    planted = planted if planted is not None else {"calc-entry": 1.0, "result-to-note": 0.8}
    rng = random.Random(seed)
    eps: list[Episode] = []
    labels: list[str | None] = []

    def make(seq, t0, kind):
        cogs, t = [], t0
        for c in seq:
            dwell = max(2.0, rng.lognormvariate(math.log(12), 0.5))
            cogs.append(Cog(t, t + dwell, c))
            t += dwell
        return Episode(task_id=f"t_{len(eps)}", person=person, role="r", origin="synthetic", t0=t0, t1=t, cogs=cogs)

    for i in range(days):
        day = start + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        base = _dt(day, 9).timestamp()
        slots = []
        for name, rate in planted.items():
            for _ in range(_poisson(rng, rate)):
                slots.append((rng.uniform(0, 8 * 3600), name))
        for _ in range(_poisson(rng, n_noise_per_day)):
            slots.append((rng.uniform(0, 8 * 3600), None))
        for off, name in sorted(slots, key=lambda x: x[0]):
            if name is None:
                seq = [rng.choice(NOISE_COGS) for _ in range(rng.randint(3, 9))]
            else:
                seq = list(BASE_PATTERNS[name])
                if rng.random() < slip:  # a small variation: one extra or dropped step
                    j = rng.randrange(len(seq))
                    if rng.random() < 0.5:
                        seq.insert(j, "CHECK")
                    elif len(seq) > 3:
                        del seq[j]
            eps.append(make(seq, base + off, name))
            labels.append(name)
    return eps, labels


def _poisson(rng: random.Random, lam: float) -> int:
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1
