"""HTTP routes for the agent runtime (docs/API_CONTRACT.md "Extensions API", BGA). Included by the agent service when
`UNDERSTUDY_X_AGENTS=1` (or `UNDERSTUDY_X=1`); every route also refuses with 404 `extension_disabled` when the flag is off.

    GET  /agents/runs?person=                    [{run_id, kind, mode, state, started, parent, children[]}]
    GET  /agents/runs/{id}                       the same plus artifacts[] and result
    POST /agents/spawn {kind, params, mode}      -> {run_id}
    POST /agents/runs/{id}/stop                  stops every child at once
    POST /agents/runs/{id}/children/{cid}/revoke ends one child at once (its lease is revoked)
    additive: POST /agents/runs/{id}/resume, GET /agents/kinds, GET /agents/morning?since=,
              GET /agents/runs/{id}/artifacts/{child}/{name}

Writes (spawn, stop, revoke, resume) are the worker's own actions: a request naming another actor in
`X-Understudy-Actor` (page, agent, model, tool, ...) or coming from a foreign origin is refused with 403.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from ..security.killflag import is_killed
from ..security.paths import runs_dir
from . import policy
from .run import AgentRun, get_run, live_runs, persisted_runs, register

router = APIRouter(prefix="/agents", tags=["agents"])
_WORKER_ACTORS = {"worker", "worker_approval"}
_ORIGINS = ("http://localhost", "http://127.0.0.1", "https://localhost", "file://", "app://")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
_RUN = re.compile(r"^r_[a-z0-9]{6,12}$")
MAX_LIVE_RUNS = 3
_spawn_lock = threading.Lock()


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _disabled() -> JSONResponse | None:
    if not policy.agents_enabled():
        return _err(404, "extension_disabled", "Background agents are off. Set UNDERSTUDY_X_AGENTS=1 to turn them on.")
    return None


def _guard(request: Request) -> JSONResponse | None:
    actor = request.headers.get("x-understudy-actor", "worker").strip() or "worker"
    origin = request.headers.get("origin")
    if actor not in _WORKER_ACTORS:
        return _err(403, "write_refused", "Only the worker starts or stops agents; this actor cannot.")
    if origin is not None and not origin.startswith(_ORIGINS):
        return _err(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def spawn_kinds() -> list[str]:
    from . import exemplars  # noqa: F401
    from .exemplars.base import KINDS

    return sorted(KINDS)


def _view(run_id: str, detail: bool) -> dict[str, Any] | None:
    r = get_run(run_id)
    if r is not None:
        return r.to_dict(detail)
    for d in persisted_runs():
        if d.get("run_id") == run_id:
            return d if detail else {k: v for k, v in d.items() if k not in ("artifacts", "result")}
    return None


@router.get("/kinds")
def kinds() -> Any:
    if (d := _disabled()) is not None:
        return d
    from .exemplars.base import KINDS

    return [{"kind": k, "title": e.title, "roles": list(e.roles), "describe": e.describe} for k, e in sorted(KINDS.items())]


@router.get("/morning")
def morning(since: str | None = None, words: bool = False) -> Any:
    """Additive: the morning report of agent runs (children and outcomes), and the one-line summary; `words=1` has the model
    reword the summary from codes and counts through the egress guard (the deterministic sentence is the fallback)."""
    if (d := _disabled()) is not None:
        return d
    from ..audit import AuditLog
    from ..queue import ApprovalQueue
    from .modes import agent_morning_report

    audit = AuditLog()
    rep = agent_morning_report(audit, ApprovalQueue(audit=audit), since)
    if words:
        from ..models import get_model_port
        from . import privacy as rtp

        kinds = {r["kind"] for r in rep["runs"]}
        if len(kinds) == 1:
            rep["summary"] = rtp.word_result(next(iter(kinds)), rep["runs"][0]["mode"], rep["runs"][0]["total"],
                                             rep["runs"][0]["verified"], get_model_port(), rep["summary"])
    return rep


@router.get("/runs")
def list_runs(person: str | None = None) -> Any:
    if (d := _disabled()) is not None:
        return d
    live = {r.run_id: r.to_dict(False) for r in live_runs()}
    rows = list(live.values())
    for d_ in persisted_runs():
        if d_.get("run_id") not in live:
            rows.append({k: v for k, v in d_.items() if k not in ("artifacts", "result")})
    if person:
        rows = [r for r in rows if r.get("person") in (None, person)]
    return sorted(rows, key=lambda r: r.get("started", ""), reverse=True)


@router.get("/runs/{run_id}")
def get_one(run_id: str) -> Any:
    if (d := _disabled()) is not None:
        return d
    v = _view(run_id, True) if _RUN.match(run_id) else None
    return v if v is not None else _err(404, "no_such_run", f"No agent run {run_id!r}.")


@router.post("/spawn")
async def spawn(request: Request) -> Any:
    if (d := _disabled()) is not None:
        return d
    if (g := _guard(request)) is not None:
        return g
    try:
        body = await request.json()
    except ValueError:
        return _err(422, "bad_body", "The body must be JSON: {kind, params, mode}.")
    if not isinstance(body, dict):
        return _err(422, "bad_body", "The body must be a JSON object.")
    kind, mode = body.get("kind"), body.get("mode", "foreground")
    params = body.get("params") or {}
    if kind not in spawn_kinds():
        return _err(422, "unknown_kind", f"Unknown kind. Known kinds: {', '.join(spawn_kinds())}.")
    if mode not in ("foreground", "nightly"):
        return _err(422, "bad_mode", "mode must be foreground or nightly.")
    if not isinstance(params, dict):
        return _err(422, "bad_params", "params must be an object.")
    if is_killed():
        return _err(423, "kill_switch_set", "The kill switch is set; clear it first.")
    with _spawn_lock:
        if sum(1 for r in live_runs() if not r.finished) >= MAX_LIVE_RUNS:
            return _err(429, "too_many_runs", f"At most {MAX_LIVE_RUNS} agent runs at a time.")
        raw_ok = bool(params.pop("raw_ok", False))
        try:
            run = AgentRun(kind=kind, params=params, mode=mode, raw_ok=raw_ok, person=body.get("person"),
                           human=_human(request))
        except ValueError as e:
            return _err(422, "bad_request", str(e)[:200])
        register(run).start()
    return {"run_id": run.run_id}


def _human(request: Request) -> Any:
    """The service's human-input signal when the agent server exposes one (so a yield reaches these runs)."""
    return getattr(request.app.state, "human_input", None)


