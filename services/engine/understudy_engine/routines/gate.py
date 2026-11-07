"""Skill gate (ANA-11): a routine is eligible for automation only when the worker has mastered what it contains.

Eligible when the pack marks the routine as not learning-relevant, or the worker is at level 4 on the routine's skill
cogs. Otherwise the answer is "coach it first": automating a step the worker has not learned would only hide the
gap. The level comes from a ``SkillSource``: the analytics track's ``SkillTracker`` (the level engine, with decay), or
``MemorySkillSource``, which reads the Skill state lines of the worker's memory file and maps skills to cogs through
the pack curriculum. Both answer ``snapshot(t) -> {cog: {"level": int}}``.
"""
from __future__ import annotations

from typing import Any, Protocol

from ..memory.doc import MemoryDoc, skill_levels
from ..memory.packinfo import PackView

MAX_LEVEL = 4


class SkillSource(Protocol):
    def snapshot(self, t: float) -> dict[str, dict[str, Any]]: ...


class MemorySkillSource:
    """Levels from the memory file's Skill state section: one line per curriculum skill, mapped to its cogs."""

    def __init__(self, doc: MemoryDoc, pack: PackView | None = None) -> None:
        self.levels = skill_levels(doc)
        self.cogs_of: dict[str, list[str]] = {}
        for sk in (pack.skills if pack else []):
            self.cogs_of[str(sk["id"])] = list(sk.get("cogs", []))

    def snapshot(self, t: float) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for sid, st in self.levels.items():
            for cog in self.cogs_of.get(sid, []):
                cur = out.get(cog, {"level": MAX_LEVEL})
                out[cog] = {"level": min(cur["level"], st["level"])}
        return out


def routine_skill_gate(source: SkillSource | None, cogs: list[str], t: float, *, learning_relevant: bool = True) -> dict[str, Any]:
    """``{eligible, reason}`` for a routine whose skill cogs are ``cogs``."""
    if not learning_relevant:
        return {"eligible": True, "reason": "pack marks this routine as not learning-relevant"}
    if not cogs:
        return {"eligible": True, "reason": "no skill cogs involved"}
    if source is None:
        return {"eligible": False, "reason": "no skill record yet: coach first"}
    snap = source.snapshot(t)
    below = [(c, snap[c]["level"] if c in snap else 1) for c in cogs]
    low = [f"{c} at L{lv}" for c, lv in below if lv < MAX_LEVEL]
    if low:
        return {"eligible": False, "reason": "coach first: " + ", ".join(low)}
    return {"eligible": True, "reason": "mastery L4 on " + ", ".join(cogs)}
