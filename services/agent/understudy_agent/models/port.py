"""The model provider port (IMPLEMENTATION_SPEC section 8). Written by the lead; do not change the
signatures without a CONTRACT-CHANGE message to the lead.

Providers (implemented by the agent-safety track in this package):
  openai_provider (primary), mock_provider (scripted, deterministic), gemini_provider (optional).
Model IDs come from env: OPENAI_MODEL_PLANNER / OPENAI_MODEL_FAST / OPENAI_MODEL_COMPUTER_USE.
Never hard-code model names. Verified in spike S1 (7 Nov 2026): the Responses API accepts
tools=[{"type": "computer"}] and returns `computer_call` items whose `actions` is a list
(e.g. [{"type": "screenshot"}]).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ActionKind = Literal[
    "click", "double_click", "type", "key", "scroll", "move", "drag", "wait", "screenshot",
    "goto", "back", "forward",   # the browsing profile only (security/actions.py BROWSER_KINDS): a page address, and a step back or forward in history
]


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    args: dict[str, Any] = field(default_factory=dict)  # validated by security/actions.py


@dataclass(frozen=True)
class Done:
    summary: str
    claimed_success: bool  # a CLAIM only; completion.py decides truth


@dataclass(frozen=True)
class Unsupported(Done):
    """The model asked for an action this provider does not map (`name` is a closed token: lower-case letters, digits and underscores).
    It IS a failed Done to any caller that only knows `Done`, but the tier-3 loop reads it as "that action does not exist here": it says so
    to the model and asks again (a few times), instead of ending the whole run as if the model had given up."""

    name: str = ""


@dataclass(frozen=True)
class SafetyStop:
    """A pending safety check from the provider. Always goes to the human queue; never auto-acked."""

    checks: list[dict[str, Any]]


class ModelPort(Protocol):
    name: str

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Planner call. If schema is given, return an object matching it."""
        ...

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Quarantined reader: sees raw untrusted content, no tools, returns schema-checked fields only."""
        ...

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Cheap verifier / classifier (fast model)."""
        ...

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]]) -> Action | Done | SafetyStop:
        """One action per turn. Fresh screenshot each call. Caller enforces step cap and deadline."""
        ...
