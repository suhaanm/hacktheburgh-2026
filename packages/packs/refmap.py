"""Reference cog mapper for pack mapping.yaml files (engine default_mapping.yaml format).

Not the engine's mapper (that is services/engine/understudy_engine/cogs). It exists so a pack's test
vectors (mapping.yaml `examples`) are checked for self-consistency by the standalone validator.
Per event it answers: which cog (or None when the event carries no cog). Timing (follow_s, idle gaps,
backdate_meta) is the engine's business; here only rule matching, reformulate_as and skip are executed.
"""
from __future__ import annotations

from typing import Any


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else [v]


def rule_matches(match: dict, ev: dict) -> bool:
    meta = ev.get("meta") or {}
    for key, want in match.items():
        if key == "type":
            got = ev["type"]
        elif key == "zone":
            got = meta.get("zone")
        elif key == "role":
            got = ev.get("role")
        elif key == "source":
            got = ev.get("source", "browser")
        else:
            raise ValueError(f"unknown match key {key!r}")
        if got not in _as_list(want):
            return False
    return True


def map_events(mapping: dict, events: list[dict]) -> list[str | None]:
    """One cog id (or None) per event. `dt` is seconds since the previous event."""
    reform_within = mapping["params"]["reformulate_within_s"]
    out: list[str | None] = []
    clock = 0.0
    prev_cog: str | None = None
    prev_t = 0.0
    for ev in events:
        clock += ev["dt"]
        cog: str | None = None
        for rule in mapping["rules"]:
            if rule_matches(rule["match"], ev):
                cog = rule["cog"]
                if cog and "reformulate_as" in rule:
                    if prev_cog in ("SEARCH", "REFORMULATE") and clock - prev_t <= reform_within:
                        cog = rule["reformulate_as"]
                break
        out.append(cog)
        if cog is not None:
            prev_cog, prev_t = cog, clock
    return out


def merge(cogs: list[str | None]) -> list[str]:
    """Collapse skipped events and consecutive repeats into the segment sequence."""
    seq: list[str] = []
    for c in cogs:
        if c is not None and (not seq or seq[-1] != c):
            seq.append(c)
    return seq
