"""Which fields the local model decides and which stay with the rules (decided by evidence, not by hope).

The evaluation compares the model against the rules field by field on a DEV split (the split the prompts were tuned on). A field
is given to the model only if it beat the rules there; otherwise the rules keep it and the model is not even asked (a smaller
schema is also faster). Fields that are pure functions of the input (size, tests touched, duration, attendees, recurrence) are
always computed by code. The choice is frozen here with the numbers behind it; ``evaluate_localmodel`` reports the held-out
result of the policy as shipped, next to the model-for-everything run.
"""
from __future__ import annotations

# "model" = ask the local model (when available); "rules" = the deterministic rules decide.
FIELD_SOURCE: dict[str, dict[str, str]] = {
    "commit_digest": {"category": "model", "risk": "model", "message_quality": "model"},
    "event_digest": {"category": "model", "needs_prep": "model"},
}
ALL_MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "commit_digest": ("category", "risk", "message_quality"),
    "event_digest": ("category", "needs_prep"),
}


def model_fields(task: str) -> tuple[str, ...]:
    src = FIELD_SOURCE[task]
    return tuple(k for k in ALL_MODEL_FIELDS[task] if src.get(k) == "model")
