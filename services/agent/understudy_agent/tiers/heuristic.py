"""A deterministic, model-free planner and reader for MOCK MODE and tests (NFR-2).

`HeuristicModelPort` wraps agent-safety's `MockProvider`: every call is delegated to it except the two
agent-core schemas, `tier2_step` (one browser action) and `calculator_result` (quarantined reader
extraction), which are answered by label-matching rules. A scripted *vulnerable* planner still gets to
hijack first, so red-team ablations behave as designed.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..completion import REF_RE

_FORWARD = ("continue", "next", "calculate", "work it out", "estimate", "show my results", "see entitlement",
            "save draft", "save", "cliff", "go back", "try again")
_STATUS = re.compile(r"(You are (?:likely|unlikely) to be eligible|Likely to qualify|Unlikely to qualify|NOT ELIGIBLE|ELIGIBLE)")
_AMOUNT = re.compile(r"(£\s?[\d,]+(?:\.\d{1,2})?(?:\s*(?:per|a)\s*month)?|[\d,]+\.\d{2}\s*GBP\s*/\s*month)")


def param_for(label: str, role: str) -> tuple[str | None, str]:
    """Map a field label to (household parameter, unit). Pure rules over the label text."""
    l = label.lower()
    unit = "year" if ("year" in l or "annual" in l) else "week" if "week" in l else "month"
    partner = any(w in l for w in ("partner", "second adult", "second"))
    if "case reference" in l:
        return "case_ref", "none"
    if "govcalc" in l:
        return "result_a", "none"
    if "quick estimator" in l:
        return "result_b", "none"
    if "entitledto" in l:
        return "result_c", "none"
    if "reconciliation" in l:
        return "reconciliation", "none"
    if l.strip() == "note":
        return "note_text", "none"
    if ("child" in l or "kids" in l) and re.search(r"\bages?\b", l):
        return "children_ages", "none"
    if "childcare" in l:
        return "childcare_monthly", unit
    if "adults" in l and not re.search(r"\bage\b", l):
        return "adults", "none"
    if re.search(r"\bage\b", l):
        return ("adult2_age" if partner else "adult1_age"), "none"
    if any(w in l for w in ("pay", "earn", "income")):
        return ("adult2_earnings_monthly" if partner else "adult1_earnings_monthly"), unit
    if any(w in l for w in ("health", "limited capability", "limits")):
        return "limited_capability", "none"
    if role == "combobox" and any(w in l for w in ("rent or own", "housing", "tenure")):
        return "tenure", "none"
    if "rent" in l and role != "combobox":
        return "rent_monthly", unit
    if "bedroom" in l:
        return "bedrooms", "none"
    if "saving" in l:
        return "savings", "none"
    return None, "none"


def tier2_heuristic(messages: list[dict[str, Any]]) -> dict[str, Any]:
    content = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
    m = re.search(r"^STATE: (\{.*\})$", content, re.M)
    if not m:
        return {"tool": "wait", "reason": "no state"}
    state = json.loads(m.group(1))
    labels = {k: v.strip() for k, v in re.findall(r"^(e\d+): (.*)$", content, re.M)}
    kind = (re.search(r"^kind: (\w+)$", content, re.M) or [None, ""])[1]
    done = set(state.get("already_set_on_this_page", []))
    allowed = set(state.get("params", []))
    elements = state.get("elements", [])
    if kind == "error":   # a problem page: go back and try again, never finish
        back = [e for e in elements if any(w in labels.get(e["ref"], "").lower() for w in ("go back", "try again", "back"))]
        if back:
            return {"tool": "click", "ref": back[0]["ref"], "reason": "the page is an error page: go back"}
        return {"tool": "wait", "reason": "error page with nothing to press"}
    for e in elements:
        if e["role"] not in ("textbox", "spinbutton", "combobox"):
            continue
        param, unit = param_for(labels.get(e["ref"], ""), e["role"])
        if param and param in allowed and param not in done:
            tool = "select" if e["role"] == "combobox" else "fill"
            return {"tool": tool, "ref": e["ref"], "param": param, "unit": unit,
                    "reason": f"field '{labels.get(e['ref'], '')[:40]}' takes {param}"}
    buttons = [e for e in elements if e["role"] == "button" and not e.get("disabled")]
    fwd = [b for b in buttons if any(w in labels.get(b["ref"], "").lower() for w in _FORWARD)]
    if fwd:
        return {"tool": "click", "ref": fwd[-1]["ref"], "reason": "move on"}
    return {"tool": "finish", "reason": "nothing left to fill or press on this page"}


def read_page_state(text: str) -> dict[str, Any]:
    t = text.lower()
    if any(w in t for w in ("there is a problem", "temporarily unavailable", "having trouble", "(503)", "must be a number",
                            "please enter", "is out of range", "service unavailable", "session has expired")):
        return {"kind": "error", "error": True}
    if REF_RE.search(text) and _AMOUNT.search(text):
        return {"kind": "result", "error": False}
    if re.search(r"\bCN-\d{4}\b", text) and "draft" in t:
        return {"kind": "saved_note", "error": False}
    return {"kind": "form", "error": False}


def read_calculator_result(text: str) -> dict[str, str]:
    amount = _AMOUNT.search(text)
    status = _STATUS.search(text)
    ref = REF_RE.search(text)
    return {"amount_text": amount.group(1).strip() if amount else "",
            "status_text": status.group(1) if status else "", "ref": ref.group(0) if ref else ""}


class HeuristicModelPort:
    name = "heuristic-mock"

    def __init__(self, inner: Any | None = None) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def _need(self) -> Any:
        if self.inner is None:
            raise RuntimeError("HeuristicModelPort has no inner provider for this call")
        return self.inner

    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        title = (schema or {}).get("title")
        self.calls.append({"method": "plan", "title": title, "messages": messages})
        if title == "tier2_step":
            if self.inner is not None:
                out = self.inner.plan(messages, schema)
                if isinstance(out, dict) and out.get("hijacked"):
                    return out
            return tier2_heuristic(messages)
        return self._need().plan(messages, schema)

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        title = schema.get("title")
        self.calls.append({"method": "read", "title": title, "chars": len(untrusted)})
        if title == "calculator_result":
            return read_calculator_result(untrusted)
        if title == "page_state":
            return read_page_state(untrusted)
        return self._need().read(untrusted, schema)

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self._need().check(prompt, schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._need().vision(image, prompt, schema)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]], **kw: Any) -> Any:
        return self._need().computer_step(goal, screenshot, history, **kw)


# ----------------------------------------------------------------------------- a grounded computer-use test double
_ELEMS_JS = r"""
() => {
  const vis = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[hidden]'); };
  const label = (el) => { const aria = el.getAttribute('aria-label'); if (aria) return aria;
    if (el.labels && el.labels.length) return el.labels[0].innerText;
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return l.innerText; }
    if (['submit','button'].includes(el.type)) return el.value || el.innerText;
    return el.innerText || el.getAttribute('title') || ''; };
  const els = [];
  for (const el of document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea')) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    els.push({tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || ''), label: label(el).trim(),
              x: r.x + r.width / 2, y: r.y + r.height / 2, value: el.value || '',
              dialog: !!el.closest('[role=dialog],[aria-modal=true]')});
  }
  return {url: location.href, text: document.body.innerText || '', els, vh: window.innerHeight, vw: window.innerWidth};
}
"""

_HANDLE_OF = {
    "adults": "household.adults", "adult1_age": "household.adult1_age", "adult2_age": "household.adult2_age",
    "children_ages": "household.children_ages", "adult1_earnings_monthly": "household.adult1_earnings",
    "adult2_earnings_monthly": "household.adult2_earnings", "limited_capability": "household.limited_capability",
    "tenure": "household.tenure", "rent_monthly": "household.rent", "bedrooms": "household.bedrooms",
    "savings": "household.savings", "childcare_monthly": "household.childcare", "case_ref": "note.case_ref",
    "result_a": "note.result_a", "result_b": "note.result_b", "result_c": "note.result_c",
    "reconciliation": "note.reconciliation", "note_text": "note.text",
}


class DomOracleComputerModel:
    """TEST DOUBLE for a competent, grounded computer-use model. It reads the page's DOM to decide where to click
    (a real model gets that from pixels) and enters data only by typing fact handles. Deterministic, offline, never
    used in a live run. It exists to prove the loop, the fact handles, the actuator and the verification work end to
    end before any model is paid to try."""

    name = "dom-oracle"

    def __init__(self, *, literal_every: int = 0, inner: Any = None) -> None:
        from ..models.mock_provider import MockProvider

        self.inner = inner or HeuristicModelPort(MockProvider("benefits_clean"))   # plan, read, check for the pipeline
        self.sessions: dict[str, dict[str, Any]] = {}
        self.literal_every = literal_every      # >0: every Nth type action is a LITERAL (to prove refusals recover)
        self.calls = 0
        self.goals: list[str] = []

    def attach(self, session: str, actuator: Any) -> None:
        import asyncio

        st = self.sessions.setdefault(session, {})
        st.update(page=actuator.page, loop=asyncio.get_running_loop())
        st["done"], st["path"] = set(), None      # a new run (a fresh page) starts with nothing filled
        st["pending"] = None
        st["enter"] = False

    def _look(self, st: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        return asyncio.run_coroutine_threadsafe(st["page"].evaluate(_ELEMS_JS), st["loop"]).result(15)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]], *, session: str | None = None,
                      **kw: Any) -> Any:
        from urllib.parse import urlparse

        from ..models.port import Action, Done

        self.calls += 1
        self.goals.append(goal)
        st = self.sessions[session or ""]
        info = self._look(st)
        text, els = info["text"], info["els"]
        vh = int(info.get("vh", 800))

        def reach(e: dict[str, Any]) -> Any:
            """A real model scrolls when the thing it wants is below the fold."""
            if 5 <= e["y"] <= vh - 5:
                return None
            return Action("scroll", {"x": int(info.get("vw", 1280)) // 2, "y": vh // 2, "scroll_x": 0,
                                     "scroll_y": max(-2000, min(2000, int(e["y"] - vh / 2)))})

        path = urlparse(info["url"]).path
        if path != st["path"]:
            st["done"], st["pending"], st["enter"], st["path"] = set(), None, False, path
        refused = "was refused" in goal or bool(history and history[-1].get("kind") == "type" and history[-1].get("ok") is False)
        if refused and st.get("last"):             # stateless requests carry the refusal as a note in the prompt, not in a history
            handle, is_select = st["last"]              # the type was refused: a competent model retries with the handle
            st["enter"] = is_select
            return Action("type", {"text": "{" + handle + "}"})
        if st["pending"]:
            handle, is_select = st["pending"]
            st["pending"] = None
            st["last"] = (handle, is_select)
            st["enter"] = is_select
            if self.literal_every and self.calls % self.literal_every == 0:
                st["enter"] = False
                return Action("type", {"text": "12345"})        # a literal value: must be refused
            return Action("type", {"text": "{" + handle + "}"})
        if st["enter"]:
            st["enter"] = False
            return Action("key", {"keys": ["Tab"]})   # Enter would submit the form; Tab commits the choice
        cliff_goal = "Check cliff edges" in goal
        marker = "Cliff edges for this household"
        note_goal = "case note" in goal.lower() and "Save draft" in goal or "Save draft" in goal
        if cliff_goal:
            if marker in text:
                return Done("the cliff panel is showing", True)
            for e in els:
                if "cliff" in e["label"].lower() and e["tag"] == "button":
                    return Action("click", {"x": int(e["x"]), "y": int(e["y"])})
            return Done("there is no cliff button on this page", False)
        if REF_RE.search(text) and _AMOUNT.search(text) and not note_goal:
            return Done("the estimate page is showing", True)
        if re.search(r"\bCN-\d{4}\b", text) and "Draft" in text:
            return Done("the case note is saved as a draft", True)
        low = text.lower()
        dialog = [e for e in els if e.get("dialog") and e["tag"] == "button"]
        if dialog:                                   # a consent dialog: reject, never accept
            rej = [e for e in dialog if re.match(r"(reject|decline|no,? thanks|not now|dismiss|close)", e["label"].lower())]
            if rej:
                return Action("click", {"x": int(rej[0]["x"]), "y": int(rej[0]["y"])})
        if any(w in low for w in ("there is a problem", "temporarily unavailable", "having trouble", "(503)", "must be a number",
                                  "please enter", "out of range", "session has expired")):
            back = [e for e in els if any(w in e["label"].lower() for w in ("back", "try again", "start again"))]
            if back:
                return Action("click", {"x": int(back[0]["x"]), "y": int(back[0]["y"])})
            return Done("the page shows a problem and I cannot go back", False)
        for e in els:
            if e["tag"] in ("input", "select", "textarea") and e["type"] not in ("submit", "button"):
                role = "combobox" if e["tag"] == "select" else "textbox"
                canon, _unit = param_for(e["label"], role)
                handle = _HANDLE_OF.get(canon or "")
                if handle and handle not in st["done"]:
                    away = reach(e)
                    if away is not None:
                        return away
                    st["done"].add(handle)
                    st["pending"] = (handle, e["tag"] == "select")
                    return Action("click", {"x": int(e["x"]), "y": int(e["y"])})
        fwd = [e for e in els if e["tag"] == "button" and any(w in e["label"].lower() for w in _FORWARD if w != "cliff")]
        if fwd:
            b = fwd[-1]
            away = reach(b)
            if away is not None:
                return away
            return Action("click", {"x": int(b["x"]), "y": int(b["y"])})
        return Done("I cannot find anything more to do on this page", False)

    # the rest of the ModelPort comes from the scripted mock (reader, drift check, planner)
    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.inner.plan(messages, schema)

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self.inner.read(untrusted, schema)

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        return self.inner.check(prompt, schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.inner.vision(image, prompt, schema)
