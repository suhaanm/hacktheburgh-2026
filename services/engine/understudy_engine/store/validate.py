"""Event validation: JSON Schema (compiled once) plus the pydantic ``core.Event`` model."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import orjson
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from pydantic import ValidationError

from ..core import Event
from .paths import schema_dir

_T_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


class InvalidEvent(ValueError):
    """Raised for a row that fails the schema or the model. ``str(e)`` is the plain reason."""


@lru_cache(maxsize=1)
def event_validator() -> Draft202012Validator:
    schema = orjson.loads((schema_dir() / "event.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def fmt_t(dt: datetime) -> str:
    """Canonical timestamp: UTC, millisecond precision, trailing Z."""
    if dt.tzinfo is None:
        raise InvalidEvent("t: timestamp has no timezone")
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def validate_row(raw: Any) -> Event:
    """Validate a raw dict against event.schema.json and core.Event. Raise InvalidEvent."""
    if isinstance(raw, Event):
        raw = to_row(raw)
    if not isinstance(raw, dict):
        raise InvalidEvent("event must be a JSON object")
    err = best_match(event_validator().iter_errors(raw))
    if err is not None:
        path = ".".join(str(p) for p in err.absolute_path)
        raise InvalidEvent(f"schema: {path + ': ' if path else ''}{err.message}"[:300])
    if not _T_RE.match(raw["t"]):
        raise InvalidEvent("schema: t: not an RFC 3339 date-time with timezone")
    try:
        return Event.model_validate(raw)
    except (ValidationError, ValueError) as exc:  # pragma: no cover - schema catches most
        raise InvalidEvent(f"model: {exc}"[:300]) from exc


def to_row(ev: Event) -> dict[str, Any]:
    """Canonical JSON-able dict (schema keys, canonical timestamp, no nulls)."""
    row: dict[str, Any] = {
        "schema": ev.schema_version,
        "id": ev.id,
        "t": fmt_t(ev.t),
        "origin": ev.origin,
        "actor": ev.actor,
        "person": ev.person,
        "role": ev.role,
        "source": ev.source,
        "type": ev.type,
    }
    if ev.target is not None:
        tgt = ev.target.model_dump(exclude_none=True)
        if tgt:
            row["target"] = tgt
    if ev.task_id is not None:
        row["task_id"] = ev.task_id
    if ev.meta:
        row["meta"] = dict(ev.meta)
    return row


def dumps_row(ev: Event) -> bytes:
    return orjson.dumps(to_row(ev), option=orjson.OPT_APPEND_NEWLINE)


def ts(ev: Event) -> float:
    return ev.t.timestamp()
