"""Prepare: build the editable content of each card from templates.

``prepared`` is the artifact the worker reads, edits and, if they press the button, the exact thing that fires: a lesson
plan as numbered steps, an automation consent summary, a drafted calendar-hold description, a git habit note, a pointer to
a finished result. It is plain text in ``text`` and ``steps`` (the screen numbers the steps), nothing else.

The words are ours, written from the numbers on the candidate and from pack text (skill labels, the expert signal, the
pack's own prompts). Source text (calendar titles, commit messages, file names) never reaches this module: candidates only
carry numbers and fixed vocabularies.

An optional model rewording can polish a template, but only through ``understudy_engine.privacy.egress.send`` with a
registered safe payload (numbers and enums, no free text); see ``reword.py``. Without it, or when it is off or fails, the
template stands. Either way the result passes through ``clean_prepared`` so what is stored is what fires.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .candidates import Candidate
from .text import clean_prepared

COG_WORDS = {
    "READ": "reading the case", "OPEN_CALCULATOR": "opening a calculator", "ENTER_HOUSEHOLD": "entering the household",
    "READ_RESULT": "reading a calculator result", "CHECK_CLIFF": "checking for a cliff edge", "RECONCILE": "comparing the three results",
    "COPY_TO_NOTE": "copying into the case note", "SEARCH": "searching for the answer", "REFORMULATE": "rewording a search",
    "COMPARE": "comparing options", "DECIDE": "making the call", "ENTER": "typing into a form", "COPY": "copying", "PASTE": "pasting",
}


def _words(cog: str) -> str:
    return COG_WORDS.get(cog, cog.replace("_", " ").lower())


def _join(items: list[str]) -> str:
    items = [str(i) for i in items if i]
    if not items:
        return "nothing else"
    return ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1]


# ---------------------------------------------------------------------------------------------------- templates
def practice_plan(p: dict[str, Any]) -> dict[str, Any]:
    label, level = p["label"], int(p.get("level", 1))
    cogs = [c for c in p.get("cogs", []) if c]
    focus = _join([_words(c) for c in cogs[:2]]) or "the step"
    prompts = p.get("prompts") or {}
    check = prompts.get("L2") or prompts.get("L1") or "Does what you did match what a careful colleague would do?"
    steps = [
        "Open a practice case: a sample, not a real one, so nothing you do here reaches anyone.",
        f"Work it the way you normally would, and slow down whenever you reach {focus}.",
        f"At that point ask yourself: {check}",
    ]
    if p.get("expert_signal"):
        steps.append(f"What good looks like: {p['expert_signal'].rstrip('.')}.")
    steps.append("Finish the case, then write one line on what you would change next time.")
    if level <= 2:
        steps.append("Ask for a hint whenever you want one; help fades on its own as you get this right.")
    text = (f"Ten minutes on one skill: {label}. You are at level {level} of 4 on it. "
            "This is a plan, not a test: edit any step so it fits how you work, then press go when you are ready.")
    return {"text": text, "steps": steps}


def automation_consent(p: dict[str, Any]) -> dict[str, Any]:
    touches = _join(list(p.get("touches") or []))
    never = _join(list(p.get("never") or [])) if p.get("never") else "nothing beyond what you approve"
    irr = list(p.get("irreversible_classes") or [])
    text = (f"What this does: {p['title']}. It came up {p['episodes']} times, about {p['minutes_per_week']:.0f} minutes a week. "
            f"Doing it for you could save {p['hours_lo']:.1f} to {p['hours_hi']:.1f} hours over the next {p['horizon_weeks']} weeks. "
            f"It touches: {touches}. It never does: {never}. "
            "It starts in shadow mode: it watches, repeats the work on the side and compares with what you did. It changes nothing on its own, "
            "and you can switch it off at any time.")
    if irr:
        text += f" Steps of this kind ({_join(irr[:4])}) always stop and wait for your own click."
    steps = [
        "Press go: a request appears in your approval queue. Nothing runs yet.",
        "Approve it there to start shadow mode. The assistant only watches and compares.",
        "Look at how often it matches you. A step up needs enough matching runs, and you choose whether to take it.",
        "Say stop at any time. Your memory file lists what you agreed to and you can delete the line.",
    ]
    return {"text": text, "steps": steps}


_HOLD_TEXT = {
    "focus": "Focus time. Protected for deep work: no meetings, notifications off. Please do not book over this.",
    "batch": "Batch time. Similar tasks are done together in this slot so there is no switching in between.",
    "review": "Review slot. A short, fixed time to check work before it goes out.",
    "hold": "Hold. Time kept free so the schedule does not fill it. Release it if it is not needed.",
    "break": "Break away from the screen. A scheduled pause or handoff; step away from the desk.",
    "back": "Buffer. A gap kept between meetings so each one can start fresh.",
}


def calendar_hold(p: dict[str, Any]) -> dict[str, Any]:
    fam = p.get("family") or "other"
    body = _HOLD_TEXT.get(fam, "A calendar change your week's shape points to.")
    nums = p.get("numbers") or {}
    extra = []
    for k in ("suggested_min", "block_min", "duration_min", "per_week"):
        if isinstance(nums.get(k), (int, float)) and not isinstance(nums.get(k), bool):
            extra.append(f"{k.replace('_', ' ')}: {nums[k]:g}")
    text = body + (" " + "; ".join(extra) + "." if extra else "")
    steps = ["Press go: a draft hold is saved on this computer and queued for your approval.",
             "Nothing is written to your calendar until you approve it, and you can edit the wording above first."]
    return {"text": text, "steps": steps}


def git_habit_note(p: dict[str, Any]) -> dict[str, Any]:
    fam = p.get("family") or "other"
    nums = p.get("numbers") or {}
    what = {"huge": "commit size", "test": "touching a test with a code change", "revert": "fix-after-fix loops and reverts",
            "message": "how clear the commit messages are", "late": "commits made late at night",
            "refactor": "mixing refactors with features"}.get(fam, "your commit habits")
    figures = ""
    lr, ex = nums.get("learner"), nums.get("expert")
    if isinstance(lr, (int, float)) and isinstance(ex, (int, float)):
        figures = (f" Yours is {lr:.0%} against the expert reference of {ex:.0%}." if (0 <= lr <= 1 and 0 <= ex <= 1)
                   else f" Yours is {lr:g} against the expert reference of {ex:g}.")
    text = (f"Look at {what} in my recent commits.{figures} Report counts and examples as numbers only, suggest one change to try on the next commit, "
            "and change nothing: read only, no edits, no pushes.")
    steps = ["Press go: a read-only analysis starts in the background and nothing in the repository is touched.",
             "The result appears as a card when it is ready, and nothing leaves this computer."]
    return {"text": text, "steps": steps}


def agent_result_review(p: dict[str, Any]) -> dict[str, Any]:
    n = int(p.get("children") or 0)
    text = (f"A background run finished" + (f" with {n} helper{'s' if n != 1 else ''}" if n else "") +
            ". Its result is waiting and nothing was changed outside its own workspace. Press go to put it in your queue and read it there.")
    return {"text": text}


TEMPLATES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "practice_plan": practice_plan, "automation_consent": automation_consent, "calendar_hold": calendar_hold,
    "git_habit_note": git_habit_note, "agent_result_review": agent_result_review,
}


def prepare(c: Candidate, *, reword: Callable[[Candidate, dict[str, Any]], dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """The editable content for a candidate. ``reword`` (optional) may return a replacement for ``text`` only; it is called
    with the templated content and must go through the egress guard (see ``reword.py``). A failing reword never fails the card."""
    t = c.prepared_template
    fn = TEMPLATES.get(t.get("template", ""))
    if fn is None:
        raise ValueError(f"no prepare template {t.get('template')!r}")
    out = fn(t.get("params", {}))
    if reword is not None:
        try:
            alt = reword(c, out)
        except Exception:
            alt = None
        if isinstance(alt, dict) and isinstance(alt.get("text"), str) and alt["text"].strip():
            out = {**out, "text": alt["text"]}
    return clean_prepared(out)
