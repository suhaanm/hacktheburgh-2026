"""Cue routes (CUE-3, CUE-6, CUE-7): the stuck-rescue decision, the assist ledger, the growth numbers. Off by default.

``api/app.py`` includes ``router`` only when ``enabled()`` (``UNDERSTUDY_X_CUE=1`` or the master ``UNDERSTUDY_X=1``). Every handler also
checks the flag itself and answers 404 ``extension_off`` when it is off. Plain JSON errors: ``{"error": {"code", "message"}}``.

    GET    /cue/next?person=&dry=&asked=&voice_ok=&denied=&away=&consent=&quiet_s=&typing=&proactivity=   {meta, data: CueDecision}
           mock mode only: &fixture=<name>&t=<seconds since progress>   (see cue/fixtures.py)
    POST   /cue/feedback    {episode_id, event: shown|accepted|dismissed|answered|resolved|abandoned|know_this, answer_id?|option_id?, seconds?}   (worker)
    POST   /cue/grounding   {for_step, found, chosen, available, box_2d, confidence, source}   latest grounding result for the person   (worker)
    POST   /cue/quiet       {minutes}   quiet for N minutes (the hotkey)   (worker)
    GET    /cue/ledger?person=&stream=&limit=      {meta, data: {rows, counts}}   rows newest first, enums and numbers only
    GET    /cue/ledger/export?person=              the same rows as one JSON document to save
    DELETE /cue/ledger?person=                     hard delete the person's rows, stored intent labels and the memory summary line   (worker)
    POST   /cue/offloaded   {person, role, stream, routine?, skill?, outcome, minutes}   one delegated or automation row   (worker or system)
    GET    /growth?person=&skill=                  {meta, data}: independence score with components, intervals, n, trend, offloaded work
    GET    /cue/reason?id=                         {id, text}: the fixed one-line why

Writes are the worker's own actions: a request naming another actor in ``X-Understudy-Actor`` or coming from a foreign origin is
refused with 403 and the refusal is audited without any content.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from .. import http_guard
from fastapi.responses import JSONResponse

from . import ledger as L
from . import paths as P
from .live import CueError, LiveCue
from .paths import FLAG, enabled
from .types import FEEDBACK_EVENTS, Grounding
from .vocab import REASONS

__all__ = ["router", "enabled", "FLAG"]

router = APIRouter(tags=["cue"])
_lock = threading.RLock()
_WORKER = ("worker", "worker_approval")
HOW = ("esc", "click", "timeout", "stale", "progress", "late", "superseded", "episode_end", "off", "quiet", "declined", "accepted_offer", "show_me")
_default: dict[str, LiveCue] = {}


# ------------------------------------------------------------------------------------------------ helpers
def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if not enabled():
        return _error(404, "extension_off", f"Cue is off. Set {FLAG}=1 (or the master UNDERSTUDY_X=1) to turn it on.")
    return None


def _clean(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _audit(note: str) -> None:
    line = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "actor": "system", "kind": "cue_write_refused", "routine": None,
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
        return _error(403, "write_refused", f"Only the worker can change Cue; the actor {_clean(actor)!r} cannot.")
    if origin is not None and not http_guard.origin_allowed(origin):
        _audit(f"origin {_clean(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def get_live(request: Request) -> LiveCue:
    live = getattr(request.app.state, "cue_live", None)
    if live is None:
        key = str(P.data_dir())
        if key not in _default:
            app = request.app
            _default[key] = LiveCue(brain_getter=lambda: getattr(app.state, "coach", None))
        live = _default[key]
    return live


def _person(request: Request, person: str | None) -> str | None:
    if person:
        return person
    try:
        from .. import routes_handoff as rh

        pid, _ = rh._resolve(None)
        if pid:
            return pid
    except Exception:
        pass
    known = get_live(request).ledger.persons()
    return known[0] if known else None


def _bool(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _meta(origin: str, n: int, note: str | None = None, split: str | None = None) -> dict[str, Any]:
    return {"origin": origin, "n": n, "n_unit": "occurrences", "split": split, "interval_level": 0.95,
            "note": note, "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _origin_of(rows: list[dict[str, Any]]) -> str:
    kinds = {r.get("origin") for r in rows}
    return "mixed" if len(kinds) > 1 else (next(iter(kinds)) if kinds else "synthetic")


# ------------------------------------------------------------------------------------------------ routes
@router.get("/cue/next")
def cue_next(request: Request, person: str | None = Query(None), dry: str = Query("0"), asked: str = Query("0"), voice_ok: str = Query("0"),
             denied: str = Query("0"), away: str = Query("0"), consent: str = Query("1"), quiet_s: float | None = Query(None),
             typing: str | None = Query(None), proactivity: str = Query("balanced"), fixture: str | None = Query(None), t: float = Query(0.0),
             now: float | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = person or _person(request, None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    try:
        with _lock:
            return get_live(request).next(pid, now=now, dry=_bool(dry), asked=_bool(asked), voice_ok=_bool(voice_ok), denied=_bool(denied), away=_bool(away),
                                          consent=_bool(consent), quiet_s=quiet_s, typing=None if typing is None else _bool(typing), proactivity=proactivity,
                                          fixture=fixture, fixture_t=t)
    except CueError as exc:
        return _error(exc.status, exc.code, exc.message)


@router.post("/cue/feedback")
def cue_feedback(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    event = str(body.get("event", ""))
    if event not in FEEDBACK_EVENTS:
        return _error(422, "bad_event", f"event must be one of {', '.join(FEEDBACK_EVENTS)}.")
    how = body.get("how")
    if how is not None and how not in HOW:
        return _error(422, "bad_how", f"how must be one of {', '.join(HOW)}.")
    pid = person or body.get("person") or get_live(request).person_of_episode(body.get("episode_id")) or _person(request, None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    secs = body.get("seconds")
    try:
        with _lock:
            return get_live(request).feedback(str(pid), event, episode_id=body.get("episode_id"), answer_id=body.get("answer_id") or body.get("option_id"),
                                              seconds=None if secs is None else float(secs), how=how)
    except CueError as exc:
        return _error(exc.status, exc.code, exc.message)
    except (TypeError, ValueError):
        return _error(422, "invalid_request", "seconds must be a number.")


@router.post("/cue/grounding")
def cue_grounding(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    pid = person or body.get("person") or _person(request, None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    box = body.get("box_2d")
    source = body.get("source", "none")
    if source not in ("dom", "vision", "none"):
        return _error(422, "invalid_request", "source must be dom, vision or none.")
    try:
        b = tuple(int(x) for x in box) if box else None
        if b is not None and (len(b) != 4 or any(not 0 <= x <= 1000 for x in b) or b[2] <= b[0] or b[3] <= b[1]):
            raise ValueError
        g = Grounding(found=bool(body.get("found")), chosen=body.get("chosen"), available=tuple(str(x) for x in (body.get("available") or [])),
                      box_2d=b, confidence=max(0.0, min(1.0, float(body.get("confidence", 0.0)))), source=source, for_step=body.get("for_step"))
    except (TypeError, ValueError):
        return _error(422, "invalid_request", "box_2d must be [y0, x0, y1, x1] on 0..1000 with positive size; confidence a number.")
    with _lock:
        get_live(request).set_grounding(str(pid), g)
    return {"person": pid, "stored": True, "ttl_s": 20}


@router.post("/cue/quiet")
def cue_quiet(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    try:
        minutes = float(body.get("minutes", 60))
    except (TypeError, ValueError):
        return _error(422, "invalid_request", "minutes must be a number.")
    if not 0 <= minutes <= 24 * 60:
        return _error(422, "invalid_request", "minutes must be between 0 and 1440.")
    pid = person or body.get("person") or _person(request, None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    with _lock:
        return get_live(request).quiet(str(pid), minutes)


@router.get("/cue/ledger")
def cue_ledger(request: Request, person: str | None = Query(None), stream: str | None = Query(None), limit: int = Query(200, ge=1, le=5000)):
    if (r := _off()) is not None:
        return r
    if stream is not None and stream not in ("assist", "delegated", "automation"):
        return _error(422, "invalid_request", "stream must be assist, delegated or automation.")
    live = get_live(request)
    pid = person or _person(request, None)
    rows = live.ledger.rows(pid, stream, limit=limit, newest_first=True)
    counts = live.ledger.counts(pid)
    return {"meta": _meta(_origin_of(rows), counts["assist"], "Enums and numbers only: no text, no screenshots. Delegated and automation rows are offloaded work and never enter the score."),
            "data": {"rows": rows, "counts": counts}}


@router.get("/cue/ledger/export")
def cue_ledger_export(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = person or _person(request, None)
    doc = get_live(request).ledger.export(pid)
    return JSONResponse(content=doc, headers={"Content-Disposition": 'attachment; filename="assist-ledger.json"'})


@router.delete("/cue/ledger")
def cue_ledger_delete(request: Request, person: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request)) is not None:
        return r
    with _lock:
        return get_live(request).delete_ledger(person or _person(request, None), actor="human")


@router.post("/cue/offloaded")
def cue_offloaded(request: Request, body: dict[str, Any] = Body(...)):
    if (r := _off()) is not None:
        return r
    if (r := _guard(request, _WORKER + ("system",))) is not None:
        return r
    try:
        stream = body.get("stream")
        if stream not in ("delegated", "automation"):
            raise L.LedgerError("stream must be delegated or automation")
        out = {"done": "clean", "queued": "abandoned", "failed": "error", "yielded": "abandoned"}.get(body.get("outcome"), None)
        if out is None:
            raise L.LedgerError("outcome must be done, queued, failed or yielded")
        now = datetime.now(timezone.utc).timestamp()
        row = L.make_row(person=str(body.get("person")), role=str(body.get("role")), skill=body.get("skill"), t=now, outcome=out,
                         origin=body.get("origin", "real"), stream=stream, routine=body.get("routine"),
                         minutes=None if body.get("minutes") is None else float(body["minutes"]), offload_outcome=body.get("outcome"),
                         origin_detail=body.get("origin_detail"), serial=int(now * 1000) % 100000)
        get_live(request).ledger.append(row)
    except L.LedgerError as exc:
        return _error(422, "invalid_request", str(exc))
    except (TypeError, ValueError):
        return _error(422, "invalid_request", "minutes must be a number.")
    return {"stored": True, "id": row["id"]}


@router.get("/cue/reason")
def cue_reason(id: str = Query(...)):
    if (r := _off()) is not None:
        return r
    text = REASONS.get(id)
    if text is None:
        return _error(404, "no_such_reason", f"There is no reason {id!r}.")
    return {"id": id, "text": text}


def _role_scope(pid: str, rows: list[dict[str, Any]], asked: str | None) -> tuple[str | None, dict[str, Any]]:
    """Which role's work Growth shows, and the roles the person has work under. Work done under one role is never mixed into another's score: the default is
    the current role (the profile's after a recorded role change, else the newest assist row's), and ``?role=`` reads an earlier one."""
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("stream") == "assist" and r.get("role"):
            e = seen.setdefault(str(r["role"]), {"role": str(r["role"]), "n": 0, "last": ""})
            e["n"] += 1
            e["last"] = max(e["last"], str(r.get("t_hour") or ""))
    newest = max(seen.values(), key=lambda e: e["last"])["role"] if seen else None
    current = newest
    try:
        from .. import routes_handoff as rh
        from ..memory import load_profile

        prof = load_profile(rh._mem()) or {}
        if prof.get("person") == pid and prof.get("history") and prof.get("role"):
            current = str(prof["role"])
    except Exception:
        pass
    shown = asked or current
    return shown, {"role": shown, "current": current, "viewing_earlier": bool(shown and current and shown != current),
                   "roles": sorted(seen.values(), key=lambda e: e["last"], reverse=True)}


@router.get("/growth")
def get_growth(request: Request, person: str | None = Query(None), skill: str | None = Query(None), now: float | None = Query(None),
               role: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    from . import score

    live = get_live(request)
    pid = person or _person(request, None)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    from .freshness import MAX_GROWTH_ROWS

    rows = live.ledger.rows(pid)[-MAX_GROWTH_ROWS:]
    shown, scope = _role_scope(pid, rows, role or None)
    if shown:
        rows = [r for r in rows if r.get("role") == shown]
    g = score.growth(rows, person=pid, skill=None if skill in (None, "", "overall") else skill, now=now)
    data = {k: v for k, v in g.items() if not k.startswith("_")}
    data["role"] = data.get("role") or shown
    data["role_scope"] = scope
    return {"meta": _meta(g["_origin"], g["_n"], g["_note"], g["_split"]), "data": data}
