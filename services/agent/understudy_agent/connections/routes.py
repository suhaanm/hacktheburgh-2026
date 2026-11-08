"""Agent-side connection routes (CONNECTIONS): the engine asks this service to start or stop a connection the worker clicked.

    POST /connections/{id}/start    start it (only if the worker's consent is on file and the pinned hash matches) and return COUNTS of its tools
    POST /connections/{id}/stop     stop the process and forget the session
    GET  /connections/{id}/status   running or not, tool counts

There is deliberately NO route that calls a tool: the only way a tool runs is a child agent's ``mcp_call`` step through the SafetyPipeline. The shared
HTTP guard (Host, Origin, JSON, actor) wraps these routes like every other write, and ``start`` re-checks the worker's consent itself, so a request
to start something the worker never switched on is refused here as well. Nothing is started at boot.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .service import default_service

router = APIRouter(tags=["connections"])
_ID = re.compile(r"^[a-z][a-z0-9_\-]{1,40}$")


def _bad() -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": {"code": "bad_id", "message": "That connection id is not valid."}})


@router.post("/connections/{conn_id}/start")
def start(conn_id: str):
    if not _ID.match(conn_id):
        return _bad()
    return default_service().start(conn_id)


@router.post("/connections/{conn_id}/stop")
def stop(conn_id: str):
    if not _ID.match(conn_id):
        return _bad()
    return default_service().stop(conn_id)


@router.get("/connections/{conn_id}/status")
def status(conn_id: str):
    if not _ID.match(conn_id):
        return _bad()
    svc = default_service()
    tools = svc.runner.tools(conn_id)
    return {"id": conn_id, "running": svc.runner.is_running(conn_id), "tools": len(tools)}
