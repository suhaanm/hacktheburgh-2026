"""Privacy coverage for the Cue package (PRV-1): there is no model path here to measure.

Cue never builds a model request and never sees a frame. The grounding call is a route on the agent service
(``POST /cue/ground``: frame plus a candidate menu in, a closed answer out); it goes through the privacy spine there. Cue receives only
the RESULT as enums, step ids from the pack's vocabulary, a box and a confidence (``types.Grounding``). Every string that can reach
the ledger is checked against the ledger schema's patterns at write time, and the static guard scans this package for model clients,
sockets and ``ModelPort``.
"""
from __future__ import annotations

NOT_APPLICABLE = ("no model path: Cue sends nothing to any model and never receives a screen frame; grounding results arrive as "
                  "enums, pack step ids, a box and a confidence from the agent route, and the ledger schema refuses any string "
                  "that is not a pattern-matched id")
FLOWS: list = []
