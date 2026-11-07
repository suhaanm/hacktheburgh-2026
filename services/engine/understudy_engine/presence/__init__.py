"""Presence: the weekly map, the return-time hazard and the start-or-wait rule (ANA-12, OFF-1, OFF-3)."""
from .evaluate import evaluate_presence
from .model import PresenceModel, PriorHours, Smoothing, window_mask
from .survival import Decision, ReturnTimeModel, SurvivalConfig, SurvivalEstimate, decide, loss_for_cap, threshold
from .timeline import (
    ACTIVE, BINS, IDLE, OFF, SLOTS, DayObs, Spell, day_states_from_events, days_from_matrix, spells_from_events,
)

__all__ = [
    "evaluate_presence", "PresenceModel", "PriorHours", "Smoothing", "window_mask",
    "Decision", "ReturnTimeModel", "SurvivalConfig", "SurvivalEstimate", "decide", "loss_for_cap", "threshold",
    "ACTIVE", "BINS", "IDLE", "OFF", "SLOTS", "DayObs", "Spell", "day_states_from_events", "days_from_matrix",
    "spells_from_events",
]
