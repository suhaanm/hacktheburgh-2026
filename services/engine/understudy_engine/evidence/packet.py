"""The evidence packet (REQ-6): a typed, closed-schema object that holds what the worker's analytics found, and nothing else.

A packet holds only: cog and habit ids, seconds, intervals (lo, hi), baseline values, counts, a split, an origin badge,
stuck-hazard readings (a probability and its source, model or rule), the coach gate's decision as enums, routine candidates and
the trust ladder as numbers and enums, and ``limitations`` chosen from a fixed list of ids. It has no free text anywhere: no
names, paths, titles, URLs, field values or event payloads. It is a ``SafePayload`` of the privacy layer, so a free string
field cannot even be declared, and the whole packet can be sent through ``egress.send`` if the worker allows a cloud wording.

Where the numbers come from. Builders take the **shapes the engine's own API already returns** (docs/API_CONTRACT.md), so they
do not reach into the analytics packages: ``from_genome`` (the ``/genome`` payload and its meta), ``from_hazard`` (``/hazard``),
``from_coach`` (a ``CoachDecision``), ``from_routines`` (the ``/routines`` rows, with the trust-ladder fields) and, when the
ML-V2 package has landed, ``from_evidence_inputs`` (``mlv2.evidence_inputs.EvidenceInputs``; see that function for the field
list it reads). Every builder rounds to one decimal for seconds and three for probabilities, so the packet is exactly what a
sentence may quote.

Every numeric leaf is a *fact* with a stable dotted path (``habit.search_loops.seconds``, ``gap.cohort_lo``). The model cites
paths; the provenance check resolves them. ``facts()`` builds that table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, ClassVar, Iterable, Literal

from pydantic import Field

from ..privacy.payload import SafePayload
from . import vocab as V

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "packages" / "schema" / "evidence_packet.schema.json"
LEVEL = 0.95


# ------------------------------------------------------------------------------------------------ models
class Meta(SafePayload):
    """The badge and the sample: where the numbers come from and how many there are."""

    description = "Origin badge, sample size and how the comparison was split."
    origin: V.Origin
    n: Annotated[int, Field(ge=0, le=100000)]
    n_unit: V.NUnit
    split: V.Split
    level: float = LEVEL
    UNITS: ClassVar[dict[str, str]] = {"n": "count", "level": "frac"}


class Gap(SafePayload):
    """One case against the nearest expert (single case: no interval), the cohort average with its interval, and the controls."""

    description = "Seconds on this case and the reference, the cohort gap with its interval, placebo and shuffled-label controls."
    case_s: float | None = None
    reference_s: float | None = None
    gap_s: float | None = None
    gap_lo: float | None = None
    gap_hi: float | None = None
    cohort_gap_s: float | None = None
    cohort_lo: float | None = None
    cohort_hi: float | None = None
    cohort_n: Annotated[int, Field(ge=0, le=100000)] | None = None
    placebo_s: float | None = None
    placebo_lo: float | None = None
    placebo_hi: float | None = None
    null_lo: float | None = None
    null_hi: float | None = None
    UNITS: ClassVar[dict[str, str]] = {"cohort_n": "count", "*": "s"}
    SIGNED: ClassVar[frozenset[str]] = frozenset({"gap_s", "cohort_gap_s", "placebo_s"})
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (
        ("gap_lo", "gap_hi", "gap_s"), ("cohort_lo", "cohort_hi", "cohort_gap_s"), ("placebo_lo", "placebo_hi", "placebo_s"),
        ("null_lo", "null_hi", None))


class Habit(SafePayload):
    """Seconds associated with one habit (a waterfall bar); a counterfactual (what would change) only when the ML layer gives one."""

    description = "Seconds for one habit, with an interval for cohort rows and an optional counterfactual."
    seconds: float
    lo: float | None = None
    hi: float | None = None
    counterfactual_s: float | None = None
    cf_lo: float | None = None
    cf_hi: float | None = None
    n: Annotated[int, Field(ge=0, le=100000)] | None = None
    UNITS: ClassVar[dict[str, str]] = {"n": "count", "*": "s"}
    SIGNED: ClassVar[frozenset[str]] = frozenset({"seconds", "counterfactual_s"})
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("lo", "hi", "seconds"), ("cf_lo", "cf_hi", "counterfactual_s"))


class Cog(SafePayload):
    """Seconds one cog family accounts for in the gap decomposition (what the behaviour counts explain)."""

    description = "Explained (or attributed) seconds for one cog family with its interval, and the experts' envelope when known."
    seconds: float
    lo: float | None = None
    hi: float | None = None
    novice_s: float | None = None
    expert_lo_s: float | None = None
    expert_hi_s: float | None = None
    UNITS: ClassVar[dict[str, str]] = {"*": "s"}
    SIGNED: ClassVar[frozenset[str]] = frozenset({"seconds"})
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("lo", "hi", "seconds"), ("expert_lo_s", "expert_hi_s", "novice_s"))


class Consequence(SafePayload):
    """What skipping a step costs in outcome terms: the share of cases that end wrong, its interval and the mean error when wrong."""

    description = "Error rate for a skipped step, with its interval and the pounds a month when wrong."
    p_error: float | None = None
    lo: float | None = None
    hi: float | None = None
    mean_gbp: float | None = None
    n: Annotated[int, Field(ge=0, le=100000)] | None = None
    UNITS: ClassVar[dict[str, str]] = {"p_error": "frac", "lo": "frac", "hi": "frac", "mean_gbp": "gbp", "n": "count"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("lo", "hi", "p_error"),)


class Hazard(SafePayload):
    """The stuck reading: a probability of 'no progress in the next minute' and where it came from (model or rule)."""

    description = "Stuck-hazard readings with their source and the model's held-out scores."
    source: V.HazardSource
    p_now: float | None = None
    peak_p: float | None = None
    mean_p: float | None = None
    alarm_threshold: float | None = None
    n_bins: Annotated[int, Field(ge=0, le=1000000)] | None = None
    model_log_loss: float | None = None
    baseline_log_loss: float | None = None
    ece: float | None = None
    false_alarms_per_hour: float | None = None
    p_lo: float | None = None
    p_hi: float | None = None
    fa_lo: float | None = None
    fa_hi: float | None = None
    calibration: V.Calibration | None = None
    UNITS: ClassVar[dict[str, str]] = {"p_now": "frac", "peak_p": "frac", "mean_p": "frac", "alarm_threshold": "frac", "n_bins": "count",
                                       "model_log_loss": "score", "baseline_log_loss": "score", "ece": "score",
                                       "false_alarms_per_hour": "per_hour", "p_lo": "frac", "p_hi": "frac", "fa_lo": "per_hour",
                                       "fa_hi": "per_hour"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("p_lo", "p_hi", "p_now"), ("fa_lo", "fa_hi", "false_alarms_per_hour"))


class Progress(SafePayload):
    """Expected minutes until the next progress event (restricted mean), with an interval."""

    description = "Expected minutes to the next progress event with its interval."
    expected_min: float
    lo: float | None = None
    hi: float | None = None
    c_index: float | None = None
    UNITS: ClassVar[dict[str, str]] = {"c_index": "score", "*": "min"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("lo", "hi", "expected_min"),)


class Coach(SafePayload):
    """What the coach gate decided at this moment, as enums and two counts."""

    description = "The coach decision as enums: action, level, trigger and reason codes."
    action: V.CoachAction
    level: V.Level
    trigger: V.CoachTrigger | None = None
    reasons: list[V.ReasonCode] = Field(default_factory=list)
    gate_consecutive: Annotated[int, Field(ge=0, le=1000)] | None = None
    missed_steps: Annotated[int, Field(ge=0, le=1000)] | None = None
    UNITS: ClassVar[dict[str, str]] = {"gate_consecutive": "count", "missed_steps": "count"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = ()


class Routine(SafePayload):
    """A routine candidate and its place on the trust ladder."""

    description = "A routine candidate: counts, minutes, a value interval, consent status and trust-ladder state."
    episodes: Annotated[int, Field(ge=0, le=100000)] | None = None
    minutes_per_week: float | None = None
    cv: float | None = None
    judgement_share: float | None = None
    hours_lo: float | None = None
    hours_hi: float | None = None
    horizon_weeks: Annotated[int, Field(ge=0, le=520)] | None = None
    status: V.RoutineStatus
    rung: V.Rung
    shadow_runs: Annotated[int, Field(ge=0, le=100000)] = 0
    shadow_matches: Annotated[int, Field(ge=0, le=100000)] = 0
    wilson_lower: float = 0.0
    next_rung: V.Rung | None = None
    runs_to_next: Annotated[int, Field(ge=0, le=100000)] | None = None
    UNITS: ClassVar[dict[str, str]] = {"episodes": "count", "minutes_per_week": "min", "cv": "score", "judgement_share": "frac",
                                       "hours_lo": "h", "hours_hi": "h", "horizon_weeks": "weeks", "shadow_runs": "count",
                                       "shadow_matches": "count", "wilson_lower": "frac", "runs_to_next": "count"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = (("hours_lo", "hours_hi", None),)


class EvidencePacket(SafePayload):
    """Everything a sentence about the worker's time may rest on."""

    description = ("Closed-schema evidence for one worker and (optionally) one case: ids, seconds, intervals, baselines, n, split, "
                   "origin badge, hazard readings, coach decision, routines and limitation ids. No free text.")
    schema_version: Literal[1] = 1
    meta: Meta
    gap: Gap | None = None
    habits: dict[V.HabitId, Habit] = Field(default_factory=dict)
    cohort_habits: dict[V.HabitId, Habit] = Field(default_factory=dict)
    cogs: dict[V.CogId, Cog] = Field(default_factory=dict)
    consequences: dict[V.StepId, Consequence] = Field(default_factory=dict)
    hazard: Hazard | None = None
    progress: Progress | None = None
    coach: Coach | None = None
    routines: dict[V.RoutineKind, Routine] = Field(default_factory=dict)
    limitations: list[V.LimitId] = Field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:                    # noqa: D401 - sent form: no nulls
        return json.loads(self.model_dump_json(exclude_none=True))

    def is_empty(self) -> bool:
        return not (self.gap or self.habits or self.cohort_habits or self.cogs or self.consequences or self.hazard or self.coach
                    or self.routines or self.progress)


