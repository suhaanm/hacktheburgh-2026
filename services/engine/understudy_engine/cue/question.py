"""The one clarifying question (CUE-4): built from the candidate steps' pack labels, worded from a fixed template set.

When the top two candidates are within the margin, or the screen disagrees with the path prior, or Cue cannot tell where the worker
is, the gate may ask ONE multiple-choice question per stuck episode: two to four steps from the pack plus a fixed "Something else".
The text is chosen by ambiguity type from ``vocab.QUESTIONS``; no model writes it. The worker's answer is a strong intent label: it
adds pseudo-counts to that person's path prior (``NextStepModel.observe_intent``) and marks the episode assisted.
"""
from __future__ import annotations

from collections.abc import Sequence

from .candidates import NextStepModel
from .types import OTHER, Candidate, Grounding
from .vocab import OTHER_LABEL, QUESTIONS

MIN_OPTIONS, MAX_OPTIONS = 2, 4


class QuestionError(ValueError):
    pass


def ambiguity_type(cands: Sequence[Candidate], grounding: Grounding | None, *, margin_thr: float, min_path_p: float,
                   confident_p: float, ground_conf_thr: float, grounded: bool) -> str | None:
    """Which template applies, or None when the path prior and the screen agree well enough to cue without asking."""
    if not cands:
        return None
    top = cands[0]
    margin = top.p - cands[1].p if len(cands) > 1 else top.p
    if len(cands) > 1 and margin < margin_thr:
        return "close_call"
    g = grounding
    if g is not None and g.found and g.chosen is not None and g.confidence >= ground_conf_thr and g.chosen != top.id \
            and g.chosen in {c.id for c in cands} and g.chosen not in _mates(cands, top):
        return "screen_disagrees"
    if top.p < min_path_p or (not grounded and top.p < confident_p):
        return "unclear"
    return None


def _mates(cands: Sequence[Candidate], top: Candidate) -> set[str]:
    return {c.id for c in cands if c.group == top.group}


def build_question(cands: Sequence[Candidate], qtype: str, grounding: Grounding | None = None) -> tuple[dict, list[dict]]:
    """``(question, options)``. Options are candidate steps (those visible on screen first), then the fixed "Something else"."""
    if qtype not in QUESTIONS:
        raise QuestionError(f"unknown question type {qtype!r}")
    visible = set(grounding.available) if grounding is not None else set()
    ordered = sorted(cands, key=lambda c: (c.id not in visible, -c.p)) if visible else list(cands)
    seen_groups: set[str] = set()
    steps: list[Candidate] = []
    for c in ordered:
        if c.group in seen_groups:        # three interchangeable calculators are one option
            continue
        seen_groups.add(c.group)
        steps.append(c)
        if len(steps) == MAX_OPTIONS:
            break
    if len(steps) < MIN_OPTIONS:
        raise QuestionError("a question needs at least two distinct steps")
    options = [{"id": c.id, "label": c.label} for c in steps] + [{"id": OTHER, "label": OTHER_LABEL}]
    return {"type": qtype, "text": QUESTIONS[qtype]}, options


def can_ask(cands: Sequence[Candidate]) -> bool:
    return len({c.group for c in cands}) >= MIN_OPTIONS


def valid_answer(option_ids: Sequence[str], answer_id: str) -> bool:
    return answer_id in set(option_ids) | {OTHER}


def answer_label(model: NextStepModel, history: Sequence[str], answer_id: str, weight: float | None = None) -> bool:
    """Record the answer as a strong intent label on ``model`` (a person's own clone). "Something else" records nothing."""
    if answer_id == OTHER:
        return False
    return model.observe_intent(history, answer_id) if weight is None else model.observe_intent(history, answer_id, weight)
