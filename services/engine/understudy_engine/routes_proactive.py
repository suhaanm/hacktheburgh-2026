"""Proactive intelligence routes (PRO-1, PRO-2): the morning briefing. ``api/app.py`` includes ``router`` only when this module
imports and ``UNDERSTUDY_X_PROACTIVE=1`` (or the master ``UNDERSTUDY_X=1``) is set; ``enabled()`` says which.

    GET  /briefing?person=              {meta, data: {cap, generated_at, cards: [Card]}}
    PUT  /briefing/{id}/prepared        the worker edits the content that will fire        (worker actor)
    POST /briefing/{id}/fire            the worker's press: {queue_id} or {run_id}          (worker actor)
    POST /briefing/{id}/dismiss         {mode?: "not_now" | "never"} ("reason" also accepted)  (worker actor)
    GET  /briefing/text?person=         {text}: counts and kinds only, safe to speak (additive)

Additive query parameters: ``refresh=1`` (make a new generation), ``include_stale=1`` (show dropped cards), ``now=ISO`` (replays).

Nothing here calls a model, and nothing fires on a read: GET prepares, only POST /fire acts. Writes are the worker's own
actions: a request naming another actor in ``X-Understudy-Actor`` (page, agent, model, tool ...) or coming from an origin
other than localhost is refused with 403, and the refusal is audited without the refused text.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from .proactive import briefing as B
from .proactive import fire as F
from .proactive.briefing import briefing_text, summary_text  # noqa: F401  (briefing_text is part of this module's surface)
from .proactive.cards import iso
from .proactive.paths import data_dir, enabled
from .proactive.reword import default_reword_why
from .proactive.sources import Readers
from .proactive.store import BriefingStore

__all__ = ["router", "enabled", "briefing_text", "FLAG"]

FLAG = "UNDERSTUDY_X_PROACTIVE"
router = APIRouter(tags=["proactive"])
_lock = threading.RLock()
_ALLOWED_ORIGIN_PREFIXES = ("http://localhost", "http://127.0.0.1", "https://localhost", "file://", "app://")
_WORKER = ("worker", "worker_approval")


# ------------------------------------------------------------------------------------------------ helpers
def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}, **extra})


def _clean(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _audit(note: str) -> None:
    line = {"t": iso(datetime.now(timezone.utc)), "actor": "system", "kind": "briefing_write_refused", "routine": None, "run_id": None,
            "tier": None, "outcome": "refused", "note": note[:120]}
    try:
        p = data_dir() / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line) + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def _guard(request: Request) -> JSONResponse | None:
    """Only the worker's own UI writes: anything naming another actor, or from a foreign origin, is refused."""
    actor = request.headers.get("x-understudy-actor", "worker").strip()
    origin = request.headers.get("origin")
    if actor not in _WORKER:
        _audit(f"actor {_clean(actor)} on {request.url.path}")
        return _error(403, "write_refused", f"Only the worker can change or press a briefing card; the actor {_clean(actor)!r} cannot.")
    if origin is not None and not origin.startswith(_ALLOWED_ORIGIN_PREFIXES):
        _audit(f"origin {_clean(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def _now(now: str | None) -> datetime | None:
    if not now:
        return None
    try:
        d = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("now must be an ISO time such as 2026-11-08T08:00:00Z")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _agents_on() -> bool:
    return os.environ.get("UNDERSTUDY_X", "").strip().lower() in ("1", "true", "yes", "on") or \
        os.environ.get("UNDERSTUDY_X_AGENTS", "").strip().lower() in ("1", "true", "yes", "on")


def _person(person: str | None) -> str | None:
    if person:
        return person
    try:
        from . import routes_handoff as rh

        pid, _ = rh._resolve(None)
        if pid:
            return pid
    except Exception:
        pass
    known = BriefingStore().persons()
    return known[0] if known else None


def _origin(person: str) -> str:
    try:
        from . import routes_handoff as rh

        return rh._src().persons().get(person, "synthetic")
    except Exception:
        return "synthetic"


def _meta(origin: str, b: B.Briefing) -> dict[str, Any]:
    n = sum(int(v.get("n") or 0) for v in b.diagnostics.values())
    return {"origin": origin, "n": n, "n_unit": "decisions", "split": None, "interval_level": 0.95,
            "note": ("Cards are chosen by fixed rules from routines, skills, calendar and git summaries, and re-checked against the current state. "
                     "No model decides what is shown, and nothing runs until you press go."
                     + (" Built from synthetic data." if origin != "real" else "")),
            "generated_at": iso(datetime.now(timezone.utc))}


# ------------------------------------------------------------------------------------------------ routes
@router.get("/briefing")
def get_briefing(person: str | None = Query(None), refresh: int = Query(0), include_stale: int = Query(0), now: str | None = Query(None)):
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Run onboarding first, or pass ?person=.")
    try:
        t = _now(now)
    except ValueError as exc:
        return _error(422, "invalid_request", str(exc))
    with _lock:
        b = B.build(pid, store=BriefingStore(), readers=Readers(), now=t, force=bool(refresh), allow_http=_agents_on(), origin=_origin(pid),
                    reword_why=default_reword_why())
        cards = b.cards
        if include_stale:
            cards = cards + [c for c in BriefingStore().cards(pid) if c.status == "stale"]
    data = {"cap": 3, "generated_at": b.generated_at, "cards": [c.to_contract() for c in cards],
            "dropped": b.dropped, "sources": {k: {"available": v.get("available"), "n": v.get("n")} for k, v in b.diagnostics.items()},
            "person": pid}
    return {"meta": _meta(_origin(pid), b), "data": data}


@router.get("/briefing/text")
def get_briefing_text(person: str | None = Query(None), now: str | None = Query(None)):
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Run onboarding first, or pass ?person=.")
    try:
        t = _now(now)
    except ValueError as exc:
        return _error(422, "invalid_request", str(exc))
    with _lock:
        return {"text": briefing_text(pid, store=BriefingStore(), readers=Readers(), now=t)}


@router.put("/briefing/{card_id}/prepared")
def put_prepared(card_id: str, request: Request, body: dict[str, Any] = Body(...)):
    refused = _guard(request)
    if refused:
        return refused
    prepared = body.get("prepared", body)
    with _lock:
        try:
            card = B.edit_prepared(card_id, prepared, actor="worker", store=BriefingStore())
        except B.EditError as exc:
            return _error(exc.status, exc.code, exc.message)
    return {"id": card["id"], "prepared": card["prepared"], "edited": card["edited"], "prepared_hash": card["prepared_hash"], "card": card}


@router.post("/briefing/{card_id}/fire")
def post_fire(card_id: str, request: Request, body: dict[str, Any] | None = Body(None)):
    refused = _guard(request)
    if refused:
        return refused
    with _lock:
        try:
            out = F.fire(card_id, actor="worker", store=BriefingStore(), readers=Readers(), allow_http=_agents_on())
        except F.FireError as exc:
            return _error(exc.status, exc.code, exc.message, **exc.extra)
    return out


@router.post("/briefing/{card_id}/dismiss")
def post_dismiss(card_id: str, request: Request, body: dict[str, Any] | None = Body(None)):
    refused = _guard(request)
    if refused:
        return refused
    mode = str((body or {}).get("mode") or (body or {}).get("reason") or "not_now")
    with _lock:
        try:
            return F.dismiss(card_id, actor="worker", store=BriefingStore(), mode=mode)
        except F.FireError as exc:
            return _error(exc.status, exc.code, exc.message, **exc.extra)
