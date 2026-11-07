"""Time-zone resolution for calendar sources: IANA names, Windows names (Microsoft Graph), and odd ICS ``TZID`` forms.

Never raises on an unknown name: returns ``None`` and the caller falls back to a default zone and counts the miss.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc

# Windows time-zone names as Microsoft Graph returns them -> IANA. Covers the common ones; unknown names fall back.
WINDOWS_TO_IANA = {
    "UTC": "UTC", "Coordinated Universal Time": "UTC", "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik", "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest", "Central European Standard Time": "Europe/Warsaw",
    "Romance Standard Time": "Europe/Paris", "E. Europe Standard Time": "Europe/Chisinau",
    "GTB Standard Time": "Europe/Bucharest", "FLE Standard Time": "Europe/Kiev", "Russian Standard Time": "Europe/Moscow",
    "Eastern Standard Time": "America/New_York", "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver", "Pacific Standard Time": "America/Los_Angeles",
    "US Mountain Standard Time": "America/Phoenix", "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu", "Atlantic Standard Time": "America/Halifax",
    "Canada Central Standard Time": "America/Regina", "Mexico Standard Time": "America/Mexico_City",
    "SA Pacific Standard Time": "America/Bogota", "E. South America Standard Time": "America/Sao_Paulo",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires", "India Standard Time": "Asia/Kolkata",
    "China Standard Time": "Asia/Shanghai", "Tokyo Standard Time": "Asia/Tokyo", "Korea Standard Time": "Asia/Seoul",
    "Singapore Standard Time": "Asia/Singapore", "Arabian Standard Time": "Asia/Dubai", "Israel Standard Time": "Asia/Jerusalem",
    "Turkey Standard Time": "Europe/Istanbul", "South Africa Standard Time": "Africa/Johannesburg",
    "Egypt Standard Time": "Africa/Cairo", "W. Central Africa Standard Time": "Africa/Lagos",
    "AUS Eastern Standard Time": "Australia/Sydney", "E. Australia Standard Time": "Australia/Brisbane",
    "Cen. Australia Standard Time": "Australia/Adelaide", "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland", "Pakistan Standard Time": "Asia/Karachi",
    "Bangladesh Standard Time": "Asia/Dhaka", "SE Asia Standard Time": "Asia/Bangkok",
}

_TAIL = re.compile(r"([A-Za-z_]+/[A-Za-z_+\-0-9]+(?:/[A-Za-z_+\-0-9]+)?)$")


@lru_cache(maxsize=256)
def _zone(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def resolve_tz(name: str | None) -> tzinfo | None:
    """IANA or Windows name (quotes and ``/mozilla.org/...`` prefixes tolerated) to a tzinfo, or None if unknown."""
    if not name:
        return None
    n = name.strip().strip('"').strip()
    if n in ("Z", "z", "UTC", "utc", "GMT", "Etc/UTC", "Coordinated Universal Time"):
        return UTC
    if n in WINDOWS_TO_IANA:
        return _zone(WINDOWS_TO_IANA[n]) if WINDOWS_TO_IANA[n] != "UTC" else UTC
    z = _zone(n)
    if z is not None:
        return z
    m = _TAIL.search(n)                         # e.g. "/mozilla.org/20050126_1/Europe/London"
    if m:
        z = _zone(m.group(1))
        if z is not None:
            return z
    m = re.fullmatch(r"(?:UTC|GMT)([+-])(\d{1,2})(?::?(\d{2}))?", n)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0)))
    return None


def local_to_utc(naive: datetime, tz: tzinfo) -> datetime:
    """Wall-clock time in ``tz`` to UTC. A time in a spring-forward gap lands on the shifted instant; an ambiguous time
    (autumn repeat) takes the first occurrence."""
    aware = naive.replace(tzinfo=tz, fold=0)
    return aware.astimezone(UTC)


def utc_to_local(dt: datetime, tz: tzinfo) -> datetime:
    return dt.astimezone(tz)


# ---------------------------------------------------------------------------------------------------- VTIMEZONE fallback
@dataclass
class Observance:
    """One STANDARD or DAYLIGHT block of an ICS VTIMEZONE: from ``dtstart`` (wall time before the change, in ``off_from``) the zone is ``off_to``."""

    dtstart: datetime                       # naive wall-clock time of the first transition
    off_from: timedelta
    off_to: timedelta
    rrule: str | None = None
    rdates: list[datetime] = field(default_factory=list)


def parse_offset(text: str) -> timedelta | None:
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})(\d{2})?", text.strip())
    if not m:
        return None
    off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)), seconds=int(m.group(4) or 0))
    return off if m.group(1) == "+" else -off


class VTimezone(tzinfo):
    """A zone built from an ICS ``VTIMEZONE`` (used when a TZID is not an IANA or Windows name, as in Outlook's display-name zones such as
    "(UTC+00:00) Dublin, Edinburgh, Lisbon, London"). It follows the yearly STANDARD and DAYLIGHT rules, so a 09:00 meeting stays at 09:00 across
    a clock change. Wall times in the repeated or skipped hour take the earlier transition's offset."""

    def __init__(self, observances: list[Observance]):
        if not observances:
            raise ValueError("a VTIMEZONE needs at least one observance")
        self._obs = observances
        self._trans: list[tuple[datetime, timedelta]] | None = None

    def _transitions(self) -> list[tuple[datetime, timedelta]]:
        if self._trans is None:
            from .rrule import RRuleError, expand, parse_rrule
            out: list[tuple[datetime, timedelta]] = []
            far = datetime(2100, 1, 1, tzinfo=UTC)
            for ob in self._obs:
                out.append((ob.dtstart, ob.off_to))
                out.extend((d, ob.off_to) for d in ob.rdates)
                if ob.rrule:
                    try:
                        rule = parse_rrule(ob.rrule, lambda t: (None, None))
                        for occ in expand(rule, ob.dtstart, timezone(ob.off_from), far, limit=800):
                            out.append((occ, ob.off_to))
                    except (RRuleError, ValueError):
                        pass
            self._trans = sorted(set(out), key=lambda x: x[0])
        return self._trans

    def utcoffset(self, dt: datetime | None) -> timedelta:
        wall = (dt.replace(tzinfo=None) if dt is not None else datetime(2000, 1, 1))
        best: timedelta | None = None
        for t, off in self._transitions():
            if t <= wall:
                best = off
            else:
                break
        return best if best is not None else self._obs[0].off_from

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str | None:
        return None
