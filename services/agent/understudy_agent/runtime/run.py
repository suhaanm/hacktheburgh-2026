"""One agent run: a parent that plans, children that work in parallel, results that code checks (BGA-1 to BGA-3).

Built on the existing supervisor: the parent's planning task runs on its own `Supervisor`, and every child runs as a task
on a `Supervisor` of its own (one worker each, so they really run in parallel; a supervisor holds one task at a time).
All of them share the worker's `HumanInputSignal`, so a yield cancels every child within a watchdog tick, and all of them
poll the same kill flag file. `stop()` cancels every supervisor synchronously and revokes every lease; nothing waits on a
model call or on a script (a running script's process group is killed within about 50 ms).

Outcome states: done (every child verified), partial, failed, stopped, killed, timeout, rejected (the plan broke policy),
yielded (waiting for the worker to go quiet; `resume()` continues), paused (a child needs a human).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from clicky_lift import LeaseBook

from ..audit import AuditLog
from ..models.port import ModelPort
from ..queue import ApprovalQueue
from ..security.killflag import is_killed
from ..security.paths import data_dir, repo_root, runs_dir
from ..supervisor import HumanInputSignal, KillSwitchActive, Supervisor, TaskContext
from . import policy
from .child import ChildAgent
from .parent import ParentAgent, PlanRejected
from .results import output_schemas
from .spec import AgentSpec, ChildResult, ChildStatus
from .workspace import Workspace, WorkspaceError

_RUN_ID = re.compile(r"^r_[a-z0-9]{6,12}$")
_STATE_OF_HANDLE: dict[str, ChildStatus] = {"stopped": "stopped", "superseded": "stopped", "killed": "killed",
                                            "timeout": "timeout", "failed": "failed", "yielded": "yielded"}


def routine_id_for(kind: str) -> str:
    """The id agent runs use in the audit log and the consent store (a safe slug)."""
    return "agent-" + kind.replace(".", "-").replace("_", "-")


@dataclass
class ChildRec:
    spec: AgentSpec
    agent: ChildAgent
    ws: Workspace
    sup: Supervisor
    handle: Any = None
    result: ChildResult | None = None
    status: str = "pending"      # pending | running | yielded | <final status>


class AgentRun:
    def __init__(self, *, kind: str, params: dict[str, Any] | None = None, mode: str = "foreground",
                 port: ModelPort | None = None, audit: AuditLog | None = None, queue: ApprovalQueue | None = None,
                 human: HumanInputSignal | None = None, run_id: str | None = None, raw_ok: bool = False,
                 auto_script: bool = True, workspace_base: Path | None = None, keep_workspaces: bool = False,
                 person: str | None = None, resume_quiet_s: float | None = None,
                 on_event: Callable[[dict[str, Any]], None] | None = None,
                 run_seconds: float = policy.RUN_MAX_SECONDS) -> None:
        from . import exemplars  # noqa: F401
        from .exemplars.base import KINDS

        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r}; known: {sorted(KINDS)}")
        if mode not in ("foreground", "nightly"):
            raise ValueError("mode must be foreground or nightly")
        self.kind, self.mode, self.person = kind, mode, person
        self.ex = KINDS[kind]
        self.params_in = dict(params or {})
        self.params: dict[str, Any] = {}
        self.run_id = run_id or "r_" + uuid.uuid4().hex[:8]
        if not _RUN_ID.match(self.run_id):
            raise ValueError("bad run id")
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.human = human or HumanInputSignal()
        self.port = port
        self.raw_ok, self.auto_script = raw_ok, auto_script
        self.workspace_base, self.keep_workspaces = workspace_base, keep_workspaces
        self.resume_quiet_s = resume_quiet_s
        self.on_event = on_event
        self.run_seconds = min(float(run_seconds), policy.RUN_MAX_SECONDS)
        self.routine_id = routine_id_for(kind)
        self.run_dir = runs_dir() / self.run_id
        self.started = time.time()
        self.finished_at: float | None = None
        self.state = "created"
        self.planner = "menu"
        self.plan_errors: list[str] = []
        self.specs: list[AgentSpec] = []
        self.children: dict[str, ChildRec] = {}
        self.results: dict[str, ChildResult] = {}
        self.queue_ids: list[str] = []
        self.parent_spent = {"steps": 0, "seconds": 0.0, "tokens": 0}
        self._lock = threading.RLock()
        self._stop_reason: str | None = None
        self._resume_evt = threading.Event()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._psup: Supervisor | None = None
        self.book = LeaseBook(killed=is_killed, on_event=self._lease_sink, max_active=16)
        self.parent_lease: Any = None

    # ------------------------------------------------------------------------------------------------ plumbing
    def _lease_sink(self, ev: dict[str, Any]) -> None:
        self.audit.append("system", ev["kind"], routine=self.routine_id, run_id=self.run_id, outcome=ev["outcome"],
                          note_code=f"lease:{ev['code']}", meta={"steps": ev["steps"], **({"tool": ev["tool"]} if "tool" in ev else {})})

    def _event(self, kind: str, **d: Any) -> None:
        if self.on_event:
            try:
                self.on_event({"kind": kind, "run_id": self.run_id, **d})
            except Exception:  # noqa: BLE001
                pass

    def _set_state(self, st: str) -> None:
        with self._lock:
            self.state = st
        self._event("state", state=st)
        self._persist()

    def _new_supervisor(self) -> Supervisor:
        return Supervisor(human_input=self.human)

    # ------------------------------------------------------------------------------------------------ lifecycle
    def start(self) -> "AgentRun":
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("already started")
            self._thread = threading.Thread(target=self._drive, daemon=True, name=f"agent-run-{self.run_id}")
        self.audit.append("agent", "run_start", routine=self.routine_id, run_id=self.run_id, outcome="started",
                          note_code=f"mode:{self.mode}", meta={"mode": self.mode})
        self._set_state("planning")
        self._thread.start()
        return self

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    def stop(self, reason: str = "stopped by the worker") -> dict[str, Any]:
        """Synchronous and model-free: every supervisor is cancelled and every lease revoked before this returns."""
        t0 = time.monotonic()
        with self._lock:
            if self._stop_reason is None:
                self._stop_reason = reason
            recs = list(self.children.values())
            psup = self._psup
        self.book.revoke_all("operator_stop")
        if psup is not None:
            psup.stop(reason)
        for r in recs:
            r.sup.stop(reason)
        self._resume_evt.set()
        self.audit.append("human", "agent_stop", routine=self.routine_id, run_id=self.run_id, outcome="requested",
                          note_code="stop")
        return {"stopped": True, "ms": round((time.monotonic() - t0) * 1000, 1)}

    def revoke_child(self, child_id: str) -> bool:
        """End one child at once (the worker's revoke button): its lease is revoked and its task cancelled."""
        with self._lock:
            rec = self.children.get(child_id)
        if rec is None:
            return False
        rec.agent.revoke("operator_revoke")
        rec.sup.stop("child revoked")
        return True

    def resume(self) -> bool:
        """Continue children that yielded to the worker (each gets a fresh lease for what is left of its budget)."""
        with self._lock:
            if self.state != "yielded":
                return False
        self._resume_evt.set()
        return True

    # ------------------------------------------------------------------------------------------------ the driver
    def _stopped(self) -> bool:
        return self._stop_reason is not None

    def _drive(self) -> None:
        try:
            self._drive_inner()
        except Exception as e:  # noqa: BLE001 - a run never dies silently
            self.audit.append("agent", "run_end", routine=self.routine_id, run_id=self.run_id, outcome="failed",
                              note_code=f"error:{type(e).__name__.lower()}"[:60])
            with self._lock:
                self.state = "failed"
                self.plan_errors.append(f"error:{type(e).__name__}")
            self._cleanup()
        finally:
            self.finished_at = time.time()
            self._persist()
            self._done.set()

    def _drive_inner(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.parent_lease = self.book.issue(holder=f"{self.run_id}.parent", tools=set(_all_tools()),
                                            ttl_s=self.run_seconds, max_steps=500)
        port = self.port if self.port is not None else _default_port()
        self.port = port
        # 1. plan (the parent's task, on its own supervisor)
        self._psup = self._new_supervisor()
        holder: dict[str, Any] = {}

        def plan_task(ctx: TaskContext) -> None:
            try:
                self.params = self.ex.prepare(self.params_in, self.run_dir)
            except (ValueError, OSError) as e:
                holder["errors"] = [f"params:{type(e).__name__.lower()}"]
                return
            if self.auto_script:
                from .mockscripts import install_if_mock

                install_if_mock(port, self.kind, self.params)
            ctx.check()
            try:
                holder["specs"] = ParentAgent(self.kind, self.mode, port, self.audit, run_id=self.run_id,
                                              routine_id=self.routine_id).plan()
            except PlanRejected as e:
                holder["errors"] = e.errors

        try:
            h = self._psup.submit(plan_task, name="plan", run_id=self.run_id, deadline_s=120.0)
        except KillSwitchActive:
            return self._finish_run("killed")
        while not h.wait(0.05):
            pass
        if self._stopped() or h.state in ("stopped", "killed", "timeout", "superseded"):
            return self._finish_run("killed" if h.state == "killed" else "timeout" if h.state == "timeout" else "stopped")
        if h.state == "failed":
            self.plan_errors = [f"plan_error:{type(h.error).__name__}"]
            return self._finish_run("failed")
        if "errors" in holder:
            self.plan_errors = holder["errors"]
            return self._finish_run("rejected")
        self.specs = holder["specs"]
        self.audit.append("agent", "run_start", routine=self.routine_id, run_id=self.run_id, outcome="planned",
                          note_code=f"children:{len(self.specs)}", meta={"children": len(self.specs)})

        # 2. build workspaces and children, then start them all
        self._set_state("running")
        self.planner = "raw" if (self.raw_ok and self.mode == "foreground" and not self.params.get("synthetic")
                                 and any(self.params.get(k) for k in self.ex.explicit_files)) else "menu"
        self._build_children()
        if self._stopped():
            return self._finish_run("stopped")
        try:
            for rec in self.children.values():
                self._submit_child(rec)
        except KillSwitchActive:
            self.stop("kill flag present")
        status = self._supervise()
        self._finish_run(status)

    def _build_children(self) -> None:
        from .exemplars.base import MENUS, load_playbook

        schemas = output_schemas()
        for spec in self.specs:
            needs = self.ex.needs(spec.role, self.params)
            ws = Workspace.create(spec.workspace, run_id=self.run_id, child_id=spec.id, base=self.workspace_base,
                                  inputs=list(needs.inputs), repo_source=needs.repo_source,
                                  scratch=tuple(MENUS[spec.role].files.values()))
            agent = ChildAgent(spec, run_id=self.run_id, kind=self.kind, port=self.port, audit=self.audit,  # type: ignore[arg-type]
                               queue=self.queue, ws=ws, params=self.params, output_schema=schemas[spec.output_schema],
                               playbook=load_playbook(spec.playbook), menu=MENUS[spec.role], book=self.book,
                               parent_lease=self.parent_lease, planner=self.planner, routine_id=self.routine_id,
                               unattended=self.mode == "nightly")
            with self._lock:
                self.children[spec.id] = ChildRec(spec, agent, ws, self._new_supervisor())

    def _submit_child(self, rec: ChildRec) -> None:
        left = max(1.0, rec.spec.budget.seconds - rec.agent.clock())
        rec.status = "running"
        rec.handle = rec.sup.submit(rec.agent.run, name=f"child-{rec.spec.id}", run_id=rec.agent.child_run_id,
                                    deadline_s=left + 5.0, yield_on_human=True)

    def _supervise(self) -> str:
        t_end = time.monotonic() + self.run_seconds
        while True:
            if self._stopped():
                break
            recs = list(self.children.values())
            if all(r.handle is not None and r.handle.finished for r in recs):
                yielded = [r for r in recs if r.handle.state == "yielded"]
                if not yielded:
                    break
                self._set_state("yielded")
                self.audit.append("agent", "yielded", routine=self.routine_id, run_id=self.run_id, outcome="yielded",
                                  note_code="human_input", meta={"children": len(yielded)})
                self._event("yielded", children=[r.spec.id for r in yielded])
                while not self._resume_evt.is_set() and not self._stopped():
                    if self.resume_quiet_s is not None and self.human.quiet_for(self.resume_quiet_s) and not is_killed():
                        break
                    time.sleep(0.05)
                self._resume_evt.clear()
                if self._stopped():
                    break
                self._set_state("running")
                try:
                    for r in yielded:
                        r.sup.close()
                        r.sup = self._new_supervisor()
                        self._submit_child(r)
                except KillSwitchActive:
                    self.stop("kill flag present")
                continue
            if time.monotonic() > t_end:
                self.stop("run deadline")
                self._stop_reason = "timeout"
                break
            time.sleep(0.03)
        self._wait_handles(1.0)
        if self._stop_reason == "timeout":
            return "timeout"
        if self._stopped():
            return "stopped"
        if is_killed() or any(r.handle is not None and r.handle.state == "killed" for r in self.children.values()):
            return "killed"
        return "ok"

    def _wait_handles(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        for r in list(self.children.values()):
            if r.handle is not None:
                r.handle.wait(max(0.0, end - time.monotonic()))

    # ------------------------------------------------------------------------------------------------ finishing
    def _child_final_status(self, rec: ChildRec, outcome: str) -> ChildStatus | None:
        """Map the supervisor's verdict on the task to a child status (None = use the child's own status)."""
        h = rec.handle
        if rec.agent.lease is not None and rec.agent.lease.snapshot()["stop_reason"] in ("revoked", "operator_revoke") \
                and rec.agent.status is None:
            return "revoked"
        if h is None:
            return "stopped"
        if h.state == "done":
            return None
        if h.state == "failed":
            return "failed"
        return _STATE_OF_HANDLE.get(h.state, "stopped")

    def _finish_run(self, outcome: str) -> None:
        results: dict[str, ChildResult] = {}
        for cid, rec in self.children.items():
            st = self._child_final_status(rec, outcome)
            if outcome in ("stopped", "killed", "timeout") and st is None and rec.agent.status is None:
                st = "stopped" if outcome == "stopped" else outcome  # type: ignore[assignment]
            reason = f"task_{rec.handle.state}" if rec.handle is not None and st in ("failed",) else ""
            try:
                results[cid] = rec.agent.result(status=st, reason=reason, run_dir=self.run_dir, repo=repo_root())
            except Exception as e:  # noqa: BLE001
                from .spec import ChildResult as CR

                results[cid] = CR(child_id=cid, role=rec.spec.role, status="failed", reason=f"finalise:{type(e).__name__}"[:60])
            rec.result, rec.status = results[cid], results[cid].status
        self.results = results
        for rec in self.children.values():
            rec.agent.revoke("run_finished")
        verified = sum(1 for r in results.values() if r.verified)
        total = len(results)
        if outcome == "ok":
            state = "done" if total and verified == total else "failed" if verified == 0 else "partial"
            if any(r.status == "paused" for r in results.values()) and state != "done":
                state = "paused"
        else:
            state = outcome
        self._write_children_json()
        self._enqueue_results(state, verified, total)
        self.audit.append("agent", "run_end", routine=self.routine_id, run_id=self.run_id, outcome=state,
                          note_code=f"verified:{verified}of{total}", meta={"verified": verified, "total": total})
        self._cleanup()
        self._set_state(state)

    def _cleanup(self) -> None:
        for rec in self.children.values():
            if not self.keep_workspaces:
                try:
                    rec.ws.cleanup()
                except Exception:  # noqa: BLE001
                    pass
            rec.sup.close()
        if self._psup is not None:
            self._psup.close()

    def _write_children_json(self) -> None:
        try:
            d = self.run_dir / "children"
            d.mkdir(parents=True, exist_ok=True)
            for cid, res in self.results.items():
                (d / f"{cid}.json").write_text(res.model_dump_json(indent=1))
        except OSError:
            pass

    def _enqueue_results(self, state: str, verified: int, total: int) -> None:
        """One summary item per run, and one approval item per patch draft. Nothing here applies anything."""
        if total == 0:
            return
        arts = [a.name for r in self.results.values() for a in r.artifacts]
        item = self.queue.enqueue(
            kind="batch_result", title=f"Agent run {self.kind}: {verified} of {total} children verified",
            summary=f"State {state}. The results were checked by code against the source data.", risk_class="normal",
            routine_id=self.routine_id, run_id=self.run_id,
            evidence={"extracted": {"kind": self.kind, "mode": self.mode, "state": state, "verified": verified, "total": total,
                                    "artifacts": arts[:12], "run_ref": f"data/runs/{self.run_id}"}},
            dedupe_key=f"agentrun:{self.run_id}")
        self.queue_ids.append(item["id"])
        for cid, res in self.results.items():
            for a in res.artifacts:
                if a.kind == "patch" and res.verified:
                    pi = self.queue.enqueue(
                        kind="batch_result", title=f"Patch draft ready for review: {res.role}",
                        summary="A draft only. Nothing was applied or pushed; approving records your review.",
                        risk_class="normal", routine_id=self.routine_id, run_id=self.run_id, signature=a.sha256,
                        evidence={"extracted": {"patch_ref": a.path_ref, "sha": a.sha256[:12], "bytes": a.bytes,
                                                "checks_ok": all(c.ok for c in res.checks)}},
                        dedupe_key=f"patch:{self.run_id}:{cid}")
                    self.queue_ids.append(pi["id"])

    # ------------------------------------------------------------------------------------------------ views
    def children_view(self) -> list[dict[str, Any]]:
        out = []
        for cid, rec in self.children.items():
            res = rec.result
            sp = res.spent.model_dump() if res else rec.agent.spent().model_dump()
            out.append({"id": cid, "role": rec.spec.role, "state": res.status if res else rec.status,
                        "budget": {"steps": rec.spec.budget.steps, "seconds": rec.spec.budget.seconds,
                                   "tokens": rec.spec.budget.tokens},
                        "spent": sp, "lease": rec.agent.lease_snapshot(),
                        **({"result_ref": f"data/runs/{self.run_id}/children/{cid}.json"} if res else {}),
                        **({"verified": res.verified} if res else {})})
        return out

    def to_dict(self, detail: bool = False) -> dict[str, Any]:
        spent_secs = round((self.finished_at or time.time()) - self.started, 3)
        d: dict[str, Any] = {
            "run_id": self.run_id, "kind": self.kind, "mode": self.mode, "state": self.state,
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)), "person": self.person,
            "parent": {"id": "p1", "role": "parent", "state": "done" if self.specs or self.plan_errors else self.state,
                       "budget": {"steps": 1, "seconds": self.run_seconds, "tokens": 0},
                       "spent": {"steps": 1 if self.specs or self.plan_errors else 0, "seconds": spent_secs, "tokens": 0}},
            "children": self.children_view(), "planner": self.planner, "plan_errors": self.plan_errors,
        }
        if detail:
            arts = [{"name": a.name, "kind": a.kind, "path_ref": a.path_ref, "child": cid}
                    for cid, r in self.results.items() for a in r.artifacts]
            verified = sum(1 for r in self.results.values() if r.verified)
            d["artifacts"] = arts
            d["result"] = {"verified": verified, "total": len(self.results), "all_verified": bool(self.results) and verified == len(self.results),
                           "children": {cid: r.model_dump() for cid, r in self.results.items()}, "queue_ids": list(self.queue_ids)}
        return d

    def _persist(self) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            p = self.run_dir / "agent_run.json"
            tmp = p.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self.to_dict(detail=True), default=str))
            os.replace(tmp, p)
        except (OSError, ValueError):
            pass


