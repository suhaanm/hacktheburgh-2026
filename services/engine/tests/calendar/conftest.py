from __future__ import annotations

import pytest

from understudy_engine.calendar import store as cal_store
from understudy_engine.calendar import synth


@pytest.fixture(autouse=True)
def _hermetic_env(tmp_path_factory, monkeypatch):
    """No test here may touch the shared data/ directory or the real ~/.understudy, and none may reach the network."""
    root = tmp_path_factory.mktemp("hermetic")
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("UNDERSTUDY_HOME", str(root / "home"))
    monkeypatch.delenv("UNDERSTUDY_GRAPH", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X", raising=False)
    monkeypatch.delenv("UNDERSTUDY_X_CALENDAR", raising=False)
    cal_store.reset_default()
    yield
    cal_store.reset_default()


@pytest.fixture(scope="session")
def synth_root(tmp_path_factory):
    """Deterministic synthetic calendars (normal and canary variants) in a tmp dir, generated once per session."""
    root = tmp_path_factory.mktemp("calsynth")
    synth.generate(root)
    synth.generate(root, canary=True)
    return root


@pytest.fixture(scope="session")
def store(synth_root):
    return cal_store.CalendarStore(synth_root)


@pytest.fixture(scope="session")
def canary_store(synth_root):
    return cal_store.CalendarStore(synth_root, canary=True)
