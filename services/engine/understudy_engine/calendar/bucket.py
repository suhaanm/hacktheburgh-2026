"""Generalisation helpers (PRV-3): what a number looks like before it may enter an outbound payload.

Local implementations. The privacy track owns the canonical ones (``understudy_engine.privacy.bucket``); ``swap_in`` below
adopts them when that module lands with these names, otherwise these stay. Rules from the spec: counts under 5 become
"lt5", times round to 15 minutes, durations to 5 minutes, ratios to 10% steps.
"""
from __future__ import annotations

import importlib
import math
from typing import Callable

LT5 = "lt5"


def bucket_count(n: int | float) -> int | str:
    """Counts under 5 become the enum ``"lt5"``; larger counts pass unchanged."""
    n = int(round(n))
    return LT5 if n < 5 else n


def round_minutes(minutes: float, step: int = 5) -> int:
    """Durations to the nearest ``step`` minutes (5 by default)."""
    return int(step * math.floor(minutes / step + 0.5))


def round_time_of_day(minute_of_day: float) -> int:
    """A time of day (minutes after midnight) to the nearest 15 minutes."""
    return round_minutes(minute_of_day, 15) % 1440


def round_ratio(x: float, step: float = 0.1) -> float:
    """Ratios to 10% steps."""
    return round(round(x / step) * step, 2)


def round_hours(hours: float) -> float:
    """Hours as a 5-minute-rounded duration."""
    return round(round_minutes(hours * 60) / 60.0, 3)


def swap_in() -> bool:
    """Adopt the privacy track's helpers when present (same names). Returns True when swapped."""
    global bucket_count, round_minutes, round_time_of_day, round_ratio
    try:
        mod = importlib.import_module("understudy_engine.privacy.bucket")
    except ImportError:
        return False
    names = ("bucket_count", "round_minutes", "round_time_of_day", "round_ratio")
    if not all(callable(getattr(mod, n, None)) for n in names):
        return False
    bucket_count, round_minutes, round_time_of_day, round_ratio = (getattr(mod, n) for n in names)
    return True
