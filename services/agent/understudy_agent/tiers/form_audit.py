"""Typed-input read-back and pre-submit audit for tier 3 (AGENTIC-3, ITERATIONS_8; cause 1 of docs/reference-notes/cu-failure-diagnosis.md).

THE GAP THIS CLOSES. In the held-out round two households reached a result page with calculator B's drop-down for bedrooms still on
its default, and one calculator lost a value typed before any field had focus. Nothing in the loop checked that a typed handle LANDED
in a control, or that EVERY handle was entered before the final button; the completion test was "the result page is showing". Code
owns the facts (it resolves each handle to a value at the moment of typing), so code can check what the page holds.

WHAT IT DOES (all in code; no model is asked anything).
  1. READ-BACK after each typed handle. A trusted read of the FOCUSED control, in the isolated world, says whether it now holds the
     value that was typed: landed yes / no / unreadable, with the focus kind (input, select, textarea, document, other), the control's
     role and the page's own id for it. The comparison happens INSIDE the page script: the expected value goes in as an argument and
     only enums, a short id token and a position come back. A control's value is never returned, printed, logged or stored.
  2. BINDING. A handle that landed is bound to the control that took it (position, tag, id, name), kept in memory only.
  3. PRE-SUBMIT AUDIT on the FINAL button (and on Enter that would press it). Before that click is allowed through, the page script
     re-reads every control the handles were bound to (hidden carried fields and fields of a hidden panel included) and compares each
     with the fact it should hold. A handle that was never entered is `not_entered`. Anything that is not clean BLOCKS the click and the
     navigator gets a code-written note naming the handle ids and a closed reason, never a value and never page text. At most
     `max_blocks_per_page` blocks per page; then the run stops (the ladder restarts once on a fresh page, then asks a human). A control that
     cannot be read (sensitive field, vanished control, ambiguous name, opaque frame) makes the audit `uncertain`: the click is held and a
     human is asked, never guessed.
  4. DONE. The tier-3 loop only accepts a claim of success when the latest pre-submit audit was clean (`inputs_ok`), and
     `completion.check_completion` refuses a calculator whose inputs were not.

WHAT IT DOES NOT DO. It cannot tell two values swapped between two fields of the same kind unless the job supplies `field_hints` (the
page's own ids a handle belongs in; the sandbox sites have them); without hints a swap that leaves each field holding SOME fact's value
is only caught when the values differ in kind. It checks the controls of the page in front of it: a handle bound on an earlier page of
a wizard whose values are not carried forward is not re-read (`earlier_page`); it was verified when it was typed.

Per-step enum records (never values): see `AuditRecord`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable, Mapping

from ..security import sensitive
from .base import TierError

FOCUS_KINDS = ("input", "select", "textarea", "document", "other", "unreadable")
FIELD_ROLES = ("text", "number", "select", "textarea", "checkbox", "radio", "hidden", "other")
LANDED = ("yes", "no", "unreadable")
REASONS = ("ok", "no_focus", "not_a_field", "empty", "mismatch", "appended", "select_unmatched", "wrong_field", "sensitive",
           "disabled", "not_entered", "not_found", "ambiguous", "earlier_page", "stray_value", "unreadable")
STATES = ("n/a", "unaudited", "clean", "mismatch", "uncertain")

# What each reason says to the navigator. Closed table, written here: a page can never put a word in it.
REASON_TEXT = {
    "no_focus": "nothing had focus, so the text went nowhere",
    "not_a_field": "the item with focus is not a form field",
    "empty": "the field is still empty",
    "mismatch": "the field holds something else",
    "appended": "the field already had text, so the new text was added to it",
    "select_unmatched": "the drop-down still shows another option",
    "wrong_field": "that is not the field for this fact",
    "not_entered": "not entered yet",
    "disabled": "the field is disabled",
    "stray_value": "a field that should be empty holds text",
}
_TOKEN_RE = re.compile(r"[^a-z0-9_#-]+")
NAMED_KEYS = frozenset({"enter", "return", "tab", "escape", "esc", "backspace", "delete", "left", "right", "up", "down", "home", "end",
                        "pageup", "pagedown", "page_up", "page_down", "space", "shift", "control", "ctrl", "alt", "option", "meta",
                        "cmd", "command"})


class FormAuditStop(TierError):
    """The form audit stopped the run: `retryable` is True when a second attempt on a fresh page may do better (the model could not
    get the form right within the cap), False when the audit cannot decide (a control it cannot read): a human is asked at once."""

    def __init__(self, why: str, *, retryable: bool) -> None:
        super().__init__(f"form audit: {why}")
        self.why, self.retryable = why, retryable


def token(s: Any, limit: int = 32) -> str:
    """A short id token from a page-authored control id or name: lower case, `[a-z0-9_#-]` only, digit runs of three or more masked."""
    t = _TOKEN_RE.sub("_", str(s or "").lower())
    return re.sub(r"[0-9]{3,}", "#", t)[:limit]


def key_names(keys: Iterable[str]) -> str:
    """The names of the keys pressed, from a closed set of named keys; anything else is `other` (a letter is never recorded)."""
    return "+".join(k.lower() if k.lower() in NAMED_KEYS else "other" for k in keys)


# ----------------------------------------------------------------------------- the page scripts (run in the ISOLATED world)
# One shared prelude. `arg.sens` carries the sensitive-field policy (packages/schema/sensitive_fields.json) so that a sensitive control's
# value is never read, even though this script runs inside the page's own DOM.
_JS_COMMON = r"""
  const base = s => String(s == null ? '' : s).replace(/ /g, ' ').replace(/£/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  const plain = s => base(s).replace(/^(\d{1,3}(,\d{3})+)(\.\d+)?$/, m => m.replace(/,/g, ''));
  const num = s => { const t = plain(s); return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : null; };
  const lst = s => base(s).split(/\s*[,;]\s*/).join(',');
  const same = (a, b) => {
    if (base(a) === base(b)) return true;
    const x = num(a), y = num(b);
    if (x !== null && y !== null) return Math.abs(x - y) < 1e-9;
    return lst(a) === lst(b);
  };
  const tok = s => String(s || '').toLowerCase().replace(/[^a-z0-9_#-]+/g, '_').replace(/[0-9]{3,}/g, '#').slice(0, 32);
  const NONTEXT = ['button', 'submit', 'reset', 'image', 'checkbox', 'radio', 'file', 'range', 'color'];
  const sensitive = e => {
    const ty = (e.getAttribute('type') || '').toLowerCase();
    if (arg.sens.types.includes(ty)) return true;
    const ac = (e.getAttribute('autocomplete') || '').toLowerCase().split(/\s+/);
    if (ac.some(t => arg.sens.ac.includes(t))) return true;
    if (NONTEXT.includes(ty)) return false;
    const lb = (e.labels && e.labels.length) ? Array.from(e.labels).map(l => l.innerText || l.textContent || '').join(' ') : '';
    const raw = [e.getAttribute('name'), e.id, lb, e.getAttribute('placeholder'), e.getAttribute('autocomplete'), e.getAttribute('aria-label')]
      .filter(Boolean).join(' ');
    const t = raw.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_\-.:\/]+/g, ' ').toLowerCase();
    return arg.sens.patterns.some(p => { try { return new RegExp(p, 'i').test(t); } catch (x) { return false; } });
  };
  const roleOf = e => {
    const tag = e.tagName.toLowerCase();
    if (tag === 'select') return 'select';
    if (tag === 'textarea') return 'textarea';
    const ty = (e.getAttribute('type') || 'text').toLowerCase();
    if (ty === 'hidden') return 'hidden';
    if (ty === 'number') return 'number';
    if (ty === 'checkbox' || ty === 'radio') return ty;
    return ['text', 'search', 'tel', 'email', 'url', ''].includes(ty) ? 'text' : 'other';
  };
  const isHidden = e => (e.getAttribute('type') || '').toLowerCase() === 'hidden' || !(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  // Does this control hold `expected`? Only enums leave this function, never the value.
  const judge = (e, expected, hint) => {
    const role = roleOf(e);
    if (sensitive(e)) return {match: 'unreadable', reason: 'sensitive', role};
    if (e.disabled) return {match: 'no', reason: 'disabled', role};
    if (hint && hint.length) {
      const ids = [e.id, e.getAttribute('name')].filter(Boolean).map(x => x.toLowerCase());
      if (!ids.some(i => hint.includes(i))) return {match: 'no', reason: 'wrong_field', role};
    }
    if (role === 'select') {
      const o = e.selectedOptions && e.selectedOptions[0];
      if (!o) return {match: 'unreadable', reason: 'unreadable', role};
      return (same(o.text, expected) || same(o.value, expected)) ? {match: 'yes', reason: 'ok', role} : {match: 'no', reason: 'select_unmatched', role};
    }
    if (role === 'text' || role === 'number' || role === 'textarea' || role === 'hidden') {
      const v = e.value;
      if (same(v, expected)) return {match: 'yes', reason: 'ok', role};
      if (base(v) === '') return {match: 'no', reason: 'empty', role};
      const bv = base(v), be = base(expected);
      if (bv.length > be.length && bv.endsWith(be)) return {match: 'no', reason: 'appended', role};
      return {match: 'no', reason: 'mismatch', role};
    }
    return {match: 'unreadable', reason: 'unreadable', role};
  };
"""

READ_BACK_JS = "(arg) => {" + _JS_COMMON + r"""
  let el = document.activeElement;
  for (let i = 0; i < 5 && el && ['iframe', 'frame'].includes(el.tagName.toLowerCase()); i++) {
    let inner = null;
    try { inner = el.contentDocument && el.contentDocument.activeElement; } catch (x) { inner = null; }
    if (!inner) break;
    el = inner;
  }
  if (!el) return {ok: false};
  const none = (focus, reason) => ({ok: true, focus, role: 'other', field: '', id: '', name: '', tag: '', ref: -1, landed: 'no', reason});
  if (el === document.body || el === document.documentElement) return none('document', 'no_focus');
  const tag = el.tagName.toLowerCase();
  if (!['input', 'select', 'textarea'].includes(tag)) return none('other', 'not_a_field');
  const all = Array.from(document.querySelectorAll('input,select,textarea'));
  const j = judge(el, arg.expected, arg.hint);
  return {ok: true, focus: tag, role: j.role, field: tok(el.id || el.getAttribute('name')), id: (el.id || '').slice(0, 80),
          name: (el.getAttribute('name') || '').slice(0, 80), tag, ref: all.indexOf(el),
          landed: j.match === 'yes' ? 'yes' : (j.match === 'no' ? 'no' : 'unreadable'), reason: j.reason};
}"""

AUDIT_FORM_JS = "(arg) => {" + _JS_COMMON + r"""
  const all = Array.from(document.querySelectorAll('input,select,textarea'));
  const opaque = Array.from(document.querySelectorAll('iframe,frame')).filter(f => { try { return !f.contentDocument; } catch (x) { return true; } }).length;
  const claimed = new Set(), results = [];
  for (const it of arg.items) {
    let cands = [];
    const r = (it.ref >= 0 && it.ref < all.length) ? all[it.ref] : null;
    const ident = e => (e.id || '') === (it.id || '') && (e.getAttribute('name') || '') === (it.name || '') && e.tagName.toLowerCase() === it.tag;
    if (r && (it.id || it.name) && ident(r)) cands = [r];
    else if (it.name) cands = all.filter(e => e.getAttribute('name') === it.name);
    if (!cands.length && it.id) cands = all.filter(e => e.id === it.id);
    if (cands.length > 1) { const vis = cands.filter(e => !isHidden(e)); if (vis.length === 1) cands = vis; }
    if (!cands.length) { results.push({h: it.h, match: 'unreadable', reason: 'not_found', role: 'other', hidden: false}); continue; }
    if (cands.length > 1) { results.push({h: it.h, match: 'unreadable', reason: 'ambiguous', role: 'other', hidden: false}); continue; }
    const e = cands[0];
    claimed.add(e);
    const j = judge(e, it.v, it.hint);
    results.push({h: it.h, match: j.match, reason: j.reason, role: j.role, hidden: isHidden(e)});
  }
  let stray = 0;     // text left in a text-like control that no fact was entered in (a count, never what it holds)
  if (arg.stray) for (const e of all) {
    if (claimed.has(e) || !['text', 'number', 'textarea'].includes(roleOf(e)) || sensitive(e)) continue;
    if (base(e.value) !== '') stray++;
  }
  return {ok: true, controls: all.length, hidden: all.filter(isHidden).length, opaque_frames: opaque, results, stray};
}"""


def script_arg(**extra: Any) -> dict[str, Any]:
    """The argument both page scripts take: the sensitive-field policy plus the call's own fields. JSON-clean."""
    return {"sens": sensitive.script_policy(), **extra}


