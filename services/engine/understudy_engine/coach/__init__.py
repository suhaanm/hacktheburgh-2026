"""The live coach brain (COA-3, COA-4): events in, one decision out. See brain.py."""
from .brain import GATE, CoachBrain, CoachError
from .messages import short_label, target_for
from .models import OUTCOMES, CoachDecision
from .signals import StuckScorer
from .steps import Progress, Step, StepPolicy

__all__ = ["CoachBrain", "CoachDecision", "CoachError", "GATE", "OUTCOMES", "Progress", "Step", "StepPolicy", "StuckScorer", "short_label", "target_for"]
