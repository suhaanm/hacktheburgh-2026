"""The grounding port (CUE-2): the interface Cue uses for "where on the screen is this step", a fake for tests and simulation, and the
box sanity checks.

The real grounding call is a route on the agent service (``POST /cue/ground``: a frame plus a candidate menu in, a closed answer out),
or the desktop's DOM grounding in a browser. Neither runs in this package: Cue never sees a frame. It receives only the RESULT, as a
``types.Grounding`` (enums, step ids, a box, a confidence), through ``grounding_from_result`` which applies the sanity checks.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from .types import Grounding

MIN_SIDE = 12            # box side in 0..1000 units
MAX_AREA = 0.5           # share of the screen
DENIED_OVERLAP = 0.2     # a box overlapping a denied region by more than this share of its area is refused


def box_ok(box: Sequence[int] | None, denied: Sequence[Sequence[int]] = ()) -> bool:
    """[y0, x0, y1, x1] on 0..1000: well formed, on the screen, not tiny, not most of the screen, not over a denied region."""
    if box is None or len(box) != 4:
        return False
    y0, x0, y1, x1 = (float(v) for v in box)
    if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
        return False
    if (y1 - y0) < MIN_SIDE or (x1 - x0) < MIN_SIDE or (y1 - y0) * (x1 - x0) > MAX_AREA * 1000 * 1000:
        return False
    area = (y1 - y0) * (x1 - x0)
    for d in denied:
        dy0, dx0, dy1, dx1 = (float(v) for v in d)
        oy = max(0.0, min(y1, dy1) - max(y0, dy0))
        ox = max(0.0, min(x1, dx1) - max(x0, dx0))
        if oy * ox > DENIED_OVERLAP * area:
            return False
    return True


def grounding_from_result(raw: dict, *, for_step: str | None, denied: Sequence[Sequence[int]] = (), t: float | None = None) -> Grounding:
    """Parse a grounding answer strictly. A box that fails the sanity checks is dropped and the answer becomes "not found"
    (a ring on a wrong place costs more than a text-only cue). Unknown fields are ignored; nothing else is kept."""
    source = raw.get("source") if raw.get("source") in ("dom", "vision") else "none"
    box = raw.get("box_2d")
    try:
        box_t = tuple(int(v) for v in box) if box else None
    except (TypeError, ValueError):
        box_t = None
    found = bool(raw.get("chosen")) and bool(raw.get("found", True))
    if box_t is not None and not box_ok(box_t, denied):
        box_t, found = None, False
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0
    avail = tuple(str(x) for x in (raw.get("available") or []))[:6]
    return Grounding(found=found, chosen=str(raw["chosen"]) if found else None, available=avail, box_2d=box_t, confidence=conf, source=source,
                     for_step=for_step, t=t)


class GroundingPort(Protocol):
    def ground(self, *, menu: Sequence[tuple[str, str]], truth: str | None, for_step: str | None, t: float) -> Grounding: ...


def box_of(step_id: str) -> tuple[int, int, int, int]:
    """A fixed, valid box per step id for fakes."""
    h = int(hashlib.sha1(step_id.encode()).hexdigest()[:8], 16)
    y0, x0 = 80 + h % 600, 60 + (h >> 8) % 600
    return (y0, x0, y0 + 70, x0 + 260)


class FakeGrounding:
    """A grounding port that is RIGHT at a configurable rate. ``truth`` is the menu id that really is on the screen (or None when none
    of the menu is). Right: finds it (or, when it is not on screen, says nothing is found). Wrong: half the time "not found" with low
    confidence, half the time confidently a different menu entry."""

    def __init__(self, accuracy: float = 0.9, seed: int = 0, conf_right: float = 0.9, conf_wrong: float = 0.85, source: str = "vision") -> None:
        if not 0.0 <= accuracy <= 1.0:
            raise ValueError("accuracy must be between 0 and 1")
        self.accuracy, self.conf_right, self.conf_wrong, self.source = accuracy, conf_right, conf_wrong, source
        self.rng = np.random.default_rng(seed)
        self.calls = 0

    def ground(self, *, menu: Sequence[tuple[str, str]], truth: str | None, for_step: str | None, t: float) -> Grounding:
        self.calls += 1
        ids = [m[0] for m in menu]
        u = float(self.rng.random())
        right = u < self.accuracy
        if truth is not None and truth in ids:
            if right:
                return Grounding(True, truth, (truth,), box_of(truth), self.conf_right, self.source, for_step, t)
            if u < self.accuracy + (1.0 - self.accuracy) / 2.0:
                return Grounding(False, None, (), None, 0.3, self.source, for_step, t)
            others = [i for i in ids if i != truth] or [truth]
            wrong = others[int(self.rng.integers(0, len(others)))]
            return Grounding(True, wrong, (wrong,), box_of(wrong), self.conf_wrong, self.source, for_step, t)
        if right:
            return Grounding(False, None, (), None, 0.3, self.source, for_step, t)
        wrong = ids[int(self.rng.integers(0, len(ids)))] if ids else None
        if wrong is None:
            return Grounding(False, None, (), None, 0.3, self.source, for_step, t)
        return Grounding(True, wrong, (wrong,), box_of(wrong), self.conf_wrong, self.source, for_step, t)
