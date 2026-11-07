"""Pure reducer and replay (CAP-3).

``fold(events) -> State`` has no clock, no I/O and no randomness: the same events always give an
equal State. ``replay`` walks a file or an event list on a virtual clock: the gap between two
events is squeezed to ``squeeze_idle_s`` and divided by ``speed``.

The idea (an append-only log, a pure reducer, replay with idle gaps squeezed) is described in
docs/reference-notes/mark8.md; the code is our own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..core import Event

LabelFn = Callable[[Event], str | None]


@dataclass
class TaskState:
    task_id: str
    person: str
    t_start: float | None = None
    t_end: float | None = None
    n_events: int = 0
    n_progress: int = 0
    n_stuck: int = 0

    @property
    def duration(self) -> float | None:
        if self.t_start is None or self.t_end is None:
            return None
        return self.t_end - self.t_start


@dataclass
class State:
    n_events: int = 0
    first_t: float | None = None
    last_t: float | None = None
    by_type: dict[str, int] = field(default_factory=dict)
    by_person: dict[str, int] = field(default_factory=dict)
    tasks: dict[str, TaskState] = field(default_factory=dict)
    open_task: dict[str, str] = field(default_factory=dict)   # person -> task_id
    os_state: dict[str, str] = field(default_factory=dict)    # person -> active|idle|locked|asleep
    last_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "n_events": self.n_events,
            "first_t": self.first_t,
            "last_t": self.last_t,
            "by_type": dict(sorted(self.by_type.items())),
            "by_person": dict(sorted(self.by_person.items())),
            "tasks": {
                k: {"person": v.person, "t_start": v.t_start, "t_end": v.t_end, "n_events": v.n_events,
                    "n_progress": v.n_progress, "n_stuck": v.n_stuck}
                for k, v in sorted(self.tasks.items())
            },
            "open_task": dict(sorted(self.open_task.items())),
            "os_state": dict(sorted(self.os_state.items())),
            "last_type": self.last_type,
        }


_OS_TRANSITION = {"idle": "idle", "lock": "locked", "sleep": "asleep", "unlock": "active", "resume": "active"}


def step(state: State, ev: Event) -> State:
    """Apply one event to ``state`` in place and return it (the building block of ``fold``)."""
    t = ev.t.timestamp()
    state.n_events += 1
    state.first_t = t if state.first_t is None else min(state.first_t, t)
    state.last_t = t if state.last_t is None else max(state.last_t, t)
    state.by_type[ev.type] = state.by_type.get(ev.type, 0) + 1
    state.by_person[ev.person] = state.by_person.get(ev.person, 0) + 1
    state.last_type = ev.type
    if ev.type in _OS_TRANSITION:
        state.os_state[ev.person] = _OS_TRANSITION[ev.type]
    elif ev.actor == "human":
        state.os_state[ev.person] = "active"
    if ev.task_id:
        ts = state.tasks.get(ev.task_id)
        if ts is None:
            ts = state.tasks[ev.task_id] = TaskState(ev.task_id, ev.person)
        ts.n_events += 1
        if ev.type == "task_start":
            ts.t_start = t
            state.open_task[ev.person] = ev.task_id
        elif ev.type == "task_end":
            ts.t_end = t
            if state.open_task.get(ev.person) == ev.task_id:
                del state.open_task[ev.person]
        elif ev.type == "progress":
            ts.n_progress += 1
        elif ev.type == "stuck":
            ts.n_stuck += 1
    return state


def fold(events: Iterable[Event]) -> State:
    """Pure reducer over events in the order given."""
    state = State()
    for ev in events:
        step(state, ev)
    return state


# ----------------------------------------------------------------------------- replay
@dataclass
class Frame:
    t_replay: float
    event: Event
    state: dict  # {"task": str|None, "last_cog": str|None, "counts": {label: int}}


@dataclass
class Replay:
    duration_s: float
    frames: list[Frame]
    final: State


def replay(
    source: Path | str | Iterable[Event],
    speed: float = 1.0,
    squeeze_idle_s: float = 30.0,
    *,
    label_fn: LabelFn | None = None,
    store=None,
    person: str | None = None,
    task: str | None = None,
) -> Replay:
    """Replay a JSONL file (or an event iterable) on a virtual clock.

    ``t_replay[i] = t_replay[i-1] + min(gap_i, squeeze_idle_s) / speed``. ``label_fn`` maps an event
    to the label counted in ``state.counts`` (default: the event type; the API passes the cog mapper).
    Deterministic: the same input gives equal frames every time.
    """
    if speed <= 0:
        raise ValueError("speed must be positive")
    if isinstance(source, (str, Path)):
        from .jsonl import EventStore

        events = (store or EventStore()).read_file(source)
    else:
        events = list(source)
    if person:
        events = [e for e in events if e.person == person]
    if task:
        events = [e for e in events if e.task_id == task]
    events = sorted(events, key=lambda e: (e.t, e.id))
    label_fn = label_fn or (lambda e: e.type)

    frames: list[Frame] = []
    counts: dict[str, int] = {}
    cur_task: str | None = None
    last_label: str | None = None
    t_rep = 0.0
    prev_t: float | None = None
    state = State()
    for ev in events:
        t = ev.t.timestamp()
        if prev_t is not None:
            t_rep += min(max(0.0, t - prev_t), squeeze_idle_s) / speed
        prev_t = t
        step(state, ev)
        lab = label_fn(ev)
        if lab:
            counts[lab] = counts.get(lab, 0) + 1
            last_label = lab
        if ev.type == "task_start":
            cur_task = ev.task_id
        elif ev.type == "task_end":
            cur_task = None
        frames.append(Frame(round(t_rep, 6), ev, {"task": cur_task, "last_cog": last_label, "counts": dict(counts)}))
    return Replay(duration_s=round(t_rep, 6), frames=frames, final=state)
