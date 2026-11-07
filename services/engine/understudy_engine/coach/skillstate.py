"""Skill state as the coach sees it: a SkillTracker built from the person's finished episodes (COA-3, ANA-13).

The level engine stays the authority. Every finished task is judged against the expert policy
(`StepPolicy.episode_outcomes`): a required step that was missed, or done only after something that needed it had
started, is an error on the step's cogs; a step the worker did after a followed coach prompt is assisted (neutral);
otherwise clean. One outcome per cog per task (any error wins, then assisted, then clean).
"""
from __future__ import annotations

from collections.abc import Iterable

from ..skills import SkillTracker
from .steps import Progress, StepPolicy


def cog_outcomes(policy: StepPolicy, prog: Progress, followed: Iterable[str] = (), already_assisted: Iterable[str] = ()) -> dict[str, str]:
    followed = set(followed)
    skip = set(already_assisted)
    by_cog: dict[str, str] = {}
    for sid, outcome in policy.episode_outcomes(prog).items():
        if sid in skip:
            continue
        if sid in followed and outcome == "clean":
            outcome = "assisted"
        elif sid in followed and sid in prog.done:
            outcome = "assisted"            # done after a followed prompt: the prompt did the work, even if it was late
        for cog in policy.steps[sid].cogs:
            prev = by_cog.get(cog)
            if prev == "error" or outcome == "error":
                by_cog[cog] = "error"
            elif prev == "assisted" or outcome == "assisted":
                by_cog[cog] = "assisted"
            else:
                by_cog[cog] = "clean"
    return by_cog


def fold_episode(tracker: SkillTracker, outcomes: dict[str, str], t: float) -> list[dict]:
    return [tracker.observe(cog, o, t) for cog, o in sorted(outcomes.items())]  # type: ignore[arg-type]
