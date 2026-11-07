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
                            "please enter", "is out of range", "service unavailable")):
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
