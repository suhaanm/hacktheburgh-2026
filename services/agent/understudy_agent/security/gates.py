"""Layer 4: action-class gate (SEC-4, D11).

Irreversible or outward-facing actions (submit, send, post, pay, delete, install, change permissions or credentials)
need a human click UNLESS the worker opted that routine in for those named classes. Rules, all in code:

* `pay`, `install`, `permission`, `credential`, `system` can never be opted in: always a human click.
* `submit`, `send`, `post`, `delete` can be opted in per routine. A compiled routine needs the opt-in; a model-driven
  routine also needs the typed confirmation (the engine records it at opt-in, with a warning banner).
* An opt-in has no effect while the routine sits on rung A0 or A1 (it has not earned autonomy), and a detector hit
  lowers the rung.
* While the kill flag is set, everything is blocked.
* A pointer click or drag, an Enter key press, or typed text that contains a newline (an implicit Enter) is only
  classified from what TRUSTED code read at the target (the DOM or the accessibility tree, never the model's own label).
  When nothing could be read there, the step is `needs_human` in EVERY mode, attended or not (S-01). The old
  `unresolved_clicks_ok` flag no longer changes this.

The gate blocks by default: it returns `allow` only when it has positively classified the step as normal or opted in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .killflag import is_killed
from .labels import (IRREVERSIBLE_CLASSES, NORMAL_CLASSES, OPT_IN_ELIGIBLE, OUTWARD_CLASSES, ActionClass, classify_keys,
                     classify_label, highest, risk_class, sensitive_path)
from .sensitive import is_sensitive_attrs

Verdict = Literal["allow", "needs_human", "block"]
Mode = Literal["interactive", "compiled", "model_driven"]
RUNGS = ("A0", "A1", "A2", "A3")


@dataclass(frozen=True)
class RoutineContext:
    """What the worker has decided about this run. Built by trusted code from the routine's consent record."""

    routine_id: str | None = None
    mode: Mode = "interactive"
    unattended: bool = False
    rung: str = "A0"
    opted_in: frozenset[ActionClass] = frozenset()   # classes the worker opted this routine into (D11)
    typed_confirm: bool = False                      # model-driven opt-in needs the typed confirmation
    recorded_hosts: frozenset[str] = frozenset()     # sites the routine recorded (layer 5 only; never limits navigation)
    unresolved_clicks_ok: bool = False               # DEPRECATED, no effect: an unreadable target always needs a human (S-01)
    run_id: str | None = None

    def with_rung(self, rung: str) -> "RoutineContext":
        from dataclasses import replace

        return replace(self, rung=rung)


@dataclass(frozen=True)
class TargetInfo:
    """What is under the cursor or in focus, as read by trusted code (DOM, accessibility tree), never by the model."""

    label: str | None = None
    role: str | None = None
    url: str | None = None            # current page address
    app: str | None = None
    field_attrs: dict[str, Any] | None = None   # name, id, label, placeholder, autocomplete, aria_label, type for inputs

    @property
    def resolved(self) -> bool:
        return self.label is not None or self.role is not None


@dataclass(frozen=True)
class GateDecision:
    verdict: Verdict
    classes: frozenset[ActionClass] = frozenset()
    top: ActionClass | None = None
    risk_class: str = "normal"
    reason: str = ""
    opt_in_used: bool = False

    @property
    def queue_kind(self) -> str:
        return "outward_step" if self.risk_class == "outward" else "irreversible_step"


POINTER_KINDS = ("click", "double_click", "drag")
_NEWLINE = re.compile(r"[\r\n]")


def enter_like(kind: str, args: dict[str, Any]) -> bool:
    """An Enter key press, or typed text with a newline in it (which presses Enter, and so can submit a form)."""
    if kind in ("key", "press"):
        return any(str(k).lower() in ("enter", "return") for k in (args.get("keys") or []))
    if kind == "type":
        return bool(_NEWLINE.search(str(args.get("text") or "")))
    return False


