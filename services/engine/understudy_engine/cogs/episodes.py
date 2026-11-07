"""Episode segmentation (ANA-1): one task attempt by one person as an ordered cog sequence."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from ..core import Episode, Event
from .mapper import Mapping, to_cogs


def segment_episodes(
    events: Iterable[Event],
    pack_mapping: Mapping | dict | str | Path | None = None,
    idle_s: float = 60.0,
    include_untagged: bool | None = None,
) -> list[Episode]:
    """Group events into episodes and map each to cogs.

    Events with a ``task_id`` form one episode per (person, task_id): the span is task_start..task_end when
    present, else first..last event. Events without a task_id are background: they only form episodes
    (split wherever the silence reaches ``idle_s``) for a person who has no tagged events at all (live
    capture before any task markers exist), or when ``include_untagged`` is True.
    A ``progress`` event is domain-defined; its time is kept in ``progress_t``.
    """
    by_person: dict[str, list[Event]] = defaultdict(list)
    for ev in sorted(events, key=lambda e: (e.t, e.id)):
        by_person[ev.person].append(ev)

    out: list[Episode] = []
    for person, evs in by_person.items():
        tagged: dict[str, list[Event]] = defaultdict(list)
        untagged: list[Event] = []
        for ev in evs:
            (tagged[ev.task_id] if ev.task_id else untagged).append(ev)
        for tid, tevs in tagged.items():
            out.append(_episode(tid, person, tevs, pack_mapping))
        use_untagged = include_untagged if include_untagged is not None else not tagged
        if use_untagged and untagged:
            chunk: list[Event] = []
            n = 0
            for ev in untagged:
                if chunk and ev.t.timestamp() - chunk[-1].t.timestamp() >= idle_s:
                    n += 1
                    out.append(_episode(f"t_u{person[2:]}{n:04d}", person, chunk, pack_mapping))
                    chunk = []
                chunk.append(ev)
            if chunk:
                out.append(_episode(f"t_u{person[2:]}{n + 1:04d}", person, chunk, pack_mapping))
    out.sort(key=lambda e: (e.t0, e.person))
    return out


def _episode(task_id: str, person: str, evs: list[Event], pack_mapping) -> Episode:
    ts = [e.t.timestamp() for e in evs]
    starts = [e.t.timestamp() for e in evs if e.type == "task_start"]
    ends = [e.t.timestamp() for e in evs if e.type == "task_end"]
    t0 = min(starts) if starts else min(ts)
    t1 = max(ends) if ends else max(ts)
    cogs = to_cogs(evs, pack_mapping, t_end=t1 if ends else None)
    if cogs and not ends:
        t1 = max(t1, cogs[-1].t1)
    return Episode(
        task_id=task_id, person=person, role=evs[0].role, origin=evs[0].origin, t0=t0, t1=t1, cogs=cogs,
        progress_t=[e.t.timestamp() for e in evs if e.type == "progress"],
    )
