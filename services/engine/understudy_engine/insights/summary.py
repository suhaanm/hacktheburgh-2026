"""Per-person summaries and the k-anonymity gate for admin views (REQ-9, owner decisions D41 and D43).

``PersonSummary`` holds numbers and enums only: counts, a share and its Wilson interval, a trend class, per-skill independence and time lost
with intervals, automation counts, a status. The ledger rows it was computed from stay in a private field and are never serialised
(``to_row`` has a fixed key set and a test scans every admin response for ledger fields and row ids).

``AdminView`` is the one door into the firm: comparison tables get their groups from ``cohort``, which refuses a group below the minimum
size (5), so no admin comparison can be computed on fewer people by accident. Per-user rows are allowed (D41) and use ``person_rows``,
ordered by the pseudonym label, never by performance.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import stats as S
from . import vocab as V
from .params import DAY, DEFAULT, Params
from .rows import (
    current_role_rows,
    grace_flags,
    is_assisted,
    is_independent,
    lost_values,
    row_t,
)
from .types import FirmSnapshot, PersonRecord

_ASSIST_STATUS_OK = ("ok",)


def est(value: float | None, lo: float | None = None, hi: float | None = None, nd: int = 4) -> dict[str, Any] | None:
    """The ``Est`` of the ADMIN-UI contract: ``{value, ci}``; ``ci`` is None when there is no interval."""
    if value is None:
        return None
    return {"value": round(float(value), nd), "ci": None if lo is None or hi is None else [round(float(lo), nd), round(float(hi), nd)]}


def est_from(e: S.Est | None, nd: int = 4, scale: float = 1.0) -> dict[str, Any] | None:
    return None if e is None else est(e.value * scale, e.lo * scale, e.hi * scale, nd)


def wilson_est(k: int, n: int, z: float = S.Z95) -> dict[str, Any] | None:
    if n <= 0:
        return None
    lo, hi = S.wilson_interval(k, n, z)
    return est(k / n, lo, hi)


@dataclass
class PersonSummary:
    id: str
    label: str
    role: str
    level: str
    unit: str
    tenure_weeks: int
    status: str                                  # ok | onboarding | stale | no_data
    n: int                                       # assist occurrences in the current role
    n_window: int                                # ... in the admin window
    n_recent: int                                # ... in the last 21 days
    last_seen_days: int | None
    last_t: float | None
    independence: dict[str, Any] | None          # share unaided over the last 20, with its Wilson interval
    assisted: dict[str, Any] | None
    trend: str
    skills: list[dict[str, Any]]
    automation: dict[str, int]
    reached: bool
    reached_at: int | None
    origin: str
    _rows: tuple[dict[str, Any], ...] = field(default=(), repr=False)         # private: never serialised
    _grace: tuple[bool, ...] = field(default=(), repr=False)
    _person: PersonRecord | None = field(default=None, repr=False)

    @property
    def band(self) -> str:
        return V.tenure_band(self.tenure_weeks)

    def enough(self, p: Params) -> bool:
        return self.status == "ok" and self.n_window >= p.min_person_n

    def to_row(self) -> dict[str, Any]:
        """The per-user row an admin sees, and the worker's transparency page shows: numbers and enums only, a fixed key set."""
        return {
            "id": self.id, "label": self.label, "role": self.role, "level": self.level, "unit": self.unit, "tenure_band": self.band,
            "tenure_weeks": int(self.tenure_weeks), "status": self.status, "trend": self.trend, "trend_label": V.TREND_LABEL[self.trend],
            "independence": self.independence, "assisted_share": self.assisted,
            "time_to_independence": {"reached": self.reached, "value": self.reached_at, "unit": "occurrences"},
            "automations_running": int(self.automation.get("routines_approved", 0)), "automation": dict(self.automation), "n": int(self.n),
            "n_recent": int(self.n_recent), "last_seen_days": self.last_seen_days, "skills": [dict(s) for s in self.skills], "origin": self.origin,
        }


def reach_index(rows: list[dict[str, Any]], target: float, window: int) -> int | None:
    """The first occurrence index (1-based) at which the share unaided over the trailing ``window`` occurrences is at least ``target``."""
    if len(rows) < window:
        return None
    flags = np.array([1 if is_independent(r) else 0 for r in rows], float)
    csum = np.concatenate([[0.0], np.cumsum(flags)])
    for i in range(window, len(rows) + 1):
        if (csum[i] - csum[i - window]) / window >= target:
            return i
    return None


