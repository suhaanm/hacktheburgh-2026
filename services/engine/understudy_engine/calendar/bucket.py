"""Generalisation helpers (PRV-3): what a number looks like before it may enter an outbound payload.

These are the privacy track's rules (``understudy_engine.privacy.bucket``): counts under 5 become ``"lt5"``, times of day round
to 15 minutes, durations to 5 minutes, ratios to 10% steps. They are imported from there; the local definitions below are only
a fallback so this layer still imports where the privacy package is absent.
"""
from __future__ import annotations

import math

LT5 = "lt5"

try:                                                    # the canonical implementations
    from ..privacy.bucket import bucket_count, bucket_hours as round_hours, bucket_ratio as round_ratio
    from ..privacy.bucket import round_duration_minutes as round_minutes, round_time_minutes as round_time_of_day
    FROM_PRIVACY = True
except ImportError:                                     # pragma: no cover - the privacy package is part of the repo
    FROM_PRIVACY = False

    def bucket_count(n):                                # type: ignore[misc]
        n = int(round(n))
        return LT5 if n < 5 else n

    def round_minutes(minutes, step=5):                 # type: ignore[misc]
        return int(step * math.floor(minutes / step + 0.5))

    def round_time_of_day(minute_of_day):               # type: ignore[misc]
        return round_minutes(minute_of_day, 15) % 1440

    def round_ratio(x, step=0.1):                       # type: ignore[misc]
        return round(round(x / step) * step, 2)

    def round_hours(hours):                             # type: ignore[misc]
        return round(round_minutes(hours * 60) / 60.0, 2)

__all__ = ["LT5", "FROM_PRIVACY", "bucket_count", "round_hours", "round_minutes", "round_ratio", "round_time_of_day"]