def classify_step(kind: str, args: dict[str, Any], target: TargetInfo | None = None) -> set[ActionClass]:
    """Classes a step belongs to. Always includes a base class (read, navigate or fill)."""
    target = target or TargetInfo()
    classes: set[ActionClass] = set()
    if kind in ("screenshot", "wait", "move", "scroll", "scroll_page", "wait_for", "extract", "back"):
        classes.add(ActionClass.READ)
    elif kind == "goto":
        classes.add(ActionClass.NAVIGATE)
    elif kind in ("type", "fill", "select_option"):
        classes.add(ActionClass.FILL)
    elif kind in ("click", "double_click", "click_element", "drag"):
        classes.add(ActionClass.READ)  # base: a click on an unremarkable target changes nothing outward
    if kind in ("key", "press"):
        classes |= classify_keys(args.get("keys", []))
        if not classes:
            classes.add(ActionClass.FILL)
    if enter_like(kind, args):
        classes |= classify_label(target.label)  # Enter acts like the focused control (or the form's own submit button)
    if kind in ("click", "double_click", "click_element"):
        classes |= classify_label(target.label)
        classes |= classify_label(args.get("label"))  # hint from the proposer; it can only ADD risk, never remove it
        classes |= classify_label(args.get("name"))
    if kind in ("type", "fill") and sensitive_path(args.get("text") or args.get("value")):
        classes.add(ActionClass.CREDENTIAL)
    return classes


def gate(kind: str, args: dict[str, Any], ctx: RoutineContext, target: TargetInfo | None = None, *,
         enabled: bool = True, killed: bool | None = None) -> GateDecision:
    target = target or TargetInfo()
    if killed is None:
        killed = is_killed()
    if killed:
        return GateDecision("block", reason="the kill switch is set")
    if not enabled:
        return GateDecision("allow", reason="layer 4 is switched off")

    # Typing into a secret field is never allowed: the product stores no credentials (SEC-11).
    if kind in ("type", "fill") and is_sensitive_attrs(target.field_attrs):
        return GateDecision("block", frozenset({ActionClass.CREDENTIAL}), ActionClass.CREDENTIAL, "irreversible",
                            "this is a password, card or identity field; the agent never types into those")

    classes = classify_step(kind, args, target)
    top = highest(classes)
    risk = risk_class(top)
    frozen = frozenset(classes)

    # A pixel click, an Enter press or a newline does whatever the control under it does. If trusted code could not
    # read that control, nothing can classify the step: a human decides, in every mode (S-01).
    if (kind in POINTER_KINDS or enter_like(kind, args)) and not target.resolved:
        return GateDecision("needs_human", frozen, top, "normal" if top is None else risk,
                            "the control under this click or Enter press could not be read by trusted code; "
                            "it needs a human click")

    if top in NORMAL_CLASSES or top is None:
        return GateDecision("allow", frozen, top, "normal", "normal step")

    # An outward or irreversible class is present.
    risky = classes & (OUTWARD_CLASSES | IRREVERSIBLE_CLASSES)
    ineligible = risky - OPT_IN_ELIGIBLE
    if ineligible:
        return GateDecision("needs_human", frozen, top, risk,
                            f"{top.value} steps always need a human click and cannot be opted in")
    if not risky <= ctx.opted_in:
        return GateDecision("needs_human", frozen, top, risk,
                            f"{top.value} is outward-facing or irreversible; the worker has not opted this routine in")
    if ctx.rung in ("A0", "A1"):
        return GateDecision("needs_human", frozen, top, risk,
                            f"opted in, but rung {ctx.rung} has not earned autonomy; it needs a human click")
    if ctx.mode == "model_driven" and not ctx.typed_confirm:
        return GateDecision("needs_human", frozen, top, risk,
                            "a model-driven routine needs the typed confirmation before it may do this")
    if ctx.mode == "interactive":
        return GateDecision("needs_human", frozen, top, risk, "interactive runs always confirm outward steps")
    return GateDecision("allow", frozen, top, risk, f"the worker opted this routine in for {top.value}", opt_in_used=True)
