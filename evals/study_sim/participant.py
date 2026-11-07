"""The participants: a language model (the real one) and a scripted FAKE used to test the harness before any model runs.

The model participant sees what a person would see (page text, a numbered list of visible controls, its household card, the
protocol's task script, the bookmarks, the coach overlay if one is up) and is told nothing about what "cliff" or "reconcile" mean.
It is reached through ``understudy_agent.models.get_model_port().check`` (the FAST tier; the model id comes from the environment).
Persona text varies carefulness, reading of on-page prompts and verbosity, and is neutral about benefits knowledge.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .budget import Budget
from .design import ParticipantSpec, Persona
from .observe import KINDS, Action, parse_actions, render_elements

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
MAX_NOTE = 280
MAX_BATCH = 4

TASK_SCRIPT = (
    "For each household you'll use GovCalc and Quick Estimator. Enter the household in each, then open the case note page, enter the "
    "case reference and the two results, choose how the calculators compare, and press Save draft. Never press Submit to claimant "
    "record. If I say stop, stop."
)


def bookmarks_text(urls: dict) -> str:
    return f"GovCalc = {urls['gov']} ; Quick Estimator = {urls['quick']} ; Case note page = {urls['note']}"


CARE = {
    "low": "You work quickly. Once something looks filled in you move on, and you rarely re-read what you entered or went past.",
    "medium": "You work at a steady pace and check the obvious things before moving on.",
    "high": "You work carefully. You look over each page and what you have entered before moving on, and you notice details on the page.",
}
READS = {
    "low": "You tend to skim past banners, notes and highlights on a page unless they stop you doing what you are doing.",
    "high": "You read any banner, note or highlight that appears on the page, and think about it before carrying on.",
}
VERB = {
    "terse": "When you write notes to yourself you keep them very short, a few words.",
    "normal": "When you write notes to yourself you write one or two plain sentences.",
    "wordy": "When you write notes to yourself you like to write things out fully, using most of the space you have.",
}

DECIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "ref": {"type": "integer"}, "text": {"type": "string"}, "url": {"type": "string"}, "seconds": {"type": "number"}},
            "required": ["kind"]}},
    },
    "required": ["thought", "actions"],
}
NOTE_SCHEMA = {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}

ACTION_HELP = (
    "Actions you can take (up to 4 per reply, they run in order; if the page changes, the rest are dropped):\n"
    "- click: ref = the number of a control\n"
    "- fill: ref = a text field, text = what to type (replaces what is there)\n"
    "- select: ref = a dropdown, text = the option to choose\n"
    "- goto: url = an address to open in this tab (bookmarks above)\n"
    "- new_tab: url = an address to open in a new tab (it becomes the active tab)\n"
    "- switch_tab: ref = the tab number to bring to the front\n"
    "- wait: seconds (at most 5)\n"
    "- dismiss_coach: close the helper app's note on your screen, if one is showing\n"
    "- finish: you are done with this case (or you want to stop)"
)


def persona_text(p: Persona) -> str:
    return " ".join([
        "You are a volunteer with no prior experience of benefits work.",
        CARE[p.carefulness], READS[p.reads_prompts], VERB[p.verbosity]])


def tabs_text(tabs: list[dict]) -> str:
    """Each tab dict carries a plain-language name worked out by the runner from the world's ports (GovCalc, Quick Estimator, ...)."""
    return "; ".join(f"tab {t['index']}{' (active)' if t.get('active') else ''}: {t.get('name', 'page')}, \"{(t.get('title') or '')[:40]}\"" for t in tabs)


@dataclass
class StepContext:
    spec: ParticipantSpec
    phase: str                      # practice | post
    card: str
    obs: dict                       # snapshot from SNAPSHOT_JS
    tabs: list[dict]
    history: list[str]
    used: int
    cap: int
    urls: dict = field(default_factory=dict)
    note_to_self: str | None = None
    coach: dict | None = None       # {message} when the overlay is up
    ring_found: bool = False


