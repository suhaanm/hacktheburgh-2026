"""Orchestrator (AGT-1, AGT-4, AGT-5): one household in, three calculators in parallel, verify, critique,
reconcile, case note, STOP BEFORE SUBMIT.

    plan (model proposes, code validates)  ->  3 navigators in parallel, one browser context each
      -> verifier (fresh observation of each result page, quarantined reader, code check)
      -> reconcile (code) -> critic (expert policy, code) -> scribe (4th context saves the note DRAFT)
      -> completion check (code decides) -> approval gate (the real gate, a queue item) -> evidence bundle

The model proposes, code decides: reconciliation, the critic, completion and the gate are plain code.
Nothing here ever clicks a submit button; the only path to it is an approved queue item (see `finalize`).
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audit import AuditLog
from .completion import (
    NOTE_ID_RE, ClaimLedger, CompletionResult, ResultFields, check_completion, validate_result_fields,
)
from .models.port import ModelPort
from .navigator import CalculatorJob, CaseNoteJob, NavResult, Navigator, RESULT_SCHEMA
from .queue import ApprovalQueue, save_screenshot
from .sandbox_sites.households import Household, as_household
from .sandbox_sites.oracle import TOLERANCE_GBP, cliff_flags
from .sandbox_sites.specs import CASENOTE_PATH, SITE_IDS, SITES, site_base_urls
from .security.actions import validate_action
from .security.config import SecurityConfig
from .security.dataflow import host_key
from .security.denylist import Denylist
from .security.gates import TargetInfo
from .security.pipeline import bind_target_signature
from .supervisor import data_dir
from .tiers.base import GateStop, InjectionStop, StepEvent, TierError
from .tiers.browser import BrowserHost
from .tiers.observe import observe
from .tiers.safety import Guard

PLAN_SCHEMA: dict[str, Any] = {
    "title": "benefits_plan",
    "type": "object",
    "properties": {
        "case_summary": {"type": "string", "maxLength": 200},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string", "maxLength": 20}, "site": {"type": "string", "maxLength": 20},
            "action": {"type": "string", "maxLength": 40}, "goal": {"type": "string", "maxLength": 160}},
            "required": ["id", "site", "action", "goal"]}},
        "stop_before": {"type": "array", "items": {"type": "string", "maxLength": 20}},
    },
    "required": ["case_summary", "steps", "stop_before"],
}
SITE_ALIASES = {"calc-a": "a", "calc-b": "b", "calc-c": "c", "a": "a", "b": "b", "c": "c"}
SUBMIT_LABEL = "Submit to claimant record"
SUBMIT_SELECTOR = "#submit-note"


# ----------------------------------------------------------------------------- expert policy (code)
@dataclass
class Check:
    id: str
    required: bool = True
    critical: bool = False
    after: tuple[str, ...] = ()


def default_checks() -> list[Check]:
    c = [Check("read_case")]
    for s in SITE_IDS:
        c.append(Check(f"calc_{s}", after=("read_case",)))
    for s in SITE_IDS:
        c.append(Check(f"cliff_{s}", critical=True, after=(f"calc_{s}",)))
    c.append(Check("reconcile", critical=True, after=tuple(f"calc_{s}" for s in SITE_IDS) + tuple(f"cliff_{s}" for s in SITE_IDS)))
    c.append(Check("write_note", after=("reconcile",)))
    c.append(Check("verify_note", required=False, after=("write_note",)))
    return c


def load_expert_checks() -> list[Check]:
    """The pack's expert policy if present (platform track owns it), else the built-in copy of the same shape."""
    try:
        import yaml

        from .supervisor import repo_root

        p = repo_root() / "packages" / "packs" / "benefits-processor" / "expert_steps.yaml"
        if p.exists():
            doc = yaml.safe_load(p.read_text())
            return [Check(c["id"], bool(c.get("required", True)), bool(c.get("critical", False)),
                          tuple(c.get("after", []))) for c in doc["checks"]]
    except Exception:  # noqa: BLE001 - a malformed pack must not stop a run
        pass
    return default_checks()


