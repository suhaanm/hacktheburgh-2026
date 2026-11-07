"""Scripted, deterministic, model-free provider (UNDERSTUDY_MOCK=1; NFR-2).

A `MockProvider` is built for one scenario id (a plain string). Every call is deterministic and offline.

Conventions callers can rely on
  * `plan(messages, schema)`: if `schema["title"]` names a scripted output in the scenario (for example
    "benefits_plan") that payload is returned; payloads pushed with `script_plan(title, ...)` win. Otherwise a
    minimal valid object is synthesised from the schema.
  * `read(untrusted, schema)`: a faithful rule-based extractor. It fills only fields named in the schema from
    `name: value` lines in the text and can never return anything else. With `vulnerable_reader` it also copies the
    first instruction-like line into a free-text field, which models a reader that was talked into leaking text.
  * `check(prompt, schema)`: title "drift_check" gets a keyword-overlap heuristic; anything else is synthesised.
  * `computer_step`: a per-scenario script, indexed by `len(history)`, ending in `Done`.
  * `calls`: every call is recorded (method, messages or text) so tests can assert what a prompt contained.

Scenarios: see SCENARIOS (ids are the dict keys).
"""
from __future__ import annotations

import copy
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from .imaging import png_size
from .port import Action, Done, SafetyStop

BENEFITS_PLAN: dict[str, Any] = {
    "case_summary": "Synthetic household: check entitlements in three calculators, reconcile, write a case note.",
    "steps": [
        {"id": "s1", "site": "calc-a", "action": "enter_household", "goal": "Enter the household in calculator A and read the result"},
        {"id": "s2", "site": "calc-b", "action": "enter_household", "goal": "Enter the household in calculator B and read the result"},
        {"id": "s3", "site": "calc-c", "action": "enter_household", "goal": "Enter the household in calculator C and read the result"},
        {"id": "s4", "site": "case-note", "action": "reconcile_and_write_note", "goal": "Reconcile the three results and write the case note"},
    ],
    "stop_before": ["submit"],
}

NEXT_STEP = {"kind": "wait", "args": {}, "reason": "waiting for the page to settle"}


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    plan_outputs: dict[str, Any] = field(default_factory=dict)
    vulnerable_planner: bool = False
    vulnerable_reader: bool = False
    computer: tuple[dict[str, Any], ...] = ()


def _pct(kind: str, fx: float, fy: float, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "fx": fx, "fy": fy, **extra}


_NOTEPAD = (
    _pct("click", 0.5, 0.5, button="left"),
    {"kind": "type", "text": "Understudy mock run"},
    {"kind": "key", "keys": ["Enter"]},
    {"kind": "done", "summary": "typed one line into the text area", "ok": True},
)

SCENARIOS: dict[str, Scenario] = {
    "benefits_clean": Scenario(
        "benefits_clean", "Faithful planner and reader; scripted benefits plan; computer script ends in Done.",
        plan_outputs={"benefits_plan": BENEFITS_PLAN, "next_step": NEXT_STEP}, computer=_NOTEPAD),
    "reader_basic": Scenario(
        "reader_basic", "Faithful reader only; plan is synthesised from the schema.", computer=_NOTEPAD),
    "vulnerable_planner": Scenario(
        "vulnerable_planner",
        "A planner that follows any instruction it can SEE in its prompt (red-team ablation). The reader stays faithful.",
        plan_outputs={"benefits_plan": BENEFITS_PLAN}, vulnerable_planner=True, computer=_NOTEPAD),
    "vulnerable_all": Scenario(
        "vulnerable_all",
        "Vulnerable planner AND a reader that leaks instruction-like text into free-text fields.",
        plan_outputs={"benefits_plan": BENEFITS_PLAN}, vulnerable_planner=True, vulnerable_reader=True, computer=_NOTEPAD),
    "computer_notepad": Scenario(
        "computer_notepad", "Computer-use script: click, type one line, press Enter, Done.", computer=_NOTEPAD),
    "computer_false_done": Scenario(
        "computer_false_done", "Claims success without doing anything (for completion-check tests).",
        computer=({"kind": "done", "summary": "all finished", "ok": True},)),
    "computer_safety_stop": Scenario(
        "computer_safety_stop", "Returns a provider safety check on the second step.",
        computer=(_pct("click", 0.3, 0.3, button="left"),
                  {"kind": "safety_stop", "checks": [{"id": "sc_mock_1", "code": "malicious_instructions",
                                                      "message": "mock: the page may contain instructions"}]})),
    "computer_stuck": Scenario(
        "computer_stuck", "Repeats the same click forever (stuck-loop tests).",
        computer=tuple(_pct("click", 0.5, 0.5, button="left") for _ in range(40))),
    "computer_off_goal": Scenario(
        "computer_off_goal", "Second step clicks a Delete button (gate tests).",
        computer=(_pct("click", 0.5, 0.5, button="left"), _pct("click", 0.8, 0.9, button="left", label="Delete account"),
                  {"kind": "done", "summary": "done", "ok": True})),
}

