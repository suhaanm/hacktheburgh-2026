"""Connections tests: hermetic and offline. Only OUR stand-in servers and test servers (written with the official SDK) are ever started, as local
subprocesses; nothing from the network, no real account, no Keychain, no real desktop input. Every test gets its own data dir and home."""
from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

TEST_SERVERS = Path(__file__).resolve().parent / "servers"


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_SECRET_BACKEND", "file")
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.setenv("UNDERSTUDY_AGENT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    for k in ("KNACK_STANDIN_POISON", "UNDERSTUDY_X_CONNECTIONS", "UNDERSTUDY_PRESETS_DIR"):
        monkeypatch.delenv(k, raising=False)
    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect, real_create = socket.socket.connect, socket.create_connection

    def ok(addr) -> bool:
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        return host in ("127.0.0.1", "::1", "localhost") or str(host).startswith("/")

    def connect(self, addr, *a, **k):
        if not ok(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        if isinstance(addr, tuple) and len(addr) > 1 and addr[1] in (7700, 7710, 5173):
            raise AssertionError(f"a test tried to reach the live stack on port {addr[1]}")
        return real_connect(self, addr, *a, **k)

    def create(addr, *a, **k):
        if not ok(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        return real_create(addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create)


@pytest.fixture()
def runner():
    from understudy_agent.connections.runner import ConnectionRunner

    r = ConnectionRunner()
    yield r
    r.stop_all()


@pytest.fixture()
def service(runner):
    from understudy_agent.connections.service import ConnectionService

    return ConnectionService(runner)


@pytest.fixture()
def connect_example():
    """Switch an EXAMPLE connection on the way the worker's click does (consent recorded, hash pinned). Nothing else ever does."""
    from understudy_engine.connections import registry, state

    def go(conn_id: str):
        state.connect(registry.get(conn_id), mode="example", confirm=True)
        return registry.get(conn_id)

    return go


def env_keys() -> set[str]:
    return set(os.environ)
