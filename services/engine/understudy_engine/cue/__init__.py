"""Cue, the stuck-rescue engine, and the assist ledger and independence score (CUE-1..9, GRO-1 data).

Flagged off by default: ``UNDERSTUDY_X_CUE=1`` or the master ``UNDERSTUDY_X=1`` (``enabled()``). Importing this package pulls in
nothing heavy; the maths lives in the modules (candidates, gate, question, ledger, score, teach, tierbandit, simulate, evaluate)
and the HTTP surface in ``routes``. No model client and no socket is opened anywhere in this package: Cue receives only the
RESULT of grounding (enums, ids, a box, a confidence) and never a frame.
"""
from .paths import FLAG, enabled

__all__ = ["enabled", "FLAG"]