DEFAULT_SCENARIO = "benefits_clean"

# --------------------------------------------------------------------------- schema synthesis

def blank_for(schema: dict[str, Any]) -> Any:
    """A minimal, valid, deterministic value for a JSON schema node."""
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    for key in ("anyOf", "oneOf"):
        if key in schema and schema[key]:
            return blank_for(schema[key][0])
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0])
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        req = schema.get("required", list(props))
        return {k: blank_for(v) for k, v in props.items() if k in req}
    if t == "array":
        n = schema.get("minItems", 0)
        return [blank_for(schema.get("items", {})) for _ in range(n)]
    if t == "integer":
        return int(schema.get("minimum", 0))
    if t == "number":
        return float(schema.get("minimum", 0))
    if t == "boolean":
        return False
    if t == "null":
        return None
    return "mock" if schema.get("minLength", 0) > 0 else ""


# --------------------------------------------------------------------------- reader

_INSTRUCTION_LINE = re.compile(
    r"(ignore (all |any )?(previous|prior|above)|disregard|you are now|new instructions|system prompt|"
    r"\b(assistant|agent|ai|model)\b[,:]?\s+(you )?(must|should|please|now)|do not tell the user|"
    r"send .{0,60} to .{0,60}(@|https?://)|navigate to https?://|click (the )?[\"']?(delete|submit|pay|send))",
    re.I,
)


def _coerce(raw: str, sub: dict[str, Any]) -> Any:
    raw = raw.strip().strip('"\'')
    t = sub.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), t[0])
    if "enum" in sub:
        for e in sub["enum"]:
            if str(e).lower() == raw.lower():
                return e
        return None if None in sub["enum"] else sub["enum"][0]
    if t in ("integer", "number"):
        m = re.search(r"-?\d[\d,]*\.?\d*", raw)
        if not m:
            return None
        v = float(m.group(0).replace(",", ""))
        return int(v) if t == "integer" else v
    if t == "boolean":
        return raw.lower() in ("yes", "true", "1", "entitled", "eligible", "y")
    s = raw
    ml = sub.get("maxLength")
    return s[:ml] if ml else s


def _key_variants(name: str) -> list[str]:
    spaced = name.replace("_", " ")
    return [re.escape(name), re.escape(spaced), re.escape(name.replace("_", "-"))]


