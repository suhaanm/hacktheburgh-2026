"""Connections routes (CONNECTIONS): the curated presets, one click to connect, one click to revoke. On by default (D48); every connection is OFF
until the worker clicks it.

``api/app.py`` includes ``router`` only when ``enabled()`` (``UNDERSTUDY_X_CONNECTIONS=1`` or the master ``UNDERSTUDY_X=1``). Plain JSON errors:
``{"error": {"code", "message"}}``. Answers are ``{"meta", "data"}``.

    GET  /connections?role=&group=            the presets (for a role: the ones its pack offers), each with state, consent lines for Example and Real
    GET  /connections/{id}                    one preset in detail: publisher, licence, hosts, sources, limits, counts
    POST /connections/{id}/connect            {mode: example|real, confirm: true, params?, secrets?}: records the consent, stores the token, asks the
                                              agent service to start it. WRITE: the worker only, from this machine, from the app.
    POST /connections/{id}/reconfirm          {confirm: true}: after a changed version or command hash
    POST /connections/{id}/revoke             off, token forgotten, the process stopped
    POST /connections/{id}/routines           {routine_id, allowed}: opt ONE routine in for ONE connection (reads only, unattended)
    GET  /connections/{id}/reads              counts only (calls, reads, changes asked, refused, bytes returned, tools used)

A token arrives once in the body of ``connect``, goes straight to the Keychain (or the mode-600 file) and is never returned, logged or echoed in
an error. The list of presets is curated: there is no route that adds a server.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import http_guard
from . import ledger, registry, service, state
from .paths import FLAG, agent_url, enabled

__all__ = ["router", "enabled", "FLAG"]

router = APIRouter(tags=["connections"])
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_FALLBACK_WORKER_ACTORS = frozenset({"worker", "worker_approval"})
MAX_BODY = 20_000


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if not enabled():
        return _error(404, "extension_off", f"Connections are off. Set {FLAG}=1 (or the master UNDERSTUDY_X=1) and restart the engine.")
    return None


def _meta(items: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    """Example connections are synthetic; real ones are real; both present is mixed. Nothing connected is synthetic by default (no data)."""
    on = [i for i in items if i.get("state") in ("connected", "error")]
    mock = sum(1 for i in on if i.get("example"))
    origin = "synthetic" if on and mock == len(on) else "real" if on and mock == 0 else "mixed" if on else "synthetic"
    return {"origin": origin, "n": len(items), "n_unit": "connections", "split": None, "interval_level": 0.95, "note": note,
            "generated_at": datetime.now(timezone.utc).isoformat()}


def _write_guard(request: Request) -> JSONResponse | None:
    """Connecting and revoking are the worker's own actions: from this machine, naming the worker actor, from the app."""
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        return _error(403, "write_refused", "Connections can only be changed from this machine.")
    try:
        from ..memory.store import WORKER_ACTORS as actors
    except Exception:  # pragma: no cover
        actors = _FALLBACK_WORKER_ACTORS
    actor = http_guard.actor_of(request)
    if actor not in actors:
        return _error(403, "write_refused", f"Only the worker can change a connection; the actor {actor[:20]!r} cannot.")
    origin = request.headers.get("origin")
    if origin is not None and not http_guard.origin_allowed(origin):
        return _error(403, "write_refused", "Changes only come from the Knack app on this machine.")
    return None


