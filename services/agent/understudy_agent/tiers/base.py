"""Shared types for the tiers: observations, step events, errors."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


class TierError(Exception):
    """Base for failures that make a navigator escalate or stop."""


class PreconditionFailed(TierError):
    def __init__(self, step_id: str, what: str) -> None:
        super().__init__(f"precondition failed at {step_id}: {what}")
        self.step_id, self.what = step_id, what


class PostconditionFailed(TierError):
    def __init__(self, step_id: str, what: str) -> None:
        super().__init__(f"postcondition failed at {step_id}: {what}")
        self.step_id, self.what = step_id, what


class ActionRejected(TierError):
    """A typed action failed validation (unknown tool, unknown element, bad parameter)."""


class StepBudgetExceeded(TierError):
    pass


class GateStop(TierError):
    """The action-class gate refused (verdict needs_human, block or pause). Never retried."""

    def __init__(self, decision: Any, label: str = "") -> None:
        super().__init__(f"gate stopped the action ({getattr(decision, 'verdict', decision)}): {label}")
        self.decision, self.label = decision, label


class InjectionStop(TierError):
    """The injection detector paused the run. A hit is never a reason to act."""

    def __init__(self, codes: str, where: str = "") -> None:
        super().__init__(f"injection detector paused the run ({codes}) {where}".strip())
        self.codes, self.where = codes, where


class StuckLoop(TierError):
    pass


class StuckDetector:
    """Same action four times in a row, or a 2 to 4 step cycle three times (SEC-7). Local backstop for model
    loops that the pipeline never sees (wait and finish)."""

    def __init__(self) -> None:
        self.seen: list[tuple[Any, ...]] = []

    def push(self, sig: tuple[Any, ...]) -> bool:
        self.seen.append(sig)
        s = self.seen
        if len(s) >= 4 and len(set(s[-4:])) == 1:
            return True
        for n in (2, 3, 4):
            if len(s) >= 3 * n and s[-n:] == s[-2 * n:-n] == s[-3 * n:-2 * n] and len(set(s[-n:])) > 1:
                return True
        return False


@dataclass(frozen=True)
class Element:
    ref: str                 # "e3": stable inside one observation
    tag: str
    role: str                # button | link | textbox | combobox | checkbox ...
    name: str                # accessible name, sanitised and truncated
    type: str = ""
    visible: bool = True
    enabled: bool = True
    filled: bool = False
    options: tuple[str, ...] = ()   # option values for selects
    id: str = ""
    field_name: str = ""
    testid: str = ""

    def as_prompt(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ref": self.ref, "role": self.role, "name": self.name}
        if self.type:
            d["type"] = self.type
        if self.role in ("textbox", "combobox", "spinbutton"):
            d["filled"] = self.filled
        if self.options:
            d["options"] = list(self.options)[:12]
        if not self.enabled:
            d["disabled"] = True
        return d


@dataclass
class Observation:
    """A fresh look at one page. `text` and the hidden/alt lists are untrusted data."""

    url: str
    title: str
    text: str
    elements: list[Element] = field(default_factory=list)
    hidden_texts: list[str] = field(default_factory=list)
    alt_texts: list[str] = field(default_factory=list)
    taken_at: float = field(default_factory=time.monotonic)

    def element(self, ref: str) -> Element | None:
        return next((e for e in self.elements if e.ref == ref), None)

    def visible_elements(self) -> list[Element]:
        return [e for e in self.elements if e.visible]

    def all_text(self) -> str:
        return "\n".join(x for x in [self.title, self.text, *self.alt_texts] if x)


@dataclass
class StepEvent:
    """One logged step. `tier` is always present (AGT-3)."""

    navigator: str
    step: int
    tier: int
    action: str
    ok: bool
    t: float = field(default_factory=time.time)
    detail: str = ""        # short, machine-safe (no page text, no values)
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = {"navigator": self.navigator, "step": self.step, "tier": self.tier, "action": self.action,
             "ok": self.ok, "t": self.t}
        if self.detail:
            d["detail"] = self.detail
        d.update(self.extra)
        return d


Emit = Callable[[StepEvent], None]
