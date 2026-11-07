"""Shared server for the role sandboxes (programmer workbench, analyst workbench). Starlette + uvicorn in a thread, like
``sandbox_sites.runner.SandboxCluster``; no external assets, no network from the pages (a strict Content-Security-Policy).

THE CONTRACT the study harness (``evals/study_roles``) and the scripted drivers rely on. Both role sandboxes follow it.

Routes (every role)
  GET  /healthz                    {"ok": true, "role": ..., "epoch": n}
  POST /__reset                    clears the state log, bumps ``epoch``  -> {"epoch": n}
  GET  /__state                    the state dump the ORACLE scores (see below)
  POST /api/act                    the page reports one user action: a JSON object with a string ``kind`` (anything else is data)
  POST /api/final                  the page reports the final grade/summary (``window.__grade``), stored as ``state["final"]``
  GET  /                           an index of the tasks (humans and tests)
  GET  /task/{task_id}/{variant}   the page for one case. Query: ``layout=v2`` (renamed ids and labels, different arrangement),
                                   ``glitch=503once`` (the first load of a page after a reset answers 503, a retry link, then OK)
                                   or ``glitch=503always``.
  GET  /static/{file}              the role's own scripts and styles (no CDN)
  GET  /worker/{file}              a script from static/worker/, served with its own CSP (unsafe-eval, connect-src 'none'): the in-page code runner

State dump (``GET /__state``)
  {"role", "epoch", "task": {"id", "variant", "layout"} | null  (the last case page that loaded), "page_loads", "events": [...],
   "counts": {kind: n}, "final": {...} | null, "glitches": {path: n}}
  Each event: {"seq", "t" (seconds since the reset), "kind", ...whatever the page sent (zone, ids, small numbers, short strings)}.

Page contract (both roles)
  * every interactive control carries its zone in ``data-understudy-zone`` (the pack's zone vocabulary) on the control or an ancestor;
  * the control that ends the case is ``#done-btn`` (programmer, label "Mark done") or ``#answer-submit`` (analyst, label
    "Submit answer"), zone ``decision_btn``; pressing it logs ``{"kind": "done"}`` and shows ``#case-done`` (``data-state="done"``);
    the page also sets ``window.__caseDone = true``;
  * the forbidden irreversible control is ``#forbidden-btn`` ("Deploy to production" / "Publish to the shared dashboard"). The
    study harness never sends that click; if it is ever pressed the page logs ``{"kind": "forbidden"}``;
  * no field name, id, label, placeholder or aria-label may match ``packages/schema/sensitive_fields.json`` (e.g. "pass", "token",
    "secret", "credit", "debit", "pin", "routing", "sort code": avoid those words in controls) or the extension will not record it.

The oracle of each role is a pure function ``score(task_id, variant, state) -> Verdict dict`` (no model, no network):
  {"outcome": "correct" | "partial" | "wrong" | "claimed_done_wrong", "points": 2 | 1 | 0 | 0, "claimed_done": bool,
   "skill_check_done": bool  (the process indicator: did the participant use the check this task's skill is about),
   "reasons": [short strings]}
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import HOST

CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; worker-src 'self'; form-action 'self'; base-uri 'none'")
WORKER_CSP = "default-src 'none'; script-src 'unsafe-eval'; connect-src 'none'"      # the runner worker: eval allowed here only, no network at all
MAX_BODY = 262_144          # bytes: a page report is small; the final grade carries file contents
MAX_STR = 4000              # strings inside a reported action are cut at this length
MAX_EVENTS = 20_000


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _clip(v: Any, depth: int = 0) -> Any:
    if isinstance(v, str):
        return v[:MAX_STR]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if depth > 4:
        return None
    if isinstance(v, list):
        return [_clip(x, depth + 1) for x in v[:400]]
    if isinstance(v, dict):
        return {str(k)[:60]: _clip(x, depth + 1) for k, x in list(v.items())[:200]}
    return str(v)[:200]


class RoleState:
    """Thread-safe log of what the page reported since the last reset. The oracle reads ``snapshot()``."""

    def __init__(self, role: str) -> None:
        self.role = role
        self.lock = threading.Lock()
        self.epoch = 0
        self._clear()

    def _clear(self) -> None:
        self.events: list[dict] = []
        self.final: dict | None = None
        self.task: dict | None = None
        self.page_loads = 0
        self.glitches: dict[str, int] = {}
        self.t0 = time.monotonic()

    def reset(self) -> int:
        with self.lock:
            self.epoch += 1
            self._clear()
            return self.epoch

    def loaded(self, task_id: str, variant: int, layout: str) -> None:
        with self.lock:
            self.page_loads += 1
            self.task = {"id": task_id, "variant": variant, "layout": layout}

    def glitch_count(self, key: str) -> int:
        with self.lock:
            self.glitches[key] = self.glitches.get(key, 0) + 1
            return self.glitches[key]

    def log(self, data: dict) -> int:
        with self.lock:
            if len(self.events) >= MAX_EVENTS:
                return -1
            ev = {"seq": len(self.events) + 1, "t": round(time.monotonic() - self.t0, 3), **{k: _clip(v) for k, v in data.items() if k not in ("seq", "t")}}
            self.events.append(ev)
            return ev["seq"]

    def set_final(self, data: dict) -> None:
        with self.lock:
            self.final = _clip(data)

    def snapshot(self) -> dict:
        with self.lock:
            counts: dict[str, int] = {}
            for e in self.events:
                counts[str(e.get("kind"))] = counts.get(str(e.get("kind")), 0) + 1
            return {"role": self.role, "epoch": self.epoch, "task": dict(self.task) if self.task else None, "page_loads": self.page_loads,
                    "events": list(self.events), "counts": counts, "final": self.final, "glitches": dict(self.glitches)}


@dataclass
class RoleSpec:
    """What a role plugs into the shared app: its name, its static files, its task index and its page renderer."""

    role: str                                                    # "programmer" | "data-analyst"
    static_dir: Path
    tasks: dict[str, Any]                                        # id -> object with .id .skill .title .variants
    render_page: Callable[[str, int, dict], str]                 # (task_id, variant, ctx{layout, glitch}) -> html
    title: str = ""


async def _json_body(request: Request) -> dict | None:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return None
    try:
        d = json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def glitch_page(retry_href: str) -> str:
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><title>Service unavailable</title>"
            "<meta name=viewport content='width=device-width,initial-scale=1'><style>body{font:16px system-ui;margin:12vh auto;max-width:34rem;padding:0 1rem}"
            "</style></head><body><main><h1>503 Service unavailable</h1><p>The workbench could not start. Please try again.</p>"
            f"<p><a id=retry href=\"{retry_href}\">Retry</a></p></main></body></html>")


def make_app(spec: RoleSpec, state: RoleState) -> Starlette:
    def headers() -> dict[str, str]:
        return {"Content-Security-Policy": CSP, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

    async def healthz(request: Request):
        return JSONResponse({"ok": True, "role": spec.role, "epoch": state.epoch}, headers=headers())

    async def reset(request: Request):
        return JSONResponse({"epoch": state.reset()}, headers=headers())

    async def get_state(request: Request):
        return JSONResponse(state.snapshot(), headers=headers())

    async def act(request: Request):
        d = await _json_body(request)
        if d is None or not isinstance(d.get("kind"), str):
            return JSONResponse({"error": "bad body"}, status_code=400, headers=headers())
        return JSONResponse({"seq": state.log(d)}, headers=headers())

    async def final(request: Request):
        d = await _json_body(request)
        if d is None:
            return JSONResponse({"error": "bad body"}, status_code=400, headers=headers())
        state.set_final(d)
        return JSONResponse({"ok": True}, headers=headers())

    async def index(request: Request):
        rows = "".join(f"<li><b>{t.title}</b> ({t.skill}): " + " ".join(f"<a href='/task/{t.id}/{v}'>v{v}</a>" for v in t.variants) + "</li>" for t in spec.tasks.values())
        return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{spec.title or spec.role}</title><h1>{spec.title or spec.role}</h1><ul>{rows}</ul>", headers=headers())

    async def task_page(request: Request):
        task_id = request.path_params["task_id"]
        try:
            variant = int(request.path_params["variant"])
        except ValueError:
            return PlainTextResponse("no such case", status_code=404, headers=headers())
        task = spec.tasks.get(task_id)
        if task is None or variant not in task.variants:
            return PlainTextResponse("no such case", status_code=404, headers=headers())
        q = request.query_params
        ctx = {"layout": "v2" if q.get("layout") == "v2" else "v1", "glitch": q.get("glitch", "") if q.get("glitch") in ("503once", "503always") else ""}
        if ctx["glitch"]:
            n = state.glitch_count(f"{task_id}/{variant}")
            if ctx["glitch"] == "503always" or n == 1:
                retry = str(request.url.path) + "?" + "&".join(f"{k}={v}" for k, v in q.items() if k != "glitch" or ctx["glitch"] == "503always")
                return HTMLResponse(glitch_page(retry), status_code=503, headers=headers())
        state.loaded(task_id, variant, ctx["layout"])
        return HTMLResponse(spec.render_page(task_id, variant, ctx), headers=headers())

    async def worker_file(request: Request):
        name = request.path_params["name"]
        path = spec.static_dir / "worker" / name
        if "/" in name or ".." in name or not path.is_file():
            return PlainTextResponse("not found", status_code=404, headers=headers())
        h = headers()
        h["Content-Security-Policy"] = WORKER_CSP
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/javascript", headers=h)

    spec.static_dir.mkdir(parents=True, exist_ok=True)
    routes = [
        Route("/healthz", healthz), Route("/__reset", reset, methods=["POST"]), Route("/__state", get_state),
        Route("/api/act", act, methods=["POST"]), Route("/api/final", final, methods=["POST"]),
        Route("/", index), Route("/task/{task_id}/{variant}", task_page), Route("/worker/{name}", worker_file),
        Mount("/static", app=StaticFiles(directory=str(spec.static_dir)), name="static"),
    ]
    return Starlette(routes=routes)


@dataclass
class RoleServer:
    """One role sandbox on one port. ``port=0`` binds a free port (tests). ``state`` is shared with the app."""

    spec: RoleSpec
    port: int = 0
    state: RoleState = field(init=False)

    def __post_init__(self) -> None:
        self.state = RoleState(self.spec.role)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def case_url(self, task_id: str, variant: int, *, layout: str = "", glitch: str = "") -> str:
        q = "&".join(x for x in (f"layout={layout}" if layout else "", f"glitch={glitch}" if glitch else "") if x)
        return f"{self.url}/task/{task_id}/{variant}" + (f"?{q}" if q else "")

    def start(self, timeout: float = 10.0) -> "RoleServer":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, self.port))
        sock.listen(128)
        self.port = sock.getsockname()[1]
        self._sock = sock
        cfg = uvicorn.Config(make_app(self.spec, self.state), log_level="error", lifespan="off", access_log=False)
        self._server = uvicorn.Server(cfg)
        self._thread = threading.Thread(target=self._server.run, kwargs={"sockets": [sock]}, daemon=True, name=f"roles-{self.spec.role}")
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return self
            time.sleep(0.02)
        self.stop()
        raise RuntimeError("role sandbox did not start in time")

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._server = self._thread = self._sock = None

    def __enter__(self) -> "RoleServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
