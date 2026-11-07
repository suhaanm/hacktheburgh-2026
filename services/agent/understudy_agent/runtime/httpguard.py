"""Write guard for the agent routes (the worker's own actions: spawn, stop, resume, revoke).

A browser page the worker happens to have open must not be able to start, stop or steer agents. Cross-site "simple" requests need
no CORS preflight (a form post, a text/plain fetch), so the guard does not rely on CORS:

* the Origin, when there is one, must be EXACTLY one of the worker's own apps (scheme, host and port compared, never a prefix:
  `http://localhost.evil.example` is not `http://localhost`); `null` and every other origin are refused;
* when an Origin is present the request must also carry an explicit `X-Understudy-Actor: worker` header (a custom header forces a
  preflight that the CORS policy denies to every other origin);
* a body must be `application/json`; `text/plain` and form encodings are refused;
* the Host header must be a loopback name (DNS rebinding), and `Sec-Fetch-Site: cross-site` is refused;
* an actor header that names anyone but the worker is refused whether or not an Origin is present.

Non-browser local clients (the engine, the desktop app's main process, curl) send no Origin and may omit the actor header.
This module has the same semantics as the shared engine helper; swap it in by editing `check_write` only.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

WORKER_ACTORS = frozenset({"worker", "worker_approval"})
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
HOSTS_OK = LOOPBACK | {"testserver"}              # testserver: Starlette's in-process client
DEFAULT_PORTS = (5173, 7700, 7710)               # the dashboard, the engine and the agent service
_APP = re.compile(r"^app://[a-z0-9\-]{1,40}$")


def _ports() -> set[int]:
    ports = set(DEFAULT_PORTS)
    for var in ("DASHBOARD_PORT", "ENGINE_PORT", "AGENT_PORT"):
        v = os.environ.get(var, "").strip()
        if v.isdigit():
            ports.add(int(v))
    return ports


def origin_allowed(origin: str) -> bool:
    """True only for one of the worker's own apps, compared exactly (never by prefix)."""
    extra = {o.strip() for o in os.environ.get("UNDERSTUDY_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    if origin in extra or origin == "file://" or _APP.match(origin):
        return True
    try:
        p = urlsplit(origin)
        port = p.port
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or p.hostname not in LOOPBACK or p.username or p.password or p.path not in ("", "/") \
            or p.query or p.fragment:
        return False
    return port in _ports() if port is not None else False


def _host_ok(host: str) -> bool:
    h = host.strip().lower()
    if h.startswith("["):
        name = h[1:].split("]")[0]
    else:
        name = h.rsplit(":", 1)[0] if h.count(":") == 1 else h
    return name in HOSTS_OK


def _refuse(code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=403)


def check_write(request: Request, *, json_body: bool = False) -> JSONResponse | None:
    """None when the request may act as the worker, else the refusal response."""
    h = request.headers
    actor = h.get("x-understudy-actor")
    origin = h.get("origin")
    if actor is not None and actor.strip() not in WORKER_ACTORS:
        return _refuse("write_refused", "Only the worker starts or stops agents; this actor cannot.")
    if not _host_ok(h.get("host", "localhost")):
        return _refuse("write_refused", "This request was not addressed to the local service.")
    if h.get("sec-fetch-site", "").lower() == "cross-site":
        return _refuse("write_refused", "Writes only come from the worker's own app on this machine.")
    if origin is not None:
        if not origin_allowed(origin):
            return _refuse("write_refused", "Writes only come from the worker's own app on this machine.")
        if actor is None:
            return _refuse("write_refused", "A browser write must carry the explicit worker header.")
    if json_body and h.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return _refuse("write_refused", "The body must be application/json.")
    return None