# ----------------------------------------------------------------------------- records
@dataclass(frozen=True)
class ReadBack:
    """What the read-back said about the control that had focus. Enums, a short id token and a position; never a value."""

    focus: str = "unreadable"
    role: str = "other"
    field: str = ""                 # the page's own id (or name) for the control, as a short token
    landed: str = "unreadable"
    reason: str = "unreadable"
    ref: int = -1                   # position among the page's form controls (to find the same control again)
    tag: str = ""
    id: str = dc_field(default="", repr=False)       # raw id and name: used only to find the control again, never recorded
    name: str = dc_field(default="", repr=False)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any] | None) -> "ReadBack":
        if not isinstance(raw, Mapping) or not raw.get("ok"):
            return cls()
        pick = lambda k, allowed, default: raw.get(k) if raw.get(k) in allowed else default  # noqa: E731
        ref = raw.get("ref")
        return cls(focus=pick("focus", FOCUS_KINDS, "other"), role=pick("role", FIELD_ROLES, "other"),
                   field=token(raw.get("field")), landed=pick("landed", LANDED, "unreadable"),
                   reason=pick("reason", REASONS, "unreadable"), ref=ref if isinstance(ref, int) and ref >= -1 else -1,
                   tag=pick("tag", ("input", "select", "textarea"), ""), id=str(raw.get("id") or "")[:80],
                   name=str(raw.get("name") or "")[:80])