@dataclass
class Finding:
    severity: str   # blocker | warning
    check: str
    text: str


@dataclass
class CriticReport:
    ok: bool
    findings: list[Finding] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "findings": [f.__dict__ for f in self.findings]}


def critic(checks: list[Check], done: dict[str, int], *, recon: "Reconciliation | None", flags: list[str],
           note_text: str | None, sites_disagree: bool) -> CriticReport:
    """Compare the evidence with the expert policy. Code, not a model."""
    out: list[Finding] = []
    for c in checks:
        if c.id not in done:
            if c.required:
                out.append(Finding("blocker" if c.critical or c.id.startswith("calc_") else "warning", c.id,
                                   f"expert step {c.id!r} was not done"))
            continue
        for pre in c.after:
            if pre in done and done[pre] > done[c.id]:
                out.append(Finding("blocker", c.id, f"{c.id!r} happened before its prerequisite {pre!r}"))
    if recon is not None and sites_disagree and recon.status == "agree":
        out.append(Finding("blocker", "reconcile", "the calculators disagree but the reconciliation says they agree"))
    if recon is not None and recon.status == "discrepancy" and note_text is not None and "discrepancy" not in note_text.lower():
        out.append(Finding("blocker", "write_note", "the note does not say the calculators disagree"))
    if flags and note_text is not None and "cliff" not in note_text.lower():
        out.append(Finding("blocker", "write_note", "the household is near a cliff edge but the note does not mention it"))
    return CriticReport(ok=not any(f.severity == "blocker" for f in out), findings=out)


# ----------------------------------------------------------------------------- reconcile and note (code)
@dataclass
class Reconciliation:
    status: str                      # agree | discrepancy
    value: float                     # median of the three monthly figures
    spread: float
    outliers: list[str]
    eligible_values: list[bool]
    needs_review: bool

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def reconcile(results: dict[str, ResultFields], tolerance: float = TOLERANCE_GBP) -> Reconciliation:
    amounts = {s: r.amount for s, r in results.items()}
    elig = [r.eligible for r in results.values()]
    spread = max(amounts.values()) - min(amounts.values())
    med = statistics.median(amounts.values())
    agree = spread <= tolerance and len(set(elig)) == 1
    outliers = [] if agree else sorted(s for s, v in amounts.items() if abs(v - med) > tolerance)
    return Reconciliation("agree" if agree else "discrepancy", round(med, 2), round(spread, 2), outliers, elig,
                          not agree)


def compose_note(h: Household, results: dict[str, ResultFields], recon: Reconciliation, flags: list[str],
                 cliff_done: dict[str, bool]) -> str:
    names = {"a": "GovCalc", "b": "Quick Estimator", "c": "EntitledTo"}
    parts = [f"Entitlement check for {h.case_ref} ({h.label}, synthetic)."]
    for s in SITE_IDS:
        r = results[s]
        parts.append(f"{names[s]}: {r.amount_text} {r.status_text} {r.ref}.")
    if recon.status == "agree":
        parts.append(f"Reconciliation: the three calculators agree (spread {recon.spread:.2f}). "
                     f"Monthly figure {recon.value:.2f}.")
    else:
        who = ", ".join(names[s] for s in recon.outliers) or "none singled out"
        parts.append(f"Reconciliation: discrepancy between calculators (spread {recon.spread:.2f}); outlier: {who}. "
                     f"Median monthly figure {recon.value:.2f}. Needs review before any decision.")
    n_cliff = sum(1 for v in cliff_done.values() if v)
    parts.append(f"Cliff checks done on {n_cliff} of 3 calculators."
                 + (f" Near an edge: {', '.join(flags)}." if flags else " Nothing near an edge."))
    parts.append("Stopped before submit: the note is a draft awaiting approval.")
    return " ".join(parts)


