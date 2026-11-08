"""Tier 3: computer use through `ModelPort.computer_step` and an `Actuator` (AGT-3, OFF-4).

One action per turn, a fresh screenshot each time, a step cap, a time budget, an action-class gate and a
stuck-loop detector. A provider safety check is NEVER auto-acknowledged: it goes to the human queue.

Actuators
  SimulatedActuator    default; performs nothing, records everything. The only one used in tests.
  BrowserPageActuator  drives ONE headless Playwright page inside the agent's own context (not the desktop).
  MacActuator          real desktop events through Quartz CGEvent. Constructed only when
                       UNDERSTUDY_REAL_ACTUATOR=1. Never exercised by tests; the owner-supervised check is run
                       by the lead against TextEdit or Calculator only.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from ..context.adapters import TIER3_BUDGET_TOKENS
from ..context.working import PageState, TypedIdError, WorkingMemory
from ..models.meter import call_context
from ..models.port import Action, Done, ModelPort, SafetyStop, Unsupported
from ..supervisor import kill_flag_path
from .base import Emit, StepBudgetExceeded, StepEvent, StuckDetector, StuckLoop, TierError
from .form_audit import FormAudit, FormAuditStop, key_names, token
from .safety import Guard



# Iteration 8b (Gemini fit). The first Gemini smokes clicked a native drop-down 13 to 15 times and typed nothing: the model expects a list of
# options to appear, and a headless screenshot never draws one. A code-written note after a click on a drop-down (read by trusted code: role
# combobox) tells it what to do next; in a live probe the next action was then the type action with the handle. No page text, no value,
# no handle named: closed wording written here. Used for the Gemini configuration only (see `ComputerUse.dropdown_note`).
DROPDOWN_NOTE = ("\nNOTE (system, not page text): you just clicked a drop-down. Its list of options is never drawn in the screenshot, so "
                 "clicking it again shows nothing. Your next action must be the type action with the handle of the fact this drop-down is for, "
                 "then press the Tab key.")


# Also iteration 8b: after a typed handle that was read back as landed, when the next frame looks the same as the one before (a value equal to
# the field's default, such as one adult in a drop-down that already says one), tell the model that it IS entered. Without it a model that
# judges by the picture types the same handle again and again until the stuck-loop detector stops the run (Gemini dev round 1, hh_0003).
ENTERED_NOTE = ("\nNOTE (system, not page text): {handle} IS entered: the field was read back and holds it, although the screen looks the same "
                "as before. Do not type it again; go on to the next field.")

# And: after a click or key press, when trusted code (the same cheap page test the Done check starts from, no model call) says the final
# screen the goal describes is showing, say so. Gemini explored a button on the result page (`Check cliff edges`) before replying DONE and the
# goal check paused the run on it (dev rounds 2 and 5, hh_0002); the cliff step is a separate task that code starts.
FINAL_NOTE = ("\nNOTE (system, not page text): the final screen the goal describes is showing. Reply DONE now and do not press anything else "
              "on it.")


# The browsing profile (a typed task in the agent's own browser; see tasks/browser_runner.py). Code-written wording, never page text.
# An action the provider cannot map used to END the run as "the model gave up" (owner report, 8 Nov 2026: every typed task, because the
# model's `navigate` was not mapped). Now the model is told, once per try, and asked again; only a model that keeps asking for things that
# do not exist is stopped, with its own reason.
UNSUPPORTED_CAP = 4
UNSUPPORTED_NOTE = ("\nNOTE (system, not page text): the action '{name}' is not available in this browser, so nothing was done. You can click, "
                    "type, press keys, scroll, wait, navigate to an address, search and go back. Choose one of those.")
WEB_REJECTED_NOTE = ("\nNOTE (system, not page text): your last action was not allowed, so it was not performed. Only http and https "
                     "addresses can be opened. Choose a different action.")
WEB_NUDGE = ("\nNOTE (system, not page text): you replied without taking an action. If the task is finished, reply DONE: followed by one "
             "plain sentence with the answer. If it is not finished, take the next action on the page. If you cannot finish, reply FAILED: "
             "followed by one word (login, captcha, blocked, payment, missing or other).")
FAILED_CODES = ("login", "captcha", "blocked", "payment", "missing", "other")


def failed_reason_code(summary: str | None) -> str:
    """A closed code for why a run ended as `gave_up`, from the model's closing words: the word after `FAILED:` when it is one of
    `FAILED_CODES` (anything else it wrote is `other`), and `no_action` when it never took a final stance (prose with no DONE or FAILED).
    The model's own sentence is never kept."""
    s = str(summary or "").strip()
    if not s.upper().startswith("FAILED"):
        return "no_action"
    m = re.match(r"(?i)^failed\s*[:\-]?\s*([a-z]+)", s)
    word = m.group(1).lower() if m else ""
    return word if word in FAILED_CODES else "other"


class ProviderSafetyStop(TierError):
    """The provider returned a pending safety check. It is queued for a human, never acknowledged here."""

    def __init__(self, checks: list[dict[str, Any]], queue_id: str | None) -> None:
        super().__init__(f"provider safety check pending ({len(checks)})")
        self.checks, self.queue_id = checks, queue_id


class ActuatorRefused(TierError):
    """An actuator guard refused (wrong frontmost app, locked screen, budget, kill flag)."""


@dataclass(frozen=True)
class TargetRead:
    """What TRUSTED code read at the target of an action: the DOM element under the point, the accessibility element
    under the pointer, or the focused control. Never the model's own words about it. `label` is the accessible name
    (for Enter, the form's default submit button is appended); `role` its role; `field_attrs` the attributes a
    sensitive-field check needs. The gate classifies a pixel click, an Enter press or a newline from this alone."""

    label: str | None
    role: str | None = None
    url: str | None = None
    field_attrs: dict[str, Any] | None = None
    structure: tuple[str, ...] = ()       # what the control structurally is (see security.gates.TargetInfo)

    @property
    def key(self) -> tuple[Any, ...]:
        return (self.label, self.role, self.structure)


class Actuator(Protocol):
    scale: float  # screenshot pixels per point

    async def screenshot(self) -> bytes: ...
    async def execute(self, action: Action) -> None: ...
    async def release_all(self) -> None: ...
    # Optional: async def read_target(self, action) -> TargetRead | None   (an actuator without it is gated as unreadable)
    # Optional: def bind_cancel(self, is_cancelled) -> None                 (stop wins inside a long action)


def merge_reads(reads: list["TargetRead | None"]) -> "TargetRead | None":
    """A drag touches two places: both must be readable, and the gate sees both labels."""
    if not reads or any(r is None for r in reads):
        return None
    first = reads[0]
    labels = [r.label for r in reads if r and r.label]
    structure = tuple(dict.fromkeys(t for r in reads if r for t in r.structure))
    return TargetRead(" / ".join(dict.fromkeys(labels)) if labels else first.label, first.role, first.url,
                      first.field_attrs, structure)


