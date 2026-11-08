"""HTTP routes for tasks and skills (docs/API_CONTRACT.md "Tasks API"; docs/TASKS.md). Served by the agent service on :7710.

    POST /tasks {text, source}                 -> {task_id, route, summary, needs_consent, question}
    GET  /tasks                                -> ROW[] newest first
    GET  /tasks/events                         -> text/event-stream: snapshot, task_started, task_progress, task_finished, heartbeat (10 s)
    GET  /tasks/{id}                           -> ROW + steps + answer
    POST /tasks/{id}/consent {choice}          -> ROW   release route: actor worker_approval and the per-boot token
    POST /tasks/{id}/answer {option_id}        -> ROW
    POST /tasks/{id}/stop                      -> ROW   stop route: no token
    POST /tasks/{id}/open                      -> {opened: true}  reveals the task's own recorded folder or file in Finder
    GET  /skills                               -> {use_claude_skills, off, skills[]}
    POST /skills/settings {use_claude_skills?, off?, max_minutes?}   -> the same shape

Writes: the shared guard (understudy_engine.http_guard) runs first on every request (Host, Origin, JSON, explicit actor, token on
release routes). On top of it each write names who may do it: creating, answering and stopping accept `worker`, `worker_approval` and
`voice`; consent accepts `worker_approval` (or a local caller with no actor and the token); settings accept `worker` and
`worker_approval`. Any other actor (agent, model, tool, page, extension) is refused with 403 `write_refused`.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .manager import TaskError, TaskManager
from .model import SOURCES, Task
from .skills import SkillBook, load_settings, save_settings
from .store import valid_id

router = APIRouter(tags=["tasks"])
HEARTBEAT_S = 10.0
POLL_S = 0.1
CREATE_ACTORS = frozenset({"worker", "worker_approval", "voice"})
SETTING_ACTORS = frozenset({"worker", "worker_approval"})


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def manager_of(request: Request) -> TaskManager:
    app = request.app
    m = getattr(app.state, "tasks", None)
    if m is None:
        from .manager import get_manager

        m = app.state.tasks = get_manager()
    return m


def _actor_refusal(request: Request, allowed: frozenset[str]) -> JSONResponse | None:
    from understudy_engine import http_guard as hg

    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return _err(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    actor = (request.headers.get(hg.ACTOR_HEADER) or "").strip()
    if not actor:
        if request.headers.get("origin") is not None:
            return _err(403, "write_refused", "Send X-Understudy-Actor explicitly.")
        return None                                           # a local process with no Origin: the worker's own script
    if actor not in allowed:
        return _err(403, "write_refused", "That actor cannot do this. Only the worker can.")
    return None


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        raw = await request.body()
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return _err(422, "bad_body", "The body must be JSON.")
    if not isinstance(data, dict):
        return _err(422, "bad_body", "The body must be a JSON object.")
    return data


def _call(fn: Any, *a: Any, **kw: Any) -> Any:
    try:
        return fn(*a, **kw)
    except TaskError as e:
        return _err(e.status, e.code, e.message)


@router.post("/tasks", status_code=201)
async def create_task(request: Request) -> Any:
    if (r := _actor_refusal(request, CREATE_ACTORS)) is not None:
        return r
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    text, source = body.get("text"), body.get("source", "typed")
    if not isinstance(text, str) or source not in SOURCES:
        return _err(422, "bad_body", "Send {text: string, source: typed or voice}.")
    m = manager_of(request)
    out = await asyncio.to_thread(_call, m.create, text, source)
    if isinstance(out, JSONResponse):
        return out
    return JSONResponse(out, status_code=201)


@router.get("/tasks")
def list_tasks(request: Request) -> Any:
    return manager_of(request).list_rows()


async def sse_stream(m: TaskManager, *, max_seconds: float | None = None, heartbeat_s: float = HEARTBEAT_S,
                     poll_s: float = POLL_S) -> AsyncIterator[str]:
    """snapshot, then every task event as it happens, then a heartbeat each `heartbeat_s` seconds of quiet."""
    def fmt(name: str, data: Any) -> str:
        return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"

    seq = m.last_seq()
    yield fmt("snapshot", {"tasks": m.snapshot(20)})
    last_beat = time.monotonic()
    t0 = time.monotonic()
    while True:
        evs = m.events_since(seq)
        for s, name, row in evs:
            seq = s
            yield fmt(name, row)
            last_beat = time.monotonic()
        if time.monotonic() - last_beat >= heartbeat_s:
            from .model import now_iso

            yield fmt("heartbeat", {"t": now_iso()})
            last_beat = time.monotonic()
        if max_seconds is not None and time.monotonic() - t0 >= max_seconds:
            return
        await asyncio.sleep(poll_s)


@router.get("/tasks/events")
async def task_events(request: Request) -> StreamingResponse:
    m = manager_of(request)
    return StreamingResponse(sse_stream(m), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> Any:
    d = manager_of(request).detail(task_id) if valid_id(task_id) else None
    return d if d is not None else _err(404, "no_such_task", "No such task.")


@router.post("/tasks/{task_id}/consent")
async def consent(task_id: str, request: Request) -> Any:
    if (r := _actor_refusal(request, frozenset({"worker_approval"})) ) is not None:
        return r
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    t = await asyncio.to_thread(_call, manager_of(request).consent, task_id, str(body.get("choice", "")), body.get("max_minutes"))
    return t if isinstance(t, JSONResponse) else t.row()


@router.post("/tasks/{task_id}/answer")
async def answer(task_id: str, request: Request) -> Any:
    if (r := _actor_refusal(request, CREATE_ACTORS)) is not None:
        return r
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    t = await asyncio.to_thread(_call, manager_of(request).answer, task_id, str(body.get("option_id", "")))
    return t if isinstance(t, JSONResponse) else t.row()


@router.post("/tasks/{task_id}/stop")
async def stop(task_id: str, request: Request) -> Any:
    if (r := _actor_refusal(request, CREATE_ACTORS)) is not None:
        return r
    t = await asyncio.to_thread(_call, manager_of(request).stop, task_id)
    return t if isinstance(t, JSONResponse) else t.row()


@router.post("/tasks/{task_id}/open")
async def open_task(task_id: str, request: Request) -> Any:
    if (r := _actor_refusal(request, frozenset({"worker", "worker_approval"}))) is not None:
        return r
    path = _call(manager_of(request).open_path, task_id)
    if isinstance(path, JSONResponse):
        return path
    if sys.platform != "darwin":
        return _err(501, "not_supported", "Opening a folder from here works on a Mac only.")
    try:                                                      # -R reveals in Finder: it never launches or runs the item
        subprocess.run(["open", "-R", path], check=True, timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return _err(500, "open_failed", "Could not open it in Finder.")
    return {"opened": True}


# ------------------------------------------------------------------------------------------------------------ skills
def _book(request: Request) -> SkillBook:
    return manager_of(request).book


@router.get("/skills")
def skills(request: Request, refresh: bool = False) -> Any:
    return _book(request).listing(fresh=refresh)


@router.post("/skills/settings")
async def skill_settings(request: Request) -> Any:
    if (r := _actor_refusal(request, SETTING_ACTORS)) is not None:
        return r
    body = await _body(request)
    if isinstance(body, JSONResponse):
        return body
    if "use_claude_skills" in body and not isinstance(body["use_claude_skills"], bool):
        return _err(422, "bad_body", "use_claude_skills must be true or false.")
    if "off" in body and not (isinstance(body["off"], list) and all(isinstance(x, str) for x in body["off"])):
        return _err(422, "bad_body", "off must be a list of skill names.")
    if "max_minutes" in body and (not isinstance(body["max_minutes"], int) or isinstance(body["max_minutes"], bool)
                                  or not 1 <= body["max_minutes"] <= 120):
        return _err(422, "bad_body", "max_minutes must be 1 to 120.")
    save_settings(body)
    return _book(request).listing()
