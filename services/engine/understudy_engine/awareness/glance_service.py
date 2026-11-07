"""The server side of a glance, as a framework-free function: ``handle_glance(body, client_host=, origin=)``.

The desktop app's main process POSTs ``{frame_b64, gates, trigger, app_kind, width, height}`` (``GlanceHttpRequest`` in
``packages/schema/awareness.schema.json``) to the service's ``/glance`` route; the route calls this and returns ``reply.status`` and
``reply.body``. Everything that decides whether a frame may leave is here and in ``privacy.egress.send_image``; no model decides it.

    @router.post("/glance")
    async def glance(request: Request):
        reply = handle_glance(await request.json(), client_host=request.client.host if request.client else None,
                              origin=request.headers.get("origin"))
        return JSONResponse(reply.body, status_code=reply.status)

What this does, in order, refusing at the first failure:

1. ``frame_request_problem("real_screen", client_host=, origin=)``: a request from another machine is refused (403); so is any request
   that carries an Origin header other than the packaged app's (a web page may not post a frame; the desktop's main process sends none).
   The source is ALWAYS ``real_screen`` from this caller: it is not read from the request.
2. the body is checked against ``GlanceHttpRequest`` (422 on failure; the reason names the rule, never a value);
3. the base64 is decoded strictly and wrapped in a ``SafeImage`` (long edge at most 1280, at most 400 KB, header size must match the
   declared size) (422 if not);
4. ``ImageGate(consent, denylisted_app, secure_input, unattended, source="real_screen")`` is built from the flags and
   ``egress.send_image("awareness.glance", ...)`` does the rest: blocked gates write one ledger row and answer ``ok: false`` with the
   gate's reason (200, so the desktop shows "skipped: <reason>"); the ledger line is written BEFORE the call; the answer is checked
   against the closed schema; the frame is wiped after the call.

Replies: ``200 {ok: true, result, model, latency_ms, cost_usd_est?, ledger_id, mock}``; ``200 {ok: false, blocked_reason}`` for a closed gate
or an answer the guard refused; ``403/422 {error: {code, message}}``; ``502`` when the model call failed; ``503`` when the ledger could
not be written (nothing was sent). The body and the base64 are never logged or put in a message here (this module has no logger).
"""
from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import jsonschema

from ..privacy import egress
from ..privacy.image import ImageGate, ImageRejectedError, SafeImage, frame_request_problem
from . import schema
from .purposes import PURPOSE

MAX_B64_CHARS = 560_000          # a 400 KB image is about 547k base64 characters
_REASON = re.compile(r"^[a-z0-9_]{1,40}$")
SOURCE = "real_screen"           # fixed: frames from the desktop awareness path are never anything else
# The desktop's main process sends no Origin header (it is not a web page). Anything that does send one is a browser page, and a web page
# may not post a frame: only the packaged app's own origins are accepted.
APP_ORIGIN_PREFIXES = ("app://", "file://")


@dataclass
class GlanceReply:
    status: int
    body: dict[str, Any]


def _error(status: int, code: str, message: str) -> GlanceReply:
    return GlanceReply(status, {"error": {"code": code, "message": message}})


@lru_cache(maxsize=1)
def _request_validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator({"$ref": "#/$defs/GlanceHttpRequest", "$defs": schema.schema()["$defs"]})


def request_problem(body: Any) -> str | None:
    """Why the request body is not a ``GlanceHttpRequest``: a rule and a path, never a value. None when valid."""
    if not isinstance(body, dict):
        return "not an object"
    errs = sorted(_request_validator().iter_errors(body), key=lambda e: (len(list(e.absolute_path)), e.validator))
    if not errs:
        return None
    e = errs[0]
    return f"{e.validator} at {'.'.join(str(p) for p in e.absolute_path) or '$'}"


def handle_glance(body: Any, *, client_host: str | None, origin: str | None, port: Any = None, now: Any = None) -> GlanceReply:
    """See the module docstring. ``port`` and ``now`` are for tests (a capturing model port, a fixed time)."""
    problem = frame_request_problem(SOURCE, client_host=client_host, origin=origin)
    if problem is not None:
        return _error(403, problem, "A frame is only accepted from the Understudy app on this machine.")
    if origin is not None and not origin.startswith(APP_ORIGIN_PREFIXES):
        return _error(403, "origin_not_app", "A frame is not accepted from a web page.")
    why = request_problem(body)
    if why is not None:
        return _error(422, "bad_request", f"The glance request is not valid ({why}).")
    b64 = body["frame_b64"]
    if len(b64) > MAX_B64_CHARS:
        return _error(422, "frame_too_large", "The frame is larger than the limit.")
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return _error(422, "bad_frame", "The frame is not valid base64.")
    try:
        image = SafeImage(data, "glance", width=body.get("width"), height=body.get("height"), source=SOURCE)
    except ImageRejectedError as exc:
        return _error(422, "bad_frame", str(exc))
    finally:
        del data
    g = body["gates"]
    gate = ImageGate(consent=g["consent"], denylisted_app=g["denylisted_app"], secure_input=g["secure_input"], unattended=g["unattended"], source=SOURCE)
    payload = {"trigger": body["trigger"], "app_kind": body.get("app_kind", "unknown")}
    kw: dict[str, Any] = {"gate": gate, "port": port}
    if now is not None:
        kw["now"] = now
    try:
        res = egress.send_image(PURPOSE, image, payload, **kw)
    except egress.ImageBlocked as exc:
        reason = getattr(exc, "reason", None)
        return GlanceReply(200, {"ok": False, "blocked_reason": reason if isinstance(reason, str) and _REASON.match(reason) else "blocked"})
    except egress.ModelOutputRejected:
        return GlanceReply(200, {"ok": False, "blocked_reason": "output_rejected"})
    except egress.ModelCallFailed:
        return _error(502, "model_failed", "The vision model did not answer. The privacy ledger lists the call.")
    except egress.EgressUnavailable:
        return _error(503, "ledger_unavailable", "The privacy ledger could not be written, so nothing was sent.")
    except egress.EgressError as exc:
        return _error(422, getattr(exc, "code", "egress_error"), "The frame was not sent.")
    finally:
        image.release()
    out: dict[str, Any] = {"ok": True, "result": res.output, "model": str(res.model)[:80], "latency_ms": res.latency_ms,
                           "ledger_id": res.ledger_id, "mock": bool(res.mock)}
    if res.cost_estimate_usd is not None:
        out["cost_usd_est"] = float(res.cost_estimate_usd)
    return GlanceReply(200, out)
