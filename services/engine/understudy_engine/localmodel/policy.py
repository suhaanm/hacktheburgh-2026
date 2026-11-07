"""Which fields the local model decides and which stay with the rules (decided by evidence, not by hope).

The evaluation compares the model against the rules field by field on a DEV split (the split the prompts were tuned on). A field
is given to the model only if it beat the rules there; otherwise the rules keep it and the model is not even asked (a smaller
schema is also faster). Fields that are pure functions of the input (size, tests touched, duration, attendees, recurrence) are
always computed by code. The choice is frozen here with the numbers behind it; ``evaluate_localmodel`` reports the held-out
result of the policy as shipped, next to the model-for-everything run.
"""
from __future__ import annotations

# "model" = ask the local model (when available); "rules" = the deterministic rules decide.
# Frozen after the dev-split comparison of prompt v3 (n = 52 per task; model correct versus rules correct):
#   commits: category 44 vs 39 (model), risk 43 vs 45 (rules), message_quality 44 vs 51 (rules)
#   events:  category 48 vs 41 (model), needs_prep 45 vs 41 (model)
# Revised ONCE after the held-out run (n = 98 per task): events needs_prep went to the rules, because on the held-out split the model was
# nominally worse (81 vs 86 correct, no clear difference) and the rules are exact, free and instant. Every other dev choice was confirmed
# (category: model better on both tasks, +14 points, paired interval above zero; risk and message quality: no clear difference, rules
# nominally better). The held-out numbers of the model-for-everything run stay the clean evidence; those of this revised policy are not
# strictly held-out for needs_prep, and the report says so.
FIELD_SOURCE: dict[str, dict[str, str]] = {
    "commit_digest": {"category": "model", "risk": "rules", "message_quality": "rules"},
    "event_digest": {"category": "model", "needs_prep": "rules"},
}
ALL_MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "commit_digest": ("category", "risk", "message_quality"),
    "event_digest": ("category", "needs_prep"),
}


def model_fields(task: str) -> tuple[str, ...]:
    src = FIELD_SOURCE[task]
    return tuple(k for k in ALL_MODEL_FIELDS[task] if src.get(k) == "model")
