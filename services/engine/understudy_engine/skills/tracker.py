"""A person's skill state: per cog, the level engine (authority) beside mastery (evidence and decay clock).

`observe` updates both. `snapshot(t)` applies absence: mastery decays and may LOWER a level (never raise).
`skill_gate` answers the routine-eligibility question (a routine may be automated only if the worker is at
L4 on its cogs, or the pack marks it as not learning-relevant). `coach_state` feeds the Today screen.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from understudy_engine.skills import levels as L
from understudy_engine.skills import tracing as T


@dataclass(frozen=True)
class CogSkill:
    level: L.LevelState = field(default_factory=L.LevelState)
    mastery: T.CogMastery = field(default_factory=T.CogMastery)


class SkillTracker:
    def __init__(self, params: T.TracingParams = T.DEFAULT) -> None:
        self.params = params
        self.cogs: dict[str, CogSkill] = {}

    def observe(self, cog: str, outcome: L.Outcome, t: float) -> dict:
        """Fold in one outcome at unix time t. Returns what changed."""
        cur = self.cogs.get(cog, CogSkill())
        # absence first: decayed mastery may cap the level before this run is counted
        m_now = T.decayed(cur.mastery, t, self.params)
        lv, decay_change = L.apply_decay(cur.level, m_now) if cur.mastery.t is not None else (cur.level, 0)
        lv, change = L.apply_outcome(lv, outcome)
        ms = T.observe(cur.mastery, outcome, t, self.params)
        self.cogs[cog] = CogSkill(lv, ms)
        return {"cog": cog, "level": lv.level, "change": change, "decay_change": decay_change,
                "mastery": ms.m}

    def snapshot(self, t: float) -> dict[str, dict]:
        """Per cog at time t: level (after absence), mastery, decay clock. Does not mutate state."""
        out = {}
        for cog, cs in self.cogs.items():
            m = T.decayed(cs.mastery, t, self.params)
            lv, _ = L.apply_decay(cs.level, m)
            out[cog] = {
                "level": lv.level, "label": lv.label, "chip": lv.chip, "streak": lv.streak,
                "mastery": m, "stability_days": cs.mastery.stability_days,
                "days_until_level_drop": _days_to_drop(cs, lv, t, self.params),
                "last_seen": None if cs.mastery.t is None else
                _dt.datetime.fromtimestamp(cs.mastery.t, tz=_dt.timezone.utc).strftime("%Y-%m-%d"),
            }
        return out

    def level_of(self, cog: str, t: float) -> int:
        snap = self.snapshot(t).get(cog)
        return snap["level"] if snap else L.MIN_LEVEL

    def coach_state(self, cogs: list[str], t: float) -> dict:
        """Today-screen fields: overall level is the lowest level among the cogs the current step needs."""
        snap = self.snapshot(t)
        lv = min((snap[c]["level"] if c in snap else L.MIN_LEVEL) for c in cogs) if cogs else L.MIN_LEVEL
        return {"level": f"L{lv}", "chip": L.CHIP[lv],
                "mastery": {c: (snap[c]["mastery"] if c in snap else self.params.p_init) for c in cogs}}


def _days_to_drop(cs: CogSkill, lv: L.LevelState, t: float, p: T.TracingParams) -> float | None:
    """Days of no practice until the level would next drop (None at L1)."""
    if lv.level <= L.MIN_LEVEL:
        return None
    return T.days_until(cs.mastery, L.MASTERY_FOR_LEVEL[lv.level], t, p)


def skill_gate(tracker: SkillTracker, cogs: list[str], t: float, *, learning_relevant: bool = True) -> dict:
    """Routine eligibility (spec 7.1 routines): automate only when the worker is at L4 on every cog involved,
    or the pack marks the routine as not learning-relevant. Otherwise the system coaches instead."""
    if not learning_relevant:
        return {"eligible": True, "reason": "pack marks this routine as not learning-relevant"}
    snap = tracker.snapshot(t)
    below = [(c, snap[c]["level"] if c in snap else L.MIN_LEVEL) for c in cogs]
    low = [f"{c} at L{lv}" for c, lv in below if lv < L.MAX_LEVEL]
    if not cogs:
        return {"eligible": True, "reason": "no cogs involved"}
    if low:
        return {"eligible": False, "reason": "coach first: " + ", ".join(low)}
    return {"eligible": True, "reason": "mastery L4 on " + ", ".join(cogs)}
