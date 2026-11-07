"""The vetted coach menu (REQ-6): advice is chosen from this list, never written by a model.

A model may pick up to two ids from the menu (the same idea as the agent runtime's menu-mode planner); code checks that each id
applies to the packet, resolves it to the text below and fills in numbers from the packet. A model never writes advice, so a
sentence like "you should do X" in a model reply is rejected by the provenance check (``unvetted_advice``).

Every action is ordinary, low-stakes coaching about how to work; none starts anything. ``review_routine`` and
``keep_shadow_going`` only point at the routine screen: nothing runs without the worker's own press.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import vocab as V
from .numbers import render
from .packet import EvidencePacket


@dataclass(frozen=True)
class Action:
    id: str
    text: str                              # may hold {x}: the habit's seconds (or the named figure) as spoken by code
    habit: str | None = None               # the habit this action addresses
    figure: str | None = None              # packet path of the figure {x} is filled from


ACTIONS: dict[str, Action] = {a.id: a for a in (
    Action("keep_pace_with_reference", "On steps you already know, follow the nearest expert's pace; a slower pace on shared steps is associated with {x} here.",
           "pace", "habit.pace.seconds"),
    Action("prepare_before_entering", "Before you start entering the household, open everything you need so the entry runs without a stop; long pauses are associated with {x} here.",
           "pauses", "habit.pauses.seconds"),
    Action("search_once_then_stop", "When a search does not give what you need, change one thing in it and try once more rather than searching again and again; search loops are associated with {x} here.",
           "search_loops", "habit.search_loops.seconds"),
    Action("read_each_result_once", "Read each calculator's result once and note the figure before you move on; repeated reads are associated with {x} here.",
           "repeated_reads", "habit.repeated_reads.seconds"),
    Action("run_cliff_check", "After entering a household, run the cliff check before you copy any figure; a missed check that was redone is associated with {x} here.",
           "missed_check", "habit.missed_check.seconds"),
    Action("compare_copied_figure", "After copying a figure into the case note, compare it with its source before you move on; copying a wrong figure again is associated with {x} here.",
           "wrong_copy", "habit.wrong_copy.seconds"),
    Action("ask_before_redoing", "If you are about to redo a step, ask for the expert's next step first; rework is associated with {x} here.",
           "rework", "habit.rework.seconds"),
    Action("keep_every_step", "Do each step in the expert's order, including the checks: skipping a step can look like saved time, and the error rates above say what it can cost.",
           "step_skips", None),
    Action("ask_for_next_step", "If you stay on the same step for a while, ask for the next step; the stuck reading here reached {x}.", None, "hazard.peak_p"),
    Action("review_routine", "Look at the suggested routine and decide whether to let it run on its own; nothing runs until you say so.", None, None),
    Action("keep_shadow_going", "Keep the routine in shadow mode a little longer; it has not yet earned your approval.", None, None),
    Action("keep_going", "Nothing stands out in this data, so keep working as you are.", None, None),
)}
assert set(ACTIONS) == set(V.MENU_IDS)

_BY_HABIT = {a.habit: a.id for a in ACTIONS.values() if a.habit}
MIN_SECONDS = 3.0         # a habit smaller than this is not worth an action


def _applies(pk: EvidencePacket) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for hid, h in pk.habits.items():
        if hid in _BY_HABIT and hid != "step_skips" and h.seconds >= MIN_SECONDS:
            out.append((h.seconds, _BY_HABIT[hid]))
    if not pk.habits:
        for hid, h in pk.cohort_habits.items():
            if hid in _BY_HABIT and hid != "step_skips" and h.seconds >= MIN_SECONDS:
                out.append((h.seconds * 0.5, _BY_HABIT[hid]))
    if "step_skips" in pk.habits or "step_skips" in pk.cohort_habits or pk.consequences:
        out.append((MIN_SECONDS + 0.1, "keep_every_step"))
    hz = pk.hazard
    if hz is not None and (hz.peak_p or hz.p_now or 0) >= max(hz.alarm_threshold or 0.5, 0.5):
        out.append((30.0, "ask_for_next_step"))
    for r in pk.routines.values():
        if r.status in ("proposed", "declined"):
            out.append((1.0, "review_routine"))
            break
    for r in pk.routines.values():
        if r.status == "shadow" and r.rung == "A1":
            out.append((1.0, "keep_shadow_going"))
            break
    return out


def applicable(pk: EvidencePacket) -> list[str]:
    """The menu ids that apply to the packet, most relevant first (largest habit first). ``keep_going`` applies only when nothing else does."""
    seen: list[str] = []
    for _, a in sorted(_applies(pk), key=lambda t: -t[0]):
        if a not in seen:
            seen.append(a)
    return seen or ["keep_going"]


def default_choice(pk: EvidencePacket, k: int = 2) -> list[str]:
    return applicable(pk)[:k]


def _figure(pk: EvidencePacket, path: str) -> tuple[str, str] | None:
    """The spoken figure for a menu path and the packet path it came from (a habit falls back to its cohort row), or None."""
    kind, *rest = path.split(".")
    if kind == "habit":
        if rest[0] in pk.habits:
            return render(pk.habits[rest[0]].seconds, "s"), path
        if rest[0] in pk.cohort_habits:
            return render(pk.cohort_habits[rest[0]].seconds, "s"), f"cohort_habit.{rest[0]}.seconds"
        return None
    if kind == "hazard" and pk.hazard is not None:
        for fld in (rest[0], "p_now"):
            if getattr(pk.hazard, fld, None) is not None:
                return render(getattr(pk.hazard, fld), "frac"), f"hazard.{fld}"
    return None


def resolve(ids: list[str], pk: EvidencePacket) -> list[dict]:
    """Menu ids to ``{id, text, uses}``. Text and figure come from code and the packet; an id that does not apply is dropped."""
    ok = set(applicable(pk))
    out = []
    for i in ids:
        if i not in ok or i not in ACTIONS:
            continue
        a = ACTIONS[i]
        text, uses = a.text, []
        if a.figure and "{x}" in text:
            fig = _figure(pk, a.figure)
            if fig is not None:
                text, uses = text.replace("{x}", fig[0]), [fig[1]]
            else:                                        # no figure: say the first clause only
                text = text.split(";")[0].rstrip(".") + "."
        out.append({"id": i, "text": text, "uses": uses})
    return out