class Question(SafePayload):
    """What was asked, as a closed intent plus the one number a worker may have typed (a duration in seconds)."""

    description = "A question reduced to a fixed intent; the worker's own words never leave the device."
    intent: V.Intent
    asked_s: float | None = None
    matches_case: bool | None = None
    UNITS: ClassVar[dict[str, str]] = {"asked_s": "s"}
    SIGNED: ClassVar[frozenset[str]] = frozenset()
    INTERVALS: ClassVar[tuple[tuple[str, str, str | None], ...]] = ()


class ExplainRequest(SafePayload):
    """What a wording model receives: the packet, the intent, and the coach actions that apply (ids only)."""

    description = "An evidence packet, a question intent and the applicable coach-menu ids. No names, no free text."
    packet: EvidencePacket
    question: Question
    menu: list[V.MenuId] = Field(default_factory=list)

    def to_wire(self) -> dict[str, Any]:                    # noqa: D401
        return json.loads(self.model_dump_json(exclude_none=True))


# ------------------------------------------------------------------------------------------------ facts
@dataclass(frozen=True)
class Fact:
    """A numeric leaf of a packet. ``path`` is what a sentence cites. ``role`` is ``point``, ``lo`` or ``hi``."""

    path: str
    value: float
    unit: str
    role: str = "point"
    signed: bool = False
    coll: str | None = None          # collection: habit, cohort_habit, cog, consequence, routine
    item: str | None = None          # id within the collection
    pair: str | None = None          # for lo/hi: the path of the interval's other end