@dataclass
class _Binding:
    ref: int
    tag: str
    id: str
    name: str
    page: str
    role: str
    field: str


@dataclass(frozen=True)
class PreSubmit:
    state: str                                   # clean | mismatch | uncertain
    bad: tuple[tuple[str, str], ...] = ()        # (handle, reason) the form does not hold as it should
    unreadable: tuple[tuple[str, str], ...] = () # (handle, reason) that could not be checked
    exhausted: bool = False                      # a mismatch after `max_blocks_per_page` blocks on this page
    stray: int = 0


# ----------------------------------------------------------------------------- the audit
class FormAudit:
    """One per tier-3 attempt. `facts` is the FactStore of the task (handles resolve to values here only to be compared, never kept).
    `final_labels`: the accessible names of the button(s) that submit the calculation; None switches the guard and the Done requirement
    off (the read-back and the records still run). `field_hints`: handle -> the page's own ids/names a handle belongs in."""

    def __init__(self, facts: Any, *, final_labels: Iterable[str] | None = None,
                 field_hints: Mapping[str, Iterable[str]] | None = None, strict_stray: bool = False,
                 max_blocks_per_page: int = 3, max_readback_fails: int = 3, max_records: int = 200) -> None:
        self.facts = facts
        self._finals = frozenset(_norm_label(x) for x in (final_labels or ()) if x)
        self.hints = {h: tuple(str(x).lower() for x in v) for h, v in (field_hints or {}).items() if v}
        self.strict_stray = strict_stray
        self.max_blocks_per_page, self.max_readback_fails, self.max_records = max_blocks_per_page, max_readback_fails, max_records
        self.bound: dict[str, _Binding] = {}
        self.records: list[dict[str, Any]] = []
        self.readbacks = {"yes": 0, "no": 0, "unreadable": 0}
        self.audits = 0
        self.blocks = 0
        self._blocks: dict[str, int] = {}
        self._rb_fails: dict[str, int] = {}
        self._state = "unaudited" if self._finals else "n/a"
        self.last: PreSubmit | None = None

    # ------------------------------------------------------------------ state
    @property
    def guarding(self) -> bool:
        return bool(self._finals)

    @property
    def state(self) -> str:
        return self._state

    @property
    def inputs_ok(self) -> bool:
        """May a claim of success be believed? Only when the latest pre-submit audit was clean (or there is no guard to hold it to)."""
        return not self.guarding or self._state == "clean"

    def required(self) -> list[str]:
        """The handles that have something to type for this household (an empty value means nothing is typed, so nothing is required)."""
        return [h for h in self.facts.handles if self.facts.has_value(h)]

    def pending(self) -> list[str]:
        return [h for h in self.required() if h not in self.bound]

    def _rec(self, step: int, kind: str, handle: str, role: str, match: str, reason: str, **extra: Any) -> None:
        if len(self.records) < self.max_records:
            self.records.append({"step": step, "k": kind, "handle": handle, "role": role, "match": match, "reason": reason, **extra})

    # ------------------------------------------------------------------ 1. read-back after a typed handle
    async def after_type(self, actuator: Any, handle: str, value: str, *, step: int, page_key: str) -> ReadBack:
        """Read the focused control back, comparing inside the page. `value` is passed to the page script as the thing to compare with
        and is not kept here."""
        try:
            raw = await actuator.read_back(expected=value, hint=list(self.hints.get(handle, ())) or None)
        except Exception:  # noqa: BLE001 - an unreadable page is unreadable, never "fine"
            raw = None
        rb = ReadBack.from_raw(raw)
        self.readbacks[rb.landed] += 1
        self._rec(step, "readback", handle, rb.role, rb.landed, rb.reason, focus=rb.focus, field=rb.field)
        if rb.landed == "no":
            self.bound.pop(handle, None)
            self._rb_fails[handle] = self._rb_fails.get(handle, 0) + 1
        else:
            self.bound[handle] = _Binding(rb.ref, rb.tag, rb.id, rb.name, page_key, rb.role, rb.field)
            self._rb_fails.pop(handle, None)
        return rb

    def readback_exhausted(self, handle: str) -> bool:
        return self._rb_fails.get(handle, 0) >= self.max_readback_fails

    def readback_note(self, handle: str, rb: ReadBack) -> str:
        why = REASON_TEXT.get(rb.reason, "it did not take")
        extra = " If a field already holds text, clear it first (select all, then Backspace)." if rb.reason in ("appended", "mismatch", "wrong_field") else ""
        return (f"\nNOTE (checked by the system, not page text): {handle} was NOT entered: {why} (focus: {rb.focus}). "
                f"Click the right field, then type {handle} again.{extra}")

    # ------------------------------------------------------------------ 2. the final button
    def is_final(self, kind: str, args: Mapping[str, Any], label: str | None) -> bool:
        """Is this action the press of a final button (a click on it, or Enter in a field whose default button it is)?"""
        if not self._finals or not label:
            return False
        if kind in ("click", "double_click"):
            pass
        elif kind == "key" and [str(k).lower() for k in args.get("keys", [])] in (["enter"], ["return"]):
            pass
        else:
            return False
        return any(_norm_label(part) in self._finals for part in str(label).split(" / "))

    async def before_final(self, actuator: Any, *, step: int, page_key: str) -> PreSubmit:
        self.audits += 1
        items: list[dict[str, Any]] = []
        bad: list[tuple[str, str]] = []
        unreadable: list[tuple[str, str]] = []
        roles: dict[str, str] = {}
        for h in self.required():
            b = self.bound.get(h)
            if b is None:
                bad.append((h, "not_entered"))
                self._rec(step, "preflight", h, "other", "no", "not_entered")
                continue
            roles[h] = b.role
            items.append({"h": h, "v": self.facts.peek(h), "ref": b.ref, "tag": b.tag, "id": b.id, "name": b.name,
                          "hint": list(self.hints.get(h, ())) or None})
        stray = 0
        if items:
            try:
                raw = await actuator.audit_form(items, stray=self.strict_stray)
            except Exception:  # noqa: BLE001
                raw = None
            finally:
                items.clear()                                   # the values go out of scope here
            got = {r.get("h"): r for r in (raw or {}).get("results", []) if isinstance(r, Mapping)} if isinstance(raw, Mapping) and raw.get("ok") else {}
            stray = int((raw or {}).get("stray", 0)) if isinstance(raw, Mapping) and raw.get("ok") else 0
            for h, role in roles.items():
                r = got.get(h)
                match = r.get("match") if r and r.get("match") in LANDED else "unreadable"
                reason = r.get("reason") if r and r.get("reason") in REASONS else "unreadable"
                rrole = r.get("role") if r and r.get("role") in FIELD_ROLES else role
                if match == "unreadable" and reason == "not_found" and self.bound[h].page != page_key:
                    reason, match = "earlier_page", "yes"      # typed and verified on an earlier page whose values this page does not carry
                self._rec(step, "preflight", h, rrole, match, reason, **({"hidden": True} if r and r.get("hidden") else {}))
                if match == "no":
                    bad.append((h, reason))
                elif match == "unreadable":
                    unreadable.append((h, reason))
        if self.strict_stray and stray:
            bad.append(("", "stray_value"))
            self._rec(step, "preflight", "", "text", "no", "stray_value", count=stray)
        exhausted = False
        if bad:
            state = "mismatch"
            self._blocks[page_key] = self._blocks.get(page_key, 0) + 1
            self.blocks += 1
            exhausted = self._blocks[page_key] > self.max_blocks_per_page
        elif unreadable:
            state = "uncertain"
        else:
            state = "clean"
        self._state = state
        self.last = PreSubmit(state, tuple(bad), tuple(unreadable), exhausted, stray)
        return self.last

    def block_note(self, v: PreSubmit) -> str:
        parts = [f"{h} ({REASON_TEXT.get(r, r)})" if h else REASON_TEXT.get(r, r) for h, r in v.bad[:8]]
        more = f" and {len(v.bad) - 8} more" if len(v.bad) > 8 else ""
        return ("\nNOTE (checked by the system, not page text): the form was checked before the final button and it is NOT ready, so the "
                f"button was not pressed. Not as it should be: {'; '.join(parts)}{more}. Fix each one (click its field, type its handle "
                "again; clear the field first if it already holds text), then press the final button again.")

    # ------------------------------------------------------------------ what is written down
    def summary(self) -> dict[str, Any]:
        """Enums and counts only: safe to put in a result file, an evidence file or an approval item."""
        return {"state": self._state, "audits": self.audits, "blocks": self.blocks, "readbacks": dict(self.readbacks),
                "pending": self.pending() if self.guarding else [], "records": list(self.records)}


def _norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()
