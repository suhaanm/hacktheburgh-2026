"""One HTTP guard for both services (engine :7700, agent :7710). Written after REVIEW-PRIVACY and REVIEW-SAFETY found that any web page
could reach the write routes of a localhost service. The rules, in the order they are checked:

1. HOST (every request, GET included): the Host header must be exactly ``127.0.0.1:<port>`` or ``localhost:<port>`` (the service's own
   port), else 421. This stops DNS rebinding: a page that rebinds ``evil.example`` to 127.0.0.1 still sends ``Host: evil.example``.
2. ORIGIN (every write: POST, PUT, PATCH, DELETE): a present ``Origin`` is parsed strictly (``scheme://host[:port]``, lowercase, no path,
   no userinfo, no trailing dot) and compared EXACTLY on (scheme, host, port) with the allow-list (the dashboard on localhost and
   127.0.0.1 at port 5173 or $DASHBOARD_PORT, plus $UNDERSTUDY_ALLOWED_ORIGINS and $UNDERSTUDY_CORS_ORIGINS, each parsed the same way).
   ``null`` and anything else is foreign (403). No ``Origin`` is allowed only from a loopback client (a local, non-browser caller).
   The one exception is the browser extension, which calls the engine directly from a ``chrome-extension://<id>`` origin. That origin
   is allowed on exactly four routes and nowhere else, reads included: ``POST /events``, ``POST /routines/{id}/recording``,
   ``GET /identity``, ``GET /routines`` (``Policy.extension_events``). Pin the id with $UNDERSTUDY_EXTENSION_ID (or a comma list in $UNDERSTUDY_EXTENSION_IDS); unpinned, any
   chrome-extension id is accepted for that one route and ``/health`` says so (``extension_id_unpinned``). The extension must send
   ``X-Understudy-Actor: extension`` (not worker, not absent) on those four; that actor is refused on every other route and from every
   other origin, and none of the four needs a token. A web page cannot forge a chrome-extension Origin, and cannot add a custom header
   cross-site without a CORS preflight, which the allow-list refuses.
3. CONTENT TYPE, with an Origin: ``application/json`` (415 otherwise). A cross-site page cannot send it without a CORS preflight, which
   the allow-list refuses; ``text/plain`` and form posts, the "simple" requests that need no preflight, never reach a route.
4. ACTOR, with an Origin: the header ``X-Understudy-Actor`` must be explicit, never defaulted to "worker" for a browser.
   (A write with NO Origin comes from a local process, not a web page: a page's cross-site request always carries an Origin. Such a
   caller may omit the content type and the actor header; the actor then defaults to "worker", as it always has.)
5. TOKEN, release routes only (clear a safety stop, approve, grant consent), with or without an Origin: ``X-Understudy-Token`` must equal
   the per-boot token in ``<data dir>/.token`` (32 random bytes, hex, mode 0600, rewritten by every service boot, read afresh on every
   request), compared in constant time; the actor must be worker or worker_approval when named. STOP routes (``POST /kill``,
   ``/human-input``, ``/run/{id}/stop``) never need the token, because stopping is the safe direction, but they pass 1 to 4.

Test mode: the repo's own engine tests set ``UNDERSTUDY_TEST_RELAXED_GUARD=1`` (services/engine/tests/conftest.py); then a local request with NO
Origin does not need the token, so the existing suites keep working. Every request WITH an Origin, and every foreign Host, is judged
exactly as in production, and ``UNDERSTUDY_GUARD_STRICT=1`` switches the relaxation off again. A server process never has either
variable. Separately, under pytest (``PYTEST_CURRENT_TEST``) the in-process client's Host ``testserver`` and peer ``testclient`` are accepted.

The agent service reuses this module: ``app.add_middleware(GuardMiddleware, port=7710, policy=AGENT_POLICY)``; routes whose need depends
on the body (spawn with raw_ok, resume) call ``require_release(request)`` themselves.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .store.paths import data_dir

log = logging.getLogger("understudy.http_guard")

TOKEN_HEADER = "x-understudy-token"
ACTOR_HEADER = "x-understudy-actor"
CORS_ALLOW_HEADERS = ["content-type", ACTOR_HEADER, TOKEN_HEADER]
WORKER_ACTORS = frozenset({"worker", "worker_approval"})
EXTENSION_ACTOR = "extension"          # the browser extension's actor: valid only on its four routes (Policy.extension_events), from its own origin
EXTENSION_SCHEMES = ("chrome-extension:", "moz-extension:", "safari-web-extension:", "edge-extension:")
LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1", "localhost"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DEFAULT_DASHBOARD_PORT = 5173
_ACTOR_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_EXT_ORIGIN = re.compile(r"^chrome-extension://([a-p]{32})$")
_ORIGIN = re.compile(r"^(https?|app|tauri)://((?:[a-z0-9-]+\.)*[a-z0-9-]+|\[[0-9a-f:]+\])(?::([0-9]{1,5}))?$")


# ---------------------------------------------------------------------------------------------------------- modes and refusals
def under_pytest() -> bool:
    """True inside a pytest process that has not asked for strict behaviour: the in-process client's Host and peer are then accepted."""
    return "PYTEST_CURRENT_TEST" in os.environ and not _truthy(os.environ.get("UNDERSTUDY_GUARD_STRICT"))


