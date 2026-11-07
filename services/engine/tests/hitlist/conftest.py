"""Hermetic fixtures for the hit list tests: temp data and home dirs, mock mode, a fixed clock, no network, no model."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import pytest

from understudy_engine.core import Cog, Episode
from understudy_engine.memory import load_pack

DAY = 86400.0
NOW = datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc).timestamp()
P = "p_hit01"

CALC = ["OPEN_CALCULATOR", "ENTER_HOUSEHOLD", "READ_RESULT"] * 3            # the benefits pack's calc-entry-3x
NOTE = ["READ_RESULT", "COPY_TO_NOTE", "READ_RESULT", "COPY_TO_NOTE"]       # case-note-copy


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    for flag in ("UNDERSTUDY_X", "UNDERSTUDY_X_HITLIST"):
        monkeypatch.delenv(flag, raising=False)

    real_connect = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise AssertionError(f"a hit list test tried to reach {host}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    yield


@pytest.fixture(scope="session")
def pack():
    return load_pack("benefits-processor")


def ep(seq, t0, dur=40.0, person=P, task="t") -> Episode:
    """One episode: ``seq`` cogs, each lasting ``dur / len(seq)`` seconds, starting at unix ``t0``."""
    step = dur / len(seq)
    cogs = [Cog(t0 + i * step, t0 + (i + 1) * step, c) for i, c in enumerate(seq)]
    return Episode(task_id=task, person=person, role="benefits-processor", origin="synthetic", t0=t0, t1=t0 + dur, cogs=cogs)


def many(seq, n, *, days_back=1.0, spread_days=5.0, dur=40.0, prefix="x", now=NOW, slip=None):
    """``n`` episodes of ``seq`` spread over ``spread_days`` days that end ``days_back`` days before ``now``. ``slip(i, seq)`` may return
    a changed sequence for episode ``i``. Task ids are unique per prefix."""
    out = []
    for i in range(n):
        t0 = now - days_back * DAY - spread_days * DAY * (i / max(n - 1, 1)) - 600 * (i % 3)
        s = list(slip(i, list(seq))) if slip else list(seq)
        out.append(ep(s, t0, dur=dur, task=f"{prefix}{i}"))
    return out