def build_prompt(ctx: StepContext) -> str:
    p = ctx.spec.persona
    parts = [
        "You are taking part in a short study of an office task, using a web browser on a computer. You act as a person would: you can "
        "only click, type, choose from dropdowns, open addresses and switch tabs.",
        f"Participant code: {ctx.spec.pid}.",
        persona_text(p),
        "",
        "THE FACILITATOR TOLD YOU:",
        TASK_SCRIPT,
        "The facilitator also said: \"I'm testing a coaching tool, not you. You will check two households on two benefit calculators, write a short case note, "
        "and I'll time each part. The households are made up and the calculators are local test sites. I can't help during a case.\"",
        f"Bookmarks: {bookmarks_text(ctx.urls)}",
        "",
        "THE HOUSEHOLD ON YOUR PAPER:",
        ctx.card,
    ]
    if ctx.phase == "post":
        parts += ["", "The facilitator says: \"This one is on your own.\""]
        if ctx.note_to_self:
            parts += [f"A note you wrote to yourself after the earlier case: \"{ctx.note_to_self}\""]
    parts += ["", f"TIME: you have about {max(ctx.cap - ctx.used, 0)} actions left before time is called.", "",
              "WHAT IS ON YOUR SCREEN NOW",
              f"Tabs: {tabs_text(ctx.tabs)}",
              f"Address of the active tab: {ctx.obs.get('url', '')}",
              f"Page text: {ctx.obs.get('text', '')[:1400]}",
              "Controls on the page:", render_elements(ctx.obs.get("elements", [])) or "(none)"]
    if ctx.coach:
        parts += ["", "A helper app called Understudy is switched on on this computer. It is showing this note on your screen"
                      + (" and has drawn an orange ring around one control" if ctx.ring_found else "") + ":",
                  f"\"{ctx.coach['message']}\""]
    parts += ["", "WHAT YOU HAVE DONE SO FAR IN THIS CASE (most recent last):",
              "\n".join(ctx.history[-10:]) or "(nothing yet)", "", ACTION_HELP, "",
              "Reply with JSON: a short thought (one sentence, why you act) and your actions."]
    return "\n".join(parts)


def build_note_prompt(spec: ParticipantSpec, digest: str, phase: str = "practice") -> str:
    return "\n".join([
        "You are taking part in a short study of an office task using a web browser. " + persona_text(spec.persona),
        f"Participant code: {spec.pid}.",
        "You have just finished a case (or time ran out). Here is what happened, in order:",
        digest,
        "",
        f"Write a note to yourself, one or two sentences and at most {MAX_NOTE} characters, about what you will do next time you do a "
        "similar case. Base it only on what happened above. Reply with JSON."])


def cache_key(model: str, prompt: str, schema: dict) -> str:
    return hashlib.sha256(json.dumps([model, prompt, schema], sort_keys=True).encode()).hexdigest()[:24]


