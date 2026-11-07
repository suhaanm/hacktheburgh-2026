"""Every threshold the decision gate uses, in one frozen dataclass (CUE-3). Nothing here is learned at run time.

``DEFAULT`` holds the values fixed before any dev replicate was looked at. ``TUNED`` (bottom of the file) is the result of the one
tuning pass on the dev replicates (``cue.evaluate.tune_on_dev``); the held-out replicates never touch it. The hard caps are not
tunable by the tuner: ``max_cues_window``, ``cap_window_s``, ``max_questions``, ``skill_gap_s`` and ``escalate_s`` are design
constants from the brief.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace


@dataclass(frozen=True)
class CueParams:
    # the stuck signal (reuses the dignity gate: need consecutive signals at or above p_signal)
    p_signal: float = 0.60
    need: int = 2
    # flow: never interrupt typing; require this much quiet first
    quiet_required_s: float = 2.0
    # minimum stall (seconds since the last progress event) before a cue, by help level; scaled up with mastery
    stall_min_l1: float = 15.0
    stall_min_l2: float = 20.0
    stall_min_l3: float = 45.0
    mastery_patience: float = 1.0
    # hard anti-spam caps (design constants)
    max_cues_window: int = 3
    cap_window_s: float = 600.0
    skill_gap_s: float = 90.0
    max_questions: int = 1
    max_offers: int = 1
    daily_budget: int = 12
    # tiers
    escalate_s: float = 25.0
    display_s: float = 12.0
    start_tier_l1: int = 2
    start_tier_l2: int = 1
    start_tier_l3: int = 1
    # the offer ("want a hand?") only after a long stall
    offer_after_s: float = 90.0
    # ambiguity and grounding
    margin_thr: float = 0.15
    min_path_p: float = 0.30
    confident_p: float = 0.50
    ground_conf_thr: float = 0.70
    # misc
    defer_s: float = 10.0
    episode_timeout_s: float = 600.0
    know_this_hold_s: float = 300.0

    def stall_min(self, level: int, mastery: float) -> float:
        base = {1: self.stall_min_l1, 2: self.stall_min_l2}.get(int(level), self.stall_min_l3)
        return base * (1.0 + self.mastery_patience * max(0.0, min(1.0, mastery)))

    def start_tier(self, level: int) -> int:
        return {1: self.start_tier_l1, 2: self.start_tier_l2}.get(int(level), self.start_tier_l3)

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "CueParams":
        return replace(self, **kw)


FIELD_NAMES = tuple(f.name for f in fields(CueParams))
DEFAULT = CueParams()
# Hard caps no tuner may change.
HARD_CAPS = ("max_cues_window", "cap_window_s", "max_questions", "skill_gap_s", "escalate_s", "max_offers")
# TUNED is the result of the one dev-only tuning pass of evals/cue/PLAN.md (15 configurations, dev population seed 11, replicate seeds 0 to 4,
# 40 workers): the highest net seconds saved per hour among those whose dev false-nudge 97.5% upper bound was at most 1.0 an hour.
# p_signal 0.30 saved a little more (25.8 against 23.9 seconds an hour) but its upper bound was 1.01. ``margin_thr`` made no difference to
# any dev number (questions are rare when the path prior is confident), so 0.10 is the first of three identical rows, not a finding.
TUNED = DEFAULT.with_(p_signal=0.40, margin_thr=0.10)
