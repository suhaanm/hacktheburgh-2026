"""Start, health-check and stop ``llama-server`` on a loopback port (LOC-1, PRV-4).

What this module guarantees
  * the server binds 127.0.0.1 only (``--host`` is hard-coded, never read from the environment), is started with
    ``--offline`` (no downloads, no network beyond localhost), with no web UI, no slots endpoint, no tools or MCP, and a
    per-start random API key in a 0600 file, so another local program cannot use it without reading that file;
  * its log goes to ``<data>/logs/llama.log`` at the default verbosity, which records timings and slot bookkeeping but no
    prompt text (verified against canaries in the tests and in the evaluation); ``-v`` and ``--log-prompts-dir`` are never
    passed and ``LLAMA_*`` environment variables are not inherited, so nothing can switch prompt logging on;
  * the model file's size and SHA-256 are verified once and cached (keyed by path, size and modification time);
  * anything missing or wrong (no binary, no model, bad size or hash, mock mode, port taken by another program, a start that
    fails) means "rules" and a short reason, never an exception to the caller.
"""
from __future__ import annotations

import atexit
import contextlib
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import config
from .client import LocalClient

BACKOFF_ENV = "UNDERSTUDY_LOCAL_MODEL_BACKOFF_S"
_HASH_CHUNK = 8 * 1024 * 1024


