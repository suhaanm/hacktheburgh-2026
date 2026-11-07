"""Time-zone resolution for calendar sources: IANA names, Windows names (Microsoft Graph), and odd ICS ``TZID`` forms.

Never raises on an unknown name: returns ``None`` and the caller falls back to a default zone and counts the miss.
"""
from __future__ import annotations

import re
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
