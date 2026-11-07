"""Where the ring goes and what the coach says. Templated plain language; no model call (PR1).

Style rule (COA-4): a hypothesis or a question, not the answer. The one exception is L1 annotate, which points at
the control (the ring) and says what comes first. Wording comes from the pack: ``expert_steps.yaml`` checks carry
``coach.question`` / ``coach.hint`` (and optionally ``coach.annotate``, ``coach.target``), ``curriculum.yaml`` skills
carry ``expert_signal`` and per-level ``prompts``. Defaults fill any gap so a thin pack still works.
"""
from __future__ import annotations

import re

from ..cogs.mapper import Mapping
from .steps import Step

# what the worker is about to do, by the cog they have just started (for "before you ...")
ACTION_PHRASE = {
    "COPY_TO_NOTE": "copy this result",
    "RECONCILE": "reconcile the results",
    "OPEN_CALCULATOR": "open the next calculator",
    "COMMIT": "commit",
    "EXPORT_RESULT": "export this",
    "RUN_QUERY": "run the query",
}

_PREFERRED_TYPES = ("click", "focus", "tab", "paste", "nav", "scroll", "copy")


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def target_for(step: Step, mapping: Mapping, site: str | None = None) -> dict:
    """``{zone, label_hint, role_hint, site?}``: the control the worker needs next, from the pack's own mapping.

    The zone is the first zone of an interactive rule (a click or focus) that maps to the step's first cog; a pack can
    override it with ``coach.target`` in the step.
    """
    override = (step.coach or {}).get("target")
    if isinstance(override, dict) and override.get("zone"):
        out = {"zone": override["zone"], "label_hint": override.get("label_hint", step.label), "role_hint": override.get("role_hint", "button")}
    else:
        cog = step.cogs[0]
        best = None
        for r in mapping.rules:
            if r.cog != cog or not r.zones:
                continue
            types = r.types or frozenset()
            rank = min((_PREFERRED_TYPES.index(t) for t in types if t in _PREFERRED_TYPES), default=len(_PREFERRED_TYPES))
            if best is None or rank < best[0]:
                best = (rank, sorted(r.zones)[0], types)
        zone = best[1] if best else None
        role = "button" if best and "click" in best[2] else ("textbox" if best and "paste" in best[2] else "region")
        out = {"zone": zone, "label_hint": short_label(step.label), "role_hint": role}
    if site:
        out["site"] = site
    return out


def short_label(label: str) -> str:
    """'Open Check cliff edges on calculator A' -> 'Check cliff edges' (what is written on the control)."""
    s = re.sub(r"\s+on calculator [A-Za-z0-9]+$", "", label.strip())
    s = re.sub(r"^Open\s+(?=[A-Z])", "", s)
    return s


def curriculum_skill(curriculum: dict | None, skill_id: str | None, step: Step) -> dict | None:
    skills = (curriculum or {}).get("skills") or []
    for sk in skills:
        if skill_id and sk.get("id") == skill_id:
            return sk
    for sk in skills:
        if set(sk.get("cogs") or []) & set(step.cogs):
            return sk
    return None


def message_for(action: str, *, missed: Step | None, violating: Step | None, current: Step | None, level: int, tone: str,
                curriculum: dict | None, stuck: bool = False) -> tuple[str, str]:
    """(message, why) for one decision. ``tone`` is "short" or "detailed" (memory preference)."""
    step = missed or current
    if step is None:
        return "", ""
    coach = step.coach or {}
    sk = curriculum_skill(curriculum, step.skill, step)
    prompts = (sk or {}).get("prompts") or {}
    signal = (sk or {}).get("expert_signal")
    why = f"Experts: {_lower_first(signal.rstrip('.'))}." if signal else (
        f"{step.label} comes before the step you are on in the expert order." if missed else "")
    if action == "takeover_offer":
        msg = f"Want me to do this one for you: {_lower_first(short_label(step.label))}? I will stop before anything is sent."
        return msg, why
    if action == "annotate":
        if coach.get("annotate"):
            msg = str(coach["annotate"])
        elif missed is not None and violating is not None:
            if " before " in step.label.lower():          # the label already says what it comes before
                msg = f"{short_label(step.label)}."
            else:
                act = ACTION_PHRASE.get(violating.cogs[0], _lower_first(violating.label.rstrip(".")))
                msg = f"{short_label(step.label)} before you {act}."
            msg = msg[0].upper() + msg[1:]
        elif stuck:
            msg = coach.get("question") or prompts.get("L1") or "Stuck? Start with the next check."
        else:
            msg = coach.get("hint") or coach.get("question") or prompts.get("L1") or f"{short_label(step.label)}."
        if tone == "detailed" and coach.get("hint") and coach.get("hint") not in msg:
            msg = f"{msg} {coach['hint']}"
        return msg, why
    if action == "nudge":
        msg = coach.get("question") or prompts.get("L2") or prompts.get("L1") or f"What does {_lower_first(short_label(step.label))} tell you?"
        return msg, why
    # silent with a dot (L3): the text the dot expands to when the worker taps it
    return prompts.get("L3") or coach.get("question") or "", why
