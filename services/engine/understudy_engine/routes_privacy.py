"""Privacy routes (PRV-2): the egress ledger and its summary. Owned by privacy-egress; ``api/app.py`` includes ``router``
only when this module imports AND ``UNDERSTUDY_X_PRIVACY=1`` or ``UNDERSTUDY_X=1`` (the routes also answer 404
``extension_off`` themselves when the flag is off, so a mistaken include cannot expose them).

  GET  /privacy/ledger?limit=        -> {meta, data: [{t, purpose, schema, fields, payload, model, bytes, ...}]} newest first
  GET  /privacy/ledger/export        -> the ledger as JSONL text (oldest first), to save
  POST /privacy/ledger/clear         -> {cleared, blocked_cleared, at}   (this machine, actor header ``worker``)
  GET  /privacy/summary              -> {meta, data: {calls, by_purpose, last_call, local_only_note, canary: {runs, planted, leaked}, ...}}
  GET  /privacy/purposes             -> {meta, data: [{purpose, schema, method, fields, bucketed, ...}]}  what may be sent, and in what shape
  POST /privacy/ledger/live          -> {allowed, status, reason, ledger_id}   a batch of live frames sent from the Electron main process
  POST /privacy/ledger/live/result   -> {ledger_id, status}                   the result of a batch that was announced first

Nothing here calls a model. The ledger holds the payloads exactly as sent (numbers, codes, fixed ids); it never holds raw
source text because none can reach a ``SafePayload``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .privacy import flags, ledger
from .privacy.image import MAX_BYTES, MAX_LONG_EDGE, ImageGate, frame_request_problem, image_purposes
from .privacy.payload import purposes as registered_purposes

router = APIRouter(tags=["privacy"])


def enabled() -> bool:
    """The app asks this module too: the router is served only while the privacy flag is on."""
    return flags.enabled("privacy")

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


# ----------------------------------------------------------------------------------------------------- live frame batches
LIVE_PURPOSE = "live.frame_batch"
MAX_LIVE_BODY = 4096                  # bytes: far too small to carry a frame, an audio clip or a transcript
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")


class LiveGate(BaseModel):
    """The gate results the Electron main process computed for this batch (see ``image.ImageGate``)."""

    model_config = ConfigDict(extra="forbid", strict=True)
    consent: bool
    denylisted_app: bool
    secure_input: bool
    unattended: bool


class LiveBatch(BaseModel):
    """What the Live agent reports about a batch of frames it streams to a provider from the main process. No frame, no audio, no
    transcript and no text of any kind can be sent here: every field is a number, a bool, a fixed enum, a 16-hex hash or a model id."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    count: int = Field(ge=1, le=1000)                    # frames in the batch
    bytes: int = Field(ge=1, le=1000 * MAX_BYTES)        # total bytes sent for the batch
    sha8: str = Field(pattern=r"^[0-9a-f]{16}$")         # first 8 bytes of the SHA-256 of the FIRST frame
    width: int = Field(ge=1, le=MAX_LONG_EDGE)           # of the first frame
    height: int = Field(ge=1, le=MAX_LONG_EDGE)
    model: str
    source: str
    gate: LiveGate
    provider: str = "gemini"
    latency_ms: int | None = Field(default=None, ge=0, le=3_600_000)    # None: announced before sending, result to follow
    ok: bool | None = None
    input_tokens: int | None = Field(default=None, ge=0, le=10**9)
    output_tokens: int | None = Field(default=None, ge=0, le=10**9)
    cost_estimate_usd: float | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _checks(self) -> "LiveBatch":
        if self.source not in ("real_screen", "sandbox"):
            raise ValueError("source must be real_screen or sandbox")
        if self.provider not in ("gemini", "openai"):
            raise ValueError("provider must be gemini or openai")
        if not _MODEL.match(self.model):
            raise ValueError("model must be a model id (letters, digits, dots, colons, dashes)")
        from .privacy.patterns import scan_text

        if scan_text(self.model):
            raise ValueError("model does not look like a model id")
        if self.bytes < self.count:
            raise ValueError("bytes is smaller than the number of frames")
        if self.bytes > self.count * MAX_BYTES:
            raise ValueError("bytes is larger than the per-frame cap allows")
        return self