@router.post("/runs/{run_id}/stop")
def stop(run_id: str, request: Request) -> Any:
    if (d := _disabled()) is not None:
        return d
    if (g := _guard(request)) is not None:
        return g
    run = get_run(run_id) if _RUN.match(run_id) else None
    if run is None:
        return _err(404, "no_such_run", f"No running agent run {run_id!r}.")
    out = run.stop("stopped through the API")
    return {"stopped": True, "run_id": run_id, **out}


@router.post("/runs/{run_id}/resume")
def resume(run_id: str, request: Request) -> Any:
    if (d := _disabled()) is not None:
        return d
    if (g := _guard(request)) is not None:
        return g
    run = get_run(run_id) if _RUN.match(run_id) else None
    if run is None:
        return _err(404, "no_such_run", f"No running agent run {run_id!r}.")
    return {"resumed": run.resume()}


@router.post("/runs/{run_id}/children/{child_id}/revoke")
def revoke(run_id: str, child_id: str, request: Request) -> Any:
    if (d := _disabled()) is not None:
        return d
    if (g := _guard(request)) is not None:
        return g
    run = get_run(run_id) if _RUN.match(run_id) else None
    if run is None:
        return _err(404, "no_such_run", f"No running agent run {run_id!r}.")
    if not run.revoke_child(child_id):
        return _err(404, "no_such_child", f"No child {child_id!r} in this run.")
    return {"revoked": True, "child_id": child_id}


@router.get("/runs/{run_id}/artifacts/{child_id}/{name}")
def artifact(run_id: str, child_id: str, name: str) -> Any:
    if (d := _disabled()) is not None:
        return d
    if not (_RUN.match(run_id) and re.match(r"^c[1-4]$", child_id) and _SAFE_NAME.match(name)):
        return _err(404, "no_such_artifact", "No such artifact.")
    p = runs_dir() / run_id / "artifacts" / child_id / name
    if not p.is_file() or p.is_symlink():
        return _err(404, "no_such_artifact", "No such artifact.")
    media = {".png": "image/png", ".json": "application/json", ".patch": "text/plain", ".md": "text/plain",
             ".txt": "text/plain"}.get(Path(name).suffix, "application/octet-stream")
    return FileResponse(p, media_type=media, headers={"X-Content-Type-Options": "nosniff"})
