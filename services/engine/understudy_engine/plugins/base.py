"""Source plugin interface (PLG-1): ``Source.read(since) -> Iterator[RawItem]``.

A ``RawItem`` carries raw content (meeting titles, attendee addresses, commit messages) **in memory only**. The rules
that make that safe (PRV-4):

* a source never writes anywhere: no files, no logs, no cache; it only reads;
* ``RawItem.__repr__`` and ``__str__`` show the kind and the times and withhold the fields, so an accidental
  ``print(item)`` or ``log.info("%s", item)`` cannot leak content;
* nothing downstream may keep ``fields`` past the step that turns an item into numbers or enums (see
  ``understudy_engine.calendar.normalize``, which drops every sensitive field when it builds a ``Block``);
* the item schema (``schemas.py``) says which fields are sensitive text, so a reviewer can see the line between
  "may be stored as a digest" and "stays in memory".

Sources carry no network code unless the manifest says ``network: true`` (the Graph sources), and those are off by
default and take an injected token provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterator, Mapping

UTC = timezone.utc


class SourceError(Exception):
    """A source could not read. The message never contains source content (codes and counts only)."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def as_utc(dt: datetime) -> datetime:
    """Aware datetime in UTC. A naive datetime is a programming error here (adapters resolve zones before this)."""
    if dt.tzinfo is None:
        raise ValueError("RawItem times must be timezone-aware")
    return dt.astimezone(UTC)


@dataclass(frozen=True)
class RawItem:
    """One raw item from a source. ``t0``/``t1`` are UTC; for a point event ``t1 == t0``. ``fields`` holds raw content."""

    kind: str
    t0: datetime
    t1: datetime
    fields: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "t0", as_utc(self.t0))
        object.__setattr__(self, "t1", as_utc(self.t1))
        if self.t1 < self.t0:
            raise ValueError("RawItem ends before it starts")

    @property
    def duration_s(self) -> float:
        return (self.t1 - self.t0).total_seconds()

    def __repr__(self) -> str:        # never show fields
        return f"RawItem(kind={self.kind!r}, t0={self.t0.isoformat()}, t1={self.t1.isoformat()}, fields=<{len(self.fields)} withheld>)"

    __str__ = __repr__


class Source(ABC):
    """Read-only source of raw items. Subclasses set ``plugin_id`` (matches the manifest ``id``) and ``schema_id``."""

    plugin_id: ClassVar[str] = ""
    schema_id: ClassVar[str] = ""

    def __init__(self) -> None:
        # Counts of non-fatal parse problems by code. Codes only, never content.
        self.stats: Counter[str] = Counter()

    @abstractmethod
    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        """Yield raw items overlapping ``[since, until)`` (both optional, UTC), ordered by ``t0``."""

    def describe(self) -> dict[str, Any]:
        return {"id": self.plugin_id, "schema": self.schema_id, "stats": dict(self.stats)}

    def _note(self, code: str, n: int = 1) -> None:
        self.stats[code] += n


def overlaps(t0: datetime, t1: datetime, since: datetime | None, until: datetime | None) -> bool:
    """Whether ``[t0, t1)`` overlaps ``[since, until)``. A zero-length item is a point at ``t0``."""
    if until is not None and t0 >= as_utc(until):
        return False
    if since is not None:
        s = as_utc(since)
        return t1 > s if t1 > t0 else t0 >= s
    return True
