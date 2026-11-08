"""The MCP client runner (CONNECTIONS): starts a connected server as a separate process, talks to it with the official SDK, and stops it.

What it does and does not do:

* It starts nothing on its own. ``start`` is called only for a connection the worker switched on (the service checks the state and the command
  hash first). A stand-in is a Python script of ours; a real server is launched with ``npx``, ``uvx`` or ``docker`` at the exact pinned version
  in the manifest, with no shell, with install scripts switched off (``npm_config_ignore_scripts``, ``UV_NO_BUILD``), and with a MINIMAL
  environment: ``PATH`` and ``HOME``, the manifest's fixed variables, the worker's own values for that connection, and the one token. Nothing else
  is inherited, so no secret of ours or of another connection reaches the process.
* One asyncio loop in one thread owns every session. Calls from other threads (a child agent) go through it with a timeout; a connect, a call and
  a stop each have a bound, so a slow or silent server cannot hang the agent.
* We never answer a server's own requests. There is no sampling, elicitation or roots callback, so a server cannot make a model of ours run
  for it or ask the worker anything; the SDK refuses those requests for us.
* A result is capped in size, flattened to text and handed back as UNTRUSTED text. Deciding what a call is and whether it may run is not done
  here (``classify`` and the service do that); this module only talks to the process.
* A crashed server is restarted at most three times in ten minutes; ``stop`` ends the process tree and forgets the session.
"""
from __future__ import annotations

import asyncio
import atexit
import contextlib
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from mcp import Client, MCPError, StdioServerParameters
from mcp.client import stdio as _stdio
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT, Implementation, TextContent

from understudy_engine.connections.manifest import Preset
from understudy_engine.connections.paths import repo_root, sandbox_dir, synthetic_dir

CONNECT_TIMEOUT_S = 25.0
CALL_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 10.0
MAX_RESULT_BYTES = 64_000
MAX_TOOLS = 500
MAX_PAGES = 20
MAX_CONNECTIONS = 8
RESTARTS_PER_WINDOW, RESTART_WINDOW_S = 3, 600.0
LAUNCHERS = frozenset({"npx", "uvx", "docker"})
_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]{1,80}$")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]{1,30})\}")
STANDIN_PASSTHROUGH = re.compile(r"^KNACK_STANDIN_[A-Z0-9_]{1,40}$")

# What the SDK lets a child inherit by default is HOME, LOGNAME, PATH, SHELL, TERM, USER. We keep the two a launcher needs.
_stdio.DEFAULT_INHERITED_ENV_VARS[:] = ["HOME", "PATH"]


class RunnerError(Exception):
    """A short stable code and a plain sentence for the worker. Never contains a token or a server's own text."""

    def __init__(self, code: str, message: str | None = None, detail: str = "") -> None:
        super().__init__(message or code)
        self.code, self.detail = code, detail           # detail: the NAME of the exception behind it, for the logs (never a message or a server's text)


@dataclass(frozen=True)
class Launch:
    kind: str                                  # stdio | http | source
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict, repr=False)          # may hold the worker's token: never printed
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    cwd: str | None = None


@dataclass(frozen=True)
class ToolInfo:
    name: str
    annotations: Any = None                    # what the server SAID about the tool: a hint, never trusted
    description_len: int = 0


@dataclass(frozen=True)
class RawResult:
    text: str
    is_error: bool
    blocks_other: int
    truncated: bool
    bytes: int


# ------------------------------------------------------------------------------------------------------------ building the launch
def _resolve(arg: str, values: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), arg)


