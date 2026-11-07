"""No engine test may talk to the live stack. A throwaway engine, a TestClient or a stray httpx call that reaches 127.0.0.1:7700 or
:7710 would hit the owner's running services (it once forwarded /kill to the live agent and stopped the whole dev stack). This guard
fails the test that tries, at the socket. Tests that need a server use an ephemeral port or an in-process client."""
from __future__ import annotations

import socket

import pytest

LIVE_PORTS = frozenset({7700, 7710})
LOCAL = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", ""})


def _is_live(address) -> bool:
    try:
        host, port = address[0], address[1]
    except (TypeError, IndexError):
        return False
    return isinstance(port, int) and port in LIVE_PORTS and str(host) in LOCAL


@pytest.fixture(autouse=True)
def _relaxed_release_guard(monkeypatch):
    """The repo's engine tests call release routes (approve, consent, kill/clear) without the per-boot token. This switch lets a local
    request with no Origin through for them; anything with an Origin, and every foreign Host, is judged as in production. Tests of the
    guard itself set UNDERSTUDY_GUARD_STRICT=1. The reviewers' tests under evals/review do not run through this file, so they see production."""
    monkeypatch.setenv("UNDERSTUDY_TEST_RELAXED_GUARD", "1")
    yield


@pytest.fixture(autouse=True)
def _never_touch_the_live_stack(monkeypatch):
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def connect(self, address):
        if _is_live(address):
            raise AssertionError(f"a test tried to connect to {address[0]}:{address[1]}, the live engine or agent port. Use AGENT_PORT=1 / an ephemeral port / an in-process client.")
        return real_connect(self, address)

    def connect_ex(self, address):
        if _is_live(address):
            raise AssertionError(f"a test tried to connect to {address[0]}:{address[1]}, the live engine or agent port.")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    yield
