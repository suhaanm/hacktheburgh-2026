"""Hermetic setup for the Clicky-lift tests (CLK-1): standard library only, fake clocks, a private data dir per test.

`vendor/clicky` is not installed as a package yet, so it is put on sys.path here. Nothing in these tests touches the
real data/ directory, the network, the real ~/.understudy, or anything under references/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
VENDOR = REPO / "vendor" / "clicky"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))


class FakeClock:
    """A settable monotonic clock."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(data))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("UNDERSTUDY_MOCK", "1")
    real_kill = REPO / "data" / "KILL"
    had = real_kill.exists()
    yield
    if not had:
        assert not real_kill.exists(), "a test left data/KILL in the REAL data dir"
