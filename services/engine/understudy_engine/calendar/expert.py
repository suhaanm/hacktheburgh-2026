"""Expert weekly templates and the week-level gap analysis (CAL-2).

``routine_expert.yaml`` (one per role pack) holds the expert's weekly structure: batch windows, review slots, standing meetings,
off-screen blocks, plus the targets the suggestion catalogue compares a learner's week against. The template is hand-authored
from the planted synthetic design, not measured on real experts.

The gap analysis has two layers:

* **feature gap** (``gap_rows``): each week feature of the learner against the expert reference, with an interval from a
  cluster bootstrap over experts (the reference is the mean over the expert cohort when one exists, else the template);
* **week ribbon** (``ribbon_gap``): the learner's week and an expert week as sequences of labelled day segments
  (MEETING, FOCUS, SLIVER, BATCH, REVIEW, OFFSCREEN, with a zero-length DAY marker between days) aligned with the genome's
  Needleman-Wunsch (``understudy_engine.genome.align``), so a week is compared by structure, not just by totals. Its
  placebo is expert against the nearest other expert.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Sequence

import yaml
from jsonschema import Draft202012Validator

from ..core import Cog
from ..genome.align import Alignment, CostModel, align
from ..plugins.tz import local_to_utc, resolve_tz
from ..store.paths import repo_root, schema_dir
from .features import (ALL_KEYS, CONTRACT_KEYS, DAY, MEETING, FOCUS, SLIVER, BATCH, REVIEW, OFFSCREEN, WeekAnalysis, analyse_week)
from .model import Block, WorkConfig
from .normalize import _series_key

DOW = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BLOCK_OF_SLOT = {"meeting": ("meeting", ""), "focus": ("focus", ""), "batch": ("focus", "batch"), "review": ("focus", "review"),
                 "offscreen": ("offscreen", ""), "break": ("break", "")}


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@dataclass(frozen=True)
class Slot:
    id: str
    kind: str
    days: tuple[int, ...]
    start: int
    end: int
    recurring: bool = False
    attendees: int = 1
    external: bool = False
    optional: bool = False


@dataclass
class ExpertTemplate:
    role: str
    summary: str
    tz_name: str
    work: WorkConfig
    slots: tuple[Slot, ...]
    targets: dict[str, float]
    plugin_refs: tuple[tuple[str, str], ...] = ()
    synth: dict[str, Any] = field(default_factory=dict)
    path: str | None = None
    version: int = 1

    def slots_on(self, dow: int) -> list[Slot]:
        return [s for s in self.slots if dow in s.days]


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads((schema_dir() / "routine_expert.schema.json").read_text(encoding="utf-8")))


def packs_dir() -> Path:
    return repo_root() / "packages" / "packs"


def template_roles() -> list[str]:
    return sorted(p.parent.name for p in packs_dir().glob("*/routine_expert.yaml"))


class TemplateError(ValueError):
    pass


def parse_template(data: dict[str, Any], path: str | None = None) -> ExpertTemplate:
    errs = [f"{'.'.join(str(x) for x in e.absolute_path) or '(template)'}: {e.message[:140]}" for e in _schema_validator().iter_errors(data)]
    if errs:
        raise TemplateError(f"{path or 'template'}: " + "; ".join(errs))
    ww, pk = data["work_window"], data["peak_focus"]
    ws, we = _hm(ww["start"]), _hm(ww["end"])
    work = WorkConfig(tz=resolve_tz(data["timezone"]) or resolve_tz("UTC"), tz_name=data["timezone"], start_min=ws, end_min=we,
                      days=tuple(DOW.index(d) for d in ww["days"]), peak=(_hm(pk["start"]) - ws, _hm(pk["end"]) - ws))
    slots = tuple(Slot(s["id"], s["kind"], tuple(DOW.index(d) for d in s["days"]), _hm(s["start"]), _hm(s["end"]),
                       bool(s.get("recurring", False)), int(s.get("attendees", 1)), bool(s.get("external", False)),
                       bool(s.get("optional", False))) for s in data["slots"])
    for s in slots:
        if s.end <= s.start:
            raise TemplateError(f"{path or 'template'}: slot {s.id} ends before it starts")
    refs = tuple((r["kind"], r["id"]) for r in data.get("plugin_refs", []))
    return ExpertTemplate(role=data["role"], summary=data["summary"], tz_name=data["timezone"], work=work, slots=slots,
                          targets=dict(data["targets"]), plugin_refs=refs, synth=dict(data.get("synth", {})), path=path,
                          version=int(data["version"]))


@lru_cache(maxsize=8)
def load_template(role: str) -> ExpertTemplate:
    p = packs_dir() / role / "routine_expert.yaml"
    if not p.is_file():
        raise TemplateError(f"no routine_expert.yaml for role {role!r}; roles with one: {', '.join(template_roles()) or 'none'}")
    return parse_template(yaml.safe_load(p.read_text(encoding="utf-8")), str(p))


def template_blocks(tpl: ExpertTemplate, monday: date, *, include_optional: bool = True) -> list[Block]:
    """The template week as text-free blocks (no jitter, nothing skipped)."""
    out: list[Block] = []
    for i in range(7):
        d = monday + timedelta(days=i)
        for s in tpl.slots_on(i):
            if s.optional and not include_optional:
                continue
            kind, tag = BLOCK_OF_SLOT[s.kind]
            t0 = local_to_utc(datetime.combine(d, datetime.min.time()) + timedelta(minutes=s.start), tpl.work.tz)
            t1 = local_to_utc(datetime.combine(d, datetime.min.time()) + timedelta(minutes=s.end), tpl.work.tz)
            out.append(Block(t0, t1, kind, tag, s.attendees, s.recurring, _series_key(f"tpl:{tpl.role}:{s.id}") if s.recurring else "",
                             s.external, s.external))
    return sorted(out, key=lambda b: (b.start, b.end))


REF_MONDAY = date(2026, 10, 12)


@lru_cache(maxsize=8)
def template_reference(role: str) -> dict[str, Any]:
    """Week features of the template's own week (no jitter, nothing skipped): the reference when no expert cohort exists."""
    tpl = load_template(role)
    wa = analyse_week(template_blocks(tpl, REF_MONDAY), tpl.work, REF_MONDAY)
    return dict(wa.features)


