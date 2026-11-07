"""Mock-mode scenarios for ``GET /cue/next?fixture=<name>&t=<seconds>`` (UNDERSTUDY_MOCK=1 only).

Each scenario is a worker's last few cogs, a progress clock and what the model and the screen would say, so the desktop and the
dashboard can be built against a Cue that answers deterministically with no event stream. ``t`` is seconds since the worker's last
progress event; poll it upward (2.5 s steps) to see wait, cue, escalation, cap and silence. The names and what each shows:

    stuck_after_result   after calculator A's result: a grounded cue for the cliff check (tier 1 at level 2)
    close_call           two candidates within the margin: one multiple-choice question
    screen_disagrees     the screen shows a different step than the path prior: one question
    ungrounded           no usable target: a text-only chip
    retrieval            teach and fade: help is withheld, kind confirm
    level_4              the worker has it: silent unless asked
    not_stuck            working normally: silent
"""
from __future__ import annotations

from .context import LiveContext

FIX_T0 = 1_800_000_000.0
READ_A = ("READ", "OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT")

NAMES = ("stuck_after_result", "close_call", "screen_disagrees", "ungrounded", "retrieval", "level_4", "not_stuck")


def _cogs(ids: tuple[str, ...], end_t: float) -> tuple[tuple[str, float], ...]:
    """Cogs of 8 s each ending at ``end_t`` (the last progress)."""
    return tuple((c, end_t - 8.0 * (len(ids) - i)) for i, c in enumerate(ids))


def build(name: str, person: str, t: float) -> LiveContext:
    if name not in NAMES:
        raise KeyError(name)
    now = FIX_T0 + t
    cogs = _cogs(READ_A, FIX_T0)
    fx: dict = {"now": now, "level": 2, "mastery": 0.1, "retrieval_due": False,
                "grounding": {"found": True, "chosen": "cliff_a", "available": ["cliff_a"], "box_2d": [412, 96, 466, 388], "confidence": 0.91,
                              "source": "dom", "for_step": "cliff_a"}}
    p_stuck = None
    if name == "close_call":
        fx["candidates"] = [("cliff_a", 0.52), ("calc_b", 0.48)]
        fx["grounding"] = None
    elif name == "screen_disagrees":
        fx["candidates"] = [("cliff_a", 0.70), ("calc_b", 0.30)]
        fx["grounding"] = {"found": True, "chosen": "calc_b", "available": ["calc_b", "cliff_a"], "box_2d": [120, 640, 176, 880],
                           "confidence": 0.9, "source": "vision", "for_step": "cliff_a"}
    elif name == "ungrounded":
        fx["grounding"] = {"found": False, "chosen": None, "available": [], "box_2d": None, "confidence": 0.2, "source": "vision", "for_step": "cliff_a"}
    elif name == "retrieval":
        fx["retrieval_due"] = True
        fx["mastery"] = 0.55
    elif name == "level_4":
        fx["level"], fx["mastery"] = 4, 0.92
    elif name == "not_stuck":
        p_stuck = 0.1
    return LiveContext(person=person, role="benefits-processor", origin="synthetic", task_open=True, task_id="t_fixture", cogs=cogs,
                       last_progress_t=FIX_T0, task_t0=cogs[0][1], last_input_t=now - 6.0, p_stuck=p_stuck, p_source="rule",
                       level={}, mastery={}, fixture=fx)
