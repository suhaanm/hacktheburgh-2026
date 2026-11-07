"""Event -> cog mapper (ANA-1). Rule-based; the rules live in the pack (see default_mapping.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from ..core import BASE_COGS, Cog, Event

DEFAULT_MAPPING_PATH = Path(__file__).with_name("default_mapping.yaml")
DEFAULT_PARAMS = {"follow_s": 6.0, "gap_idle_s": 20.0, "reformulate_within_s": 90.0, "max_cog_s": 300.0}


def _as_set(v: Any) -> frozenset[str] | None:
    if v is None:
        return None
    return frozenset(v if isinstance(v, (list, tuple)) else [v])


@dataclass(frozen=True)
class Rule:
    types: frozenset[str] | None
    zones: frozenset[str] | None
    roles: frozenset[str] | None
    sources: frozenset[str] | None
    cog: str | None
    reformulate_as: str | None = None
    backdate_meta: str | None = None
    starts: bool = False

    def matches(self, ev: Event) -> bool:
        if self.types is not None and ev.type not in self.types:
            return False
        if self.zones is not None and ev.meta.get("zone") not in self.zones:
            return False
        if self.roles is not None and (ev.target is None or ev.target.role not in self.roles):
            return False
        if self.sources is not None and ev.source not in self.sources:
            return False
        return True


@dataclass(frozen=True)
class Mapping:
    rules: tuple[Rule, ...]
    params: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    extra_cogs: tuple[str, ...] = ()

    @property
    def cogs(self) -> tuple[str, ...]:
        return BASE_COGS + self.extra_cogs

    def classify(self, ev: Event) -> Rule | None:
        for r in self.rules:
            if r.matches(ev):
                return r
        return None


def compile_mapping(doc: dict) -> Mapping:
    if "rules" not in doc:
        raise ValueError("mapping needs a `rules` list (understudy mapping format v1)")
    rules = []
    for raw in doc["rules"]:
        m = raw.get("match", {})
        rules.append(Rule(
            types=_as_set(m.get("type")), zones=_as_set(m.get("zone")), roles=_as_set(m.get("role")),
            sources=_as_set(m.get("source")), cog=raw.get("cog"), reformulate_as=raw.get("reformulate_as"),
            backdate_meta=raw.get("backdate_meta"), starts=bool(raw.get("starts", False)),
        ))
    params = {**DEFAULT_PARAMS, **{k: float(v) for k, v in (doc.get("params") or {}).items()}}
    return Mapping(tuple(rules), params, tuple(doc.get("extra_cogs") or ()))


@lru_cache(maxsize=8)
def _load_path(path: str) -> Mapping:
    return compile_mapping(yaml.safe_load(Path(path).read_text()))


def load_mapping(source: Mapping | dict | str | Path | None = None) -> Mapping:
    """The built-in default, a compiled Mapping, a dict, or a path to a mapping.yaml."""
    if source is None:
        return _load_path(str(DEFAULT_MAPPING_PATH))
    if isinstance(source, Mapping):
        return source
    if isinstance(source, dict):
        return compile_mapping(source)
    return _load_path(str(Path(source)))


@dataclass
class _Run:
    cog: str
    start: float
    last: float


def to_cogs(events: Iterable[Event], pack_mapping: Mapping | dict | str | Path | None = None, *, t_end: float | None = None) -> list[Cog]:
    """Map one person's events (any order) to a cog sequence.

    Consecutive events with the same cog merge into one segment, unless the rule says ``starts``. A segment
    keeps going until the next one starts, or for ``follow_s`` after its last event when the silence is
    longer than ``gap_idle_s``; the silence becomes an IDLE segment. OS idle events start an IDLE segment
    ``meta.idle_s`` seconds in the past. ``t_end`` clips the last segment (a task_end, say).
    """
    mp = load_mapping(pack_mapping)
    p = mp.params
    evs = sorted(events, key=lambda e: (e.t, e.id))
    persons = {e.person for e in evs}
    if len(persons) > 1:
        raise ValueError(f"to_cogs takes one person's events, got {sorted(persons)}")

    runs: list[_Run] = []
    prev_search_t: float | None = None
    for ev in evs:
        rule = mp.classify(ev)
        if rule is None or rule.cog is None:
            continue
        t = ev.t.timestamp()
        cog = rule.cog
        start = t
        if rule.reformulate_as and prev_search_t is not None and t - prev_search_t <= p["reformulate_within_s"]:
            cog = rule.reformulate_as
        if ev.type == "search":
            prev_search_t = t
        if rule.backdate_meta:
            back = ev.meta.get(rule.backdate_meta)
            if isinstance(back, (int, float)):
                start = t - float(back)
        if runs and runs[-1].cog == cog and not rule.starts and start - runs[-1].last <= p["gap_idle_s"] + p["follow_s"]:
            runs[-1].last = max(runs[-1].last, t)
        else:
            runs.append(_Run(cog, start, t))

    cogs: list[Cog] = []
    for i, run in enumerate(runs):
        nxt = runs[i + 1] if i + 1 < len(runs) else None
        if run.cog == "IDLE":
            end = nxt.start if nxt is not None else run.last + p["follow_s"]
        elif nxt is not None and nxt.start - run.last <= p["gap_idle_s"]:
            end = nxt.start
        else:
            end = run.last + p["follow_s"]
        if nxt is not None:
            end = min(end, max(nxt.start, run.start))
        end = min(end, run.start + p["max_cog_s"])
        if t_end is not None:
            end = min(end, t_end)
        if end < run.start:
            continue
        # a silence between this segment and the next becomes IDLE (unless the next one is IDLE already)
        if nxt is not None and nxt.start - end > 0.5 and run.cog != "IDLE":
            if nxt.cog == "IDLE":
                nxt.start = min(nxt.start, end)
            else:
                gap_start = end
                cogs.append(Cog(run.start, end, run.cog))
                cogs.append(Cog(gap_start, nxt.start, "IDLE"))
                continue
        cogs.append(Cog(run.start, end, run.cog))
    # merge adjacent IDLE segments
    merged: list[Cog] = []
    for c in cogs:
        if merged and merged[-1].id == "IDLE" and c.id == "IDLE":
            merged[-1] = Cog(merged[-1].t0, max(merged[-1].t1, c.t1), "IDLE")
        else:
            merged.append(c)
    return [c for c in merged if c.t1 > c.t0 or c.id != "IDLE"]


def cog_labeler(pack_mapping: Mapping | dict | str | Path | None = None):
    """``Event -> cog id | None`` for replay counts (stateless: no sequence context)."""
    mp = load_mapping(pack_mapping)

    def label(ev: Event) -> str | None:
        rule = mp.classify(ev)
        if rule is None or rule.cog is None:
            return None
        return rule.cog

    return label
