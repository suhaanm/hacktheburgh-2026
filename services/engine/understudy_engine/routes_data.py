"""Engine API routes owned by engine-data (contract: docs/API_CONTRACT.md): health, events, replay, packs, genome,
graph/transitions, queue, audit, kill, run evidence, eval report.

Analytic GETs return ``{meta, data}``. Plain reads and writes return their body as documented.
Everything answers from files on disk; no endpoint needs a model call, so mock mode is the same code path.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .api import files
from .api.errors import ApiError
from .cogs import cog_labeler
from .core import AnalyticMeta
from .genome import GenomeError, GenomeService
from .packs import list_packs
from .store import EventStore, fmt_t, is_mock, replay, to_row
from .store.paths import evals_dir

router = APIRouter()
START = time.time()
_agent_probe: dict = {"t": 0.0, "ok": False}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _meta(origin: str, n: int, n_unit: str, note: str | None = None, split: str | None = None) -> dict:
    m = AnalyticMeta(origin=origin, n=n, n_unit=n_unit, split=split, note=note, generated_at=_now())
    return m.model_dump(mode="json")


def _store(request: Request) -> EventStore:
    return request.app.state.store


def _genome(request: Request) -> GenomeService:
    return request.app.state.genome


def agent_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('AGENT_PORT', '7710')}"


def _agent_up() -> bool:
    if time.time() - _agent_probe["t"] < 2.0:
        return _agent_probe["ok"]
    try:
        ok = httpx.get(f"{agent_url()}/health", timeout=0.3).status_code < 500
    except httpx.HTTPError:
        ok = False
    _agent_probe.update(t=time.time(), ok=ok)
    return ok


# ------------------------------------------------------------------------------------------ health
@router.get("/health")
def health(request: Request):
    mock = is_mock()
    status = getattr(request.app.state, "router_status", {})

    def model(name: str) -> str:
        v = os.environ.get(name, "").strip()
        return v or ("mock" if mock else "(not set)")

    return {
        "ok": True, "version": __version__, "mock": mock,
        "models": {"planner": model("OPENAI_MODEL_PLANNER"), "fast": model("OPENAI_MODEL_FAST"), "computer_use": model("OPENAI_MODEL_COMPUTER_USE")},
        "services": {"engine": True, "agent": _agent_up()},
        # additive: which optional routers this engine loaded, and whether the caches are warm
        "routers": {"data": True, "analytics": status.get("routes_analytics") == "included", "handoff": status.get("routes_handoff") == "included",
                    "coach": status.get("routes_coach") == "included"},
        "warm": dict(getattr(request.app.state, "warm", {})),
    }


# ------------------------------------------------------------------------------------------ events
@router.post("/events")
async def post_events(request: Request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError(400, "bad_json", "The body is not valid JSON. Send one event or a list of events.")
    if isinstance(body, dict) and isinstance(body.get("events"), list):
        body = body["events"]
    rows = body if isinstance(body, list) else [body]
    if len(rows) > 20000:
        raise ApiError(413, "too_many_events", "Send at most 20000 events per request.")
    res = _store(request).append_many(rows)
    return {"accepted": res.accepted, "rejected": res.rejected}


def _parse_since(since: str | None):
    if not since:
        return None
    try:
        datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "bad_since", "since must be an ISO-8601 time such as 2026-11-07T09:00:00Z.")
    return since


@router.get("/events")
def get_events(
    request: Request,
    partition: Literal["real", "synthetic"] = "real",
    person: str | None = None,
    since: str | None = None,
    limit: int = Query(1000, ge=1, le=50000),
):
    evs = _store(request).read(partition, person=person, since=_parse_since(since), limit=limit)
    return {"events": [to_row(e) for e in evs]}


@router.get("/replay")
def get_replay(
    request: Request,
    person: str | None = None,
    task: str | None = None,
    speed: float = Query(20.0, ge=1.0, le=200.0),
    squeeze_idle_s: float = Query(30.0, ge=0.0, le=3600.0),
    partition: Literal["real", "synthetic"] | None = None,
    limit: int = Query(4000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
):
    store = _store(request)
    if not person and not task:
        try:
            person, task = _genome(request).default_person_episode()
        except GenomeError as exc:
            raise ApiError(422, "person_or_task_required", "Give person or task. (No default case is available: " + exc.message + ")")
    if partition is None:
        partition = "real" if store.read("real", person=person, task=task, limit=1) else "synthetic"
    evs = store.read(partition, person=person, task=task)
    if not evs:
        raise ApiError(404, "no_events", f"No {partition} events for person={person!r} task={task!r}.")
    rp = replay(evs, speed=speed, squeeze_idle_s=squeeze_idle_s, label_fn=cog_labeler())
    frames = rp.frames[offset: offset + limit]
    return {
        "duration_s": rp.duration_s,
        "partition": partition,
        "total_frames": len(rp.frames),
        "truncated": offset + limit < len(rp.frames),
        "frames": [{"t_replay": f.t_replay, "event": to_row(f.event), "state": f.state} for f in frames],
    }


# ------------------------------------------------------------------------------------------ packs
@router.get("/packs")
def get_packs():
    return list_packs()


# ------------------------------------------------------------------------------------------ genome
def _gerr(exc: GenomeError) -> ApiError:
    return ApiError(exc.status, exc.code, exc.message)


@router.get("/genome/{task}")
def get_genome(
    request: Request, task: str, person: str | None = None,
    reference: Literal["nearest_expert", "consensus"] = "nearest_expert",
    partition: Literal["real", "synthetic"] | None = None, episode: str | None = None,
):
    try:
        data, meta = _genome(request).genome(task, person=person, reference=reference, partition=partition, episode=episode)
    except GenomeError as exc:
        raise _gerr(exc)
    return {"meta": meta.model_dump(mode="json") | {"generated_at": fmt_t(_now())}, "data": data}


@router.get("/graph/transitions")
def get_transitions(request: Request, task: str = "benefits-household-entry", person: str | None = None,
                    partition: Literal["real", "synthetic"] | None = None):
    try:
        data, meta = _genome(request).transitions(task, person=person, partition=partition)
    except GenomeError as exc:
        raise _gerr(exc)
    return {"meta": meta.model_dump(mode="json") | {"generated_at": fmt_t(_now())}, "data": data}


# ------------------------------------------------------------------------------------------ queue
class Auth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["local", "auth0_stepup"] = "local"
    sub_hash: str | None = Field(None, description="12 lowercase hex characters, a hash of the identity subject; never a name, email or token")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auth: Auth | None = None


def _queue_origin() -> str:
    return "synthetic" if is_mock() else "real"


@router.get("/queue")
def get_queue(status: Literal["pending", "approved", "rejected", "expired", "all"] = "pending"):
    items = files.queue_list(status)
    return {"meta": _meta(_queue_origin(), len(items), "episodes", "Items raised by agent runs. Approve or reject each one yourself."), "data": items}


def _decide(item_id: str, action: str, body: Decision | None):
    auth = body.auth.model_dump(exclude_none=True) if body and body.auth else None
    return files.queue_decide(item_id, action, auth)


@router.post("/queue/{item_id}/approve")
def approve(item_id: str, body: Decision | None = None):
    return _decide(item_id, "approve", body)


@router.post("/queue/{item_id}/reject")
def reject(item_id: str, body: Decision | None = None):
    return _decide(item_id, "reject", body)


# ------------------------------------------------------------------------------------------ audit
@router.get("/audit")
def get_audit(limit: int = Query(100, ge=1, le=5000)):
    rows = files.audit_read(limit)
    return {"meta": _meta(_queue_origin(), len(rows), "episodes", "Redacted: no page text, hashed notes, hash-chained."), "data": rows}


# ------------------------------------------------------------------------------------------ kill
def _notify_agent_kill() -> bool:
    try:
        return httpx.post(f"{agent_url()}/kill", timeout=0.8).status_code < 500
    except httpx.HTTPError:
        return False


@router.get("/kill")
def get_kill():
    return files.kill_state()


@router.post("/kill")
def post_kill():
    files.kill_set()          # the file first: stopping never waits for the agent
    st = files.kill_state()
    return {"killed": True, "at": st["at"], "agent_notified": _notify_agent_kill()}


@router.post("/kill/clear")
def post_kill_clear():
    files.kill_clear()
    return {"killed": False, "at": None}


# ------------------------------------------------------------------------------------------ run evidence
@router.get("/runs/{run_id}/{file}")
def get_run_file(run_id: str, file: str):
    path, media = files.evidence_path(run_id, file)
    return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------------------------------ eval report
def report_path() -> Path:
    env = os.environ.get("UNDERSTUDY_EVAL_REPORT", "").strip()
    return Path(env).expanduser() if env else evals_dir() / "report.json"


@router.get("/eval/report")
def get_eval_report():
    p = report_path()
    if not p.is_file():
        raise ApiError(404, "no_report", "evals/report.json does not exist yet. Run `make eval` to write it.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ApiError(500, "bad_report", "evals/report.json is not valid JSON. Run `make eval` again.")