@dataclass
class FactTable:
    facts: dict[str, Fact] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)             # non-numeric leaves (enums) by path
    containers: set[str] = field(default_factory=set)
    intervals: list[tuple[str, str, str | None]] = field(default_factory=list)   # (lo path, hi path, point path or None)
    habits: tuple[str, ...] = ()
    cohort_habits: tuple[str, ...] = ()
    cogs: tuple[str, ...] = ()
    routines: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    levels: frozenset[str] = frozenset()
    rungs: frozenset[str] = frozenset()

    def under(self, path: str) -> list[Fact]:
        """Facts a citation of ``path`` covers: the fact itself, or every fact below a container."""
        if path in self.facts:
            return [self.facts[path]]
        if path in self.containers:
            pre = path + "."
            return [f for p, f in self.facts.items() if p.startswith(pre)]
        return []

    def known(self, path: str) -> bool:
        return path in self.facts or path in self.containers or path in self.labels

    def all_paths(self) -> list[str]:
        return sorted(set(self.facts) | self.containers | set(self.labels))


COLLECTIONS = {"habits": "habit", "cohort_habits": "cohort_habit", "cogs": "cog", "consequences": "consequence", "routines": "routine"}
BLOCKS = ("gap", "hazard", "progress", "coach")


def _units_of(model: SafePayload) -> dict[str, str]:
    return getattr(type(model), "UNITS", {})


def _unit(model: SafePayload, name: str) -> str:
    u = _units_of(model)
    return u.get(name) or u.get("*") or "count"


