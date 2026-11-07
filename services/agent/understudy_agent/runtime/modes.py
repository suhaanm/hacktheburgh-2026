"""Foreground and nightly modes for agent runs (BGA-2, BGA-3). Both write queue items and audit lines; neither writes content.

FOREGROUND: the worker keeps working. Children run under supervisors that share the worker's `HumanInputSignal`, so the
first input cancels every child within a watchdog tick (the run becomes `yielded`, children keep their state), and the
run resumes by itself once the worker has been quiet for `quiet_s`. Results are held back until a natural break: the
worker has been quiet for `break_s` (the proactive layer can use the same test); each finished run is reported once.

NIGHTLY: the same decision flow as `offhours.OffHoursRunner.tick`, with the same pieces, for agent runs: the routine's
consent file must allow an unattended run (`handoff_io.consent_allows`: mode unattended, rung A2 or A3), the kill flag
must be clear, the screen must be unlocked and awake, and the engine's start-or-wait rule (`/offhours/decide`, the
presence forecast) must say go. Keep-awake is held only while the run is active, a presence watcher turns the worker's
return into a human-input signal (the run yields inside a second), and the audit lines use the same `offhours` kind and
codes, so the existing morning report lists these runs too. `agent_morning_report` adds the children and their outcomes.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..audit import AuditLog
from ..handoff_io import consent_allows, read_consent
from ..models.port import ModelPort
from ..offhours import REASONS, KeepAwake, PresenceWatcher, ScreenState, StartResult
from ..queue import ApprovalQueue
from ..security.killflag import is_killed
from ..supervisor import HumanInputSignal
from .run import AgentRun, persisted_runs, register, routine_id_for


def _report_of(run: AgentRun) -> dict[str, Any]:
    d = run.to_dict(detail=True)
    res = d.get("result", {})
    return {"run_id": run.run_id, "kind": run.kind, "mode": run.mode, "state": run.state,
            "verified": res.get("verified", 0), "total": res.get("total", 0),
            "children": [{"id": c["id"], "role": c["role"], "state": c["state"], "verified": c.get("verified", False)}
                         for c in d["children"]],
            "artifacts": [{"name": a["name"], "kind": a["kind"], "path_ref": a["path_ref"]} for a in d.get("artifacts", [])],
            "queue_ids": res.get("queue_ids", [])}


class ForegroundCoordinator:
    def __init__(self, human: HumanInputSignal, *, audit: AuditLog | None = None, queue: ApprovalQueue | None = None,
                 quiet_s: float = 5.0, break_s: float = 3.0, port: ModelPort | None = None) -> None:
        self.human, self.quiet_s, self.break_s, self.port = human, quiet_s, break_s, port
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.runs: list[AgentRun] = []
        self._reported: set[str] = set()
        self._lock = threading.Lock()

    def spawn(self, kind: str, params: dict[str, Any] | None = None, **kw: Any) -> AgentRun:
        run = AgentRun(kind=kind, params=params, mode="foreground", human=self.human, audit=self.audit, queue=self.queue,
                       resume_quiet_s=self.quiet_s, port=kw.pop("port", self.port), **kw)
        with self._lock:
            self.runs.append(run)
        register(run).start()
        return run

    def at_natural_break(self) -> bool:
        return self.human.quiet_for(self.break_s)

    def pop_reports(self) -> list[dict[str, Any]]:
        """Reports of runs that finished, handed over once, and only at a natural break (the worker has gone quiet)."""
        if not self.at_natural_break():
            return []
        out = []
        with self._lock:
            runs = list(self.runs)
        for r in runs:
            if r.finished and r.run_id not in self._reported:
                self._reported.add(r.run_id)
                rep = _report_of(r)
                self.audit.append("agent", "agent_report", routine=r.routine_id, run_id=r.run_id, outcome=r.state,
                                  note_code="natural_break", meta={"verified": rep["verified"], "total": rep["total"]})
                out.append(rep)
        return out


class NightlyRunner:
    """One poll: decide, and start a nightly agent run only if consent, the kill flag, the screen and the presence rule allow."""

    def __init__(self, kind: str, *, engine: Any, screen: ScreenState | None, keepawake: KeepAwake, human: HumanInputSignal,
                 audit: AuditLog | None = None, queue: ApprovalQueue | None = None, root: Path | None = None,
                 poll_s: float = 0.2, port: ModelPort | None = None, quiet_s: float = 30.0) -> None:
        self.kind, self.engine, self.screen, self.keepawake, self.human = kind, engine, screen, keepawake, human
        self.audit = audit or AuditLog()
        self.queue = queue or ApprovalQueue(audit=self.audit)
        self.root, self.poll_s, self.port, self.quiet_s = root, poll_s, port, quiet_s
        self.routine_id = routine_id_for(kind)
        self._watcher: PresenceWatcher | None = None
        self._finalizer: threading.Thread | None = None
        self.run: AgentRun | None = None
        self.last: StartResult | None = None

    def _refuse(self, code: str, decision: dict[str, Any] | None = None) -> StartResult:
        self.audit.append("agent", "offhours", routine=self.routine_id, outcome="refused", note_code=code)
        self.last = StartResult(False, code, REASONS[code], decision)
        return self.last

    def tick(self, params: dict[str, Any] | None = None, *, person: str, d_min: float, gain: float, loss: float,
             now: str | None = None) -> StartResult:
        if self._finalizer is not None and self._finalizer.is_alive():
            return self._refuse("already_running")
        ok, _ = consent_allows(read_consent(self.routine_id, self.root), "unattended")
        if not ok:
            return self._refuse("consent")
        if is_killed():
            return self._refuse("kill")
        if self.screen is None:
            return self._refuse("screen_unknown")
        try:
            locked, asleep = self.screen.locked(), self.screen.asleep()
        except Exception:  # noqa: BLE001
            return self._refuse("screen_unknown")
        if asleep:
            return self._refuse("screen_asleep")
        if locked:
            return self._refuse("screen_locked")
        try:
            dec = self.engine.offhours_decide(person=person, d_min=d_min, gain=gain, loss=loss, screen="unlocked", now=now)
        except Exception:  # noqa: BLE001 - an unreachable presence service is a refusal, never a start
            return self._refuse("engine_unreachable")
        if not dec.get("go"):
            return self._refuse("engine_wait", dec)
        self.keepawake.start()
        self._watcher = PresenceWatcher(self.screen, self.human, poll_s=self.poll_s)
        self._watcher.start()
        t0 = time.time()
        try:
            run = AgentRun(kind=self.kind, params=params, mode="nightly", human=self.human, audit=self.audit, queue=self.queue,
                           resume_quiet_s=self.quiet_s, port=self.port, person=person)
            register(run).start()
        except Exception:
            self._cleanup()
            raise
        self.run = run
        self.audit.append("agent", "offhours", routine=self.routine_id, run_id=run.run_id, outcome="started", note_code="go",
                          meta={"survival": float(dec.get("survival", 0)), "d_min": d_min})

        def finish() -> None:
            run.wait()
            minutes = round((time.time() - t0) / 60, 3)
            self._cleanup()
            self.audit.append("agent", "offhours", routine=self.routine_id, run_id=run.run_id, outcome=run.state,
                              note_code="ended", meta={"minutes": minutes})

        self._finalizer = threading.Thread(target=finish, daemon=True, name="nightly-agent-finalizer")
        self._finalizer.start()
        self.last = StartResult(True, "go", "Started: the worker is away and the window is long enough.", dec, None, run.run_id)
        return self.last

    def _cleanup(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self.keepawake.stop()

    def join(self, timeout: float = 60.0) -> None:
        if self._finalizer is not None:
            self._finalizer.join(timeout)


# ---------------------------------------------------------------------------------------------- the morning report
def _iso_ge(a: str, b: str | None) -> bool:
    return b is None or str(a) >= str(b)


def agent_morning_report(audit: AuditLog, queue: ApprovalQueue | None = None, since: str | None = None) -> dict[str, Any]:
    """BGA-3: which agent runs happened, with every child and its outcome, what is queued for approval, and what was refused.
    Built from the run records and the redacted audit log; no file text anywhere in it."""
    runs = []
    for d in persisted_runs():
        if not _iso_ge(d.get("started", ""), since):
            continue
        res = d.get("result", {})
        runs.append({"run_id": d["run_id"], "kind": d["kind"], "mode": d["mode"], "state": d["state"], "started": d["started"],
                     "verified": res.get("verified", 0), "total": res.get("total", 0),
                     "children": [{"id": c["id"], "role": c["role"], "state": c["state"], "verified": c.get("verified", False)}
                                  for c in d.get("children", [])],
                     "queue_ids": res.get("queue_ids", [])})
    t0 = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else datetime.fromtimestamp(0, timezone.utc)
    refused = []
    for ln in audit.read(100000):
        if str(ln.get("routine", "")).startswith("agent-") and ln["kind"] == "offhours" and ln.get("outcome") == "refused":
            if datetime.fromisoformat(str(ln["t"]).replace("Z", "+00:00")) >= t0:
                refused.append({"routine": ln["routine"], "at": ln["t"], "code": ln.get("note"),
                                "reason": REASONS.get(str(ln.get("note")), "refused")})
    pending = [i["id"] for i in (queue.list("pending") if queue is not None else []) if str(i.get("routine_id", "")).startswith("agent-")]
    n_ver = sum(r["verified"] for r in runs)
    n_tot = sum(r["total"] for r in runs)
    summary = (f"{len(runs)} agent run{'s' if len(runs) != 1 else ''}: {n_ver} of {n_tot} children verified by code; "
               f"{len(pending)} item{'s' if len(pending) != 1 else ''} waiting for you; {len(refused)} start{'s' if len(refused) != 1 else ''} refused.")
    return {"since": since, "runs": runs, "queued": pending, "refused": refused, "summary": summary}
