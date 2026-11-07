"""SafetyPipeline: the one facade agent code calls (layers 1 to 8 wired together).

    pipe = SafetyPipeline(port, config, audit=AuditLog(), queue=ApprovalQueue(), routine=RoutineContext(...))
    obs  = pipe.observe(PageObservation(...), schema=SCHEMA)          # L6 detector, L2 reader, taint tags
    msgs = pipe.planner_messages(goal, [obs])                          # L1 + L2: no raw page text
    dec  = pipe.authorise(action, observation=obs, target=TargetInfo(label=..., url=...))
    if dec.verdict == "allow": ...execute...; pipe.record_result(dec.action, ok=True)

Verdicts: allow | pause (run is paused; resume after the worker approves the pause item) | needs_human (a queue item
exists; once the worker approves it, call authorise again with approved_queue_id) | block (never, with a reason).
Every decision is audited without page text. Layers can be switched off one at a time through SecurityConfig for the
red-team ablation; the kill flag, the denylist and the audit log are not layers and are never switched off.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace as dc_replace
from typing import Any, Callable, Literal

from ..audit import AuditLog
from ..models.port import ModelPort
from ..queue import ApprovalQueue
from .actions import (ActionRejected, BudgetExceeded, ObservationClock, ObservationToken, StaleObservation, StepBudget,
                      ValidatedAction, action_signature, validate_model_action)
from .config import SecurityConfig
from .dataflow import DataFlowGuard, Taint, host_key
from .denylist import Denylist
from .detector import DetectionReport, InjectionDetector, PageObservation
from .drift import DriftChecker, StuckLoopDetector, describe_step
from .gates import RUNGS, RoutineContext, TargetInfo, gate
from .killflag import is_killed
from .reader import (ObservationView, QuarantinedReader, ReaderResult, assert_planner_prompt_clean,
                     build_planner_messages)
from .sanitize import safe_label
from .settings import SettingsGuard

Verdict = Literal["allow", "pause", "needs_human", "block"]
# Steps the goal-drift model check is NOT spent on. Reading, waiting and scrolling change nothing. Plain typing or filling a field on the
# page the run is already on moves nothing outward by itself: layer 5 stops typed data that is tainted or personal from reaching a site
# the routine did not record, and layer 4 gates the controls that send, submit or delete. Asking a model about every typing step
# produced false pauses on clean pages (measured: 5 of 93 live runs) and added no protection the other layers lack.
_BENIGN_FOR_DRIFT = {"screenshot", "wait", "scroll", "move", "scroll_page", "wait_for", "back", "type", "fill", "select_option", "extract"}


@dataclass
class Observation:
    token: ObservationToken | None
    report: DetectionReport
    paused: bool = False
    rung_delta: int = 0
    fields: dict[str, Any] | None = None
    reader: ReaderResult | None = None
    raw_text: str | None = None            # only set when layer 2 is off
    queue_id: str | None = None
    url: str = ""
    source: str = "web"

    @property
    def hits(self) -> tuple[Any, ...]:
        return self.report.hits

    @property
    def view(self) -> ObservationView:
        return ObservationView(source=self.source, fields=self.fields, raw_text=self.raw_text,
                               note="This page contained text aimed at an AI and the run is paused." if self.paused else "")


def bind_target_signature(sig: str, target: TargetInfo | None) -> str:
    """Tie an action signature to the control trusted code read under it (label, role, structure), so an approval for
    one control is no use for another that happens to sit in the same pixel bucket (S-11)."""
    if target is None or (target.label is None and target.role is None):
        return sig
    h = hashlib.sha256(f"{target.label or ''}|{target.role or ''}|{','.join(target.structure or ())}".encode()).hexdigest()[:10]
    return f"{sig}|t:{h}"


@dataclass
class StepDecision:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)     # audit-safe
    layer: str | None = None
    queue_id: str | None = None
    action: ValidatedAction | None = None
    check_error: str | None = None     # layer 7 only: why the goal check did not run (one of drift.CHECK_ERROR_CLASSES); None otherwise
    check_attempts: int = 0            # layer 7 only: how many times the check was called for this step

    @property
    def allowed(self) -> bool:
        return self.verdict == "allow"


def lower_rung(rung: str) -> str:
    i = RUNGS.index(rung) if rung in RUNGS else 0
    return RUNGS[max(0, i - 1)]


class SafetyPipeline:
    def __init__(self, port: ModelPort, config: SecurityConfig | None = None, *, audit: AuditLog | None = None,
                 queue: ApprovalQueue | None = None, routine: RoutineContext | None = None,
                 denylist: Denylist | None = None, goal: str = "", clock: Callable[[], float] = time.monotonic,
                 reader_memo: int = 0, sleep: Callable[[float], None] = time.sleep) -> None:
        self.port = port
        self.config = config or SecurityConfig()
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.routine = routine or RoutineContext()
        self.denylist = denylist or Denylist()
        self.goal = goal
        self.detector = InjectionDetector(enabled=self.config.detector)
        self.reader = QuarantinedReader(port, config=self.config, detector=self.detector, memo_size=reader_memo)
        self.drift = DriftChecker(port, enabled=self.config.drift, clock=clock, sleep=sleep)   # clock and sleep are injectable: a test never waits
        self.stuck = StuckLoopDetector()
        self.settings = SettingsGuard(enabled=self.config.settings)
        self.dataflow = DataFlowGuard(self.routine.recorded_hosts, enabled=self.config.dataflow)
        self.budget = StepBudget(self.config.max_steps, self.config.deadline_s, clock)
        self.obs_clock = ObservationClock(self.config.max_observation_age_s, clock)
        self.rung = self.routine.rung
        self.paused = False
        self._pause_queue_id: str | None = None
        self._recent: list[str] = []
        self._raw_seen: list[str] = []
        self._approval_note: str | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def _run(self) -> str | None:
        return self.routine.run_id

    def _log(self, kind: str, outcome: str, code: str | None = None, actor: str = "system", **meta: Any) -> None:
        self.audit.append(actor, kind, routine=self.routine.routine_id, run_id=self._run, outcome=outcome,
                          note_code=code, meta=meta or None)

    def _ctx(self) -> RoutineContext:
        return self.routine.with_rung(self.rung)

    def lower_rung(self, why: str) -> None:
        new = lower_rung(self.rung)
        if new != self.rung:
            self.rung = new
            self._log("rung_lowered", new, why)

    # ------------------------------------------------------------------ observe
    def observe(self, page: PageObservation, schema: dict[str, Any] | None = None, *, source: str = "web",
                fresh: bool = False) -> Observation:
        token = self.obs_clock.new_observation() if self.config.actions else None
        report = self.detector.scan_page(page) if self.config.detector else DetectionReport()
        obs = Observation(token=token, report=report, url=page.url, source=source)
        if report.paused:
            obs.paused = True
            obs.rung_delta = -1
            self.paused = True
            self.lower_rung("injection_hit")
            item = self.queue.enqueue(
                kind="injection_pause", title="A page tried to instruct the agent; run paused",
                summary="Text aimed at an AI was found on a page. Nothing was done because of it.",
                risk_class="normal", routine_id=self.routine.routine_id, run_id=self._run,
                evidence={"extracted": {"rules": sorted({h.rule for h in report.hits}),
                                        "locations": sorted({h.where for h in report.hits}),
                                        "excerpts": [h.excerpt for h in report.hits[:5]]}},
                dedupe_key=f"inj:{self._run}:{page.url}:{report.summary_code()}")
            obs.queue_id = item["id"]
            self._pause_queue_id = item["id"]
            self._log("injection_pause", "paused", report.summary_code(), score=report.score, hits=len(report.hits))
        else:
            self._log("observation", "clean" if report.clean else "weak_signal", report.summary_code() or None,
                      hits=len(report.hits))

        visible = page.visible_text()
        if report.paused:
            return obs  # the run is paused: nothing downstream will read this page, so no reader call is spent on it
        if self.config.reader:
            if schema is not None:
                rr = self.reader.read(visible, schema, source=source, fresh=fresh)
                obs.reader = rr
                obs.fields = rr.fields if rr.ok else None
                self._raw_seen = (self._raw_seen + [visible, *page.hidden_texts, *page.alt_texts])[-12:]
                if rr.ok:
                    self.dataflow.tag_fields(rr.fields, Taint.WEB, origin=host_key(page.url))
                if rr.flagged_fields:
                    self._log("observation", "fields_blanked", ",".join(sorted(set(rr.flag_reasons))), n=len(rr.flagged_fields))
        else:
            obs.raw_text = page.full_dump()  # the ablation: a naive text dump goes straight toward the planner
        return obs

    def planner_messages(self, goal: str, observations: list[Observation], history_summary: str = "",
                         system: str | None = None) -> list[dict[str, str]]:
        msgs = build_planner_messages(goal, [o.view for o in observations], self.config, history_summary=history_summary,
                                      system=system)
        if self.config.reader:
            assert_planner_prompt_clean(msgs, self._raw_seen)
        return msgs

    build_planner_messages = planner_messages  # alias used in the hand-off notes

    # ------------------------------------------------------------------ authorise
    def _decision(self, verdict: Verdict, layer: str | None, code: str, reason: str, action: ValidatedAction | None,
                  queue_id: str | None = None) -> StepDecision:
        self._log("gate" if verdict != "block" else "settings_blocked" if layer == "settings" else "gate",
                  verdict, f"{layer or 'none'}:{code}")
        return StepDecision(verdict, [reason], [f"{layer or 'none'}:{code}"], layer, queue_id, action)

    def _raise_for_human(self, layer: str, code: str, reason: str, action: ValidatedAction, target: TargetInfo,
                         risk: str, kind: str) -> StepDecision:
        # The approver's title names the CLASSIFIED class and the host, never the page's own label: the page chooses its labels, so a
        # label in the title would let a page word the question the worker is asked (review, queue title). The label stays out of
        # the queue item altogether; the evidence carries the layer, the code, the action kind and the host.
        cls = code[len("class_"):] if code.startswith("class_") else code
        host = host_key(target.url) or "this screen"
        item = self.queue.enqueue(
            kind=kind, title=f"{action.kind}: {safe_label(cls.replace('_', ' '), 30)} step on {safe_label(host, 40)}",
            summary=(f"{self._approval_note}; {reason}" if self._approval_note else reason), risk_class=risk, routine_id=self.routine.routine_id, run_id=self._run,
            evidence={"extracted": {"layer": layer, "code": code, "action": action.kind,
                                    "host": host_key(target.url)}, "tier_log": []},
            signature=action.signature, dedupe_key=f"{self._run}:{action.signature}:{layer}")
        dec = self._decision("needs_human", layer, code, reason, action, item["id"])
        if self._approval_note:
            dec.reasons.insert(0, self._approval_note)
            dec.codes.append("approval:expired")
        return dec

    def authorise(self, action: Any, *, observation: Observation | None = None, target: TargetInfo | None = None,
                  screen: tuple[int, int] | None = None, approved_queue_id: str | None = None) -> StepDecision:
        target = target or TargetInfo()
        cfg = self.config
        self._approval_note = None

        if is_killed():
            return self._decision("block", "kill", "kill_flag", "the kill switch is set", None)
        if self.paused:
            return self._decision("pause", "detector", "run_paused", "the run is paused until the worker clears the pause",
                                  None, self._pause_queue_id)

        # --- layer 3: typed one-step actions, budgets, fresh observation
        if cfg.actions:
            try:
                va = validate_model_action(action, screen=screen)
            except ActionRejected as e:
                return self._decision("block", "actions", e.code, str(e), None)
            try:
                self.budget.check()
                self.obs_clock.authorise(observation.token if observation else None)
            except BudgetExceeded as e:
                return self._decision("block", "actions", f"budget_{e.which}", str(e), va)
            except StaleObservation as e:
                return self._decision("block", "actions", "stale_observation", str(e), va)
        else:
            if isinstance(action, dict):
                kind, args = action.get("kind"), action.get("args") or {}
            else:
                kind, args = getattr(action, "kind", None), getattr(action, "args", None) or {}
            try:
                sig = action_signature(kind, args or {})
            except Exception:
                sig = f"{kind}:unsigned"
            va = ValidatedAction(kind, dict(args or {}), sig)
        va = dc_replace(va, signature=bind_target_signature(va.signature, target))
        kind, args = va.kind, va.args

        # --- denylist (optional, the worker's own) and the page we are already on
        if target.url and self.denylist.check_url(target.url).denied:
            return self._decision("block", "denylist", "current_page_denied", self.denylist.check_url(target.url).reason, va)
        if kind == "goto":
            d = self.denylist.check_url(args["url"])
            if d.denied:
                return self._decision("block", "denylist", "navigation_denied", d.reason, va)

        # --- layer 8: protected settings
        if cfg.settings:
            if kind == "goto":
                s = self.settings.check_navigation(args["url"])
                if not s.allowed:
                    return self._decision("block", "settings", "protected_navigation", s.reason, va)
            s = self.settings.check_target(label=target.label or args.get("label"), role=target.role, url=target.url, app=target.app)
            if not s.allowed:
                return self._decision("block", "settings", "protected_target", s.reason, va)

        approved = False
        if approved_queue_id:
            chk = self.queue.try_consume_approval(approved_queue_id, va.signature, run_id=self._run)
            approved = chk.ok
            if chk.code == "expired":
                self._approval_note = chk.reason  # the new queue item and the decision say why the worker is being asked again

        # --- layer 4: action-class gate
        g = gate(kind, args, self._ctx(), target, enabled=cfg.gates)
        if g.verdict == "block":
            return self._decision("block", "gates", "gate_block", g.reason, va)
        if g.verdict == "needs_human" and not approved:
            return self._raise_for_human("gates", f"class_{g.top.value if g.top else 'unknown'}", g.reason, va, target,
                                         g.risk_class, g.queue_kind)

        # --- layer 5: data-flow rules
        if cfg.dataflow:
            fd = None
            if kind in ("type", "fill") and ("text" in args or "value" in args):
                fd = self.dataflow.check_text_sink(args.get("text", args.get("value", "")), target.url)
            elif kind == "goto":
                fd = self.dataflow.check_navigation(args["url"])
            if fd is not None and fd.verdict != "allow" and not approved:
                return self._raise_for_human("dataflow", "tainted_data_unrecorded_site", "; ".join(fd.reasons[:2]), va,
                                             target, "outward", "outward_step")

        # --- layer 7: stuck loops, then goal drift (cheap model check last)
        if cfg.drift:
            st = self.stuck.check()
            if st is not None and not approved:
                self.stuck.reset()
                self._log("stuck_loop", "paused", st.code())
                return self._raise_for_human("drift", st.code(), "the same actions are repeating; the run is paused",
                                             va, target, "normal", "injection_pause")
            on_recorded_site = kind == "goto" and self.dataflow.is_recorded(args.get("url"))
            if kind not in _BENIGN_FOR_DRIFT and not approved and not on_recorded_site:
                # Only the CHECK is retried when it fails to run (drift.py): the action in hand is authorised once, below, or not at all.
                v = self.drift.check(self.goal, describe_step(kind, args, label=target.label or args.get("label"),
                                                              host=host_key(target.url or args.get("url"))), self._recent,
                                     should_stop=is_killed)
                if v.error_class:                  # at least one try failed to run: say so, with the class (a token) and the count, never text
                    self._log("drift_check", "recovered" if v.source == "model" else "failed", None,
                              attempts=v.attempts, error_class=v.error_class)
                if not v.on_goal:
                    unavailable = v.source == "unavailable"
                    self._log("drift_pause", "paused", f"drift:{v.source}",
                              **({"check_error": v.error_class, "attempts": v.attempts} if unavailable else {}))
                    dec = self._raise_for_human("drift", f"off_goal_{v.source}", v.reason or "step does not serve the goal",
                                                va, target, "normal", "injection_pause")
                    if unavailable:
                        dec.check_error, dec.check_attempts = v.error_class, v.attempts
                    return dec

        # --- allowed
        if cfg.actions:
            self.budget.tick()
        self._recent.append(f"{kind} {safe_label(target.label or '', 40)}".strip())
        self._log("step", "allowed" + ("_approved" if approved else ""), f"{kind}", actor="agent", step=self.budget.steps)
        return StepDecision("allow", [], [], None, None, va)

    # ------------------------------------------------------------------ after the step
    def record_result(self, action: ValidatedAction, ok: bool) -> None:
        self.stuck.record(action.signature)
        if not ok:
            self._log("step", "failed", action.kind, actor="agent")

    def authorise_launch(self, app_name: str) -> StepDecision:
        """Before opening an application (desktop tier)."""
        if is_killed():
            return self._decision("block", "kill", "kill_flag", "the kill switch is set", None)
        d = self.denylist.check_app(app_name)
        if d.denied:
            return self._decision("block", "denylist", "app_denied", d.reason, None)
        s = self.settings.check_target(app=app_name)
        if self.config.settings and not s.allowed:
            return self._decision("block", "settings", "protected_app", s.reason, None)
        return StepDecision("allow")

    def resume(self, queue_id: str) -> bool:
        """Clear a detector pause once the worker has approved the pause item. Returns True if resumed."""
        item = self.queue.get(queue_id)
        if item and item["status"] == "approved" and item["kind"] == "injection_pause":
            self.paused = False
            self._pause_queue_id = None
            self.stuck.reset()
            self._log("injection_pause", "resumed_by_worker")
            return True
        return False
