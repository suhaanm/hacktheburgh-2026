"""Autonomy ladder A0..A3 with Wilson lower bounds (HND-4).

  A0  observe only
  A1  suggest and run in shadow mode (the agent does the work off to the side; the result is compared
      with what the worker did, nothing is saved or submitted)
  A2  do it, with the worker's approval of the result
  A3  do it, then report

Deterministic code decides, never a model:

  A0 -> A1   only by an explicit worker action (`grant_shadow`); never automatic
  A1 -> A2   at least 20 trials AND Wilson lower bound (z = 1.96) of the clean rate >= 0.80
             (20 clean of 20 gives about 0.839; one mismatch needs about 30 trials)
  A2 -> A3   Wilson lower bound >= 0.95 (73 clean of 73; the demo does not reach this, by design)
  any rung   one rung DOWN on a failure, an undo within seconds, or an injection-detector hit; the
             evidence counters reset so the lower rung has to be earned again

A shadow *mismatch* at A1 is a failed trial that counts against the bound but is not a failure of the
run itself, so it does not demote. `cap` is the highest rung the worker consented to; evidence may
earn more than the cap allows, in which case the rung stays at the cap.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from understudy_engine.trust.stats import wilson_lower

Rung = Literal["A0", "A1", "A2", "A3"]
RUNGS: tuple[Rung, ...] = ("A0", "A1", "A2", "A3")
Outcome = Literal["clean", "mismatch", "failure", "undo", "injection"]

Z = 1.96
MIN_RUNS_A2 = 20
LOWER_A2 = 0.80
LOWER_A3 = 0.95


def _idx(r: Rung) -> int:
    return RUNGS.index(r)


@dataclass(frozen=True)
class LadderState:
    rung: Rung = "A0"
    runs: int = 0     # trials since the last demotion (shadow comparisons and approved runs)
    clean: int = 0    # of which clean
    history: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def wilson_lower(self) -> float:
        return wilson_lower(self.clean, self.runs, Z) if self.runs else 0.0

    def to_dict(self) -> dict:
        return {"rung": self.rung, "runs": self.runs, "matches": self.clean,
                "wilson_lower": self.wilson_lower}


@dataclass(frozen=True)
class Decision:
    state: LadderState
    promoted: bool = False
    demoted: bool = False
    reason: str = ""


def earned_rung(runs: int, clean: int) -> Rung:
    """The highest rung the evidence alone supports (ignoring consent): A1 is the floor for any evidence."""
    lb = wilson_lower(clean, runs, Z) if runs else 0.0
    if lb >= LOWER_A3 and runs >= MIN_RUNS_A2:
        return "A3"
    if runs >= MIN_RUNS_A2 and lb >= LOWER_A2:
        return "A2"
    return "A1"


def grant_shadow(state: LadderState) -> Decision:
    """The worker opts the routine into shadow mode: A0 -> A1. Idempotent above A0."""
    if state.rung != "A0":
        return Decision(state)
    new = replace(state, rung="A1", history=state.history + ({"event": "grant_shadow", "to": "A1"},))
    return Decision(new, promoted=True, reason="worker enabled shadow mode")


def record_run(state: LadderState, outcome: Outcome, *, cap: Rung = "A3") -> Decision:
    """Apply one observed outcome. Returns the new state and what changed."""
    if outcome in ("failure", "undo", "injection"):
        if state.rung == "A0":
            return Decision(replace(state, runs=0, clean=0,
                                    history=state.history + ({"event": outcome, "to": "A0"},)),
                            reason=f"{outcome}: already at A0")
        new_rung = RUNGS[_idx(state.rung) - 1]
        new = LadderState(new_rung, 0, 0, state.history + ({"event": outcome, "from": state.rung, "to": new_rung},))
        return Decision(new, demoted=True, reason=f"{outcome}: demoted {state.rung} -> {new_rung}")
    if state.rung == "A0":
        return Decision(state, reason="observation only at A0; no evidence counted")
    if outcome == "mismatch":
        new = replace(state, runs=state.runs + 1)
        if state.rung != "A1":  # a mismatch above A1 means the result was wrong: treat as a failure
            return record_run(state, "failure", cap=cap)
        return Decision(new, reason="shadow mismatch counted against the bound")
    if outcome != "clean":
        raise ValueError(f"unknown outcome {outcome!r}")
    new = replace(state, runs=state.runs + 1, clean=state.clean + 1)
    target = min(_idx(earned_rung(new.runs, new.clean)), _idx(cap))
    if target > _idx(new.rung):
        # one rung at a time
        to = RUNGS[_idx(new.rung) + 1]
        new = replace(new, rung=to, history=new.history + ({"event": "promote", "to": to,
                                                            "runs": new.runs, "wilson_lower": new.wilson_lower},))
        return Decision(new, promoted=True, reason=f"promoted to {to}: lower bound {new.wilson_lower:.3f} on {new.runs} trials")
    return Decision(new, reason=f"{new.clean}/{new.runs}, lower bound {new.wilson_lower:.3f}")


def runs_needed(target: Rung, clean_so_far: int = 0, runs_so_far: int = 0) -> int | None:
    """How many further consecutive clean runs would reach `target` (None if the rung is not evidence-gated)."""
    if target in ("A0", "A1"):
        return None
    bar = LOWER_A2 if target == "A2" else LOWER_A3
    k = 0
    while k < 5000:
        n, c = runs_so_far + k, clean_so_far + k
        if n >= MIN_RUNS_A2 and wilson_lower(c, n, Z) >= bar:
            return k
        k += 1
    return None