def run_async(coro: Any) -> Any:
    """asyncio.run for a worker thread. A stop cancels Playwright calls mid-flight; the 'Task was cancelled' futures
    that leaves behind are expected, so they are not printed as errors."""
    loop = asyncio.new_event_loop()

    def handler(lp: Any, ctx: dict[str, Any]) -> None:
        exc = ctx.get("exception")
        if exc is not None and "Task was cancelled" in str(exc):
            return
        lp.default_exception_handler(ctx)

    loop.set_exception_handler(handler)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()


# ----------------------------------------------------------------------------- the run
@dataclass
class RunOptions:
    mode: str = "mock"                        # mock | live (model port); "cached" is handled by the server
    navigators: int = 3
    query: dict[str, str] = field(default_factory=dict)   # per-site url switches, e.g. {"b": "?layout=v2"}
    security: SecurityConfig | None = None
    use_tier1: bool = True
    allow_tier3: bool = False
    max_actions: int = 150                     # hard cap on model-driven actions per navigator; the real limit is progress
    deadline_s: float = 300.0
    routine_id: str | None = None
    opted_in: frozenset[Any] = frozenset()
    denylist: Denylist | None = None
    screenshots: bool = True
    bundles: dict[str, dict[str, Any]] | None = None   # compiled routine bundles by site; None = built-in tier-1 bundles
    unattended: bool = False                            # the worker is away: the gate is stricter about unreadable clicks
    rung: str = "A0"                                    # autonomy rung from the routine's consent
    page_state: bool = False                            # tier 2: the quarantined reader tells the planner the page KIND each step
    start_tier: int = 1                                 # 3: computer use from the first step (tiers 1 and 2 off)
    t3_max_steps: int = 200                             # hard cap on computer-use steps per navigator
    stall_limit: int = 12                               # steps with no visible progress before a loop gives up
    pause: Any = None                                   # a PauseGate shared by every navigator (step-level pause and resume)


