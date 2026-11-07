"""Calendar layer data model. A ``Block`` holds **no text**: no title, no name, no address, no id. It is what raw
calendar items are reduced to the moment they are read (see ``normalize.py``), so everything downstream of that line
(features, expert gaps, suggestions, API responses, evaluation) can only ever contain numbers and enums."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Mapping

UTC = timezone.utc
KINDS = ("meeting", "focus", "break", "offscreen")
TAGS = ("", "batch", "review")
Window = tuple[int, int]            # (start minute, end minute) after local midnight


@dataclass(frozen=True)
class Block:
    start: datetime                  # UTC
    end: datetime                    # UTC
    kind: str                        # meeting | focus | break | offscreen
    tag: str = ""                    # "" | batch | review (only for kind == focus)
    n_attendees: int = 1
    recurring: bool = False
    series: str = ""                 # opaque, per-process salted hash; never emitted
    external: bool = False
    online: bool = False

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


def attendee_bucket(n: int) -> str:
    return "lt5" if n < 5 else ("5to9" if n < 10 else "10plus")


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt_hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@dataclass
class WorkConfig:
    """The person's usual hours (from onboarding) and the analysis zone. ``by_date`` overrides single dates (a schedule
    change, a day off as ``None``)."""

    tz: tzinfo = UTC
    start_min: int = 9 * 60
    end_min: int = 17 * 60 + 30
    days: tuple[int, ...] = (0, 1, 2, 3, 4)       # Monday = 0
    peak: Window = (30, 180)                       # when judgement-heavy work happens: minutes after the window starts
    by_date: dict[date, Window | None] = field(default_factory=dict)
    b2b_gap_min: float = 5.0                       # gaps up to this are "back to back"
    buffer_min: float = 10.0                       # wanted buffer before an external call
    tz_name: str = "UTC"

    def peak_for(self, window: Window) -> Window:
        return (window[0] + self.peak[0], window[0] + self.peak[1])

    def window(self, d: date) -> Window | None:
        if d in self.by_date:
            return self.by_date[d]
        if d.weekday() in self.days:
            return (self.start_min, self.end_min)
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"tz": self.tz_name, "start": fmt_hm(self.start_min), "end": fmt_hm(self.end_min), "days": list(self.days),
                "peak_offset_min": [self.peak[0], self.peak[1]],
                "by_date": {d.isoformat(): (None if w is None else [fmt_hm(w[0]), fmt_hm(w[1])]) for d, w in sorted(self.by_date.items())}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "WorkConfig":
        from ..plugins.tz import resolve_tz
        name = d.get("tz", "UTC")
        by_date: dict[date, Window | None] = {}
        for k, v in (d.get("by_date") or {}).items():
            by_date[date.fromisoformat(k)] = None if v is None else (_hm(v[0]), _hm(v[1]))
        return cls(tz=resolve_tz(name) or UTC, tz_name=name, start_min=_hm(d.get("start", "09:00")), end_min=_hm(d.get("end", "17:30")),
                   days=tuple(d.get("days", (0, 1, 2, 3, 4))), peak=tuple(d["peak_offset_min"]) if d.get("peak_offset_min") else (30, 180),
                   by_date=by_date)


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def parse_week(week: str | date | None) -> date | None:
    """``2026-W44``, ``2026-10-26`` or a date to the Monday of that week. None stays None."""
    if week is None or week == "":
        return None
    if isinstance(week, date):
        return monday_of(week)
    w = str(week).strip()
    if "-W" in w.upper():
        y, ww = w.upper().split("-W")
        return date.fromisocalendar(int(y), int(ww), 1)
    return monday_of(date.fromisoformat(w))


def week_label(monday: date) -> str:
    y, w, _ = monday.isocalendar()
    return f"{y}-W{w:02d}"
