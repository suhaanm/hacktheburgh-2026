"""Teach and fade (CUE-8): one line of why after a resolved step, once per skill per day; retrieval practice scheduled by mastery decay.

* **Teach.** After an occurrence that needed help, the decision's ``step.reason_id`` resolves to a line of 12 words or fewer from the
  fixed reason table (``vocab``). It is shown once per skill per day (``reason_due``); "Why this?" is always one tap away and is not
  limited. No model writes it.
* **Fade by retrieval.** The ledger is replayed through ``skills.tracing`` (clean, error and assisted evidence, forgetting between
  occurrences) to get the skill's mastery now. When it has decayed into the window where a recall is a fair test (``lo`` to ``hi``),
  at least ``min_gap_s`` after the last help, the next occurrence is a retrieval practice: the gate returns ``confirm`` (it withholds
  and only confirms afterwards) and the ledger row is marked ``retrieval``. Guards: not twice in a day for one skill; never again
  right after a failed retrieval (the worker needs help, not a test).
Pure functions of ledger rows and a clock.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..skills import tracing as T
from .ledger import hour_to_epoch

DAY_S = 86400.0


@dataclass(frozen=True)
class RetrievalParams:
    lo: float = 0.35               # below this the worker likely cannot recall: help, not a test
    hi: float = 0.80               # above this the worker has it: nothing to practise yet
    min_gap_s: float = 4 * 3600.0  # after the last help
    max_per_day: int = 1
    min_occurrences: int = 2       # a skill is taught before it is tested


DEFAULT_RETRIEVAL = RetrievalParams()


def row_time(r: dict[str, Any]) -> float:
    """The row's time: the middle of its hour bucket (the ledger never holds anything finer)."""
    return hour_to_epoch(r["t_hour"]) + 1800.0


def replay_mastery(rows: Sequence[dict[str, Any]], params: T.TracingParams = T.DEFAULT, assisted_as: str = "none") -> T.CogMastery:
    """Fold the assist rows of ONE skill, oldest first, through the tracing model. Abandoned counts as no evidence (assisted); an
    error is evidence against; a clean occurrence is evidence for. Delegated and automation rows must be filtered out by the caller
    (``assist_rows``). ``assisted_as="error"`` counts an assisted occurrence as an unaided failure (the learner could not do it alone);
    the default leaves it as no evidence, as the level engine does."""
    state = T.CogMastery()
    for r in sorted(rows, key=row_time):
        ev = {"clean": "clean", "error": "error"}.get(r["outcome"], "error" if (r["outcome"] == "assisted" and assisted_as == "error") else "assisted")
        state = T.observe(state, ev, row_time(r), params)          # type: ignore[arg-type]
    return state


def assist_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("stream") == "assist"]


@dataclass(frozen=True)
class SkillMem:
    n: int
    mastery_now: float
    last_help_t: float | None
    last_taught_t: float | None
    withheld_today: int
    last_retrieval_failed: bool


def skill_memory(rows: Sequence[dict[str, Any]], now: float, params: T.TracingParams = T.DEFAULT) -> SkillMem:
    rs = sorted(assist_rows(rows), key=row_time)
    st = replay_mastery(rs, params)
    helps = [row_time(r) for r in rs if r["outcome"] == "assisted"]
    taught = [row_time(r) for r in rs if r.get("taught")]
    day0 = now - (now % DAY_S)
    withheld_today = sum(1 for r in rs if r.get("retrieval") and row_time(r) >= day0)
    retr = [r for r in rs if r.get("retrieval")]
    failed = bool(retr and retr[-1]["outcome"] in ("error", "abandoned", "assisted"))
    return SkillMem(len(rs), T.decayed(st, now, params), helps[-1] if helps else None, taught[-1] if taught else None, withheld_today, failed)


def retrieval_due(mem: SkillMem, now: float, p: RetrievalParams = DEFAULT_RETRIEVAL) -> bool:
    if mem.n < p.min_occurrences or mem.last_help_t is None:
        return False
    if not (p.lo <= mem.mastery_now <= p.hi):
        return False
    if now - mem.last_help_t < p.min_gap_s or mem.withheld_today >= p.max_per_day or mem.last_retrieval_failed:
        return False
    return True


def reason_due(rows: Sequence[dict[str, Any]], now: float) -> bool:
    """True when no occurrence of this skill was marked taught today (UTC day)."""
    day0 = now - (now % DAY_S)
    return not any(r.get("taught") and row_time(r) >= day0 for r in assist_rows(rows))


def reason_for(vocab, step_id: str) -> dict[str, str | None]:
    rid = vocab.reason_id(step_id)
    return {"id": rid, "text": vocab.text_of(rid)}


def withheld_report(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """How many cues were withheld on purpose, and how those occurrences ended."""
    rs = [r for r in assist_rows(rows) if r.get("retrieval")]
    out = {"withheld": len(rs), "clean": 0, "assisted": 0, "error": 0, "abandoned": 0}
    for r in rs:
        out[r["outcome"]] += 1
    return out