async def _body(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return None, _error(413, "too_large", "That request is too large.")
    try:
        data = await request.json() if raw else {}
    except ValueError:
        return None, _error(400, "bad_json", "The request was not valid JSON.")
    return (data, None) if isinstance(data, dict) else (None, _error(400, "bad_json", "The request must be a JSON object."))


def _agent(path: str, body: dict[str, Any] | None = None, timeout: float = 25.0) -> dict[str, Any] | None:
    """Ask the local agent service (this machine only) to start, probe or stop a connection. None when it is not reachable; the state is
    already saved, so the worker's click is not lost."""
    try:
        r = httpx.post(f"{agent_url()}{path}", json=body or {}, timeout=timeout)
        out = r.json() if r.status_code < 500 else None
        return out if isinstance(out, dict) else None
    except (httpx.HTTPError, OSError, ValueError):
        return None


def _preset_or_404(conn_id: str):
    p = registry.get(conn_id)
    return (p, None) if p else (None, _error(404, "unknown_connection", "That connection is not in the curated list."))


# ----------------------------------------------------------------------------------------------------------------- reads
@router.get("/connections")
def list_connections(role: str | None = Query(None, max_length=40), group: str | None = Query(None, max_length=12)):
    if (r := _off()) is not None:
        return r
    items = service.listing(role, group)
    return {"meta": _meta(items, "Every connection starts off. Example connections use invented data on this Mac."), "data": items}


@router.get("/connections/{conn_id}")
def get_connection(conn_id: str):
    if (r := _off()) is not None:
        return r
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    v = service.view(p, detail=True)
    return {"meta": _meta([v]), "data": v}


@router.get("/connections/{conn_id}/reads")
def get_reads(conn_id: str):
    if (r := _off()) is not None:
        return r
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    return {"meta": _meta([service.view(p)]), "data": ledger.reads_summary(p.id)}


# ---------------------------------------------------------------------------------------------------------------- writes
@router.post("/connections/{conn_id}/connect")
async def connect(conn_id: str, request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _write_guard(request)) is not None:
        return g
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    body, bad = await _body(request)
    if bad is not None:
        return bad
    try:
        await run_in_threadpool(lambda: state.connect(p, mode=str(body.get("mode", "")), confirm=body.get("confirm") is True,
                                                      params=body.get("params"), secrets=body.get("secrets")))
    except state.ConnectError as e:
        return _error(e.status, e.code, str(e))
    probe = await run_in_threadpool(_agent, f"/connections/{p.id}/start")
    if probe is not None:
        state.mark_probe(p.id, probe)
    v = service.view(p, detail=True)
    v["agent"] = "online" if probe is not None else "offline"
    return {"meta": _meta([v]), "data": v}


@router.post("/connections/{conn_id}/reconfirm")
async def reconfirm(conn_id: str, request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _write_guard(request)) is not None:
        return g
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    body, bad = await _body(request)
    if bad is not None:
        return bad
    try:
        await run_in_threadpool(lambda: state.reconfirm(p, confirm=body.get("confirm") is True))
    except state.ConnectError as e:
        return _error(e.status, e.code, str(e))
    probe = await run_in_threadpool(_agent, f"/connections/{p.id}/start")
    if probe is not None:
        state.mark_probe(p.id, probe)
    v = service.view(p, detail=True)
    return {"meta": _meta([v]), "data": v}


@router.post("/connections/{conn_id}/revoke")
def revoke(conn_id: str, request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _write_guard(request)) is not None:
        return g
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    out = state.revoke(p)
    stopped = _agent(f"/connections/{p.id}/stop", timeout=10.0)
    out["process_stopped"] = bool(stopped and stopped.get("stopped", True))
    out["agent"] = "online" if stopped is not None else "offline"
    return {"meta": _meta([service.view(p)]), "data": {**out, "connection": service.view(p)}}


@router.post("/connections/{conn_id}/routines")
async def routine_optin(conn_id: str, request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _write_guard(request)) is not None:
        return g
    p, err = _preset_or_404(conn_id)
    if err is not None:
        return err
    body, bad = await _body(request)
    if bad is not None:
        return bad
    try:
        ids = state.set_routine(p, str(body.get("routine_id", "")), body.get("allowed") is True)
    except state.ConnectError as e:
        return _error(e.status, e.code, str(e))
    return {"meta": _meta([service.view(p)], "Only reads ever run unattended, whatever is allowed here."), "data": {"id": p.id, "routines": ids}}
