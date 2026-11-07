"""Schema-valid stub output for offline runs and test doubles (no model, no network, deterministic)."""
from __future__ import annotations

from typing import Any


def stub_from_schema(schema: dict[str, Any] | None, *, text: str = "stub wording") -> Any:
    """A minimal value that satisfies a JSON schema node. Strings become ``text`` (cut to ``maxLength``)."""
    if not schema:
        return {"text": text}
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if schema.get(key):
            for sub in schema[key]:
                if sub.get("type") != "null":
                    return stub_from_schema(sub, text=text)
            return None
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0] if t else None)
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        req = schema.get("required")
        names = list(props) if req is None else [k for k in props if k in req]
        return {k: stub_from_schema(props[k], text=text) for k in names}
    if t == "array":
        n = int(schema.get("minItems", 0))
        return [stub_from_schema(schema.get("items", {}), text=text) for _ in range(n)]
    if t == "integer":
        return int(schema.get("minimum", 0))
    if t == "number":
        return float(schema.get("minimum", 0))
    if t == "boolean":
        return False
    if t == "null":
        return None
    out = text
    ml = schema.get("maxLength")
    if isinstance(ml, int) and ml >= 0:
        out = out[:ml]
    mn = schema.get("minLength")
    if isinstance(mn, int) and len(out) < mn:
        out = out + "x" * (mn - len(out))
    return out


class BuiltinMockPort:
    """Used only when ``UNDERSTUDY_MOCK`` is on and the agent package (and its mock provider) is not importable."""

    name = "mock"
    offline = True

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return stub_from_schema(schema)

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return stub_from_schema(schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return stub_from_schema(schema)
