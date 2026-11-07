"""Evidence routes (REQ-6). ``api/app.py`` includes ``router`` only when this module imports and ``enabled()`` is true
(``UNDERSTUDY_X_EVIDENCE=1`` or the master ``UNDERSTUDY_X=1``); the handlers also answer 404 ``extension_off`` when the flag is off.

    GET  /evidence/packet?person=&case=[&hazard=1]   {meta, data: {person, case, blocks, packet, facts, limitations}}
    POST /evidence/explain  {person?, case?, question?, include_packet?}   {meta, data: ExplainResult}   (worker actor)

The packet is the closed-schema object the explainer works from: numbers, intervals, ids and enums, no text. ``/evidence/explain``
answers with the words, the source that wrote them (``template`` | ``local`` | ``cloud``), the provenance check's verdict and the
coach actions chosen from the vetted menu. Mock mode (``UNDERSTUDY_MOCK=1``) uses the deterministic template only; the local model
is used when the local-model layer is on; the cloud wording only when ``UNDERSTUDY_EVIDENCE_CLOUD=1`` and then only through the
egress guard. Writes are the worker's own action: another actor in ``X-Understudy-Actor``, or a foreign origin, is refused with 403.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import explain as E
from . import intent as I
from . import vocab as V
from .packet import facts
from .sources import NoEvidence, Sources, build_packet

FLAG = "UNDERSTUDY_X_EVIDENCE"
router = APIRouter(tags=["evidence"])
_TRUE = ("1", "true", "yes", "on")
_WORKER = ("worker", "worker_approval")
_ALLOWED_ORIGIN_PREFIXES = ("http://localhost", "http://127.0.0.1", "https://localhost", "file://", "app://")


def enabled() -> bool:
    return any(os.environ.get(n, "").strip().lower() in _TRUE for n in ("UNDERSTUDY_X", FLAG))


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse:
    return _error(404, "extension_off", "The evidence layer is off. Set UNDERSTUDY_X_EVIDENCE=1 (or UNDERSTUDY_X=1) and restart the engine.")


def _guard(request: Request) -> JSONResponse | None:
    actor = request.headers.get("x-understudy-actor", "worker").strip()
    origin = request.headers.get("origin")
    if actor not in _WORKER:
        return _error(403, "write_refused", f"Only the worker can ask for an explanation; the actor {actor[:20]!r} cannot.")
    if origin is not None and not origin.startswith(_ALLOWED_ORIGIN_PREFIXES):
        return _error(403, "write_refused", "Writes only come from the worker's own app on this machine.")
    return None


def _sources(request: Request, compute_hazard: bool) -> Sources:
    over = getattr(request.app.state, "evidence_sources", None)          # tests and demos may install their own
    return over if over is not None else Sources.from_app(request.app, compute_hazard=compute_hazard)


def _meta(built, note: str) -> dict[str, Any]:
    m = built.packet.meta
    return {"origin": {"live": "real"}.get(m.origin, "synthetic"), "n": m.n,
            "n_unit": {"cases": "episodes"}.get(m.n_unit, m.n_unit), "split": m.split, "interval_level": m.level, "note": note,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}


class ExplainBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person: str | None = Field(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    case: str | None = Field(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    question: str | None = Field(None, max_length=I.MAX_QUESTION)
    include_packet: bool = False


@router.get("/evidence/packet")
def get_packet(request: Request, person: str | None = Query(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$"),
               case: str | None = Query(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$"), hazard: bool = Query(False)):
    if not enabled():
        return _off()
    try:
        built = build_packet(person, case, _sources(request, hazard))
    except NoEvidence as exc:
        return _error(404, exc.code, str(exc))
    pk = built.packet
    tab = facts(pk)
    data = {
        "person": built.person, "case": built.case, "blocks": built.blocks, "packet": pk.to_wire(),
        "facts": [{"path": p, "value": f.value, "unit": f.unit} for p, f in sorted(tab.facts.items())],
        "limitations": [{"id": i, "text": V.LIMITATIONS[i]} for i in pk.limitations],
    }
    return {"meta": _meta(built, "A packet of numbers, intervals and ids from the engine's analytics. It holds no text, names or paths."), "data": data}


@router.post("/evidence/explain")
def post_explain(request: Request, body: ExplainBody = Body(...)):
    if not enabled():
        return _off()
    refused = _guard(request)
    if refused:
        return refused
    try:
        built = build_packet(body.person, body.case, _sources(request, False))
    except NoEvidence as exc:
        return _error(404, exc.code, str(exc))
    try:
        out = E.explain(built.packet, body.question)
    except ValueError as exc:
        return _error(500, "packet_invalid", str(exc))
    out["person"], out["case"], out["blocks"] = built.person, built.case, built.blocks
    if body.include_packet:
        out["packet"] = built.packet.to_wire()
    note = {"template": "Words from the built-in template.", "local": "Words from the local model.", "cloud": "Words from the cloud model, sent through the egress guard."}[out["source"]]
    return {"meta": _meta(built, note + " Every number was checked against the packet; that proves it traces to the data, not that it is true."), "data": out}
