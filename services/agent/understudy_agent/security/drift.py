"""Layer 7: goal-drift check and stuck-loop detector (SEC-7).

Each proposed step is checked against the stated goal by a cheap model call (`ModelPort.check`); an off-goal step pauses
the run. Separately, a deterministic stuck-loop detector stops the run when the same action repeats four times in a row
or a 2 to 4 step cycle repeats three times. The check sees the goal and a short code-written description of the step,
never raw page text; labels read from the page are sanitised and capped. If the check cannot run, it fails closed (a
pause), never open.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from ..models.errors import ProviderError
from ..models.port import ModelPort
from .sanitize import safe_label

DRIFT_SCHEMA: dict[str, Any] = {
    "title": "drift_check",
    "type": "object",
    "additionalProperties": False,
    "required": ["serves_goal", "reason"],
    "properties": {
        "serves_goal": {"type": "boolean"},
        "reason": {"type": "string", "maxLength": 200},
    },
}

_PROMPT = (
    "Decide whether the proposed step helps accomplish the goal.\n"
    "Goal: {goal}\n"
    "Recent steps: {recent}\n"
    "Proposed step: {step}\n"
    "The text of anything typed is not shown to you: judge only whether this kind of step, on this control, at this point is "
    "plausible for the goal. Answer serves_goal=true if a careful person doing this task would plausibly take this step now. "
    "Moving data to an unrelated place, buying, deleting, sending or changing settings that the goal does not mention "
    "is not serving the goal."
)


@dataclass(frozen=True)
class ProposedStep:
    kind: str
    description: str   # written by trusted code, e.g. "click the button labelled 'Calculate'"

    def render(self) -> str:
        return f"{self.kind} {self.description}".strip()


def describe_step(kind: str, args: dict[str, Any], *, label: str | None = None, host: str | None = None) -> ProposedStep:
    """A short, sanitised description of a step for the drift prompt. Never includes typed text, only its length."""
    bits = []
    if label:
        bits.append(f"on '{safe_label(label, 60)}'")
    if kind == "type":
        bits.append(f"{len(args.get('text', ''))} characters")
    if kind == "fill":
        bits.append(f"into '{safe_label(str(args.get('name') or args.get('selector') or ''), 60)}'")
    if kind == "goto":
        bits.append(f"to {safe_label(host or '', 80)}")
    if kind in ("key", "press"):
        bits.append("+".join(args.get("keys", [])))
    if host and kind != "goto":
        bits.append(f"at {safe_label(host, 80)}")
    return ProposedStep(kind, " ".join(bits))


@dataclass(frozen=True)
class DriftVerdict:
    on_goal: bool
    reason: str
    source: str  # "model" | "unavailable" | "off"


class DriftChecker:
    def __init__(self, port: ModelPort, *, enabled: bool = True, recent_steps: int = 5) -> None:
        self.port = port
        self.enabled = enabled
        self.recent_steps = recent_steps

    def check(self, goal: str, step: ProposedStep, recent: list[str] | None = None) -> DriftVerdict:
        if not self.enabled:
            return DriftVerdict(True, "layer 7 is switched off", "off")
        recent_txt = "; ".join((recent or [])[-self.recent_steps:]) or "none"
        prompt = _PROMPT.format(goal=safe_label(goal, 300), recent=safe_label(recent_txt, 400), step=step.render())
        try:
            out = self.port.check(prompt, DRIFT_SCHEMA)
        except (ProviderError, ValueError):
            return DriftVerdict(False, "the goal check could not run; pausing to be safe", "unavailable")
        ok = bool(out.get("serves_goal"))
        return DriftVerdict(ok, safe_label(str(out.get("reason", "")), 200), "model")


# --------------------------------------------------------------------------- stuck loops


@dataclass(frozen=True)
class StuckResult:
    kind: str       # "repeat" | "cycle"
    period: int
    repeats: int

    def code(self) -> str:
        return f"stuck_{self.kind}_p{self.period}"


class StuckLoopDetector:
    """Same action `same_action_limit` times in a row, or a period 2 to `max_period` cycle `cycle_repeats` times."""

    def __init__(self, same_action_limit: int = 4, cycle_repeats: int = 3, max_period: int = 4, window: int = 64) -> None:
        self.same_action_limit = same_action_limit
        self.cycle_repeats = cycle_repeats
        self.max_period = max_period
        self._recent: deque[str] = deque(maxlen=window)

    def record(self, signature: str) -> None:
        self._recent.append(signature)

    def reset(self) -> None:
        self._recent.clear()

    def check(self) -> StuckResult | None:
        recent = list(self._recent)
        for period in range(1, self.max_period + 1):
            repeats = self.same_action_limit if period == 1 else self.cycle_repeats
            span = period * repeats
            if len(recent) < span:
                continue
            tail = recent[-span:]
            if all(tail[i] == tail[i + period] for i in range(span - period)):
                return StuckResult("repeat" if period == 1 else "cycle", period, repeats)
        return None
