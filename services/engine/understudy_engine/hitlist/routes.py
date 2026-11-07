"""Hit list routes: the repeated work the worker has done many times by hand and could hand over. ``api/app.py`` includes ``router``
only when this module imports and ``enabled()`` is true (``UNDERSTUDY_X_HITLIST=1`` or the master ``UNDERSTUDY_X=1``).

    GET  /hitlist?person=&window=7|30[&now=ISO]   {meta, data: {state, message, window_days, window_from, window_to, counting_since,
                                                  episodes_in_window, rows[<=10], automated[], hidden[], held_back[], not_shown, total}}
    POST /hitlist/hide    {id, window?}           the worker hides one row; it stays hidden until its count has doubled   (worker actor)
    POST /hitlist/unhide  {id}                    the worker brings a hidden row back                                      (worker actor)
    POST /hitlist/reset                           start counting again: clears the hit list counts and hidden marks only   (worker actor)
    GET  /hitlist/firm?window=7|30[&role=]        {meta, data}: the same list across the synthetic firm, an aggregate; a group
                                                  under 5 people is not listed; no person is named or ranked

Row: ``{id, label, key, family, count, minutes_per_week:{point,lo,hi}, judgement_share, status, stops_before, variation, variants,
overlaps[], seconds_per_time, t, actions:{routine_id, can_automate, card_id}, what, touches[], never[]}``. ``status`` is one of
candidate | proposed | learning | running | automated; ``stops_before`` one of none | submit | payment | message | delete | share | release.

Nothing here calls a model or the network. A write is the worker's own action: a request naming another actor in
``X-Understudy-Actor`` (page, agent, model, tool ...) or coming from an origin other than the worker's own app is refused with 403, and the
refusal is audited without any content. Reset clears the hit list's own counters and nothing else (never events, episodes, routines,
consent, ledgers or the memory file), and writes one audit line with counts only.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from .. import http_guard
from . import service as S
from .firm import firm_hitlist
from .service import FLAG, WINDOWS, enabled
from .state import audit

__all__ = ["router", "enabled", "FLAG"]

router = APIRouter(tags=["hitlist"])
_lock = threading.RLock()
_WORKER = ("worker", "worker_approval")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _clean(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _guard(request: Request) -> JSONResponse | None:
    actor = http_guard.actor_of(request)
    origin = request.headers.get("origin")
    if actor not in _WORKER:
        audit("hitlist_write_refused", f"actor {_clean(actor)} on {request.url.path}", outcome="refused", actor="system")
        return _error(403, "write_refused", f"Only the worker can change the repeats list; the actor {_clean(actor)!r} cannot.")
    if origin is not None and not http_guard.origin_allowed(origin):
        audit("hitlist_write_refused", f"origin {_clean(origin)} on {request.url.path}", outcome="refused", actor="system")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def _window(w: int | None) -> int | JSONResponse:
    w = 7 if w is None else w
    if w not in WINDOWS:
        return _error(422, "bad_window", "window must be 7 or 30 (days).")
    return w


def _now(now: str | None) -> float | None | JSONResponse:
    if not now:
        return None
    try:
        d = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        return _error(422, "invalid_request", "now must be an ISO time such as 2026-11-08T08:00:00Z")
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


@router.get("/hitlist")
def get_hitlist(person: str | None = Query(None), window: int | None = Query(None), now: str | None = Query(None)):
    w = _window(window)
    if isinstance(w, JSONResponse):
        return w
    t = _now(now)
    if isinstance(t, JSONResponse):
        return t
    try:
        with _lock:
            res = S.compute(person, w, now=t)
    except S.UnknownPerson:
        return _error(404, "unknown_person", "No events for that person. Run onboarding first, or leave person out.")
    return {"meta": S.meta_for(res), "data": res.data}


@router.post("/hitlist/hide")
def post_hide(request: Request, body: dict[str, Any] = Body(...)):
    refused = _guard(request)
    if refused:
        return refused
    rid = str(body.get("id") or "")
    if not rid:
        return _error(422, "bad_request", "Send {id}.")
    w = _window(body.get("window") if isinstance(body.get("window"), int) else None)
    if isinstance(w, JSONResponse):
        return w
    try:
        with _lock:
            out = S.hide(body.get("person") if isinstance(body.get("person"), str) else None, rid, w)
    except KeyError:
        return _error(404, "unknown_row", "That row is not on the list any more. Reload the page.")
    except S.UnknownPerson:
        return _error(404, "unknown_person", "No events for that person.")
    audit("hitlist_hide", "one row hidden")
    return out


@router.post("/hitlist/unhide")
def post_unhide(request: Request, body: dict[str, Any] = Body(...)):
    refused = _guard(request)
    if refused:
        return refused
    rid = str(body.get("id") or "")
    if not rid:
        return _error(422, "bad_request", "Send {id}.")
    try:
        with _lock:
            ok = S.unhide(body.get("person") if isinstance(body.get("person"), str) else None, rid)
    except S.UnknownPerson:
        return _error(404, "unknown_person", "No events for that person.")
    if not ok:
        return _error(404, "unknown_row", "That row was not hidden.")
    audit("hitlist_unhide", "one row shown again")
    return {"shown": rid}


@router.post("/hitlist/reset")
def post_reset(request: Request, body: dict[str, Any] | None = Body(None)):
    refused = _guard(request)
    if refused:
        return refused
    try:
        with _lock:
            out = S.reset((body or {}).get("person") if isinstance((body or {}).get("person"), str) else None)
    except S.UnknownPerson:
        return _error(404, "unknown_person", "No events for that person.")
    c = out["cleared"]
    audit("hitlist_reset", f"cleared {c['counters']} counters and {c['hidden_marks']} hidden marks")
    return out


@router.get("/hitlist/firm")
def get_firm(window: int | None = Query(None), role: str | None = Query(None)):
    w = _window(window)
    if isinstance(w, JSONResponse):
        return w
    data, source = firm_hitlist(w, role)
    meta = {"origin": "synthetic", "n": data["people"], "n_unit": "people", "split": None, "interval_level": 0.95,
            "note": ("A synthetic firm of about 60 people in three roles, not real people. Totals add up what each role repeats; "
                     "a group of fewer than 5 people is not listed, and no person is named or ranked. For coaching and onboarding, "
                     "not for evaluating individuals."),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "firm_source": source}
    return {"meta": meta, "data": data}
