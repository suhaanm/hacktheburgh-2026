"""RFC 5545 ``RRULE`` expansion for the common cases, written from the RFC (no third-party recurrence library).

Supported: ``FREQ`` DAILY, WEEKLY, MONTHLY, YEARLY; ``INTERVAL``; ``COUNT``; ``UNTIL`` (date, local or UTC);
``BYDAY`` (plain weekdays, and ordinals such as ``1MO`` or ``-1FR`` for MONTHLY and YEARLY); ``BYMONTHDAY`` (negative
values count from month end); ``BYMONTH``; ``BYSETPOS``; ``WKST``. Not supported (counted by the caller, the series is
treated as a single event): ``BYHOUR``, ``BYMINUTE``, ``BYSECOND``, ``BYYEARDAY``, ``BYWEEKNO``, ``SECONDLY`` and finer.

Expansion happens in the wall-clock time of ``DTSTART``'s zone, so a 09:00 meeting stays at 09:00 across a clock change;
the caller converts each local occurrence to UTC.
"""
from __future__ import annotations

import calendar as _cal   # stdlib (this package is understudy_engine.plugins; absolute import is the standard library)
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Callable, Iterator

DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
SUPPORTED_FREQ = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
UNSUPPORTED_PARTS = ("BYHOUR", "BYMINUTE", "BYSECOND", "BYYEARDAY", "BYWEEKNO")
MAX_OCCURRENCES = 20000


class RRuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int = 1
    count: int | None = None
    until: datetime | None = None            # aware UTC (a date-only UNTIL is end of that local day, resolved by the caller)
    until_date: date | None = None           # set when UNTIL was a bare date
    byday: tuple[tuple[int, int], ...] = ()  # (ordinal or 0, weekday 0=Monday)
    bymonthday: tuple[int, ...] = ()
    bymonth: tuple[int, ...] = ()
    bysetpos: tuple[int, ...] = ()
    wkst: int = 0


def _ints(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(",") if x.strip())


def parse_rrule(text: str, parse_until: Callable[[str], tuple[datetime | None, date | None]]) -> Rule:
    """Parse the value of an ``RRULE`` property. ``parse_until`` turns the UNTIL text into (utc instant, bare date)."""
    parts: dict[str, str] = {}
    for chunk in text.strip().split(";"):
        if not chunk:
            continue
        if "=" not in chunk:
            raise RRuleError("malformed RRULE part")
        k, v = chunk.split("=", 1)
        parts[k.strip().upper()] = v.strip()
    freq = parts.get("FREQ", "").upper()
    if freq not in SUPPORTED_FREQ:
        raise RRuleError("unsupported FREQ")
    for bad in UNSUPPORTED_PARTS:
        if bad in parts:
            raise RRuleError(f"unsupported {bad}")
    interval = int(parts.get("INTERVAL", "1"))
    if interval < 1:
        raise RRuleError("bad INTERVAL")
    count = int(parts["COUNT"]) if "COUNT" in parts else None
    until = until_date = None
    if "UNTIL" in parts:
        until, until_date = parse_until(parts["UNTIL"])
    byday: list[tuple[int, int]] = []
    for tok in parts.get("BYDAY", "").split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        wd = DAYS.get(tok[-2:])
        if wd is None:
            raise RRuleError("bad BYDAY")
        ordv = tok[:-2]
        byday.append((int(ordv) if ordv not in ("", "+", "-") else 0, wd))
    return Rule(freq=freq, interval=interval, count=count, until=until, until_date=until_date, byday=tuple(byday),
                bymonthday=_ints(parts.get("BYMONTHDAY", "")), bymonth=_ints(parts.get("BYMONTH", "")),
                bysetpos=_ints(parts.get("BYSETPOS", "")), wkst=DAYS.get(parts.get("WKST", "MO").upper(), 0))


def _month_days(year: int, month: int) -> int:
    return _cal.monthrange(year, month)[1]


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date | None:
    last = _month_days(year, month)
    days = [d for d in range(1, last + 1) if date(year, month, d).weekday() == weekday]
    try:
        return date(year, month, days[n - 1] if n > 0 else days[n])
    except IndexError:
        return None


