"""Working-hours and quiet-hours helpers shared by onboarding, presence and the routes."""
from __future__ import annotations

import re
from typing import Any

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_QUIET = re.compile(r"^Quiet hours:\s*(?P<s>\d{2}:\d{2})\s+to\s+(?P<e>\d{2}:\d{2}),\s*(?P<d>.+?)\.?\s*$", re.I)
DEFAULT_QUIET = {"start": "22:00", "end": "06:00", "days": list(DAYS)}


def fmt_days(days: list[str]) -> str:
    idx = sorted({DAYS.index(d) for d in days})
    if len(idx) == 7:
        return "mon to sun"
    if len(idx) > 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f"{DAYS[idx[0]]} to {DAYS[idx[-1]]}"
    return ", ".join(DAYS[i] for i in idx)


def parse_days(text: str) -> list[str]:
    t = text.strip().lower()
    m = re.fullmatch(r"([a-z]{3})\s+to\s+([a-z]{3})", t)
    if m and m.group(1) in DAYS and m.group(2) in DAYS:
        a, b = DAYS.index(m.group(1)), DAYS.index(m.group(2))
        rng = range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        return [DAYS[i] for i in rng]
    out = [p.strip()[:3] for p in re.split(r"[,\s]+", t) if p.strip()]
    return [d for d in DAYS if d in out]


def check_hhmm(t: str) -> str:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(t).strip())
    if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
        raise ValueError(f"bad time {t!r}, expected HH:MM")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def normalise_window(w: dict[str, Any]) -> dict[str, Any]:
    try:
        start, end = check_hhmm(w["start"]), check_hhmm(w["end"])
        days = [str(d).lower()[:3] for d in (w.get("days") or DAYS)]
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError("expected {start, end, days}") from e
    bad = [d for d in days if d not in DAYS]
    if bad or not days:
        raise ValueError(f"bad days {bad or days!r}")
    return {"start": start, "end": end, "days": [d for d in DAYS if d in days]}


def quiet_line(w: dict[str, Any]) -> str:
    return f"Quiet hours: {w['start']} to {w['end']}, {fmt_days(w['days'])}."


def parse_quiet_line(text: str) -> dict[str, Any] | None:
    m = _QUIET.match(text.strip())
    if not m:
        return None
    days = parse_days(m.group("d"))
    return {"start": m.group("s"), "end": m.group("e"), "days": days or list(DAYS)}


def minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)
