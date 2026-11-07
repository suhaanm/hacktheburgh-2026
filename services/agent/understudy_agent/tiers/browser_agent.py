"""Tier 2: the browser agent (AGT-3, SEC-2, SEC-3).

Each turn: observe -> (read) -> plan -> authorise -> act -> record, one typed action, through the safety pipeline.

  * Tools are a fixed set: click(ref), fill(ref, param), select(ref, param), wait, finish.
  * The model NEVER types a value. It names a household parameter; code looks the value up (and converts
    units). Text found on a page therefore cannot be typed anywhere (SEC-5).
  * The planner prompt comes from `pipeline.planner_messages`: the goal and schema-checked fields, never raw page
    text. We append only the element refs, roles and short (<= 48 char) labels, wrapped as untrusted data.
  * A claim of `finish` is checked by code; a claim that fails is a false claim.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from ..completion import ClaimLedger
from ..models.errors import ProviderError
from ..models.port import ModelPort
from ..security.sanitize import wrap_untrusted
from .base import (
    ActionRejected, Emit, GateStop, Observation, StepBudgetExceeded, StepEvent, StuckDetector, StuckLoop,
)
from .observe import observe
from .safety import Guard

TOOLS = ("click", "fill", "select", "wait", "finish")
UNITS = ("none", "month", "week", "year")
MONETARY_MONTHLY = {"adult1_earnings_monthly", "adult2_earnings_monthly", "rent_monthly", "childcare_monthly"}
FILLABLE_ROLES = {"textbox", "spinbutton", "combobox"}
LABEL_CAP = 48  # below the pipeline's 50-character verbatim-copy window, so a label can never look like a page dump

TIER2_SCHEMA: dict[str, Any] = {
    "title": "tier2_step",
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": list(TOOLS)},
        "ref": {"type": ["string", "null"]},
        "param": {"type": ["string", "null"]},
        "unit": {"type": "string", "enum": list(UNITS)},
        "reason": {"type": "string", "maxLength": 200},
        "confidence": {"type": ["number", "null"]},   # with `finish`: how sure you are the results page is showing (0 to 1)
    },
    "required": ["tool", "reason"],
}

PAGE_STATE_SCHEMA: dict[str, Any] = {
    "title": "page_state",
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["form", "result", "error", "saved_note", "other"]},
        "error": {"type": "boolean"},
    },
    "required": ["kind", "error"],
}

TOOL_HELP = (
    "TOOLS (return exactly one as JSON):\n"
    "- click(ref): press a button or follow a link.\n"
    "- fill(ref, param, unit): put the household value named `param` into the text field `ref`. Money parameters are "
    "stored per month; if the field asks for a per-week or per-year amount, set unit to week or year, otherwise month. "
    "Leave unit as none for everything else.\n"
    "- select(ref, param): choose the option for `param` in the drop-down `ref`.\n"
    "- wait: do nothing for a moment.\n"
    "- finish(confidence): the page is showing the final result (the estimate, its status and its reference) or the saved "
    "case note. Say how sure you are, 0 to 1.\n"
    "Only fill a field once per page. Never invent a parameter name. Move on with the forward button when the page's "
    "fields are done. If the extracted page kind is `error`, the page is a problem page: do NOT finish. Press its Go "
    "back or Try again link, then press the forward button again. Only finish on a `result` page or a `saved_note` page."
)

__all__ = ["BrowserAgent", "StuckLoop", "Tier2Task", "Tier2Result", "TIER2_SCHEMA", "PAGE_STATE_SCHEMA", "convert_unit"]


def convert_unit(param: str, value: str, unit: str) -> str:
    """Household money params are monthly. A field that asks for a year or a week gets the converted figure."""
    if param not in MONETARY_MONTHLY or value == "" or unit in ("none", "month"):
        return value
    v = float(value)
    return f"{v * 12:.2f}" if unit == "year" else f"{v * 12 / 52:.2f}" if unit == "week" else value


@dataclass
class Tier2Task:
    goal: str                                   # trusted wording: also what the goal-drift check compares steps to
    params: dict[str, str]
    allowed_params: tuple[str, ...]
    looks_final: Callable[[Observation], bool]  # cheap: is this plausibly the finished page?
    schema: dict[str, Any] | None               # reader schema for a final page (None: parse the DOM text in code)
    parse: Callable[[Observation, dict[str, Any] | None], dict[str, Any] | None]  # code check; None = not done
    param_help: dict[str, str] = field(default_factory=dict)   # trusted wording: what each household parameter means


@dataclass
class Tier2Result:
    outputs: dict[str, Any] | None
    actions: int = 0
    false_claims: int = 0
    reason: str = ""
    claims: list[str] = field(default_factory=list)


def _normalise(out: dict[str, Any]) -> dict[str, Any]:
    """Accept the typed format and the loose `kind/args` format other planners (and hijacked ones) use."""
    if isinstance(out.get("next_step"), dict):
        out = out["next_step"]
    if "tool" in out:
        return {"tool": out.get("tool"), "ref": out.get("ref"), "param": out.get("param"),
                "unit": out.get("unit") or "none", "reason": out.get("reason", ""), "args": out.get("args", {}),
                "confidence": out.get("confidence")}
    kind = out.get("kind")
    args = out.get("args", {}) if isinstance(out.get("args"), dict) else {}
    tool = {"wait": "wait", "goto": "goto", "click_element": "click_label", "type": "type_text"}.get(kind, str(kind))
    return {"tool": tool, "ref": None, "param": None, "unit": "none", "reason": out.get("reason", ""), "args": args}


class BrowserAgent:
    def __init__(self, model: ModelPort, guard: Guard, *, navigator: str, emit: Emit | None = None,
                 is_current: Callable[[], bool] = lambda: True, step_start: int = 0, max_actions: int = 20,
                 ledger: ClaimLedger | None = None, page_state: bool = False) -> None:
        self.model, self.guard, self.navigator = model, guard, navigator
        self.page_state = page_state    # ask the quarantined reader what KIND of page this is, every step
        self.ledger = ledger or ClaimLedger()
        self.emit = emit
        self.is_current = is_current
        self.step_start = step_start
        self.max_actions = max_actions
        self.used = 0
        self.stuck = StuckDetector()

    def _event(self, n: int, action: str, ok: bool, detail: str, extra: dict[str, Any] | None = None) -> None:
        ev = StepEvent(navigator=self.navigator, step=n, tier=2, action=action, ok=ok, detail=detail, extra=extra or {})
        self.guard.record_step(ev)
        if self.emit:
            self.emit(ev)

    async def run(self, page: Any, task: Tier2Task) -> Tier2Result:
        self.guard.set_mode("model_driven")
        self.guard.set_goal(task.goal)
        done_on: dict[str, set[str]] = defaultdict(set)
        history: list[dict[str, Any]] = []
        res = Tier2Result(outputs=None)
        rejected_streak = 0
        prev_path: str | None = None
        n = self.step_start
        while res.actions < self.max_actions:
            if not self.is_current():
                raise asyncio.CancelledError()
            obs = await observe(page)
            candidate = task.looks_final(obs)
            schema = task.schema if candidate else (PAGE_STATE_SCHEMA if self.page_state else None)
            seen = await asyncio.to_thread(self.guard.observe_obs, obs, schema=schema, navigator=self.navigator)
            if candidate:
                outputs = task.parse(obs, seen.fields)
                if outputs is not None:
                    res.outputs, res.reason = outputs, "code check passed"
                    return res
            page_key = urlparse(obs.url).path
            if page_key != prev_path:
                done_on[page_key] = set()   # arriving on a page (a new one, or this one again after Back) starts it blank
            prev_path = page_key
            visible = obs.visible_elements()
            state = {
                "page": page_key,
                "elements": [e.as_prompt() for e in visible],
                "params": list(task.allowed_params),
                "param_meaning": task.param_help,
                "already_set_on_this_page": sorted(done_on[page_key]),
                "recent": history[-6:],
                "actions_left": self.max_actions - res.actions,
            }
            labels = "\n".join(f"{e.ref}: {e.name[:LABEL_CAP]}" for e in visible)
            extra = (TOOL_HELP + "\n\nSTATE: " + json.dumps(state, sort_keys=True)
                     + "\nELEMENT LABELS (copied from the page):\n" + wrap_untrusted(labels, source="web"))
            msgs = self.guard.planner_messages(task.goal, seen, history_summary=f"{res.actions} actions taken", extra=extra)
            try:
                raw = await asyncio.to_thread(self.model.plan, msgs, TIER2_SCHEMA)
            except (ProviderError, ValueError) as exc:  # a malformed or refused answer is one wasted turn, not a dead run
                res.actions += 1
                self.used = res.actions
                n += 1
                rejected_streak += 1
                history.append({"tool": "plan", "ok": False, "why": type(exc).__name__})
                self._event(n, "plan", False, f"rejected: {type(exc).__name__}")
                if rejected_streak >= 3:
                    raise
                continue
            act = _normalise(raw if isinstance(raw, dict) else {})
            res.actions += 1
            self.used = res.actions
            n += 1
            tool = act["tool"]
            if self.stuck.push((tool, act.get("ref"), act.get("param"), page_key)) and self.guard.config.drift:
                self._event(n, tool, False, "stuck loop")
                raise StuckLoop(f"stuck loop on {page_key}")
            try:
                await self._act(page, seen, act, task, done_on[page_key], n)
                rejected_streak = 0
                history.append({"tool": tool, "param": act.get("param"), "ref": act.get("ref"), "ok": True})
            except ActionRejected as exc:
                rejected_streak += 1
                history.append({"tool": tool, "ok": False, "why": str(exc)[:60]})
                self._event(n, tool, False, f"rejected: {str(exc)[:60]}")
                if rejected_streak >= 3:
                    raise
            if tool == "finish":
                obs2 = await observe(page)
                ok = False
                if task.looks_final(obs2):
                    seen2 = await asyncio.to_thread(self.guard.observe_obs, obs2, schema=task.schema, navigator=self.navigator)
                    ok = task.parse(obs2, seen2.fields) is not None
                res.claims.append("verified" if ok else "false")
                self.ledger.record(f"tier2:{self.navigator}", True, ok, "finish claimed")
                if not ok:
                    res.false_claims += 1
                    history.append({"tool": "finish", "ok": False, "why": "claim not confirmed by code"})
        raise StepBudgetExceeded(f"tier 2 action cap {self.max_actions} reached")

    # ------------------------------------------------------------------ one action
    async def _act(self, page: Any, seen: Any, act: dict[str, Any], task: Tier2Task, done: set[str], n: int) -> None:
        tool, obs = act["tool"], seen.obs
        if tool == "finish":
            conf = act.get("confidence")
            self._event(n, "finish", True, "claim",
                        extra={"confidence": max(0.0, min(1.0, float(conf)))} if isinstance(conf, (int, float)) else None)
            return
        if tool == "wait":
            dec = self.guard.authorise({"kind": "wait", "args": {"seconds": 0.15}}, seen, url=obs.url)
            self.guard.require(dec, "wait", navigator=self.navigator)
            await asyncio.sleep(0.15)
            self.guard.record(dec, True)
            self._event(n, "wait", True, "")
            return
        if tool in ("click", "fill", "select"):
            el = obs.element(act.get("ref") or "")
            if el is None or not el.visible or not el.enabled:
                raise ActionRejected(f"unknown or unavailable element {act.get('ref')!r}")
            sel = f'[data-uref="{el.ref}"]'
            loc = page.locator(sel)
            label = el.name[:120]
            if tool == "click":
                if el.role not in ("button", "link"):
                    raise ActionRejected(f"{el.ref} is not clickable")
                dec = self.guard.authorise({"kind": "click_element", "args": {"selector": sel, "label": label}}, seen,
                                           label=el.name, role=el.role, url=obs.url)
                self._require(dec, el.name, n, "click")
                await loc.click()
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:  # noqa: BLE001
                    pass
                self.guard.record(dec, True)
                self._event(n, "click", True, el.ref)
                return
            param = act.get("param")
            if param not in task.allowed_params:
                raise ActionRejected(f"parameter {param!r} is not one of the known household fields")
            if el.role not in FILLABLE_ROLES:
                raise ActionRejected(f"{el.ref} cannot take a value")
            unit = act.get("unit") if act.get("unit") in UNITS else "none"
            value = convert_unit(param, task.params[param], unit)
            attrs = {"name": el.field_name, "id": el.id, "label": el.name, "type": el.type}
            if tool == "fill":
                action = {"kind": "fill", "args": {"selector": sel, "param": param}}
            else:
                action = {"kind": "select_option", "args": {"selector": sel, "value": value}}
            dec = self.guard.authorise(action, seen, label=el.name, role=el.role, url=obs.url, field_attrs=attrs)
            self._require(dec, el.name, n, tool)
            if tool == "fill":
                await loc.fill(value)
            else:
                try:
                    await loc.select_option(value=value, timeout=2000)
                except Exception:  # noqa: BLE001
                    await loc.select_option(label=value, timeout=2000)
            self.guard.record(dec, True)
            done.add(param)
            self._event(n, tool, True, f"param={param}")
            return
        # Loose actions only a hijacked planner (or a layer-3-off ablation) would emit. With layer 3 (typed
        # actions) on, the tool set above is all there is.
        if self.guard.config.actions:
            raise ActionRejected(f"tool {tool!r} is not one of the typed tools")
        args = act.get("args") or {}
        if tool == "goto" and args.get("url"):
            dec = self.guard.authorise({"kind": "goto", "args": {"url": str(args["url"])}}, seen, url=obs.url)
            self._require(dec, "goto", n, "goto")
            await page.goto(str(args["url"]), wait_until="domcontentloaded")
            self.guard.record(dec, True)
            self._event(n, "goto", True, "loose")
            return
        if tool == "click_label" and args.get("label"):
            want = str(args["label"]).lower()
            el = next((e for e in obs.visible_elements() if e.role in ("button", "link") and want in e.name.lower()), None)
            if el is not None:
                sel = f'[data-uref="{el.ref}"]'
                dec = self.guard.authorise({"kind": "click_element", "args": {"selector": sel, "label": el.name[:120]}},
                                           seen, label=el.name, role=el.role, url=obs.url)
                self._require(dec, el.name, n, "click")
                await page.locator(sel).click()
                self.guard.record(dec, True)
                self._event(n, "click", True, "loose")
                return
        dec = self.guard.authorise({"kind": str(tool), "args": args}, seen, url=obs.url)
        self._require(dec, str(tool), n, str(tool))
        raise ActionRejected(f"tool {tool!r} is not allowed")

    def _require(self, dec: Any, label: str, n: int, action: str) -> None:
        if dec.verdict != "allow":
            self._event(n, action, False, f"{dec.verdict} {dec.layer or ''}".strip())
        self.guard.require(dec, label, navigator=self.navigator)
