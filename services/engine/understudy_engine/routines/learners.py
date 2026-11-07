"""Learner trajectories (``data/synthetic/learners``) as skill state: a ``SkillTracker`` built case by case.

Three synthetic novices, 30 benefits cases each. For every case we derive what the coach would have counted, per cog:

* a cog seen in the case is ``clean``, unless one of its segments carries a planted deficit tag, or a deficit that
  belongs to it is present in the case, in which case it is an ``error``;
* a deficit the coach prompted and the learner followed is ``assisted`` (neutral: it moves no level);
* time passes as in the data, so an absence decays mastery (the level engine only ever lowers a level after absence).

The tracker never reads the planted skill curve; only per-case outcomes (``truth.traces``) go in. The analytics track's
``SkillTracker`` is the authority for levels and the chip; this module only feeds it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..memory.paths import data_dir
from ..skills import SkillTracker

#: the cog each planted deficit is about (what the worker would be coached on)
DEFICIT_COG = {
    "copy_error": "COPY_TO_NOTE", "idle_before_enter": "ENTER_HOUSEHOLD", "repeated_read_result": "READ_RESULT",
    "search_loop": "SEARCH", "skipped_check_cliff": "CHECK_CLIFF",
}
IGNORE = {"IDLE", "REVERT"}


@dataclass
class LearnerState:
    person: str
    case: int
    n_cases: int
    t_ref: float
    tracker: SkillTracker
    trace: dict[str, Any]
    snapshot: dict[str, dict[str, Any]]


def _truth(root: Path | None = None) -> dict[str, Any] | None:
    p = (root or data_dir()) / "synthetic" / "learners" / "truth.json"
    return json.loads(p.read_text()) if p.exists() else None


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def learner_people(root: Path | None = None) -> list[str]:
    t = _truth(root)
    return [p["person"] for p in t["people"]] if t else []


def case_outcomes(trace: dict[str, Any]) -> dict[str, str]:
    """cog -> clean | error | assisted for one case."""
    seen = {c for c, _, _ in trace["cogs"] if c not in IGNORE}
    tagged = {c for c, _, tag in trace["cogs"] if tag and c not in IGNORE}
    followed = {co["deficit"] for co in trace.get("coach", []) if co.get("shown") and co.get("followed")}
    out = {c: ("error" if c in tagged else "clean") for c in seen}
    for d in trace.get("deficits", []):
        cog = DEFICIT_COG.get(d["type"])
        if cog:
            out[cog] = "assisted" if d["type"] in followed else "error"
    return out


def tracker_at(person: str, case: int | None = None, root: Path | None = None) -> LearnerState | None:
    truth = _truth(root)
    if not truth:
        return None
    traces = sorted((t for t in truth["traces"] if t["person"] == person), key=lambda t: t["case"])
    if not traces:
        return None
    n = len(traces)
    case = n if case is None else min(max(1, case), n)
    tr = SkillTracker()
    t_ref = 0.0
    cur = traces[0]
    for t in traces[:case]:
        t_ref = _ts(t["t1"])
        for cog, outcome in sorted(case_outcomes(t).items()):
            tr.observe(cog, outcome, t_ref)  # type: ignore[arg-type]
        cur = t
    return LearnerState(person, case, n, t_ref, tr, cur, tr.snapshot(t_ref))