# Targets (limits) the suggestion catalogue uses, and how each reads against a feature.
# (feature key, comparison, target key) : the learner is "short" when the comparison fails.
TARGET_RULES: dict[str, tuple[str, str]] = {
    "meeting_h": ("max", "meeting_h_max"),
    "meeting_share": ("max", "meeting_share_max"),
    "focus_blocks_90": ("min", "focus_blocks_90_min"),
    "focus_blocks_60": ("min", "focus_blocks_60_min"),
    "longest_focus_min": ("min", "longest_focus_min_min"),
    "fragmentation": ("max", "fragmentation_max"),
    "fragmented_days": ("max", "fragmented_days_max"),
    "back_to_back_runs": ("max", "back_to_back_runs_max"),
    "work_span_h": ("max", "work_span_h_max"),
    "offscreen_h": ("min", "offscreen_h_min"),
    "recurring_in_peak_h": ("max", "recurring_in_peak_h_max"),
    "external_unbuffered_n": ("max", "external_unbuffered_max"),
    "review_slots": ("min", "review_slots_min"),
    "batch_windows": ("min", "batch_windows_min"),
    "outside_hours_h": ("max", "outside_hours_h_max"),
}


def breaches(features: dict[str, Any], targets: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Which targets a week misses: ``{feature: {value, target, kind, shortfall}}`` (shortfall is relative, 0..1+)."""
    out: dict[str, dict[str, Any]] = {}
    for feat, (kind, tkey) in TARGET_RULES.items():
        if tkey not in targets or feat not in features:
            continue
        v, t = float(features[feat]), float(targets[tkey])
        if kind == "min" and v < t:
            out[feat] = {"value": features[feat], "target": targets[tkey], "kind": "min", "shortfall": round((t - v) / t, 3) if t else 1.0}
        elif kind == "max" and v > t:
            out[feat] = {"value": features[feat], "target": targets[tkey], "kind": "max", "shortfall": round((v - t) / t, 3) if t else 1.0}
    return out
