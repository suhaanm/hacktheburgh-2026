"""Shadow mode and background runs (HND-4, HND-5).

Shadow mode: on the next real episode, run the compiled routine in a SEPARATE browser context, compare its result
with what the worker did, and post the code-checked verdict to the engine, which owns the ladder and the Wilson bound.
Nothing is saved or submitted in shadow mode. It does not even start before the worker's consent.

Background runs: the full workflow (calculators, verifier, critic, scribe, approval gate) for an approved routine in
its own browser context, under the supervisor with `yield_on_human=True`: a human-input signal cancels the run within
the watchdog interval (well under a second), a `yielded` audit line is written, and the run can resume once the human
has been quiet for the hold-off period.
"""
from __future__ import annotations

import re

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audit import AuditLog
from .completion import parse_money, validate_result_fields
from .handoff_io import EngineClient, EngineError, consent_allows, read_consent
from .models.port import ModelPort
from .orchestrator import BenefitsRun, RunOptions, run_async
from .queue import ApprovalQueue
from .sandbox_sites.households import Household, as_household
from .sandbox_sites.specs import SITE_IDS, site_base_urls
from .security.denylist import Denylist
from .supervisor import HumanInputSignal, Supervisor, TaskHandle
from .tiers.base import GateStop, InjectionStop, TierError
from .tiers.browser import BrowserHost
from .tiers.dsl import DslRuntime, goto_hosts, run_bundle, to_internal
from .tiers.safety import Guard

MATCH_TOLERANCE = 0.05   # site c converts annual and weekly figures back to monthly: a few pence of rounding


class ConsentRefused(RuntimeError):
    pass


@dataclass
class ShadowOutcome:
    run_id: str
    matched: bool
    diffs: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    event: str | None = None                  # failure | injection when the run itself could not complete
    engine: dict[str, Any] | None = None
    agent: dict[str, float | None] = field(default_factory=dict)


def compare(agent: dict[str, float | None], worker: dict[str, float]) -> tuple[bool, list[dict[str, Any]]]:
    """Code-checked verdict: every site's figure equals the worker's. A missing figure is a mismatch."""
    diffs = []
    for site, w in worker.items():
        a = agent.get(site)
        if a is None or abs(a - float(w)) > MATCH_TOLERANCE:
            diffs.append({"site": site, "agent": a, "worker": float(w)})
    return not diffs, diffs


class ShadowRunner:
    def __init__(self, routine_id: str, bundles: dict[str, dict[str, Any]], *, model: ModelPort,
                 engine: EngineClient | None = None, audit: AuditLog | None = None, queue: ApprovalQueue | None = None,
                 base_urls: dict[str, str] | None = None, root: Path | None = None) -> None:
        self.routine_id, self.bundles, self.model = routine_id, bundles, model
        self.engine = engine
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.base_urls = base_urls or site_base_urls()
        self.root = root

    async def run_episode(self, host: BrowserHost, household: Household | dict[str, Any], worker: dict[str, float], *,
                          run_id: str | None = None, query: dict[str, str] | None = None) -> ShadowOutcome:
        ok, why = consent_allows(read_consent(self.routine_id, self.root), "shadow")
        if not ok:
            self.audit.append("agent", "consent", routine=self.routine_id, outcome="refused", note_code="shadow_no_consent")
            raise ConsentRefused(f"shadow mode did not start: {why}")
        h = as_household(household)
        run_id = run_id or "r_shadow_" + uuid.uuid4().hex[:8]
        self.audit.append("agent", "shadow", routine=self.routine_id, run_id=run_id, outcome="started")
        agent: dict[str, float | None] = {}
        event: str | None = None
        reason = ""
        try:
            for site, bundle in self.bundles.items():
                ctx = await host.new_context()  # a separate context: never the worker's browser
                try:
                    page = await ctx.new_page()
                    guard = Guard(self.model, run_id=run_id, routine_id=self.routine_id, mode="compiled", rung="A1",
                                  audit=self.audit, queue=self.queue, denylist=Denylist.load(),
                                  recorded_hosts=frozenset(goto_hosts(to_internal(bundle))))
                    rt = DslRuntime(page=page, params=h.params(), base_url=self.base_urls.get(site, ""),
                                    query=(query or {}).get(site, ""), navigator=f"shadow-{site}", guard=guard,
                                    stop_before_irreversible=True, pre_timeout_ms=2500, post_timeout_ms=4000)
                    out = (await run_bundle(bundle, rt)).outputs
                finally:
                    await ctx.close()
                fields, _ = validate_result_fields(site, out) if {"amount", "status", "ref"} <= set(out) else (None, [])
                agent[site] = fields.amount if fields else (parse_money(out.get("amount", "")) if out.get("amount") else None)
        except InjectionStop:
            event, reason = "injection", "the detector paused the shadow run"
        except (GateStop, TierError, ValueError) as exc:
            event, reason = "failure", f"{type(exc).__name__} in the compiled routine"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - selectors that no longer match and timeouts are failures, not crashes
            event, reason = "failure", f"{type(exc).__name__} in the compiled routine"
        matched, diffs = (False, []) if event else compare(agent, worker)
        if not event and not matched:
            reason = "figure differs on " + ", ".join(d["site"] for d in diffs)
            self.queue.enqueue(kind="shadow_mismatch", title=f"Shadow mismatch on {self.routine_id}",
                               summary="The compiled routine and the worker disagree. Nothing was saved or submitted.",
                               risk_class="normal", routine_id=self.routine_id, run_id=run_id,
                               evidence={"extracted": {"agent": {k: v for k, v in agent.items()},
                                                       "worker": dict(worker)}, "diff": diffs})
        item: dict[str, Any] = {"run_id": run_id}
        if event:
            item["event"] = event
        else:
            item["matched"] = matched
            if reason:
                item["reason"] = reason[:200]
        out_row = ShadowOutcome(run_id, matched, diffs, reason, event, None, agent)
        if self.engine is not None:
            try:
                out_row.engine = self.engine.post_shadow(self.routine_id, [item])
            except EngineError as exc:
                out_row.engine = {"error": exc.code, "status": exc.status}
        self.audit.append("agent", "shadow", routine=self.routine_id, run_id=run_id,
                          outcome=event or ("clean" if matched else "mismatch"))
        return out_row