@dataclass
class RunResult:
    run_id: str
    state: str                                # done | failed | paused | stopped
    reason: str = ""
    household_id: str = ""
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    reconciliation: dict[str, Any] | None = None
    critic: dict[str, Any] | None = None
    completion: dict[str, Any] = field(default_factory=lambda: {"ok": False, "missing": ["not finished"]})
    note_id: str | None = None
    note_text: str | None = None
    awaiting_approval: bool = False
    queue_id: str | None = None
    queue_ids: list[str] = field(default_factory=list)
    false_claims: int = 0
    cliff_checked: dict[str, bool] = field(default_factory=dict)
    tier_log: list[dict[str, Any]] = field(default_factory=list)
    expert_done: dict[str, int] = field(default_factory=dict)
    evidence_dir: str | None = None
    elapsed_s: float = 0.0
    navigators: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class BenefitsRun:
    def __init__(self, run_id: str, household: Household | dict[str, Any], *, model: ModelPort,
                 base_urls: dict[str, str] | None = None, queue: ApprovalQueue | None = None,
                 audit: AuditLog | None = None, options: RunOptions | None = None,
                 is_current: Callable[[], bool] = lambda: True,
                 on_event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.run_id = run_id
        self.h = as_household(household)
        self.model = model
        self.base_urls = base_urls or site_base_urls()
        self.opt = options or RunOptions()
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.is_current = is_current
        self.on_event = on_event
        self.ledger = ClaimLedger()
        self.events: list[dict[str, Any]] = []
        self.navigator_objs: dict[str, Any] = {}
        self.nav_state: dict[str, dict[str, Any]] = {}
        self.result = RunResult(run_id=run_id, state="running", household_id=self.h.id)
        self._seq = 0
        self.done: dict[str, int] = {}
        self._guards: list[Guard] = []
        self.denylist = self.opt.denylist if self.opt.denylist is not None else Denylist.load()
        hosts = {host_key(u) for u in self.base_urls.values()}
        self._hosts = frozenset(h for h in hosts if h)

    # ------------------------------------------------------------------ events
    def _emit_raw(self, ev: dict[str, Any]) -> None:
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)

    def emit_step(self, ev: StepEvent) -> None:
        d = ev.as_dict()
        d["event"] = "step"
        st = self.nav_state.setdefault(ev.navigator, {"id": ev.navigator, "site": "", "step": 0, "tier": ev.tier,
                                                      "state": "running"})
        st.update(step=ev.step, tier=ev.tier)
        self._emit_raw(d)

    def stage(self, name: str, **info: Any) -> None:
        self._emit_raw({"event": "stage", "stage": name, "t": time.time(), **info})

    def _mark(self, check: str) -> None:
        self._seq += 1
        self.done[check] = self._seq

    def _guard(self, nav_id: str, goal: str) -> Guard:
        g = Guard(self.model, run_id=self.run_id, routine_id=self.opt.routine_id, config=self.opt.security,
                  audit=self.audit, queue=self.queue, mode="compiled", opted_in=self.opt.opted_in,
                  recorded_hosts=self._hosts, goal=goal, denylist=self.denylist, unattended=self.opt.unattended,
                  rung=self.opt.rung)
        self._guards.append(g)
        return g

    # ------------------------------------------------------------------ stage 1: plan
    def plan(self) -> list[dict[str, Any]]:
        """The model proposes a task graph; code checks it covers the three calculators and the note, else uses
        the built-in graph. The graph decides nothing about safety."""
        builtin = [{"id": f"n{s}", "site": s, "action": "enter_household", "goal": f"{SITES[s].name}"} for s in SITE_IDS]
        builtin.append({"id": "scribe", "site": "casenote", "action": "reconcile_and_write_note", "goal": "case note"})
        try:
            msgs = [{"role": "system", "content": "Plan the entitlement check as steps over calc-a, calc-b, calc-c and "
                                                  "case-note. Stop before submit."},
                    {"role": "user", "content": json.dumps({"household": self.h.id, "adults": len(self.h.adults),
                                                            "children": len(self.h.children_ages)})}]
            out = self.model.plan(msgs, PLAN_SCHEMA)
            sites = {SITE_ALIASES.get(str(s.get("site")), str(s.get("site"))) for s in out.get("steps", [])}
            if {"a", "b", "c"} <= sites and "case-note" in {str(s.get("site")) for s in out.get("steps", [])} \
                    and "submit" in [str(x).lower() for x in out.get("stop_before", [])]:
                return [{"id": str(s["id"]), "site": SITE_ALIASES.get(s["site"], "casenote"), "action": str(s["action"]),
                         "goal": str(s["goal"])} for s in out["steps"]]
        except Exception:  # noqa: BLE001 - a bad plan falls back to the built-in graph
            pass
        return builtin

    # ------------------------------------------------------------------ the run
    async def execute(self) -> RunResult:
        t0 = time.monotonic()
        res = self.result
        host: BrowserHost | None = None
        main_task = asyncio.current_task()
        watcher = asyncio.create_task(self._watch(main_task))
        try:
            self._mark("read_case")
            graph = self.plan()
            self.stage("plan", steps=[{"id": s["id"], "site": s["site"]} for s in graph])
            self.audit.append("agent", "run_start", routine=self.opt.routine_id, run_id=self.run_id, outcome="started")
            async with BrowserHost() as host:
                await self._run(host, res)
        except asyncio.CancelledError:
            res.state, res.reason = "stopped", "stopped or cancelled"
        except InjectionStop as exc:
            res.state, res.reason = "paused", f"injection detector paused the run ({exc.codes})"
        except GateStop as exc:
            res.state, res.reason = "paused", f"the action gate stopped the run: {getattr(exc.decision, 'verdict', '')}"
            qid = getattr(exc.decision, "queue_id", None)
            if qid:
                res.queue_ids.append(qid)
        except TierError as exc:
            res.state, res.reason = "failed", str(exc)[:160]
        finally:
            watcher.cancel()
            res.elapsed_s = round(time.monotonic() - t0, 2)
            res.false_claims = self.ledger.false_claims
            res.tier_log = [e for e in self.events if e.get("event") == "step"]
            res.navigators = [dict(v) for v in self.nav_state.values()]
            res.expert_done = dict(self.done)
            self.audit.append("agent", "run_end", routine=self.opt.routine_id, run_id=self.run_id, outcome=res.state)
            self.stage("done", state=res.state, reason=res.reason)
        return res

    async def _watch(self, main: asyncio.Task | None) -> None:
        """Polls the supervisor's generation: a stop or kill cancels this coroutine tree within ~50 ms."""
        while True:
            await asyncio.sleep(0.05)
            if not self.is_current() and main is not None:
                main.cancel()
                return

    async def _run(self, host: BrowserHost, res: RunResult) -> None:
        h = self.h
        flags = cliff_flags(h)
        params = h.params()
        navs: dict[str, Navigator] = {}
        jobs: dict[str, CalculatorJob] = {}
        for s in SITE_IDS[: max(1, self.opt.navigators)]:
            nid = f"nav-{s}"
            job = CalculatorJob(s, params)
            guard = self._guard(nid, job.goal)
            ctx = await host.new_context()
            navs[s] = Navigator(
                nid, context=ctx, model=self.model, guard=guard, base_url=self.base_urls[s],
                emit=self.emit_step, is_current=self.is_current, query=self.opt.query.get(s, ""),
                ledger=self.ledger, use_tier1=self.opt.use_tier1, max_actions=self.opt.max_actions,
                allow_tier3=self.opt.allow_tier3, bundle=(self.opt.bundles or {}).get(s),
                page_state=self.opt.page_state, defer_cliff=True, start_tier=self.opt.start_tier,
                t3_max_steps=self.opt.t3_max_steps, stall_limit=self.opt.stall_limit, pause=self.opt.pause)
            jobs[s] = job
            self.nav_state[nid] = {"id": nid, "site": s, "step": 0, "tier": 1, "state": "running"}
        self.navigator_objs = navs                    # kept for the evaluation harness: per-navigator tier-3 records
        self.stage("navigators_start", n=len(navs))

        tasks = {s: asyncio.create_task(navs[s].run(jobs[s])) for s in navs}
        stop_exc: BaseException | None = None
        nres: dict[str, NavResult] = {}
        pending = set(tasks.values())
        by_task = {t: s for s, t in tasks.items()}
        try:
            while pending:
                finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in finished:
                    s = by_task[t]
                    nid = f"nav-{s}"
                    exc = t.exception() if not t.cancelled() else asyncio.CancelledError()
                    if exc is None:
                        nres[s] = t.result()
                        self.nav_state[nid]["state"] = nres[s].state
                    else:
                        self.nav_state[nid]["state"] = "stopped" if isinstance(exc, asyncio.CancelledError) else "paused"
                        if stop_exc is None:
                            stop_exc = exc
                        # a detector hit, a gate stop or a cancel pauses the WHOLE run: nobody keeps acting
                        for other in pending:
                            other.cancel()
        finally:
            for t in tasks.values():
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        if stop_exc is not None:
            raise stop_exc
        for s, r in nres.items():
            if r.queue_id:
                res.queue_ids.append(r.queue_id)
            if r.state == "done":
                self._mark(f"calc_{s}")
        good = {s: r for s, r in nres.items() if r.state == "done"}
        self.stage("navigators_done", ok=sorted(good))

        # ---- verifier: a fresh observation of each result page, read again, compared with what the navigator said
        results: dict[str, ResultFields] = {}
        for s, r in good.items():
            ok, why = await self._verify(s, r, navs[s])
            if ok:
                results[s] = r.value
            else:
                self.ledger.record(f"verifier:nav-{s}", True, False, why)
                self.nav_state[f"nav-{s}"]["state"] = "unverified"
        self.stage("verified", ok=sorted(results))
        # the cliff check, the expert's signature step, AFTER the verifier has re-read each result
        for s in results:
            await navs[s].cliff_check(jobs[s], good[s])
            res.cliff_checked[s] = good[s].cliff_checked
            if good[s].cliff_checked:
                self._mark(f"cliff_{s}")
            res.results[s] = good[s].value.as_dict() | {"tiers": good[s].tiers_used, "steps": navs[s].steps,
                                                        "cliff": good[s].cliff_text[:400]}
        if self.opt.screenshots:
            for i, (s, r) in enumerate(good.items(), 1):
                await self._shot(r.page, i, f"result_{s}")

        if set(results) != set(SITE_IDS[: max(1, self.opt.navigators)]) or len(results) < 3:
            missing = [f"calculator {s}: no verified result" for s in SITE_IDS if s not in results]
            res.state, res.reason = "failed", "not every calculator produced a verified result"
            res.completion = CompletionResult(False, tuple(missing)).as_dict()
            res.critic = critic(load_expert_checks(), self.done, recon=None, flags=flags, note_text=None,
                                sites_disagree=False).as_dict()
            self._write_evidence(res, results, None)
            return

        # ---- reconcile (code), then the note text, then the critic
        recon = reconcile(results)
        self._mark("reconcile")
        res.reconciliation = recon.as_dict()
        note_text = compose_note(h, results, recon, flags, res.cliff_checked)
        sites_disagree = (max(r.amount for r in results.values()) - min(r.amount for r in results.values())
                          > TOLERANCE_GBP) or len({r.eligible for r in results.values()}) > 1
        report = critic(load_expert_checks(), self.done, recon=recon, flags=flags, note_text=note_text,
                        sites_disagree=sites_disagree)
        res.critic = report.as_dict()
        self.stage("critic", ok=report.ok, findings=len(report.findings))
        if not report.ok:
            res.state, res.reason = "failed", "the critic blocked the note: " + "; ".join(
                f.text for f in report.findings if f.severity == "blocker")[:200]
            item = self.queue.enqueue(kind="batch_result", title=f"Needs review: {h.case_ref}",
                                      summary="The critic found a problem with this entitlement check. Nothing was saved.",
                                      risk_class="normal", run_id=self.run_id, routine_id=self.opt.routine_id,
                                      evidence={"extracted": {"findings": [f.text for f in report.findings]}})
            res.queue_ids.append(item["id"])
            self._write_evidence(res, results, None)
            return

        # ---- scribe: a fourth context saves the note as a DRAFT
        note_params = {
            "case_ref": h.case_ref, "result_a": results["a"].amount_text, "result_b": results["b"].amount_text,
            "result_c": results["c"].amount_text,
            "reconciliation": "agree" if recon.status == "agree" else "discrepancy", "note_text": note_text}
        job = CaseNoteJob(note_params)
        sg = self._guard("scribe", job.goal)
        ctx = await host.new_context()
        scribe = Navigator("scribe", context=ctx, model=self.model, guard=sg, base_url=self.base_urls["a"],
                           emit=self.emit_step, is_current=self.is_current, query=self.opt.query.get("a", ""),
                           ledger=self.ledger, use_tier1=self.opt.use_tier1, max_actions=self.opt.max_actions,
                           allow_tier3=self.opt.allow_tier3, start_tier=self.opt.start_tier,
                           t3_max_steps=self.opt.t3_max_steps, stall_limit=self.opt.stall_limit, pause=self.opt.pause)
        self.nav_state["scribe"] = {"id": "scribe", "site": "casenote", "step": 0, "tier": 1, "state": "running"}
        sres = await scribe.run(job)
        self.nav_state["scribe"]["state"] = sres.state
        if sres.state != "done":
            res.state, res.reason = "failed", "the case note could not be saved"
            if sres.queue_id:
                res.queue_ids.append(sres.queue_id)
            self._write_evidence(res, results, None)
            return
        self._mark("write_note")
        res.note_id, res.note_text = sres.value["note_id"], note_text

        # ---- completion: code decides, on a fresh observation of the final page
        final = await observe(sres.page)
        comp = check_completion(final.text, results, res.note_id)
        res.completion = comp.as_dict()
        if comp.ok:
            self._mark("verify_note")
        else:
            self.ledger.record("orchestrator", True, False, "run claimed done; completion check failed")
        if self.opt.screenshots:
            await self._shot(sres.page, 4, "case_note")

        # ---- approval gate: the real gate, on the real submit button. We never click it.
        res.queue_id = await self._gate(sg, sres.page, final, res, results, recon)
        res.awaiting_approval = res.queue_id is not None
        res.state = "done" if comp.ok else "failed"
        res.reason = "stopped before submit; awaiting approval" if comp.ok else "completion check failed"
        self._write_evidence(res, results, recon)

    # ------------------------------------------------------------------ pieces
    async def _verify(self, site: str, nr: NavResult, nav: Navigator) -> tuple[bool, str]:
        """Fresh observation of the result page, read again by the quarantined reader, compared with the claim."""
        try:
            raw = await nav._read_final(nr.page, nav_job_for(site, self.h))
        except InjectionStop:
            raise
        except Exception as exc:  # noqa: BLE001
            return False, f"re-read failed: {type(exc).__name__}"
        if raw is None:
            return False, "page no longer shows a result"
        again, _ = validate_result_fields(site, raw)
        first: ResultFields = nr.value
        if again is None or (again.amount, again.ref, again.eligible) != (first.amount, first.ref, first.eligible):
            return False, "fresh observation does not match what the navigator reported"
        return True, ""

    async def _shot(self, page: Any, n: int, name: str) -> str | None:
        try:
            png = await page.screenshot(type="png")
            return save_screenshot(self.run_id, n, png)
        except Exception:  # noqa: BLE001
            return None

    async def _gate(self, guard: Guard, page: Any, final: Any, res: RunResult, results: dict[str, ResultFields],
                    recon: Reconciliation) -> str | None:
        """Ask the real gate about the real submit button and attach the evidence bundle to its queue item."""
        va = validate_action("click_element", {"selector": SUBMIT_SELECTOR, "label": SUBMIT_LABEL})
        sig = bind_target_signature(va.signature, TargetInfo(label=SUBMIT_LABEL, role="button"))   # as the pipeline will see it
        shots = [f"data/runs/{self.run_id}/s{i}.png" for i in range(1, 5)] if self.opt.screenshots else []
        evidence = {
            "screenshots": shots,
            "extracted": {s: r.as_dict() for s, r in results.items()} | {"note_id": res.note_id},
            "expected": {"calculators": 3, "cliff_checks": 3, "reconciled_monthly": recon.value,
                         "status": recon.status},
            "diff": [{"site": s, "amount": r.amount, "vs_median": round(r.amount - recon.value, 2)}
                     for s, r in results.items() if abs(r.amount - recon.value) > TOLERANCE_GBP],
            "tier_log": [{"navigator": e["navigator"], "step": e["step"], "tier": e["tier"]} for e in self.events
                         if e.get("event") == "step"][:80],
        }
        item = self.queue.enqueue(
            kind="irreversible_step", title=f"Submit case note {res.note_id}",
            summary=f"{self.h.case_ref}: " + ("calculators agree" if recon.status == "agree" else "calculators DISAGREE")
                    + f", monthly {recon.value:.2f}. The agent stopped before submit.",
            risk_class="irreversible", routine_id=self.opt.routine_id, run_id=self.run_id, evidence=evidence,
            signature=sig, dedupe_key=f"{self.run_id}:{sig}:gates")
        seen = await guard.observe(page, navigator="scribe", tier=1)
        dec = guard.authorise({"kind": "click_element", "args": {"selector": SUBMIT_SELECTOR, "label": SUBMIT_LABEL}}, seen,
                              label=SUBMIT_LABEL, role="button", url=page.url)
        self.stage("gate", verdict=dec.verdict, queue_id=dec.queue_id or item["id"])
        if dec.verdict == "allow":
            # Never expected: the gate would only allow this if the worker had opted the routine in AND the rung
            # allows it. Even then, this track does not click: it queues, so the worker's tap is always required.
            self.audit.append("agent", "gate", routine=self.opt.routine_id, run_id=self.run_id, outcome="unexpected_allow")
        return dec.queue_id or item["id"]

    def _write_evidence(self, res: RunResult, results: dict[str, ResultFields], recon: Reconciliation | None) -> None:
        d = data_dir() / "runs" / self.run_id
        d.mkdir(parents=True, exist_ok=True)
        res.evidence_dir = f"data/runs/{self.run_id}"
        payload = res.as_dict()
        payload["household"] = {"id": self.h.id, "case_ref": self.h.case_ref, "archetype": self.h.archetype,
                                "synthetic": True}
        payload["claims"] = self.ledger.claims
        payload["events"] = self.events[-300:]
        tmp = d / "evidence.json.tmp"
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(d / "evidence.json")
        if res.note_text:
            (d / "case_note.md").write_text(f"# Case note {res.note_id}\n\n{res.note_text}\n", encoding="utf-8")


