"""The fixed lines Understudy may speak, and the code that turns a line id plus typed slots into text.

Why this exists (REVIEW-PRIVACY, P1b): the voice route used to take up to 4000 characters of ANY text and post it to a third-party
speech service. A person's name passes a pattern filter. So the caller no longer sends text at all. It names a line:

    {"line_id": "briefing.overnight", "slots": {"runs": 2, "review": 1}}

and THIS module, in code, produces the sentence. A slot is a bounded integer or one id from a closed set; a free string is never a slot.
What can be spoken is therefore a closed set we wrote, plus numbers: it cannot carry a name, an address, a case figure or anything
read off a screen. The personal-data filter in ``tts.py`` stays as a second layer on the finished sentence.

Three families:
  coach.*     short fixed coach lines (a nudge after a step, a reassurance).
  briefing.*  the morning briefing and the overnight-run report: fixed templates with counts.
  question.*  the spoken form of Cue's fixed question templates.
  whisper.<step_id>   "Next, <the pack's short label>" for a step of a shipped pack. The label is pack text we authored; the id must
              name a step that exists in a pack, and the wording rule is the engine's (``cue.vocab.whisper_text``), re-implemented
              here when the engine module cannot be imported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Kind = Literal["nudge", "briefing"]

LINE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
MAX_SLOTS = 8


class LineError(ValueError):
    """The line id or its slots are not acceptable. ``code`` is a closed set; the message never contains the offending value."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IntSlot:
    lo: int = 0
    hi: int = 999

    def check(self, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int) or not (self.lo <= v <= self.hi):
            raise LineError("bad_slot", f"the slot must be a whole number from {self.lo} to {self.hi}")
        return v

    def describe(self) -> dict[str, Any]:
        return {"type": "int", "min": self.lo, "max": self.hi}


@dataclass(frozen=True)
class EnumSlot:
    """One id from a closed set; the sentence uses the mapped words, never the id the caller sent."""

    choices: dict[str, str] = field(default_factory=dict)

    def check(self, v: Any) -> str:
        if not isinstance(v, str) or v not in self.choices:
            raise LineError("bad_slot", "the slot must be one of the listed ids")
        return self.choices[v]

    def describe(self) -> dict[str, Any]:
        return {"type": "enum", "ids": sorted(self.choices)}


Slot = IntSlot | EnumSlot


@dataclass(frozen=True)
class Line:
    id: str
    kind: Kind
    render: Callable[[dict[str, Any]], str]
    slots: dict[str, Slot] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolved:
    line_id: str
    text: str
    kind: Kind


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _fixed(line_id: str, kind: Kind, text: str) -> Line:
    return Line(line_id, kind, lambda _s, t=text: t)


_LINES: dict[str, Line] = {}


def _add(line: Line) -> None:
    _LINES[line.id] = line


# ---------------------------------------------------------------------------------------------------- coach lines
for _id, _text in {
    "coach.nice_work": "Nice work on that step.",
    "coach.take_breath": "Take a breath. You are doing well.",
    "coach.look_again": "Take another look at the screen.",
    "coach.one_step": "One step at a time.",
    "coach.almost": "Almost there.",
    "coach.ask_me": "Press the talk key if you want a hand.",
    "coach.well_done": "That is done. Well done.",
}.items():
    _add(_fixed(_id, "nudge", _text))

# ---------------------------------------------------------------------------------------------------- briefing and reports
_add(_fixed("briefing.quiet", "briefing", "Good morning. Nothing ran overnight."))
_add(_fixed("report.all_clear", "briefing", "Everything ran cleanly."))
_add(_fixed("report.run_stopped", "briefing", "A routine stopped and is waiting for you."))
_add(
    Line(
        "briefing.overnight",
        "briefing",
        lambda s: f"Good morning. {plural(s['runs'], 'routine')} ran overnight and {s['review']} {'needs' if s['review'] == 1 else 'need'} your review.",
        {"runs": IntSlot(0, 999), "review": IntSlot(0, 999)},
    )
)
_add(
    Line(
        "briefing.saved",
        "briefing",
        lambda s: f"Good morning. {plural(s['runs'], 'routine')} ran overnight, saving about {plural(s['minutes'], 'minute')}.",
        {"runs": IntSlot(0, 999), "minutes": IntSlot(0, 9999)},
    )
)
_add(
    Line(
        "briefing.review",
        "briefing",
        lambda s: f"{plural(s['review'], 'item')} {'needs' if s['review'] == 1 else 'need'} your review.",
        {"review": IntSlot(0, 999)},
    )
)
_add(
    Line(
        "report.run_done",
        "briefing",
        lambda s: f"{plural(s['runs'], 'routine')} finished and {s['review']} {'needs' if s['review'] == 1 else 'need'} your review.",
        {"runs": IntSlot(0, 999), "review": IntSlot(0, 999)},
    )
)
_add(
    Line(
        "briefing.greeting",
        "briefing",
        lambda s: f"Good {s['part']}.",
        {"part": EnumSlot({"morning": "morning", "afternoon": "afternoon", "evening": "evening"})},
    )
)

