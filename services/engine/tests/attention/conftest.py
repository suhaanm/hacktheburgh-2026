from __future__ import annotations

import socket
from datetime import datetime, timezone

import pytest

from understudy_engine.attention import vocab as V
from understudy_engine.attention.events import Event
from understudy_engine.attention.service import AttentionService
from understudy_engine.attention.state import Settings, WorkerState
from understudy_engine.attention.store import AttentionStore

T0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc).timestamp()      # a Monday, 10:00 UTC
P = "p_test01"


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path, monkeypatch):
    """No attention test touches the shared data/ directory or the real home, none reaches the network, none calls a model."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    monkeypatch.delenv("UNDERSTUDY_ATTENTION_LEVEL_GLANCE", raising=False)
    for flag in ("UNDERSTUDY_X", "UNDERSTUDY_X_ATTENTION"):
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


def ws(now: float = T0, **kw) -> WorkerState:
    """A calm, present worker at a natural break (quiet 60 s, no task), local hour 10. Override anything."""
    base = dict(known=True, quiet_s=60.0, local_hour=10)
    base.update(kw)
    return WorkerState(now=now, **base)


def busy(now: float = T0, **kw) -> WorkerState:
    """Typing right now."""
    return ws(now, typing_burst=True, quiet_s=0.4, **kw)


def ev(type_: str, subject: str = "s1", **kw) -> Event:
    return Event(type=type_, person=P, subject=subject, **kw)


@pytest.fixture()
def svc():
    return AttentionService(AttentionStore(), clock=lambda: T0)


def settings(**modes) -> Settings:
    return Settings(modes=dict(modes))
