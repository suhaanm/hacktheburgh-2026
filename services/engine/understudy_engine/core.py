"""Shared core types for the engine. Written by the lead; both engine tracks import from here.

Do not change field names without a CONTRACT-CHANGE message to the lead. Mirrors
packages/schema/event.schema.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["real", "synthetic"]
Actor = Literal["human", "agent"]
Source = Literal["browser", "screen", "os", "desk", "agent", "coach"]

EVENT_TYPES = (
    "nav", "click", "scroll", "focus", "tab", "copy", "paste", "search",
    "idle", "lock", "unlock", "sleep", "resume", "stuck",
    "coach_shown", "coach_followed", "coach_dismissed",
    "agent_step", "approval", "undo", "task_start", "task_end", "progress",
)
EventType = Literal[
    "nav", "click", "scroll", "focus", "tab", "copy", "paste", "search",
    "idle", "lock", "unlock", "sleep", "resume", "stuck",
    "coach_shown", "coach_followed", "coach_dismissed",
    "agent_step", "approval", "undo", "task_start", "task_end", "progress",
]

BASE_COGS = (
    "READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE",
    "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK",
)


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str | None = None
    label_hash: str | None = None   # "h:<hex>"
    domain_hash: str | None = None  # "d:<hex>"


class Event(BaseModel):
    """Event schema v1. No free text, no URLs, no field values. `meta` holds numbers/enums only."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(1, alias="schema")
    id: str
    t: datetime
    origin: Origin
    actor: Actor
    person: str
    role: str
    source: Source
    type: EventType
    target: Target | None = None
    task_id: str | None = None
    meta: dict[str, int | float | str | bool] = Field(default_factory=dict)


@dataclass(frozen=True)
class Cog:
    """A cognitive-step segment. t0/t1 are unix seconds (UTC)."""

    t0: float
    t1: float
    id: str  # base cog or role cog

    @property
    def dwell(self) -> float:
        return max(0.0, self.t1 - self.t0)


@dataclass
class Episode:
    """One task attempt by one person: an ordered cog sequence."""

    task_id: str
    person: str
    role: str
    origin: Origin
    t0: float
    t1: float
    cogs: list[Cog] = field(default_factory=list)
    progress_t: list[float] = field(default_factory=list)  # unix seconds of `progress` events

    @property
    def duration(self) -> float:
        return max(0.0, self.t1 - self.t0)


# Convention for every analytic API response: {"meta": AnalyticMeta, "data": ...}
class AnalyticMeta(BaseModel):
    origin: Origin | Literal["mixed"]
    n: int
    n_unit: str = "people"          # what n counts: people, personas, households, episodes, days
    split: str | None = None        # e.g. "leave-one-person-out"
    interval_level: float = 0.95
    note: str | None = None         # honest caveat shown beside the chart
    generated_at: datetime | None = None