class LiveResult(BaseModel):
    """The result of a batch that was announced (``latency_ms`` omitted) with ``POST /privacy/ledger/live``."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    ref: str = Field(pattern=r"^e_[0-9a-f]{12,32}$")
    ok: bool
    latency_ms: int = Field(ge=0, le=3_600_000)
    input_tokens: int | None = Field(default=None, ge=0, le=10**9)
    output_tokens: int | None = Field(default=None, ge=0, le=10**9)
    cost_estimate_usd: float | None = Field(default=None, ge=0, le=1000)


async def _live_body(request: Request, model: type[BaseModel]) -> tuple[BaseModel | None, JSONResponse | None]:
    """Read and validate a small JSON body. Errors name fields and rules, never values: the 422 of a body that tried to carry a frame
    must not echo it. A body over ``MAX_LIVE_BODY`` bytes is refused before it is parsed."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_LIVE_BODY:
        return None, _error(413, "too_large", f"A live batch report is at most {MAX_LIVE_BODY} bytes; frames, audio and text do not go here.")
    raw = await request.body()
    if len(raw) > MAX_LIVE_BODY:
        return None, _error(413, "too_large", f"A live batch report is at most {MAX_LIVE_BODY} bytes; frames, audio and text do not go here.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, _error(400, "bad_json", "The body is not valid JSON.")
    if not isinstance(data, dict):
        return None, _error(422, "invalid_request", "The body must be a JSON object.")
    try:
        return model.model_validate(data), None
    except ValidationError as exc:
        parts = []
        for e in exc.errors(include_input=False, include_url=False, include_context=False)[:6]:
            loc = ".".join(str(x) for x in e.get("loc", ())) or "body"
            parts.append(f"{loc}: {e.get('type', 'invalid')}")
        return None, _error(422, "invalid_request", "The batch report was refused (" + "; ".join(parts) + "). Only the documented numeric fields are accepted.")


def _live_guard(request: Request, source: str) -> JSONResponse | None:
    """Worker or the local Electron main process only: this machine, a worker actor, an app or no Origin, and the sandbox rule."""
    if (g := _write_guard(request)) is not None:
        return g
    host = request.client.host if request.client else ""
    problem = frame_request_problem(source, client_host=host, origin=request.headers.get("origin"))
    if problem is not None:
        return _error(403, "write_refused", {"sandbox_origin": "A web page cannot report a sandbox frame batch.",
                                              "not_this_machine": "Live batches are only reported from this machine.",
                                              "unknown_source": "Unknown frame source."}.get(problem, "Refused."))
    return None


@router.post("/privacy/ledger/live")
async def post_live_batch(request: Request):
    """One ledger row for a batch of live frames streamed to a provider from the Electron main process (frames never pass through
    Python). The gate is applied as in ``egress.send_image``: unattended + real_screen always blocks, then secure input, a denylisted
    app, and missing consent; a refusal writes a ``blocked`` row and answers ``allowed: false`` (the main process must not send).
    ``latency_ms`` omitted: the batch is announced before sending and its result follows to ``/privacy/ledger/live/result``;
    given: the batch is reported as complete. A batch reported as already sent that the gate would have refused is recorded as
    blocked with ``error: reported_after_send``: the ledger says the gate was bypassed rather than hiding it."""
    if (r := _off()) is not None:
        return r
    batch, err = await _live_body(request, LiveBatch)
    if err is not None:
        return err
    assert isinstance(batch, LiveBatch)
    if (g := _live_guard(request, batch.source)) is not None:
        return g
    from .privacy._paths import is_mock

    mock = is_mock()
    gate = ImageGate(batch.gate.consent, batch.gate.denylisted_app, batch.gate.secure_input, batch.gate.unattended, batch.source)
    meta = {"sha8": batch.sha8, "bytes": batch.bytes, "width": batch.width, "height": batch.height, "kind": "live_frame", "source": batch.source}
    reason = gate.reason()
    if reason is not None:
        row = ledger.record_image_blocked(purpose=LIVE_PURPOSE, reason=reason, source=batch.source, image_meta=meta, mock=mock)
        if batch.latency_ms is not None or batch.ok is not None:
            ledger.finish_image(row["id"], status="blocked", ok=False, latency_ms=batch.latency_ms, error="reported_after_send")
        return {"allowed": False, "status": "blocked", "reason": reason, "ledger_id": row["id"]}
    try:
        row = ledger.begin_image({
            "purpose": LIVE_PURPOSE, "schema": "LiveFrameBatch", "method": "live", "fields": ["frames"], "payload": {"frames": batch.count},
            "image": meta, "source": batch.source, "provider": batch.provider, "model": f"{batch.provider}:{batch.model}",
            "bytes": batch.bytes, "mock": mock})
    except OSError:
        return _error(503, "ledger_unwritable", "The privacy ledger could not be written, so the main process must not send these frames.")
    status = "sending"
    if batch.latency_ms is not None:
        status = "ok" if batch.ok in (None, True) else "failed"
        ledger.finish_image(row["id"], status=status, ok=status == "ok", latency_ms=batch.latency_ms, input_tokens=batch.input_tokens,
                            output_tokens=batch.output_tokens, cost_estimate_usd=batch.cost_estimate_usd)
    return {"allowed": True, "status": status, "reason": None, "ledger_id": row["id"]}


@router.post("/privacy/ledger/live/result")
async def post_live_result(request: Request):
    """The result of a batch that was announced (the first call omitted ``latency_ms``): ``{ref, ok, latency_ms, tokens, cost}``.
    The ``ref`` must be a live batch row that is still ``sending``."""
    if (r := _off()) is not None:
        return r
    res, err = await _live_body(request, LiveResult)
    if err is not None:
        return err
    assert isinstance(res, LiveResult)
    if (g := _write_guard(request)) is not None:
        return g
    rows = {x["id"]: x for x in ledger.read_all()}
    row = rows.get(res.ref)
    if row is None or row.get("purpose") != LIVE_PURPOSE or row.get("kind") != "image":
        return _error(404, "no_such_batch", "There is no live batch with that reference.")
    if row.get("status") != "sending":
        return _error(409, "already_finished", "That batch already has a result.")
    status = "ok" if res.ok else "failed"
    ledger.finish_image(res.ref, status=status, ok=res.ok, latency_ms=res.latency_ms, input_tokens=res.input_tokens,
                        output_tokens=res.output_tokens, cost_estimate_usd=res.cost_estimate_usd)
    return {"ledger_id": res.ref, "status": status}
