"""Microsoft Graph Outlook calendar source (``/me/calendarView``). **Off by default; read only; aggregate-only use.**

``calendarView`` already expands recurring series into occurrences (``type`` is ``occurrence`` or ``exception``, with a
``seriesMasterId``), so no recurrence expansion happens here. This module parses events (times and zones, paging,
cancelled, all-day, response status, online-meeting flags) into ``RawItem`` objects of schema ``calendar_event.v1``.

Response shapes are taken from the public Graph documentation and exercised only against recorded fake responses
(``tests/plugins/fixtures``); they have not been checked against a live tenant by this code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import quote

from .base import RawItem, Source, overlaps
from .graph_common import Fetch, GraphClient, TokenProvider, iso_z, parse_graph_dt, window
from .tz import resolve_tz

UTC = timezone.utc
BASE = "https://graph.microsoft.com/v1.0"
SELECT = ("subject,start,end,isAllDay,showAs,isCancelled,type,seriesMasterId,attendees,organizer,isOnlineMeeting,"
          "onlineMeetingProvider,location,sensitivity,responseStatus,iCalUId,id")

SHOW_AS = {"free": "free", "tentative": "tentative", "busy": "busy", "oof": "oof", "workingElsewhere": "working_elsewhere", "unknown": "busy"}
RESPONSE = {"organizer": "organizer", "accepted": "accepted", "tentativelyAccepted": "tentative", "declined": "declined",
            "notResponded": "none", "none": "none"}
PROVIDER = {"teamsForBusiness": "teams", "skypeForBusiness": "other", "skypeForConsumer": "other", "unknown": "other"}
SENSITIVITY = {"normal": "normal", "personal": "personal", "private": "private", "confidential": "confidential"}


def _address(obj) -> str:
    try:
        return str(obj["emailAddress"]["address"]).lower()
    except (KeyError, TypeError):
        return ""


class OutlookGraphSource(Source):
    plugin_id = "graph_outlook"
    schema_id = "calendar_event.v1"

    def __init__(self, token_provider: TokenProvider, fetch: Fetch | None = None, *, page_size: int = 50, max_pages: int = 100,
                 sleep=None):
        super().__init__()
        kw = {"sleep": sleep} if sleep is not None else {}
        self._client = GraphClient(token_provider, fetch, max_pages=max_pages, **kw)
        self._page_size = page_size

    def url(self, since: datetime, until: datetime) -> str:
        return (f"{BASE}/me/calendarView?startDateTime={quote(iso_z(since))}&endDateTime={quote(iso_z(until))}"
                f"&$top={self._page_size}&$select={SELECT}&$orderby=start/dateTime")

    def _item(self, ev: dict) -> RawItem | None:
        if ev.get("isCancelled"):
            self._note("cancelled_skipped")
            return None
        t0, t1 = parse_graph_dt(ev.get("start")), parse_graph_dt(ev.get("end"))
        if t0 is None or t1 is None:
            self._note("bad_datetime")
            return None
        if resolve_tz((ev.get("start") or {}).get("timeZone")) is None:
            self._note("tz_unknown_default_used")
        all_day = bool(ev.get("isAllDay"))
        organizer = _address(ev.get("organizer"))
        attendees = sorted({a for a in (_address(x) for x in ev.get("attendees") or []) if a})
        people = set(attendees) | ({organizer} if organizer else set())
        typ = ev.get("type", "singleInstance")
        recurring = typ in ("occurrence", "exception", "seriesMaster")
        online = bool(ev.get("isOnlineMeeting"))
        provider = PROVIDER.get(ev.get("onlineMeetingProvider") or "unknown", "other") if online else "none"
        resp = RESPONSE.get((ev.get("responseStatus") or {}).get("response", "none"), "none")
        loc = ev.get("location")
        fields = {
            "title": str(ev.get("subject") or ""),
            "organizer": organizer,
            "attendees": attendees,
            "location": str(loc.get("displayName") or "") if isinstance(loc, dict) else "",
            "series_id": str(ev.get("seriesMasterId") or "") if recurring else "",
            "source_id": str(ev.get("iCalUId") or ev.get("id") or ""),
            "n_attendees": max(1, len(people)),
            "all_day": all_day,
            "recurring": recurring,
            "online": online,
            "show_as": SHOW_AS.get(ev.get("showAs", "busy"), "busy"),
            "status": "confirmed",
            "response": resp,
            "provider": provider,
            "sensitivity": SENSITIVITY.get(ev.get("sensitivity", "normal"), "normal"),
        }
        return RawItem("calendar_event", t0, t1, fields)

    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        s, u = window(since, until)
        out: list[RawItem] = []
        for page in self._client.pages(self.url(s, u)):
            self._note("pages")
            for ev in page:
                if not isinstance(ev, dict):
                    continue
                item = self._item(ev)
                if item is not None and overlaps(item.t0, item.t1, s, u):
                    out.append(item)
        out.sort(key=lambda r: (r.t0, r.t1))
        self._note("events_read", len(out))
        yield from out
