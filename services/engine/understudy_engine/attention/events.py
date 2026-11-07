"""The event a producer submits, and the item the layer keeps (REQ-8). Closed vocabularies, ids and enums only.

An event carries no text from any screen, file, page or model: a type from a closed enum, the person slug, an opaque subject id (the
run, the queue item, the card, the episode, the routine: whatever the event is about), an op, a few enums and small numbers. The
parser refuses an unknown field, a value outside its enum or pattern, and a number out of range. It is the same contract as
``packages/schema/attention_event.schema.json`` (a test checks the two agree).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from . import vocab as V

SUBJECT_RE = re.compile(V.SubjectPattern)
PERSON_RE = re.compile(V.PersonPattern)
FIELDS = ("type", "person", "subject", "op", "t", "risk_class", "outcome", "run_mode", "service", "count", "minutes", "expires_in_s",
          "deadline_in_s", "blocks_run", "asked", "origin", "state")
STATE_FIELDS = ("typing_burst", "quiet_s", "deep_work", "task_in_progress", "task_marker_s", "away", "away_s", "locked", "dnd", "screen_sharing",
                "on_call", "in_meeting", "voice_session", "dashboard_focused", "local_hour", "t")


class EventError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Event:
    type: str
    person: str
    subject: str
    op: str = "raise"
    t: float | None = None                  # taken-at, the producer's clock (replays and simulation); production uses the server clock
    risk_class: str | None = None
    outcome: str | None = None
    run_mode: str | None = None
    service: str | None = None
    count: int = 1
    minutes: float | None = None
    expires_in_s: float | None = None
    deadline_in_s: float | None = None
    blocks_run: bool = False
    asked: bool = False                     # the worker pressed for help (Cue): the quiet, budget and learning rules do not apply to it
    origin: str = "real"

    @property
    def family(self) -> str:
        return V.TYPES[self.type].family

    @property
    def dedup_key(self) -> str:
        return f"{self.family}:{self.subject}"

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in FIELDS if k not in ("state",) and getattr(self, k) is not None}


def _enum(d: dict[str, Any], key: str, allowed: tuple[str, ...], default: str | None = None) -> str | None:
    v = d.get(key, default)
    if v is None:
        return None
    if v not in allowed:
        raise EventError("invalid_event", f"{key} must be one of {', '.join(allowed)}.")
    return v


def _num(d: dict[str, Any], key: str, lo: float, hi: float) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise EventError("invalid_event", f"{key} must be a number.")
    if not lo <= float(v) <= hi:
        raise EventError("invalid_event", f"{key} must be between {lo:g} and {hi:g}.")
    return float(v)


def parse_event(d: Any, *, person: str | None = None) -> Event:
    """Validate and normalise one event. Raises ``EventError``; never returns a partially valid event."""
    if not isinstance(d, dict):
        raise EventError("invalid_event", "An event is a JSON object.")
    extra = sorted(set(d) - set(FIELDS))
    if extra:
        raise EventError("invalid_event", f"Unknown field {extra[0]!r}. An event carries ids and enums only.")
    typ = d.get("type")
    if typ not in V.SUBMITTABLE:
        raise EventError("invalid_event", f"type must be one of {', '.join(V.SUBMITTABLE)}.")
    pid = d.get("person", person)
    if not isinstance(pid, str) or not PERSON_RE.fullmatch(pid):
        raise EventError("invalid_event", "person must be a slug such as p_ada.")
    subject = d.get("subject")
    if not isinstance(subject, str) or not SUBJECT_RE.fullmatch(subject):
        raise EventError("invalid_event", "subject must be an opaque id of letters, digits and _ . : - (at most 64 characters).")
    op = _enum(d, "op", V.OPS, "raise")
    count = d.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 999:
        raise EventError("invalid_event", "count must be a whole number from 1 to 999.")
    for k in ("blocks_run", "asked"):
        if k in d and not isinstance(d[k], bool):
            raise EventError("invalid_event", f"{k} must be true or false.")
    ev = Event(type=typ, person=pid, subject=subject, op=op or "raise", t=_num(d, "t", 0.0, 4e9),
               risk_class=_enum(d, "risk_class", V.RISK_CLASSES), outcome=_enum(d, "outcome", V.OUTCOMES),
               run_mode=_enum(d, "run_mode", V.RUN_MODES), service=_enum(d, "service", V.SERVICES), count=count,
               minutes=_num(d, "minutes", 0.0, 1440.0), expires_in_s=_num(d, "expires_in_s", 1.0, 604800.0),
               deadline_in_s=_num(d, "deadline_in_s", 0.0, 2678400.0), blocks_run=bool(d.get("blocks_run", False)),
               asked=bool(d.get("asked", False)), origin=_enum(d, "origin", V.ORIGINS, "real") or "real")
    if typ == "service_degraded" and ev.service is None:
        raise EventError("invalid_event", "service_degraded needs a service.")
    if typ == "calendar_deadline" and ev.deadline_in_s is None:
        raise EventError("invalid_event", "calendar_deadline needs deadline_in_s.")
    if typ == "approval_waiting" and ev.blocks_run:
        ev = replace(ev, type="approval_blocking")           # a job waits on it: it is the time-sensitive kind
    if ev.asked and V.TYPES[ev.type].cls != V.HELPFUL:
        ev = replace(ev, asked=False)                          # only a cue can be asked for
    return ev


@dataclass
class Item:
    """One thing the worker may be told, and where it is in its life. Metadata only."""
    id: str
    person: str
    type: str
    subject: str
    dedup_key: str
    first_t: float
    expires_at: float
    state: str = "held"
    count: int = 1
    occurrences: int = 1
    op: str = "raise"
    risk_class: str | None = None
    outcome: str | None = None
    run_mode: str | None = None
    service: str | None = None
    minutes: float | None = None
    blocks_run: bool = False
    asked: bool = False
    origin: str = "real"
    channel: str = "log"
    deliver_at: str = "now"
    reason_code: str = ""
    interrupted: bool = False             # a toast, chip, card or voice line was actually shown
    shown_t: float | None = None
    until: float | None = None            # the display (and lock) ends here
    reminders: int = 0
    reminded_t: float | None = None
    prev_interruption_t: float | None = None   # the spacing clock before this item was shown, so a deferral can give it back
    prev_budget: list[int] = field(default_factory=list)   # [budget_used, wait_toasts] before it was shown
    reacted: str | None = None            # the implicit label the worker's reaction produced
    labelled: bool = False
    folded_into: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)      # a digest's counts (numbers and enums)
    needs_you_n: int = 0
    transitions: list[list[Any]] = field(default_factory=list)  # [t, state, reason_code], capped

    @property
    def family(self) -> str:
        return V.TYPES[self.type].family

    @property
    def spec(self) -> V.TypeSpec:
        return V.TYPES[self.type]

    @classmethod
    def from_event(cls, ev: Event, item_id: str, now: float) -> Item:
        sp = V.TYPES[ev.type]
        t0 = ev.t if ev.t is not None else now
        ttl = sp.ttl_s
        if ev.type == "calendar_deadline" and ev.deadline_in_s is not None:
            life = ev.deadline_in_s
        else:
            life = ev.expires_in_s if ev.expires_in_s is not None else ttl
        life = max(1.0, min(life, ttl if ev.type != "calendar_deadline" else 2678400.0))
        return cls(id=item_id, person=ev.person, type=ev.type, subject=ev.subject, dedup_key=ev.dedup_key, first_t=t0, expires_at=t0 + life,
                   count=ev.count, op=ev.op, risk_class=ev.risk_class, outcome=ev.outcome, run_mode=ev.run_mode, service=ev.service,
                   minutes=ev.minutes, blocks_run=ev.blocks_run, asked=ev.asked, origin=ev.origin)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Item:
        keys = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in keys})

    def note(self, t: float, state: str, reason: str) -> None:
        self.transitions.append([round(t, 3), state, reason])
        if len(self.transitions) > 14:
            del self.transitions[1:3]
