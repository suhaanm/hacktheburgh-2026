"""What Cue reads from the rest of the engine: a plain snapshot of the worker's live state, and an adapter that makes one from
``CoachBrain.snapshot``. Tolerant of fields that are missing (a renamed field degrades to ``None`` and Cue answers ``no_context``).

``LiveContext`` holds ids, numbers and times only: cog ids, the last progress and input times, the stuck probability and its
source, and per-cog level and mastery. No events, no text, no payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LiveContext:
    person: str
    role: str
    origin: str = "real"
    task_open: bool = True
    task_id: str | None = None
    cogs: tuple[tuple[str, float], ...] = ()          # (cog id, start time in unix seconds), oldest first
    last_progress_t: float | None = None
    task_t0: float | None = None
    last_input_t: float | None = None
    t: float | None = None                            # when the snapshot was taken (its age is checked against freshness.MAX_AGE_S)
    p_stuck: float | None = None
    p_source: str | None = None                       # "model" | "rule"
    level: dict[str, int] = field(default_factory=dict)       # cog -> help level 1..4
    mastery: dict[str, float] = field(default_factory=dict)   # cog -> mastery 0..1
    # fixtures only (mock mode): force what the model and the screen would say
    fixture: dict[str, Any] | None = None

    @property
    def cog_ids(self) -> tuple[str, ...]:
        return tuple(c for c, _ in self.cogs)


class ContextProvider(Protocol):
    def read(self, person: str, now: float) -> LiveContext | None: ...


def from_snapshot(snap: Any) -> LiveContext | None:
    """``CoachSnapshot`` -> ``LiveContext``. Returns None when the snapshot is unusable (no person, no role)."""
    try:
        person, role = snap.person, snap.role
    except AttributeError:
        return None
    if not person or not role:
        return None
    cogs = tuple((str(getattr(c, "id", None) or c[0]), float(getattr(c, "t0", None) if hasattr(c, "t0") else c[1]))
                 for c in (getattr(snap, "cogs", ()) or ()))
    skills = getattr(snap, "skills", ()) or ()
    level, mastery = {}, {}
    for s in skills:
        cog = getattr(s, "cog", None) or getattr(s, "id", None)
        if cog is None:
            continue
        level[str(cog)] = int(getattr(s, "level", 1))
        mastery[str(cog)] = float(getattr(s, "mastery", 0.0))
    return LiveContext(person=str(person), role=str(role), origin=str(getattr(snap, "origin", "real") or "real"),
                       task_open=bool(getattr(snap, "task_open", bool(cogs))), task_id=getattr(snap, "task_id", None), cogs=cogs,
                       last_progress_t=getattr(snap, "last_progress_t", None), task_t0=cogs[0][1] if cogs else None,
                       last_input_t=getattr(snap, "last_input_t", None), p_stuck=getattr(snap, "p_stuck", None),
                       p_source=getattr(snap, "p_source", None), level=level, mastery=mastery, t=getattr(snap, "t", None))


class BrainProvider:
    """Reads ``CoachBrain.snapshot(person, now, sync=True)``: read-only, writes nothing, never moves the dignity gate."""

    def __init__(self, brain: Any) -> None:
        self.brain = brain

    def read(self, person: str, now: float) -> LiveContext | None:
        fn = getattr(self.brain, "snapshot", None)
        if not callable(fn):
            return None
        try:
            return from_snapshot(fn(person, now, sync=True))
        except Exception:
            return None


class StaticProvider:
    """A provider over fixed contexts, for tests and the mock-mode fixtures."""

    def __init__(self, contexts: dict[str, LiveContext] | None = None) -> None:
        self.contexts = dict(contexts or {})

    def read(self, person: str, now: float) -> LiveContext | None:
        return self.contexts.get(person)