# ----------------------------------------------------------------------------------------------------- model verification
@dataclass
class ModelCheck:
    path: str
    exists: bool
    size_bytes: int | None
    expected_size: int | None
    size_ok: bool
    sha256: str | None
    expected_sha256: str | None
    sha_ok: bool | None            # None = not verified yet, or nothing to compare against
    checked_at: float | None

    @property
    def ok(self) -> bool:
        return self.exists and self.size_ok and self.sha_ok is not False

    @property
    def file(self) -> str:
        return Path(self.path).name


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(path.read_text())
        return v if isinstance(v, dict) else None
    except (OSError, ValueError):
        return None


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def model_check(compute: bool = False, force: bool = False) -> ModelCheck:
    """Size always (a stat), SHA-256 from the cache, or computed once when ``compute`` is true (about 17 s for 4.7 GB)."""
    p = config.model_path()
    exp_size, exp_sha = config.expected_model()
    try:
        st = p.stat()
    except OSError:
        return ModelCheck(str(p), False, None, exp_size, False, None, exp_sha, None, None)
    size_ok = exp_size is None or st.st_size == exp_size
    cache_p = config.check_cache_path()
    cached = _read_json(cache_p) or {}
    sha: str | None = None
    at: float | None = None
    if (not force and cached.get("path") == str(p) and cached.get("size") == st.st_size
            and cached.get("mtime_ns") == st.st_mtime_ns and isinstance(cached.get("sha256"), str)):
        sha, at = cached["sha256"], cached.get("checked_at")
    elif compute and size_ok:
        sha, at = _file_sha256(p), time.time()
        with contextlib.suppress(OSError):
            _atomic_write(cache_p, json.dumps({"path": str(p), "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                                               "sha256": sha, "checked_at": at}))
    sha_ok = None if (sha is None or exp_sha is None) else (sha == exp_sha)
    return ModelCheck(str(p), True, st.st_size, exp_size, size_ok, sha, exp_sha, sha_ok, at)


# ------------------------------------------------------------------------------------------------------------- the server
def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((config.HOST, port)) == 0


def _pid_alive(pid: int) -> bool:
    try:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:        # our own child that has exited: reap it (no zombie)
            return False
    except ChildProcessError:
        pass                                              # not our child (started by another process): fall through
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _command_of(pid: int) -> str:
    try:
        return subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _clean_env() -> dict[str, str]:
    """A minimal environment: nothing from the caller's (keys, proxies, HF tokens, LLAMA_* switches) reaches the server."""
    keep = {k: os.environ[k] for k in ("HOME", "TMPDIR", "USER", "LANG", "LC_ALL") if k in os.environ}
    keep["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
    return keep


class LocalServer:
    def __init__(self) -> None:
        self.port = config.port()
        self.model = config.model_path()
        self.binary = config.binary()
        self.endpoint = f"http://{config.HOST}:{self.port}"
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._failed_until = 0.0
        self.last_error: str | None = None
        self._bench: dict[str, Any] | None = None
        self._bench_busy = False

    # -- identity of the configuration, so a changed environment rebuilds the instance
    @staticmethod
    def config_key() -> tuple[Any, ...]:
        return (str(config.model_path()), config.port(), config.binary(), str(config.data_dir()))

    # -- availability
    def unavailable_reason(self, ignore_flag: bool = False) -> str | None:
        """Why the rules path is used right now, or None when the model path is usable. Cheap: no process, no hashing.
        ``ignore_flag`` is for an explicit evaluation run; mock mode and rules-only are never ignored."""
        if config.is_mock():
            return "mock_mode"
        if config.rules_only():
            return "rules_only"
        if not ignore_flag and not config.flag_on():
            return "flag_off"
        if not self.binary:
            return "no_binary"
        mc = model_check(compute=False)
        if not mc.exists:
            return "no_model"
        if not mc.size_ok:
            return "bad_model_size"
        if mc.sha_ok is False:
            return "bad_model_sha"
        if time.monotonic() < self._failed_until:
            return "start_failed_recently"
        return None

    def _remember_failure(self, reason: str) -> None:
        self.last_error = reason
        try:
            backoff = float(os.environ.get(BACKOFF_ENV, "60"))
        except ValueError:
            backoff = 60.0
        self._failed_until = time.monotonic() + max(0.0, backoff)

    # -- process bookkeeping
    def _pid_info(self) -> dict[str, Any] | None:
        info = _read_json(config.pid_path())
        if not info or not isinstance(info.get("pid"), int):
            return None
        if not _pid_alive(info["pid"]) or f"--port {info.get('port')}" not in _command_of(info["pid"]):
            return None
        return info

    def owned(self) -> bool:
        """True when the server on our port is one this module started (pid file, live process, right port)."""
        info = self._pid_info()
        return bool(info and info.get("port") == self.port)

    def api_key(self) -> str | None:
        try:
            return config.key_path().read_text().strip() or None
        except OSError:
            return None

    def client(self, **kw: Any) -> LocalClient:
        return LocalClient(self.endpoint, api_key=self.api_key(), **kw)

    def healthy(self) -> bool:
        c = LocalClient(self.endpoint)
        try:
            return c.healthy()
        finally:
            c.close()

    def running(self) -> bool:
        return self.owned() and self.healthy()

    # -- start and stop
    def _command(self, keyfile: Path) -> list[str]:
        assert self.binary
        return [
            self.binary, "-m", str(self.model),
            "--host", config.HOST, "--port", str(self.port),
            "-ngl", "99", "-c", str(config.CONTEXT_SIZE), "-np", "1",
            "--no-webui", "--no-slots", "--offline", "--api-key-file", str(keyfile),
            "-lv", "3", "--log-colors", "off", "--timeout", "120", "--cache-ram", "256",
        ]

    def start(self, wait_s: float = 120.0, ignore_flag: bool = False) -> bool:
        """Start (or reuse) the server. Returns True when it is healthy. Never raises; ``last_error`` says why not."""
        with self._lock:
            reason = self.unavailable_reason(ignore_flag=ignore_flag)
            if reason:
                self.last_error = reason
                return False
            if self.running():
                self.last_error = None
                return True
            if _port_open(self.port):                      # something else holds the port: we neither use nor kill it
                self._remember_failure("port_in_use")
                return False
            mc = model_check(compute=True)                  # once; cached afterwards
            if not mc.ok:
                self._remember_failure("bad_model_sha" if mc.sha_ok is False else "bad_model_size")
                return False
            key = secrets.token_urlsafe(24)
            _atomic_write(config.key_path(), key + "\n", mode=0o600)
            lp = config.log_path()
            lp.parent.mkdir(parents=True, exist_ok=True)
            if lp.exists() and lp.stat().st_size > 5_000_000:
                lp.write_bytes(b"")                          # keep the log small; it holds no prompts anyway
            try:
                logf = open(lp, "ab")  # noqa: SIM115 - owned by the child for its lifetime
                self._proc = subprocess.Popen(
                    self._command(config.key_path()), stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                    env=_clean_env(), start_new_session=True,
                )
                logf.close()
            except OSError:
                self._remember_failure("spawn_failed")
                return False
            _atomic_write(config.pid_path(), json.dumps({"pid": self._proc.pid, "port": self.port, "model": mc.file,
                                                         "started_at": time.time()}))
            atexit.register(self.stop_if_started_here)
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    self._remember_failure("server_exited")
                    return False
                if self.healthy():
                    self.last_error = None
                    return True
                time.sleep(0.25)
            self._kill(self._proc.pid)
            self._remember_failure("start_timeout")
            return False

    @staticmethod
    def _kill(pid: int) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(os.getpgid(pid), sig)
            except (ProcessLookupError, PermissionError):
                return
            for _ in range(40):
                if not _pid_alive(pid):
                    return
                time.sleep(0.1)

    def stop(self) -> bool:
        """Stop the server this module started (ours by pid file and port). Never touches a foreign process."""
        with self._lock:
            info = self._pid_info()
            stopped = False
            if info and info.get("port") == self.port:
                self._kill(info["pid"])
                stopped = not _pid_alive(info["pid"])
            if self._proc is not None:
                with contextlib.suppress(Exception):
                    self._proc.wait(timeout=1)
                self._proc = None
            with contextlib.suppress(OSError):
                config.pid_path().unlink()
            with contextlib.suppress(OSError):
                config.key_path().unlink()
            self._bench = None
            return stopped

    def stop_if_started_here(self) -> None:
        if self._proc is not None:
            self.stop()

    # -- status
    def status(self, bench: bool = False) -> dict[str, Any]:
        mc = model_check(compute=False)
        reason = self.unavailable_reason()
        running = self.running()
        out: dict[str, Any] = {
            "enabled": config.flag_on(),
            "running": running,
            "model": {"file": mc.file, "size_bytes": mc.size_bytes, "sha_ok": mc.sha_ok},
            "endpoint": self.endpoint,
            "mode": mode(),
            "reason": reason or ("ok" if running else (self.last_error or "not_started")),
            "binary": bool(self.binary),
            "bind": config.HOST,
            "context": config.CONTEXT_SIZE,
            "parallel": 1,
            "sha256": mc.sha256,
        }
        if running and bench:
            tps = self.benchmark()
            if tps is not None:
                out["tokens_per_s"] = tps
        return out

    def benchmark(self, max_age_s: float = 300.0) -> float | None:
        """One fixed synthetic commit through the real constrained path; generation tokens per second. Cached: fresh values are
        returned as they are, a stale value is returned at once while a daemon thread refreshes it, and only the very first
        call blocks (about 1 to 5 s, the prompt prefix is processed once)."""
        b = self._bench
        if b and time.monotonic() - b["at"] < max_age_s:
            return b["tps"]
        if b:
            if not self._bench_busy:
                self._bench_busy = True
                threading.Thread(target=self._refresh_bench, name="localmodel-bench", daemon=True).start()
            return b["tps"]
        return self._refresh_bench()

    def _refresh_bench(self) -> float | None:
        from .digest import benchmark_once

        try:
            tps = benchmark_once(self)
            if tps is not None:
                self._bench = {"tps": round(tps, 1), "at": time.monotonic()}
                return self._bench["tps"]
            return None
        finally:
            self._bench_busy = False


# ---------------------------------------------------------------------------------------------------------- module level
_server: LocalServer | None = None
_server_key: tuple[Any, ...] | None = None
_srv_lock = threading.Lock()


def get_server() -> LocalServer:
    global _server, _server_key
    with _srv_lock:
        key = LocalServer.config_key()
        if _server is None or key != _server_key:
            _server, _server_key = LocalServer(), key
        return _server


def mode() -> str:
    """``"model"`` when a digest call would use the local model, ``"rules"`` otherwise. Side-effect free: it never starts the
    server and never hashes the model. (The first digest call starts the server lazily; a failed start flips this to rules
    for a minute.)"""
    return "model" if get_server().unavailable_reason() is None else "rules"


def shutdown() -> None:
    """Stop the server if this process started it or a pid file says one of ours is running. Safe to call at any time."""
    get_server().stop()
