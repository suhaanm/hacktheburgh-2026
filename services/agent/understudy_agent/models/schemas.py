"""Closed response schemas for pointing, glances and screen checks, and the code that parses a model's answer.

The schemas are the privacy track's (`understudy_engine.privacy.purposes`: GLANCE_RESPONSE, POINT_RESPONSE, VERIFY_RESPONSE): one
source of truth, so what the bake-off measures is exactly what `egress.send_image` will enforce. They are CLOSED: every string is an
enum, so nothing read off a screen can come back as text. `closed_problem()` re-checks that with the privacy track's own checker.

* point.element       -> `PointResult`: found, confidence 0..1, box_2d [ymin, xmin, ymax, xmax] in 0..1000 (the Gemini convention;
                         optional when not found).
* glance.screen_state -> `GlanceResult`: app_kind, task_phase, blocker (enums), confidence, optional box_2d.
* verify.agent_run    -> a verdict dict {verdict: yes|no|unsure, confidence}.

Deterministic code, not the model, decides what a box is worth: `parse_point` rejects degenerate and oversize boxes. The AWARENESS
track may move the enums into `packages/schema/`; until then they live in the privacy purposes (the lead knows).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Literal

from understudy_engine.privacy.image import closed_schema_problem
from understudy_engine.privacy.purposes import GLANCE_RESPONSE, POINT_RESPONSE, VERIFY_RESPONSE

from .errors import SchemaViolation

BoxYXYX = tuple[int, int, int, int]  # [ymin, xmin, ymax, xmax], 0..1000, origin top-left

POINT_SCHEMA: dict[str, Any] = copy.deepcopy(POINT_RESPONSE)
GLANCE_SCHEMA: dict[str, Any] = copy.deepcopy(GLANCE_RESPONSE)
VERIFY_SCHEMA: dict[str, Any] = copy.deepcopy(VERIFY_RESPONSE)

APP_KINDS = tuple(GLANCE_SCHEMA["properties"]["app_kind"]["enum"])
TASK_PHASES = tuple(GLANCE_SCHEMA["properties"]["task_phase"]["enum"])
BLOCKERS = tuple(GLANCE_SCHEMA["properties"]["blocker"]["enum"])
VERDICTS = tuple(VERIFY_SCHEMA["properties"]["verdict"]["enum"])

MAX_BOX_AREA_FRACTION = 0.5   # a box over half the screen is "did not really find it" (same rule as the old project)
MIN_BOX_SIDE = 3              # normalised units (about 4 px on a 1280-wide screen)

PointReason = Literal["ok", "model_not_found", "no_box", "degenerate_box", "oversize_box", "timeout", "unavailable", "error"]


def closed_problem(schema: dict[str, Any]) -> str | None:
    """Why a schema could let free text come back, or None (the privacy track's checker)."""
    return closed_schema_problem(schema)


@dataclass(frozen=True)
class PointResult:
    found: bool
    box_2d: BoxYXYX | None
    confidence: float
    reason: PointReason = "ok"   # decided by code, not by the model (the last three are set by the router)

    def center_xy(self) -> tuple[float, float] | None:
        """Normalised (x, y) of the box centre, 0..1000."""
        if self.box_2d is None:
            return None
        ymin, xmin, ymax, xmax = self.box_2d
        return (xmin + xmax) / 2.0, (ymin + ymax) / 2.0

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int] | None:
        """(x0, y0, x1, y1) in pixels of an image of the given size."""
        if self.box_2d is None:
            return None
        ymin, xmin, ymax, xmax = self.box_2d
        return (round(xmin / 1000 * width), round(ymin / 1000 * height),
                round(xmax / 1000 * width), round(ymax / 1000 * height))

    def as_dict(self) -> dict[str, Any]:
        return {"found": self.found, "box_2d": list(self.box_2d) if self.box_2d else None,
                "confidence": self.confidence, "reason": self.reason}


@dataclass(frozen=True)
class GlanceResult:
    app_kind: str
    task_phase: str
    blocker: str
    confidence: float
    box_2d: BoxYXYX | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"app_kind": self.app_kind, "task_phase": self.task_phase, "blocker": self.blocker,
                "confidence": self.confidence, "box_2d": list(self.box_2d) if self.box_2d else None}


def _clamp(n: float) -> int:
    return int(max(0, min(1000, round(n))))


def _box(raw: Any) -> BoxYXYX | None:
    """Validate and normalise a model box. All-zero or missing means 'none'. Swapped corners are tolerated, never invented."""
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw):
        raise SchemaViolation("box_2d must be four numbers")
    ymin, xmin, ymax, xmax = (float(v) for v in raw)
    if ymin == xmin == ymax == xmax == 0:
        return None
    return (_clamp(min(ymin, ymax)), _clamp(min(xmin, xmax)), _clamp(max(ymin, ymax)), _clamp(max(xmin, xmax)))


def box_problem(b: BoxYXYX) -> Literal["degenerate_box", "oversize_box"] | None:
    ymin, xmin, ymax, xmax = b
    h, w = ymax - ymin, xmax - xmin
    if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
        return "degenerate_box"
    if (w * h) / 1_000_000 > MAX_BOX_AREA_FRACTION:
        return "oversize_box"
    return None


def _conf(raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise SchemaViolation("confidence must be a number")
    return float(max(0.0, min(1.0, raw)))


def parse_point(raw: dict[str, Any]) -> PointResult:
    """Model output -> PointResult. A `found` answer with a missing, degenerate or oversize box becomes not-found with the reason
    (the model's confidence is kept so the escalation rule can still see it)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("found"), bool):
        raise SchemaViolation("point result needs a boolean 'found'")
    conf = _conf(raw.get("confidence", 0.0))
    box = _box(raw.get("box_2d"))
    if not raw["found"]:
        return PointResult(found=False, box_2d=None, confidence=conf, reason="model_not_found")
    if box is None:
        return PointResult(found=False, box_2d=None, confidence=conf, reason="no_box")
    problem = box_problem(box)
    if problem:
        return PointResult(found=False, box_2d=None, confidence=conf, reason=problem)
    return PointResult(found=True, box_2d=box, confidence=conf, reason="ok")


def parse_glance(raw: dict[str, Any], *, check_enums: bool = True) -> GlanceResult:
    """`check_enums=False` when the answer already passed a closed schema that has other enum values (the AWARENESS glance)."""
    if not isinstance(raw, dict):
        raise SchemaViolation("glance result must be an object")
    for key, allowed in (("app_kind", APP_KINDS), ("task_phase", TASK_PHASES), ("blocker", BLOCKERS)):
        if not isinstance(raw.get(key), str) or (check_enums and raw.get(key) not in allowed):
            raise SchemaViolation(f"glance field {key!r} is not one of the allowed values")
    box = _box(raw.get("box_2d"))
    if box is not None and box_problem(box):
        box = None
    return GlanceResult(app_kind=raw["app_kind"], task_phase=raw["task_phase"], blocker=raw["blocker"],
                        confidence=_conf(raw.get("confidence", 0.0)), box_2d=box)


def parse_verify(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("verdict") not in VERDICTS:
        raise SchemaViolation("verify result needs a verdict of yes, no or unsure")
    return {"verdict": raw["verdict"], "confidence": _conf(raw.get("confidence", 0.0))}
