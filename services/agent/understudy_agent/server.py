"""Agent service on port 7710 (docs/API_CONTRACT.md "Agent API").

    uv run python -m understudy_agent.server           # serves 7710; starts the sandbox sites if they are not up

One supervisor, one worker: a new run replaces the running one. `POST /run/{id}/stop` and `POST /kill` never
wait for a model call. Mock mode (UNDERSTUDY_MOCK=1 or mode "mock") is deterministic and needs no network.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import golden
from .compile import load_bundles
from .handoff_io import ENGINE_URL, EngineClient, consent_allows, read_consent
from .offhours import morning_report
from .shadow import BackgroundRunner, ConsentRefused, ShadowRunner
from .audit import AuditLog
from .models import get_model_port, mock_enabled
from .orchestrator import BenefitsRun, RunOptions, finalize, run_async
from .queue import ApprovalQueue
from .sandbox_sites.households import Household, as_household, generate_households, get_household
from .sandbox_sites.runner import SandboxCluster
from .sandbox_sites.specs import DEFAULT_PORTS, SITE_IDS, site_base_urls
from .security.killflag import clear_kill, set_kill
from .supervisor import HumanInputSignal, KillSwitchActive, Supervisor, TaskContext
from .tiers.heuristic import HeuristicModelPort

PORT = 7710
TERMINAL_STATES = {"done", "failed", "stopped", "paused"}


class RunIn(BaseModel):
    household_id: str | None = None
    household: dict[str, Any] | None = None
    mode: str = Field("mock", pattern="^(live|cached|mock)$")
    navigators: int = Field(3, ge=1, le=3)
    # additive: url switches per site for demos and red-team runs, e.g. {"b": "?layout=v2", "c": "?variant=injected"}
    switches: dict[str, str] = Field(default_factory=dict)


class RoutineRunIn(BaseModel):
    mode: str = Field("shadow", pattern="^(shadow|approved|background)$")
    household_id: str | None = None
    # shadow mode compares with what the worker did; without it the routine still runs but nothing is compared
    worker_results: dict[str, float] | None = None


@dataclass
class RunRecord:
    run_id: str
    mode: str
    household_id: str
    started: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    handle: Any = None
    run: BenefitsRun | None = None
    result: dict[str, Any] | None = None
    state: str = "running"
    cached: bool = False
    generation: int = 0


def _model_for(mode: str):
    mock = mode in ("mock", "cached") or mock_enabled()
    port = get_model_port(mock=True) if mock else get_model_port()
    return HeuristicModelPort(port) if getattr(port, "name", "") == "mock" else port


def create_app(*, base_urls: dict[str, str] | None = None, autostart_sandbox: bool | None = None,
               supervisor: Supervisor | None = None, queue: ApprovalQueue | None = None,
               audit: AuditLog | None = None) -> FastAPI:
    urls = base_urls or site_base_urls()
    human = (supervisor.human_input if supervisor is not None and supervisor.human_input else HumanInputSignal())
    sup = supervisor or Supervisor(human_input=human)
    if sup.human_input is None:
        sup.attach_human_input(human)
    audit = audit or AuditLog()
    queue = queue or ApprovalQueue(audit=audit)
    runs: dict[str, RunRecord] = {}
    cluster_holder: dict[str, SandboxCluster] = {}
    auto = (base_urls is None) if autostart_sandbox is None else autostart_sandbox

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if auto:
            try:
                httpx.get(urls["a"] + "/healthz", timeout=0.5)
            except Exception:  # noqa: BLE001 - not running: start our own copy on the default ports
                try:
                    cluster_holder["c"] = SandboxCluster().start()
                except Exception:  # noqa: BLE001
                    pass
        yield
        if "c" in cluster_holder:
            cluster_holder["c"].stop()
        sup.close()

    app = FastAPI(title="Understudy agent service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.runs, app.state.supervisor, app.state.queue, app.state.audit = runs, sup, queue, audit

    voice = False
    try:
        from .voice.router import router as voice_router

        app.include_router(voice_router)
        voice = True
    except ImportError:
        pass

    def err(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)

    @app.exception_handler(HTTPException)
    async def _http_err(_, exc: HTTPException) -> JSONResponse:  # contract: plain {"error": {code, message}}
        return err(exc.status_code, "http_error", str(exc.detail))

    def sandbox_up() -> bool:
        try:
            return httpx.get(urls["a"] + "/healthz", timeout=0.5).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ health
    @app.get("/health")
    def health() -> dict[str, Any]:
        sup.kill_flag_set(fresh=True)
        snap = sup.snapshot()
        return {"ok": True, "mock": mock_enabled(), "supervisor": {"generation": snap["generation"], "state": snap["state"]},
                "voice": voice, "sandbox": sandbox_up()}

    # ------------------------------------------------------------------ runs
    def pick_household(body: RunIn) -> Household:
        if body.household:
            return as_household(body.household)
        if body.household_id:
            try:
                return get_household(body.household_id)
            except KeyError:
                raise HTTPException(404, f"unknown household {body.household_id!r}") from None
        return generate_households(1)[0]

    def state_of(rec: RunRecord) -> str:
        if rec.result is not None:
            return rec.result.get("state", "done")
        h = rec.handle
        if h is not None and h.finished:
            return {"killed": "stopped", "stopped": "stopped", "superseded": "stopped", "yielded": "stopped",
                    "timeout": "failed", "failed": "failed"}.get(h.state, "failed")
        return "running"

    def finish(rec: RunRecord, result: dict[str, Any]) -> None:
        rec.result = result
        rec.state = result.get("state", "done")

    @app.post("/run/benefits")
    def run_benefits(body: RunIn) -> dict[str, Any]:
        h = pick_household(body)
        rec = RunRecord(run_id="r_" + os.urandom(4).hex(), mode=body.mode, household_id=h.id)
        runs[rec.run_id] = rec
        if body.mode == "cached":
            gold = golden.load_golden()
            if gold is None:
                runs.pop(rec.run_id, None)
                raise HTTPException(409, "no cached golden run yet; run once in mock mode with ?record=1, "
                                         "or python -m understudy_agent.golden record")
            rec.cached = True

            def work_cached(ctx: TaskContext) -> None:
                out = golden.replay(gold, rec.run_id, emit=rec.events.append, sleep=ctx.sleep, queue=queue)
                if ctx.is_current():
                    finish(rec, out)

            try:
                rec.handle = sup.submit(work_cached, name="benefits-cached", run_id=rec.run_id)
            except KillSwitchActive:
                runs.pop(rec.run_id, None)
                raise HTTPException(423, "the kill switch is set; clear it first") from None
            rec.generation = rec.handle.generation
            return {"run_id": rec.run_id}

        model = _model_for(body.mode)
        opts = RunOptions(mode=body.mode, navigators=body.navigators, query=dict(body.switches))
        run = BenefitsRun(rec.run_id, h, model=model, base_urls=urls, queue=queue, audit=audit, options=opts,
                          on_event=rec.events.append)
        rec.run = run

        def work(ctx: TaskContext) -> None:
            run.is_current = ctx.is_current
            res = run_async(run.execute())
            if ctx.is_current() or res.state == "stopped":
                finish(rec, res.as_dict())

        try:
            rec.handle = sup.submit(work, name="benefits", run_id=rec.run_id, deadline_s=opts.deadline_s)
        except KillSwitchActive:
            runs.pop(rec.run_id, None)
            raise HTTPException(423, "the kill switch is set; clear it first") from None
        rec.generation = rec.handle.generation
        return {"run_id": rec.run_id}

    def get_rec(run_id: str) -> RunRecord:
        rec = runs.get(run_id)
        if rec is None:
            raise HTTPException(404, f"no run {run_id!r}")
        return rec

    @app.get("/run/{run_id}")
    def run_status(run_id: str) -> dict[str, Any]:
        rec = get_rec(run_id)
        st = state_of(rec)
        res = rec.result or {}
        navs = (rec.run.nav_state.values() if rec.run else []) or res.get("navigators", [])
        out = {
            "run_id": run_id, "state": st, "generation": rec.generation,
            "navigators": [dict(n) for n in navs],
            "completion": res.get("completion", {"ok": False, "missing": []}),
            "false_claims": (rec.run.ledger.false_claims if rec.run else res.get("false_claims", 0)),
            # additive fields
            "mode": rec.mode, "cached": rec.cached, "household_id": rec.household_id,
            "awaiting_approval": bool(res.get("awaiting_approval")), "queue_id": res.get("queue_id"),
            "note_id": res.get("note_id"), "reason": res.get("reason", ""), "reconciliation": res.get("reconciliation"),
            "critic": res.get("critic"), "evidence_dir": res.get("evidence_dir"),
        }
        if st == "running" and rec.handle is not None and rec.handle.finished and rec.result is None:
            out["state"] = "failed"
        return out

    @app.get("/run/{run_id}/result")
    def run_result(run_id: str) -> dict[str, Any]:
        rec = get_rec(run_id)
        if rec.result is None:
            raise HTTPException(409, "the run has not finished")
        return rec.result

    @app.get("/run/{run_id}/stream")
    async def run_stream(run_id: str) -> StreamingResponse:
        rec = get_rec(run_id)

        async def gen() -> AsyncIterator[str]:
            i = 0
            idle = 0.0
            while True:
                while i < len(rec.events):
                    e = rec.events[i]
                    i += 1
                    kind = e.get("event", "step")
                    payload = {k: v for k, v in e.items() if k != "event"}
                    if kind == "step":
                        payload = {"navigator": e.get("navigator"), "step": e.get("step"), "tier": e.get("tier"),
                                   "action": e.get("action"), "ok": e.get("ok"), **({"cached": True} if e.get("cached") else {})}
                    yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
                    idle = 0.0
                if state_of(rec) in TERMINAL_STATES or (rec.handle is not None and rec.handle.finished and rec.result is None):
                    if i >= len(rec.events):
                        yield f"event: end\ndata: {json.dumps({'state': state_of(rec)})}\n\n"
                        return
                    continue
                await asyncio.sleep(0.05)
                idle += 0.05
                if idle >= 10:
                    yield ": keep-alive\n\n"
                    idle = 0.0

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.post("/run/{run_id}/stop")
    def run_stop(run_id: str) -> dict[str, Any]:
        rec = get_rec(run_id)
        out = sup.stop("stopped through the API")
        if rec.result is None:
            rec.state = "stopped"
        return {"stopped": True, "generation": out["generation"]}

    @app.post("/run/{run_id}/finalize")
    async def run_finalize(run_id: str) -> dict[str, Any]:
        """Additive: press the real submit button for a case note whose queue item the worker approved."""
        rec = get_rec(run_id)
        res = rec.result or {}
        if not (res.get("note_id") and res.get("queue_id")):
            raise HTTPException(409, "this run has no note waiting for approval")
        if rec.cached:
            raise HTTPException(409, "a cached run has no live case note to submit")
        out = await finalize(run_id, res["note_id"], res["queue_id"], model=_model_for(rec.mode), base_url_a=urls["a"],
                             queue=queue, audit=audit)
        return out

    # ------------------------------------------------------------------ kill
    @app.post("/kill")
    def kill() -> dict[str, Any]:
        try:
            set_kill("agent service /kill")
        except OSError:
            pass
        sup.kill("agent service /kill")
        return {"killed": True}

    @app.post("/kill/clear")
    def kill_clear() -> dict[str, Any]:
        clear_kill()
        return {"killed": False}

    # ------------------------------------------------------------------ human input, routines, off-hours
    @app.post("/human-input")
    def human_input() -> dict[str, Any]:
        """The desktop app calls this when the worker touches the keyboard or pointer (HND-5): background runs yield."""
        human.signal()
        return {"signalled": True}

    @app.post("/routines/{routine_id}/run")
    def routine_run(routine_id: str, body: RoutineRunIn) -> dict[str, Any]:
        kind = {"shadow": "shadow", "approved": "approved", "background": "background"}[body.mode]
        ok, why = consent_allows(read_consent(routine_id), kind)
        if not ok:
            raise HTTPException(409, f"not started: {why}")
        bundles = load_bundles(routine_id)
        if not bundles:
            raise HTTPException(404, f"no compiled routine {routine_id!r} on this machine (data/routines/{routine_id}/steps.json)")
        by_site = {k: v for k, v in bundles.items() if k != "primary"} or {"a": bundles["primary"]}
        h = pick_household(RunIn(household_id=body.household_id))
        rec = RunRecord(run_id="r_" + os.urandom(4).hex(), mode=body.mode, household_id=h.id)
        runs[rec.run_id] = rec
        model = _model_for("mock" if mock_enabled() else "live")
        engine = EngineClient(ENGINE_URL)
        if body.mode == "shadow":
            from .tiers.browser import BrowserHost

            def work_shadow(ctx: TaskContext) -> None:
                async def go() -> dict[str, Any]:
                    async with BrowserHost() as host:
                        sr = ShadowRunner(routine_id, by_site, model=model, engine=engine, audit=audit, queue=queue,
                                          base_urls=urls)
                        out = await sr.run_episode(host, h, body.worker_results or {}, run_id=rec.run_id)
                    return {"state": "done", "matched": out.matched if body.worker_results else None,
                            "diffs": out.diffs, "event": out.event, "engine": out.engine, "agent": out.agent,
                            "completion": {"ok": out.event is None, "missing": []}}

                finish(rec, run_async(go()))

            rec.handle = sup.submit(work_shadow, name="shadow", run_id=rec.run_id, deadline_s=120.0)
        else:
            br = BackgroundRunner(routine_id, supervisor=sup, human_input=human, model=model, bundles=by_site,
                                  base_urls=urls, audit=audit, queue=queue, engine=engine)
            try:
                rec.handle = br.start(h, run_id=rec.run_id)
            except ConsentRefused as exc:
                runs.pop(rec.run_id, None)
                raise HTTPException(409, str(exc)) from None
            rec.run = None

            def after(handle: Any = rec.handle) -> None:
                handle.wait()
                if handle.state == "done" and isinstance(handle.result, dict):
                    finish(rec, handle.result)

            threading.Thread(target=after, daemon=True).start()
        rec.generation = rec.handle.generation
        return {"run_id": rec.run_id}

    @app.get("/offhours/report")
    def offhours_report(since: str | None = None) -> dict[str, Any]:
        return morning_report(audit, queue, since)

    return app


def main() -> None:  # pragma: no cover - manual use
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