def build_launch(preset: Preset, mode: str, params: dict[str, str], secrets: dict[str, str], which=shutil.which, extra_env: dict[str, str] | None = None) -> Launch:
    """The exact process to start. Raises ``RunnerError`` (launcher missing, bad value). Pure apart from ``which``."""
    if mode == "example":
        script = preset.standin.get("script")
        if not script:
            return Launch("source")                                    # an existing read-only source plugin: nothing to start
        values = {"sandbox": str(sandbox_dir()), "synthetic": str(synthetic_dir())}
        Path(values["sandbox"]).mkdir(parents=True, exist_ok=True)
        path = Path(script) if Path(script).is_absolute() else repo_root() / script
        env = {k: v for k, v in os.environ.items() if STANDIN_PASSTHROUGH.match(k)}
        env.update(extra_env or {})
        return Launch("stdio", sys.executable, (str(path), *[_resolve(a, values) for a in preset.standin.get("args", [])]), env)
    real = preset.real
    if real is None:
        raise RunnerError("no_real_mode", "This connection has only an example.")
    if real["transport"] == "plugin":
        return Launch("source")
    for k, v in params.items():
        if not isinstance(v, str) or v.startswith("-") or "\x00" in v:
            raise RunnerError("bad_param", "A value you entered cannot be used.")
    env: dict[str, str] = dict(real.get("env_fixed", {}))
    for p in real.get("params", []):
        if p.get("env") and p["name"] in params:
            env[p["env"]] = params[p["name"]]
    for k, v in secrets.items():
        if k not in preset.credential_envs:
            raise RunnerError("unknown_secret", "A token that is not part of this connection was given.")
        env[k] = v
    if real["transport"] == "streamable-http":
        url = real["url"]
        if not (url.startswith("https://") or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", url)):
            raise RunnerError("bad_url", "Only https addresses (or this machine) are allowed.")
        headers: dict[str, str] = {}
        for c in real.get("credentials", []):
            if c.get("header") and c["env"] in secrets:
                headers[c["header"]] = secrets[c["env"]] if c["header"].lower() != "authorization" else f"Bearer {secrets[c['env']]}"
        return Launch("http", url=url, headers=headers)
    command = real["command"]
    if command not in LAUNCHERS:
        raise RunnerError("bad_launcher", "That launcher is not allowed.")
    if which(command) is None:
        raise RunnerError("launcher_missing", {"npx": "Node is not installed on this Mac (npx was not found).", "uvx": "uv is not installed on this Mac (uvx was not found).",
                                               "docker": "Docker is not installed or not running on this Mac."}[command])
    if command == "npx":
        env.update({"npm_config_ignore_scripts": "true", "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false"})
    elif command == "uvx":
        env.update({"UV_NO_BUILD": "1", "UV_NO_PROGRESS": "1"})
    args = tuple(_resolve(a, params) for a in real["args"])
    if any(_PLACEHOLDER.search(a) for a in args):
        raise RunnerError("missing_param", "A value this connection needs was not set.")
    return Launch("stdio", command, args, env)


def _flatten(result: Any, cap: int) -> RawResult:
    """Text blocks joined (structured content as JSON only when there is no text), everything else only counted. Capped by bytes."""
    parts: list[str] = []
    other = 0
    for b in getattr(result, "content", None) or []:
        if isinstance(b, TextContent):
            parts.append(b.text)
        else:
            other += 1
    sc = getattr(result, "structured_content", None)
    if sc is not None and not parts:                     # the spec has a server send text too; structured content alone is used only when there is none
        try:
            js = json.dumps(sc, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            js = ""
        if js:
            parts.append(js)
    text = "\n".join(parts)
    raw = text.encode("utf-8", "replace")
    truncated = len(raw) > cap
    if truncated:
        text = raw[:cap].decode("utf-8", "ignore")
    return RawResult(text, bool(getattr(result, "is_error", False)), other, truncated, min(len(raw), cap))


# ------------------------------------------------------------------------------------------------------------ one live session
class _Conn:
    def __init__(self, conn_id: str, launch: Launch, loop: asyncio.AbstractEventLoop) -> None:
        self.id, self.launch, self.loop = conn_id, launch, loop
        self.stop_evt = asyncio.Event()
        self.ready: asyncio.Future[bool] = loop.create_future()
        self.client: Client | None = None
        self.tools: dict[str, ToolInfo] = {}
        self.alive = False
        self.task: asyncio.Task[None] | None = None
        self.error_type = ""                    # the NAME of the exception that ended it (never its message: a server's text is untrusted)
        self.cause: BaseException | None = None  # kept in memory for the traceback of a failed start; never logged or returned

    def _transport(self) -> Any:
        ln = self.launch
        if ln.kind == "stdio":
            return StdioServerParameters(command=ln.command, args=list(ln.args), env=dict(ln.env), cwd=ln.cwd)
        import httpx2                                              # the SDK's own HTTP client; headers carry the worker's token

        return streamable_http_client(ln.url, http_client=httpx2.AsyncClient(headers=dict(ln.headers), timeout=httpx2.Timeout(CALL_TIMEOUT_S, connect=10.0)))

    async def _list(self, client: Client) -> dict[str, ToolInfo]:
        tools: dict[str, ToolInfo] = {}
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            page = await client.list_tools(cursor=cursor)
            for t in page.tools:
                if _TOOL_NAME.match(t.name or "") and len(tools) < MAX_TOOLS:
                    tools[t.name] = ToolInfo(t.name, getattr(t, "annotations", None), len(t.description or ""))
            cursor = getattr(page, "next_cursor", None)
            if not cursor:
                break
        return tools

    async def serve(self) -> None:
        try:
            async with contextlib.AsyncExitStack() as stack:
                # The connect timeout is a watchdog that cancels THIS task: a cancel scope cannot be left open across the session (anyio nests them),
                # so the usual `with fail_after(...)` around a client that stays open for the whole session is not an option.
                watchdog = self.loop.call_later(CONNECT_TIMEOUT_S, lambda: self.task.cancel() if self.task and not self.ready.done() else None)
                try:
                    # no sampling, elicitation or roots callbacks on purpose; no response cache; nothing else is offered to the server
                    client = await stack.enter_async_context(Client(self._transport(), read_timeout_seconds=CALL_TIMEOUT_S, cache=None,
                                                                    client_info=Implementation(name="knack", version="1")))
                    self.tools = await self._list(client)
                finally:
                    watchdog.cancel()
                self.client, self.alive = client, True
                if not self.ready.done():
                    self.ready.set_result(True)
                await self.stop_evt.wait()
        except TimeoutError:
            self._fail("timeout")
        except FileNotFoundError:
            self._fail("launcher_missing")
        except OSError:
            self._fail("start_failed")
        except MCPError:
            self._fail("server_error")
        except asyncio.CancelledError:
            self._fail("timeout")                                    # the watchdog, or a stop while it was still starting
            raise
        except BaseException as exc:                                 # noqa: BLE001 - an ExceptionGroup from the SDK's task groups, or anything else
            leaf = exc
            while getattr(leaf, "exceptions", None):
                leaf = leaf.exceptions[0]
            self.cause, self.error_type = leaf, type(leaf).__name__
            self._fail("start_failed" if not self.alive else "server_gone")
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            self.alive = False
            self.client = None

    def _fail(self, code: str) -> None:
        self.alive = False
        if not self.ready.done():
            err = RunnerError(code, detail=self.error_type)
            err.__cause__ = self.cause
            self.ready.set_exception(err)


class ConnectionRunner:
    """Owns every live session on one background loop. Thread-safe: ``start``, ``call`` and ``stop`` may be called from any thread."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._conns: dict[str, _Conn] = {}
        self._launches: dict[str, Launch] = {}
        self._restarts: dict[str, list[float]] = {}
        atexit.register(self.stop_all)

    # ---- the loop
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="knack-connections", daemon=True).start()
                self._loop = loop
            return self._loop

    def _run(self, coro: Any, timeout: float) -> Any:
        fut = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        try:
            return fut.result(timeout)
        except TimeoutError:
            fut.cancel()
            raise RunnerError("timeout", "It took too long, so it was stopped.") from None

    # ---- lifecycle
    def start(self, conn_id: str, launch: Launch) -> list[ToolInfo]:
        """Start (or restart) the server and return its tools. Raises ``RunnerError``. The caller has already checked consent and the pin."""
        if launch.kind == "source":
            return []
        self.stop(conn_id)
        with self._lock:
            if len(self._conns) >= MAX_CONNECTIONS:
                raise RunnerError("too_many", "Too many connections are running.")
        loop = self._ensure_loop()

        async def go() -> _Conn:
            conn = _Conn(conn_id, launch, loop)
            conn.task = loop.create_task(conn.serve())
            await asyncio.wait_for(asyncio.shield(conn.ready), CONNECT_TIMEOUT_S + 5)
            return conn

        try:
            conn = self._run(go(), CONNECT_TIMEOUT_S + 10)
        except RunnerError:
            raise
        except TimeoutError:
            raise RunnerError("timeout", "It did not start in time.") from None
        except Exception as exc:                                     # noqa: BLE001 - _Conn._fail put a RunnerError on the future; anything else is a start failure
            raise exc if isinstance(exc, RunnerError) else RunnerError("start_failed", "It could not be started.") from None
        with self._lock:
            self._conns[conn_id] = conn
            self._launches[conn_id] = launch
        return list(conn.tools.values())

    def stop(self, conn_id: str) -> bool:
        with self._lock:
            conn = self._conns.pop(conn_id, None)
            self._launches.pop(conn_id, None)
        if conn is None or self._loop is None:
            return False

        async def end() -> None:
            conn.stop_evt.set()
            if conn.task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(conn.task), STOP_TIMEOUT_S)
                except (TimeoutError, asyncio.TimeoutError):
                    conn.task.cancel()
                except BaseException:                                 # noqa: BLE001
                    pass

        try:
            self._run(end(), STOP_TIMEOUT_S + 5)
        except RunnerError:
            pass
        return True

    def stop_all(self) -> None:
        for cid in list(self._conns):
            try:
                self.stop(cid)
            except Exception:                                         # noqa: BLE001 - at exit: best effort
                pass

    def has_session(self, conn_id: str) -> bool:
        """True when this connection was started before (so a start now is a RESTART and counts against the budget)."""
        return conn_id in self._launches

    def may_restart(self, conn_id: str) -> bool:
        with self._lock:
            return self._may_restart(conn_id)

    def clear_restarts(self, conn_id: str) -> None:
        """The worker started it again by hand: the budget begins afresh."""
        with self._lock:
            self._restarts.pop(conn_id, None)

    def is_running(self, conn_id: str) -> bool:
        c = self._conns.get(conn_id)
        return bool(c and c.alive)

    def tools(self, conn_id: str) -> dict[str, ToolInfo]:
        c = self._conns.get(conn_id)
        return dict(c.tools) if c else {}

    # ---- a call
    def _may_restart(self, conn_id: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._restarts.get(conn_id, []) if now - t < RESTART_WINDOW_S]
        self._restarts[conn_id] = recent
        if len(recent) >= RESTARTS_PER_WINDOW:
            return False
        recent.append(now)
        return True

    def call(self, conn_id: str, tool: str, arguments: dict[str, Any], timeout: float = CALL_TIMEOUT_S, cap: int = MAX_RESULT_BYTES) -> RawResult:
        """One tool call. Raises ``RunnerError`` (not running, unknown tool, timeout, server gone). A tool error the server reports is a RESULT
        (``is_error``), not an exception."""
        conn = self._conns.get(conn_id)
        if conn is None or not conn.alive:
            launch = self._launches.get(conn_id)
            if launch is None or not self._may_restart(conn_id):
                raise RunnerError("not_running", "The connection is not running.")
            self.start(conn_id, launch)                              # one supervised restart, bounded above
            conn = self._conns.get(conn_id)
            if conn is None:
                raise RunnerError("not_running", "The connection is not running.")
        if tool not in conn.tools:
            raise RunnerError("unknown_tool", "That server has no such tool.")

        async def go() -> RawResult:
            assert conn.client is not None
            try:
                with anyio.fail_after(timeout):
                    res = await conn.client.call_tool(tool, arguments, read_timeout_seconds=timeout)
            except TimeoutError:
                raise RunnerError("timeout", "It took too long, so it was stopped.") from None
            except MCPError as e:
                if e.code == CONNECTION_CLOSED:                       # the process went away under the call
                    conn.alive = False
                    raise RunnerError("server_gone", "The server stopped answering.") from None
                if e.code == REQUEST_TIMEOUT:
                    raise RunnerError("timeout", "It took too long, so it was stopped.") from None
                raise RunnerError("server_error", "The server refused the call.") from None
            except RunnerError:
                raise
            except BaseException as exc:                              # noqa: BLE001
                if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise
                conn.alive = False
                raise RunnerError("server_gone", "The server stopped answering.") from None
            return _flatten(res, cap)

        return self._run(go(), timeout + 5)


_default: ConnectionRunner | None = None
_default_lock = threading.Lock()


def default_runner() -> ConnectionRunner:
    global _default
    with _default_lock:
        if _default is None:
            _default = ConnectionRunner()
        return _default
