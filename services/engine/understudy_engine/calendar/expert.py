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
from .features import (ALL_KEYS, CONTRACT_KEYS, DAY, FOCUS, SLIVER, BATCH, REVIEW, WeekAnalysis, analyse_week)
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


# ---------------------------------------------------------------------------------------------------- week ribbon alignment
GAP_FEATURES = CONTRACT_KEYS + ("meeting_share", "fragmented_days", "recurring_in_peak_h", "external_unbuffered_n", "review_slots",
                                "batch_windows", "outside_hours_h")
# focus-like segments are one family (a sliver where the expert has focus time is a near miss, not an unrelated step);
# everything else is unrelated to everything else, so it aligns as an extra step plus a missing step
RIBBON_COST = CostModel(gap=1.0, same_family=0.5, unrelated=2.5, families=(frozenset({FOCUS, BATCH, REVIEW, SLIVER}),))


def ribbon_cogs(wa: WeekAnalysis) -> list[Cog]:
    """The week as a sequence of labelled day segments, times in seconds from Monday 00:00 local (DAY markers have zero length)."""
    return [Cog(t0, t1, kind) for kind, t0, t1 in wa.ribbon()]


@dataclass
class RibbonResult:
    distance: float                     # sum of |seconds| over the aligned columns divided by the longer week's total segment time
    alignment: Alignment

    def rows(self, limit: int | None = None) -> list[dict[str, Any]]:
        out = []
        for c in self.alignment.columns:
            if c.cog_expert == DAY and c.cog_novice == DAY:
                continue
            if c.cog_expert == DAY or c.cog_novice == DAY:
                continue
            out.append({"op": c.op, "expert": c.cog_expert, "learner": c.cog_novice, "minutes": round(abs(c.seconds) / 60.0, 1)})
        return out[:limit] if limit else out


def ribbon_distance(expert: WeekAnalysis, learner: WeekAnalysis) -> RibbonResult:
    """Align the learner's week against an expert week (genome Needleman-Wunsch on day segments) and normalise."""
    a = align(ribbon_cogs(expert), ribbon_cogs(learner), RIBBON_COST)
    denom = max(a.expert_s, a.novice_s, 1.0)
    return RibbonResult(round(a.abs_seconds / denom, 4), a)


# ---------------------------------------------------------------------------------------------------- expert reference
@dataclass
class ExpertWeek:
    person: str
    monday: date
    wa: WeekAnalysis


class ExpertReference:
    """The expert side of every comparison: a cohort of expert calendars (synthetic, from the template) or, when a role has none,
    the template's own week. ``exclude`` removes one person (an expert compared with the others is the placebo)."""

    def __init__(self, role: str, template: ExpertTemplate, weeks: list[ExpertWeek], source: str):
        self.role, self.template, self.weeks, self.source = role, template, weeks, source
        self.people = sorted({w.person for w in weeks})
        self._per_person: dict[str, dict[str, float]] = {}
        for p in self.people:
            ws = [w.wa.features for w in weeks if w.person == p]
            self._per_person[p] = {k: fmean(float(f[k]) for f in ws) for k in ALL_KEYS}

    @property
    def n_experts(self) -> int:
        return len(self.people) if self.source == "cohort" else 0

    def features(self, exclude: str | None = None) -> dict[str, float]:
        ps = [p for p in self.people if p != exclude] or self.people
        return {k: fmean(self._per_person[p][k] for p in ps) for k in ALL_KEYS}

    def bootstrap(self, exclude: str | None = None, n_boot: int = 300, seed: int = 0) -> dict[str, list[float]] | None:
        """Cluster bootstrap over experts: the reference mean of each feature in ``n_boot`` resamples (None for a template)."""
        ps = [p for p in self.people if p != exclude]
        if self.source != "cohort" or len(ps) < 3:
            return None
        rng = random.Random(f"ref:{self.role}:{exclude}:{seed}")
        out: dict[str, list[float]] = {k: [] for k in GAP_FEATURES}
        for _ in range(n_boot):
            pick = [rng.choice(ps) for _ in ps]
            for k in GAP_FEATURES:
                out[k].append(fmean(self._per_person[p][k] for p in pick))
        return out

    def ranges(self, exclude: str | None = None) -> dict[str, tuple[float, float]]:
        """The 95% range of each feature over expert weeks (one value per person-week, ``exclude`` left out): what a normal expert week looks like."""
        ws = [w.wa.features for w in self.weeks if w.person != exclude] or [w.wa.features for w in self.weeks]
        out = {}
        for k in GAP_FEATURES:
            v = sorted(float(f[k]) for f in ws)
            lo = v[0] if len(v) < 20 else v[int(round(0.025 * (len(v) - 1)))]
            hi = v[-1] if len(v) < 20 else v[int(round(0.975 * (len(v) - 1)))]
            out[k] = (lo, hi)
        return out

    def placebo(self, n_boot: int = 300, seed: int = 0) -> dict[str, Any]:
        """Expert against the nearest OTHER expert, by ribbon distance: should be near zero. Mean per expert, then the mean over
        experts with a cluster bootstrap by person. Cached per reference."""
        key = (n_boot, seed)
        cache = self.__dict__.setdefault("_placebo", {})
        if key in cache:
            return cache[key]
        per: dict[str, list[float]] = {}
        for w in self.weeks:
            if self.source == "cohort" and len(self.people) > 1:
                per.setdefault(w.person, []).append(self.nearest(w.wa, exclude=w.person)[1].distance)
        means = {p: fmean(v) for p, v in per.items()}
        out: dict[str, Any] = {"distance": None, "ci": None, "n_experts": len(means)}
        if means:
            rng = random.Random(f"placebo:{self.role}:{seed}")
            people = sorted(means)
            draws = sorted(fmean(means[rng.choice(people)] for _ in people) for _ in range(n_boot))
            out.update(distance=round(fmean(means.values()), 4), ci=[round(draws[int(0.025 * (n_boot - 1))], 4), round(draws[int(round(0.975 * (n_boot - 1)))], 4)])
        cache[key] = out
        return out

    def nearest(self, learner: WeekAnalysis, exclude: str | None = None) -> tuple[ExpertWeek, RibbonResult]:
        """The expert week closest to the learner's week by ribbon distance (excluding ``exclude``'s own weeks)."""
        best: tuple[ExpertWeek, RibbonResult] | None = None
        for w in self.weeks:
            if exclude is not None and w.person == exclude:
                continue
            r = ribbon_distance(w.wa, learner)
            if best is None or r.distance < best[1].distance:
                best = (w, r)
        assert best is not None, "no expert weeks to compare with"
        return best