def _add_leaf_facts(tab: FactTable, prefix: str, model: SafePayload, coll: str | None, item: str | None) -> None:
    signed = getattr(type(model), "SIGNED", frozenset())
    pairs = {}
    for lo, hi, pt in getattr(type(model), "INTERVALS", ()):
        pairs[lo] = hi
        pairs[hi] = lo
    tab.containers.add(prefix)
    interval_lo_hi = set()
    for lo, hi, pt in getattr(type(model), "INTERVALS", ()):
        if getattr(model, lo, None) is not None and getattr(model, hi, None) is not None:
            tab.intervals.append((f"{prefix}.{lo}", f"{prefix}.{hi}", f"{prefix}.{pt}" if pt and getattr(model, pt, None) is not None else None))
            interval_lo_hi.update({lo, hi})
    for name in type(model).model_fields:
        v = getattr(model, name)
        if v is None:
            continue
        path = f"{prefix}.{name}"
        if isinstance(v, bool):
            tab.labels[path] = "true" if v else "false"
        elif isinstance(v, (int, float)):
            role = "point"
            for lo, hi, pt in getattr(type(model), "INTERVALS", ()):
                if name == lo:
                    role = "lo"
                elif name == hi:
                    role = "hi"
            pair = f"{prefix}.{pairs[name]}" if name in pairs and name in interval_lo_hi else None
            tab.facts[path] = Fact(path, float(v), _unit(model, name), role, name in signed, coll, item, pair)
        elif isinstance(v, str):
            tab.labels[path] = v
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    tab.labels[f"{path}.{x}"] = x
            tab.containers.add(path)


def facts(obj: EvidencePacket | ExplainRequest) -> FactTable:
    """The fact table of a packet (or of a request: the packet's facts plus ``question.asked_s``)."""
    tab = FactTable()
    pk = obj.packet if isinstance(obj, ExplainRequest) else obj
    _add_leaf_facts(tab, "meta", pk.meta, None, None)
    for blk in BLOCKS:
        m = getattr(pk, blk)
        if m is not None:
            _add_leaf_facts(tab, blk, m, None, None)
    for fld, coll in COLLECTIONS.items():
        d = getattr(pk, fld)
        if d:
            tab.containers.add(coll)
        for key, m in d.items():
            _add_leaf_facts(tab, f"{coll}.{key}", m, coll, key)
    tab.habits = tuple(pk.habits)
    tab.cohort_habits = tuple(pk.cohort_habits)
    tab.cogs = tuple(pk.cogs)
    tab.routines = tuple(pk.routines)
    tab.steps = tuple(pk.consequences)
    levels = {pk.coach.level} if pk.coach else set()
    tab.levels = frozenset(levels)
    tab.rungs = frozenset(r.rung for r in pk.routines.values()) | frozenset(r.next_rung for r in pk.routines.values() if r.next_rung)
    if isinstance(obj, ExplainRequest):
        _add_leaf_facts(tab, "question", obj.question, None, None)
        tab.labels["question.intent"] = obj.question.intent
    return tab


#: facts a sentence may use without citing them: the badge always printed with the answer
AMBIENT = ("meta.n", "meta.level", "question.asked_s")


# ------------------------------------------------------------------------------------------------ limitations
def limitations_for(pk: EvidencePacket) -> list[str]:
    """Which fixed limitation ids apply, chosen by code from the packet (never by a model)."""
    out = ["association_only", "not_expert_claim", "explainer_readability"]
    if pk.meta.origin == "synthetic":
        out.insert(0, "synthetic_data")
    elif pk.meta.origin == "simulated_participants":
        out.insert(0, "simulated_participants")
    if pk.meta.n < 30:
        out.append("small_n")
    if pk.gap is not None and pk.gap.case_s is not None and pk.gap.gap_lo is None:
        out.append("single_case")
    if pk.hazard is not None:
        out.append("hazard_not_diagnosis")
        if pk.hazard.source == "rule":
            out.append("hazard_rule_fallback")
    if any(h.counterfactual_s is not None for h in list(pk.habits.values()) + list(pk.cohort_habits.values())):
        out.append("counterfactual_model")
    if pk.consequences:
        out.append("consequence_rules")
    if "step_skips" in pk.habits or "step_skips" in pk.cohort_habits:
        out.append("saved_time_by_skips")
    if pk.meta.origin == "synthetic" and pk.hazard is not None:
        out.append("scripted_tasks")
    seen: list[str] = []
    for x in out:
        if x not in seen:
            seen.append(x)
    return seen