# ----------------------------------------------------------------------------- background runs
class BackgroundRunner:
    """Runs the approved routine in its own browser context under the supervisor, and yields to the human."""

    def __init__(self, routine_id: str, *, supervisor: Supervisor, human_input: HumanInputSignal, model: ModelPort,
                 bundles: dict[str, dict[str, Any]] | None = None, base_urls: dict[str, str] | None = None,
                 audit: AuditLog | None = None, queue: ApprovalQueue | None = None, engine: EngineClient | None = None,
                 root: Path | None = None, hold_off_s: float = 3.0, unattended: bool = False,
                 clock: Callable[[], float] = time.time, checkpoint_dir: Path | None = None) -> None:
        self.routine_id, self.sup, self.human, self.model = routine_id, supervisor, human_input, model
        self.bundles, self.base_urls = bundles, base_urls or site_base_urls()
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.engine, self.root, self.hold_off_s, self.unattended = engine, root, hold_off_s, unattended
        self.clock = clock
        self.checkpoint_dir = checkpoint_dir     # set: each run keeps a typed step-level checkpoint here, and a start with a run id
                                                 # that has one RESUMES from it (a yield no longer restarts the household)
        self.last: dict[str, Any] = {}

    def _kind(self) -> str:
        return "unattended" if self.unattended else "background"

    def start(self, household: Household | dict[str, Any], *, run_id: str | None = None,
              query: dict[str, str] | None = None, deadline_s: float = 300.0,
              on_start: Callable[[], None] | None = None, on_finish: Callable[[], None] | None = None) -> TaskHandle:
        """`on_start` / `on_finish` run in the worker thread around the run (the server uses them to hold and release
        the shared sandbox lock for exactly as long as the browser is acting)."""
        ok, why = consent_allows(read_consent(self.routine_id, self.root), self._kind())
        if not ok:
            self.audit.append("agent", "consent", routine=self.routine_id, outcome="refused", note_code=f"{self._kind()}_refused")
            raise ConsentRefused(f"{self._kind()} run refused: {why}")
        h = as_household(household)
        rid = run_id or "r_bg_" + uuid.uuid4().hex[:8]
        consent = read_consent(self.routine_id, self.root)

        def work(ctx: Any) -> dict[str, Any]:
            if on_start:
                on_start()
            try:
                return _work(ctx)
            finally:
                if on_finish:
                    on_finish()

        def _work(ctx: Any) -> dict[str, Any]:
            ck: dict[str, Any] = {}
            if self.checkpoint_dir is not None:
                ck = {"checkpoint_path": Path(self.checkpoint_dir) / (re.sub(r"[^A-Za-z0-9_.-]", "_", rid)[:80] + ".json"), "resume": True}
            opts = RunOptions(denylist=Denylist.load(), routine_id=self.routine_id, bundles=self.bundles,
                              query=dict(query or {}), unattended=self.unattended, rung=consent.rung, **ck)
            run = BenefitsRun(rid, h, model=self.model, base_urls=self.base_urls, queue=self.queue, audit=self.audit,
                              options=opts, is_current=ctx.is_current)
            t0 = self.clock()
            self.audit.append("agent", "offhours" if self.unattended else "run_start", routine=self.routine_id, run_id=rid,
                              outcome="background_started")
            res = run_async(run.execute())
            self.last = res.as_dict()
            if res.state == "stopped":
                ctx.checkpoint({"run_id": rid, "stage": run.events[-1].get("stage", "?") if run.events else "start",
                                "done": sorted(run.done)})
            if res.state == "paused" and "injection" in res.reason and self.engine is not None:
                try:
                    self.engine.post_shadow(self.routine_id, [{"run_id": rid, "event": "injection"}])
                except EngineError:
                    pass
            self.last["minutes"] = round((self.clock() - t0) / 60, 3)
            return self.last

        handle = self.sup.submit(work, name=f"background:{self.routine_id}", run_id=rid, deadline_s=deadline_s,
                                 yield_on_human=True)

        def after() -> None:
            handle.wait()
            if handle.state == "yielded":
                self.audit.append("agent", "yielded", routine=self.routine_id, run_id=rid, outcome="yielded",
                                  note_code="human_input")

        self._after = threading.Thread(target=after, daemon=True, name="background-after")
        self._after.start()
        return handle

    def join_after(self, timeout: float = 2.0) -> None:
        """Wait for the bookkeeping that follows a run (the `yielded` audit line)."""
        t = getattr(self, "_after", None)
        if t is not None:
            t.join(timeout)

    def can_resume(self) -> bool:
        """The human has been quiet for the hold-off period."""
        return self.human.quiet_for(self.hold_off_s)