def build_reference(role: str, cohort: Sequence[Any] | None) -> ExpertReference:
    """``cohort``: PersonCalendar-like objects (``person``, ``weeks``, ``week(monday)``) of experts, or None for the template."""
    tpl = load_template(role)
    if cohort and len(cohort) >= 3:
        weeks = [ExpertWeek(pc.person, m, pc.week(m)) for pc in cohort for m in pc.weeks]
        return ExpertReference(role, tpl, weeks, "cohort")
    wa = analyse_week(template_blocks(tpl, REF_MONDAY), tpl.work, REF_MONDAY)
    return ExpertReference(role, tpl, [ExpertWeek("template", REF_MONDAY, wa)], "template")


def gap_rows(learner: dict[str, Any], ref: ExpertReference, *, exclude: str | None = None, n_boot: int = 300, seed: int = 0,
             keys: Iterable[str] = GAP_FEATURES) -> list[dict[str, Any]]:
    """Learner against expert reference, feature by feature: ``{feature, learner, expert, delta, ci, expert_range, significant}``. ``ci`` is a
    cluster bootstrap over experts (uncertainty in the reference mean only; the learner's own week-to-week spread is not in it), so on its
    own it would flag ordinary weeks; ``significant`` therefore also needs the learner to be outside the range of expert weeks."""
    mean = ref.features(exclude)
    boot = ref.bootstrap(exclude, n_boot, seed)
    rng = ref.ranges(exclude) if ref.source == "cohort" else None
    rows = []
    for k in keys:
        lv, ev = float(learner[k]), mean[k]
        row: dict[str, Any] = {"feature": k, "learner": learner[k], "expert": round(ev, 3), "delta": round(lv - ev, 3), "ci": None,
                               "expert_range": None, "significant": None}
        if boot is not None:
            ds = sorted(lv - x for x in boot[k])
            lo, hi = ds[int(0.025 * (len(ds) - 1))], ds[int(round(0.975 * (len(ds) - 1)))]
            row["ci"] = [round(lo, 3), round(hi, 3)]
            r_lo, r_hi = rng[k]                                                  # type: ignore[index]
            row["expert_range"] = [round(r_lo, 3), round(r_hi, 3)]
            # significant = the interval of the difference excludes zero AND the learner's week lies outside the range of expert weeks
            row["significant"] = bool((lo > 0 or hi < 0) and (lv < r_lo - 1e-9 or lv > r_hi + 1e-9))
        rows.append(row)
    return rows
