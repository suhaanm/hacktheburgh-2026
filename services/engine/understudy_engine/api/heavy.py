"""Single-flight, a short result cache and a concurrency limit for the engine's heavy read routes.

Why: the dashboard window, the desktop app's main process and several open pages all ask the same few heavy GETs (coach/state, briefing,
routines, hitlist, growth, presence, graph/work, evidence, ...) every few seconds. A client that times out does not cancel the work on the
server, so abandoned copies of the same request kept computing in the thread pool, GIL-contended, until the event loop starved and even /health
timed out. This middleware makes that impossible:

* SINGLE-FLIGHT: identical requests that arrive while one is computing wait for that one result. The computation runs as its own task, so a
  client that gives up (or all of them) neither cancels it nor starts a second copy; its result still fills the cache.
* TTL CACHE: a computed 200 answer is served again for ``ttl`` seconds (default 10). Bounded (entries and bytes). Only 200 answers; errors never.
* INVALIDATION: any request that is not a GET, HEAD or OPTIONS clears the whole cache (when it arrives and when it finishes), and a computation
  that started before a write never stores its answer. A change of the worker's memory or routine files (role switch, consent, forget) changes
  the key. A client that sends ``Cache-Control: no-cache`` (or ``?refresh=1``) gets a fresh computation, whose answer replaces the cached one.
* CONCURRENCY: at most ``limit`` (default 2) heavy handlers compute at once; the others wait their turn (never 429). Cheap routes bypass all of
  this, so /health, /kill, /identity, /queue and /attention/next keep answering.
* The key holds the method, path, query, the role header, whether the per-boot token is valid and the actor, so an admin answer is never served
  to a worker and the other way round.

Results are the handler's own bytes: a cached answer equals an uncached one. Pure ASGI (no BaseHTTPMiddleware), placed inside CORS and the guard, so
those still judge every request and decorate every response.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import http_guard

#: GET routes that cost 100 ms of CPU or more on the live data (tests/perf/measure.py), plus the ones that fan out on a page.
HEAVY_PREFIXES: tuple[str, ...] = (
    "/coach/state", "/briefing", "/routines", "/hitlist", "/growth", "/presence", "/graph/", "/insights/", "/genome/", "/hazard/", "/calendar/",
    "/git/", "/attention/digest", "/attention/why", "/evidence/", "/connections", "/profile", "/memory/proposals", "/eval/report", "/packs",
    "/replay", "/offhours/report",
)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CACHE_HEADER = b"x-understudy-cache"
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


def is_heavy(method: str, path: str, prefixes: tuple[str, ...] = HEAVY_PREFIXES) -> bool:
    if method != "GET":
        return False
    return any(path == p or path.startswith(p if p.endswith("/") else p + "/") for p in prefixes)


def settings_from_env() -> dict:
    """``UNDERSTUDY_HEAVY_TTL`` seconds (default 10; 0 turns the result cache off), ``UNDERSTUDY_HEAVY_LIMIT`` (default 2), ``UNDERSTUDY_HEAVY_ENTRIES``.
    Inside a pytest run the result cache is off unless asked for: tests write data files directly and read again, with no write request in between
    (single-flight and the limit stay on)."""
    def num(name: str, default: float) -> float:
        try:
            return float(os.environ[name])
        except (KeyError, ValueError):
            return default

    ttl = num("UNDERSTUDY_HEAVY_TTL", 0.0 if "PYTEST_CURRENT_TEST" in os.environ and "UNDERSTUDY_HEAVY_TTL" not in os.environ else 10.0)
    return {"ttl": max(0.0, ttl), "limit": max(1, int(num("UNDERSTUDY_HEAVY_LIMIT", 2))), "max_entries": max(1, int(num("UNDERSTUDY_HEAVY_ENTRIES", 256)))}


def _version_signature() -> tuple:
    """The worker's memory and routine files: their size and mtime are part of every key, so a role switch, a consent or a forgotten line changes the key
    even when the change did not come through this process."""
    try:
        from ..store.paths import home_dir

        home = home_dir()
        out = []
        for name in ("memory.md", "memory_state.json", "routines_state.json"):
            try:
                st = (home / name).stat()
                out.append((name, st.st_size, st.st_mtime_ns))
            except OSError:
                out.append((name, 0, 0))
        return tuple(out)
    except Exception:  # pragma: no cover - the key still holds the rest
        return ()


@dataclass
class _Captured:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes


@dataclass
class _Entry:
    expires: float
    got: _Captured
    size: int


class _Flight:
    __slots__ = ("task", "forced", "gen")

    def __init__(self, task: "asyncio.Task", forced: bool, gen: int) -> None:
        self.task, self.forced, self.gen = task, forced, gen


class _LoopState:
    """Per event loop: asyncio primitives belong to one loop (the in-process test client makes a loop per request)."""

    def __init__(self, limit: int) -> None:
        self.sem = asyncio.Semaphore(limit)
        self.flights: dict[tuple, _Flight] = {}


class HeavyGetMiddleware:
    def __init__(self, app, *, ttl: float = 10.0, limit: int = 2, max_entries: int = 256, prefixes: tuple[str, ...] = HEAVY_PREFIXES,
                 clock: Callable[[], float] = time.monotonic, signature: Callable[[], tuple] = _version_signature) -> None:
        self.app = app
        self.ttl, self.limit, self.max_entries, self.prefixes = ttl, limit, max_entries, prefixes
        self.clock, self.signature = clock, signature
        self._cache: "OrderedDict[tuple, _Entry]" = OrderedDict()
        self._bytes = 0
        self._gen = 0
        self._lock = threading.Lock()
        self._loops: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopState]" = weakref.WeakKeyDictionary()
        self.stats = {"hit": 0, "shared": 0, "computed": 0, "invalidations": 0, "max_running": 0}
        self._running = 0

    # ------------------------------------------------------------------------------------------------ state
    def _state(self) -> _LoopState:
        loop = asyncio.get_running_loop()
        with self._lock:
            st = self._loops.get(loop)
            if st is None:
                st = self._loops[loop] = _LoopState(self.limit)
            return st

    def invalidate(self) -> None:
        """Forget every cached answer and every in-flight computation as a source for new requests (the ones already waiting still get theirs)."""
        with self._lock:
            self._gen += 1
            self._cache.clear()
            self._bytes = 0
            self.stats["invalidations"] += 1
            for st in list(self._loops.values()):
                st.flights.clear()

    def _key(self, scope) -> tuple:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        role = (headers.get("x-understudy-role") or "").strip().lower()
        token = headers.get("x-understudy-token")
        token_class = bool(token) and http_guard.token_ok(token)
        actor = (headers.get("x-understudy-actor") or "").strip().lower()
        return (scope["path"], scope.get("query_string", b""), role, token_class, actor, self.signature())

    def _lookup(self, key: tuple) -> _Captured | None:
        with self._lock:
            e = self._cache.get(key)
            if e is None:
                return None
            if e.expires <= self.clock():
                self._cache.pop(key, None)
                self._bytes -= e.size
                return None
            self._cache.move_to_end(key)
            return e.got

    def _store(self, key: tuple, got: _Captured, gen: int) -> None:
        if self.ttl <= 0 or got.status != 200:
            return
        size = len(got.body)
        if size > MAX_ENTRY_BYTES:
            return
        with self._lock:
            if gen != self._gen:
                return                                   # a write happened while this was computing: the answer may be stale
            old = self._cache.pop(key, None)
            if old is not None:
                self._bytes -= old.size
            self._cache[key] = _Entry(self.clock() + self.ttl, got, size)
            self._bytes += size
            while self._cache and (len(self._cache) > self.max_entries or self._bytes > MAX_TOTAL_BYTES):
                _, ev = self._cache.popitem(last=False)
                self._bytes -= ev.size

    # ------------------------------------------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope["method"]
        if method not in SAFE_METHODS:
            self.invalidate()                            # the write arrives: nothing computed before it may be served after it
            try:
                return await self.app(scope, receive, send)
            finally:
                self.invalidate()                        # and once more when it is done: reads during the write may have seen half of it
        if not is_heavy(method, scope["path"], self.prefixes):
            return await self.app(scope, receive, send)

        forced = self._forced(scope)
        key = self._key(scope)
        tag = b"hit"
        got = None if forced else self._lookup(key)
        if got is not None:
            self.stats["hit"] += 1
        else:
            st = self._state()
            fl = st.flights.get(key)
            if fl is not None and (fl.forced or not forced):
                tag = b"shared"
                self.stats["shared"] += 1
            else:
                tag = b"miss"
                fl = self._start(scope, key, st, forced)
            got = await self._wait(fl)
        await self._replay(got, send, tag)

    @staticmethod
    def _forced(scope) -> bool:
        for k, v in scope.get("headers", []):
            if k == b"cache-control" and b"no-cache" in v.lower():
                return True
        return b"refresh=1" in scope.get("query_string", b"").split(b"&")

    def _start(self, scope, key: tuple, st: _LoopState, forced: bool) -> _Flight:
        gen = self._gen
        scope_copy = dict(scope)

        async def compute() -> _Captured:
            async with st.sem:
                with self._lock:
                    self._running += 1
                    self.stats["max_running"] = max(self.stats["max_running"], self._running)
                try:
                    self.stats["computed"] += 1
                    return await self._run_inner(scope_copy)
                finally:
                    with self._lock:
                        self._running -= 1

        task = asyncio.get_running_loop().create_task(compute())
        fl = _Flight(task, forced, gen)
        st.flights[key] = fl

        def done(t: "asyncio.Task") -> None:
            if st.flights.get(key) is fl:
                st.flights.pop(key, None)
            if t.cancelled() or t.exception() is not None:
                return
            # Stored under the key as it is NOW: some reads write the worker's memory or routine files (GET /routines merges what it found into the registry), which
            # moves the files' signature during the computation, and the next request will compute its key from the files as they are after it.
            self._store(self._key(scope_copy), t.result(), gen)

        task.add_done_callback(done)
        return fl

    async def _run_inner(self, scope) -> _Captured:
        status = 500
        headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []
        sent_request = False
        never = asyncio.Event()

        async def receive():
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await never.wait()                           # a GET has no body; there is no client to disconnect: this computation outlives it
            return {"type": "http.disconnect"}           # pragma: no cover

        async def capture(message):
            nonlocal status, headers
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(bytes(k), bytes(v)) for k, v in message.get("headers", [])]
            elif message["type"] == "http.response.body":
                chunks.append(bytes(message.get("body", b"")))

        await self.app(scope, receive, capture)
        return _Captured(status, headers, b"".join(chunks))

    @staticmethod
    async def _wait(fl: _Flight) -> _Captured:
        await asyncio.wait([fl.task])                    # a waiter that is cancelled does not cancel the computation (unlike awaiting the task)
        return fl.task.result()

    @staticmethod
    async def _replay(got: _Captured, send, tag: bytes) -> None:
        headers = [(k, v) for k, v in got.headers if k.lower() != CACHE_HEADER]
        headers.append((CACHE_HEADER, tag))
        await send({"type": "http.response.start", "status": got.status, "headers": headers})
        await send({"type": "http.response.body", "body": got.body, "more_body": False})
