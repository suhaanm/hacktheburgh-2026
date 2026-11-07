"""AnalyticMeta-shaped dicts for the evaluate_* outputs (API_CONTRACT: every analytic carries meta)."""
from __future__ import annotations

import datetime as _dt


def analytic_meta(origin: str, n: int, n_unit: str, split: str | None, note: str | None = None,
                  interval_level: float = 0.95) -> dict:
    return {
        "origin": origin, "n": int(n), "n_unit": n_unit, "split": split, "interval_level": interval_level,
        "note": note, "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