def _all_tools() -> tuple[str, ...]:
    from .spec import TOOL_NAMES

    return TOOL_NAMES


def _default_port() -> ModelPort:
    from ..models import get_model_port, mock_enabled

    if mock_enabled():
        from ..models.mock_provider import MockProvider

        return MockProvider("benefits_clean")      # a fresh one per run, so scripted queues never stack
    return get_model_port()


# ---------------------------------------------------------------------------------------------- the registry
_RUNS: dict[str, AgentRun] = {}
_REG_LOCK = threading.Lock()


def register(run: AgentRun) -> AgentRun:
    with _REG_LOCK:
        _RUNS[run.run_id] = run
    return run


def get_run(run_id: str) -> AgentRun | None:
    with _REG_LOCK:
        return _RUNS.get(run_id)


def live_runs() -> list[AgentRun]:
    with _REG_LOCK:
        return list(_RUNS.values())


def reset_registry() -> None:
    with _REG_LOCK:
        _RUNS.clear()


def persisted_runs() -> list[dict[str, Any]]:
    """Runs recorded on disk (agent_run.json), newest first. Used after a restart and for nightly reports."""
    out = []
    base = runs_dir()
    if not base.is_dir():
        return out
    for p in base.glob("r_*/agent_run.json"):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda d: d.get("started", ""), reverse=True)
