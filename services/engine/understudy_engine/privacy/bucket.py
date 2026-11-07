"""Generalisation before anything enters a payload (PRV-3).

* counts under 5 become ``"lt5"`` (including zero; larger counts are sent as they are),
* attendee counts become ``"lt5"``, ``"5to9"`` or ``"10plus"``,
* times of day round to 15 minutes (as minutes since midnight, 0 to 1440),
* durations round to 5 minutes,
* ratios round to 10% steps (a float from 0.0 to 1.0).

The pure functions are the rule; the ``Annotated`` types (``Count``, ``Attendees``, ``TimeOfDay``, ``DurationMin``,
``Hours``, ``Ratio``) apply it automatically when a ``SafePayload`` is built, and every rule is idempotent, so
``egress.send`` can re-validate a payload and get the same bytes. Rounding is half up (``x.5`` goes up), so it is stable
and monotone: a bigger input never gives a smaller output.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, time, timedelta
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator

from .payload import Bucket, Vocab, register_vocabulary

LT5 = "lt5"
COUNT_FLOOR = 5
TIME_STEP_MIN = 15
DURATION_STEP_MIN = 5
RATIO_STEPS = 10
MINUTES_PER_DAY = 1440
_EPS = 1e-9


def _real(x: Any, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{what} must be a number")
    if isinstance(x, float) and not math.isfinite(x):
        raise ValueError(f"{what} must be finite")
    return float(x)


def _half_up(x: float) -> int:
    return int(math.floor(x + 0.5 + _EPS))


# ------------------------------------------------------------------------------------------------------- pure rules
def bucket_count(n: Any) -> int | str:
    """Counts under 5 (including 0) become ``"lt5"``; 5 and more are unchanged."""
    if isinstance(n, str):
        if n == LT5:
            return n
        raise ValueError("a count must be a whole number")
    x = _real(n, "a count")
    if x < 0 or abs(x - round(x)) > _EPS:
        raise ValueError("a count must be a whole number of 0 or more")
    k = int(round(x))
    return LT5 if k < COUNT_FLOOR else k


def bucket_attendees(n: Any) -> str:
    """Attendee counts: ``lt5``, ``5to9`` or ``10plus``."""
    if isinstance(n, str):
        if n in (LT5, "5to9", "10plus"):
            return n
        raise ValueError("attendees must be a whole number")
    c = bucket_count(n)
    if c == LT5:
        return LT5
    return "5to9" if int(c) <= 9 else "10plus"


def minute_of_day(t: Any) -> float:
    """Minutes since midnight from a ``datetime``, a ``time`` or a number of minutes."""
    if isinstance(t, datetime):
        return t.hour * 60 + t.minute + t.second / 60.0
    if isinstance(t, time):
        return t.hour * 60 + t.minute + t.second / 60.0
    return _real(t, "a time of day")


def round_time_minutes(t: Any, step: int = TIME_STEP_MIN) -> int:
    """Time of day to the nearest ``step`` minutes (default 15), as minutes since midnight in 0..1440."""
    m = minute_of_day(t)
    if m < -_EPS or m > MINUTES_PER_DAY + _EPS:
        raise ValueError("a time of day must be between 0 and 1440 minutes")
    return min(MINUTES_PER_DAY, max(0, _half_up(m / step) * step))


def round_duration_minutes(minutes: Any, step: int = DURATION_STEP_MIN) -> int:
    """Duration in minutes to the nearest ``step`` (default 5)."""
    m = _real(minutes, "a duration")
    if m < 0:
        raise ValueError("a duration must not be negative")
    return _half_up(m / step) * step


def round_duration_seconds(seconds: Any, step: int = DURATION_STEP_MIN) -> int:
    """Duration given in seconds, returned as minutes rounded to ``step``."""
    return round_duration_minutes(_real(seconds, "a duration") / 60.0, step)


def bucket_hours(hours: Any) -> float:
    """Hours rounded to 5 minutes, returned in hours with two decimals (so 1h50m is 1.83)."""
    h = _real(hours, "a number of hours")
    if h < 0:
        raise ValueError("hours must not be negative")
    return round(round_duration_minutes(h * 60.0) / 60.0, 2)


def bucket_ratio(x: Any) -> float:
    """A ratio from 0 to 1 in 10% steps."""
    r = _real(x, "a ratio")
    if r < -_EPS or r > 1 + _EPS:
        raise ValueError("a ratio must be between 0 and 1")
    return min(RATIO_STEPS, max(0, _half_up(r * RATIO_STEPS))) / RATIO_STEPS


def minutes_to_hhmm(m: int) -> str:
    """For local display only (never put the result in a payload: it is a free string)."""
    return (datetime(2000, 1, 1) + timedelta(minutes=m)).strftime("%H:%M") if m < MINUTES_PER_DAY else "24:00"


# ------------------------------------------------------------------------------------------------------- annotated types
Count = Annotated[int | Literal["lt5"], BeforeValidator(bucket_count), Bucket("count_lt5")]
Attendees = Annotated[Literal["lt5", "5to9", "10plus"], BeforeValidator(bucket_attendees), Bucket("attendees")]
TimeOfDay = Annotated[int, BeforeValidator(round_time_minutes), Bucket("time_15min")]
DurationMin = Annotated[int, BeforeValidator(round_duration_minutes), Bucket("duration_5min")]
Hours = Annotated[float, BeforeValidator(bucket_hours), Bucket("hours_5min")]
Ratio = Annotated[float, BeforeValidator(bucket_ratio), Bucket("ratio_10pct")]

# ------------------------------------------------------------------------------------------------------- feature maps
FEATURE_RULES: dict[str, Any] = {
    "count": bucket_count,
    "duration_min": round_duration_minutes,
    "hours": bucket_hours,
    "ratio": bucket_ratio,
    "time15": round_time_minutes,
    "raw": lambda v: round(float(v), 2) if isinstance(v, float) else v,
}
_features_lock = threading.RLock()
_FEATURE_KIND: dict[str, str] = {}


def register_feature(name: str, kind: str) -> None:
    """Declare a named number (``meeting_h``) and how it is generalised (``count``, ``duration_min``, ``hours``, ``ratio``,
    ``time15`` or ``raw``). Adds ``name`` to the ``feature`` vocabulary. Re-registering with the same kind is a no-op."""
    if kind not in FEATURE_RULES:
        raise ValueError(f"unknown bucket kind {kind!r}; use one of {sorted(FEATURE_RULES)}")
    with _features_lock:
        old = _FEATURE_KIND.get(name)
        if old is not None and old != kind:
            raise ValueError(f"feature {name!r} is already registered as {old!r}")
        _FEATURE_KIND[name] = kind
    register_vocabulary("feature", [name], extend=True)


def feature_kinds() -> dict[str, str]:
    with _features_lock:
        return dict(_FEATURE_KIND)


def _bucket_numbers(value: Any) -> Any:
    """Before-validator for ``Numbers``: generalise each value by its feature's rule; unknown names pass through so the
    vocabulary check rejects them."""
    if not isinstance(value, dict):
        return value
    kinds = feature_kinds()
    out: dict[Any, Any] = {}
    for k, v in value.items():
        kind = kinds.get(k) if isinstance(k, str) else None
        out[k] = FEATURE_RULES[kind](v) if kind and not (isinstance(v, str) and kind != "count") else v
    return out


#: ``{feature: number}`` with every value generalised by the rule registered for its feature.
Numbers = Annotated[
    dict[Annotated[str, Vocab("feature")], int | float | Literal["lt5"]],
    BeforeValidator(_bucket_numbers), Bucket("by_feature"),
]
