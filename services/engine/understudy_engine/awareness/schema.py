"""The awareness schema and what is read from it. ``packages/schema/awareness.schema.json`` is the single source of truth: the enums
here, the desktop app's TypeScript enums (a test compares them), the glance model's closed answer and the store's validation all
come from or agree with that file.

Validation reasons never contain a value from the event (a value could be anything an untrusted client sent): they name the rule and
the path only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import jsonschema

from .paths import schema_path

_ZONE_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    return json.loads(schema_path().read_text(encoding="utf-8"))


def _defs() -> dict[str, Any]:
    return schema()["$defs"]


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema())


def _enum(name: str) -> tuple[str, ...]:
    return tuple(_defs()[name]["enum"])


APP_KINDS = _enum("AppKind")
APP_KINDS_OR_UNKNOWN = _enum("AppKindOrUnknown")
TASK_PHASES = _enum("TaskPhase")
BLOCKERS = _enum("Blocker")
TRIGGER_REASONS = _enum("TriggerReason")
# Blockers that mean "nothing visible in the way" (or the model could not tell): not evidence of a block.
NO_BLOCK = ("none", "unknown")


def glance_response_schema() -> dict[str, Any]:
    """The closed JSON schema the glance model must answer in (every string is an enum), as ``egress.register_image_purpose`` wants it.
    ``null`` is not offered to the model: when unsure it answers ``other``, ``unknown`` or lowers its confidence."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "app_kind": {"enum": list(APP_KINDS)},
            "task_phase": {"enum": list(TASK_PHASES)},
            "blocker": {"enum": list(BLOCKERS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "box_2d": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1000}, "minItems": 4, "maxItems": 4},
        },
        "required": ["app_kind", "task_phase", "blocker", "confidence"],
    }


def parse_time(value: str) -> float:
    """ISO-8601 to unix seconds (UTC). Raises ValueError."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def problem(event: Any) -> str | None:
    """Why this event is not valid, or None. The reason names a rule and a path, never a value."""
    if not isinstance(event, dict):
        return "not an object"
    errors = sorted(_validator().iter_errors(event), key=lambda e: (len(list(e.absolute_path)), e.validator))
    if errors:
        e = errors[0]
        path = ".".join(str(p) for p in e.absolute_path) or "$"
        return f"{e.validator} at {path}"
    try:
        parse_time(event["t"])
    except (ValueError, KeyError, TypeError):
        return "format at t"
    cursor = event.get("cursor")
    if isinstance(cursor, dict):  # belt and braces for the zone pattern on nullable fields
        for k in ("dwell_zone", "zone_a", "zone_b"):
            v = cursor.get(k)
            if v is not None and not (isinstance(v, str) and _ZONE_RE.match(v)):
                return f"pattern at cursor.{k}"
    return None


def is_valid(event: Any) -> bool:
    return problem(event) is None
