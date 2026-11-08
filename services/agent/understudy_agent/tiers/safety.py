"""Navigator-side wrapper around agent-safety's `SafetyPipeline` (the ONE facade for layers 1 to 8).

Every step goes: observe -> (plan) -> authorise -> act -> record_result. One `Guard` per navigator, so each
navigator has its own step budget, stuck-loop memory and pause state; they share the audit log and the queue.

Verdicts become exceptions the tiers already understand:
  needs_human -> GateStop      (a QueueItem exists; approval is bound to that action and works once)
  pause       -> InjectionStop (the run is paused until the worker approves the pause item)
  block       -> ActionRejected for a malformed action (layer 3), GateStop otherwise (kill, denylist, settings)
  drift/stuck -> StuckLoop     (the ladder recovers or escalates)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..audit import AuditLog
from ..models.port import ModelPort
from ..queue import ApprovalQueue
from ..security.config import SecurityConfig
from ..security.denylist import Denylist
from ..security.detector import PageObservation
from ..security.gates import RoutineContext, TargetInfo
from ..security.pipeline import Observation as PipeObservation
from ..security.pipeline import SafetyPipeline, StepDecision
from .base import ActionRejected, GateStop, InjectionStop, Observation, StepEvent, StuckLoop
from .observe import observe as observe_page

from ..security.reader import MEMO_SIZE as READER_MEMO

MIN_STEP_BUDGET = 120  # a compiled bundle is up to 60 steps, plus tier 2 and 3 on top (their own caps are 20)


@dataclass
class Seen:
    """One fresh observation: our DOM view (for refs and labels) and the pipeline's checked view."""

    obs: Observation
    pipe: PipeObservation

    @property
    def fields(self) -> dict[str, Any] | None:
        return self.pipe.fields