def blank_png(w: int = 1280, h: int = 720) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (245, 245, 245)).save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------- simulated
class SimulatedActuator:
    """Records actions and returns a blank screenshot. Nothing happens anywhere. The default and the test double."""

    def __init__(self, size: tuple[int, int] = (1280, 720), *, max_actions: int = 200,
                 targets: "TargetRead | Callable[[Action], TargetRead | None] | None" = None) -> None:
        self.size = size
        self.scale = 1.0
        self._targets = targets          # what "trusted code" reads at a target; None means unreadable (the safe default)
        self.actions: list[Action] = []
        self.max_actions = max_actions
        self.released = 0
        self.typed = ""
        self.cursor = (size[0] // 2, size[1] // 2)

    async def screenshot(self) -> bytes:
        return blank_png(*self.size)

    async def execute(self, action: Action) -> None:
        if len(self.actions) >= self.max_actions:
            raise ActuatorRefused("action budget used up")
        self.actions.append(action)
        if action.kind in ("click", "double_click", "move"):
            self.cursor = (action.args["x"], action.args["y"])
        elif action.kind == "type":
            self.typed += action.args["text"]

    async def release_all(self) -> None:
        self.released += 1

    async def read_target(self, action: Action) -> "TargetRead | None":
        t = self._targets
        return t(action) if callable(t) else t


_PW_KEYS = {"enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Escape", "escape": "Escape", "space": "Space",
            "backspace": "Backspace", "delete": "Delete", "del": "Delete", "up": "ArrowUp", "down": "ArrowDown",
            "left": "ArrowLeft", "right": "ArrowRight", "home": "Home", "end": "End", "pageup": "PageUp",
            "page_up": "PageUp", "pagedown": "PageDown", "page_down": "PageDown", "ctrl": "Control", "control": "Control",
            "alt": "Alt", "option": "Alt", "shift": "Shift", "cmd": "Meta", "command": "Meta", "meta": "Meta"}


def playwright_key(keys: list[str]) -> str:
    """The pipeline normalises key names to lower case; Playwright wants Enter, ArrowDown, Control and so on."""
    out = []
    for k in keys:
        low = k.lower()
        out.append(_PW_KEYS.get(low) or (low.upper() if re.fullmatch(r"f\d{1,2}", low) else k))
    return "+".join(out)


READ_TARGET_JS = r"""
([x, y]) => {
  const txt = e => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  const CTRL = 'button,a[href],input,select,textarea,summary,[role=button],[role=link],[role=menuitem],[role=checkbox],' +
               '[role=radio],[role=tab],[role=switch],[role=option],[onclick]';
  const BTN = ['submit', 'button', 'reset', 'image'];
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const visible = e => {
    const tag = e.tagName.toLowerCase(), ty = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && BTN.includes(ty)) return (e.value || '').trim();
    return txt(e).slice(0, 120);
  };
  const name = e => {
    const al = e.getAttribute('aria-label'); if (al && al.trim()) return al.trim();
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean).map(txt).join(' ').trim(); if (t) return t; }
    const tag = e.tagName.toLowerCase(), ty = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && BTN.includes(ty)) return (e.value || e.getAttribute('alt') || e.getAttribute('title') || '').trim();
    if (e.labels && e.labels.length) { const t = Array.from(e.labels).map(txt).join(' ').trim(); if (t) return t; }
    if (['input', 'textarea', 'select'].includes(tag)) return (e.getAttribute('placeholder') || e.getAttribute('title') || '').trim();
    const t = txt(e); if (t) return t.slice(0, 120);
    return (e.getAttribute('alt') || e.getAttribute('title') || '').trim();
  };
  const hostOf = u => { try { const x = new URL(u, location.href); return (x.protocol === 'http:' || x.protocol === 'https:') ? x : null; } catch (e) { return null; } };
  // what the ADDRESS says it does: the path and the query KEYS (never values), as words, for the gate to read
  const pathWords = u => { try { const x = new URL(u, location.href);
    return (decodeURIComponent(x.pathname) + ' ' + Array.from(x.searchParams.keys()).join(' ')).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  } catch (e) { return ''; } };
  // Everything the page calls this control, and what it structurally is. The page chooses its names; it does not choose
  // its type, its form target or its href.
  const analyse = c => {
    const tag = c.tagName.toLowerCase(), ty = (c.getAttribute('type') || '').toLowerCase();
    const names = [], st = [];
    const al = (c.getAttribute('aria-label') || '').trim(), vis = visible(c), ti = (c.getAttribute('title') || '').trim();
    for (const n of [al, vis, ti, name(c)]) if (n && !names.map(norm).includes(norm(n))) names.push(n);
    if (al && vis && !norm(al).includes(norm(vis)) && !norm(vis).includes(norm(al))) st.push('label_mismatch');
    const form = c.form || c.closest('form');
    const submits = (tag === 'button' && (ty === 'submit' || ty === '')) || (tag === 'input' && (ty === 'submit' || ty === 'image'));
    if (submits && form) {
      st.push('submit_control');
      // read the ATTRIBUTES: the properties can be clobbered by a field named "action", and a button's formAction
      // property answers with the page's own address when it has no formaction of its own
      const fa = c.getAttribute('formaction') || form.getAttribute('action');
      if (fa !== null && fa !== undefined && fa.trim() !== '') {
        const u = hostOf(fa);
        if (!u || u.origin !== location.origin) st.push('external_form:' + (u ? u.host : 'non-web'));
        const pw = pathWords(fa); if (pw) st.push('path:' + pw);
      }
    }
    if (tag === 'a' && c.hasAttribute('href')) {
      const raw = (c.getAttribute('href') || '').trim();
      const u = hostOf(c.href);
      const back = /^javascript:\s*history\.(back\(\)|go\(\s*-1\s*\))\s*;?$/i.test(raw);   // the one script link that is plainly harmless
      if (!back && (!u || u.origin !== location.origin)) st.push('cross_origin_link:' + (u ? u.host : 'non-web'));
      if (!back && u) { const pw = pathWords(raw); if (pw) st.push('path:' + pw); }
      if (c.hasAttribute('download')) st.push('download');
    }
    if (norm(c.getAttribute('aria-haspopup')) === 'dialog') st.push('opens_dialog');
    return {names, st};
  };
  const focus = (x === null || x === undefined);
  let el = focus ? document.activeElement : document.elementFromPoint(x, y);
  // Typing goes to the focused element INSIDE a same-origin frame, not to the frame element itself (S-28). A cross-origin or
  // sandboxed frame has no readable document: the frame stays the answer, and 'opaque content' below makes it unreadable.
  for (let i = 0; focus && i < 5 && el && ['iframe', 'frame'].includes(el.tagName.toLowerCase()); i++) {
    let inner = null;
    try { inner = el.contentDocument && el.contentDocument.activeElement; } catch (e) { inner = null; }
    if (!inner) break;
    el = inner;
  }
  for (let i = 0; !focus && i < 5 && el && el.shadowRoot && el.shadowRoot.elementFromPoint; i++) {
    const inner = el.shadowRoot.elementFromPoint(x, y); if (!inner || inner === el) break; el = inner;
  }
  if (!el) return {ok: false, why: 'nothing there'};
  if (['iframe', 'frame', 'embed', 'object', 'canvas', 'video'].includes(el.tagName.toLowerCase()))
    return {ok: false, why: 'opaque content'};
  // a custom element (a hyphenated tag) or any shadow host hides what is inside it (a closed shadow root answers with the host)
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    if (n.tagName.indexOf('-') >= 0 || n.shadowRoot) return {ok: false, why: 'opaque custom element'};
  }
  if (focus && (el === document.body || el === document.documentElement)) return {ok: true, label: '', role: 'document', field: null, structure: []};
  let t = el.closest(CTRL);
  if (!t) { const lab = el.closest('label'); t = (lab && lab.control) ? lab.control : el; }
  const tag = t.tagName.toLowerCase(), ty = (t.getAttribute('type') || '').toLowerCase();
  const implicit = {button: 'button', a: 'link', select: 'combobox', textarea: 'textbox', summary: 'button'};
  const byType = {submit: 'button', button: 'button', reset: 'button', image: 'button', checkbox: 'checkbox', radio: 'radio'};
  const role = t.getAttribute('role') || (tag === 'input' ? (byType[ty] || 'textbox') : implicit[tag]) || 'generic';
  const ctrl = !(role === 'generic' && !t.matches(CTRL));
  let own = ctrl ? analyse(t) : {names: [], st: []};
  if (!ctrl) {
    // A plain element can still be a script-driven button (a <div> with a listener, with or without a pointer cursor). Its own
    // text and its ancestors' text up to three levels (short texts only: a button's name, not a paragraph) name it for the gate.
    const parts = [];
    for (let n = t, i = 0; n && n.nodeType === 1 && i < 4; n = n.parentElement, i++) {
      const tx = txt(n); if (tx && tx.length <= 40 && !parts.includes(tx)) parts.push(tx);
    }
    const pointer = getComputedStyle(t).cursor === 'pointer';
    if (pointer && !parts.length) return {ok: false, why: 'unnamed clickable'};
    own = {names: parts, st: pointer ? ['script_clickable'] : []};
  }
  const named = ['button', 'link', 'menuitem', 'tab', 'switch', 'option', 'checkbox', 'radio'].includes(role);
  if (named && !own.names.length) return {ok: false, why: 'unnamed control'};
  // A text box does nothing outward when clicked, whatever its caption says ("Your take-home pay"): its caption is kept for
  // the sensitive-field check, not for the action classes. Enter in it acts as the form's default button, so THAT is read.
  const isField = ['input', 'textarea', 'select'].includes(tag);
  const textField = isField && !(tag === 'input' && (BTN.includes(ty) || ty === 'checkbox' || ty === 'radio'));
  let names = textField ? [] : own.names.slice(), st = textField ? [] : own.st.slice();
  // Implicit submission (Enter presses the form's default button) exists for text-like <input> elements only. A <select> or a
  // <textarea> does not submit on Enter, so the default button's name and structure are not the focused control's: reading them
  // here put the label 'Show my results' (and submit_control, path:results) on a drop-down and sent a benign key press to the drift check.
  if (focus && textField && tag === 'input') {                                   // Enter here submits the form's default button
    const f = t.form || t.closest('form');
    const b = f && f.querySelector('input[type=submit],button[type=submit],button:not([type]),input[type=image]');
    if (b) { const a2 = analyse(b); names = names.concat(a2.names); st = st.concat(a2.st); }
  }
  const field = isField ? {name: t.getAttribute('name') || '', id: t.id || '', label: own.names[0] || '', placeholder: t.getAttribute('placeholder') || '',
                           autocomplete: t.getAttribute('autocomplete') || '', aria_label: t.getAttribute('aria-label') || '',
                           type: ty || (tag === 'input' ? 'text' : tag), role} : null;
  return {ok: true, label: names.join(' / '), role, field, structure: Array.from(new Set(st))};
}
"""


class BrowserPageActuator:
    """Mouse and keyboard on ONE headless Playwright page, in the agent's own context. Not the desktop."""

    def __init__(self, page: Any, *, max_actions: int = 400) -> None:
        self.page, self.scale, self.max_actions, self.n = page, 1.0, max_actions, 0
        self.last_nav_error: str | None = None

    @property
    def url(self) -> str | None:
        try:
            return self.page.url
        except Exception:  # noqa: BLE001
            return None

    async def _read_js(self, arg: list[Any]) -> Any:
        """Run the target read in an ISOLATED world (CDP Page.createIsolatedWorld): the page's own scripts cannot replace
        `document.elementFromPoint` or any other function the read uses (S-26). The DOM is shared, the JavaScript globals are
        not. A page object without a browser context (a test double) falls back to a plain evaluate.

        For a POINTER read there is a second mechanism: the browser's own hit test (`DOM.getNodeForLocation`, the same test a
        real mouse event goes through) must name the element the isolated read found, or one inside or around it. Any
        disagreement, or any failure of either read, makes the target unreadable, which the gate sends to a human."""
        ctx = getattr(self.page, "context", None)
        if ctx is None:
            return await self.page.evaluate(READ_TARGET_JS, arg)
        import json as _json

        cdp = await ctx.new_cdp_session(self.page)
        try:
            fid = (await cdp.send("Page.getFrameTree"))["frameTree"]["frame"]["id"]
            world = await cdp.send("Page.createIsolatedWorld", {"frameId": fid, "worldName": "understudy-read"})
            cid = world["executionContextId"]
            r = await cdp.send("Runtime.evaluate", {"expression": f"({READ_TARGET_JS})({_json.dumps(arg)})",
                                                    "contextId": cid, "returnByValue": True})
            if "exceptionDetails" in r:
                raise RuntimeError("the isolated read failed")
            value = r["result"].get("value")
            if arg[0] is not None and isinstance(value, dict) and value.get("ok"):
                if not await self._hit_agrees(cdp, cid, int(arg[0]), int(arg[1])):
                    return {"ok": False, "why": "the two reads of the target disagree"}
            return value
        finally:
            try:
                await cdp.detach()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    async def _hit_agrees(cdp: Any, context_id: int, x: int, y: int) -> bool:
        """The browser's hit test at (x, y) against the isolated world's `elementFromPoint`: the same element, or one that contains
        the other (a span inside a button), or a shadow host. Anything else is a disagreement."""
        node = await cdp.send("DOM.getNodeForLocation", {"x": x, "y": y, "includeUserAgentShadowDOM": True})
        bid = node.get("backendNodeId")
        if bid is None:
            return False
        obj = (await cdp.send("DOM.resolveNode", {"backendNodeId": bid, "executionContextId": context_id})).get("object") or {}
        if not obj.get("objectId"):
            return False
        out = await cdp.send("Runtime.callFunctionOn", {
            "objectId": obj["objectId"], "returnByValue": True, "arguments": [{"value": x}, {"value": y}],
            "functionDeclaration": "function (x, y) { const n = this.nodeType === 1 ? this : this.parentElement;"
                                   " const e = document.elementFromPoint(x, y); if (!n || !e) return false;"
                                   " if (e === n || e.contains(n) || n.contains(e)) return true;"
                                   " const h = n.getRootNode && n.getRootNode().host;"
                                   " return !!h && (h === e || e.contains(h)); }"})
        return out.get("result", {}).get("value") is True

    async def read_target(self, action: Action) -> TargetRead | None:
        """The element under the pointer (or the focused control, for typing and Enter), read from the DOM by this
        code. None when it cannot be read (nothing there, an iframe or canvas, a button with no name)."""
        a = action.args
        if action.kind in ("click", "double_click"):
            points: list[Any] = [[a["x"], a["y"]]]
        elif action.kind == "drag":
            path = a["path"]
            points = [[path[0]["x"], path[0]["y"]], [path[-1]["x"], path[-1]["y"]]]
        else:
            points = [[None, None]]
        reads: list[TargetRead | None] = []
        for pt in points:
            try:
                r = await self._read_js(pt)
            except Exception:  # noqa: BLE001 - a page mid-navigation cannot be read: unreadable, never "fine"
                return None
            reads.append(TargetRead(r["label"], r["role"], self.url, r.get("field"), tuple(r.get("structure") or ()))
                         if r and r.get("ok") else None)
        return merge_reads(reads)

    async def _eval_isolated(self, js: str, arg: dict[str, Any]) -> Any:
        """Run a page script in the same ISOLATED world as the target read (the page's own scripts cannot replace any function it uses)
        and return its value. Raises on any failure: the callers turn that into `unreadable`, never into "fine"."""
        import json as _json

        ctx = getattr(self.page, "context", None)
        if ctx is None:
            return await self.page.evaluate(js, arg)
        cdp = await ctx.new_cdp_session(self.page)
        try:
            fid = (await cdp.send("Page.getFrameTree"))["frameTree"]["frame"]["id"]
            world = await cdp.send("Page.createIsolatedWorld", {"frameId": fid, "worldName": "understudy-read"})
            r = await cdp.send("Runtime.evaluate", {"expression": f"({js})({_json.dumps(arg)})",
                                                    "contextId": world["executionContextId"], "returnByValue": True})
            if "exceptionDetails" in r:
                raise RuntimeError("the isolated script failed")
            return r["result"].get("value")
        finally:
            try:
                await cdp.detach()
            except Exception:  # noqa: BLE001
                pass

    async def read_back(self, *, expected: str, hint: list[str] | None = None) -> dict[str, Any]:
        """Did the text just typed land in the control that has focus? The comparison runs inside the page script: `expected` goes in, and
        only enums, a short id token and a position come back (never the control's value). See tiers/form_audit.py."""
        from .form_audit import READ_BACK_JS, script_arg

        return await self._eval_isolated(READ_BACK_JS, script_arg(expected=expected, hint=hint))

    async def audit_form(self, items: list[dict[str, Any]], *, stray: bool = False,
                         presence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """The pre-submit audit: for each item (a handle, the value it should hold and where it was bound) say whether the page holds
        it; for each `presence` entry (a handle and the page's own ids for it) say whether a control for it is on screen. Enums only
        come back."""
        from .form_audit import AUDIT_FORM_JS, script_arg

        return await self._eval_isolated(AUDIT_FORM_JS, script_arg(items=items, stray=stray, presence=presence or []))

    async def screenshot(self) -> bytes:
        """A click that submits a form can leave the page mid-navigation; wait for it, and retry once on a timeout."""
        last: Exception | None = None
        for _ in range(2):
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                return await self.page.screenshot(type="png", timeout=15000, animations="disabled")
            except Exception as exc:  # noqa: BLE001 - Playwright timeouts
                last = exc
                await asyncio.sleep(0.2)
        raise ActuatorRefused(f"could not take a screenshot: {type(last).__name__}")

    async def execute(self, action: Action) -> None:
        self.n += 1
        if self.n > self.max_actions:
            raise ActuatorRefused("page actuator action budget used up")
        a, p = action.args, self.page
        if action.kind == "click":
            await p.mouse.click(a["x"], a["y"])
        elif action.kind == "double_click":
            await p.mouse.dblclick(a["x"], a["y"])
        elif action.kind == "move":
            await p.mouse.move(a["x"], a["y"])
        elif action.kind == "type":
            await p.keyboard.type(a["text"])
        elif action.kind == "key":
            await p.keyboard.press(playwright_key(list(a["keys"])))
        elif action.kind == "scroll":
            await p.mouse.wheel(a.get("scroll_x", 0), a.get("scroll_y", 0))
        elif action.kind == "wait":
            await asyncio.sleep(float(a.get("seconds", 1)))
        elif action.kind == "goto":              # only reached through the gates (typed action, denylist, protected pages, data flow, goal check)
            await self._navigate(p.goto(a["url"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS))
        elif action.kind == "back":
            await self._navigate(p.go_back(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS))
        elif action.kind != "screenshot":
            raise ActuatorRefused(f"the page actuator cannot perform {action.kind!r}")

    async def _navigate(self, nav: Awaitable[Any]) -> None:
        """A page that will not load (no such host, a refused connection, too slow) is something the model should SEE in the next screenshot
        (the browser draws its own error page, or what had loaded by then) and decide about, not the end of the run. The class name of the
        failure is kept for the audit line; its message (which holds the address) never is."""
        self.last_nav_error = None
        try:
            await nav
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Playwright's own errors: Error, TimeoutError
            self.last_nav_error = type(exc).__name__

    async def release_all(self) -> None:
        return None


NAV_TIMEOUT_MS = 20000


# ----------------------------------------------------------------------------- real desktop (guarded)
TITLE_BAR_PT = 28.0       # a typing target must be below the window's title bar
TYPE_CHUNK = 6            # at most this many characters are typed per verification
FOCUS_POLL_S = 0.025
FOCUS_WAIT_S = 0.5
REAL_KEYS = frozenset({"enter", "return", "tab", "esc", "escape", "backspace", "left", "right", "up", "down", "home", "end"})
MIN_SHOT_H = 16           # a capture shorter than this is not a screen; the vertical bound is only enforced above it
OVERLAY_OWNERS = tuple(x.strip() for x in os.environ.get("UNDERSTUDY_OVERLAY_OWNERS", "Knack,Understudy,Electron").split(",") if x.strip())


class MacBackend(Protocol):
    """Everything MacActuator needs from the operating system. `QuartzBackend` is the real one; tests pass a fake.
    Methods are synchronous and fast. Coordinates are in POINTS.

    `window_at` returns the topmost on-screen window of ANY layer at the point (that is the window that would take the
    click: the Dock, a notification banner, a floating panel or a system alert count), as a dict with `owner`, `bounds`
    and, when the OS gives them, `number`, `pid`, `layer`, `title`.
    Optional (used when present): `windows_of(owner)`, `element_at(x, y)` and `focused_element()` (accessibility reads:
    dicts with role, title, description, help, secure, in_dialog), `set_stop_check(fn)`, `read_document(app)`."""

    def frontmost_app(self) -> str: ...
    def screen_locked(self) -> bool: ...
    def backing_scale(self) -> float: ...                 # NSScreen.mainScreen().backingScaleFactor()
    def display_width_pts(self) -> float: ...             # CGDisplayBounds width, in points
    def window_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None: ...
    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None: ...   # move | down | up | drag
    def type_text(self, text: str) -> None: ...
    def key(self, keys: list[str]) -> None: ...
    def scroll(self, dx: int, dy: int) -> None: ...
    def screenshot_png(self) -> bytes: ...
    def release_all(self) -> None: ...


def png_size(png: bytes) -> tuple[int, int] | None:
    import struct

    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", png[16:24])
    return int(w), int(h)


def png_width(png: bytes) -> int:
    size = png_size(png)
    if size is None:
        raise ValueError("not a PNG")
    return size[0]


# macOS virtual key codes (ANSI layout) for the chords the model may press.
_KEYCODES = {**{c: k for c, k in zip("asdfhgzxcvbqweryt", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17])},
             "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
             "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
             "enter": 36, "return": 36, "tab": 48, "space": 49, "backspace": 51, "delete": 117, "esc": 53, "escape": 53,
             "left": 123, "right": 124, "down": 125, "up": 126, "home": 115, "end": 119, "pageup": 116, "page_up": 116,
             "pagedown": 121, "page_down": 121}
_MOD_FLAGS = {"cmd": 0x100000, "command": 0x100000, "meta": 0x100000, "shift": 0x20000, "alt": 0x80000, "option": 0x80000,
              "ctrl": 0x40000, "control": 0x40000}

_AX_ROLES = {"AXButton": "button", "AXLink": "link", "AXCheckBox": "checkbox", "AXRadioButton": "radio",
             "AXMenuItem": "menuitem", "AXMenuBarItem": "menuitem", "AXPopUpButton": "button", "AXTextField": "textbox",
             "AXTextArea": "textbox", "AXComboBox": "textbox", "AXSecureTextField": "textbox", "AXTab": "tab"}
_AX_NAMED = {"button", "link", "checkbox", "radio", "menuitem", "tab"}
# roles that carry no action of their own: a click on one changes nothing outward, so an unnamed one is fine (S-29). EVERY other role
# that is not mapped above is an unknown actionable (a group, an image, a menu button, a disclosure triangle, a cell, a slider ...):
# it needs a name like a button, and it is classed as a script-driven clickable, so an unrecognised verb is a human's call.
_AX_HARMLESS = frozenset({"AXTextArea", "AXTextField", "AXStaticText", "AXScrollArea", "AXWindow", "AXSplitGroup"})


def target_from_ax(el: dict[str, Any] | None, *, app: str | None = None) -> TargetRead | None:
    """An accessibility element as the gate wants it. None (unreadable) for a missing element, a role with no name, or an unnamed
    element that can be pressed (AXPress in its actions). Text boxes keep their caption for the sensitive-field check only. The
    harmless unnamed roles are the allow-list `_AX_HARMLESS`; any other role is treated like a button that needs a name."""
    if not el:
        return None
    raw = str(el.get("role") or "")
    role = _AX_ROLES.get(raw) or (raw[2:].lower() if raw.startswith("AX") and len(raw) > 2 else None)
    if not role:
        return None
    names = [str(n).strip() for n in (el.get("title"), el.get("description"), el.get("help")) if n and str(n).strip()]
    structure: tuple[str, ...] = ("opens_dialog",) if el.get("in_dialog") else ()
    if role == "textbox":
        attrs = {"type": "password" if el.get("secure") or raw == "AXSecureTextField" else "text",
                 "label": names[0] if names else "", "role": role}
        return TargetRead("", role, None, attrs, structure)
    pressable = "AXPress" in (el.get("actions") or ())
    if role in _AX_NAMED:
        if not names:
            return None
        return TargetRead(" / ".join(dict.fromkeys(names)), role, None, None, structure)
    if raw in _AX_HARMLESS and not pressable:
        return TargetRead(" / ".join(dict.fromkeys(names)), role, None, None, structure)
    if not names:                                   # an unknown or pressable element with no name: nothing can classify it
        return None
    return TargetRead(" / ".join(dict.fromkeys(names)), role, None, None, (*structure, "script_clickable"))


class QuartzBackend:
    """Real macOS events via pyobjc (Quartz CGEvent, AppKit NSWorkspace/NSScreen, ApplicationServices accessibility).
    Imports lazily; install with `uv run --with pyobjc-framework-Quartz --with pyobjc-framework-Cocoa
    --with pyobjc-framework-ApplicationServices ...`. Reference: scripts/s2_textedit_test.py. The window list and event
    code is exercised against a fake Quartz module; the accessibility reads and real events only by the owner-supervised
    check."""

    def __init__(self) -> None:
        try:
            import AppKit  # noqa: F401
            import Quartz  # noqa: F401
        except ImportError as exc:  # pragma: no cover - needs pyobjc
            raise ImportError("QuartzBackend needs pyobjc-framework-Quartz and pyobjc-framework-Cocoa") from exc
        self._down = False
        self._stop: Callable[[], bool] | None = None

    def set_stop_check(self, fn: Callable[[], bool]) -> None:
        """Polled between every typed character: the kill file, a supervisor Stop. Stop wins inside a long type."""
        self._stop = fn

    def frontmost_app(self) -> str:  # pragma: no cover - real desktop
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName()) if app else ""

    def screen_locked(self) -> bool:  # pragma: no cover - real desktop
        import Quartz

        d = Quartz.CGSessionCopyCurrentDictionary() or {}
        asleep = bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))
        return bool(d.get("CGSSessionScreenIsLocked", 0)) or asleep

    def backing_scale(self) -> float:  # pragma: no cover - real desktop
        from AppKit import NSScreen

        return float(NSScreen.mainScreen().backingScaleFactor())

    def display_width_pts(self) -> float:  # pragma: no cover - real desktop
        import Quartz

        return float(Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.width)

    @staticmethod
    def _win_dict(w: Any) -> dict[str, Any] | None:
        b = w.get("kCGWindowBounds") or {}
        x, y, ww, hh = float(b.get("X", 0)), float(b.get("Y", 0)), float(b.get("Width", 0)), float(b.get("Height", 0))
        if ww <= 0 or hh <= 0 or float(w.get("kCGWindowAlpha", 1.0)) <= 0.0:
            return None
        return {"owner": str(w.get("kCGWindowOwnerName", "")), "bounds": (x, y, ww, hh),
                "layer": int(w.get("kCGWindowLayer", 0)), "title": str(w.get("kCGWindowName", "") or ""),
                "number": w.get("kCGWindowNumber"), "pid": w.get("kCGWindowOwnerPID")}

    def _all_windows(self) -> list[dict[str, Any]]:
        """On-screen windows front to back, EVERY layer (the Dock, banners, floating panels, system alerts and menus take
        clicks too). Skipped: windows with no area or no opacity, the desktop, and the full-display Dock or Window Server
        surfaces and the Understudy overlay (click-through; it covers the display and is never the click's target)."""
        import Quartz

        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        disp = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size
        out = []
        for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
            d = self._win_dict(w)
            if d is None:
                continue
            covers = d["bounds"][2] >= float(disp.width) - 1 and d["bounds"][3] >= float(disp.height) - 1
            if covers and (d["owner"] in ("Dock", "Window Server") or d["owner"] in OVERLAY_OWNERS):
                continue
            out.append(d)
        return out

    def all_windows(self) -> list[dict[str, Any]]:
        """Every on-screen window, front to back, any layer (the list the hit test uses). Metadata only: no pixels are read."""
        return self._all_windows()

    def window_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None:
        """The topmost window of any layer at the point: the one that would receive the click."""
        for d in self._all_windows():
            x, y, ww, hh = d["bounds"]
            if x <= x_pt < x + ww and y <= y_pt < y + hh:
                return d
        return None

    def windows_of(self, owner: str) -> list[dict[str, Any]]:
        """The app's DOCUMENT windows (layer 0, not tiny): what an owner means by "the windows of this app"."""
        return [d for d in self._all_windows() if d["owner"] == owner and d["layer"] == 0
                and d["bounds"][2] * d["bounds"][3] >= 10000.0]

    def all_windows_of(self, owner: str) -> list[dict[str, Any]]:
        """EVERY on-screen window of the app, any size and any layer (a find panel, a popover, a tiny document count). The
        actuator's single-window rule and the preflight use THIS one, so a small topmost window cannot be pinned by mistake."""
        return [d for d in self._all_windows() if d["owner"] == owner]

    def _post(self, ev: Any, flags: int = 0) -> None:
        import Quartz as Q

        Q.CGEventSetFlags(ev, flags)          # explicit: never inherit the modifiers the worker is physically holding (S-13)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def mouse(self, kind: str, x_pt: float, y_pt: float) -> None:  # pragma: no cover - real desktop
        import Quartz as Q

        ev_type = {"move": Q.kCGEventMouseMoved, "down": Q.kCGEventLeftMouseDown, "up": Q.kCGEventLeftMouseUp,
                   "drag": Q.kCGEventLeftMouseDragged}[kind]
        self._post(Q.CGEventCreateMouseEvent(None, ev_type, (x_pt, y_pt), Q.kCGMouseButtonLeft))
        self._down = kind in ("down", "drag") or (self._down and kind != "up")

    def type_text(self, text: str) -> None:
        import Quartz as Q

        for ch in text:
            if self._stop is not None and self._stop():
                self.release_all()
                raise ActuatorRefused("stopped while typing (kill file or supervisor stop)")
            for down in (True, False):
                ev = Q.CGEventCreateKeyboardEvent(None, 0, down)
                Q.CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
                self._post(ev, 0)
                time.sleep(0.012)

    def key(self, keys: list[str]) -> None:
        """A chord: modifiers (cmd, shift, alt/option, ctrl) plus one key from the keycode table, with the flags set
        explicitly on both events. Anything not in the table is refused, never guessed."""
        import Quartz as Q

        mods = [k.lower() for k in keys if k.lower() in _MOD_FLAGS]
        rest = [k.lower() for k in keys if k.lower() not in _MOD_FLAGS]
        if len(rest) != 1 or rest[0] not in _KEYCODES:
            raise ActuatorRefused(f"key chord {keys!r} is not supported by the real actuator")
        flags = 0
        for m in mods:
            flags |= _MOD_FLAGS[m]
        for down in (True, False):
            self._post(Q.CGEventCreateKeyboardEvent(None, _KEYCODES[rest[0]], down), flags)
            time.sleep(0.012)

    def scroll(self, dx: int, dy: int) -> None:  # pragma: no cover - real desktop
        import Quartz as Q

        self._post(Q.CGEventCreateScrollWheelEvent(None, Q.kCGScrollEventUnitPixel, 2, dy, dx))

    def display_pixel_size(self) -> tuple[int, int]:  # pragma: no cover - real desktop
        """Width and height in PIXELS of the main display, read from the captured image: nothing is encoded or kept."""
        import Quartz as Q

        img = Q.CGDisplayCreateImage(Q.CGMainDisplayID())
        if img is None:
            raise ActuatorRefused("the display could not be read (is Screen Recording allowed?)")
        return int(Q.CGImageGetWidth(img)), int(Q.CGImageGetHeight(img))

    @staticmethod
    def _png_of(img: Any) -> bytes:  # pragma: no cover - real desktop
        """A CGImage to PNG bytes in memory (ImageIO into a mutable data object). No file, no path, no helper process."""
        import Quartz as Q
        from Foundation import NSMutableData

        data = NSMutableData.data()
        dest = Q.CGImageDestinationCreateWithData(data, "public.png", 1, None)
        if dest is None:
            raise ActuatorRefused("could not start an in-memory PNG encoder")
        Q.CGImageDestinationAddImage(dest, img, None)
        if not Q.CGImageDestinationFinalize(dest):
            raise ActuatorRefused("could not encode the captured frame")
        return bytes(data)

    def screenshot_png(self) -> bytes:  # pragma: no cover - real desktop
        """The main display as PNG bytes, captured and encoded in memory (D30: a frame is held for one call and never written)."""
        import Quartz as Q

        img = Q.CGDisplayCreateImage(Q.CGMainDisplayID())
        if img is None:
            raise ActuatorRefused("the display could not be captured (is Screen Recording allowed?)")
        return self._png_of(img)

    def window_png(self, window_number: int) -> bytes:  # pragma: no cover - real desktop
        """ONE window (the pinned target) as PNG bytes, in memory: for R2 and later, so other apps never enter a frame."""
        import Quartz as Q

        img = Q.CGWindowListCreateImage(Q.CGRectNull, Q.kCGWindowListOptionIncludingWindow, int(window_number),
                                        Q.kCGWindowImageBoundsIgnoreFraming)
        if img is None:
            raise ActuatorRefused("the window could not be captured")
        return self._png_of(img)

    def secure_input(self) -> bool:  # pragma: no cover - real desktop
        """True while macOS secure input is on (a password field has the keyboard): the login session's own dictionary carries the pid of the
        process that turned it on (`kCGSSessionSecureInputPID`). A status read, no prompt, no capture. If the dictionary cannot be read the
        answer is True: unknown counts as on, so a frame is not sent. NOT yet confirmed on the real Mac against a focused password field."""
        try:
            import Quartz

            d = Quartz.CGSessionCopyCurrentDictionary()
            if d is None:
                return True
            return bool(d.get("kCGSSessionSecureInputPID"))
        except Exception:  # noqa: BLE001
            return True

    def release_all(self) -> None:
        if self._down:
            import Quartz as Q

            p = Q.CGEventGetLocation(Q.CGEventCreate(None))
            self.mouse("up", float(p.x), float(p.y))
            self._down = False

    # ---- accessibility (needs the Accessibility permission the owner already grants for events)
    def _ax_dict(self, el: Any) -> dict[str, Any] | None:  # pragma: no cover - real desktop
        import ApplicationServices as AS

        def attr(e: Any, name: str) -> Any:
            err, val = AS.AXUIElementCopyAttributeValue(e, name, None)
            return val if err == 0 else None

        role = attr(el, "AXRole")
        if not role:
            return None
        win = attr(el, "AXWindow")
        wrole, wsub = (attr(win, "AXRole"), attr(win, "AXSubrole")) if win is not None else (None, None)
        in_dialog = str(wrole) == "AXSheet" or str(wsub) in ("AXDialog", "AXSystemDialog", "AXFloatingWindow")
        try:
            aerr, acts = AS.AXUIElementCopyActionNames(el, None)
            actions = [str(a) for a in acts] if aerr == 0 and acts else []
        except Exception:  # noqa: BLE001 - no action list: only the role and the name can speak
            actions = []
        return {"role": str(role), "subrole": str(attr(el, "AXSubrole") or ""), "title": attr(el, "AXTitle"),
                "description": attr(el, "AXDescription"), "help": attr(el, "AXHelp"), "actions": actions,
                "secure": str(attr(el, "AXSubrole") or "") == "AXSecureTextField", "in_dialog": bool(in_dialog)}

    def element_at(self, x_pt: float, y_pt: float) -> dict[str, Any] | None:  # pragma: no cover - real desktop
        try:
            import ApplicationServices as AS

            err, el = AS.AXUIElementCopyElementAtPosition(AS.AXUIElementCreateSystemWide(), x_pt, y_pt, None)
            return self._ax_dict(el) if err == 0 and el is not None else None
        except Exception:  # noqa: BLE001 - unreadable, which the gate sends to a human
            return None

    def focused_element(self) -> dict[str, Any] | None:  # pragma: no cover - real desktop
        try:
            import ApplicationServices as AS

            err, el = AS.AXUIElementCopyAttributeValue(AS.AXUIElementCreateSystemWide(), "AXFocusedUIElement", None)
            return self._ax_dict(el) if err == 0 and el is not None else None
        except Exception:  # noqa: BLE001
            return None

    def read_document(self, app: str) -> str | None:  # pragma: no cover - real desktop
        """The frontmost document's text, read by trusted code through the OS (AppleScript), never by the model."""
        import subprocess

        if app != "TextEdit":
            return None
        r = subprocess.run(["osascript", "-e", 'tell application "TextEdit" to get text of document 1'],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.rstrip("\n") if r.returncode == 0 else None


class MacActuator:
    """Real desktop actuator behind every guard. Only constructed when UNDERSTUDY_REAL_ACTUATOR=1, and only ever
    for the named harmless target app.

    Guards (a failure aborts, releases held buttons and keys, and raises ActuatorRefused):
      * scale: points come from the BACKING scale (NSScreen), cross-checked against screenshot pixel width divided by
        the display's width in points; if they disagree nothing is done. No pointer action runs before a screenshot
        has verified the scale.
      * space: a pointer point must lie inside the screenshot the model saw (no negatives, nothing beyond it).
      * hit test before EVERY pointer action: the topmost window of ANY layer at the point must belong to the target
        app (a banner, the Dock or an alert above it refuses) and, once the run has pinned its window at the first click,
        must be THAT window (same number and pid; a second window of the same app refuses). The probe is repeated
        immediately before every mouse-down with no wait in between.
      * pointer buttons other than left, and held modifier keys, are refused rather than silently dropped.
      * after a click, poll up to 500 ms for two consecutive reads where the frontmost app AND the window at the click
        point are the target window; otherwise abort (activation lag is exactly what this catches).
      * before EVERY typed chunk (at most 6 characters) and every key event the same check is repeated at the last
        verified click point. Typing without a verified click is refused. The kill file and the supervisor stop are
        polled between chunks AND between characters.
      * if the backend can enumerate windows, the target app must have exactly one at the first click.
      * kill flag, supervisor stop, locked or asleep screen, action budget and time budget before every event.
    `report` records the scale cross-check and every hit test for the owner to read."""

    is_real = True

    def __init__(self, target_app: str, *, backend: MacBackend | None = None, kill_flag: Path | None = None,
                 max_actions: int = 40, time_budget_s: float = 120.0,
                 clock: Callable[[], float] = time.monotonic, env: dict[str, str] | None = None,
                 focus_wait_s: float = FOCUS_WAIT_S, focus_poll_s: float = FOCUS_POLL_S,
                 is_cancelled: Callable[[], bool] | None = None, require_single_window: bool = True,
                 permit: Any = None, pinned_window: dict[str, Any] | None = None, window_capture: bool = False) -> None:
        if (env if env is not None else os.environ).get("UNDERSTUDY_REAL_ACTUATOR") != "1":
            raise ActuatorRefused("the real actuator is disabled; set UNDERSTUDY_REAL_ACTUATOR=1 (owner present only)")
        if not target_app:
            raise ActuatorRefused("a target app name is required")
        self.target_app = target_app
        self.permit = permit                   # a RunPermit (tiers/owner_present.py): without a valid one every action is refused
        self.backend = backend or QuartzBackend()
        self._kill = kill_flag
        self._cancelled = is_cancelled
        self.max_actions, self.time_budget_s, self._clock = max_actions, time_budget_s, clock
        self._focus_wait, self._focus_poll = focus_wait_s, focus_poll_s
        self._require_single = require_single_window
        self._started = clock()
        self.n = 0
        self.scale = float(self.backend.backing_scale())
        self._scale_verified = False
        self._shot_px: tuple[int, int] | None = None
        self._last_point: tuple[float, float] | None = None
        self._pin: tuple[Any, ...] | None = None
        self._expected: TargetRead | None = None
        self._origin: tuple[float, float] = (0.0, 0.0)     # window capture: where the picture's top-left corner is on the display, in points
        self.report: dict[str, Any] = {"target_app": target_app, "backing_scale": self.scale, "scale_check": None,
                                       "hits": [], "typed_chars": 0, "pinned_window": None}
        # A run for ONE window the worker was shown (a typed task): the window is pinned from the start, by number and pid, instead of at the
        # first click, so no other window of the same app can ever be acted in. With `window_capture` the model is shown that window ALONE
        # (never the display), so nothing of any other app enters a frame, and its picture's pixels are mapped through the window's origin.
        if window_capture and not pinned_window:
            raise ActuatorRefused("window capture needs the pinned window")
        self._window_capture = bool(window_capture and pinned_window)
        if pinned_window:
            if pinned_window.get("number") is None or pinned_window.get("owner", target_app) != target_app:
                raise ActuatorRefused("the pinned window must be a window of the target app with a window number")
            self._pin = self._identity(pinned_window)
            self.report["pinned_window"] = {"number": pinned_window.get("number"), "pid": pinned_window.get("pid")}
            if self._window_capture:
                self._origin = (float(pinned_window["bounds"][0]), float(pinned_window["bounds"][1]))
        stop = getattr(self.backend, "set_stop_check", None)
        if callable(stop):
            stop(self._should_stop)

    # ------------------------------------------------------------------ guards
    def bind_cancel(self, is_cancelled: Callable[[], bool]) -> None:
        self._cancelled = is_cancelled

    def expect_target(self, target: TargetRead | None) -> None:
        """What trusted code read at the next pointer action's target. Re-read immediately before the mouse-down; a
        different or unreadable target aborts (the screen moved between the read and the click)."""
        self._expected = target

    def _should_stop(self) -> bool:
        flag = self._kill or kill_flag_path()
        return flag.exists() or bool(self._cancelled and self._cancelled())

    def _abort(self, why: str) -> None:
        try:
            self.backend.release_all()
        finally:
            self.report["aborted"] = why
            raise ActuatorRefused(why)

    def _guard_passive(self) -> None:
        if self.permit is None or not self.permit.valid_for(self.target_app):
            self._abort("no valid owner permit: a real-desktop run needs the owner's one-time token consumed for this target")
        flag = self._kill or kill_flag_path()
        if flag.exists():
            try:                                    # how long the stop took to be honoured (the owner reads this at R1)
                self.report["kill_latency_ms"] = round(max(0.0, time.time() - flag.stat().st_mtime) * 1000, 1)
            except OSError:
                pass
            self._abort("kill flag present")
        if self._cancelled is not None and self._cancelled():
            self._abort("the run was stopped (supervisor stop or a human took over)")
        if self.backend.screen_locked():
            self._abort("screen is locked or asleep")

    def _guard(self) -> None:
        self._guard_passive()
        front = self.backend.frontmost_app()
        if front != self.target_app:
            self._abort(f"frontmost app is {front!r}, not {self.target_app!r}")
        if self.n >= self.max_actions:
            self._abort("action budget used up")
        if self._clock() - self._started > self.time_budget_s:
            self._abort("time budget used up")

    @staticmethod
    def _identity(w: dict[str, Any]) -> tuple[Any, ...]:
        if w.get("number") is not None:
            return ("n", w.get("number"), w.get("pid"))
        return ("t", w.get("owner"), w.get("title"))

    def _window_ok(self, w: dict[str, Any] | None, *, y_pt: float, need_body: bool) -> str | None:
        """None if the window may be acted in, else why not."""
        if w is None:
            return "no window there"
        if w["owner"] != self.target_app:
            return f"the window at that point belongs to {w['owner']!r}, not {self.target_app!r}"
        if self._pin is not None and self._identity(w) != self._pin:
            return "the window under the point is not the window this run started in (another window of the same app)"
        bx, by, bw, bh = w["bounds"]
        if need_body and y_pt < by + TITLE_BAR_PT:
            return "the point is in the window's title bar, not in its body"
        return None

    def _hit(self, x_pt: float, y_pt: float, *, label: str, need_body: bool) -> dict[str, Any]:
        """Refuse unless the topmost window of any layer at the point is the target app's (pinned) window."""
        w = self.backend.window_at(x_pt, y_pt)
        rec = {"at": label, "x_pt": round(x_pt, 2), "y_pt": round(y_pt, 2), "scale": self.scale,
               "owner": (w or {}).get("owner"), "bounds": (w or {}).get("bounds"),
               "number": (w or {}).get("number"), "pid": (w or {}).get("pid")}
        self.report["hits"].append(rec)
        if w is not None and self._pin is None and need_body and w["owner"] == self.target_app:
            self._pin_window(w)
        why = self._window_ok(w, y_pt=y_pt, need_body=need_body)
        if why:
            self._abort(f"{why} ({x_pt:.0f}, {y_pt:.0f}) pt; refusing to act there" if w is None else why)
        return rec

    def _pin_window(self, w: dict[str, Any]) -> None:
        """The first verified click names the window this run acts in. Where the OS can enumerate windows, the target
        app must have exactly one, so the first click cannot land in the wrong one of several."""
        ws = getattr(self.backend, "all_windows_of", None) or getattr(self.backend, "windows_of", None)
        if self._require_single and callable(ws):
            wins = ws(self.target_app)
            if len(wins) != 1:
                self._abort(f"{self.target_app} has {len(wins)} windows on screen; close the others so the run cannot reach the wrong one")
            if self._identity(wins[0]) != self._identity(w):
                self._abort("the window under the point is not the app's one window on screen")
        self._pin = self._identity(w)
        self.report["pinned_window"] = {"number": w.get("number"), "pid": w.get("pid")}

    def _pt(self, v: int) -> float:
        return v / self.scale

    def _xy(self, x: int, y: int) -> tuple[float, float]:
        """A pixel of the picture the model saw, as a point on the display (the window's origin is added in window-capture mode)."""
        return self._origin[0] + x / self.scale, self._origin[1] + y / self.scale

    def _pinned_now(self) -> dict[str, Any] | None:
        """The pinned window as the OS lists it right now (by number and pid), or None if it is not on screen."""
        ws = getattr(self.backend, "all_windows_of", None) or getattr(self.backend, "windows_of", None)
        if not callable(ws):
            return None
        for w in ws(self.target_app):
            if self._pin is not None and self._identity(w) == self._pin:
                return w
        return None

    def _check_window_unmoved(self) -> None:
        """Window capture: the picture's pixels map to the display through the window's origin. If the window moved or went away since
        the picture was taken, a click would land on the wrong control, so nothing is done."""
        if not self._window_capture:
            return
        w = self._pinned_now()
        if w is None:
            self._abort("the window this run works in is no longer on screen")
        bx, by = float(w["bounds"][0]), float(w["bounds"][1])
        if abs(bx - self._origin[0]) > 1.0 or abs(by - self._origin[1]) > 1.0:
            self._abort("the window moved since the screenshot, so the click was not made")

    def _check_px(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            self._abort("a negative coordinate is outside the screenshot the model saw")
        if self._shot_px is not None:
            w, h = self._shot_px
            if x >= w or (h >= MIN_SHOT_H and y >= h):
                self._abort(f"the point ({x}, {y}) px is outside the {w}x{h} screenshot the model saw")

    async def _focus_stable(self, x_pt: float, y_pt: float, *, need_body: bool) -> None:
        """Wait up to 500 ms for TWO consecutive consistent reads; abort if they never come."""
        deadline = self._clock() + self._focus_wait
        good = 0
        while True:
            w = self.backend.window_at(x_pt, y_pt)
            ok = (self.backend.frontmost_app() == self.target_app
                  and self._window_ok(w, y_pt=y_pt, need_body=need_body) is None)
            good = good + 1 if ok else 0
            if good >= 2:
                return
            if self._clock() >= deadline:
                self._abort("focus did not settle on the target app and window after the click")
            await asyncio.sleep(self._focus_poll)

    async def _verify_typing_target(self) -> None:
        self._guard()
        if self._last_point is None:
            self._abort("no verified click target yet; refusing to type")
        await self._focus_stable(*self._last_point, need_body=True)

    # ------------------------------------------------------------------ trusted target reads (the gate's evidence)
    async def read_target(self, action: Action) -> TargetRead | None:
        """What is under the pointer (or focused, for typing and Enter), read through accessibility. None if the
        backend cannot read it, which the gate sends to a human."""
        self._guard_passive()
        a = action.args
        elem, focus = getattr(self.backend, "element_at", None), getattr(self.backend, "focused_element", None)
        reads: list[TargetRead | None] = []
        if action.kind in ("click", "double_click", "drag"):
            if elem is None:
                return None
            pts = [(a["x"], a["y"])] if action.kind != "drag" else [(a["path"][0]["x"], a["path"][0]["y"]),
                                                                     (a["path"][-1]["x"], a["path"][-1]["y"])]
            for px, py in pts:
                reads.append(target_from_ax(elem(*self._xy(px, py)), app=self.target_app))
        else:
            if focus is None:
                return None
            reads.append(target_from_ax(focus(), app=self.target_app))
        return merge_reads(reads)

    async def _expect_matches(self, action: Action) -> bool:
        exp, self._expected = self._expected, None
        if exp is None:
            return True
        now = await self.read_target(action)
        return now is not None and now.key == exp.key

    # ------------------------------------------------------------------ screenshot and scale
    async def screenshot(self) -> bytes:
        self._guard_passive()
        if self._window_capture:
            w = self._pinned_now()
            if w is None:
                self._abort("the window this run works in is no longer on screen")
            self._origin = (float(w["bounds"][0]), float(w["bounds"][1]))
            png = self.backend.window_png(int(w["number"]))      # the one window, in memory: no other app is in the frame
            pts = float(w["bounds"][2])
        else:
            png = self.backend.screenshot_png()
            pts = float(self.backend.display_width_pts())
        size = png_size(png)
        if size is None:
            self._abort("the screenshot is not a PNG")
        px = size[0]
        measured = px / pts if pts else 0.0
        ok = abs(measured - self.scale) <= 0.05 or (self._window_capture and abs(px - pts * self.scale) <= 2.0)
        self.report["scale_check"] = {"backing_scale": self.scale, "screenshot_px": px, "display_pts": pts,
                                      "measured_scale": round(measured, 3), "agree": ok}
        if not ok:
            self._abort(f"scale disagreement: backing scale {self.scale} but the screenshot says {measured:.3f}")
        self._scale_verified = True
        self._shot_px = size
        return png

    # ------------------------------------------------------------------ actions
    async def execute(self, action: Action) -> None:
        self._guard()
        a = action.args
        self.n += 1
        try:
            if action.kind in ("move", "click", "double_click", "scroll", "drag"):
                if a.get("button", "left") != "left":
                    self._abort("only the left mouse button is supported by the real actuator")
                if a.get("hold_keys"):
                    self._abort("held modifier keys are not supported by the real actuator")
                if not self._scale_verified:
                    self._abort("the display scale has not been verified against a screenshot yet")
                if action.kind == "drag":
                    await self._drag(a["path"])
                    return
                self._check_px(a["x"], a["y"])
                self._check_window_unmoved()
                x, y = self._xy(a["x"], a["y"])
                self._hit(x, y, label=action.kind, need_body=action.kind != "move")
                self.backend.mouse("move", x, y)
                if action.kind == "move":
                    return
                await asyncio.sleep(0.05)
                self._guard()
                if action.kind == "scroll":
                    self._hit(x, y, label="scroll:recheck", need_body=True)
                    self.backend.scroll(int(a.get("scroll_x", 0)), int(a.get("scroll_y", 0)))
                    return
                for i in range(2 if action.kind == "double_click" else 1):
                    # one atomic step: probe the window, re-read the target, press, with no wait between (S-18)
                    self._guard_passive()
                    self._hit(x, y, label=f"{action.kind}:before-down", need_body=True)
                    if i == 0 and not await self._expect_matches(action):
                        self._abort("the control under the pointer is not the one that was authorised")
                    self.backend.mouse("down", x, y)
                    await asyncio.sleep(0.04)
                    self.backend.mouse("up", x, y)
                await self._focus_stable(x, y, need_body=True)   # activation lag is caught here, before any typing
                self._last_point = (x, y)
            elif action.kind == "type":
                text = a["text"]
                for i in range(0, len(text), TYPE_CHUNK):
                    await self._verify_typing_target()     # re-verify before EVERY chunk
                    chunk = text[i:i + TYPE_CHUNK]
                    self.backend.type_text(chunk)
                    self.report["typed_chars"] += len(chunk)
            elif action.kind == "key":
                if a.get("hold_keys"):
                    self._abort("held modifier keys are not supported by the real actuator")
                if len(a["keys"]) != 1 or str(a["keys"][0]).lower() not in REAL_KEYS:
                    # the real desktop takes single named keys only (S-25): no chord can leave the app, save, close or quit
                    self._abort("the real actuator presses only enter, tab, escape, backspace, arrows, home and end")
                await self._verify_typing_target()
                self.backend.key(list(a["keys"]))
            elif action.kind == "wait":
                await asyncio.sleep(float(a.get("seconds", 1)))
            elif action.kind != "screenshot":
                self._abort(f"action kind {action.kind!r} is not supported by the real actuator")
        except ActuatorRefused:
            raise
        except BaseException:
            self.backend.release_all()
            raise

    async def _drag(self, path: list[dict[str, int]]) -> None:
        """Press at the first point, move through the rest, release at the last: every point is checked in the pixel
        space and hit-tested, and the button is always released."""
        for p in path:
            self._check_px(p["x"], p["y"])
        self._check_window_unmoved()
        pts = [self._xy(p["x"], p["y"]) for p in path]
        for i, (x, y) in enumerate(pts):
            self._hit(x, y, label=f"drag:{i}", need_body=True)
        sx, sy = pts[0]
        self.backend.mouse("move", sx, sy)
        await asyncio.sleep(0.05)
        self._guard()
        self._hit(sx, sy, label="drag:before-down", need_body=True)
        if not await self._expect_matches(Action("drag", {"path": path})):
            self._abort("the control under the pointer is not the one that was authorised")
        try:
            self.backend.mouse("down", sx, sy)
            for x, y in pts[1:]:
                self._guard()
                self._hit(x, y, label="drag:move", need_body=True)
                self.backend.mouse("drag", x, y)
                await asyncio.sleep(0.02)
            ex, ey = pts[-1]
            self._hit(ex, ey, label="drag:before-up", need_body=True)
            self.backend.mouse("up", ex, ey)
        except BaseException:
            self.backend.release_all()
            raise
        await self._focus_stable(*pts[-1], need_body=True)
        self._last_point = pts[-1]

    async def release_all(self) -> None:
        self.backend.release_all()


# ----------------------------------------------------------------------------- the tier-3 loop
@dataclass
class Tier3Result:
    outcome: str                       # done | claimed_not_verified | gave_up | stalled | step_cap | stopped
    steps: int = 0
    claimed_done: bool = False
    false_claim: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)
    progress_steps: int = 0            # steps after which the screen had visibly changed
    refusals: int = 0                  # typed literals, unknown handles or letter keys refused by the fact-handle check
    done_summary_len: int = 0
    last_summary: str = ""             # the model's own closing words (model output, never page text or values)
    prompt_chars: list[int] = field(default_factory=list)   # size of the TEXT sent each step (goal, task state, history); frames excluded
    resets: int = 0                    # times the provider's conversation was restarted from the compact task state
    nudges: int = 0                    # times the model ended its turn early and the system told it, in its own words, to continue
    premature_claims: int = 0          # of those, how many were a claimed success that code then refused to confirm
    inputs: str = "n/a"                # the form audit's state when the loop ended (n/a | unaudited | clean | mismatch | uncertain); tiers/form_audit.py
    readback_failures: int = 0         # typed handles that did NOT land in the control that had focus (the handle stays pending)
    audit_blocks: int = 0              # final-button presses held back because the form was not as the facts say
    audit: dict[str, Any] = field(default_factory=dict)   # the audit's summary: enums, counts and handle ids only
    model_retries: int = 0             # model calls asked again after a transient provider failure (the answer, never an action, was lost)
    model_retry_classes: list[str] = field(default_factory=list)   # the error class (a closed enum) of each, in order
    why: str = ""                      # for outcome gave_up: a closed code (FAILED_CODES, `no_action` or `unsupported`); never the model's words
    unsupported: int = 0               # actions the provider could not map (told to the model, asked again; see UNSUPPORTED_CAP)


# A provider failure that only says "try again": a rate limit, a timeout, a dropped connection or a server error, and an answer that
# arrived empty, cut off or malformed. A refusal, a refused key and a blocked answer are the same on the next ask, and an error nothing
# classifies is a bug to see, not to hide, so none of those is asked again.
MODEL_RETRY_CLASSES = frozenset({"rate_limit", "timeout", "transport", "invalid_answer"})
MODEL_RETRIES = 2                       # asks after the first (so at most 3 calls per step)
MODEL_BACKOFF_S = (0.5, 1.5)            # fixed waits before ask 2 and ask 3: no jitter, so a test can predict every wait


FP_SIZE = (640, 400)
PIXEL_DELTA = 24        # grey levels a pixel must move to count as changed
CHANGED_PIXELS = 12     # changed pixels (at 640 x 400) that make a screen "different": a typed digit is 15 to 25


def screen_fingerprint(png: bytes) -> bytes | None:
    """A half-size grey-scale copy of a screenshot, to tell whether the screen changed. None if undecodable."""
    try:
        from PIL import Image

        return Image.open(io.BytesIO(png)).convert("L").resize(FP_SIZE).tobytes()
    except Exception:  # noqa: BLE001
        return None


def screen_changed(a: bytes, b: bytes, min_pixels: int = CHANGED_PIXELS) -> bool:
    """True if at least `min_pixels` pixels moved by more than PIXEL_DELTA grey levels. One typed character changes
    well over a dozen pixels; a pointer shadow or anti-aliasing flicker does not."""
    if len(a) != len(b) or not a:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y and abs(x - y) > PIXEL_DELTA:
            n += 1
            if n >= min_pixels:
                return True
    return False


_TARGETED = ("click", "double_click", "drag", "type", "key")   # actions whose effect depends on what is under them


def seed_working_memory(goal_id: str, handles: list[str], snapshot: dict[str, Any] | None, *, page_kept: bool) -> WorkingMemory:
    """The working memory for a tier-3 attempt: new, or seeded from a snapshot of an earlier attempt or of a checkpoint. What was
    VERIFIED by code, the step count and the open problems carry over. What belongs to a PAGE (the handles typed on it, the page state)
    carries over only when the page is kept: on a fresh page nothing is typed and nothing is known, so every handle is pending again and
    the memory says it was resumed. A snapshot that is invalid or for another task or another list of handles is ignored."""
    fresh = lambda: WorkingMemory(goal_id, handles=handles, pending=handles, last_k=6)  # noqa: E731
    if snapshot is None:
        return fresh()
    try:
        wm = WorkingMemory.restore(snapshot)
    except (TypedIdError, ValueError, KeyError, TypeError):
        return fresh()
    if wm.goal_id != goal_id or tuple(wm.handles) != tuple(handles):
        return fresh()
    if page_kept:
        wm.add_problem("previous_attempt_failed")
    else:
        wm.mark_resumed()
        wm.set_pending(handles)
    return wm


class ComputerUse:
    """The tier-3 loop. Budgeting is by PROGRESS, not a flat cap: the run may go on while the screen keeps changing
    (a form being filled, pages advancing) up to `max_steps`, and stops early after `stall_limit` consecutive steps in
    which the screen did not change (the stuck-loop detector covers repeats on top of that).

    `facts` switches on fact handles: typed text must be exactly one handle from the closed vocabulary, which is
    resolved to the real value only at the moment of actuation. Without `facts` the loop behaves as before."""

    def __init__(self, model: ModelPort, actuator: Actuator, guard: Guard, *, navigator: str,
                 emit: Emit | None = None, is_current: Callable[[], bool] = lambda: True, step_start: int = 0,
                 max_steps: int = 120, deadline_s: float = 600.0, screenshot_size: tuple[int, int] = (1280, 720),
                 facts: Any = None, stall_limit: int = 12, pause: Any = None, context_reset_every: int = 4, max_nudges: int = 2, stateless: bool | None = None,
                 resume_wm: dict[str, Any] | None = None, page_kept: bool = False,
                 on_snapshot: Callable[[int, dict[str, Any]], None] | None = None, postcondition: str = "final_page",
                 form_audit: FormAudit | None = None, dropdown_note: bool | None = None, entered_note: bool | None = None,
                 final_hint: Callable[[], Awaitable[bool]] | None = None, final_note: bool | None = None,
                 model_retries: int = MODEL_RETRIES, model_backoff_s: tuple[float, ...] = MODEL_BACKOFF_S,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, profile: str | None = None) -> None:
        # `profile="web"` is a typed browsing task (tasks/browser_runner.py): it has no ground truth for code to check, so a model that says DONE
        # is not sent back to look for a "final screen" (only an answer with no DONE or FAILED at all is asked to carry on, in words that fit
        # a free task), the provider is told to use its browsing wording, and a rejected action is explained to the model. Every other
        # profile (none) is exactly the loop that was validated on the forms and the desktop.
        self.profile = profile
        self.model_retries, self.model_backoff_s, self._sleep = max(0, int(model_retries)), tuple(model_backoff_s) or (0.0,), sleep
        self.model_retry_classes: list[str] = []      # kept on the instance too, so a run that ends in an exception still reports them
        if stateless is None:                  # UNDERSTUDY_CU_STATELESS=0 opts back into the chained provider thread (comparison only)
            stateless = os.environ.get("UNDERSTUDY_CU_STATELESS", "1").strip().lower() not in ("0", "false", "no", "off")
        self.stateless = stateless               # no provider-side thread: each step is goal + code-built working memory + ONE fresh frame
        self.max_nudges = max_nudges             # early endings the loop answers with a code-written 'not finished, continue'
        self.context_reset_every = context_reset_every   # bounded working memory: restart the provider's thread this often
        self.model, self.actuator, self.guard, self.navigator = model, actuator, guard, navigator
        self.emit, self.is_current, self.step_start = emit, is_current, step_start
        self.max_steps, self.deadline_s, self.size = max_steps, deadline_s, screenshot_size
        self.facts, self.stall_limit, self.pause = facts, stall_limit, pause
        self.stuck = StuckDetector()
        self.last_steps = 0
        # A snapshot of the working memory to seed from (a resume after a kill, or a second attempt after a failure); `page_kept` says
        # whether the page the new attempt starts on is the one the snapshot was taken on. `on_snapshot(steps, snapshot)` is called after
        # every step with the typed snapshot (the run checkpoint). `postcondition` is the id recorded when code verifies the final page.
        self.resume_wm, self.page_kept, self.on_snapshot, self.postcondition = resume_wm, page_kept, on_snapshot, postcondition
        self.wm: Any = None
        self.last_manifest: dict[str, Any] | None = None
        # The typed-input read-back and the pre-submit audit (tiers/form_audit.py). Only an actuator that can read the page's controls takes
        # part (the page actuator); the desktop and simulated actuators run exactly as before.
        self.form_audit = form_audit
        self._audit_logged = 0
        if dropdown_note is None or entered_note is None or final_note is None:    # the Gemini fit (iteration 8b); every other provider's prompts are as they were
            from ..models.gemini_provider import fit_enabled

            fit = getattr(model, "name", "") == "gemini" and fit_enabled()
            dropdown_note = fit if dropdown_note is None else dropdown_note
            entered_note = fit if entered_note is None else entered_note
            final_note = fit if final_note is None else final_note
        self.dropdown_note, self.entered_note, self.final_note = bool(dropdown_note), bool(entered_note), bool(final_note)
        self.final_hint = final_hint

    def _snapshot(self, steps: int, wm: Any) -> None:
        if self.on_snapshot is None:
            return
        try:
            self.on_snapshot(steps, wm.snapshot())
        except Exception:  # noqa: BLE001 - a checkpoint that cannot be written must not stop the run; it is noted, never silent
            self.guard.note("checkpoint_failed", "failed", "snapshot", tier=3)

    @staticmethod
    def _sync_memory(wm: Any, res: "Tier3Result", synced: int, base: int = 0) -> int:
        """Typed step records into the working memory, from the history the loop keeps (handle names, kinds, outcomes)."""
        from ..context.working import Outcome, StepRecord, code_of

        for i in range(synced, len(res.history)):
            h = res.history[i]
            handle = h.get("handle")
            why = code_of(h.get("why") or "", "")
            if h.get("ok") is False:
                outcome = Outcome.REFUSED if why in ("literal_text", "unknown_handle", "key_types_text", "value_not_single_line") else Outcome.FAILED
            else:
                outcome = Outcome.OK
            wm.record(StepRecord(n=base + i + 1, kind="type_fact" if handle else code_of(h.get("kind"), "step"),
                                 target=code_of(handle or "", ""), outcome=outcome, tier=3, code=why if h.get("ok") is False else "",
                                 verified=code_of(h.get("verified") or "", "")))
        return len(res.history)

    @staticmethod
    def _task_state(res: "Tier3Result") -> str:
        """The code-kept TASK STATE: authoritative after any restart of the provider's thread. Built only from typed step
        records (handle names, counts), so it holds no value, no page text and no model prose, and is bounded in size."""
        if not res.history:
            return ""
        handles = [h["handle"] for h in res.history if h.get("handle")]
        seen = list(dict.fromkeys(handles))[-24:]
        kinds: dict[str, int] = {}
        for h in res.history:
            kinds[h.get("kind", "?")] = kinds.get(h.get("kind", "?"), 0) + 1
        counts = ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
        return (f"\n\nTASK STATE (kept by the system; it is correct even if you remember otherwise): {res.steps} steps so far ({counts}); "
                f"{res.progress_steps} changed the screen"
                + (f"; handles already typed in this run: {', '.join(seen)}" if seen else "") + ".")

    async def _read_target(self, out: Action) -> TargetRead | None:
        reader = getattr(self.actuator, "read_target", None)
        if reader is None or out.kind not in _TARGETED:
            return None
        try:
            return await reader(out)
        except ActuatorRefused:
            raise
        except Exception:  # noqa: BLE001 - an unreadable target is unresolved, which the gate sends to a human
            return None

    def _event(self, n: int, action: str, ok: bool, detail: str = "") -> None:
        ev = StepEvent(navigator=self.navigator, step=n, tier=3, action=action, ok=ok, detail=detail)
        self.guard.record_step(ev)
        if self.emit:
            self.emit(ev)

    async def _ask_model(self, n: int, res: "Tier3Result", *args: Any, **kw: Any) -> Any:
        """One `computer_step` call, asked AGAIN (at most `model_retries` times, fixed waits) when the provider failed in a way that only
        says "try again" (`MODEL_RETRY_CLASSES`). A failed call means nothing was done on the screen: asking again cannot repeat an
        action, and what comes back still goes through every gate on its own. The frame is the one already held in memory, and every ask
        goes through the same egress guard and ledger as the first. Anything else, a stop, or the last failed ask is raised unchanged."""
        attempt = 0
        while True:
            try:
                return await asyncio.to_thread(self.model.computer_step, *args, **kw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - classified below; an unknown class is raised, never retried
                from ..security.drift import classify_provider_error

                cls, retryable = classify_provider_error(exc)
                if not (retryable and cls in MODEL_RETRY_CLASSES) or attempt >= self.model_retries or not self.is_current():
                    raise
                wait = float(self.model_backoff_s[min(attempt, len(self.model_backoff_s) - 1)])
                attempt += 1
                res.model_retries += 1
                res.model_retry_classes.append(cls)
                self.model_retry_classes.append(cls)
                self._event(n + 1, "model_retry", True, f"the model call failed ({cls}); asking again")
                await self._sleep(wait)
                if not self.is_current():
                    raise

    def _page_key(self) -> str:
        """A short id for the page the actuator is on (its URL path), so the audit can tell one page of a wizard from the next."""
        url = getattr(self.actuator, "url", None)
        if not url:
            return ""
        import hashlib as _h
        from urllib.parse import urlsplit

        return "p" + _h.sha1(urlsplit(url).path.encode()).hexdigest()[:8]

    def _audit_in_use(self) -> FormAudit | None:
        a = self.form_audit
        if a is not None and callable(getattr(self.actuator, "read_back", None)) and callable(getattr(self.actuator, "audit_form", None)):
            return a
        return None

    def _flush_audit(self, audit: FormAudit) -> None:
        """One audit line per new record: kind, handle id, reason (all tokens; never a value)."""
        for rec in audit.records[self._audit_logged:]:
            self.guard.note("form_audit", rec["match"], f"{rec['k']}:{rec['handle'] or 'form'}:{rec['reason']}", tier=3)
        self._audit_logged = len(audit.records)

    @staticmethod
    def _act_detail(act: Action, tr: "TargetRead | None") -> str:
        """What the step touched, as enums and the page's own control id as a short token: never typed text, never a label. This is
        what makes a misplaced click or key visible in the evidence afterwards."""
        bits: list[str] = []
        if act.kind == "key":
            bits.append(f"keys={key_names([str(k) for k in act.args.get('keys', [])])}")
        if tr is not None:
            bits.append(f"role={token(tr.role, 16) or '?'}")
            fa = tr.field_attrs or {}
            ident = token(fa.get("id") or fa.get("name"))
            if ident:
                bits.append(f"field={ident}")
        return " ".join(bits)

    async def run(self, goal: str, verify: Callable[[], Awaitable[bool]]) -> Tier3Result:
        from .facts import FactRefused, UnresolvedFact, key_would_type_text

        base_goal = goal + ("\n\n" + self.facts.goal_block() if self.facts is not None else "")
        self.guard.set_mode("model_driven")
        self.guard.set_goal(goal)
        bind = getattr(self.actuator, "bind_cancel", None)
        if callable(bind):            # Stop wins inside a long action too (a chunked type checks this between chunks)
            bind(lambda: not self.is_current())
        begin = getattr(self.model, "begin_task", None)
        if callable(begin):           # a provider that queues the rest of a multi-part action (click-and-type) starts this task clean
            begin(self.navigator, profile=self.profile) if self.profile else begin(self.navigator)
        attach = getattr(self.model, "attach", None)
        if callable(attach):          # test doubles that need the actuator's page; real providers have no such hook
            attach(self.navigator, self.actuator)
        res = Tier3Result("step_cap")
        audit = self._audit_in_use()
        wm = None
        synced = 0
        base_step = 0
        frames: Any = None
        if self.stateless:
            from ..context.adapters import computer_use_text
            from ..context.working import WorkingMemory

            hs = list(self.facts.handles) if self.facts is not None else []
            wm = seed_working_memory(re.sub(r"[^a-z0-9_.:-]", "", self.navigator.lower())[:48] or "nav", hs, self.resume_wm,
                                     page_kept=self.page_kept)
            base_step = wm.step                       # step numbers in the memory continue from a resumed or carried snapshot
            self.wm = wm
            from ..context.frames import FrameRetention

            # The frame hint ("the screen did / did not change since the last step") is OFF unless UNDERSTUDY_CU_FRAME_HINT=1. The
            # configuration that was validated live on the dev households had no such sentence, and the first live check with it on
            # (7 Nov, gpt-5.5, one calculator) got a screenshot-repeat stuck loop twice; a prompt that changed after validation is not
            # confirmed, so the default stays byte-identical to the validated one. The hint is tested offline and kept for an A/B.
            frames: Any = FrameRetention() if os.environ.get("UNDERSTUDY_CU_FRAME_HINT", "0").strip() in ("1", "true", "yes", "on") else None
        t0 = time.monotonic()
        n = self.step_start
        last_fp: bytes | None = None
        stalled = 0
        refused_streak = 0
        unsupported_streak = 0
        retargets = 0
        last_reset = 0
        feedback = ""
        entered_check: str | None = None      # a handle just typed and read back as landed: did the picture change? (see ENTERED_NOTE)
        final_check = False                   # a click or key just ran: is the final screen showing now? (see FINAL_NOTE)
        try:
            while res.steps < self.max_steps:
                if not self.is_current():
                    raise asyncio.CancelledError()
                if self.pause is not None:
                    await self.pause.wait_if_paused()          # step-level pause: the run keeps its place and its page
                if time.monotonic() - t0 > self.deadline_s:
                    res.outcome = "stopped"
                    raise StepBudgetExceeded("tier 3 time budget used up")
                shot = await self.actuator.screenshot()
                sz = png_size(shot)
                if sz is not None:
                    self.size = sz              # the model answers in THIS capture's pixels; validate in that space (S-10)
                fp = screen_fingerprint(shot)
                if fp is not None and last_fp is not None:
                    changed = screen_changed(fp, last_fp)
                    stalled = 0 if changed else stalled + 1
                    res.progress_steps += 1 if changed else 0
                    if stalled >= self.stall_limit:
                        res.outcome = "stalled"
                        raise StepBudgetExceeded(f"tier 3 made no visible progress in {stalled} steps")
                    if entered_check is not None and not changed:
                        feedback += ENTERED_NOTE.format(handle=entered_check)     # landed (read back), but the picture did not change
                entered_check = None
                if final_check:
                    final_check = False
                    try:
                        if self.final_hint is not None and await self.final_hint():
                            feedback += FINAL_NOTE      # the final screen is showing: say so, until the model replies DONE
                    except Exception:  # noqa: BLE001 - a page mid-navigation has no verdict; no note
                        pass
                last_fp = fp if fp is not None else last_fp
                pobs = self.guard.observe_screen()  # one fresh observation authorises exactly one action
                # Working memory is bounded: the provider's thread (every earlier frame) is restarted every N steps from
                # the compact TASK STATE below, which code builds from typed step records (never from model text).
                if (not self.stateless and self.context_reset_every and res.steps and res.steps % self.context_reset_every == 0
                        and res.steps != last_reset):
                    reset = getattr(self.model, "reset_session", None)
                    if callable(reset):
                        reset(session=self.navigator)
                        res.resets += 1
                    last_reset = res.steps
                if wm is not None:
                    synced = self._sync_memory(wm, res, synced, base_step)
                    self._snapshot(res.steps, wm)
                    url = getattr(self.actuator, "url", None)
                    if url:                                       # a new page starts blank: handles typed on the last one no longer count
                        import hashlib as _h
                        from urllib.parse import urlsplit

                        wm.set_page(PageState.UNKNOWN, "p" + _h.sha1(urlsplit(url).path.encode()).hexdigest()[:8])
                    try:
                        plan = frames.push(shot, passthrough=True) if frames is not None else None   # the code-written hint, when switched on
                    except Exception:  # noqa: BLE001 - an undecodable capture simply has no hint
                        plan = None
                    profile = "openai_cu" if getattr(self.model, "name", "") == "openai" else "default"
                    # the frame's own tokens are added to the budget, so the text sections keep the room they had before the hint existed
                    from ..context.tokens import estimate_image_tokens

                    extra = estimate_image_tokens(plan.frames[0].width, plan.frames[0].height, profile) if plan is not None else 0
                    asm = computer_use_text(base_goal, wm, plan, feedback=feedback, budget_tokens=TIER3_BUDGET_TOKENS + extra, image_profile=profile)
                    prompt = asm.text()
                    manifest = asm.manifest.to_meter_dict()
                    self.last_manifest = manifest
                    res.prompt_chars.append(len(prompt))
                    # a scripted double (the mock provider) indexes its script by history length; a real provider gets none
                    hist = list(res.history) if getattr(self.model, "name", "") == "mock" else []
                    with call_context(manifest):          # the meter records the sections and token counts of THIS call, never the text
                        out = await self._ask_model(n, res, prompt, shot, hist, session=self.navigator, store=False)
                else:
                    prompt = base_goal + self._task_state(res) + feedback
                    res.prompt_chars.append(len(prompt) + sum(len(str(h)) for h in res.history[-12:]))
                    out = await self._ask_model(n, res, prompt, shot, list(res.history), session=self.navigator)
                feedback = ""
                res.steps += 1
                self.last_steps = res.steps
                n += 1
                if isinstance(out, SafetyStop):
                    item = self.guard.enqueue(
                        kind="injection_pause", title=f"Model provider raised a safety check ({self.navigator})",
                        summary="A pending safety check from the model provider was not acknowledged. A human decides.",
                        risk_class="normal",
                        evidence={"screenshots": [], "extracted": {"checks": [c.get("code") for c in out.checks]},
                                  "expected": {}, "diff": [], "tier_log": []})
                    self._event(n, "safety_stop", False, "provider safety check")
                    raise ProviderSafetyStop(out.checks, item["id"])
                if isinstance(out, Unsupported):
                    # The provider could not map what the model asked for. That is not the model giving up: say what exists and ask again.
                    unsupported_streak += 1
                    res.unsupported += 1
                    res.history.append({"kind": "unsupported", "ok": False})
                    name = token(out.name, 30) or "unknown"
                    self.guard.note("action_unsupported", "refused", name, tier=3)
                    self._event(n, "unsupported", False, f"the model asked for {name}, which is not available here")
                    if unsupported_streak >= UNSUPPORTED_CAP:
                        res.outcome, res.why = "gave_up", "unsupported"
                        if wm is not None:
                            synced = self._sync_memory(wm, res, synced, base_step)
                        return res
                    feedback = UNSUPPORTED_NOTE.format(name=name)
                    continue
                if isinstance(out, Done):
                    stray = not out.claimed_success and not str(out.summary or "").strip().upper().startswith("FAILED")
                    claim_nudge = out.claimed_success and self.profile != "web"    # a free browsing task has no final screen to check a claim against
                    if (claim_nudge or stray) and res.nudges < self.max_nudges and not await verify():
                        # The model ended its turn but code says the goal's final screen is not showing. Code decides, so the
                        # claim is not believed; the model is told, once or twice, to carry on. The premature claim is
                        # counted and reported; it is never hidden by the retry.
                        res.nudges += 1
                        res.premature_claims += 1 if out.claimed_success else 0
                        self._event(n, "done", False, "ended early; the system said the task is not finished and told the model to continue")
                        feedback = WEB_NUDGE if self.profile == "web" else (
                            "\nNOTE: you ended your turn, but the system checked and the goal is NOT finished: its final screen is "
                            "not showing yet. Look at the screenshot and take the next action. Reply DONE only when the final "
                            "screen the goal describes is on screen.")
                        last_fp = None
                        continue
                    res.claimed_done = out.claimed_success
                    res.done_summary_len = len(out.summary or "")
                    res.last_summary = out.summary or ""
                    ok = await verify()
                    inputs_refused = False
                    if ok and audit is not None and not audit.inputs_ok:
                        # The final page is showing, but the last pre-submit audit was not clean (or there was none): nothing confirms the
                        # form held the household's facts when the calculation was asked for. A claim is not believed on that.
                        ok, inputs_refused = False, True
                    if audit is not None:
                        res.inputs, res.audit = audit.state, audit.summary()
                    if ok:                                       # code looked at the final page and it is the page the goal describes
                        res.history.append({"kind": "verify", "ok": True, "verified": self.postcondition})
                    if wm is not None:
                        synced = self._sync_memory(wm, res, synced, base_step)
                        self._snapshot(res.steps, wm)
                    res.false_claim = bool(out.claimed_success and not ok)
                    res.outcome = "done" if ok else ("claimed_not_verified" if out.claimed_success else "gave_up")
                    if res.outcome == "gave_up":
                        res.why = failed_reason_code(out.summary)
                    self._event(n, "done", ok, "claim verified" if ok else (
                        ("claim NOT verified by code (the form audit did not confirm the inputs)" if inputs_refused
                         else "claim NOT verified by code") if out.claimed_success else "the model said it could not finish"))
                    return res
                handle: str | None = None
                if self.facts is not None:
                    try:
                        if out.kind == "type":
                            handle = self.facts.check(out.args.get("text"))
                        elif out.kind == "key" and key_would_type_text(list(out.args.get("keys", []))):
                            raise FactRefused("key_types_text", "a letter or digit key would type a literal value")
                    except FactRefused as exc:
                        res.refusals += 1
                        refused_streak += 1
                        res.history.append({"kind": out.kind, "ok": False, "why": exc.code})
                        self.guard.note("fact_refused", "refused", exc.code, tier=3)
                        self._event(n, "type_fact" if out.kind == "type" else out.kind, False, f"refused: {exc.code}")
                        feedback = ("\nNOTE: your last action was refused. Type only a handle from the FACTS list, "
                                    "exactly, as the whole text of one type action. Do not type values or press letter keys.")
                        if refused_streak >= 4:
                            raise StuckLoop(f"the model keeps trying to type literal values ({exc.code})") from None
                        continue
                refused_streak = 0
                unsupported_streak = 0
                if self.pause is not None and await self.pause.wait_if_paused():
                    res.steps -= 1                              # the human arrived while the model was thinking:
                    n -= 1                                      # that action is stale, look at the screen again
                    continue
                if not self.is_current():                       # Stop or a human taking over while the model thought (S-03)
                    raise asyncio.CancelledError()
                # What the gate sees is what TRUSTED code reads at the target. The model's own `label` is only a hint
                # that can add risk (it stays in the action's args); it never makes a step "resolved" (S-01).
                tr = await self._read_target(out)
                if audit is not None and audit.is_final(out.kind, out.args, tr.label if tr else None):
                    # The press of the FINAL button (or Enter that would press it): code reads every control back first. Anything that is
                    # not as the facts say holds the press and tells the navigator which handles (ids and a closed reason, never a
                    # value). Deterministic code, before any model call is spent on the step, and before the gate authorises it.
                    pre = await audit.before_final(self.actuator, step=n, page_key=self._page_key())
                    self._flush_audit(audit)
                    if pre.state != "clean":
                        res.audit_blocks += 1
                        res.history.append({"kind": out.kind, "ok": False, "why": "form_not_ready"})
                        self._event(n, out.kind, False, f"held: form check {pre.state}, {len(pre.bad)} not as it should be, "
                                                        f"{len(pre.unreadable)} could not be read")
                        if pre.state == "uncertain":
                            raise FormAuditStop("a field could not be read, so a person is asked", retryable=False)
                        if pre.exhausted:
                            raise FormAuditStop("the form was still not right after the allowed number of checks on this page", retryable=True)
                        feedback = audit.block_note(pre)
                        continue
                elif audit is not None and audit.is_forward(out.kind, out.args, tr.label if tr else None):
                    # A button that moves on from a page that is not the last: a handle whose control is on THIS page and is not entered
                    # holds the press, so a skipped field is fixed on the page where it exists (a wizard cannot go back).
                    fwd = await audit.before_forward(self.actuator, step=n, page_key=self._page_key())
                    self._flush_audit(audit)
                    if fwd.state != "clean":
                        res.audit_blocks += 1
                        res.history.append({"kind": out.kind, "ok": False, "why": "page_not_ready"})
                        self._event(n, out.kind, False, f"held: page check, {len(fwd.bad)} not as it should be on this page")
                        if fwd.exhausted:
                            raise FormAuditStop("this page was still not right after the allowed number of checks", retryable=True)
                        feedback = audit.block_note(fwd, where="forward")
                        continue
                dec = self.guard.authorise(out, pobs, label=tr.label if tr else None, role=tr.role if tr else None,
                                           url=(tr.url if tr else None) or getattr(self.actuator, "url", None),
                                           field_attrs=tr.field_attrs if tr else None, screen=self.size,
                                           app=getattr(self.actuator, "target_app", None),
                                           structure=tr.structure if tr else ())
                if dec.verdict == "block" and dec.layer == "actions":
                    res.history.append({"kind": getattr(out, "kind", "?"), "ok": False})
                    self._event(n, getattr(out, "kind", "?"), False, f"rejected: {dec.codes[:1]}")
                    if self.profile == "web":
                        feedback = WEB_REJECTED_NOTE     # without it the model sees the same page and proposes the same thing again
                    continue
                if dec.verdict != "allow":
                    self._event(n, out.kind, False, f"{dec.verdict} {dec.layer or ''}".strip())
                self.guard.require(dec, (tr.label if tr else None) or out.kind, navigator=self.navigator)
                if self.stuck.push((out.kind, tuple(sorted((k, str(v)) for k, v in out.args.items())), fp)):
                    self._event(n, out.kind, False, "stuck loop")
                    raise StuckLoop("tier 3 stuck loop")
                act = Action(dec.action.kind, dict(dec.action.args)) if dec.action else out  # the validated form
                # Stop wins, and the page may have moved under the pointer since the read: look once more, right before
                # the event. A different target, or one that became unreadable, voids this action (nothing was done).
                if not self.is_current():
                    raise asyncio.CancelledError()
                if out.kind in _TARGETED:
                    tr2 = await self._read_target(out)
                    expect = getattr(self.actuator, "expect_target", None)
                    if callable(expect):        # a real actuator re-reads this once more, right before the press
                        expect(tr2)
                    if (tr is None) != (tr2 is None) or (tr is not None and tr.key != tr2.key):
                        res.steps -= 1
                        n -= 1
                        retargets += 1
                        if retargets > 5:
                            raise StepBudgetExceeded("the target under the pointer keeps changing before the action runs")
                        self.guard.note("target_changed", "refused", out.kind, tier=3)
                        self._event(n + 1, out.kind, False, "the target changed before the action; looking again")
                        feedback = "\nNOTE: the screen changed before your last action ran, so it was not performed."
                        continue
                if handle is not None:
                    try:
                        value = self.facts.resolve(handle)      # the ONLY place a value exists, and it goes straight out
                    except UnresolvedFact as exc:  # pragma: no cover - the vocabulary check already passed
                        raise TierError(str(exc)) from None
                    self.guard.check_typed_value(value, url=(tr.url if tr else None) or getattr(self.actuator, "url", None),
                                                 signature=dec.action.signature if dec.action else "type")
                    if re.search(r"[\x00-\x1f\x7f]", value):      # typed values are single-line: a newline would press Enter
                        raise TierError("a fact value contains a control character or newline; it will not be typed")
                    self.guard.record(dec, True)
                    if value == "":
                        res.history.append({"kind": "type", "handle": handle, "ok": True, "empty": True})
                        self._event(n, "type_fact", True, f"handle={handle} (no value for this household)")
                        continue
                    await self.actuator.execute(Action("type", {"text": value}))
                    rb = None
                    if audit is not None:
                        # Read the focused control back: did the text land? The page script compares; only enums come back.
                        rb = await audit.after_type(self.actuator, handle, value, step=n, page_key=self._page_key())
                        self._flush_audit(audit)
                    del value
                    if rb is not None and rb.landed == "no":
                        res.readback_failures += 1
                        res.history.append({"kind": "type", "handle": handle, "ok": False, "why": "not_landed"})
                        self._event(n, "type_fact", False, f"handle={handle} landed=no reason={rb.reason} focus={rb.focus} field={rb.field}")
                        if audit.readback_exhausted(handle):
                            raise FormAuditStop(f"{handle} would not land after {audit.max_readback_fails} tries", retryable=True)
                        feedback = audit.readback_note(handle, rb)
                        continue
                    res.history.append({"kind": "type", "handle": handle, "ok": True})
                    self._event(n, "type_fact", True, f"handle={handle}" + (
                        f" focus={rb.focus} field={rb.field} landed={rb.landed}" if rb is not None else ""))
                    if self.entered_note and rb is not None and rb.landed == "yes":
                        entered_check = handle
                    continue
                retargets = 0
                await self.actuator.execute(act)
                self.guard.record(dec, True)
                res.history.append({"kind": act.kind, "args": {k: v for k, v in act.args.items() if k != "text"}, "ok": True})
                self._event(n, act.kind, True, self._act_detail(act, tr))
                if self.dropdown_note and act.kind in ("click", "double_click") and tr is not None and tr.role == "combobox":
                    feedback = DROPDOWN_NOTE        # trusted code read a drop-down under the click: say what comes next
                elif self.final_note and self.final_hint is not None and act.kind in ("click", "double_click", "key"):
                    final_check = True              # look at the NEXT frame (the screenshot waits for the page to load), then say so if it is final
            raise StepBudgetExceeded(f"tier 3 step cap {self.max_steps} reached")
        finally:
            await self.actuator.release_all()
