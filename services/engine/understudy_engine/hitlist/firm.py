"""The firm variant of the hit list (admin): the same repeated actions, added up across people, as an aggregate.

Privacy by construction (D41, and the owner's note that the firm list is an aggregate by default):

* A row is one action in one role, with the number of people who repeat it, the repeats in total, and the minutes and hours a week it
  takes in total. No person id, name or per-person row leaves this module: people are counted, never listed.
* A group of fewer than ``min_group`` (5) people is not listed at all; the number of such groups is reported as ``suppressed``.
* The figure is for coaching and onboarding, not for evaluating individuals: no ranking of people, no single score.

The people come from the synthetic firm of the insights layer when it exists (``insights.firm.repeat_people``); otherwise a small
deterministic firm is built here from the role packs (about 60 people in three roles, D43), so the page works on its own.
Everything is badged synthetic.
"""
from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

from ..memory.packinfo import PackView, list_pack_ids, load_pack
from . import vocab as V

MIN_GROUP = 5
MAX_ROWS = 10
# (people in the firm, per role). About 60 in all, three roles (D43).
FIRM_SIZE = {"benefits-processor": 36, "data-analyst": 12, "programmer": 12}
# typical runs a week for each shipped template, and the share of people in the role who do it at all
RUNS_PER_WEEK = {"calc-entry-3x": 14.0, "case-note-copy": 9.0, "weekly-report": 1.0, "weekly-metric-refresh": 1.2, "rerun-failed-ci": 6.0}
SHARE_WHO_DO_IT = {"calc-entry-3x": 0.9, "case-note-copy": 0.75, "weekly-report": 0.1, "weekly-metric-refresh": 0.8, "rerun-failed-ci": 0.85}


def combine(parts: Sequence[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Sum of independent estimates: the points add, the half-widths add in quadrature. ``(point, lo, hi)`` each."""
    point = sum(p for p, _, _ in parts)
    half = math.sqrt(sum((((hi - lo) / 2.0) ** 2) for _, lo, hi in parts))
    return point, max(0.0, point - half), point + half


def _iv(point: float, lo: float, hi: float, digits: int = 1) -> dict[str, float]:
    return {"point": round(point, digits), "lo": round(lo, digits), "hi": round(hi, digits)}


def aggregate(people: Sequence[Mapping[str, Any]], window_days: int, *, min_group: int = MIN_GROUP, role: str | None = None,
              max_rows: int = MAX_ROWS) -> dict[str, Any]:
    """``people``: ``[{"person", "role", "rows": [{id, label, key, family, count, minutes_per_week:{point,lo,hi}, stops_before}]}]``.
    Returns the firm hit list data. The ``person`` field is used only to count distinct people and is never copied out."""
    cohort = [p for p in people if role is None or p.get("role") == role]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for p in cohort:
        who = str(p.get("person"))
        for r in p.get("rows") or []:
            mp = r["minutes_per_week"]
            g = groups.setdefault((str(p.get("role")), str(r["id"])), {
                "role": str(p.get("role")), "id": str(r["id"]), "label": r["label"], "key": r.get("key"), "family": r.get("family", "step"),
                "stops_before": r.get("stops_before", "none"), "who": set(), "count": 0, "mins": []})
            g["who"].add(who)
            g["count"] += int(r["count"])
            g["mins"].append((float(mp["point"]), float(mp["lo"]), float(mp["hi"])))
    listed, suppressed = [], 0
    for g in groups.values():
        if len(g["who"]) < min_group:
            suppressed += 1
            continue
        pt, lo, hi = combine(g["mins"])
        listed.append({
            "id": g["id"], "label": g["label"], "key": g["key"], "family": g["family"], "role": g["role"], "people": len(g["who"]),
            "count": g["count"], "minutes_per_week": _iv(pt, lo, hi), "hours_per_week": _iv(pt / 60, lo / 60, hi / 60, 2),
            "stops_before": g["stops_before"],
        })
    listed.sort(key=lambda r: (-round(r["minutes_per_week"]["point"], 1), -r["people"], r["role"], r["id"]))
    shown = listed[:max_rows]
    if shown:
        pt, lo, hi = combine([(r["minutes_per_week"]["point"], r["minutes_per_week"]["lo"], r["minutes_per_week"]["hi"]) for r in shown])
        hours = _iv(pt / 60, lo / 60, hi / 60, 2)
    else:
        hours = _iv(0.0, 0.0, 0.0, 2)
    return {
        "window_days": int(window_days), "people": len(cohort), "min_group": min_group, "suppressed": suppressed,
        "not_shown": len(listed) - len(shown),
        "total": {"actions": len(shown), "people": len(cohort), "hours_per_week": hours},
        "rows": shown,
    }


# ----------------------------------------------------------------------------------------------- a small synthetic firm
def _row(t: Mapping[str, Any], count: int, per_run_min: float, weeks: float, pack: PackView) -> dict[str, Any]:
    label, key, fam = V.label_for(t, list(t["cogs"]))
    point = count / weeks * per_run_min
    half = 1.96 * point / math.sqrt(max(count, 1))               # a Poisson count: the relative half-width is 1.96 / sqrt(n)
    return {"id": str(t["id"]), "label": label, "key": key, "family": fam, "count": count,
            "minutes_per_week": {"point": round(point, 1), "lo": round(max(0.0, point - half), 1), "hi": round(point + half, 1)},
            "stops_before": V.stops_for_never(t.get("never") or [])}


def tiny_firm(window_days: int, seed: int = 43) -> list[dict[str, Any]]:
    """About 60 synthetic people in three roles, each with the repeated actions the role pack ships. Deterministic."""
    weeks = max(window_days, 7) / 7.0
    out: list[dict[str, Any]] = []
    have = set(list_pack_ids())
    for role, size in FIRM_SIZE.items():
        if role not in have:
            continue
        pack = load_pack(role)
        templates = [t for t in pack.templates if t.get("automatable", True)]
        for i in range(size):
            rng = random.Random(f"{seed}:{role}:{i}")
            speed = rng.lognormvariate(0.0, 0.3)
            rows = []
            for t in templates:
                if rng.random() > SHARE_WHO_DO_IT.get(str(t["id"]), 0.7):
                    continue
                rate = RUNS_PER_WEEK.get(str(t["id"]), 5.0) * rng.lognormvariate(0.0, 0.35)
                count = max(0, round(rate * weeks + rng.gauss(0, math.sqrt(max(rate * weeks, 1.0)))))
                mpr = float((t.get("value_defaults") or {}).get("manual_minutes_per_run", 4.0)) * speed
                if count >= 3 and count / weeks * mpr >= 1.0:
                    rows.append(_row(t, count, mpr, weeks, pack))
            out.append({"person": f"f_{role[:3]}_{i:02d}", "role": role, "rows": rows})
    return out


def firm_people(window_days: int) -> tuple[list[dict[str, Any]], str]:
    """``(people, source)``: the insights layer's synthetic firm when it offers one in the right shape, else the small one built here."""
    try:
        from ..insights import firm as F          # type: ignore[attr-defined]

        fn = getattr(F, "repeat_people", None)
        if callable(fn):
            ppl = fn(window_days)
            if isinstance(ppl, list) and ppl and all(isinstance(p, dict) and "role" in p and isinstance(p.get("rows"), list) for p in ppl):
                return ppl, "insights"
    except Exception:
        pass
    return tiny_firm(window_days), "built-in"


def firm_hitlist(window_days: int, role: str | None = None) -> tuple[dict[str, Any], str]:
    people, source = firm_people(window_days)
    return aggregate(people, window_days, role=role), source