def test_relaxed() -> bool:
    """True only in the repo's own engine tests (they set UNDERSTUDY_TEST_RELAXED_GUARD) that have not asked for strict behaviour."""
    return _truthy(os.environ.get("UNDERSTUDY_TEST_RELAXED_GUARD")) and not _truthy(os.environ.get("UNDERSTUDY_GUARD_STRICT"))


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Refusal:
    status: int
    code: str
    message: str

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


# ---------------------------------------------------------------------------------------------------------------------- origins
Origin = tuple[str, str, "int | None"]


def parse_origin(raw: str | None) -> Origin | None:
    """``(scheme, host, port)`` for a canonical origin string, else None. ``null``, paths, userinfo, upper case and trailing dots are all None.
    ``file://`` has no host and parses as ``("file", "", None)``."""
    if not raw:
        return None
    if raw == "file://":
        return ("file", "", None)
    m = _ORIGIN.fullmatch(raw)
    if not m:
        return None
    scheme, host, port = m.group(1), m.group(2), m.group(3)
    if ".." in host:
        return None
    p = int(port) if port else None
    if p is not None and (not (0 < p < 65536) or str(p) != port):          # no leading zeros: one spelling per origin
        return None
    return (scheme, host, p)


def origin_string(o: Origin) -> str:
    scheme, host, port = o
    if scheme == "file":
        return "file://"
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


def allowed_origins(env: Mapping[str, str] | None = None) -> frozenset[Origin]:
    """The exact allow-list: the dashboard on localhost and 127.0.0.1, plus whatever the environment adds (each entry parsed strictly)."""
    env = os.environ if env is None else env
    ports = {DEFAULT_DASHBOARD_PORT}
    dp = (env.get("DASHBOARD_PORT") or "").strip()
    if dp.isdigit() and 0 < int(dp) < 65536:
        ports.add(int(dp))
    out: set[Origin] = {("http", h, p) for h in ("localhost", "127.0.0.1") for p in ports}
    for var in ("UNDERSTUDY_ALLOWED_ORIGINS", "UNDERSTUDY_CORS_ORIGINS"):
        for raw in (env.get(var) or "").split(","):
            raw = raw.strip()
            if not raw:
                continue
            parsed = parse_origin(raw)
            if parsed is None:
                log.warning("%s: ignoring %r (not a canonical origin: scheme://host[:port], lowercase, no path)", var, raw)
            else:
                out.add(parsed)
    return frozenset(out)


def cors_origins(env: Mapping[str, str] | None = None) -> list[str]:
    """The same allow-list as strings, for the CORS middleware."""
    return sorted(origin_string(o) for o in allowed_origins(env))


def origin_allowed(origin: str | None, env: Mapping[str, str] | None = None) -> bool:
    """True when ``origin`` is exactly on the allow-list. An absent Origin is not 'allowed' here: callers decide what no Origin means."""
    parsed = parse_origin(origin)
    return parsed is not None and parsed in allowed_origins(env)


