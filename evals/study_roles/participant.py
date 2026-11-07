"""The participants: a language model (the real one, two declared tiers) and scripted FAKE participants used to test the harness before any model runs.

The model participant sees what a person would see (page text, the full text of the text boxes, a numbered list of visible controls, what it has done so far, how many
actions are left, and the coach overlay when one is up) and is told nothing about the checks the coach teaches. Persona text varies carefulness, reading of on-page prompts
and verbosity, and is neutral about the job's habits. Reached through ``understudy_agent.models.get_model_port()``; the tier is declared in advance:

    fast       port.check(prompt, schema)   the fast model at reasoning effort none (the port's default for the fast role)
    fast-low   port.check(prompt, schema)   the fast model with OPENAI_EFFORT_FAST=low set by the harness before the port is built
    planner    port.plan([{"role": "user", "content": prompt}], schema)   the planner model at the port's default effort (low): declared, NOT run unless the pilot
               shows both fast options at the floor and a measured cost that affords at least 12 participants (PLAN.md)

Model ids come from the environment through the port and are recorded; nothing is hard-coded here.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from evals.study_sim.budget import Budget

from .design import ParticipantSpec, Persona, Slot
from .observe_roles import KINDS, RAction, parse_actions, render_elements, snapshot_text
from .roles import cfg

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
MAX_NOTE = 280
MAX_BATCH = 4
TIERS = ("fast", "fast-low", "planner")

CARE = {
    "low": "You work quickly. Once something looks done you move on, and you rarely re-read what you did or went past.",
    "medium": "You work at a steady pace and check the obvious things before moving on.",
    "high": "You work carefully. You look over each page and what you have done before moving on, and you notice details on the page.",
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
NOVICE = "You are a beginner at this job. You are unsure what to check, you tend to accept the first plausible result, and you want to finish quickly."   # the weaker prompt of the (unfunded) sensitivity check

DECIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(KINDS)}, "ref": {"type": "integer"}, "text": {"type": "string"}, "find": {"type": "string"},
            "url": {"type": "string"}, "seconds": {"type": "number"}}, "required": ["kind"]}},
    },
    "required": ["thought", "actions"],
}
NOTE_SCHEMA = {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}

ACTION_HELP = (
    "Actions you can take (up to 4 per reply, they run in order; if the page changes, the rest are dropped):\n"
    "- click: ref = the number of a control\n"
    "- fill: ref = a text field or text box, text = what to put in it (replaces everything that is there)\n"
    "- replace: ref = a text box, find = a piece of text that is in it, text = what to put in its place (only the first match changes)\n"
    "- select: ref = a dropdown, text = the option to choose\n"
    "- goto: reload this page (for example after an error page); no address is needed\n"
    "- wait: seconds (at most 5)\n"
    "- dismiss_coach: close the helper app's note on your screen, if one is showing\n"
    "- finish: you are done with this case (or you want to stop)"
)


def persona_text(role: str, p: Persona) -> str:
    return " ".join([cfg(role).intro, CARE[p.carefulness], READS[p.reads_prompts], VERB[p.verbosity]] + ([NOVICE] if p.strength == "novice" else []))


@dataclass
class StepContext:
    spec: ParticipantSpec
    slot: Slot
    obs: dict
    history: list[str]
    used: int
    cap: int
    note_to_self: str | None = None
    coach: dict | None = None       # {message, step} when the overlay is up
    ring_found: bool = False


def build_prompt(ctx: StepContext) -> str:
    c = cfg(ctx.spec.role)
    parts = [
        "You are taking part in a short study of an office task, using a web browser on a computer. You act as a person would: you can only click, type, "
        "choose from dropdowns and edit text in text boxes.",
        f"Participant code: {ctx.spec.pid}.", persona_text(ctx.spec.role, ctx.spec.persona), "",
        "THE FACILITATOR TOLD YOU:", c.facilitator]
    if ctx.slot.phase in ("practice",):
        pass
    else:
        parts += ["", "The facilitator says: \"This one is on your own.\""]
    if ctx.slot.phase == "post" and ctx.note_to_self:
        parts += [f"A note you wrote to yourself after an earlier case: \"{ctx.note_to_self}\""]
    parts += ["", f"TIME: you have about {max(ctx.cap - ctx.used, 0)} actions left before time is called.", "",
              "WHAT IS ON YOUR SCREEN NOW", "Page text:", snapshot_text(ctx.obs),
              "", "Controls on the page:", render_elements(ctx.obs.get("elements", [])) or "(none)"]
    if ctx.coach:
        parts += ["", "A helper app called Understudy is switched on on this computer. It is showing this note on your screen"
                      + (" and has drawn an orange ring around one control" if ctx.ring_found else "") + ":", f"\"{ctx.coach['message']}\""]
    parts += ["", "WHAT YOU HAVE DONE SO FAR IN THIS CASE (most recent last):", "\n".join(ctx.history[-12:]) or "(nothing yet)", "", ACTION_HELP, "",
              "Reply with JSON: a short thought (one sentence, why you act) and your actions."]
    return "\n".join(parts)


def build_note_prompt(spec: ParticipantSpec, digest: str) -> str:
    return "\n".join([
        "You are taking part in a short study of an office task using a web browser. " + persona_text(spec.role, spec.persona), f"Participant code: {spec.pid}.",
        "You have just finished a case (or time ran out). Here is what happened, in order:", digest, "",
        f"Write a note to yourself, one or two sentences and at most {MAX_NOTE} characters, about what you will do next time you do a similar case. "
        "Base it only on what happened above. Reply with JSON."])


def cache_key(tier: str, model: str, prompt: str, schema: dict) -> str:
    return hashlib.sha256(json.dumps([tier, model, prompt, schema], sort_keys=True).encode()).hexdigest()[:24]


class HarnessModelError(RuntimeError):
    """The model call failed. The case is a harness error (exclusion), not a participant behaviour."""


class ModelParticipant:
    """Calls the model port on a declared tier. Cached by prompt hash (the participant code is in every prompt, so two participants never share a hash)."""

    retry_sleeps = (3.0, 10.0, 30.0)

    def __init__(self, port, spec: ParticipantSpec, budget: Budget, tier: str, model_id: str, cache_dir: Path = CACHE_DIR) -> None:
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        self.port, self.spec, self.budget, self.tier, self.model_id, self.cache_dir = port, spec, budget, tier, model_id, cache_dir
        self.calls = 0
        self.errors = 0

    def _ask(self, prompt: str, schema: dict) -> dict:
        if self.tier in ("fast", "fast-low"):
            return self.port.check(prompt, schema)
        return self.port.plan([{"role": "user", "content": prompt}], schema)

    def _check_with_retries(self, prompt: str, schema: dict) -> dict:
        for i in range(len(self.retry_sleeps) + 1):
            try:
                return self._ask(prompt, schema)
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
        key = cache_key(self.tier, self.model_id, prompt, schema)
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

    async def decide(self, ctx: StepContext) -> list[RAction]:
        try:
            out = await asyncio.to_thread(self._call_sync, build_prompt(ctx), DECIDE_SCHEMA, "decide")
        except Exception as exc:  # noqa: BLE001
            self.errors += 1
            if type(exc).__name__ == "BudgetExhausted":
                raise
            raise HarnessModelError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        return parse_actions(out, MAX_BATCH)

    async def write_note(self, digest: str) -> str:
        try:
            out = await asyncio.to_thread(self._call_sync, build_note_prompt(self.spec, digest), NOTE_SCHEMA, "note")
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "BudgetExhausted":
                raise
            raise HarnessModelError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        return " ".join(str(out.get("note", "")).split())[:MAX_NOTE]


# ------------------------------------------------------------------------------------------------ the FAKE participants (no model)
@dataclass
class ScriptedParticipant:
    """Runs a program (the step tuples of ``sandbox.program``) against the visible controls, no model. ``obeys``: when the coach note is up, insert the snippet that does
    the step it is about; ``dismisses``: close the note instead; ``presses_forbidden``: press the forbidden control (protocol-violation test). ``style`` is the program style
    (expert | skipper | claimer); ``variation`` permutes the expert's order."""
    spec: ParticipantSpec
    slot: Slot
    program: list
    snippets: dict
    obeys: bool = False
    dismisses: bool = False
    presses_forbidden: bool = False
    note_text: str = "fake participant: no model was used"
    started: bool = False
    seen_coach: str | None = None
    calls: int = 0
    steps: list = field(default_factory=list)

    @staticmethod
    def find(elements: list[dict], needle: str) -> dict | None:
        n = needle.lower()
        return next((e for e in elements if n in (e.get("label") or "").lower()), None)

    async def decide(self, ctx: StepContext) -> list[RAction]:
        self.calls += 1
        if not self.started:
            self.steps = list(self.program)
            if self.presses_forbidden:
                self.steps.insert(-1, ("click", cfg(self.spec.role).forbidden_label)) if self.steps else None
            self.started = True
        if ctx.coach and ctx.coach["message"] != self.seen_coach:
            self.seen_coach = ctx.coach["message"]
            if self.dismisses:
                return [RAction("dismiss_coach")]
            if self.obeys:
                self.steps[0:0] = list(self.snippets.get(ctx.coach.get("step") or "", []))
        while self.steps:
            step = self.steps[0]
            kind = step[0]
            if kind == "wait":
                self.steps.pop(0)
                return [RAction("wait", seconds=float(step[1]))]
            el = self.find(ctx.obs.get("elements", []), step[1])
            self.steps.pop(0)
            if el is None:
                continue                         # not on this page (a step the page already did): skip; the checks catch real problems
            if kind == "click":
                return [RAction("click", ref=el["ref"])]
            if kind == "fill":
                return [RAction("fill", ref=el["ref"], text=step[2])]
            if kind == "replace":
                return [RAction("replace", ref=el["ref"], find=step[2], text=step[3])]
            if kind == "select":
                return [RAction("select", ref=el["ref"], text=step[2])]
        return [RAction("finish")]

    async def write_note(self, digest: str) -> str:
        return self.note_text[:MAX_NOTE]