class Guard:
    def __init__(
        self,
        port: ModelPort,
        *,
        run_id: str | None = None,
        routine_id: str | None = None,
        config: SecurityConfig | None = None,
        audit: AuditLog | None = None,
        queue: ApprovalQueue | None = None,
        mode: str = "compiled",
        unattended: bool = False,
        rung: str = "A0",
        opted_in: frozenset[Any] = frozenset(),
        typed_confirm: bool = False,
        recorded_hosts: tuple[str, ...] | frozenset[str] = (),
        goal: str = "",
        denylist: Denylist | None = None,
    ) -> None:
        cfg = config or SecurityConfig()
        if cfg.max_steps < MIN_STEP_BUDGET:
            cfg = replace(cfg, max_steps=MIN_STEP_BUDGET)
        audit = audit or AuditLog()
        queue = queue or ApprovalQueue(audit=audit)
        ctx = RoutineContext(
            routine_id=routine_id, mode=mode, unattended=unattended, rung=rung, opted_in=frozenset(opted_in),  # type: ignore[arg-type]
            typed_confirm=typed_confirm, recorded_hosts=frozenset(recorded_hosts), run_id=run_id)
        self.port = port
        self.pipe = SafetyPipeline(port, cfg, audit=audit, queue=queue, routine=ctx,
                                   denylist=denylist if denylist is not None else Denylist.load(), goal=goal,
                                   reader_memo=READER_MEMO)   # one navigator, one person: the reader remembers its own closed output
        self.run_id, self.routine_id = run_id, routine_id
        self._apply_mode(mode)

    # ------------------------------------------------------------------ plumbing
    @property
    def unattended(self) -> bool:
        return bool(self.pipe.routine.unattended)

    @property
    def config(self) -> SecurityConfig:
        return self.pipe.config

    @property
    def queue(self) -> ApprovalQueue:
        return self.pipe.queue

    @property
    def audit(self) -> AuditLog:
        return self.pipe.audit

    def _apply_mode(self, mode: str) -> None:
        self.pipe.routine = replace(self.pipe.routine, mode=mode)  # type: ignore[arg-type]
        # A compiled step is fixed by a validated bundle, not proposed by a model: the goal-drift model check is
        # for model-proposed steps (tier 2 and 3). The stuck-loop detector stays on for both.
        self.pipe.drift.enabled = self.pipe.config.drift and mode != "compiled"

    def set_mode(self, mode: str) -> None:
        self._apply_mode(mode)

    def set_goal(self, goal: str) -> None:
        self.pipe.goal = goal

    def credit_wait(self, seconds: float) -> None:
        """Time spent waiting for the worker's click is not time the run used (the budget clock is paused for it)."""
        self.pipe.credit_wait(seconds)

    def new_page(self) -> None:
        """A fresh page: the reader's memo of earlier pages is dropped (it never carries from one page to another)."""
        self.pipe.reader.clear_memo()

    # ------------------------------------------------------------------ observe
    async def observe(self, page: Any, *, obs: Observation | None = None, schema: dict[str, Any] | None = None,
                      navigator: str = "", step: int = 0, tier: int = 0) -> Seen:
        obs = obs or await observe_page(page)
        return self.observe_obs(obs, schema=schema, navigator=navigator)

    def observe_obs(self, obs: Observation, *, schema: dict[str, Any] | None = None, navigator: str = "", fresh: bool = False) -> Seen:
        po = PageObservation(text=obs.text, hidden_texts=list(obs.hidden_texts), alt_texts=list(obs.alt_texts),
                             title=obs.title, url=obs.url)
        pobs = self.pipe.observe(po, schema=schema, fresh=fresh)
        if pobs.paused:
            raise InjectionStop(pobs.report.summary_code(), f"({navigator})")
        return Seen(obs, pobs)

    def observe_screen(self, ocr_text: str = "") -> PipeObservation:
        """A screenshot is the observation for a desktop-style step (OCR text optional)."""
        pobs = self.pipe.observe(PageObservation(text="", ocr_text=ocr_text))
        if pobs.paused:
            raise InjectionStop(pobs.report.summary_code(), "(screen)")
        return pobs

    # ------------------------------------------------------------------ plan
    def planner_messages(self, goal: str, seen: Seen | PipeObservation, history_summary: str = "",
                         extra: str = "") -> list[dict[str, str]]:
        pobs = seen.pipe if isinstance(seen, Seen) else seen
        msgs = self.pipe.planner_messages(goal, [pobs], history_summary)
        if extra:
            msgs[-1] = {"role": msgs[-1]["role"], "content": msgs[-1]["content"] + "\n\n" + extra}
        return msgs

    # ------------------------------------------------------------------ authorise
    def authorise(self, action: Any, seen: Seen | PipeObservation | None, *, label: str | None = None,
                  role: str | None = None, url: str | None = None, field_attrs: dict[str, Any] | None = None,
                  screen: tuple[int, int] | None = None, approved_queue_id: str | None = None,
                  app: str | None = None, structure: tuple[str, ...] = ()) -> StepDecision:
        pobs = seen.pipe if isinstance(seen, Seen) else seen
        target = TargetInfo(label=label, role=role, url=url, app=app, field_attrs=field_attrs, structure=tuple(structure))
        return self.pipe.authorise(action, observation=pobs, target=target, screen=screen,
                                   approved_queue_id=approved_queue_id)

    def peek_gate(self, action: Any, *, label: str | None = None, role: str | None = None, url: str | None = None,
                  field_attrs: dict[str, Any] | None = None, structure: tuple[str, ...] = ()) -> Any:
        """What the action-class gate (layer 4) would say about this action, as the pipeline computes it, with NO side effect: no queue item,
        no audit line, no budget used. A browsing task that may wait for the worker's click asks this first, to be sure that a step it is about
        to ask about is a normal one (read, navigate, fill) and not an outward or irreversible one."""
        from ..security.gates import gate

        kind = action.get("kind") if isinstance(action, dict) else getattr(action, "kind", None)
        args = (action.get("args") if isinstance(action, dict) else getattr(action, "args", None)) or {}
        target = TargetInfo(label=label, role=role, url=url, field_attrs=field_attrs, structure=tuple(structure))
        return gate(str(kind), dict(args), self.pipe._ctx(), target, enabled=self.config.gates)

    def check_typed_value(self, value: str, *, url: str | None, signature: str) -> None:
        """Layer 5 on the value a fact handle ACTUALLY resolved to, at the moment it is about to be typed (S-15). The
        handle string passed layer 5 when the step was authorised; the value did not. Tainted data (read from a page or a
        file) typed into a site this routine never recorded goes to the queue, exactly as a literal would. The value
        itself is never written down: the queue item carries the layer and a code."""
        fd = self.pipe.dataflow.check_text_sink(value, url)
        if fd is None or fd.verdict == "allow":
            return
        why = fd.reasons[0] if fd.reasons else "tainted data typed into a site the routine did not record"
        item = self.pipe.queue.enqueue(
            kind="outward_step", title="type: a fact value that came from a page", summary=why, risk_class="outward",
            routine_id=self.routine_id, run_id=self.run_id,
            evidence={"extracted": {"layer": "dataflow", "code": "tainted_value_via_handle"}, "tier_log": []},
            signature=signature, dedupe_key=f"{self.run_id}:{signature}:dataflow")
        self.audit.append("agent", "gate", routine=self.routine_id, run_id=self.run_id, outcome="needs_human",
                          note_code="dataflow:tainted_value_via_handle")
        dec = StepDecision("needs_human", [why], ["dataflow:tainted_value_via_handle"], "dataflow", item["id"], None)
        raise GateStop(dec, "typed fact value")

    def require(self, dec: StepDecision, label: str = "", *, navigator: str = "") -> None:
        """Turn a non-allow verdict into the exception the tiers handle."""
        if dec.verdict == "allow":
            return
        if dec.verdict == "pause":
            raise InjectionStop(",".join(dec.codes), f"({navigator})")
        if dec.layer == "drift" and any("stuck" in c for c in dec.codes):
            raise StuckLoop(",".join(dec.codes))
        if dec.verdict == "block" and dec.layer == "actions":
            raise ActionRejected(dec.reasons[0] if dec.reasons else "action rejected")
        raise GateStop(dec, label)

    def record(self, dec: StepDecision, ok: bool) -> None:
        if dec.action is not None:
            self.pipe.record_result(dec.action, ok)

    # ------------------------------------------------------------------ audit
    def record_step(self, ev: StepEvent) -> None:
        self.audit.append("agent", "agent_step", routine=self.routine_id, run_id=self.run_id,
                          tier=ev.tier if ev.tier in (1, 2, 3) else None, outcome="ok" if ev.ok else "failed",
                          note_code=ev.action)

    def note(self, kind: str, outcome: str, code: str | None = None, tier: int | None = None) -> None:
        self.audit.append("agent", kind, routine=self.routine_id, run_id=self.run_id,
                          tier=tier if tier in (1, 2, 3) else None, outcome=outcome, note_code=code)

    def enqueue(self, **kw: Any) -> dict[str, Any]:
        kw.setdefault("run_id", self.run_id)
        kw.setdefault("routine_id", self.routine_id)
        return self.queue.enqueue(**kw)

    def resume(self, queue_id: str) -> bool:
        return self.pipe.resume(queue_id)
