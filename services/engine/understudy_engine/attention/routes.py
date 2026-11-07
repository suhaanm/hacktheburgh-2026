"""Attention routes (REQ-8): one layer decides whether, where, when and how loudly the worker is told anything. Off by default.

``api/app.py`` includes ``router`` only when ``enabled()`` (``UNDERSTUDY_X_ATTENTION=1`` or the master ``UNDERSTUDY_X=1``). Every handler also
checks the flag and answers 404 ``extension_off`` when it is off. Plain JSON errors: ``{"error": {"code", "message"}}``. ENGINE-DATA adds
one line to ``api/flags.py``: ``"attention": "attention.routes"`` in ``EXTENSIONS``.

    POST /attention/events    {type, person, subject, op?, risk_class?, outcome?, run_mode?, service?, count?, minutes?, expires_in_s?,
                               deadline_in_s?, blocks_run?, asked?, origin?, t?, state?}     producers (worker, system, agent actors)
                              -> {item_id, coalesced, show, decision, state}. For helpful-now events (cue_*, voice_line) ``show`` is the
                              admission answer: the caller draws the cue only when it is true. ``state`` is an optional worker state.
    GET  /attention/next      ?person=&typing_burst=&quiet_s=&away=&away_s=&locked=&dnd=&screen_sharing=&on_call=&in_meeting=&deep_work=
                              &task_in_progress=&task_marker_s=&voice_session=&dashboard_focused=&local_hour=&t=   (``typing`` also accepted;
                              ``peek=1`` returns only the passive counts and what is on screen, and delivers nothing)
                              -> {meta, data: {item, active, badges, digest_ready, poll_after_s}}   at most ONE item
    GET  /attention/digest    ?person=&kind=morning|return|rollup|now  -> {meta, data}
    POST /attention/feedback  {item_id, event: shown|followed|dismissed|ignored|never|opened|deferred, seconds?}      (worker)
                              ``deferred``: the desktop could not draw the item (the voice was taken): it goes back to held, no label
    GET  /attention/why       ?item=  -> {meta, data}: the fixed one-line reason, the transitions, the mode, the budget
    GET  /attention/settings  ?person=
    POST /attention/settings  {modes?: {type: loud|normal|quiet|digest}, budget_per_day?, level_glance?, reset_learned?}   (worker only)
    GET  /attention/stats     ?person=   today's shown and dropped counts, the budget, what was learned
    GET  /attention/export    ?person=   the metadata the layer holds, as one document
    DELETE /attention         ?person=   hard delete the person's attention state                         (worker)

Metadata only: ids, enums and counts. A request naming another actor in ``X-Understudy-Actor`` (page, model, tool ...) or coming from a
foreign origin is refused with 403 and the refusal is audited without any content.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from .. import http_guard
from . import paths as P
from . import vocab as V
from .events import STATE_FIELDS, EventError, parse_event
from .paths import FLAG, enabled
from .service import AttentionService
from .state import parse_state
from .store import AttentionStore

__all__ = ["router", "enabled", "FLAG"]

router = APIRouter(tags=["attention"])
_lock = threading.RLock()
_WORKER = ("worker", "worker_approval")
_PRODUCERS = _WORKER + ("system", "agent", "desktop")
_default: dict[str, AttentionService] = {}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if not enabled():
        return _error(404, "extension_off", f"Attention is off. Set {FLAG}=1 (or the master UNDERSTUDY_X=1) to turn it on.")
    return None


def _clean(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _audit(note: str) -> None:
    line = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "actor": "system", "kind": "attention_write_refused", "routine": None,
            "run_id": None, "tier": None, "outcome": "refused", "note": note[:120]}
    try:
        p = P.data_dir() / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def _guard(request: Request, allowed: tuple[str, ...] = _WORKER) -> JSONResponse | None:
    actor = http_guard.actor_of(request)
    origin = request.headers.get("origin")
    if actor not in allowed:
        _audit(f"actor {_clean(actor)} on {request.url.path}")
        return _error(403, "write_refused", f"The actor {_clean(actor)!r} cannot do this to the attention layer.")
    if origin is not None and not http_guard.origin_allowed(origin):
        _audit(f"origin {_clean(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def get_service(request: Request) -> AttentionService:
    svc = getattr(request.app.state, "attention", None)
    if svc is None:
        key = str(P.data_dir())
        if key not in _default:
            _default[key] = AttentionService(AttentionStore(P.state_path(), P.log_path()))
        svc = _default[key]
    return svc


def _person(person: str | None) -> str | None:
    if person:
        return person
    try:
        from .. import routes_handoff as rh

        pid, _ = rh._resolve(None)
        if pid:
            return pid
    except Exception:
        pass
    return None


def _meta(origin: str = "real", n: int = 0, note: str | None = None) -> dict[str, Any]:
    return {"origin": origin, "n": n, "n_unit": "items", "interval_level": None, "note": note,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _now(svc: AttentionService, t: float | None) -> float:
    """A client's own clock is honoured only in mock mode (replays); a real server uses its own."""
    return float(t) if t is not None and P.is_mock() else svc.clock()


