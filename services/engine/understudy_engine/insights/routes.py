"""Insights routes (REQ-9): a few pointers for the worker, granular detail for the admin. Off by default.

``api/app.py`` includes ``router`` only when ``enabled()`` (``UNDERSTUDY_X_INSIGHTS=1`` or the master ``UNDERSTUDY_X=1``). Every handler also
checks the flag and answers 404 ``extension_off`` when it is off. Plain JSON errors: ``{"error": {"code", "message"}}``.

    GET  /insights/worker?person=            worker   up to 3 pointers (fixed-template text, no statistics), status, week, monday_note
    GET  /insights/admin/overview            admin    up to 7 insights with effect, interval, n and a drill link; coverage; risk; role comparison summary
    GET  /insights/admin/roles               admin    experts versus juniors per role with intervals, per-habit decomposition, tenure bands
    GET  /insights/admin/firm                admin    users grouped by role: counts, trend classes, aggregate intervals, per-user rows (numbers and enums)
    GET  /insights/admin/onboarding          admin    time to independence by role: Kaplan-Meier and learning curve, target labelled a design target
    GET  /insights/admin/drill?insight=      admin    granular tables and series for one insight
    GET  /insights/why?insight=[&person=]    either   selected or suppressed, a fixed reason code and sentence (the caller's own audience)
    POST /insights/feedback                  either   {insight, event: useful|not_useful|dismissed|done|never_show|hide_kind|show_kind, person?}: only quieter
    GET  /insights/sharing?person=           worker   read-only: what an admin can see about this worker, since when, to whom, and the exact row

The ADMIN role: ``x-understudy-role: admin`` is accepted ONLY together with the per-boot token in ``x-understudy-token`` (the one the release
routes use; Auth0 roles come later). An admin header without a valid token is refused (403 ``admin_token_required``); an admin route
without the admin header is refused (403 ``admin_only``). The worker route never returns admin-granularity data, whatever header it gets.
``?source=firm|local`` picks the data: the synthetic firm (the default under ``UNDERSTUDY_MOCK=1``) or this device's own ledger.

Writes (feedback) come from the worker's own app: another actor or a foreign origin is refused, audited without content.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from .. import http_guard
from . import paths as P
from . import vocab as V
from .paths import FLAG, enabled
from .service import InsightsService, UnknownPerson
from .store import InsightsStore

__all__ = ["router", "enabled", "FLAG"]

router = APIRouter(tags=["insights"])
_lock = threading.RLock()
_WORKER = ("worker", "worker_approval")
_default: dict[str, InsightsService] = {}
ROLE_HEADER = "x-understudy-role"


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if not enabled():
        return _error(404, "extension_off", f"Insights are off. Set {FLAG}=1 (or the master UNDERSTUDY_X=1) to turn them on.")
    return None


def _audit(note: str) -> None:
    line = {"t": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "actor": "system", "kind": "insights_refused", "routine": None, "run_id": None,
            "tier": None, "outcome": "refused", "note": note[:120]}
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


def _clean(a: str) -> str:
    return "".join(ch for ch in a if ch.isalnum() or ch in "-_.:")[:24] or "unknown"


def _actor_header(request: Request) -> str:
    return (request.headers.get(http_guard.ACTOR_HEADER) or "").strip()


def _actor_refused(request: Request) -> JSONResponse | None:
    """An agent, a model, a tool or any other non-worker actor never reads per-user firm data, even with the token: a script that holds the token is not a person.
    No actor header at all is allowed (the dashboard's reads send none)."""
    actor = _actor_header(request)
    if actor and actor not in _WORKER:
        _audit(f"actor {_clean(actor)} refused as admin on {request.url.path}")
        return _error(403, "admin_actor_refused", f"The actor {_clean(actor)!r} cannot use the admin views. They are for a person with the Admin role.")
    return None


def is_admin(request: Request) -> bool:
    """True only for the admin header WITH a valid per-boot token and no non-worker actor. A bad token is not an admin."""
    if (request.headers.get(ROLE_HEADER) or "").strip().lower() != "admin":
        return False
    return http_guard.token_ok(request.headers.get(http_guard.TOKEN_HEADER)) and _actor_refused(request) is None


def _admin_gate(request: Request) -> JSONResponse | None:
    role = (request.headers.get(ROLE_HEADER) or "").strip().lower()
    if role != "admin":
        return _error(403, "admin_only", "This view is for the Admin role.")
    if not http_guard.token_ok(request.headers.get(http_guard.TOKEN_HEADER)):
        _audit(f"admin role without a valid token on {request.url.path}")
        return _error(403, "admin_token_required", "The admin role needs the per-boot token in x-understudy-token (see data/.token).")
    return _actor_refused(request)


#: The one admin gate of the engine (role header + per-boot token + a person, never an agent). Every route that returns firm data uses it: the Admin insights here, and the
#: firm's repeated work in ``hitlist.routes``.
admin_gate = _admin_gate


def _acts_as_admin(request: Request) -> JSONResponse | None:
    """For the routes that serve either audience: a request that claims the admin role with the token but a non-worker actor is refused, not quietly served as a worker."""
    if (request.headers.get(ROLE_HEADER) or "").strip().lower() == "admin" and http_guard.token_ok(request.headers.get(http_guard.TOKEN_HEADER)):
        return _actor_refused(request)
    return None


def _write_guard(request: Request) -> JSONResponse | None:
    actor = http_guard.actor_of(request)
    origin = request.headers.get("origin")
    if actor not in _WORKER:
        _audit(f"actor {_clean(actor)} on {request.url.path}")
        return _error(403, "write_refused", f"The actor {_clean(actor)!r} cannot give feedback on insights.")
    if origin is not None and not http_guard.origin_allowed(origin):
        _audit(f"origin {_clean(origin)} on {request.url.path}")
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def get_service(request: Request) -> InsightsService:
    svc = getattr(request.app.state, "insights", None)
    if svc is None:
        key = str(P.data_dir())
        if key not in _default:
            _default[key] = InsightsService(InsightsStore(P.state_path()))
        svc = _default[key]
    return svc


def _source(source: str | None, audience: str = "worker") -> str:
    """Which data a request reads.

    * Admin routes: ``?source=`` wins; otherwise the firm, when the data directory holds a built firm (the seed writes ``<data>/firm/``) or under ``UNDERSTUDY_MOCK=1``;
      otherwise this device's own ledger (``local``: one person, so the comparisons say they have nothing to compare).
    * Worker routes (the worker's own page): the worker's own ledger. Outside mock mode the firm is never served here, whatever ``?source=`` says, so a worker view cannot be
      pointed at the firm's people. Under mock mode the example firm answers (and stands in for a profile it does not hold), as before.
    """
    if audience == "admin":
        if source in ("firm", "local"):
            return source
        from . import firmstore as FS

        return "firm" if (P.is_mock() or FS.has_firm(P.data_dir())) else "local"
    if P.is_mock():
        return source if source in ("firm", "local") else "firm"
    return "local"


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


def _meta(svc: InsightsService, source: str, *, n: int = 0, n_unit: str = "people", interval: bool = True, note: str | None = None, audience: str = "admin") -> dict[str, Any]:
    snap = svc.snapshot(source)
    return {"origin": snap.origin, "badge": snap.badge, "n": n, "n_unit": n_unit, "interval_level": 0.95 if interval else None, "note": note, "source": source,
            "audience": audience, "as_of": datetime.fromtimestamp(snap.now, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_at": datetime.fromtimestamp(svc.clock(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}


NOTE_ADMIN = "For coaching and onboarding, not for evaluating individuals. Groups under 5 people are not compared."


STAND_IN_NOTE = "This profile has no recorded days yet."


def _identity_role(pid: str) -> str | None:
    """The role of a profile the engine itself knows (it has events for them, or they are the engine's default identity); None for anyone else."""
    try:
        from .. import routes_handoff as rh

        _p, data = rh._resolve(pid)
        if data is not None:
            return str(getattr(data, "role", "") or "benefits-processor")
        d_pid, d_data = rh._resolve(None)
        if d_pid == pid:
            return str(getattr(d_data, "role", "") or "benefits-processor") if d_data is not None else "benefits-processor"
    except Exception:
        return None
    return None


def _target(svc: InsightsService, src: str, pid: str) -> tuple[str, str | None]:
    """``(person to serve, stand-in label or None)``. In MOCK mode only, a profile that is not in the synthetic firm but that the engine knows (its identity) is served from a
    fixed stand-in member of the same role, so the worker's page shows an example week instead of "unknown person". Never outside mock mode (the 404 stays), never for admin."""
    if not (P.is_mock() and src == "firm"):
        return pid, None
    try:
        if any(p.id == pid for p in svc.snapshot(src).people):
            return pid, None
        role = _identity_role(pid)
        if role is None:
            return pid, None
        firm_roles = {p.role for p in svc.snapshot(src).people}
        sid, label = svc.stand_in(role if role in firm_roles else "benefits-processor", src)
    except Exception:
        return pid, None
    return sid, label


# ------------------------------------------------------------------------------------------------ worker
@router.get("/insights/worker")
def get_worker(request: Request, person: str | None = Query(None), source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    svc, src = get_service(request), _source(source)
    eff, label = _target(svc, src, pid)
    try:
        with _lock:
            data = svc.worker(eff, src)
    except UnknownPerson:
        return _error(404, "unknown_person", "There is no such person in this data.")
    note = "A few pointers, chosen by fixed rules and worded from fixed sentences. No statistics are shown here."
    if label is not None:
        data = {**data, "person": pid, "stand_in": True, "stand_in_label": label}
        note = STAND_IN_NOTE
    return {"meta": _meta(svc, src, n=len(data["pointers"]), n_unit="pointers", interval=False, audience="worker", note=note), "data": data}


# ------------------------------------------------------------------------------------------------ admin
@router.get("/insights/admin/overview")
def get_overview(request: Request, source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _admin_gate(request)) is not None:
        return r
    svc, src = get_service(request), _source(source, "admin")
    with _lock:
        data = svc.overview(src)
    return {"meta": _meta(svc, src, n=data["firm"]["users"], note=NOTE_ADMIN), "data": data}


@router.get("/insights/admin/roles")
def get_roles(request: Request, source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _admin_gate(request)) is not None:
        return r
    svc, src = get_service(request), _source(source, "admin")
    with _lock:
        data = svc.roles(src)
    return {"meta": _meta(svc, src, n=sum(x["n_expert"] + x["n_junior"] for x in data["roles"]), note=NOTE_ADMIN), "data": data}


@router.get("/insights/admin/firm")
def get_firm(request: Request, source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _admin_gate(request)) is not None:
        return r
    svc, src = get_service(request), _source(source, "admin")
    with _lock:
        data = svc.firm(src)
    return {"meta": _meta(svc, src, n=data["totals"]["users"], note=NOTE_ADMIN), "data": data}


@router.get("/insights/admin/onboarding")
def get_onboarding(request: Request, source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _admin_gate(request)) is not None:
        return r
    svc, src = get_service(request), _source(source, "admin")
    with _lock:
        data = svc.onboarding(src)
    return {"meta": _meta(svc, src, n=sum(x["n"] for x in data["roles"]), note="The target line is a design target the firm sets, not a measured standard. " + NOTE_ADMIN), "data": data}


@router.get("/insights/admin/drill")
def get_drill(request: Request, insight: str = Query(...), source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _admin_gate(request)) is not None:
        return r
    svc, src = get_service(request), _source(source, "admin")
    with _lock:
        data = svc.drill(src, insight)
    if data is None:
        return _error(404, "unknown_insight", V.REASON_TEXT["unknown_insight"])
    return {"meta": _meta(svc, src, n=0, note=NOTE_ADMIN), "data": data}


# ------------------------------------------------------------------------------------------------ either audience
@router.get("/insights/why")
def get_why(request: Request, insight: str = Query(...), person: str | None = Query(None), source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _acts_as_admin(request)) is not None:
        return r
    svc = get_service(request)
    audience = "admin" if is_admin(request) else "worker"
    src = _source(source, audience)
    pid = _person(person) if audience == "worker" else None
    if audience == "worker" and not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    label = None
    if audience == "worker" and pid:
        pid, label = _target(svc, src, pid)
    try:
        with _lock:
            data = svc.why(insight, audience=audience, source=src, person=pid)
    except UnknownPerson:
        return _error(404, "unknown_person", "There is no such person in this data.")
    if data is None:
        return _error(404, "unknown_insight", V.REASON_TEXT["unknown_insight"])
    note = "The reason is a fixed sentence, not model text."
    if label is not None:
        data = {**data, "stand_in": True, "stand_in_label": label}
        note = STAND_IN_NOTE
    return {"meta": _meta(svc, src, interval=False, audience=audience, note=note), "data": data}


@router.post("/insights/feedback")
def post_feedback(request: Request, body: dict[str, Any] = Body(...), person: str | None = Query(None), source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    if (r := _write_guard(request)) is not None:
        return r
    insight, event = str(body.get("insight", "")), str(body.get("event", ""))
    if event not in V.FEEDBACK_EVENTS:
        return _error(422, "invalid_event", f"event must be one of {', '.join(V.FEEDBACK_EVENTS)}.")
    svc = get_service(request)
    audience = "admin" if is_admin(request) else "worker"
    src = _source(source or body.get("source"), audience)
    pid = _person(person or body.get("person")) if audience == "worker" else None
    if audience == "worker" and not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    label = None
    if audience == "worker" and pid:
        pid, label = _target(svc, src, pid)
    try:
        with _lock:
            out = svc.feedback(insight, event, audience=audience, source=src, person=pid)
    except UnknownPerson:
        return _error(404, "unknown_person", "There is no such person in this data.")
    if out is None:
        return _error(404, "unknown_insight", V.REASON_TEXT["unknown_insight"])
    return {**out, "stand_in": True} if label is not None else out


@router.get("/insights/sharing")
def get_sharing(request: Request, person: str | None = Query(None), source: str | None = Query(None)):
    if (r := _off()) is not None:
        return r
    actor = _actor_header(request)
    if actor and actor not in _WORKER:                      # the page holds the exact per-user row an admin sees: only the worker's own app reads it
        _audit(f"actor {_clean(actor)} refused on {request.url.path}")
        return _error(403, "worker_actor_required", "Only the worker's own app can read what their admin can see.")
    pid = _person(person)
    if not pid:
        return _error(404, "unknown_person", "No person is set up yet. Pass ?person=.")
    svc, src = get_service(request), _source(source)
    eff, label = _target(svc, src, pid)
    try:
        with _lock:
            data = svc.sharing(eff, src)
    except UnknownPerson:
        return _error(404, "unknown_person", "There is no such person in this data.")
    note = "Read-only: this is exactly what an admin sees about you."
    if label is not None:
        data = {**data, "person": pid, "stand_in": True, "stand_in_label": label}
        note = STAND_IN_NOTE
    return {"meta": _meta(svc, src, n=1, n_unit="people", interval=False, audience="worker", note=note), "data": data}