def _trend_class(rows: list[dict[str, Any]], seed: int) -> str:
    try:
        from ..cue import score as cscore

        tr = cscore.trend(rows, n_boot=100, seed=seed)
    except Exception:  # pragma: no cover - the cue score module is unavailable
        return "not_enough_data"
    return {"less_help": "improving", "more_help": "needs_attention", "steady": "cannot_tell_yet", "too_early": "not_enough_data"}.get(tr.get("direction"), "not_enough_data")


def summarise(person: PersonRecord, snap: FirmSnapshot, p: Params = DEFAULT) -> PersonSummary:
    now = snap.now
    rows = current_role_rows(person)
    n = len(rows)
    last_t = max((row_t(r) for r in rows), default=None)
    if n == 0:
        status = "no_data"
    elif now - (last_t or 0.0) > p.stale_days * DAY:
        status = "stale"
    elif n < p.onboard_min:
        status = "onboarding"
    else:
        status = "ok"
    grace = grace_flags(rows, p)
    win_idx = [i for i, r in enumerate(rows) if now - p.admin_window_days * DAY < row_t(r) <= now]
    n_recent = sum(1 for r in rows if now - p.recent_days * DAY < row_t(r) <= now)
    last20 = rows[-20:]
    ind = wilson_est(sum(1 for r in last20 if is_independent(r)), len(last20)) if n >= p.onboard_min and status != "no_data" else None
    asst = wilson_est(sum(1 for r in last20 if is_assisted(r)), len(last20)) if n >= p.onboard_min and status != "no_data" else None
    skills: list[dict[str, Any]] = []
    by: dict[str, list[int]] = defaultdict(list)
    for i in win_idx:
        if rows[i].get("skill"):
            by[rows[i]["skill"]].append(i)
    for s, idx in sorted(by.items()):
        rs = [rows[i] for i in idx]
        ng = [rows[i] for i in idx if not grace[i]]
        vals = lost_values(ng, p.lost_clip)
        e = S.median_est(vals) if len(vals) >= 3 and len(vals) >= 0.5 * max(1, len(ng)) else None
        skills.append({"skill": s, "label": skill_label(person.role, s), "n": len(rs), "independence_share": round(sum(1 for r in rs if is_independent(r)) / len(rs), 4),
                       "lost_s": est_from(e, 1)})
    approved = [r for r in snap.routines if r.get("person") == person.id and r.get("status") in ("approval", "unattended")]
    auto_rows = [r for r in person.rows if r.get("stream") == "automation" and r.get("offload_outcome") == "done" and now - row_t(r) <= 28 * DAY]
    ri = reach_index(rows, p.target_share, p.target_window)
    trend = _trend_class(rows, S.seed_from("trend", person.id, n)) if n >= 30 and status in ("ok", "stale") else "not_enough_data"
    return PersonSummary(
        id=person.id, label=person.label or person.id, role=person.role, level=person.level, unit=person.unit, tenure_weeks=person.tenure_weeks, status=status,
        n=n, n_window=len(win_idx), n_recent=n_recent, last_seen_days=None if last_t is None else int(max(0.0, now - last_t) // DAY), last_t=last_t, independence=ind, assisted=asst,
        trend=trend, skills=skills, automation={"routines_approved": len(approved), "runs_done": len(auto_rows), "minutes": int(round(math.fsum(r.get("minutes") or 0.0 for r in auto_rows)))},
        reached=ri is not None, reached_at=ri, origin=person.origin, _rows=tuple(rows), _grace=tuple(grace), _person=person)


_SKILL_LABELS: dict[tuple[str, str], str] = {}


def skill_label(role: str, skill: str) -> str:
    """A short name for a skill id: the pack curriculum's label when it loads, else the id with spaces. Cached; never a model."""
    key = (role, skill)
    if key not in _SKILL_LABELS:
        label = skill.replace("-", " ").replace("_", " ")
        try:
            from ..cue.vocab import skill_info

            label = skill_info(role, skill)["label"] or label
        except Exception:
            pass
        _SKILL_LABELS[key] = label
    return _SKILL_LABELS[key]


def skill_name(role: str, skill: str) -> str:
    """A short noun phrase for a sentence ("the cliff check"): the layer's own table, never a pack label (those are whole sentences)."""
    return V.skill_phrase(skill)


def merge_small(cells: dict[str, list[str]], k: int) -> list[tuple[str, list[str]]]:
    """Cells below ``k`` people are pooled into "Other"; if the pool is still below ``k`` it joins the smallest cell that meets ``k``; if none
    does, nothing is shown. The result is in label order with "Other" last. A comparison table is never built on a group smaller than ``k``."""
    keep = {c: sorted(ids) for c, ids in cells.items() if len(ids) >= k}
    pool = sorted(i for c, ids in cells.items() if len(ids) < k for i in ids)
    if pool:
        if len(pool) >= k:
            keep["Other"] = pool
        elif keep:
            smallest = min(keep, key=lambda c: (len(keep[c]), c))
            keep[smallest] = sorted(keep[smallest] + pool)
    return sorted(keep.items(), key=lambda kv: (kv[0] == "Other", kv[0]))


class AdminView:
    """Everything an admin may see, derived once from the snapshot. Comparison groups come only from ``cohort``."""

    def __init__(self, snap: FirmSnapshot, p: Params = DEFAULT) -> None:
        self.snap, self.p, self.now = snap, p, snap.now
        self._cache: dict[Any, Any] = {}
        self.sums: dict[str, PersonSummary] = {pr.id: summarise(pr, snap, p) for pr in snap.people}

    # ----- groups
    def people(self, *, role: str | None = None, level: str | None = None, unit: str | None = None) -> list[PersonSummary]:
        return sorted((s for s in self.sums.values() if (role is None or s.role == role) and (level is None or s.level == level) and (unit is None or s.unit == unit)), key=lambda s: s.id)

    def cohort(self, *, role: str | None = None, level: str | None = None, unit: str | None = None, enough: bool = True) -> list[PersonSummary] | None:
        """The group for a COMPARISON, or None when it has fewer than ``k_anon`` people (with enough data when ``enough``)."""
        g = [s for s in self.people(role=role, level=level, unit=unit) if (s.enough(self.p) if enough else s.status != "no_data")]
        return sorted(g, key=lambda s: s.id) if len(g) >= self.p.k_anon else None

    def roles(self) -> list[str]:
        return sorted({s.role for s in self.sums.values()})

    def person_rows(self, role: str | None = None) -> list[dict[str, Any]]:
        """Per-user rows: numbers and enums only, ordered by the pseudonym label (not by any performance)."""
        return [s.to_row() for s in sorted(self.people(role=role), key=lambda s: (s.label, s.id))]

    # ----- coverage
    def coverage(self) -> dict[str, Any]:
        ss = list(self.sums.values())
        enough = [s for s in ss if s.status == "ok" and s.n_window >= self.p.enough_n]
        by_status = {k: sum(1 for s in ss if s.status == k) for k in V.STATUSES_PERSON}
        return {"users": len(ss), "enough_data": len(enough), "min_occurrences": self.p.enough_n, "share_enough": round(len(enough) / len(ss), 4) if ss else 0.0,
                "by_status": by_status, "roles": [{"role": r, "name": V.role_name(r), "users": len(self.people(role=r)),
                                                  "enough_data": sum(1 for s in enough if s.role == r)} for r in self.roles()]}

    # ----- person-level numbers for comparisons (rows never leave this class)
    def person_skill(self, s: PersonSummary, *, since_days: float | None = None, until_days: float = 0.0, exclude_grace: bool = True) -> dict[str, dict[str, float]]:
        """``{skill: {n, lost, assisted, indep}}`` for one person in a window, from rows kept private to this view."""
        lo = self.now - (since_days if since_days is not None else self.p.admin_window_days) * DAY
        hi = self.now - until_days * DAY
        acc: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for i, r in enumerate(s._rows):
            if lo < row_t(r) <= hi and r.get("skill") and not (exclude_grace and s._grace[i]):
                acc[r["skill"]].append(r)
        out: dict[str, dict[str, float]] = {}
        for sk, rs in acc.items():
            lv = lost_values(rs, self.p.lost_clip)
            out[sk] = {"n": float(len(rs)), "lost": float(np.median(lv)) if len(lv) >= 0.5 * len(rs) and lv else float("nan"),
                       "assisted": sum(1 for r in rs if is_assisted(r)) / len(rs), "indep": sum(1 for r in rs if is_independent(r)) / len(rs),
                       "errors": float(sum(1 for r in rs if r["outcome"] == "error"))}
        return out
