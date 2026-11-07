"""Reference cog mapper for pack mapping.yaml files.

Not the engine's mapper. It exists so the pack's test vectors (mapping.yaml `examples`) are checked
for self-consistency, and so the engine's `cogs/` module has a small executable statement of the rule
semantics documented in packages/schema/pack.schema.json#/$defs/mapping.
"""
from __future__ import annotations

from typing import Any


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else [v]


def _meta_ok(test: Any, value: Any) -> bool:
    if not isinstance(test, dict):
        return value == test
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return (
        ("gte" not in test or value >= test["gte"])
        and ("lte" not in test or value <= test["lte"])
        and ("gt" not in test or value > test["gt"])
        and ("lt" not in test or value < test["lt"])
    )


def rule_matches(when: dict, ev: dict, prev_type: str | None, prev_cog: str | None,
                 has_prev: bool, tables: dict) -> bool:
    target = ev.get("target") or {}
    meta = ev.get("meta") or {}
    for key, want in when.items():
        if key == "type":
            if ev["type"] not in _as_list(want):
                return False
        elif key == "actor":
            if ev.get("actor", "human") != want:
                return False
        elif key == "target_role":
            if target.get("role") not in _as_list(want):
                return False
        elif key == "domain_role":
            hashes = {h for r in _as_list(want) for h in tables["domain"].get(r, [])}
            if target.get("domain_hash") not in hashes:
                return False
        elif key == "label_role":
            hashes = {h for r in _as_list(want) for h in tables["label"].get(r, [])}
            if target.get("label_hash") not in hashes:
                return False
        elif key == "meta":
            if not all(k in meta and _meta_ok(t, meta[k]) for k, t in want.items()):
                return False
        elif key == "prev_cog":
            if prev_cog not in _as_list(want):
                return False
        elif key == "not_prev_cog":
            if prev_cog in _as_list(want):
                return False
        elif key == "prev_type":
            if prev_type not in _as_list(want):
                return False
        elif key == "within_s":
            if not has_prev or ev["dt"] > want:
                return False
        else:
            raise ValueError(f"unknown predicate {key!r}")
    return True


def map_events(mapping: dict, events: list[dict], hash_roles: dict) -> list[str | None]:
    """Return one cog id (or None when ignored) per event. `dt` is seconds since the previous event."""
    tables = {"domain": hash_roles.get("domain", {}), "label": hash_roles.get("label", {})}
    rules = list(mapping.get("role_rules", [])) + list(mapping["base_rules"])
    out: list[str | None] = []
    prev_type: str | None = None
    prev_cog: str | None = None
    for i, ev in enumerate(events):
        cog: str | None = None
        for rule in rules:
            if rule_matches(rule["when"], ev, prev_type, prev_cog, i > 0, tables):
                cog = None if rule.get("ignore") else rule["cog"]
                break
        out.append(cog)
        if cog is not None:
            prev_cog = cog
        prev_type = ev["type"]
    return out
