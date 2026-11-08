"""HRT track (predictions and decisions): a prospective prediction ledger, a guard that notices when a model stops being better than a naive
predictor, and a decisions scoreboard (realised cost against naive and oracle policies).

Pre-registration: ``evals/hrt/PLAN.md`` (committed before any held-out run). Everything here is deterministic code; no model is called.
Importing this package is cheap: the heavy modules (worlds, prospective, scoreboard) are imported where they are used.
"""
from __future__ import annotations

__all__ = ["LEDGER_FILE"]

LEDGER_FILE = "predictions.jsonl"
