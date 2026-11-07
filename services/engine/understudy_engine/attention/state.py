"""The router's inputs besides the event: the worker's state, the fixed parameters, the worker's settings and the history (REQ-8).

All three are plain values. The router reads them and nothing else, so one decision is a pure function of (event, worker state,
history, parameters): the same inputs give the same answer on any day, which is what the tests and the simulated workday rely on.

``WorkerState`` is built by the desktop adapter from signals the awareness layer already has (input rhythm, presence, the worker's quiet
hotkey, screen-share and call probes, the calendar layer's meeting flag). None of it is content. A reading older than ``state_max_age_s``
is treated as unknown (the freshness table's ``worker_state`` row: 10 s), and an unknown worker is held, never interrupted, except for
safety, which is never held.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from . import vocab as V

HARD_QUIET_ORDER = ("dnd", "screen_sharing", "on_call", "in_meeting")


@dataclass(frozen=True)
class Params:
    """Every number the router uses. ``HARD`` values are design constants no tuning pass may change; the rest were fixed before any run
    and may be tuned on the development seeds only (evals/attention/PLAN.md)."""
    # HARD constants
    max_reminders: int = 1
    # spacing and budget
    budget_per_day: int = 10
    min_gap_s: float = 90.0
    wait_toasts_per_day: int = 3
    loud_budget_mult: float = 1.5
    quiet_budget_mult: float = 0.5
    # flow
    flow_quiet_s: float = 2.0
    max_hold_soft_s: float = 600.0
    # natural break (the first three are proposals.ts DEFAULT_RULES)
    break_after_task_quiet_s: float = 3.0
    break_after_task_window_s: float = 90.0
    break_idle_quiet_s: float = 15.0
    break_midtask_quiet_s: float = 90.0
    return_window_s: float = 120.0
    # reminders
    reminder_after_s: float = 1200.0
    reminder_after_loud_s: float = 600.0
    deadline_reminder_min_s: float = 600.0
    # the 2 s level glance
    level_glance_per_hour: int = 2
    # learning
    n_min: float = 6.0
    quiet_thr1: float = 0.25
    quiet_thr2: float = 0.12
    label_window: int = 60
    never_subjects_for_max: int = 3
    # worker state freshness (the shared freshness table's row)
    state_max_age_s: float = 10.0
    # digest
    welcome_away_s: float = 1800.0
    morning_away_s: float = 14400.0
    morning_hour_lo: int = 4
    morning_hour_hi: int = 12
    digest_gap_s: float = 10800.0
    digest_max_lines: int = 7
    needs_max_lines: int = 5

    def reminder_after(self, mode: str) -> float | None:
        return {"loud": self.reminder_after_loud_s, "normal": self.reminder_after_s}.get(mode)


DEFAULT = Params()
HARD = ("max_reminders",)


@dataclass(frozen=True)
class Settings:
    """What the worker chose. Defaults are the balanced first-day setting."""
    modes: Mapping[str, str] = field(default_factory=dict)
    budget_per_day: int = DEFAULT.budget_per_day
    level_glance: bool = True

    def mode(self, type_id: str) -> str:
        if V.TYPES[type_id].cls == V.SAFETY:
            return "normal"                         # safety ignores every mode: the table has the same row in all four
        return self.modes.get(type_id, "normal")

    def to_dict(self) -> dict[str, Any]:
        return {"modes": dict(self.modes), "budget_per_day": self.budget_per_day, "level_glance": self.level_glance}


@dataclass(frozen=True)
class WorkerState:
    now: float
    known: bool = True                      # False when nothing was read, or the reading is stale: the worker is unknown
    t: float | None = None                  # when the reading was taken (the freshness convention)
    typing_burst: bool = False
    quiet_s: float = 60.0                   # seconds since the last input
    deep_work: bool = False                 # at least 25 minutes of continuous activity without a break (the adapter decides)
    task_in_progress: bool = False
    task_marker_s: float | None = None      # seconds since the last task or episode end
    away: bool = False
    away_s: float = 0.0
    locked: bool = False
    dnd: bool = False                       # the worker's own quiet hotkey or quiet-until time
    screen_sharing: bool = False
    on_call: bool = False
    in_meeting: bool = False                # from the calendar layer when it is on; else always False
    voice_session: bool = False
    dashboard_focused: bool = False
    local_hour: int = 12
    # derived by the service from the presence it has seen (never sent by a client)
    returned_s: float | None = None         # seconds since the worker came back from an absence, or since the first activity of the day
    day: str = ""

    def hard_quiet(self) -> str | None:
        if not self.known:
            return None
        for name in HARD_QUIET_ORDER:
            if getattr(self, name):
                return name
        return None

    @property
    def absent(self) -> bool:
        return self.away or self.locked


_BOOLS = ("typing_burst", "deep_work", "task_in_progress", "away", "locked", "dnd", "screen_sharing", "on_call", "in_meeting", "voice_session",
          "dashboard_focused")
_FLOATS = ("quiet_s", "away_s", "task_marker_s")
_TRUE = ("1", "true", "yes", "on")


def parse_state(q: Mapping[str, Any], now: float, p: Params = DEFAULT) -> WorkerState:
    """A worker state from query parameters or a JSON object. No parameter at all means unknown; a stale ``t`` means unknown."""
    def b(v: Any) -> bool:
        return v if isinstance(v, bool) else str(v).strip().lower() in _TRUE

    given = [k for k in _BOOLS + _FLOATS + ("local_hour",) if q.get(k) is not None]
    kw: dict[str, Any] = {}
    for k in _BOOLS:
        if q.get(k) is not None:
            kw[k] = b(q[k])
    for k in _FLOATS:
        if q.get(k) is not None:
            try:
                kw[k] = max(0.0, float(q[k]))
            except (TypeError, ValueError):
                pass
    if q.get("local_hour") is not None:
        try:
            kw["local_hour"] = int(float(q["local_hour"])) % 24
        except (TypeError, ValueError):
            pass
    taken = None
    if q.get("t") is not None:
        try:
            taken = float(q["t"])
        except (TypeError, ValueError):
            taken = None
    known = bool(given) and not (taken is not None and now - taken > p.state_max_age_s)
    return WorkerState(now=now, known=known, t=taken, **kw)


@dataclass(frozen=True)
class Lock:
    """The one-voice lock as the engine tracks it: whatever is on screen holds it until its display ends or it gets a reaction."""
    item_id: str
    owner: str                              # safety | asked | decision | cue | notice | glance
    family_key: str                         # the dedup key of the holder: the same key continues, another waits
    until: float


Learned = Callable[[str, int], int]


def _no_learning(_type: str, _hour: int) -> int:
    return 0


@dataclass
class History:
    """Read-only to the router (the service builds a fresh one for each decision from its store)."""
    day: str = ""
    budget_used: int = 0
    wait_toasts: int = 0
    last_interruption_t: float | None = None
    level_glances: tuple[float, ...] = ()
    lock: Lock | None = None
    settings: Settings = field(default_factory=Settings)
    never_subjects: frozenset[str] = frozenset()
    learned_drop: Learned = _no_learning
    level_glance_env_off: bool = False
