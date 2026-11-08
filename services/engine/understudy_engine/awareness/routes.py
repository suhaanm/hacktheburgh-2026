"""Awareness routes (AWR-1, AWR-2). ``api/app.py`` includes ``router`` when ``enabled()``; every route also answers 404 ``extension_off``
itself when the flag is off, so a mistaken include cannot expose them.

  POST /awareness/events          one event or a list (at most 500)  ->  {accepted, duplicates, rejected: [{index, reason}]}
  GET  /awareness/summary?person=&origin=real|synthetic&since=&until=  ->  {meta, data}  counts and means for the Privacy screen
  GET  /awareness/windows?person=&origin=&since=&until=&limit=         ->  {meta, data: {windows: [...], loose_glances: [...]}}
  GET  /awareness/columns                                              ->  {meta, data: {columns: [...]}}  the hazard feature column names
  POST /awareness/clear           {person?, origin?}  (this machine, actor header ``worker``)  ->  {cleared}

Events are the desktop app's own and arrive from this machine only (loopback, and an Origin that is the app or localhost when one is
sent), like ``POST /events``. Only the awareness schema is accepted: numbers and closed enums, no coordinates, titles, text or pixels; a
rejection names the rule and the path, never a value. Nothing here calls a model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from .. import http_guard
from fastapi.responses import JSONResponse

from . import flag_enabled, schema
from .features import AWARENESS_COLUMNS
from .store import MAX_BATCH, ORIGINS, AwarenessStore, default_store

router = APIRouter(tags=["awareness"])

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_FALLBACK_WORKER_ACTORS = frozenset({"worker", "worker_approval"})


def enabled() -> bool:
    return flag_enabled()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if enabled():
        return None
    return _error(404, "extension_off", "The awareness layer is off. Set UNDERSTUDY_X_AWARENESS=1 (or UNDERSTUDY_X=1) and restart the engine.")


def _store() -> AwarenessStore:
    return default_store()


def _guard(request: Request, *, worker: bool = False) -> JSONResponse | None:
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        return _error(403, "write_refused", "Awareness events are only accepted from this machine.")
    origin = request.headers.get("origin")
    if origin is not None and not http_guard.origin_allowed(origin):
        return _error(403, "write_refused", "Writes only come from the Understudy app on this machine.")
    if worker:
        try:
            from ..memory.store import WORKER_ACTORS as actors
        except Exception:                                    # pragma: no cover - the memory module is always present in the repo
            actors = _FALLBACK_WORKER_ACTORS
        actor = request.headers.get("x-understudy-actor", "").strip()
        if actor not in actors:
            return _error(403, "write_refused", "Only the worker can delete awareness data.")
    return None


def _meta(origin: str, n: int, note: str) -> dict[str, Any]:
    try:
        from ..core import AnalyticMeta

        return AnalyticMeta(origin=origin, n=n, n_unit="windows", split=None, note=note, generated_at=datetime.now(timezone.utc)).model_dump(mode="json")
    except Exception:                                        # pragma: no cover
        return {"origin": origin, "n": n, "n_unit": "windows", "split": None, "interval_level": 0.95, "note": note,
                "generated_at": datetime.now(timezone.utc).isoformat()}


def _time(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return schema.parse_time(value)
    except ValueError:
        raise ValueError("bad time")


def _person_origin(person: str, origin: str) -> JSONResponse | None:
    if origin not in ORIGINS:
        return _error(422, "bad_origin", "origin must be real or synthetic.")
    try:
        _store().path(person, origin)
    except ValueError:
        return _error(422, "bad_person", "person must look like p_demo01.")
    return None


@router.post("/awareness/events")
async def post_events(request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _guard(request)) is not None:
        return g
    try:
        body = await request.json()
    except ValueError:
        return _error(422, "bad_json", "The body must be JSON: one awareness event or a list of them.")
    events = body if isinstance(body, list) else [body]
    if len(events) > MAX_BATCH:
        return _error(422, "batch_too_large", f"At most {MAX_BATCH} events per request.")
    res = _store().append(events)
    return {"accepted": res.accepted, "duplicates": res.duplicates, "rejected": [{"index": i, "reason": why} for i, why in res.rejected]}


@router.get("/awareness/summary")
def get_summary(person: str = Query(...), origin: str = Query("real"), since: str | None = Query(None), until: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (bad := _person_origin(person, origin)) is not None:
        return bad
    try:
        s, u = _time(since), _time(until)
    except ValueError:
        return _error(422, "bad_time", "since and until must be ISO-8601 times such as 2026-11-07T09:30:00Z.")
    data = _store().summary(person, origin, since=s, until=u)
    note = ("Counts and means of on-device features and the closed answers of screen glances. No coordinates, titles, text or pixels are stored. "
            + ("Generated events." if origin == "synthetic" else "Live events from this Mac."))
    return {"meta": _meta(origin, data["windows"], note), "data": data}


@router.get("/awareness/windows")
def get_windows(person: str = Query(...), origin: str = Query("real"), since: str | None = Query(None), until: str | None = Query(None),
                limit: int = Query(300, ge=1, le=5000)):
    if (r := _off()) is not None:
        return r
    if (bad := _person_origin(person, origin)) is not None:
        return bad
    try:
        s, u = _time(since), _time(until)
    except ValueError:
        return _error(422, "bad_time", "since and until must be ISO-8601 times such as 2026-11-07T09:30:00Z.")
    wins, loose = _store().windows(person, origin, since=s, until=u)
    wins = wins[-limit:]

    def g(x: Any) -> dict[str, Any]:
        return {"t": schema.iso(x.t), "trigger": x.trigger, "app_kind": x.app_kind, "task_phase": x.task_phase, "blocker": x.blocker,
                "confidence": x.confidence, **({"box_2d": list(x.box_2d)} if x.box_2d else {})}

    rows = [{"t": schema.iso(w.t0), "window_s": w.window_s, "app_kind": w.app_kind, "sys_idle_s": w.sys_idle_s, "cursor": w.cursor,
             "glances": [g(x) for x in w.glances]} for w in wins]
    return {"meta": _meta(origin, len(rows), "Windows are two-second summaries; they hold numbers and enums only."),
            "data": {"windows": rows, "loose_glances": [g(x) for x in loose[-limit:]]}}


@router.get("/awareness/columns")
def get_columns():
    if (r := _off()) is not None:
        return r
    return {"meta": _meta("synthetic", len(AWARENESS_COLUMNS), "Names of the awareness columns offered to the stuck hazard (n counts columns)."),
            "data": {"columns": list(AWARENESS_COLUMNS), "span_s": 30}}


@router.post("/awareness/clear")
async def post_clear(request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _guard(request, worker=True)) is not None:
        return g
    try:
        body = await request.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    person, origin = body.get("person"), body.get("origin")
    if origin is not None and origin not in ORIGINS:
        return _error(422, "bad_origin", "origin must be real or synthetic.")
    if person is not None:
        try:
            _store().path(str(person), origin or "real")
        except ValueError:
            return _error(422, "bad_person", "person must look like p_demo01.")
    return {"cleared": _store().clear(person, origin), "at": datetime.now(timezone.utc).isoformat()}
