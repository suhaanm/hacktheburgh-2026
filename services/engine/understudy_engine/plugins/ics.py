"""ICS (RFC 5545) calendar source: a local ``.ics`` export or text, with recurrence expansion. Read-only, no network.

Handles line unfolding, property parameters (quoted values), text escapes, ``DTSTART``/``DTEND``/``DURATION`` in UTC,
floating, ``TZID`` (IANA, Windows and Mozilla-style names, with a ``VTIMEZONE`` standard-offset fallback) and all-day
dates, ``RRULE`` (see ``rrule.py``) with ``EXDATE``, ``RDATE`` and ``RECURRENCE-ID`` overrides, ``STATUS:CANCELLED``,
``TRANSP``, Microsoft busy-status and conference hints. Nested ``VALARM`` blocks are skipped.

Raw text (titles, addresses, descriptions) lives only in the ``RawItem`` it builds. Parse problems are counted by code
in ``self.stats`` and never carry content. The description is scanned for a join link to set ``online`` and ``provider``
and is then dropped; it never reaches an item.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Iterator

from .base import RawItem, Source, SourceError, overlaps
from .rrule import RRuleError, expand, parse_rrule
from .tz import local_to_utc, resolve_tz

UTC = timezone.utc
MAX_BYTES = 64 * 1024 * 1024


@dataclass
class _Prop:
    name: str
    params: dict[str, str]
    value: str


@dataclass
class _Ev:
    uid: str
    props: list[_Prop] = field(default_factory=list)

    def get(self, name: str) -> _Prop | None:
        for p in self.props:
            if p.name == name:
                return p
        return None

    def all(self, name: str) -> list[_Prop]:
        return [p for p in self.props if p.name == name]


def unfold(text: str) -> list[str]:
    """RFC 5545 line unfolding: a line starting with space or tab continues the previous one."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _split_unquoted(s: str, sep: str) -> list[str]:
    out, cur, quoted = [], [], False
    for ch in s:
        if ch == '"':
            quoted = not quoted
            cur.append(ch)
        elif ch == sep and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def parse_line(line: str) -> _Prop | None:
    """``NAME;P=V;P2="a:b":value`` -> property. None for a line that is not a property."""
    if not line or ":" not in line:
        return None
    # the value starts at the first colon outside quotes
    quoted, idx = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            idx = i
            break
    if idx < 0:
        return None
    head, value = line[:idx], line[idx + 1:]
    parts = _split_unquoted(head, ";")
    name = parts[0].strip().upper()
    if not name:
        return None
    params: dict[str, str] = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return _Prop(name, params, value)


def unescape(v: str) -> str:
    out, i = [], 0
    while i < len(v):
        c = v[i]
        if c == "\\" and i + 1 < len(v):
            n = v[i + 1]
            out.append("\n" if n in "nN" else n)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


_DUR = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(v: str) -> timedelta | None:
    m = _DUR.match(v.strip().upper())
    if not m or not any(m.groups()[1:]):
        return None
    sign = -1 if m.group(1) == "-" else 1
    w, d, h, mi, s = (int(x) if x else 0 for x in m.groups()[1:])
    return sign * timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


_MAIL = re.compile(r"^mailto:", re.I)
_JOIN = (("teams.microsoft.com", "teams"), ("teams.live.com", "teams"), ("zoom.us", "zoom"), ("zoom.com", "zoom"),
         ("meet.google.com", "meet"), ("webex.com", "other"), ("gotomeeting.com", "other"), ("whereby.com", "other"))
_COMPACT_DT = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?)?(Z)?$", re.I)


def _addr(p: _Prop) -> str:
    return _MAIL.sub("", p.value.strip()).lower()


class _Cal:
    """Parsed calendar: events (with zone data resolved lazily)."""

    def __init__(self) -> None:
        self.events: list[_Ev] = []
        self.vtz_offsets: dict[str, timedelta] = {}