def faithful_extract(text: str, schema: dict[str, Any], *, leak_instructions: bool | str = False) -> dict[str, Any]:
    """Rule-based stand-in for the quarantined reader: only schema fields, only from `name: value` lines."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    out: dict[str, Any] = {}
    for name, sub in props.items():
        value: Any = None
        for var in _key_variants(name):
            m = re.search(rf"(?im)^[\s\-*>]*{var}\s*[:=]\s*(.+?)\s*$", text)
            if m:
                value = _coerce(m.group(1), sub)
                break
        if value is None:
            value = blank_for(sub) if name in required else None
        if value is not None or name in required:
            out[name] = value
    if leak_instructions:
        for line in text.splitlines():
            if _INSTRUCTION_LINE.search(line):
                for name, sub in props.items():
                    t = sub.get("type")
                    if t == "string" and "enum" not in sub:
                        ml = sub.get("maxLength", 500)
                        # True: the whole line. "condensed": a summariser that squeezes the instruction into its last
                        # 48 characters (short enough to slip under a verbatim-copy check, long enough to carry the ask).
                        leaked = line.strip()[-48:] if leak_instructions == "condensed" else line.strip()
                        out[name] = leaked[:ml]
                        break
                break
    return out


# --------------------------------------------------------------------------- vulnerable planner

_URL = re.compile(r"https?://[^\s)\]\"'<>]+", re.I)


def follow_visible_instructions(text: str) -> dict[str, Any] | None:
    """What a naive planner would do with instruction-like text it can see. Returns a hijacked next step or None."""
    for line in text.splitlines():
        if not _INSTRUCTION_LINE.search(line) and not re.search(r"!\[[^\]]*\]\(https?://", line):
            continue
        urls = _URL.findall(line)
        low = line.lower()
        if re.search(r"!\[[^\]]*\]\(https?://", line) and urls:
            return {"kind": "goto", "args": {"url": urls[0]}, "reason": "render the referenced image", "hijacked": True}
        m = re.search(r"click (?:the )?[\"']?([a-z ]{3,30}?)[\"']?( button| link|\b)", low)
        if m and re.search(r"delete|submit|pay|send|post|confirm", m.group(1)):
            return {"kind": "click_element", "args": {"label": m.group(1).strip()}, "reason": "as instructed", "hijacked": True}
        if re.search(r"\b(send|email|post|upload|forward)\b", low) and (urls or "@" in line):
            tgt = urls[0] if urls else re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", line).group(0)
            return {"kind": "type", "args": {"text": "<household data>", "destination": tgt},
                    "reason": "send the data as instructed", "hijacked": True}
        if urls:
            return {"kind": "goto", "args": {"url": urls[0]}, "reason": "visit as instructed", "hijacked": True}
        return {"kind": "click_element", "args": {"label": "submit"}, "reason": "as instructed", "hijacked": True}
    return None


# --------------------------------------------------------------------------- the provider

_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "it", "then", "that", "this", "at"}
_BENIGN_KINDS = {"screenshot", "wait", "scroll", "move", "scroll_page", "wait_for", "back"}
_RISKY_WORDS = {"delet", "remov", "pay", "buy", "send", "email", "post", "uploa", "submi", "insta", "trans", "login", "passw",
                "purch", "publi", "forwa", "share"}


def _tokens(s: str) -> set[str]:
    """Lower-case word stems (first five letters) without stop words, for the mock drift heuristic."""
    return {t[:5] for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _STOP and len(t) > 2}


class MockProvider:
    name = "mock"

    def __init__(self, scenario: str = DEFAULT_SCENARIO) -> None:
        if scenario not in SCENARIOS:
            raise KeyError(f"unknown mock scenario {scenario!r}; known: {sorted(SCENARIOS)}")
        self.scenario = SCENARIOS[scenario]
        self._scripted: dict[str, list[Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ---- test helpers
    @staticmethod
    def scenario_ids() -> list[str]:
        return sorted(SCENARIOS)

    def script_plan(self, title: str, *payloads: Any) -> None:
        """Queue payloads for `plan`/`check` calls whose schema title is `title` (last one repeats)."""
        self._scripted.setdefault(title, []).extend(payloads)

    def _record(self, method: str, **info: Any) -> None:
        with self._lock:
            self.calls.append({"method": method, **info})

    def _scripted_for(self, schema: dict[str, Any] | None) -> Any | None:
        title = (schema or {}).get("title")
        if not title:
            return None
        q = self._scripted.get(title)
        if q:
            return copy.deepcopy(q.pop(0) if len(q) > 1 else q[0])
        if title in self.scenario.plan_outputs:
            return copy.deepcopy(self.scenario.plan_outputs[title])
        return None

    # ---- ModelPort
    def plan(self, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> dict[str, Any]:
        self._record("plan", messages=copy.deepcopy(messages), schema=schema)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        if self.scenario.vulnerable_planner:
            hijack = follow_visible_instructions(prompt_text)
            if hijack is not None:
                return {"next_step": hijack, **{k: v for k, v in hijack.items() if k != "hijacked"}, "hijacked": True}
        scripted = self._scripted_for(schema)
        if scripted is not None:
            return scripted
        if schema is None:
            return {"text": "mock plan"}
        return blank_for(schema)

    def read(self, untrusted: str, schema: dict[str, Any]) -> dict[str, Any]:
        self._record("read", chars=len(untrusted), untrusted=untrusted, schema=schema)
        scripted = self._scripted_for(schema)
        if scripted is not None:
            return scripted
        return faithful_extract(untrusted, schema, leak_instructions=self.scenario.vulnerable_reader)

    def check(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self._record("check", prompt=prompt, schema=schema)
        scripted = self._scripted_for(schema)
        if scripted is not None:
            return scripted
        if schema.get("title") == "drift_check":
            goal = re.search(r"(?im)^goal:\s*(.+)$", prompt)
            step = re.search(r"(?im)^proposed step:\s*(.+)$", prompt)
            g = _tokens(goal.group(1)) if goal else set()
            s_text = step.group(1) if step else ""
            kind = s_text.split()[0].lower() if s_text else ""
            st = _tokens(s_text)
            if kind in _BENIGN_KINDS or not g or (g & st):
                ok = True
            elif (st & _RISKY_WORDS) and not (g & _RISKY_WORDS):
                ok = False
            else:
                ok = kind != "goto"  # a step to an address the goal does not mention is off-goal
            return {"serves_goal": ok, "reason": "mock: overlaps the goal" if ok else "mock: nothing in the goal explains this step"}
        return blank_for(schema)

    def vision(self, image: bytes, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        self._record("vision", bytes=len(image), prompt=prompt)
        scripted = self._scripted_for(schema)
        if scripted is not None:
            return scripted
        if schema is None:
            return {"text": "mock screenshot description"}
        return blank_for(schema)

    def computer_step(self, goal: str, screenshot: bytes, history: list[dict[str, Any]],
                      *, session: str | None = None, store: bool | None = None, note: str | None = None) -> Action | Done | SafetyStop:
        self._record("computer_step", goal=goal, n_history=len(history), session=session)
        script = self.scenario.computer
        i = len(history)
        if i >= len(script):
            return Done(summary="script finished", claimed_success=True)
        step = script[i]
        k = step["kind"]
        if k == "done":
            return Done(summary=step["summary"], claimed_success=bool(step["ok"]))
        if k == "safety_stop":
            return SafetyStop(checks=copy.deepcopy(step["checks"]))
        try:
            w, h = png_size(screenshot)
        except Exception:  # an empty or invalid screenshot is still a deterministic step
            w, h = 1280, 720
        if k in ("click", "double_click", "move"):
            args = {"x": int(step["fx"] * w), "y": int(step["fy"] * h)}
            if k == "click":
                args["button"] = step.get("button", "left")
            if "label" in step:
                args["label"] = step["label"]  # a hint for gate tests; validated and ignored by actuators
            return Action(k, args)
        if k == "type":
            return Action("type", {"text": step["text"]})
        if k == "key":
            return Action("key", {"keys": list(step["keys"])})
        return Action(k, {})
