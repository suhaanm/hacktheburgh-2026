"""Deterministic help-level engine L1..L4 (COA-3). This is the AUTHORITY; tracing only informs it.

  L1  full help    L2  small help    L3  a dot    L4  gone (the worker has it)

Rules (per cog, per person):
  - three clean runs in a row move one level UP (L4 is the ceiling)
  - two or more errors among the last five counted outcomes move one level DOWN (L1 is the floor)
  - an assisted run is neutral: it neither adds to a streak, nor breaks one, nor enters the window
  - after any level change the streak and the window start fresh, so the new level gets a fair trial
  - after absence, mastery can only LOWER the level: the level is capped by what the decayed mastery supports
    (`cap_for_mastery`), never raised by it

No model, no randomness, no clock inside: every function takes what it needs and returns a new state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

Outcome = Literal["clean", "error", "assisted"]

MIN_LEVEL, MAX_LEVEL = 1, 4
PROMOTE_STREAK = 3
DEMOTE_ERRORS = 2
WINDOW = 5
# mastery needed to hold level 2, 3, 4 after absence (decayed mastery below this lowers the level)
MASTERY_FOR_LEVEL = {2: 0.40, 3: 0.65, 4: 0.85}
CHIP = {1: "full", 2: "small", 3: "dot", 4: "gone"}


@dataclass(frozen=True)
class LevelState:
    level: int = MIN_LEVEL
    streak: int = 0                 # consecutive clean runs since the last change
    recent: tuple[str, ...] = ()    # up to WINDOW counted outcomes since the last change: "c" or "e"
    attempts: int = 0               # counted + assisted, for display
    assisted: int = 0

    @property
    def label(self) -> str:
        return f"L{self.level}"

    @property
    def chip(self) -> str:
        return CHIP[self.level]


def apply_outcome(state: LevelState, outcome: Outcome) -> tuple[LevelState, int]:
    """Returns (new state, change) where change is +1, -1 or 0."""
    if outcome == "assisted":
        return replace(state, attempts=state.attempts + 1, assisted=state.assisted + 1), 0
    if outcome not in ("clean", "error"):
        raise ValueError(f"unknown outcome {outcome!r}")
    code = "c" if outcome == "clean" else "e"
    streak = state.streak + 1 if code == "c" else 0
    recent = (state.recent + (code,))[-WINDOW:]
    new = replace(state, streak=streak, recent=recent, attempts=state.attempts + 1)
    if code == "c" and streak >= PROMOTE_STREAK and state.level < MAX_LEVEL:
        return replace(new, level=state.level + 1, streak=0, recent=()), +1
    if code == "e" and recent.count("e") >= DEMOTE_ERRORS and state.level > MIN_LEVEL:
        return replace(new, level=state.level - 1, streak=0, recent=()), -1
    return new, 0


def cap_for_mastery(mastery: float) -> int:
    """The highest level a (decayed) mastery supports."""
    level = MIN_LEVEL
    for lv in (2, 3, 4):
        if mastery >= MASTERY_FOR_LEVEL[lv]:
            level = lv
    return level


def apply_decay(state: LevelState, mastery_now: float) -> tuple[LevelState, int]:
    """After absence: lower the level to what the decayed mastery supports (never raise). Resets streak and window
    when it lowers, because the worker is effectively starting that level again."""
    cap = cap_for_mastery(mastery_now)
    if state.level > cap:
        return replace(state, level=cap, streak=0, recent=()), cap - state.level
    return state, 0


def run_outcomes(outcomes: list[str], start: LevelState | None = None) -> LevelState:
    s = start or LevelState()
    for o in outcomes:
        s, _ = apply_outcome(s, o)  # type: ignore[arg-type]
    return s