def finalise(pk: EvidencePacket) -> EvidencePacket:
    """Return the packet with its limitation ids filled in by ``limitations_for``."""
    return pk.model_copy(update={"limitations": limitations_for(pk)})


# ------------------------------------------------------------------------------------------------ builders
def _r1(x: Any) -> float | None:
    try:
        return None if x is None else round(float(x), 1)
    except (TypeError, ValueError):
        return None


def _r3(x: Any) -> float | None:
    try:
        return None if x is None else round(float(x), 3)
    except (TypeError, ValueError):
        return None


def _ci(x: Any) -> tuple[float | None, float | None]:
    if isinstance(x, (list, tuple)) and len(x) == 2:
        return _r1(x[0]), _r1(x[1])
    return None, None


def _meta_block(meta: dict[str, Any] | None, *, origin: str | None, split: str, n_default: int = 0, n_unit: str = "people") -> Meta:
    meta = meta or {}
    o = origin or {"real": "live", "synthetic": "synthetic", "mixed": "synthetic"}.get(str(meta.get("origin")), "synthetic")
    if o not in V.ORIGINS:
        o = "synthetic"
    unit = str(meta.get("n_unit") or n_unit)
    unit = {"days": "cases", "decisions": "cases", "runs": "cases"}.get(unit, unit)
    if unit not in ("people", "cases", "episodes", "households", "personas"):
        unit = "cases"
    return Meta(origin=o, n=int(meta.get("n") or n_default), n_unit=unit, split=split)


def from_genome(data: dict[str, Any], meta: dict[str, Any] | None = None, *, origin: str | None = None) -> EvidencePacket:
    """From the ``/genome/{task}`` payload (``GenomeService.genome``'s first value) and its meta.

    Per case: seconds on the case and on the nearest expert (dwell sums, so ``gap_s = case_s - reference_s`` matches the
    alignment's own total), the habits (waterfall bars) of that case. Per cohort: the average gap with its cluster-bootstrap
    interval, the cohort waterfall bars with intervals, the explained seconds by cog family, the placebo and shuffled-label
    controls, and what skipping a step costs when ``evals/cases/skip_consequences.json`` exists."""
    mt = meta.model_dump() if hasattr(meta, "model_dump") else meta
    m = _meta_block(mt, origin=origin, split="descriptive_nearest_expert")
    nov = (data.get("novice") or {}).get("segments") or []
    exp = (data.get("expert") or {}).get("segments") or []
    case_s = sum(float(s["t1"]) - float(s["t0"]) for s in nov) if nov else None
    ref_s = sum(float(s["t1"]) - float(s["t0"]) for s in exp) if exp else None
    people = (data.get("people") or {}).get("novices") or []
    lo, hi = _ci(data.get("total_gap_ci"))
    ctrl = data.get("controls") or {}
    pl, nl = ctrl.get("placebo") or {}, ctrl.get("null") or {}
    pl_lo, pl_hi = _ci(pl.get("ci"))
    nl_lo, nl_hi = _ci(nl.get("ci"))
    gap = Gap(
        case_s=_r1(case_s), reference_s=_r1(ref_s),
        gap_s=_r1(data["person_gap_s"]) if data.get("person_gap_s") is not None else (_r1(case_s - ref_s) if case_s is not None and ref_s is not None else None),
        cohort_gap_s=_r1(data.get("total_gap_s")), cohort_lo=lo, cohort_hi=hi, cohort_n=len(people) or None,
        placebo_s=_r1(pl.get("gap_s")), placebo_lo=pl_lo, placebo_hi=pl_hi, null_lo=nl_lo, null_hi=nl_hi,
    )
    habits: dict[str, Habit] = {}
    for row in data.get("person_waterfall") or []:
        hid = V.LABEL_TO_HABIT.get(str(row.get("label")))
        sec = _r1(row.get("seconds"))
        if hid and sec is not None and abs(sec) >= 0.5:
            habits[hid] = Habit(seconds=sec)
    cohort: dict[str, Habit] = {}
    for row in data.get("waterfall") or []:
        hid = V.LABEL_TO_HABIT.get(str(row.get("label")))
        sec = _r1(row.get("seconds"))
        h_lo, h_hi = _ci(row.get("ci"))
        if hid and sec is not None and abs(sec) >= 0.5:
            cohort[hid] = Habit(seconds=sec, lo=h_lo, hi=h_hi, n=len(people) or None)
    cogs: dict[str, Cog] = {}
    # explained seconds by cog family: only the behaviours that account for ADDED time (a negative term is an artefact of the
    # regression, such as undo counts offsetting extra reads, and has no plain reading for a worker)
    comps = [c for c in ((data.get("decomposition") or {}).get("components") or [])
             if c.get("cog") in V.COG_IDS and float(c.get("seconds") or 0) >= 0.5]
    for c in sorted(comps, key=lambda c: -float(c.get("seconds") or 0))[:3]:
        c_lo, c_hi = _ci(c.get("ci"))
        cogs[c["cog"]] = Cog(seconds=_r1(c["seconds"]), lo=c_lo, hi=c_hi)
    cons: dict[str, Consequence] = {}
    for row in data.get("consequences") or []:
        step = row.get("step")
        if step not in V.STEP_NAME:
            continue
        p_lo, p_hi = (None, None)
        ci = row.get("p_error_ci95")
        if isinstance(ci, (list, tuple)) and len(ci) == 2:
            p_lo, p_hi = _r3(ci[0]), _r3(ci[1])
        if row.get("p_error") is None:
            continue                    # CHECK_CLIFF: no p_error today; the panel does not change today's figure
        cons[step] = Consequence(p_error=_r3(row.get("p_error")), lo=p_lo, hi=p_hi,
                                 mean_gbp=_r1(row.get("mean_error_gbp")), n=int(row["n"]) if row.get("n") is not None else None)
    return finalise(EvidencePacket(meta=m, gap=gap, habits=habits, cohort_habits=cohort, cogs=cogs, consequences=cons))