# ------------------------------------------------------------------------------------------------ routes
@router.post("/attention/events")
def post_event(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request, _PRODUCERS)) is not None:
        return r
    svc = get_service(request)
    try:
        state_in = body.get("state")
        if state_in is not None and (not isinstance(state_in, dict) or set(state_in) - set(STATE_FIELDS)):
            raise EventError("invalid_event", "state carries only the worker-state flags and numbers.")
        data = {k: v for k, v in body.items() if k != "state"}
        pid = person or data.get("person") or _person(None)
        ev = parse_event(data, person=pid)
        if not P.is_mock():
            from dataclasses import replace
            ev = replace(ev, t=None)
        t = _now(svc, ev.t)
        ws = parse_state(state_in, t, svc.p) if state_in else None
        with _lock:
            return svc.submit(ev, ws, now=t)
    except EventError as exc:
        return _error(422, exc.code, exc.message)


@router.get("/attention/next")
def get_next(request: Request, person: str | None = Query(None), t: float | None = Query(None), now: float | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    svc = get_service(request)
    q = dict(request.query_params)
    if q.get("peek", "").lower() in ("1", "true", "yes"):
        with _lock:
            return {"meta": _meta(note="A peek delivers nothing."), "data": svc.peek(pid, _now(svc, now))}
    if "typing" in q and "typing_burst" not in q:
        q["typing_burst"] = q["typing"]
    clock = _now(svc, now)
    ws = parse_state(q, clock, svc.p)
    with _lock:
        data = svc.next(pid, ws)
    return {"meta": _meta(note="At most one item; the badges are passive counts."), "data": data}


@router.get("/attention/digest")
def get_digest(request: Request, person: str | None = Query(None), kind: str = Query("now"), now: float | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if kind not in V.DIGEST_KINDS:
        return _error(422, "invalid_request", f"kind must be one of {', '.join(V.DIGEST_KINDS)}.")
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    svc = get_service(request)
    with _lock:
        return {"meta": _meta(note="Counts and fixed lines only."), "data": svc.digest(pid, kind, _now(svc, now))}


@router.post("/attention/feedback")
def post_feedback(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    svc = get_service(request)
    pid = person or body.get("person") or _person(None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    secs = body.get("seconds")
    try:
        with _lock:
            out = svc.feedback(str(pid), str(body.get("item_id", "")), str(body.get("event", "")), None if secs is None else float(secs))
    except EventError as exc:
        return _error(404 if exc.code == "unknown_item" else 422, exc.code, exc.message)
    except (TypeError, ValueError):
        return _error(422, "invalid_request", "seconds must be a number.")
    return out


@router.get("/attention/why")
def get_why(request: Request, item: str = Query(...)):
    if (r := _off()) is not None:
        return r
    with _lock:
        d = get_service(request).why(item)
    if d is None:
        return _error(404, "unknown_item", "There is no such item.")
    return {"meta": _meta(note="The reason is a fixed line, not model text."), "data": d}


@router.get("/attention/settings")
def get_settings(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    with _lock:
        return {"meta": _meta(), "data": get_service(request).get_settings(pid)}


@router.post("/attention/settings")
def post_settings(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    pid = person or body.get("person") or _person(None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    extra = sorted(set(body) - {"person", "modes", "budget_per_day", "level_glance", "reset_learned"})
    if extra:
        return _error(422, "invalid_setting", f"Unknown setting {extra[0]!r}.")
    try:
        with _lock:
            return {"meta": _meta(), "data": get_service(request).set_settings(
                str(pid), modes=body.get("modes"), budget_per_day=body.get("budget_per_day"), level_glance=body.get("level_glance"),
                reset_learned=body.get("reset_learned"))}
    except EventError as exc:
        return _error(422, exc.code, exc.message)


@router.get("/attention/stats")
def get_stats(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    with _lock:
        return {"meta": _meta(), "data": get_service(request).stats(pid)}


@router.get("/attention/export")
def get_export(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    with _lock:
        doc = get_service(request).store.export(pid)
    return JSONResponse(content=doc, headers={"Content-Disposition": 'attachment; filename="attention.json"'})


@router.delete("/attention")
def delete_state(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    with _lock:
        n = get_service(request).store.delete(pid)
    return {"deleted": n}
