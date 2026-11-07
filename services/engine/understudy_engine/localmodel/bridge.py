"""From digests to the privacy layer's ``digest.meta`` payload: counts and minutes per fixed category, nothing else.

Pure functions, no I/O, no privacy import (the payload is a plain dict that ``egress.send("digest.meta", ...)`` accepts and
re-validates). The commit and calendar vocabularies are mapped onto the privacy layer's ``digest.category`` vocabulary
(feature, bugfix, refactor, test, docs, chore, revert, meeting, focus, admin, review, other).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

COMMIT_TO_META = {"feature": "feature", "fix": "bugfix", "refactor": "refactor", "test": "test", "docs": "docs", "chore": "chore",
                  "revert": "revert", "other": "other"}
EVENT_TO_META = {"one_to_one": "meeting", "team_meeting": "meeting", "external": "meeting", "review": "review", "focus": "focus",
                 "admin": "admin", "social": "other", "travel": "other", "unknown": "other"}
# a representative length for each duration bucket, in minutes (an all-day entry counts as one working day)
BUCKET_MINUTES = {"lt30": 15, "30to59": 45, "60to89": 75, "90to179": 120, "180plus": 240, "allday": 480}


def meta_payload(kind: str, digests: Sequence[dict[str, Any]], window_days: int = 7) -> dict[str, Any]:
    """``kind`` is ``"commit"`` or ``"event"``. Returns ``{kind, window_days, counts, minutes}`` ready for ``digest.meta``."""
    if kind == "commit":
        counts = Counter(COMMIT_TO_META[d["category"]] for d in digests)
        return {"kind": "commit", "window_days": window_days, "counts": dict(counts), "minutes": {}}
    if kind == "event":
        counts: Counter[str] = Counter()
        minutes: Counter[str] = Counter()
        for d in digests:
            cat = EVENT_TO_META[d["category"]]
            counts[cat] += 1
            minutes[cat] += BUCKET_MINUTES[d["duration_bucket"]]
        return {"kind": "event", "window_days": window_days, "counts": dict(counts), "minutes": dict(minutes)}
    raise ValueError("kind is 'commit' or 'event'")