def from_hazard(data: dict[str, Any], meta: dict[str, Any] | None = None, *, person: str | None = None) -> Hazard:
    """From the ``/hazard/{person}`` payload: readings over the person's held-out series, and the model's cohort scores."""
    series = [float(p["p"]) for p in (data.get("series") or []) if isinstance(p, dict) and p.get("p") is not None]
    model = data.get("model") or {}
    base = (data.get("baselines") or {}).get("time_since_progress") or {}
    thr = None
    pdat = data.get("person") or {}
    if isinstance(pdat.get("alarm_rule"), dict):
        thr = pdat["alarm_rule"].get("threshold")
    return Hazard(
        source="model", p_now=_r3(series[-1]) if series else None, peak_p=_r3(max(series)) if series else None,
        mean_p=_r3(sum(series) / len(series)) if series else None, alarm_threshold=_r3(thr), n_bins=len(series) or None,
        model_log_loss=_r3(model.get("log_loss")), baseline_log_loss=_r3(base.get("log_loss")), ece=_r3(model.get("ece")),
        false_alarms_per_hour=_r3(data.get("false_alarms_per_hour")))


def from_coach(decision: dict[str, Any]) -> tuple[Coach, Hazard | None]:
    """From a ``CoachDecision`` (as a dict): the gate's decision as enums, and its stuck reading when it carries one."""
    reasons = [r if r in V.REASON_CODES else "other" for r in (decision.get("reason_codes") or [])][:8]
    gate = decision.get("gate") or {}
    trig = decision.get("trigger")
    level = decision.get("level") if decision.get("level") in ("L1", "L2", "L3", "L4") else "L1"
    action = decision.get("action") if decision.get("action") in ("silent", "nudge", "annotate", "takeover_offer") else "silent"
    coach = Coach(action=action, level=level, trigger=trig if trig in ("expert_policy", "stuck", "ask") else None,
                  reasons=reasons, gate_consecutive=int(gate.get("consecutive") or 0), missed_steps=len(decision.get("missed") or []))
    hz = None
    if decision.get("p_stuck") is not None:
        hz = Hazard(source="model" if decision.get("p_source") == "hazard" else "rule", p_now=_r3(decision["p_stuck"]))
    return coach, hz


