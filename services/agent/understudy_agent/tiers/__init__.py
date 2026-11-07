"""The three execution tiers (AGT-3): 1 compiled JSON step DSL, 2 browser agent, 3 computer use.

Cheapest first; escalate only when a precondition fails; every step logs its tier.
"""
from .base import (
    ActionRejected, Element, GateStop, InjectionStop, Observation, PostconditionFailed,
    PreconditionFailed, StepBudgetExceeded, StepEvent, StuckDetector, StuckLoop, TierError,
)

__all__ = [
    "ActionRejected", "Element", "GateStop", "InjectionStop", "Observation", "PostconditionFailed",
    "PreconditionFailed", "StepBudgetExceeded", "StepEvent", "StuckDetector", "StuckLoop", "TierError",
]
