"""The numbers an explainer may use (REQ-6, EVIDENCE contract), as typed, frozen, validated dataclasses.

Only these things may appear: closed-set ids (habits, cogs, enums, limitation ids), numbers, (lo, hi) intervals, baselines, the origin badge,
n, split, the model version and whether the variant was accepted against v1. **No names, paths, titles, URLs or field values, and no free
text**: ``validate()`` rejects any string that is not a member of its closed set or does not match the id pattern. The explainer quotes the
limitation sentence for an id from ``LIMITATIONS`` (or writes its own wording for the id); it never receives a sentence from this module that
it did not ask for by id.

Raw floats are carried; the consumer rounds (seconds to 1 decimal, probabilities to 3).
Field names for the accept test: ``inputs.provenance.model_version`` ("v1" | "v2") and ``inputs.provenance.accepted`` (True | False | None;
None = not applicable, for example v1 itself), also exposed as ``inputs.model_version`` and ``inputs.accepted``. Drop an input when
``accepted is False``.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Mapping

SCHEMA_VERSION = 1

# ---- closed sets (agreed with EVIDENCE, 7 Nov) ----
HABIT_IDS = ("pace", "pauses", "search_loops", "repeated_reads", "missed_check", "wrong_copy", "rework", "step_skips", "other_extra")
ORIGINS = ("synthetic", "simulated_participants", "live")
N_UNITS = ("people", "cases", "episodes", "households", "personas")
SPLITS = ("descriptive_nearest_expert", "leave_one_person_out", "none")
POOLS = ("d0", "dev", "heldout", "mismatch", "sim", "none")
HAZARD_SOURCES = ("model", "rule")
METHODS = ("alignment", "splice", "shapley")
CALIBRATION = ("calibrated", "overconfident", "underconfident", "untested")
MODEL_VERSIONS = ("v1", "v2")
BASELINE_NAMES = ("base_rate", "time_since_progress", "nearest_single_expert", "placebo_expert_vs_expert", "no_personal_shift")

# Waterfall bar (genome.labels) and planted deficit name -> habit id. 'Skipped steps' is step_skips, never the literal word.
HABIT_OF_LABEL = {
    "Slower on shared steps": "pace", "Long pauses": "pauses", "Search loops": "search_loops", "Repeated reads": "repeated_reads",
    "Missed check, redone": "missed_check", "Wrong figure, copied again": "wrong_copy", "Rework": "rework",
    "Skipped steps": "step_skips", "Other extra steps": "other_extra",
}
HABIT_OF_DEFICIT = {
    "idle_before_enter": "pauses", "search_loop": "search_loops", "repeated_read_result": "repeated_reads",
    "skipped_check_cliff": "missed_check", "copy_error": "wrong_copy",
}

# The fixed limitation table (id -> a plain default sentence; the consumer may use its own wording for the same id).
LIMITATIONS: dict[str, str] = {
    "synthetic_people_only": "These results come from people we generated, not from real workers.",
    "generator_planted_structure": "The structure these methods find was planted by our own data generator, so this shows recovery of what we planted.",
    "n_four_personas": "The stuck-prediction result rests on four generated personas.",
    "shared_steps_mispriced": "When two habits share steps, the seconds can be shifted between them.",
    "additive_counterfactual_assumes_rest_unchanged": "The seconds-if-fixed estimate assumes the rest of the path would stay the same.",
    "interactions_not_modelled": "Interactions between habits are not modelled, so the parts need not add up exactly.",
    "calibrated_on_synthetic": "The probabilities were calibrated on generated data.",
    "alarm_budget_is_design_choice": "The false-alarm budget is a design choice, not a measured tolerance of real workers.",
    "llm_participants_not_people": "These traces come from language-model participants, not people.",
    "timing_reconstructed": "Timing in these traces was reconstructed from action counts, not measured.",
    "held_out_replicates_same_generator": "The held-out check used fresh draws of the same generator, so it cannot show the model avoided learning the generator.",
    "generator_mismatch_tested": "The model was also tested on data from a differently built generator; results for that test are labelled separately.",
    "small_n_simulated_participants": "Only a few language-model participants finished, so the intervals are wide.",
    "interval_too_narrow": "The interval for this estimate was too narrow in testing and should be read as optimistic.",
}
LIMITATION_IDS = tuple(LIMITATIONS)

_ID_RE = re.compile(r"^[a-z0-9_.:-]+$")
_COG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PERSON_RE = re.compile(r"^p_[a-z0-9_]+$")
_TASK_RE = re.compile(r"^t_?[a-z0-9_.-]+$")


class EvidenceInputError(ValueError):
    """Raised by ``validate()``: the inputs hold something an explainer may not see."""


@dataclass(frozen=True)
class Provenance:
    origin: str                       # ORIGINS
    n: int
    n_unit: str                       # N_UNITS
    split: str                        # SPLITS
    model_version: str                # "v1" | "v2"
    accepted: bool | None = None      # the pre-registered verdict against v1 (None = not applicable)
    pool: str = "none"                # POOLS: which data pool the numbers come from (d0, dev, heldout, mismatch, sim)
    interval_level: float = 0.95
    interval_adjusted: bool = False   # True when the intervals use a Bonferroni-adjusted level


@dataclass(frozen=True)
class HabitInput:
    habit_id: str                     # HABIT_IDS
    cog_ids: tuple[str, ...]          # pack cog ids the habit touches
    seconds: float                    # attributed by alignment (v1-style), seconds lost on this case or per case
    seconds_lo: float
    seconds_hi: float
    counterfactual_s: float | None    # seconds recovered if the habit were fixed (splice), or None when not computed
    counterfactual_lo: float | None
    counterfactual_hi: float | None
    n: int                            # cases behind the figures
    method: str = "alignment"         # METHODS: how counterfactual_s (or seconds) was obtained
    shapley_share: float | None = None  # this habit's Shapley share of the total recovered seconds (0..1), if computed


@dataclass(frozen=True)
class EnvelopeRow:
    cog_id: str
    novice_s: float                   # dwell of the person on this cog on this case
    expert_lo_s: float                # the experts' envelope for this cog (interval over experts)
    expert_hi_s: float
    attributed_s: float
    attributed_lo: float
    attributed_hi: float


@dataclass(frozen=True)
class HazardInput:
    p: float                          # probability of no progress in the next 60 s
    source: str                       # "model" | "rule"
    threshold: float | None           # the alarm threshold in force (None when no alarm rule applies)
    n_bins: int                       # scored bins behind the calibration figures
    ece: float | None
    log_loss: float | None
    base_rate_log_loss: float | None  # baseline: always predict the training base rate
    tsp_log_loss: float | None        # baseline: time since progress only
    false_alarms_per_hour: float | None
    fa_lo: float | None
    fa_hi: float | None
    budget_per_hour: float | None = 1.0
    calibration: str = "untested"     # CALIBRATION
    p_lo: float | None = None
    p_hi: float | None = None


@dataclass(frozen=True)
class TimeToProgress:
    expected_min: float               # restricted mean minutes until the next progress event (cap 5 min)
    lo: float | None
    hi: float | None
    c_index: float | None = None


@dataclass(frozen=True)
class CaseInput:
    person_id: str                    # an opaque id such as p_nov03, never a name
    task_id: str                      # an opaque id such as t_nov03a
    case_s: float                     # the person's total dwell seconds on this case
    reference_s: float                # the reference (expert) total dwell seconds
    gap_s: float
    gap_lo: float
    gap_hi: float
    habits: tuple[HabitInput, ...] = ()
    envelope: tuple[EnvelopeRow, ...] = ()
    hazard: HazardInput | None = None
    time_to_progress: TimeToProgress | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CohortInput:
    gap_s: float                      # mean novice-minus-reference seconds per case
    gap_lo: float
    gap_hi: float
    n: int
    n_unit: str = "people"


@dataclass(frozen=True)
class EvidenceInputs:
    provenance: Provenance
    cases: tuple[CaseInput, ...] = ()
    cohort: CohortInput | None = None
    hazard: HazardInput | None = None                 # cohort-level reading and held-out figures
    baselines: Mapping[str, float] = field(default_factory=dict)   # BASELINE_NAMES -> value (lower or higher is better as named)
    limitations: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    @property
    def model_version(self) -> str:
        return self.provenance.model_version

    @property
    def accepted(self) -> bool | None:
        return self.provenance.accepted

    def usable(self) -> bool:
        """False for a variant that failed its pre-registered acceptance test against v1 (the explainer should drop it)."""
        return self.provenance.accepted is not False

    def validate(self) -> "EvidenceInputs":
        _validate(self)
        return self

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


# ------------------------------------------------------------------------------------------------ validation
def _bad(path: str, msg: str):
    raise EvidenceInputError(f"{path}: {msg}")


def _check_num(path: str, v: Any, *, optional: bool = False, lo: float | None = None, hi: float | None = None) -> None:
    if v is None:
        if optional:
            return
        _bad(path, "missing number")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _bad(path, f"not a number: {type(v).__name__}")
    if not math.isfinite(float(v)):
        _bad(path, "not finite")
    if lo is not None and v < lo:
        _bad(path, f"{v} below {lo}")
    if hi is not None and v > hi:
        _bad(path, f"{v} above {hi}")


def _check_enum(path: str, v: Any, allowed: tuple[str, ...]) -> None:
    if v not in allowed:
        _bad(path, f"{v!r} is not one of {allowed}")


def _check_pair(path: str, lo: Any, hi: Any, *, optional: bool = False) -> None:
    if lo is None and hi is None and optional:
        return
    _check_num(path + ".lo", lo)
    _check_num(path + ".hi", hi)
    if lo > hi + 1e-9:
        _bad(path, f"lo {lo} above hi {hi}")


def _check_id(path: str, v: Any, pattern: re.Pattern) -> None:
    if not isinstance(v, str) or not pattern.match(v) or len(v) > 64:
        _bad(path, f"{v!r} is not a plain id")


def _validate_hazard(path: str, h: HazardInput | None) -> None:
    if h is None:
        return
    _check_num(path + ".p", h.p, lo=0.0, hi=1.0)
    _check_enum(path + ".source", h.source, HAZARD_SOURCES)
    _check_num(path + ".threshold", h.threshold, optional=True, lo=0.0, hi=1.5)
    _check_num(path + ".n_bins", h.n_bins, lo=0)
    for name in ("ece", "log_loss", "base_rate_log_loss", "tsp_log_loss", "false_alarms_per_hour", "fa_lo", "fa_hi", "budget_per_hour", "p_lo", "p_hi"):
        _check_num(f"{path}.{name}", getattr(h, name), optional=True, lo=0.0)
    _check_enum(path + ".calibration", h.calibration, CALIBRATION)


def _validate(x: EvidenceInputs) -> None:
    pv = x.provenance
    _check_enum("provenance.origin", pv.origin, ORIGINS)
    _check_enum("provenance.n_unit", pv.n_unit, N_UNITS)
    _check_enum("provenance.split", pv.split, SPLITS)
    _check_enum("provenance.pool", pv.pool, POOLS)
    _check_enum("provenance.model_version", pv.model_version, MODEL_VERSIONS)
    _check_num("provenance.n", pv.n, lo=0)
    _check_num("provenance.interval_level", pv.interval_level, lo=0.5, hi=1.0)
    if pv.accepted is not None and not isinstance(pv.accepted, bool):
        _bad("provenance.accepted", "must be True, False or None")
    if not isinstance(pv.interval_adjusted, bool):
        _bad("provenance.interval_adjusted", "must be a bool")
    for lid in x.limitations:
        _check_enum("limitations", lid, LIMITATION_IDS)
    for k, v in x.baselines.items():
        _check_enum("baselines key", k, BASELINE_NAMES)
        _check_num(f"baselines.{k}", v)
    if x.cohort is not None:
        c = x.cohort
        _check_num("cohort.gap_s", c.gap_s)
        _check_pair("cohort.gap", c.gap_lo, c.gap_hi)
        _check_num("cohort.n", c.n, lo=0)
        _check_enum("cohort.n_unit", c.n_unit, N_UNITS)
    _validate_hazard("hazard", x.hazard)
    for i, case in enumerate(x.cases):
        cp = f"cases[{i}]"
        _check_id(cp + ".person_id", case.person_id, _PERSON_RE)
        _check_id(cp + ".task_id", case.task_id, _TASK_RE)
        for name in ("case_s", "reference_s"):
            _check_num(f"{cp}.{name}", getattr(case, name), lo=0.0)
        _check_num(cp + ".gap_s", case.gap_s)
        _check_pair(cp + ".gap", case.gap_lo, case.gap_hi)
        for lid in case.limitations:
            _check_enum(cp + ".limitations", lid, LIMITATION_IDS)
        for j, h in enumerate(case.habits):
            hp = f"{cp}.habits[{j}]"
            _check_enum(hp + ".habit_id", h.habit_id, HABIT_IDS)
            for cog in h.cog_ids:
                _check_id(hp + ".cog_ids", cog, _COG_RE)
            _check_num(hp + ".seconds", h.seconds)
            _check_pair(hp + ".seconds", h.seconds_lo, h.seconds_hi)
            _check_num(hp + ".counterfactual_s", h.counterfactual_s, optional=True)
            _check_pair(hp + ".counterfactual", h.counterfactual_lo, h.counterfactual_hi, optional=h.counterfactual_s is None)
            _check_num(hp + ".n", h.n, lo=0)
            _check_enum(hp + ".method", h.method, METHODS)
            _check_num(hp + ".shapley_share", h.shapley_share, optional=True, lo=-1.0, hi=1.0)
        for j, e in enumerate(case.envelope):
            ep = f"{cp}.envelope[{j}]"
            _check_id(ep + ".cog_id", e.cog_id, _COG_RE)
            for name in ("novice_s", "expert_lo_s", "expert_hi_s"):
                _check_num(f"{ep}.{name}", getattr(e, name), lo=0.0)
            _check_num(ep + ".attributed_s", e.attributed_s)
            _check_pair(ep + ".attributed", e.attributed_lo, e.attributed_hi)
        _validate_hazard(cp + ".hazard", case.hazard)
        if case.time_to_progress is not None:
            t = case.time_to_progress
            _check_num(cp + ".time_to_progress.expected_min", t.expected_min, lo=0.0)
            _check_pair(cp + ".time_to_progress", t.lo, t.hi, optional=True)
            _check_num(cp + ".time_to_progress.c_index", t.c_index, optional=True, lo=0.0, hi=1.0)


def _to_dict(o: Any) -> Any:
    if is_dataclass(o) and not isinstance(o, type):
        return {f.name: _to_dict(getattr(o, f.name)) for f in fields(o)}
    if isinstance(o, (list, tuple)):
        return [_to_dict(v) for v in o]
    if isinstance(o, Mapping):
        return {str(k): _to_dict(v) for k, v in o.items()}
    return o


def sorted_habits(habits: list[HabitInput]) -> tuple[HabitInput, ...]:
    """Largest counterfactual (else attributed) seconds first."""
    return tuple(sorted(habits, key=lambda h: -(h.counterfactual_s if h.counterfactual_s is not None else h.seconds)))


def build(person: str, case: str | None = None, **kw) -> EvidenceInputs:
    """Alias of ``understudy_engine.mlv2.evidence_builder.build_for(person, case, ...)`` (imported lazily so this module stays dependency-free)."""
    from understudy_engine.mlv2.evidence_builder import build_for

    return build_for(person, case, **kw)
