"""Privacy routes (PRV-2): the egress ledger and its summary. Owned by privacy-egress; ``api/app.py`` includes ``router``
only when this module imports AND ``UNDERSTUDY_X_PRIVACY=1`` or ``UNDERSTUDY_X=1`` (the routes also answer 404
``extension_off`` themselves when the flag is off, so a mistaken include cannot expose them).

  GET  /privacy/ledger?limit=        -> {meta, data: [{t, purpose, schema, fields, payload, model, bytes, ...}]} newest first
  GET  /privacy/ledger/export        -> the ledger as JSONL text (oldest first), to save
  POST /privacy/ledger/clear         -> {cleared, blocked_cleared, at}   (this machine, actor header ``worker``)
  GET  /privacy/summary              -> {meta, data: {calls, by_purpose, last_call, local_only_note, canary: {runs, planted, leaked}, ...}}
  GET  /privacy/purposes             -> {meta, data: [{purpose, schema, method, fields, bucketed, ...}]}  what may be sent, and in what shape

Nothing here calls a model. The ledger holds the payloads exactly as sent (numbers, codes, fixed ids); it never holds raw
source text because none can reach a ``SafePayload``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .privacy import flags, ledger
from .privacy.image import image_purposes
from .privacy.payload import purposes as registered_purposes

router = APIRouter(tags=["privacy"])

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_ALLOWED_ORIGIN_PREFIXES = ("http://localhost", "http://127.0.0.1", "https://localhost", "app://", "file://")
_FALLBACK_WORKER_ACTORS = frozenset({"worker", "worker_approval"})


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse | None:
    if flags.enabled("privacy"):
        return None
    return _error(404, "extension_off", "The privacy extension is off. Set UNDERSTUDY_X_PRIVACY=1 (or UNDERSTUDY_X=1) and restart the engine.")


def _meta(rows: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    """Ledger lines made in mock mode are synthetic; real calls are real; both present is mixed."""
    mock = sum(1 for r in rows if r.get("mock"))
    real = len(rows) - mock
    origin = "synthetic" if real == 0 else ("real" if mock == 0 else "mixed")
    try:
        from .core import AnalyticMeta

        return AnalyticMeta(origin=origin, n=len(rows), n_unit="runs", split=None, note=note,
                            generated_at=datetime.now(timezone.utc)).model_dump(mode="json")
    except Exception:  # pragma: no cover - core always imports; keep the route alive regardless
        return {"origin": origin, "n": len(rows), "n_unit": "runs", "split": None, "interval_level": 0.95, "note": note,
                "generated_at": datetime.now(timezone.utc).isoformat()}


def _write_guard(request: Request) -> JSONResponse | None:
    """Clearing the ledger is the worker's own action: from this machine, naming the worker actor, from the app."""
    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        return _error(403, "write_refused", "The ledger can only be cleared from this machine.")
    try:
        from .memory.store import WORKER_ACTORS as actors
    except Exception:  # pragma: no cover
        actors = _FALLBACK_WORKER_ACTORS
    actor = request.headers.get("x-understudy-actor", "worker").strip()
    if actor not in actors:
        return _error(403, "write_refused", f"Only the worker can clear the ledger; the actor {actor[:20]!r} cannot.")
    origin = request.headers.get("origin")
    if origin is not None and not origin.startswith(_ALLOWED_ORIGIN_PREFIXES):
        return _error(403, "write_refused", "Writes only come from the Understudy app on this machine.")
    return None


@router.get("/privacy/ledger")
def get_ledger(limit: int = Query(100, ge=1, le=1000)):
    if (r := _off()) is not None:
        return r
    rows = ledger.read(limit)
    note = ("Newest first. Each line is one call to a remote model with exactly the content sent. Lines marked mock were made "
            "in mock mode or with a test port and reached no model.")
    return {"meta": _meta(rows, note), "data": rows}


@router.get("/privacy/ledger/export")
def export_ledger():
    if (r := _off()) is not None:
        return r
    return PlainTextResponse(ledger.export_jsonl(), media_type="application/x-ndjson",
                             headers={"content-disposition": 'attachment; filename="egress_ledger.jsonl"'})


@router.post("/privacy/ledger/clear")
def clear_ledger(request: Request):
    if (r := _off()) is not None:
        return r
    if (g := _write_guard(request)) is not None:
        return g
    return ledger.clear()


@router.get("/privacy/summary")
def get_summary():
    if (r := _off()) is not None:
        return r
    data = ledger.summary()
    rows = ledger.read(None)
    return {"meta": _meta(rows, "Counts are from this machine's ledger only. The canary figures are from the last evaluation run."),
            "data": data}


@router.get("/privacy/purposes")
def get_purposes():
    if (r := _off()) is not None:
        return r
    rows = [p.public() for p in registered_purposes().values()] + [p.public() for p in image_purposes().values()]
    return {"meta": _meta([], "What each purpose is allowed to send. Free text is not possible in any of them."), "data": rows}
