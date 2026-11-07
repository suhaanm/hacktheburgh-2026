"""JSON calendar source: a simple export format (``understudy.calendar.v1``) for synthetic data and hand-made exports.

Accepted shapes: a list of events, or ``{"format": "understudy.calendar.v1", "tz": "Europe/London", "events": [...]}``.
Each event: ``start`` and ``end`` (ISO-8601; an offset or ``Z`` is honoured, a naive time uses the file's ``tz``),
optional ``title``, ``organizer``, ``attendees`` (list of addresses) or ``n_attendees``, ``location``, ``all_day``,
``recurring``, ``series`` (an opaque series id), ``show_as``, ``status``, ``online``, ``provider``, ``response``.
Unknown keys are ignored. Read-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterator

from .base import RawItem, Source, SourceError, overlaps
from .schemas import PROVIDER, RESPONSE, SHOW_AS, STATUS
from .tz import local_to_utc, resolve_tz

UTC = timezone.utc
FORMAT = "understudy.calendar.v1"


class JSONCalendarSource(Source):
    plugin_id = "jsoncal"
    schema_id = "calendar_event.v1"

    def __init__(self, data: Any = None, *, path: str | Path | None = None, default_tz: str = "UTC"):
        super().__init__()
        if (data is None) == (path is None):
            raise ValueError("give exactly one of data (parsed JSON or JSON text) or path")
        if path is not None:
            data = Path(path).read_text(encoding="utf-8")
        if isinstance(data, (str, bytes)):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise SourceError("bad_json", f"calendar JSON did not parse (line {exc.lineno})") from None
        self._data = data
        self._default_tz: tzinfo = resolve_tz(default_tz) or UTC

    def _dt(self, v: Any, tz: tzinfo) -> datetime | None:
        if not isinstance(v, str):
            return None
        s = v.strip().replace("Z", "+00:00").replace("z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        return dt.astimezone(UTC) if dt.tzinfo else local_to_utc(dt, tz)

    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        data = self._data
        tz = self._default_tz
        if isinstance(data, dict):
            fmt = data.get("format")
            if fmt not in (None, FORMAT):
                raise SourceError("unknown_format")
            tz = resolve_tz(data.get("tz")) or tz
            events = data.get("events", [])
        else:
            events = data
        if not isinstance(events, list):
            raise SourceError("bad_shape")
        out: list[RawItem] = []
        for ev in events:
            if not isinstance(ev, dict):
                self._note("event_not_object")
                continue
            t0 = self._dt(ev.get("start"), tz)
            t1 = self._dt(ev.get("end"), tz)
            all_day = bool(ev.get("all_day", False))
            if t0 is None:
                self._note("bad_datetime")
                continue
            if t1 is None:
                t1 = t0 + timedelta(days=1) if all_day else t0
            if t1 < t0:
                self._note("end_before_start")
                t1 = t0
            attendees = [str(a).lower() for a in ev.get("attendees", []) if isinstance(a, (str, int))]
            organizer = str(ev.get("organizer", "")).lower()
            people = set(attendees) | ({organizer} if organizer else set())
            n = ev.get("n_attendees")
            n = int(n) if isinstance(n, int) and not isinstance(n, bool) else max(1, len(people))
            show_as = ev.get("show_as", "busy")
            status = ev.get("status", "confirmed")
            provider = ev.get("provider", "teams" if ev.get("online") else "none")
            response = ev.get("response", "none")
            recurring = bool(ev.get("recurring", bool(ev.get("series"))))
            fields = {
                "title": str(ev.get("title", "")),
                "organizer": organizer,
                "attendees": sorted(attendees),
                "location": str(ev.get("location", "")),
                "series_id": str(ev.get("series", "")) if recurring else "",
                "source_id": str(ev.get("id", "")),
                "n_attendees": max(1, n),
                "all_day": all_day,
                "recurring": recurring,
                "online": bool(ev.get("online", provider != "none")),
                "show_as": show_as if show_as in SHOW_AS else "busy",
                "status": status if status in STATUS else "confirmed",
                "response": response if response in RESPONSE else "none",
                "provider": provider if provider in PROVIDER else "other",
                "sensitivity": "normal",
            }
            if overlaps(t0, t1, since, until):
                out.append(RawItem("calendar_event", t0, t1, fields))
        out.sort(key=lambda r: (r.t0, r.t1))
        self._note("events_read", len(out))
        yield from out
