from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path, monkeypatch):
    """No test here may touch the shared data/ directory, the real ~/.understudy or the real Keychain, and none may reach the network."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_SECRET_BACKEND", "file")
    monkeypatch.setenv("UNDERSTUDY_AGENT_URL", "http://127.0.0.1:1")      # nothing listens there: the routes see an agent that is not running
    monkeypatch.setenv("AGENT_PORT", "1")                                 # the engine's health probe of the agent goes nowhere either, never to 7710
    monkeypatch.setenv("ENGINE_PORT", "1")
    monkeypatch.delenv("UNDERSTUDY_REPO_ROOT", raising=False)
    monkeypatch.delenv("UNDERSTUDY_MOCK", raising=False)
    for flag in ("UNDERSTUDY_X", "UNDERSTUDY_X_CONNECTIONS", "UNDERSTUDY_PRESETS_DIR"):
        monkeypatch.delenv(flag, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def is_loopback(addr) -> bool:
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        return host in ("127.0.0.1", "::1", "localhost") or str(host).startswith("/")

    def connect(self, addr, *a, **k):
        if not is_loopback(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        return real_connect(self, addr, *a, **k)

    def create(addr, *a, **k):
        if not is_loopback(addr):
            raise AssertionError(f"a test tried to open a network connection to {addr!r}")
        return real_create(addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create)