# ---------------------------------------------------------------------------------------------------- the engine's own tables (read-only)
_FALLBACK_QUESTIONS = {
    "close_call": "Which of these is next?",
    "screen_disagrees": "I can see more than one option. Which is next?",
    "unclear": "I cannot tell where you are. What is next?",
}


def _questions() -> dict[str, str]:
    try:
        from understudy_engine.cue.vocab import QUESTIONS

        return dict(QUESTIONS)
    except Exception:  # the engine module is optional here; the same three questions are fixed below
        return dict(_FALLBACK_QUESTIONS)


_ROLES = ("benefits-processor", "programmer", "data-analyst")
_WHISPER_WORDS = 8
_LABEL_MAX = 32


def _short(label: str, limit: int = _LABEL_MAX) -> str:
    label = re.sub(r"\s+", " ", label.strip())
    if len(label) <= limit:
        return label
    return label[:limit].rsplit(" ", 1)[0] or label[:limit]


def _whisper_text(label: str) -> str:
    return "Next, " + " ".join(_short(label).split()[: _WHISPER_WORDS - 3])


def _pack_labels() -> dict[str, str]:
    """step id -> the pack's short label, for the shipped packs. Empty when the engine's pack loader is not importable."""
    out: dict[str, str] = {}
    try:
        from understudy_engine.cue.vocab import get_vocab

        for role in _ROLES:
            v = get_vocab(role)
            if v is None:
                continue
            for step_id in v.policy.steps:
                out.setdefault(step_id, v.label(step_id))
    except Exception:
        return out
    return out


# ---------------------------------------------------------------------------------------------------- public API
def get_line(line_id: str) -> Line | None:
    if not isinstance(line_id, str) or len(line_id) > 90 or not LINE_ID_RE.match(line_id):
        return None
    line = _LINES.get(line_id)
    if line is not None:
        return line
    family, _, rest = line_id.partition(".")
    if family == "question":
        text = _questions().get(rest)
        return _fixed(line_id, "nudge", text) if text else None
    if family == "whisper":
        label = _pack_labels().get(rest)
        return _fixed(line_id, "nudge", _whisper_text(label)) if label else None
    return None


def resolve(line_id: Any, slots: Any = None) -> Resolved:
    """Line id + slots -> the sentence. Raises LineError for an unknown id, a missing, extra or out-of-range slot."""
    if not isinstance(line_id, str):
        raise LineError("unknown_line", "line_id must be a string")
    line = get_line(line_id)
    if line is None:
        raise LineError("unknown_line", "that line id is not one of the fixed lines")
    given = {} if slots is None else slots
    if not isinstance(given, dict) or len(given) > MAX_SLOTS:
        raise LineError("bad_slots", "slots must be an object with a few entries")
    extra = [k for k in given if k not in line.slots]
    if extra:
        raise LineError("unknown_slot", "that line does not take that slot")
    values: dict[str, Any] = {}
    for name, spec in line.slots.items():
        if name not in given:
            raise LineError("missing_slot", "a required slot is missing")
        values[name] = spec.check(given[name])
    return Resolved(line_id, line.render(values), line.kind)


def catalogue() -> list[dict[str, Any]]:
    """Every fixed line id with the shape of its slots (no text), for a client that wants to know what it may ask for."""
    rows = [{"line_id": l.id, "kind": l.kind, "slots": {k: s.describe() for k, s in l.slots.items()}} for l in _LINES.values()]
    rows += [{"line_id": f"question.{k}", "kind": "nudge", "slots": {}} for k in _questions()]
    rows += [{"line_id": f"whisper.{k}", "kind": "nudge", "slots": {}} for k in _pack_labels()]
    return sorted(rows, key=lambda r: r["line_id"])