def nav_job_for(site: str, h: Household) -> CalculatorJob:
    return CalculatorJob(site, h.params())


# ----------------------------------------------------------------------------- after approval
async def finalize(run_id: str, note_id: str, queue_id: str, *, model: ModelPort, base_url_a: str,
                   queue: ApprovalQueue | None = None, audit: AuditLog | None = None) -> dict[str, Any]:
    """Press the submit button for an APPROVED queue item, exactly once. Only the worker's approval, recorded in
    the queue, lets this run; the approval is bound to the action signature and is consumed here."""
    audit = audit or AuditLog()
    queue = queue or ApprovalQueue(audit=audit)
    item = queue.get(queue_id)
    if not item or item["status"] != "approved" or item["run_id"] != run_id:
        return {"submitted": False, "reason": "no approved queue item for this run"}
    guard = Guard(model, run_id=run_id, audit=audit, queue=queue, mode="interactive",
                  recorded_hosts=frozenset({host_key(base_url_a)}), denylist=Denylist.load())
    async with BrowserHost() as host:
        ctx = await host.new_context()
        page = await ctx.new_page()
        await page.goto(f"{base_url_a.rstrip('/')}{CASENOTE_PATH}/{note_id}", wait_until="domcontentloaded")
        seen = await guard.observe(page, navigator="finalize", tier=1)
        dec = guard.authorise({"kind": "click_element", "args": {"selector": SUBMIT_SELECTOR, "label": SUBMIT_LABEL}}, seen,
                              label=SUBMIT_LABEL, role="button", url=page.url, approved_queue_id=queue_id)
        if not dec.allowed:
            return {"submitted": False, "reason": f"gate: {dec.verdict} {','.join(dec.codes)}"}
        await page.locator(SUBMIT_SELECTOR).click()
        guard.record(dec, True)
        text = await page.locator("body").inner_text()
    audit.append("agent", "submit_after_approval", run_id=run_id, outcome="submitted" if "Submitted" in text else "unknown")
    return {"submitted": "Submitted" in text, "reason": "approved by the worker"}
