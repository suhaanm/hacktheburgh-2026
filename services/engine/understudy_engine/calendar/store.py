"""Calendar store: where the layer reads people's calendars from, and the one place a ``Source`` becomes analysed weeks.

Synthetic calendars live under ``<data>/synthetic/calendars`` (``index.json`` lists people, zone, usual hours and the
owner's own address; ``truth.json`` is the planted truth and is only read by the evaluation). If the folder is missing the
store generates the same deterministic data in memory (mock mode must answer every endpoint without a setup step).

``CalendarStore.analyse`` is the pipeline: source -> RawItem (text, in memory) -> ``to_blocks`` (text stops here) ->
``analyse_week``. Nothing textual is cached: only blocks (no text), features and counts.
"""
from __future__ import annotations

import json
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ..plugins.base import Source
from ..plugins.ics import ICSSource
from ..plugins.jsoncal import JSONCalendarSource
from ..store.paths import data_dir
from .features import WeekAnalysis, analyse_week
from .model import Block, WorkConfig, monday_of, week_label
from .normalize import NormStats, to_blocks

UTC = timezone.utc


@dataclass
class PersonCalendar:
    person: str
    group: str
    role: str
    work: WorkConfig
    blocks: list[Block]
    off_dates: frozenset[date]
    stats: NormStats
    origin: str = "synthetic"
    weeks: list[date] = field(default_factory=list)       # Mondays covered by at least one block

    def week(self, monday: date) -> WeekAnalysis:
        return analyse_week(self.blocks, self.work, monday, self.off_dates)

    def all_weeks(self) -> list[WeekAnalysis]:
        return [self.week(m) for m in self.weeks]


def load_blocks(source: Source, work: WorkConfig, since: datetime | None = None, until: datetime | None = None
                ) -> tuple[list[Block], frozenset[date], NormStats]:
    """Read a source and reduce it to text-free blocks. The raw items are consumed here and not kept."""
    return to_blocks(source.read(since, until), work)


def week_mondays(blocks: list[Block], work: WorkConfig) -> list[date]:
    days = sorted({b.start.astimezone(work.tz).date() for b in blocks})
    return sorted({monday_of(d) for d in days})


class CalendarStore:
    def __init__(self, root: Path | str | None = None, *, canary: bool = False):
        self._root = Path(root) if root else None
        self._canary = canary
        self._lock = threading.Lock()
        self._index: dict[str, Any] | None = None
        self._dir: Path | None = None
        self._cache: dict[str, PersonCalendar] = {}
        self._tmp: tempfile.TemporaryDirectory | None = None

    # --- location
    def _ensure(self) -> None:
        if self._index is not None:
            return
        with self._lock:
            if self._index is not None:
                return
            base = self._root if self._root else data_dir()
            d = base / "synthetic" / "calendars" / ("canary" if self._canary else "")
            if not (d / "index.json").is_file():
                from . import synth
                self._tmp = tempfile.TemporaryDirectory(prefix="understudy-cal-")
                synth.generate(self._tmp.name, canary=self._canary)
                d = Path(self._tmp.name) / "synthetic" / "calendars" / ("canary" if self._canary else "")
            self._dir = d
            self._index = json.loads((d / "index.json").read_text(encoding="utf-8"))

    @property
    def directory(self) -> Path:
        self._ensure()
        assert self._dir is not None
        return self._dir

    def meta(self) -> dict[str, Any]:
        self._ensure()
        return dict(self._index["meta"])          # type: ignore[index]

    def people(self, group: str | None = None) -> list[str]:
        self._ensure()
        return [p for p, v in self._index["people"].items() if group is None or v["group"] == group]   # type: ignore[index]

    def info(self, person: str) -> dict[str, Any] | None:
        self._ensure()
        return self._index["people"].get(person)    # type: ignore[index]

    def truth(self) -> dict[str, Any] | None:
        self._ensure()
        p = self.directory / "truth.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    # --- loading
    def source_for(self, person: str, kind: str = "ics") -> tuple[Source, WorkConfig, dict[str, Any]]:
        info = self.info(person)
        if info is None:
            raise KeyError(person)
        work = WorkConfig.from_dict(info["work"])
        path = self.directory / (info["ics"] if kind == "ics" else info["json"])
        if kind == "ics":
            src: Source = ICSSource(path=path, default_tz=info["tz"], self_email=info.get("self_email"))
        else:
            src = JSONCalendarSource(path=path, default_tz=info["tz"])
        return src, work, info

    def get(self, person: str, kind: str = "ics") -> PersonCalendar | None:
        key = f"{person}:{kind}"
        if key in self._cache:
            return self._cache[key]
        if self.info(person) is None:
            return None
        src, work, info = self.source_for(person, kind)
        blocks, off, stats = load_blocks(src, work)
        pc = PersonCalendar(person, info["group"], info["role"], work, blocks, off, stats, "synthetic", week_mondays(blocks, work))
        with self._lock:
            self._cache[key] = pc
        return pc

    def cohort(self, group: str, kind: str = "ics") -> list[PersonCalendar]:
        return [pc for p in self.people(group) if (pc := self.get(p, kind)) is not None]


_default: CalendarStore | None = None
_default_lock = threading.Lock()


def default_store() -> CalendarStore:
    """Process-wide store over the configured data directory (reset with ``reset_default`` after regenerating data)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = CalendarStore()
        return _default


def reset_default() -> None:
    global _default
    with _default_lock:
        _default = None