def parse_calendar(text: str) -> _Cal:
    cal = _Cal()
    stack: list[str] = []
    cur: _Ev | None = None
    vtz_id: str | None = None
    vtz_kind: str | None = None
    for line in unfold(text):
        u = line.strip().upper()
        if u.startswith("BEGIN:"):
            comp = u[6:]
            stack.append(comp)
            if comp == "VEVENT":
                cur = _Ev(uid="")
            elif comp == "VTIMEZONE":
                vtz_id = None
            elif comp in ("STANDARD", "DAYLIGHT"):
                vtz_kind = comp
            continue
        if u.startswith("END:"):
            comp = u[4:]
            if stack and stack[-1] == comp:
                stack.pop()
            if comp == "VEVENT" and cur is not None:
                uid = cur.get("UID")
                cur.uid = uid.value.strip() if uid else ""
                cal.events.append(cur)
                cur = None
            elif comp in ("STANDARD", "DAYLIGHT"):
                vtz_kind = None
            elif comp == "VTIMEZONE":
                vtz_id = None
            continue
        if not stack:
            continue
        top = stack[-1]
        prop = parse_line(line)
        if prop is None:
            continue
        if top == "VEVENT" and cur is not None:
            cur.props.append(prop)
        elif top == "VTIMEZONE" and prop.name == "TZID":
            vtz_id = prop.value.strip()
        elif top == "STANDARD" and prop.name == "TZOFFSETTO" and vtz_id:
            m = re.fullmatch(r"([+-])(\d{2})(\d{2})(\d{2})?", prop.value.strip())
            if m:
                off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
                cal.vtz_offsets[vtz_id] = off if m.group(1) == "+" else -off
    return cal


