"""Start the three sandbox sites in one process (ports 7801 to 7803, or ephemeral ports in tests).

    uv run python -m understudy_agent.sandbox_sites          # serves 7801, 7802, 7803 until Ctrl-C
"""
from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field

import uvicorn

from .sites import SandboxState, make_apps
from .specs import DEFAULT_PORTS, HOST, SITE_IDS


def free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


@dataclass
class SandboxCluster:
    """Owns the three uvicorn servers. `ephemeral=True` binds free ports (for tests)."""

    ephemeral: bool = False
    ports: dict[str, int] = field(default_factory=dict)
    state: SandboxState = field(default_factory=SandboxState)

    def __post_init__(self) -> None:
        if not self.ports:
            self.ports = {s: (free_port() if self.ephemeral else DEFAULT_PORTS[s]) for s in SITE_IDS}
        self._servers: list[uvicorn.Server] = []
        self._threads: list[threading.Thread] = []
        self._socks: list[socket.socket] = []

    @property
    def urls(self) -> dict[str, str]:
        return {s: f"http://{HOST}:{self.ports[s]}" for s in SITE_IDS}

    def start(self, timeout: float = 10.0) -> "SandboxCluster":
        apps = make_apps(self.state, self.ports)
        for s in SITE_IDS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((HOST, self.ports[s]))
            sock.listen(128)
            self._socks.append(sock)
            cfg = uvicorn.Config(apps[s], log_level="error", lifespan="off", access_log=False)
            server = uvicorn.Server(cfg)
            t = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True,
                                 name=f"sandbox-{s}")
            t.start()
            self._servers.append(server)
            self._threads.append(t)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all(sv.started for sv in self._servers):
                return self
            time.sleep(0.02)
        self.stop()
        raise RuntimeError("sandbox sites did not start in time")

    def stop(self) -> None:
        for sv in self._servers:
            sv.should_exit = True
        for t in self._threads:
            t.join(timeout=5)
        for sock in self._socks:
            try:
                sock.close()
            except OSError:
                pass
        self._servers, self._threads, self._socks = [], [], []

    def __enter__(self) -> "SandboxCluster":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()


def main() -> None:  # pragma: no cover - manual use
    cluster = SandboxCluster().start()
    print("sandbox sites:", ", ".join(f"{s}={u}" for s, u in cluster.urls.items()), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        cluster.stop()


class RemoteState:
    """Same reset/snapshot interface as SandboxState, for sites that run in another process (the shared 7801-7803)."""

    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def reset(self) -> None:
        import httpx

        httpx.post(self.base + "/__reset", timeout=3)

    def snapshot(self) -> dict:
        import httpx

        return httpx.get(self.base + "/__state", timeout=3).json()


@dataclass
class SharedSites:
    """The sandbox sites already running on 7801 to 7803. Take `sandbox_lock` around a batch that uses them."""

    ports: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_PORTS))

    @property
    def urls(self) -> dict[str, str]:
        return {s: f"http://{HOST}:{self.ports[s]}" for s in SITE_IDS}

    @property
    def state(self) -> RemoteState:
        return RemoteState(self.urls["a"])

    def __enter__(self) -> "SharedSites":
        import httpx

        try:
            httpx.get(self.urls["a"] + "/healthz", timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("the shared sandbox sites are not running: uv run python -m understudy_agent.sandbox_sites") from exc
        return self

    def __exit__(self, *exc: object) -> None:
        return None