def _month_candidates(rule: Rule, year: int, month: int, start: date) -> list[date]:
    last = _month_days(year, month)
    out: set[date] = set()
    if rule.byday:
        for ordv, wd in rule.byday:
            if ordv:
                d = _nth_weekday(year, month, wd, ordv)
                if d:
                    out.add(d)
            else:
                out.update(date(year, month, d) for d in range(1, last + 1) if date(year, month, d).weekday() == wd)
        if rule.bymonthday:
            allowed = {d if d > 0 else last + d + 1 for d in rule.bymonthday}
            out = {d for d in out if d.day in allowed}
    elif rule.bymonthday:
        for d in rule.bymonthday:
            day = d if d > 0 else last + d + 1
            if 1 <= day <= last:
                out.add(date(year, month, day))
    else:
        if start.day <= last:
            out.add(date(year, month, start.day))
    days = sorted(out)
    if rule.bysetpos:
        picked = []
        for p in rule.bysetpos:
            try:
                picked.append(days[p - 1] if p > 0 else days[p])
            except IndexError:
                pass
        days = sorted(set(picked))
    return days


def _week_start(d: date, wkst: int) -> date:
    return d - timedelta(days=(d.weekday() - wkst) % 7)


def _periods(rule: Rule, start: date) -> Iterator[tuple[date, list[date]]]:
    """(period anchor date, candidate dates) per recurrence period, in order, before the COUNT/UNTIL/horizon cut."""
    k = 0
    while True:
        if rule.freq == "DAILY":
            d = start + timedelta(days=k * rule.interval)
            ok = (not rule.byday or any(d.weekday() == wd for _, wd in rule.byday)) \
                and (not rule.bymonth or d.month in rule.bymonth) \
                and (not rule.bymonthday or d.day in {x if x > 0 else _month_days(d.year, d.month) + x + 1 for x in rule.bymonthday})
            yield d, ([d] if ok else [])
        elif rule.freq == "WEEKLY":
            ws = _week_start(start, rule.wkst) + timedelta(weeks=k * rule.interval)
            wds = sorted({wd for _, wd in rule.byday}) if rule.byday else [start.weekday()]
            days = sorted(ws + timedelta(days=(wd - rule.wkst) % 7) for wd in wds)
            if rule.bymonth:
                days = [d for d in days if d.month in rule.bymonth]
            yield ws, days
        elif rule.freq == "MONTHLY":
            total = start.year * 12 + (start.month - 1) + k * rule.interval
            year, month = divmod(total, 12)
            month += 1
            if rule.bymonth and month not in rule.bymonth:
                yield date(year, month, 1), []
            else:
                yield date(year, month, 1), _month_candidates(rule, year, month, start)
        else:  # YEARLY
            year = start.year + k * rule.interval
            months = rule.bymonth or (start.month,)
            days: list[date] = []
            for m in sorted(months):
                if rule.byday or rule.bymonthday:
                    days.extend(_month_candidates(rule, year, m, start))
                elif start.day <= _month_days(year, m):
                    days.append(date(year, m, start.day))
            yield date(year, 1, 1), sorted(days)
        k += 1


def expand(rule: Rule, start_local: datetime, tz: tzinfo, horizon_utc: datetime, *, limit: int = MAX_OCCURRENCES) -> Iterator[datetime]:
    """Yield naive local occurrence start times (``start_local`` first when it matches), up to ``horizon_utc``, COUNT and UNTIL.

    ``start_local`` is DTSTART's wall-clock time (naive) in ``tz``. The caller converts each to UTC."""
    tod: time = start_local.time()
    start = start_local.date()
    emitted = 0
    horizon_date = (horizon_utc.astimezone(tz) + timedelta(days=1)).date()
    until_utc = rule.until
    for anchor, days in _periods(rule, start):
        if anchor > horizon_date:
            return
        for d in days:
            if d < start:
                continue
            if d > horizon_date:
                return
            if rule.until_date is not None and d > rule.until_date:
                return
            occ = datetime.combine(d, tod)
            if until_utc is not None and occ.replace(tzinfo=tz).astimezone(timezone.utc) > until_utc:
                return
            emitted += 1
            yield occ
            if (rule.count is not None and emitted >= rule.count) or emitted >= limit:
                return