def from_routines(rows: Iterable[dict[str, Any]]) -> dict[str, Routine]:
    """From the ``/routines`` rows: routines that match a pack template (others have no id a sentence may use), each with its
    consent status, ladder rung, shadow evidence and, from ``trust.ladder.runs_needed``, the clean runs to the next rung."""
    out: dict[str, Routine] = {}
    for r in rows:
        kind = r.get("id") or r.get("template_id")
        if kind not in V.ROUTINE_KINDS:
            continue
        val = r.get("value") or {}
        hours = val.get("hours_saved") if isinstance(val.get("hours_saved"), (list, tuple)) and len(val.get("hours_saved")) == 2 else (None, None)
        sh = r.get("shadow") or {}
        rung = r.get("rung") if r.get("rung") in ("A0", "A1", "A2", "A3") else "A0"
        status = r.get("status") if r.get("status") in V.STATUS_PHRASE else "proposed"
        runs, matches = int(sh.get("runs") or 0), int(sh.get("matches") or 0)
        nxt, need = None, None
        if rung in ("A1", "A2"):
            nxt = "A2" if rung == "A1" else "A3"
            try:
                from ..trust.ladder import runs_needed

                need = runs_needed(nxt, matches, runs)
            except Exception:
                need = None
        out[kind] = Routine(
            episodes=int(r["episodes"]) if r.get("episodes") is not None else None, minutes_per_week=_r1(r.get("minutes_per_week")),
            cv=_r3(r.get("cv")), judgement_share=_r3(r.get("judgement_share")), hours_lo=_r1(hours[0]), hours_hi=_r1(hours[1]),
            horizon_weeks=int(val["horizon_weeks"]) if val.get("horizon_weeks") is not None else None,
            status=status, rung=rung, shadow_runs=runs, shadow_matches=matches, wilson_lower=_r3(sh.get("wilson_lower")) or 0.0,
            next_rung=nxt, runs_to_next=need)
    return out


def combine(base: EvidencePacket, *, hazard: Hazard | None = None, coach: Coach | None = None,
            routines: dict[str, Routine] | None = None) -> EvidencePacket:
    """Add blocks to a packet (a block already present is kept unless the new one is richer) and refresh its limitations."""
    upd: dict[str, Any] = {}
    if hazard is not None and (base.hazard is None or (base.hazard.source == "rule" and hazard.source == "model")
                               or (hazard.n_bins and not base.hazard.n_bins)):
        upd["hazard"] = hazard
    if coach is not None:
        upd["coach"] = coach
    if routines:
        upd["routines"] = {**base.routines, **routines}
    new = base.model_copy(update=upd)
    return finalise(EvidencePacket.model_validate_json(new.model_dump_json()))


def empty_packet(meta: Meta) -> EvidencePacket:
    return finalise(EvidencePacket(meta=meta))


# ------------------------------------------------------------------------------------------------ ML-V2 adapter
try:                                                         # the ML-V2 track exports typed EvidenceInputs (REQ-6)
    from ..mlv2.evidence_inputs import EvidenceInputs         # type: ignore[import-not-found]
except Exception:                                            # not present, or it failed to import: v1 builders only
    EvidenceInputs = None                                    # type: ignore[assignment,misc]


class InputNotAccepted(ValueError):
    """The ML-V2 variant failed its pre-registered acceptance test against v1 (``provenance.accepted is False``): drop it."""


def _hazard_from(h: Any) -> Hazard | None:
    if h is None:
        return None
    src = h.source if h.source in ("model", "rule") else "rule"
    cal = h.calibration if h.calibration in ("calibrated", "overconfident", "underconfident", "untested") else None
    return Hazard(source=src, p_now=_r3(h.p), alarm_threshold=_r3(h.threshold), n_bins=int(h.n_bins) if h.n_bins else None,
                  model_log_loss=_r3(h.log_loss), baseline_log_loss=_r3(h.tsp_log_loss), ece=_r3(h.ece),
                  false_alarms_per_hour=_r3(h.false_alarms_per_hour), p_lo=_r3(h.p_lo), p_hi=_r3(h.p_hi),
                  fa_lo=_r3(h.fa_lo), fa_hi=_r3(h.fa_hi), calibration=cal)


def _habit_from(x: Any) -> Habit:
    cf = x.counterfactual_s is not None
    return Habit(seconds=_r1(x.seconds), lo=_r1(x.seconds_lo), hi=_r1(x.seconds_hi),
                 counterfactual_s=_r1(x.counterfactual_s) if cf else None, cf_lo=_r1(x.counterfactual_lo) if cf else None,
                 cf_hi=_r1(x.counterfactual_hi) if cf else None, n=int(x.n) if x.n is not None else None)


def known_limitations(ids: Iterable[str]) -> list[str]:
    """Limitation ids another track named, mapped through the aliases and filtered to the fixed list (an unknown id is dropped)."""
    out: list[str] = []
    for i in ids:
        i = V.LIMIT_ALIASES.get(i, i)
        if i in V.LIMITATIONS and i not in out:
            out.append(i)
    return out


