"""One read-only, aggregate-only check of a calendar source (owner decision D26, 7 Nov 2026).

``run(source)`` reads a ``Source`` once and returns **only counts, durations and enums**: no titles, no attendees, no bodies, no
names, no ids, no addresses and no calendar dates (weeks are numbered 0, 1, 2 from the first week with events; the span is a
number of days). It writes nothing to disk, logs nothing and keeps nothing: the raw items are consumed by ``normalize.to_blocks``,
which drops every text field, and only the text-free blocks are analysed.

It is meant to be run by the lead, with the owner's approval of that specific run, through a source plugin (for example the Graph
Outlook source with the worker's own sign-in, or an ICS export of their own calendar). The same function is tested on canary-seeded
fixtures to show that no planted name, address, title, location or id reaches the result.

    from understudy_engine.calendar.real_check import run
    result = run(source, tz="Europe/London")      # a dict of numbers and enums
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from ..plugins.base import Source
from .bucket import bucket_count
from .features import ALL_KEYS, CONTRACT_KEYS, analyse_week
from .model import WorkConfig
from .normalize import to_blocks

PRIVACY_NOTE = "Counts, durations and enums only. No titles, attendees, bodies, names, addresses, ids or calendar dates were kept."
DURATION_BUCKETS = (("le15", 15), ("16to30", 30), ("31to60", 60), ("61to90", 90), ("gt90", 10**9))


def _bucket_duration(minutes: float) -> str:
    for name, hi in DURATION_BUCKETS:
        if minutes <= hi:
            return name
    return "gt90"


def run(source: Source, *, tz: str = "Europe/London", work: WorkConfig | None = None, since: datetime | None = None,
        until: datetime | None = None, bucket_small: bool = False) -> dict[str, Any]:
    """Read ``source`` and return the aggregate result. ``bucket_small=True`` replaces counts under 5 with ``"lt5"`` (the payload rule)."""
    from ..plugins.tz import resolve_tz
    if work is None:
        zone = resolve_tz(tz)
        work = WorkConfig(tz=zone or resolve_tz("UTC"), tz_name=tz if zone else "UTC")
    blocks, off_dates, stats = to_blocks(source.read(since, until), work)          # raw text stops here
    c = (lambda n: bucket_count(n)) if bucket_small else (lambda n: n)
    meetings = [b for b in blocks if b.kind == "meeting"]
    dur = Counter(_bucket_duration(b.minutes) for b in meetings)
    att = Counter("lt5" if b.n_attendees < 5 else "5to9" if b.n_attendees < 10 else "10plus" for b in meetings)
    hours = [0] * 24
    wdays = [0] * 7
    for b in meetings:
        local = b.start.astimezone(work.tz)
        hours[local.hour] += 1
        wdays[local.weekday()] += 1
    from .store import week_mondays
    mondays = week_mondays(blocks, work)
    weeks = [analyse_week(blocks, work, m, off_dates).features for m in mondays]
    span_days = 0
    if blocks:
        span_days = (max(b.end for b in blocks) - min(b.start for b in blocks)).days + 1
    summary: dict[str, dict[str, float]] = {}
    for k in CONTRACT_KEYS + ("meetings_n", "fragmented_days", "recurring_in_peak_h", "external_unbuffered_n", "outside_hours_h", "meeting_share"):
        vals = [float(w[k]) for w in weeks]
        if vals:
            summary[k] = {"mean": round(sum(vals) / len(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2)}
    return {
        "kind": "calendar_aggregate_check", "schema": 1,
        "span_days": span_days, "weeks_covered": len(weeks),
        "items": {"read": c(stats.read), "used": c(stats.blocks), "cancelled": c(stats.cancelled), "declined": c(stats.declined),
                  "free_time": c(stats.free_skipped), "all_day_skipped": c(stats.all_day_skipped), "days_off": c(stats.days_off)},
        "blocks_by_kind": {k: c(v) for k, v in sorted(Counter(b.kind for b in blocks).items())},
        "meetings": {"n": c(len(meetings)), "online": c(sum(b.online for b in meetings)), "external": c(sum(b.external for b in meetings)),
                     "recurring": c(sum(b.recurring for b in meetings)), "recurring_series": c(len({b.series for b in meetings if b.series})),
                     "duration_buckets": {k: c(dur.get(k, 0)) for k, _ in DURATION_BUCKETS},
                     "attendee_buckets": {k: c(att.get(k, 0)) for k in ("lt5", "5to9", "10plus")},
                     "start_hour_histogram": [c(x) for x in hours], "weekday_histogram": [c(x) for x in wdays]},
        "weeks": [{"index": i, "features": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in w.items() if k in ALL_KEYS}} for i, w in enumerate(weeks)],
        "summary": summary,
        "privacy": PRIVACY_NOTE,
    }
