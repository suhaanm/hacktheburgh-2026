"""Calendar routine layer (CAL-1 to CAL-4). Off by default: ``UNDERSTUDY_X=1`` or ``UNDERSTUDY_X_CALENDAR=1`` turns the API on.

Pipeline (text stops at ``normalize``): source plugin -> ``RawItem`` (raw text, in memory) -> ``normalize.to_blocks`` (text-free
``Block`` objects) -> ``features.analyse_week`` (numbers and enums) -> ``expert`` (reference and gap) -> ``suggest`` (code selects
templates; wording through the egress guard only).

    from understudy_engine.calendar import features, expert, suggest, synth, store, real_check, evaluate
"""
from __future__ import annotations

import os


def flag_enabled() -> bool:
    on = ("1", "true", "yes")
    return os.environ.get("UNDERSTUDY_X_CALENDAR", "").strip().lower() in on or os.environ.get("UNDERSTUDY_X", "").strip().lower() in on
