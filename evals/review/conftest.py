"""Shared hermetic guard for EVERY reproducer under evals/review/ (safety and privacy). Added after a real data/KILL appeared in the repo at 17:34.
* UNDERSTUDY_DATA_DIR and UNDERSTUDY_HOME point at the test's tmp_path, so nothing can read or write <repo>/data or ~/.understudy
* any socket connect to a live service port (7700 engine, 7710 agent, 7720 ext server, 5173 dashboard, 7801-7803 sandbox sites) raises
* the test FAILS if <repo>/data/KILL exists afterwards and did not exist before (and it is never created here)
In-process TestClients do not open sockets, so they keep working; anything that tries the real network on those ports is a bug in the test."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO_DATA = Path(__file__).resolve().parents[2] / "data"
LIVE_PORTS = {7700, 7710, 7720, 5173, 7801, 7802, 7803}


@pytest.fixture(autouse=True)
def review_hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_PORT", "1")                                    # engine -> agent notifications go nowhere
    monkeypatch.setenv("ENGINE_PORT", "1")
    monkeypatch.setenv("UNDERSTUDY_AGENT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("ENGINE_URL", "http://127.0.0.1:1")
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def refuse(address) -> None:
        if isinstance(address, tuple) and len(address) >= 2 and address[1] in LIVE_PORTS:
            raise AssertionError(f"TRIPWIRE: a review test tried to connect to live port {address[1]}")

    monkeypatch.setattr(socket.socket, "connect", lambda self, address: (refuse(address), real_connect(self, address))[1])
    monkeypatch.setattr(socket.socket, "connect_ex", lambda self, address: (refuse(address), real_connect_ex(self, address))[1])
    existed = (REPO_DATA / "KILL").exists()
    yield
    if not existed:
        assert not (REPO_DATA / "KILL").exists(), "a review test left data/KILL in the REAL data dir"