def from_evidence_inputs(inp: Any, *, person: str | None = None, case: str | None = None) -> EvidencePacket:
    """Build a packet from ML-V2's ``mlv2.evidence_inputs.EvidenceInputs`` (frozen dataclasses; ``validate()`` has already refused
    ids outside the closed sets, non-finite numbers, ``lo > hi`` and free text).

    * A variant with ``provenance.accepted is False`` raises ``InputNotAccepted`` (the caller falls back to the v1 packet).
    * The case is the one whose ``person_id`` and ``task_id`` match ``person`` and ``case`` (else the first). Its habits become
      ``habits`` (with counterfactual seconds and their own interval when present); its cog envelope becomes ``cogs``; its
      hazard and time-to-progress become ``hazard`` and ``progress``. The cohort block fills ``cohort_gap_s`` and its interval.
    * ``baselines.placebo_expert_vs_expert`` becomes ``gap.placebo_s``. Other baselines are not quoted.
    * Limitation ids are the union of the inputs', the case's and the ones ``limitations_for`` derives; ids are mapped through
      ``vocab.LIMIT_ALIASES`` (the privacy backstop refuses a payload value of 32 or more id characters)."""
    if hasattr(inp, "usable") and not inp.usable():
        raise InputNotAccepted("the ML-V2 variant failed its acceptance test against v1")
    if hasattr(inp, "validate"):
        inp.validate()
    pv = inp.provenance
    m = Meta(origin=pv.origin, n=int(pv.n), n_unit=pv.n_unit, split=pv.split, level=float(pv.interval_level))
    cases = list(inp.cases)
    c = next((x for x in cases if (person is None or x.person_id == person) and (case is None or x.task_id == case)), cases[0] if cases else None)
    coh = inp.cohort
    base = dict(inp.baselines or {})
    gap = None
    if c is not None or coh is not None:
        gap = Gap(
            case_s=_r1(c.case_s) if c else None, reference_s=_r1(c.reference_s) if c else None, gap_s=_r1(c.gap_s) if c else None,
            gap_lo=_r1(c.gap_lo) if c else None, gap_hi=_r1(c.gap_hi) if c else None,
            cohort_gap_s=_r1(coh.gap_s) if coh else None, cohort_lo=_r1(coh.gap_lo) if coh else None, cohort_hi=_r1(coh.gap_hi) if coh else None,
            cohort_n=int(coh.n) if coh else None, placebo_s=_r1(base.get("placebo_expert_vs_expert")))
    habits: dict[str, Habit] = {}
    cogs: dict[str, Cog] = {}
    hz, prog, lim = _hazard_from(inp.hazard), None, list(inp.limitations)
    if c is not None:
        for h in c.habits:
            if h.habit_id in V.HABITS:
                habits[h.habit_id] = _habit_from(h)
        for e in c.envelope:
            if e.cog_id in V.COG_IDS:
                cogs[e.cog_id] = Cog(seconds=_r1(e.attributed_s), lo=_r1(e.attributed_lo), hi=_r1(e.attributed_hi), novice_s=_r1(e.novice_s),
                                     expert_lo_s=_r1(e.expert_lo_s), expert_hi_s=_r1(e.expert_hi_s))
        hz = _hazard_from(c.hazard) or hz
        if c.time_to_progress is not None:
            t = c.time_to_progress
            prog = Progress(expected_min=_r1(t.expected_min), lo=_r1(t.lo), hi=_r1(t.hi), c_index=_r3(t.c_index))
        lim += list(c.limitations)
    pk = EvidencePacket(meta=m, gap=gap, habits=habits, cogs=cogs, hazard=hz, progress=prog)
    pk = finalise(pk)
    extra = known_limitations(lim)
    merged = list(pk.limitations) + [x for x in extra if x not in pk.limitations]
    return pk.model_copy(update={"limitations": merged})


# ------------------------------------------------------------------------------------------------ schema file
def json_schema() -> dict[str, Any]:
    """The packet's JSON Schema (closed: ``additionalProperties: false`` on every object, enums for ids)."""
    sch = EvidencePacket.model_json_schema()
    sch = {"$schema": "https://json-schema.org/draft/2020-12/schema",
           "$id": "https://understudy.local/schema/evidence_packet.schema.json", **sch}
    sch["title"] = "EvidencePacket"
    sch["description"] = EvidencePacket.description
    return sch


def write_schema(path: Path | None = None) -> Path:
    p = path or SCHEMA_PATH
    p.write_text(json.dumps(json_schema(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return p
