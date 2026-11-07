from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path, monkeypatch):
    """No insights test touches the shared data/ directory or the real home, none reaches the network, none calls a model."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for flag in ("UNDERSTUDY_X", "UNDERSTUDY_X_INSIGHTS"):
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
            raise AssertionError(f"insights tests may not open a network connection: {addr!r}")
        return real_connect(self, addr, *a, **k)

    def create(addr, *a, **k):
        if not is_loopback(addr):
            raise AssertionError(f"insights tests may not open a network connection: {addr!r}")
        return real_create(addr, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create)
    yield