def extension_ids(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """The pinned extension ids: $UNDERSTUDY_EXTENSION_ID (one) and $UNDERSTUDY_EXTENSION_IDS (comma list), both honoured."""
    env = os.environ if env is None else env
    raw = f"{env.get('UNDERSTUDY_EXTENSION_ID') or ''},{env.get('UNDERSTUDY_EXTENSION_IDS') or ''}"
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def extension_id_pinned(env: Mapping[str, str] | None = None) -> bool:
    return bool(extension_ids(env))


def extension_origin_ok(origin: str | None, env: Mapping[str, str] | None = None) -> bool:
    """A browser extension's origin: ``chrome-extension://<32 letters a to p>``; pinned to the configured id(s) when any is set."""
    m = _EXT_ORIGIN.fullmatch(origin or "")
    if not m:
        return False
    pinned = extension_ids(env)
    return not pinned or m.group(1) in pinned


def cors_extension(env: Mapping[str, str] | None = None) -> tuple[list[str], str | None]:
    """What the CORS middleware may answer to for the extension: its pinned origin(s) exactly, or, unpinned, any well-formed
    chrome-extension origin (a regex). Only a preflight answer: the guard still limits an extension origin to its four routes."""
    ids = sorted(extension_ids(env))
    if ids:
        return [f"chrome-extension://{i}" for i in ids if re.fullmatch(r"[a-p]{32}", i)], None
    return [], r"chrome-extension://[a-p]{32}"


def status(env: Mapping[str, str] | None = None) -> dict:
    """What /health reports about the guard: no secrets, only whether the extension id is pinned."""
    pinned = extension_id_pinned(env)
    return {"extension_id_pinned": pinned, "warnings": [] if pinned else ["extension_id_unpinned"]}


def client_is_local(client_host: str | None) -> bool:
    return (client_host or "") in LOOPBACK_CLIENTS or (under_pytest() and client_host == "testclient")


# ------------------------------------------------------------------------------------------------------------------------- hosts
def allowed_hosts(port: int, env: Mapping[str, str] | None = None) -> frozenset[str]:
    env = os.environ if env is None else env
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    hosts |= {h.strip() for h in (env.get("UNDERSTUDY_ALLOWED_HOSTS") or "").split(",") if h.strip()}
    if under_pytest():
        hosts.add("testserver")
    return frozenset(hosts)


def host_ok(host_header: str | None, port: int, env: Mapping[str, str] | None = None) -> bool:
    return bool(host_header) and host_header in allowed_hosts(port, env)


# ------------------------------------------------------------------------------------------------------------------------ token
def token_path() -> Path:
    return data_dir() / ".token"


def ensure_token(path: Path | None = None) -> str:
    """The per-boot token: made by whichever service starts first (32 random bytes as hex, mode 0600, never overwritten once there).
    ``make dev`` and ``make demo`` delete the file before starting the services, so every boot rotates it."""
    p = path or token_path()
    existing = read_token(p)
    if existing:
        return existing
    p.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    fd, tmp = tempfile.mkstemp(prefix=".token.", dir=str(p.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(token + "\n")
        try:
            os.link(tmp, p)                       # atomic and first-writer-wins: two services starting together agree
        except FileExistsError:
            pass
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return read_token(p) or token


def rotate_token(path: Path | None = None) -> str:
    """A fresh token, written atomically (mode 0600) over whatever was there. Every service calls this at boot, so a restart rotates it;
    nothing caches the token (it is read afresh on each request), so two services booting one after the other stay consistent."""
    p = path or token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    fd, tmp = tempfile.mkstemp(prefix=".token.", dir=str(p.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(token + "\n")
        os.replace(tmp, p)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return token


def read_token(path: Path | None = None) -> str | None:
    try:
        t = (path or token_path()).read_text().strip()
    except OSError:
        return None
    return t if re.fullmatch(r"[0-9a-f]{64}", t) else None


def token_ok(presented: str | None, path: Path | None = None) -> bool:
    expected = read_token(path)
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.strip().encode(), expected.encode())


# -------------------------------------------------------------------------------------------------------------------- policy
@dataclass(frozen=True)
class Policy:
    """Which write routes are STOP (no token: stopping is the safe direction) and which are RELEASE (token required)."""
    stop: tuple[tuple[str, str], ...] = ()
    release: tuple[tuple[str, str], ...] = ()
    # the only routes the browser extension may call (from a chrome-extension origin, with actor "extension"): L0 ingest, the L1 recording
    # upload, and two read-only lookups (the person the engine owns, the routines the worker opted into)
    extension_events: tuple[tuple[str, str], ...] = (
        ("POST", r"/events"), ("POST", r"/routines/[^/]+/recording"), ("GET", r"/identity"), ("GET", r"/routines"),
    )

    def matches(self, group: str, method: str, path: str) -> bool:
        return any(m == method and re.fullmatch(p, path) for m, p in getattr(self, group))


ENGINE_POLICY = Policy(
    stop=(("POST", r"/kill"),),
    release=(
        ("POST", r"/kill/clear"),
        ("POST", r"/queue/[^/]+/(approve|reject)"),
        ("POST", r"/routines/[^/]+/(consent|shadow|promote)"),
        ("POST", r"/privacy/ledger/clear"),
    ),
)
AGENT_POLICY = Policy(
    stop=(("POST", r"/kill"), ("POST", r"/human-input"), ("POST", r"/run/[^/]+/stop"), ("POST", r"/agents/runs/[^/]+/stop")),
    release=(
        ("POST", r"/kill/clear"),
        ("POST", r"/queue/[^/]+/(approve|reject)"),
        ("POST", r"/agents/runs/[^/]+/resume"),
        ("POST", r"/routines/[^/]+/(consent|shadow|promote)"),
    ),
    extension_events=(),
)


def evaluate(method: str, path: str, headers: Mapping[str, str], client_host: str | None, *, port: int, policy: Policy = ENGINE_POLICY,
             env: Mapping[str, str] | None = None, release: bool | None = None) -> Refusal | None:
    """The whole decision as a pure function. ``headers`` keys are lower case. ``release`` forces the token rule (for routes whose need
    depends on the body). Returns None to let the request through."""
    method = method.upper()
    if not host_ok(headers.get("host"), port, env):
        return Refusal(421, "host_refused", "This service answers only to its own address (127.0.0.1 or localhost on its own port).")
    if method == "OPTIONS":                       # a CORS preflight carries no data and no authority; the CORS allow-list answers it
        return None
    origin = headers.get("origin")
    ctype = (headers.get("content-type") or "").split(";")[0].strip().lower()
    actor = (headers.get(ACTOR_HEADER) or "").strip()
    ingest = origin is not None and policy.matches("extension_events", method, path) and extension_origin_ok(origin, env)
    if method not in WRITE_METHODS:               # reads: only the extension rules apply (Host was judged above)
        if origin is not None and origin.lower().startswith(EXTENSION_SCHEMES) and not ingest:
            return Refusal(403, "origin_refused", "An extension may only call the few routes the Understudy extension uses.")
        if ingest and not actor:
            return Refusal(403, "actor_required", f"Send {ACTOR_HEADER}: {EXTENSION_ACTOR} explicitly.")
        if (ingest and actor != EXTENSION_ACTOR) or (actor == EXTENSION_ACTOR and not ingest):
            return Refusal(403, "actor_refused", "The extension actor is valid only on the extension's own routes, from its own origin.")
        return None
    if origin is not None:
        if not ingest and not origin_allowed(origin, env):
            return Refusal(403, "origin_refused", "Writes only come from the Understudy app on this machine.")
        if ctype != "application/json":
            return Refusal(415, "json_required", "Writes must be sent as Content-Type: application/json.")
        if not actor:
            what = EXTENSION_ACTOR if ingest else "worker"
            return Refusal(403, "actor_required", f"Send {ACTOR_HEADER}: {what} explicitly; it is never assumed for a browser caller.")
        if ingest and actor != EXTENSION_ACTOR:
            return Refusal(403, "actor_refused", f"The extension ingests events as {ACTOR_HEADER}: {EXTENSION_ACTOR}.")
    else:
        if not client_is_local(client_host):
            return Refusal(403, "origin_refused", "A write with no Origin is accepted only from this machine.")
        # no Origin = a local process, not a web page. An empty POST (/kill) may omit the type; anything that declares or carries a
        # body must say it is JSON.
        has_body = (headers.get("content-length") or "0").strip() not in ("", "0") or bool(headers.get("transfer-encoding"))
        if (ctype and ctype != "application/json") or (not ctype and has_body):
            return Refusal(415, "json_required", "Writes must be sent as Content-Type: application/json.")
    if actor and not _ACTOR_RE.fullmatch(actor):
        return Refusal(403, "actor_refused", "That actor name is not valid.")
    if actor == EXTENSION_ACTOR and not ingest:
        return Refusal(403, "actor_refused", "The extension actor is valid only on the extension's own routes, from its own origin.")
    is_release = release if release is not None else policy.matches("release", method, path)
    if is_release:
        if actor and actor not in WORKER_ACTORS:
            return Refusal(403, "actor_refused", "Only the worker can release a stop or grant authority.")
        if not (origin is None and test_relaxed()):
            presented = headers.get(TOKEN_HEADER)
            if not presented:
                return Refusal(403, "token_required", f"This action needs the per-boot token in {TOKEN_HEADER} (see data/.token).")
            if not token_ok(presented):
                return Refusal(403, "token_invalid", "The token is wrong or out of date: restart the services to rotate it, and send the new one.")
    return None


def require_release(headers: Mapping[str, str], client_host: str | None, *, port: int, path: str = "", method: str = "POST") -> Refusal | None:
    """For a route whose need for the token depends on its body (agent spawn with raw_ok, resume): the same checks, token forced."""
    return evaluate(method, path or "/", {k.lower(): v for k, v in headers.items()}, client_host, port=port, policy=Policy(), release=True)


def _token_part(value: str | None, limit: int = 40) -> str:
    """A value made safe for the audit log: lower case, only [a-z0-9_.:-], at most ``limit`` characters. Never the text of a request body."""
    return re.sub(r"[^a-z0-9_.:\-]", "-", (value or "").lower())[:limit] or "none"


class RefusalAudit:
    """Writes one redacted line to data/audit.jsonl (the hash-chained AuditLog) for a request the guard refused: the code, the status, the
    method, the first path segment, the origin and the actor, each reduced to a short token. No body, no header value beyond those two,
    no token. Rate limited (``limit`` lines per ``window`` seconds) so a hostile page cannot flood the log; the lines it could not
    write are counted and reported on the next one (``suppressed``). Never raises, and a service without the agent package skips it."""

    def __init__(self, *, limit: int = 30, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._stamps: deque[float] = deque()
        self._suppressed = 0
        self._lock = threading.Lock()

    def __call__(self, refusal: Refusal, method: str, path: str, headers: Mapping[str, str]) -> bool:
        now = self.clock()
        with self._lock:
            while self._stamps and now - self._stamps[0] > self.window:
                self._stamps.popleft()
            if len(self._stamps) >= self.limit:
                self._suppressed += 1
                return False
            self._stamps.append(now)
            suppressed, self._suppressed = self._suppressed, 0
        meta: dict = {"code": refusal.code, "status": refusal.status, "method": _token_part(method, 8),
                      "route": _token_part(path.strip("/").split("/")[0] if path.strip("/") else "root", 24),
                      "origin": _token_part(headers.get("origin")), "actor": _token_part(headers.get(ACTOR_HEADER), 24)}
        if suppressed:
            meta["suppressed"] = suppressed
        try:
            from understudy_agent.audit import AuditLog

            AuditLog().append("system", "http_refused", outcome="refused", note_code=refusal.code, meta=meta)
            return True
        except Exception as exc:  # the agent package missing, a read-only disk: the refusal itself already stands
            log.debug("guard refusal not audited: %s", type(exc).__name__)
            return False


class GuardMiddleware:
    """Pure ASGI middleware: runs ``evaluate`` on every HTTP request and answers a refusal itself. Add it LAST so it is outermost.
    ``on_refusal(refusal, method, path, headers)`` (for example a ``RefusalAudit``) is called for each refusal; it must not raise."""

    def __init__(self, app, *, port: int, policy: Policy = ENGINE_POLICY, env: Mapping[str, str] | None = None,
                 on_refusal: Callable[[Refusal, str, str, Mapping[str, str]], object] | None = None):
        self.app, self.port, self.policy, self.env, self.on_refusal = app, port, policy, env, on_refusal

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        client = (scope.get("client") or (None, None))[0]
        refusal = evaluate(scope["method"], scope["path"], headers, client, port=self.port, policy=self.policy, env=self.env)
        if refusal is None:
            await self.app(scope, receive, send)
            return
        if self.on_refusal is not None:
            try:
                self.on_refusal(refusal, scope["method"], scope["path"], headers)
            except Exception as exc:  # pragma: no cover - auditing never changes the answer
                log.debug("on_refusal failed: %s", type(exc).__name__)
        body = json.dumps(refusal.body()).encode()
        await send({"type": "http.response.start", "status": refusal.status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})


# ---------------------------------------------------------------------------------------------------- helpers for route modules
def actor_of(request, default: str = "worker") -> str:
    """The caller's actor. With an Origin present (a browser) the header must be explicit: an absent one is "" and fails every worker
    check. Without an Origin from a local client the old default stays."""
    header = (request.headers.get(ACTOR_HEADER) or "").strip()
    if header:
        return header
    if request.headers.get("origin") is not None:
        return ""
    return default
