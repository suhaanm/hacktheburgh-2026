"""Closed response schemas for the pointing and glance capabilities.

"Closed" means every string field is an enum: nothing the model says can carry free text out of, or back into, the system. This
is also what the privacy track's `egress.send_image` will enforce when a purpose is registered, so the shapes here are the ones
to register. The AWARENESS track may move the enums into `packages/schema/` later; until then they live here and the lead
knows (see the DONE report).

* `POINT_SCHEMA`  -> `PointResult` : found, box_2d [ymin, xmin, ymax, xmax] in 0..1000 (the Gemini convention), confidence 0..1.
* `GLANCE_SCHEMA` -> `GlanceResult`: app_kind, task_phase, blocker (enums), confidence, box_2d (all-zero when there is none).

Deterministic code, not the model, decides what a box is worth: `parse_point` rejects degenerate and oversize boxes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .errors import SchemaViolation

BoxYXYX = tuple[int, int, int, int]  # [ymin, xmin, ymax, xmax], 0..1000, origin top-left

APP_KINDS = ("browser", "editor_or_ide", "terminal", "spreadsheet", "document", "email", "chat", "calendar",
             "file_manager", "video_call", "settings", "other", "unknown")
TASK_PHASES = ("starting", "entering_data", "reviewing_result", "waiting", "error_state", "finished", "unknown")
BLOCKERS = ("none", "error_message", "validation_error", "login_or_verification", "loading", "dialog_or_popup",
            "unclear_next_step", "unknown")

MAX_BOX_AREA_FRACTION = 0.5   # a box over half the screen is "did not really find it" (same rule as the old project)
MIN_BOX_SIDE = 3              # normalised units (about 4 px on a 1280-wide screen)

POINT_SCHEMA: dict[str, Any] = {
    "title": "PointResult",
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
        "confidence": {"type": "number"},
    },
    "required": ["found", "box_2d", "confidence"],
}

GLANCE_SCHEMA: dict[str, Any] = {
    "title": "GlanceResult",
    "type": "object",
    "properties": {
        "app_kind": {"type": "string", "enum": list(APP_KINDS)},
        "task_phase": {"type": "string", "enum": list(TASK_PHASES)},
        "blocker": {"type": "string", "enum": list(BLOCKERS)},
        "confidence": {"type": "number"},
        "box_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
    },
    "required": ["app_kind", "task_phase", "blocker", "confidence", "box_2d"],
}

# A yes/no screen check (the independent verifier). One boolean and a confidence: no text.
VERIFY_SCHEMA: dict[str, Any] = {
    "title": "ScreenCheck",
    "type": "object",
    "properties": {"holds": {"type": "boolean"}, "confidence": {"type": "number"}},
    "required": ["holds", "confidence"],
}

PointReason = Literal["ok", "model_not_found", "no_box", "degenerate_box", "oversize_box", "timeout", "unavailable", "error"]


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
    """Validate and normalise a model box. All-zero means 'none'. Swapped corners are tolerated, never invented."""
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


def parse_glance(raw: dict[str, Any]) -> GlanceResult:
    if not isinstance(raw, dict):
        raise SchemaViolation("glance result must be an object")
    for key, allowed in (("app_kind", APP_KINDS), ("task_phase", TASK_PHASES), ("blocker", BLOCKERS)):
        if raw.get(key) not in allowed:
            raise SchemaViolation(f"glance field {key!r} is not one of the allowed values")
    box = _box(raw.get("box_2d"))
    if box is not None and box_problem(box):
        box = None
    return GlanceResult(app_kind=raw["app_kind"], task_phase=raw["task_phase"], blocker=raw["blocker"],
                        confidence=_conf(raw.get("confidence", 0.0)), box_2d=box)


def is_closed(schema: dict[str, Any]) -> bool:
    """True when no string in the schema is free text (every string has an enum). Used by tests and, later, by the egress guard."""
    def walk(node: Any) -> bool:
        if not isinstance(node, dict):
            return True
        t = node.get("type")
        types = t if isinstance(t, list) else [t]
        if "string" in types and "enum" not in node:
            return False
        for key in ("properties", "$defs", "definitions"):
            if isinstance(node.get(key), dict) and not all(walk(v) for v in node[key].values()):
                return False
        for key in ("items", "not"):
            if key in node and not walk(node[key]):
                return False
        for key in ("anyOf", "oneOf", "allOf"):
            if key in node and not all(walk(v) for v in node[key]):
                return False
        return True

    return walk(schema)
