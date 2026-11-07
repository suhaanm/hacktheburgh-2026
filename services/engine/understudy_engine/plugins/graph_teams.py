"""Microsoft Graph Teams meeting metadata source (``/me/onlineMeetings``, optional attendance reports). **Off by default.**

Emits ``calendar_event`` items with ``online=True`` and ``provider="teams"`` so the calendar features treat a Teams
meeting like any other meeting. With ``with_attendance=True`` it also asks for each meeting's attendance report and sets
``attended_s`` to the owner's own time in the meeting (matched by ``self_address``), or to the report's meeting length when
no address is given. Subjects, participants and join links are read into the item (in memory) and nowhere else.

Shapes follow the public Graph documentation and are exercised only against recorded fake responses; they have not been
checked against a live tenant by this code (tenant policies differ on who may list online meetings at all).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import quote

from .base import RawItem, Source, overlaps
from .graph_common import Fetch, GraphClient, TokenProvider, iso_z, window

UTC = timezone.utc
BASE = "https://graph.microsoft.com/v1.0"


_FRAC = re.compile(r"\.(\d{6})\d+")


def _iso(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    s = _FRAC.sub(r".\1", v.strip().replace("Z", "+00:00"))
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def _upn(p) -> str:
    if not isinstance(p, dict):
        return ""
    return str(p.get("upn") or p.get("emailAddress") or "").lower()


class TeamsMeetingsSource(Source):
    plugin_id = "graph_teams"
    schema_id = "calendar_event.v1"

    def __init__(self, token_provider: TokenProvider, fetch: Fetch | None = None, *, self_address: str | None = None,
                 with_attendance: bool = False, page_size: int = 50, max_pages: int = 100, sleep=None):
        super().__init__()
        kw = {"sleep": sleep} if sleep is not None else {}
        self._client = GraphClient(token_provider, fetch, max_pages=max_pages, **kw)
        self._self = (self_address or "").lower() or None
        self._with_attendance = with_attendance
        self._page_size = page_size

    def url(self, since: datetime, until: datetime) -> str:
        flt = quote(f"startDateTime ge {iso_z(since)} and startDateTime lt {iso_z(until)}")
        return f"{BASE}/me/onlineMeetings?$top={self._page_size}&$filter={flt}"

    def _attended_s(self, meeting_id: str, fallback_s: int) -> int:
        url = f"{BASE}/me/onlineMeetings/{quote(meeting_id, safe='')}/attendanceReports?$expand=attendanceRecords"
        best = 0
        found = False
        for page in self._client.pages(url):
            for rep in page:
                recs = rep.get("attendanceRecords") or []
                if self._self:
                    for r in recs:
                        if _upn(r) == self._self or str(r.get("emailAddress", "")).lower() == self._self:
                            best = max(best, int(r.get("totalAttendanceInSeconds") or 0))
                            found = True
                else:
                    a, b = _iso(rep.get("meetingStartDateTime")), _iso(rep.get("meetingEndDateTime"))
                    if a and b:
                        best = max(best, int((b - a).total_seconds()))
                        found = True
        return best if found else fallback_s

    def _item(self, m: dict) -> RawItem | None:
        t0, t1 = _iso(m.get("startDateTime")), _iso(m.get("endDateTime"))
        if t0 is None or t1 is None or t1 < t0:
            self._note("bad_datetime")
            return None
        parts = m.get("participants") or {}
        organizer = _upn(parts.get("organizer"))
        attendees = sorted({a for a in (_upn(x) for x in parts.get("attendees") or []) if a})
        people = set(attendees) | ({organizer} if organizer else set())
        fields = {
            "title": str(m.get("subject") or ""),
            "organizer": organizer,
            "attendees": attendees,
            "location": "",
            "series_id": "",
            "source_id": str(m.get("id") or ""),
            "n_attendees": max(1, len(people)),
            "all_day": False,
            "recurring": False,
            "online": True,
            "show_as": "busy",
            "status": "confirmed",
            "response": "organizer" if self._self and organizer == self._self else "none",
            "provider": "teams",
            "sensitivity": "normal",
        }
        if self._with_attendance and m.get("id"):
            fields["attended_s"] = self._attended_s(str(m["id"]), int((t1 - t0).total_seconds()))
        return RawItem("calendar_event", t0, t1, fields)

    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        s, u = window(since, until)
        out: list[RawItem] = []
        for page in self._client.pages(self.url(s, u)):
            self._note("pages")
            for m in page:
                if not isinstance(m, dict):
                    continue
                item = self._item(m)
                if item is not None and overlaps(item.t0, item.t1, s, u):
                    out.append(item)
        out.sort(key=lambda r: (r.t0, r.t1))
        self._note("events_read", len(out))
        yield from out
