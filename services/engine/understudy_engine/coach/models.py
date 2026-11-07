"""The CoachDecision contract: what the desktop overlay and the Today screen consume."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Action = Literal["silent", "nudge", "annotate", "takeover_offer"]
Outcome = Literal["followed", "dismissed", "repeated", "undone"]
OUTCOMES = ("followed", "dismissed", "repeated", "undone")


@dataclass
class CoachDecision:
    person: str
    t: str                                   # ISO time the decision was made for
    action: Action = "silent"
    message: str = ""                        # plain language, one line unless the worker chose detailed
    why: str = ""                            # one sentence the worker can open: what the expert does
    target: dict | None = None               # {zone, label_hint, role_hint, site?}: where the ring goes
    missed: list[str] = field(default_factory=list)   # step ids not done that something already started needed
    confidence: float = 0.0
    level: str = "L1"                        # help level from the level engine, "L1" full .. "L4" gone
    chip: str = "full"                       # full | small | dot | gone
    decision_id: str | None = None           # set only when the coach acted and the decision was recorded
    task_id: str | None = None
    step: str | None = None                  # the step the worker is on
    trigger: str | None = None               # expert_policy | stuck | ask | None
    reason_codes: list[str] = field(default_factory=list)
    gate: dict = field(default_factory=dict)     # {consecutive, reason}
    p_stuck: float | None = None
    p_source: str | None = None              # hazard | heuristic
    candidate: dict | None = None            # what the coach would say if the gate opened (for the Today screen)
    mastery: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
