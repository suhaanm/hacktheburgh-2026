"""Helpers over assist-ledger-shaped rows (REQ-9). Pure functions, no I/O.

Every independence-based insight reads rows through ``assist_only``: delegated and automation rows are offloaded work and never enter an
independence number (the same rule as ``cue.score.assist_only``; a test keeps the two in step).
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from .params import DAY, DEFAULT, Params
from .types import PersonRecord


@lru_cache(maxsize=1 << 17)
def _hour_epoch(h: str) -> float:
    y, mo, d, hh = int(h[0:4]), int(h[5:7]), int(h[8:10]), int(h[11:13])
    return float(calendar.timegm((y, mo, d, hh, 0, 0)))


def row_t(r: dict[str, Any]) -> float:
    """The middle of the row's UTC hour bucket (the ledger holds nothing finer)."""
    return _hour_epoch(r["t_hour"]) + 1800.0


def assist_only(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The assist stream only, oldest first. Within one hour bucket (the finest the ledger holds) rows are ordered by id, so the order never depends on how
    the rows were handed in."""
    rs = [r for r in rows if r.get("stream") == "assist"]
    return sorted(rs, key=lambda r: (r["t_hour"], r.get("id", "")))


def is_independent(r: dict[str, Any]) -> bool:
    return r["outcome"] == "clean" and not r.get("accepted")


def is_assisted(r: dict[str, Any]) -> bool:
    return r["outcome"] == "assisted"


def current_role_rows(p: PersonRecord) -> list[dict[str, Any]]:
    """Assist rows of the person's current role at or after the role change (baselines reset on a role or pack change)."""
    since = p.role_since_t
    out = [r for r in assist_only(p.rows) if r.get("role") == p.role and (since is None or row_t(r) >= since - 1800.0)]
    return out


def clip(x: float, bounds: tuple[float, float]) -> float:
    return min(bounds[1], max(bounds[0], float(x)))


def lost_values(rows: Sequence[dict[str, Any]], bounds: tuple[float, float]) -> list[float]:
    return [clip(r["lost_s"], bounds) for r in rows if r.get("lost_s") is not None]


def in_window(rows: Sequence[dict[str, Any]], t0: float, t1: float) -> list[dict[str, Any]]:
    """Rows with ``t0 < t <= t1``."""
    return [r for r in rows if t0 < row_t(r) <= t1]


def grace_flags(rows: Sequence[dict[str, Any]], p: Params = DEFAULT) -> list[bool]:
    """Parallel to ``rows`` (assist rows, oldest first): True for the first ``absence_grace_n`` occurrences of each skill after an absence,
    where an absence is a gap of ``absence_days`` or more between two consecutive occurrences of anything. Settling back in is not a habit."""
    flags = [False] * len(rows)
    left: dict[str, int] = defaultdict(int)
    prev_t: float | None = None
    skills = {r.get("skill") for r in rows}
    for i, r in enumerate(rows):
        t = row_t(r)
        if prev_t is not None and t - prev_t >= p.absence_days * DAY:
            for s in skills:
                left[s] = p.absence_grace_n
        s = r.get("skill")
        if left[s] > 0:
            flags[i] = True
            left[s] -= 1
        prev_t = t
    return flags


def weekly_buckets(now: float, weeks: int = 3) -> list[tuple[float, float]]:
    """``(start, end]`` pairs of the last ``weeks`` 7-day buckets, newest first."""
    return [(now - (i + 1) * 7 * DAY, now - i * 7 * DAY) for i in range(weeks)]


def origin_of(rows: Sequence[dict[str, Any]]) -> str:
    o = {r.get("origin") for r in rows}
    if not o:
        return "synthetic"
    return "mixed" if len(o) > 1 else ("real" if "real" in o else "synthetic")


def first_last(rows: Sequence[dict[str, Any]]) -> tuple[float | None, float | None]:
    if not rows:
        return None, None
    ts = [row_t(r) for r in rows]
    return min(ts), max(ts)


def week_bounds(now: float, tz_name: str) -> tuple[str, float, float]:
    """``(iso_week_key, start, end)`` of the worker's calendar week (Monday 00:00 to the next Monday 00:00) in their own zone. An unknown zone is UTC."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = datetime.fromtimestamp(now, tz)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=tz)
    nxt = monday + timedelta(days=7)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=tz)
    iso = local.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}", start.timestamp(), end.timestamp()


def iso_date(t: float) -> str:
    return datetime.fromtimestamp(t, ZoneInfo("UTC")).strftime("%Y-%m-%d")


def finite(x: float | None) -> bool:
    return x is not None and math.isfinite(float(x))
