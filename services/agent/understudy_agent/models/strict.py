"""JSON-schema helpers for OpenAI structured outputs (strict mode) plus output validation.

Strict mode needs every property listed in `required` and `additionalProperties: false`. Callers write
natural schemas (optional fields, no additionalProperties); `to_strict_schema` converts them and
`validate_output` checks the result against the caller's ORIGINAL schema, dropping nulls that only exist
because we made an optional field required.
"""
from __future__ import annotations

import copy
from typing import Any

import jsonschema

from .errors import SchemaViolation

_UNSUPPORTED_KEYS = {"default", "examples", "$schema", "$id", "minLength", "maxLength", "pattern", "format",
                     "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems",
                     "uniqueItems", "multipleOf"}


def _nullable(sub: dict[str, Any]) -> dict[str, Any]:
    t = sub.get("type")
    if isinstance(t, str):
        sub["type"] = [t, "null"] if t != "null" else "null"
    elif isinstance(t, list):
        if "null" not in t:
            sub["type"] = [*t, "null"]
    elif "enum" in sub:
        if None not in sub["enum"]:
            sub["enum"] = [*sub["enum"], None]
    elif "anyOf" in sub:
        if not any(s.get("type") == "null" for s in sub["anyOf"]):
            sub["anyOf"] = [*sub["anyOf"], {"type": "null"}]
    return sub


def to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy that satisfies OpenAI strict structured outputs."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        node = {k: v for k, v in node.items() if k not in _UNSUPPORTED_KEYS}
        for key in ("properties", "$defs", "definitions"):
            if key in node and isinstance(node[key], dict):
                node[key] = {k: walk(v) for k, v in node[key].items()}
        for key in ("items", "anyOf", "oneOf", "allOf", "not"):
            if key in node:
                node[key] = walk(node[key])
        if node.get("type") == "object" or "properties" in node:
            props = node.get("properties", {})
            req = set(node.get("required", []))
            for name, sub in props.items():
                if name not in req:
                    props[name] = _nullable(sub)
            node["properties"] = props
            node["required"] = list(props.keys())
            node["additionalProperties"] = False
            node.setdefault("type", "object")
        return node

    return walk(copy.deepcopy(schema))


def _drop_optional_nulls(obj: Any, schema: dict[str, Any]) -> Any:
    if isinstance(obj, dict) and isinstance(schema, dict) and "properties" in schema:
        req = set(schema.get("required", []))
        out = {}
        for k, v in obj.items():
            sub = schema["properties"].get(k, {})
            if v is None and k not in req:
                continue
            out[k] = _drop_optional_nulls(v, sub)
        return out
    if isinstance(obj, list) and isinstance(schema, dict) and "items" in schema:
        return [_drop_optional_nulls(v, schema["items"]) for v in obj]
    return obj


def validate_output(obj: Any, schema: dict[str, Any]) -> Any:
    """Validate against the caller's schema; return the cleaned object or raise SchemaViolation."""
    cleaned = _drop_optional_nulls(obj, schema)
    try:
        jsonschema.validate(cleaned, schema)
    except jsonschema.ValidationError as e:  # pragma: no cover - message formatting
        raise SchemaViolation(f"model output does not match schema: {e.message[:200]}") from e
    return cleaned


def schema_name(schema: dict[str, Any], default: str = "result") -> str:
    raw = str(schema.get("title") or default)
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in raw)[:60]
    return cleaned or default