class ModelParticipant:
    """Calls the model port. Cached by prompt hash; the participant code is in every prompt so two participants never share a hash."""

    def __init__(self, port, spec: ParticipantSpec, budget: Budget, model_id: str, cache_dir: Path = CACHE_DIR) -> None:
        self.port, self.spec, self.budget, self.model_id, self.cache_dir = port, spec, budget, model_id, cache_dir
        self.calls = 0
        self.errors = 0

    retry_sleeps = (3.0, 10.0, 30.0)

    def _check_with_retries(self, prompt: str, schema: dict) -> dict:
        """A transient provider error (rate limit, timeout, an output that fails the schema) is retried with the same prompt; a refusal is not
        retried and counts as the participant doing nothing. Anything else after the last retry is a harness error."""
        for i in range(len(self.retry_sleeps) + 1):
            try:
                return self.port.check(prompt, schema)
            except Exception as exc:  # noqa: BLE001
                name = type(exc).__name__
                if name == "ModelRefusal":
                    return {"thought": "", "actions": [], "note": ""}
                if name == "BudgetExhausted" or i == len(self.retry_sleeps):
                    raise
                self.errors += 1
                time.sleep(self.retry_sleeps[i])
        raise RuntimeError("unreachable")

    def _call_sync(self, prompt: str, schema: dict, role: str) -> dict:
        key = cache_key(self.model_id, prompt, schema)
        f = self.cache_dir / f"{key}.json"
        if f.exists():
            self.budget.hit(self.spec.pid)
            return json.loads(f.read_text())
        out = self._check_with_retries(prompt, schema)
        self.calls += 1
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(out))
        stats = getattr(self.port, "stats", None)
        if isinstance(stats, dict) and "input_tokens" in stats:
            self.budget.charge_from_stats(self.spec.pid, role, dict(stats))
        else:
            self.budget.charge(self.spec.pid, role, len(prompt) // 4, len(json.dumps(out)) // 4, estimated=True)
        return out

    async def decide(self, ctx: StepContext) -> list[Action]:
        prompt = build_prompt(ctx)
        try:
            out = await asyncio.to_thread(self._call_sync, prompt, DECIDE_SCHEMA, "decide")
        except Exception as exc:  # noqa: BLE001 - a provider error ends the case as a harness error, never silently
            self.errors += 1
            if type(exc).__name__ == "BudgetExhausted":
                raise
            raise HarnessModelError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        return parse_actions(out, MAX_BATCH)

    async def write_note(self, digest: str) -> str:
        prompt = build_note_prompt(self.spec, digest)
        try:
            out = await asyncio.to_thread(self._call_sync, prompt, NOTE_SCHEMA, "note")
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "BudgetExhausted":
                raise
            raise HarnessModelError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        return " ".join(str(out.get("note", "")).split())[:MAX_NOTE]


class HarnessModelError(RuntimeError):
    """The model call failed. The case is a harness error (exclusion), not a participant behaviour."""


# ------------------------------------------------------------------------------------------------ the FAKE participant
@dataclass
class FakeParticipant:
    """Scripted, no model. ``style``:
    - 'skipper': both calculators, then the note with the default 'agree', never opens a cliff panel, never switches tabs
    - 'thorough': opens both cliff panels, switches between the calculator tabs, chooses 'discrepancy'
    plus ``obeys``: when the coach note is up, do the step it is about ('cliff' presses the buttons, 'reconcile' switches tabs and chooses
    discrepancy). ``dismisses`` closes the note instead. ``submits`` presses the forbidden button (protocol violation test)."""
    spec: ParticipantSpec
    case_inputs: dict           # household site_inputs for 'a' and 'b'
    case_ref: str
    urls: dict = field(default_factory=dict)   # gov, quick, note
    style: str = "skipper"
    obeys: bool = False
    dismisses: bool = False
    submits: bool = False
    note_text: str = "fake participant: no model was used"
    program: list = field(default_factory=list)
    started: bool = False
    seen_coach: str | None = None
    calls: int = 0

    A_LABELS = {"adult1_age": "Your age", "adult1_earnings_monthly": "Your monthly take-home pay", "rent_monthly": "Monthly rent",
                "savings": "Total savings", "childcare_monthly": "Monthly childcare", "tenure": "rent or own", "bedrooms": "Bedrooms you need",
                "adults": "How many adults", "limited_capability": "health condition"}
    B_LABELS = {"adult1_age": "Your age", "adult1_earnings_monthly": "Your monthly pay", "rent_monthly": "Monthly rent",
                "savings": "Savings", "childcare_monthly": "Monthly childcare", "tenure": "Rent or own", "bedrooms": "Bedrooms needed",
                "adults": "Adults in household", "limited_capability": "Health condition"}

    def _calc_a(self) -> list:
        v = self.case_inputs["a"]
        return [("goto", self.urls["gov"]),
                ("fill", self.A_LABELS["adult1_age"], v["adult1_age"]), ("click", "Continue"),
                ("fill", self.A_LABELS["adult1_earnings_monthly"], v["adult1_earnings_monthly"]), ("click", "Continue"),
                ("fill", self.A_LABELS["rent_monthly"], v["rent_monthly"]), ("click", "Continue"),
                ("fill", self.A_LABELS["savings"], v["savings"]), ("click", "Calculate")]

    def _calc_b(self) -> list:
        v = self.case_inputs["b"]
        return [("fill", self.B_LABELS["adult1_age"], v["adult1_age"]), ("fill", self.B_LABELS["adult1_earnings_monthly"], v["adult1_earnings_monthly"]),
                ("fill", self.B_LABELS["rent_monthly"], v["rent_monthly"]), ("fill", self.B_LABELS["savings"], v["savings"]), ("click", "Calculate")]

    def _note(self, reconcile: bool) -> list:
        steps = [("goto", self.urls["note"]), ("fill", "Case reference", self.case_ref), ("fill", "GovCalc result", "1"),
                 ("fill", "Quick Estimator result", "2"), ("fill", "EntitledTo result", "n/a")]
        if reconcile:
            steps.append(("select", "Reconciliation", "Discrepancy"))
        steps += [("click", "Save draft")]
        return steps

    def _start(self) -> None:
        p: list = []
        if self.style == "thorough":
            p += self._calc_a() + [("click", "Check cliff edges"), ("new_tab", self.urls["quick"])] + self._calc_b()
            p += [("click", "Check cliff edges"), ("switch_tab", 0), ("switch_tab", 1), ("switch_tab", 0), ("new_tab", self.urls["note"])]
            p += self._note(True)[1:]
        else:
            p += self._calc_a() + [("new_tab", self.urls["quick"])] + self._calc_b()
            p += [("new_tab", self.urls["note"])] + self._note(False)[1:]
        if self.submits:
            p = p[:-1] + [("click", "Save draft"), ("click", "Submit to claimant record")]
        p.append(("finish",))
        self.program = p
        self.started = True

    def _find(self, elements: list[dict], needle: str) -> dict | None:
        n = needle.lower()
        return next((e for e in elements if n in (e.get("label") or "").lower()), None)

    async def decide(self, ctx: StepContext) -> list[Action]:
        self.calls += 1
        if not self.started:
            self._start()
        if ctx.coach and ctx.coach["message"] != self.seen_coach:
            self.seen_coach = ctx.coach["message"]
            if self.dismisses:
                self.program.insert(0, ("dismiss_coach",))
            elif self.obeys:
                msg = ctx.coach["message"].lower()
                if "cliff" in msg:
                    self.program[0:0] = [("switch_tab", 0), ("click", "Check cliff edges"), ("switch_tab", 1), ("click", "Check cliff edges"), ("switch_tab", 2)]
                elif "reconcile" in msg or "agree" in msg:
                    self.program[0:0] = [("switch_tab", 0), ("switch_tab", 1), ("switch_tab", 2), ("select", "Reconciliation", "Discrepancy")]
        while self.program:
            step = self.program[0]
            kind = step[0]
            if kind == "goto":
                self.program.pop(0)
                return [Action("goto", url=step[1])]
            if kind == "new_tab":
                self.program.pop(0)
                return [Action("new_tab", url=step[1])]
            if kind == "switch_tab":
                self.program.pop(0)
                return [Action("switch_tab", ref=step[1])]
            if kind == "dismiss_coach":
                self.program.pop(0)
                return [Action("dismiss_coach")]
            if kind == "finish":
                return [Action("finish")]
            el = self._find(ctx.obs.get("elements", []), step[1])
            if el is None:
                self.program.pop(0)                  # not on this page (e.g. a button already clicked): skip, the check catches real problems
                continue
            self.program.pop(0)
            if kind == "fill":
                return [Action("fill", ref=el["ref"], text=step[2])]
            if kind == "select":
                return [Action("select", ref=el["ref"], text=step[2])]
            if kind == "click":
                return [Action("click", ref=el["ref"])]
        return [Action("finish")]

    async def write_note(self, digest: str) -> str:
        return self.note_text[:MAX_NOTE]


def sleep_s(x: float) -> float:
    return max(0.0, min(float(x), 5.0))