class ICSSource(Source):
    """Read events from ICS text or a file. ``default_tz`` applies to floating times; ``self_email`` (optional) lets the
    source report the owner's own response and skip events they declined."""

    plugin_id = "ics"
    schema_id = "calendar_event.v1"

    def __init__(self, text: str | None = None, *, path: str | Path | None = None, default_tz: str = "UTC",
                 self_email: str | None = None, horizon_days: int = 120):
        super().__init__()
        if (text is None) == (path is None):
            raise ValueError("give exactly one of text or path")
        if path is not None:
            p = Path(path)
            if p.stat().st_size > MAX_BYTES:
                raise SourceError("file_too_large")
            text = p.read_text(encoding="utf-8", errors="replace")
        self._text = text or ""
        self._default_tz: tzinfo = resolve_tz(default_tz) or UTC
        self._self = (self_email or "").lower() or None
        self._horizon_days = horizon_days

    # ------------------------------------------------------------------ time parsing
    def _zone(self, tzid: str | None, cal: _Cal) -> tzinfo:
        if not tzid:
            return self._default_tz
        z = resolve_tz(tzid)
        if z is not None:
            return z
        off = cal.vtz_offsets.get(tzid)
        if off is not None:
            self._note("tz_fixed_offset_fallback")
            return timezone(off)
        self._note("tz_unknown_default_used")
        return self._default_tz

    def _parse_dt(self, prop: _Prop, cal: _Cal) -> tuple[datetime, datetime, bool, tzinfo] | None:
        """-> (utc instant, naive local wall time, all_day, zone)."""
        v = prop.value.strip()
        m = _COMPACT_DT.match(v)
        if not m:
            m2 = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?(Z)?", v)   # tolerate ISO text
            if not m2:
                self._note("bad_datetime")
                return None
            m = m2
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mi, ss = (int(m.group(i) or 0) for i in (4, 5, 6))
        all_day = prop.params.get("VALUE", "").upper() == "DATE" or m.group(4) is None
        try:
            naive = datetime(y, mo, d, hh, mi, ss)
        except ValueError:
            self._note("bad_datetime")
            return None
        if m.group(7):
            return naive.replace(tzinfo=UTC), naive, all_day, UTC
        tz = self._zone(prop.params.get("TZID"), cal)
        return local_to_utc(naive, tz), naive, all_day, tz

    def _parse_until(self, text: str, tz: tzinfo):
        t = text.strip()
        m = _COMPACT_DT.match(t)
        if not m:
            raise RRuleError("bad UNTIL")
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4) is None:
            return None, date(y, mo, d)
        naive = datetime(y, mo, d, int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
        if m.group(7):
            return naive.replace(tzinfo=UTC), None
        return local_to_utc(naive, tz), None

    # ------------------------------------------------------------------ event building
    def _fields(self, ev: _Ev, *, all_day: bool, recurring: bool) -> dict | None:
        status_p = ev.get("STATUS")
        status = (status_p.value.strip().lower() if status_p else "confirmed")
        status = {"confirmed": "confirmed", "tentative": "tentative", "cancelled": "cancelled", "canceled": "cancelled"}.get(status, "confirmed")
        busy = ev.get("X-MICROSOFT-CDO-BUSYSTATUS")
        transp = ev.get("TRANSP")
        if busy:
            show_as = {"FREE": "free", "TENTATIVE": "tentative", "BUSY": "busy", "OOF": "oof", "WORKINGELSEWHERE": "working_elsewhere"}.get(busy.value.strip().upper(), "busy")
        elif transp and transp.value.strip().upper() == "TRANSPARENT":
            show_as = "free"
        elif status == "tentative":
            show_as = "tentative"
        else:
            show_as = "busy"
        org_p = ev.get("ORGANIZER")
        organizer = _addr(org_p) if org_p else ""
        attendees = []
        response = "organizer" if (org_p and self._self and _addr(org_p) == self._self) else "none"
        for a in ev.all("ATTENDEE"):
            addr = _addr(a)
            attendees.append(addr)
            if self._self and addr == self._self:
                response = {"ACCEPTED": "accepted", "TENTATIVE": "tentative", "DECLINED": "declined"}.get(a.params.get("PARTSTAT", "").upper(), "none")
        people = {x for x in attendees if x} | ({organizer} if organizer else set())
        # conference hints: scan description, location, url, conference once, keep only the provider enum
        hay = " ".join(p.value for p in ev.props if p.name in ("DESCRIPTION", "LOCATION", "URL", "CONFERENCE", "X-ALT-DESC",
                                                               "X-GOOGLE-CONFERENCE", "X-MICROSOFT-ONLINEMEETINGEXTERNALLINK")).lower()
        provider = "none"
        if ev.get("X-MICROSOFT-SKYPETEAMSMEETINGURL") or ev.get("X-MICROSOFT-ONLINEMEETINGCONFLINK"):
            provider = "teams"
        for host, prov in _JOIN:
            if provider == "none" and host in hay:
                provider = prov
        cls = ev.get("CLASS")
        sensitivity = {"PUBLIC": "normal", "PRIVATE": "private", "CONFIDENTIAL": "confidential"}.get(cls.value.strip().upper(), "normal") if cls else "normal"
        sens_p = ev.get("X-MICROSOFT-CDO-SENSITIVITY")
        if sens_p and sens_p.value.strip() == "1":
            sensitivity = "personal"
        title = ev.get("SUMMARY")
        loc = ev.get("LOCATION")
        return {
            "title": unescape(title.value) if title else "",
            "organizer": organizer,
            "attendees": sorted(x for x in attendees if x),
            "location": unescape(loc.value) if loc else "",
            "series_id": ev.uid if recurring else "",
            "source_id": ev.uid,
            "n_attendees": max(1, len(people)),
            "all_day": all_day,
            "recurring": recurring,
            "online": provider != "none",
            "show_as": show_as,
            "status": status,
            "response": response,
            "provider": provider,
            "sensitivity": sensitivity,
        }

    def _times(self, ev: _Ev, cal: _Cal):
        ds = ev.get("DTSTART")
        if ds is None:
            self._note("event_without_start")
            return None
        start = self._parse_dt(ds, cal)
        if start is None:
            return None
        utc0, local0, all_day, tz = start
        de, dur = ev.get("DTEND"), ev.get("DURATION")
        if de is not None:
            end = self._parse_dt(de, cal)
            if end is None:
                return None
            utc1 = end[0]
        elif dur is not None and parse_duration(dur.value) is not None:
            utc1 = utc0 + parse_duration(dur.value)
        elif all_day:
            utc1 = local_to_utc(local0 + timedelta(days=1), tz)
        else:
            utc1 = utc0
        if utc1 < utc0:
            self._note("end_before_start")
            utc1 = utc0
        return utc0, utc1, local0, all_day, tz

    # ------------------------------------------------------------------ read
    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        cal = parse_calendar(self._text)
        masters: dict[str, _Ev] = {}
        overrides: dict[str, dict[datetime, _Ev]] = {}
        singles: list[_Ev] = []
        for ev in cal.events:
            if ev.get("RECURRENCE-ID") is not None and ev.uid:
                rid = self._parse_dt(ev.get("RECURRENCE-ID"), cal)
                if rid is not None:
                    overrides.setdefault(ev.uid, {})[rid[0]] = ev
                continue
            if ev.get("RRULE") is not None or ev.get("RDATE") is not None:
                masters[ev.uid or f"_anon{len(masters)}"] = ev
            else:
                singles.append(ev)

        # horizon for open-ended rules: the latest end among bounded events, else the earliest start + horizon_days
        starts, ends = [], []
        for ev in cal.events:
            t = self._times(ev, cal)
            if t:
                starts.append(t[0])
                ends.append(t[1])
        if not starts:
            return
        horizon = max(max(ends), min(starts) + timedelta(days=self._horizon_days))
        if until is not None:
            horizon = min(horizon, until.astimezone(UTC) + timedelta(days=1))

        far = datetime(2100, 1, 1, tzinfo=UTC)
        out: list[RawItem] = []

        def emit(t0: datetime, t1: datetime, ev: _Ev, all_day: bool, recurring: bool) -> None:
            f = self._fields(ev, all_day=all_day, recurring=recurring)
            if f is None:
                return
            if overlaps(t0, t1, since, until):
                out.append(RawItem("calendar_event", t0, t1, f))

        for ev in singles:
            t = self._times(ev, cal)
            if t:
                emit(t[0], t[1], ev, t[3], False)

        for uid, ev in masters.items():
            t = self._times(ev, cal)
            if not t:
                continue
            utc0, utc1, local0, all_day, tz = t
            dur = utc1 - utc0
            occ_starts: list[datetime] = []
            rr = ev.get("RRULE")
            if rr is not None:
                try:
                    rule = parse_rrule(rr.value, lambda s: self._parse_until(s, tz))
                    # a rule with COUNT or UNTIL ends by itself; only an open-ended rule needs the horizon
                    bounded = rule.count is not None or rule.until is not None or rule.until_date is not None
                    hz = (min(far, until.astimezone(UTC) + timedelta(days=1)) if until is not None else far) if bounded else horizon
                    for loc in expand(rule, local0, tz, hz):
                        occ_starts.append(local_to_utc(loc, tz) if not all_day else local_to_utc(loc, tz))
                except (RRuleError, ValueError):
                    self._note("rrule_unsupported_single_event")
                    occ_starts = [utc0]
            else:
                occ_starts = [utc0]
            for rd in ev.all("RDATE"):
                for piece in rd.value.split(","):
                    parsed = self._parse_dt(_Prop("RDATE", rd.params, piece), cal)
                    if parsed:
                        occ_starts.append(parsed[0])
            ex: set[datetime] = set()
            for exd in ev.all("EXDATE"):
                for piece in exd.value.split(","):
                    parsed = self._parse_dt(_Prop("EXDATE", exd.params, piece), cal)
                    if parsed:
                        ex.add(parsed[0])
                        if parsed[2]:      # a bare date excludes every occurrence on that local day
                            for s in occ_starts:
                                if s.astimezone(tz).date() == parsed[1].date():
                                    ex.add(s)
            seen: set[datetime] = set()
            for s in occ_starts:
                if s in ex or s in seen:
                    continue
                seen.add(s)
                ov = overrides.get(uid, {}).get(s)
                if ov is not None:
                    ot = self._times(ov, cal)
                    if ot is None:
                        continue
                    f = self._fields(ov, all_day=ot[3], recurring=True)
                    if f and f["status"] != "cancelled" and overlaps(ot[0], ot[1], since, until):
                        out.append(RawItem("calendar_event", ot[0], ot[1], f))
                    continue
                emit(s, s + dur, ev, all_day, True)

        # overrides whose master we never saw (an export containing only an exception)
        for uid, per in overrides.items():
            if uid in masters:
                continue
            for ov in per.values():
                ot = self._times(ov, cal)
                if ot:
                    emit(ot[0], ot[1], ov, ot[3], True)

        self._note("events_read", len(out))
        out.sort(key=lambda r: (r.t0, r.t1))
        yield from out
