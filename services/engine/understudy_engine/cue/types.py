"""Shared types for Cue: enums as tuples, the CueDecision the desktop consumes, and the inputs the decision gate reads.

Everything that can reach the screen, the ledger or an API response is an id from the pack's vocabulary, an enum, a number or a
fixed template text. There is no free-text field anywhere in this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

KINDS = ("none", "confirm", "cue", "ask", "offer")
SOURCES = ("dom", "vision", "none")
STREAMS = ("assist", "delegated", "automation")
TRIGGERS = ("none", "auto", "asked")
OUTCOMES = ("clean", "assisted", "error", "abandoned")
FEEDBACK_EVENTS = ("shown", "accepted", "dismissed", "answered", "resolved", "abandoned", "know_this")
OTHER = "other"                       # the fixed "something else" option of a question
STUCK_BUCKETS = ("p00_59", "p60_79", "p80_94", "p95_100")

# Every reason id the gate may put in ``why.reasons``. A test checks the gate never emits an id outside this list.
REASONS = (
    # silence
    "no_consent", "denied", "quiet", "flow", "level_4", "not_stuck", "wait_signals", "unsure_away", "below_stall_min",
    "cap_10min", "cooldown_skill", "budget_spent", "waiting_escalation", "deferred", "dismissed_in_episode", "know_this",
    "no_candidates", "no_context", "progress", "ladder_done", "ambiguous_after_question", "no_target_for_tier",
    "recovered", "timeout",
    # why something is shown
    "stuck_signal", "asked", "escalated", "retrieval_withheld", "path_confident", "path_close_call",
    "grounded_dom", "grounded_vision", "ungrounded", "screen_disagrees", "answer_known", "long_stall",
    "level_1", "level_2", "level_3", "voice_capped", "persisting",
)


@dataclass(frozen=True)
class Candidate:
    """One next step the expert path and the pack's order rules allow. Pack vocabulary only: an id, a short label, a number."""

    id: str                     # the specific step (the first not-yet-started one of an interchangeable group)
    group: str                  # representative id of the interchangeable group (calc_a for calc_a/b/c)
    label: str                  # short pack label
    p: float                    # probability among the allowed next steps
    skill: str                  # the pack's skill id for the step (falls back to the step id)
    reason_id: str | None = None
    cogs: tuple[str, ...] = ()
    in_progress: bool = False   # the worker is part-way through this step

    def to_dict(self) -> dict:
        return {"id": self.id, "group": self.group, "label": self.label, "p": round(self.p, 4), "skill": self.skill,
                "reason_id": self.reason_id, "in_progress": self.in_progress}


@dataclass(frozen=True)
class Grounding:
    """What the grounding port returned: enums, ids, a box and a confidence. Never pixels, never text from the screen."""

    found: bool = False
    chosen: str | None = None                    # a menu id (step id) or None
    available: tuple[str, ...] = ()              # menu ids visible on screen
    box_2d: tuple[int, int, int, int] | None = None    # [y0, x0, y1, x1] on 0..1000
    confidence: float = 0.0
    source: str = "none"                         # dom | vision | none
    for_step: str | None = None                  # the top candidate the caller asked about (to notice a stale result)
    t: float | None = None                       # unix seconds the result was produced


@dataclass(frozen=True)
class CueInput:
    """Everything the decision gate reads. Booleans for consent and the denylist are passed in; nothing here is looked up."""

    now: float
    person: str
    role: str
    p_stuck: float
    p_source: str                                # "model" | "rule"
    last_progress_t: float                       # unix seconds of the last progress event (or the task start)
    candidates: tuple[Candidate, ...]            # sorted, best first
    level: int = 2                               # help level 1..4 of the top step's skill
    mastery: float = 0.0                         # mastery of the top step's skill, 0..1
    grounding: Grounding | None = None
    quiet_s: float = 10.0                        # seconds since the last keyboard or pointer input
    typing_burst: bool = False
    away: bool = False                           # locked, idle, on a call or screen-sharing: the worker is not at the screen
    consent: bool = True
    denied: bool = False                         # denylisted app or secure input: never bypassed, not even when asked
    quiet_hour: bool = False
    asked: bool = False                          # the worker pressed the hotkey or the ask button for this poll
    voice_ok: bool = False                       # the worker used voice or asked for it: only then may a whisper exist
    retrieval_due: bool = False                  # teach and fade: withhold help for this step, confirm afterwards

    @property
    def stall_s(self) -> float:
        return max(0.0, self.now - self.last_progress_t)


@dataclass
class CueDecision:
    kind: str = "none"
    episode_id: str | None = None
    tier: int | None = None
    step: dict | None = None                     # {id, label, reason_id}
    target: dict | None = None                   # {box_2d, source, confidence}
    options: list[dict] | None = None            # [{id, label}] (2..4 steps plus the fixed "something else")
    say: dict | None = None                      # {chip: <=40 chars | None, whisper: <=8 words | None}
    why: dict = field(default_factory=dict)      # {path_prob, margin, p_stuck, mastery, level, reasons: [enum ids]}
    budget_left: int = 0
    cooldown_s: float = 0.0
    source: str = "rule"                         # the stuck signal: "model" | "rule"
    meta: dict = field(default_factory=dict)
    # additive fields (agreed with CUE-UX, the old parser ignores them)
    new: bool = False                            # true on the poll where this tier first appears
    question: dict | None = None                 # {type, text}: a fixed template, never model-written
    expires_in_s: float | None = None
    retrieval: bool = False
    ground_wanted: bool = False
    teach: dict | None = None                    # {reason_id, text}: the one-line why, on the poll that sees the step finished (once per skill per day)
    menu: list[dict] | None = None               # [{id, label}] the candidate steps: the menu a grounding call wants (with ground_wanted)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
